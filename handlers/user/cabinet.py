from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from keyboards.user_keyboards import (
    get_cabinet_keyboard, get_user_history_keyboard, get_fav_addresses_manage_keyboard, 
    get_confirm_delete_fav_address_keyboard
)
from keyboards.reply_keyboards import main_menu_keyboard, fav_addr_name_skip_keyboard
from keyboards.common import Navigate
from utils.callback_factories import HistoryPaginator, TripDetailsCallbackData, FavAddressManage
from aiogram.filters import Command, StateFilter
from config.config import BASE_DIR, GEOCODING_CITY_CONTEXT
from handlers.common.helpers import send_message_with_photo
from handlers.common.helpers import safe_edit_or_send
import html
from states.fsm_states import FavAddressState
from database import queries as db_queries
from ..common.paginator import show_paginated_list
from dateutil import parser

# Bounding box для Сумської області, щоб пріоритезувати результати пошуку
# ((south_latitude, west_longitude), (north_latitude, east_longitude))
SUMY_OBLAST_VIEWBOX = ((50.35, 33.25), (51.9, 35.25))

router = Router()

CABINET_IMAGE_PATH = BASE_DIR / "assets" / "images" / "user_cabinet.jpg"

ORDERS_PER_PAGE = 5

async def get_cabinet_text_and_keyboard(user_id: int) -> tuple[str, types.InlineKeyboardMarkup | None]:
    """
    Generates the content and keyboard for the user's personal cabinet.

    Args:
        user_id: The Telegram ID of the user.

    Returns:
        A tuple containing the cabinet text and the corresponding inline keyboard.
    """
    client_stats = await db_queries.get_client_stats(user_id)
    if not client_stats:
        return "Не вдалося знайти ваші дані. Спробуйте натиснути /start", None

    response_text = (
        f'<b>Ласкаво просимо до особистого кабінету!</b>\n\n'
        f'<b>Статус: </b>🚘Клієнт🚘\n'
    )

    response_text += f'\n<b>Кількість успішних поїздок: </b>{client_stats["finish_applic"]}\n'
    response_text += f'<b>Кількість скасованих замовлень: </b>{client_stats["cancel_applic"]}\n'
    
    return response_text, get_cabinet_keyboard()

async def show_history_page(call: types.CallbackQuery, page: int) -> None:
    """
    Displays a paginated history of the user's completed trips.

    Args:
        call: The callback query that triggered this view.
        page: The page number to display.
    """
    user_id = call.from_user.id
    no_items_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="↩️ До кабінету", callback_data="back_to_cabinet")]
    ])

    await show_paginated_list(
        target=call,
        page=page,
        count_func=db_queries.get_user_orders_count,
        page_func=db_queries.get_user_orders_page,
        keyboard_func=get_user_history_keyboard,
        title="Історія поїздок",
        items_per_page=ORDERS_PER_PAGE,
        no_items_text='<b>Історія поїздок</b>\n\nУ вас ще немає завершених поїздок.',
        no_items_keyboard=no_items_kb,
        item_list_title="Оберіть поїздку, щоб переглянути деталі:",
        items_list_kwarg_name='orders',
        count_func_kwargs={'user_id': user_id},
        page_func_kwargs={'user_id': user_id}
    )
    
@router.callback_query(Navigate.filter(F.to == "back_to_cabinet"))
async def back_to_cabinet_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Back to Cabinet" inline button from various sub-menus.

    Args:
        call: The callback query.
    """
    user_id = call.from_user.id
    text, keyboard = await get_cabinet_text_and_keyboard(user_id)
    # Delete the old message and send a new one for a consistent UX
    await send_message_with_photo(call, CABINET_IMAGE_PATH, text, keyboard, delete_old=True)
    await call.answer()

@router.message(Command('cabinet'), StateFilter(None))
@router.message(F.text == '🏠 Особистий кабінет', StateFilter(None))
async def main_cabinet(message: types.Message) -> None:
    """
    Handler for entering the personal cabinet via command or reply keyboard.

    Args:
        message: The user's message.
    """
    user_id = message.from_user.id
    text, keyboard = await get_cabinet_text_and_keyboard(user_id)
    await send_message_with_photo(message, CABINET_IMAGE_PATH, text, keyboard)

@router.callback_query(Navigate.filter(F.to == "trip_history"))
async def trip_history_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "Trip History" button, showing the first page of history.

    Args:
        call: The callback query.
    """
    await show_history_page(call, page=0)

