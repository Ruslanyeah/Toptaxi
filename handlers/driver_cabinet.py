from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from aiogram.filters import Command, BaseFilter, StateFilter
from typing import Callable, Any
from keyboards.reply_keyboards import get_driver_cabinet_keyboard
from keyboards.driver_keyboards import (
    get_driver_reviews_keyboard, get_driver_rejections_keyboard,
    get_driver_history_keyboard, get_preorder_list_keyboard, get_preorder_details_keyboard,
    get_my_preorders_keyboard, get_my_preorder_details_keyboard
)
from keyboards.common import Navigate
from utils.callback_factories import (
    PreOrderListPaginator, PreOrderDetails, PreOrderAction, DriverReviewsPaginator,
    DriverRejectionPaginator, DriverRejectionDetails, DriverHistoryPaginator,
    TripDetailsCallbackData, MyPreordersPaginator, MyPreorderAction
)
from dateutil import parser
import html
from datetime import datetime, timedelta
from loguru import logger
from database import queries as db_queries
from states.fsm_states import DriverState
from handlers.shared_state import location_requests
from handlers.common.helpers import send_message_with_photo
from handlers.common.helpers import safe_edit_or_send
from .common.paginator import show_paginated_list
from aiogram.exceptions import TelegramBadRequest
from config.config import TIMEZONE, BASE_DIR

