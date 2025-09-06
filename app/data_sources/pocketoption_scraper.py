from __future__ import annotations
import os, json, time, re, random, asyncio
from typing import Literal, List, Optional
import pandas as pd
import contextlib

from ..config import (
    PO_ENABLE_SCRAPE, PO_PROXY, PO_PROXY_FIRST,
    PO_NAV_TIMEOUT_MS, PO_IDLE_TIMEOUT_MS, PO_WAIT_EXTRA_MS, PO_SCRAPE_DEADLINE,
    PO_BROWSER_ORDER, LOG_LEVEL
)
from ..utils.user_agents import UAS
from ..utils.logging import setup

logger = setup(LOG_LEVEL)

_TF_MAP = {
    "15s": ["15", "15s", "15-sec", "resolution=15", "period=15"],
    "30s": ["30", "30s", "30-sec", "resolution=30", "period=30"],
    "1m":  ["60", "1m", "1-min", "resolution=60", "period=60"],
    "5m":  ["300", "5m", "5-min", "resolution=300", "period=300"],
    "15m": ["900", "15m", "15-min", "resolution=900", "period=900"],
    "1h":  ["3600", "1h", "60-min", "resolution=3600", "period=3600"],
}
def _tf_tokens(tf: str) -> List[str]:
    tf = tf.lower()
    return _TF_MAP.get(tf, _TF_MAP["15m"])

def _proxy_dict() -> Optional[dict]:
    if PO_PROXY and (PO_PROXY_FIRST or os.environ.get("PO_SCRAPE_PROXY_FIRST","1") == "1"):
        return {"server": PO_PROXY}
    return None

def _looks_like_ohlc(data) -> Optional[pd.DataFrame]:
    try:
        if isinstance(data, dict) and all(k in data for k in ("t","o","h","l","c")):
            t,o,h,l,c = data["t"], data["o"], data["h"], data["l"], data["c"]
            if all(isinstance(x, list) for x in (t,o,h,l,c)) and len(t) > 20:
                df = pd.DataFrame({"Date": pd.to_datetime(t, unit="s"), "Open": o, "High": h, "Low": l, "Close": c})
                return df.set_index("Date").sort_index()

        if isinstance(data, dict) and "candles" in data and isinstance(data["candles"], list) and len(data["candles"])>20:
            rows = data["candles"]
            if all(all(k in r for k in ("t","o","h","l","c")) for r in rows):
                df = pd.DataFrame([{"Date": pd.to_datetime(r["t"], unit="s"), "Open": r["o"], "High": r["h"], "Low": r["l"], "Close": r["c"]} for r in rows])
                return df.set_index("Date").sort_index()

        if isinstance(data, list) and len(data)>20 and isinstance(data[0], dict):
            k = data[0].keys()
            if {"time","open","high","low","close"} <= set(k):
                df = pd.DataFrame([{"Date": pd.to_datetime(r["time"], unit="s"), "Open": r["open"], "High": r["high"], "Low": r["low"], "Close": r["close"]} for r in data])
                return df.set_index("Date").sort_index()
            if {"t","o","h","l","c"} <= set(k):
                df = pd.DataFrame([{"Date": pd.to_datetime(r["t"], unit="s"), "Open": r["o"], "High": r["h"], "Low": r["l"], "Close": r["c"]} for r in data])
                return df.set_index("Date").sort_index()
    except Exception as e:
        logger.debug(f"parse payload err: {e}")
    return None

def _url_hint_ok(url: str, symbol: str, tf_tokens: List[str]) -> bool:
    u = url.lower()
    s = symbol.lower().replace("/", "")
    any_sym = (symbol.lower() in u) or (s in u)
    any_tf = any(tok in u for tok in tf_tokens)
    needles = ["chart","charts","history","candles","ohlc","bars","series","kline","timeseries","feed","marketdata"]
    likely = any(n in u for n in needles)
    return likely and (any_sym or any_tf)

async def _activate_symbol(page, symbol: str, otc: bool):
    logger.debug(f"Try activate symbol: {symbol} (otc={otc})")
    variants = [symbol, symbol.replace("/", ""), symbol.replace("/", " / "), symbol.replace("/", "-")]
    if otc:
        variants += [f"{symbol} OTC", f"{symbol.replace('/', '')} OTC"]

    for v in variants:
        try:
            el = page.get_by_text(v, exact=True)
            if el and await el.count() > 0:
                await el.first.click(timeout=800)
                await asyncio.sleep(0.2)
                logger.debug(f"Clicked symbol text: {v}")
                return True
        except Exception:
            pass

    try:
        import re as _re
        input_box = page.get_by_placeholder(_re.compile("search", _re.I)).first
        if input_box:
            await input_box.click()
            await input_box.fill(symbol.replace("/", ""))
            await asyncio.sleep(0.2)
            await page.keyboard.press("Enter")
            logger.debug("Used search box to select symbol")
            return True
    except Exception:
        pass
    return False

