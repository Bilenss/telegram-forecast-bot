import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "ru")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

PO_ENABLE_SCRAPE = int(os.getenv("PO_ENABLE_SCRAPE", "1"))
PO_PROXY = os.getenv("PO_PROXY", "")  # http://user:pass@host:port or empty

ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_KEY", "")
PAIR_TIMEFRAME = os.getenv("PAIR_TIMEFRAME", "15m")  # default

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENABLE_CHARTS = int(os.getenv("ENABLE_CHARTS", "0"))
TMP_DIR = os.getenv("TMP_DIR", "/tmp")

# 🔧 Новые настройки для Pocket Option Scraper
PO_SCRAPE_DEADLINE   = int(os.getenv("PO_SCRAPE_DEADLINE", "24"))           # общий лимит, сек
PO_PROXY_FIRST       = os.getenv("PO_SCRAPE_PROXY_FIRST", "0") == "1"       # 1=сначала через прокси
PO_NAV_TIMEOUT_MS    = int(os.getenv("PO_NAV_TIMEOUT_MS", "18000"))         # playwright.goto timeout
PO_IDLE_TIMEOUT_MS   = int(os.getenv("PO_IDLE_TIMEOUT_MS", "10000"))        # playwright ожидание networkidle
PO_WAIT_EXTRA_MS     = int(os.getenv("PO_WAIT_EXTRA_MS", "6000"))           # доп. ожидание после загрузки
PO_HTTPX_TIMEOUT     = float(os.getenv("PO_HTTPX_TIMEOUT", "3.0"))          # таймаут httpx
