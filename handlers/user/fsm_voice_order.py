from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from states.fsm_states import VoiceOrderState
from keyboards.reply_keyboards import (
    fsm_cancel_keyboard, location_or_skip_keyboard, main_menu_keyboard, phone_request_keyboard
)
from database import queries as db_queries
from .order_dispatch import dispatch_order_to_drivers
from .order_helpers import _go_to_phone_number_step
from utils.validators import is_valid_phone

router = Router()

@router.message(F.text == '🎙️ Швидке замовлення голосом')
async def start_voice_order(message: types.Message, state: FSMContext):
    """
    Starts the multi-step voice order process.
    """
    await state.clear()
    await state.set_state(VoiceOrderState.get_voice)
    await message.answer(
        "<b>🎙️ Швидке замовлення голосом (Крок 1/3)</b>\n\n"
        "Запишіть одне голосове повідомлення, в якому скажіть, <b>звідки і куди</b> вам потрібно їхати.\n\n"
        "<i>Наприклад: «Добрий день, потрібне таксі від вулиці Київська 1 до Вокзалу».</i>",
        reply_markup=fsm_cancel_keyboard
    )

@router.message(VoiceOrderState.get_voice, F.voice)
async def process_voice_message(message: types.Message, state: FSMContext):
    """
    Receives the voice message and asks for optional location.
    """
    await state.update_data(begin_address_voice_id=message.voice.file_id)
    await state.set_state(VoiceOrderState.get_location)
    await message.answer(
        "<b>Крок 2/3: Ваша геолокація (необов'язково)</b>\n\n"
        "Щоб водію було легше вас знайти, ви можете поділитися своєю геолокацією. "
        "Або просто пропустіть цей крок.",
        reply_markup=location_or_skip_keyboard
    )

@router.message(VoiceOrderState.get_voice)
async def wrong_input_for_voice(message: types.Message):
    """Catches any input other than a voice message at the first step."""
    await message.answer("Будь ласка, надішліть саме <b>голосове повідомлення</b>, щоб створити замовлення.")

@router.message(VoiceOrderState.get_location, F.location)
async def process_location(message: types.Message, state: FSMContext):
    """Processes the location and asks for the phone number."""
    await state.update_data(latitude=message.location.latitude, longitude=message.location.longitude)
    await message.answer("✅ Геолокацію отримано.")
    await state.set_state(VoiceOrderState.get_number)
    await message.answer(
        '📱 <b>Крок 3/3: Ваш контакт</b>\n\nНадішліть ваш номер телефону для зв\'язку з водієм.',
        reply_markup=phone_request_keyboard
    )

@router.message(VoiceOrderState.get_location, F.text == '➡️ Пропустити')
async def skip_location(message: types.Message, state: FSMContext):
    """Skips the location step and asks for the phone number."""
    await state.set_state(VoiceOrderState.get_number)
    await message.answer(
        '📱 <b>Крок 3/3: Ваш контакт</b>\n\nНадішліть ваш номер телефону для зв\'язку з водієм.',
        reply_markup=phone_request_keyboard
    )

@router.message(VoiceOrderState.get_location)
async def wrong_input_for_location(message: types.Message):
    """Catches incorrect input at the location step."""
    await message.answer("Будь ласка, натисніть одну з кнопок: 'Надіслати геолокацію' або 'Пропустити'.")

@router.message(VoiceOrderState.get_number, (F.contact | F.text))
async def process_phone_and_create_order(message: types.Message, state: FSMContext):
    """Processes the phone number, creates, and dispatches the order."""
    phone_number = message.contact.phone_number if message.contact else message.text

    if not is_valid_phone(phone_number):
        await message.answer("❌ <b>Неправильний формат номеру.</b>\n\nБудь ласка, введіть коректний номер або поділіться контактом.")
        return

    await state.update_data(number=phone_number)
    await db_queries.update_client_phone(message.from_user.id, phone_number)

    user_data = await state.get_data()
    # Finalize data for order creation
    final_order_data = {
        'order_type': 'single_voice_order',
        'begin_address': "📍 Адреса у голосовому повідомленні",
        'finish_address': "📍 Адреса у голосовому повідомленні",
        'begin_address_voice_id': user_data.get('begin_address_voice_id'),
        'latitude': user_data.get('latitude'),
        'longitude': user_data.get('longitude'),
        'number': user_data.get('number')
    }

    order_id = await db_queries.create_order_in_db(message.from_user.id, final_order_data, initial_status='searching')
    if not order_id:
        await message.answer("Сталася помилка під час створення замовлення. Будь ласка, почніть заново.", reply_markup=main_menu_keyboard)
    else:
        await dispatch_order_to_drivers(message.bot, order_id, final_order_data, message.from_user)
        await message.answer(
            "✅ <b>Ваше голосове замовлення створено!</b>\n\n"
            "<i>Ми почали пошук водія. Очікуйте на сповіщення.</i>",
            reply_markup=main_menu_keyboard
        )
    
    await state.clear()