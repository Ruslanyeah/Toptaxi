from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup
from keyboards.reply_keyboards import (
    build_address_input_keyboard, main_menu_keyboard, build_destination_address_keyboard, 
    phone_request_keyboard, fsm_cancel_keyboard
)
from keyboards.user_keyboards import (
    get_confirm_unfound_address_keyboard, get_address_clarification_keyboard,
    get_confirm_clarified_address_keyboard
)
from keyboards.common import Navigate
from utils.callback_factories import (
    AddressCallbackData, ClarifyAddressCallbackData, ConfirmClarifiedAddress, ConfirmUnfoundAddress
)
from aiogram.exceptions import TelegramBadRequest
from config.config import DB_PATH, GEOCODING_CITY_CONTEXT, BASE_DIR
from ..common.helpers import send_message_with_photo
import html
import aiosqlite
from typing import Type
import re
from utils.geocoder import reverse, geocode
from database import queries as db_queries
from states.fsm_states import UserState, PreOrderState, DeliveryState
from .order_helpers import _go_to_finish_address_step, _go_to_phone_number_step
from loguru import logger

# Создаем собственный роутер для этой логики
router = Router()

# This module handles all FSM logic for address input.
# It's designed to be reusable across different order types (taxi, pre-order, delivery).
# The handlers are registered for a union of states from different FSMs.

# States for the very first step of address input (choosing method)
LOCATE_STATES = {UserState.locate, PreOrderState.locate, DeliveryState.locate}

# States for when the bot is expecting the user to type the START address
BEGIN_ADDRESS_STATES = {UserState.begin_address, PreOrderState.begin_address, DeliveryState.begin_address}

# States for when the bot is expecting a VOICE message for the START address
BEGIN_ADDRESS_VOICE_STATES = {UserState.begin_address_voice, PreOrderState.begin_address_voice, DeliveryState.begin_address_voice}

# States for when the bot is expecting the user to type the DESTINATION address
FINISH_ADDRESS_STATES = {UserState.finish_address, PreOrderState.finish_address, DeliveryState.finish_address}

# ((south_latitude, west_longitude), (north_latitude, east_longitude))
SUMY_OBLAST_VIEWBOX = ((50.35, 33.25), (51.9, 35.25))

def _shorten_address(full_address: str) -> str:
    """Removes redundant parts like region or district from the address string."""
    return full_address.replace("Сумська область, ", "").replace("Глухівський район, ", "").replace("місто Глухів, ", "").replace("Глухів, ", "").strip()

async def process_fav_address_begin(message: types.Message, state: FSMContext) -> None:
    """
    Handles the selection of a favorite address for the starting point.
    """
    fav_name = message.text.removeprefix('❤️ ')
    fav_addr = await db_queries.get_fav_address_by_name(message.from_user.id, fav_name)

    if not fav_addr:
        await message.answer("Не вдалося знайти цю збережену адресу. Спробуйте ще раз.")
        return

    await state.update_data(begin_address=fav_addr[0], latitude=fav_addr[1], longitude=fav_addr[2])
    await message.answer(f'✅ Адресу подачі встановлено: <b>{html.escape(fav_addr[0])}</b>')
    await _go_to_finish_address_step(message, state)

async def process_fav_address_finish(message: types.Message, state: FSMContext) -> None:
    """
    Handles selecting a favorite address for the destination.
    """
    fav_name = message.text.removeprefix('❤️ ')
    fav_addr = await db_queries.get_fav_address_by_name(message.from_user.id, fav_name)

    if not fav_addr:
        await message.answer("Не вдалося знайти цю збережену адресу. Спробуйте ще раз.")
        return

    await state.update_data(finish_address=fav_addr[0])
    await _go_to_phone_number_step(message, state)

