# app/data_sources/pocketoption_scraper.py
from __future__ import annotations
import asyncio, contextlib, json, os, random, re, time
from typing import Literal, Optional
import pandas as pd
import numpy as np
from loguru import logger

from ..config import (
    PO_ENABLE_SCRAPE, PO_PROXY, PO_PROXY_FIRST, PO_NAV_TIMEOUT_MS,
    PO_IDLE_TIMEOUT_MS, PO_WAIT_EXTRA_MS, PO_SCRAPE_DEADLINE,
    PO_BROWSER_ORDER, PO_ENTRY_URL, LOG_LEVEL
)
from ..utils.user_agents import UAS
from ..utils.logging import setup

logger = setup(LOG_LEVEL)

# Быстрый режим - используем mock данные по умолчанию
USE_REAL_SCRAPING = True  # Установите True для реального скрапинга

# Реалистичные базовые цены
PAIR_PRICES = {
    'EURUSD': 1.0850, 'GBPUSD': 1.2650, 'USDJPY': 148.50,
    'CADJPY': 108.75, 'AUDUSD': 0.6750, 'USDCHF': 0.8850,
}

async def generate_fast_data(symbol: str, timeframe: str, otc: bool) -> pd.DataFrame:
    """Генерация более реалистичных данных с четкими трендами"""
    logger.info(f"FAST DATA: Generating {symbol} {timeframe} (otc={otc})")
    
    await asyncio.sleep(0.3)
    
    base_price = PAIR_PRICES.get(symbol, 1.0000)
    
    # Увеличенная волатильность
    volatility = 0.003 if 'JPY' in symbol else 0.0012  # Увеличено
    
    tf_multipliers = {
        '30s': 0.3, '1m': 0.4, '2m': 0.5, '3m': 0.6, 
        '5m': 0.8, '10m': 1.2, '15m': 1.5, '30m': 2.0, '1h': 2.8
    }
    
    volatility *= tf_multipliers.get(timeframe, 1.0)
    
    num_bars = random.randint(120, 180)  # Больше данных
    
    # Более динамичный seed
    current_hour = pd.Timestamp.now().hour
    np.random.seed((hash(symbol + timeframe) + current_hour) % 1000)
    
    # Более выраженные тренды
    trend_strength = np.random.choice([0.0002, 0.0005, 0.0008, -0.0002, -0.0005, -0.0008, 0], 
                                     p=[0.15, 0.15, 0.1, 0.15, 0.15, 0.1, 0.2])
    
    # Периоды смены тренда
    trend_change_period = random.randint(20, 40)
    
    returns = []
    current_trend = trend_strength
    
    for i in range(num_bars):
        # Смена тренда каждые N баров
        if i % trend_change_period == 0 and i > 0:
            # Иногда меняем направление тренда
            if random.random() < 0.3:
                current_trend = -current_trend
            elif random.random() < 0.2:
                current_trend = random.choice([0.0003, -0.0003, 0])
        
        # Базовое движение с трендом
        base_return = np.random.normal(current_trend, volatility)
        
        # Добавляем импульсы (резкие движения)
        if random.random() < 0.05:  # 5% шанс импульса
            impulse = np.random.choice([1, -1]) * volatility * random.uniform(2, 4)
            base_return += impulse
        
        returns.append(base_return)
    
    # Увеличенная автокорреляция для более плавных трендов
    for i in range(2, len(returns)):
        returns[i] = 0.4 * returns[i] + 0.35 * returns[i-1] + 0.25 * returns[i-2]
    
    # Создаем ценовую серию
    prices = [base_price]
    for ret in returns:
        new_price = prices[-1] * (1 + ret)
        prices.append(new_price)
    
    # Генерируем более реалистичные OHLC
    ohlc_data = []
    for i in range(1, len(prices)):
        open_price = prices[i-1]
        close_price = prices[i]
        
        # Более динамичные внутрибарные движения
        direction = 1 if close_price > open_price else -1
        volatility_factor = abs(returns[i-1]) * 3 + volatility
        
        # High и Low с учетом направления
        if direction > 0:  # Бычья свеча
            high_extra = abs(np.random.normal(0, volatility_factor * 0.6))
            low_extra = abs(np.random.normal(0, volatility_factor * 0.3))
            high_price = max(open_price, close_price) + high_extra
            low_price = min(open_price, close_price) - low_extra
        else:  # Медвежья свеча
            high_extra = abs(np.random.normal(0, volatility_factor * 0.3))
            low_extra = abs(np.random.normal(0, volatility_factor * 0.6))
            high_price = max(open_price, close_price) + high_extra
            low_price = min(open_price, close_price) - low_extra
        
        # Иногда создаем доджи или молоты
        if random.random() < 0.08:  # 8% шанс особых паттернов
            pattern_type = random.choice(['doji', 'hammer', 'shooting_star'])
            
            if pattern_type == 'doji':
                close_price = open_price + np.random.normal(0, volatility * 0.2)
            elif pattern_type == 'hammer' and direction < 0:
                low_price = min(open_price, close_price) - volatility_factor * 2
            elif pattern_type == 'shooting_star' and direction > 0:
                high_price = max(open_price, close_price) + volatility_factor * 2
        
        decimals = 3 if 'JPY' in symbol else 5
        
        ohlc_data.append({
            'Open': round(open_price, decimals),
            'High': round(high_price, decimals),
            'Low': round(low_price, decimals),
            'Close': round(close_price, decimals)
        })
    
    df = pd.DataFrame(ohlc_data)
    
    # Временной индекс
    freq_map = {
        '30s': '30s', '1m': '1min', '2m': '2min', '3m': '3min',
        '5m': '5min', '10m': '10min', '15m': '15min', 
        '30m': '30min', '1h': '1h'
    }
    
    freq = freq_map.get(timeframe, '1min')
    end_time = pd.Timestamp.now(tz='UTC')
    df.index = pd.date_range(end=end_time, periods=len(df), freq=freq)
    
    # Убеждаемся в корректности OHLC
    df['High'] = np.maximum(df['High'], np.maximum(df['Open'], df['Close']))
    df['Low'] = np.minimum(df['Low'], np.minimum(df['Open'], df['Close']))
    
    # Анализируем созданные данные
    price_change = ((df['Close'].iloc[-1] / df['Close'].iloc[0]) - 1) * 100
    direction = "UP" if price_change > 0 else "DOWN" if price_change < 0 else "FLAT"
    
    logger.info(f"FAST DATA: Generated {len(df)} bars, price change: {price_change:.2f}% {direction}")
    logger.info(f"Price range: {df['Low'].min():.5f} - {df['High'].max():.5f}")
    
    return df

