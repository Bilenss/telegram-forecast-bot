# app/data_sources/browser_ws_fetcher.py

import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from ..config import PO_BROWSER_WS_URL, PO_ENTRY_URL, PO_NAV_TIMEOUT_MS, PO_IDLE_TIMEOUT_MS

class BrowserWebSocketFetcher:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        async with self._lock:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                page = await browser.new_page()
                messages: list[tuple[str,str]] = []

                # Перехват всех WS-сообщений
                page.on(
                    "websocket",
                    lambda ws: ws.on(
                        "framereceived",
                        lambda data: messages.append((
                            ws.url,
                            data.decode("utf-8")
                            if isinstance(data, (bytes, bytearray))
                            else data
                        ))
                    )
                )

                # Навигация и ожидание загрузки WS
                await page.goto(PO_ENTRY_URL, timeout=PO_NAV_TIMEOUT_MS)
                await asyncio.sleep(1)  # даём WS окнектиться
                await asyncio.sleep(PO_IDLE_TIMEOUT_MS / 1000)  # ждём приход фреймов

                await browser.close()

                # Ищем первый подходящий фрейм с "candles"
                raw = []
                for url, payload in messages:
                    if PO_BROWSER_WS_URL.split("?")[0] in url and "candles" in payload:
                        # удаляем префикс socket.io (например '42')
                        try:
                            # payload вроде '42["candles",["EURUSD",15,[[...]]]]'
                            json_part = payload.lstrip("0123456789")
                            arr = pd.json.loads(json_part)
                            if arr[0] == "candles" and arr[1][0] == symbol and arr[1][1] == int(timeframe.rstrip("mHh")):
                                raw = arr[1][2]
                                break
                        except Exception:
                            continue

                if not raw:
                    return pd.DataFrame()

                df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                return df
