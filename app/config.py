from __future__ import annotations
import os

def _env_str(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v is not None else default

def _env_float(name: str, default: float = 0.0) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v is not None and v != "" else default
    except:
        return default

def _env_int(name: str, default: int = 0) -> int:
    v = os.environ.get(name)
    try:
        return int(v) if v is not None and v != "" else default
    except:
        return default

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return str(v).lower() in ("1","true","yes","on")

# Core
TELEGRAM_TOKEN    = _env_str("TELEGRAM_TOKEN")
LOG_LEVEL         = _env_str("LOG_LEVEL","INFO").upper()
CACHE_TTL_SECONDS = _env_int("CACHE_TTL_SECONDS",600)

# PocketOption HTTP-API URL (возьмите точно из DevTools XHR → Request URL!)
PO_ENTRY_URL      = _env_str("PO_ENTRY_URL","https://pocketoption.com/en/cabinet/try-demo/")
PO_HTTP_API_URL   = _env_str(
    "PO_HTTP_API_URL",
    # ← сюда вставьте ваш скопированный Request URL без параметров
    "https://try-demo-eu.po.market/api/chart/history"
)
PO_HTTPX_TIMEOUT  = _env_float("PO_HTTPX_TIMEOUT",10.0)
