from aiogram import types, F, Router
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from keyboards.reply_keyboards import main_menu_keyboard
from keyboards.reply_keyboards import build_address_input_keyboard
from keyboards.user_keyboards import get_contacts_keyboard
from config.config import BASE_DIR
from states.fsm_states import UserState
from ..common.helpers import send_message_with_photo
from database import queries as db_queries
import html
from loguru import logger

router = Router()

WELCOME_IMAGE_PATH = BASE_DIR / "assets" / "images" / "main_menu.jpg"
ORDER_START_IMAGE_PATH = BASE_DIR / "assets" / "images" / "order_start.jpg"

WELCOME_TEXT = (
    '<b>"Top🚕Taxi Глухів" – ваш надійний друг на дорозі!</b>\n\n'
    '📜 <b>Що ми пропонуємо:</b>\n'
    '• Швидкі поїздки містом та за його межі\n'
    '• Поїздки без стресу і зайвого клопоту\n'
    '• Тверезий водій, якщо вечір був насиченим\n'
    '• Поїздки з дітьми (дитячі крісла за потребою)\n'
    '• Доставка документів та невеликих пакунків'
)

@router.message(CommandStart())
async def menu_handler(message: types.Message) -> None:
    """
    Handles the /start command. Greets the user, creates or updates their
    profile in the database, and displays the main menu.

    Args:
        message: The user's message.
    """
    user = message.from_user
    await db_queries.add_or_update_user(
        user_id=user.id,
        full_name=user.full_name,
        username=user.username
    )
    personalized_text = f"<b>Привіт, {html.escape(user.first_name)}!</b>\n\n" + WELCOME_TEXT
    await send_message_with_photo(message, WELCOME_IMAGE_PATH, personalized_text, main_menu_keyboard)

@router.message(Command('stop'))
async def stop_command_handler(message: types.Message, state: FSMContext) -> None:
    """
    Handles the /stop command, cancelling any active FSM state
    and returning the user to the main menu.

    Args:
        message: The user's message.
        state: The FSM context.
    """
    await state.clear()
    await message.answer("✅ Дію скасовано. Ви повернулися в головне меню.", reply_markup=main_menu_keyboard)

@router.callback_query(F.data == "stop_fsm")
async def stop_fsm_callback_handler(call: types.CallbackQuery, state: FSMContext) -> None:
    """
    Handles the "Cancel action" inline button, cancelling any active FSM state.
    """
    await state.clear()
    try:
        await call.message.edit_text("✅ Дію скасовано.", reply_markup=None)
    except Exception:
        await call.message.answer("✅ Дію скасовано. Ви повернулися в головне меню.", reply_markup=main_menu_keyboard)
    await call.answer()

@router.message(F.text == '🔙 Повернутися в меню', StateFilter('*'))
async def back_handler(message: types.Message, state: FSMContext) -> None:
    """
    Handles the "Back to menu" button, clearing any state and showing the main menu.

    Args:
        message: The user's message.
        state: The FSM context.
    """
    await state.clear()
    personalized_text = f"<b>Привіт, {html.escape(message.from_user.first_name)}!</b>\n\n" + WELCOME_TEXT
    await send_message_with_photo(message, WELCOME_IMAGE_PATH, personalized_text, main_menu_keyboard)

@router.message(F.text == '🚫 Скасувати')
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    """
    Handles the "Cancel order" button during the FSM order creation process.
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("ℹ️ Наразі немає активного замовлення для скасування.", reply_markup=main_menu_keyboard)
        return

    await state.clear()
    # To provide a consistent experience, show the main menu with the image after cancellation.
    await message.answer('✅ Створення замовлення скасовано. Ви повернулися в головне меню.')
    personalized_text = f"<b>Привіт, {html.escape(message.from_user.first_name)}!</b>\n\n" + WELCOME_TEXT
    await send_message_with_photo(message, WELCOME_IMAGE_PATH, personalized_text, main_menu_keyboard)

@router.message(F.text == '☎️ Контакти та допомога')
async def contacts_handler(message: types.Message) -> None:
    """
    Displays contact information.

    Args:
        message: The user's message.
    """
    operator_phone = "+380992782620"
    text = (
        f"<b>Зв'язок з нами:</b>\n\n"
        f"📞 <b>Телефон оператора для дзвінків:</b>\n"
        f"<code>{operator_phone}</code>\n\n"
        f"Якщо у вас виникли питання або проблеми, ви можете зателефонувати нам.\n\n"
        f"Також, слідкуйте за нами в соцмережах та залишайте відгуки!"
    )
    await message.answer(text, reply_markup=get_contacts_keyboard())
