from __future__ import annotations
import random, time
import pandas as pd
import httpx
from bs4 import BeautifulSoup
from ..utils.user_agents import UAS
from ..utils.logging import setup
from ..config import PO_PROXY

logger = setup()

def _headers():
    return {
        "User-Agent": random.choice(UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Referer": "https://pocketoption.com/",
    }

def _client():
    proxies = None
    if PO_PROXY:
        proxies = {"http://": PO_PROXY, "https://": PO_PROXY}
    return httpx.Client(timeout=20, headers=_headers(), proxies=proxies, follow_redirects=True)

def _asset_candidates(symbol: str, otc: bool):
    cands = [symbol]
    if otc:
        base = symbol.upper()
        cands += [f"{base}_OTC", f"{base}-OTC", f"{base}OTC", f"{base}_otc", f"{base}-otc", f"{base}otc"]
    # убираем дубли сохраняя порядок
    seen, out = set(), []
    for s in cands:
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def _parse_embedded_candles(text: str) -> pd.DataFrame | None:
    """
    Ищем в встраиваемых <script> JSON-массив свечей: [{"t":..,"o":..,"h":..,"l":..,"c":..}, ...]
    """
    import re, json
    m = re.search(r'\\[(?:\\{[^\\}]*\\}\\s*,\\s*)*\\{[^\\}]*\\}\\]', text, re.S)
    if not m: 
        return None
    try:
        data = json.loads(m.group(0))
        rows = []
        for it in data:
            t = pd.to_datetime(it.get("t") or it.get("time") or 0, unit="s")
            o,h,l,c = float(it["o"]), float(it["h"]), float(it["l"]), float(it["c"])
            rows.append([t,o,h,l,c])
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["time","Open","High","Low","Close"]).set_index("time")
        return df
    except Exception:
        return None

def fetch_po_ohlc(symbol: str, timeframe: str = "5m", limit: int = 300, otc: bool = False) -> pd.DataFrame:
    """
    Пытается получить свечи с публичной страницы графика PO.
    Для OTC перебирает несколько вариантов кода актива.
    """
    # страница графика на нескольких локалях
    base_paths = ["https://pocketoption.com/en/chart/?asset={asset}",
                  "https://pocketoption.com/ru/chart/?asset={asset}"]

    with _client() as client:
        for asset in _asset_candidates(symbol, otc=otc):
            for tpl in base_paths:
                url = tpl.format(asset=asset)
                try:
                    r = client.get(url)
                    if r.status_code == 404:
                        continue
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")
                    for sc in soup.find_all("script"):
                        txt = sc.string or sc.text or ""
                        df = _parse_embedded_candles(txt)
                        if df is not None and not df.empty:
                            return df.tail(limit)
                except httpx.HTTPError as e:
                    logger.debug(f"PO request failed for {url}: {e}")
                # небольшая задержка чтобы не палиться
                time.sleep(random.uniform(0.3, 0.8))
    raise RuntimeError("PO scraping failed (no candles found)")
