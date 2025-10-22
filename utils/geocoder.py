from geopy.geocoders import Nominatim
import asyncio
from loguru import logger
import time

# Константа для ограничения области поиска геокодера (Сумская область)
# Координаты [юго-запад, северо-восток]
SUMY_OBLAST_VIEWBOX = [50.20, 33.35, 51.65, 35.75]


# Ініціалізуємо геокодер з унікальним user_agent, як того вимагає політика Nominatim
# geolocator_nominatim = Nominatim(user_agent="nubira_taxi_bot/1.0", timeout=10)
class RateLimitedGeocoder:
    """
    Асинхронная обертка для geopy.Nominatim, обеспечивающая соблюдение
    ограничения по частоте запросов (1 запрос в секунду) без блокировки
    всего приложения с помощью asyncio.sleep().
    """
    def __init__(self, user_agent: str, timeout: int = 10):
        self._geolocator = Nominatim(user_agent=user_agent, timeout=timeout)
        self._lock = asyncio.Lock()
        self._last_request_time = 0
        self._delay = 1.1  # Задержка чуть больше 1 секунды

    async def _execute_request(self, func, *args, **kwargs):
        async with self._lock:
            # Проверяем, сколько времени прошло с последнего запроса
            time_since_last_request = time.monotonic() - self._last_request_time
            if time_since_last_request < self._delay:
                # Если времени прошло недостаточно, асинхронно ждем оставшееся время
                await asyncio.sleep(self._delay - time_since_last_request)

            try:
                # Выполняем блокирующий сетевой запрос в отдельном потоке
                location = await asyncio.to_thread(func, *args, **kwargs)
                return location
            except Exception as e:
                logger.error(f"Geocoding request failed for query '{args[0]}': {e}")
                return None
            finally:
                # Обновляем время последнего запроса
                self._last_request_time = time.monotonic()

    async def geocode(self, query: str, **kwargs):
        """Асинхронно вызывает геокодер для преобразования адреса в координаты."""
        return await self._execute_request(self._geolocator.geocode, query, **kwargs)

    async def reverse(self, query, **kwargs):
        """Асинхронно вызывает геокодер для преобразования координат в адрес."""
        return await self._execute_request(self._geolocator.reverse, query, **kwargs)

# Создаем единственный экземпляр нашего нового геокодера
geocoder = RateLimitedGeocoder(user_agent="nubira_taxi_bot/1.0", timeout=10)

async def geocode(query: str, **kwargs):
    """Асинхронно викликає геокодер для перетворення адреси в координати."""
    return await geocoder.geocode(query, **kwargs)

async def reverse(query, **kwargs):
    """Асинхронно викликає геокодер для перетворення координат в адресу."""
    return await geocoder.reverse(query, **kwargs)
