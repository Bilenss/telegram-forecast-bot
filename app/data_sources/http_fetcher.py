# app/data_sources/http_fetcher.py
import time
import httpx
import pandas as pd
from ..config import PO_HTTP_API_URL, PO_HTTPX_TIMEOUT

class HTTPFetcher:
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        """
        Запрашивает исторические свечи у HTTP-API PocketOption.
        Ожидает JSON вида {'candles': [[ts,o,h,l,c], …]}.
        """
        if not PO_HTTP_API_URL:
            return pd.DataFrame()

        # Текущие метки времени в мс
        now_ms = int(time.time() * 1000)
        # Длительность одной свечи в мс
        interval_map = {
            "1m": 60_000,
            "2m": 2 * 60_000,
            "3m": 3 * 60_000,
            "5m": 5 * 60_000,
            "10m": 10 * 60_000,
            "15m": 15 * 60_000,
            "30m": 30 * 60_000,
            "1h": 60 * 60_000,
        }
        interval = interval_map.get(timeframe, 60_000)
        # Запросим последние 100 свечей
        start_ms = now_ms - interval * 100
        params = {
            "symbol": symbol,
            "timeframe": timeframe.rstrip("m"),  # некоторые API требуют без 'm'
            "from": start_ms,
            "to": now_ms,
        }
        headers = {
            "User-Agent": "Mozilla/5.0",  # можно точнее
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://pocketoption.com/en/cabinet/try-demo/",
        }
        async with httpx.AsyncClient(timeout=PO_HTTPX_TIMEOUT) as client:
            resp = await client.get(PO_HTTP_API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        candles = data.get("candles") or []
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles, columns=["timestamp","open","high","low","close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
