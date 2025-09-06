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

LANG = {"ru": {"hi": "Привет! Выберите язык / Choose language",
               "mode": "Выберите режим анализа",
               "category": "Выберите категорию актива",
               "pair": "Выберите валютную пару",
               "tf": "Выберите таймфрейм",
               "processing": "Секунду, анализирую…",
               "otc_need_po": "OTC доступно только при включённом скрапинге PocketOption.",
               "no_data": "Не удалось получить данные для {} на таймфрейме {}",
               "result": "👉 Прогноз: <b>{}</b>",
               "ind": "📈 Индикаторы: RSI={}; EMAfast={}; EMAslow={}; EMAcrossUp={}; EMAcrossDown={}; MACD={}; MACDs={}; MACDh={}",
               "notes": "ℹ️ {}",
               "chart": "График: {}"},
        "en": {"hi": "Hello! Choose language",
               "mode": "Choose analysis mode",
               "category": "Choose asset category",
               "pair": "Choose pair",
               "tf": "Choose timeframe",
               "processing": "One sec, crunching data…",
               "otc_need_po": "OTC is available only when PocketOption scraping is enabled.",
               "no_data": "Failed to load data for {} at timeframe {}",
               "result": "👉 Signal: <b>{}</b>",
               "ind": "📈 Indicators: RSI={}; EMAfast={}; EMAslow={}; EMAcrossUp={}; EMAcrossDown={}; MACD={}; MACDs={}; MACDh={}",
               "notes": "ℹ️ {}",
               "chart": "Chart: {}"}}

def tr(lang, key):
    return LANG["ru" if lang == "ru" else "en"][key]

@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer(tr(DEFAULT_LANG, "hi"), reply_markup=lang_keyboard())
    await ST.Language.set()

@dp.message_handler(state=ST.Language)
async def set_lang(m: types.Message, state: FSMContext):
    lang = "ru" if "RU" in m.text.upper() else "en"
    await state.update_data(lang=lang)
    await m.answer(tr(lang, "mode"), reply_markup=mode_keyboard(lang))
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
    po_available = bool(PO_ENABLE_SCRAPE)
    await m.answer(tr(lang, "tf"), reply_markup=timeframe_keyboard(lang, po_available))
    await ST.Timeframe.set()

@dp.message_handler(state=ST.Timeframe)
async def set_timeframe(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    mode = data.get("mode", "ind")
    cat = data.get("category", "fin")
    pair_human = data.get("pair")
    tf = m.text.strip().lower()

    await m.answer(tr(lang, "processing"))

    pairs = all_pairs(cat)
    pair_info = pairs.get(pair_human)
    try:
        df = await load_ohlc(pair_info, timeframe=tf, category=cat)
    except Exception as e:
        await m.answer(tr(lang, "no_data").format(pair_human, tf) + f"\n{e}")
        await state.finish()
        return

    if mode == "ind":
        ind = compute_indicators(df)
        action, notes = signal_from_indicators(df, ind)
        msg = [tr(lang, "result").format(action)]
        msg.append(tr(lang, "ind").format(ind["RSI"], ind["EMA_fast"], ind["EMA_slow"], ind["EMA_cross_up"], ind["EMA_cross_down"], ind["MACD"], ind["MACD_signal"], ind["MACD_hist"]))
        if notes:
            msg.append(tr(lang, "notes").format("; ".join(notes)))
        await m.answer("\n".join(msg), parse_mode="HTML")
    else:
        action, notes = simple_ta_signal(df)
        msg = [tr(lang, "result").format(action)]
        if notes:
            msg.append(tr(lang, "notes").format("; ".join(notes)))
        await m.answer("\n".join(msg), parse_mode="HTML")

    # charts optional
    if ENABLE_CHARTS:
        try:
            from .utils.charts import plot_candles
            import os, tempfile
            with tempfile.TemporaryDirectory() as tmpd:
                p = os.path.join(tmpd, "chart.png")
                out = plot_candles(df, p)
                if out:
                    await m.answer_photo(types.InputFile(out))
        except Exception as e:
            logger.error(f"Chart error: {e}")

    await state.finish()

async def load_ohlc(pair_info: dict, timeframe: str, category: str):
    # OTC only with PocketOption (not supported by public feeds)
    if category == "otc":
        if not PO_ENABLE_SCRAPE:
            raise RuntimeError("OTC: " + tr("ru", "otc_need_po"))
        df = fetch_po_ohlc(pair_info['po'], timeframe=timeframe, otc=True)
        return df

    # FIN: try PocketOption if enabled
    if PO_ENABLE_SCRAPE:
        try:
            df = fetch_po_ohlc(pair_info['po'], timeframe=timeframe, otc=False)
            return df
        except Exception as e:
            logger.debug(f"PO scraping failed, fallback to public feed: {e}")

    # Fallback to public (yfinance)
    df = fetch_public_ohlc(pair_info['yf'], timeframe=timeframe, limit=400)
    return df

def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()
