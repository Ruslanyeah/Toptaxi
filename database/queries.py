import aiosqlite
from config.config import DB_PATH
from datetime import datetime, timedelta
from loguru import logger
import json
import asyncio

# --- Connection Helper ---
def _get_db():
    return aiosqlite.connect(DB_PATH)

# --- User & Driver Checks ---

async def is_admin(user_id: int) -> bool:
    """Checks if a user has admin privileges."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def is_driver(user_id: int) -> bool:
    """Checks if a user is a registered driver."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT 1 FROM drivers WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def is_user_banned(user_id: int) -> bool:
    """Checks if a user is banned."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

# --- User Registration & Updates ---

async def add_or_update_user(user_id: int, full_name: str, username: str | None):
    """Adds a new user or updates an existing one's info."""
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO users (user_id, full_name, username, created_at, last_activity)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                username = excluded.username,
                last_activity = excluded.last_activity
            """,
            (user_id, full_name, username, datetime.now(), datetime.now())
        )
        await db.commit()

async def update_user_activity(user_id: int):
    """Updates the last_activity timestamp for a user."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET last_activity = ? WHERE user_id = ?", (datetime.now(), user_id))
        await db.commit()

async def update_client_phone(user_id: int, phone_number: str):
    """Updates the phone number for a client."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET phone_number = ? WHERE user_id = ?", (phone_number, user_id))
        await db.commit()

# --- Admin Management ---

async def get_all_admins():
    """Retrieves all admins from the database."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT u.user_id, u.full_name FROM admins a JOIN users u ON a.user_id = u.user_id")
        return await cursor.fetchall()

async def add_admin(user_id: int):
    """Adds a user to the admins table."""
    async with _get_db() as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def remove_admin(user_id: int):
    """Removes a user from the admins table."""
    async with _get_db() as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()

# --- Ban Management ---

async def ban_user(user_id: int, reason: str | None = "No reason provided"):
    """Adds a user to the blacklist."""
    async with _get_db() as db:
        await db.execute(
            "INSERT INTO blacklist (user_id, reason, banned_at) VALUES (?, ?, ?)",
            (user_id, reason, datetime.now())
        )
        await db.commit()

async def unban_user(user_id: int):
    """Removes a user from the blacklist."""
    async with _get_db() as db:
        await db.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
        await db.commit()

# --- Driver Management ---

async def get_working_driver_ids(order_id: int, order_lat: float | None, order_lon: float | None, excluded_driver_id: int | None = None) -> list[int]:
    """
    Gets a list of working, available driver IDs, optionally sorted by proximity.
    """
    async with _get_db() as db:
        query = """
            SELECT user_id, last_lat, last_lon FROM drivers 
            WHERE is_working = 1 AND is_available = 1
        """
        params = []
        if excluded_driver_id:
            query += " AND user_id != ?"
            params.append(excluded_driver_id)
        
        cursor = await db.execute(query, params)
        drivers = await cursor.fetchall()

        if not drivers:
            return []

        # If order has coordinates, sort drivers by distance
        if order_lat is not None and order_lon is not None:
            drivers_with_distance = []
            for driver_id, lat, lon in drivers:
                if lat is not None and lon is not None:
                    # Simple squared Euclidean distance for sorting (faster than sqrt)
                    distance_sq = (lat - order_lat)**2 + (lon - order_lon)**2
                    drivers_with_distance.append((driver_id, distance_sq))
            
            # Sort by distance (ascending)
            drivers_with_distance.sort(key=lambda x: x[1])
            return [driver[0] for driver in drivers_with_distance]
        else:
            # If no coordinates, return as is
            return [driver[0] for driver in drivers]

async def start_driver_shift(driver_id: int):
    """Starts a driver's shift."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE drivers SET is_working = 1, is_available = 1, shift_started_at = ? WHERE user_id = ?",
            (datetime.now(), driver_id)
        )
        await db.commit()

async def stop_driver_shift(driver_id: int):
    """Stops a driver's shift."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE drivers SET is_working = 0, is_available = 0, shift_started_at = NULL, last_lat = NULL, last_lon = NULL WHERE user_id = ?",
            (driver_id,)
        )
        await db.commit()

async def set_driver_availability(driver_id: int, is_available: bool):
    """Sets a driver's availability status."""
    async with _get_db() as db:
        await db.execute("UPDATE drivers SET is_available = ? WHERE user_id = ?", (1 if is_available else 0, driver_id))
        await db.commit()

