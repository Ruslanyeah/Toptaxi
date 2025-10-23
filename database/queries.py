import aiosqlite
from config.config import DB_PATH
from datetime import datetime, timedelta
from loguru import logger
import json
import asyncio

# --- Вспомогательная функция для подключения к БД ---
def _get_db():
    """Возвращает асинхронное подключение к базе данных."""
    return aiosqlite.connect(DB_PATH)

# --- Проверки статуса пользователя ---

async def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def is_driver(user_id: int) -> bool:
    """Проверяет, является ли пользователь зарегистрированным водителем."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT 1 FROM drivers WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None

async def is_user_banned(user_id: int) -> bool:
    """Проверяет, забанен ли пользователь."""
    # В новой схеме таблица 'blacklist' не используется, проверка идет по полю в 'users'
    async with _get_db() as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] == 1 if result else False

# --- Регистрация и обновление пользователей ---

async def add_or_update_user(user_id: int, full_name: str, username: str | None):
    """Добавляет нового пользователя или обновляет информацию о существующем."""
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
    """Обновляет временную метку последней активности пользователя."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET last_activity = ? WHERE user_id = ?", (datetime.now(), user_id))
        await db.commit()

async def update_client_phone(user_id: int, phone_number: str):
    """Обновляет номер телефона клиента."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET phone_number = ? WHERE user_id = ?", (phone_number, user_id))
        await db.commit()

# --- Регистрация и обновление водителей ---

async def register_driver(user_id: int, full_name: str, username: str | None, phone_num: str, avto_num: str):
    """Регистрирует нового водителя."""
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO drivers (user_id, full_name, phone_num, avto_num, created_at, rating, isWorking, is_available)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                phone_num = excluded.phone_num,
                avto_num = excluded.avto_num
            """,
            (user_id, full_name, phone_num, avto_num, datetime.now(), 0.0, 0, 0)
        )
        # Также добавляем/обновляем запись в общей таблице users
        await db.execute(
            """
            INSERT INTO users (user_id, full_name, username, phone_number) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name, username=excluded.username, phone_number=excluded.phone_number
            """,
            (user_id, full_name, username, phone_num)
        )
        await db.commit()

async def update_driver_details(user_id: int, field: str, value: str):
    """Обновляет указанное поле в профиле водителя."""
    async with _get_db() as db:
        # Обновляем в таблице drivers
        await db.execute(f"UPDATE drivers SET {field} = ? WHERE user_id = ?", (value, user_id))
        # Обновляем в таблице users для консистентности
        if field == 'full_name':
            await db.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (value, user_id))
        elif field == 'phone_num':
            await db.execute("UPDATE users SET phone_number = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

async def delete_driver(user_id: int):
    """Удаляет водителя из системы."""
    async with _get_db() as db:
        await db.execute("DELETE FROM drivers WHERE user_id = ?", (user_id,))
        await db.commit()

async def update_driver_location(user_id: int, lat: float, lon: float):
    """Обновляет геолокацию водителя."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE drivers SET latitude = ?, longitude = ?, last_location_update = ? WHERE user_id = ?",
            (lat, lon, datetime.now(), user_id)
        )
        await db.commit()

async def get_driver_location(user_id: int) -> aiosqlite.Row | None:
    """Получает последнюю известную геолокацию водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT latitude, longitude FROM drivers WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

# --- Управление сменой водителя ---

async def start_driver_shift(driver_id: int):
    """Начинает смену для водителя."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE drivers SET isWorking = 1, is_available = 1, shift_started_at = ? WHERE user_id = ?",
            (datetime.now(), driver_id)
        )
        await db.commit()

async def stop_driver_shift(driver_id: int):
    """Завершает смену для водителя."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE drivers SET isWorking = 0, is_available = 0, shift_started_at = NULL WHERE user_id = ?",
            (driver_id,)
        )
        await db.commit()

