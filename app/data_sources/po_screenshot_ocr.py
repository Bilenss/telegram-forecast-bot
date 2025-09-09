# app/data_sources/po_screenshot_ocr.py
"""
Анализ скриншотов графиков PocketOption
"""
import asyncio
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import pytesseract
from playwright.async_api import async_playwright
from loguru import logger
import io

class ScreenshotAnalyzer:
    """
    Анализирует скриншоты графиков для извлечения данных
    """
    
    async def capture_and_analyze(self, symbol: str, timeframe: str, otc: bool = False):
        """
        Делает скриншот и анализирует график
        """
        logger.info(f"Capturing screenshot for {symbol} {timeframe}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
            
            # Формируем URL
            url = f"https://pocketoption.com/en/cabinet/demo-quick-high-low/"
            if symbol:
                clean_symbol = symbol.replace('/', '').upper()
                if otc:
                    clean_symbol += "_otc"
                url += f"#{clean_symbol}"
            
            await page.goto(url, wait_until='networkidle')
            await asyncio.sleep(5)  # Ждем загрузки графика
            
            # Делаем скриншот области графика
            chart_element = await page.query_selector('canvas, .chart-container, #chart')
            
            if chart_element:
                screenshot = await chart_element.screenshot()
            else:
                screenshot = await page.screenshot()
            
            await browser.close()
            
            # Анализируем скриншот
            return self._analyze_chart_image(screenshot)
    
    def _analyze_chart_image(self, screenshot_bytes):
        """
        Анализирует изображение графика
        """
        # Конвертируем в numpy array
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Извлекаем свечи
        candles = self._detect_candles(img)
        
        # Извлекаем цены с помощью OCR
        prices = self._extract_prices_ocr(img)
        
        # Комбинируем данные
        if candles and prices:
            return self._create_dataframe(candles, prices)
        
        return pd.DataFrame()
    
    def _detect_candles(self, img):
        """
        Детектирует свечи на графике используя компьютерное зрение
        """
        # Конвертируем в HSV для лучшего распознавания цветов
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Определяем диапазоны для зеленых (бычьих) и красных (медвежьих) свечей
        green_lower = np.array([40, 40, 40])
        green_upper = np.array([80, 255, 255])
        red_lower = np.array([0, 40, 40])
        red_upper = np.array([10, 255, 255])
        
        # Маски для свечей
        green_mask = cv2.inRange(hsv, green_lower, green_upper)
        red_mask = cv2.inRange(hsv, red_lower, red_upper)
        
        # Находим контуры
        green_contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        red_contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candles = []
        
        # Обрабатываем зеленые свечи
        for contour in green_contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h > 5 and w > 2:  # Фильтруем шум
                candles.append({
                    'x': x,
                    'y': y,
                    'height': h,
                    'type': 'bullish',
                    'top': y,
                    'bottom': y + h
                })
        
        # Обрабатываем красные свечи
        for contour in red_contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h > 5 and w > 2:
                candles.append({
                    'x': x,
                    'y': y,
                    'height': h,
                    'type': 'bearish',
                    'top': y,
                    'bottom': y + h
                })
        
        # Сортируем по X координате (временная последовательность)
        candles.sort(key=lambda c: c['x'])
        
        logger.info(f"Detected {len(candles)} candles")
        return candles
    
    def _extract_prices_ocr(self, img):
        """
        Извлекает цены с помощью OCR
        """
        # Обрезаем правую часть где обычно находится шкала цен
        height, width = img.shape[:2]
        price_area = img[:, width-150:]  # Правые 150 пикселей
        
        # Препроцессинг для OCR
        gray = cv2.cvtColor(price_area, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # OCR
        try:
            text = pytesseract.image_to_string(thresh, config='--psm 6 -c tessedit_char_whitelist=0123456789.')
            
            # Извлекаем числа
            prices = []
            for line in text.split('\n'):
                try:
                    price = float(line.strip())
                    if price > 0:
                        prices.append(price)
                except:
                    continue
            
            logger.info(f"Extracted {len(prices)} price levels")
            return prices
            
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return []
    
    def _create_dataframe(self, candles, prices):
        """
        Создает DataFrame из распознанных свечей
        """
        if not candles:
            return pd.DataFrame()
        
        # Оцениваем диапазон цен
        if prices:
            min_price = min(prices)
            max_price = max(prices)
        else:
            # Используем дефолтные значения
            min_price = 1.0800
            max_price = 1.0900
        
        # Высота области графика
        min_y = min(c['top'] for c in candles)
        max_y = max(c['bottom'] for c in candles)
        y_range = max_y - min_y
        
        # Конвертируем координаты Y в цены
        price_range = max_price - min_price
        
        ohlc_data = []
        for candle in candles:
            # Масштабируем Y координаты в цены
            high = max_price - ((candle['top'] - min_y) / y_range) * price_range
            low = max_price - ((candle['bottom'] - min_y) / y_range) * price_range
            
            if candle['type'] == 'bullish':
                open_price = low
                close_price = high
            else:
                open_price = high
                close_price = low
            
            ohlc_data.append({
                'Open': open_price,
                'High': high,
                'Low': low,
                'Close': close_price
            })
        
        df = pd.DataFrame(ohlc_data)
        
        # Добавляем временной индекс
        df.index = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq='1min')
        
        return df
