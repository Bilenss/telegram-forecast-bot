# Telegram Forecast Bot (Railway-ready)

Простой Telegram-бот с FSM, индикаторами (на основе pandas-ta) и данными из PocketOption.

PocketOption scraping включён по умолчанию (`PO_STRICT_ONLY=True`), используется **только PocketOption** — без fallback-источников.

---

## 🚀 Быстрый старт локально

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
export TELEGRAM_TOKEN="YOUR_TOKEN"
export PO_ENABLE_SCRAPE=1
python -m app.main
⚙️ Переменные окружения (Railway Variables)
Обязательные:

TELEGRAM_TOKEN — токен Telegram-бота.

Опциональные/рекомендуемые:

DEFAULT_LANG — язык интерфейса: ru или en (по умолчанию ru)

LOG_LEVEL — уровень логов: DEBUG / INFO (по умолчанию INFO)

CACHE_TTL_SECONDS — кэш исторических данных, в секундах (по умолчанию 60)

ENABLE_CHARTS — 1 включает генерацию графиков (mplfinance уже в requirements)

PAIR_TIMEFRAME — дефолтный таймфрейм в кнопках (по умолчанию 15m)

Скрапинг PocketOption (обязательно):

PO_ENABLE_SCRAPE — 1 включает скрапинг PocketOption (обязательно для работы)

PO_STRICT_ONLY — 1 (всегда использовать только PO, без fallback — по умолчанию)

PO_ENTRY_URL — (опционально) URL демо-страницы PO (по умолчанию используется стандартный)

PO_FAST_FAIL_SEC — максимальное ожидание ответа PO (по умолчанию 45)

PO_PROXY — прокси в формате http://user:pass@host:port (если используется)

PO_PROXY_FIRST — 1, чтобы начинать с прокси (по умолчанию 1)

PO_SCRAPE_DEADLINE — общий лимит времени на скрапинг (в секундах, по умолчанию 120)

PO_HTTPX_TIMEOUT — таймаут HTTP-запросов (по умолчанию 3.0)

PO_NAV_TIMEOUT_MS — таймаут навигации Playwright (по умолчанию 20000)

PO_IDLE_TIMEOUT_MS — таймаут простоя страницы (по умолчанию 12000)

PO_WAIT_EXTRA_MS — дополнительное ожидание (по умолчанию 5000)

PO_BROWSER_ORDER — порядок браузеров: firefox,chromium,webkit

🚉 Railway

Подключите репозиторий к Railway.

Procfile уже содержит процесс worker.

Используется Dockerfile, совместимый с Playwright.

Добавьте переменные окружения и деплойте.