async def update_driver_location(driver_id: int, lat: float, lon: float):
    """Updates a driver's last known location."""
    async with _get_db() as db:
        await db.execute("UPDATE drivers SET last_lat = ?, last_lon = ? WHERE user_id = ?", (lat, lon, driver_id))
        await db.commit()

async def is_driver_on_shift(driver_id: int) -> bool:
    """Checks if a driver is currently on shift."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT 1 FROM drivers WHERE user_id = ? AND is_working = 1", (driver_id,))
        return await cursor.fetchone() is not None

# --- Order Management ---

async def create_order(client_id: int, data: dict) -> int:
    """Creates a new order in the database and returns its ID."""
    async with _get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO orders (client_id, begin_address, finish_address, comment, phone_number, 
                                latitude, longitude, status, created_at, order_type, order_details,
                                begin_address_voice_id, finish_address_voice_id, comment_voice_id, scheduled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_creation', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                data.get('begin_address'),
                data.get('finish_address'),
                data.get('comment'),
                data.get('number'),
                data.get('latitude'),
                data.get('longitude'),
                datetime.now(),
                data.get('order_type', 'taxi'),
                data.get('order_details'),
                data.get('begin_address_voice_id'),
                data.get('finish_address_voice_id'),
                data.get('comment_voice_id'),
                data.get('scheduled_at')
            )
        )
        await db.commit()
        return cursor.lastrowid

async def update_order_status(order_id: int, status: str):
    """Updates the status of an order."""
    async with _get_db() as db:
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        await db.commit()

async def get_order_details(order_id: int) -> aiosqlite.Row | None:
    """Gets details for a specific order."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        return await cursor.fetchone()