async def set_driver_availability(driver_id: int, is_available: bool):
    """Устанавливает доступность водителя для приема заказов."""
    async with _get_db() as db:
        await db.execute("UPDATE drivers SET is_available = ? WHERE user_id = ?", (1 if is_available else 0, driver_id))
        await db.commit()

async def is_driver_on_shift(driver_id: int) -> bool:
    """Проверяет, находится ли водитель на смене."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT isWorking FROM drivers WHERE user_id = ?", (driver_id,))
        result = await cursor.fetchone()
        return result[0] == 1 if result else False

# --- Создание и управление заказами ---

async def create_order_in_db(client_id: int, data: dict, initial_status: str) -> int | None:
    """Создает новый заказ в базе данных и возвращает его ID."""
    async with _get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO orders (
                client_id, status, begin_address, finish_address, comment, client_phone,
                latitude, longitude, order_type, order_details, scheduled_at,
                begin_address_voice_id, finish_address_voice_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id, initial_status, data.get('begin_address'), data.get('finish_address'),
                data.get('comment'), data.get('number'), data.get('latitude'), data.get('longitude'),
                data.get('order_type', 'taxi'), data.get('order_details'), data.get('scheduled_at'),
                data.get('begin_address_voice_id'), data.get('finish_address_voice_id')
            )
        )
        await db.commit()
        return cursor.lastrowid

async def update_order_status(order_id: int, status: str):
    """Обновляет статус заказа."""
    async with _get_db() as db:
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        await db.commit()

async def get_order_details(order_id: int) -> aiosqlite.Row | None:
    """Получает детали заказа по ID."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        return await cursor.fetchone()

async def get_full_order_details(order_id: int) -> aiosqlite.Row | None:
    """Получает полную информацию о заказе, включая имена клиента и водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                o.*,
                c.full_name as client_name,
                c.phone_number as client_phone,
                d.full_name as driver_name,
                d.phone_num as driver_phone
            FROM orders o
            LEFT JOIN users c ON o.client_id = c.user_id
            LEFT JOIN drivers d ON o.driver_id = d.user_id
            WHERE o.id = ?
        """, (order_id,))
        return await cursor.fetchone()

async def get_order_client_id(order_id: int) -> int | None:
    """Получает ID клиента по ID заказа."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT client_id FROM orders WHERE id = ?", (order_id,))
        result = await cursor.fetchone()
        return result[0] if result else None

async def get_order_finish_address(order_id: int, user_id: int) -> str | None:
    """Получает адрес назначения из заказа для конкретного пользователя."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT finish_address FROM orders WHERE id = ? AND client_id = ?", (order_id, user_id))
        result = await cursor.fetchone()
        return result[0] if result else None

# --- Диспетчеризация заказов ---

async def get_working_driver_ids(order_id: int, order_lat: float | None, order_lon: float | None, excluded_driver_id: int | None = None) -> list[int]:
    """
    Получает список ID работающих и доступных водителей, отсортированных по близости к заказу.
    Исключает водителей, которые уже отказались от этого заказа.
    """
    async with _get_db() as db:
        # Получаем ID водителей, которые уже отказались
        rejected_cursor = await db.execute("SELECT driver_id FROM driver_rejections WHERE order_id = ?", (order_id,))
        rejected_ids = {row[0] for row in await rejected_cursor.fetchall()}
        if excluded_driver_id:
            rejected_ids.add(excluded_driver_id)

        # Основной запрос
        query = "SELECT user_id, latitude, longitude FROM drivers WHERE isWorking = 1 AND is_available = 1"
        params = []
        if rejected_ids:
            query += f" AND user_id NOT IN ({','.join('?' for _ in rejected_ids)})"
            params.extend(list(rejected_ids))

        cursor = await db.execute(query, params)
        drivers = await cursor.fetchall()

        if not drivers:
            return []

        # Сортировка по расстоянию, если есть координаты заказа
        if order_lat is not None and order_lon is not None:
            drivers.sort(key=lambda d: (
                (d[1] - order_lat)**2 + (d[2] - order_lon)**2) if d[1] is not None and d[2] is not None else float('inf')
            )

        return [d[0] for d in drivers]

