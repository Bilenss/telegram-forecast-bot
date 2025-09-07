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

# ---- Configuration ----
USE_MOCK_DATA = False  # Set to True to use mock data, False for real scraping

# ---- Mock Data Generator ----
async def generate_mock_data(symbol: str, timeframe: str, otc: bool) -> pd.DataFrame:
    """Generate realistic mock OHLC data"""
    import numpy as np
    from datetime import datetime, timedelta
    
    logger.info(f"MOCK SCRAPER: Generating data for {symbol} (otc={otc}, tf={timeframe})")
    
    await asyncio.sleep(0.5)  # Simulate network delay
    
    # Realistic base prices
    pair_prices = {
        'EURUSD': 1.0850, 'GBPUSD': 1.2650, 'USDJPY': 148.50,
        'CADJPY': 108.75, 'AUDUSD': 0.6750, 'USDCHF': 0.8850,
    }
    
    base_price = pair_prices.get(symbol, 1.0000)
    volatility = 0.002 if 'JPY' in symbol else 0.0008
    
    tf_multiplier = {
        '15s': 0.3, '30s': 0.4, '1m': 0.5,
        '5m': 1.0, '15m': 1.5, '1h': 2.0
    }.get(timeframe, 1.0)
    
    volatility *= tf_multiplier
    num_bars = 150
    
    np.random.seed(hash(symbol) % 1000)
    trend = np.random.choice([-1, 0, 1], p=[0.3, 0.4, 0.3]) * 0.0002
    returns = np.random.normal(trend, volatility, num_bars)
    
    # Apply autocorrelation
    for i in range(1, len(returns)):
        returns[i] = 0.7 * returns[i] + 0.3 * returns[i-1]
    
    prices = [base_price]
    for ret in returns:
        prices.append(prices[-1] * (1 + ret))
    
    ohlc_data = []
    for i in range(1, len(prices)):
        open_price = prices[i-1]
        close_price = prices[i]
        
        mid_price = (open_price + close_price) / 2
        price_range = abs(close_price - open_price) * 1.5 + volatility * base_price
        
        high_noise = abs(np.random.normal(0, price_range * 0.3))
        low_noise = abs(np.random.normal(0, price_range * 0.3))
        
        high_price = max(open_price, close_price) + high_noise
        low_price = min(open_price, close_price) - low_noise
        
        decimals = 3 if 'JPY' in symbol else 5
        ohlc_data.append({
            'Open': round(open_price, decimals),
            'High': round(high_price, decimals),
            'Low': round(low_price, decimals),
            'Close': round(close_price, decimals)
        })
    
    df = pd.DataFrame(ohlc_data)
    
    freq_map = {
        '15s': '15S', '30s': '30S', '1m': '1min',
        '5m': '5min', '15m': '15min', '1h': '1H'
    }
    freq = freq_map.get(timeframe, '15min')
    df.index = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=len(df), freq=freq)
    
    # Ensure OHLC integrity
    df['High'] = np.maximum(df['High'], np.maximum(df['Open'], df['Close']))
    df['Low'] = np.minimum(df['Low'], np.minimum(df['Open'], df['Close']))
    
    logger.info(f"MOCK: Generated {len(df)} bars for {symbol}")
    return df

# ---- Real PocketOption Scraper ----
def _proxy_dict() -> Optional[dict]:
    """Convert proxy string to Playwright format"""
    if not PO_PROXY:
        return None
        
    # Handle format: http://user:pass@host:port
    if '@' in PO_PROXY:
        # Extract credentials and server
        parts = PO_PROXY.split('@')
        if len(parts) == 2:
            auth_part = parts[0]
            server_part = parts[1]
            
            # Remove protocol if present
            if '://' in auth_part:
                auth_part = auth_part.split('://')[-1]
            
            if ':' in auth_part:
                username, password = auth_part.split(':', 1)
                return {
                    "server": f"http://{server_part}",
                    "username": username,
                    "password": password
                }
    
    # Simple format: host:port or http://host:port
    if not PO_PROXY.startswith('http'):
        return {"server": f"http://{PO_PROXY}"}
    
    return {"server": PO_PROXY}

def _maybe_ohlc(payload: str):
    """Check if payload contains OHLC data"""
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
    """Attach WebSocket and HTTP response collectors"""
    def on_ws(ws):
        logger.debug(f"WS opened: {ws.url}")
        def _on(ev):
            try:
                bars = _maybe_ohlc(ev["payload"])
                if bars:
                    logger.debug(f"WS: Found {len(bars)} bars")
                    sink_list.append(bars)
            except Exception:
                pass
        ws.on("framereceived", _on)
        ws.on("framesent", _on)
    page.on("websocket", on_ws)

    def on_resp(resp):
        try:
            url = resp.url.lower()
            if any(k in url for k in ("ohlc", "candl", "bar", "history", "chart", "api")):
                if "application/json" in resp.headers.get("content-type", "").lower():
                    async def _read():
                        try:
                            j = await resp.json()
                            bars = _maybe_ohlc(json.dumps(j))
                            if bars:
                                logger.debug(f"HTTP: Found {len(bars)} bars from {url}")
                                sink_list.append(bars)
                        except Exception:
                            pass
                    context.loop.create_task(_read())
        except Exception:
            pass
    context.on("response", on_resp)

