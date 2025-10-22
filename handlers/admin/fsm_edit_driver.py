from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
import html

from states.fsm_states import AdminState
from database import queries as db_queries
from keyboards.common import Navigate
from keyboards.reply_keyboards import fsm_cancel_keyboard
from utils.callback_factories import AdminDriverAction

router = Router()

# --- Edit Driver FSM ---

@router.callback_query(AdminDriverAction.filter(F.action == 'edit_fullname'))
async def edit_driver_fullname_start(call: types.CallbackQuery, callback_data: AdminDriverAction, state: FSMContext):
    """Starts the FSM to edit a driver's full name."""
    await state.set_state(AdminState.edit_driver_fullname)
    await state.update_data(driver_id_to_edit=callback_data.user_id)
    await call.message.answer(
        f"<b>✏️ Редагування ПІБ водія ID {callback_data.user_id}</b>\n\n"
        "Введіть нове повне ім'я:",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.edit_driver_fullname, F.text)
async def process_edit_driver_fullname(message: types.Message, state: FSMContext):
    """Processes the new full name and updates the database."""
    data = await state.get_data()
    driver_id = data.get('driver_id_to_edit')
    
    await db_queries.update_driver_field(driver_id, 'full_name', message.text)
    await message.answer(f"✅ ПІБ для водія ID <code>{driver_id}</code> оновлено.", reply_markup=types.ReplyKeyboardRemove())
    
    await state.clear()
    from ..common.helpers import _display_driver_profile
    await _display_driver_profile(message, driver_id)

@router.callback_query(AdminDriverAction.filter(F.action == 'edit_avto_num'))
async def edit_driver_avto_num_start(call: types.CallbackQuery, callback_data: AdminDriverAction, state: FSMContext):
    """Starts the FSM to edit a driver's car number."""
    await state.set_state(AdminState.edit_driver_avto_num)
    await state.update_data(driver_id_to_edit=callback_data.user_id)
    await call.message.answer(
        f"<b>✏️ Редагування номера авто водія ID {callback_data.user_id}</b>\n\n"
        "Введіть новий номер автомобіля:",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.edit_driver_avto_num, F.text)
async def process_edit_driver_avto_num(message: types.Message, state: FSMContext):
    """Processes the new car number and updates the database."""
    data = await state.get_data()
    driver_id = data.get('driver_id_to_edit')
    
    await db_queries.update_driver_field(driver_id, 'avto_num', message.text)
    await message.answer(f"✅ Номер авто для водія ID <code>{driver_id}</code> оновлено.", reply_markup=types.ReplyKeyboardRemove())
    
    await state.clear()
    from ..common.helpers import _display_driver_profile
    await _display_driver_profile(message, driver_id)

@router.callback_query(AdminDriverAction.filter(F.action == 'edit_phone_num'))
async def edit_driver_phone_num_start(call: types.CallbackQuery, callback_data: AdminDriverAction, state: FSMContext):
    """Starts the FSM to edit a driver's phone number."""
    await state.set_state(AdminState.edit_driver_phone_num)
    await state.update_data(driver_id_to_edit=callback_data.user_id)
    await call.message.answer(
        f"<b>✏️ Редагування телефону водія ID {callback_data.user_id}</b>\n\n"
        "Введіть новий контактний номер телефону:",
        reply_markup=fsm_cancel_keyboard
    )
    await call.answer()

@router.message(AdminState.edit_driver_phone_num, F.text)
async def process_edit_driver_phone_num(message: types.Message, state: FSMContext):
    """Processes the new phone number and updates the database."""
    data = await state.get_data()
    driver_id = data.get('driver_id_to_edit')
    
    await db_queries.update_driver_field(driver_id, 'phone_num', message.text)
    await message.answer(f"✅ Телефон для водія ID <code>{driver_id}</code> оновлено.", reply_markup=types.ReplyKeyboardRemove())
    
    await state.clear()
    from ..common.helpers import _display_driver_profile
    await _display_driver_profile(message, driver_id)

# --- Generic Cancellation for this FSM ---
@router.message(
    StateFilter(
        AdminState.edit_driver_fullname,
        AdminState.edit_driver_avto_num,
        AdminState.edit_driver_phone_num
    ),
    F.text == "🚫 Скасувати"
)
async def cancel_edit_driver_action(message: types.Message, state: FSMContext):
    """Cancels any driver editing action."""
    data = await state.get_data()
    driver_id = data.get('driver_id_to_edit')
    await state.clear()
    await message.answer("✅ Редагування скасовано.", reply_markup=types.ReplyKeyboardRemove())
    if driver_id:
        from ..common.helpers import _display_driver_profile
        await _display_driver_profile(message, driver_id)
