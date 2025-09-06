# app/data_sources/pocketoption_scraper.py
from __future__ import annotations
import asyncio, contextlib, json, os, random, re, time
from typing import List, Literal, Optional
import pandas as pd

from ..config import (
    PO_ENABLE_SCRAPE, PO_PROXY, PO_PROXY_FIRST, PO_NAV_TIMEOUT_MS,
    PO_IDLE_TIMEOUT_MS, PO_WAIT_EXTRA_MS, PO_SCRAPE_DEADLINE,
    PO_BROWSER_ORDER, PO_ENTRY_URL, LOG_LEVEL
)
from ..utils.user_agents import UAS
from ..utils.logging import setup

logger = setup(LOG_LEVEL)

_TF_MAP = {
    "15s": ["15", "15s", "resolution=15", "period=15"],
    "30s": ["30", "30s", "resolution=30", "period=30"],
    "1m":  ["60", "1m", "resolution=60", "period=60"],
    "5m":  ["300", "5m", "resolution=300", "period=300"],
    "15m": ["900", "15m", "resolution=900", "period=900"],
    "1h":  ["3600", "1h", "resolution=3600", "period=3600"],
}

def _tf_tokens(tf: str) -> List[str]:
    return _TF_MAP.get(tf.lower(), _TF_MAP["15m"])

def _proxy_dict() -> Optional[dict]:
    if PO_PROXY and (PO_PROXY_FIRST or os.environ.get("PO_SCRAPE_PROXY_FIRST", "1") == "1"):
        return {"server": PO_PROXY}
    return None

def _looks_like_ohlc(data) -> Optional[pd.DataFrame]:
    try:
        if isinstance(data, dict) and all(k in data for k in ("t", "o", "h", "l", "c")):
            t, o, h, l, c = data["t"], data["o"], data["h"], data["l"], data["c"]
            if all(isinstance(x, list) for x in (t, o, h, l, c)) and len(t) > 20:
                df = pd.DataFrame({
                    "Date": pd.to_datetime(t, unit="s"),
                    "Open": o, "High": h, "Low": l, "Close": c
                })
                return df.set_index("Date").sort_index()

        if isinstance(data, dict) and isinstance(data.get("candles"), list):
            rows = data["candles"]
            if len(rows) > 20 and all(all(k in r for k in ("t", "o", "h", "l", "c")) for r in rows):
                df = pd.DataFrame([
                    {"Date": pd.to_datetime(r["t"], unit="s"), "Open": r["o"], "High": r["h"], "Low": r["l"], "Close": r["c"]}
                    for r in rows
                ])
                return df.set_index("Date").sort_index()

        if isinstance(data, list) and len(data) > 20 and isinstance(data[0], dict):
            ks = set(data[0].keys())
            if {"time", "open", "high", "low", "close"} <= ks:
                df = pd.DataFrame([
                    {"Date": pd.to_datetime(r["time"], unit="s"), "Open": r["open"], "High": r["high"], "Low": r["low"], "Close": r["close"]}
                    for r in data
                ])
                return df.set_index("Date").sort_index()
            if {"t", "o", "h", "l", "c"} <= ks:
                df = pd.DataFrame([
                    {"Date": pd.to_datetime(r["t"], unit="s"), "Open": r["o"], "High": r["h"], "Low": r["l"], "Close": r["c"]}
                    for r in data
                ])
                return df.set_index("Date").sort_index()
    except Exception as e:
        logger.debug(f"parse payload err: {e}")
    return None

# Для сбора WebSocket-данных со страницы (включая iframe)
collected_ws: List[List[dict]] = []

def _maybe_ohlc(payload: str) -> Optional[List[dict]]:
    try:
        j = json.loads(payload)
    except Exception:
        return None
    if isinstance(j, list) and j and isinstance(j[0], dict):
        keys = j[0].keys()
        if {"open", "high", "low", "close"} <= set(map(str.lower, keys)):
            return j
    if isinstance(j, dict) and {"open", "high", "low", "close"} <= set(map(str.lower, j.keys())):
        return [j]
    return None

def _attach_ws_listeners(page):
    def on_ws(ws):
        logger.debug(f"WS opened: {ws.url}")
        ws.on("framereceived", lambda ev: _on_frame(ev))
        ws.on("framesent",     lambda ev: _on_frame(ev))
    def _on_frame(ev):
        try:
            bars = _maybe_ohlc(ev["payload"])
            if bars:
                collected_ws.append(bars)
        except Exception:
            pass
    page.on("websocket", on_ws)

async def _dismiss_popups(page):
    texts = ["Accept", "I agree", "Allow all", "OK", "Принять", "Согласен", "Хорошо"]
    import re as _re
    for t in texts:
        try:
            btn = page.get_by_role("button", name=_re.compile(rf"\b{_re.escape(t)}\b", _re.I)).first
            if btn and await btn.count() > 0:
                await btn.click(timeout=800)
                await asyncio.sleep(0.1)
                logger.debug(f"Popup dismissed by button: {t}")
                break
        except:
            pass

