import time
import httpx
import pandas as pd
from ..config import PO_ENTRY_URL, PO_HTTP_API_URL, PO_HTTPX_TIMEOUT

class HTTPFetcher:
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        """
        1) Заливаем страницу, чтобы собрать куки
        2) Повторяем XHR-запрос с теми же куками и заголовками
        """
        if not PO_HTTP_API_URL:
            return pd.DataFrame()

        # рассчитываем period в мс
        now = int(time.time() * 1000)
        tf_map = {
            "1m": 60_000, "2m": 120_000, "3m": 180_000,
            "5m": 300_000, "10m": 600_000, "15m": 900_000,
            "30m": 1_800_000,"1h": 3_600_000
        }
        interval = tf_map.get(timeframe, 60_000)
        start = now - interval * 100  # 100 баров

        params = {
            "symbol":    symbol,
            "timeframe": timeframe.rstrip("m"),
            "from":      start,
            "to":        now,
        }

        headers = {
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept":          "application/json, text/plain, */*",
            "Referer":         PO_ENTRY_URL,
            "Origin":          "https://pocketoption.com",
            # "Cookie":       client.cookies.jar if нужно вручную
        }

        async with httpx.AsyncClient(
            timeout=PO_HTTPX_TIMEOUT,
            follow_redirects=True
        ) as client:
            # 1) примим куки
            await client.get(PO_ENTRY_URL, headers=headers)
            # 2) реальный XHR
            resp = await client.get(PO_HTTP_API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        candles = data.get("candles") or []
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(
            candles,
            columns=["timestamp","open","high","low","close"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
