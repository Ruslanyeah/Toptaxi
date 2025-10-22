import asyncio
import sys
import os
import pytest
from unittest.mock import AsyncMock, ANY
from pytest_mock import MockerFixture

# Добавляем корень проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aiogram import Dispatcher, Bot
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import User, Chat, Message, Update

from handlers import setup_routers

# --- Фикстуры (можно использовать общие, но для ясности определим здесь) ---

@pytest.fixture(scope="function")
def storage():
    """Фикстура для создания временного хранилища FSM в памяти."""
    return MemoryStorage()

@pytest.fixture
def bot() -> AsyncMock:
    """Фикстура для создания мок-объекта бота."""
    bot_mock = AsyncMock(spec=Bot)
    bot_mock.send_message = AsyncMock()
    bot_mock.send_photo = AsyncMock()
    return bot_mock

@pytest.fixture(scope="function")
def dispatcher(storage):
    """Фикстура для создания и настройки диспетчера с роутерами."""
    dp = Dispatcher(storage=storage)
    main_router, other_router, error_router = setup_routers()
    dp.include_router(main_router)
    dp.include_router(other_router)
    dp.include_router(error_router)
    return dp

@pytest.fixture
def user():
    """Фикстура, представляющая обычного пользователя (не водителя)."""
    return User(id=123, is_bot=False, first_name="Тестовый", username="testuser")

@pytest.fixture
def chat(user):
    """Фикстура, представляющая чат с пользователем."""
    return Chat(id=user.id, type="private", first_name=user.first_name, username=user.username)

async def send_message(dp: Dispatcher, bot: Bot, user: User, chat: Chat, text: str):
    """Вспомогательная функция для симуляции сообщения от пользователя."""
    message = Message(message_id=1, date=asyncio.get_event_loop().time(), chat=chat, from_user=user, text=text)
    await dp.feed_update(bot, Update(update_id=1, message=message))

# --- Тест на конфликт ---

@pytest.mark.asyncio
async def test_non_driver_access_driver_cabinet(dispatcher: Dispatcher, bot: Bot, user: User, chat: Chat, mocker: MockerFixture):
    """
    Тест проверяет, что обычный пользователь НЕ МОЖЕТ получить доступ к кабинету водителя
    и его сообщение НЕ "проглатывается" системой, а обрабатывается как неизвестная команда.
    """
    # Мокируем запрос в БД, чтобы пользователь гарантированно не был водителем
    mocker.patch('database.queries.is_driver', return_value=False)

    # Пользователь нажимает на кнопку, которая ведет в кабинет водителя
    await send_message(dispatcher, bot, user, chat, "🚕 Для водіїв")

    # Ожидаемое поведение:
    # 1. Обработчик из `driver_cabinet.py` НЕ должен быть вызван, так как фильтр IsDriver вернет False.
    # 2. Сообщение должно дойти до самого последнего обработчика `unhandled_message_handler` в `error_handler.py`.
    # 3. Этот обработчик должен ответить "Такої команди немає :("

    # Проверяем, что НЕ БЫЛО попытки отправить фото из кабинета водителя
    bot.send_photo.assert_not_called()

    # Проверяем, что был вызван обработчик неизвестных команд
    bot.send_message.assert_called_once_with(
        chat.id,
        'Такої команди немає :(\n\nСпробуйте ще раз, або поверніться в /start.'
    )
