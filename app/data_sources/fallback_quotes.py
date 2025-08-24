from __future__ import annotations
import os
import pandas as pd
import yfinance as yf
import requests
from loguru import logger

# Гибкий фолбэк Yahoo + дополнительный фолбэк Alpha Vantage (без логина, публично)

_DEF_CANDIDATES = {
    "1m":  [("1m", "5d"), ("5m", "5d"), ("15m", "1mo"), ("1h", "3mo")],
    "2m":  [("2m", "5d"), ("5m", "5d"), ("15m", "1mo"), ("1h", "3mo")],
    "5m":  [("5m", "5d"), ("15m", "1mo"), ("1h", "3mo")],
    "15m": [("15m", "1mo"), ("1h", "3mo"), ("1d", "6mo")],
    "30m": [("30m", "1mo"), ("1h", "3mo"), ("1d", "6mo")],
    "1h":  [("1h", "3mo"), ("1d", "6mo")],
}

def _download_yf(ticker: str, interval: str, period: str) -> pd.DataFrame | None:
    try:
        df = yf.download(tickers=ticker, interval=interval, period=period, progress=False)
        if df is None or df.empty:
            logger.info(f"Yahoo empty: {ticker} iv={interval} period={period}")
            return None
        df = df.rename(columns=str.lower)
        need = [c for c in ["open","high","low","close","volume"] if c in df.columns]
        df = df[need]
        df.index.name = "time"
        logger.info(f"Yahoo OK: {ticker} iv={interval} period={period} rows={len(df)}")
        return df
    except Exception as e:
        logger.warning(f"Yahoo error: {e}")
        return None

def fetch_yf_ohlc(ticker: str, interval: str = "5m", lookback: int = 600) -> pd.DataFrame | None:
    candidates = _DEF_CANDIDATES.get(interval, [(interval, "1mo"), ("1h", "3mo"), ("1d", "6mo")])
    for iv, period in candidates:
        df = _download_yf(ticker, iv, period)
        if df is not None and not df.empty:
            return df.tail(lookback)
    return None

# ---------- Alpha Vantage fallback ----------

_IV_MAP = {
    "1m": "5min",
    "2m": "5min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "60min",
}

def fetch_av_ohlc(pair: str, interval: str = "5m", lookback: int = 600) -> pd.DataFrame | None:
    """FX_INTRADAY Alpha Vantage: public intraday FX bars."""
    key = os.getenv("ALPHAVANTAGE_KEY")
    if not key:
        logger.info("AlphaVantage: no API key set")
        return None
    base = pair.replace(" OTC", "")
    if "/" not in base:
        return None
    from_sym, to_sym = base.split("/", 1)
    av_iv = _IV_MAP.get(interval, "15min")

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "FX_INTRADAY",
        "from_symbol": from_sym,
        "to_symbol": to_sym,
        "interval": av_iv,
        "outputsize": "compact",
        "datatype": "json",
        "apikey": key,
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        if "Note" in data:
            logger.warning(f"AlphaVantage rate limit: {data['Note'][:160]}")
            return None
        if "Error Message" in data:
            logger.error(f"AlphaVantage error: {data['Error Message'][:160]}")
            return None
        keyname = f"Time Series FX ({av_iv})"
        ts = data.get(keyname)
        if not ts:
            logger.info(f"AlphaVantage empty: {pair} iv={av_iv}")
            return None
        rows = []
        for t_s, ohlc in ts.items():
            rows.append([
                pd.to_datetime(t_s),
                float(ohlc.get("1. open", "nan")),
                float(ohlc.get("2. high", "nan")),
                float(ohlc.get("3. low", "nan")),
                float(ohlc.get("4. close", "nan")),
                0.0,
            ])
        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
        df = df.sort_values("time").set_index("time")
        df = df.tail(lookback).dropna()
        logger.info(f"AlphaVantage OK: {from_sym}/{to_sym} iv={av_iv} rows={len(df)}")
        return df
    except Exception as e:
        logger.warning(f"AlphaVantage error: {e}")
        return None
