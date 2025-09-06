from __future__ import annotations
import os, json, time, math, re, random
from typing import Literal, List, Dict, Any, Optional
import pandas as pd

from ..config import (
    PO_ENABLE_SCRAPE, PO_PROXY, PO_PROXY_FIRST, PO_HTTPX_TIMEOUT,
    PO_NAV_TIMEOUT_MS, PO_IDLE_TIMEOUT_MS, PO_WAIT_EXTRA_MS, PO_SCRAPE_DEADLINE,
    PO_BROWSER_ORDER, LOG_LEVEL
)
from ..utils.user_agents import UAS
from ..utils.logging import setup

logger = setup(LOG_LEVEL)

# ---- Timeframe helpers ----
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

def _now_ts() -> int:
    return int(time.time())

def _try_parse_ohlc_payload(data: Any) -> Optional[pd.DataFrame]:
    """Try multiple common shapes used by TV-compatible endpoints."""
    try:
        # Shape A: { t:[...], o:[...], h:[...], l:[...], c:[...] }
        if isinstance(data, dict) and all(k in data for k in ("t","o","h","l","c")):
            t,o,h,l,c = data["t"], data["o"], data["h"], data["l"], data["c"]
            if all(isinstance(x, list) for x in (t,o,h,l,c)) and len(t)==len(o)==len(h)==len(l)==len(c) and len(t)>10:
                df = pd.DataFrame({"Date": pd.to_datetime(t, unit="s"), "Open": o, "High": h, "Low": l, "Close": c})
                df = df.set_index("Date").sort_index()
                return df

        # Shape B: { candles: [{t,o,h,l,c}, ...] }
        if isinstance(data, dict) and "candles" in data and isinstance(data["candles"], list) and len(data["candles"])>10:
            rows = data["candles"]
            if all(all(k in r for k in ("t","o","h","l","c")) for r in rows):
                df = pd.DataFrame([{"Date": pd.to_datetime(r["t"], unit="s"), "Open": r["o"], "High": r["h"], "Low": r["l"], "Close": r["c"]} for r in rows])
                df = df.set_index("Date").sort_index()
                return df

        # Shape C: list of {time/open/high/low/close}
        if isinstance(data, list) and len(data)>10 and isinstance(data[0], dict):
            keysets = [set(x.keys()) for x in data if isinstance(x, dict)]
            common = set.intersection(*keysets) if keysets else set()
            # Accept both short and long names
            if {"time","open","high","low","close"} <= common:
                df = pd.DataFrame([{"Date": pd.to_datetime(r["time"], unit="s"), "Open": r["open"], "High": r["high"], "Low": r["low"], "Close": r["close"]} for r in data])
                df = df.set_index("Date").sort_index()
                return df
            if {"t","o","h","l","c"} <= common:
                df = pd.DataFrame([{"Date": pd.to_datetime(r["t"], unit="s"), "Open": r["o"], "High": r["h"], "Low": r["l"], "Close": r["c"]} for r in data])
                df = df.set_index("Date").sort_index()
                return df
    except Exception as e:
        logger.debug(f"payload parse error: {e}")
    return None

def _url_looks_like_chart_api(url: str) -> bool:
    u = url.lower()
    # Heuristics for typical datafeed endpoints
    needles = ["chart", "charts", "history", "candles", "kline", "ohlc", "bars", "timeseries", "series", "marketdata", "feed"]
    return any(n in u for n in needles)

def _url_contains_symbol(url: str, symbol: str) -> bool:
    s = symbol.lower()
    u = url.lower()
    return (s in u) or (s.replace('/', '') in u) or (s.replace('_','') in u)

def _url_contains_tf(url: str, tf_tokens: List[str]) -> bool:
    u = url.lower()
    return any(tok in u for tok in tf_tokens)

def _pick_df(candidates: List[pd.DataFrame]) -> pd.DataFrame:
    # choose the one with longest length
    candidates = [df for df in candidates if isinstance(df, pd.DataFrame) and not df.empty]
    if not candidates:
        raise RuntimeError("No OHLC candidates collected")
    candidates.sort(key=lambda d: len(d), reverse=True)
    return candidates[0]

def _proxy_dict() -> Optional[dict]:
    if PO_PROXY and (PO_PROXY_FIRST or os.environ.get("PO_SCRAPE_PROXY_FIRST","1") == "1"):
        return {"server": PO_PROXY}
    return None

