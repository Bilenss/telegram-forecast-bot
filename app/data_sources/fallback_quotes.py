from __future__ import annotations
import pandas as pd
import yfinance as yf

# Гибкий фолбэк на публичные котировки Yahoo Finance.
# Учитывает выходные/нерабочие часы: пробует несколько (interval, period).

_DEF_CANDIDATES = {
    "1m":  [("1m", "5d"), ("5m", "5d"), ("15m", "1mo"), ("1h", "3mo")],
    "2m":  [("2m", "5d"), ("5m", "5d"), ("15m", "1mo"), ("1h", "3mo")],
    "5m":  [("5m", "5d"), ("15m", "1mo"), ("1h", "3mo")],
    "15m": [("15m", "1mo"), ("1h", "3mo"), ("1d", "6mo")],
    "30m": [("30m", "1mo"), ("1h", "3mo"), ("1d", "6mo")],
    "1h":  [("1h", "3mo"), ("1d", "6mo")],
}

def _download(ticker: str, interval: str, period: str) -> pd.DataFrame | None:
    try:
        df = yf.download(tickers=ticker, interval=interval, period=period, progress=False)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower)
        needed = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[needed]
        df.index.name = "time"
        return df
    except Exception:
        return None

def fetch_yf_ohlc(ticker: str, interval: str = "5m", lookback: int = 600) -> pd.DataFrame | None:
    candidates = _DEF_CANDIDATES.get(interval, [(interval, "1mo"), ("1h", "3mo"), ("1d", "6mo")])
    for iv, period in candidates:
        df = _download(ticker, iv, period)
        if df is not None and not df.empty:
            return df.tail(lookback)
    return None