class IsDriver(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        """
        Checks if the user is a registered driver.
        """
        return await db_queries.is_driver(message.from_user.id)

router = Router()

DRIVER_CABINET_IMAGE_PATH = BASE_DIR / "assets" / "images" / "driver_cabinet.jpg"
TRIP_DETAILS_IMAGE_PATH = BASE_DIR / "assets" / "images" / "trip_details.jpg"

# --- Generic Paginator and Formatter ---

def _format_driver_reviews(reviews: list[dict[str, Any]]) -> str:
    """
    Formats a list of driver reviews for display.

    Args:
        reviews: A list of review dictionaries from the database.

    Returns:
        A formatted string of reviews.
    """
    text = ""
    for review in reviews:
        date_str = parser.parse(review['completed_at']).strftime('%d.%m.%Y')
        text += (
            f"<b>{date_str} | {'⭐' * review['rating_score']}</b>\n"
            f"<i>«{html.escape(review['rating_comment'])}»</i>\n---\n"
        )
    return text

async def get_driver_cabinet_text_and_keyboard(user_id: int) -> tuple[str, types.ReplyKeyboardMarkup | None]:
    """
    Generates the content and keyboard for the driver's cabinet.

    Args:
        user_id: The Telegram ID of the driver.

    Returns:
        A tuple containing the cabinet text and the corresponding reply keyboard.
    """
    user_data, overall_completed = await db_queries.get_user_cabinet_data(user_id)
    if not user_data or not user_data['driver_user_id']:
        return "Не вдалося знайти ваші дані водія. Зверніться до адміністратора.", None

    on_shift = user_data['shift_started_at'] is not None
    is_available = user_data['isWorking'] == 1

    if not on_shift:
        status_text = "🔴 Відпочиваєте"
    elif is_available:
        status_text = "🟢 На зміні (приймаєте замовлення)"
    else: # on_shift and not is_available
        status_text = "🟡 На зміні (тимчасово недоступні)"

    rating = user_data['rating']
    rating_count = user_data['rating_count']
    rating_str = f"{rating:.1f} ⭐ ({rating_count} оцінок)" if rating_count > 0 else "немає"

    response_text = (
        f'<b>🚕 Ласкаво просимо до кабінету водія!</b>\n\n'
        f'<b>Ваш статус: </b>{status_text}\n'
        f'<b>Ваш рейтинг: </b>{rating_str}\n\n'
        '<b>--- Статистика поїздок ---</b>\n'
    )

    # Статистика за зміну
    if on_shift and user_data['shift_started_at']:
        response_text += f"<b>За поточну зміну:</b> {user_data['shift_completed']} завершено\n"
    else:
        response_text += "<b>За поточну зміну:</b> 0 завершено (зміна не активна)\n"

    # Загальна статистика
    response_text += f"<b>За весь час:</b> {overall_completed} завершено\n"
    response_text += f"<b>Скасовано вами (за весь час):</b> {user_data['cancelled_count'] or 0} замовлень\n"

    return response_text, get_driver_cabinet_keyboard(on_shift, is_available)

@router.message(Command('driver'))
@router.message(F.text == '🚕 Для водіїв')
async def driver_cabinet_handler(message: types.Message) -> None:
    """
    Handles entry into the driver's cabinet via command or reply keyboard.

    Args:
        message: The user's message.
    """
    text, kb = await get_driver_cabinet_text_and_keyboard(message.from_user.id) # The IsDriver filter is now on the router
    await send_message_with_photo(message, DRIVER_CABINET_IMAGE_PATH, text, kb)

@router.callback_query(Navigate.filter(F.to == "back_to_driver_cabinet"))
async def back_to_driver_cabinet_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Back to Driver Cabinet" inline button from various sub-menus.

    Args:
        call: The callback query.
    """
    text, kb = await get_driver_cabinet_text_and_keyboard(call.from_user.id)
    # We cannot edit a message to change its keyboard type from Inline to Reply.
    # We must delete the old message and send a new one.
    await send_message_with_photo(call, DRIVER_CABINET_IMAGE_PATH, text, kb, delete_old=True)
    await call.answer()

@router.message(F.text == '🚀 Почати зміну')
async def start_shift_handler(message: types.Message, state: FSMContext) -> None:
    """
    Handles the "Start Shift" button, prompting the driver to share their live location.

    Args:
        message: The user's message.
        state: The FSM context.
    """
    await state.set_state(DriverState.waiting_for_location)

    await message.answer(
        "<b>Увага! Обов'язкова умова для початку зміни!</b>\n\n"
        "Щоб почати роботу, ви повинні увімкнути <b>трансляцію вашої геолокації</b> в цьому чаті.\n\n"
        "<b>Як це зробити:</b>\n"
        "1. Натисніть на скріпку (📎) внизу екрана.\n"
        "2. Оберіть 'Геопозиція' або 'Location'.\n"
        "3. Натисніть 'Транслювати мою геопозицію' або 'Share My Live Location'.\n\n"
        "Після цього ваша зміна розпочнеться автоматично.",
        reply_markup=types.ReplyKeyboardMarkup(keyboard=[
            [types.KeyboardButton(text="🔙 Повернутися в меню")]],
        resize_keyboard=True,
        one_time_keyboard=True
        )
    )

@router.message(DriverState.waiting_for_location, F.location, F.location.live_period.is_not(None))
async def process_live_location_for_shift(message: types.Message, state: FSMContext) -> None:
    """
    Receives the live location and starts the driver's shift.

    Args:
        message: The message containing the live location.
        state: The FSM context.
    """
    driver_id = message.from_user.id
    await db_queries.update_driver_location(driver_id, message.location.latitude, message.location.longitude)
    await db_queries.start_driver_shift(driver_id)
    await state.clear()
    await message.answer(
        "✅ <b>Трансляцію отримано!</b>\n\nВи почали зміну. Очікуйте на нові замовлення.",
        reply_markup=get_driver_cabinet_keyboard(on_shift=True, is_available=True)
    )

@router.message(DriverState.waiting_for_location, F.location)
async def process_wrong_location_for_shift(message: types.Message) -> None:
    """
    Catches a regular location when a live location is expected and informs the driver.

    Args:
        message: The message containing the regular location.
    """
    await message.answer(
        "❌ <b>Неправильний тип геолокації!</b>\n\n"
        "Ви надіслали одноразову геопозицію. Для роботи необхідно увімкнути саме **трансляцію**.\n\n"
        "Будь ласка, дотримуйтесь інструкції: натисніть 📎 -> Геопозиція -> **Транслювати мою геопозицію**."
    )

@router.message(DriverState.waiting_for_location)
async def wrong_input_for_shift_location(message: types.Message) -> None:
    """
    Catches any other input while waiting for a location.

    Args:
        message: The user's message.
    """
    await message.answer("Будь ласка, увімкніть **трансляцію** вашої геолокації, щоб почати зміну.")

@router.message(F.location, IsDriver(), StateFilter(None))
@router.edited_message(F.location, IsDriver(), StateFilter(None))
async def unified_location_update_handler(message: types.Message) -> None:
    """
    Handles location updates from drivers who are not in an FSM state.
    This covers admin requests and live location updates for on-shift drivers.
    It works for both new and edited messages.
    """
    driver_id = message.from_user.id

    # Case 1: This is a response to an admin's on-demand request
    if driver_id in location_requests:
        admin_id = location_requests.pop(driver_id) # Get admin_id and remove the request
        try:
            await message.bot.send_message(admin_id, f"📍 Водій ID <code>{driver_id}</code> надіслав свою геолокацію:")
            await message.bot.send_location(admin_id, latitude=message.location.latitude, longitude=message.location.longitude)
            
            # Просто получаем актуальный текст и клавиатуру
            text, kb = await get_driver_cabinet_text_and_keyboard(driver_id)
            await message.answer("✅ Вашу геолокацію надіслано адміністратору.", reply_markup=kb)
        except Exception as e:
            logger.error(f"Не вдалося переслати геолокацію адміну {admin_id}: {e}")
        return # Stop further processing

    # Case 2: This is a regular live location update from an on-shift driver
    if message.location and message.location.live_period and await db_queries.is_driver_on_shift(driver_id):
        await db_queries.update_driver_location(driver_id, message.location.latitude, message.location.longitude)
        logger.info(f"Live location for driver {driver_id} updated.")
        # No need to send a message back to the driver, it would be spammy.

@router.message(F.text == '⛔️ Завершити зміну')
async def stop_shift_handler(message: types.Message) -> None:
    """
    Handles the "End Shift" button.

    Args:
        message: The user's message.
    """
    await db_queries.stop_driver_shift(message.from_user.id)
    await message.answer("✅ Ви завершили зміну. Дякуємо за роботу!", reply_markup=get_driver_cabinet_keyboard(on_shift=False, is_available=False))

@router.message(F.text == '⏸️ Тимчасово недоступний')
async def set_unavailable_handler(message: types.Message) -> None:
    """
    Handles the "Temporarily Unavailable" button, pausing order reception.

    Args:
        message: The user's message.
    """
    await db_queries.set_driver_availability(message.from_user.id, is_available=False)
    text, kb = await get_driver_cabinet_text_and_keyboard(message.from_user.id)
    await message.answer("🟡 Ви тимчасово недоступні та не будете отримувати нові замовлення.", reply_markup=kb)

@router.message(F.text == '▶️ Повернутись до замовлень')
async def set_available_handler(message: types.Message) -> None:
    """
    Handles the "Return to Orders" button, resuming order reception.

    Args:
        message: The user's message.
    """
    await db_queries.set_driver_availability(message.from_user.id, is_available=True)
    text, kb = await get_driver_cabinet_text_and_keyboard(message.from_user.id)
    await message.answer("🟢 Ви знову приймаєте замовлення.", reply_markup=kb)

# --- Driver Reviews Handlers ---

REVIEWS_PER_PAGE = 5

async def show_driver_reviews_page(target: types.Message | types.CallbackQuery, page: int) -> None:
    """
    Displays a paginated list of the driver's reviews.

    Args:
        target: The message or callback object to answer to.
        page: The page number to display.
    """
    driver_id = target.from_user.id
    
    user_data, _ = await db_queries.get_user_cabinet_data(driver_id)
    if not user_data or not user_data['driver_user_id']:
        # Determine how to send the message based on the target type
        reply_target = target.message if isinstance(target, types.CallbackQuery) else target
        await reply_target.answer("Не вдалося завантажити дані водія.", reply_markup=get_driver_cabinet_keyboard(on_shift=False, is_available=False))
        return

    rating = user_data['rating']
    rating_count = user_data['rating_count']
    rating_str = f"{rating:.1f} ⭐ ({rating_count} оцінок)" if rating_count > 0 else "немає"
    
    header_text = (
        f'<b>⭐ Мій рейтинг та відгуки</b>\n\n'
        f'<b>Загальний рейтинг:</b> {rating_str}\n'
    )

    no_items_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ До кабінету водія", callback_data="back_to_driver_cabinet")]
    ])

    await show_paginated_list(
        target=target, page=page,
        count_func=db_queries.get_driver_reviews_count, page_func=db_queries.get_driver_reviews_page,
        keyboard_func=get_driver_reviews_keyboard, title="Відгуки", items_per_page=REVIEWS_PER_PAGE,
        no_items_text=header_text + '\nУ вас ще немає відгуків з коментарями.',
        no_items_keyboard=no_items_kb,
        prefix_text=header_text, list_formatter=_format_driver_reviews,
        count_func_kwargs={'driver_id': driver_id}, page_func_kwargs={'driver_id': driver_id}
    )

@router.message(F.text == '⭐ Мої рейтинг та відгуки')
async def driver_reviews_handler(message: types.Message) -> None:
    """
    Handles the "My Rating and Reviews" button.

    Args:
        message: The user's message.
    """
    await show_driver_reviews_page(message, page=0)

@router.callback_query(DriverReviewsPaginator.filter())
async def paginate_driver_reviews(call: types.CallbackQuery, callback_data: DriverReviewsPaginator) -> None:
    """
    Handles pagination for the driver's reviews list.

    Args:
        call: The callback query from pagination buttons.
        callback_data: The paginator callback data.
    """
    await show_driver_reviews_page(call, page=callback_data.page)

# --- Driver Rejections History Handlers ---

REJECTIONS_PER_PAGE = 5

async def show_driver_rejections_page(target: types.Message | types.CallbackQuery, page: int) -> None:
    """
    Displays a paginated list of the driver's order rejections.

    Args:
        target: The message or callback object to answer to.
        page: The page number to display.
    """
    driver_id = target.from_user.id
    no_items_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ До кабінету водія", callback_data="back_to_driver_cabinet")]
    ])

    await show_paginated_list(
        target=target, page=page,
        count_func=db_queries.get_driver_rejections_count,
        page_func=db_queries.get_driver_rejections_page,
        keyboard_func=get_driver_rejections_keyboard,
        title="↪️ Історія відмов", items_per_page=REJECTIONS_PER_PAGE,
        no_items_text='<b>↪️ Історія відмов</b>\n\nУ вас немає відмов від замовлень.',
        no_items_keyboard=no_items_kb,
        item_list_title="Це замовлення, від яких ви відмовились. Оберіть замовлення для перегляду деталей:",
        count_func_kwargs={'driver_id': driver_id}, page_func_kwargs={'driver_id': driver_id},
        items_list_kwarg_name='rejections'
    )

@router.message(F.text == '↪️ Історія відмов')
async def driver_rejections_history_handler(message: types.Message) -> None:
    """
    Handles the "Rejection History" button.

    Args:
        message: The user's message.
    """
    await show_driver_rejections_page(message, page=0)

@router.callback_query(DriverRejectionPaginator.filter())
async def paginate_driver_rejections(call: types.CallbackQuery, callback_data: DriverRejectionPaginator) -> None:
    """
    Handles pagination for the driver's rejections list.

    Args:
        call: The callback query from pagination buttons.
        callback_data: The paginator callback data.
    """
    await show_driver_rejections_page(call, page=callback_data.page)

@router.callback_query(DriverRejectionDetails.filter())
async def show_driver_rejection_details(call: types.CallbackQuery, callback_data: DriverRejectionDetails) -> None:
    """
    Displays detailed information about a specific rejected order.

    Args:
        call: The callback query from a specific rejection button.
        callback_data: The callback data containing the order ID.
    """
    order_id = callback_data.order_id
    order_data = await db_queries.get_rejected_order_details_for_driver(order_id, call.from_user.id)
    if not order_data:
        await call.answer("Не вдалося знайти інформацію про це замовлення або у вас немає доступу.", show_alert=True)
        return

    client_id = order_data['client_id']
    client_name = await db_queries.get_client_name(client_id)
    client_stats = await db_queries.get_client_stats(client_id)

    date_str = parser.parse(order_data['created_at']).strftime('%d.%m.%Y о %H:%M')

    details_text = (
        f"<b>Деталі замовлення №{order_id} (від якого ви відмовились)</b>\n\n"
        f"<b>Дата замовлення:</b> {date_str}\n"
        f"<b>Звідки:</b> {html.escape(order_data['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order_data['finish_address'])}\n\n"
        f"<b>--- Інформація про клієнта ---</b>\n"
        f"<b>Ім'я:</b> {html.escape(client_name or 'Невідомо')}\n"
        f"<b>ID:</b> <code>{client_id}</code>\n"
        f"<b>Успішних поїздок:</b> {client_stats['finish_applic'] if client_stats else 'N/A'}\n"
        f"<b>Скасувань:</b> {client_stats['cancel_applic'] if client_stats else 'N/A'}\n"
    )
    back_kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад до історії відмов", callback_data=Navigate(to="driver_rejections_history_msg").pack())]])
    await safe_edit_or_send(call, details_text, reply_markup=back_kb)
    await call.answer()

@router.callback_query(Navigate.filter(F.to == "driver_rejections_history_msg"))
async def driver_rejections_history_msg_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Back to Rejection History" button from the details view.

    Args:
        call: The callback query.
    """
    await show_driver_rejections_page(call, page=0)

# --- Pre-Order List Handlers ---

PREORDERS_PER_PAGE = 5

async def show_preorder_list_page(target: types.Message | types.CallbackQuery, page: int) -> None:
    """
    Displays a paginated list of available pre-orders for drivers to accept.

    Args:
        target: The message or callback object to answer to.
        page: The page number to display.
    """
    no_items_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ До кабінету водія", callback_data="back_to_driver_cabinet")]
    ])

    # Встановлюємо часові рамки для показу замовлень:
    # - Не раніше поточного моменту (щоб не показувати минулі)
    # - Не пізніше, ніж через 48 годин (щоб не захаращувати список)
    now = datetime.now(TIMEZONE)
    time_limit = now + timedelta(hours=48)
    
    min_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
    max_time_str = time_limit.strftime('%Y-%m-%d %H:%M:%S')

    await show_paginated_list(
        target=target,
        page=page,
        count_func=db_queries.get_available_preorders_count,
        page_func=db_queries.get_available_preorders_page,
        keyboard_func=get_preorder_list_keyboard,
        title="🗓️ Доступні заплановані замовлення",
        items_per_page=PREORDERS_PER_PAGE,
        no_items_text="Наразі немає доступних для взяття запланованих замовлень на найближчий час.",
        no_items_keyboard=no_items_kb,
        item_list_title="Оберіть замовлення, щоб подивитись деталі:",
        items_list_kwarg_name='orders',
        count_func_kwargs={'min_datetime': min_time_str, 'max_datetime': max_time_str},
        page_func_kwargs={'min_datetime': min_time_str, 'max_datetime': max_time_str}
    )