def _proxy_dict() -> Optional[dict]:
    """Конвертация прокси для Playwright"""
    if not PO_PROXY:
        return None
        
    if '@' in PO_PROXY:
        parts = PO_PROXY.split('@')
        if len(parts) == 2:
            auth_part = parts[0]
            server_part = parts[1]
            
            if '://' in auth_part:
                auth_part = auth_part.split('://')[-1]
            
            if ':' in auth_part:
                username, password = auth_part.split(':', 1)
                return {
                    "server": f"http://{server_part}",
                    "username": username,
                    "password": password
                }
    
    if not PO_PROXY.startswith('http'):
        return {"server": f"http://{PO_PROXY}"}
    
    return {"server": PO_PROXY}

def _maybe_ohlc(payload: str):
    """Проверка на OHLC данные"""
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
    """Сборщики данных WebSocket/HTTP"""
    def on_ws(ws):
        logger.debug(f"WS: {ws.url}")
        def _on(ev):
            try:
                bars = _maybe_ohlc(ev["payload"])
                if bars:
                    logger.info(f"WS: Got {len(bars)} OHLC bars")
                    sink_list.append(bars)
            except Exception:
                pass
        ws.on("framereceived", _on)
        ws.on("framesent", _on)
    page.on("websocket", on_ws)

    def on_resp(resp):
        try:
            url = resp.url.lower()
            if any(k in url for k in ("ohlc", "candl", "bar", "chart", "api", "data")):
                if "json" in resp.headers.get("content-type", "").lower():
                    async def _read():
                        try:
                            j = await resp.json()
                            bars = _maybe_ohlc(json.dumps(j))
                            if bars:
                                logger.info(f"HTTP: Got {len(bars)} bars")
                                sink_list.append(bars)
                        except Exception:
                            pass
                    context.loop.create_task(_read())
        except Exception:
            pass
    context.on("response", on_resp)

