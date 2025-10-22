from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dateutil import parser
from utils.callback_factories import *
from .common import Navigate, _add_pagination_buttons
import html
from datetime import datetime
from config.config import TIMEZONE

def get_driver_rate_client_keyboard(order_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(
            text=f"{'⭐' * i}",
            callback_data=DriverRateClientCallback(order_id=order_id, score=i)
        )
    builder.button(text="Пропустити", callback_data=DriverRateClientCallback(order_id=order_id, score=0))
    builder.adjust(5, 1)
    return builder.as_markup()

def get_driver_reviews_keyboard(page: int, total_pages: int) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації відгуків водія."""
    builder = InlineKeyboardBuilder()
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, DriverReviewsPaginator)
    builder.button(text="↩️ До кабінету водія", callback_data=Navigate(to="back_to_driver_cabinet"))
    
    if pagination_row_size > 0: builder.adjust(pagination_row_size, 1)
    else: builder.adjust(1)
    return builder.as_markup()

def get_driver_rejections_keyboard(page: int, total_pages: int, rejections: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для історії відмов водія."""
    builder = InlineKeyboardBuilder()
    for rejection in rejections:
        date_str = parser.parse(rejection['rejected_at']).strftime('%d.%m.%Y')
        button_text = f"↪️ №{rejection['order_id']} від {date_str} (Клієнт: {html.escape(rejection['client_name'])})"
        builder.button(
            text=button_text,
            callback_data=DriverRejectionDetails(order_id=rejection['order_id'])
        )

    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, DriverRejectionPaginator)
    builder.button(text="↩️ До кабінету водія", callback_data=Navigate(to="back_to_driver_cabinet"))

    layout = [1] * len(rejections)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_preorder_list_keyboard(page: int, total_pages: int, orders: list) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for the list of available pre-orders."""
    builder = InlineKeyboardBuilder()
    for order in orders:
        time_str = parser.parse(order['scheduled_at']).strftime('%d.%m %H:%M')
        route_str = f"{html.escape(order['begin_address'])} -> {html.escape(order['finish_address'])}"
        builder.button(
            text=f"🗓️ №{order['id']} на {time_str} - {route_str}",
            callback_data=PreOrderDetails(order_id=order['id'])
        )
    
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, PreOrderListPaginator)
    builder.button(text="↩️ До кабінету водія", callback_data=Navigate(to="back_to_driver_cabinet"))

    layout = [1] * len(orders)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_preorder_details_keyboard(order_id: int) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for viewing pre-order details."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Взяти це замовлення",
        callback_data=PreOrderAction(action='accept', order_id=order_id)
    )
    builder.button(text="⬅️ До списку запланованих", callback_data=Navigate(to="scheduled_orders_list"))
    builder.adjust(1)
    return builder.as_markup()

def get_my_preorders_keyboard(page: int, total_pages: int, orders: list) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for the list of driver's own active pre-orders."""
    builder = InlineKeyboardBuilder()
    for order in orders:
        time_str = parser.parse(order['scheduled_at']).strftime('%d.%m %H:%M')
        builder.button(
            text=f"🗓️ №{order['id']} на {time_str} - {html.escape(order['begin_address'])}",
            callback_data=MyPreorderAction(action='details', order_id=order['id'])
        )
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, MyPreordersPaginator)
    builder.button(text="↩️ До кабінету водія", callback_data=Navigate(to="back_to_driver_cabinet"))

    layout = [1] * len(orders)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_my_preorder_details_keyboard(order_id: int) -> types.InlineKeyboardMarkup:
    """Generates a keyboard for viewing a driver's own pre-order details."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Скасувати це замовлення",
        callback_data=MyPreorderAction(action='cancel', order_id=order_id)
    )
    builder.button(text="⬅️ До моїх запланованих", callback_data=Navigate(to="my_scheduled_orders_list"))
    builder.adjust(1)
    return builder.as_markup()

def get_driver_history_keyboard(page: int, total_pages: int, orders_on_page: list) -> types.InlineKeyboardMarkup:
    """Генерує клавіатуру для історії поїздок водія."""
    builder = InlineKeyboardBuilder()
    for order in orders_on_page:
        date_str = parser.parse(order['created_at']).strftime('%d.%m.%Y')
        builder.button(
            text=f"Поїздка №{order['id']} від {date_str}",
            callback_data=TripDetailsCallbackData(order_id=order['id'])
        )
    
    pagination_row_size = _add_pagination_buttons(builder, page, total_pages, DriverHistoryPaginator)
    builder.button(text="↩️ До кабінету водія", callback_data=Navigate(to="back_to_driver_cabinet"))

    layout = [1] * len(orders_on_page)
    if pagination_row_size > 0: layout.append(pagination_row_size)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()