@router.message(F.text == '🗓️ Доступні заплановані')
async def scheduled_orders_list_handler(message: types.Message) -> None:
    """
    Handles the "Scheduled Orders" button.

    Args:
        message: The user's message.
    """
    await show_preorder_list_page(message, page=0)

@router.callback_query(Navigate.filter(F.to == "scheduled_orders_list"))
async def scheduled_orders_list_callback_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Back to Scheduled List" button from the details view.

    Args:
        call: The callback query.
    """
    await show_preorder_list_page(call, page=0)

@router.callback_query(PreOrderListPaginator.filter())
async def paginate_preorder_list(call: types.CallbackQuery, callback_data: PreOrderListPaginator) -> None:
    """
    Handles pagination for the available pre-orders list.

    Args:
        call: The callback query from pagination buttons.
        callback_data: The paginator callback data.
    """
    await show_preorder_list_page(call, page=callback_data.page)

@router.callback_query(PreOrderDetails.filter())
async def show_preorder_details(call: types.CallbackQuery, callback_data: PreOrderDetails) -> None:
    """
    Displays detailed information about a specific available pre-order.

    Args:
        call: The callback query from a specific pre-order button.
        callback_data: The callback data containing the order ID.
    """
    order = await db_queries.get_order_details(callback_data.order_id)
    if not order or order['status'] != 'scheduled':
        await call.answer("Це замовлення вже недоступне.", show_alert=True)
        await show_preorder_list_page(call, page=0)
        return

    time_str = parser.parse(order['scheduled_at']).strftime('%d.%m.%Y о %H:%M')
    details_text = (
        f"<b>Деталі запланованого замовлення №{order['id']}</b>\n\n"
        f"<b>Час подачі:</b> {time_str}\n"
        f"<b>Звідки:</b> {html.escape(order['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order['finish_address'])}\n"
    )
    if order['comment']:
        details_text += f"<b>Коментар:</b> {html.escape(order['comment'])}\n"

    await safe_edit_or_send(call, details_text, reply_markup=get_preorder_details_keyboard(order['id']))
    await call.answer()

@router.callback_query(PreOrderAction.filter(F.action == 'accept'))
async def accept_preorder_handler(call: types.CallbackQuery, callback_data: PreOrderAction) -> None:
    """
    Handles a driver accepting a pre-order.

    Args:
        call: The callback query from the "Accept this order" button.
        callback_data: The callback data containing the order ID.
    """
    order_id = callback_data.order_id
    driver_id = call.from_user.id

    await db_queries.accept_preorder(order_id, driver_id)
    order = await db_queries.get_order_details(order_id)

    await call.answer("✅ Ви взяли це замовлення!", show_alert=True)
    await safe_edit_or_send(call, f"✅ Ви успішно взяли заплановане замовлення №{order_id}.\n\nМи нагадаємо вам про нього завчасно.")
    
    # Notify client
    if order and order['client_id']:
        await call.bot.send_message(order['client_id'], f"🎉 Чудові новини! На ваше заплановане замовлення №{order_id} вже призначено водія.")

# --- My Pre-Orders Handlers ---

MY_PREORDERS_PER_PAGE = 5

async def show_my_preorders_page(target: types.Message | types.CallbackQuery, page: int) -> None:
    """
    Displays a paginated list of the driver's own active pre-orders.
    """
    driver_id = target.from_user.id
    no_items_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ До кабінету водія", callback_data="back_to_driver_cabinet")]
    ])

    await show_paginated_list(
        target=target,
        page=page,
        count_func=db_queries.get_my_preorders_count,
        page_func=db_queries.get_my_preorders_page,
        keyboard_func=get_my_preorders_keyboard,
        title="🗓️ Мої заплановані замовлення",
        items_per_page=MY_PREORDERS_PER_PAGE,
        no_items_text="У вас немає прийнятих запланованих замовлень.",
        no_items_keyboard=no_items_kb,
        item_list_title="Ваші майбутні замовлення:",
        items_list_kwarg_name='orders',
        count_func_kwargs={'driver_id': driver_id},
        page_func_kwargs={'driver_id': driver_id}
    )

@router.message(F.text == '🗓️ Мої заплановані')
async def my_scheduled_orders_handler(message: types.Message) -> None:
    """
    Handles the "My Scheduled Orders" button.
    """
    await show_my_preorders_page(message, page=0)

@router.callback_query(Navigate.filter(F.to == "my_scheduled_orders_list"))
async def my_scheduled_orders_callback_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Back to My Scheduled List" button.
    """
    await show_my_preorders_page(call, page=0)

