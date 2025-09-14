from __future__ import annotations
import os
from urllib.parse import urlparse

def _env_str(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v is not None else default

def _env_int(name: str, default: int = 0) -> int:
    v = os.environ.get(name)
    try:
        return int(v) if v is not None and v != "" else default
    except Exception:
        return default

def _env_float(name: str, default: float = 0.0) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v is not None and v != "" else default
    except Exception:
        return default

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

# Основные настройки
TELEGRAM_TOKEN     = _env_str("TELEGRAM_TOKEN", "")
DEFAULT_LANG       = _env_str("DEFAULT_LANG", "en").lower()
LOG_LEVEL          = _env_str("LOG_LEVEL", "INFO").upper()
CACHE_TTL_SECONDS  = _env_int("CACHE_TTL_SECONDS", 60)
ENABLE_CHARTS      = _env_bool("ENABLE_CHARTS", False)
PAIR_TIMEFRAME     = _env_str("PAIR_TIMEFRAME", "15m")

# Настройки PocketOption-скрапинга
PO_ENABLE_SCRAPE    = _env_bool("PO_ENABLE_SCRAPE", False)
PO_PROXY            = _env_str("PO_PROXY", "")
PO_PROXY_FIRST      = _env_bool("PO_PROXY_FIRST", True)
PO_SCRAPE_DEADLINE  = _env_int("PO_SCRAPE_DEADLINE", 120)
PO_HTTPX_TIMEOUT    = _env_float("PO_HTTPX_TIMEOUT", 10.0)
PO_NAV_TIMEOUT_MS   = _env_int("PO_NAV_TIMEOUT_MS", 20000)
PO_IDLE_TIMEOUT_MS  = _env_int("PO_IDLE_TIMEOUT_MS", 12000)
PO_WAIT_EXTRA_MS    = _env_int("PO_WAIT_EXTRA_MS", 5000)
PO_BROWSER_ORDER    = _env_str("PO_BROWSER_ORDER", "firefox,chromium,webkit")
PO_ENTRY_URL        = _env_str("PO_ENTRY_URL", "https://pocketoption.com/en/cabinet/try-demo/")
PO_FAST_FAIL_SEC    = _env_int("PO_FAST_FAIL_SEC", 45)
PO_STRICT_ONLY      = _env_bool("PO_STRICT_ONLY", True)

# HTTP-API для исторических свечей PocketOption
PO_HTTP_API_URL    = _env_str(
    "PO_HTTP_API_URL",
    "https://try-demo-eu.po.market/api/chart/history"
)
PO_HTTPX_TIMEOUT   = _env_float("PO_HTTPX_TIMEOUT", 10.0)

# Порядок провайдеров и флаги дополнительных фетчеров
PO_FETCH_ORDER     = _env_str("PO_FETCH_ORDER", "po,interceptor,ocr").split(",")
PO_USE_INTERCEPTOR = _env_bool("PO_USE_INTERCEPTOR", True)
PO_USE_OCR         = _env_bool("PO_USE_OCR", False)

# Логируем настройки (без секретов)
try:
    from .utils.logging import setup
    logger = setup(LOG_LEVEL)
    logger.info("Config loaded: " + str({
        "DEFAULT_LANG": DEFAULT_LANG,
        "CACHE_TTL_SECONDS": CACHE_TTL_SECONDS,
        "ENABLE_CHARTS": ENABLE_CHARTS,
        "PAIR_TIMEFRAME": PAIR_TIMEFRAME,
        "PO_ENABLE_SCRAPE": PO_ENABLE_SCRAPE,
        "PO_PROXY_FIRST": PO_PROXY_FIRST,
        "PO_PROXY": PO_PROXY,
        "PO_BROWSER_ORDER": PO_BROWSER_ORDER,
        "PO_HTTPX_TIMEOUT": PO_HTTPX_TIMEOUT,
        "PO_NAV_TIMEOUT_MS": PO_NAV_TIMEOUT_MS,
        "PO_IDLE_TIMEOUT_MS": PO_IDLE_TIMEOUT_MS,
        "PO_WAIT_EXTRA_MS": PO_WAIT_EXTRA_MS,
        "PO_SCRAPE_DEADLINE": PO_SCRAPE_DEADLINE,
        "PO_ENTRY_URL": PO_ENTRY_URL,
        "PO_FAST_FAIL_SEC": PO_FAST_FAIL_SEC,
        "PO_STRICT_ONLY": PO_STRICT_ONLY,
        "PO_FETCH_ORDER": PO_FETCH_ORDER,
        "PO_USE_INTERCEPTOR": PO_USE_INTERCEPTOR,
        "PO_USE_OCR": PO_USE_OCR,
        "PO_HTTP_API_URL": PO_HTTP_API_URL,
        "PO_HTTPX_TIMEOUT": PO_HTTPX_TIMEOUT,
        "LOG_LEVEL": LOG_LEVEL,
    }))
except Exception:
    pass
