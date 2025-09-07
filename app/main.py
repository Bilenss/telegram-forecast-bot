from __future__ import annotations
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext

from .config import (
    TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, PO_STRICT_ONLY,
    ENABLE_CHARTS, LOG_LEVEL
)
from .states import ForecastStates as ST
from .keyboards import mode_keyboard, category_keyboard, pairs_keyboard, timeframe_keyboard
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import all_pairs
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.pocketoption_scraper import fetch_po_ohlc_async

logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)

def format_forecast_message(mode, timeframe, action, data, notes=None, lang="en"):
    """Безопасное форматирование сообщения без HTML"""
    
    tf_upper = timeframe.upper()
    
    if mode == "ind":
        # Для индикаторов
        message_parts = [
            f"👉 Forecast for {tf_upper}: {action}",
            "",
            "📈 Indicators:",
            f"RSI: {data['RSI']:.1f}",
            f"EMA fast: {data['EMA_fast']:.5f}",
            f"EMA slow: {data['EMA_slow']:.5f}", 
            f"MACD: {data['MACD']:.5f}",
            f"MACD signal: {data['MACD_signal']:.5f}"
        ]
    else:
        # Для технического анализа
        message_parts = [
            f"👉 Forecast for {tf_upper}: {action}",
            "",
            f"📊 Technical Analysis: {'; '.join(notes) if notes else 'Basic analysis completed'}"
        ]
    
    if notes and mode == "ind":
        message_parts.extend(["", f"ℹ️ {'; '.join(notes)}"])
    
    return "\n".join(message_parts)

@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await state.update_data(lang=DEFAULT_LANG)
    
    welcome_text = "Hello! Choose analysis mode:" if DEFAULT_LANG == "en" else "Привет! Выберите режим анализа:"
    await m.answer(welcome_text, reply_markup=mode_keyboard(DEFAULT_LANG))
    await ST.Mode.set()

@dp.message_handler(state=ST.Mode)
async def set_mode(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    mode = "ta" if "Тех" in m.text or "Technical" in m.text else "ind"
    await state.update_data(mode=mode)
    
    category_text = "Choose asset category:" if lang == "en" else "Выберите категорию актива:"
    await m.answer(category_text, reply_markup=category_keyboard(lang))
    await ST.Category.set()

@dp.message_handler(state=ST.Category)
async def set_category(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=cat)
    
    pairs = all_pairs(cat)
    pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
    await m.answer(pair_text, reply_markup=pairs_keyboard(pairs))
    await ST.Pair.set()

@dp.message_handler(state=ST.Pair)
async def set_pair(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = data.get("category", "fin")
    pairs = all_pairs(cat)
    
    if m.text not in pairs:
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs))
        return
        
    await state.update_data(pair=m.text)
    tf_text = "Choose timeframe:" if lang == "en" else "Выберите таймфрейм:"
    await m.answer(tf_text, reply_markup=timeframe_keyboard(lang, po_available=True))
    await ST.Timeframe.set()

@dp.message_handler(state=ST.Timeframe)
async def set_timeframe(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    mode = data.get("mode", "ind")
    cat = data.get("category", "fin")
    pair_human = data.get("pair")
    tf = m.text.strip().lower()

    # Показать сообщение об анализе
    processing_text = "Analyzing data..." if lang == "en" else "Анализирую данные..."
    processing_msg = await m.answer(processing_text)

    pairs = all_pairs(cat)
    pair_info = pairs.get(pair_human)
    
    if not pair_info:
        await processing_msg.edit_text(f"Error: Invalid pair {pair_human}")
        await state.finish()
        return

    try:
        logger.info(f"Loading OHLC data for {pair_human} ({pair_info}) on {tf}")
        
        # Кешируем данные по ключу
        cache_key = f"{pair_info['po']}_{tf}_{cat}"
        df = cache.get(cache_key)
        
        if df is None:
            df = await load_ohlc(pair_info, timeframe=tf, category=cat)
            cache.set(cache_key, df)
            logger.info(f"Cached data for {cache_key}")
        else:
            logger.info(f"Using cached data for {cache_key}")
            
        logger.info(f"Got {len(df)} bars for analysis")
    except Exception as e:
        logger.error(f"Error loading OHLC data: {e}")
        error_text = f"Failed to load data for {pair_human} at timeframe {tf}\nError: {str(e)}"
        await processing_msg.edit_text(error_text)
        await state.finish()
        return

    try:
        if mode == "ind":
            logger.info("Computing indicators...")
            ind = compute_indicators(df)
            action, notes = signal_from_indicators(df, ind)
            
            # Используем безопасную функцию форматирования
            result_message = format_forecast_message(mode, tf, action, ind, notes, lang)
            
        else:
            logger.info("Computing TA signal...")
            action, notes = simple_ta_signal(df)
            
            # Используем безопасную функцию форматирования  
            result_message = format_forecast_message(mode, tf, action, {}, notes, lang)

        # Отправляем сообщение БЕЗ parse_mode
        await processing_msg.edit_text(result_message)
        logger.info(f"Sent forecast: {action} for {tf}")
        
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        await processing_msg.edit_text(f"Analysis error: {str(e)}")

    if ENABLE_CHARTS:
        try:
            from .utils.charts import plot_candles
            import os, tempfile
            with tempfile.TemporaryDirectory() as tmpd:
                p = os.path.join(tmpd, "chart.png")
                out = plot_candles(df, p)
                if out and os.path.exists(out):
                    await m.answer_photo(types.InputFile(out))
                    logger.info("Chart sent successfully")
        except Exception as e:
            logger.error(f"Chart error: {e}")

    await state.finish()

async def load_ohlc(pair_info: dict, timeframe: str, category: str):
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PocketOption scraping is required (set PO_ENABLE_SCRAPE=1)")
    
    if not pair_info or 'po' not in pair_info:
        raise RuntimeError(f"Invalid pair info: {pair_info}")
    
    otc = (category == "otc")
    logger.info(f"Fetching {pair_info['po']} data, otc={otc}, timeframe={timeframe}")
    return await fetch_po_ohlc_async(pair_info['po'], timeframe=timeframe, otc=otc)

def main():
    print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10] if TELEGRAM_TOKEN else 'NOT SET'}...")
    print(f"PO_ENABLE_SCRAPE: {PO_ENABLE_SCRAPE}")
    print(f"DEFAULT_LANG: {DEFAULT_LANG}")
    print(f"LOG_LEVEL: {LOG_LEVEL}")
    
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")
    
    logger.info("Starting Telegram bot...")
    logger.info(f"Bot configuration: PO_ENABLE_SCRAPE={PO_ENABLE_SCRAPE}, DEFAULT_LANG={DEFAULT_LANG}")
    
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise

if __name__ == "__main__":
    main()
