import asyncio
import logging
from typing import Callable, Coroutine, Any
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError
logger = logging.getLogger(__name__)

async def broadcast_messages(
    bot: Bot,
    user_ids: list[int],
    send_function: Callable[[int], Coroutine[Any, Any, Any]],
    status_message: Message | None = None
) -> tuple[int, int]:
    """
    Sends messages to a list of users in batches to avoid hitting Telegram's rate limits.

    Args:
        bot: The Bot instance.
        user_ids: A list of user IDs to send messages to.
        send_function: An awaitable function that takes a user_id and sends the message.
        status_message: An optional message to edit with the progress of the broadcast.

    Returns:
        A tuple of (success_count, fail_count).
    """
    total_users = len(user_ids)
    if total_users == 0:
        return 0, 0

    success_count = 0
    fail_count = 0
    batch_size = 25  # Send 25 messages per batch
    delay_between_batches = 1.1  # Wait just over 1 second between batches

    for i in range(0, total_users, batch_size):
        batch = user_ids[i:i + batch_size]

        # Создаем задачи для параллельной отправки сообщений в пакете
        tasks = [send_function(user_id) for user_id in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обрабатываем результаты
        for j, result in enumerate(results):
            user_id = batch[j]
            if isinstance(result, Exception):
                fail_count += 1
                # Логируем конкретную ошибку, если это ошибка API
                if isinstance(result, TelegramAPIError):
                     if "bot was blocked" in str(result) or result.message.startswith("Forbidden:"):
                         logger.info(f"Broadcast failed for user {user_id}: Bot was blocked.")
                     else:
                         logger.warning(f"Broadcast failed for user {user_id} with TelegramAPIError: {result}")
                else:
                    logger.error(f"Broadcast failed for user {user_id} with an unexpected error: {result}")
            else:
                success_count += 1

        if status_message:
            progress_text = (
                f"⏳ <b>Триває розсилка...</b>\n\n"
                f"Надіслано: {success_count}/{total_users}\n"
                f"Помилок: {fail_count}"
            )
            await status_message.edit_text(progress_text)

        if i + batch_size < total_users:
            await asyncio.sleep(delay_between_batches)

    return success_count, fail_count