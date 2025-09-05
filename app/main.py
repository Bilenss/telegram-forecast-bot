from __future__ import annotations
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext

from .config import TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS, PO_ENABLE_SCRAPE, ENABLE_CHARTS, LOG_LEVEL
from .states import ForecastStates as ST
from .keyboards import lang_keyboard, mode_keyboard, category_keyboard, pairs_keyboard, timeframe_keyboard
from .utils.cache import TTLCache
from .utils.logging import setup
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

# -------------------- helpers --------------------

def _cache_key(pair_info: dict, timeframe: str) -> str:
    return f"{pair_info.get('po','')}:{timeframe}"

def _fetch_ohlc(pair_info: dict, timeframe: str):
    cache_key = f"{pair_info['po']}:{timeframe}"
    df = cache.get(cache_key)
    if df is not None:
        return df

    is_otc = bool(pair_info.get("otc", False))

    if is_otc:
        if not PO_ENABLE_SCRAPE:
            raise RuntimeError("OTC requires PocketOption scraping (PO_ENABLE_SCRAPE=1)")
        df = fetch_po_ohlc(pair_info['po'], timeframe=timeframe, otc=True)
        cache.set(cache_key, df)
        return df

    if PO_ENABLE_SCRAPE:
        try:
            df = fetch_po_ohlc(pair_info['po'], timeframe=timeframe, otc=False)
            cache.set(cache_key, df)
            return df
        except Exception as e:
            logger.debug(f"PO scraping failed: {e}")

    df = fetch_public_ohlc(pair_info['yf'], timeframe=timeframe)
    cache.set(cache_key, df)
    return df

# -------------------- handlers --------------------

@dp.message_handler(commands=['start'])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer(INTRO_RU if DEFAULT_LANG == 'ru' else INTRO_EN, reply_markup=lang_keyboard())
    await ST.Language.set()

@dp.message_handler(lambda m: m.text in ["RU", "EN"], state=ST.Language)
async def lang_selected(m: types.Message, state: FSMContext):
    lang = 'ru' if m.text == "RU" else 'en'
    await state.update_data(lang=lang)
    text = "Выберите режим анализа:" if lang == 'ru' else "Choose analysis mode:"
    await m.answer(text, reply_markup=mode_keyboard(lang))
    await ST.Mode.set()

@dp.message_handler(lambda m: m.text in ["📊 Технический анализ", "📈 Индикаторы", "📊 Technical analysis", "📈 Indicators"], state=ST.Mode)
async def mode_selected(m: types.Message, state: FSMContext):
    lang = (await state.get_data()).get("lang", "ru")
    mode = "ta" if "Техничес" in m.text or "Technical" in m.text else "ind"
    await state.update_data(mode=mode)
    text = "Выберите категорию актива:" if lang == 'ru' else "Choose asset category:"
    await m.answer(text, reply_markup=category_keyboard(lang))
    await ST.Category.set()

@dp.message_handler(lambda m: m.text in ["💰 ACTIVE FIN", "⏱️ ACTIVE OTC"], state=ST.Category)
async def category_selected(m: types.Message, state: FSMContext):
    lang = (await state.get_data()).get("lang", "ru")
    category = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=category)
    pairs = all_pairs(category)
    text = "Выберите валютную пару:" if lang == 'ru' else "Choose a pair:"
    await m.answer(text, reply_markup=pairs_keyboard(pairs))
    await ST.Pair.set()

@dp.message_handler(state=ST.Pair)
async def pair_selected(m: types.Message, state: FSMContext):
    lang = (await state.get_data()).get("lang", "ru")
    category = (await state.get_data()).get("category", "fin")
    pairs = all_pairs(category)
    if m.text not in pairs:
        await m.answer("Пожалуйста, выберите из клавиатуры." if lang == 'ru' else "Please use the keyboard.")
        return
    await state.update_data(pair=m.text)
    text = "Выберите таймфрейм:" if lang == 'ru' else "Select timeframe:"
    await m.answer(text, reply_markup=timeframe_keyboard(lang, po_available=bool(PO_ENABLE_SCRAPE)))
    await ST.Timeframe.set()

@dp.message_handler(state=ST.Timeframe)
async def timeframe_selected(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    category = data.get("category", "fin")
    mode = data.get("mode", "ind")
    pair_name = data.get("pair")
    pairs = all_pairs(category)
    info = pairs[pair_name]
    timeframe = m.text.strip()

    await m.answer("Готовлю данные..." if lang == 'ru' else "Fetching data...")

    try:
        df = await asyncio.wait_for(
            asyncio.to_thread(_fetch_ohlc, info, timeframe),
            timeout=35
        )
    except asyncio.TimeoutError:
        msg_ru = ("Истек таймаут получения данных с PocketOption. Попробуйте другой таймфрейм или позже, "
                  "либо выберите категорию 💰 ACTIVE FIN.")
        msg_en = ("Timed out fetching data from PocketOption. Try another timeframe or later, "
                  "or choose 💰 ACTIVE FIN.")
        await m.answer(msg_ru if lang == 'ru' else msg_en)
        await state.finish()
        return
    except Exception as e:
        if info.get("otc"):
            msg_ru = ("OTC-пары доступны только на платформе PocketOption. Сейчас не удалось получить данные. "
                      "Попробуйте другой таймфрейм или позже, либо выберите категорию 💰 ACTIVE FIN.")
            msg_en = ("OTC pairs are available only on PocketOption. Failed to fetch data now. "
                      "Try another timeframe or later, or choose 💰 ACTIVE FIN.")
            await m.answer(msg_ru if lang == 'ru' else msg_en)
        else:
            await m.answer("Не удалось получить котировки сейчас." if lang == 'ru' else "Failed to fetch quotes right now.")
        logger.debug(f"Fetch error: {e}")
        await state.finish()
        return

    # анализ
    if mode == "ind":
        ind = compute_indicators(df)
        action, notes = signal_from_indicators(df, ind)
    else:
        action, notes = simple_ta_signal(df)
        ind = {}

    # только текст (графики отключены)
    if lang == "ru":
        lines = [f"👉 Прогноз: <b>{action}</b>"]
        if ind:
            lines.append("📈 Индикаторы: " + ", ".join([
                f"RSI={ind['RSI']}", f"EMA9={ind['EMA_fast']}", f"EMA21={ind['EMA_slow']}"
            ]))
        if notes:
            lines.append("ℹ️ " + "; ".join(notes))
    else:
        lines = [f"👉 Forecast: <b>{action}</b>"]
        if ind:
            lines.append("📈 Indicators: " + ", ".join([
                f"RSI={ind['RSI']}", f"EMA9={ind['EMA_fast']}", f"EMA21={ind['EMA_slow']}"
            ]))
        if notes:
            lines.append("ℹ️ " + "; ".join(notes))

    await m.answer("\n".join(lines), parse_mode="HTML")
    await state.finish()

def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()
