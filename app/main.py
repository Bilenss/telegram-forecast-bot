from __future__ import annotations
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from aiohttp import web
import time

from .config import (
    TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, PO_STRICT_ONLY,
    ENABLE_CHARTS, LOG_LEVEL
)
from .states import ForecastStates as ST
from .keyboards_inline import (
    get_mode_keyboard, get_category_keyboard, get_pairs_keyboard,
    get_timeframe_keyboard, get_restart_keyboard
)
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import all_pairs, get_available_pairs, availability_checker, get_pair_info
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

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)

# Создаём единственный инстанс CompositeFetcher для всего приложения
_fetcher = CompositeFetcher()

# Хранилище активных пользователей
active_users = set()


def track_time(method_name):
    """Decorator to track execution time"""
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
                raise
            finally:
                RESPONSE_TIME.labels(method=method_name).observe(time.time() - start)
        return wrapper
    return decorator


def format_forecast_message(mode, timeframe, action, data, notes=None, lang="en"):
    """Format forecast message - always in English"""
    tf_upper = timeframe.upper()

    if mode == "ind":
        # For indicators
        message_parts = [
            f"🎯 **FORECAST for {tf_upper}**",
            "",
            f"💡 Recommendation: **{action}**",
            "",
            "📊 **Indicators:**",
            f"• RSI: {data['RSI']:.1f}",
            f"• EMA fast: {data['EMA_fast']:.5f}",
            f"• EMA slow: {data['EMA_slow']:.5f}",
            f"• MACD: {data['MACD']:.5f}",
            f"• MACD signal: {data['MACD_signal']:.5f}"
        ]
    else:
        # For technical analysis
        message_parts = [
            f"🎯 **FORECAST for {tf_upper}**",
            "",
            f"💡 Recommendation: **{action}**",
            "",
            "📊 **Technical Analysis:**"
        ]

        if notes:
            for note in notes:
                message_parts.append(f"• {note}")
        else:
            message_parts.append("• Market analysis completed")

    if notes and mode == "ind":
        message_parts.extend(["", "ℹ️ **Additional Notes:**"])
        for note in notes:
            message_parts.append(f"• {note}")

    message_parts.extend(["", "_Analysis based on market data patterns_"])

    return "\n".join(message_parts)


@dp.message_handler(commands=["start"])
@track_time("start_command")
async def cmd_start(m: types.Message, state: FSMContext, **kwargs):
    await state.finish()
    await state.update_data(lang="en")  # Always English

    # Track active user
    active_users.add(m.from_user.id)
    ACTIVE_USERS.set(len(active_users))

    welcome_text = "Hello! Choose analysis mode:"
    await m.answer(welcome_text, reply_markup=get_mode_keyboard())
    await ST.Mode.set()


@dp.callback_query_handler(lambda c: c.data == "back", state="*")
async def handle_back(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current_state = await state.get_state()
    data = await state.get_data()
    lang = "en"

    if current_state == "ForecastStates:Category":
        await callback.message.edit_text("Choose analysis mode:", reply_markup=get_mode_keyboard())
        await ST.Mode.set()

    elif current_state == "ForecastStates:Pair":
        await callback.message.edit_text("Choose asset category:", reply_markup=get_category_keyboard())
        await ST.Category.set()

    elif current_state == "ForecastStates:Timeframe":
        cat = data.get("category", "fin")
        pairs = await get_available_pairs(cat)
        await callback.message.edit_text("Choose pair:", reply_markup=get_pairs_keyboard(pairs))
        await ST.Pair.set()

    else:
        await cmd_start_inline(callback.message, state)

    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "restart", state="*")
