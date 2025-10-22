from aiogram.fsm.state import StatesGroup, State

class UserState(StatesGroup):
    """States for the regular user order process."""
    # Address-related states
    locate = State()
    begin_address = State()
    begin_address_voice = State()
    finish_address = State()
    clarify_begin_address = State()
    finish_address_voice = State()
    clarify_finish_address = State()
    confirm_unfound_address = State()
    
    # Order-specific states
    number = State()
    comment = State()
    confirm_order = State()

class PreOrderState(StatesGroup):
    """States for the pre-order (scheduled order) process."""
    # Pre-order specific states
    get_datetime = State()
    get_hour = State()
    get_minute = State()
    
    # Address-related states
    locate = State()
    begin_address = State()
    begin_address_voice = State()
    finish_address = State()
    clarify_begin_address = State()
    finish_address_voice = State()
    clarify_finish_address = State()
    confirm_unfound_address = State()

    # Order-specific states
    number = State()
    comment = State()
    confirm_preorder = State()

class AdminState(StatesGroup):
    """States for various admin panel FSMs."""
    # Newsletter
    newsletter_message = State()
    newsletter_audience = State()
    newsletter_confirm = State()
    # Custom stats
    get_custom_date_range = State()
    # Add driver
    add_driver_id = State()
    get_admin_id_to_add = State()
    add_driver_fullname = State()
    add_driver_avto_num = State()
    add_driver_phone_num = State()
    add_driver_about = State()
    add_driver_confirm = State()
    # Edit driver
    edit_driver_fullname = State()
    edit_driver_avto_num = State()
    edit_driver_phone_num = State()
    # User management
    get_client_search_query = State()
    get_ban_reason = State()
    get_message_to_user = State()
    get_user_id_for_info = State()
    # Order management
    get_driver_id_for_reassign = State()
    get_client_id_for_order_search = State()
    get_order_id_for_search = State()

class DriverState(StatesGroup):
    """States for the driver cabinet."""
    waiting_for_location = State()

class FavAddressState(StatesGroup):
    """States for adding/editing a favorite address."""
    get_address = State()
    get_name = State()

class RatingState(StatesGroup):
    """Unified state for rating a user (client or driver)."""
    get_comment = State()

class DeliveryState(StatesGroup):
    """States for the delivery order process."""
    # Delivery-specific states
    get_type = State()
    get_shopping_list = State()
    get_parcel_description = State()
    
    # Address-related states
    locate = State()
    begin_address = State()
    begin_address_voice = State()
    finish_address = State()
    clarify_begin_address = State()
    finish_address_voice = State()
    clarify_finish_address = State()
    confirm_unfound_address = State()
    
    # A special state to transition from address logic within delivery FSM
    address_input_completed = State()

    # Order-specific states
    get_phone = State()
    get_comment = State()
    confirm_delivery = State()

class VoiceOrderState(StatesGroup):
    """States for the voice-only order process."""
    get_voice = State()
    get_location = State()
    get_number = State()