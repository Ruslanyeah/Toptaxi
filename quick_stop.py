#!/usr/bin/env python3
"""
Быстрый скрипт для остановки Telegram бота.
Использует новый менеджер бота для надежной остановки.
"""

import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from bot_manager import force_stop_bot
    
    if __name__ == '__main__':
        print("🛑 Швидка зупинка Telegram бота")
        print("=" * 35)
        force_stop_bot()
        
except ImportError as e:
    print(f"❌ Помилка імпорту: {e}")
    print("Переконайтеся, що файл bot_manager.py існує та доступний.")
    sys.exit(1)
except Exception as e:
    print(f"❌ Неочікувана помилка: {e}")
    sys.exit(1)
