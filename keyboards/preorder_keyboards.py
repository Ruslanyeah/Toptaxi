from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
from config.config import TIMEZONE
from utils.callback_factories import TimePickerCallback

def get_date_keyboard() -> types.InlineKeyboardMarkup:
    """Generates a keyboard to select a date for the pre-order."""
    builder = InlineKeyboardBuilder()
    today = datetime.now(TIMEZONE).date()
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime('%d.%m.%Y')
        day_name = "Сьогодні" if i == 0 else "Завтра" if i == 1 else date.strftime('%A')
        builder.button(
            text=f"{date_str} ({day_name})",
            callback_data=f"date_{date_str}"
        )
    builder.adjust(1)
    return builder.as_markup()

def get_hour_keyboard() -> types.InlineKeyboardMarkup:
    """Generates a keyboard for picking the hour."""
    builder = InlineKeyboardBuilder()
    for hour in range(24):
        builder.button(text=f"{hour:02}", callback_data=f"hour_{hour}")
    
    builder.button(text="🚫 Скасувати", callback_data="stop_fsm")
    builder.adjust(6, 6, 6, 6, 1)
    return builder.as_markup()

def get_minute_keyboard() -> types.InlineKeyboardMarkup:
    """
    Generates a keyboard for picking the minute (in 15-minute intervals).
    """
    builder = InlineKeyboardBuilder()
    for minute in [0, 15, 30, 45]:
        builder.button(text=f"{minute:02}", callback_data=f"minute_{minute}")
    
    builder.button(text="⬅️ Назад до годин", callback_data="hour_back")
    builder.adjust(4, 1)
    return builder.as_markup()