from aiogram import Router
from . import fsm_edit_driver, fsm_newsletter, fsm_order_management, fsm_user_management

# Этот роутер объединяет все FSM-роутеры админ-панели
router = Router()
router.include_routers(
    fsm_edit_driver.router,
    fsm_newsletter.router,
    fsm_order_management.router,
    fsm_user_management.router
)