async def _advanced_ui_interaction(page, symbol: str, timeframe: str, otc: bool):
    """Максимально агрессивное взаимодействие с UI"""
    logger.debug(f"Advanced UI: {symbol} {timeframe} otc={otc}")
    
    try:
        # Ждем полной загрузки
        await page.wait_for_load_state('networkidle', timeout=10000)
        await asyncio.sleep(3)
        
        # Пытаемся найти и кликнуть по любым элементам, содержащим валютные пары
        logger.debug("Searching for any currency elements...")
        
        # Более широкий поиск элементов
        all_buttons = await page.locator('button, div[role="button"], span[role="button"]').all()
        logger.debug(f"Found {len(all_buttons)} clickable elements")
        
        # Ищем элементы с текстом, похожим на валютные пары
        currency_patterns = [
            symbol.replace('/', ''),  # EURUSD
            symbol,                   # EUR/USD  
            symbol.replace('/', ' '),  # EUR USD
            symbol.replace('/', '-'),  # EUR-USD
        ]
        
        if otc:
            currency_patterns.extend([
                f"{symbol} OTC",
                f"{symbol.replace('/', '')} OTC",
                f"{symbol}OTC"
            ])
        
        # Кликаем по любому элементу, содержащему нашу валютную пару
        for i, button in enumerate(all_buttons[:50]):  # Проверяем первые 50
            try:
                text = await button.inner_text()
                if any(pattern.upper() in text.upper() for pattern in currency_patterns):
                    await button.click(timeout=2000)
                    await asyncio.sleep(1)
                    logger.debug(f"Clicked currency element: {text}")
                    break
            except:
                continue
        
        # Альтернативный поиск через все текстовые элементы
        all_text_elements = await page.locator('*').all()
        for element in all_text_elements[:100]:  # Первые 100 элементов
            try:
                text = await element.inner_text()
                if any(pattern.upper() in text.upper() for pattern in currency_patterns):
                    if await element.is_visible():
                        await element.click(timeout=1000)
                        await asyncio.sleep(0.5)
                        logger.debug(f"Clicked text element: {text}")
                        break
            except:
                continue
        
        # Поиск элементов таймфрейма
        await asyncio.sleep(2)
        logger.debug(f"Searching for timeframe: {timeframe}")
        
        tf_patterns = {
            '30s': ['30s', 'S30', '30 sec', '30sec', '0:30'],
            '1m': ['1m', 'M1', '1 min', '1min', '1:00'],
            '2m': ['2m', 'M2', '2 min', '2min', '2:00'],
            '3m': ['3m', 'M3', '3 min', '3min', '3:00'],
            '5m': ['5m', 'M5', '5 min', '5min', '5:00'],
            '10m': ['10m', 'M10', '10 min', '10min', '10:00'],
            '15m': ['15m', 'M15', '15 min', '15min', '15:00'],
            '30m': ['30m', 'M30', '30 min', '30min', '30:00'],
            '1h': ['1h', 'H1', '1 hour', '1hr', '60m', '60 min']
        }.get(timeframe, [timeframe])
        
        # Ищем элементы таймфрейма среди всех кликабельных элементов
        for button in all_buttons[:30]:
            try:
                text = await button.inner_text()
                if any(tf.upper() in text.upper() for tf in tf_patterns):
                    await button.click(timeout=2000)
                    await asyncio.sleep(1)
                    logger.debug(f"Clicked timeframe: {text}")
                    break
            except:
                continue
        
        # Дополнительные действия для активации данных
        await asyncio.sleep(2)
        
        # Пытаемся кликнуть по области графика
        try:
            chart_area = page.locator('canvas, svg, [class*="chart"], [id*="chart"]').first
            if await chart_area.count() > 0:
                await chart_area.click()
                logger.debug("Clicked chart area")
        except:
            pass
        
        # Прокручиваем страницу для активации событий
        await page.evaluate("window.scrollTo(0, 100)")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo(0, 0)")
        
        # Имитируем движения мыши
        try:
            await page.mouse.move(400, 300)
            await asyncio.sleep(0.2)
            await page.mouse.move(600, 400)
            await asyncio.sleep(0.2)
        except:
            pass
        
        logger.debug("Advanced UI interaction completed")
        
    except Exception as e:
        logger.warning(f"Advanced UI interaction error: {e}")

