from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger

class LoggingMiddleware(BaseMiddleware):
    """
    Это middleware "привязывает" ID пользователя и чата ко всем логам,
    сгенерированным во время обработки одного события.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = data.get('event_from_user').id if data.get('event_from_user') else "System"
        chat_id = data.get('event_chat').id if data.get('event_chat') else "N/A"
        # Используем contextvars для безопасной передачи контекста в асинхронной среде
        with logger.contextualize(user_id=user_id, chat_id=chat_id):
            return await handler(event, data)