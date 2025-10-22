from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from states.fsm_states import DeliveryState
from keyboards.reply_keyboards import (
    delivery_type_keyboard, fsm_cancel_keyboard, phone_request_keyboard,
    order_confirm_keyboard, main_menu_keyboard
)
from database import queries as db_queries
import html
from .order_helpers import process_phone_input, show_unified_confirmation
from ..common.helpers import send_message_with_photo
from loguru import logger
from config.config import BASE_DIR

router = Router()

DELIVERY_START_IMAGE_PATH = BASE_DIR / "assets" / "images" / "delivery_start.jpg"
DELIVERY_PICKUP_IMAGE_PATH = BASE_DIR / "assets" / "images" / "delivery_pickup.jpg"
DELIVERY_SHOPPING_IMAGE_PATH = BASE_DIR / "assets" / "images" / "delivery_shopping.jpg"


# --- Entry Point & Type Selection ---

@router.message(F.text == '📦 Замовити доставку')
async def start_delivery_order(message: types.Message, state: FSMContext):
    """Handles the 'Order Delivery' button, starting the FSM."""
    await state.clear()
    await state.set_state(DeliveryState.get_type)
    await send_message_with_photo(
        message,
        DELIVERY_START_IMAGE_PATH,
        "<b>📦 Замовлення доставки</b>\n\n"
        "Оберіть, будь ласка, тип доставки:",
        reply_markup=delivery_type_keyboard
    )

@router.message(DeliveryState.get_type, F.text.in_(['🛍️ Купити і доставити', '📮 Забрати і доставити']))
async def process_delivery_type(message: types.Message, state: FSMContext):
    """Processes the selected delivery type and moves to the next step."""
    if message.text == '🛍️ Купити і доставити':
        await state.update_data(order_type='buy_delivery')
        await state.set_state(DeliveryState.get_shopping_list)
        await message.answer(
            "<b>Список покупок</b>\n\n"
            "Напишіть, що потрібно купити. За бажанням, вкажіть магазин.\n\n"
            "<i>Наприклад: Хліб, молоко в АТБ.</i>",
            reply_markup=fsm_cancel_keyboard
        )
    elif message.text == '📮 Забрати і доставити':
        from keyboards.reply_keyboards import build_address_input_keyboard
        await state.update_data(order_type='pickup_delivery')
        await state.set_state(DeliveryState.locate) # Use the new 'locate' state
        fav_addresses = await db_queries.get_user_fav_addresses(message.from_user.id)
        text = "<b>Адреса, звідки забрати</b>\n\nБудь ласка, оберіть спосіб введення адреси, звідки забрати посилку."
        await send_message_with_photo(message, DELIVERY_PICKUP_IMAGE_PATH, text, build_address_input_keyboard(fav_addresses))

# --- "Buy and Deliver" FSM Handlers ---

@router.message(DeliveryState.get_shopping_list, F.text)
async def process_shopping_list(message: types.Message, state: FSMContext):
    """Processes the shopping list and asks for the delivery address."""
    await state.update_data(order_details=message.text)
    await state.set_state(DeliveryState.finish_address) # Correct state for destination address
    from keyboards.reply_keyboards import build_address_input_keyboard # Use the simpler keyboard
    fav_addresses = await db_queries.get_user_fav_addresses(message.from_user.id)
    text = "<b>Адреса доставки</b>\n\nТепер введіть адресу, куди потрібно доставити покупки."
    await send_message_with_photo(message, DELIVERY_SHOPPING_IMAGE_PATH, text, build_address_input_keyboard(fav_addresses))

# --- "Pick up and Deliver" FSM Handlers ---

@router.message(DeliveryState.get_parcel_description)
async def process_parcel_description(message: types.Message, state: FSMContext):
    """Processes the parcel description and asks for the phone number."""
    await state.update_data(order_details=message.text) # This was missing
    await state.set_state(DeliveryState.get_phone)
    await message.answer(
        "<b>Ваш контакт</b>\n\n"
        "Надішліть ваш номер телефону для зв'язку з водієм.",
        reply_markup=phone_request_keyboard
    )

# --- Custom transition handler for Delivery FSM ---
@router.message(DeliveryState.address_input_completed)
async def after_address_input_for_delivery(message: types.Message, state: FSMContext):
    """
    This handler catches the custom state set by fsm_address_logic
    and decides where to go next based on the delivery type.
    """
    data = await state.get_data()
    if data.get('order_type') == 'pickup_delivery':
        # For pickup_delivery, we need to ask for parcel description
        await state.set_state(DeliveryState.get_parcel_description)
        await message.answer(
            "<b>Опис посилки</b>\n\n"
            "Напишіть, що саме потрібно перевезти (наприклад, 'документи', 'невеликий пакунок').",
            reply_markup=fsm_cancel_keyboard
        )
    else: # For 'buy_delivery' and potentially other types, go straight to phone
        await state.set_state(DeliveryState.get_phone)
        await message.answer(
            "<b>Ваш контакт</b>\n\n"
            "Надішліть ваш номер телефону для зв'язку з водієм.",
            reply_markup=phone_request_keyboard
        )

# --- Common FSM Handlers (Phone & Confirmation) ---
@router.message(DeliveryState.get_phone, (F.contact | F.text))
async def process_delivery_phone(message: types.Message, state: FSMContext):
    """Processes the phone number and shows the final confirmation."""
    # The process_phone_input helper will handle validation and move to the next state (comment)
    await process_phone_input(message, state, next_state=DeliveryState.get_comment) # This line is already correct, but we confirm it

@router.message(DeliveryState.get_comment, F.text == 'Без коментаря') # This line is already correct, but we confirm it
async def skip_delivery_comment(message: types.Message, state: FSMContext):
    """Handles skipping the comment for a delivery order."""
    await state.update_data(comment=None)
    await show_unified_confirmation(message, state, DeliveryState.confirm_delivery)

@router.message(DeliveryState.get_comment, F.text) # This line is already correct, but we confirm it
async def process_delivery_comment(message: types.Message, state: FSMContext):
    """Handles the comment for a delivery order."""
    await state.update_data(comment=message.text)
    await show_unified_confirmation(message, state, DeliveryState.confirm_delivery)

# Общие обработчики адресов регистрируются централизованно в handlers/__init__.py