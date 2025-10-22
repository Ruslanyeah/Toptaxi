from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dateutil import parser
from utils.callback_factories import *
from .common import Navigate, _add_pagination_buttons
import html
from datetime import datetime, timedelta
from config.config import ADMIN_IDS

def get_admin_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='📣 Розсилка', callback_data=Navigate(to='news'))
    builder.button(text='📊 Статистика та Аналітика', callback_data=Navigate(to='analytics_menu'))
    builder.button(text='📋 Список водіїв', callback_data=Navigate(to='drivers_list'))
    builder.button(text='🚦 Водії на зміні', callback_data=Navigate(to='working_drivers_list'))
    builder.button(text='⚙️ Керування користувачами', callback_data=Navigate(to='user_management'))
    builder.button(text='🗂️ Керування замовленнями', callback_data=Navigate(to='order_management'))
    builder.button(text='👑 Керування адмінами', callback_data=Navigate(to='admin_management'))
    builder.adjust(2, 1, 2, 1)
    return builder.as_markup()

def get_newsletter_audience_keyboard(counts: dict[str, int]) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"👥 Всім користувачам ({counts.get('all', 0)})", callback_data=Navigate(to='nl_audience_all'))
    builder.button(text=f"👤 Тільки клієнтам ({counts.get('clients', 0)})", callback_data=Navigate(to='nl_audience_clients'))
    builder.button(text=f"🚕 Тільки водіям ({counts.get('drivers', 0)})", callback_data=Navigate(to='nl_audience_drivers'))
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))
    builder.adjust(1)
    return builder.as_markup()

def get_newsletter_confirm_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Надіслати', callback_data=Navigate(to='nl_confirm_send'))
    builder.button(text='✏️ Змінити повідомлення', callback_data=Navigate(to='nl_change_message'))
    builder.button(text='🚫 Скасувати розсилку', callback_data=Navigate(to='admin_panel'))
    return builder.as_markup()

def get_admin_management_keyboard(admins: list) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for the admin management menu."""
    builder = InlineKeyboardBuilder()
    if admins:
        builder.button(text="--- Поточні адміністратори ---", callback_data="noop") # No-op button as a header
        for admin in admins:
            builder.button(
                text=f"➖ {html.escape(admin['full_name'])}",
                callback_data=AdminAction(action='remove_admin', target_id=admin['user_id'])
            )
    builder.button(text='➕ Додати адміністратора', callback_data=AdminAction(action='add_admin_start'))
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))
    builder.adjust(1)
    return builder.as_markup()

def get_analytics_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='📊 Загальна статистика', callback_data=Navigate(to='general_stats'))
    builder.button(text='📈 Продуктивність водіїв', callback_data=Navigate(to='drivers_kpi'))
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))
    builder.adjust(1)
    return builder.as_markup()

def get_analytics_period_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='📅 За сьогодні', callback_data=Navigate(to='stats_period_today'))
    builder.button(text='📅 За тиждень', callback_data=Navigate(to='stats_period_week'))
    builder.button(text='📅 За місяць', callback_data=Navigate(to='stats_period_month'))
    builder.button(text='🗓️ Вказати період', callback_data=Navigate(to='stats_period_custom'))
    builder.button(text='↩️ До аналітики', callback_data=Navigate(to='analytics_menu'))
    builder.adjust(1)
    return builder.as_markup()

def get_drivers_kpi_keyboard(page: int, total_pages: int) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації списку KPI водіїв."""
    builder = InlineKeyboardBuilder()
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, KpiPaginator)
    builder.button(text='↩️ До аналітики', callback_data=Navigate(to='analytics_menu'))
    if pagination_row_size > 0:
        builder.adjust(pagination_row_size, 1)
    else:
        builder.adjust(1)
    return builder.as_markup()

def get_order_management_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='⚡ Активні замовлення', callback_data=Navigate(to='active_orders_list'))
    builder.button(text='🗂️ Вся історія замовлень', callback_data=Navigate(to='all_orders_history'))
    builder.button(text='🔎 Знайти замовлення по клієнту', callback_data=Navigate(to='search_order_by_client'))
    builder.button(text='🔎 Знайти замовлення по ID', callback_data=Navigate(to='search_order_by_id'))
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))
    builder.adjust(1)
    return builder.as_markup()

def get_user_management_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='👥 Список користувачів', callback_data=Navigate(to='clients_list'))
    builder.button(text='🚫 Заблоковані користувачі', callback_data=Navigate(to='banned_clients_list'))
    builder.button(text='ℹ️ Інфо по ID', callback_data=Navigate(to='get_user_info'))
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))
    builder.adjust(1)
    return builder.as_markup()

