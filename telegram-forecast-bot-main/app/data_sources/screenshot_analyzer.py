# app/data_sources/screenshot_analyzer.py
import asyncio
import cv2
import numpy as np
from PIL import Image
import io
from playwright.async_api import async_playwright
from typing import List, Tuple, Optional
import pandas as pd
from ..utils.logging import setup
from ..config import LOG_LEVEL

logger = setup(LOG_LEVEL)

class PocketOptionScreenshotAnalyzer:
    def __init__(self):
        self.chart_region = None  # Область графика на скриншоте
        
    async def capture_chart_screenshot(self) -> bytes:
        """Делает скриншот графика PocketOption"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            try:
                # Переходим на страницу
                await page.goto('https://pocketoption.com/ru/cabinet/try-demo/', 
                              wait_until='networkidle', timeout=30000)
                await asyncio.sleep(3)
                
                # Настраиваем график как на ваших скриншотах
                await self._setup_chart(page)
                
                # Делаем скриншот
                screenshot = await page.screenshot(full_page=False)
                logger.info("Screenshot captured successfully")
                return screenshot
                
            except Exception as e:
                logger.error(f"Screenshot error: {e}")
                raise
            finally:
                await browser.close()

    async def _setup_chart(self, page):
        """Настраивает график: свечи, таймфрейм 5м, зум"""
        try:
            # Ждем загрузки интерфейса
            await asyncio.sleep(2)
            
            # Переключаем на свечи (если не активно)
            candle_button = page.locator('[data-testid*="candle"], button:has-text("Свечи"), [class*="candle"]')
            if await candle_button.count() > 0:
                await candle_button.first.click()
                await asyncio.sleep(1)
            
            # Устанавливаем таймфрейм 5м
            tf_buttons = page.locator('button:has-text("5m"), button:has-text("M5"), button:has-text("5 мин")')
            if await tf_buttons.count() > 0:
                await tf_buttons.first.click()
                await asyncio.sleep(2)
            
            # Имитируем зум колесом мыши (отдаляем)
            chart_area = page.locator('canvas, [class*="chart"], [id*="chart"]').first
            if await chart_area.count() > 0:
                # Наводим на центр графика
                box = await chart_area.bounding_box()
                if box:
                    center_x = box['x'] + box['width'] / 2
                    center_y = box['y'] + box['height'] / 2
                    
                    # Отдаляем зум (несколько прокруток вниз)
                    for _ in range(3):
                        await page.mouse.wheel(center_x, center_y, 0, 120)
                        await asyncio.sleep(0.5)
            
            await asyncio.sleep(2)
            logger.info("Chart setup completed")
            
        except Exception as e:
            logger.warning(f"Chart setup error: {e}")

    def extract_candles_from_image(self, image_bytes: bytes) -> List[dict]:
        """Извлекает данные свечей из изображения"""
        # Преобразуем в OpenCV формат
        image = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Определяем область графика
        chart_region = self._find_chart_region(img_bgr)
        if chart_region is None:
            logger.error("Chart region not found")
            return []
        
        # Извлекаем свечи
        candles = self._detect_candles(img_bgr, chart_region)
        logger.info(f"Extracted {len(candles)} candles from image")
        return candles

    def _find_chart_region(self, img: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Находит область графика на изображении"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Ищем темную область графика (фон обычно темный)
        # Приблизительные координаты из ваших скриншотов
        height, width = gray.shape
        
        # Область графика примерно: левая треть экрана, центральная часть
        x_start = int(width * 0.05)  # 5% от левого края
        x_end = int(width * 0.75)    # 75% ширины
        y_start = int(height * 0.15) # 15% от верха
        y_end = int(height * 0.85)   # 85% высоты
        
        return (x_start, y_start, x_end, y_end)

    def _detect_candles(self, img: np.ndarray, region: Tuple[int, int, int, int]) -> List[dict]:
        """Определяет свечи в области графика"""
        x1, y1, x2, y2 = region
        chart_img = img[y1:y2, x1:x2]
        
        # Преобразуем в HSV для лучшего определения цветов
        hsv = cv2.cvtColor(chart_img, cv2.COLOR_BGR2HSV)
        
        # Определяем зеленые свечи (бычьи)
        green_lower = np.array([40, 50, 50])
        green_upper = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv, green_lower, green_upper)
        
        # Определяем красные свечи (медвежьи)
        red_lower = np.array([0, 50, 50])
        red_upper = np.array([20, 255, 255])
        red_mask = cv2.inRange(hsv, red_lower, red_upper)
        
        # Находим контуры свечей
        green_contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        red_contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candles = []
        
        # Обрабатываем зеленые свечи
        for contour in green_contours:
            if cv2.contourArea(contour) > 10:  # Минимальный размер
                x, y, w, h = cv2.boundingRect(contour)
                candle_data = self._extract_candle_data(x, y, w, h, 'bullish', chart_img)
                if candle_data:
                    candles.append(candle_data)
        
        # Обрабатываем красные свечи
        for contour in red_contours:
            if cv2.contourArea(contour) > 10:
                x, y, w, h = cv2.boundingRect(contour)
                candle_data = self._extract_candle_data(x, y, w, h, 'bearish', chart_img)
                if candle_data:
                    candles.append(candle_data)
        
        # Сортируем по X координате (временная последовательность)
        candles.sort(key=lambda c: c['x'])
        
        return candles

    def _extract_candle_data(self, x: int, y: int, w: int, h: int, candle_type: str, img: np.ndarray) -> Optional[dict]:
        """Извлекает OHLC данные из одной свечи"""
        # Примерная логика определения OHLC по геометрии свечи
        # Это упрощенная версия - в реальности нужно более сложное определение цен
        
        chart_height = img.shape[0]
        
        # Примерный диапазон цен (нужно калибровать под конкретный график)
        price_range = 0.002  # Примерно 200 пипсов на график
        base_price = 1.17000  # Базовая цена для EUR/USD
        
        # Преобразуем пиксели в цены (очень упрощенно)
        top_price = base_price + (1 - y / chart_height) * price_range
        bottom_price = base_price + (1 - (y + h) / chart_height) * price_range
        
        if candle_type == 'bullish':
            open_price = bottom_price
            close_price = top_price
        else:
            open_price = top_price
            close_price = bottom_price
        
        # High и Low определяем по теням свечи (упрощенно)
        high_price = top_price + 0.00005
        low_price = bottom_price - 0.00005
        
        return {
            'x': x,
            'open': round(open_price, 5),
            'high': round(high_price, 5),
            'low': round(low_price, 5),
            'close': round(close_price, 5),
            'type': candle_type
        }

    def candles_to_dataframe(self, candles: List[dict]) -> pd.DataFrame:
        """Преобразует список свечей в DataFrame для анализа"""
        if not candles:
            return pd.DataFrame()
        
        # Создаем DataFrame
        df_data = []
        for i, candle in enumerate(candles):
            df_data.append({
                'Open': candle['open'],
                'High': candle['high'],
                'Low': candle['low'],
                'Close': candle['close']
            })
        
        df = pd.DataFrame(df_data)
        
        # Добавляем временной индекс
        end_time = pd.Timestamp.now(tz='UTC')
        df.index = pd.date_range(end=end_time, periods=len(df), freq='5min')
        
        return df

    async def get_analysis_data(self) -> pd.DataFrame:
        """Полный цикл: скриншот -> анализ -> DataFrame"""
        try:
            # Делаем скриншот
            screenshot = await self.capture_chart_screenshot()
            
            # Извлекаем свечи
            candles = self.extract_candles_from_image(screenshot)
            
            # Преобразуем в DataFrame
            df = self.candles_to_dataframe(candles)
            
            if len(df) > 10:
                logger.info(f"Successfully extracted {len(df)} candles for analysis")
                return df
            else:
                raise ValueError("Too few candles extracted")
                
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise

# Интеграция в основной scraper
async def fetch_po_screenshot_data(symbol: str, timeframe: str, otc: bool) -> pd.DataFrame:
    """Получение данных через анализ скриншотов"""
    analyzer = PocketOptionScreenshotAnalyzer()
    
    try:
        logger.info(f"SCREENSHOT ANALYSIS: {symbol} {timeframe} otc={otc}")
        df = await analyzer.get_analysis_data()
        
        if len(df) < 20:
            logger.warning("Insufficient data from screenshot, using mock fallback")
            raise ValueError("Not enough candles")
        
        return df
        
    except Exception as e:
        logger.error(f"Screenshot analysis failed: {e}")
        raise
