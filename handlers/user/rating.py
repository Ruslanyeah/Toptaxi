from aiogram import types, F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from loguru import logger
from database import queries as db_queries
from utils.callback_factories import RatingCallbackData, DriverRateClientCallback, SaveAddress
from keyboards.common import Navigate
from keyboards.user_keyboards import get_rating_keyboard
from keyboards.driver_keyboards import get_driver_rate_client_keyboard
from states.fsm_states import RatingState, UserState
from ..common.helpers import safe_edit_or_send

router = Router()

async def _finalize_rating(state: FSMContext, rater_id: int, comment: str | None = None) -> bool:
    """
    A unified helper to validate, save, and finalize a rating process.
    It prevents double-rating and cleans up the FSM state.
    Returns True if rating was saved, False otherwise.
    """
    data = await state.get_data()
    order_id = data.get('order_id')
    score = data.get('score')
    rated_user_type = data.get('rated_user_type')

    if not all([order_id, score, rated_user_type]):
        logger.error(f"Rating finalization failed: incomplete FSM data for rater {rater_id}.")
        await state.clear()
        return False

    order_details = await db_queries.get_order_details(order_id)
    if not order_details:
        logger.warning(f"Attempted to save rating for non-existent order {order_id}")
        await state.clear()
        return False
    
    if order_details['is_rated'] and rated_user_type == 'driver': # Only clients can rate once
        logger.warning(f"Attempted to double-rate order {order_id} by client {rater_id}.")
        await state.clear()
        return False

    if rated_user_type == 'client':
        rated_user_id = order_details['client_id']
        if not rated_user_id: return False
        await db_queries.add_client_review(order_id, rated_user_id, rater_id, score, comment)
        await db_queries.add_rating_to_client(rated_user_id, score)
    elif rated_user_type == 'driver':
        rated_user_id = order_details['driver_id']
        if not rated_user_id: return False
        await db_queries.rate_order(order_id, score, comment)
        await db_queries.add_rating_to_driver(rated_user_id, score)
    else:
        await state.clear()
        return False
    
    await state.clear()
    return True

# --- Handlers for driver rating client ---

async def request_rating_from_driver_for_client(message: types.Message, order_id: int):
    """Initiates the process for a driver to rate a client."""
    # Instead of sending a new message, we edit the existing one.
    # This keeps the context in one place for the driver.
    await safe_edit_or_send(
        message,
        f"Будь ласка, оцініть пасажира за цю поїздку:",
        reply_markup=get_driver_rate_client_keyboard(order_id)
    )

@router.callback_query(DriverRateClientCallback.filter(), StateFilter(None))
async def process_client_rating_score(callback: types.CallbackQuery, callback_data: DriverRateClientCallback, state: FSMContext) -> None:
    """
    Handles the driver selecting a rating score for the client.
    """
    order_id = callback_data.order_id
    score = callback_data.score

    if score == 0: # Skip button
        try:
            await callback.message.edit_text("Дякуємо за роботу! Ви знову готові приймати замовлення.")
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    await state.set_state(RatingState.get_comment)
    await state.update_data(order_id=order_id, score=score, rated_user_type='client')
    
    skip_comment_kb = InlineKeyboardBuilder().button(
        text="➡️ Пропустити коментар", callback_data=Navigate(to="skip_client_comment")
    ).as_markup()

    try:
        await callback.message.edit_text(
            f"Ви поставили оцінку: {'⭐' * score}\n\n"
            "Тепер, будь ласка, напишіть короткий коментар про пасажира (або натисніть 'Пропустити').",
            reply_markup=skip_comment_kb
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.callback_query(Navigate.filter(F.to == "skip_client_comment"), RatingState.get_comment)
async def skip_client_rating_comment(callback: types.CallbackQuery, state: FSMContext) -> None:
    """
    Handles the driver skipping the comment when rating a client.
    """
    await _finalize_rating(state, callback.from_user.id, comment=None)
    try:
        await callback.message.edit_text("✅ Дякуємо за ваш відгук! Ви знову готові приймати замовлення.")
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.message(RatingState.get_comment)
async def process_client_rating_comment(message: types.Message, state: FSMContext) -> None:
    """
    Processes the driver's text comment for a client rating.
    """
    if await _finalize_rating(state, message.from_user.id, comment=message.text):
        await message.answer("✅ Дякуємо за ваш відгук! Ви знову готові приймати замовлення.")

# --- Handlers for client rating driver ---

async def start_driver_rating_process(bot: Bot, client_id: int, order_id: int):
    """Initiates the process for a client to rate a driver."""
    rating_kb = get_rating_keyboard(order_id, with_save_address=True)
    await bot.send_message(
        client_id,
        f"🙏 Поїздка за замовленням №{order_id} завершена. Дякуємо, що обрали нас!\n\n"
        "Будь ласка, оцініть поїздку:", reply_markup=rating_kb)

@router.callback_query(RatingCallbackData.filter())
async def process_rating_score(callback: types.CallbackQuery, callback_data: RatingCallbackData, state: FSMContext):
    """
    Handles the client selecting a rating score for the driver.
    """
    order_id = callback_data.order_id
    score = callback_data.score

    order = await db_queries.get_order_for_rating(order_id)

    if not order or order['is_rated']:
        await callback.answer("Ви вже оцінили цю поїздку або сталася помилка.", show_alert=True)
        try:
            await callback.message.edit_text("Дякуємо за ваш відгук!")
        except TelegramBadRequest:
            pass
        return

    await state.set_state(RatingState.get_comment)
    await state.update_data(order_id=order_id, score=score, rated_user_type='driver')

    skip_comment_kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="➡️ Пропустити коментар", callback_data=Navigate(to="skip_driver_comment").pack())
    ]])

    try:
        await callback.message.edit_text(
            f"Ви поставили оцінку: {'⭐' * score}\n\n"
            "За бажанням, можете залишити короткий коментар для водія (або пропустити).",
            reply_markup=skip_comment_kb
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.callback_query(Navigate.filter(F.to == "skip_driver_comment"), RatingState.get_comment)
async def skip_driver_rating_comment(callback: types.CallbackQuery, state: FSMContext) -> None:
    """
    Handles the client skipping the comment when rating a driver.
    """
    await _finalize_rating(state, callback.from_user.id, comment=None)
    try:
        await callback.message.edit_text("👍 Дякуємо за ваш відгук!")
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.message(RatingState.get_comment)
async def process_driver_rating_comment(message: types.Message, state: FSMContext) -> None:
    """
    Processes the client's text comment for a driver rating.
    """
    if await _finalize_rating(state, message.from_user.id, comment=message.text):
        await message.answer("👍 Дякуємо за ваш відгук!")