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
from .pairs import all_pairs, get_available_pairs, availability_checker, get_pair_info
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.pocketoption_scraper import fetch_po_ohlc_async

logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)


def format_forecast_message(mode, timeframe, action, data, notes=None, lang="en"):
    tf_upper = timeframe.upper()
    
    if mode == "ind":
        message_parts = [
            f"🎯 **ПРОГНОЗ на {tf_upper}**",
            "",
            f"💡 Рекомендация: **{action}**",
            "",
            "📊 **Индикаторы:**",
            f"• RSI: {data['RSI']:.1f}",
            f"• EMA быстрая: {data['EMA_fast']:.5f}",
            f"• EMA медленная: {data['EMA_slow']:.5f}", 
            f"• MACD: {data['MACD']:.5f}",
            f"• MACD сигнал: {data['MACD_signal']:.5f}"
        ]
    else:
        message_parts = [
            f"🎯 **ПРОГНОЗ на {tf_upper}**",
            "",
            f"💡 Рекомендация: **{action}**",
            "",
            f"📊 **Технический анализ:**",
            f"• {'; '.join(notes) if notes else 'Анализ завершен'}"
        ]
    
    if notes and mode == "ind":
        message_parts.extend(["", f"ℹ️ {'; '.join(notes)}"])
    
    message_parts.extend(["", "⏱ _Анализ выполнен на основе данных PocketOption_"])
    
    return "\n".join(message_parts)


@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await state.update_data(lang=DEFAULT_LANG)
    
    welcome_text = "Hello! Choose analysis mode:" if DEFAULT_LANG == "en" else "Привет! Выберите режим анализа:"
    await m.answer(welcome_text, reply_markup=mode_keyboard(DEFAULT_LANG))
    await ST.Mode.set()


@dp.message_handler(lambda m: "⬅️" in m.text, state="*")
async def handle_back(m: types.Message, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    if current_state == "ForecastStates:Category":
        welcome_text = "Choose analysis mode:" if lang == "en" else "Выберите режим анализа:"
        await m.answer(welcome_text, reply_markup=mode_keyboard(lang))
        await ST.Mode.set()
    
    elif current_state == "ForecastStates:Pair":
        category_text = "Choose asset category:" if lang == "en" else "Выберите категорию актива:"
        await m.answer(category_text, reply_markup=category_keyboard(lang))
        await ST.Category.set()
    
    elif current_state == "ForecastStates:Timeframe":
        cat = data.get("category", "fin")
        pairs = await get_available_pairs(cat)
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
        await ST.Pair.set()
    
    else:
        await cmd_start(m, state)


@dp.message_handler(lambda m: "🔄" in m.text or "New forecast" in m.text or "Новый прогноз" in m.text, state="*")
async def handle_restart(m: types.Message, state: FSMContext):
    await cmd_start(m, state)


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
    
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    cat = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=cat)
    
    pairs = await get_available_pairs(cat)
    
    if not pairs:
        await m.answer("No pairs available at the moment. Please try later.")
        await state.finish()
        return
    
    pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
    await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
    await ST.Pair.set()


