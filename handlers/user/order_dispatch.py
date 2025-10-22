from aiogram import types, Bot
import asyncio
import json
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
import html
from database import queries as db_queries
from keyboards.reply_keyboards import main_menu_keyboard
from config.config import DRIVER_ACCEPT_TIMEOUT
from utils.callback_factories import OrderCallbackData

async def _format_and_build_for_driver(order_id: int, order_data: dict, client_user: types.User) -> tuple[str, types.InlineKeyboardMarkup]:
    """Helper to format the message and build the keyboard for the driver."""
    # Fetch client info for the driver message
    client_rating_data = await db_queries.get_client_rating(client_user.id)
    client_reviews = await db_queries.get_client_reviews_for_driver(client_user.id)

    client_rating_text = "новий клієнт"
    if client_rating_data and client_rating_data['rating_count'] > 0:
        rating = client_rating_data['rating']
        count = client_rating_data['rating_count']
        client_rating_text = f"<b>{rating:.1f} ⭐</b> ({count} оцінок)"

    reviews_text = ""
    if client_reviews:
        reviews_text += "\n\n<b>Останні відгуки:</b>\n"
        for review in client_reviews[:3]:
            if review and review['comment']:
                comment_text = review['comment']
                if len(comment_text) > 70:
                    comment_text = comment_text[:70] + '…'
                reviews_text += f"- {'⭐' * review['score']} {html.escape(comment_text)}\n"
            else:
                reviews_text += f"- {'⭐' * review['score']}\n"

    text_for_driver = _format_order_for_driver(order_id, order_data, client_user, client_rating_text, reviews_text)

    keyboard_builder = InlineKeyboardBuilder()
    keyboard_builder.button(text='✅ Прийняти замовлення', callback_data=OrderCallbackData(action='accept', order_id=order_id))
    keyboard_builder.button(text='❌ Відмовитись', callback_data=OrderCallbackData(action='reject_by_driver', order_id=order_id))
    keyboard_builder.adjust(2)

    return text_for_driver, keyboard_builder.as_markup()

async def _process_next_driver_in_dispatch(bot: Bot, order_id: int) -> None:
    """
    Processes the next driver in the dispatch queue stored in the database.
    This function is now self-sufficient and fetches all required data.
    """
    dispatch_payload_json = await db_queries.get_dispatch_payload(order_id)
    if not dispatch_payload_json:
        logger.error(f"Cannot process next driver for order {order_id}: dispatch payload not found.")
        return

    payload = json.loads(dispatch_payload_json)
    order_data = payload['order_data']
    
    try:
        # Try to reconstruct the User object from the stored payload
        client_user = types.User(**payload['client_user'])
    except Exception:
        # If it fails (due to old data format), fetch the user directly from Telegram
        client_id = payload['client_user'].get('id')
        if not client_id:
            logger.error(f"Cannot process order {order_id}: client_id is missing from old payload.")
            return
        client_user = await bot.get_chat(client_id)

    driver_ids, current_index = await db_queries.get_dispatch_info(order_id)

    if not driver_ids or current_index >= len(driver_ids):
        logger.info(f"No more drivers in queue for order {order_id}. Cancelling.")
        try:
            await bot.send_message(client_user.id, 'На жаль, ніхто з водіїв не прийняв ваше замовлення. Спробуйте створити нове замовлення пізніше.', reply_markup=main_menu_keyboard)
        except Exception as e:
            logger.warning(f"Failed to send cancellation notice to client {client_user.id} for order {order_id}: {e}")
        await db_queries.update_order_status(order_id, 'cancelled_no_drivers')
        return

    current_driver_id = driver_ids[current_index]

    try:
        text_for_driver, keyboard_for_driver = await _format_and_build_for_driver(order_id, order_data, client_user)

        # First, send the text message with order details and buttons
        await bot.send_message(current_driver_id, text_for_driver, reply_markup=keyboard_for_driver)

        # Then, if coordinates are available, send the location separately
        lat, lon = order_data.get('latitude'), order_data.get('longitude')
        if lat and lon:
            await bot.send_location(
                chat_id=current_driver_id,
                latitude=lat,
                longitude=lon
            )
        
        logger.info(f"Замовлення {order_id} запропоновано водію {current_driver_id}.")
        await db_queries.mark_dispatch_offer_sent(order_id)
    except Exception as e:
        logger.warning(f"Failed to send order to driver {current_driver_id}, skipping. Error: {e}")
        await db_queries.increment_dispatch_index(order_id)
        asyncio.create_task(_process_next_driver_in_dispatch(bot, order_id))

