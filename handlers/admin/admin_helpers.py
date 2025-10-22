from aiogram import types
import html
import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from database import queries as db_queries
from ..common.paginator import show_paginated_list
from ..common.helpers import safe_edit_or_send
from keyboards.admin_keyboards import get_client_history_keyboard, get_admin_order_keyboard, get_clients_list_keyboard
from utils.callback_factories import ClientProfile, ClientHistoryPaginator, AdminOrderDetails

CLIENT_HISTORY_PER_PAGE = 10
CLIENTS_PER_PAGE = 5

async def update_admin_commands(bot: Bot, user_id: int, is_admin: bool):
    """
    Instantly updates the command menu for a user when their admin status changes.
    """
    try:
        if is_admin:
            # Set admin commands
            admin_commands = [
                BotCommand(command="start", description="🚀 Розпочати роботу / Головне меню"),
                BotCommand(command="cabinet", description="🏠 Особистий кабінет"),
                BotCommand(command="driver", description="🚕 Кабінет водія"),
                BotCommand(command="stop", description="🚫 Скасувати поточну дію"),
                BotCommand(command="admin", description="👑 Адмін-панель"),
            ]
            await bot.set_my_commands(admin_commands, BotCommandScopeChat(chat_id=user_id))
        else:
            # Revert to default user commands
            user_commands = [
                BotCommand(command="start", description="🚀 Розпочати роботу / Головне меню"),
                BotCommand(command="cabinet", description="🏠 Особистий кабінет"),
                BotCommand(command="driver", description="🚕 Кабінет водія"),
                BotCommand(command="stop", description="🚫 Скасувати поточну дію"),
            ]
            await bot.set_my_commands(user_commands, BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        # Log the error but don't crash the main logic
        logging.warning(f"Could not update commands for user {user_id}: {e}")

def _format_client(client: dict) -> str:
    """
    Formats a single client's info for display in a list.
    """
    return (
        f"👤 <b>{html.escape(client['full_name'] or 'Ім`я не вказано')}</b> (ID: <code>{client['user_id']}</code>)\n"
        f"  - Телефон: <code>{html.escape(client['phone_number'] or 'Не вказано')}</code>\n"
        f"  - Поїздки: ✅ {client['finish_applic']} / ❌ {client['cancel_applic']}\n\n"
    )

async def show_clients_page(target: types.CallbackQuery | types.Message, page: int, search_query: str | None = None) -> None:
    """
    Displays a paginated list of clients, with an optional search query.
    """
    no_items_kb = get_clients_list_keyboard(page=0, total_pages=0, clients=[], search_active=bool(search_query))
    
    if search_query:
        no_items_text = f"<b>🔎 Результати пошуку для '{html.escape(search_query)}'</b>\n\nНічого не знайдено."
    else:
        no_items_text = '<b>👥 Список користувачів</b>\n\nНаразі немає зареєстрованих користувачів.'

    await show_paginated_list(
        target=target,
        page=page,
        count_func=db_queries.get_clients_count,
        page_func=db_queries.get_clients_page,
        keyboard_func=get_clients_list_keyboard,
        title="👥 Список користувачів",
        items_per_page=CLIENTS_PER_PAGE,
        no_items_text=no_items_text,
        no_items_keyboard=no_items_kb,
        count_func_kwargs={'search_query': search_query},
        page_func_kwargs={'search_query': search_query},
        keyboard_func_kwargs={'search_active': bool(search_query)},
        item_formatter=_format_client,
        items_list_kwarg_name='clients'
    )

async def show_client_history_page(target: types.CallbackQuery | types.Message, user_id: int, page: int) -> None:
    """
    Displays a paginated history of a specific client's orders.

    Args:
        target: The message or callback query to respond to.
        user_id: The ID of the client whose history to show.
        page: The page number to display.
    """
    client_name = await db_queries.get_client_name(user_id) or f"ID: {user_id}"
    await show_paginated_list(
        target=target,
        page=page,
        count_func=db_queries.get_all_orders_count_by_client,
        page_func=db_queries.get_all_orders_page_by_client,
        keyboard_func=get_client_history_keyboard,
        title=f"Історія замовлень для {html.escape(client_name)}",
        items_per_page=CLIENT_HISTORY_PER_PAGE,
        no_items_text=f"<b>Історія замовлень для {html.escape(client_name)}</b>\n\nУ цього користувача немає замовлень.",
        no_items_keyboard=InlineKeyboardBuilder().button(
            text="↩️ До профілю користувача",
            callback_data=ClientProfile(user_id=user_id)
        ).as_markup(),
        count_func_kwargs={'client_id': user_id},
        page_func_kwargs={'client_id': user_id},
        keyboard_func_kwargs={'client_id': user_id},
        item_list_title="Оберіть замовлення для перегляду деталей:",
        items_list_kwarg_name='orders'
    )

async def show_admin_order_details(target: types.Message | types.CallbackQuery, callback_data: AdminOrderDetails) -> None:
    """
    Displays detailed information about a specific order for the admin.
    """
    order_id = callback_data.order_id
    order = await db_queries.get_order_details(order_id)

    if not order:
        await target.answer("Замовлення не знайдено.", show_alert=True)
        return

    client_info, _, _, _, _, _ = await db_queries.get_full_user_info(order['client_id'])
    driver_info = "Не призначено"
    if order['driver_id']:
        info_text, is_driver, _, _, _, _ = await db_queries.get_full_user_info(order['driver_id'])
        if not is_driver:
            driver_info = f"<i>Водія (ID: {order['driver_id']}) було видалено з системи.</i>"
        else:
            driver_info = info_text

    rating_text = "Не оцінено"
    if order['is_rated'] and order['rating_score']:
        rating_text = f"{order['rating_score']} ⭐"

    text = (
        f"<b>Деталі замовлення №{order_id}</b>\n\n"
        f"<b>Статус:</b> {order['status']}\n"
        f"<b>Створено:</b> {order['created_at']}\n"
        f"<b>Звідки:</b> {html.escape(order['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order['finish_address'])}\n"
        f"<b>Оцінка водію:</b> {rating_text}\n\n"
        f"<b>--- Клієнт ---</b>\n{client_info}\n\n"
        f"<b>--- Водій ---</b>\n{driver_info}"
    )
    keyboard = get_admin_order_keyboard(order_id, order['status'])
    await safe_edit_or_send(target, text, reply_markup=keyboard)
    if isinstance(target, types.CallbackQuery):
        await target.answer()