def get_drivers_list_keyboard(page: int, total_pages: int, drivers: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації списку водіїв."""
    builder = InlineKeyboardBuilder()
    for driver in drivers:
        builder.button(
            text=f"👤 {driver['full_name']}",
            callback_data=DriverProfile(user_id=driver['user_id'])
        )
    
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, Paginator)
    builder.button(text='➕ Додати водія', callback_data=Navigate(to='add_driver_start'))
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))

    layout = [1] * len(drivers)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.extend([1, 1])
    builder.adjust(*layout)
    return builder.as_markup()

def get_working_drivers_keyboard(page: int, total_pages: int, drivers: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації списку водіїв на зміні."""
    builder = InlineKeyboardBuilder()
    for driver in drivers:
        builder.button(
            text=f"👤 {driver['full_name']}",
            callback_data=DriverProfile(user_id=driver['user_id'])
        )

    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, WorkingDriversPaginator)
    builder.button(text='↩️ До адмін-панелі', callback_data=Navigate(to='admin_panel'))

    layout = [1] * len(drivers)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_clients_list_keyboard(page: int, total_pages: int, clients: list, search_active: bool = False) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації списку клієнтів."""
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.button(
            text=f"👤 {html.escape(client['full_name'] or 'Ім`я не вказано')}",
            callback_data=ClientProfile(user_id=client['user_id'])
        )
    
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, ClientPaginator)
    if search_active:
        builder.button(text='❌ Скасувати пошук', callback_data=Navigate(to='clients_list'))
    else:
        builder.button(text='🔎 Пошук', callback_data=Navigate(to='start_client_search'))

    builder.button(text='↩️ До керування', callback_data=Navigate(to='user_management'))
    
    layout = [1] * len(clients)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.extend([1, 1])
    builder.adjust(*layout)
    return builder.as_markup()

def get_client_profile_keyboard(user_id: int, is_banned: bool, is_admin: bool) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для профілю клієнта з кнопками дій."""
    builder = InlineKeyboardBuilder()
    if is_banned:
        builder.button(
            text="✅ Розблокувати", callback_data=AdminClientAction(action='unban', user_id=user_id)
        )
    else:
        builder.button(
            text="🚫 Заблокувати", callback_data=AdminClientAction(action='ban', user_id=user_id)
        )
    
    # Додаємо кнопку для керування правами адміністратора, якщо це не супер-адмін
    if user_id not in ADMIN_IDS:
        if is_admin:
            builder.button(text="👑 Забрати права адміна", callback_data=AdminAction(action='toggle_admin', target_id=user_id))
        else:
            builder.button(text="👑 Надати права адміна", callback_data=AdminAction(action='toggle_admin', target_id=user_id))

    builder.button(text="✉️ Надіслати повідомлення", callback_data=AdminClientAction(action='send_message', user_id=user_id))
    builder.button(text="📖 Історія замовлень", callback_data=ClientHistory(user_id=user_id))
    builder.button(text="⬅️ Назад до списку", callback_data=Navigate(to='clients_list'))
    builder.adjust(1)
    return builder.as_markup()

def get_client_history_keyboard(page: int, total_pages: int, orders: list, client_id: int) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для історії замовлень клієнта."""
    builder = InlineKeyboardBuilder()
    status_emoji = {
        'completed': '✅', 'cancelled_by_user': '❌', 'cancelled_by_driver': '❌',
        'cancelled_by_admin': '❌', 'cancelled_no_drivers': '🤷', 'searching': '🔎',
        'accepted': '👍', 'in_progress': '🚗', 'scheduled': '📅'
    }
    for order in orders:
        emoji = status_emoji.get(order['status'], '❓')
        date_str = parser.parse(order['created_at']).strftime('%d.%m %H:%M')
        builder.button(
            text=f"{emoji} №{order['id']} від {date_str}",
            callback_data=AdminOrderDetails(order_id=order['id'])
        )

    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, ClientHistoryPaginator, user_id=client_id)
    builder.button(text="↩️ До профілю користувача", callback_data=ClientProfile(user_id=client_id))

    layout = [1] * len(orders)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_driver_profile_keyboard(user_id: int, on_shift: bool, is_available: bool) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not on_shift:
        builder.button(text="🚀 Примусово почати зміну", callback_data=AdminDriverAction(action='force_start_shift', user_id=user_id))
    else:
        if is_available:
            builder.button(text="⏸️ Зробити тимчасово недоступним", callback_data=AdminDriverAction(action='set_unavailable', user_id=user_id))
        else:
            builder.button(text="▶️ Повернути до прийому замовлень", callback_data=AdminDriverAction(action='set_available', user_id=user_id))
        builder.button(text="⛔️ Примусово завершити зміну", callback_data=AdminDriverAction(action='force_stop_shift', user_id=user_id))

    if on_shift:
        builder.button(text="📍 Показати поточну геолокацію", callback_data=AdminShowLocation(user_id=user_id))
    else:
        builder.button(text="📍 Запросити геолокацію (не на зміні)", callback_data=AdminRequestLocation(user_id=user_id))
    
    builder.button(text="✏️ Редагувати дані", callback_data=AdminDriverAction(action='edit_details', user_id=user_id))
    builder.button(text="🗑️ Видалити водія", callback_data=AdminDriverAction(action='delete_start', user_id=user_id))
    builder.button(text="⬅️ Назад до списку", callback_data=Navigate(to='drivers_list'))
    builder.adjust(1)
    return builder.as_markup()

def get_working_driver_profile_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для профілю водія, відкритого зі списку 'на зміні'."""
    builder = InlineKeyboardBuilder()
    # Оскільки водій на зміні, пропонуємо відповідні дії
    builder.button(text="⛔️ Примусово завершити зміну", callback_data=AdminDriverAction(action='force_stop_shift', user_id=user_id))
    builder.button(text="📍 Показати поточну геолокацію", callback_data=AdminShowLocation(user_id=user_id))
    builder.button(text="✏️ Редагувати дані", callback_data=AdminDriverAction(action='edit_details', user_id=user_id))
    builder.button(text="🗑️ Видалити водія", callback_data=AdminDriverAction(action='delete_start', user_id=user_id))
    
    # Кнопка "Назад" повертає до списку водіїв на зміні
    builder.button(text="⬅️ Назад до списку", callback_data=Navigate(to='working_drivers_list'))
    builder.adjust(1)
    return builder.as_markup()