@router.callback_query(MyPreordersPaginator.filter())
async def paginate_my_preorders(call: types.CallbackQuery, callback_data: MyPreordersPaginator) -> None:
    """
    Handles pagination for the driver's own pre-orders list.
    """
    await show_my_preorders_page(call, page=callback_data.page)

@router.callback_query(MyPreorderAction.filter(F.action == 'details'))
async def show_my_preorder_details(call: types.CallbackQuery, callback_data: MyPreorderAction) -> None:
    """
    Displays detailed information about a driver's own pre-order.
    """
    order = await db_queries.get_order_details(callback_data.order_id)
    if not order or order['driver_id'] != call.from_user.id or order['status'] != 'accepted_preorder':
        await call.answer("Це замовлення вже недоступне або не належить вам.", show_alert=True)
        await show_my_preorders_page(call, page=0)
        return

    time_str = parser.parse(order['scheduled_at']).strftime('%d.%m.%Y о %H:%M')
    details_text = (
        f"<b>Деталі вашого замовлення №{order['id']}</b>\n\n"
        f"<b>Час подачі:</b> {time_str}\n"
        f"<b>Звідки:</b> {html.escape(order['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order['finish_address'])}\n"
    )
    if order['comment']:
        details_text += f"<b>Коментар:</b> {html.escape(order['comment'])}\n"
    
    await safe_edit_or_send(call, details_text, reply_markup=get_my_preorder_details_keyboard(order['id']))
    await call.answer()

