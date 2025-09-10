import pandas as pd
from .pocketoption_scraper import fetch_po_ohlc_async
from .po_interceptor import intercept_chart_data
from .po_screenshot_ocr import ScreenshotAnalyzer
from ..config import PO_FETCH_ORDER, PO_USE_INTERCEPTOR, PO_USE_OCR

class PocketOptionFetcher:
    async def fetch(self, symbol, timeframe, otc=False) -> pd.DataFrame:
        return await fetch_po_ohlc_async(symbol, timeframe, otc)

class InterceptorFetcher:
    def __init__(self):
        from .po_interceptor import PocketOptionInterceptor
        self._i = PocketOptionInterceptor()

    async def fetch(self, symbol, timeframe, otc=False) -> pd.DataFrame:
        return await self._i.intercept_chart_data(symbol, timeframe, otc)

class OCRFetcher:
    def __init__(self):
        self._a = ScreenshotAnalyzer()

    async def fetch(self, symbol, timeframe, otc=False) -> pd.DataFrame:
        return await self._a.capture_and_analyze(symbol, timeframe, otc)

class CompositeFetcher:
    def __init__(self):
        providers = {
            "po": PocketOptionFetcher(),
            "interceptor": InterceptorFetcher(),
            "ocr": OCRFetcher(),
        }
        order = [o for o in PO_FETCH_ORDER
                 if o in providers and (o != "interceptor" or PO_USE_INTERCEPTOR)
                                and (o != "ocr" or PO_USE_OCR)]
        self.fetchers = [providers[o] for o in order]

    async def fetch(self, symbol, timeframe, otc=False) -> pd.DataFrame:
        for f in self.fetchers:
            df = await f.fetch(symbol, timeframe, otc)
            if df is not None and not df.empty:
                return df
        return pd.DataFrame()
