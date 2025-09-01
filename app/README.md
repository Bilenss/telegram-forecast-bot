# Telegram Forecast Bot (Railway)

Бот телеграм с прогнозами по валютным парам. Источник котировок — PocketOption (скрапинг) с автоматическим
переходом на публичные котировки (Yahoo/AlphaVantage) при сбое.

## Быстрый старт локально

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
export TELEGRAM_TOKEN=....
python -m app.main
```

## Переменные окружения

- `TELEGRAM_TOKEN` — токен бота (обязательно).
- `PO_ENABLE_SCRAPE` — 1/0: включить попытку скрапинга PocketOption (по умолчанию 1).
- `PO_PROXY` — прокси (http://user:pass@host:port), опционально.
- `CACHE_TTL_SECONDS` — TTL кэша котировок, по умолчанию 60 сек.
- `ALPHAVANTAGE_KEY` — ключ для AlphaVantage (если решите использовать как альтернативный источник).
- `PAIR_TIMEFRAME` — дефолтный таймфрейм (например, 15m).
- `ENABLE_CHARTS` — 1/0: генерировать ли график.
- `DEFAULT_LANG` — ru|en.

## Railway

- Добавьте **Service** -> `worker`.
- В `Procfile`: `worker: python -m app.main`.
- В `Dockerfile` уже всё готово для сборки.
- Установите переменные окружения.
- Задеплойте подключив GitHub-репозиторий.

## Ограничения

- Таймфреймы 15s/30s доступны только когда удаётся скрапинг с PocketOption.
- Fallback-источник поддерживает 1m/5m/15m/1h.
