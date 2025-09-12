# app/main.py
from __future__ import annotations
import asyncio
import os
import tempfile
import time
from typing import Any, Dict, Optional, Tuple

from aiogram import Bot, Dispatcher, executor
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from loguru import logger

# пытаемся импортировать aioprometheus
try:
    from aioprometheus import Service, Counter, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from app.config import (
    TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, ENABLE_CHARTS, LOG_LEVEL,
    METRICS_ENABLED, METRICS_PORT
)
from app.keyboards_inline import mode_kb, category_kb, pairs_kb, timeframe_kb
from app.utils.cache import TTLCache
from app.utils.logging import setup
from app.pairs import get_available_pairs, availability_checker, get_pair_info
from app.analysis.indicators import compute_indicators
from app.analysis.decision import signal_from_indicators, simple_ta_signal
from app.data_sources.fetchers import CompositeFetcher
from app.utils.dataframe_fix import fix_ohlc_columns, validate_ohlc_data

# ------------------------------------------------------------------------------
# ЛОГ / БОТ / DP / КЭШ / FETCHER / METРИКИ
# ------------------------------------------------------------------------------
logger = setup(LOG_LEVEL)

bot     = Bot(token=TELEGRAM_TOKEN)
dp      = Dispatcher(bot, storage=MemoryStorage())
cache   = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)
fetcher = CompositeFetcher()

if PROMETHEUS_AVAILABLE:
    REQUESTS      = Counter("bot_requests_total", "Total bot requests")
    FETCH_LATENCY = Histogram("ohlc_fetch_latency_seconds", "OHLC fetch latency")
else:
    REQUESTS = FETCH_LATENCY = None

# ------------------------------------------------------------------------------
# ВСПОМОГАТЕЛИ: load_ohlc, format_forecast_message, run_analysis
# ------------------------------------------------------------------------------

async def load_ohlc(pair_info: dict, timeframe: str, category: str):
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PocketOption scraping is required (set PO_ENABLE_SCRAPE=1)")
    otc = (category == "otc")
    logger.info(f"Fetching {pair_info['po']} data (otc={otc}, tf={timeframe})")

    df = await fetcher.fetch(pair_info['po'], timeframe=timeframe, otc=otc)
    if not df or df.empty:
        logger.error("No OHLC data fetched")
        return None

    df = fix_ohlc_columns(df)
    if not validate_ohlc_data(df):
        logger.warning("Fixed invalid OHLC rows")

    logger.info(f"DataFrame columns: {df.columns.tolist()}")
    return df

def format_forecast_message(
    mode: str, timeframe: str, action: str,
    data: dict, notes: Optional[list]=None
) -> str:
    tf_up = timeframe.upper()
    lines = [
        f"🎯 **FORECAST for {tf_up}**", "",
        f"💡 Recommendation: **{action}**", ""
    ]
    if mode == "ind":
        lines += [
            "📊 **Indicators:**",
            f"• RSI: {data.get('RSI',0):.1f}",
            f"• EMA fast: {data.get('EMA_fast',0):.5f}",
            f"• EMA slow: {data.get('EMA_slow',0):.5f}",
            f"• MACD: {data.get('MACD',0):.5f}",
            f"• MACD signal: {data.get('MACD_signal',0):.5f}"
        ]
        if notes:
            lines += ["", "ℹ️ **Additional Notes:**"] + [f"• {n}" for n in notes]
    else:
        lines.append("📊 **Technical Analysis:**")
        if notes:
            lines += [f"• {n}" for n in notes]
        else:
            lines.append("• Market analysis completed")

    lines += ["", "_Analysis based on market data patterns_"]
    return "\n".join(lines)

async def run_analysis(
    df, timeframe: str, mode: str
) -> Tuple[str, Optional[str]]:
    if not df or df.empty:
        raise RuntimeError("No data to analyze")
    if mode == "ind":
        ind = compute_indicators(df)
        action, notes = signal_from_indicators(df, ind)
        text = format_forecast_message("ind", timeframe, action, ind, notes)
    else:
        action, notes = simple_ta_signal(df)
        text = format_forecast_message("ta", timeframe, action, {}, notes)
    return text, action

# ------------------------------------------------------------------------------
# METRICS SERVER
# ------------------------------------------------------------------------------
async def start_metrics_server():
    if not PROMETHEUS_AVAILABLE:
        logger.warning("METRICS_ENABLED=True but aioprometheus is not installed; skipping metrics server")
        return
    svc = Service()
    svc.register(REQUESTS)
    svc.register(FETCH_LATENCY)
    await svc.start(addr="0.0.0.0", port=METRICS_PORT)
    logger.info(f"Metrics exposed on :{METRICS_PORT}/metrics")