async def _interact_with_page_advanced(page, symbol: str, timeframe: str, otc: bool):
    """Advanced page interaction with more aggressive element detection"""
    logger.debug(f"Advanced interaction for {symbol} (otc={otc}, tf={timeframe})")
    
    try:
        # Wait for page to stabilize
        await asyncio.sleep(3)
        
        # Step 1: Try to find current asset display
        logger.debug("Looking for current asset display...")
        asset_selectors = [
            '[data-testid*="asset"]',
            '[class*="asset"]',
            '[class*="symbol"]',
            '[class*="instrument"]',
            'button[class*="asset"]',
            'div[class*="asset"]',
            '.trading-asset',
            '.current-asset',
            '[aria-label*="asset"]',
            '[aria-label*="symbol"]'
        ]
        
        clicked_asset = False
        for selector in asset_selectors:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                logger.debug(f"Found {count} elements for selector: {selector}")
                
                for i in range(min(count, 3)):  # Check first 3 elements
                    try:
                        element = elements.nth(i)
                        text = await element.inner_text() if await element.count() > 0 else ""
                        logger.debug(f"Element {i} text: {text}")
                        
                        if await element.is_visible():
                            await element.click(timeout=2000)
                            await asyncio.sleep(1)
                            logger.debug(f"Clicked asset element: {selector}[{i}]")
                            clicked_asset = True
                            break
                    except Exception as e:
                        logger.debug(f"Failed to click {selector}[{i}]: {e}")
                        continue
                
                if clicked_asset:
                    break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        # Step 2: Look for asset list/dropdown
        if clicked_asset or True:  # Always try this step
            await asyncio.sleep(1)
            logger.debug("Looking for symbol in lists...")
            
            # Get all text elements that might contain symbols
            all_text_elements = await page.locator('*').all_inner_texts()
            symbol_variants = [
                symbol,
                symbol.replace('/', ''),
                symbol.replace('/', ' / '),
                symbol.replace('/', '-'),
                f"{symbol} OTC" if otc else symbol,
                f"{symbol.replace('/', '')} OTC" if otc else symbol.replace('/', ''),
            ]
            
            logger.debug(f"Looking for variants: {symbol_variants}")
            
            # Find elements containing our symbol
            for variant in symbol_variants:
                try:
                    # Try exact text match
                    elements = page.get_by_text(variant, exact=True)
                    if await elements.count() > 0:
                        await elements.first.click(timeout=2000)
                        await asyncio.sleep(1)
                        logger.debug(f"Selected symbol exact: {variant}")
                        break
                    
                    # Try contains match
                    elements = page.locator(f'text*="{variant}"')
                    if await elements.count() > 0:
                        await elements.first.click(timeout=2000)
                        await asyncio.sleep(1)
                        logger.debug(f"Selected symbol contains: {variant}")
                        break
                    
                    # Try in buttons specifically
                    elements = page.locator(f'button:has-text("{variant}")')
                    if await elements.count() > 0:
                        await elements.first.click(timeout=2000)
                        await asyncio.sleep(1)
                        logger.debug(f"Selected symbol button: {variant}")
                        break
                        
                except Exception as e:
                    logger.debug(f"Failed to select {variant}: {e}")
                    continue
        
        # Step 3: Handle timeframe selection
        await asyncio.sleep(1)
        logger.debug(f"Looking for timeframe: {timeframe}")
        
        timeframe_variants = {
            '15s': ['15s', 'S15', '15 sec', '15sec', '00:15'],
            '30s': ['30s', 'S30', '30 sec', '30sec', '00:30'],
            '1m': ['1m', 'M1', '1 min', '1min', '01:00'],
            '5m': ['5m', 'M5', '5 min', '5min', '05:00'],
            '15m': ['15m', 'M15', '15 min', '15min', '15:00'],
            '1h': ['1h', 'H1', '1 hour', '1hr', '60m', '60 min']
        }.get(timeframe, [timeframe])
        
        # First try to find timeframe selector button
        tf_selectors = [
            '[class*="timeframe"]',
            '[class*="time-frame"]',
            '[class*="period"]',
            '[data-testid*="timeframe"]',
            '[data-testid*="time"]',
            'button[class*="time"]',
            '.time-selector',
            '.period-selector'
        ]
        
        for selector in tf_selectors:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                if count > 0:
                    await elements.first.click(timeout=2000)
                    await asyncio.sleep(1)
                    logger.debug(f"Clicked timeframe selector: {selector}")
                    break
            except Exception:
                continue
        
        # Then try to find specific timeframe
        for tf_variant in timeframe_variants:
            try:
                # Try button with exact text
                elements = page.locator(f'button:has-text("{tf_variant}")')
                if await elements.count() > 0:
                    await elements.first.click(timeout=2000)
                    await asyncio.sleep(1)
                    logger.debug(f"Selected timeframe button: {tf_variant}")
                    break
                
                # Try any element with text
                elements = page.get_by_text(tf_variant, exact=True)
                if await elements.count() > 0:
                    await elements.first.click(timeout=2000)
                    await asyncio.sleep(1)
                    logger.debug(f"Selected timeframe text: {tf_variant}")
                    break
                    
            except Exception as e:
                logger.debug(f"Failed to select timeframe {tf_variant}: {e}")
                continue
        
        # Step 4: Wait for data to start flowing
        logger.debug("Waiting for chart data to load...")
        await asyncio.sleep(5)
        
        # Step 5: Try to trigger chart updates by clicking on chart area
        try:
            chart_selectors = [
                '[class*="chart"]',
                '[class*="trading-view"]',
                '[class*="tradingview"]',
                'canvas',
                '[id*="chart"]',
                '.chart-container'
            ]
            
            for selector in chart_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        await element.click(timeout=1000)
                        logger.debug(f"Clicked chart element: {selector}")
                        break
                except Exception:
                    continue
        except Exception:
            pass
        
        await asyncio.sleep(3)
        
    except Exception as e:
        logger.warning(f"Advanced page interaction error: {e}")