def get_banned_clients_list_keyboard(page: int, total_pages: int, clients: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для списку заблокованих клієнтів."""
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.button(
            text=f"👤 {html.escape(client['full_name'] or 'Ім`я не вказано')}",
            callback_data=ClientProfile(user_id=client['user_id'])
        )
    
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, BannedClientPaginator)
    builder.button(text='↩️ До керування користувачами', callback_data=Navigate(to='user_management'))

    layout = [1] * len(clients)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_active_orders_keyboard(page: int, total_pages: int, orders_on_page: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для списку активних замовлень (адмін)."""
    builder = InlineKeyboardBuilder()
    status_emoji = {
        'searching': '🔎', 'accepted': '👍', 'in_progress': '🚗', 'scheduled': '📅'
    }
    for order in orders_on_page:
        emoji = status_emoji.get(order['status'], '❓')
        date_str = parser.parse(order['created_at']).strftime('%d.%m %H:%M')
        builder.button(
            text=f"{emoji} №{order['id']} від {date_str}",
            callback_data=AdminOrderDetails(order_id=order['id'])
        )

    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, AdminOrderPaginator)
    builder.button(text="↩️ До керування замовленнями", callback_data=Navigate(to="order_management"))

    layout = [1] * len(orders_on_page)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_admin_order_keyboard(order_id: int, status: str) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для керування конкретним замовленням (адмін)."""
    builder = InlineKeyboardBuilder()
    # Дозволити скасування/перепризначення, якщо замовлення активне
    if status in ['searching', 'accepted', 'in_progress', 'scheduled']:
        builder.button(
            text="🔄 Перепризначити водія",
            callback_data=AdminOrderAction(action='reassign_order', order_id=order_id)
        )
        builder.button(
            text="❌ Скасувати замовлення",
            callback_data=AdminOrderAction(action='cancel_order', order_id=order_id)
        )
    
    builder.button(text="⬅️ Назад до керування замовленнями", callback_data=Navigate(to="order_management"))
    builder.adjust(1)
    return builder.as_markup()

def get_all_orders_keyboard(page: int, total_pages: int, orders: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для всієї історії замовлень (адмін)."""
    builder = InlineKeyboardBuilder()
    status_emoji = {
        'completed': '✅', 'cancelled_by_user': '❌', 'cancelled_by_driver': '❌',
        'cancelled_by_admin': '❌', 'cancelled_no_drivers': '🤷', 'searching': '🔎',
        'accepted': '👍', 'in_progress': '🚗', 'scheduled': '📅'
    }
    for order in orders:
        emoji = status_emoji.get(order['status'], '❓')
        date_str = parser.parse(order['created_at']).strftime('%d.%m %H:%M')
        builder.button(
            text=f"{emoji} №{order['id']} від {date_str}",
            callback_data=AdminOrderDetails(order_id=order['id'])
        )

    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, AllOrdersPaginator)
    builder.button(text="↩️ До керування замовленнями", callback_data=Navigate(to="order_management"))

    layout = [1] * len(orders)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_confirm_delete_driver_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Так, видалити", callback_data=AdminDriverAction(action='delete_confirm', user_id=user_id))
    builder.button(text="❌ Ні, скасувати", callback_data=DriverProfile(user_id=user_id))
    builder.adjust(2)
    return builder.as_markup()

def get_edit_driver_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Змінити ПІБ", callback_data=AdminDriverAction(action='edit_fullname', user_id=user_id))
    builder.button(text="✏️ Змінити номер авто", callback_data=AdminDriverAction(action='edit_avto_num', user_id=user_id))
    builder.button(text="✏️ Змінити телефон", callback_data=AdminDriverAction(action='edit_phone_num', user_id=user_id))
    builder.button(text="⬅️ Назад до профілю", callback_data=DriverProfile(user_id=user_id))
    builder.adjust(1)
    return builder.as_markup()

fsm_cancel_keyboard = ReplyKeyboardBuilder().button(
    text="🚫 Скасувати"
).as_markup(
    resize_keyboard=True
)