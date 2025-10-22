from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from states.fsm_states import PreOrderState
from keyboards.reply_keyboards import (
    main_menu_keyboard, build_address_input_keyboard, phone_request_keyboard,
    comment_skip_keyboard, order_confirm_keyboard
)
from keyboards.preorder_keyboards import get_date_keyboard, get_hour_keyboard, get_minute_keyboard
from database import queries as db_queries
from datetime import datetime, timedelta
from dateutil import parser
from config.config import TIMEZONE, BASE_DIR
from ..common.helpers import send_message_with_photo
from .order_helpers import process_phone_input, show_unified_confirmation

router = Router()

PREORDER_START_IMAGE_PATH = BASE_DIR / "assets" / "images" / "preorder_start.jpg"

# --- Entry Point ---

@router.message(F.text == '📅 Замовити на час')
async def start_pre_order(message: types.Message, state: FSMContext) -> None:
    """
    Handles the "Order for a specific time" button, starting the pre-order FSM.
    """
    await state.clear()
    await state.set_state(PreOrderState.get_datetime)
    await state.update_data(is_preorder=True)
    await send_message_with_photo(
        message,
        PREORDER_START_IMAGE_PATH,
        "<b>📅 Попереднє замовлення</b>\n\n"
        "<b>Крок 1: Дата та час</b>\n\n"
        "Оберіть дату для подачі автомобіля:",
        reply_markup=get_date_keyboard()
    )

# --- Date and Time Selection ---

@router.callback_query(F.data.startswith('date_'), PreOrderState.get_datetime)
async def process_date(call: types.CallbackQuery, state: FSMContext) -> None:
    """
    Processes the selected date and asks for the hour.
    """
    selected_date_str = call.data.split('_')[1]
    await state.update_data(selected_date=selected_date_str)
    await state.set_state(PreOrderState.get_hour)
    await call.message.edit_text(
        f"Ви обрали дату: <b>{selected_date_str}</b>\n\n"
        "Тепер оберіть годину:",
        reply_markup=get_hour_keyboard()
    )
    await call.answer()

@router.callback_query(F.data.startswith('hour_'), PreOrderState.get_hour)
async def process_hour(call: types.CallbackQuery, state: FSMContext) -> None:
    """
    Processes the selected hour and asks for the minute.
    """
    selected_hour = int(call.data.split('_')[1])
    await state.update_data(selected_hour=selected_hour)
    await state.set_state(PreOrderState.get_minute)
    
    data = await state.get_data()
    selected_date_str = data.get('selected_date')
    
    await call.message.edit_text(
        f"Ви обрали: <b>{selected_date_str}</b>, <b>{selected_hour:02d}:xx</b>\n\n"
        "Тепер оберіть хвилини:",
        reply_markup=get_minute_keyboard()
    )
    await call.answer()

@router.callback_query(F.data.startswith('minute_'), PreOrderState.get_minute)
async def process_minute(call: types.CallbackQuery, state: FSMContext) -> None:
    """
    Processes the selected minute, validates the full datetime, and moves to the address step.
    """
    selected_minute = int(call.data.split('_')[1])
    data = await state.get_data()
    
    try:
        full_datetime_str = f"{data['selected_date']} {data['selected_hour']}:{selected_minute}"
        scheduled_at = parser.parse(full_datetime_str)
        scheduled_at = TIMEZONE.localize(scheduled_at)
    except (KeyError, ValueError):
        await call.answer("Сталася помилка. Будь ласка, почніть заново.", show_alert=True)
        await call.message.answer("Помилка даних. Повернення в головне меню.", reply_markup=main_menu_keyboard)
        await state.clear()
        return

    # Validation: time must be in the future
    if scheduled_at <= datetime.now(TIMEZONE) + timedelta(minutes=10):
        await call.answer("❌ Час подачі має бути мінімум через 10 хвилин від поточного.", show_alert=True)
        return

    await state.update_data(scheduled_at=scheduled_at.isoformat())
    await state.set_state(PreOrderState.locate)
    
    fav_addresses = await db_queries.get_user_fav_addresses(call.from_user.id)
    
    # We can't edit a text message into a photo message, so we send a new one.
    await call.message.delete()
    await call.message.answer(
        f"✅ Час подачі встановлено: <b>{scheduled_at.strftime('%d.%m.%Y о %H:%M')}</b>\n\n"
        "<b>Крок 2: Адреса</b>\n\n"
        "Тепер вкажіть адресу подачі:",
        reply_markup=build_address_input_keyboard(fav_addresses)
    )
    await call.answer()

# --- Final Steps: Phone and Comment ---

@router.message(PreOrderState.number, (F.contact | F.text))
async def handle_preorder_phone(message: types.Message, state: FSMContext):
    await process_phone_input(message, state, next_state=PreOrderState.comment)

@router.message(PreOrderState.comment, F.text == 'Без коментаря')
async def handle_preorder_skip_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=None)
    await show_unified_confirmation(message, state, PreOrderState.confirm_preorder)

@router.message(PreOrderState.comment, F.text)
async def handle_preorder_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text)
    await show_unified_confirmation(message, state, PreOrderState.confirm_preorder)
