from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
import html
from keyboards.reply_keyboards import (
    main_menu_keyboard, comment_skip_keyboard, phone_request_keyboard, build_address_input_keyboard,
    build_destination_address_keyboard, order_confirm_keyboard
)
from dateutil import parser
from utils.callback_factories import ConfirmUnfoundAddress
from database import queries as db_queries # Keep this import
from utils.validators import is_valid_phone
from loguru import logger

async def validate_addresses(message: types.Message, state: FSMContext, data: dict) -> bool:
    """
    Validates begin and finish addresses for an order.
    Returns True if valid, False otherwise (and sends an error message).
    """
    begin_address = data.get('begin_address')
    finish_address = data.get('finish_address')

    if not begin_address or not finish_address:
        await message.answer(
            "❌ <b>Помилка:</b> Адреса подачі або призначення не вказана.\n"
            "Будь ласка, почніть створення замовлення заново.",
            reply_markup=main_menu_keyboard
        )
        await state.clear()
        return False

    if begin_address == finish_address and finish_address != "За погодженням з водієм":
        await message.answer(
            "❌ <b>Помилка:</b> Адреса подачі та призначення не можуть бути однаковими.\n"
            "Будь ласка, почніть створення замовлення заново.",
            reply_markup=main_menu_keyboard
        )
        await state.clear()
        return False
    
    return True

def _shorten_address(full_address: str) -> str:
    """Removes redundant parts like region or district from the address string."""
    if not full_address:
        return ""
    parts_to_remove = ["Сумська область, ", "Глухівський район, ", "місто Глухів, ", "Глухів, "]
    for part in parts_to_remove:
        if full_address.startswith(part):
            return full_address.replace(part, '', 1).strip()
    return full_address

async def validate_order_data(data: dict) -> tuple[bool, str]:
    """
    Validates the collected order data before creating the order.
    Returns a tuple (is_valid, error_message).
    """
    order_type = data.get('order_type', 'taxi')

    if not data.get('number'):
        return False, "❌ Помилка: не вказано номер телефону. Почніть заново."

    if order_type == 'taxi' or order_type == 'pickup_delivery':
        if not data.get('begin_address') or not data.get('finish_address'):
            return False, "❌ Помилка: не вказано адресу подачі або призначення. Почніть заново."
        if data.get('begin_address') == data.get('finish_address') and data.get('finish_address') != "За погодженням з водієм":
            return False, "❌ Помилка: Адреса подачі та призначення не можуть бути однаковими. Почніть заново."
    
    if order_type == 'buy_delivery':
        if not data.get('finish_address'):
            return False, "❌ Помилка: не вказано адресу доставки. Почніть заново."
        if not data.get('order_details'):
            return False, "❌ Помилка: не вказано, що потрібно купити. Почніть заново."

    if order_type == 'pickup_delivery' and not data.get('order_details'):
        return False, "❌ Помилка: не вказано, що потрібно везти. Почніть заново."

    return True, ""

def format_confirmation_text(data: dict, is_final: bool = False) -> str:
    """
    Generates a formatted text string for order confirmation or final success message.
    """
    from dateutil import parser

    order_type = data.get('order_type', 'taxi')
    
    header = "✅ <b>Ваше замовлення створено!</b>\n\n" if is_final else "📝 <b>Підтвердження замовлення</b>\n\n"
    if is_final:
        if order_type in ['buy_delivery', 'pickup_delivery']: header = "✅ <b>Ваше замовлення на доставку створено!</b>\n\n"
        elif data.get('is_preorder'): header = "✅ <b>Ваше попереднє замовлення прийнято!</b>\n\n"
        footer = "\n<i>Ми почали пошук водія. Очікуйте на сповіщення.</i>"
        if data.get('is_preorder'): footer = "\n<i>Ми почнемо шукати водія завчасно, щоб подати машину вчасно.</i>"
    else:
        footer = "\n<i>Будь ласка, перевірте дані та підтвердіть створення замовлення.</i>"

    body = ""
    if data.get('is_preorder'): body += f"<b>Час подачі:</b> {parser.parse(data.get('scheduled_at')).strftime('%d.%m.%Y о %H:%M')}\n"
    if order_type == 'taxi': body += f"<b>Звідки:</b> {html.escape(str(data.get('begin_address')))}\n<b>Куди:</b> {html.escape(str(data.get('finish_address')))}\n"
    elif order_type == 'voice_taxi': body += f"<b>Звідки:</b> 🎙️ Адреса записана голосом\n<b>Куди:</b> 🎙️ Адреса записана голосом\n"
    elif order_type == 'buy_delivery': body += f"<b>Тип:</b> Купити і доставити\n<b>Що купити:</b> {html.escape(str(data.get('order_details')))}\n<b>Адреса доставки:</b> {html.escape(_shorten_address(data.get('finish_address', '')))}\n"
    elif order_type == 'pickup_delivery': body += f"<b>Тип:</b> Забрати і доставити\n<b>Звідки:</b> {html.escape(str(data.get('begin_address')))}\n<b>Куди:</b> {html.escape(str(data.get('finish_address')))}\n<b>Що везти:</b> {html.escape(str(data.get('order_details')))}\n"
    if data.get('comment'): body += f"<b>Коментар:</b> {html.escape(str(data.get('comment')))}\n"
    if data.get('number'): body += f"<b>Телефон:</b> {html.escape(str(data.get('number')))}\n"

    return header + body + footer

