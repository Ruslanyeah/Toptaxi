from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter, BaseFilter
import html
from dateutil import parser

from states.fsm_states import AdminState
from database import queries as db_queries
from keyboards.common import Navigate
from keyboards.reply_keyboards import main_menu_keyboard, fsm_cancel_keyboard
from .common.paginator import show_paginated_list
from config.config import BASE_DIR
from .common.helpers import send_message_with_photo
from keyboards.admin_keyboards import get_admin_keyboard

router = Router()

ADMIN_PANEL_IMAGE_PATH = BASE_DIR / "assets" / "images" / "admin_panel.jpg"
DRIVERS_PER_PAGE = 5
CLIENTS_PER_PAGE = 5
ORDERS_PER_PAGE = 5

class IsAdmin(BaseFilter):
    """
    Custom filter to check if a user is an admin.
    """
    async def __call__(self, message: types.Message) -> bool:
        return await db_queries.is_admin(message.from_user.id)

# --- Admin Panel Entry ---

@router.message(Command("admin"), IsAdmin(), StateFilter(None))
async def admin_panel(message: types.Message, state: FSMContext):
    """Displays the main admin panel."""
    await state.clear()
    stats = await db_queries.get_main_stats()
    text = (
        f"<b>👑 Адміністративна панель</b>\n\n"
        f"<b>Статистика:</b>\n"
        f"  - Всього водіїв: {stats['total_drivers']}\n"
        f"  - Водіїв на зміні: {stats['working_drivers']}\n"
        f"  - Всього клієнтів: {stats['total_clients']}\n"
        f"  - Активних замовлень: {stats['active_orders']}\n"
        f"  - Завершено замовлень: {stats['completed_orders']}"
    )
    await send_message_with_photo(message, ADMIN_PANEL_IMAGE_PATH, text, get_admin_keyboard())

@router.callback_query(Navigate.filter(F.to == "admin_panel"))
async def back_to_admin_panel(call: types.CallbackQuery, state: FSMContext):
    """Handles the 'Back to Admin Panel' button."""
    await admin_panel(call.message, state)
    await call.answer()

# --- Driver Management ---

async def show_drivers_list(call: types.CallbackQuery, page: int, list_type: str):
    """Helper to show a paginated list of drivers."""
    title_map = {
        'all': "Список всіх водіїв",
        'working': "Водії на зміні",
        'not_working': "Водії не на зміні"
    }
    count_func_map = {
        'all': db_queries.get_drivers_count,
        'working': lambda: db_queries.get_drivers_count(is_working=True),
        'not_working': lambda: db_queries.get_drivers_count(is_working=False)
    }
    page_func_map = {
        'all': db_queries.get_drivers_page,
        'working': lambda limit, offset: db_queries.get_drivers_page(limit=limit, offset=offset, is_working=True),
        'not_working': lambda limit, offset: db_queries.get_drivers_page(limit=limit, offset=offset, is_working=False)
    }

    from keyboards.admin_keyboards import get_drivers_list_keyboard, get_back_to_drivers_menu_keyboard
    await show_paginated_list(
        target=call,
        page=page,
        count_func=count_func_map[list_type],
        page_func=page_func_map[list_type],
        keyboard_func=lambda page, total_pages, items: get_drivers_list_keyboard(page, total_pages, items, list_type),
        title=title_map[list_type],
        items_per_page=DRIVERS_PER_PAGE,
        no_items_text=f"<b>{title_map[list_type]}</b>\n\nНемає водіїв, що відповідають критерію.",
        no_items_keyboard=get_back_to_drivers_menu_keyboard(),
        item_list_title="Оберіть водія для перегляду профілю:",
        items_list_kwarg_name='items'
    )

@router.callback_query(Navigate.filter(F.to == "manage_drivers"))
async def manage_drivers_menu(call: types.CallbackQuery):
    """Shows the driver management menu."""
    from keyboards.admin_keyboards import get_driver_management_keyboard
    await call.message.edit_text("<b>Керування водіями</b>", reply_markup=get_driver_management_keyboard())
    await call.answer()

@router.callback_query(F.data.startswith("admin_drv_list:"))
async def drivers_list_paginator(call: types.CallbackQuery):
    """Handles pagination for driver lists."""
    from utils.callback_factories import AdminDriverList
    callback_data = AdminDriverList.unpack(call.data)
    await show_drivers_list(call, callback_data.page, callback_data.list_type)

