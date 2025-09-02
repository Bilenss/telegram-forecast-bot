from __future__ import annotations
import random, time, json, re
from urllib.parse import urlparse

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
    return httpx.Client(timeout=25, headers=_headers(), proxies=proxies, follow_redirects=True)


def _pw_proxy():
    if not PO_PROXY:
        return None
    u = urlparse(PO_PROXY)
    if not u.scheme or not u.hostname:
        return {"server": PO_PROXY}
    proxy = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        proxy["username"] = u.username
    if u.password:
        proxy["password"] = u.password
    return proxy


def _asset_candidates(symbol: str, otc: bool):
    base = symbol.upper().replace(" ", "").replace("/", "")
    cands = [base]
    if otc:
        cands += [
            f"{base}_OTC", f"{base}-OTC", f"{base}OTC",
            f"OTC_{base}", f"OTC-{base}", f"OTC{base}",
            f"{base}_otc", f"{base}-otc", f"{base}otc"
        ]
    seen, out = set(), []
    for s in cands:
        if s not in seen:
            seen.add(s); out.append(s)
    return out


def _parse_embedded_candles(text: str) -> pd.DataFrame | None:
    try:
        m = re.search(r'\[(?:\{[^\}]*\}\s*,\s*)*\{[^\}]*\}\]', text, re.S)
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
            ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int, float)) else pd.to_datetime(t, errors="coerce")
            if pd.isna(ts):
                continue
            rows.append([ts, float(o), float(h), float(l), float(c)])
        if not rows:
            return None
        return pd.DataFrame(rows, columns=["time", "Open", "High", "Low", "Close"]).set_index("time")
    except Exception:
        return None


def _try_static(asset: str, base_paths: list[str], limit: int) -> pd.DataFrame | None:
    with _client() as client:
        for tpl in base_paths:
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
            time.sleep(random.uniform(0.2, 0.5))
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
            ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int, float)) else pd.to_datetime(t, errors="coerce")
            if pd.isna(ts):
                continue
            rows.append([ts, float(o), float(h), float(l), float(c)])
        except Exception:
            continue


def _try_playwright(asset: str, base_paths: list[str], limit: int) -> pd.DataFrame | None:
    rows: list[list] = []

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ],
        }
        pwp = _pw_proxy()
        if pwp:
            launch_kwargs["proxy"] = pwp
            logger.debug(f"PO[pw] using proxy: {pwp.get('server')}")

        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=random.choice(UAS),
            locale="en-US",
            timezone_id="UTC",
            viewport={"width": 1280, "height": 800},
        )
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "font", "stylesheet", "media") else route.continue_())
        page = context.new_page()

        def on_response(resp):
            ctype = (resp.headers or {}).get("content-type", "").lower()
            if "application/json" not in ctype:
                return
            url = resp.url.lower()
            if any(k in url for k in ["candle", "candles", "ohlc", "history", "chart", "series", "timeseries"]):
                try:
                    j = resp.json()
                    _collect_from_json_object(j, rows)
                    logger.debug(f"PO[pw] JSON {url} -> parsed")
                except Exception as e:
                    logger.debug(f"PO[pw] JSON parse fail {url}: {e}")

        page.on("response", on_response)

        for tpl in base_paths:
            url = tpl.format(asset=asset)
            try:
                logger.debug(f"PO[pw] goto {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_load_state("networkidle", timeout=20000)
                page.wait_for_timeout(8000)

                if not rows:
                    try:
                        obj = page.evaluate("""(() => {
                          const bag = {};
                          for (const k of Object.getOwnPropertyNames(window)) {
                            if (!k || k.startsWith('_')) continue;
                            try { bag[k] = window[k]; } catch(e){}
                          }
                          return bag;
                        })()""")
                        _collect_from_json_object(obj, rows)
                    except Exception:
                        pass
                    try:
                        ls = page.evaluate("""(() => {
                          const out = {};
                          for (let i=0;i<localStorage.length;i++){
                            const k = localStorage.key(i);
                            out[k] = localStorage.getItem(k);
                          }
                          return out;
                        })()""")
                        for v in ls.values():
                            try:
                                j = json.loads(v)
                                _collect_from_json_object(j, rows)
                            except Exception:
                                continue
                    except Exception:
                        pass

                if rows:
                    break
            except Exception as e:
                logger.debug(f"PO[pw] navigation failed for {url}: {e}")

        context.close()
        browser.close()

    if not rows:
        return None

    df = (pd.DataFrame(rows, columns=["time", "Open", "High", "Low", "Close"])
          .dropna()
          .drop_duplicates(subset=["time"])
          .sort_values("time")
          .set_index("time")
          .tail(limit))
    return df if not df.empty else None


def fetch_po_ohlc(symbol: str, timeframe: str = "5m", limit: int = 300, otc: bool = False) -> pd.DataFrame:
    base_paths = [
        "https://pocketoption.com/en/chart/?asset={asset}",
        "https://pocketoption.com/ru/chart/?asset={asset}",
        "https://pocketoption.com/en/chart-new/?asset={asset}",
        "https://pocketoption.com/ru/chart-new/?asset={asset}",
    ]

    candidates = _asset_candidates(symbol, otc=otc)
    logger.debug(f"PO candidates: {candidates}")

    for asset in candidates:
        logger.debug(f"PO try asset={asset}")

        # 1) Static HTML
        df = _try_static(asset, base_paths, limit)
        if df is not None and not df.empty:
            return df

        # 2) Playwright (не падаем, если крашится)
        try:
            df = _try_playwright(asset, base_paths, limit)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"PO[pw] fatal on {asset}: {type(e).__name__}: {e}")
            continue

    raise RuntimeError("PO scraping failed (no candles found)")