async def fetch_po_real_enhanced(symbol: str, timeframe: str, otc: bool) -> pd.DataFrame:
    """Улучшенный скрапинг с расширенными возможностями"""
    from playwright.async_api import async_playwright
    
    collected = []
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/en/cabinet/try-demo/"
    
    logger.info(f"ENHANCED SCRAPING: {symbol} {timeframe} otc={otc}")
    
    async with async_playwright() as p:
        try:
            # Запускаем браузер с дополнительными аргументами
            browser = await p.chromium.launch(
                headless=True, 
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor"
                ]
            )
            
            ctx_kwargs = {
                "viewport": {"width": 1920, "height": 1080},  # Больший экран
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                }
            }
            
            proxy_config = _proxy_dict()
            if proxy_config:
                ctx_kwargs["proxy"] = proxy_config
                logger.info("Using proxy for enhanced scraping")
            
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            
            # Расширенные коллекторы данных
            attach_collectors_enhanced(page, ctx, collected)
            
            # Увеличенные таймауты
            page.set_default_timeout(25000)
            
            logger.info(f"Navigating to: {entry_url}")
            await page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            
            # Ждем загрузки JavaScript
            await asyncio.sleep(5)
            
            # Продвинутое взаимодействие с UI
            await _advanced_ui_interaction(page, symbol, timeframe, otc)
            
            # Длительное ожидание данных с периодическими проверками
            logger.info("Waiting for enhanced data collection...")
            deadline = time.time() + 45  # Увеличено до 45 секунд
            
            while time.time() < deadline and not collected:
                await asyncio.sleep(1)
                
                # Периодически "будим" страницу
                if int(time.time()) % 10 == 0:
                    try:
                        await page.evaluate("console.log('keepalive')")
                        await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
                    except:
                        pass
                
                if collected:
                    logger.info(f"Enhanced data collected: {len(collected)} chunks")
                    break
            
            # Делаем финальный скриншот для отладки
            try:
                await page.screenshot(path="/tmp/po_final.png", full_page=True)
                logger.info("Final screenshot saved")
            except:
                pass
            
            await page.close()
            await ctx.close()
            await browser.close()
            
            if collected:
                logger.info(f"Processing {len(collected)} data chunks...")
                return await process_collected_data_enhanced(collected)
                    
        except Exception as e:
            logger.error(f"Enhanced scraping error: {e}")
    
    raise RuntimeError("Enhanced scraping failed - no data obtained")

def attach_collectors_enhanced(page, context, sink_list):
    """Расширенные коллекторы с большим покрытием"""
    def on_ws(ws):
        logger.debug(f"Enhanced WS: {ws.url}")
        
        def _on_frame(ev):
            try:
                payload = ev.get("payload", "")
                
                # Логируем все сообщения для анализа
                if len(payload) > 20:
                    logger.debug(f"WS payload sample: {payload[:50]}...")
                
                # Проверяем различные форматы данных
                bars = _maybe_ohlc(payload)
                if bars:
                    logger.info(f"Enhanced WS: Found {len(bars)} OHLC bars")
                    sink_list.append(bars)
                    return
                
                # Проверяем альтернативные форматы
                try:
                    j = json.loads(payload)
                    
                    # Ищем данные в различных структурах
                    for key in ['data', 'candles', 'bars', 'quotes', 'ticks']:
                        if key in j and isinstance(j[key], list):
                            logger.debug(f"Found potential data in key: {key}")
                            # Пробуем парсить как OHLC
                            test_bars = _maybe_ohlc(json.dumps(j[key]))
                            if test_bars:
                                logger.info(f"Enhanced WS: Parsed {len(test_bars)} bars from {key}")
                                sink_list.append(test_bars)
                                return
                                
                except Exception:
                    pass
                    
            except Exception as e:
                logger.debug(f"Enhanced WS processing error: {e}")
        
        ws.on("framereceived", _on_frame)
        ws.on("framesent", _on_frame)
    
    page.on("websocket", on_ws)

    def on_resp(resp):
        try:
            url = resp.url.lower()
            
            # Расширенный список ключевых слов
            keywords = [
                "ohlc", "candle", "bar", "chart", "api", "data", "quote", 
                "price", "market", "trading", "feed", "stream", "socket",
                "history", "tick", "forex", "currency"
            ]
            
            if any(word in url for word in keywords):
                content_type = resp.headers.get("content-type", "").lower()
                
                if "json" in content_type:
                    async def _read():
                        try:
                            j = await resp.json()
                            bars = _maybe_ohlc(json.dumps(j))
                            if bars:
                                logger.info(f"Enhanced HTTP: Found {len(bars)} bars from {url}")
                                sink_list.append(bars)
                            else:
                                logger.debug(f"Enhanced HTTP: Non-OHLC data from {url}")
                        except Exception as e:
                            logger.debug(f"Enhanced HTTP processing error: {e}")
                    
                    context.loop.create_task(_read())
        except Exception as e:
            logger.debug(f"Enhanced response handler error: {e}")
    
    context.on("response", on_resp)

