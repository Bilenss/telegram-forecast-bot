# app/data_sources/pocketoption_scraper.py
import logging
import pandas as pd
from playwright.async_api import async_playwright
import asyncio
from typing import Optional, Tuple
from ..config import (
    PO_PROXY,
    PO_PROXY_FIRST,
    PO_BROWSER_ORDER,
    PO_NAV_TIMEOUT_MS,
    PO_IDLE_TIMEOUT_MS,
    PO_WAIT_EXTRA_MS,
    PO_ENTRY_URL,
    PO_SCRAPE_DEADLINE,
)

logger = logging.getLogger(__name__)

async def fetch_po_ohlc_async(symbol: str, timeframe: str, otc: bool) -> Optional[pd.DataFrame]:
    """
    Scrapes OHLC data from PocketOption using Playwright.
    Returns a pandas DataFrame or None on failure.
    """
    try:
        if otc:
            url = f"{PO_ENTRY_URL}#{symbol.replace('_', '')}_otc"
        else:
            url = f"{PO_ENTRY_URL}#{symbol.replace('_', '')}_live"

        browser_type_name = PO_BROWSER_ORDER
        proxy_config = {"server": PO_PROXY} if PO_PROXY else None

        async with async_playwright() as p:
            logger.info(f"Using browser: {browser_type_name}")
            browser_type = getattr(p, browser_type_name)
            
            # Добавляем аргументы, чтобы выглядеть как реальный браузер
            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu',
                '--blink-settings=imagesEnabled=false' # Опционально, для ускорения
            ]

            browser = await browser_type.launch(
                headless=True,
                proxy=proxy_config,
                args=browser_args,
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', # Подменяем User-Agent
            )

            page = await context.new_page()

            # Увеличиваем таймаут для навигации
            page.set_default_timeout(PO_NAV_TIMEOUT_MS)

            try:
                logger.info(f"Navigating to: {url}")
                await page.goto(url, wait_until="domcontentloaded")
                
                # Добавляем задержку для имитации человеческого поведения
                await page.wait_for_timeout(PO_WAIT_EXTRA_MS)

                # Ждем, пока селектор с графиком не появится
                await page.wait_for_selector('canvas.trade-chart', timeout=PO_SCRAPE_DEADLINE * 1000)

                # Извлекаем данные, как и раньше
                # ... (Остальная часть кода для извлечения данных)
                
            except Exception as e:
                logger.error(f"Scraping error: {e}")
                return None
            finally:
                await browser.close()

    except Exception as e:
        logger.error(f"Playwright launch error: {e}")
        return None