async def _handle_manual_address_input(message: types.Message, state: FSMContext, current_address_type: str) -> None:
    """
    Helper to process a manually entered address for both start and destination.
    """
    try:
        if len(message.text) > 100:
            await message.answer("❌ Адреса занадто довга. Будь ласка, введіть більш короткий та точний варіант.", reply_markup=fsm_cancel_keyboard)
            return

        search_text = message.text
        # Add city context for better geocoding results
        if GEOCODING_CITY_CONTEXT and GEOCODING_CITY_CONTEXT.lower() not in search_text.lower():
            search_text = f"{search_text}, {GEOCODING_CITY_CONTEXT}"

        from states import fsm_states # Local import to avoid cycles

        locations = await geocode(
            search_text,
            language='uk',
            exactly_one=False,
            limit=5,
            viewbox=SUMY_OBLAST_VIEWBOX
        )

        current_state_group_name = (await state.get_state()).split(':')[0]
        states = getattr(fsm_states, current_state_group_name, fsm_states.UserState)

        if not locations:
            await state.update_data(unfound_address_text=message.text, unfound_address_type=current_address_type)
            await state.set_state(states.confirm_unfound_address)
            await message.answer(
                "⚠️ Не вдалося знайти цю адресу на карті. Ви можете використати введений текст як є, або спробувати ввести адресу знову.",
                reply_markup=get_confirm_unfound_address_keyboard()
            )
            return

        original_input = message.text
        if len(locations) > 1:
            clarification_options = [
                {"address": loc.address, "latitude": loc.latitude, "longitude": loc.longitude}
                for loc in locations
            ]
            await state.update_data(original_address_input=original_input, current_address_type=current_address_type)
            await state.update_data(clarification_options=clarification_options)
            
            next_clarify_state = states.clarify_begin_address if current_address_type == 'begin' else states.clarify_finish_address
            await state.set_state(next_clarify_state)
            
            prompt_text = "🤔 <b>Будь ласка, уточніть адресу подачі:</b>" if current_address_type == 'begin' else "🤔 <b>Будь ласка, уточніть адресу призначення:</b>"
            await message.answer(
                prompt_text,
                reply_markup=get_address_clarification_keyboard(locations)
            )
        else:
            location = locations[0]
            short_address = _shorten_address(location.address)

            if current_address_type == 'begin':
                await state.update_data(begin_address=short_address, latitude=location.latitude, longitude=location.longitude)
                await message.answer(f'✅ Адресу подачі встановлено: <b>{html.escape(short_address)}</b>')
                await _go_to_finish_address_step(message, state)
            else: # finish
                await state.update_data(finish_address=short_address)
                await message.answer(f'✅ Адресу призначення встановлено: <b>{html.escape(short_address)}</b>')
                await _go_to_phone_number_step(message, state)
                
    except Exception as e:
        logger.error(f"Geopy error during forward geocoding: {e}")
        await message.answer("Під час пошуку адреси сталася помилка. Спробуйте ще раз.", reply_markup=fsm_cancel_keyboard)

async def process_initial_location(message: types.Message, state: FSMContext) -> None:
    """
    Handles receiving a location for the starting address.
    """
    from states.fsm_states import UserState, PreOrderState, DeliveryState # Local import
    location = None
    try:
        location = await reverse(f"{message.location.latitude}, {message.location.longitude}", language='uk')
    except Exception as e:
        logger.error(f"Geopy reverse geocoding error: {e}")
        await message.answer("Не вдалося визначити адресу за вашою геолокацією. Спробуйте ввести адресу вручну.", reply_markup=main_menu_keyboard)
        await state.clear()
        return

    if location:
        short_address = _shorten_address(location.address)
        await state.update_data(begin_address=short_address, latitude=message.location.latitude, longitude=message.location.longitude)
        await message.answer(f'✅ Адресу подачі встановлено: <b>{html.escape(short_address)}</b>')
        await _go_to_finish_address_step(message, state)
    else:
        await message.answer("Не вдалося визначити адресу. Спробуйте ще раз або введіть вручну.")

async def process_clarify_with_driver(message: types.Message, state: FSMContext) -> None:
    """
    Handles the 'Clarify with driver' button for the destination address.
    """
    await state.update_data(finish_address="За погодженням з водієм")
    await _go_to_phone_number_step(message, state)

# --- Generic Logic Functions (not handlers) ---

