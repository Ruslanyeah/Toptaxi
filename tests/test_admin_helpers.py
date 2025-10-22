import pytest
from unittest.mock import AsyncMock, ANY
import html

from aiogram import types, Bot
from aiogram.types import BotCommand, BotCommandScopeChat

# Импортируем функции для тестирования.
# _format_client - "приватная", но для теста мы можем её импортировать.
from handlers.admin.admin_helpers import _format_client, update_admin_commands


# --- Тесты для функции _format_client ---

def test_format_client_with_full_data():
    """
    Тестирует форматирование клиента с полными данными.
    """
    client_data = {
        'user_id': 12345,
        'full_name': 'John Doe',
        'phone_number': '+1234567890',
        'finish_applic': 10,
        'cancel_applic': 2
    }
    
    expected_output = (
        f"👤 <b>{html.escape(client_data['full_name'])}</b> (ID: <code>{client_data['user_id']}</code>)\n"
        f"  - Телефон: <code>{html.escape(client_data['phone_number'])}</code>\n"
        f"  - Поїздки: ✅ {client_data['finish_applic']} / ❌ {client_data['cancel_applic']}\n\n"
    )
    
    result = _format_client(client_data)
    assert result == expected_output

def test_format_client_with_missing_data():
    """
    Тестирует форматирование клиента, у которого отсутствуют некоторые данные (имя, телефон).
    """
    client_data = {
        'user_id': 54321,
        'full_name': None,
        'phone_number': None,
        'finish_applic': 0,
        'cancel_applic': 1
    }
    
    expected_output = (
        f"👤 <b>Ім`я не вказано</b> (ID: <code>{client_data['user_id']}</code>)\n"
        f"  - Телефон: <code>Не вказано</code>\n"
        f"  - Поїздки: ✅ {client_data['finish_applic']} / ❌ {client_data['cancel_applic']}\n\n"
    )
    
    result = _format_client(client_data)
    assert result == expected_output


# --- Тесты для функции update_admin_commands ---

@pytest.fixture
def mock_bot() -> AsyncMock:
    """
    Создает мок (имитацию) объекта Bot с асинхронным методом set_my_commands.
    """
    bot = AsyncMock(spec=Bot)
    bot.set_my_commands = AsyncMock()
    return bot

@pytest.mark.asyncio
async def test_update_admin_commands_grants_admin_rights(mock_bot):
    """
    Тестирует, что при is_admin=True устанавливаются команды администратора.
    """
    user_id = 123
    await update_admin_commands(mock_bot, user_id, is_admin=True)

    # Проверяем, что метод set_my_commands был вызван один раз
    mock_bot.set_my_commands.assert_awaited_once()
    
    # Проверяем, что в списке команд есть команда 'admin'
    call_args = mock_bot.set_my_commands.call_args
    commands_list = call_args.args[0]
    scope = call_args.args[1]
    
    assert any(cmd.command == 'admin' for cmd in commands_list)
    assert isinstance(scope, BotCommandScopeChat)
    assert scope.chat_id == user_id

@pytest.mark.asyncio
async def test_update_admin_commands_revokes_admin_rights(mock_bot):
    """
    Тестирует, что при is_admin=False устанавливаются обычные команды пользователя.
    """
    user_id = 456
    await update_admin_commands(mock_bot, user_id, is_admin=False)

    # Проверяем, что метод set_my_commands был вызван один раз
    mock_bot.set_my_commands.assert_awaited_once()
    
    # Проверяем, что в списке команд НЕТ команды 'admin'
    call_args = mock_bot.set_my_commands.call_args
    commands_list = call_args.args[0]
    scope = call_args.args[1]

    assert not any(cmd.command == 'admin' for cmd in commands_list)
    assert isinstance(scope, BotCommandScopeChat)
    assert scope.chat_id == user_id