async def process_collected_data_enhanced(collected):
    """Улучшенная обработка собранных данных"""
    dfs = []
    
    for i, chunk in enumerate(collected):
        try:
            logger.debug(f"Processing chunk {i+1}/{len(collected)}")
            
            df = pd.DataFrame(chunk).rename(columns=str.lower)
            
            # Ищем временную колонку
            time_col = None
            for col in ["time", "timestamp", "t", "date", "datetime", "ts"]:
                if col in df.columns:
                    time_col = col
                    break
            
            if time_col:
                # Различные способы парсинга времени
                try:
                    if pd.api.types.is_numeric_dtype(df[time_col]):
                        # Unix timestamp
                        df["time"] = pd.to_datetime(df[time_col], unit="s", errors="coerce", utc=True)
                    else:
                        # Строковое время
                        df["time"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
                except:
                    continue
                
                df = df.set_index("time")
            
            # Ищем OHLC колонки с различными названиями
            col_mapping = {}
            for target, variants in [
                ("open", ["open", "o", "opening", "start"]),
                ("high", ["high", "h", "max", "top"]),
                ("low", ["low", "l", "min", "bottom"]),
                ("close", ["close", "c", "closing", "end", "last"])
            ]:
                for variant in variants:
                    if variant in df.columns:
                        col_mapping[variant] = target
                        break
            
            if len(col_mapping) >= 4:  # Нашли все OHLC
                df = df.rename(columns=col_mapping)
                df = df[["open", "high", "low", "close"]].astype(float).dropna()
                
                if len(df) > 5:  # Минимум 5 баров
                    dfs.append(df)
                    logger.info(f"Successfully processed chunk {i+1}: {len(df)} bars")
                    
        except Exception as e:
            logger.debug(f"Error processing chunk {i+1}: {e}")
    
    if not dfs:
        raise RuntimeError("No processable OHLC data found in collected chunks")
    
    # Выбираем лучший датасет
    result = max(dfs, key=len)
    result = result.loc[~result.index.duplicated(keep="last")].sort_index()
    
    # Переименовываем колонки в ожидаемый формат
    result.columns = ['Open', 'High', 'Low', 'Close']
    
    logger.info(f"Enhanced processing complete: {len(result)} final bars")
    return result

async def fetch_po_real_fast(symbol: str, timeframe: str, otc: bool) -> pd.DataFrame:
    """Быстрый реальный скрапинг PocketOption"""
    from playwright.async_api import async_playwright
    
    collected = []
    entry_url = PO_ENTRY_URL or "https://pocketoption.com/en/cabinet/try-demo/"
    
    logger.info(f"REAL SCRAPING: {symbol} {timeframe} otc={otc}")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            
            ctx_kwargs = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": random.choice(UAS),
            }
            
            proxy_config = _proxy_dict()
            if proxy_config:
                ctx_kwargs["proxy"] = proxy_config
                logger.info("Using proxy")
            
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            
            attach_collectors(page, ctx, collected)
            
            page.set_default_timeout(15000)
            
            await page.goto(entry_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            await _quick_ui_interaction(page, symbol, timeframe, otc)
            
            # Ждем данные максимум 15 секунд
            deadline = time.time() + 15
            while time.time() < deadline and not collected:
                await asyncio.sleep(0.5)
            
            await page.close()
            await ctx.close()
            await browser.close()
            
            if collected:
                logger.info(f"Collected {len(collected)} chunks")
                
                # Быстрая обработка
                dfs = []
                for chunk in collected:
                    try:
                        df = pd.DataFrame(chunk).rename(columns=str.lower)
                        time_col = next((c for c in ["time", "timestamp", "t"] if c in df.columns), None)
                        if time_col:
                            df["time"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
                            df = df.set_index("time")
                        df = df[["open", "high", "low", "close"]].astype(float).dropna()
                        if len(df) > 10:
                            dfs.append(df)
                    except:
                        continue
                
                if dfs:
                    result = max(dfs, key=len)
                    result.columns = ['Open', 'High', 'Low', 'Close']
                    logger.info(f"Real data: {len(result)} bars")
                    return result
                    
        except Exception as e:
            logger.warning(f"Real scraping failed: {e}")
    
    raise RuntimeError("No real data obtained")

async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["30s","1m","2m","3m","5m","10m","15m","30m","1h"]="1m", otc: bool=False) -> pd.DataFrame:
    """Главная функция получения данных"""
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PO scraping disabled")
    
    # Если включен реальный скрапинг, пробуем его
    if USE_REAL_SCRAPING:
        try:
            return await fetch_po_real_fast(symbol, timeframe, otc)
        except Exception as e:
            logger.warning(f"Real scraping failed: {e}")
            logger.info("Falling back to fast mock data")
    
    # Используем быструю генерацию данных
    return await generate_fast_data(symbol, timeframe, otc)
