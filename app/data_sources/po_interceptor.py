# app/data_sources/po_interceptor.py
"""
Перехват реальных данных с PocketOption через браузер
"""
import asyncio
import json
import pandas as pd
from playwright.async_api import async_playwright
from loguru import logger
import re

class PocketOptionInterceptor:
    """
    Перехватывает реальные данные графиков PocketOption
    """
    
    def __init__(self):
        self.collected_data = []
        self.chart_data = None
    
    async def intercept_chart_data(self, symbol: str, timeframe: str, otc: bool = False) -> pd.DataFrame:
        """
        Запускает браузер и перехватывает данные графика
        """
        logger.info(f"Starting data interception for {symbol} {timeframe}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,  # Можно сделать True после отладки
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
            )
            
            page = await context.new_page()
            
            # Перехватываем сетевые запросы
            async def handle_route(route):
                request = route.request
                url = request.url
                
                # Логируем все запросы к API
                if any(x in url for x in ['api', 'socket', 'chart', 'candle', 'history']):
                    logger.debug(f"API Request: {url}")
                
                await route.continue_()
            
            # Перехватываем ответы
            async def handle_response(response):
                url = response.url
                
                # Ищем данные графиков в ответах
                patterns = [
                    'candles', 'history', 'chart', 'ohlc', 
                    'quotes', 'api/v', 'socket.io'
                ]
                
                if any(pattern in url.lower() for pattern in patterns):
                    try:
                        content_type = response.headers.get('content-type', '')
                        if 'json' in content_type or 'application/json' in content_type:
                            data = await response.json()
                            
                            # Проверяем, похоже ли на OHLC данные
                            if self._is_chart_data(data):
                                logger.info(f"📊 Found chart data in: {url}")
                                self.collected_data.append(data)
                                
                    except Exception as e:
                        pass
            
            # Перехват WebSocket сообщений
            def handle_websocket(ws):
                logger.info(f"WebSocket connected: {ws.url}")
                
                def on_frame(payload):
                    # Парсим socket.io сообщения
                    if isinstance(payload, str):
                        # Socket.io формат: "42[event,data]"
                        if payload.startswith('42'):
                            try:
                                json_str = payload[2:]  # Убираем "42"
                                data = json.loads(json_str)
                                
                                if self._is_chart_data(data):
                                    logger.info("📊 Found chart data in WebSocket")
                                    self.collected_data.append(data)
                                    
                            except:
                                pass
                
                ws.on("framereceived", lambda e: on_frame(e.payload if hasattr(e, 'payload') else str(e)))
            
            # Устанавливаем обработчики
            await page.route("**/*", handle_route)
            page.on("response", handle_response)
            page.on("websocket", handle_websocket)
            
            # Переходим на PocketOption
            url = "https://pocketoption.com/en/cabinet/demo-quick-high-low/"
            if symbol:
                # Добавляем символ в URL
                clean_symbol = symbol.replace('/', '').upper()
                if otc:
                    clean_symbol += "_otc"
                url += f"#{clean_symbol}"
            
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until='networkidle')
            
            # Ждем загрузки графика
            await page.wait_for_selector('canvas, iframe, [class*="chart"]', timeout=10000)
            await asyncio.sleep(3)
            
            # Пробуем программно получить данные через консоль браузера
            try:
                chart_data = await page.evaluate("""
                    () => {
                        // Ищем объект графика в window
                        if (window.chart) return window.chart.data;
                        if (window.Chart) return window.Chart.data;
                        if (window.tvChart) return window.tvChart.data;
                        if (window.tradingView) return window.tradingView.activeChart?.data;
                        
                        // Ищем в глобальных переменных
                        for (let key in window) {
                            if (key.includes('chart') || key.includes('Chart')) {
                                if (window[key]?.data) return window[key].data;
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
            
            # Пробуем кликнуть на разные таймфреймы для получения данных
            timeframe_map = {
                '1m': '1',
                '5m': '5', 
                '15m': '15',
                '30m': '30',
                '1h': '60'
            }
            
            if timeframe in timeframe_map:
                try:
                    tf_selector = f'[data-time="{timeframe_map[timeframe]}"], button:has-text("{timeframe}")'
                    await page.click(tf_selector, timeout=3000)
                    await asyncio.sleep(2)
                except:
                    pass
            
            await browser.close()
            
            # Обрабатываем собранные данные
            if self.collected_data:
                return self._process_collected_data()
            elif self.chart_data:
                return self._process_chart_data(self.chart_data)
            else:
                logger.warning("No data intercepted")
                return pd.DataFrame()
    
    def _is_chart_data(self, data):
        """Проверяет, похожи ли данные на OHLC"""
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict):
                # Проверяем наличие OHLC полей
                ohlc_fields = {'open', 'high', 'low', 'close', 'o', 'h', 'l', 'c'}
                time_fields = {'time', 'timestamp', 't', 'date'}
                
                has_ohlc = any(f in str(first).lower() for f in ohlc_fields)
                has_time = any(f in str(first).lower() for f in time_fields)
                
                return has_ohlc or (has_time and len(first) >= 4)
        
        elif isinstance(data, dict):
            # Проверяем вложенные структуры
            for key, value in data.items():
                if 'candle' in key.lower() or 'data' in key.lower():
                    return self._is_chart_data(value)
        
        return False
    
    def _process_collected_data(self):
        """Обрабатывает перехваченные данные"""
        all_candles = []
        
        for data_chunk in self.collected_data:
            if isinstance(data_chunk, list):
                all_candles.extend(data_chunk)
            elif isinstance(data_chunk, dict):
                # Ищем массив свечей в объекте
                for key, value in data_chunk.items():
                    if isinstance(value, list) and len(value) > 0:
                        all_candles.extend(value)
        
        if not all_candles:
            return pd.DataFrame()
        
        # Конвертируем в DataFrame
        df = pd.DataFrame(all_candles)
        
        # Стандартизируем названия колонок
        rename_map = {
            'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close',
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
            't': 'time', 'timestamp': 'time'
        }
        
        df.rename(columns=rename_map, inplace=True)
        
        # Устанавливаем временной индекс
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
        
        # Выбираем только OHLC колонки
        ohlc_cols = ['Open', 'High', 'Low', 'Close']
        available_cols = [col for col in ohlc_cols if col in df.columns]
        
        if len(available_cols) == 4:
            return df[available_cols]
        
        return pd.DataFrame()
    
    def _process_chart_data(self, chart_data):
        """Обрабатывает данные из JavaScript"""
        try:
            if isinstance(chart_data, str):
                chart_data = json.loads(chart_data)
            
            return self._process_collected_data([chart_data])
        except:
            return pd.DataFrame()

# Использование
async def get_real_po_data(symbol: str, timeframe: str, otc: bool = False):
    """Получает реальные данные с PocketOption"""
    interceptor = PocketOptionInterceptor()
    
    try:
        df = await interceptor.intercept_chart_data(symbol, timeframe, otc)
        
        if len(df) > 0:
            logger.info(f"✅ Got {len(df)} real candles from PocketOption")
            return df
        else:
            logger.warning("No data intercepted, using fallback")
            return None
            
    except Exception as e:
        logger.error(f"Interception failed: {e}")
        return None
