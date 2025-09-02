from __future__ import annotations
import random, time, json, re
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
    base = symbol.upper()
    cands = [base]
    if otc:
        # Перебираем популярные варианты OTC-кода
        cands += [f"{base}_OTC", f"{base}-OTC", f"{base}OTC", f"{base}_otc", f"{base}-otc", f"{base}otc"]
    seen, out = set(), []
    for s in cands:
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def _parse_embedded_candles(text: str) -> pd.DataFrame | None:
    """Пробуем достать массив свечей из <script>."""
    try:
        # ищем любой JSON-массив объектов
        m = re.search(r'\[(?:\{[^\}]*\}\s*,\s*)*\{[^\}]*\}\]', text, re.S)
        if not m: 
            return None
        data = json.loads(m.group(0))
        rows = []
        for it in data:
            keys = {k.lower() for k in it.keys()}
            # поддерживаем варианты: t|time, o|open, h|high, l|low, c|close
            t = it.get("t") or it.get("time") or it.get("timestamp")
            o = it.get("o") or it.get("open")
            h = it.get("h") or it.get("high")
            l = it.get("l") or it.get("low")
            c = it.get("c") or it.get("close")
            if t is None or o is None or h is None or l is None or c is None:
                continue
            ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int,float)) else pd.to_datetime(t, errors="coerce")
            if pd.isna(ts): 
                continue
            rows.append([ts, float(o), float(h), float(l), float(c)])
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

def _try_playwright(asset: str, base_paths: list[str], limit: int) -> pd.DataFrame | None:
    """Открываем страницу в Chromium и перехватываем все JSON-ответы, ищем свечи."""
    rows = []

    def collect_from_json(obj):
        def find_list(x):
            # ищем список словарей с ключами свечей
            if isinstance(x, list) and x and isinstance(x[0], dict):
                keys = set(map(str.lower, x[0].keys()))
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
            o = it.get("o") or it.get("open")
            h = it.get("h") or it.get("high")
            l = it.get("l") or it.get("low")
            c = it.get("c") or it.get("close")
            try:
                ts = pd.to_datetime(t, unit="s", errors="coerce") if isinstance(t, (int,float)) else pd.to_datetime(t, errors="coerce")
                if pd.isna(ts): 
                    continue
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

        # Блокируем тяжелые ресурсы
        def route_handler(route):
            r = route.request
            if r.resource_type in ("image", "font", "stylesheet"):
                return route.abort()
            return route.continue_()
        context.route("**/*", route_handler)

        page = context.new_page()

        def on_response(resp):
            ctype = (resp.headers or {}).get("content-type", "")
            if "application/json" not in ctype.lower():
                return
            url = resp.url.lower()
            if any(k in url for k in ["candle", "candles", "ohlc", "history", "chart", "series"]):
                try:
                    j = resp.json()
                    collect_from_json(j)
                    logger.debug(f"PO[pw] JSON {url} -> ok")
                except Exception as e:
                    logger.debug(f"PO[pw] JSON parse fail {url}: {e}")

        page.on("response", on_response)
        page.on("requestfinished", lambda req: None)  # просто активируем событие

        for tpl in base_paths:
            url = tpl.format(asset=asset)
            try:
                logger.debug(f"PO[pw] goto {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_load_state("networkidle", timeout=20000)
                page.wait_for_timeout(3500)  # дать XHR добежать
                if rows:
                    break
            except Exception as e:
                logger.debug(f"PO[pw] navigation failed for {url}: {e}")

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
    Для OTC перебирает варианты кода + локали; если статикой не вышло — Playwright.
    """
    base_paths = [
        "https://pocketoption.com/en/chart/?asset={asset}",
        "https://pocketoption.com/ru/chart/?asset={asset}",
        # на всякий случай дополнительный путь
        "https://pocketoption.com/en/chart-new/?asset={asset}",
        "https://pocketoption.com/ru/chart-new/?asset={asset}",
    ]

    for asset in _asset_candidates(symbol, otc=otc):
        logger.debug(f"PO try asset={asset}")
        # 1) статикой
        df = _try_static(asset, base_paths, limit)
        if df is not None and not df.empty:
            return df
        # 2) Playwright
        df = _try_playwright(asset, base_paths, limit)
        if df is not None and not df.empty:
            return df

    raise RuntimeError("PO scraping failed (no candles found)")