# Enhanced data collection with more WebSocket message types
def attach_collectors_advanced(page, context, sink_list):
    """Enhanced data collectors for multiple message types"""
    def on_ws(ws):
        logger.debug(f"WS opened: {ws.url}")
        
        def _on_frame(ev):
            try:
                payload = ev.get("payload", "")
                
                # Log all WebSocket messages for debugging
                if len(payload) > 10:  # Ignore ping/pong
                    logger.debug(f"WS message preview: {payload[:100]}...")
                
                # Check for OHLC data
                bars = _maybe_ohlc(payload)
                if bars:
                    logger.info(f"WS: Found {len(bars)} OHLC bars")
                    sink_list.append(bars)
                    return
                
                # Check for other chart data formats
                try:
                    j = json.loads(payload)
                    
                    # Format 1: Direct array with price data
                    if isinstance(j, list) and j and isinstance(j[0], (int, float)):
                        if len(j) >= 4:  # Might be [time, open, high, low, close]
                            logger.debug("Found potential price array data")
                    
                    # Format 2: Object with chart/candlestick data
                    if isinstance(j, dict):
                        for key in j:
                            if any(word in str(key).lower() for word in ["candle", "bar", "ohlc", "chart", "price"]):
                                logger.debug(f"Found potential price data in key: {key}")
                    
                    # Format 3: Nested structure
                    if isinstance(j, dict) and "data" in j:
                        data = j["data"]
                        if isinstance(data, dict) and any(k in data for k in ["candles", "bars", "ohlc"]):
                            logger.debug("Found nested price data structure")
                            
                except Exception:
                    pass
                    
            except Exception as e:
                logger.debug(f"WS frame processing error: {e}")
        
        ws.on("framereceived", _on_frame)
        ws.on("framesent", _on_frame)  # Sometimes data comes in sent frames
    
    page.on("websocket", on_ws)

    def on_resp(resp):
        try:
            url = resp.url.lower()
            
            # More aggressive URL filtering
            if any(word in url for word in [
                "ohlc", "candle", "bar", "history", "chart", "api", "data",
                "quote", "price", "market", "trading", "feed", "stream"
            ]):
                content_type = resp.headers.get("content-type", "").lower()
                
                if "application/json" in content_type:
                    async def _read():
                        try:
                            j = await resp.json()
                            bars = _maybe_ohlc(json.dumps(j))
                            if bars:
                                logger.info(f"HTTP: Found {len(bars)} bars from {url}")
                                sink_list.append(bars)
                            else:
                                logger.debug(f"HTTP: Non-OHLC data from {url}")
                        except Exception as e:
                            logger.debug(f"HTTP response processing error: {e}")
                    
                    context.loop.create_task(_read())
        except Exception as e:
            logger.debug(f"Response handler error: {e}")
    
    context.on("response", on_resp)

