# app/main.py
# -*- coding: utf-8 -*-

import asyncio
import datetime
import time
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from aiohttp import web

from .config import (
    TELEGRAM_TOKEN,
    CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE,
    ENABLE_CHARTS,
    LOG_LEVEL,
)
from .states import ForecastStates
from .keyboards_inline import (
    get_mode_keyboard,
    get_category_keyboard,
    get_pairs_keyboard,
    get_timeframe_keyboard,
    get_restart_keyboard,
)
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import get_available_pairs, availability_checker, get_pair_info
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.fetchers import CompositeFetcher

logger = setup(LOG_LEVEL)

# Prometheus metrics
REQUEST_COUNT = Counter("bot_requests_total", "Total number of requests", ["method", "status"])
RESPONSE_TIME = Histogram("bot_response_duration_seconds", "Response time in seconds", ["method"])
ACTIVE_USERS = Gauge("bot_active_users", "Number of active users")
FORECAST_COUNT = Counter("bot_forecasts_total", "Total number of forecasts", ["pair", "timeframe", "action"])
ERROR_COUNT = Counter("bot_errors_total", "Total number of errors", ["error_type"])
CACHE_HITS = Counter("bot_cache_hits_total", "Total number of cache hits")
CACHE_MISSES = Counter("bot_cache_misses_total", "Total number of cache misses")

# Core setup
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)
_fetcher = CompositeFetcher()
active_users: set[int] = set()