async def process_confirm_unfound_address(call: types.CallbackQuery, callback_data: ConfirmUnfoundAddress, state: FSMContext):
    """
    Handles the user's choice after a manually entered address was not found on the map.
    """
    data = await state.get_data()
    address_type = data.get('unfound_address_type', 'begin')
    original_input = data.get('unfound_address_text', '') # Corrected key

    current_state_group_name = (await state.get_state()).split(':')[0]
    from states import fsm_states
    states = getattr(fsm_states, current_state_group_name, fsm_states.UserState)

    if callback_data.action == 'use_anyway':
        if address_type == 'begin':
            await state.update_data(begin_address=original_input, latitude=None, longitude=None)
            await call.message.edit_text(f'✅ Адресу подачі встановлено як: <b>{html.escape(original_input)}</b>')
            await _go_to_finish_address_step(call, state)
        else: # finish
            await state.update_data(finish_address=original_input)
            await call.message.edit_text(f'✅ Адресу призначення встановлено як: <b>{html.escape(original_input)}</b>')
            await _go_to_phone_number_step(call, state)
    elif callback_data.action == 'retry':
        next_state = states.begin_address if address_type == 'begin' else states.finish_address
        await state.set_state(next_state)
        await call.message.edit_text("Будь ласка, спробуйте ввести адресу ще раз, можливо, більш детально.", reply_markup=None)
    
    await call.answer()

async def process_clarified_address(call: types.CallbackQuery, callback_data: ClarifyAddressCallbackData, state: FSMContext):
    """
    Handles the user selecting one of the clarified address options.
    """
    data = await state.get_data()
    options = data.get('clarification_options', [])
    address_type = data.get('current_address_type', 'begin')
    
    if not options or callback_data.index >= len(options):
        await call.answer("Помилка: опція не знайдена. Спробуйте знову.", show_alert=True)
        return

    selected_option = options[callback_data.index]
    short_address = _shorten_address(selected_option['address'])

    if address_type == 'begin':
        await state.update_data(begin_address=short_address, latitude=selected_option['latitude'], longitude=selected_option['longitude'])
        await call.message.edit_text(f'✅ Адресу подачі встановлено: <b>{html.escape(short_address)}</b>')
        await _go_to_finish_address_step(call, state)
    else: # finish
        await state.update_data(finish_address=short_address)
        await call.message.edit_text(f'✅ Адресу призначення встановлено: <b>{html.escape(short_address)}</b>')
        await _go_to_phone_number_step(call, state)

    await call.answer()

async def process_clarify_skip(call: types.CallbackQuery, state: FSMContext):
    """
    Handles the user choosing to use their original text input instead of the clarified options.
    """
    data = await state.get_data()
    original_input = data.get('original_address_input', '')
    address_type = data.get('current_address_type', 'begin')

    if not original_input:
        await call.answer("Помилка: не вдалося знайти оригінальний текст. Спробуйте знову.", show_alert=True)
        return

    if address_type == 'begin':
        await state.update_data(begin_address=original_input, latitude=None, longitude=None)
        await call.message.edit_text(f'✅ Адресу подачі встановлено як: <b>{html.escape(original_input)}</b>')
        await _go_to_finish_address_step(call, state)
    else: # finish
        await state.update_data(finish_address=original_input)
        await call.message.edit_text(f'✅ Адресу призначення встановлено як: <b>{html.escape(original_input)}</b>')
        await _go_to_phone_number_step(call, state)
    
    await call.answer()

async def process_clarify_retry(call: types.CallbackQuery, state: FSMContext):
    """
    Handles the user wanting to re-enter the address after clarification failed.
    """
    data = await state.get_data()
    address_type = data.get('current_address_type', 'begin')
    
    current_state_group_name = (await state.get_state()).split(':')[0]
    from states import fsm_states
    states = getattr(fsm_states, current_state_group_name, fsm_states.UserState)

    next_state = states.begin_address if address_type == 'begin' else states.finish_address
    await state.set_state(next_state)
    await call.message.edit_text("Будь ласка, спробуйте ввести адресу ще раз, можливо, більш детально.", reply_markup=None)
    await call.answer()

# --- Centralized Handlers ---

