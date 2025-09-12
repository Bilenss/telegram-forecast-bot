"""
Диагностика работы с PocketOption
Запуск: python -m app.utils.po_diagnostic
"""

import asyncio
import logging
from datetime import datetime
import sys
import os

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.data_sources.pocketoption_scraper import fetch_po_ohlc_async
from app.config import PO_ENABLE_SCRAPE, PO_PROXY, PO_BROWSER_ORDER

# NEW: импортируем CompositeFetcher
from app.data_sources.fetchers import CompositeFetcher  # NEW

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_pocketoption_connection():
    """Полная диагностика подключения к PocketOption"""

    print("="*60)
    print("🔍 ДИАГНОСТИКА POCKETOPTION")
    print("="*60)

    # 1. Проверка конфигурации
    print("\n1️⃣ КОНФИГУРАЦИЯ:")
    print(f"   PO_ENABLE_SCRAPE: {PO_ENABLE_SCRAPE}")
    print(f"   PO_PROXY: {'Configured' if PO_PROXY else 'Not configured'}")
    print(f"   PO_BROWSER_ORDER: {PO_BROWSER_ORDER}")

    if not PO_ENABLE_SCRAPE:
        print("\n❌ PO_ENABLE_SCRAPE=0 - скрапинг отключен!")
        print("   Установите PO_ENABLE_SCRAPE=1 в переменных окружения")
        return False

    # 2. Тест простого запроса
    print("\n2️⃣ ТЕСТ ЗАГРУЗКИ ДАННЫХ:")

    test_cases = [
        ("EURUSD", "1m", False),  # FIN пара
        ("EURUSD", "5m", False),  # Другой таймфрейм
        ("EURUSD", "1m", True),   # OTC пара
    ]

    results = []

    for symbol, timeframe, otc in test_cases:
        try:
            print(f"\n   Тестирую {symbol} {timeframe} (OTC={otc})...")
            start_time = datetime.now()

            df = await fetch_po_ohlc_async(
                symbol=symbol,
                timeframe=timeframe,
                otc=otc
            )

            elapsed = (datetime.now() - start_time).total_seconds()

            if df is not None and len(df) > 0:
                print(f"   ✅ Успешно! Получено {len(df)} баров за {elapsed:.1f} сек")
                print(f"      Последняя цена: {df['close'].iloc[-1]:.5f}")
                print(f"      Время последнего бара: {df.index[-1]}")
                results.append(True)
            else:
                print(f"   ⚠️ Получен пустой DataFrame")
                results.append(False)

        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)}")
            results.append(False)

    # 3. Тест скорости
    print("\n3️⃣ ТЕСТ СКОРОСТИ (целевое время < 10 сек):")

    try:
        print("   Измеряю скорость загрузки EURUSD 1m...")
        times = []

        for i in range(3):
            start = datetime.now()
            df = await fetch_po_ohlc_async("EURUSD", "1m", False)
            elapsed = (datetime.now() - start).total_seconds()
            times.append(elapsed)
            print(f"   Попытка {i+1}: {elapsed:.1f} сек")

        avg_time = sum(times) / len(times)

        print(f"\n   Среднее время: {avg_time:.1f} сек")
        if avg_time < 10:
            print("   ✅ Скорость в пределах нормы!")
        else:
            print("   ⚠️ Скорость ниже целевой (>10 сек)")
            print("   Рекомендации:")
            print("   - Используйте прокси ближе к серверу")
            print("   - Уменьшите PO_WAIT_EXTRA_MS")
            print("   - Используйте chromium вместо firefox")

    except Exception as e:
        print(f"   ❌ Ошибка теста скорости: {e}")

    # 4. Итоговый результат
    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТЫ ДИАГНОСТИКИ:")

    success_rate = sum(results) / len(results) * 100 if results else 0

    if success_rate >= 66:
        print(f"✅ Система работает! Успешность: {success_rate:.0f}%")
        print("\nРекомендации для улучшения:")
        print("• Оптимизируйте таймауты в config.py")
        print("• Используйте кэширование для повторных запросов")
        print("• Рассмотрите использование пула браузеров")
        return True
    else:
        print(f"❌ Проблемы с подключением! Успешность: {success_rate:.0f}%")
        print("\nВозможные причины:")
        print("• Блокировка IP адреса")
        print("• Изменения в структуре сайта PocketOption")
        print("• Проблемы с прокси")
        print("• Слишком маленькие таймауты")
        print("\nРешения:")
        print("• Попробуйте другой прокси")
        print("• Увеличьте PO_NAV_TIMEOUT_MS и PO_IDLE_TIMEOUT_MS")
        print("• Проверьте доступность pocketoption.com")
        return False

async def test_fast_mode():
    """Тест режима быстрых прогнозов"""
    print("\n" + "="*60)
    print("⚡ ТЕСТ БЫСТРОГО РЕЖИМА")
    print("="*60)

    try:
        from app.analysis.fast_prediction import fast_predictor

        print("\n1. Загружаю данные...")
        df = await fetch_po_ohlc_async("EURUSD", "1m", False)

        if df is None or len(df) == 0:
            print("❌ Не удалось загрузить данные")
            return

        print(f"✅ Загружено {len(df)} баров")

        print("\n2. Генерирую быстрый прогноз...")
        start = datetime.now()

        prediction_text, prediction_data = await fast_predictor.get_fast_prediction(
            pair="EUR/USD",
            timeframe="1m",
            df=df,
            mode="ind"
        )

        elapsed = (datetime.now() - start).total_seconds()

        print(f"✅ Прогноз сгенерирован за {elapsed:.1f} сек")
        print("\nПРОГНОЗ:")
        print("-"*40)
        print(prediction_text[:500])  # Первые 500 символов
        print("-"*40)

        if elapsed < 5:
            print("✅ Отличная скорость!")
        elif elapsed < 10:
            print("✅ Хорошая скорость!")
        else:
            print("⚠️ Скорость можно улучшить")

    except ImportError:
        print("❌ Модуль fast_prediction не найден")
        print("   Создайте файл app/analysis/fast_prediction.py")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# NEW: тест для CompositeFetcher
async def test_real_fetch():  # NEW
    """Тест реального фетча через CompositeFetcher"""  # NEW
    print("\n" + "="*60)  # NEW
    print("🔄 ТЕСТ CompositeFetcher")  # NEW
    print("="*60)  # NEW

    cf = CompositeFetcher()  # NEW
    try:  # NEW
        df = await cf.fetch("EURUSD", "1m", False)  # NEW
        if df is not None:  # NEW
            print(f"Bars: {len(df)}, Columns: {df.columns.tolist()}")  # NEW
        else:  # NEW
            print("CompositeFetcher returned None or empty DataFrame")  # NEW
    except Exception as e:  # NEW
        print(f"Error during CompositeFetcher test: {e}")  # NEW

if __name__ == "__main__":
    print("Запуск диагностики PocketOption...")
    print(f"Время: {datetime.now()}")

    # Основная диагностика
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(test_pocketoption_connection())

    # Тест быстрого режима
    if result:
        loop.run_until_complete(test_fast_mode())

    # NEW: тест CompositeFetcher
    loop.run_until_complete(test_real_fetch())  # NEW

    print("\n✅ Диагностика завершена!")
