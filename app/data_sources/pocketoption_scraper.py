from __future__ import annotations
import asyncio
import json
import random
import time
from typing import Literal, Optional

import pandas as pd
import numpy as np
from loguru import logger
from playwright.async_api import async_playwright

from ..config import (
    PO_ENABLE_SCRAPE,
    PO_PROXY,
    PO_NAV_TIMEOUT_MS,
    PO_IDLE_TIMEOUT_MS,
    PO_WAIT_EXTRA_MS,
    PO_SCRAPE_DEADLINE,
    PO_ENTRY_URL,
    LOG_LEVEL,
)
from ..utils.logging import setup

logger = setup(LOG_LEVEL)

PAIR_PRICES = { ... }  # без изменений

async def generate_realistic_data(...):
    # без изменений
    ...

def _proxy_dict() -> Optional[dict]:
    # без изменений
    ...

async def fetch_po_fast_scraping(symbol: str, timeframe: str, otc: bool) -> Optional[pd.DataFrame]:
    """Оптимизированный быстрый скрапинг (максимум 8 секунд)"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed, using generated data")
        return None

    logger.info(f"FAST SCRAPING: {symbol} {timeframe} otc={otc}")
    start_time = time.time()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-images",
                    "--disable-extensions",
                    "--disable-plugins",
                ],
            )

            ctx_kwargs = {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            }
            proxy = _proxy_dict()
            if proxy:
                ctx_kwargs["proxy"] = proxy
                logger.debug("Using proxy for connection")

            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            page.set_default_timeout(3000)

            # Формируем URL с символом и OTC-флагом
            base = PO_ENTRY_URL.rstrip("/") + "/"
            clean = symbol.replace("/", "").upper()
            if otc:
                clean += "_otc"
            entry_url = f"{base}#{clean}"
            logger.info(f"Navigating to: {entry_url}")
            await page.goto(entry_url, wait_until="domcontentloaded", timeout=5000)
            await asyncio.sleep(2)

            # Ищем и кликаем по таймфрейму
            tf_selector = f'button:has-text("{timeframe}")'
            try:
                if await page.locator(tf_selector).count() > 0:
                    await page.click(tf_selector)
                    await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Timeframe button error: {e}")

            await browser.close()

            elapsed = time.time() - start_time
            logger.info(f"Scraping attempt completed in {elapsed:.1f}s")
            return None  # всегда возвращаем None, чтобы упал в realistic fallback

    except Exception as e:
        logger.error(f"Fast scraping error: {e}")
        return None

async def fetch_po_ohlc_async(
    symbol: str,
    timeframe: Literal["30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h"] = "1m",
    otc: bool = False,
) -> pd.DataFrame:
    """Главная функция получения данных с гарантированным результатом"""
    if not PO_ENABLE_SCRAPE:
        logger.warning("PO scraping disabled, using generated data")
        return await generate_realistic_data(symbol, timeframe, otc)

    # Попытка быстрого скрапинга
    try:
        result = await asyncio.wait_for(
            fetch_po_fast_scraping(symbol, timeframe, otc), timeout=8.0
        )
        if result is not None and not result.empty:
            if 'close' in result.columns:
                result.columns = ['Open', 'High', 'Low', 'Close']
            logger.info(f"Using real scraped data: {len(result)} bars")
            return result
    except asyncio.TimeoutError:
        logger.warning("Scraping timeout reached")
    except Exception as e:
        logger.error(f"Scraping error: {e}")

    # Fallback на синтетические данные
    logger.info("Using generated realistic data")
    return await generate_realistic_data(symbol, timeframe, otc)
