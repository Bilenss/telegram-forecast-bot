# app/data_sources/pocketoption_scraper.py
from __future__ import annotations
import asyncio, contextlib, json, os, random, re, time
from typing import List, Literal, Optional
import pandas as pd
from loguru import logger

from ..config import (
    PO_ENABLE_SCRAPE, PO_PROXY, PO_PROXY_FIRST, PO_NAV_TIMEOUT_MS,
    PO_IDLE_TIMEOUT_MS, PO_WAIT_EXTRA_MS, PO_SCRAPE_DEADLINE,
    PO_BROWSER_ORDER, PO_ENTRY_URL, LOG_LEVEL
)
from ..utils.user_agents import UAS
from ..utils.logging import setup

logger = setup(LOG_LEVEL)

def _proxy_dict() -> Optional[dict]:
    if PO_PROXY and (PO_PROXY_FIRST or os.environ.get("PO_SCRAPE_PROXY_FIRST", "1") == "1"):
        return {"server": PO_PROXY}
    return None

def _maybe_ohlc(payload: str):
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

def _attach_ws_listeners(page, collected_ws: list):
    def on_ws(ws):
        logger.debug(f"WS opened: {ws.url}")
        ws.on("framereceived", lambda ev: _on_frame(ev))
        ws.on("framesent", lambda ev: _on_frame(ev))

    def _on_frame(ev):
        try:
            bars = _maybe_ohlc(ev["payload"])
            if bars:
                collected_ws.append(pd.DataFrame(bars))
        except Exception:
            pass

    page.on("websocket", on_ws)

async def _dismiss_popups(page):
    texts = [
        "Accept", "I agree", "Agree", "Allow all", "OK", "Got it"
    ]
    import re as _re
    for t in texts:
        try:
            btn = page.get_by_role("button", name=_re.compile(rf"\b{_re.escape(t)}\b", _re.I)).first
            if await btn.count() > 0:
                await btn.click(timeout=800)
                await asyncio.sleep(0.1)
                break
        except Exception:
            pass

async def _activate_symbol(page, symbol: str, otc: bool):
    logger.debug(f"Try activate symbol: {symbol} (otc={otc})")

    for sel in [
        '[data-testid="select-asset"]',
        'button:has-text("Assets")',
        'button[aria-label*="Assets"]',
        'button:has(svg)',
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=1500)
                await asyncio.sleep(0.2)
                break
        except Exception:
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
        except Exception:
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
    except Exception:
        pass
    return False

async def _set_timeframe(page, timeframe: str):
    logger.debug(f"Try set timeframe: {timeframe}")
    tf = timeframe.lower()

    aliases = {
        "15s": ["15s", "S15"],
        "30s": ["30s", "S30"],
        "1m": ["1m", "m1", "M1", "1 min"],
        "5m": ["5m", "m5", "M5", "5 min"],
        "15m": ["15m", "m15", "M15", "15 min"],
        "1h": ["1h", "h1", "H1", "1 hour"],
    }
    look_for = aliases.get(tf, [tf])

    for label in look_for:
        for sel in [
            f'button:has-text("{label}")',
            f'text="{label}"',
        ]:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=1000)
                    await asyncio.sleep(0.3)
                    logger.debug(f"Clicked timeframe via alias: {label}")
                    return True
            except Exception:
                pass
    return False

async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")

    from playwright.async_api import async_playwright

    ua = random.choice(UAS)
    collected_ws: List[pd.DataFrame] = []
    deadline = time.time() + PO_SCRAPE_DEADLINE
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/en/cabinet/try-demo/"

    async with async_playwright() as p:
        for brand in [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]:
            browser = ctx = page = None
            try:
                browser = await getattr(p, brand).launch(headless=True)
                ctx_kwargs = {
                    "user_agent": ua,
                    "viewport": {"width": 1366, "height": 768},
                    "locale": "en-US",
                    "timezone_id": "Europe/London",
                }
                prox = _proxy_dict()
                if prox:
                    ctx_kwargs["proxy"] = prox

                ctx = await browser.new_context(**ctx_kwargs)
                page = await ctx.new_page()
                _attach_ws_listeners(page, collected_ws)

                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(max(PO_IDLE_TIMEOUT_MS, PO_NAV_TIMEOUT_MS))

                await page.goto(entry_url, wait_until="commit")
                await asyncio.sleep(PO_WAIT_EXTRA_MS / 1000.0)

                await _dismiss_popups(page)
                await _activate_symbol(page, symbol, otc)
                await _set_timeframe(page, timeframe)

                inner_deadline = min(deadline, time.time() + 25)

                while time.time() < inner_deadline and not collected_ws:
                    for fr in page.frames:
                        try:
                            payloads = await fr.evaluate(
                                "() => { const a = window.__po_frames__ || []; window.__po_frames__ = []; return a; }"
                            )
                            for p in payloads:
                                bars = _maybe_ohlc(p["data"] if isinstance(p, dict) else p)
                                if bars:
                                    collected_ws.append(pd.DataFrame(bars))
                        except Exception:
                            pass
                    await asyncio.sleep(0.25)

                await page.close()
                await ctx.close()
                await browser.close()

                if collected_ws:
                    break

            except Exception as e:
                logger.warning(f"Browser loop error: {e}")
                with contextlib.suppress(Exception):
                    if page: await page.close()
                with contextlib.suppress(Exception):
                    if ctx: await ctx.close()
                with contextlib.suppress(Exception):
                    if browser: await browser.close()

    # --- finalize OHLC -------------------------------------------------------
    dfs = [df for df in collected_ws if isinstance(df, pd.DataFrame) and not df.empty]

    if not dfs:
        raise RuntimeError("PocketOption: no OHLC captured within deadline")

    best = max(dfs, key=len).dropna()

    if not isinstance(best.index, pd.DatetimeIndex):
        best.index = pd.to_datetime(best.index, errors="coerce", utc=True)

    best = best.loc[~best.index.duplicated(keep="last")]
    best = best.sort_index()

    if len(best) < 30:
        logger.warning(f"Only {len(best)} bars captured for {symbol} {timeframe} (otc={otc})")

    return best
