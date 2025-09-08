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
from .keyboards import (
    mode_keyboard, category_keyboard, pairs_keyboard, 
    timeframe_keyboard, restart_keyboard, remove_keyboard
)
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import all_pairs
from .analysis.fast_prediction import fast_predictor
from .data_sources.pocketoption_scraper import fetch_po_ohlc_async

logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)

@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await state.update_data(lang=DEFAULT_LANG)
    
    welcome_text = "Hello! Choose analysis mode:" if DEFAULT_LANG == "en" else "Привет! Выберите режим анализа:"
    await m.answer(welcome_text, reply_markup=mode_keyboard(DEFAULT_LANG))
    await ST.Mode.set()

@dp.message_handler(lambda m: "⬅️" in m.text, state="*")
async def handle_back(m: types.Message, state: FSMContext):
    """Обработка кнопки Назад"""
    current_state = await state.get_state()
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    if current_state == "ForecastStates:Category":
        # Возврат к выбору режима
        welcome_text = "Choose analysis mode:" if lang == "en" else "Выберите режим анализа:"
        await m.answer(welcome_text, reply_markup=mode_keyboard(lang))
        await ST.Mode.set()
    
    elif current_state == "ForecastStates:Pair":
        # Возврат к выбору категории
        category_text = "Choose asset category:" if lang == "en" else "Выберите категорию актива:"
        await m.answer(category_text, reply_markup=category_keyboard(lang))
        await ST.Category.set()
    
    elif current_state == "ForecastStates:Timeframe":
        # Возврат к выбору пары
        cat = data.get("category", "fin")
        pairs = all_pairs(cat)
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
        await ST.Pair.set()
    
    else:
        # По умолчанию возврат к старту
        await cmd_start(m, state)

@dp.message_handler(lambda m: "🔄" in m.text, state="*")
async def handle_restart(m: types.Message, state: FSMContext):
    """Обработка кнопки Новый прогноз"""
    await cmd_start(m, state)

@dp.message_handler(state=ST.Mode)
async def set_mode(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    mode = "ta" if "Тех" in m.text or "Technical" in m.text else "ind"
    await state.update_data(mode=mode)
    
    category_text = "Choose asset category:" if lang == "en" else "Выберите категорию актива:"
    await m.answer(category_text, reply_markup=category_keyboard(lang))
    await ST.Category.set()

@dp.message_handler(state=ST.Category)
async def set_category(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    cat = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=cat)
    
    pairs = all_pairs(cat)
    pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
    await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
    await ST.Pair.set()

@dp.message_handler(state=ST.Pair)
async def set_pair(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = data.get("category", "fin")
    pairs = all_pairs(cat)
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    if m.text not in pairs:
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
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
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return

    # ВАЖНО: Убираем клавиатуру сразу после выбора
    processing_text = "⏳ Analyzing PocketOption data..." if lang == "en" else "⏳ Анализирую данные PocketOption..."
    processing_msg = await m.answer(processing_text, reply_markup=remove_keyboard())

    pairs = all_pairs(cat)
    pair_info = pairs.get(pair_human)
    
    if not pair_info:
        await processing_msg.edit_text(f"Error: Invalid pair {pair_human}")
        await m.answer("Press /start to begin again", reply_markup=restart_keyboard(lang))
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
        
        # Используем быстрый предиктор
        prediction_text, prediction_data = await fast_predictor.get_fast_prediction(
            pair=pair_human,
            timeframe=tf,
            df=df,
            mode=mode
        )
        
        # Отправляем прогноз с кнопкой перезапуска
        await processing_msg.delete()  # Удаляем сообщение о загрузке
        await m.answer(prediction_text, 
                      parse_mode='Markdown',
                      reply_markup=restart_keyboard(lang))
        
        logger.info(f"Sent fast forecast for {pair_human} {tf}")
        
    except Exception as e:
        logger.error(f"Error loading/analyzing OHLC data: {e}")
        error_text = f"Failed to analyze {pair_human} at timeframe {tf}\nError: {str(e)}"
        await processing_msg.edit_text(error_text)
        await m.answer("Press /start to begin again", reply_markup=restart_keyboard(lang))
        await state.finish()
        return

    # Отправка графика если включено
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
    
    logger.info("Starting Telegram bot with fast predictions...")
    logger.info(f"Bot configuration: PO_ENABLE_SCRAPE={PO_ENABLE_SCRAPE}, DEFAULT_LANG={DEFAULT_LANG}")
    
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise

if __name__ == "__main__":
    main()