@router.callback_query(F.data.startswith("adm_drv:view:"))
async def show_driver_profile(call: types.CallbackQuery):
    """Shows a specific driver's profile."""
    from utils.callback_factories import AdminDriverAction
    callback_data = AdminDriverAction.unpack(call.data)
    from .common.helpers import _display_driver_profile
    await _display_driver_profile(call, callback_data.user_id)

@router.callback_query(F.data.startswith("adm_drv:ban:"))
async def ban_driver(call: types.CallbackQuery):
    """Bans a driver."""
    from utils.callback_factories import AdminDriverAction
    callback_data = AdminDriverAction.unpack(call.data)
    await db_queries.ban_user(callback_data.user_id)
    await call.answer("Водія заблоковано", show_alert=True)
    from .common.helpers import _display_driver_profile
    await _display_driver_profile(call, callback_data.user_id)

@router.callback_query(F.data.startswith("adm_drv:unban:"))
async def unban_driver(call: types.CallbackQuery):
    """Unbans a driver."""
    from utils.callback_factories import AdminDriverAction
    callback_data = AdminDriverAction.unpack(call.data)
    await db_queries.unban_user(callback_data.user_id)
    await call.answer("Водія розблоковано", show_alert=True)
    from .common.helpers import _display_driver_profile
    await _display_driver_profile(call, callback_data.user_id)

# --- Client Management ---

async def show_clients_list(call: types.CallbackQuery, page: int):
    """Helper to show a paginated list of clients."""
    from keyboards.admin_keyboards import get_clients_list_keyboard, get_back_to_admin_keyboard
    await show_paginated_list(
        target=call,
        page=page,
        count_func=db_queries.get_clients_count,
        page_func=db_queries.get_clients_page,
        keyboard_func=get_clients_list_keyboard,
        title="Список клієнтів",
        items_per_page=CLIENTS_PER_PAGE,
        no_items_text="<b>Список клієнтів</b>\n\nКлієнтів не знайдено.",
        no_items_keyboard=get_back_to_admin_keyboard(),
        item_list_title="Оберіть клієнта для перегляду профілю:",
        items_list_kwarg_name='items'
    )

@router.callback_query(Navigate.filter(F.to == "manage_clients"))
async def manage_clients_menu(call: types.CallbackQuery):
    """Shows the first page of the client list."""
    await show_clients_list(call, 0)

@router.callback_query(F.data.startswith("admin_cl_list:"))
async def clients_list_paginator(call: types.CallbackQuery):
    """Handles pagination for the client list."""
    from utils.callback_factories import AdminClientList
    callback_data = AdminClientList.unpack(call.data)
    await show_clients_list(call, callback_data.page)

@router.callback_query(F.data.startswith("adm_cli:view:"))
async def show_client_profile(call: types.CallbackQuery):
    """Shows a specific client's profile."""
    from utils.callback_factories import AdminClientAction
    callback_data = AdminClientAction.unpack(call.data)
    from .common.helpers import _display_client_profile
    await _display_client_profile(target=call, user_id=callback_data.user_id)

@router.callback_query(F.data.startswith("adm_cli:ban:"))
async def ban_client(call: types.CallbackQuery):
    """Bans a client."""
    from utils.callback_factories import AdminClientAction
    callback_data = AdminClientAction.unpack(call.data)
    await db_queries.ban_user(callback_data.user_id)
    await call.answer("Клієнта заблоковано", show_alert=True)
    from .common.helpers import _display_client_profile
    await _display_client_profile(target=call, user_id=callback_data.user_id)

@router.callback_query(F.data.startswith("adm_cli:unban:"))
async def unban_client(call: types.CallbackQuery):
    """Unbans a client."""
    from utils.callback_factories import AdminClientAction
    callback_data = AdminClientAction.unpack(call.data)
    await db_queries.unban_user(callback_data.user_id)
    await call.answer("Клієнта розблоковано", show_alert=True)
    from .common.helpers import _display_client_profile
    await _display_client_profile(target=call, user_id=callback_data.user_id)

@router.callback_query(F.data.startswith("adm_cli:make_admin:"))
async def make_admin(call: types.CallbackQuery):
    """Grants admin rights to a user."""
    from utils.callback_factories import AdminClientAction
    callback_data = AdminClientAction.unpack(call.data)
    await db_queries.add_admin(callback_data.user_id)
    await call.answer("Права адміністратора надано", show_alert=True)
    from .common.helpers import _display_client_profile
    await _display_client_profile(target=call, user_id=callback_data.user_id)

