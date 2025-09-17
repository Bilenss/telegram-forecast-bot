import asyncio
import json
import pandas as pd
from playwright.async_api import async_playwright
from loguru import logger
import re

from ..config import PO_ENTRY_URL, PO_PROXY, PO_NAV_TIMEOUT_MS

class PocketOptionInterceptor:
    """
    Перехватывает реальные данные графиков PocketOption
    """
    def __init__(self):
        self.collected_data = []
        self.chart_data = None
        self.proxy_config = {"server": PO_PROXY} if PO_PROXY else None

    async def intercept_chart_data(self, symbol: str, timeframe: str, otc: bool = False) -> pd.DataFrame:
        """
        Запускает браузер и перехватывает данные графика
        """
        logger.info(f"Starting data interception for {symbol} {timeframe}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled'],
                    proxy=self.proxy_config
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                page.set_default_timeout(PO_NAV_TIMEOUT_MS)

                # Перехват сетевых запросов
                async def handle_route(route):
                    await route.continue_()

                # Перехват ответов
                async def handle_response(response):
                    url = response.url
                    patterns = ['candles', 'history', 'chart', 'ohlc', 'quotes', 'api/v', 'socket.io']
                    if any(p in url.lower() for p in patterns):
                        try:
                            data = await response.json()
                            if self._is_chart_data(data):
                                logger.info(f"📊 Found chart data in: {url}")
                                self.collected_data.append(data)
                        except Exception:
                            pass

                # Перехват WebSocket
                def handle_websocket(ws):
                    def on_frame(payload):
                        if isinstance(payload, str) and payload.startswith('42'):
                            try:
                                data = json.loads(payload[2:])
                                if self._is_chart_data(data):
                                    logger.info("📊 Found chart data in WebSocket")
                                    self.collected_data.append(data)
                            except:
                                pass
                    ws.on("framereceived", lambda e: on_frame(e.payload if hasattr(e, 'payload') else str(e)))

                await page.route("**/*", handle_route)
                page.on("response", handle_response)
                page.on("websocket", handle_websocket)

                # Формируем URL с символом и OTC-флагом
                base = PO_ENTRY_URL.rstrip("/") + "/"
                clean = symbol.replace("/", "").upper()
                if otc:
                    clean += "_otc"
                url = f"{base}#{clean}"
                logger.info(f"Navigating to: {url}")
                await page.goto(url, wait_until='networkidle')

                # Ждём загрузки графика
                await page.wait_for_selector('canvas, iframe, [class*="chart"]', timeout=PO_NAV_TIMEOUT_MS)
                await asyncio.sleep(3)

                # Пробуем получить chart.data через JS
                try:
                    chart_data = await page.evaluate("""
                        () => {
                            if (window.chart) return window.chart.data;
                            if (window.Chart) return window.Chart.data;
                            if (window.tvChart) return window.tvChart.data;
                            if (window.tradingView) return window.tradingView.activeChart?.data;
                            for (let key in window) {
                                if ((key.toLowerCase().includes('chart') || key.includes('Chart')) 
                                    && window[key]?.data) {
                                    return window[key].data;
                                }
                            }
                            return null;
                        }
                    """)
                    if chart_data:
                        logger.info("✅ Got chart data from JavaScript")
                        self.chart_data = chart_data
                except Exception as e:
                    logger.error(f"JS evaluation error: {e}")

                # Даем время на сбор данных
                await asyncio.sleep(5)

                # Кликаем по выбранному таймфрейму
                tf_selector = f'button:has-text("{timeframe}")'
                try:
                    if await page.locator(tf_selector).count() > 0:
                        await page.click(tf_selector)
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"Timeframe click error: {e}")

                await browser.close()

                # Обрабатываем данные
                if self.collected_data:
                    return self._process_collected_data()
                if self.chart_data:
                    return self._process_chart_data(self.chart_data)

                logger.warning("No data intercepted")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"Interceptor failed with fatal error: {e}")
            return pd.DataFrame()

    def _is_chart_data(self, data):
        # (тот же код)
        return isinstance(data, list) and len(data) > 0 and all(isinstance(i, list) and len(i) == 5 for i in data)

    def _process_collected_data(self):
        # (тот же код)
        if self.collected_data:
            # Flatten list of lists
            data_list = [item for sublist in self.collected_data if isinstance(sublist, list) for item in sublist]
            if not data_list:
                return pd.DataFrame()
            df = pd.DataFrame(data_list, columns=['timestamp', 'open', 'high', 'low', 'close'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            df = df.resample('1T').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last'
            }).dropna()
            return df
        return pd.DataFrame()

    def _process_chart_data(self, chart_data):
        # (тот же код)
        if chart_data:
            df = pd.DataFrame(chart_data)
            df.columns = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.drop('volume', axis=1, inplace=True)
            df.sort_index(inplace=True)
            return df
        return pd.DataFrame()

async def get_real_po_data(symbol: str, timeframe: str, otc: bool = False):
    interceptor = PocketOptionInterceptor()
    try:
        df = await interceptor.intercept_chart_data(symbol, timeframe, otc)
        if not df.empty:
            logger.info(f"✅ Got {len(df)} real candles from PocketOption")
            return df
        logger.warning("No data intercepted, using fallback")
        return None
    except Exception as e:
        logger.error(f"Interception failed: {e}")
        return None
