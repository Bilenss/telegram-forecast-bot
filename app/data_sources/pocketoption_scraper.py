from __future__ import annotations
import asyncio
import json
import re
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urlparse
import pandas as pd
from playwright.async_api import async_playwright
from ..utils.user_agents import random_ua
from ..config import settings
from ..utils.logging import logger

@asynccontextmanager
async def _browser():
    ua = random_ua()
    raw = settings.po_proxy
    proxy_cfg = None
    if raw:
        try:
            u = urlparse(raw)
            server = f"{u.scheme}://{u.hostname}:{u.port}"
            proxy_cfg = {"server": server}
            if u.username and u.password:
                proxy_cfg["username"] = u.username
                proxy_cfg["password"] = u.password
            logger.info(f"Using proxy: {server}")
        except Exception as e:
            logger.error(f"Error while parsing proxy: {e}")

    async with async_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        }
        if proxy_cfg:
            launch_kwargs["proxy"] = proxy_cfg
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=ua,
            locale="ru-RU",
            viewport={"width": 1366, "height": 768},
        )
        context.set_default_timeout(60000)
        context.set_default_navigation_timeout(90000)
        page = await context.new_page()
        try:
            yield page
        finally:
            await context.close()
            await browser.close()

async def fetch_po_ohlc(pair_slug: str, interval: str = "1m", lookback: int = 500) -> Optional[pd.DataFrame]:
    if not settings.po_enable_scrape:
        return None
    url = "https://pocketoption.com/ru/"
    try:
        async with _browser() as page:
            logger.info(f"Loading page: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1500)
            html = await page.content()
            logger.info("Page loaded successfully")
            m = re.search(r"\{[^{}]*\"candles\"\s*:\s*\[.*?\]\}", html, flags=re.DOTALL)
            if m:
                try:
                    blob = json.loads(m.group(0))
                    candles = blob.get("candles")
                    if candles:
                        df = pd.DataFrame(candles)[-lookback:]
                        cols = {c: c for c in ["open", "high", "low", "close", "volume"] if c in df.columns}
                        if "time" in df.columns and cols:
                            df = df.rename(columns=cols).set_index(pd.to_datetime(df["time"], unit="s"))
                            df.index.name = "time"
                            logger.info(f"Successfully parsed {len(df)} candles")
                            return df[["open", "high", "low", "close", "volume"]]
                except Exception as e:
                    logger.error(f"Failed to parse candles: {e}")
            else:
                logger.warning("No candles data found in HTML")
    except Exception as e:
        logger.error(f"Error while scraping PocketOption: {e}")

    return None
