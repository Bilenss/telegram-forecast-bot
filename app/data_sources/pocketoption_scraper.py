# app/data_sources/pocketoption_scraper.py
# Исправленные импорты
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

# Остальная часть файла остается без изменений...
(Ваш существующий код pocketoption_scraper.py)

# ---- Collectors ----
def _proxy_dict() -> Optional[dict]:
    if PO_PROXY and (PO_PROXY_FIRST or os.getenv("PO_SCRAPE_PROXY_FIRST", "1") == "1"):
        return {"server": PO_PROXY}
    return None

def _maybe_ohlc(payload: str):
    try:
        j = json.loads(payload)
    except Exception:
        return None
    def _is_bar(d: dict):
        ks = {k.lower() for k in d.keys()}
        return {"open","high","low","close"} <= ks and any(k in ks for k in ("time","timestamp","t","date"))
    if isinstance(j, list) and j and isinstance(j[0], dict) and _is_bar(j[0]):
        return j
    if isinstance(j, dict) and _is_bar(j):
        return [j]
    return None

def attach_collectors(page, context, sink_list):
    def on_ws(ws):
        logger.debug(f"WS opened: {ws.url}")
        def _on(ev):
            try:
                bars = _maybe_ohlc(ev["payload"])
                if bars:
                    sink_list.append(bars)
            except Exception:
                pass
        ws.on("framereceived", _on)
        ws.on("framesent", _on)
    page.on("websocket", on_ws)

    def on_resp(resp):
        try:
            url = resp.url.lower()
            if any(k in url for k in ("ohlc", "candl", "bar", "history", "chart")):
                if "application/json" in resp.headers.get("content-type", "").lower():
                    async def _read():
                        try:
                            j = await resp.json()
                            bars = _maybe_ohlc(json.dumps(j))
                            if bars:
                                sink_list.append(bars)
                        except Exception:
                            pass
                    context.loop.create_task(_read())
        except Exception:
            pass
    context.on("response", on_resp)

# ---- UI Interaction Helpers ----
async def _open_assets_and_pick(page, symbol: str, otc: bool) -> bool:
    logger.debug(f"Try activate symbol: {symbol} (otc={otc})")
    import re
    openers = [
        '[data-testid="select-asset"]',
        'button[aria-label*="Assets"]',
        'button:has-text("Assets")',
        'header button',
    ]
    opened = False
    for sel in openers:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=1500)
                await asyncio.sleep(0.25)
                opened = True
                break
        except Exception:
            pass

    if not opened:
        try:
            guess = page.locator("header, [role='toolbar']").locator("button")
            texts = await guess.all_inner_texts()
            for i, t in enumerate(texts[:6]):
                if re.search(r"[A-Z]{3}/?[A-Z]{3}", t or ""):
                    await guess.nth(i).click(timeout=1500)
                    await asyncio.sleep(0.25)
                    opened = True
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
                await el.first.click(timeout=1200)
                await asyncio.sleep(0.25)
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

    logger.warning("Asset picker: symbol not found via UI")
    return False

async def _pick_timeframe(page, timeframe: str) -> bool:
    logger.debug(f"Try set timeframe: {timeframe}")
    import re
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

    try:
        bar = page.locator("button", has_text=re.compile(r"\b(M|H|S)?\d+\b")).first
        if await bar.count() > 0:
            await bar.click(timeout=1000)
            await asyncio.sleep(0.2)
    except Exception:
        pass

    for label in look_for:
        for sel in [f'button:has-text("{label}")', f'text="{label}"']:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=1000)
                    await asyncio.sleep(0.3)
                    logger.debug(f"Clicked timeframe alias: {label}")
                    return True
            except Exception:
                pass

    logger.warning("Timeframe not clicked via UI")
    return False

# ---- Main Fetch Function ----
async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")

    from playwright.async_api import async_playwright

    ua = random.choice(UAS)
    collected = []
    deadline = time.time() + PO_SCRAPE_DEADLINE
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/en/cabinet/try-demo/"

    async with async_playwright() as p:
        for brand in [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]:
            browser = ctx = page = None
            try:
                browser = await getattr(p, brand).launch(headless=True, args=["--no-sandbox"])
                prox = _proxy_dict()
                ctx_kwargs = {
                    "locale": "en-US",
                    "accept_downloads": True,
                    "ignore_https_errors": True,
                    "viewport": {"width": 1366, "height": 768},
                    "user_agent": ua,
                    "timezone_id": "Europe/London",
                    "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"}
                }
                if prox:
                    ctx_kwargs["proxy"] = prox

                ctx = await browser.new_context(**ctx_kwargs)
                page = await ctx.new_page()
                attach_collectors(page, ctx, collected)

                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(max(PO_IDLE_TIMEOUT_MS, PO_NAV_TIMEOUT_MS))

                await page.goto(entry_url, wait_until="commit")
                await asyncio.sleep(PO_WAIT_EXTRA_MS / 1000)

                try:
                    await page.screenshot(path="/tmp/po_after_goto.png", full_page=True)
                    logger.info("Saved /tmp/po_after_goto.png")
                except:
                    pass

                ok = await _open_assets_and_pick(page, symbol, otc)
                ok_tf = await _pick_timeframe(page, timeframe)

                deadline_ts = time.time() + min(25, max(10, PO_SCRAPE_DEADLINE // 12))
                while time.time() < deadline_ts and not collected:
                    await asyncio.sleep(0.25)

                await page.close()
                await ctx.close()
                await browser.close()

                if collected:
                    break

            except Exception as e:
                logger.warning(f"Error in {brand}: {e}")
                with contextlib.suppress(Exception):
                    if page: await page.close()
                    if ctx: await ctx.close()
                    if browser: await browser.close()

    if not collected:
        raise RuntimeError("PocketOption: no OHLC captured within deadline")

    dfs = []
    for chunk in collected:
        try:
            df = pd.DataFrame(chunk).rename(columns=str.lower)
            for tk in ("time","timestamp","t","date"):
                if tk in df.columns:
                    df["time"] = pd.to_datetime(df[tk], unit="s", errors="coerce", utc=True) \
                                 if pd.api.types.is_numeric_dtype(df[tk]) \
                                 else pd.to_datetime(df[tk], errors="coerce", utc=True)
                    break
            df = df.set_index("time")[["open","high","low","close"]].astype(float).dropna()
            dfs.append(df)
        except Exception:
            pass

    if not dfs:
        raise RuntimeError("PocketOption: no parsable OHLC from transport")

    best = max(dfs, key=len).dropna()
    if not isinstance(best.index, pd.DatetimeIndex):
        best.index = pd.to_datetime(best.index, errors="coerce", utc=True)
    best = best.loc[~best.index.duplicated(keep="last")].sort_index()

    if len(best) < 30:
        logger.warning(f"Only {len(best)} bars captured for {symbol} {timeframe} (otc={otc})")

    return best