@dp.message_handler(state=ST.Pair)
async def set_pair(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = data.get("category", "fin")
    
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    if "(N/A)" in m.text:
        na_text = "This pair is temporarily unavailable" if lang == "en" else "Эта пара временно недоступна"
        await m.answer(f"⚠️ {na_text}")
        
        pairs = await get_available_pairs(cat)
        pair_text = "Choose another pair:" if lang == "en" else "Выберите другую пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
        return
    
    pair_info = get_pair_info(m.text)
    
    if not pair_info:
        pairs = await get_available_pairs(cat)
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
        return
    
    is_available = await availability_checker.is_available(m.text)
    
    if not is_available:
        na_text = "This pair became unavailable" if lang == "en" else "Эта пара стала недоступна"
        await m.answer(f"⚠️ {na_text}")
        
        pairs = await get_available_pairs(cat)
        await m.answer("Choose another pair:", reply_markup=pairs_keyboard(pairs, lang))
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

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
    
    restart_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    restart_text = "🔄 Новый прогноз" if lang == "ru" else "🔄 New forecast"
    restart_kb.add(KeyboardButton(restart_text))
    restart_kb.add(KeyboardButton("/start"))
    
    processing_text = "⏳ Анализирую данные PocketOption..." if lang == "ru" else "⏳ Analyzing PocketOption data..."
    processing_msg = await m.answer(processing_text, reply_markup=ReplyKeyboardRemove())

    pairs = await get_available_pairs(cat)
    pair_info = get_pair_info(pair_human)
    
    if not pair_info:
        await processing_msg.delete()
        await m.answer(f"Error: Invalid pair {pair_human}", reply_markup=restart_kb)
        await state.finish()
        return

    try:
        logger.info(f"Loading OHLC data for {pair_human} ({pair_info}) on {tf}")
        cache_key = f"{pair_info['po']}_{tf}_{cat}"
        df = cache.get(cache_key)
        
        if df is None:
            df = await load_ohlc(pair_info, timeframe=tf, category=cat)
            if df is not None and len(df) > 0:
                cache.set(cache_key, df)
                logger.info(f"Cached data for {cache_key}")
        else:
            logger.info(f"Using cached data for {cache_key}")
        
        if df is None or len(df) == 0:
            raise Exception("No data received from PocketOption")
            
        logger.info(f"Got {len(df)} bars for analysis")
        
        if mode == "ind":
            logger.info("Computing indicators...")
            ind = compute_indicators(df)
            action, notes = signal_from_indicators(df, ind)
            result_message = format_forecast_message(mode, tf, action, ind, notes, lang)
        else:
            logger.info("Computing TA signal...")
            action, notes = simple_ta_signal(df)
            result_message = format_forecast_message(mode, tf, action, {}, notes, lang)
        
        await processing_msg.delete()
        await m.answer(result_message, parse_mode='Markdown', reply_markup=restart_kb)
        logger.info(f"Sent forecast: {action} for {tf}")
        
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        await processing_msg.delete()
        error_msg = f"❌ Ошибка анализа\n\nПричина: {str(e)}\n\nПопробуйте другую пару или таймфрейм"
        await m.answer(error_msg, reply_markup=restart_kb)

    if ENABLE_CHARTS and df is not None and len(df) > 0:
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
    
    try:
        df = await fetch_po_ohlc_async(pair_info['po'], timeframe=timeframe, otc=otc)
        if df is None or len(df) == 0:
            logger.warning(f"Empty dataframe received for {pair_info['po']}")
            return None
        
        try:
            from .utils.dataframe_fix import fix_ohlc_columns, validate_ohlc_data
            df = fix_ohlc_columns(df)
            if not validate_ohlc_data(df):
                logger.warning("OHLC data validation failed, but continuing")
        except ImportError:
            if 'close' in df.columns:
                df.columns = ['Open', 'High', 'Low', 'Close']
        
        logger.info(f"DataFrame columns: {df.columns.tolist()}")
        return df
        
    except Exception as e:
        logger.error(f"Failed to fetch OHLC: {e}")
        raise


async def auto_update_availability():
    while True:
        try:
            await availability_checker.update_availability()
            logger.info("Pairs availability updated")
        except Exception as e:
            logger.error(f"Failed to update availability: {e}")
        
        await asyncio.sleep(300)


def main():
    print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10] if TELEGRAM_TOKEN else 'NOT SET'}...")
    print(f"PO_ENABLE_SCRAPE: {PO_ENABLE_SCRAPE}")
    print(f"DEFAULT_LANG: {DEFAULT_LANG}")
    print(f"LOG_LEVEL: {LOG_LEVEL}")
    
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")
    
    logger.info("Starting Telegram bot...")
    logger.info(f"Bot configuration: PO_ENABLE_SCRAPE={PO_ENABLE_SCRAPE}, DEFAULT_LANG={DEFAULT_LANG}")

    loop = asyncio.get_event_loop()
    loop.create_task(auto_update_availability())

    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


if __name__ == "__main__":
    main()