# ------------------------------------------------------------------------------
# PERIODIC AVAILABILITY UPDATES
# ------------------------------------------------------------------------------
async def auto_update_availability():
    while True:
        try:
            await availability_checker.update_availability()
            logger.info("Availability updated")
        except Exception as e:
            logger.error(f"Availability update error: {e}")
        await asyncio.sleep(300)

# ------------------------------------------------------------------------------
# HANDLERS
# ------------------------------------------------------------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(m: Message):
    await state_storage.clear(m.from_user.id)
    await state_storage.set(m.from_user.id, {"lang": DEFAULT_LANG})
    await m.answer("Choose mode:", reply_markup=mode_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("mode:"))
async def cb_mode(cq: CallbackQuery):
    await cq.answer()
    mode = cq.data.split(":",1)[1]
    await state_storage.update(cq.from_user.id, mode=mode)
    await cq.message.edit_text("Choose category:", reply_markup=category_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("category:"))
async def cb_category(cq: CallbackQuery):
    await cq.answer()
    category = cq.data.split(":",1)[1]
    uid = cq.from_user.id
    await state_storage.update(uid, category=category)
    pairs = await get_available_pairs(category)
    if not pairs:
        await cq.message.edit_text("No pairs available, try later.")
        await state_storage.clear(uid)
        return
    await cq.message.edit_text("Choose pair:", reply_markup=pairs_kb(pairs))

@dp.callback_query_handler(lambda c: c.data.startswith("pair:"))
async def cb_pair(cq: CallbackQuery):
    await cq.answer()
    pair_code = cq.data.split(":",1)[1]
    uid = cq.from_user.id
    if not await availability_checker.is_available(pair_code):
        st = await state_storage.get(uid)
        kb = pairs_kb(await get_available_pairs(st["category"]))
        await cq.message.edit_text("⚠️ Unavailable, choose again:", reply_markup=kb)
        return
    await state_storage.update(uid, pair=pair_code)
    st = await state_storage.get(uid)
    await cq.message.edit_text("Choose timeframe:", reply_markup=timeframe_kb(st["category"]))

@dp.callback_query_handler(lambda c: c.data == "back:category")
async def cb_back_category(cq: CallbackQuery):
    await cq.answer()
    await state_storage.clear(cq.from_user.id)
    await cq.message.edit_text("Choose category:", reply_markup=category_kb())

@dp.callback_query_handler(lambda c: c.data == "back:pair")
async def cb_back_pair(cq: CallbackQuery):
    await cq.answer()
    st = await state_storage.get(cq.from_user.id)
    await state_storage.update(cq.from_user.id, pair=None)
    kb = pairs_kb(await get_available_pairs(st["category"]))
    await cq.message.edit_text("Choose pair:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("timeframe:"))
async def cb_timeframe(cq: CallbackQuery):
    await cq.answer()
    tf = cq.data.split(":",1)[1]
    uid = cq.from_user.id
    st = await state_storage.get(uid)
    mode, category, pair_code = st["mode"], st["category"], st["pair"]
    await state_storage.update(uid, timeframe=tf)
    await cq.message.edit_text("⏳ Analyzing…")

    cache_key = f"{pair_code}_{tf}_{category}"
    df = cache.get(cache_key)

    try:
        if df is None:
            if PROMETHEUS_AVAILABLE:
                REQUESTS.inc({"type":"ohlc"})
            start = time.time()
            df = await load_ohlc(get_pair_info(pair_code), tf, category)
            if PROMETHEUS_AVAILABLE:
                FETCH_LATENCY.observe({"type":"ohlc"}, time.time() - start)
            if df:
                cache.set(cache_key, df)

        if not df or df.empty:
            raise RuntimeError("Empty data")

        text, _ = await run_analysis(df, tf, mode)
        await cq.message.edit_text(text, parse_mode="Markdown")

        if ENABLE_CHARTS:
            from app.utils.charts import plot_candles
            with tempfile.TemporaryDirectory() as td:
                path = os.path.join(td, "chart.png")
                out = plot_candles(df, path)
                if out and os.path.exists(out):
                    await bot.send_photo(cq.message.chat.id, InputFile(out))
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        await cq.message.edit_text(f"❌ Error: {e}\nPress /start")

    await state_storage.clear(uid)

# ------------------------------------------------------------------------------
# ENTRYPOINT
# ------------------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN is required")

    loop = asyncio.get_event_loop()
    loop.create_task(auto_update_availability())
    if METRICS_ENABLED:
        loop.create_task(start_metrics_server())

    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()