def fetch_po_ohlc(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    """
    Opens PocketOption trading page and passively collects XHR/fetch JSON that contains OHLC.
    Does NOT login. Tries to prefer endpoints that include requested symbol & timeframe in URL.
    """
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")

    # Lazy import to avoid Playwright overhead when disabled
    from playwright.sync_api import sync_playwright

    tf_tokens = _tf_tokens(timeframe)
    deadline = time.time() + PO_SCRAPE_DEADLINE
    ua = random.choice(UAS)

    # Heuristic list of entry URLs (fallbacks)
    entry_urls = [
        "https://pocketoption.com/en/trading/",
        "https://pocketoption.com/trading/",
        "https://pocketoption.com/",
    ]

    # Collector
    collected: List[pd.DataFrame] = []
    seen_urls = set()

    def _handle_response(resp):
        try:
            if resp.request.resource_type not in ("xhr","fetch"):
                return
        except Exception:
            return
        url = resp.url
        if url in seen_urls:
            return
        seen_urls.add(url)

        if not _url_looks_like_chart_api(url):
            return

        body_text = None
        try:
            # Some endpoints return JSON, others text
            body_text = resp.text()
        except Exception:
            try:
                body_text = resp.body().decode("utf-8","ignore")
            except Exception:
                return
        if not body_text:
            return

        # Fast prefilter by symbol/timeframe if present in URL
        sym_ok = _url_contains_symbol(url, symbol)
        tf_ok = _url_contains_tf(url, tf_tokens)
        if not (sym_ok or tf_ok):
            # still parse body; sometimes URL has no hint
            pass

        # Try parse JSON
        try:
            data = json.loads(body_text)
        except Exception:
            # Sometimes a JSON is wrapped or has junk -> try to find a JSON object/array substring
            m = re.search(r"(\{.*\}|\[.*\])", body_text, flags=re.S)
            if not m:
                return
            try:
                data = json.loads(m.group(1))
            except Exception:
                return

        df = _try_parse_ohlc_payload(data)
        if df is None:
            return

        # If URL shows wrong symbol/timeframe, keep but lower priority
        # We'll simply collect; the final picker chooses the longest
        collected.append(df)
        logger.debug(f"Captured OHLC from {url} rows={len(df)}")


    with sync_playwright() as p:
        browser_order = [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]
        browser = None
        ctx = None
        page = None
        last_err = None

        for brand in browser_order:
            try:
                if brand == "firefox":
                    browser = p.firefox.launch(headless=True)
                elif brand == "chromium":
                    browser = p.chromium.launch(headless=True, args=[
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ])
                elif brand == "webkit":
                    browser = p.webkit.launch(headless=True)
                else:
                    continue

                ctx_kwargs = {
                    "user_agent": ua,
                    "viewport": {"width": 1366, "height": 768},
                    "locale": "en-US",
                }
                prox = _proxy_dict()
                if prox:
                    ctx_kwargs["proxy"] = prox

                ctx = browser.new_context(**ctx_kwargs)

                page = ctx.new_page()
                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(max(PO_IDLE_TIMEOUT_MS, PO_NAV_TIMEOUT_MS))

                # Listen for network
                page.on("response", _handle_response)

                # Visit entry URLs until we start collecting
                for url in entry_urls:
                    try:
                        page.goto(url, wait_until="domcontentloaded")
                        # Give the page some time to boot widgets/requests
                        time.sleep(PO_WAIT_EXTRA_MS / 1000.0)
                        # Small random move/scroll to stimulate lazy loaders
                        page.mouse.move(random.randint(10,400), random.randint(10,400))
                        page.mouse.wheel(0, random.randint(100,600))
                        # Attempt to find any instrument area and click it to trigger data
                        # Best-effort: look for the symbol text (EURUSD or EUR/USD)
                        sym_variants = [symbol, symbol.replace("/", ""), symbol.replace("/"," / ")]
                        for sv in sym_variants:
                            try:
                                el = page.locator(f"text={sv}").first
                                if el and el.count() > 0:
                                    el.click(timeout=500)
                                    time.sleep(0.5)
                                    break
                            except Exception:
                                pass

                        # Wait loop until deadline or enough data captured
                        inner_deadline = min(deadline, time.time() + 10)
                        while time.time() < inner_deadline and len(collected) < 1:
                            time.sleep(0.25)

                        if collected:
                            break
                    except Exception as e:
                        last_err = e
                        continue

                # If still nothing, try a soft reload to trigger network again, until global deadline
                while time.time() < deadline and len(collected) < 1:
                    try:
                        page.reload(wait_until="domcontentloaded")
                        time.sleep(PO_WAIT_EXTRA_MS / 1000.0)
                        inner_deadline = time.time() + 5
                        while time.time() < inner_deadline and len(collected) < 1:
                            time.sleep(0.25)
                    except Exception as e:
                        last_err = e
                        break

                break  # exit browser brand loop if we reached here
            except Exception as e:
                last_err = e
                try:
                    if page: page.close()
                    if ctx: ctx.close()
                    if browser: browser.close()
                except Exception:
                    pass
                browser = None; ctx=None; page=None
                continue

        try:
            if page: page.close()
            if ctx: ctx.close()
            if browser: browser.close()
        except Exception:
            pass

    if not collected:
        raise RuntimeError(f"PocketOption: no OHLC captured within deadline ({PO_SCRAPE_DEADLINE}s){' with proxy' if _proxy_dict() else ''}. Last error: {last_err}")

    df = _pick_df(collected)

    # Basic sanity filter: drop NaNs, duplicates
    df = df.dropna().copy()
    df = df[~df.index.duplicated(keep='last')]

    # Ensure we return reasonable length
    if len(df) < 30:
        logger.warning(f"Captured only {len(df)} candles; signals may be unstable")

    return df
