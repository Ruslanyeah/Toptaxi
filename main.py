import asyncio
import logging
import signal
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from loguru import logger
from bot_manager import safe_bot_start
from aiogram.exceptions import TelegramConflictError
from config.config import TOKEN, ADMIN_IDS
from config.logging_config import setup_logging

# --- Підключення роутерів ---
from database.db import init_db
from database import queries as db_queries
from handlers.middlewares.logging_middleware import LoggingMiddleware
from handlers.middlewares.activity_middleware import ActivityMiddleware
from handlers.middlewares.ban_middleware import BanMiddleware
from handlers import setup_routers
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.user.scheduler import check_scheduled_orders, check_dispatch_timeouts, check_preorder_reminders, check_pending_dispatch_orders

# Глобальные переменные для корректного завершения
bot = None
scheduler = None

# Настраиваем логирование при старте приложения
setup_logging()

async def set_bot_commands(bot: Bot):
    """Встановлює меню команд для різних типів користувачів."""
    user_commands = [
        BotCommand(command="start", description="🚀 Розпочати роботу / Головне меню"),
        BotCommand(command="cabinet", description="🏠 Особистий кабінет"),
        BotCommand(command="driver", description="🚕 Кабінет водія"),
        BotCommand(command="stop", description="🚫 Скасувати поточну дію"),
    ]
    await bot.set_my_commands(user_commands, BotCommandScopeDefault())

    admin_commands = user_commands + [
        BotCommand(command="admin", description="👑 Адмін-панель"),
    ]

    # Отримуємо всіх адміністраторів (з конфігурації та з бази даних)
    all_admin_ids = set(ADMIN_IDS)
    db_admins = await db_queries.get_all_admins()
    if db_admins:
        for admin in db_admins:
            all_admin_ids.add(admin['user_id'])

    for admin_id in all_admin_ids:
        try:
            await bot.set_my_commands(admin_commands, BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logger.warning(f"Не вдалося встановити команди для адміністратора {admin_id}: {e}")

async def graceful_shutdown(dp: Dispatcher):
    """Корректное завершение работы бота."""
    global bot, scheduler # Убираем dp из этой строки
    
    logger.info("Початок корректного завершення роботи бота...")
    
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=True)
            logger.info("Планувальник зупинено")
        except Exception as e:
            logger.error(f"Помилка при зупинці планувальника: {e}")
    
    if dp:
        try:
            await dp.stop_polling()
            logger.info("Polling зупинено")
        except Exception as e:
            logger.error(f"Помилка при зупинці polling: {e}")
    if dp:
        try:
            await dp.fsm.storage.close()
            logger.info("FSM сховище закрито")
        except Exception as e:
            logger.error(f"Помилка при закритті FSM сховища: {e}")
    
    if bot:
        try:
            await bot.close()
            logger.info("Сесія бота закрита")
        except Exception as e:
            logger.error(f"Помилка при закритті сесії бота: {e}")
    
    logger.info("Корректне завершення роботи завершено.")

async def start_bot(dp: Dispatcher):
    global bot, scheduler
    
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    bot_info = await bot.get_me()

    # Спробуємо видалити вебхук перед запуском, щоб уникнути конфліктів
    # і зробити запуск більш "відчутним" для користувача
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Попередній вебхук видалено.")
    except Exception as e:
        logger.warning(f"Не вдалося видалити вебхук: {e}")

    logger.info("Ініціалізація бази даних...")
    await init_db()
    logger.info("Базу даних ініціалізовано.")

    # Додаємо обробники сигналів для граційного завершення
    # Це більш надійний спосіб для asyncio, ніж signal.signal
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(graceful_shutdown(dp)))
        except NotImplementedError:
            # На Windows може не підтримуватися для SIGTERM
            pass

    scheduler = AsyncIOScheduler(timezone="Europe/Kiev")
    scheduler.add_job(check_scheduled_orders, trigger='interval', seconds=60, kwargs={'bot': bot})
    scheduler.add_job(check_dispatch_timeouts, trigger='interval', seconds=5, kwargs={'bot': bot})
    scheduler.add_job(check_pending_dispatch_orders, trigger='interval', seconds=60, kwargs={'bot': bot})
    scheduler.add_job(check_preorder_reminders, trigger='interval', minutes=1, kwargs={'bot': bot})
    scheduler.start()
    
    await set_bot_commands(bot)

    dp.message.middleware(BanMiddleware())
    # Применяем middleware для логирования ко всем типам событий
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(ActivityMiddleware()) # Добавляем middleware для отслеживания активности
    dp.callback_query.middleware(BanMiddleware())
    
    try:
        logger.info("Запуск бота...")
        await dp.start_polling(bot)
    except TelegramConflictError:
        logger.critical(
            f"Виявлено конфлікт для бота @{bot_info.username} (ID: {bot_info.id}).\n"
            "Інший екземпляр бота вже запущений.\n"
            "Щоб це виправити, запустіть скрипт: python stop_bot.py або python quick_stop.py"
        )
    except Exception as e:
        await graceful_shutdown(dp)
        raise e

async def main():
    # Инициализируем Dispatcher здесь, а не глобально
    dp = Dispatcher()

    # Настраиваем роутеры
    main_commands_router, other_handlers_router, errors_router = setup_routers()
    # Сначала регистрируем роутер с глобальными командами
    dp.include_router(main_commands_router)
    # Затем - все остальные роутеры
    dp.include_router(other_handlers_router)
    # Роутер для обработки ошибок должен быть последним
    dp.include_router(errors_router)

    # Передаем dp в функцию запуска, чтобы избежать глобальных переменных
    await safe_bot_start(lambda: start_bot(dp))

if __name__ == '__main__':
    # Запуск через asyncio.run() обробляє KeyboardInterrupt та інші винятки
    asyncio.run(main())