async def start_order_dispatch(order_id: int, driver_ids: list[int], payload: str):
    """Начинает процесс диспетчеризации, сохраняя очередь водителей и данные заказа."""
    async with _get_db() as db:
        await db.execute(
            """
            UPDATE orders SET
                dispatch_driver_ids = ?,
                dispatch_current_driver_index = 0,
                dispatch_payload = ?,
                dispatch_offer_sent_at = NULL
            WHERE id = ?
            """,
            (','.join(map(str, driver_ids)), payload, order_id)
        )
        await db.commit()

async def get_dispatch_payload(order_id: int) -> str | None:
    """Получает JSON-строку с данными для диспетчеризации."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT dispatch_payload FROM orders WHERE id = ?", (order_id,))
        result = await cursor.fetchone()
        return result[0] if result else None

async def get_dispatch_info(order_id: int) -> tuple[list[int], int]:
    """Получает очередь водителей и текущий индекс для заказа."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT dispatch_driver_ids, dispatch_current_driver_index FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            return [], 0
        driver_ids = [int(id_str) for id_str in row[0].split(',')]
        current_index = row[1] or 0
        return driver_ids, current_index

async def increment_dispatch_index(order_id: int):
    """Увеличивает индекс текущего водителя в очереди диспетчеризации."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE orders SET dispatch_current_driver_index = dispatch_current_driver_index + 1, dispatch_offer_sent_at = NULL WHERE id = ?",
            (order_id,)
        )
        await db.commit()

async def mark_dispatch_offer_sent(order_id: int):
    """Отмечает время отправки предложения водителю."""
    async with _get_db() as db:
        await db.execute("UPDATE orders SET dispatch_offer_sent_at = ? WHERE id = ?", (datetime.now(), order_id))
        await db.commit()

async def get_stale_and_timed_out_dispatches(timeout_seconds: int) -> list[aiosqlite.Row]:
    """Получает заказы, которые "зависли" в поиске или у которых истек таймаут предложения."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        threshold = datetime.now() - timedelta(seconds=timeout_seconds)
        cursor = await db.execute(
            """
            SELECT * FROM orders
            WHERE status = 'searching' AND (
                (dispatch_offer_sent_at IS NOT NULL AND dispatch_offer_sent_at < ?) OR
                (dispatch_offer_sent_at IS NULL)
            )
            """,
            (threshold,)
        )
        return await cursor.fetchall()

async def accept_order(order_id: int, driver_id: int) -> bool:
    """Принятие заказа водителем. Атомарная операция."""
    async with _get_db() as db:
        # Проверяем, что заказ все еще ищет водителя
        cursor = await db.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
        status = (await cursor.fetchone() or [None])[0]
        if status != 'searching':
            return False

        await db.execute(
            "UPDATE orders SET driver_id = ?, status = 'accepted' WHERE id = ? AND status = 'searching'",
            (driver_id, order_id)
        )
        await db.commit()
        return db.total_changes > 0

async def revert_order_to_searching(order_id: int, driver_id: int) -> bool:
    """Возвращает заказ в поиск, если водитель отменил его после принятия."""
    async with _get_db() as db:
        # Атомарно обновляем статус, только если заказ был принят этим водителем
        await db.execute(
            "UPDATE orders SET status = 'searching', driver_id = NULL WHERE id = ? AND driver_id = ?",
            (order_id, driver_id)
        )
        await db.commit()
        # Записываем отказ
        await record_driver_rejection(order_id, driver_id)
        return db.total_changes > 0

