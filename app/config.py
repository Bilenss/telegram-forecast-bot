import os
from dataclasses import dataclass

@dataclass
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    po_enable_scrape: bool = os.getenv("PO_ENABLE_SCRAPE", "0") == "1"
    timeframe: str = os.getenv("PAIR_TIMEFRAME", "1m")
    cache_ttl: int = int(os.getenv("CACHE_TTL_SECONDS", "60"))
    http_proxy: str | None = os.getenv("HTTP_PROXY")
    https_proxy: str | None = os.getenv("HTTPS_PROXY")

settings = Settings()
