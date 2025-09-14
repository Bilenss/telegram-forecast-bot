import pandas as pd
from ..config import PO_HTTP_API_URL
from .http_fetcher import HTTPFetcher
from .pocketoption_scraper import fetch_po_ohlc_async
from .po_interceptor import PocketOptionInterceptor
from .po_screenshot_ocr import ScreenshotAnalyzer

class PocketOptionFetcher:
    async def fetch(self, symbol, timeframe, otc=False):
        return await fetch_po_ohlc_async(symbol, timeframe, otc)

class InterceptorFetcher:
    def __init__(self):
        self._i = PocketOptionInterceptor()
    async def fetch(self, symbol, timeframe, otc=False):
        return await self._i.intercept_chart_data(symbol, timeframe, otc)

class OCRFetcher:
    def __init__(self):
        self._o = ScreenshotAnalyzer()
    async def fetch(self, symbol, timeframe, otc=False):
        return await self._o.capture_and_analyze(symbol, timeframe, otc)

class CompositeFetcher:
    def __init__(self):
        providers = {
            "http": HTTPFetcher(),
            "po":   PocketOptionFetcher(),
            "interceptor": InterceptorFetcher(),
            "ocr":  OCRFetcher(),
        }
        # HTTP-фетчер первым, если URL задан
        order = ["http"] if PO_HTTP_API_URL else []
        order += [k for k in ("po","interceptor","ocr") if k in providers]
        self.fetchers = [providers[k] for k in order]

    async def fetch(self, symbol, timeframe, otc=False) -> pd.DataFrame:
        for f in self.fetchers:
            df = await f.fetch(symbol, timeframe, otc)
            if df is not None and not df.empty:
                return df
        return pd.DataFrame()