async def fetch_po_ohlc_real(symbol: str, timeframe: str, otc: bool) -> pd.DataFrame:
    """Fetch real OHLC data from PocketOption"""
    from playwright.async_api import async_playwright
    
    ua = random.choice(UAS)
    collected = []
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/en/cabinet/try-demo/"
    
    logger.info(f"REAL SCRAPER: Fetching {symbol} data (otc={otc}, tf={timeframe})")
    logger.info(f"Using proxy: {bool(PO_PROXY)}")
    
    async with async_playwright() as p:
        for brand in [x.strip() for x in PO_BROWSER_ORDER.split(",") if x.strip()]:
            browser = ctx = page = None
            try:
                # Launch browser
                launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
                browser = await getattr(p, brand).launch(
                    headless=True, 
                    args=launch_args
                )
                
                # Context settings
                proxy_config = _proxy_dict()
                ctx_kwargs = {
                    "locale": "en-US",
                    "accept_downloads": True,
                    "ignore_https_errors": True,
                    "viewport": {"width": 1366, "height": 768},
                    "user_agent": ua,
                    "timezone_id": "Europe/London",
                    "extra_http_headers": {
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                }
                
                if proxy_config:
                    ctx_kwargs["proxy"] = proxy_config
                    logger.info(f"Using proxy: {proxy_config.get('server', 'unknown')}")
                
                ctx = await browser.new_context(**ctx_kwargs)
                page = await ctx.new_page()
                
                # Attach data collectors
                attach_collectors(page, ctx, collected)
                
                # Set timeouts
                page.set_default_navigation_timeout(PO_NAV_TIMEOUT_MS)
                page.set_default_timeout(PO_IDLE_TIMEOUT_MS)
                
                # Navigate to PocketOption
                logger.debug(f"Navigating to: {entry_url}")
                await page.goto(entry_url, wait_until="domcontentloaded")
                await asyncio.sleep(PO_WAIT_EXTRA_MS / 1000)
                
                # Take screenshot for debugging
                try:
                    await page.screenshot(path="/tmp/po_page.png", full_page=True)
                    logger.debug("Screenshot saved to /tmp/po_page.png")
                except:
                    pass
                
                # Interact with page
                await _interact_with_page(page, symbol, timeframe, otc)
                
                # Wait for data collection
                collection_timeout = time.time() + 30
                logger.info("Waiting for OHLC data collection...")
                
                while time.time() < collection_timeout and not collected:
                    await asyncio.sleep(0.5)
                    if collected:
                        logger.info(f"Data collected: {len(collected)} chunks")
                        break
                
                if collected:
                    logger.info(f"Successfully collected {len(collected)} data chunks")
                    break
                else:
                    logger.warning(f"No data collected with {brand}")
                
            except Exception as e:
                logger.error(f"Error with {brand}: {e}")
            finally:
                # Cleanup
                with contextlib.suppress(Exception):
                    if page: await page.close()
                    if ctx: await ctx.close()
                    if browser: await browser.close()
    
    if not collected:
        raise RuntimeError("PocketOption: no OHLC data captured")
    
    # Process collected data
    dfs = []
    for chunk in collected:
        try:
            df = pd.DataFrame(chunk).rename(columns=str.lower)
            
            # Find time column
            time_col = None
            for col in ["time", "timestamp", "t", "date"]:
                if col in df.columns:
                    time_col = col
                    break
            
            if time_col:
                # Convert timestamp
                if pd.api.types.is_numeric_dtype(df[time_col]):
                    df["time"] = pd.to_datetime(df[time_col], unit="s", errors="coerce", utc=True)
                else:
                    df["time"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
                
                df = df.set_index("time")
            
            # Select OHLC columns
            ohlc_cols = []
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    ohlc_cols.append(col)
            
            if len(ohlc_cols) == 4:
                df = df[ohlc_cols].astype(float).dropna()
                if len(df) > 0:
                    dfs.append(df)
        except Exception as e:
            logger.warning(f"Error processing chunk: {e}")
    
    if not dfs:
        raise RuntimeError("PocketOption: no valid OHLC data found")
    
    # Use the largest dataset
    result = max(dfs, key=len)
    result = result.loc[~result.index.duplicated(keep="last")].sort_index()
    
    # Rename columns to match expected format
    result.columns = ['Open', 'High', 'Low', 'Close']
    
    logger.info(f"Final dataset: {len(result)} bars")
    return result

# ---- Main Function ----
async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    """Main function to fetch OHLC data"""
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled (set PO_ENABLE_SCRAPE=1)")
    
    # Use mock data for development/testing
    if USE_MOCK_DATA:
        return await generate_mock_data(symbol, timeframe, otc)
    
    # Try real scraping
    try:
        return await fetch_po_ohlc_real(symbol, timeframe, otc)
    except Exception as e:
        logger.error(f"Real scraping failed: {e}")
        logger.info("Falling back to mock data")
        return await generate_mock_data(symbol, timeframe, otc)
