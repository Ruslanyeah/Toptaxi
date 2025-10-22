import aiosqlite
import asyncio
from config.config import DB_PATH
from loguru import logger

async def _execute_script(cursor, script):
    """Executes a multi-statement SQL script."""
    try:
        await cursor.executescript(script)
    except aiosqlite.Error as e:
        logger.error(f"Error executing script: {e}")
        raise

async def _check_and_add_column(cursor, table_name, column_name, column_type):
    """Checks if a column exists in a table and adds it if it doesn't."""
    await cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [info[1] for info in await cursor.fetchall()]
    if column_name not in columns:
        logger.info(f"Column '{column_name}' not found in table '{table_name}'. Adding it...")
        try:
            await cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type};")
            logger.info(f"✅ Column '{column_name}' added successfully.")
        except aiosqlite.Error as e:
            logger.error(f"Failed to add column '{column_name}': {e}")
    else:
        logger.trace(f"Column '{column_name}' already exists in '{table_name}'.")


async def init_db():
    """
    Initializes the database: creates tables if they don't exist
    and runs necessary schema migrations.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.cursor()

            # --- Table Creation Script ---
            # This script will only create tables that do not already exist.
            create_tables_script = """
                CREATE TABLE IF NOT EXISTS clients (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    phone_number TEXT,
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    is_admin INTEGER DEFAULT 0,
                    finish_applic INTEGER DEFAULT 0,
                    cancel_applic INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0,
                    rating_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    phone_number TEXT,
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    is_admin INTEGER DEFAULT 0,
                    finish_applic INTEGER DEFAULT 0,
                    cancel_applic INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0,
                    rating_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS drivers (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    avto_num TEXT,
                    phone_num TEXT,
                    about TEXT,
                    isWorking INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0,
                    rating_count INTEGER DEFAULT 0,
                    cancelled_count INTEGER DEFAULT 0,
                    latitude REAL,
                    longitude REAL,
                    last_location_update TIMESTAMP,
                    shift_started_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    driver_id INTEGER,
                    status TEXT,
                    begin_address TEXT,
                    finish_address TEXT,
                    comment TEXT,
                    client_phone TEXT,
                    latitude REAL,
                    longitude REAL,
                    is_rated INTEGER DEFAULT 0,
                    rating_score INTEGER,
                    rating_comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    order_type TEXT DEFAULT 'taxi',
                    order_details TEXT,
                    scheduled_at TIMESTAMP,
                    reminder_sent INTEGER DEFAULT 0,
                    pending_dispatch_at TIMESTAMP,
                    dispatch_driver_ids TEXT,
                    dispatch_current_driver_index INTEGER,
                    dispatch_offer_sent_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS favorite_addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT,
                    address TEXT,
                    latitude REAL,
                    longitude REAL,
                    UNIQUE(user_id, name)
                );

                CREATE TABLE IF NOT EXISTS client_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    client_id INTEGER,
                    driver_id INTEGER,
                    score INTEGER,
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS driver_rejections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    driver_id INTEGER,
                    rejected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(order_id, driver_id)
                );

                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS dispatch_queue (
                    order_id INTEGER PRIMARY KEY,
                    driver_ids_json TEXT,
                    current_driver_index INTEGER,
                    payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_offer_sent_at TIMESTAMP,
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                );
            """
            await _execute_script(cursor, create_tables_script)
            
            # --- Schema Migrations ---
            # Here we add new columns to existing tables if they are missing.
            # This makes the database update automatically when you add new features.
            logger.info("Checking for necessary database migrations...")
            await _check_and_add_column(cursor, 'orders', 'dispatch_payload', 'TEXT')
            await _check_and_add_column(cursor, 'orders', 'begin_address_voice_id', 'TEXT')
            await _check_and_add_column(cursor, 'orders', 'finish_address_voice_id', 'TEXT')
            await _check_and_add_column(cursor, 'users', 'last_activity', 'TIMESTAMP')
            await _check_and_add_column(cursor, 'clients', 'last_activity', 'TIMESTAMP')
            
            await db.commit()
            logger.info("Database initialization and migration check complete.")

            # --- Index Creation ---
            logger.info("Створення/перевірка індексів...")
            index_script = """
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
                CREATE INDEX IF NOT EXISTS idx_orders_driver_id ON orders(driver_id);
                CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id);
                CREATE INDEX IF NOT EXISTS idx_drivers_isWorking ON drivers(isWorking);
                CREATE INDEX IF NOT EXISTS idx_orders_scheduled_at ON orders(scheduled_at);
            """
            await _execute_script(cursor, index_script)
            await db.commit()
            logger.info("Індекси успішно створені/перевірені.")

    except aiosqlite.Error as e:
        logger.critical(f"Critical database initialization error: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(init_db())