async def finish_order(order_id: int, driver_id: int):
    """Завершает заказ."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE orders SET status = 'completed', completed_at = ? WHERE id = ? AND driver_id = ?",
            (datetime.now(), order_id, driver_id)
        )
        await db.commit()

async def get_current_driver_for_order(order_id: int) -> int | None:
    """Получает ID водителя, которому сейчас предложен заказ."""
    driver_ids, current_index = await get_dispatch_info(order_id)
    if driver_ids and current_index < len(driver_ids):
        return driver_ids[current_index]
    return None

# --- Предварительные заказы ---

async def get_due_scheduled_orders() -> list[aiosqlite.Row]:
    """Получает запланированные заказы, которые пора запускать в работу."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now(TIMEZONE)
        cursor = await db.execute(
            "SELECT * FROM orders WHERE status = 'scheduled' AND scheduled_at <= ?",
            (now.strftime('%Y-%m-%d %H:%M:%S'),)
        )
        return await cursor.fetchall()

async def get_pending_dispatch_orders() -> list[aiosqlite.Row]:
    """Получает заказы, ожидающие повторной попытки найти водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE status = 'pending_dispatch'")
        return await cursor.fetchall()

async def get_preorders_for_reminder(minutes: int) -> list[aiosqlite.Row]:
    """Получает принятые предзаказы, о которых пора напомнить водителю."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now(TIMEZONE)
        reminder_time_limit = now + timedelta(minutes=minutes)
        cursor = await db.execute(
            """
            SELECT * FROM orders
            WHERE status = 'accepted_preorder'
            AND reminder_sent = 0
            AND scheduled_at BETWEEN ? AND ?
            """,
            (now.strftime('%Y-%m-%d %H:%M:%S'), reminder_time_limit.strftime('%Y-%m-%d %H:%M:%S'))
        )
        return await cursor.fetchall()

async def mark_preorder_reminder_sent(order_id: int):
    """Отмечает, что напоминание о предзаказе было отправлено."""
    async with _get_db() as db:
        await db.execute("UPDATE orders SET reminder_sent = 1 WHERE id = ?", (order_id,))
        await db.commit()

async def get_available_preorders_count(min_datetime: str, max_datetime: str) -> int:
    """Считает количество доступных для взятия предзаказов."""
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'scheduled' AND scheduled_at BETWEEN ? AND ?",
            (min_datetime, max_datetime)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_available_preorders_page(limit: int, offset: int, min_datetime: str, max_datetime: str) -> list[aiosqlite.Row]:
    """Получает страницу доступных для взятия предзаказов."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE status = 'scheduled' AND scheduled_at BETWEEN ? AND ? ORDER BY scheduled_at ASC LIMIT ? OFFSET ?",
            (min_datetime, max_datetime, limit, offset)
        )
        return await cursor.fetchall()

async def accept_preorder(order_id: int, driver_id: int):
    """Водитель принимает предзаказ."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE orders SET driver_id = ?, status = 'accepted_preorder' WHERE id = ? AND status = 'scheduled'",
            (driver_id, order_id)
        )
        await db.commit()

