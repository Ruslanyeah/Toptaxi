# This file makes the 'handlers' directory a Python package.
from aiogram import Router


def setup_routers():
    """
    Creates and configures all routers for the application.
    This function imports and initializes routers locally to ensure they are clean for each call,
    which is crucial for isolated testing.

    Возвращает три роутера:
    1. main_router: для всех пользовательских и FSM обработчиков.
    2. admin_root_router: для административных обработчиков.
    3. error_router: для обработки ошибок.
    """
    # Local imports to avoid global state issues during testing
    from . import admin_main
    from .admin import admin_router
    from .user import (
        main_user_handler, cabinet, application, fsm_fav_address, fsm_address_logic,
        delivery, pre_order, order_actions, order_finalization, fsm_order, fsm_voice_order,
        rating, error_handler
    )
    from . import driver_cabinet
    from .driver_cabinet import IsDriver

    # 1. Setup Admin Router
    # admin_main.router уже содержит в себе все необходимые FSM-роутеры.
    # Нам просто нужно его вернуть.
    admin_root_router = admin_main.router

    # 2. Setup User Routers
    main_router = Router()
    
    # Include all user-facing routers in a logical order
    main_router.include_routers(
        # 1. FSM Entry points by specific text commands. This is the highest priority.
        fsm_order.router,
        delivery.router,
        pre_order.router,
        fsm_voice_order.router,
        
        # 2. Logic inside FSMs (address input, finalization, etc.)
        fsm_address_logic.router,
        fsm_fav_address.router,
        order_finalization.router,
        order_actions.router,
        
        # 3. General purpose handlers (cabinets, rating, etc.)
        cabinet.router,
        driver_cabinet.router,
        rating.router,
        application.router,
        
        # 4. Generic commands (/start, back to menu) must be last.
        main_user_handler.router,
    )
    
    # 3. Return the configured routers
    return main_router, admin_root_router, error_handler.router