# app/data_sources/pocketoption_scraper.py
from __future__ import annotations

import time
import random
import json
import re
from urllib.parse import urlparse

import pandas as pd
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from ..utils.user_agents import UAS
from ..utils.logging import setup
from ..config import (
    PO_PROXY,
    PO_SCRAPE_DEADLINE,
    PO_PROXY_FIRST,
    PO_NAV_TIMEOUT_MS,
    PO_IDLE_TIMEOUT_MS,   # оставим в конфиге, но ждать networkidle больше не будем
    PO_WAIT_EXTRA_MS,
    PO_HTTPX_TIMEOUT,
    PO_BROWSER_ORDER,
)

logger = setup()

KEYWORDS = (
    "candle", "candles", "ohlc", "ohlcv", "history",
    "chart", "series", "timeseries", "feed", "ticks",
    "tick", "quotes", "quote"
)

# -------------------- helpers --------------------

def _headers() -> dict:
    return {
        "User-Agent": random.choice(UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Referer": "https://pocketoption.com/",
    }

def _client() -> httpx.Client:
    proxies = {"http://": PO_PROXY, "https://": PO_PROXY} if PO_PROXY else None
    return httpx.Client(
        timeout=PO_HTTPX_TIMEOUT,
        headers=_headers(),
        proxies=proxies,
        follow_redirects=True,
    )

def _pw_proxy():
    if not PO_PROXY:
        return None
    u = urlparse(PO_PROXY)
    if not u.scheme or not u.hostname:
        return {"server": PO_PROXY}
    p = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        p["username"] = u.username
    if u.password:
        p["password"] = u.password
    return p

def _pw_launch_kwargs(use_proxy: bool) -> dict:
    kw: dict = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    if use_proxy:
        prox = _pw_proxy()
        if prox:
            kw["proxy"] = prox
            logger.debug(f"PO[pw] using proxy: {prox.get('server')}")
    return kw

def _asset_candidates(symbol: str, otc: bool) -> list[str]:
    base = symbol.upper().replace(" ", "").replace("/", "")
    cands = [base]
    if otc:
        cands += [
            f"{base}_OTC", f"{base}-OTC", f"{base}OTC",
            f"OTC_{base}", f"OTC-{base}", f"OTC{base}",
            f"{base}_otc", f"{base}-otc", f"{base}otc",
        ]
    low = base.lower()
    cands += [low, f"{low}_otc", f"{low}-otc", f"{low}otc",
              f"otc_{low}", f"otc-{low}", f"otc{low}"]
    seen, out = set(), []
    for s in cands:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def _parse_embedded_candles(text: str) -> pd.DataFrame | None:
    try:
        m = re.search(r"\[(?:\{[^\}]*\}\s*,\s*)*\{[^\}]*\}\]", text, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        rows = []
        for it in data:
            t = it.get("t") or it.get("time") or it.get("timestamp")
            o = it.get("o") or it.get("open")
            h = it.get("h") or it.get("high")
            l = it.get("l") or it.get("low")
            c = it.get("c") or it.get("close")
            if None in (t, o, h, l, c):
                continue
            ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int, float)) \
                 else pd.to_datetime(t, errors="coerce")
            if pd.isna(ts):
                continue
            rows.append([ts, float(o), float(h), float(l), float(c)])
        if not rows:
            return None
        return pd.DataFrame(rows, columns=["time", "Open", "High", "Low", "Close"]).set_index("time")
    except Exception:
        return None

def _collect_from_json_object(obj, rows: list):
    def find_list(x):
        if isinstance(x, list) and x and isinstance(x[0], dict):
            keys = set(map(str.lower, x[0].keys()))
            if {"o", "h", "l", "c"}.issubset(keys) or {"open", "high", "low", "close"}.issubset(keys):
                return x
        if isinstance(x, dict):
            for v in x.values():
                r = find_list(v)
                if r is not None:
                    return r
        if isinstance(x, list):
            for v in x:
                r = find_list(v)
                if r is not None:
                    return r
        return None

    items = find_list(obj)
    if not items:
        return
    for it in items:
        t = it.get("t") or it.get("time") or it.get("timestamp")
        o = it.get("o") or it.get("open")
        h = it.get("h") or it.get("high")
        l = it.get("l") or it.get("low")
        c = it.get("c") or it.get("close")
        try:
            ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int, float)) \
                 else pd.to_datetime(t, errors="coerce")
            if pd.isna(ts):
                continue
            rows.append([ts, float(o), float(h), float(l), float(c)])
        except Exception:
            continue

# -------------------- static try --------------------

def _try_static(asset: str, base_paths: list[str], limit: int, deadline_at: float) -> pd.DataFrame | None:
    with _client() as client:
        for tpl in base_paths:
            if time.time() > deadline_at:
                return None
            url = tpl.format(asset=asset)
            try:
                r = client.get(url)
                logger.debug(f"PO[static] GET {url} -> {r.status_code}")
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
                logger.debug(f"PO[static] failed {url}: {e}")
            time.sleep(0.3)
    return None

# -------------------- playwright --------------------