async def _set_timeframe(page, timeframe: str):
    logger.debug(f"Try set timeframe: {timeframe}")
    tf_label = timeframe.lower()
    variants = [tf_label, tf_label.upper(), tf_label.replace("h","H")]
    import re as _re
    candidates = [
        page.get_by_role("button", name=_re.compile("|".join([_re.escape(v) for v in variants]))),
        page.get_by_text(_re.compile(rf"\b{_re.escape(tf_label)}\b", _re.I)),
    ]
    for cand in candidates:
        try:
            if cand and await cand.count() > 0:
                await cand.first.click(timeout=800)
                await asyncio.sleep(0.2)
                logger.debug(f"Clicked timeframe: {timeframe}")
                return True
        except Exception:
            pass

    try:
        interval_btn = page.get_by_role("button", name=_re.compile("interval|timeframe", _re.I)).first
        if interval_btn:
            await interval_btn.click(timeout=800)
            await asyncio.sleep(0.1)
            opt = page.get_by_text(_re.compile(rf"\b{_re.escape(tf_label)}\b", _re.I)).first
            if opt:
                await opt.click(timeout=800)
                await asyncio.sleep(0.2)
                logger.debug(f"Selected timeframe from menu: {timeframe}")
                return True
    except Exception:
        pass
    return False

async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")

    from playwright.async_api import async_playwright

    tf_tokens = _tf_tokens(timeframe)
    collected: List[pd.DataFrame] = []
    seen = set()

    async def handle_response(resp):
        url = resp.url
        if url in seen:
            return
        seen.add(url)
        if not _url_hint_ok(url, symbol, tf_tokens):
            return
        try:
            txt = await resp.text()
        except Exception:
            try:
                b = await resp.body()
                txt = b.decode("utf-8","ignore")
            except Exception:
                return
        if not txt:
            return
        try:
            data = json.loads(txt)
        except Exception:
            m = re.search(r"(\{.*\}|\[.*\])", txt, flags=re.S)
            if not m:
                return
            try:
                data = json.loads(m.group(1))
            except Exception:
                return
        df = _looks_like_ohlc(data)
        if df is not None:
            collected.append(df)
            logger.debug(f"Captured {len(df)} bars from {url}")

    deadline = time.time() + PO_SCRAPE_DEADLINE
    entry_urls = [
        "https://pocketoption.com/en/trading/",
        "https://www.pocketoption.com/en/trading/",
        "https://pocketoption.com/trading/",
        "https://www.pocketoption.com/trading/",
        "https://pocketoption.com/",
        "https://www.pocketoption.com/",
    ]
    ua = random.choice(UAS)

    async with async_playwright() as p:
        last_err = None
        for brand in [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]:
            browser = None; ctx=None; page=None
            try:
                if brand == "firefox":
                    browser = await p.firefox.launch(headless=True)
                elif brand == "chromium":
                    browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage","--no-sandbox"])
                elif brand == "webkit":
                    browser = await p.webkit.launch(headless=True)
                else:
                    continue
                ctx_kwargs = {"user_agent": ua, "viewport":{"width":1366,"height":768}, "locale":"en-US"}
                prox = _proxy_dict()
                if prox: ctx_kwargs["proxy"] = prox
                ctx = await browser.new_context(**{**ctx_kwargs, "accept_downloads": True, "ignore_https_errors": True})
        # Stealth-ish tweaks to lower bot detection
        await ctx.add_init_script("""
Object.defineProperty(navigator, "webdriver", {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, "languages", {get: () => ["en-US","en"]});
Object.defineProperty(navigator, "platform", {get: () => "Win32"});
Object.defineProperty(navigator, "plugins", {get: () => [1,2,3]});
        """)
                page = await ctx.new_page()
        page.on("download", lambda d: logger.debug(f"Download started: {getattr(d, \"suggested_filename\", None)}"))
                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(max(PO_IDLE_TIMEOUT_MS, PO_NAV_TIMEOUT_MS))

                # page.on callback must not await -> schedule
                page.on("response", lambda r: asyncio.create_task(handle_response(r)))

                for url in entry_urls:
                    try:
                        try:
                        await page.goto(url, wait_until="commit")
                    except Exception as e:
                        logger.warning(f"goto(commit) warning on {url}: {e}")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=PO_NAV_TIMEOUT_MS)
                    except Exception as e:
                        logger.warning(f"wait_for_load_state(domcontentloaded) warning on {url}: {e}")
                        await asyncio.sleep(PO_WAIT_EXTRA_MS/1000.0)
                        await _activate_symbol(page, symbol, otc)
                        await _set_timeframe(page, timeframe)

                        inner_deadline = min(deadline, time.time() + 12)
                        while time.time() < inner_deadline and (not collected or (len(collected[-1]) < 180)):
                            await asyncio.sleep(0.25)

                        if collected:
                            break
                    except Exception as e:
                        last_err = e
                        continue

                if collected:
                    with contextlib.suppress(Exception):
                        await page.close()
                    with contextlib.suppress(Exception):
                        await ctx.close()
                    with contextlib.suppress(Exception):
                        await browser.close()
                    break
                else:
                    with contextlib.suppress(Exception):
                        await page.close()
                    with contextlib.suppress(Exception):
                        await ctx.close()
                    with contextlib.suppress(Exception):
                        await browser.close()
            except Exception as e:
                last_err = e
                try:
                    if page: await page.close()
                except Exception: pass
                try:
                    if ctx: await ctx.close()
                except Exception: pass
                try:
                    if browser: await browser.close()
                except Exception: pass

    if not collected:
        raise RuntimeError(f"PocketOption: no OHLC captured within deadline ({PO_SCRAPE_DEADLINE}s). Last error: {last_err}")

    best = max(collected, key=lambda d: len(d))
    best = best.dropna()
    best = best[~best.index.duplicated(keep="last")]
    return best