# --- UserState Handlers ---
@router.message(UserState.locate, F.text == '✏️ Ввести адресу вручну')
async def handle_manual_input_begin_user(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Вкажіть <b>АДРЕСУ</b> або <b>МІСЦЕ</b>, звідки вас потрібно забрати:",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(UserState.begin_address)

@router.message(UserState.locate, F.text.startswith('❤️ '))
async def handle_fav_address_begin_user(message: types.Message, state: FSMContext):
    await process_fav_address_begin(message, state)

@router.message(UserState.locate, F.text == '🎙️ Записати голосом')
async def handle_voice_input_begin_user(message: types.Message, state: FSMContext):
    await message.answer(
        "🎙️ <b>Запишіть голосове повідомлення з адресою подачі.</b>\n\n"
        "Чітко назвіть вулицю та номер будинку.",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(UserState.begin_address_voice)

@router.message(UserState.locate, F.content_type == types.ContentType.LOCATION)
async def handle_location_begin_user(message: types.Message, state: FSMContext):
    await process_initial_location(message, state)

@router.message(UserState.begin_address, F.text)
async def handle_text_begin_user(message: types.Message, state: FSMContext):
    if message.text.startswith('❤️ '):
        await process_fav_address_begin(message, state)
    else:
        await _handle_manual_address_input(message, state, 'begin')

@router.message(UserState.begin_address_voice, F.voice)
async def handle_voice_begin_user(message: types.Message, state: FSMContext):
    await state.update_data(begin_address="📍 Адреса голосом", begin_address_voice_id=message.voice.file_id, latitude=None, longitude=None)
    await message.answer(f'✅ Адресу подачі записано як голосове повідомлення.')
    await _go_to_finish_address_step(message, state)

@router.message(UserState.finish_address, F.text == '✏️ Ввести адресу вручну')
async def handle_manual_input_finish_user(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Вкажіть, <b>КУДИ</b> вас потрібно відвезти:",
        reply_markup=fsm_cancel_keyboard,
    )
    # No state change needed, we are already in finish_address

@router.message(UserState.finish_address, F.text == '🎙️ Записати голосом')
async def handle_voice_input_finish_user(message: types.Message, state: FSMContext):
    await message.answer(
        "🎙️ <b>Запишіть голосове повідомлення з адресою призначення.</b>\n\n"
        "Чітко назвіть вулицю та номер будинку, або скажіть 'до центру', 'на вокзал' і т.д.",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(UserState.finish_address_voice)

@router.message(UserState.finish_address, F.text == '📍 Уточнити водієві')
async def handle_clarify_finish_user(message: types.Message, state: FSMContext):
    await process_clarify_with_driver(message, state)

@router.message(UserState.finish_address, F.text)
async def handle_text_finish_user(message: types.Message, state: FSMContext):
    if message.text.startswith('❤️ '):
        await process_fav_address_finish(message, state)
    else:
        await _handle_manual_address_input(message, state, 'finish')

@router.message(UserState.finish_address_voice, F.voice)
async def handle_voice_finish_user(message: types.Message, state: FSMContext):
    await state.update_data(finish_address="📍 Адреса голосом", finish_address_voice_id=message.voice.file_id)
    await message.answer(f'✅ Адресу призначення записано як голосове повідомлення.')
    await _go_to_phone_number_step(message, state)

# --- PreOrderState Handlers ---
@router.message(PreOrderState.locate, F.text == '✏️ Ввести адресу вручну')
async def handle_manual_input_begin_preorder(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Вкажіть <b>АДРЕСУ</b> або <b>МІСЦЕ</b>, звідки вас потрібно забрати:",
        reply_markup=fsm_cancel_keyboard,
    )
    await state.set_state(PreOrderState.begin_address)

@router.message(PreOrderState.locate, F.text.startswith('❤️ '))
async def handle_fav_address_begin_preorder(message: types.Message, state: FSMContext):
    await process_fav_address_begin(message, state)

@router.message(PreOrderState.locate, F.text == '🎙️ Записати голосом')
async def handle_voice_input_begin_preorder(message: types.Message, state: FSMContext):
    await message.answer(
        "🎙️ <b>Запишіть голосове повідомлення з адресою подачі.</b>\n\n"
        "Чітко назвіть вулицю та номер будинку.",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(PreOrderState.begin_address_voice)

@router.message(PreOrderState.locate, F.content_type == types.ContentType.LOCATION)
async def handle_location_begin_preorder(message: types.Message, state: FSMContext):
    await process_initial_location(message, state)

@router.message(PreOrderState.begin_address, F.text)
async def handle_text_begin_preorder(message: types.Message, state: FSMContext):
    if message.text.startswith('❤️ '): await process_fav_address_begin(message, state)
    else: await _handle_manual_address_input(message, state, 'begin')

@router.message(PreOrderState.begin_address_voice, F.voice)
async def handle_voice_begin_preorder(message: types.Message, state: FSMContext):
    await state.update_data(begin_address="📍 Адреса голосом", begin_address_voice_id=message.voice.file_id, latitude=None, longitude=None)
    await message.answer(f'✅ Адресу подачі записано як голосове повідомлення.')
    await _go_to_finish_address_step(message, state)

@router.message(PreOrderState.finish_address, F.text == '✏️ Ввести адресу вручну')
async def handle_manual_input_finish_preorder(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Вкажіть, <b>КУДИ</b> вас потрібно відвезти:",
        reply_markup=fsm_cancel_keyboard,
    )
    # No state change needed

@router.message(PreOrderState.finish_address, F.text == '🎙️ Записати голосом')
async def handle_voice_input_finish_preorder(message: types.Message, state: FSMContext):
    await message.answer(
        "🎙️ <b>Запишіть голосове повідомлення з адресою призначення.</b>\n\n"
        "Чітко назвіть вулицю та номер будинку, або скажіть 'до центру', 'на вокзал' і т.д.",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(PreOrderState.finish_address_voice)

@router.message(PreOrderState.finish_address, F.text == '📍 Уточнити водієві')
async def handle_clarify_finish_preorder(message: types.Message, state: FSMContext):
    await process_clarify_with_driver(message, state)

@router.message(PreOrderState.finish_address, F.text)
async def handle_text_finish_preorder(message: types.Message, state: FSMContext):
    if message.text.startswith('❤️ '): await process_fav_address_finish(message, state)
    else: await _handle_manual_address_input(message, state, 'finish')

@router.message(PreOrderState.finish_address_voice, F.voice)
async def handle_voice_finish_preorder(message: types.Message, state: FSMContext):
    await state.update_data(finish_address="📍 Адреса голосом", finish_address_voice_id=message.voice.file_id)
    await message.answer(f'✅ Адресу призначення записано як голосове повідомлення.')
    await _go_to_phone_number_step(message, state)

# --- DeliveryState Handlers ---
@router.message(DeliveryState.locate, F.text == '✏️ Ввести адресу вручну')
async def handle_manual_input_begin_delivery(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Вкажіть <b>АДРЕСУ</b> або <b>МІСЦЕ</b>, звідки потрібно забрати посилку:",
        reply_markup=fsm_cancel_keyboard,
    )
    await state.set_state(DeliveryState.begin_address)

@router.message(DeliveryState.locate, F.text.startswith('❤️ '))
async def handle_fav_address_begin_delivery(message: types.Message, state: FSMContext):
    await process_fav_address_begin(message, state)

@router.message(DeliveryState.locate, F.text == '🎙️ Записати голосом')
async def handle_voice_input_begin_delivery(message: types.Message, state: FSMContext):
    await message.answer(
        "🎙️ <b>Запишіть голосове повідомлення з адресою, звідки забрати посилку.</b>",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(DeliveryState.begin_address_voice)

@router.message(DeliveryState.locate, F.content_type == types.ContentType.LOCATION)
async def handle_location_begin_delivery(message: types.Message, state: FSMContext):
    await process_initial_location(message, state)

@router.message(DeliveryState.begin_address, F.text)
async def handle_text_begin_delivery(message: types.Message, state: FSMContext):
    if message.text.startswith('❤️ '): await process_fav_address_begin(message, state)
    else: await _handle_manual_address_input(message, state, 'begin')

@router.message(DeliveryState.begin_address_voice, F.voice)
async def handle_voice_begin_delivery(message: types.Message, state: FSMContext):
    await state.update_data(begin_address="📍 Адреса голосом", begin_address_voice_id=message.voice.file_id, latitude=None, longitude=None)
    await message.answer(f"✅ Адресу 'Звідки' записано як голосове повідомлення.")
    await _go_to_finish_address_step(message, state)

@router.message(DeliveryState.finish_address, F.text == '✏️ Ввести адресу вручну')
async def handle_manual_input_finish_delivery(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Вкажіть, <b>КУДИ</b> потрібно доставити:",
        reply_markup=fsm_cancel_keyboard,
    )
    # No state change needed

@router.message(DeliveryState.finish_address, F.text == '🎙️ Записати голосом')
async def handle_voice_input_finish_delivery(message: types.Message, state: FSMContext):
    await message.answer(
        "🎙️ <b>Запишіть голосове повідомлення з адресою доставки.</b>",
        reply_markup=fsm_cancel_keyboard
    )
    await state.set_state(DeliveryState.finish_address_voice)

@router.message(DeliveryState.finish_address, F.text)
async def handle_text_finish_delivery(message: types.Message, state: FSMContext):
    if message.text.startswith('❤️ '): await process_fav_address_finish(message, state)
    else: await _handle_manual_address_input(message, state, 'finish')

@router.message(DeliveryState.finish_address_voice, F.voice)
async def handle_voice_finish_delivery(message: types.Message, state: FSMContext):
    await state.update_data(finish_address="📍 Адреса голосом", finish_address_voice_id=message.voice.file_id)
    await message.answer(f'✅ Адресу доставки записано як голосове повідомлення.')
    await _go_to_phone_number_step(message, state)

# --- Handlers that were missing ---

ALL_CONFIRM_UNFOUND_STATES = {
    UserState.confirm_unfound_address, PreOrderState.confirm_unfound_address, DeliveryState.confirm_unfound_address
}
ALL_CLARIFY_STATES = {
    UserState.clarify_begin_address, UserState.clarify_finish_address,
    PreOrderState.clarify_begin_address, PreOrderState.clarify_finish_address,
    DeliveryState.clarify_begin_address, DeliveryState.clarify_finish_address
}

@router.callback_query(ConfirmUnfoundAddress.filter(F.action == "use_anyway"), F.state.in_(ALL_CONFIRM_UNFOUND_STATES))
async def handle_confirm_unfound_use_anyway(call: types.CallbackQuery, callback_data: ConfirmUnfoundAddress, state: FSMContext):
    """Handles the 'Use as is' button for an unfound address."""
    await process_confirm_unfound_address(call, callback_data, state)

@router.callback_query(ConfirmUnfoundAddress.filter(F.action == "retry"), F.state.in_(ALL_CONFIRM_UNFOUND_STATES))
async def handle_confirm_unfound_retry(call: types.CallbackQuery, callback_data: ConfirmUnfoundAddress, state: FSMContext):
    """Handles the 'Retry' button for an unfound address."""
    await process_confirm_unfound_address(call, callback_data, state)

@router.callback_query(ClarifyAddressCallbackData.filter(), F.state.in_(ALL_CLARIFY_STATES))
async def handle_clarified_address(call: types.CallbackQuery, callback_data: ClarifyAddressCallbackData, state: FSMContext):
    """Handles the choice of a clarified address."""
    await process_clarified_address(call, callback_data, state)

@router.callback_query(Navigate.filter(F.to == "clarify_addr_skip"), F.state.in_(ALL_CLARIFY_STATES))
async def handle_clarify_skip(call: types.CallbackQuery, state: FSMContext):
    """Handles skipping address clarification."""
    await process_clarify_skip(call, state)

@router.callback_query(Navigate.filter(F.to == "clarify_addr_retry"), F.state.in_(ALL_CLARIFY_STATES))
async def handle_clarify_retry(call: types.CallbackQuery, state: FSMContext):
    """Handles retrying address input after clarification."""
    await process_clarify_retry(call, state)
