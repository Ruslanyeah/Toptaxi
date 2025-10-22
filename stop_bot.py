#!/usr/bin/env python3
"""
Скрипт для примусової зупинки всіх екземплярів Telegram бота.
Використовуйте його, якщо `main.py` повідомляє про конфлікт (`TelegramConflictError`).
"""

import logging
import os
import sys

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def stop_processes():
    """Знаходить та примусово завершує всі процеси, пов'язані з main.py."""
    try:
        import psutil
    except ImportError:
        logger.error("Для роботи цього скрипта потрібна бібліотека psutil. Встановіть її: pip install psutil")
        sys.exit(1)

    found_procs = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if 'python' in proc.info['name'].lower() and proc.info['cmdline'] and 'main.py' in ' '.join(proc.info['cmdline']):
                found_procs.append(proc)
    except Exception as e:
        logger.error(f"Помилка під час пошуку процесів: {e}")
        return

    if not found_procs:
        logger.info("Не знайдено запущених процесів з main.py.")
        return

    for proc in found_procs:
        logger.warning(f"Знайдено процес бота з PID: {proc.pid}. Примусове завершення...")
        try:
            proc.kill()
            logger.info(f"Процес {proc.pid} успішно завершено.")
        except psutil.NoSuchProcess:
            logger.warning(f"Процес {proc.pid} вже завершився.")
        except Exception as e:
            logger.error(f"Не вдалося завершити процес {proc.pid}: {e}")

if __name__ == '__main__':
    stop_processes()
    logger.info("Перевірку завершено. Можна спробувати запустити бота знову: python main.py")
