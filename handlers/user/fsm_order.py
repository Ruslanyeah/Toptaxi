from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
import html

from states.fsm_states import UserState, PreOrderState, DeliveryState
from keyboards.reply_keyboards import (
    build_address_input_keyboard, main_menu_keyboard, build_destination_address_keyboard,
    phone_request_keyboard, fsm_cancel_keyboard, comment_skip_keyboard
)
from database import queries as db_queries
from ..common.helpers import send_message_with_photo
from .order_helpers import process_phone_input, show_unified_confirmation
from config.config import BASE_DIR

router = Router()

ORDER_START_IMAGE_PATH = BASE_DIR / "assets" / "images" / "order_start.jpg"

# --- Entry Point ---

@router.message(F.text == '🚕 Замовити таксі')
async def start_order(message: types.Message, state: FSMContext) -> None:
    """
    Handles the "Order a taxi" button, starting the standard order FSM.
    """
    await state.clear()
    await state.set_state(UserState.locate)
    fav_addresses = await db_queries.get_user_fav_addresses(message.from_user.id)
    text = '📍 <b>Крок 1: Адреса подачі</b>\n\nБудь ласка, оберіть спосіб введення адреси:'
    await send_message_with_photo(message, ORDER_START_IMAGE_PATH, text, build_address_input_keyboard(fav_addresses))

# --- Final Steps: Phone and Comment ---

@router.message(UserState.number, (F.contact | F.text))
async def handle_phone(message: types.Message, state: FSMContext):
    await process_phone_input(message, state, next_state=UserState.comment)

@router.message(UserState.comment, F.text == 'Без коментаря')
async def handle_skip_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=None)
    await show_unified_confirmation(message, state, UserState.confirm_order)

@router.message(UserState.comment, F.text)
async def handle_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text)
    await show_unified_confirmation(message, state, UserState.confirm_order)