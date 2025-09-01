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
