from __future__ import annotations
import random, time
import pandas as pd
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
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
    # убрать дубли, сохранить порядок
    seen, out = set(), []
    for s in cands:
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def _parse_embedded_candles(text: str) -> pd.DataFrame | None:
    """Пробуем достать массив свечей из встраиваемых <script>."""
    import re, json
    m = re.search(r'\[(?:\{[^\}]*\}\s*,\s*)*\{[^\}]*\}\]', text, re.S)
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
        return pd.DataFrame(rows, columns=["time","Open","High","Low","Close"]).set_index("time")
    except Exception:
        return None

def _try_static(asset: str, base_paths: list[str], limit: int) -> pd.DataFrame | None:
    with _client() as client:
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
                logger.debug(f"PO static request failed for {url}: {e}")
            time.sleep(random.uniform(0.2, 0.5))
    return None

def _try_playwright(asset: str, base_paths: list[str], limit: int) -> pd.DataFrame | None:
    """Открываем страницу в Chromium и перехватываем JSON-ответы со свечами."""
    rows = []

    def collect_from_json(obj):
        # рекурсивно ищем список словарей с ключами o/h/l/c (+ t|time|timestamp)
        def find_list(x):
            if isinstance(x, list) and x and isinstance(x[0], dict):
                keys = set(x[0].keys())
                if {"o","h","l","c"}.issubset(keys) or {"open","high","low","close"}.issubset(keys):
                    return x
            if isinstance(x, dict):
                for v in x.values():
                    r = find_list(v)
                    if r is not None: return r
            if isinstance(x, list):
                for v in x:
                    r = find_list(v)
                    if r is not None: return r
            return None

        items = find_list(obj)
        if not items: 
            return
        for it in items:
            t = it.get("t") or it.get("time") or it.get("timestamp")
            ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int,float)) else pd.to_datetime(t, errors="coerce")
            if ts is pd.NaT: 
                continue
            o = it.get("o") or it.get("open")
            h = it.get("h") or it.get("high")
            l = it.get("l") or it.get("low")
            c = it.get("c") or it.get("close")
            try:
                rows.append([ts, float(o), float(h), float(l), float(c)])
            except Exception:
                continue

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if PO_PROXY:
            launch_kwargs["proxy"] = {"server": PO_PROXY}
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(user_agent=random.choice(UAS), locale="en-US")
        page = context.new_page()

        def on_response(resp):
            ctype = (resp.headers or {}).get("content-type", "")
            if "application/json" not in ctype.lower():
                return
            url = resp.url.lower()
            if any(k in url for k in ["candle", "candles", "ohlc", "history", "chart"]):
                try:
                    collect_from_json(resp.json())
                except Exception:
                    pass

        page.on("response", on_response)

        for tpl in base_paths:
            url = tpl.format(asset=asset)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(4000)  # дать времени XHR запросам
                if rows:
                    break
            except Exception as e:
                logger.debug(f"Playwright navigation failed for {url}: {e}")

        context.close()
        browser.close()

    if not rows:
        return None

    df = (pd.DataFrame(rows, columns=["time","Open","High","Low","Close"])
            .dropna()
            .drop_duplicates(subset=["time"])
            .sort_values("time")
            .set_index("time")
            .tail(limit))
    return df if not df.empty else None

def fetch_po_ohlc(symbol: str, timeframe: str = "5m", limit: int = 300, otc: bool = False) -> pd.DataFrame:
    """Получает свечи с публичной страницы графика PocketOption.
    Для OTC перебирает варианты кода + локали; если статикой не вышло — используем Playwright.
    """
    base_paths = [
        "https://pocketoption.com/en/chart/?asset={asset}",
        "https://pocketoption.com/ru/chart/?asset={asset}",
    ]

    for asset in _asset_candidates(symbol, otc=otc):
        # 1) лёгкая попытка — парсинг встраиваемого JSON
        df = _try_static(asset, base_paths, limit)
        if df is not None and not df.empty:
            return df
        # 2) тяжёлая артиллерия — headless Chromium
        df = _try_playwright(asset, base_paths, limit)
        if df is not None and not df.empty:
            return df

    raise RuntimeError("PO scraping failed (no candles found)")
