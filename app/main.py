import os, asyncio, random, time
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from .config import TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS, PO_ENABLE_SCRAPE, ENABLE_CHARTS, TMP_DIR, LOG_LEVEL
from .states import ForecastStates as ST
from .keyboards import lang_keyboard, mode_keyboard, category_keyboard, pairs_keyboard, timeframe_keyboard
from .utils.cache import TTLCache
from .utils.logging import setup
from .utils.charts import plot_candles
from .pairs import all_pairs
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.pocketoption_scraper import fetch_po_ohlc
from .data_sources.fallback_quotes import fetch_public_ohlc

logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)

INTRO_RU = "Привет! Я бот прогнозов. Выберите язык."
INTRO_EN = "Hello! I am a forecasts bot. Choose language."

@dp.message_handler(commands=['start'])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer(INTRO_RU if DEFAULT_LANG=='ru' else INTRO_EN, reply_markup=lang_keyboard())
    await ST.Language.set()

@dp.message_handler(lambda m: m.text in ["RU", "EN"], state=ST.Language)
async def lang_selected(m: types.Message, state: FSMContext):
    lang = 'ru' if m.text == "RU" else 'en'
    await state.update_data(lang=lang)
    text = "Выберите режим анализа:" if lang=='ru' else "Choose analysis mode:"
    await m.answer(text, reply_markup=mode_keyboard(lang))
    await ST.Mode.set()

@dp.message_handler(lambda m: m.text in ["📊 Технический анализ","📈 Индикаторы","📊 Technical analysis","📈 Indicators"], state=ST.Mode)
async def mode_selected(m: types.Message, state: FSMContext):
    lang = (await state.get_data()).get("lang","ru")
    mode = "ta" if "Техничес" in m.text or "Technical" in m.text else "ind"
    await state.update_data(mode=mode)
    text = "Выберите категорию актива:" if lang=='ru' else "Choose asset category:"
    await m.answer(text, reply_markup=category_keyboard(lang))
    await ST.Category.set()

@dp.message_handler(lambda m: m.text in ["💰 ACTIVE FIN","⏱️ ACTIVE OTC"], state=ST.Category)
async def category_selected(m: types.Message, state: FSMContext):
    lang = (await state.get_data()).get("lang","ru")
    category = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=category)
    pairs = all_pairs(category)
    text = "Выберите валютную пару:" if lang=='ru' else "Choose a pair:"
    await m.answer(text, reply_markup=pairs_keyboard(pairs))
    await ST.Pair.set()

@dp.message_handler(state=ST.Pair)
async def pair_selected(m: types.Message, state: FSMContext):
    lang = (await state.get_data()).get("lang","ru")
    category = (await state.get_data()).get("category","fin")
    pairs = all_pairs(category)
    if m.text not in pairs:
        await m.answer("Пожалуйста, выберите из клавиатуры." if lang=='ru' else "Please use the keyboard.")
        return
    await state.update_data(pair=m.text)
    text = "Выберите таймфрейм:" if lang=='ru' else "Select timeframe:"
    await m.answer(text, reply_markup=timeframe_keyboard(lang))
    await ST.Timeframe.set()

def _fetch_ohlc(pair_info: dict, timeframe: str):
    # Cache first
    cache_key = f"{pair_info['po']}:{timeframe}"
    df = cache.get(cache_key)
    if df is not None:
        return df
    # Try PocketOption scraping if enabled
    if PO_ENABLE_SCRAPE:
        try:
            df = fetch_po_ohlc(pair_info['po'], timeframe=timeframe)
            cache.set(cache_key, df); return df
        except Exception as e:
            logger.warning(f"PO scraping failed: {e}")
    # Fallback public quotes
    try:
        df = fetch_public_ohlc(pair_info['yf'], timeframe=timeframe)
        cache.set(cache_key, df); return df
    except Exception as e:
        logger.error(f"Public quotes failed: {e}")
        raise

@dp.message_handler(state=ST.Timeframe)
async def timeframe_selected(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang","ru")
    category = data.get("category","fin")
    mode = data.get("mode","ind")
    pair_name = data.get("pair")
    pairs = all_pairs(category)
    info = pairs[pair_name]
    timeframe = m.text.strip()

    await m.answer(("Готовлю данные..." if lang=='ru' else "Fetching data..."))
    try:
        df = _fetch_ohlc(info, timeframe)
    except Exception:
        await m.answer("Не удалось получить котировки сейчас." if lang=='ru' else "Failed to fetch quotes right now.")
        await state.finish()
        return

    if mode == "ind":
        ind = compute_indicators(df)
        action, notes = signal_from_indicators(df, ind)
    else:
        action, notes = simple_ta_signal(df)
        ind = {}

    # Chart
    photo_path = ""
    if ENABLE_CHARTS:
        fname = os.path.join(TMP_DIR, f"chart_{int(time.time())}.png")
        photo_path = plot_candles(df, fname)

    # Message
    if lang == "ru":
        lines = [f"👉 Прогноз: <b>{action}</b>"]
        if ind:
            lines.append("📈 Индикаторы: " + ", ".join([f"RSI={ind['RSI']}", f"EMA9={ind['EMA_fast']}", f"EMA21={ind['EMA_slow']}"]))
        if notes:
            lines.append("ℹ️ " + "; ".join(notes))
        text = "\n".join(lines)
    else:
        lines = [f"👉 Forecast: <b>{action}</b>"]
        if ind:
            lines.append("📈 Indicators: " + ", ".join([f"RSI={ind['RSI']}", f"EMA9={ind['EMA_fast']}", f"EMA21={ind['EMA_slow']}"]))
        if notes:
            lines.append("ℹ️ " + "; ".join(notes))
        text = "\n".join(lines)

    if photo_path and os.path.exists(photo_path):
        with open(photo_path, "rb") as ph:
            await m.answer_photo(ph, caption=text, parse_mode="HTML")
    else:
        await m.answer(text, parse_mode="HTML")

    await state.finish()

def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()
