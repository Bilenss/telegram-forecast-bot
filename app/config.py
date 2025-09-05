# app/config.py
from __future__ import annotations
import os
from urllib.parse import urlparse

# ---------------- helpers ----------------

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

def _as_bool_int(v: str | None, default: int = 0) -> int:
    if v is None:
        return default
    return 1 if str(v).strip().lower() in ("1", "true", "yes", "on") else 0

def _mask_secret(val: str, keep: int = 4) -> str:
    if not val:
        return ""
    if len(val) <= keep:
        return "*" * len(val)
    return val[:keep] + "…" + "*" * max(0, len(val) - keep)

def _mask_proxy(p: str) -> str:
    if not p:
        return ""
    try:
        u = urlparse(p)
        hostport = f"{u.hostname}:{u.port}" if u.hostname else ""
        return f"{u.scheme}://{hostport}"
    except Exception:
        return p

# --------------- public config ----------------

# Бот / общий
TELEGRAM_TOKEN      = _env_str("TELEGRAM_TOKEN")
DEFAULT_LANG        = _env_str("DEFAULT_LANG", "ru")
CACHE_TTL_SECONDS   = _env_int("CACHE_TTL_SECONDS", 60)
ENABLE_CHARTS       = _env_int("ENABLE_CHARTS", 0)
LOG_LEVEL           = _env_str("LOG_LEVEL", "INFO")
ALPHAVANTAGE_KEY    = _env_str("ALPHAVANTAGE_KEY", "")

# Scraper (HTTPX)
PO_HTTPX_TIMEOUT    = _env_float("PO_HTTPX_TIMEOUT", 3.0)

# Scraper (Playwright/общие)
PO_NAV_TIMEOUT_MS   = _env_int("PO_NAV_TIMEOUT_MS", 12000)
PO_IDLE_TIMEOUT_MS  = _env_int("PO_IDLE_TIMEOUT_MS", 8000)
PO_WAIT_EXTRA_MS    = _env_int("PO_WAIT_EXTRA_MS", 3500)
PO_SCRAPE_DEADLINE  = _env_int("PO_SCRAPE_DEADLINE", 90)

# Включатель скрейпера (той самой константы раньше не хватало)
PO_ENABLE_SCRAPE    = _env_int("PO_ENABLE_SCRAPE", 1)

# Порядок браузеров Playwright
PO_BROWSER_ORDER    = _env_str("PO_BROWSER_ORDER", "firefox,chromium,webkit")

# Прокси (одна строка: схемa://user:pass@host:port)
PO_PROXY            = _env_str("PO_PROXY", "").strip()

# Где пытаться сначала: прокси/прямой (поддерживаем оба названия env)
PO_PROXY_FIRST = _as_bool_int(
    os.environ.get("PO_SCRAPE_PROXY_FIRST", os.environ.get("PO_PROXY_FIRST", "0")),
    default=0,
)

# ---------------- debug print (без секретов) ----------------
try:
    # Лёгкое логирование, без зависимостей от нашего логгера
    print(
        "CONFIG:",
        {
            "DEFAULT_LANG": DEFAULT_LANG,
            "CACHE_TTL_SECONDS": CACHE_TTL_SECONDS,
            "ENABLE_CHARTS": ENABLE_CHARTS,
            "LOG_LEVEL": LOG_LEVEL,
            "PO_HTTPX_TIMEOUT": PO_HTTPX_TIMEOUT,
            "PO_NAV_TIMEOUT_MS": PO_NAV_TIMEOUT_MS,
            "PO_IDLE_TIMEOUT_MS": PO_IDLE_TIMEOUT_MS,
            "PO_WAIT_EXTRA_MS": PO_WAIT_EXTRA_MS,
            "PO_SCRAPE_DEADLINE": PO_SCRAPE_DEADLINE,
            "PO_ENABLE_SCRAPE": PO_ENABLE_SCRAPE,
            "PO_BROWSER_ORDER": PO_BROWSER_ORDER,
            "PO_PROXY_FIRST": PO_PROXY_FIRST,
            "PO_PROXY": _mask_proxy(PO_PROXY),
            "TELEGRAM_TOKEN": _mask_secret(TELEGRAM_TOKEN, 6),
            "ALPHAVANTAGE_KEY": _mask_secret(ALPHAVANTAGE_KEY, 6),
        }
    )
except Exception:
    pass
