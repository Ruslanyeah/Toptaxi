from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
import html
from database import queries as db_queries
from keyboards.admin_keyboards import get_driver_profile_keyboard, get_client_profile_keyboard
from keyboards.common import Navigate
from dateutil import parser

async def safe_edit_or_send(
    target: types.Message | types.CallbackQuery,
    text: str,
    reply_markup: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup | None = None,
    **kwargs
) -> types.Message:
    """
    A helper function to safely edit a message if it's a CallbackQuery
    or send a new one if it's a Message.
    """
    try:
        if isinstance(target, types.CallbackQuery):
            # Answer the callback query to remove the "loading" state on the button
            await target.answer()
            # Edit the message text
            return await target.message.edit_text(text, reply_markup=reply_markup, **kwargs)
        else:
            # Send a new message
            return await target.answer(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as e:
        # This can happen if the message content is unchanged.
        if "message is not modified" in e.message:
            logger.trace("Message not modified, skipping edit.")
            # Still need to answer the callback if it's a callback query
            if isinstance(target, types.CallbackQuery):
                await target.answer()
            return target.message if isinstance(target, types.CallbackQuery) else target
        else:
            logger.error(f"Error during safe_edit_or_send: {e}")
            # If editing fails for other reasons, try sending a new message as a fallback
            if isinstance(target, types.CallbackQuery):
                return await target.message.answer(text, reply_markup=reply_markup, **kwargs)
            raise e # Re-raise if it's not a "not modified" error on a message

async def send_message_with_photo(
    target: types.Message | types.CallbackQuery,
    photo_path: str,
    caption: str,
    reply_markup: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup | None = None,
    delete_old: bool = False
) -> types.Message:
    """
    Sends a message with a photo, handling both Message and CallbackQuery objects.
    Can delete the original message from a CallbackQuery.
    """
    photo = types.FSInputFile(photo_path)
    chat_id = target.chat.id if isinstance(target, types.Message) else target.message.chat.id
    
    if delete_old and isinstance(target, types.CallbackQuery):
        try:
            await target.message.delete()
        except TelegramBadRequest as e:
            logger.warning(f"Could not delete old message: {e}")

    return await target.bot.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=caption,
        reply_markup=reply_markup
    )

async def _display_driver_profile(target: types.Message | types.CallbackQuery, driver_id: int):
    """Displays a driver's profile to an admin."""
    driver_data = await db_queries.get_driver_details(driver_id)
    if not driver_data:
        await safe_edit_or_send(target, f"Водія з ID {driver_id} не знайдено.")
        return

    status_icon = "🟢" if driver_data['is_working'] else "🔴"
    is_banned = await db_queries.is_user_banned(driver_id)
    ban_icon = "🚫" if is_banned else ""

    text = (
        f"<b>Профіль водія {ban_icon}</b>\n\n"
        f"<b>ID:</b> <code>{driver_data['user_id']}</code>\n"
        f"<b>Ім'я:</b> {html.escape(driver_data['full_name'])}\n"
        f"<b>Username:</b> @{driver_data['username'] if driver_data['username'] else 'не вказано'}\n"
        f"<b>Телефон:</b> <code>{html.escape(driver_data['phone_num'])}</code>\n"
        f"<b>Номер авто:</b> <code>{html.escape(driver_data['avto_num'])}</code>\n"
        f"<b>Статус:</b> {status_icon} {'На зміні' if driver_data['is_working'] else 'Не на зміні'}\n"
        f"<b>Рейтинг:</b> {driver_data['rating']:.2f} ⭐ ({driver_data['rating_count']} оцінок)\n"
        f"<b>Поїздок виконано:</b> {driver_data['completed_orders']}\n"
        f"<b>Дата реєстрації:</b> {parser.parse(driver_data['created_at']).strftime('%d.%m.%Y %H:%M')}"
    )
    keyboard = get_driver_profile_keyboard(driver_id, is_banned)
    await safe_edit_or_send(target, text, keyboard)

async def _display_client_profile(target: types.Message | types.CallbackQuery, user_id: int):
    """Displays a client's profile to an admin."""
    client_data = await db_queries.get_client_details(user_id)
    if not client_data:
        await safe_edit_or_send(target, f"Клієнта з ID {user_id} не знайдено.")
        return

    is_banned = await db_queries.is_user_banned(user_id)
    is_admin = await db_queries.is_admin(user_id)
    ban_icon = "🚫" if is_banned else ""
    admin_icon = "👑" if is_admin else ""

    text = (
        f"<b>Профіль клієнта {ban_icon}{admin_icon}</b>\n\n"
        f"<b>ID:</b> <code>{client_data['user_id']}</code>\n"
        f"<b>Ім'я:</b> {html.escape(client_data['full_name'])}\n"
        f"<b>Username:</b> @{client_data['username'] if client_data['username'] else 'не вказано'}\n"
        f"<b>Телефон:</b> <code>{html.escape(client_data['phone_num'] or 'не вказано')}</code>\n"
        f"<b>Рейтинг:</b> {client_data['rating']:.2f} ⭐ ({client_data['rating_count']} оцінок)\n"
        f"<b>Поїздок виконано:</b> {client_data['completed_orders']}\n"
        f"<b>Дата реєстрації:</b> {parser.parse(client_data['created_at']).strftime('%d.%m.%Y %H:%M')}"
    )
    keyboard = get_client_profile_keyboard(user_id, is_banned, is_admin)
    await safe_edit_or_send(target, text, keyboard)
