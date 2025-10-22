from aiogram.filters.callback_data import CallbackData
from typing import Optional

# --- Admin Panel Callbacks ---
class KpiPaginator(CallbackData, prefix="kpi_page"):
    page: int

class Paginator(CallbackData, prefix="driver_page"):
    page: int

class DriverProfile(CallbackData, prefix="driver_profile"):
    user_id: int

class WorkingDriversPaginator(CallbackData, prefix="wd_page"):
    page: int

class WorkingDriverProfile(CallbackData, prefix="wd_profile"):
    user_id: int

class AdminDriverAction(CallbackData, prefix="admin_driver"):
    action: str
    user_id: int

class ClientPaginator(CallbackData, prefix="client_page"):
    page: int

class ClientProfile(CallbackData, prefix="client_profile"):
    user_id: int

class AdminClientAction(CallbackData, prefix="admin_client"):
    action: str
    user_id: int

class ClientHistory(CallbackData, prefix="client_history"):
    user_id: int

class ClientHistoryPaginator(CallbackData, prefix="client_hist_page"):
    page: int
    user_id: int

class BannedClientPaginator(CallbackData, prefix="banned_page"):
    page: int

class AdminRequestLocation(CallbackData, prefix="admin_req_loc"):
    user_id: int

class AdminShowLocation(CallbackData, prefix="admin_show_loc"):
    user_id: int

class AdminOrderPaginator(CallbackData, prefix="admin_ord_page"):
    page: int

class AdminOrderDetails(CallbackData, prefix="admin_ord_details"):
    order_id: int

class AdminOrderAction(CallbackData, prefix="admin_ord_action"):
    action: str
    order_id: int

class AdminAction(CallbackData, prefix="admin_action"):
    action: str
    target_id: int | None = None

class AllOrdersPaginator(CallbackData, prefix="all_ord_page"):
    page: int

# --- User Order/Application Callbacks ---
class OrderCallbackData(CallbackData, prefix="order"):
    action: str
    order_id: int

class SaveAddress(CallbackData, prefix="save_addr"):
    type: str
    order_id: int

class RatingCallbackData(CallbackData, prefix="rate"):
    order_id: int
    score: int

class DriverRateClientCallback(CallbackData, prefix="rate_client"):
    order_id: int
    score: int

class TimePickerCallback(CallbackData, prefix="time_pick"):
    action: str  # 'hour' or 'minute'
    value: int


# --- User Cabinet Callbacks ---
class HistoryPaginator(CallbackData, prefix="hist_page"):
    page: int

class TripDetailsCallbackData(CallbackData, prefix="trip_details"):
    order_id: int

class FavAddressManage(CallbackData, prefix="fav_addr_mng"):
    """CallbackData helper for managing favorite addresses.

    Fields:
    - action: operation, e.g. 'add', 'delete_start', 'delete_confirm'
    - address_id: optional id of the favourite address for delete/confirm actions
    """
    action: str
    address_id: int | None = None

# --- Driver Cabinet Callbacks ---
class PreOrderListPaginator(CallbackData, prefix="preorder_list_page"):
    page: int

class PreOrderDetails(CallbackData, prefix="preorder_details"):
    order_id: int

class PreOrderAction(CallbackData, prefix="preorder_action"):
    action: str
    order_id: int

class MyPreordersPaginator(CallbackData, prefix="my_preorder_page"):
    page: int

class MyPreorderAction(CallbackData, prefix="my_preorder_action"):
    action: str # 'details' or 'cancel'
    order_id: int

class DriverReviewsPaginator(CallbackData, prefix="drv_rev_page"):
    page: int

class DriverRejectionPaginator(CallbackData, prefix="drv_rej_page"):
    page: int

class DriverRejectionDetails(CallbackData, prefix="drv_rej_details"):
    order_id: int

class DriverHistoryPaginator(CallbackData, prefix="drv_hist_page"):
    page: int

# --- FSM Address Logic Callbacks ---
class AddressCallbackData(CallbackData, prefix="addr_action"):
    action: str

class ClarifyAddressCallbackData(CallbackData, prefix="clarify_addr"):
    index: int

class ConfirmClarifiedAddress(CallbackData, prefix="confirm_clarified"):
    action: str
    address_type: str

class ConfirmUnfoundAddress(CallbackData, prefix="confirm_unfound"):
    action: str