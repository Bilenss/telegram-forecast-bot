# app/data_sources/fetchers.py
import pandas as pd

from ..config import (
    PO_FETCH_ORDER,
    PO_USE_INTERCEPTOR,
    PO_USE_OCR,
    PO_USE_WS_FETCHER,
    PO_HTTP_API_URL,
)
from .pocketoption_scraper import fetch_po_ohlc_async
from .po_interceptor import PocketOptionInterceptor
from .po_screenshot_ocr import ScreenshotAnalyzer
from .ws_fetcher import WebSocketFetcher
from .http_fetcher import HTTPFetcher  # новый

class PocketOptionFetcher:
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        return await fetch_po_ohlc_async(symbol, timeframe, otc)

class InterceptorFetcher:
    def __init__(self):
        self._i = PocketOptionInterceptor()
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        return await self._i.intercept_chart_data(symbol, timeframe, otc)

class OCRFetcher:
    def __init__(self):
        self._o = ScreenshotAnalyzer()
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        return await self._o.capture_and_analyze(symbol, timeframe, otc)

class CompositeFetcher:
    def __init__(self):
        providers = {
            "http": HTTPFetcher(),
            "ws":   WebSocketFetcher(),
            "po":   PocketOptionFetcher(),
            "interceptor": InterceptorFetcher(),
            "ocr":  OCRFetcher(),
        }
        order = []
        # 1) HTTP API, если задан
        if PO_HTTP_API_URL:
            order.append("http")
        # 2) WS-fetcher, если включён
        if PO_USE_WS_FETCHER:
            order.append("ws")
        # 3) остальной порядок из конфигурации
        order += [
            key for key in PO_FETCH_ORDER
            if key in providers
            and (key != "interceptor" or PO_USE_INTERCEPTOR)
            and (key != "ocr"         or PO_USE_OCR)
        ]
        self.fetchers = [providers[k] for k in order]

    async def fetch(self, symbol: str, timeframe: str, otc: bool=False) -> pd.DataFrame:
        for f in self.fetchers:
            df = await f.fetch(symbol, timeframe, otc)
            if df is not None and not df.empty:
                return df
        return pd.DataFrame()
