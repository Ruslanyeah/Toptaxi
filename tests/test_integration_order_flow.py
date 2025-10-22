# tests/test_integration_order_flow.py
import asyncio
import sys
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, ANY
from pytest_mock import MockerFixture

# Добавляем корень проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aiogram import Dispatcher, Bot
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import User, Chat, Message, CallbackQuery, Update, FSInputFile

from handlers import setup_routers
from states.fsm_states import UserState
from database import queries as db_queries
from handlers.user import order_dispatch

# --- Фикстуры для настройки тестового окружения ---

@pytest.fixture(scope="function")
def storage():
    """Фикстура для создания временного хранилища FSM в памяти."""
    return MemoryStorage()

@pytest.fixture
def bot() -> AsyncMock:
    """Фикстура для создания мок-объекта бота."""
    bot_mock = AsyncMock(spec=Bot)
    bot_mock.id = 123456789
    # Мокируем методы, которые могут быть вызваны в процессе
    bot_mock.send_message = AsyncMock()
    bot_mock.edit_message_text = AsyncMock()
    bot_mock.answer_callback_query = AsyncMock()
    bot_mock.get_chat = AsyncMock(return_value=User(id=123, first_name="Test", is_bot=False))
    bot_mock.copy_message = AsyncMock()
    bot_mock.send_location = AsyncMock()
    bot_mock.send_photo = AsyncMock() # Добавляем мок для send_photo
    return bot_mock

@pytest.fixture(scope="function")
def dispatcher(storage):
    """Фикстура для создания и настройки диспетчера с роутерами."""
    dp = Dispatcher(storage=storage)
    # Настраиваем все роутеры, как в main.py
    main_router, other_router, error_router = setup_routers()
    dp.include_router(main_router)
    dp.include_router(other_router)
    dp.include_router(error_router)
    return dp

@pytest.fixture
def user():
    """Фикстура, представляющая тестового пользователя."""
    return User(id=123, is_bot=False, first_name="Тестовый", last_name="Пользователь", username="testuser")

@pytest.fixture
def chat(user):
    """Фикстура, представляющая чат с тестовым пользователем."""
    return Chat(id=user.id, type="private", first_name=user.first_name, last_name=user.last_name, username=user.username)

# --- Вспомогательная функция для симуляции сообщений ---

async def send_message(dp: Dispatcher, bot: Bot, user: User, chat: Chat, text: str):
    """Симулирует отправку сообщения от пользователя и его обработку диспетчером."""
    message = Message(
        message_id=1,
        date=asyncio.get_event_loop().time(),
        chat=chat,
        from_user=user,
        text=text
    )
    await dp.feed_update(bot, Update(update_id=1, message=message))


# --- Тесты ---