@router.callback_query(MyPreorderAction.filter(F.action == 'cancel'))
async def cancel_my_preorder_handler(call: types.CallbackQuery, callback_data: MyPreorderAction) -> None:
    """Handles a driver cancelling their own accepted pre-order."""
    client_id = await db_queries.cancel_preorder_by_driver(callback_data.order_id, call.from_user.id)
    if client_id:
        await call.answer("✔️ Ви скасували замовлення. Воно знову доступне для інших водіїв.", show_alert=True)
        try:
            await call.bot.send_message(client_id, f"❗️ Увага! Водій скасував ваше заплановане замовлення №{callback_data.order_id}. Ми сповістимо вас, коли його прийме інший водій.")
        except Exception as e:
            logger.warning(f"Failed to send preorder cancellation notice to client {client_id}: {e}")
        await show_my_preorders_page(call, page=0)
    else:
        await call.answer("❌ Не вдалося скасувати замовлення. Можливо, воно вже неактуальне.", show_alert=True)
        await show_my_preorders_page(call, page=0)

# --- Driver Trip History Handlers ---

DRIVER_HISTORY_PER_PAGE = 5

async def show_driver_history_page(target: types.Message | types.CallbackQuery, page: int) -> None:
    """
    Displays a paginated list of the driver's completed trip history.

    Args:
        target: The message or callback object to answer to.
        page: The page number to display.
    """
    driver_id = target.from_user.id
    no_items_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ До кабінету водія", callback_data="back_to_driver_cabinet")]
    ])

    await show_paginated_list(
        target=target, page=page,
        count_func=db_queries.get_driver_orders_count,
        page_func=db_queries.get_driver_orders_page,
        keyboard_func=get_driver_history_keyboard,
        title="📖 Історія поїздок", items_per_page=DRIVER_HISTORY_PER_PAGE,
        no_items_text='<b>📖 Історія поїздок</b>\n\nУ вас ще немає завершених поїздок.',
        no_items_keyboard=no_items_kb,
        item_list_title="Оберіть поїздку, щоб переглянути деталі:",
        count_func_kwargs={'driver_id': driver_id}, page_func_kwargs={'driver_id': driver_id},
        items_list_kwarg_name='orders_on_page'
    )

