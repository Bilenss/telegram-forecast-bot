from __future__ import annotations
import os
from dataclasses import dataclass

def _parse_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    v = str(v).strip().lower()
    return v in {"1", "true", "yes", "on", "y"}

@dataclass
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    timeframe: str = os.getenv("PAIR_TIMEFRAME", "5m")
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "60"))
    po_enable_scrape: bool = _parse_bool(os.getenv("PO_ENABLE_SCRAPE"), False)

    # используем отдельную переменную только для Playwright
    po_proxy: str | None = os.getenv("PO_PROXY") or None

    # оставим совместимость, но НЕ используем их в коде
    http_proxy: str | None = os.getenv("HTTP_PROXY") or None
    https_proxy: str | None = os.getenv("HTTPS_PROXY") or None

settings = Settings()
