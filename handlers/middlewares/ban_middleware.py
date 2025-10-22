from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import aiosqlite
from config.config import DB_PATH

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get('event_from_user')
        if not user:
            return await handler(event, data)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT is_banned FROM clients WHERE user_id = ?", (user.id,))
            result = await cursor.fetchone()

        if result and result[0] == 1:
            print(f"Ignoring update from banned user {user.id}")
            return

        return await handler(event, data)