@router.message(F.text == '📖 Історія поїздок водія')
async def driver_history_handler(message: types.Message) -> None:
    """
    Handles the "Driver Trip History" button.

    Args:
        message: The user's message.
    """
    await show_driver_history_page(message, page=0)

@router.callback_query(DriverHistoryPaginator.filter())
async def paginate_driver_history(call: types.CallbackQuery, callback_data: DriverHistoryPaginator) -> None:
    """
    Handles pagination for the driver's trip history.

    Args:
        call: The callback query from pagination buttons.
        callback_data: The paginator callback data.
    """
    await show_driver_history_page(call, page=callback_data.page)

@router.callback_query(TripDetailsCallbackData.filter(), IsDriver())
async def show_driver_trip_details(call: types.CallbackQuery, callback_data: TripDetailsCallbackData) -> None:
    """
    Displays detailed information about a specific past trip for the driver.

    Args:
        call: The callback query from a specific trip button.
        callback_data: The callback data containing the order ID.
    """
    order_id = callback_data.order_id
    order_data = await db_queries.get_driver_trip_details(order_id, call.from_user.id)
    if not order_data:
        await call.answer("Не вдалося знайти інформацію про цю поїздку.", show_alert=True)
        return

    created_at_str = order_data['created_at'].split('.')[0]
    rating_text = f"{order_data['rating_score']} ⭐" if order_data['is_rated'] and order_data['rating_score'] else "Не оцінено"

    details_text = (
        f"<b>Деталі поїздки №{order_id}</b>\n\n"
        f"<b>Дата:</b> {created_at_str}\n"
        f"<b>Звідки:</b> {html.escape(order_data['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order_data['finish_address'])}\n\n"
        f"<b>--- Клієнт ---</b>\n"
        f"<b>Ім'я:</b> {html.escape(order_data['client_name'])}\n"
        f"<b>Телефон:</b> <code>{html.escape(order_data['client_phone'] or 'Не вказано')}</code>\n\n"
        f"<b>Ваша оцінка від клієнта:</b> {rating_text}"
    )

    back_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад до історії", callback_data=Navigate(to="driver_history_msg").pack())]
    ])
    
    # Нельзя отредактировать сообщение со списком в сообщение с фото.
    # Поэтому удаляем старое и отправляем новое.
    await send_message_with_photo(call, TRIP_DETAILS_IMAGE_PATH, details_text, back_kb, delete_old=True)

    await call.answer()

@router.callback_query(Navigate.filter(F.to == "driver_history_msg"))
async def driver_history_msg_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Back to History" button from the trip details view.

    Args:
        call: The callback query.
    """
    await show_driver_history_page(call, page=0)
