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

async def _dismiss_popups(page):
    texts = [
        "Accept", "I agree", "Agree", "Allow all", "OK", "Got it",
        "Принять", "Согласен", "Хорошо", "Понятно", "Разрешить все",
    ]
    import re as _re
    for t in texts:
        try:
            btn = page.get_by_role("button", name=_re.compile(rf"\b{_re.escape(t)}\b", _re.I)).first
            if btn and await btn.count() > 0:
                await btn.click(timeout=800); await asyncio.sleep(0.1)
                logger.debug(f"Popup dismissed by button: {t}")
                break
        except Exception:
            pass
    for t in texts:
        try:
            lnk = page.get_by_role("link", name=_re.compile(rf"\b{_re.escape(t)}\b", _re.I)).first
            if lnk and await lnk.count() > 0:
                await lnk.click(timeout=800); await asyncio.sleep(0.1)
                logger.debug(f"Popup dismissed by link: {t}")
                break
        except Exception:
            pass

async def _activate_symbol(page, symbol: str, otc: bool):
    logger.debug(f"Try activate symbol: {symbol} (otc={otc})")
    import re as _re
    # 0) Попробовать открыть панель выбора активов / поиск
    try:
        for cand in [
            page.get_by_role("button", name=_re.compile("(Актив|Активы|Assets|Asset|Поиск|Search)", _re.I)).first,
            page.locator('[data-testid="select-asset"]').first,
        ]:
            if cand and await cand.count() > 0:
                await cand.click(timeout=1000); await asyncio.sleep(0.2)
                break
    except Exception:
        pass

    # 1) Прямой клик по видимому тексту
    variants = [symbol, symbol.replace("/", ""), symbol.replace("/", " / "), symbol.replace("/", "-")]
    if otc:
        variants += [f"{symbol} OTC", f"{symbol.replace('/', '')} OTC"]
    for v in variants:
        try:
            el = page.get_by_text(v, exact=True)
            if el and await el.count() > 0:
                await el.first.click(timeout=800); await asyncio.sleep(0.2)
                logger.debug(f"Clicked symbol text: {v}")
                return True
        except Exception:
            pass

    # 2) Через поле поиска (RU/EN)
    try:
        box = page.get_by_placeholder(_re.compile("(search|поиск)", _re.I)).first
        if box and await box.count() > 0:
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
    import re as _re

    aliases = {
        "15s": ["15s", "15 sec", "15 сек", "15с", "S15"],
        "30s": ["30s", "30 sec", "30 сек", "30с", "S30"],
        "1m":  ["1m", "m1", "1 min", "1 мин", "1мин", "М1"],
        "5m":  ["5m", "m5", "5 min", "5 мин", "5мин", "М5"],
        "15m": ["15m", "m15", "15 min", "15 мин", "15мин", "М15"],
        "1h":  ["1h", "h1", "1 hour", "1 ч", "H1"],
    }
    look_for = aliases.get(tf, [tf])

    cands = []
    for label in look_for:
        cands.append(page.get_by_role("button", name=_re.compile(rf"\b{_re.escape(label)}\b", _re.I)))
        cands.append(page.get_by_text(_re.compile(rf"\b{_re.escape(label)}\b", _re.I)))

    for c in cands:
        try:
            if c and await c.count() > 0:
                await c.first.click(timeout=800); await asyncio.sleep(0.3)
                logger.debug(f"Clicked timeframe: {timeframe} via alias")
                return True
        except Exception:
            pass
    return False

def _try_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", s, flags=re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None

async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")

    from playwright.async_api import async_playwright

    ua = random.choice(UAS)
    collected: List[pd.DataFrame] = []
    collected_ws: List[pd.DataFrame] = []
    deadline = time.time() + PO_SCRAPE_DEADLINE
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/ru/cabinet/try-demo/"

    async with async_playwright() as p:
        for brand in [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]:
            browser = ctx = page = None
            try:
                if brand == "firefox":
                    browser = await p.firefox.launch(headless=True)
                elif brand == "chromium":
                    browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
                elif brand == "webkit":
                    browser = await p.webkit.launch(headless=True)
                else:
                    continue

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
                await ctx.add_init_script("""
window.__po_frames__ = [];
(function(){
  const OrigWS = window.WebSocket;
  window.WebSocket = function(url, prot){
    const ws = prot ? new OrigWS(url, prot) : new OrigWS(url);
    ws.addEventListener("message", function(ev){
      try {
        const push = s => { try { window.__po_frames__.push({t: Date.now(), data: s}); } catch(e){} };
        if (typeof ev.data === "string") push(ev.data);
        else if (ev.data instanceof Blob){ const r=new FileReader(); r.onload=()=>push(r.result); r.readAsText(ev.data); }
        else if (ev.data instanceof ArrayBuffer){ try{ push(new TextDecoder().decode(ev.data)); }catch(e){} }
      } catch(e){}
    });
    return ws;
  };
  window.WebSocket.prototype = OrigWS.prototype;
})();
                """)

                page = await ctx.new_page()
                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(max(PO_IDLE_TIMEOUT_MS, PO_NAV_TIMEOUT_MS))

                await page.goto(entry_url, wait_until="commit")
                await asyncio.sleep(PO_WAIT_EXTRA_MS / 1000.0)

                await _dismiss_popups(page)
                await _activate_symbol(page, symbol, otc)
                await _set_timeframe(page, timeframe)

                # изменённый блок с увеличенным тайм-аутом и сбором с ВСЕХ фреймов
                inner_deadline = min(deadline, time.time() + 25)

                while time.time() < inner_deadline and not (collected or collected_ws):
                    # Считать буфер кадров из КАЖДОГО фрейма страницы
                    frames_payload = []
                    for fr in page.frames:
                        try:
                            frames_payload.extend(await fr.evaluate(
                                "() => { const a = window.__po_frames__ || []; window.__po_frames__ = []; return a; }"
                            ))
                        except Exception:
                            pass

                    for frmsg in frames_payload:
                        data = _try_json(frmsg.get("data", ""))
                        df = _looks_like_ohlc(data)
                        if df is not None:
                            collected_ws.append(df)
                            logger.debug(f"Captured {len(df)} bars from WS[hook@frame])")

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

    all_sets = collected + collected_ws
    if not all_sets:
        raise RuntimeError(f"PocketOption: no OHLC captured within deadline ({PO_SCRAPE_DEADLINE}s)")

    best = max(all_sets, key=lambda d: len(d)).dropna()
    best = best[~best.index.duplicated(keep="last")]
    if len(best) < 30:
        logger.warning(f"Captured only {len(best)} candles; signals may be unstable")
    return best