async def get_my_preorders_count(driver_id: int) -> int:
    """Считает количество активных предзаказов водителя."""
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE driver_id = ? AND status = 'accepted_preorder'",
            (driver_id,)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_my_preorders_page(limit: int, offset: int, driver_id: int) -> list[aiosqlite.Row]:
    """Получает страницу активных предзаказов водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE driver_id = ? AND status = 'accepted_preorder' ORDER BY scheduled_at ASC LIMIT ? OFFSET ?",
            (driver_id, limit, offset)
        )
        return await cursor.fetchall()

async def cancel_preorder_by_driver(order_id: int, driver_id: int) -> int | None:
    """Водитель отменяет свой предзаказ. Возвращает ID клиента для уведомления."""
    async with _get_db() as db:
        # Получаем ID клиента до изменения
        cursor = await db.execute("SELECT client_id FROM orders WHERE id = ? AND driver_id = ?", (order_id, driver_id))
        client_id_row = await cursor.fetchone()
        if not client_id_row:
            return None

        # Возвращаем заказ в статус 'scheduled'
        await db.execute(
            "UPDATE orders SET driver_id = NULL, status = 'scheduled' WHERE id = ? AND driver_id = ?",
            (order_id, driver_id)
        )
        await db.commit()
        return client_id_row[0] if db.total_changes > 0 else None

# --- Рейтинги и отзывы ---

async def rate_order(order_id: int, score: int, comment: str | None):
    """Сохраняет оценку и комментарий для заказа (от клиента водителю)."""
    async with _get_db() as db:
        await db.execute(
            "UPDATE orders SET is_rated = 1, rating_score = ?, rating_comment = ? WHERE id = ?",
            (score, comment, order_id)
        )
        await db.commit()

async def add_rating_to_driver(driver_id: int, score: int):
    """Обновляет совокупный рейтинг водителя."""
    async with _get_db() as db:
        await db.execute(
            """
            UPDATE drivers SET
                rating = (rating * rating_count + ?) / (rating_count + 1),
                rating_count = rating_count + 1
            WHERE user_id = ?
            """,
            (score, driver_id)
        )
        await db.commit()

async def add_client_review(order_id: int, client_id: int, driver_id: int, score: int, comment: str | None):
    """Сохраняет отзыв водителя о клиенте."""
    async with _get_db() as db:
        await db.execute(
            "INSERT INTO client_reviews (order_id, client_id, driver_id, score, comment) VALUES (?, ?, ?, ?, ?)",
            (order_id, client_id, driver_id, score, comment)
        )
        await db.commit()

async def add_rating_to_client(client_id: int, score: int):
    """Обновляет совокупный рейтинг клиента."""
    async with _get_db() as db:
        await db.execute(
            """
            UPDATE users SET
                rating = (rating * rating_count + ?) / (rating_count + 1),
                rating_count = rating_count + 1
            WHERE user_id = ?
            """,
            (score, client_id)
        )
        await db.commit()

async def get_order_for_rating(order_id: int) -> aiosqlite.Row | None:
    """Получает заказ для проверки, можно ли его оценить."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT is_rated FROM orders WHERE id = ?", (order_id,))
        return await cursor.fetchone()

async def get_client_rating(client_id: int) -> aiosqlite.Row | None:
    """Получает рейтинг клиента."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT rating, rating_count FROM users WHERE user_id = ?", (client_id,))
        return await cursor.fetchone()

async def get_client_reviews_for_driver(client_id: int) -> list[aiosqlite.Row]:
    """Получает последние отзывы о клиенте для показа водителю."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT score, comment FROM client_reviews WHERE client_id = ? ORDER BY created_at DESC LIMIT 3",
            (client_id,)
        )
        return await cursor.fetchall()

# --- Кабинет водителя ---

async def get_driver_cabinet_data(driver_id: int) -> tuple[aiosqlite.Row | None, int]:
    """Получает все необходимые данные для кабинета водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        
        driver_cursor = await db.execute(
            """
            SELECT 
                d.user_id as driver_user_id,
                d.isWorking,
                d.is_available,
                d.shift_started_at,
                COALESCE(d.rating, 0) as rating,
                COALESCE(d.rating_count, 0) as rating_count,
                COALESCE(d.cancelled_count, 0) as cancelled_count,
                (SELECT COUNT(*) FROM orders o WHERE o.driver_id = d.user_id AND o.status = 'completed' AND o.completed_at >= d.shift_started_at) as shift_completed
            FROM drivers d
            WHERE d.user_id = ?
            """,
            (driver_id,)
        )
        driver_data = await driver_cursor.fetchone()

        overall_cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE driver_id = ? AND status = 'completed'",
            (driver_id,)
        )
        overall_completed_row = await overall_cursor.fetchone()
        overall_completed = overall_completed_row[0] if overall_completed_row else 0

        return driver_data, overall_completed

async def get_driver_reviews_count(driver_id: int) -> int:
    """Считает количество отзывов с комментариями для водителя."""
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE driver_id = ? AND rating_comment IS NOT NULL AND rating_comment != ''",
            (driver_id,)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_driver_reviews_page(limit: int, offset: int, driver_id: int) -> list[aiosqlite.Row]:
    """Получает страницу отзывов с комментариями для водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT completed_at, rating_score, rating_comment FROM orders WHERE driver_id = ? AND rating_comment IS NOT NULL AND rating_comment != '' ORDER BY completed_at DESC LIMIT ? OFFSET ?",
            (driver_id, limit, offset)
        )
        return await cursor.fetchall()