async def accept_order(order_id: int, driver_id: int) -> bool:
    """
    Atomically marks an order as accepted by a driver if it's currently being searched for.
    Returns True on success, False if the order was already taken or cancelled.
    """
    async with _get_db() as db:
        cursor = await db.execute(
            "UPDATE orders SET driver_id = ?, status = 'accepted', accepted_at = ? WHERE id = ? AND status = 'searching'",
            (driver_id, datetime.now(), order_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def get_current_driver_for_order(order_id: int) -> int | None:
    """
    Gets the user_id of the driver currently being offered the order.
    This is calculated based on the current_driver_index in the dispatch_queue.
    """
    async with _get_db() as db:
        # First, get the JSON list of driver IDs and the current index
        cursor = await db.execute(
            "SELECT driver_ids_json, current_driver_index FROM dispatch_queue WHERE order_id = ?",
            (order_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        driver_ids_json, current_index = row
        driver_ids = json.loads(driver_ids_json)

        if 0 <= current_index < len(driver_ids):
            return driver_ids[current_index]
        else:
            return None

async def record_driver_rejection(order_id: int, driver_id: int):
    """
    Records that a driver has rejected a specific order.
    """
    async with _get_db() as db:
        await db.execute(
            "INSERT INTO order_rejections (order_id, driver_id, rejected_at) VALUES (?, ?, ?)",
            (order_id, driver_id, datetime.now())
        )
        await db.commit()


async def cancel_order_by_user(order_id: int, user_id: int):
    """Marks an order as cancelled by the user."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE orders SET status = 'cancelled_by_user' WHERE id = ? AND client_id = ?",
            (order_id, user_id)
        )
        await db.commit()

async def complete_order(order_id: int, driver_id: int):
    """Marks an order as completed."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE orders SET status = 'completed', completed_at = ? WHERE id = ? AND driver_id = ?",
            (datetime.now(), order_id, driver_id)
        )
        await db.commit()

# --- Dispatch Logic ---

async def start_order_dispatch(order_id: int, driver_ids: list[int], payload: str):
    """Initializes the dispatch process for an order."""
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO dispatch_queue (order_id, driver_ids_json, current_driver_index, created_at, payload_json)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                driver_ids_json = excluded.driver_ids_json,
                current_driver_index = 0,
                created_at = excluded.created_at,
                payload_json = excluded.payload_json
            """,
            (order_id, json.dumps(driver_ids), datetime.now(), payload)
        )
        await db.commit()

async def get_dispatch_info(order_id: int) -> tuple[list[int] | None, int | None]:
    """Gets the driver list and current index for a dispatch."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT driver_ids_json, current_driver_index FROM dispatch_queue WHERE order_id = ?", (order_id,))
        row = await cursor.fetchone()
        if row:
            return json.loads(row[0]), row[1]
        return None, None

async def get_dispatch_payload(order_id: int) -> str | None:
    """Gets the JSON payload for a dispatch."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT payload_json FROM dispatch_queue WHERE order_id = ?", (order_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def increment_dispatch_index(order_id: int):
    """Increments the driver index for a dispatch."""
    async with _get_db() as db:
        await db.execute("UPDATE dispatch_queue SET current_driver_index = current_driver_index + 1 WHERE order_id = ?", (order_id,))
        await db.commit()

async def mark_dispatch_offer_sent(order_id: int):
    """Updates the timestamp for the last offer sent."""
    async with _get_db() as db:
        await db.execute("UPDATE dispatch_queue SET last_offer_sent_at = ? WHERE order_id = ?", (datetime.now(), order_id))
        await db.commit()

async def remove_from_dispatch_queue(order_id: int):
    """Removes an order from the dispatch queue."""
    async with _get_db() as db:
        await db.execute("DELETE FROM dispatch_queue WHERE order_id = ?", (order_id,))
        await db.commit()

# --- Scheduler Queries ---

async def get_stale_and_timed_out_dispatches(timeout_seconds: int) -> list[aiosqlite.Row]:
    """
    Gets dispatches that have timed out waiting for a driver to accept,
    or are 'stale' (stuck in the queue after a restart without an offer being sent).
    """
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        timeout_moment = datetime.now() - timedelta(seconds=timeout_seconds)
        cursor = await db.execute(
            """
            SELECT * FROM dispatch_queue 
            WHERE 
                -- Offer was sent and has expired
                (last_offer_sent_at IS NOT NULL AND last_offer_sent_at < ?)
                OR 
                -- Offer was never sent (stale) and the dispatch is old
                (last_offer_sent_at IS NULL AND created_at < ?)
            """,
            (timeout_moment, timeout_moment)
        )
        return await cursor.fetchall()

async def get_orders_to_start_dispatch() -> list[aiosqlite.Row]:
    """Gets scheduled orders that are due to start dispatch."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now()
        cursor = await db.execute(
            "SELECT * FROM orders WHERE status = 'scheduled' AND scheduled_at <= ?",
            (now,)
        )
        return await cursor.fetchall()

# --- Favorite Addresses ---

async def get_user_fav_addresses(user_id: int) -> list[aiosqlite.Row]:
    """Gets a user's favorite addresses."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, name, address FROM favorite_addresses WHERE user_id = ? ORDER BY name", (user_id,))
        return await cursor.fetchall()

async def get_fav_address_by_name(user_id: int, name: str) -> tuple | None:
    """Gets a specific favorite address by its name."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT address, latitude, longitude FROM favorite_addresses WHERE user_id = ? AND name = ?", (user_id, name))
        return await cursor.fetchone()

async def add_favorite_address(user_id: int, name: str, address: str, latitude: float | None, longitude: float | None) -> bool:
    """Adds a new favorite address for a user."""
    async with _get_db() as db:
        try:
            await db.execute(
                "INSERT INTO favorite_addresses (user_id, name, address, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, address, latitude, longitude)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"User {user_id} tried to add a favorite address with a duplicate name '{name}'.")
            return False

async def delete_fav_address(address_id: int, user_id: int):
    """Deletes a favorite address."""
    async with _get_db() as db:
        await db.execute("DELETE FROM favorite_addresses WHERE id = ? AND user_id = ?", (address_id, user_id))
        await db.commit()

# --- Rating ---

async def save_rating(order_id: int, rater_id: int, rated_id: int, score: int, comment: str | None):
    """Saves a rating for an order."""
    async with _get_db() as db:
        await db.execute(
            "INSERT INTO ratings (order_id, rater_user_id, rated_user_id, score, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, rater_id, rated_id, score, comment, datetime.now())
        )
        await db.execute("UPDATE orders SET is_rated = 1 WHERE id = ?", (order_id,))
        await db.commit()

async def get_client_rating(client_id: int) -> aiosqlite.Row | None:
    """Gets a client's average rating and count."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT AVG(score) as rating, COUNT(score) as rating_count FROM ratings WHERE rated_user_id = ?",
            (client_id,)
        )
        return await cursor.fetchone()

# --- Stats & Details for Admin/Cabinet ---

async def get_main_stats() -> dict:
    """Gets main statistics for the admin panel."""
    async with _get_db() as db:
        cursors = await asyncio.gather(
            db.execute("SELECT COUNT(*) FROM drivers"),
            db.execute("SELECT COUNT(*) FROM drivers WHERE is_working = 1"),
            db.execute("SELECT COUNT(*) FROM users"),
            db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('searching', 'accepted', 'in_progress')"),
            db.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
        )
        results = [await c.fetchone() for c in cursors]
        return {
            'total_drivers': results[0][0],
            'working_drivers': results[1][0],
            'total_clients': results[2][0],
            'active_orders': results[3][0],
            'completed_orders': results[4][0]
        }

async def get_client_stats(user_id: int) -> aiosqlite.Row | None:
    """Gets statistics for a specific client."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT 
                (SELECT COUNT(*) FROM orders WHERE client_id = ? AND status = 'completed') as finish_applic,
                (SELECT COUNT(*) FROM orders WHERE client_id = ? AND status LIKE 'cancelled%') as cancel_applic
            """,
            (user_id, user_id)
        )
        return await cursor.fetchone()

async def get_user_orders_count(user_id: int) -> int:
    """Gets the total count of a user's completed orders."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE client_id = ? AND status = 'completed'", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_user_orders_page(user_id: int, limit: int, offset: int) -> list[aiosqlite.Row]:
    """Gets a paginated list of a user's completed orders."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, created_at FROM orders WHERE client_id = ? AND status = 'completed' ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        )
        return await cursor.fetchall()

async def get_trip_details(order_id: int, user_id: int) -> aiosqlite.Row | None:
    """Gets detailed information about a past trip for a user."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT 
                o.id, o.created_at, o.begin_address, o.finish_address, o.is_rated,
                d.full_name as driver_name, d.avto_num, d.phone_num as driver_phone,
                r.score as rating_score
            FROM orders o
            LEFT JOIN drivers d ON o.driver_id = d.user_id
            LEFT JOIN ratings r ON o.id = r.order_id AND r.rater_user_id = o.client_id
            WHERE o.id = ? AND o.client_id = ?
            """,
            (order_id, user_id)
        )
        return await cursor.fetchone()

async def get_driver_details(driver_id: int) -> aiosqlite.Row | None:
    """Gets detailed information about a driver for the admin panel."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT 
                d.user_id, u.full_name, u.username, d.phone_num, d.avto_num, d.is_working, d.created_at,
                COALESCE(AVG(r.score), 0) as rating,
                COUNT(r.score) as rating_count,
                (SELECT COUNT(*) FROM orders WHERE driver_id = d.user_id AND status = 'completed') as completed_orders
            FROM drivers d
            JOIN users u ON d.user_id = u.user_id
            LEFT JOIN ratings r ON d.user_id = r.rated_user_id
            WHERE d.user_id = ?
            GROUP BY d.user_id
            """,
            (driver_id,)
        )
        return await cursor.fetchone()

async def get_client_details(user_id: int) -> aiosqlite.Row | None:
    """Gets detailed information about a client for the admin panel."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT 
                u.user_id, u.full_name, u.username, u.phone_number as phone_num, u.created_at,
                COALESCE(AVG(r.score), 0) as rating,
                COUNT(r.score) as rating_count,
                (SELECT COUNT(*) FROM orders WHERE client_id = u.user_id AND status = 'completed') as completed_orders
            FROM users u
            LEFT JOIN ratings r ON u.user_id = r.rated_user_id
            WHERE u.user_id = ?
            GROUP BY u.user_id
            """,
            (user_id,)
        )
        return await cursor.fetchone()

async def update_driver_field(driver_id: int, field: str, value: str):
    """Updates a specific field for a driver."""
    # A whitelist of allowed fields to prevent SQL injection
    allowed_fields = ['full_name', 'avto_num', 'phone_num']
    if field not in allowed_fields:
        raise ValueError(f"Invalid field name: {field}")
    
    # For 'full_name', we need to update the 'users' table
    if field == 'full_name':
        table = 'users'
    else:
        table = 'drivers'

    async with _get_db() as db:
        # The field name is sanitized by the whitelist check
        query = f"UPDATE {table} SET {field} = ? WHERE user_id = ?"
        await db.execute(query, (value, driver_id))
        await db.commit()
