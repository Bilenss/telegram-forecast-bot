from __future__ import annotations
import os
import pandas as pd
import yfinance as yf
import requests
from loguru import logger

# Глобальные заметки по последним попыткам (для /diag)
_last_notes: dict[str, str] = {}

def _note(src: str, msg: str) -> None:
    _last_notes[src] = msg

def get_last_notes() -> dict[str, str]:
    return dict(_last_notes)

# Заголовки для имитации браузера
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Кандидаты для Yahoo Finance
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
        yf.shared._requests_kwargs = {"headers": HEADERS, "timeout": 20}
        df = yf.download(tickers=ticker, interval=interval, period=period, progress=False)
        if df is None or df.empty:
            _note("yf", f"empty iv={interval} period={period}")
            logger.warning(f"Yahoo(yfinance) empty: {ticker} iv={interval} period={period}")
            return None
        df = df.rename(columns=str.lower)
        need = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[need]
        df.index.name = "time"
        _note("yf", f"ok iv={interval} period={period} rows={len(df)}")
        logger.info(f"Yahoo(yfinance) OK: {ticker} iv={interval} period={period} rows={len(df)}")
        return df
    except Exception as e:
        _note("yf", f"error {type(e).__name__}: {e}")
        logger.error(f"Yahoo(yfinance) error: {e}")
        return None

def fetch_yf_ohlc(ticker: str, interval: str = "5m", lookback: int = 600) -> pd.DataFrame | None:
    candidates = _DEF_CANDIDATES.get(interval, [(interval, "1mo"), ("1h", "3mo"), ("1d", "6mo")])
    for iv, period in candidates:
        df = _download_yf(ticker, iv, period)
        if df is not None and not df.empty:
            return df.tail(lookback)
    return None

# Yahoo Chart API
_YH_COMBOS = {
    "1m":  ["5d", "1mo"],
    "2m":  ["5d", "1mo"],
    "5m":  ["5d", "1mo"],
    "15m": ["1mo", "3mo"],
    "30m": ["1mo", "3mo"],
    "1h":  ["3mo", "6mo"],
}

def _download_yahoo_chart(ticker: str, interval: str, rang: str) -> pd.DataFrame | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"interval": interval, "range": rang, "includePrePost": "true"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        j = r.json()
        result = (j.get("chart") or {}).get("result")
        if not result:
            _note("yhd", f"empty result iv={interval} range={rang}")
            logger.info(f"Yahoo(chart) empty result: {ticker} iv={interval} range={rang}")
            return None
        res0 = result[0]
        ts = res0.get("timestamp")
        ind = (res0.get("indicators") or {}).get("quote")
        if not ts or not ind or not ind[0]:
            _note("yhd", f"missing series iv={interval} range={rang}")
            logger.info(f"Yahoo(chart) missing series: {ticker} iv={interval} range={rang}")
            return None
        q = ind[0]
        df = pd.DataFrame({
            "time": pd.to_datetime(ts, unit="s"),
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "close": q.get("close"),
            "volume": q.get("volume") or [0] * len(ts),
        })
        df = df.dropna().sort_values("time").set_index("time")
        _note("yhd", f"ok iv={interval} range={rang} rows={len(df)}")
        logger.info(f"Yahoo(chart) OK: {ticker} iv={interval} range={rang} rows={len(df)}")
        return df if not df.empty else None
    except Exception as e:
        _note("yhd", f"error {type(e).__name__}: {e}")
        logger.warning(f"Yahoo(chart) error: {e}")
        return None

def fetch_yahoo_direct_ohlc(ticker: str, interval: str = "15m", lookback: int = 600) -> pd.DataFrame | None:
    ranges = _YH_COMBOS.get(interval, ["1mo", "3mo"])
    for rang in ranges:
        df = _download_yahoo_chart(ticker, interval, rang)
        if df is not None and not df.empty:
            return df.tail(lookback)
    fallback = {"1m": "5m", "2m": "5m", "5m": "15m", "15m": "1h", "30m": "1h"}.get(interval)
    if fallback:
        ranges = _YH_COMBOS.get(fallback, ["1mo", "3mo"])
        for rang in ranges:
            df = _download_yahoo_chart(ticker, fallback, rang)
            if df is not None and not df.empty:
                return df.tail(lookback)
    return None

# Alpha Vantage
_IV_MAP = {
    "1m": "5min",
    "2m": "5min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "60min",
}

def fetch_av_ohlc(pair: str, interval: str = "5m", lookback: int = 600) -> pd.DataFrame | None:
    key = os.getenv("ALPHAVANTAGE_KEY")
    if not key:
        _note("av", "no_api_key")
        logger.info("AlphaVantage: no API key set")
        return None
    base = pair.replace(" OTC", "")
    if "/" not in base:
        _note("av", "bad_pair")
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
            _note("av", f"rate_limit: {data['Note'][:120]}")
            logger.warning(f"AlphaVantage rate limit: {data['Note'][:160]}")
            return None
        if "Error Message" in data:
            _note("av", f"error: {data['Error Message'][:120]}")
            logger.error(f"AlphaVantage error: {data['Error Message'][:160]}")
            return None
        keyname = f"Time Series FX ({av_iv})"
        ts = data.get(keyname)
        if not ts:
            _note("av", "empty_series")
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
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        df = df.sort_values("time").set_index("time").dropna()
        _note("av", f"ok iv={av_iv} rows={len(df)}")
        logger.info(f"AlphaVantage OK: {from_sym}/{to_sym} iv={av_iv} rows={len(df)}")
        return df.tail(lookback) if not df.empty else None
    except Exception as e:
        _note("av", f"error {type(e).__name__}: {e}")
        logger.warning(f"AlphaVantage error: {e}")
        return None
