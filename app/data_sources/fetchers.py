import pandas as pd

from ..config import (
    PO_FETCH_ORDER,
    PO_USE_INTERCEPTOR,
    PO_USE_OCR,
    PO_USE_WS_FETCHER,
    PO_USE_BROWSER_WS,
)

from .pocketoption_scraper import fetch_po_ohlc_async
from .po_interceptor import PocketOptionInterceptor
from .po_screenshot_ocr import ScreenshotAnalyzer
from .ws_fetcher import WebSocketFetcher
from .browser_ws_fetcher import BrowserWebSocketFetcher  # новый импорт

class PocketOptionFetcher:
    async def fetch(self, symbol: str, timeframe: str, otc: bool = False) -> pd.DataFrame:
        return await fetch_po_ohlc_async(symbol, timeframe, otc)

class InterceptorFetcher:
    def __init__(self):
        self._i = PocketOptionInterceptor()

    async def fetch(self, symbol: str, timeframe: str, otc: bool = False) -> pd.DataFrame:
        return await self._i.intercept_chart_data(symbol, timeframe, otc)

class OCRFetcher:
    def __init__(self):
        self._o = ScreenshotAnalyzer()

    async def fetch(self, symbol: str, timeframe: str, otc: bool = False) -> pd.DataFrame:
        return await self._o.capture_and_analyze(symbol, timeframe, otc)

class CompositeFetcher:
    def __init__(self):
        providers = {
            "wsb": BrowserWebSocketFetcher(),  # Browser WebSocket
            "ws": WebSocketFetcher(),          # Raw WebSocket
            "po": PocketOptionFetcher(),       # DOM-скрапинг
            "interceptor": InterceptorFetcher(),
            "ocr": OCRFetcher(),
        }

        order = []
        if PO_USE_BROWSER_WS:
            order.append("wsb")  # приоритет Browser WS
        elif PO_USE_WS_FETCHER:
            order.append("ws")   # иначе обычный WS

        order += [
            key for key in PO_FETCH_ORDER
            if key in providers
            and (key != "interceptor" or PO_USE_INTERCEPTOR)
            and (key != "ocr" or PO_USE_OCR)
        ]

        self.fetchers = [providers[k] for k in order]

    async def fetch(self, symbol: str, timeframe: str, otc: bool = False) -> pd.DataFrame:
        for f in self.fetchers:
            df = await f.fetch(symbol, timeframe, otc)
            if df is not None and not df.empty:
                return df
        return pd.DataFrame()
