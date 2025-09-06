# Telegram Forecast Bot (Railway-ready)

Минимальная рабочая версия бота с FSM, индикаторами (pandas-ta), fallback-данными (yfinance).
Скрапинг PocketOption отключён по умолчанию, но заготовки есть — можно включить позже.

## Быстрый старт локально

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
export TELEGRAM_TOKEN="YOUR_TOKEN"
python -m app.main
```

## Переменные окружения (Railway Variables)

Обязательные:
- `TELEGRAM_TOKEN` — токен бота.

Опциональные/рекомендуемые:
- `DEFAULT_LANG` — `ru` или `en` (по умолчанию `ru`)
- `LOG_LEVEL` — `DEBUG`/`INFO` (по умолчанию `INFO`)
- `CACHE_TTL_SECONDS` — кэш исторических данных в секундах (по умолчанию `60`)
- `ENABLE_CHARTS` — `0`/`1` (по умолчанию `0`). Для графиков требуется `mplfinance` (уже в requirements).
- `PAIR_TIMEFRAME` — дефолтный таймфрейм меню (по умолчанию `15m`)

Скрапинг PocketOption (опционально, по умолчанию выключен):
- `PO_ENABLE_SCRAPE` — `1` включает попытку скрапинга, иначе бот использует публичные котировки
- `PO_PROXY` — строка прокси `http://user:pass@host:port` (если нужен)
- `PO_PROXY_FIRST` — `1` чтобы начинать с прокси
- `PO_SCRAPE_DEADLINE` — общая дедлайновая длительность скрапинга в секундах (по умолчанию `120`)
- `PO_HTTPX_TIMEOUT` — таймаут httpx (сек)
- `PO_NAV_TIMEOUT_MS`, `PO_IDLE_TIMEOUT_MS`, `PO_WAIT_EXTRA_MS` — тайминги для Playwright
- `PO_BROWSER_ORDER` — список `firefox,chromium,webkit`

Fallback на публичные котировки:
- `ALPHAVANTAGE_KEY` — ключ (используется только если Yahoo недоступен).

## Railway

- Репозиторий подключить к Railway.
- `Procfile` уже содержит процесс `worker`.
- Dockerfile использует Playwright-образ.
- Добавьте переменные окружения, деплойте.
