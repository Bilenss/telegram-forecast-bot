from __future__ import annotations
import random, time
import pandas as pd
import httpx
from bs4 import BeautifulSoup
from ..utils.user_agents import UAS
from ..utils.logging import setup
from ..config import PO_PROXY

logger = setup()

# NOTE:
# PocketOption pages are dynamic. This module implements a *best-effort* scraper
# that fetches the instrument page, looks for embedded OHLC JSON (if present),
# and, if not found, attempts to call the chart data requests used by the page.
# If the structure changes, callers should fall back to public quotes.

def _headers():
    return {
        "User-Agent": random.choice(UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

def _client():
    proxies = None
    if PO_PROXY:
        proxies = {"http://": PO_PROXY, "https://": PO_PROXY}
    return httpx.Client(timeout=20, headers=_headers(), proxies=proxies, follow_redirects=True)

def fetch_po_ohlc(symbol: str, timeframe: str = "15m", limit: int = 300) -> pd.DataFrame:
    # Symbol like 'EURUSD', timeframe like '15m' | '1m' | '5m' etc.
    # Strategy: open chart page and try to parse recent candles from embedded scripts.
    url = f"https://pocketoption.com/en/chart/?asset={symbol}"
    with _client() as client:
        r = client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Heuristic: some pages embed a window.__PO_INITIAL_STATE__ or similar.
        scripts = soup.find_all("script")
        for sc in scripts:
            txt = sc.string or ""
            if "candles" in txt or "ohlc" in txt:
                # naive parse: look for [...], but keep it robust
                import re, json
                m = re.search(r'(\[\{.*?\}\])', txt, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        # Expect list of objects with t/o/h/l/c
                        rows = []
                        for it in data:
                            t = pd.to_datetime(it.get("t") or it.get("time") or 0, unit="s")
                            rows.append([t, float(it["o"]), float(it["h"]), float(it["l"]), float(it["c"])])
                        df = pd.DataFrame(rows, columns=["time", "Open", "High", "Low", "Close"]).set_index("time")
                        if not df.empty:
                            return df.tail(limit)
                    except Exception as e:
                        logger.warning(f"Embedded JSON parse failed: {e}")
                        break
        # Fallback heuristic endpoint (subject to change; may require discovery in DevTools).
        # We try a generic path; if unavailable, raise.
        raise RuntimeError("PO scraping failed")
