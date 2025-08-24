from __future__ import annotations
import pandas as pd
import yfinance as yf
from datetime import timedelta

# Получить OHLC (UTC индекс) по тикеру Yahoo, интервал и глубина
# Возвращает DataFrame c колонками: open, high, low, close, volume

def fetch_yf_ohlc(ticker: str, interval: str = "1m", lookback: int = 500) -> pd.DataFrame | None:
    # yfinance периоды для мелких интервалов
    period = "1d" if interval in {"1m", "2m", "5m"} else "5d"
    try:
        df = yf.download(tickers=ticker, interval=interval, period=period, progress=False)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower)[["open","high","low","close","volume"]]
        df = df.tail(lookback)
        df.index.name = "time"
        return df
    except Exception:
        return None
