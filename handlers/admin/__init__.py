from aiogram import Router

from .fsm_edit_driver import router as edit_driver_router
from .fsm_newsletter import router as newsletter_router
from .fsm_order_management import router as order_management_router
from .fsm_user_management import router as user_management_router
from .fsm_admin_management import router as admin_management_router

admin_router = Router()

admin_router.include_routers(
    edit_driver_router,
    newsletter_router,
    order_management_router,
    user_management_router,
    admin_management_router,
)