def _format_order_for_driver(order_id: int, order_data: dict, client_user: types.User, client_rating_text: str, reviews_text: str) -> str:
    """
    Formats the order details into a text message for the driver based on the order type.
    """
    client_link = f"https://t.me/{client_user.username}" if client_user.username else f"tg://user?id={client_user.id}"    
    comment = order_data.get('comment')
    order_type = order_data.get('order_type', 'taxi')
    timeout_text = f"<i>У вас є {DRIVER_ACCEPT_TIMEOUT} секунд, щоб прийняти замовлення.</i>"
    
    # --- Client Info Block ---
    client_info_block = (
        f"<b>👤 Клієнт:</b> <a href='{client_link}'>{html.escape(client_user.full_name)}</a>\n"
        f"<b>📞 Телефон:</b> <code>{html.escape(str(order_data.get('number', 'Не вказано')))}</code>\n"
        f"<b>⭐ Рейтинг:</b> {client_rating_text}\n"
    )

    if order_type == 'taxi':
        return (
            f"🚕 <b>Нове замовлення №{order_id}</b>\n\n"
            f"<b>➡️ Звідки:</b> {html.escape(str(order_data.get('begin_address', '')))}\n"
            f"<b>🏁 Куди:</b> {html.escape(str(order_data.get('finish_address', '')))}\n"
            + (f"<b>💬 Коментар:</b> {html.escape(comment)}\n" if comment else "") +
            f"\n" + client_info_block +
            f"{reviews_text}\n" + timeout_text
        )
    elif order_type == 'voice_taxi':
        return (
            f"🚕🎙️ <b>Нове замовлення (адреси голосом) №{order_id}</b>\n\n"
            f"<b>➡️ Звідки:</b> 🎙️ Адреса записана голосом\n"
            f"<b>🏁 Куди:</b> 🎙️ Адреса записана голосом\n"
            + (f"<b>💬 Коментар:</b> {html.escape(comment)}\n" if comment else "") +
            f"\n" + client_info_block +
            f"{reviews_text}\n" + timeout_text
        )
    elif order_type == 'single_voice_order':
        return (
            f"🚕🎙️ <b>Швидке замовлення голосом №{order_id}</b>\n\n"
            f"<b>➡️ Звідки/Куди:</b> 🎙️ Вся інформація у голосовому повідомленні\n"
            + (f"<b>💬 Коментар:</b> {html.escape(comment)}\n" if comment else "") +
            f"\n" + client_info_block +
            f"{reviews_text}\n" + timeout_text
        )
    elif order_type == 'pickup_delivery':
        return (
            f"📦 <b>Нова доставка (забрати-привезти) №{order_id}</b>\n\n"
            f"<b>➡️ Звідки:</b> {html.escape(str(order_data.get('begin_address', '')))}\n"
            f"<b>🏁 Куди:</b> {html.escape(str(order_data.get('finish_address', '')))}\n"
            f"<b>📋 Деталі:</b> {html.escape(str(order_data.get('order_details', '')))}\n"
            + (f"<b>💬 Коментар:</b> {html.escape(comment)}\n" if comment else "") +
            f"\n" + client_info_block +
            f"{reviews_text}\n" + timeout_text
        )
    elif order_type == 'buy_delivery':
        return (
            f"🛒 <b>Нова доставка (покупка) №{order_id}</b>\n\n"
            f"<b>📋 Що купити:</b> {html.escape(str(order_data.get('order_details', '')))}\n"
            f"<b>🏁 Адреса доставки:</b> {html.escape(str(order_data.get('finish_address', '')))}\n"
            + (f"<b>💬 Коментар:</b> {html.escape(comment)}\n" if comment else "") +
            f"\n" + client_info_block +
            f"{reviews_text}\n" +
            "<i>❗️ Узгодьте з клієнтом деталі покупки та оплати.</i>\n\n" + timeout_text
        )
    return f"Невідомий тип замовлення №{order_id}"

async def dispatch_order_to_drivers(bot: Bot, order_id: int, order_data: dict, client_user: types.User, excluded_driver_id: int | None = None) -> None:
    """
    Initiates the sequential dispatch of an order to available drivers.
    """
    driver_ids: list[int] = await db_queries.get_working_driver_ids(
        order_id=order_id,
        order_lat=order_data.get('latitude'),
        order_lon=order_data.get('longitude'),
        excluded_driver_id=excluded_driver_id
    )

    if not driver_ids:
        # If this was a re-search and no other drivers were found, notify the client.
        if excluded_driver_id:
            await bot.send_message(client_user.id, 'На жаль, нам не вдалося знайти іншого водія для вашого замовлення. Спробуйте створити нове.', reply_markup=main_menu_keyboard)
            await db_queries.update_order_status(order_id, 'cancelled_no_drivers')
        # This is a regular search, and no drivers were found.
        # Or it's a pending dispatch that found no one.
        elif order_data.get('status') != 'pending_dispatch':
             await bot.send_message(client_user.id, 'На жаль, наразі немає вільних водіїв. Будь ласка, спробуйте пізніше.', reply_markup=main_menu_keyboard)
             await db_queries.update_order_status(order_id, 'cancelled_no_drivers')
        logger.info(f"No available drivers for order {order_id} (status: {order_data.get('status')}, is_research: {bool(excluded_driver_id)}).")
        return # Exit the function in all "no drivers" cases.
        
    # Prepare data to be stored for re-dispatch
    client_user_data = client_user.model_dump()
    # Store all necessary data in the database to be retrieved later
    dispatch_payload = {'order_data': order_data, 'client_user': client_user_data}
    
    await db_queries.start_order_dispatch(order_id, driver_ids, json.dumps(dispatch_payload))
    await db_queries.update_order_status(order_id, 'searching')

    # The initial call to process the first driver in the queue.
    # The function will now fetch all necessary data itself.
    await _process_next_driver_in_dispatch(bot, order_id)