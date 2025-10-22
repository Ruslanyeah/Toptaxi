from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from loguru import logger
import html
import traceback
from config.config import ADMIN_IDS

router = Router()

# Этот обработчик будет ловить ВСЕ исключения, которые не были пойманы в других местах
@router.errors()
async def errors_handler(exception: types.ErrorEvent):
    """
    Catches all exceptions from routers and handlers.
    Logs the error and notifies admins.
    """
    # Логируем полное исключение
    logger.exception(f"Cause exception: {exception.exception}")

    # Формируем сообщение для администраторов
    tb_str = traceback.format_exception(type(exception.exception), exception.exception, exception.exception.__traceback__)
    error_text = "".join(tb_str)
    
    # Обрезаем слишком длинные сообщения
    if len(error_text) > 4000:
        error_text = error_text[-4000:]
    error_message = f"<b>❗️ Unhandled Error</b>\n\n<pre>{html.escape(error_text)}</pre>"

    # Отправляем сообщение всем администраторам
    for admin_id in ADMIN_IDS:
        try:
            await exception.update.bot.send_message(admin_id, error_message)
        except Exception as e:
            logger.error(f"Failed to send error notification to admin {admin_id}: {e}")

    # Отвечаем пользователю, если это возможно
    if exception.update.callback_query:
        await exception.update.callback_query.message.answer("😔 Вибачте, сталася непередбачена помилка. Ми вже працюємо над її виправленням.")
    elif exception.update.message:
        await exception.update.message.answer("😔 Вибачте, сталася непередбачена помилка. Ми вже працюємо над її виправленням.")
    
    return True # Сообщаем aiogram, что ошибка обработана

@router.callback_query()
async def unhandled_callback_handler(callback: types.CallbackQuery):
    """
    Ловит все необработанные callback-запросы (например, от старых сообщений).
    Это предотвращает "зависание" кнопок в состоянии загрузки.
    """
    # Логируем, какой именно callback не был обработан
    logger.warning(f"Необработанный callback: data='{callback.data}' от user_id={callback.from_user.id}")
    await callback.answer("Ця кнопка вже неактуальна, або сталася помилка.", show_alert=True)

@router.message()
async def unhandled_message_handler(message: types.Message, state: FSMContext) -> None:
    """
    Catches all unhandled text messages and always replies.
    """    
    logger.warning(f"Unhandled message: '{message.text}' from user_id={message.from_user.id}. Current state: {await state.get_state()}")
    await message.answer('Такої команди немає :(\n\nСпробуйте ще раз, або поверніться в /start.')
