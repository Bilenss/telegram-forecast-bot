# app/data_sources/http_fetcher.py
import time
import httpx
import pandas as pd
from ..config import PO_HTTP_API_URL, PO_HTTPX_TIMEOUT, PO_ENTRY_URL

class HTTPFetcher:
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        """
        1) GET главную страницу, чтобы клиент сохранил куки
        2) GET запроса исторических свечей (XHR) с теми же куками/headers
        """
        if not PO_HTTP_API_URL:
            return pd.DataFrame()

        # Маппинг длины свечи
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

        now_ms   = int(time.time() * 1000)
        start_ms = now_ms - interval * 100  # последние 100 свечей

        params = {
            "symbol":     symbol,
            "timeframe":  timeframe.rstrip("m"),  # или как требует API
            "from":       start_ms,
            "to":         now_ms,
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept":     "application/json, text/plain, */*",
            "Referer":    PO_ENTRY_URL,
        }

        async with httpx.AsyncClient(timeout=PO_HTTPX_TIMEOUT) as client:
            # 1) Загружаем демо-кабинет, чтобы получить куки
            await client.get(PO_ENTRY_URL, headers=headers)
            # 2) Запрашиваем свечи XHR
            resp = await client.get(PO_HTTP_API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        candles = data.get("candles", [])
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles, columns=["timestamp","open","high","low","close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
