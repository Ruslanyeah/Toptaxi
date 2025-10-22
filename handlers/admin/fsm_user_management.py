from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
import html
from aiogram.filters import StateFilter

from states.fsm_states import AdminState
from database import queries as db_queries
from keyboards.common import Navigate
from keyboards.reply_keyboards import fsm_cancel_keyboard
from utils.callback_factories import AdminClientAction
from .admin_helpers import show_clients_page
from ..common.helpers import _display_client_profile

router = Router()

# --- Search Client ---
@router.callback_query(Navigate.filter(F.to == 'start_client_search'))
async def start_client_search(call: types.CallbackQuery, state: FSMContext):
    """Starts the FSM to search for a client."""
    await state.set_state(AdminState.get_client_search_query)
    await call.message.answer(
        "<b>🔎 Пошук користувача</b>\n\n"
        "Введіть ID, ім'я, або номер телефону для пошуку.",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.get_client_search_query)
async def process_client_search_query(message: types.Message, state: FSMContext):
    """Processes the search query and shows the results."""
    query = message.text
    await state.update_data(client_search_query=query)
    await message.answer("🔎 Виконую пошук...", reply_markup=types.ReplyKeyboardRemove())
    await show_clients_page(message, page=0, search_query=query)

# --- Ban/Unban Client ---
@router.callback_query(AdminClientAction.filter(F.action == 'ban'))
async def ban_client_start(call: types.CallbackQuery, callback_data: AdminClientAction, state: FSMContext):
    """Starts the FSM to ban a client."""
    await state.set_state(AdminState.get_ban_reason)
    await state.update_data(user_id_to_ban=callback_data.user_id)
    await call.message.answer(
        f"<b>🚫 Блокування користувача ID {callback_data.user_id}</b>\n\n"
        "Введіть причину блокування (буде видна користувачу).",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.get_ban_reason)
async def process_ban_reason(message: types.Message, state: FSMContext):
    """Processes the ban reason and bans the user."""
    if not message.text:
        await message.answer("Будь ласка, введіть причину блокування.", reply_markup=fsm_cancel_keyboard)
        return

    data = await state.get_data()
    user_id = data.get('user_id_to_ban')
    
    await db_queries.ban_user(user_id, message.text)
    await message.answer(f"✅ Користувача ID <code>{user_id}</code> заблоковано.")
    await message.answer("Блокування завершено.", reply_markup=types.ReplyKeyboardRemove())
    
    try:
        await message.bot.send_message(user_id, f"<b>Ваш акаунт було заблоковано.</b>\nПричина: {html.escape(message.text)}")
    except Exception:
        pass # Ignore if user blocked the bot

    await _display_client_profile(message, user_id)
    await state.clear()

@router.callback_query(AdminClientAction.filter(F.action == 'unban'))
async def unban_client(call: types.CallbackQuery, callback_data: AdminClientAction):
    """Unbans a client."""
    user_id = callback_data.user_id
    await db_queries.unban_user(user_id)
    await call.answer(f"✅ Користувача ID {user_id} розблоковано.", show_alert=True)
    
    try:
        await call.bot.send_message(user_id, "<b>🎉 Ваш акаунт було розблоковано.</b>")
    except Exception:
        pass

    await _display_client_profile(call, user_id)

# --- Send Message to User ---
@router.callback_query(AdminClientAction.filter(F.action == 'send_message'))
async def send_message_to_user_start(call: types.CallbackQuery, callback_data: AdminClientAction, state: FSMContext):
    """Starts the FSM to send a message to a specific user."""
    await state.set_state(AdminState.get_message_to_user)
    await state.update_data(user_id_to_message=callback_data.user_id)
    await call.message.answer(
        f"<b>✉️ Відправка повідомлення користувачу ID {callback_data.user_id}</b>\n\n"
        "Надішліть повідомлення (текст, фото, тощо), яке потрібно відправити.",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.get_message_to_user)
async def process_message_to_user(message: types.Message, state: FSMContext):
    """Copies and sends the message to the target user."""
    data = await state.get_data()
    user_id = data.get('user_id_to_message')
    
    try:
        # Используем copy_message для поддержки всех типов контента, но без клавиатуры
        await message.bot.copy_message(chat_id=user_id, from_chat_id=message.chat.id, message_id=message.message_id)
        await message.answer(f"✅ Повідомлення успішно надіслано користувачу ID <code>{user_id}</code>.", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e:
        await message.answer(f"❌ Не вдалося надіслати повідомлення: {e}", reply_markup=types.ReplyKeyboardRemove())
    
    await state.clear()
    await _display_client_profile(message, user_id) # Возвращаемся к профилю

# --- Get User Info by ID ---
@router.callback_query(Navigate.filter(F.to == 'get_user_info'))
async def get_user_info_start(call: types.CallbackQuery, state: FSMContext):
    """Starts the FSM to get user info by ID."""
    await state.set_state(AdminState.get_user_id_for_info)
    # Нельзя редактировать сообщение, чтобы добавить ReplyKeyboard. Отправляем новое.
    await call.message.answer(
        "<b>ℹ️ Інформація по ID</b>\n\nВведіть Telegram ID користувача.",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.get_user_id_for_info)
async def process_get_user_info_id(message: types.Message, state: FSMContext):
    """Processes the user ID and shows their profile."""
    if not message.text.isdigit():
        await message.answer("❌ Помилка: ID користувача має бути числом. Спробуйте ще раз.", reply_markup=fsm_cancel_keyboard)
        return

    user_id = int(message.text)
    await state.clear()
    await message.answer("✅ Пошук завершено.", reply_markup=types.ReplyKeyboardRemove())
    await _display_client_profile(message, user_id)

# --- Generic FSM Cancellation ---

@router.message(
    StateFilter(
        AdminState.get_client_search_query,
        AdminState.get_ban_reason,
        AdminState.get_message_to_user,
        AdminState.get_user_id_for_info
    ),
    F.text == "🚫 Скасувати"
)
async def cancel_user_management_action(message: types.Message, state: FSMContext):
    """Cancels any FSM action in this module."""
    await state.clear()
    await message.answer("✅ Дію скасовано.", reply_markup=types.ReplyKeyboardRemove())
    # Можно добавить возврат в меню управления пользователями, если нужно
    # await user_management_menu(message) # Потребует импорта и небольшой адаптации