# --- История отказов и поездок водителя ---

async def record_driver_rejection(order_id: int, driver_id: int):
    """Записывает отказ водителя от заказа."""
    async with _get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO driver_rejections (order_id, driver_id) VALUES (?, ?)",
            (order_id, driver_id)
        )
        # Увеличиваем счетчик отмен у водителя
        await db.execute("UPDATE drivers SET cancelled_count = cancelled_count + 1 WHERE user_id = ?", (driver_id,))
        await db.commit()

async def get_driver_rejections_count(driver_id: int) -> int:
    """Считает количество отказов для водителя."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM driver_rejections WHERE driver_id = ?", (driver_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_driver_rejections_page(limit: int, offset: int, driver_id: int) -> list[aiosqlite.Row]:
    """Получает страницу истории отказов водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT dr.order_id, dr.rejected_at, u.full_name as client_name
            FROM driver_rejections dr
            JOIN orders o ON dr.order_id = o.id
            JOIN users u ON o.client_id = u.user_id
            WHERE dr.driver_id = ?
            ORDER BY dr.rejected_at DESC LIMIT ? OFFSET ?
            """,
            (driver_id, limit, offset)
        )
        return await cursor.fetchall()

async def get_rejected_order_details_for_driver(order_id: int, driver_id: int) -> aiosqlite.Row | None:
    """Получает детали заказа, от которого отказался водитель."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT o.created_at, o.begin_address, o.finish_address, o.client_id
            FROM orders o
            JOIN driver_rejections dr ON o.id = dr.order_id
            WHERE o.id = ? AND dr.driver_id = ?
            """,
            (order_id, driver_id)
        )
        return await cursor.fetchone()

async def get_driver_orders_count(driver_id: int) -> int:
    """Считает количество завершенных поездок водителя."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE driver_id = ? AND status = 'completed'", (driver_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_driver_orders_page(limit: int, offset: int, driver_id: int) -> list[aiosqlite.Row]:
    """Получает страницу истории поездок водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, created_at FROM orders WHERE driver_id = ? AND status = 'completed' ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (driver_id, limit, offset)
        )
        return await cursor.fetchall()

async def get_driver_trip_details(order_id: int, driver_id: int) -> aiosqlite.Row | None:
    """Получает детали завершенной поездки для водителя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                o.created_at, o.begin_address, o.finish_address, o.is_rated, o.rating_score,
                u.full_name as client_name, u.phone_number as client_phone
            FROM orders o
            JOIN users u ON o.client_id = u.user_id
            WHERE o.id = ? AND o.driver_id = ?
            """,
            (order_id, driver_id)
        )
        return await cursor.fetchone()

# --- Кабинет клиента ---

async def get_client_stats(user_id: int) -> aiosqlite.Row | None:
    """Получает статистику поездок для клиента."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT finish_applic, cancel_applic FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()

async def increment_client_finish_count(client_id: int):
    """Увеличивает счетчик успешных поездок клиента."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET finish_applic = finish_applic + 1 WHERE user_id = ?", (client_id,))
        await db.commit()

async def get_user_orders_count(user_id: int) -> int:
    """Считает количество завершенных поездок клиента."""
    return await get_driver_orders_count(user_id) # Логика та же, но для client_id

async def get_user_orders_page(limit: int, offset: int, user_id: int) -> list[aiosqlite.Row]:
    """Получает страницу истории поездок клиента."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, created_at FROM orders WHERE client_id = ? AND status = 'completed' ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        )
        return await cursor.fetchall()

async def get_trip_details(order_id: int, user_id: int) -> aiosqlite.Row | None:
    """Получает детали поездки для клиента."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                o.id, o.created_at, o.begin_address, o.finish_address, o.is_rated, o.rating_score,
                d.full_name as driver_name, d.avto_num, d.phone_num as driver_phone
            FROM orders o
            LEFT JOIN drivers d ON o.driver_id = d.user_id
            WHERE o.id = ? AND o.client_id = ?
            """,
            (order_id, user_id)
        )
        return await cursor.fetchone()