async def _activate_symbol(page, symbol: str, otc: bool):
    logger.debug(f"Try activate symbol: {symbol} (otc={otc})")
    import re
    # Универсальный селектор активов (UI на английском)
    for sel in ['[data-testid="select-asset"]', 'button:has-text("Assets")']:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=1500)
                await asyncio.sleep(0.2)
                break
        except:
            pass

    variants = [symbol, symbol.replace("/", ""), symbol.replace("/", " / "), symbol.replace("/", "-")]
    if otc:
        variants += [f"{symbol} OTC", f"{symbol.replace('/', '')} OTC"]
    for v in variants:
        try:
            el = page.get_by_text(v, exact=True)
            if await el.count() > 0:
                await el.first.click(timeout=1000)
                await asyncio.sleep(0.2)
                logger.debug(f"Clicked symbol text: {v}")
                return True
        except:
            pass

    try:
        box = page.get_by_placeholder(re.compile("search", re.I)).first
        if await box.count() == 0:
            box = page.locator('input[type="search"]').first
        if await box.count() > 0:
            await box.click()
            await box.fill(symbol.replace("/", ""))
            await asyncio.sleep(0.2)
            await page.keyboard.press("Enter")
            logger.debug("Used search box to select symbol")
            return True
    except:
        pass

    return False

async def _set_timeframe(page, timeframe: str):
    logger.debug(f"Try set timeframe: {timeframe}")
    tf = timeframe.lower()
    import re

    aliases = {
        "15s": ["15s", "S15"],
        "30s": ["30s", "S30"],
        "1m":  ["1m", "m1", "M1", "1 min"],
        "5m":  ["5m", "m5", "M5", "5 min"],
        "15m": ["15m", "m15", "M15", "15 min"],
        "1h":  ["1h", "h1", "H1", "1 hour"],
    }
    look_for = aliases.get(tf, [tf])

    for label in look_for:
        for sel in [f'button:has-text("{label}")', f'text="{label}"']:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=1000)
                    await asyncio.sleep(0.3)
                    logger.debug(f"Clicked timeframe via alias: {label}")
                    return True
            except:
                pass

    return False

async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")

    from playwright.async_api import async_playwright

    ua = random.choice(UAS)
    collected: List[pd.DataFrame] = []
    deadline = time.time() + PO_SCRAPE_DEADLINE
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/en/cabinet/try-demo/"

    async with async_playwright() as p:
        for brand in [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]:
            browser, ctx, page = None, None, None
            try:
                browser = await getattr(p, brand).launch(headless=True, args=["--no-sandbox"])
                ctx_kwargs = {
                    "locale": "en-US",
                    "accept_downloads": True,
                    "ignore_https_errors": True,
                    "viewport": {"width": 1366, "height": 768},
                    "user_agent": ua,
                    "timezone_id": "Europe/London",
                    "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"}
                }
                prox = _proxy_dict()
                if prox:
                    ctx_kwargs["proxy"] = prox

                ctx = await browser.new_context(**ctx_kwargs)
                page = await ctx.new_page()
                _attach_ws_listeners(page)

                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(max(PO_IDLE_TIMEOUT_MS, PO_NAV_TIMEOUT_MS))

                await page.goto(entry_url, wait_until="commit")
                await asyncio.sleep(PO_WAIT_EXTRA_MS / 1000)

                await _dismiss_popups(page)
                await _activate_symbol(page, symbol, otc)
                await _set_timeframe(page, timeframe)

                inner_deadline = min(deadline, time.time() + 25)
                while time.time() < inner_deadline and not collected_ws:
                    # Poll iframe data and any accumulated WS frames
                    for fr in page.frames:
                        try:
                            payloads = await fr.evaluate(
                                "() => { const a = window.__po_frames__ || []; window.__po_frames__ = []; return a; }"
                            )
                            for p in payloads:
                                bars = _maybe_ohlc(p["data"] if isinstance(p, dict) else p)
                                if bars:
                                    collected_ws.append(bars)
                        except:
                            pass
                    await asyncio.sleep(0.25)

                await page.close()
                await ctx.close()
                await browser.close()

                if collected_ws:
                    break

            except Exception as e:
                logger.warning(f"Error in {brand} attempt: {e}")
                with contextlib.suppress(Exception):
                    await page.close()
                    await ctx.close()
                    await browser.close()

    if not collected_ws:
        raise RuntimeError("PocketOption: no OHLC captured within deadline")

    # Parse DataFrames and return the largest valid set
    dfs = [ _looks_like_ohlc(item) for batch in collected_ws for item in batch if _looks_like_ohlc(item) is not None ]
    best = max(dfs, key=len).dropna()
best = best.loc[~best.index.duplicated(keep='last')]
best = best.sort_index()

    if len(best) < 30:
        logger.warning(f"Captured only {len(best)} candles; signals may be unstable")

    return best
