from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
import html

from states.fsm_states import AdminState
from database import queries as db_queries
from keyboards.common import Navigate
from keyboards.reply_keyboards import fsm_cancel_keyboard
from keyboards.admin_keyboards import get_admin_management_keyboard
from utils.callback_factories import AdminAction
from .admin_helpers import update_admin_commands
from handlers.common.helpers import _display_client_profile
from config.config import ADMIN_IDS

router = Router()

async def show_admin_management_menu(target: types.Message | types.CallbackQuery):
    """Displays the admin management menu with a list of current admins."""
    all_admins = await db_queries.get_all_admins()
    # Exclude root admins from the list of manageable admins
    manageable_admins = [admin for admin in all_admins if admin['user_id'] not in ADMIN_IDS]

    text = "<b>👑 Керування адміністраторами</b>\n\n"
    if manageable_admins:
        text += "Натисніть на ім'я, щоб забрати права адміністратора."
    else:
        text += "Наразі немає додаткових адміністраторів."

    if isinstance(target, types.CallbackQuery):
        await target.message.edit_caption(caption=text, reply_markup=get_admin_management_keyboard(manageable_admins))
    else:
        await target.answer(text, reply_markup=get_admin_management_keyboard(manageable_admins))

@router.callback_query(Navigate.filter(F.to == "admin_management"))
async def admin_management_entry(call: types.CallbackQuery):
    """Entry point for the admin management menu."""
    await show_admin_management_menu(call)
    await call.answer()

@router.callback_query(AdminAction.filter(F.action == 'add_admin_start'))
async def add_admin_start(call: types.CallbackQuery, state: FSMContext):
    """Starts the FSM to add a new admin."""
    await state.set_state(AdminState.get_admin_id_to_add)
    await call.message.answer(
        "<b>➕ Додавання адміністратора</b>\n\n"
        "Введіть Telegram ID користувача, якому ви хочете надати права адміністратора.",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.get_admin_id_to_add)
async def process_add_admin_id(message: types.Message, state: FSMContext):
    """Processes the user ID, grants admin rights, and shows the updated list."""
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Помилка: ID має бути числом. Спробуйте ще раз.", reply_markup=fsm_cancel_keyboard)
        return

    user_id = int(message.text)
    
    if not await db_queries.get_client_name(user_id):
        await message.answer(f"❌ Користувача з ID <code>{user_id}</code> не знайдено. Переконайтесь, що він хоча б раз запускав бота.", reply_markup=fsm_cancel_keyboard)
        return

    if user_id in ADMIN_IDS:
        await message.answer(f"❌ Цей користувач є супер-адміністратором. Його права не можна змінити.", reply_markup=types.ReplyKeyboardRemove())
    else:
        await db_queries.set_admin_status(user_id, is_admin=True)
        await message.answer(f"✅ Права адміністратора надано користувачу ID <code>{user_id}</code>.", reply_markup=types.ReplyKeyboardRemove())
        try:
            await update_admin_commands(message.bot, user_id, is_admin=True)
            await message.bot.send_message(user_id, "🎉 Вітаємо! Вам надано права адміністратора.")
        except Exception:
            pass

    await state.clear()
    await show_admin_management_menu(message)

@router.callback_query(AdminAction.filter(F.action == 'remove_admin'))
async def remove_admin(call: types.CallbackQuery, callback_data: AdminAction):
    """Removes admin rights from a user."""
    user_id = callback_data.target_id
    if user_id in ADMIN_IDS:
        await call.answer("❌ Не можна видалити права у супер-адміністратора.", show_alert=True)
        return

    await db_queries.set_admin_status(user_id, is_admin=False)
    await call.answer("✅ Права адміністратора відкликано.", show_alert=True)
    try:
        await update_admin_commands(call.bot, user_id, is_admin=False)
        await call.bot.send_message(user_id, "❗️ Ваші права адміністратора було відкликано.")
    except Exception:
        pass

    await show_admin_management_menu(call)

@router.message(AdminState.get_admin_id_to_add, F.text == "🚫 Скасувати")
async def cancel_add_admin(message: types.Message, state: FSMContext):
    """Cancels the process of adding an admin."""
    await state.clear()
    await message.answer("✅ Додавання скасовано.", reply_markup=types.ReplyKeyboardRemove())
    await show_admin_management_menu(message)

@router.callback_query(AdminAction.filter(F.action == 'toggle_admin'))
async def toggle_admin_rights(call: types.CallbackQuery, callback_data: AdminAction):
    """Toggles admin rights for a user directly from their profile."""
    user_id = callback_data.target_id
    if user_id in ADMIN_IDS:
        await call.answer("❌ Не можна змінювати права супер-адміністратора.", show_alert=True)
        return

    is_currently_admin = await db_queries.is_user_admin(user_id)
    new_status = not is_currently_admin

    await db_queries.set_admin_status(user_id, is_admin=new_status)

    if new_status:
        await call.answer("✅ Права адміністратора надано.", show_alert=True)
        await update_admin_commands(call.bot, user_id, is_admin=True)
        notification_text = "🎉 Вітаємо! Вам надано права адміністратора."
    else:
        await call.answer("✅ Права адміністратора відкликано.", show_alert=True)
        await update_admin_commands(call.bot, user_id, is_admin=False)
        notification_text = "❗️ Ваші права адміністратора було відкликано."
    
    try:
        await call.bot.send_message(user_id, notification_text)
    except Exception:
        pass # Ignore if user blocked the bot

    # Refresh the profile view to show the updated status
    await _display_client_profile(call, user_id)