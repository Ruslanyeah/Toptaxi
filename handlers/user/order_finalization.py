from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
import asyncio
import json
from aiogram.filters import StateFilter, or_f

from states.fsm_states import UserState, PreOrderState, DeliveryState
from keyboards.reply_keyboards import main_menu_keyboard
from database import queries as db_queries
from utils.callback_factories import ConfirmUnfoundAddress, OrderCallbackData
from .order_dispatch import dispatch_order_to_drivers, _process_next_driver_in_dispatch
from .order_helpers import format_confirmation_text, validate_order_data, _go_to_phone_number_step, _go_to_finish_address_step, _go_to_begin_address_step

router = Router()

@router.message(
    F.text == 'Створити замовлення 🏁',
    StateFilter(UserState.confirm_order, PreOrderState.confirm_preorder, DeliveryState.confirm_delivery)
)
async def create_order_confirmed(message: types.Message, state: FSMContext) -> None:
    """
    A unified handler for the final order confirmation button across all order types.
    """
    user_data = await state.get_data()

    is_valid, error_message = await validate_order_data(user_data)
    if not is_valid:
        await message.answer(error_message, reply_markup=main_menu_keyboard)
        await state.clear()
        return

    is_preorder = user_data.get('is_preorder', False)
    initial_status = 'scheduled' if is_preorder else 'searching'

    order_id = await db_queries.create_order_in_db(message.from_user.id, user_data, initial_status=initial_status)
    if not order_id:
        await message.answer("Сталася помилка під час створення замовлення. Будь ласка, почніть заново.", reply_markup=main_menu_keyboard)
        await state.clear()
        return

    # For regular orders, immediately start the dispatch process
    if not is_preorder:
        # Prepare a clean data dictionary to pass to the dispatcher
        dispatch_data = {
            'latitude': user_data.get('latitude'),
            'longitude': user_data.get('longitude'),
            'begin_address': user_data.get('begin_address'),
            'finish_address': user_data.get('finish_address'),
            'comment': user_data.get('comment'),
            'number': user_data.get('number'),
            'order_type': user_data.get('order_type', 'taxi'),
            'order_details': user_data.get('order_details')
        }
        await dispatch_order_to_drivers(message.bot, order_id, dispatch_data, message.from_user)
    
    success_text = format_confirmation_text(user_data, is_final=True)
    await message.answer(success_text, reply_markup=main_menu_keyboard)
    await state.clear()

@router.callback_query(ConfirmUnfoundAddress.filter(F.action == 'use_anyway'))
async def use_unfound_address_anyway(call: types.CallbackQuery, state: FSMContext):
    """
    Handles the 'Use anyway' button when a geocoding service fails to find an address.
    """
    await call.answer()
    data = await state.get_data()
    unfound_address = data.get('unfound_address_text')

    if not unfound_address or not data.get('unfound_address_type'):
        await call.message.answer("Сталася помилка. Будь ласка, спробуйте ввести адресу ще раз.")
        return

    address_type = data.get('unfound_address_type')
    if address_type == 'begin':
        await state.update_data(begin_address=unfound_address, latitude=None, longitude=None)
        await call.message.edit_text(f'✅ Адресу подачі встановлено як: <b>{unfound_address}</b>')
        await _go_to_finish_address_step(call, state)
    else: # finish
        await state.update_data(finish_address=unfound_address)
        await call.message.edit_text(f'✅ Адресу призначення встановлено як: <b>{unfound_address}</b>')
        await _go_to_phone_number_step(call, state)

@router.callback_query(ConfirmUnfoundAddress.filter(F.action == 'retry'))
async def retry_unfound_address(call: types.CallbackQuery, state: FSMContext):
    """
    Handles the 'Retry' button when a geocoding service fails to find an address,
    returning the user to the address input step.
    """
    await call.answer()
    data = await state.get_data()
    address_type = data.get('unfound_address_type')

    await call.message.edit_text("Будь ласка, спробуйте ввести адресу ще раз, можливо, більш детально.")

    if address_type == 'begin':
        # This was missing. We need to go back to the BEGIN address step.
        await _go_to_begin_address_step(call, state)
    else: # finish or unknown, default to finish
        # This is the old behavior, which is correct for the finish address.
        await _go_to_finish_address_step(call, state)

@router.callback_query(OrderCallbackData.filter(F.action == 'reject_by_driver'))
async def reject_order_by_driver(call: types.CallbackQuery, callback_data: OrderCallbackData):
    """
    Handles a driver rejecting an order.
    It increments the dispatch index and offers the order to the next driver.
    """
    order_id = callback_data.order_id
    driver_id = call.from_user.id

    # Check if this driver is the one the order was offered to
    is_correct_driver = await db_queries.check_if_driver_is_current_for_order(order_id, driver_id)
    if not is_correct_driver:
        await call.answer("Це замовлення вже не актуальне для вас.", show_alert=True)
        return

    await call.answer("Ви відмовились від замовлення.")
    await call.message.edit_text(f"Ви відмовились від замовлення №{order_id}.")
    await db_queries.record_driver_rejection(order_id, driver_id)

    # Increment index and proceed to the next driver
    await db_queries.increment_dispatch_index(order_id)

    # The self-sufficient function will handle fetching data and sending the order.
    asyncio.create_task(_process_next_driver_in_dispatch(call.bot, order_id))