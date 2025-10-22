from aiogram import types, F, Router, Bot
from aiogram.fsm.context import FSMContext
from keyboards.reply_keyboards import fav_addr_name_skip_keyboard
from utils.callback_factories import (
    SaveAddress
)
from states.fsm_states import FavAddressState
import html
from loguru import logger
from database import queries as db_queries

router = Router()

@router.callback_query(SaveAddress.filter())
async def save_address_start(callback: types.CallbackQuery, callback_data: SaveAddress, state: FSMContext) -> None:
    """
    Starts the process of saving a favorite address after a trip.

    Args:
        callback: The callback query from the "Save address" button.
        callback_data: The callback data containing the order ID.
        state: The FSM context.
    """
    user_id = callback.from_user.id
    order_id = callback_data.order_id

    address_data = {}
    geocoded_successfully = False
    if order_id: # Збереження після поїздки
        finish_address = await db_queries.get_order_finish_address(order_id, user_id)
        if not finish_address:
            await callback.answer("Не вдалося знайти адресу цього замовлення.", show_alert=True)
            return
        address_data['address'] = finish_address
        # Спробуємо отримати координати для збереженої адреси
        try:
            from utils.geocoder import geocode, SUMY_OBLAST_VIEWBOX
            location = await geocode(f"{finish_address}, Глухів", language='uk', timeout=10, viewbox=SUMY_OBLAST_VIEWBOX, bounded=True)
            address_data['latitude'] = location.latitude if location else None
            address_data['longitude'] = location.longitude if location else None
            geocoded_successfully = location is not None
        except Exception as e:
            logger.warning(f"Не вдалося геокодувати адресу '{finish_address}' при збереженні: {e}")
            address_data['latitude'] = None
            address_data['longitude'] = None

        await state.set_state(FavAddressState.get_name)
        await state.update_data(fav_address_to_save=address_data)

        message_text = (
            f"Ви хочете зберегти адресу:\n"
            f"<b>{html.escape(address_data['address'])}</b>\n\n"
        )
        if not geocoded_successfully:
            message_text += "⚠️ <i>Не вдалося визначити точні координати. Адреса буде збережена як текст.</i>\n\n"
        
        message_text += (
            "🏷️ Тепер придумайте коротку назву для неї (наприклад, 'Дім', 'Робота').\n\n"
            "<i>Або натисніть 'Пропустити', і ми використаємо саму адресу як назву.</i>"
        )

        await callback.message.answer(
            message_text,
            reply_markup=fav_addr_name_skip_keyboard
        )
        await callback.answer()