@router.callback_query(F.data.startswith("adm_cli:remove_admin:"))
async def remove_admin(call: types.CallbackQuery):
    """Revokes admin rights from a user."""
    from utils.callback_factories import AdminClientAction
    callback_data = AdminClientAction.unpack(call.data)
    await db_queries.remove_admin(callback_data.user_id)
    await call.answer("Права адміністратора відкликано", show_alert=True)
    from .common.helpers import _display_client_profile
    await _display_client_profile(target=call, user_id=callback_data.user_id)

# --- Order Management ---

async def show_orders_list(call: types.CallbackQuery, page: int, status: str):
    """Helper to show a paginated list of orders by status."""
    title_map = {
        'searching': "Активні замовлення (в пошуку)",
        'active': "Активні замовлення (виконуються)",
        'completed': "Завершені замовлення",
        'cancelled': "Скасовані замовлення",
        'scheduled': "Заплановані замовлення"
    }
    
    from keyboards.admin_keyboards import get_orders_list_keyboard, get_back_to_orders_menu_keyboard
    await show_paginated_list(
        target=call,
        page=page,
        count_func=lambda: db_queries.get_orders_count_by_status(status),
        page_func=lambda limit, offset: db_queries.get_orders_page_by_status(status, limit, offset),
        keyboard_func=lambda page, total_pages, items: get_orders_list_keyboard(page, total_pages, items, status),
        title=title_map.get(status, "Список замовлень"),
        items_per_page=ORDERS_PER_PAGE,
        no_items_text=f"<b>{title_map.get(status, 'Список замовлень')}</b>\n\nНемає замовлень з таким статусом.",
        no_items_keyboard=get_back_to_orders_menu_keyboard(),
        item_formatter=lambda item: (
            f"<b>№{item['id']}</b> від {parser.parse(item['created_at']).strftime('%d.%m %H:%M')} "
            f"(Клієнт: {html.escape(item['client_name'])})\n"
        ),
        items_list_kwarg_name='items'
    )

@router.callback_query(Navigate.filter(F.to == "manage_orders"))
async def manage_orders_menu(call: types.CallbackQuery):
    """Shows the order management menu."""
    from keyboards.admin_keyboards import get_order_management_keyboard
    await call.message.edit_text("<b>Керування замовленнями</b>", reply_markup=get_order_management_keyboard())
    await call.answer()

@router.callback_query(F.data.startswith("admin_ord_list:"))
async def orders_list_paginator(call: types.CallbackQuery):
    """Handles pagination for order lists."""
    from utils.callback_factories import AdminOrderList
    callback_data = AdminOrderList.unpack(call.data)
    await show_orders_list(call, callback_data.page, callback_data.status)

@router.callback_query(F.data.startswith("adm_ord:view:"))
async def show_order_details_admin(call: types.CallbackQuery):
    """Shows detailed information about a specific order for an admin."""
    from utils.callback_factories import AdminOrderAction
    callback_data = AdminOrderAction.unpack(call.data)
    order_id = callback_data.order_id
    order = await db_queries.get_full_order_details(order_id)
    if not order:
        await call.answer("Замовлення не знайдено", show_alert=True)
        return

    created_at = parser.parse(order['created_at']).strftime('%d.%m.%Y %H:%M')
    
    text = (
        f"<b>Деталі замовлення №{order_id}</b>\n\n"
        f"<b>Статус:</b> {order['status']}\n"
        f"<b>Дата створення:</b> {created_at}\n"
        f"<b>Звідки:</b> {html.escape(order['begin_address'])}\n"
        f"<b>Куди:</b> {html.escape(order['finish_address'])}\n"
        f"<b>Коментар:</b> {html.escape(order['comment'] or 'немає')}\n\n"
        f"<b>--- Клієнт ---</b>\n"
        f"<b>ID:</b> <code>{order['client_id']}</code>\n"
        f"<b>Ім'я:</b> {html.escape(order['client_name'])}\n"
        f"<b>Телефон:</b> <code>{html.escape(order['client_phone'])}</code>\n\n"
    )
    if order['driver_id']:
        text += (
            f"<b>--- Водій ---</b>\n"
            f"<b>ID:</b> <code>{order['driver_id']}</code>\n"
            f"<b>Ім'я:</b> {html.escape(order['driver_name'])}\n"
            f"<b>Телефон:</b> <code>{html.escape(order['driver_phone'])}</code>\n"
        )
    
    from keyboards.admin_keyboards import get_order_details_keyboard
    await call.message.edit_text(text, reply_markup=get_order_details_keyboard(order_id, order['status'], order['client_id'], order['driver_id']))
    await call.answer()