from __future__ import annotations
import os, time, datetime as dt
import pandas as pd
import yfinance as yf
from ..utils.logging import setup

logger = setup()

def fetch_public_ohlc(ticker: str, timeframe: str = "15m", limit: int = 300) -> pd.DataFrame:
    # timeframe mapping for yfinance
    tf_map = {
        "15s": "1m",
        "30s": "1m",
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "60m",
    }
    interval = tf_map.get(timeframe, "15m")
    # period must cover enough points
    periods = {
        "1m": "2d",
        "5m": "5d",
        "15m": "30d",
        "60m": "90d",
    }
    period = periods.get(interval, "30d")
    logger.debug(f"YF download: {ticker} {interval} {period}")
    data = yf.download(tickers=ticker, interval=interval, period=period, progress=False)
    if data.empty:
        raise RuntimeError("No data from public source")
    df = data.rename(columns=str.title)[["Open", "High", "Low", "Close"]].tail(limit).copy()
    df.index = pd.to_datetime(df.index)
    return df
