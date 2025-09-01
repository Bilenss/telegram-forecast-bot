from __future__ import annotations
import os
import re
import datetime as dt
import pandas as pd
import httpx
from ..utils.user_agents import UAS
from ..utils.logging import setup
from ..config import PO_PROXY, ALPHAVANTAGE_KEY

logger = setup()

def _client():
    headers = {
        "User-Agent": UAS[0],
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    proxies = None
    if PO_PROXY:
        proxies = {"http://": PO_PROXY, "https://": PO_PROXY}
    return httpx.Client(timeout=25, headers=headers, follow_redirects=True, proxies=proxies)

def _yf_interval_and_range(tf: str):
    tf = tf.lower()
    if tf in ("15s","30s"):   # Yahoo не отдаёт субминутные ТФ; подменим на 1m
        return "1m","2d"
    if tf == "1m":
        return "1m","2d"
    if tf == "5m":
        return "5m","5d"
    if tf == "15m":
        return "15m","30d"
    if tf == "1h":
        return "60m","90d"
    return "15m","30d"

def _parse_from_to(yf_ticker: str):
    # EURUSD=X -> EUR,USD  |  CADJPY=X -> CAD,JPY  |  JPY=X -> USD,JPY
    m = re.match(r"^([A-Z]{3})([A-Z]{3})=X$", yf_ticker)
    if m:
        return m.group(1), m.group(2)
    if yf_ticker == "JPY=X":
        return "USD","JPY"
    if yf_ticker.endswith("=X") and len(yf_ticker)==6:
        return "USD", yf_ticker[:3]
    raise ValueError(f"Can't parse ticker {yf_ticker}")

def _fetch_yahoo(yf_ticker: str, timeframe: str, limit: int) -> pd.DataFrame:
    interval, rng = _yf_interval_and_range(timeframe)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}?interval={interval}&range={rng}"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        data = r.json()
    try:
        res = data["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        df = pd.DataFrame({
            "time": pd.to_datetime(ts, unit="s"),
            "Open": q["open"],
            "High": q["high"],
            "Low": q["low"],
            "Close": q["close"],
        }).dropna()
        df = df.set_index("time").tail(limit)
        if df.empty:
            raise RuntimeError("Yahoo returned empty data")
        return df
    except Exception as e:
        raise RuntimeError(f"Yahoo parse failed: {e}")

def _fetch_alphavantage(yf_ticker: str, timeframe: str, limit: int) -> pd.DataFrame:
    if not ALPHAVANTAGE_KEY:
        raise RuntimeError("No AlphaVantage key")
    frm, to = _parse_from_to(yf_ticker)
    map_tf = {"15s":"1min","30s":"1min","1m":"1min","5m":"5min","15m":"15min","1h":"60min"}
    itv = map_tf.get(timeframe, "15min")
    url = ("https://www.alphavantage.co/query?function=FX_INTRADAY"
           f"&from_symbol={frm}&to_symbol={to}&interval={itv}&outputsize=compact&datatype=json&apikey={ALPHAVANTAGE_KEY}")
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        j = r.json()
    k = next((x for x in j.keys() if x.startswith("Time Series FX")), None)
    if not k:
        raise RuntimeError(f"AV error: {j.get('Note') or j.get('Error Message') or 'unknown'}")
    ts = j[k]
    rows = []
    for t, ohlc in sorted(ts.items()):
        rows.append([pd.to_datetime(t), float(ohlc["1. open"]), float(ohlc["2. high"]), float(ohlc["3. low"]), float(ohlc["4. close"])])
    df = pd.DataFrame(rows, columns=["time","Open","High","Low","Close"]).set_index("time").tail(limit)
    if df.empty:
        raise RuntimeError("AlphaVantage returned empty")
    return df

def fetch_public_ohlc(ticker: str, timeframe: str = "15m", limit: int = 300) -> pd.DataFrame:
    """Robust public quotes fetcher.
    Order of attempts:
        1) Yahoo Chart API (with UA/proxy)
        2) AlphaVantage (if ALPHAVANTAGE_KEY set)
    """
    last_err = None
    try:
        return _fetch_yahoo(ticker, timeframe, limit)
    except Exception as e:
        last_err = e
        logger.warning(f"Yahoo fallback failed: {e}")
    try:
        return _fetch_alphavantage(ticker, timeframe, limit)
    except Exception as e:
        last_err = e
        logger.error(f"AlphaVantage fallback failed: {e}")
    raise RuntimeError(f"No data from public source; last error: {last_err}")
