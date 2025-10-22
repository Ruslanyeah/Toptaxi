from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
import html, logging

from states.fsm_states import AdminState
from database import queries as db_queries
from keyboards.common import Navigate
from keyboards.reply_keyboards import fsm_cancel_keyboard
from utils.callback_factories import AdminOrderAction
from .admin_helpers import show_client_history_page, show_admin_order_details

logger = logging.getLogger(__name__)

router = Router()

# --- Search Order by Client ID ---

@router.callback_query(Navigate.filter(F.to == 'search_order_by_client'))
async def search_order_by_client_start(call: types.CallbackQuery, state: FSMContext):
    """Starts the FSM to search for orders by client ID."""
    await state.set_state(AdminState.get_client_id_for_order_search)
    await call.message.edit_text(
        "<b>🔎 Пошук замовлень по клієнту</b>\n\n"
        "Введіть Telegram ID клієнта, щоб переглянути його історію замовлень.",
        reply_markup=None
    )
    await call.answer()

@router.message(AdminState.get_client_id_for_order_search)
async def process_client_id_for_search(message: types.Message, state: FSMContext):
    """Processes the client ID and shows their order history."""
    if not message.text or not message.text.isdigit():
        await message.answer("Будь ласка, введіть коректний числовий ID.")
        return

    client_id = int(message.text)
    await state.clear()
    
    # Reuse the existing function to show order history
    await show_client_history_page(message, client_id, page=0)

# --- Search Order by Order ID ---

@router.callback_query(Navigate.filter(F.to == 'search_order_by_id'))
async def search_order_by_id_start(call: types.CallbackQuery, state: FSMContext):
    """Starts the FSM to search for an order by its ID."""
    await state.set_state(AdminState.get_order_id_for_search)
    await call.message.edit_text(
        "<b>🔎 Пошук замовлення по ID</b>\n\n"
        "Введіть ID замовлення, щоб переглянути його деталі.",
        reply_markup=None
    )
    await call.answer()

@router.message(AdminState.get_order_id_for_search)
async def process_order_id_for_search(message: types.Message, state: FSMContext):
    """Processes the order ID and shows its details."""
    if not message.text or not message.text.isdigit():
        await message.answer("Будь ласка, введіть коректний числовий ID замовлення.")
        return

    order_id = int(message.text)
    await state.clear()

    # Create a dummy callback data object to reuse the existing details handler
    class DummyCallbackData:
        def __init__(self, order_id):
            self.order_id = order_id

    await show_admin_order_details(message, DummyCallbackData(order_id))

# --- Reassign Order ---

@router.callback_query(AdminOrderAction.filter(F.action == 'reassign_order'))
async def reassign_order_start(call: types.CallbackQuery, callback_data: AdminOrderAction, state: FSMContext):
    """Starts the FSM to reassign an order to a different driver."""
    await state.set_state(AdminState.get_driver_id_for_reassign)
    await state.update_data(order_id_to_reassign=callback_data.order_id)
    # Отправляем новое сообщение с ReplyKeyboard для возможности отмены
    await call.message.answer(
        f"<b>🔄 Перепризначення замовлення №{callback_data.order_id}</b>\n\n"
        "Введіть Telegram ID нового водія.",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.get_driver_id_for_reassign, F.text)
async def process_reassign_driver_id(message: types.Message, state: FSMContext):
    """
    Processes the new driver's ID, validates it, and reassigns the order.
    """
    if not message.text.isdigit():
        await message.answer("❌ Помилка: ID водія має бути числом. Спробуйте ще раз.", reply_markup=fsm_cancel_keyboard)
        return

    new_driver_id = int(message.text)
    data = await state.get_data()
    order_id = data.get('order_id_to_reassign')

    if not order_id:
        await message.answer("❌ Помилка: не вдалося знайти ID замовлення. Процес скасовано.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        return

    # Проверяем, существует ли такой водитель и свободен ли он
    driver_data = await db_queries.get_driver_for_reassign(new_driver_id)
    if not driver_data:
        await message.answer(f"❌ Водія з ID <code>{new_driver_id}</code> не знайдено. Перевірте ID та спробуйте ще раз.", reply_markup=fsm_cancel_keyboard)
        return
    
    if not driver_data['isWorking']:
        await message.answer(f"❌ Водій ID <code>{new_driver_id}</code> зараз зайнятий на іншому замовленні. Оберіть іншого водія.", reply_markup=fsm_cancel_keyboard)
        return

    # Получаем ID старого водителя для корректного освобождения
    order_info = await db_queries.get_order_for_reassign(order_id)
    old_driver_id = order_info['driver_id'] if order_info else None

    try:
        await db_queries.reassign_order(order_id, new_driver_id, old_driver_id)
        await message.answer(f"✅ Замовлення №{order_id} успішно перепризначено на водія ID <code>{new_driver_id}</code>.", reply_markup=types.ReplyKeyboardRemove())

        # Уведомляем всех участников
        await message.bot.send_message(new_driver_id, f"❗️ Адміністратор призначив вам замовлення №{order_id}.")
        if old_driver_id:
            await message.bot.send_message(old_driver_id, f"❗️ Замовлення №{order_id} було знято з вас адміністратором.")
        if order_info and order_info['client_id']:
            await message.bot.send_message(order_info['client_id'], f"❗️ Увага! На ваше замовлення №{order_id} було призначено іншого водія.")

    except Exception as e:
        logger.error(f"Failed to reassign order {order_id} to driver {new_driver_id}: {e}")
        await message.answer(f"❌ Сталася помилка під час перепризначення: {e}", reply_markup=types.ReplyKeyboardRemove())
    finally:
        await state.clear()
        # Показываем обновленные детали заказа
        class DummyCallbackData:
            def __init__(self, oid): self.order_id = oid
        await show_admin_order_details(message, DummyCallbackData(order_id))

@router.message(AdminState.get_driver_id_for_reassign, F.text == "🚫 Скасувати")
async def cancel_reassign_order(message: types.Message, state: FSMContext):
    """Cancels the order reassignment process."""
    data = await state.get_data()
    order_id = data.get('order_id_to_reassign')
    await state.clear()
    await message.answer("✅ Перепризначення скасовано.", reply_markup=types.ReplyKeyboardRemove())
    if order_id:
        # Возвращаемся к деталям заказа
        class DummyCallbackData:
            def __init__(self, oid): self.order_id = oid
        await show_admin_order_details(message, DummyCallbackData(order_id))