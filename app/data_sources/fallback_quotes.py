from __future__ import annotations
import datetime as dt
from typing import Literal
import pandas as pd
import yfinance as yf

# Map timeframe label to yfinance interval and period
_INTERVAL = {
    "1m": ("1m", "2d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "60d"),
    "1h": ("60m", "730d"),
}
def _map_timeframe(tf: str) -> tuple[str,str]:
    tf = tf.lower()
    return _INTERVAL.get(tf, ("15m", "60d"))

def fetch_public_ohlc(yf_ticker: str, timeframe: Literal["1m","5m","15m","1h"]="15m", limit: int = 300) -> pd.DataFrame:
    interval, period = _map_timeframe(timeframe)
    data = yf.download(yf_ticker, interval=interval, period=period, progress=False)
    if data is None or data.empty:
        raise RuntimeError("No data from Yahoo Finance")
    data = data.rename(columns={"Open":"Open","High":"High","Low":"Low","Close":"Close"})
    data = data[["Open","High","Low","Close"]]
    # Trim to limit
    if len(data) > limit:
        data = data.tail(limit)
    data.index.name = "Date"
    return data
