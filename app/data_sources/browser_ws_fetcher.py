# app/data_sources/browser_ws_fetcher.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from ..config import PO_BROWSER_WS_URL, PO_ENTRY_URL, PO_NAV_TIMEOUT_MS, PO_IDLE_TIMEOUT_MS

class BrowserWebSocketFetcher:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        """
        Подключаемся к PocketOption в headless браузере,
        перехватываем WebSocket-сообщения candles.
        """
        async with self._lock:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                page = await browser.new_page()
                messages = []

                # Перехват всех WS-сообщений, фильтруем по URL и по “candles”
                page.on("websocket", lambda ws: ws.on("framereceived", 
                    lambda frame: messages.append((ws.url, frame.payload))
                ))

                # Навигируем на демо-кабинет
                await page.goto(PO_ENTRY_URL, timeout=PO_NAV_TIMEOUT_MS)
                # Ждём, пока WS откроется
                await asyncio.sleep(1)

                # Эмулируем подписку на подсчет баров (точный код зависит от клиента PO)
                # Здесь мы просто используем тот же URL, он откроется автоматически при загрузке
                # Если нужно – можно прокинуть через page.evaluate JS-код подписки.

                # Ждём, пока придут сообщения
                await asyncio.sleep(PO_IDLE_TIMEOUT_MS / 1000)

                # Фильтруем нужный канал
                key = f"{symbol}_{timeframe}"
                raw = []
                for url, payload in messages:
                    if PO_BROWSER_WS_URL.split("?")[0] in url and "candles" in payload:
                        # payload – строка вида '42["candles",["AUDUSD",15,[[...]]]]'
                        try:
                            # убираем префикс Socket.IO '42'
                            j = payload.lstrip("42")
                            arr = pd.json.loads(j)
                            if arr[0] == "candles" and arr[1][0] == symbol and arr[1][1] == int(timeframe.rstrip("mHh")):
                                raw = arr[1][2]
                                break
                        except Exception:
                            continue

                await browser.close()

                if not raw:
                    return pd.DataFrame()

                df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                return df
