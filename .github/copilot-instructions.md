# AI Coding Agent Instructions for Nubira Taxi Bot

## Architecture Overview

This is a Telegram taxi booking bot built with aiogram 3.x, SQLite, and AsyncIO. The bot follows a **layered FSM (Finite State Machine) architecture** with clear separation between user flows, admin management, and driver operations.

### Key Components

- **FSM-First Design**: All user interactions use aiogram FSM states (`states/fsm_states.py`). Each flow (taxi orders, pre-orders, delivery, voice orders) has dedicated state classes
- **Router Hierarchy**: Handlers are organized by domain in `handlers/` with specific import order in `handlers/__init__.py:setup_routers()` - FSM handlers have higher priority than generic commands
- **Callback Factories**: All inline keyboards use typed callback data classes from `utils/callback_factories.py` for type safety
- **Database Layer**: All database operations go through `database/queries.py` - never write raw SQL in handlers

## Critical Patterns

### FSM State Management
```python
# Always clear state when starting new flows
await state.clear()
await state.set_state(UserState.locate)

# Use state data for cross-handler communication  
await state.update_data(begin_address="Some street")
data = await state.get_data()
```

### Router Registration Order (CRITICAL)
In `handlers/__init__.py`, router order matters:
1. Specific FSM handlers first (fsm_order, delivery, pre_order)
2. Address logic and finalization handlers
3. General handlers (cabinet, rating)
4. Generic commands (/start) last

### Database Architecture
- **SQLite Database**: Located at `database/taxi_bot.db`
- **Query Layer**: All operations through `database/queries.py` - never write raw SQL in handlers
- **Connection Management**: Uses `aiosqlite` with proper async context managers
- **Auto-migrations**: Schema updates handled automatically in `database/db.py:init_db()`
- **Key Tables**: 
  - `users`/`clients` - User profiles and activity tracking
  - `drivers` - Driver info, location, work status, ratings
  - `orders` - All order types with status tracking and scheduling
  - `favorite_addresses` - User saved locations
  - `client_reviews`/`driver_rejections` - Rating and performance tracking
  - `dispatch_queue` - Order distribution queue management

### Middleware Stack
Applied in `main.py` in specific order:
1. `BanMiddleware` - blocks banned users
2. `LoggingMiddleware` - adds user/chat context to logs
3. `ActivityMiddleware` - tracks user activity

## Development Workflows

### Running the Bot
```bash
python main.py              # Start bot
python stop_bot.py          # Graceful stop
python quick_stop.py        # Force stop
python bot_manager.py stop  # Alternative stop method
```

### Testing
- Integration tests in `tests/` use pytest with aiogram test utilities
- Mock database with `pytest_asyncio` fixtures
- Test FSM flows by simulating message/callback sequences

### Configuration
- Environment variables in `.env` file (see README.md)
- Configuration loaded in `config/config.py` with validation
- Database path: `database/taxi_bot.db`
- Timezone: Europe/Kiev for all operations

## Service Boundaries

### User Flow Types
Each has dedicated FSM states and handlers:
- **Standard Taxi** (`UserState`): Immediate booking with instant driver dispatch
- **Pre-orders** (`PreOrderState`): Scheduled rides with datetime picker - stored in database and activated by scheduler
- **Delivery** (`DeliveryState`): Package/shopping delivery with item details and special handling
- **Voice Orders** (`VoiceOrderState`): Voice-to-text address input for accessibility

### Admin Operations
- Admin panel accessible via `/admin` command 
- Admin IDs configured in `.env` and database `admins` table
- Admin FSM states in `AdminState` for newsletters, user management, driver management
- **Real-time driver tracking**: Admins can view current driver locations and work status
- **Order management**: Full control over order statuses, reassignment, and cancellation
- **Driver status control**: Can activate/deactivate drivers and manage their work shifts

### Driver System
- Driver registration and status management with work shift controls
- Real-time location tracking with coordinate updates
- Queue-based order distribution - orders offered to drivers sequentially until accepted
- Timeout handling for driver responses with automatic failover to next driver
- Rating system with rejection tracking and performance metrics

## Integration Points

### External Services
- **Geopy/Nominatim**: Address geocoding with rate limiting in `utils/geocoder.py`
- **APScheduler**: Background jobs for order scheduling and timeouts
- **Voice Recognition**: Telegram voice message processing (handlers contain voice FSM states)

### Data Flow Patterns
1. **Order Dispatch Queue**: Orders distributed to drivers sequentially in queue order - first available driver gets the order
2. **Pre-order Scheduling**: Scheduled orders stored in database, activated by APScheduler background jobs
3. **Delivery System**: Special order type with item descriptions, shopping lists, and delivery-specific workflows
4. **Address Logic**: Shared geocoding and address input flow via `handlers/user/fsm_address_logic.py`
5. **Rating System**: Bidirectional ratings between clients and drivers after order completion
   - **Client ratings of drivers**: Visible to clients during rating process
   - **Driver ratings of clients**: Hidden from clients - only visible to drivers and admins
   - Client reviews stored in database but not shown to rated clients

## Privacy & Access Control

### Rating System Privacy
- **CRITICAL**: Client ratings of other clients are NEVER shown to the rated client
- Driver ratings and reviews of clients are only accessible to:
  - The rating driver
  - Admin panel users
  - Other drivers (for safety/service quality info)
- Client-facing interfaces should never expose that they are being rated by drivers

### Admin Privileges
- Real-time driver location tracking and monitoring
- Full order lifecycle management (create, modify, cancel, reassign)
- Driver work status control (activate/deactivate, manage shifts)
- Access to all rating data including driver-to-client ratings

## Conventions

### File Organization
- Handlers: `handlers/{domain}/{feature}.py`
- States: All FSM states in single `states/fsm_states.py` file
- Keyboards: Domain-specific keyboard builders in `keyboards/`
- Database: All queries in `database/queries.py`, schema in `database/db.py`

### Error Handling
- Use loguru logger with context (user_id, chat_id automatically added by middleware)
- Graceful degradation - bot continues working even if external services fail
- Database migrations handled automatically in `init_db()`

### Code Style
- Async/await throughout - no blocking operations in handlers
- Type hints with `types.Message`, `FSMContext` parameters
- HTML parse mode for all messages with user data
- Russian language for all user-facing text