def track_time(method_name: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                REQUEST_COUNT.labels(method=method_name, status="success").inc()
                return result
            except Exception as e:
                REQUEST_COUNT.labels(method=method_name, status="error").inc()
                ERROR_COUNT.labels(error_type=type(e).__name__).inc()
                logger.exception(f"{method_name} error")
                raise
            finally:
                RESPONSE_TIME.labels(method=method_name).observe(time.time() - start)
        return wrapper
    return decorator

def format_forecast_message(
    mode: str,
    timeframe: str,
    action: str,
    data: Optional[dict] = None,
    notes: Optional[list[str]] = None,
) -> str:
    tf_upper = timeframe.upper()
    if mode == "ind" and data:
        parts = [
            f"🎯 FORECAST for {tf_upper}",
            "",
            f"💡 Recommendation: {action}",
            "",
            "📊 Indicators:",
            f"• RSI: {data.get('RSI', 0):.1f}",
            f"• EMA fast: {data.get('EMA_fast', 0):.5f}",
            f"• EMA slow: {data.get('EMA_slow', 0):.5f}",
            f"• MACD: {data.get('MACD', 0):.5f}",
            f"• MACD signal: {data.get('MACD_signal', 0):.5f}",
        ]
    else:
        parts = [
            f"🎯 FORECAST for {tf_upper}",
            "",
            f"💡 Recommendation: {action}",
            "",
            "📊 Technical Analysis:",
        ]
        if notes:
            parts.extend([f"• {n}" for n in notes])
        else:
            parts.append("• Market analysis completed")
    if notes and mode == "ind":
        parts.extend(["", "ℹ️ Additional Notes:"])
        parts.extend([f"• {n}" for n in notes])
    parts.append("")
    parts.append("_Analysis based on market data patterns_")
    return "\n".join(parts)

@dp.message(Command("start"))
@track_time("start_command")
async def cmd_start(message: types.Message, state: FSMContext, **kwargs):
    await state.clear()
    await state.update_data(lang="en")
    active_users.add(message.from_user.id)
    ACTIVE_USERS.set(len(active_users))

    await message.answer("Hello! Choose analysis mode:", reply_markup=get_mode_keyboard())
    await state.set_state(ForecastStates.Mode)

@dp.callback_query(F.data == "analysis", StateFilter(ForecastStates.Mode))
@track_time("mode_selection")
async def set_mode(callback: CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    await state.update_data(mode="ind")
    await callback.message.answer("Choose asset category:", reply_markup=get_category_keyboard())
    await state.set_state(ForecastStates.Category)

@dp.callback_query(StateFilter(ForecastStates.Category))
@track_time("category_selection")
async def set_category(callback: CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    if callback.data == "back":
        return await cmd_start(callback.message, state)

    cat = callback.data  # "fin" | "otc"
    # выходные для fin
    weekday = datetime.datetime.utcnow().weekday()  # Mon=0 … Sun=6
    if cat == "fin" and weekday in (5, 6):
        return await callback.message.answer(
            "Financial market is closed on weekends. Please try again on Monday.",
            reply_markup=get_restart_keyboard()
        )

    await state.update_data(category=cat)
    pairs = await get_available_pairs(cat)
    if not pairs:
        return await callback.message.answer(
            "No pairs available at the moment. Please try later.",
            reply_markup=get_restart_keyboard()
        )

    await callback.message.answer("Choose pair:", reply_markup=get_pairs_keyboard(pairs))
    await state.set_state(ForecastStates.Pair)

@dp.callback_query(StateFilter(ForecastStates.Pair))
@track_time("pair_selection")
async def set_pair(callback: CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    if callback.data == "back":
        return await set_category(callback, state)

    pair_name = callback.data
    if "(N/A)" in pair_name:
        return await callback.message.answer(
            "⚠️ This pair is temporarily unavailable",
            reply_markup=get_restart_keyboard()
        )

    pair_info = get_pair_info(pair_name)
    if not pair_info:
        return await callback.message.answer(
            "Invalid pair selected",
            reply_markup=get_restart_keyboard()
        )

    if not await availability_checker.is_available(pair_name):
        return await callback.message.answer(
            "⚠️ This pair became unavailable",
            reply_markup=get_restart_keyboard()
        )

    await state.update_data(pair=pair_name)
    await callback.message.answer("Choose timeframe:", reply_markup=get_timeframe_keyboard())
    await state.set_state(ForecastStates.Timeframe)

@dp.callback_query(StateFilter(ForecastStates.Timeframe))
@track_time("forecast_generation")
async def set_timeframe(callback: CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    if callback.data == "back":
        return await set_pair(callback, state)

    data = await state.get_data()
    mode = data.get("mode", "ind")
    cat = data.get("category", "fin")
    pair_human = data.get("pair")
    tf = callback.data

    processing = await callback.message.answer("⏳ Analyzing PocketOption data...")
    try:
        cache_key = f"{get_pair_info(pair_human)['po']}_{tf}_{cat}"
        df = cache.get(cache_key)
        if df is None:
            CACHE_MISSES.inc()
            df = await _fetcher.fetch(get_pair_info(pair_human)["po"], timeframe=tf, otc=(cat == "otc"))
            if df and len(df) > 0:
                cache.set(cache_key, df)
        else:
            CACHE_HITS.inc()

        if not df or df.empty:
            raise RuntimeError("No data received from PocketOption")

        if mode == "ind":
            ind = compute_indicators(df)
            action, notes = signal_from_indicators(df, ind)
            text = format_forecast_message(mode, tf, action, ind, notes)
        else:
            action, notes = simple_ta_signal(df)
            text = format_forecast_message(mode, tf, action, {}, notes)

        FORECAST_COUNT.labels(pair=pair_human, timeframe=tf, action=action).inc()
        await processing.edit_text(text, reply_markup=get_restart_keyboard())

    except Exception as e:
        ERROR_COUNT.labels(error_type="analysis_error").inc()
        await processing.edit_text(
            f"❌ Analysis error\n\nReason: {e}\nTry another pair or timeframe",
            reply_markup=get_restart_keyboard()
        )

    await state.clear()

async def metrics_handler(request):
    return web.Response(body=generate_latest(), content_type="text/plain")

async def start_metrics_server():
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def auto_update_availability():
    while True:
        await availability_checker.update_availability()
        await asyncio.sleep(300)

async def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")
    logger.info("Starting Telegram bot...")
    asyncio.create_task(start_metrics_server())
    asyncio.create_task(auto_update_availability())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