# --- Избранные адреса ---

async def get_user_fav_addresses(user_id: int) -> list[aiosqlite.Row]:
    """Получает список избранных адресов пользователя."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, name, address FROM favorite_addresses WHERE user_id = ? ORDER BY name", (user_id,))
        return await cursor.fetchall()

async def get_fav_address_by_name(user_id: int, name: str) -> tuple | None:
    """Получает избранный адрес по имени."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT address, latitude, longitude FROM favorite_addresses WHERE user_id = ? AND name = ?", (user_id, name))
        return await cursor.fetchone()

async def add_fav_address(user_id: int, name: str, address: str, lat: float | None, lon: float | None):
    """Добавляет новый избранный адрес."""
    async with _get_db() as db:
        await db.execute(
            "INSERT INTO favorite_addresses (user_id, name, address, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, address, lat, lon)
        )
        await db.commit()

async def delete_fav_address(address_id: int, user_id: int):
    """Удаляет избранный адрес."""
    async with _get_db() as db:
        await db.execute("DELETE FROM favorite_addresses WHERE id = ? AND user_id = ?", (address_id, user_id))
        await db.commit()

# --- Админ-панель ---

async def get_all_admins() -> list[aiosqlite.Row]:
    """Получает всех администраторов из базы данных."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT u.user_id, u.full_name FROM admins a JOIN users u ON a.user_id = u.user_id")
        return await cursor.fetchall()

async def add_admin(user_id: int):
    """Добавляет пользователя в администраторы."""
    async with _get_db() as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        await db.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def remove_admin(user_id: int):
    """Удаляет пользователя из администраторов."""
    async with _get_db() as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id,))
        await db.commit()

async def ban_user(user_id: int):
    """Блокирует пользователя."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def unban_user(user_id: int):
    """Разблокирует пользователя."""
    async with _get_db() as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_main_stats() -> dict:
    """Получает основную статистику для админ-панели."""
    async with _get_db() as db:
        total_drivers_c = await db.execute("SELECT COUNT(*) FROM drivers")
        working_drivers_c = await db.execute("SELECT COUNT(*) FROM drivers WHERE isWorking = 1")
        total_clients_c = await db.execute("SELECT COUNT(*) FROM users")
        active_orders_c = await db.execute("SELECT COUNT(*) FROM orders WHERE status NOT IN ('completed', 'cancelled_by_user', 'cancelled_no_drivers', 'cancelled_by_admin')")
        completed_orders_c = await db.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
        
        return {
            'total_drivers': (await total_drivers_c.fetchone() or [0])[0],
            'working_drivers': (await working_drivers_c.fetchone() or [0])[0],
            'total_clients': (await total_clients_c.fetchone() or [0])[0],
            'active_orders': (await active_orders_c.fetchone() or [0])[0],
            'completed_orders': (await completed_orders_c.fetchone() or [0])[0],
        }