async def handle_restart(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await state.finish()
    await state.update_data(lang="en")
    await callback.message.edit_text("Choose analysis mode:", reply_markup=get_mode_keyboard())
    await ST.Mode.set()
    await callback.answer()


async def cmd_start_inline(m: types.Message, state: FSMContext, **kwargs):
    """Start command for inline mode"""
    await state.finish()
    await state.update_data(lang="en")
    await m.edit_text("Choose analysis mode:", reply_markup=get_mode_keyboard())
    await ST.Mode.set()


@dp.callback_query_handler(state=ST.Mode)
@track_time("mode_selection")
async def set_mode(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    mode = callback.data  # "ta" or "ind"
    await state.update_data(mode=mode)

    await callback.message.edit_text("Choose asset category:", reply_markup=get_category_keyboard())
    await ST.Category.set()
    await callback.answer()


@dp.callback_query_handler(state=ST.Category)
@track_time("category_selection")
async def set_category(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    if callback.data == "back":
        await handle_back(callback, state)
        return

    cat = callback.data  # "fin" or "otc"
    await state.update_data(category=cat)

    pairs = await get_available_pairs(cat)

    if not pairs:
        await callback.message.edit_text("No pairs available at the moment. Please try later.",
                                         reply_markup=get_restart_keyboard())
        await state.finish()
        await callback.answer()
        return

    await callback.message.edit_text("Choose pair:", reply_markup=get_pairs_keyboard(pairs))
    await ST.Pair.set()
    await callback.answer()


@dp.callback_query_handler(state=ST.Pair)
@track_time("pair_selection")
async def set_pair(callback: types.CallbackQuery, state: FSMContext, **kwargs):
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
    await ST.Timeframe.set()
    await callback.answer()


@dp.callback_query_handler(state=ST.Timeframe)
@track_time("forecast_generation")
async def set_timeframe(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    if callback.data == "back":
        await handle_back(callback, state)
        return

    data = await state.get_data()
    mode = data.get("mode", "ind")
    cat = data.get("category", "fin")
    pair_human = data.get("pair")
    tf = callback.data  # Timeframe like "1m", "5m", etc.

    await callback.answer("⏳ Analyzing...")

    # Send processing message
    processing_msg = await callback.message.edit_text("⏳ Analyzing PocketOption data...")

    pair_info = get_pair_info(pair_human)
    if not pair_info:
        await processing_msg.edit_text(
            f"Error: Invalid pair {pair_human}",
            reply_markup=get_restart_keyboard()
        )
        await state.finish()
        return

    try:
        logger.info(f"Loading OHLC data for {pair_human} ({pair_info}) on {tf}")
        cache_key = f"{pair_info['po']}_{tf}_{cat}"
        df = cache.get(cache_key)

        if df is None:
            CACHE_MISSES.inc()
            df = await load_ohlc(pair_info, timeframe=tf, category=cat)
            if df is not None and len(df) > 0:
                cache.set(cache_key, df)
                logger.info(f"Cached data for {cache_key}")
        else:
            CACHE_HITS.inc()
            logger.info(f"Using cached data for {cache_key}")

        if df is None or len(df) == 0:
            raise Exception("No data received from PocketOption")

        logger.info(f"Got {len(df)} bars for analysis")

        if mode == "ind":
            logger.info("Computing indicators...")
            ind = compute_indicators(df)
            action, notes = signal_from_indicators(df, ind)
            result_message = format_forecast_message(mode, tf, action, ind, notes)
        else:
            logger.info("Computing TA signal...")
            action, notes = simple_ta_signal(df)
            result_message = format_forecast_message(mode, tf, action, {}, notes)

        # Track forecast
        FORECAST_COUNT.labels(pair=pair_human, timeframe=tf, action=action).inc()

        await processing_msg.edit_text(
            result_message,
            parse_mode='Markdown',
            reply_markup=get_restart_keyboard()
        )
        logger.info(f"Sent forecast: {action} for {tf}")

        # Send chart if enabled
        if ENABLE_CHARTS and df is not None and len(df) > 0:
            try:
                from .utils.charts import plot_candles
                import os, tempfile
                with tempfile.TemporaryDirectory() as tmpd:
                    p = os.path.join(tmpd, "chart.png")
                    out = plot_candles(df, p)
                    if out and os.path.exists(out):
                        await bot.send_photo(callback.message.chat.id, types.InputFile(out))
                        logger.info("Chart sent successfully")
            except Exception as e:
                logger.error(f"Chart error: {e}")

    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        ERROR_COUNT.labels(error_type="analysis_error").inc()
        await processing_msg.edit_text(
            f"❌ Analysis error\n\nReason: {str(e)}\n\nTry another pair or timeframe",
            reply_markup=get_restart_keyboard()
        )

    await state.finish()


async def load_ohlc(pair_info: dict, timeframe: str, category: str):
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PocketOption scraping is required (set PO_ENABLE_SCRAPE=1)")

    if not pair_info or 'po' not in pair_info:
        raise RuntimeError(f"Invalid pair info: {pair_info}")

    otc = (category == "otc")
    logger.info(f"Fetching {pair_info['po']} data, otc={otc}, timeframe={timeframe}")

    try:
        # Используем CompositeFetcher вместо прямого вызова скрапинга
        df = await _fetcher.fetch(pair_info['po'], timeframe=timeframe, otc=otc)
        if df is None or df.empty:
            logger.error("Failed to fetch any OHLC data from PocketOption")
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


# Prometheus metrics endpoint
async def metrics_handler(request):
    metrics = generate_latest()
    return web.Response(body=metrics, content_type="text/plain")


async def start_metrics_server():
    """Start HTTP server for Prometheus metrics"""
    app = web.Application()
    app.router.add_get('/metrics', metrics_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Prometheus metrics available at http://0.0.0.0:8080/metrics")


def main():
    print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10] if TELEGRAM_TOKEN else 'NOT SET'}...")
    print(f"PO_ENABLE_SCRAPE: {PO_ENABLE_SCRAPE}")
    print(f"DEFAULT_LANG: en")
    print(f"LOG_LEVEL: {LOG_LEVEL}")

    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN env var is required")

    logger.info("Starting Telegram bot...")
    logger.info(f"Bot configuration: PO_ENABLE_SCRAPE={PO_ENABLE_SCRAPE}, DEFAULT_LANG=en")

    loop = asyncio.get_event_loop()

    # Start metrics server
    loop.create_task(start_metrics_server())

    # Start availability updater
    loop.create_task(auto_update_availability())

    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


if __name__ == "__main__":
    main()
