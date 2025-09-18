# app/data_sources/fetchers.py
import logging
import pandas as pd
from ..config import (
    PO_FETCH_ORDER,
    PO_USE_INTERCEPTOR,
    PO_USE_OCR,
    PO_USE_WS_FETCHER,
)
from .ws_fetcher import WebSocketFetcher
from .pocketoption_scraper import fetch_po_ohlc_async
from .po_interceptor import PocketOptionInterceptor
from .po_screenshot_ocr import ScreenshotAnalyzer

logger = logging.getLogger(__name__)

class PocketOptionFetcher:
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False):
        df = await fetch_po_ohlc_async(symbol, timeframe, otc)
        return df, "po"

class InterceptorFetcher:
    def __init__(self):
        self._i = PocketOptionInterceptor()
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False):
        df = await self._i.intercept_chart_data(symbol, timeframe, otc)
        return df, "interceptor"

class OCRFetcher:
    def __init__(self):
        self._o = ScreenshotAnalyzer()
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False):
        df = await self._o.capture_and_analyze(symbol, timeframe, otc)
        return df, "ocr"

class WebSocketWrapper:
    def __init__(self):
        self._w = WebSocketFetcher()
    async def fetch(self, symbol: str, timeframe: str, otc: bool=False):
        df = await self._w.fetch(symbol, timeframe, otc)
        return df, "ws"

class CompositeFetcher:
    def __init__(self):
        providers = {
            "ws":         WebSocketWrapper(),
            "po":         PocketOptionFetcher(),
            "interceptor": InterceptorFetcher(),
            "ocr":        OCRFetcher(),
        }
        order = []
        if PO_USE_WS_FETCHER:
            order.append("ws")
        order += [
            key for key in PO_FETCH_ORDER
            if key in providers
            and (key != "interceptor" or PO_USE_INTERCEPTOR)
            and (key != "ocr" or PO_USE_OCR)
        ]
        self.fetchers = [(k, providers[k]) for k in order]
        logger.debug("CompositeFetcher order: %s", [k for k,_ in self.fetchers])

    async def fetch(self, symbol: str, timeframe: str, otc: bool=False):
        """
        Returns: (df, source) where source is one of 'ws','po','interceptor','ocr' or 'generated'
        """
        for name, f in self.fetchers:
            try:
                logger.debug("Trying fetcher: %s for %s %s", name, symbol, timeframe)
                result = await f.fetch(symbol, timeframe, otc)
                if isinstance(result, tuple):
                    df, source = result
                else:
                    df, source = result, name
                if df is not None and not df.empty:
                    logger.info("Fetcher %s returned %d rows for %s %s", source, len(df), symbol, timeframe)
                    try:
                        logger.debug("Sample rows from %s:\n%s", source, df.head(3).to_dict(orient="records"))
                    except Exception as e:
                        logger.debug("Failed to serialize df head: %s", e)
                    return df, source
                else:
                    logger.warning("Fetcher %s returned empty for %s %s", name, symbol, timeframe)
            except Exception as e:
                logger.error("Fetcher %s error for %s %s: %s", name, symbol, timeframe, e)
        logger.info("All fetchers failed — returning empty DataFrame (will trigger realistic generator upstream)")
        return pd.DataFrame(), "generated"
