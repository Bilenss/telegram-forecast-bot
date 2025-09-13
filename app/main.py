import asyncio
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
    TELEGRAM_TOKEN, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, ENABLE_CHARTS, LOG_LEVEL
)
from .states import ForecastStates
from .keyboards_inline import (
    get_mode_keyboard, get_category_keyboard, get_pairs_keyboard,
    get_timeframe_keyboard, get_restart_keyboard
)
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import get_available_pairs, availability_checker, get_pair_info
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.fetchers import CompositeFetcher

logger = setup(LOG_LEVEL)

# Prometheus metrics
REQUEST_COUNT = Counter('bot_requests_total', 'Total number of requests', ['method', 'status'])
RESPONSE_TIME = Histogram('bot_response_duration_seconds', 'Response time in seconds', ['method'])
ACTIVE_USERS = Gauge('bot_active_users', 'Number of active users')
FORECAST_COUNT = Counter('bot_forecasts_total', 'Total number of forecasts', ['pair', 'timeframe', 'action'])
ERROR_COUNT = Counter('bot_errors_total', 'Total number of errors', ['error_type'])
CACHE_HITS = Counter('bot_cache_hits_total', 'Total number of cache hits')
CACHE_MISSES = Counter('bot_cache_misses_total', 'Total number of cache misses')

# Core
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)
_fetcher = CompositeFetcher()
active_users = set()


def track_time(method_name: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                REQUEST_COUNT.labels(method=method_name, status='success').inc()
                return result
            except Exception as e:
                REQUEST_COUNT.labels(method=method_name, status='error').inc()
                ERROR_COUNT.labels(error_type=type(e).__name__).inc()
                logger.exception(f"{method_name} error: {e}")
                raise
            finally:
                RESPONSE_TIME.labels(method=method_name).observe(time.time() - start)
        return wrapper
    return decorator


def format_forecast_message(mode: str, timeframe: str, action: str, data: Optional[dict] = None, notes=None) -> str:
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
    parts.extend(["", "_Analysis based on market data patterns_"])
    return "\n".join(parts)


@dp.message(Command("start"))
@track_time("start_command")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.update_data(lang="en")
    active_users.add(message.from_user.id)
    ACTIVE_USERS.set(len(active_users))
    await message.answer("Hello! Choose analysis mode:", reply_markup=get_mode_keyboard())
    await state.set_state(ForecastStates.Mode)


@dp.callback_query(F.data == "back")
async def handle_back(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    data = await state.get_data()

    if current == ForecastStates.Category.state:
        await callback.message.edit_text("Choose analysis mode:", reply_markup=get_mode_keyboard())
        await state.set_state(ForecastStates.Mode)

    elif current == ForecastStates.Pair.state:
        await callback.message.edit_text("Choose asset category:", reply_markup=get_category_keyboard())
        await state.set_state(ForecastStates.Category)

    elif current == ForecastStates.Timeframe.state:
        cat = data.get("category", "fin")
        pairs = await get_available_pairs(cat)
        await callback.message.edit_text("Choose pair:", reply_markup=get_pairs_keyboard(pairs))
        await state.set_state(ForecastStates.Pair)

    else:
        await state.clear()
        await callback.message.edit_text("Choose analysis mode:", reply_markup=get_mode_keyboard())
        await state.set_state(ForecastStates.Mode)

    await callback.answer()


@dp.callback_query(F.data == "restart")
async def handle_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(lang="en")
    await callback.message.edit_text("Choose analysis mode:", reply_markup=get_mode_keyboard())
    await state.set_state(ForecastStates.Mode)
    await callback.answer()


@dp.callback_query(StateFilter(ForecastStates.Mode))
@track_time("mode_selection")
async def set_mode(callback: CallbackQuery, state: FSMContext):
    await state.update_data(mode=callback.data)
    await callback.message.edit_text("Choose asset category:", reply_markup=get_category_keyboard())
    await state.set_state(ForecastStates.Category)
    await callback.answer()


@dp.callback_query(StateFilter(ForecastStates.Category))
@track_time("category_selection")
async def set_category(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back":
        await handle_back(callback, state)
        return

    cat = callback.data
    await state.update_data(category=cat)

    pairs = await get_available_pairs(cat)
    if not pairs:
        await callback.message.edit_text("No pairs available at the moment. Please try later.",
                                         reply_markup=get_restart_keyboard())
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text("Choose pair:", reply_markup=get_pairs_keyboard(pairs))
    await state.set_state(ForecastStates.Pair)
    await callback.answer()


@dp.callback_query(StateFilter(ForecastStates.Pair))
@track_time("pair_selection")
async def set_pair(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back":
        await handle_back(callback, state)
        return

    pair_name = callback.data

    if "(N/A)" in pair_name:
        await callback.answer("⚠️ This pair is temporarily unavailable", show_alert=True)
        pairs = await get_available_pairs("fin")
        await callback.message.edit_text("Choose another pair:", reply_markup=get_pairs_keyboard(pairs))
        return

    pair_info = get_pair_info(pair_name)
    if not pair_info:
        await callback.answer("Invalid pair selected", show_alert=True)
        pairs = await get_available_pairs("fin")
        await callback.message.edit_text("Choose pair:", reply_markup=get_pairs_keyboard(pairs))
        return

    is_available = await availability_checker.is_available(pair_name)
    if not is_available:
        await callback.answer("⚠️ This pair became unavailable", show_alert=True)
        pairs = await get_available_pairs("fin")
        await callback.message.edit_text("Choose another pair:", reply_markup=get_pairs_keyboard(pairs))
        return

    await state.update_data(pair=pair_name)
    await callback.message.edit_text("Choose timeframe:", reply_markup=get_timeframe_keyboard())
    await state.set_state(ForecastStates.Timeframe)
    await callback.answer()


@dp.callback_query(StateFilter(ForecastStates.Timeframe))
@track_time("forecast_generation")
async def set_timeframe(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back":
        await handle_back(callback, state)
        return

    data = await state.get_data()
    mode = data.get("mode", "ind")
    cat = data.get("category", "fin")
    pair_human = data.get("pair")
    tf = callback.data

    await callback.answer("⏳ Analyzing...")
    processing_msg = await callback.message.edit_text("⏳ Analyzing PocketOption data...")

    pair_info = get_pair_info(pair_human)
    if not pair_info:
        await processing_msg.edit_text("Error: Invalid pair", reply_markup=get_restart_keyboard())
        await state.clear()
        return

    try:
        cache_key = f"{pair_info['po']}_{tf}_{cat}"
        df = cache.get(cache_key)
        if df is None:
            CACHE_MISSES.inc()
            df = await _
