from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dateutil import parser
from utils.callback_factories import *
from .common import Navigate, _add_pagination_buttons
from datetime import datetime, timedelta
from config.config import TIMEZONE
import html

# --- User Cabinet ---

def get_cabinet_keyboard() -> types.InlineKeyboardMarkup:
    """Generates the keyboard for the user's personal cabinet."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 Історія поїздок", callback_data=Navigate(to="trip_history"))
    builder.button(text="❤️ Мої адреси", callback_data=Navigate(to="fav_addresses"))
    builder.adjust(1)
    return builder.as_markup()

def get_user_history_keyboard(page: int, total_pages: int, orders: list) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for the user's trip history with pagination."""
    builder = InlineKeyboardBuilder()
    for order in orders:
        date_str = parser.parse(order['created_at']).strftime('%d.%m.%Y')
        builder.button(
            text=f"Поїздка №{order['id']} від {date_str}",
            callback_data=TripDetailsCallbackData(order_id=order['id'])
        )
    
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, HistoryPaginator)
    builder.button(text="↩️ До кабінету", callback_data=Navigate(to="back_to_cabinet"))
    
    layout = [1] * len(orders)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_fav_addresses_manage_keyboard(addresses: list) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if addresses:
        for addr in addresses:
            # Обрізаємо довгу адресу для відображення на кнопці
            address_preview = (addr['address'][:30] + '...') if len(addr['address']) > 30 else addr['address']
            builder.button(
                text=f"🗑️ {addr['name']}: {address_preview}",
                callback_data=FavAddressManage(action='delete_start', address_id=addr['id'])
            )
    
    builder.button(text="➕ Додати нову адресу", callback_data=FavAddressManage(action='add'))
    builder.button(text="↩️ До кабінету", callback_data=Navigate(to="back_to_cabinet"))
    builder.adjust(1) # All buttons on separate rows
    return builder.as_markup()

def get_confirm_delete_fav_address_keyboard(address_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Так, видалити", callback_data=FavAddressManage(action='delete_confirm', address_id=address_id))
    builder.button(text="❌ Ні, скасувати", callback_data=Navigate(to="fav_addresses"))
    builder.adjust(2)
    return builder.as_markup()

# --- Rating ---

def get_rating_keyboard(order_id: int, with_save_address: bool = False) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for the client to rate the driver."""
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(
            text=f"{'⭐' * i}",
            callback_data=RatingCallbackData(order_id=order_id, score=i)
        )
    if with_save_address:
        builder.button(
            text="❤️ Зберегти адресу призначення",
            callback_data=SaveAddress(type='finish', order_id=order_id)
        )
        builder.adjust(5, 1)
    else:
        builder.adjust(5)
    return builder.as_markup()

# --- Address Clarification (FSM) ---

def get_confirm_unfound_address_keyboard() -> types.InlineKeyboardMarkup:
    """Creates a keyboard to confirm using an address that was not found on the map."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Використати як є", callback_data=ConfirmUnfoundAddress(action='use_anyway'))
    builder.button(text="✏️ Ввести знову", callback_data=ConfirmUnfoundAddress(action='retry'))
    builder.adjust(1)
    return builder.as_markup()

def get_address_clarification_keyboard(locations: list) -> types.InlineKeyboardMarkup:
    """Створює клавіатуру для уточнення адреси."""
    builder = InlineKeyboardBuilder()
    for i, location in enumerate(locations):
        # Обрізаємо занадто довгі адреси для кнопок
        address_text = (location.address[:60] + '…') if len(location.address) > 60 else location.address
        builder.button(
            text=address_text,
            callback_data=ClarifyAddressCallbackData(index=i)
        )
    builder.button(text="➡️ Використати мій варіант як є", callback_data=Navigate(to="clarify_addr_skip"))
    builder.button(text="↩️ Ввести адресу знову", callback_data=Navigate(to="clarify_addr_retry"))
    builder.adjust(*([1] * (len(locations) + 2)))
    return builder.as_markup()

def get_confirm_clarified_address_keyboard(address_type: str) -> types.InlineKeyboardMarkup:
    """Створює клавіатуру для підтвердження або уточнення обраної адреси."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Так, все вірно", callback_data=ConfirmClarifiedAddress(action='confirm', address_type=address_type))
    builder.button(text="✏️ Уточнити вручну", callback_data=ConfirmClarifiedAddress(action='retry', address_type=address_type))
    builder.adjust(1)
    return builder.as_markup()

# --- Other ---

def get_contacts_keyboard() -> types.InlineKeyboardMarkup:
    """Клавіатура для розділу "Контакти та допомога" """
    builder = InlineKeyboardBuilder()
    builder.button(text='Ми на Google Картах 🗺️', url='https://maps.app.goo.gl/YOUR_BUSINESS_LINK_HERE')
    builder.button(text='📸 Наш Instagram', url='https://www.instagram.com/taksiglukhov?igsh=MTB5OTFvajl5YWw0dg==')
    builder.adjust(1)
    return builder.as_markup()