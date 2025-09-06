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
    return str(v).strip().lower() in ("1","true","yes","y","on")

# Core
TELEGRAM_TOKEN = _env_str("TELEGRAM_TOKEN", "")
DEFAULT_LANG    = _env_str("DEFAULT_LANG", "ru").lower()
LOG_LEVEL       = _env_str("LOG_LEVEL", "INFO").upper()
CACHE_TTL_SECONDS = _env_int("CACHE_TTL_SECONDS", 60)
ENABLE_CHARTS   = _env_bool("ENABLE_CHARTS", False)
PAIR_TIMEFRAME  = _env_str("PAIR_TIMEFRAME", "15m")

# PocketOption scraping (optional)
PO_ENABLE_SCRAPE = _env_bool("PO_ENABLE_SCRAPE", False)
PO_PROXY         = _env_str("PO_PROXY", "")
PO_PROXY_FIRST   = _env_bool("PO_PROXY_FIRST", True)
PO_SCRAPE_DEADLINE = _env_int("PO_SCRAPE_DEADLINE", 120)
PO_HTTPX_TIMEOUT = _env_float("PO_HTTPX_TIMEOUT", 3.0)
PO_NAV_TIMEOUT_MS = _env_int("PO_NAV_TIMEOUT_MS", 20000)
PO_IDLE_TIMEOUT_MS = _env_int("PO_IDLE_TIMEOUT_MS", 12000)
PO_WAIT_EXTRA_MS = _env_int("PO_WAIT_EXTRA_MS", 5000)
PO_BROWSER_ORDER = _env_str("PO_BROWSER_ORDER", "firefox,chromium,webkit")

# Public sources
ALPHAVANTAGE_KEY = _env_str("ALPHAVANTAGE_KEY", "")

def _mask_secret(s: str, keep: int = 4) -> str:
    if not s:
        return ""
    return s[:keep] + "…" + ("*" * max(0, len(s) - keep))

def _mask_proxy(proxy: str) -> str:
    if not proxy: return ""
    try:
        u = urlparse(proxy)
        if u.username:
            masked_auth = f"{u.username}:******"
            return f"{u.scheme}://{masked_auth}@{u.hostname}:{u.port or ''}"
        return proxy
    except Exception:
        return proxy

# Print config summary at import-time for logs (without secrets)
try:
    from .utils.logging import setup
    logger = setup(LOG_LEVEL)
    logger.info("Config: " + str({
        "DEFAULT_LANG": DEFAULT_LANG,
        "CACHE_TTL_SECONDS": CACHE_TTL_SECONDS,
        "ENABLE_CHARTS": ENABLE_CHARTS,
        "PAIR_TIMEFRAME": PAIR_TIMEFRAME,
        "PO_ENABLE_SCRAPE": PO_ENABLE_SCRAPE,
        "PO_PROXY_FIRST": PO_PROXY_FIRST,
        "PO_PROXY": _mask_proxy(PO_PROXY),
        "PO_BROWSER_ORDER": PO_BROWSER_ORDER,
        "PO_HTTPX_TIMEOUT": PO_HTTPX_TIMEOUT,
        "PO_NAV_TIMEOUT_MS": PO_NAV_TIMEOUT_MS,
        "PO_IDLE_TIMEOUT_MS": PO_IDLE_TIMEOUT_MS,
        "PO_WAIT_EXTRA_MS": PO_WAIT_EXTRA_MS,
        "PO_SCRAPE_DEADLINE": PO_SCRAPE_DEADLINE,
        "ALPHAVANTAGE_KEY": _mask_secret(ALPHAVANTAGE_KEY, 4),
        "TELEGRAM_TOKEN": _mask_secret(TELEGRAM_TOKEN, 6),
        "LOG_LEVEL": LOG_LEVEL,
    }))
except Exception:
    pass