def _playwright_attempt_with_browser(pw, browser_name: str, asset: str, base_paths, limit, deadline_at, use_proxy: bool):
    rows = []

    launcher = getattr(pw, browser_name)
    browser = launcher.launch(**_pw_launch_kwargs(use_proxy))
    context = browser.new_context(
        user_agent=random.choice(UAS),
        locale="en-US",
        timezone_id="UTC",
        viewport={"width": 1280, "height": 800},
        java_script_enabled=True,
        service_workers="block",
        bypass_csp=True,
    )
    context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

    # Глушим только тяжёлое, XHR/WS/JS не трогаем.
    context.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "font", "stylesheet", "media") else r.continue_())

    page = context.new_page()
    page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
    page.set_default_timeout(PO_NAV_TIMEOUT_MS)

    def on_response(resp):
        # фильтр домена + ключевых слов в пути
        try:
            host = urlparse(resp.url).hostname or ""
        except Exception:
            return
        if not host.endswith("pocketoption.com"):
            return
        url_l = resp.url.lower()
        if not any(k in url_l for k in KEYWORDS):
            return
        # best-effort: json() либо text()->json
        try:
            payload = resp.json()
        except Exception:
            try:
                payload = json.loads(resp.text())
            except Exception:
                return
        _collect_from_json_object(payload, rows)
        logger.debug(f"PO[pw][{browser_name}] JSON {resp.url} -> parsed")

    page.on("response", on_response)

    try:
        for tpl in base_paths:
            if time.time() > deadline_at:
                break
            url = tpl.format(asset=asset)
            try:
                logger.debug(f"PO[pw][{browser_name}] goto {url}")
                # ждём максимум 'load', без networkidle (Cloudflare мешает)
                page.goto(url, wait_until="load", timeout=PO_NAV_TIMEOUT_MS)
                # даём окну ещё немного времени на XHR
                page.wait_for_timeout(PO_WAIT_EXTRA_MS)

                if rows:
                    break

                # запасной путь: вытащить возможный JSON из инлайновых <script>
                try:
                    html = page.content()
                    df_from_html = _parse_embedded_candles(html)
                    if df_from_html is not None and not df_from_html.empty:
                        context.close(); browser.close()
                        return df_from_html.tail(limit)
                except Exception:
                    pass

            except PWTimeout as e:
                logger.debug(f"PO[pw][{browser_name}] navigation timeout {url}: {e}")
            except Exception as e:
                logger.debug(f"PO[pw][{browser_name}] navigation failed {url}: {e}")
    finally:
        context.close()
        browser.close()

    if not rows:
        return None

    df = (
        pd.DataFrame(rows, columns=["time", "Open", "High", "Low", "Close"])
        .dropna()
        .drop_duplicates(subset=["time"])
        .sort_values("time")
        .set_index("time")
        .tail(limit)
    )
    return df if not df.empty else None

def _try_playwright(asset: str, base_paths: list[str], limit: int, deadline_at: float) -> pd.DataFrame | None:
    browser_order = [b.strip() for b in PO_BROWSER_ORDER.split(",") if b.strip()]
    direct_first = not PO_PROXY_FIRST
    proxy_order = [False, True] if direct_first else [True, False]

    with sync_playwright() as pw:
        for use_proxy in proxy_order:
            for bname in browser_order:
                if time.time() > deadline_at:
                    return None
                df = _playwright_attempt_with_browser(pw, bname, asset, base_paths, limit, deadline_at, use_proxy)
                if df is not None and not df.empty:
                    logger.debug(f"PO[pw] success via {'proxy' if use_proxy else 'direct'} on {bname}")
                    return df
                logger.debug(f"PO[pw] attempt failed on {bname} ({'proxy' if use_proxy else 'direct'})")
    return None

# -------------------- public API --------------------

__all__ = ["fetch_po_ohlc"]

def fetch_po_ohlc(symbol: str, timeframe: str = "5m", limit: int = 300, otc: bool = False) -> pd.DataFrame:
    base_paths_fin = [
        "https://pocketoption.com/en/chart/?asset={asset}",
        "https://pocketoption.com/ru/chart/?asset={asset}",
        "https://pocketoption.com/en/chart-new/?asset={asset}",
        "https://pocketoption.com/ru/chart-new/?asset={asset}",
        # торговые страницы иногда отдают свечи через XHR без авторизации
        "https://pocketoption.com/en/cabinet-2/trade/{asset}/",
        "https://pocketoption.com/en/cabinet/trade/{asset}/",
        "https://pocketoption.com/en/cabinet/trade_demo/{asset}/",
        "https://pocketoption.com/en/cabinet-2/trade_demo/{asset}/",
    ]
    base_paths_otc = base_paths_fin[::-1]  # для OTC приоритет trade-страниц

    base_paths = base_paths_otc if otc else base_paths_fin

    deadline_at = time.time() + PO_SCRAPE_DEADLINE
    candidates = _asset_candidates(symbol, otc=otc)
    logger.debug(f"PO candidates: {candidates}")

    for asset in candidates:
        if time.time() > deadline_at:
            break
        logger.debug(f"PO try asset={asset}")

        if otc:
            df = _try_playwright(asset, base_paths, limit, deadline_at)
            if df is not None and not df.empty:
                return df
            df = _try_static(asset, base_paths, limit, deadline_at)
            if df is not None and not df.empty:
                return df
        else:
            df = _try_static(asset, base_paths, limit, deadline_at)
            if df is not None and not df.empty:
                return df
            df = _try_playwright(asset, base_paths, limit, deadline_at)
            if df is not None and not df.empty:
                return df

    raise RuntimeError("PO scraping failed (no candles found)")
