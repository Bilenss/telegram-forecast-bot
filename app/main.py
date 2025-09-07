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

LANG = {
    "ru": {
        "hi": "Привет! Выберите режим анализа:",
        "mode": "Выберите режим анализа:",
        "category": "Выберите категорию актива:",
        "pair": "Выберите валютную пару:",
        "tf": "Выберите таймфрейм:",
        "processing": "Анализирую данные...",
        "no_data": "Не удалось получить данные для {} на таймфрейме {}",
        "result": "👉 Прогноз на {}: {}",
        "ind": "📈 Индикаторы:\nRSI: {:.1f}\nEMA fast: {:.5f}\nEMA slow: {:.5f}\nMACD: {:.5f}\nMACD signal: {:.5f}",
        "ta_result": "📊 Технический анализ: {}",
        "notes": "ℹ️ {}",
        "chart": "График: {}"
    },
    "en": {
        "hi": "Hello! Choose analysis mode:",
        "mode": "Choose analysis mode:",
        "category": "Choose asset category:",
        "pair": "Choose pair:",
        "tf": "Choose timeframe:",
        "processing": "Analyzing data...",
        "no_data": "Failed to load data for {} at timeframe {}",
        "result": "👉 Forecast for {}: {}",
        "ind": "📈 Indicators:\nRSI: {:.1f}\nEMA fast: {:.5f}\nEMA slow: {:.5f}\nMACD: {:.5f}\nMACD signal: {:.5f}",
        "ta_result": "📊 Technical Analysis: {}",
        "notes": "ℹ️ {}",
        "chart": "Chart: {}"
    }
}

def tr(lang, key):
    return LANG.get(lang, LANG["en"])[key]

def escape_html(text):
    """Экранирование HTML символов для Telegram"""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    # Сразу используем язык по умолчанию без выбора
    await state.update_data(lang=DEFAULT_LANG)
    await m.answer(tr(DEFAULT_LANG, "hi"), reply_markup=mode_keyboard(DEFAULT_LANG))
    await ST.Mode.set()

@dp.message_handler(state=ST.Mode)
async def set_mode(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    mode = "ta" if "Тех" in m.text or "Technical" in m.text else "ind"
    await state.update_data(mode=mode)
    await m.answer(tr(lang, "category"), reply_markup=category_keyboard(lang))
    await ST.Category.set()

@dp.message_handler(state=ST.Category)
async def set_category(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=cat)
    pairs = all_pairs(cat)
    await m.answer(tr(lang, "pair"), reply_markup=pairs_keyboard(pairs))
    await ST.Pair.set()

@dp.message_handler(state=ST.Pair)
async def set_pair(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = data.get("category", "fin")
    pairs = all_pairs(cat)
    if m.text not in pairs:
        await m.answer(tr(lang, "pair"), reply_markup=pairs_keyboard(pairs))
        return
    await state.update_data(pair=m.text)
    await m.answer(tr(lang, "tf"), reply_markup=timeframe_keyboard(lang, po_available=True))
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
    processing_msg = await m.answer(tr(lang, "processing"))

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
        await processing_msg.edit_text(tr(lang, "no_data").format(pair_human, tf) + f"\nError: {str(e)}")
        await state.finish()
        return

    try:
        if mode == "ind":
            logger.info("Computing indicators...")
            ind = compute_indicators(df)
            action, notes = signal_from_indicators(df, ind)
            
            # Безопасное форматирование для индикаторов (без HTML)
            result_text = tr(lang, "result").format(tf.upper(), action)
            ind_text = tr(lang, "ind").format(
                ind["RSI"], ind["EMA_fast"], ind["EMA_slow"], 
                ind["MACD"], ind["MACD_signal"]
            )
            
            msg_parts = [result_text, ind_text]
            
            if notes:
                notes_text = tr(lang, "notes").format("; ".join(notes))
                msg_parts.append(notes_text)
                
            # Отправляем без HTML форматирования
            await processing_msg.edit_text("\n\n".join(msg_parts))
            
        else:
            logger.info("Computing TA signal...")
            action, notes = simple_ta_signal(df)
            
            # Форматированный ответ для ТА
            result_text = tr(lang, "result").format(tf.upper(), action)
            ta_text = tr(lang, "ta_result").format("; ".join(notes) if notes else "Basic analysis completed")
            
            msg_parts = [result_text, ta_text]
            
            # Отправляем без HTML форматирования
            await processing_msg.edit_text("\n\n".join(msg_parts))

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
