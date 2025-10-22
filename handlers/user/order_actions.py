from aiogram import types, F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
from loguru import logger
from database import queries as db_queries
from utils.callback_factories import OrderCallbackData
from .order_dispatch import dispatch_order_to_drivers, _process_next_driver_in_dispatch
from ..common.helpers import safe_edit_or_send, _display_driver_profile
from .rating import start_driver_rating_process, request_rating_from_driver_for_client

router = Router()

@router.callback_query(OrderCallbackData.filter(F.action == 'accept'))
async def accept_order(callback: types.CallbackQuery, callback_data: OrderCallbackData, state: FSMContext) -> None:
    """
    Handles a driver accepting an order.
    """
    driver_id = callback.from_user.id
    order_id = callback_data.order_id

    success = await db_queries.accept_order(order_id, driver_id)

    if not success:
        await callback.answer("Замовлення вже прийнято або скасовано.", show_alert=True)
        await safe_edit_or_send(callback, f"Замовлення №{order_id} вже неактуальне.")
        return


    # Fetch order details to get coordinates for the navigation button
    order_details = await db_queries.get_order_details(order_id)
    driver_info = await db_queries.get_driver_info_for_client(driver_id)
    await callback.answer("✅ Ви прийняли замовлення!", show_alert=True)

    kb_builder = InlineKeyboardBuilder()
    kb_builder.button(text='🚗 Я на місці', callback_data=OrderCallbackData(action='driver_arrived', order_id=order_id))
    
    # Add a button to listen to the voice message for voice orders
    if order_details and order_details['order_type'] == 'single_voice_order':
        kb_builder.button(text='🎙️ Прослухати замовлення', callback_data=OrderCallbackData(action='listen_voice_order', order_id=order_id))

    # Add navigation button if coordinates are available
    if order_details and order_details['latitude'] and order_details['longitude']:
        lat, lon = order_details['latitude'], order_details['longitude']
        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
        kb_builder.button(text="🗺️ Прокласти маршрут", url=nav_url)

    kb_builder.button(text='❌ Скасувати замовлення', callback_data=OrderCallbackData(action='cancel_by_driver', order_id=order_id))
    kb_builder.adjust(1) # Each button on a new line for clarity

    driver_order_kb = kb_builder.as_markup()

    await state.clear()

    await safe_edit_or_send(callback, f"🚗 Ви прийняли замовлення №{order_id}. Повідомте, коли прибудете до клієнта.", reply_markup=driver_order_kb)
    
    client_id = await db_queries.get_order_client_id(order_id)
    try:
        client_key = StorageKey(bot_id=callback.bot.id, chat_id=client_id, user_id=client_id)
        await state.storage.set_state(client_key, state=None)
        await state.storage.set_data(client_key, data={})
        logger.info(f"Стан для клієнта {client_id} очищено після прийняття замовлення {order_id}.")
    except Exception as e:
        logger.error(f"Не вдалося очистити стан для клієнта {client_id}: {e}")

    rating_str = f"{driver_info['rating']:.1f} ⭐" if driver_info and driver_info['rating'] > 0 else "немає"
    client_message_text = (
        f"🎉 <b>Ваше замовлення №{order_id} прийнято! Водій вже в дорозі!</b>\n\n"
        f"<b>Ім'я:</b> {driver_info['full_name']}\n"
        f"<b>Рейтинг:</b> {rating_str}\n"
        f"<b>Номер автомобіля:</b> {driver_info['avto_num']}\n"
        f"<b>Номер телефону:</b> {driver_info['phone_num']}"
    )
    try:
        await callback.bot.send_message(client_id, client_message_text)

    except Exception as e:
        logger.error(f"Не вдалося сповістити клієнта {client_id} про прийняття замовлення {order_id}: {e}")

@router.callback_query(OrderCallbackData.filter(F.action == 'reject_by_driver'))
async def reject_by_driver(callback: types.CallbackQuery, callback_data: OrderCallbackData, bot: Bot) -> None:
    """
    Handles a driver rejecting an order, then immediately processes the next driver.
    """
    order_id = callback_data.order_id
    driver_id = callback.from_user.id

    # Check if the order is still in 'searching' state and offered to this driver
    current_driver_id_in_db = await db_queries.get_current_driver_for_order(order_id)
    if current_driver_id_in_db != driver_id:
        await callback.answer("Це замовлення вже неактуальне для вас.", show_alert=True)
        try:
            await safe_edit_or_send(callback, f"Замовлення №{order_id} вже неактуальне.")
        except TelegramBadRequest:
            pass # Message might have been deleted, ignore
        return

    await db_queries.increment_dispatch_index(order_id)
    await db_queries.record_driver_rejection(order_id, driver_id)
    
    await callback.answer("Ви відмовились від замовлення.", show_alert=True)
    try:
        await safe_edit_or_send(callback, f"❌ Ви відмовились від замовлення №{order_id}.")
    except TelegramBadRequest:
        pass # Ignore if message is already gone

    # Immediately try to dispatch to the next driver
    asyncio.create_task(_process_next_driver_in_dispatch(bot, order_id))