async def show_unified_confirmation(message: types.Message, state: FSMContext, next_state: State):
    """
    A unified helper to show the confirmation screen for any order type.
    """
    from keyboards.reply_keyboards import order_confirm_keyboard
    data = await state.get_data()
    confirmation_text = format_confirmation_text(data, is_final=False)
    await message.answer(confirmation_text, reply_markup=order_confirm_keyboard)
    await state.set_state(next_state)

async def _go_to_begin_address_step(target: types.Message | types.CallbackQuery, state: FSMContext):
    """Moves the FSM to the start address input step."""
    try:
        current_state_str = await state.get_state()
        if not current_state_str:
            logger.warning("Cannot go to begin address step: state is None.")
            return

        current_state_group_name = current_state_str.split(':')[0]
        states = globals().get(current_state_group_name)
        if not states: # Fallback
            from states.fsm_states import UserState
            states = UserState

        await state.set_state(states.locate)
        fav_addresses = await db_queries.get_user_fav_addresses(target.from_user.id)

        message_target = target.message if isinstance(target, types.CallbackQuery) else target
        await message_target.answer(
            '📍 <b>Крок 1: Адреса подачі</b>\n\nБудь ласка, оберіть спосіб введення адреси:',
            reply_markup=build_address_input_keyboard(fav_addresses)
        )
    except Exception as e:
        logger.exception(f"Error in _go_to_begin_address_step: {e}")

async def _go_to_finish_address_step(target: types.Message | types.CallbackQuery, state: FSMContext):
    """Moves the FSM to the destination address input step."""
    try:
        current_state_str = await state.get_state()
        if not current_state_str:
            logger.warning("Cannot go to finish address step: state is None.")
            return

        current_state_group_name = current_state_str.split(':')[0]
        from states import fsm_states
        states = getattr(fsm_states, current_state_group_name, fsm_states.UserState)
        if not states: # Fallback
            from states.fsm_states import UserState
            states = UserState
        
        # Only set the state if we are not already in a more specific sub-state
        # Always set the state to finish_address when moving to this step.
        await state.set_state(states.finish_address)

        data = await state.get_data()
        fav_addresses = await db_queries.get_user_fav_addresses(target.from_user.id)
        is_preorder = data.get('is_preorder', False)
        step_num = "3" if is_preorder else "2"
        
        message_target = target.message if isinstance(target, types.CallbackQuery) else target
        # Use .answer() for new messages, not .reply()
        await message_target.answer(
            f'🏁 <b>Крок {step_num}: Адреса призначення</b>\n\nТепер вкажіть, <b>КУДИ</b> вас потрібно відвезти',
            reply_markup=build_destination_address_keyboard(fav_addresses)
        )
    except Exception as e:
        logger.exception(f"Error in _go_to_finish_address_step: {e}")

async def _go_to_phone_number_step(target: types.Message | types.CallbackQuery, state: FSMContext):
    """Moves the FSM to the phone number input step."""
    message_target = target.message if isinstance(target, types.CallbackQuery) else target
    
    current_state_str = await state.get_state()
    current_state_group_name = current_state_str.split(':')[0]
    states = globals().get(current_state_group_name)
    if not states: # Fallback
        from states.fsm_states import UserState
        states = UserState

    next_state = states.number if hasattr(states, 'number') else states.get_phone
    await state.set_state(next_state)
    await message_target.answer(
        '📱 <b>Ваш контакт</b>\n\nНадішліть ваш номер телефону для зв\'язку з водієм.',
        reply_markup=phone_request_keyboard
    )

async def process_phone_input(
    message: types.Message,
    state: FSMContext,
    next_state: State
) -> None:
    """
    Processes user's phone number from text or contact and moves to the next state.
    """
    phone_number = message.contact.phone_number if message.contact else message.text

    if is_valid_phone(phone_number):
        await state.update_data(number=phone_number)
        await db_queries.update_client_phone(message.from_user.id, phone_number)
        # After phone, always go to comment state
        await state.set_state(next_state) # This should be the comment state
        await message.answer(
            f"💬 <b>Коментар до замовлення</b> (необов'язково)\n\n"
            "Можете додати будь-яку важливу інформацію для водія.",
            reply_markup=comment_skip_keyboard
        )
    else:
        await message.answer(
            "❌ <b>Неправильний формат номеру.</b>\n\n"
            "Будь ласка, введіть коректний номер телефону або натисніть кнопку '📱 Поділитися номером телефону'.",
            reply_markup=phone_request_keyboard
        )

async def process_voice_comment_input(
    message: types.Message, 
    state: FSMContext, 
    next_state: State
) -> None:
    """
    Processes user's phone number from text or contact and moves to the next state.
    """
    await state.update_data(comment="🎤 Голосовий коментар", comment_voice_id=message.voice.file_id)
    await message.answer("✅ Ваш голосовий коментар збережено.")
    # After voice comment, go to confirmation
    await show_unified_confirmation(message, state, next_state)
