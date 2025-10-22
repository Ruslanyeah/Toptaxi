from aiogram import types
from typing import Callable, Any
from .helpers import safe_edit_or_send
import math

async def show_paginated_list(
    target: types.Message | types.CallbackQuery,
    page: int,
    count_func: Callable,
    page_func: Callable,
    keyboard_func: Callable,
    title: str,
    items_per_page: int,
    no_items_text: str,
    no_items_keyboard: types.InlineKeyboardMarkup,
    item_list_title: str | None = None,
    item_formatter: Callable | None = None,
    prefix_text: str = "",
    items_list_kwarg_name: str = 'items',
    count_func_kwargs: dict | None = None,
    page_func_kwargs: dict | None = None,
    keyboard_func_kwargs: dict | None = None
) -> None:
    """
    A generic helper to display a paginated list of items.

    Args:
        target: The message or callback query to respond to.
        page: The current page number (0-indexed).
        count_func: An awaitable function to get the total count of items.
        page_func: An awaitable function to get a page of items.
        keyboard_func: A function to generate the pagination keyboard.
        title: The title for the message.
        items_per_page: The number of items to display per page.
        no_items_text: The text to display if there are no items.
        no_items_keyboard: The keyboard to display if there are no items.
        item_list_title: An optional title to display above the list of items.
        item_formatter: An optional function to format each item in the list.
        prefix_text: Optional text to prepend before the item list.
        items_list_kwarg_name: The keyword argument name for the list of items in keyboard_func.
        count_func_kwargs: Keyword arguments for the count function.
        page_func_kwargs: Keyword arguments for the page function.
        keyboard_func_kwargs: Keyword arguments for the keyboard function.
    """
    count_kwargs = count_func_kwargs or {}
    page_kwargs = page_func_kwargs or {}
    kb_kwargs = keyboard_func_kwargs or {}

    total_items = await count_func(**count_kwargs)
    
    if total_items == 0:
        await safe_edit_or_send(target, no_items_text, reply_markup=no_items_keyboard)
        if isinstance(target, types.CallbackQuery):
            await target.answer()
        return

    total_pages = math.ceil(total_items / items_per_page)
    offset = page * items_per_page
    
    items = await page_func(limit=items_per_page, offset=offset, **page_kwargs)
    
    response_text = f"<b>{title}</b>\n\n"
    if prefix_text:
        response_text += prefix_text + "\n"

    if item_formatter:
        response_text += "".join(item_formatter(item) for item in items)
    elif item_list_title:
        response_text += item_list_title

    # Pass the fetched items to the keyboard function
    kb_kwargs[items_list_kwarg_name] = items
    keyboard = keyboard_func(page=page, total_pages=total_pages, **kb_kwargs)
    
    await safe_edit_or_send(target, response_text, reply_markup=keyboard)
    if isinstance(target, types.CallbackQuery):
        await target.answer()
