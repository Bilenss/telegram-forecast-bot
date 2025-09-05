# app/config.py
import os
import logging

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in ("1", "true", "t", "yes", "y", "on")

def _mask_proxy(p: str | None) -> str:
    if not p:
        return ""
    # логируем без логина/пароля
    try:
        from urllib.parse import urlparse
        u = urlparse(p)
        host = u.hostname or ""
        port = f":{u.port}" if u.port else ""
        return f"{u.scheme}://{host}{port}"
    except Exception:
        return p

# --- основные переменные проекта ---
TELEGRAM_TOKEN       = os.getenv("TELEGRAM_TOKEN", "")
DEFAULT_LANG         = os.getenv("DEFAULT_LANG", "ru").lower()
CACHE_TTL_SECONDS    = _env_int("CACHE_TTL_SECONDS", 60)
ENABLE_CHARTS        = _env_bool("ENABLE_CHARTS", False)
LOG_LEVEL            = os.getenv("LOG_LEVEL", "INFO").upper()

# --- PocketOption scraper ---
PO_PROXY             = os.getenv("PO_PROXY", "").strip() or None
PO_PROXY_FIRST       = _env_bool("PO_PROXY_FIRST", False)   # False = сначала direct
PO_BROWSER_ORDER     = os.getenv("PO_BROWSER_ORDER", "firefox,chromium,webkit")

PO_HTTPX_TIMEOUT     = float(os.getenv("PO_HTTPX_TIMEOUT", "3.0"))
PO_IDLE_TIMEOUT_MS   = _env_int("PO_IDLE_TIMEOUT_MS", 8000)
PO_NAV_TIMEOUT_MS    = _env_int("PO_NAV_TIMEOUT_MS", 20000)
PO_WAIT_EXTRA_MS     = _env_int("PO_WAIT_EXTRA_MS", 5000)
PO_SCRAPE_DEADLINE   = _env_int("PO_SCRAPE_DEADLINE", 120)

# отладочный вывод конфигурации на старте
def log_effective_config(logger: logging.Logger):
    logger.debug(
        "CONFIG: PROXY_FIRST=%s, NAV_TIMEOUT_MS=%s, IDLE_TIMEOUT_MS=%s, WAIT_EXTRA_MS=%s, "
        "HTTPX_TIMEOUT=%.1f, DEADLINE=%s, BROWSERS=%s, PROXY=%s",
        PO_PROXY_FIRST, PO_NAV_TIMEOUT_MS, PO_IDLE_TIMEOUT_MS, PO_WAIT_EXTRA_MS,
        PO_HTTPX_TIMEOUT, PO_SCRAPE_DEADLINE, PO_BROWSER_ORDER, _mask_proxy(PO_PROXY)
    )