async def get_drivers_count(is_working: bool | None = None) -> int:
    """Считает количество водителей по статусу."""
    query = "SELECT COUNT(*) FROM drivers"
    params = []
    if is_working is not None:
        query += " WHERE isWorking = ?"
        params.append(1 if is_working else 0)
    
    async with _get_db() as db:
        cursor = await db.execute(query, params)
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_drivers_page(limit: int, offset: int, is_working: bool | None = None) -> list[aiosqlite.Row]:
    """Получает страницу со списком водителей."""
    query = "SELECT user_id, full_name FROM drivers"
    params = []
    if is_working is not None:
        query += " WHERE isWorking = ?"
        params.append(1 if is_working else 0)
    query += " ORDER BY full_name LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        return await cursor.fetchall()

async def get_driver_details(user_id: int) -> aiosqlite.Row | None:
    """Получает детальную информацию о водителе для админ-панели."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT d.user_id, d.full_name, u.username, d.phone_num, d.avto_num, d.isWorking, d.rating
            FROM drivers d
            LEFT JOIN users u ON d.user_id = u.user_id
            WHERE d.user_id = ?
            """,
            (user_id,)
        )
        return await cursor.fetchone()

async def get_clients_count(search_query: str | None = None) -> int:
    """Считает количество клиентов, опционально с поиском."""
    query = "SELECT COUNT(*) FROM users"
    params = []
    if search_query:
        query += " WHERE full_name LIKE ? OR username LIKE ? OR phone_number LIKE ?"
        params.extend([f'%{search_query}%'] * 3)

    async with _get_db() as db:
        cursor = await db.execute(query, params)
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_clients_page(limit: int, offset: int, search_query: str | None = None) -> list[aiosqlite.Row]:
    """Получает страницу со списком клиентов, опционально с поиском."""
    query = "SELECT user_id, full_name FROM users"
    params = []
    if search_query:
        query += " WHERE full_name LIKE ? OR username LIKE ? OR phone_number LIKE ?"
        params.extend([f'%{search_query}%'] * 3)
    query += " ORDER BY last_activity DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        return await cursor.fetchall()

async def get_client_details(user_id: int) -> aiosqlite.Row | None:
    """Получает детальную информацию о клиенте для админ-панели."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, full_name, username, phone_number FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()

async def get_client_name(user_id: int) -> str | None:
    """Получает имя клиента по ID."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else None

async def get_orders_count_by_status(status: str) -> int:
    """Считает количество заказов по статусу."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (status,))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_orders_page_by_status(status: str, limit: int, offset: int) -> list[aiosqlite.Row]:
    """Получает страницу заказов по статусу."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT o.id, o.created_at, u.full_name as client_name
            FROM orders o
            JOIN users u ON o.client_id = u.user_id
            WHERE o.status = ? ORDER BY o.created_at DESC LIMIT ? OFFSET ?
            """,
            (status, limit, offset)
        )
        return await cursor.fetchall()

async def get_driver_info_for_client(driver_id: int) -> aiosqlite.Row | None:
    """Получает информацию о водителе для показа клиенту."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT full_name, avto_num, phone_num, rating FROM drivers WHERE user_id = ?",
            (driver_id,)
        )
        return await cursor.fetchone()

async def get_full_user_info(user_id: int) -> tuple:
    """Возвращает полную информацию о пользователе (клиент/водитель)."""
    # Эта функция-заглушка, ее нужно будет реализовать
    return f"User Info for {user_id}", False, False, False, False, False

async def get_all_orders_count_by_client(client_id: int) -> int:
    """Считает все заказы клиента."""
    async with _get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE client_id = ?", (client_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_all_orders_page_by_client(client_id: int, limit: int, offset: int) -> list[aiosqlite.Row]:
    """Получает страницу всех заказов клиента."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, created_at, status FROM orders WHERE client_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (client_id, limit, offset)
        )
        return await cursor.fetchall()