@router.callback_query(HistoryPaginator.filter())
async def paginate_history(call: types.CallbackQuery, callback_data: HistoryPaginator) -> None:
    """
    Handles pagination for the trip history.

    Args:
        call: The callback query from pagination buttons.
        callback_data: The paginator callback data.
    """
    await show_history_page(call, page=callback_data.page)

@router.callback_query(TripDetailsCallbackData.filter())
async def show_trip_details(call: types.CallbackQuery, callback_data: TripDetailsCallbackData) -> None:
    """
    Displays detailed information about a specific past trip.

    Args:
        call: The callback query from a specific trip button.
        callback_data: The callback data containing the order ID.
    """
    order_id = callback_data.order_id
    order_data = await db_queries.get_trip_details(order_id, call.from_user.id)
    if not order_data:
        await call.answer("Не вдалося знайти інформацію про цю поїздку.", show_alert=True)
        return

    created_at_str = parser.parse(order_data['created_at']).strftime('%d.%m.%Y %H:%M')
    
    rating_status = "Ні"
    if order_data['is_rated'] == 1:
        score = order_data['rating_score']
        rating_status = f"Так ({'⭐' * score})" if score else "Так"

    details_text = (
        f"<b>Деталі поїздки №{order_data['id']}</b>\n\n"
        f"<b>Дата:</b> {created_at_str}\n"
        f"<b>Звідки:</b> {html.escape(order_data['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order_data['finish_address'])}\n"
    )

    if order_data['driver_name']:
        details_text += (
            f"<b>--- Водій ---</b>\n"
            f"<b>Ім'я:</b> {html.escape(order_data['driver_name'])}\n"
            f"<b>Авто:</b> {html.escape(order_data['avto_num'])}\n"
            f"<b>Телефон:</b> <code>{html.escape(order_data['driver_phone'])}</code>\n\n"
        )
    else:
        details_text += "<i>Інформація про водія недоступна.</i>\n\n"

    details_text += f"<b>Поїздку оцінено:</b> {rating_status}"

    back_to_history_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад до історії", callback_data=Navigate(to="trip_history").pack())]
    ])

    await safe_edit_or_send(call, details_text, reply_markup=back_to_history_kb)

# --- Favorite Addresses Handlers ---

async def fav_addresses_menu(target: types.Message | types.CallbackQuery) -> None:
    """
    Generic helper to display the favorite addresses management menu.
    Works with both Message and CallbackQuery.
    """
    user_id = target.from_user.id
    addresses = await db_queries.get_user_fav_addresses(user_id)
    
    text = "<b>❤️ Мої адреси</b>\n\nТут ви можете керувати збереженими адресами для швидкого замовлення."
    if not addresses:
        text += "\n\nУ вас ще немає збережених адрес."
        
    await safe_edit_or_send(
        target,
        text,
        reply_markup=get_fav_addresses_manage_keyboard(addresses)
    )

@router.callback_query(Navigate.filter(F.to == "fav_addresses"))
async def fav_addresses_menu_handler(call: types.CallbackQuery) -> None:
    """
    Handles the "My Addresses" button, showing the management menu.
    This is the entry point from a callback query.
    """
    await fav_addresses_menu(call)

@router.callback_query(FavAddressManage.filter(F.action == 'add'))
async def add_fav_address_start(call: types.CallbackQuery, state: FSMContext) -> None:
    """
    Starts the FSM for adding a new favorite address.
    """
    await state.set_state(FavAddressState.get_address)
    await safe_edit_or_send(
        call,
        "<b>➕ Додавання нової адреси</b>\n\n"
        "<b>Крок 1/2:</b> Введіть адресу, яку хочете зберегти.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="↩️ Назад", callback_data=Navigate(to="fav_addresses").pack())]
        ])
    )

@router.callback_query(FavAddressManage.filter(F.action == 'delete_start'))
async def delete_fav_address_start(call: types.CallbackQuery, callback_data: FavAddressManage) -> None:
    """
    Shows the confirmation step for deleting a favorite address.
    """
    await safe_edit_or_send(
        call,
        "Ви впевнені, що хочете видалити цю адресу?",
        reply_markup=get_confirm_delete_fav_address_keyboard(callback_data.address_id)
    )

@router.callback_query(FavAddressManage.filter(F.action == 'delete_confirm'))
async def delete_fav_address_confirm(call: types.CallbackQuery, callback_data: FavAddressManage) -> None:
    """
    Handles the final confirmation for deleting a favorite address.
    """
    address_id = callback_data.address_id
    user_id = call.from_user.id

    await db_queries.delete_fav_address(address_id, user_id)
    await call.answer("Адресу видалено.", show_alert=True)
    
    # Show updated list
    await fav_addresses_menu(call)