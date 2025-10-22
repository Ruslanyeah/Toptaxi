import pytest
import html
from aiogram import types

# Since we are testing a "private" helper function, we import it directly.
# In a larger project, you might consider making it public if it's used elsewhere.
from handlers.user.order_dispatch import _format_order_for_driver


@pytest.fixture
def mock_client_user() -> types.User:
    """Provides a mock aiogram User object for tests."""
    return types.User(
        id=12345,
        is_bot=False,
        first_name="John",
        last_name="Doe",
        username="johndoe",
        full_name="John Doe"
    )


@pytest.fixture
def mock_order_data_taxi() -> dict:
    """Provides mock data for a standard taxi order."""
    return {
        'begin_address': '123 Main St',
        'finish_address': '456 Oak Ave',
        'comment': 'Please ring the bell.',
        'number': '+1234567890',
        'order_type': 'taxi'
    }


@pytest.fixture
def mock_order_data_pickup() -> dict:
    """Provides mock data for a pickup & delivery order."""
    return {
        'begin_address': 'Store A',
        'finish_address': 'Client B',
        'order_details': 'A small box',
        'comment': 'Handle with care',
        'number': '+1987654321',
        'order_type': 'pickup_delivery'
    }


@pytest.fixture
def mock_order_data_buy() -> dict:
    """Provides mock data for a buy & deliver order."""
    return {
        'finish_address': 'Client C',
        'order_details': 'Milk and bread',
        'comment': None,  # No comment
        'number': '+1122334455',
        'order_type': 'buy_delivery'
    }


def test_format_taxi_order_with_comment_and_rating(mock_client_user, mock_order_data_taxi):
    """
    Tests formatting for a standard taxi order with all details present.
    """
    order_id = 101
    client_rating_text = "<b>4.8 ⭐</b> (10 оцінок)"
    reviews_text = "\n\n<b>Останні відгуки:</b>\n- ⭐⭐⭐⭐⭐ Good passenger\n"

    result = _format_order_for_driver(
        order_id, mock_order_data_taxi, mock_client_user, client_rating_text, reviews_text
    )

    assert f"🚕 <b>Нове замовлення №{order_id}</b>" in result
    assert f"<b>➡️ Звідки:</b> {mock_order_data_taxi['begin_address']}" in result
    assert f"<b>🏁 Куди:</b> {mock_order_data_taxi['finish_address']}" in result
    assert f"<b>💬 Коментар:</b> {mock_order_data_taxi['comment']}" in result
    assert f"<b>👤 Клієнт:</b> <a href='https://t.me/johndoe'>John Doe</a>" in result
    assert f"<b>📞 Телефон:</b> <code>{mock_order_data_taxi['number']}</code>" in result
    assert client_rating_text in result
    assert "Good passenger" in result


def test_format_taxi_order_no_comment_new_client(mock_client_user, mock_order_data_taxi):
    """
    Tests formatting for a taxi order from a new client with no comment.
    """
    order_id = 102
    mock_order_data_taxi['comment'] = None
    client_rating_text = "новий клієнт"
    reviews_text = ""  # No reviews

    result = _format_order_for_driver(
        order_id, mock_order_data_taxi, mock_client_user, client_rating_text, reviews_text
    )

    assert f"🚕 <b>Нове замовлення №{order_id}</b>" in result
    assert "<b>💬 Коментар:</b>" not in result  # Comment block should be absent
    assert "<b>⭐ Рейтинг:</b> новий клієнт" in result
    assert "<b>Останні відгуки:</b>" not in result  # Reviews block should be absent


def test_format_pickup_delivery_order(mock_client_user, mock_order_data_pickup):
    """
    Tests formatting for a "pickup and deliver" order.
    """
    order_id = 201
    client_rating_text = "новий клієнт"
    reviews_text = ""

    result = _format_order_for_driver(
        order_id, mock_order_data_pickup, mock_client_user, client_rating_text, reviews_text
    )

    assert f"📦 <b>Нова доставка (забрати-привезти) №{order_id}</b>" in result
    assert f"<b>➡️ Звідки:</b> {mock_order_data_pickup['begin_address']}" in result
    assert f"<b>🏁 Куди:</b> {mock_order_data_pickup['finish_address']}" in result
    assert f"<b>📋 Деталі:</b> {mock_order_data_pickup['order_details']}" in result
    assert f"<b>💬 Коментар:</b> {mock_order_data_pickup['comment']}" in result


def test_format_buy_delivery_order(mock_client_user, mock_order_data_buy):
    """
    Tests formatting for a "buy and deliver" order.
    """
    order_id = 301
    client_rating_text = "<b>5.0 ⭐</b> (1 оцінка)"
    reviews_text = ""

    result = _format_order_for_driver(
        order_id, mock_order_data_buy, mock_client_user, client_rating_text, reviews_text
    )

    assert f"🛒 <b>Нова доставка (покупка) №{order_id}</b>" in result
    assert f"<b>📋 Що купити:</b> {mock_order_data_buy['order_details']}" in result
    assert f"<b>🏁 Адреса доставки:</b> {mock_order_data_buy['finish_address']}" in result
    assert "<b>💬 Коментар:</b>" not in result  # No comment was provided
    assert "<i>❗️ Узгодьте з клієнтом деталі покупки та оплати.</i>" in result


def test_html_escaping_in_comment(mock_client_user, mock_order_data_taxi):
    """
    Ensures that HTML tags in user comments are properly escaped to prevent formatting issues.
    """
    order_id = 401
    mock_order_data_taxi['comment'] = "<b>Please</b> use the <script>alert('XSS')</script> side door."
    expected_escaped_comment = html.escape(mock_order_data_taxi['comment'])

    result = _format_order_for_driver(
        order_id, mock_order_data_taxi, mock_client_user, "новий клієнт", ""
    )

    assert expected_escaped_comment in result
    assert "<b>Please</b>" not in result  # The tag should be escaped, not rendered