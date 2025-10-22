import sqlite3
import os

# --- Конфигурация ---
USER_ID_TO_UNBAN = 437724267  # Ваш Telegram ID
DB_RELATIVE_PATH = 'database/database.db'
# ---------------------

# Получаем абсолютный путь к базе данных
# Предполагается, что скрипт запускается из корневой папки проекта (Nubira-Taxi-main)
db_path = os.path.join(os.getcwd(), DB_RELATIVE_PATH)

if not os.path.exists(db_path):
    print(f"Ошибка: Файл базы данных не найден по пути '{db_path}'")
    print("Пожалуйста, убедитесь, что вы запускаете этот скрипт из корневой папки вашего проекта ('Nubira-Taxi-main').")
else:
    try:
        # Подключаемся к базе данных SQLite
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Проверяем текущий статус бана
        cursor.execute("SELECT is_banned FROM clients WHERE user_id = ?", (USER_ID_TO_UNBAN,))
        result = cursor.fetchone()

        if result is None:
            print(f"Пользователь с ID {USER_ID_TO_UNBAN} не найден в таблице 'clients'.")
        elif result[0] == 0:
            print(f"Пользователь с ID {USER_ID_TO_UNBAN} уже не заблокирован.")
        else:
            # Обновляем статус 'is_banned' на 0 (не заблокирован)
            print(f"Пользователь {USER_ID_TO_UNBAN} в данный момент заблокирован. Снимаю блокировку...")
            cursor.execute("UPDATE clients SET is_banned = 0 WHERE user_id = ?", (USER_ID_TO_UNBAN,))
            conn.commit()
            print(f"Блокировка с пользователя с ID {USER_ID_TO_UNBAN} успешно снята.")

        # Закрываем соединение
        conn.close()

    except sqlite3.Error as e:
        print(f"Произошла ошибка: {e}")