@pytest.mark.asyncio
async def test_standard_taxi_order_flow(dispatcher: Dispatcher, bot: Bot, user: User, chat: Chat, mocker: MockerFixture):
    """
    Интеграционный тест полного сценария заказа такси:
    1. Нажатие "Замовити таксі"
    2. Выбор "Ввести адресу вручну"
    3. Ввод адреса подачи
    4. Ввод адреса назначения
    5. Ввод номера телефона
    6. Пропуск комментария
    7. Подтверждение и создание заказа
    """
    # Мокируем все обращения к базе данных и внешним сервисам, чтобы изолировать тест
    mocker.patch('database.queries.get_user_fav_addresses', return_value=[])
    mocker.patch('utils.geocoder.geocode', side_effect=[
        [AsyncMock(address="вулиця Соборна, 1, Глухів", latitude=51.677, longitude=33.911)], # Адрес подачи
        [AsyncMock(address="вулиця Київська, 43, Глухів", latitude=51.68, longitude=33.92)]  # Адрес назначения
    ])
    mocker.patch('database.queries.update_client_phone', return_value=None)
    mocker.patch('database.queries.create_order_in_db', return_value=999) # Возвращаем ID созданного заказа
    mocker.patch('handlers.user.order_dispatch.dispatch_order_to_drivers', return_value=None)
    
    # Определяем корректную асинхронную функцию для мока
    async def mock_send_with_photo(msg, path, text, kb):
        return await bot.send_photo(chat_id=msg.chat.id, photo=ANY, caption=text, reply_markup=kb, parse_mode='HTML')

    # Мокируем вспомогательную функцию, чтобы она не читала файл, а вызывала нужный метод бота
    mocker.patch('handlers.common.helpers.send_message_with_photo', side_effect=mock_send_with_photo)

    # --- Шаг 1: Пользователь нажимает "Замовити таксі" ---
    await send_message(dispatcher, bot, user, chat, "🚕 Замовити таксі")
    # Изменяем проверку на send_photo с параметром caption
    bot.send_photo.assert_called_with(
        chat_id=chat.id, # Используем именованный аргумент
        photo=ANY, # Мы не проверяем саму картинку, только факт ее наличия
        caption='📍 <b>Крок 1: Адреса подачі</b>\n\nБудь ласка, оберіть спосіб введення адреси:',
        reply_markup=ANY,
        parse_mode='HTML'
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state == UserState.locate.state

    # --- Шаг 2: Пользователь выбирает "Ввести адресу вручну" ---
    await send_message(dispatcher, bot, user, chat, "✏️ Ввести адресу вручну")
    # Этот обработчик отвечает простым сообщением, а не фото
    bot.send_message.assert_called_with(
        chat.id,
        "✍️ Вкажіть <b>АДРЕСУ</b> або <b>МІСЦЕ</b>, звідки вас потрібно забрати:",
        reply_markup=ANY
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state == UserState.begin_address.state

    # --- Шаг 3: Пользователь вводит адрес подачи ---
    await send_message(dispatcher, bot, user, chat, "Соборна 1")
    bot.send_message.assert_called_with(
        chat.id,
        '✅ Адресу подачі встановлено: <b>вулиця Соборна, 1, Глухів</b>'
    )
    # Проверяем второй вызов - переход к следующему шагу
    bot.send_message.assert_called_with(
        chat.id,
        '🏁 <b>Крок 2: Адреса призначення</b>\n\nТепер вкажіть, <b>КУДИ</b> вас потрібно відвезти',
        reply_markup=ANY
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state == UserState.finish_address.state

    # --- Шаг 4: Пользователь вводит адрес назначения ---
    await send_message(dispatcher, bot, user, chat, "Київська 43")
    bot.send_message.assert_called_with(
        chat.id,
        '✅ Адресу призначення встановлено: <b>вулиця Київська, 43, Глухів</b>'
    )
    bot.send_message.assert_called_with(
        chat.id,
        '📱 <b>Ваш контакт</b>\n\nНадішліть ваш номер телефону для зв\'язку з водієм.',
        reply_markup=ANY
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state == UserState.number.state

    # --- Шаг 5: Пользователь вводит номер телефона ---
    await send_message(dispatcher, bot, user, chat, "+380991234567")
    bot.send_message.assert_called_with(
        chat.id,
        "💬 <b>Коментар до замовлення</b> (необов'язково)\n\nМожете додати будь-яку важливу інформацію для водія.",
        reply_markup=ANY
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state == UserState.comment.state

    # --- Шаг 6: Пользователь пропускает комментарий ---
    await send_message(dispatcher, bot, user, chat, "Без коментаря")
    bot.send_message.assert_called_with(
        chat.id,
        ANY, # Текст подтверждения
        reply_markup=ANY
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state == UserState.confirm_order.state

    # --- Шаг 7: Пользователь подтверждает заказ ---
    await send_message(dispatcher, bot, user, chat, "Створити замовлення 🏁")
    db_queries.create_order_in_db.assert_awaited_once()
    order_dispatch.dispatch_order_to_drivers.assert_awaited_once()
    bot.send_message.assert_called_with(
        chat.id,
        ANY, # Финальный текст
        reply_markup=ANY
    )
    state = await dispatcher.fsm.get_context(bot, user.id, user.id).get_state()
    assert state is None # Состояние должно быть сброшено

if __name__ == "__main__":
    # Для запуска тестов используйте команду: pytest
    pass