@router.callback_query(OrderCallbackData.filter(F.action == 'driver_arrived'))
async def driver_arrived(callback: types.CallbackQuery, callback_data: OrderCallbackData) -> None:
    """
    Handles the driver pressing the "I have arrived" button.
    """
    client_id = await db_queries.get_order_client_id(callback_data.order_id)
    if not client_id:
        await callback.answer("Не вдалося знайти замовлення.", show_alert=True)
        return

    order_id = callback_data.order_id
    embark_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='✅ Пасажир у машині', callback_data=OrderCallbackData(action='client_embarked', order_id=order_id).pack())],
        [types.InlineKeyboardButton(text='❌ Скасувати замовлення', callback_data=OrderCallbackData(action='cancel_by_driver', order_id=order_id).pack())]
    ])
    await safe_edit_or_send(callback, f"⏳ Ви повідомили клієнта про прибуття. Очікуйте, поки він сяде в машину.", reply_markup=embark_kb)
    
    await callback.bot.send_message(client_id, f"👋 Водій за замовленням №{order_id} прибув і очікує на вас.")
    await callback.answer("✅ Сповіщення клієнту надіслано.")

@router.callback_query(OrderCallbackData.filter(F.action == 'listen_voice_order'))
async def listen_voice_order_handler(callback: types.CallbackQuery, callback_data: OrderCallbackData):
    """
    Handles the driver's request to re-listen to the voice order.
    """
    order_id = callback_data.order_id
    driver_id = callback.from_user.id

    order_details = await db_queries.get_order_details(order_id)

    if not order_details or order_details['driver_id'] != driver_id:
        await callback.answer("Це замовлення більше не актуальне для вас.", show_alert=True)
        return

    voice_id = order_details['begin_address_voice_id']
    if voice_id:
        await callback.bot.send_voice(driver_id, voice_id, caption=f"<b>🎙️ Голосове замовлення №{order_id}:</b>")
        await callback.answer("✔️ Голосове повідомлення надіслано.")
    else:
        await callback.answer("❌ Не вдалося знайти голосове повідомлення для цього замовлення.", show_alert=True)


@router.callback_query(OrderCallbackData.filter(F.action == 'client_embarked'))
async def client_embarked(callback: types.CallbackQuery, callback_data: OrderCallbackData) -> None:
    """
    Handles the driver pressing the "Passenger is in the car" button.
    """
    order_id = callback_data.order_id
    await db_queries.update_order_status(order_id, 'in_progress')
    client_id = await db_queries.get_order_client_id(order_id)
    if not client_id: return

    finish_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='🏁 Завершити поїздку', callback_data=OrderCallbackData(action='finish_by_driver', order_id=order_id).pack())],
        [types.InlineKeyboardButton(text='❌ Скасувати замовлення', callback_data=OrderCallbackData(action='cancel_by_driver', order_id=order_id).pack())]
    ])
    await safe_edit_or_send(callback, f"🛣️ Поїздка за замовленням №{order_id} почалася. Після прибуття на місце призначення, завершіть поїздку.", reply_markup=finish_kb)
    await callback.bot.send_message(client_id, "😊 Приємної поїздки!")
    await callback.answer("✅ Поїздка почалася!")

@router.callback_query(OrderCallbackData.filter(F.action == 'finish_by_driver'))
async def finish_by_driver(callback: types.CallbackQuery, callback_data: OrderCallbackData, state: FSMContext) -> None:
    """
    Handles the driver finishing the trip.
    """
    order_id = callback_data.order_id
    driver_id = callback.from_user.id
    client_id = await db_queries.get_order_client_id(order_id)

    await db_queries.finish_order(order_id, driver_id)
    await state.clear()

    await safe_edit_or_send(callback, f"✅ Замовлення №{order_id} успішно завершено!")
    await callback.answer("✅ Замовлення завершено!", show_alert=True)

    # Запрашиваем у водителя оценку для клиента
    # Функция start_client_rating_process переименована для ясности
    await request_rating_from_driver_for_client(callback.message, order_id)

    if client_id:
        await start_driver_rating_process(callback.bot, client_id, order_id)
        await db_queries.increment_client_finish_count(client_id)

@router.callback_query(OrderCallbackData.filter(F.action == 'cancel_by_driver'))
async def cancel_by_driver(callback: types.CallbackQuery, callback_data: OrderCallbackData, state: FSMContext) -> None:
    """
    Handles a driver cancelling an accepted order.
    """
    driver_id = callback.from_user.id
    order_id = callback_data.order_id
    
    # Atomically revert the order status. If it fails, the order was already handled.
    reverted_successfully = await db_queries.revert_order_to_searching(order_id, driver_id)
    if not reverted_successfully:
        await callback.answer("Це замовлення вже неактуальне.", show_alert=True)
        await safe_edit_or_send(callback, f"Замовлення №{order_id} вже неактуальне.")
        return

    await state.clear()
    await safe_edit_or_send(callback, f"↪️ Ви скасували замовлення №{order_id}. Воно передано іншим водіям.")
    await callback.answer("↪️ Замовлення скасовано та передано іншим.", show_alert=True)

    order = await db_queries.get_order_details(order_id)
    if not order:
        logger.warning(f"Order {order_id} disappeared after driver cancellation.")
        return

    client_id = order['client_id']

    try:
        await callback.bot.send_message(
            client_id,
            f"❗️<b>Увага!</b>\nВодій скасував ваше замовлення №{order_id}. "
            "Ми вже автоматично шукаємо нового водія для вас."
        )
    except Exception as e:
        logger.warning(f"Failed to send re-search notice to client {client_id} (bot might be blocked). Cancelling order {order_id} permanently. Error: {e}")
        await db_queries.update_order_status(order_id, 'cancelled_no_drivers')
    finally:
        # Если уведомление успешно, запускаем новый поиск
        # This runs regardless of whether the notification was successful,
        # ensuring the order is re-dispatched.
        client_user = await callback.bot.get_chat(client_id)
        order_data = dict(order)
        asyncio.create_task(dispatch_order_to_drivers(callback.bot, order_id, order_data, client_user, excluded_driver_id=driver_id))