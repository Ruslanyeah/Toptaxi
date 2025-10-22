from aiogram import types

# --- Main Menu ---
main_menu_kb = [
    [types.KeyboardButton(text='🚕 Замовити таксі'), types.KeyboardButton(text='📅 Замовити на час')],
    [types.KeyboardButton(text='🎙️ Швидке замовлення голосом')],
    [types.KeyboardButton(text='📦 Замовити доставку')],
    [types.KeyboardButton(text='🏠 Особистий кабінет'), types.KeyboardButton(text='☎️ Контакти та допомога')]
]
main_menu_keyboard = types.ReplyKeyboardMarkup(keyboard=main_menu_kb, resize_keyboard=True)

# --- FSM & Order Creation ---
phone_request_kb = [
    [types.KeyboardButton(text='📱 Поділитися номером телефону', request_contact=True)],
    [types.KeyboardButton(text='🔙 Повернутися в меню')]
]
phone_request_keyboard = types.ReplyKeyboardMarkup(keyboard=phone_request_kb, resize_keyboard=True)

order_confirm_kb = [
    [types.KeyboardButton(text='Створити замовлення 🏁')],
    [types.KeyboardButton(text='🚫 Скасувати')]
]
order_confirm_keyboard = types.ReplyKeyboardMarkup(keyboard=order_confirm_kb, resize_keyboard=True)

comment_skip_kb = [
    [types.KeyboardButton(text='Без коментаря')],
    [types.KeyboardButton(text='🚫 Скасувати')]
]
comment_skip_keyboard = types.ReplyKeyboardMarkup(keyboard=comment_skip_kb, resize_keyboard=True)

fav_addr_name_skip_kb = [
    [types.KeyboardButton(text='➡️ Пропустити')]
]
fav_addr_name_skip_keyboard = types.ReplyKeyboardMarkup(keyboard=fav_addr_name_skip_kb, resize_keyboard=True, one_time_keyboard=True)

location_or_skip_kb = [
    [types.KeyboardButton(text='📍 Надіслати геолокацію', request_location=True)],
    [types.KeyboardButton(text='➡️ Пропустити')],
    [types.KeyboardButton(text='🚫 Скасувати')]
]
location_or_skip_keyboard = types.ReplyKeyboardMarkup(keyboard=location_or_skip_kb, resize_keyboard=True, one_time_keyboard=True)

delivery_type_kb = [
    [types.KeyboardButton(text='📮 Забрати і доставити')],
    [types.KeyboardButton(text='🛍️ Купити і доставити')],
    [types.KeyboardButton(text='🔙 Повернутися в меню')]
]
delivery_type_keyboard = types.ReplyKeyboardMarkup(keyboard=delivery_type_kb, resize_keyboard=True, one_time_keyboard=True)

def get_driver_cabinet_keyboard(on_shift: bool, is_available: bool) -> types.ReplyKeyboardMarkup:
    driver_cabinet_kb = []
    if not on_shift:
        driver_cabinet_kb.append([types.KeyboardButton(text='🚀 Почати зміну')])
    else:
        # Водій на зміні
        if is_available:
            driver_cabinet_kb.append([types.KeyboardButton(text='⏸️ Тимчасово недоступний')])
        else:
            driver_cabinet_kb.append([types.KeyboardButton(text='▶️ Повернутись до замовлень')])
        driver_cabinet_kb.append([types.KeyboardButton(text='⛔️ Завершити зміну')])
    driver_cabinet_kb.extend([
        [types.KeyboardButton(text='🗓️ Доступні заплановані'), types.KeyboardButton(text='🗓️ Мої заплановані')],
        [types.KeyboardButton(text='⭐ Мої рейтинг та відгуки'), types.KeyboardButton(text='↪️ Історія відмов')],
        [types.KeyboardButton(text='📖 Історія поїздок водія')],
        [types.KeyboardButton(text='🔙 Повернутися в меню')]
    ])
    return types.ReplyKeyboardMarkup(keyboard=driver_cabinet_kb, resize_keyboard=True)

fsm_cancel_kb = [
    [types.KeyboardButton(text='🚫 Скасувати')]
]
fsm_cancel_keyboard = types.ReplyKeyboardMarkup(keyboard=fsm_cancel_kb, resize_keyboard=True, one_time_keyboard=True)

# --- Address Input ---

def build_address_input_keyboard(fav_addresses: list) -> types.ReplyKeyboardMarkup:
    """Формує клавіатуру для першого кроку введення адреси (подача)."""
    kb = []
    if fav_addresses:
        row = []
        for addr in fav_addresses:
            row.append(types.KeyboardButton(text=f"❤️ {addr['name']}"))
            if len(row) == 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)

    kb.extend([
        [types.KeyboardButton(text='📍 Надіслати геолокацію', request_location=True)],
        [types.KeyboardButton(text='✏️ Ввести адресу вручну')],
        [types.KeyboardButton(text='🔙 Повернутися в меню')]
    ])
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def build_destination_address_keyboard(fav_addresses: list) -> types.ReplyKeyboardMarkup:
    """Формує клавіатуру для другого кроку введення адреси (призначення)."""
    kb = []
    if fav_addresses:
        row = []
        for addr in fav_addresses:
            row.append(types.KeyboardButton(text=f"❤️ {addr['name']}"))
            if len(row) == 2: # Keep 2 favorite addresses per row
                kb.append(row)
                row = []
        if row:
            kb.append(row)
    kb.append([types.KeyboardButton(text='✏️ Ввести адресу вручну')])
    kb.append([types.KeyboardButton(text='📍 Уточнити водієві')])
    kb.append([types.KeyboardButton(text='🔙 Повернутися в меню')])
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)