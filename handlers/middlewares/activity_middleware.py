from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import asyncio

from database import queries as db_queries

class ActivityMiddleware(BaseMiddleware):
    """
    Это middleware обновляет время последней активности пользователя
    при каждом входящем событии (сообщение, нажатие кнопки).
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get('event_from_user')
        if user:
            # Запускаем обновление в фоне, чтобы не замедлять обработку
            asyncio.create_task(db_queries.update_user_activity(user.id))
        
        return await handler(event, data)