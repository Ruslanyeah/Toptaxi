from aiogram import Bot
from loguru import logger
import aiosqlite
from config.config import TIMEZONE, DRIVER_ACCEPT_TIMEOUT
from database import queries as db_queries
from dateutil import parser
from datetime import datetime, timedelta
import html
import asyncio
from utils.batch_sender import broadcast_messages

PENDING_DISPATCH_TIMEOUT_MINUTES = 15 # Таймаут для поиска водителя для предзаказа
PREORDER_REMINDER_MINUTES = 30 # Remind driver X minutes before the order

async def check_scheduled_orders(bot: Bot):
    """
    Checks for scheduled orders that are due and starts the driver search.
    """
    from .order_dispatch import dispatch_order_to_drivers
    orders_to_start = await db_queries.get_due_scheduled_orders()

    if not orders_to_start:
        return

    logger.info(f"Found {len(orders_to_start)} scheduled order(s) to start. Processing...")

    async def _process_single_scheduled_order(order: dict):
        order_id = order['id']
        client_id = order['client_id']
        try:
            await bot.send_message(client_id, f"⏰ Настав час вашого замовлення №{order_id}. Починаємо пошук водія!")
            client_user = await bot.get_chat(client_id)
            await dispatch_order_to_drivers(bot, order_id, dict(order), client_user)
        except Exception as e:
            logger.error(f"Error processing scheduled order {order_id}: {e}")

    # Create a background task for each order to avoid blocking the scheduler
    for order in orders_to_start:
        asyncio.create_task(_process_single_scheduled_order(order))

async def check_dispatch_timeouts(bot: Bot):
    """
    Checks for orders in 'searching' state where the offer to a driver has timed out.
    Also handles "stale" orders that got stuck in 'searching' state after a restart.
    """
    from .order_dispatch import _process_next_driver_in_dispatch
    
    # Fetch both timed-out orders and stale orders (stuck without an offer sent)
    stale_and_timed_out_orders = await db_queries.get_stale_and_timed_out_dispatches(DRIVER_ACCEPT_TIMEOUT)
    
    if not stale_and_timed_out_orders:
        return

    logger.info(f"Found {len(stale_and_timed_out_orders)} stale or timed-out dispatch(es). Processing...")

    async def _process_single_timeout(order_row: aiosqlite.Row):
        # Преобразуем объект sqlite3.Row в стандартный словарь Python
        order = dict(order_row)
        order_id = order.get('id')
        client_id = order.get('client_id')
        
        driver_ids_str = order.get('dispatch_driver_ids')
        current_index = order.get('dispatch_current_driver_index', 0)
        driver_ids = [int(id_str) for id_str in driver_ids_str.split(',')] if driver_ids_str else []

        # Notify the previous driver that the offer has expired
        if driver_ids and current_index < len(driver_ids):
            previous_driver_id = driver_ids[current_index]
            try:
                # Only send timeout message if an offer was actually sent
                if order.get('dispatch_offer_sent_at'):
                    await bot.send_message(previous_driver_id, f"⌛️ Час на прийняття замовлення №{order_id} вичерпано.")
            except Exception as e:
                logger.warning(f"Could not send timeout message to driver {previous_driver_id}: {e}")

        if order.get('dispatch_offer_sent_at'):
            logger.info(f"Dispatch for order {order_id} has timed out. Advancing to next driver.")
        else:
            logger.info(f"Found stale searching order {order_id}. Restarting dispatch process.")

        # Increment the dispatch index and let the self-sufficient function handle the rest
        await db_queries.increment_dispatch_index(order_id)
        await _process_next_driver_in_dispatch(bot, order_id)

    # Запускаем обработку каждого заказа как отдельную фоновую задачу.
    # Это позволяет основной функции планировщика завершиться мгновенно, не блокируя event loop.
    for order in stale_and_timed_out_orders:
        asyncio.create_task(_process_single_timeout(order))

async def check_pending_dispatch_orders(bot: Bot):
    """
    Periodically checks for orders awaiting dispatch and tries to find drivers.
    This gives pre-orders a grace period to find a driver instead of failing instantly.
    """
    from .order_dispatch import dispatch_order_to_drivers
    pending_orders = await db_queries.get_pending_dispatch_orders()

    if not pending_orders:
        return

    logger.info(f"Found {len(pending_orders)} pending dispatch order(s). Processing...")

    async def _process_single_pending_order(order: dict):
        order_id = order['id']
        client_id = order['client_id']
        
        # Проверяем, не истек ли таймаут ожидания
        pending_time = parser.parse(order['pending_dispatch_at'])
        if datetime.now(TIMEZONE) > pending_time + timedelta(minutes=PENDING_DISPATCH_TIMEOUT_MINUTES):
            logger.warning(f"Order {order_id} has been pending for too long. Cancelling.")
            await db_queries.update_order_status(order_id, 'cancelled_no_drivers')
            try:
                await bot.send_message(client_id, f"На жаль, нам не вдалося знайти водія для вашого замовлення №{order_id} протягом {PENDING_DISPATCH_TIMEOUT_MINUTES} хвилин. Замовлення скасовано.")
            except Exception as e:
                logger.error(f"Failed to send final cancellation for pending order {order_id} to client {client_id}: {e}")
            return

        try:
            client_user = await bot.get_chat(client_id)
            await dispatch_order_to_drivers(bot, order_id, dict(order), client_user)
        except Exception as e:
            logger.error(f"Error dispatching pending order {order_id}: {e}")

    # Create a background task for each pending order
    for order in pending_orders:
        asyncio.create_task(_process_single_pending_order(order))

async def check_preorder_reminders(bot: Bot):
    """
    Checks for accepted pre-orders and sends a reminder to the driver.
    """
    orders_for_reminder = await db_queries.get_preorders_for_reminder(PREORDER_REMINDER_MINUTES)

    if not orders_for_reminder:
        return

    logger.info(f"Found {len(orders_for_reminder)} pre-order(s) to remind drivers about. Sending reminders...")

    async def _send_single_reminder(order: dict):
        try:
            time_str = parser.parse(order['scheduled_at']).strftime('%H:%M')
            reminder_text = (
                f"🔔 <b>Нагадування про заплановане замовлення!</b>\n\n"
                f"Замовлення №{order['id']} на <b>{time_str}</b>\n"
                f"Адреса подачі: {html.escape(order['begin_address'])}\n\n"
                f"Будь ласка, не запізнюйтесь."
            )
            await bot.send_message(order['driver_id'], reminder_text)
            await db_queries.mark_preorder_reminder_sent(order['id'])
        except Exception as e:
            logger.error(f"Failed to send reminder for order {order['id']} to driver {order['driver_id']}: {e}")

    # Create a background task for each reminder
    for order in orders_for_reminder:
        asyncio.create_task(_send_single_reminder(order))
        
    logger.info(f"Finished sending {len(orders_for_reminder)} reminders.")