import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from pathlib import Path

load_dotenv()

# --- Base Directory ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Telegram Bot ---
TOKEN = os.getenv('TELEGRAM_TOKEN')

# --- Валидация критично важливих змінних ---
if not TOKEN:
    raise ValueError("Необхідно встановити TELEGRAM_TOKEN в .env файлі")

ADMIN_IDS_STR = os.getenv('ADMIN_IDS')
if not ADMIN_IDS_STR:
    raise ValueError("Необхідно встановити ADMIN_IDS в .env файлі")

ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]

# --- Database ---
DB_PATH = BASE_DIR / 'database' / 'taxi_bot.db'

# Місто або регіон для пріоритезації пошуку адрес
GEOCODING_CITY_CONTEXT = os.getenv('GEOCODING_CITY_CONTEXT', 'Сумська область')

# Основний часовий пояс для операцій бота (наприклад, місто роботи таксі)
TIMEZONE = ZoneInfo("Europe/Kiev")

# Час в секундах, який дається водію на прийняття замовлення
DRIVER_ACCEPT_TIMEOUT = int(os.getenv('DRIVER_ACCEPT_TIMEOUT', 60))
# --- Тарифи ---
# Завантажуємо тарифи з .env, з значенням за замовчуванням 0.
# Використовуємо float для можливості вказувати копійки.
TOWN_PRICE = float(os.getenv('TOWN_PRICE', 0))
DRIVER_TOWN_PRICE = float(os.getenv('DRIVER_TOWN_PRICE', 0))
