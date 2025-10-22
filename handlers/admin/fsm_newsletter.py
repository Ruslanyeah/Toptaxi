from aiogram import types, F, Router, Bot
from aiogram.fsm.context import FSMContext
import asyncio
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from states.fsm_states import AdminState
from database import queries as db_queries
from keyboards.reply_keyboards import fsm_cancel_keyboard
from keyboards.admin_keyboards import get_newsletter_audience_keyboard, get_newsletter_confirm_keyboard
from keyboards.common import Navigate
from utils.batch_sender import broadcast_messages

router = Router()

@router.callback_query(Navigate.filter(F.to == "news"))
async def start_newsletter(call: types.CallbackQuery, state: FSMContext):
    """Starts the newsletter FSM by asking for the audience."""
    await state.set_state(AdminState.newsletter_audience)

    # Fetch user counts for each category
    total_users_count = await db_queries.get_clients_count()
    total_drivers_count = await db_queries.get_total_drivers_count()
    counts = {
        'all': total_users_count,
        'drivers': total_drivers_count,
        'clients': total_users_count - total_drivers_count
    }

    await call.message.edit_caption(
        "<b>📣 Розсилка повідомлень</b>\n\n"
        "<b>Крок 1: Аудиторія</b>\n\n"
        "Оберіть, кому ви хочете надіслати повідомлення:",
        reply_markup=get_newsletter_audience_keyboard(counts)
    )
    await call.answer()

@router.callback_query(Navigate.filter(F.to.startswith("nl_audience_")), AdminState.newsletter_audience)
async def set_newsletter_audience(call: types.CallbackQuery, callback_data: Navigate, state: FSMContext):
    """Sets the audience and asks for the message content."""
    audience = callback_data.to.split('_')[-1]
    await state.update_data(audience=audience)
    await state.set_state(AdminState.newsletter_message)

    audience_map = {'all': 'Всім користувачам', 'clients': 'Тільки клієнтам', 'drivers': 'Тільки водіям'}

    await call.message.edit_caption(
        f"<b>Крок 2: Повідомлення</b>\n\n"
        f"<i>Аудиторія: {audience_map.get(audience, 'Невідомо')}</i>\n\n"
        "Тепер надішліть повідомлення, яке ви хочете розіслати. "
        "Це може бути текст, фото, відео або будь-який інший тип контенту.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data=Navigate(to="news").pack())]])
    )
    await call.answer()

@router.message(AdminState.newsletter_message)
async def process_newsletter_message(message: types.Message, state: FSMContext):
    """
    Receives the message to be broadcasted and shows a confirmation screen.
    """
    data = await state.get_data()
    audience = data.get('audience')

    user_ids_tuples = []
    if audience == 'all':
        user_ids_tuples = await db_queries.get_all_users_id()
    elif audience == 'clients':
        user_ids_tuples = await db_queries.get_clients_only_ids()
    elif audience == 'drivers':
        user_ids_tuples = await db_queries.get_all_drivers_id()
    
    user_ids = [item[0] for item in user_ids_tuples]

    if not user_ids:
        await message.answer("Не знайдено користувачів для цієї аудиторії.")
        await state.clear()
        return
    
    # Save message details and user IDs to the state
    await state.update_data(
        message_to_send_id=message.message_id,
        chat_to_send_from_id=message.chat.id,
        user_ids=user_ids
    )
    await state.set_state(AdminState.newsletter_confirm)

    # Show a preview of the message
    await message.copy_to(chat_id=message.chat.id)
    
    await message.answer(
        f"<b>Крок 3: Підтвердження</b>\n\n"
        f"Ви збираєтеся надіслати це повідомлення <b>{len(user_ids)}</b> користувачам.\n\n"
        "<b>Все вірно?</b>",
        reply_markup=get_newsletter_confirm_keyboard()
    )

@router.callback_query(Navigate.filter(F.to == "nl_confirm_send"), AdminState.newsletter_confirm)
async def confirm_and_send_newsletter(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    """
    Confirms and starts the broadcasting task.
    """
    data = await state.get_data()
    user_ids = data.get('user_ids', [])
    message_id = data.get('message_to_send_id')
    chat_id = data.get('chat_to_send_from_id')

    if not all([user_ids, message_id, chat_id]):
        await call.message.edit_text("❌ Помилка: дані для розсилки втрачено. Спробуйте знову.")
        await state.clear()
        return

    # Clear the state immediately so the admin can continue working
    await state.clear()

    # Edit the confirmation message to show progress
    status_message = await call.message.edit_text(
        f"✅ Починаю розсилку для <b>{len(user_ids)}</b> користувачів. "
        "Я повідомлю вас про завершення."
    )

    # Define the specific send function for this broadcast
    async def send_copy(user_id: int):
        await bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)

    # Run the broadcasting in the background
    async def run_broadcast():
        logger.info(f"Starting newsletter for {len(user_ids)} users.")
        success, failed = await broadcast_messages(bot, user_ids, send_copy, status_message)
        logger.info(f"Newsletter finished. Success: {success}, Failed: {failed}.")
        # Send the final report to the admin
        await bot.send_message(
            chat_id,
            f"✅ <b>Розсилку завершено!</b>\n\nУспішно надіслано: {success}\nПомилок: {failed}"
        )

    asyncio.create_task(run_broadcast())
    await call.answer()

@router.callback_query(Navigate.filter(F.to == "nl_change_message"), AdminState.newsletter_confirm)
async def change_newsletter_message(call: types.CallbackQuery, state: FSMContext):
    """Allows the admin to go back and send a different message."""
    await state.set_state(AdminState.newsletter_message)
    await call.message.edit_text(
        "<b>Крок 2: Повідомлення (змінено)</b>\n\n"
        "Будь ласка, надішліть нове повідомлення для розсилки.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data=Navigate(to="news").pack())]])
    )
    await call.answer()