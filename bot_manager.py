#!/usr/bin/env python3
"""
Простой менеджер для управления ботом.
"""
import asyncio
import os
from pathlib import Path
import psutil
from config.config import TOKEN
from loguru import logger

class BotManager:
    """Простой менеджер бота."""
    
    def __init__(self):
        self.lock_file = Path("bot.lock")
    
    def is_running(self) -> bool:
        """Проверяет, запущен ли уже бот."""
        return self.lock_file.exists()

    def get_pid(self) -> int | None:
        """Читает PID из файла блокировки."""
        if not self.is_running():
            return None
        try:
            with open(self.lock_file, 'r') as f:
                pid = int(f.read().strip())
            return pid
        except (IOError, ValueError) as e:
            logger.error(f"Ошибка чтения PID из файла блокировки: {e}")
            return None
    
    def create_lock(self) -> bool:
        """Создает файл блокировки."""
        # Проверка на "устаревший" lock-файл
        pid = self.get_pid()
        if pid and psutil.pid_exists(pid):
            logger.warning(f"Бот уже запущен с PID {pid}.")
            return False
        elif pid:
            logger.warning(f"Найден устаревший файл блокировки с неактивным PID {pid}. Удаляю его.")
            self.remove_lock()
        elif self.is_running() and not pid:
            logger.warning("Найден поврежденный файл блокировки. Удаляю его.")
            self.remove_lock()
        
        try:
            with open(self.lock_file, 'w') as f:
                f.write(str(os.getpid()))
            logger.info("Создан файл блокировки")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания блокировки: {e}")
            return False
    
    def remove_lock(self):
        """Удаляет файл блокировки."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
                logger.info("Файл блокировки удален")
        except Exception as e:
            logger.error(f"Ошибка удаления блокировки: {e}")

# Глобальный экземпляр
bot_manager = BotManager()

async def safe_bot_start(start_func):
    """Безопасный запуск бота."""
    try:
        # Проверяем блокировку
        if not bot_manager.create_lock():
            return False
        
        logger.info("Запуск бота...")
        await start_func()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        raise
    finally:
        bot_manager.remove_lock()
        logger.info("Бот остановлен")
    
    return True

def stop_bot():
    """Остановка бота."""
    bot_manager.remove_lock()
    print("✅ Бот остановлен")

def force_stop_bot():
    """Принудительно останавливает процесс бота."""
    pid = bot_manager.get_pid()
    if not pid:
        logger.info("Файл блокировки не найден. Возможно, бот не запущен.")
        print("✅ Бот не запущен.")
        return

    try:
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            # Сначала пытаемся завершить грациозно
            process.terminate()
            logger.info(f"Отправлен сигнал terminate процессу с PID {pid}")
            print(f"Отправлен сигнал на остановку процессу {pid}...")
            
            try:
                # Ждем недолго, чтобы процесс мог завершиться
                process.wait(timeout=5)
                logger.info(f"Процесс {pid} успешно завершен.")
                print("✅ Процесс бота успешно остановлен.")
            except psutil.TimeoutExpired:
                logger.warning(f"Процесс {pid} не завершился. Принудительная остановка (kill).")
                process.kill()
                process.wait()
                logger.info(f"Процесс {pid} принудительно остановлен.")
                print("✅ Процесс бота принудительно остановлен.")
        else:
            logger.warning(f"Процесс с PID {pid} не найден, но файл блокировки существует.")
            print("ℹ️ Процесс бота не найден, но остался файл блокировки.")
    except psutil.NoSuchProcess:
        logger.warning(f"Процесс с PID {pid} уже не существует.")
        print("ℹ️ Процесс бота уже не существует.")
    finally:
        bot_manager.remove_lock()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'stop':
        stop_bot()
    else:
        print("Использование: python bot_manager.py stop")
