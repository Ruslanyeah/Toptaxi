from aiogram import types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

class Navigate(CallbackData, prefix="nav"):
    to: str

def _add_pagination_buttons(builder: InlineKeyboardBuilder, page: int, total_pages: int, paginator_callback: type[CallbackData], **kwargs) -> int:
    """
    Adds pagination buttons to an InlineKeyboardBuilder.

    Args:
        builder: The InlineKeyboardBuilder instance.
        page: The current page number.
        total_pages: The total number of pages.
        paginator_callback: The CallbackData class to use for pagination.
        **kwargs: Additional arguments to pass to the paginator callback.

    Returns:
        The number of buttons added to the pagination row (0, 1, or 2).
    """
    pagination_row_size = 0
    if page > 0:
        builder.button(text="⬅️ Назад", callback_data=paginator_callback(page=page - 1, **kwargs))
        pagination_row_size += 1
    if page < total_pages - 1:
        builder.button(text="Вперед ➡️", callback_data=paginator_callback(page=page + 1, **kwargs))
        pagination_row_size += 1
    return pagination_row_size