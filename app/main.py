# app/main.py
from __future__ import annotations
import asyncio
import os
import tempfile
import time
from typing import Any, Dict, Optional, Tuple

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from loguru import logger

from .config import (
    TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, PO_STRICT_ONLY,
    ENABLE_CHARTS, LOG_LEVEL,
    METRICS_ENABLED, METRICS_PORT
)
from .keyboards_inline import mode_kb, category_kb, pairs_kb, timeframe_kb
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import get_available_pairs, availability_checker, get_pair_info
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.fetchers import CompositeFetcher

from aioprometheus import Service, Counter, Histogram

# ------------------------------------------------------------------------------
# ЛОГИРОВАНИЕ / БОТ / DISPATCHER / CACHE / FETCHER / STATE
# ------------------------------------------------------------------------------
logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

cache     = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)
_fetcher  = CompositeFetcher()

REQUESTS       = Counter("bot_requests_total", "Total number of bot requests")
FETCH_LATENCY  = Histogram("ohlc_fetch_latency_seconds", "OHLC fetch latency in seconds")


class InMemoryStateStorage:
    """
    Простое хранение состояния выбора пользователя в памяти.
    """
    def __init__(self) -> None:
        self._data: Dict[int, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, user_id: int) -> Dict[str, Any]:
        async with self._lock:
            return dict(self._data.get(user_id, {}))

    async def set(self, user_id: int, value: Dict[str, Any]) -> None:
        async with self._lock:
            self._data[user_id] = dict(value)

    async def update(self, user_id: int, **kwargs) -> None:
        async with self._lock:
            cur = self._data.get(user_id, {})
            cur.update(kwargs)
            self._data[user_id] = cur

    async def clear(self, user_id: int) -> None:
        async with self._lock:
            self._data.pop(user_id, None)


state_storage = InMemoryStateStorage()


# ------------------------------------------------------------------------------
# ФУНКЦИИ ЗАГРУЗКИ И АНАЛИЗА
# ------------------------------------------------------------------------------

async def load_ohlc(pair_info: dict, timeframe: str, category: str):
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PocketOption scraping is required (set PO_ENABLE_SCRAPE=1)")

    otc = (category == "otc")
    logger.info(f"Fetching {pair_info['po']} data, otc={otc}, timeframe={timeframe}")

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


async def run_analysis(df, timeframe: str, mode: str) -> Tuple[str, Optional[str]]:
    """
    Возвращает (markdown_text, action)
    """
    if df is None or len(df) == 0:
        raise RuntimeError("No data to analyze")

    if mode == "ind":
        logger.info("Computing indicators...")
        ind = compute_indicators(df)
        action, notes = signal_from_indicators(df, ind)
        text = format_forecast_message("ind", timeframe, action, ind, notes)
        return text, action
    else:
        logger.info("Computing TA signal...")
        action, notes = simple_ta_signal(df)
        text = format_forecast_message("ta", timeframe, action, {}, notes)
        return text, action


def format_forecast_message(
    mode: str,
    timeframe: str,
    action: str,
    data: dict,
    notes: Optional[list] = None,
    lang: str = "en"
) -> str:
    tf_upper = timeframe.upper()
    if mode == "ind":
        parts = [
            f"🎯 **FORECAST for {tf_upper}**", "",
            f"💡 Recommendation: **{action}**", "",
            "📊 **Indicators:**",
            f"• RSI: {data.get('RSI', 0):.1f}",
            f"• EMA fast: {data.get('EMA_fast', 0):.5f}",
            f"• EMA slow: {data.get('EMA_slow', 0):.5f}",
            f"• MACD: {data.get('MACD', 0):.5f}",
            f"• MACD signal: {data.get('MACD_signal', 0):.5f}",
        ]
    else:
        parts = [
            f"🎯 **FORECAST for {tf_upper}**", "",
            f"💡 Recommendation: **{action}**", "",
            "📊 **Technical Analysis:**",
        ]
        if notes:
            for note in notes:
                parts.append(f"• {note}")
        else:
            parts.append("• Market analysis completed")

    if notes and mode == "ind":
        parts.extend(["", "ℹ️ **Additional Notes:**"])
        for note in notes:
            parts.append(f"• {note}")

    parts.extend(["", "_Analysis based on market data patterns_"])
    return "\n".join(parts)


# ------------------------------------------------------------------------------
# ФОН vs METRICS SERVER
# ------------------------------------------------------------------------------
async def start_metrics_server():
    svc = Service()
    svc.register(REQUESTS)
    svc.register(FETCH_LATENCY)
    await svc.start(addr="0.0.0.0", port=METRICS_PORT)
    logger.info(f"Metrics exposed on :{METRICS_PORT}/metrics")


async def auto_update_availability():
    while True:
        try:
            await availability_checker.update_availability()
            logger.info("Pairs availability updated")
        except Exception as e:
            logger.error(f"Failed to update availability: {e}")
        await asyncio.sleep(300)


# ------------------------------------------------------------------------------
# HANDLERS: /start, callbacks(mode→category→pair→timeframe→analysis, back buttons)
# ------------------------------------------------------------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(m: Message):
    await state_storage.clear(m.from_user.id)
    await state_storage.set(m.from_user.id, {"lang": DEFAULT_LANG})
    await m.answer("Choose mode:", reply_markup=mode_kb())


@dp.callback_query_handler(lambda c: c.data.startswith("mode:"))
async def on_mode(cq: CallbackQuery):
    await cq.answer()
    mode = cq.data.split(":", 1)[1]
    await state_storage.update(cq.from_user.id, mode=mode)
    await cq.message.edit_text("Choose category:", reply_markup=category_kb())


@dp.callback_query_handler(lambda c: c.data.startswith("category:"))
async def on_category(cq: CallbackQuery):
    await cq.answer()
    category = cq.data.split(":", 1)[1]
    user_id = cq.from_user.id
    await state_storage.update(user_id, category=category)

    pairs = await get_available_pairs(category)
    if not pairs:
        await cq.message.edit_text(
            "No pairs available at the moment. Please try again."
        )
        await state_storage.clear(user_id)
        return

    await cq.message.edit_text("Choose pair:", reply_markup=pairs_kb(pairs))


@dp.callback_query_handler(lambda c: c.data.startswith("pair:"))
async def on_pair(cq: CallbackQuery):
    await cq.answer()
    pair_code = cq.data.split(":", 1)[1]  # e.g. 'EURUSD'
    user_id = cq.from_user.id

    is_avail = await availability_checker.is_available(pair_code)
    if not is_avail:
        st = await state_storage.get(user_id)
        pairs = await get_available_pairs(st.get("category", "fin"))
        await cq.message.edit_text(
            "⚠️ This pair became unavailable.\nChoose another pair:",
            reply_markup=pairs_kb(pairs)
        )
        return

    await state_storage.update(user_id, pair=pair_code)
    st = await state_storage.get(user_id)
    await cq.message.edit_text(
        "Choose timeframe:",
        reply_markup=timeframe_kb(st.get("category", "fin"))
    )


@dp.callback_query_handler(lambda c: c.data == "back:category")
async def on_back_category(cq: CallbackQuery):
    await cq.answer()
    await state_storage.update(cq.from_user.id, pair=None, timeframe=None)
    await cq.message.edit_text("Choose category:", reply_markup=category_kb())


@dp.callback_query_handler(lambda c: c.data == "back:pair")
async def on_back_pair(cq: CallbackQuery):
    await cq.answer()
    st = await state_storage.get(cq.from_user.id)
    await state_storage.update(cq.from_user.id, pair=None, timeframe=None)
    pairs = await get_available_pairs(st.get("category", "fin"))
    await cq.message.edit_text("Choose pair:", reply_markup=pairs_kb(pairs))


@dp.callback_query_handler(lambda c: c.data.startswith("timeframe:"))
async def on_timeframe(cq: CallbackQuery):
    await cq.answer()
    timeframe = cq.data.split(":", 1)[1]
    user_id = cq.from_user.id

    st = await state_storage.get(user_id)
    mode     = st.get("mode", "ind")
    category = st.get("category", "fin")
    pair_code= st.get("pair")

    if not pair_code:
        await cq.message.edit_text("Error: pair not selected. Press /start")
        await state_storage.clear(user_id)
        return

    pair_info = get_pair_info(pair_code)
    if not pair_info:
        await cq.message.edit_text(f"Error: Invalid pair {pair_code}. Press /start")
        await state_storage.clear(user_id)
        return

    await state_storage.update(user_id, timeframe=timeframe)
    await cq.message.edit_text("⏳ Analyzing data...")

    cache_key = f"{pair_info['po']}_{timeframe}_{category}"
    df = cache.get(cache_key)

    try:
        if df is None:
            logger.info(f"Loading OHLC for {pair_code} on {timeframe}")
            REQUESTS.inc({"type": "ohlc"})
            start = time.time()

            df = await load_ohlc(pair_info, timeframe, category)
            FETCH_LATENCY.observe({"type": "ohlc"}, time.time() - start)

            if df:
                cache.set(cache_key, df)
                logger.info(f"Cached data for {cache_key}")
        else:
            logger.info(f"Using cached data for {cache_key}")

        if not df or len(df) == 0:
            raise RuntimeError("No data received from PocketOption")

        text, action = await run_analysis(df, timeframe, mode)
        await cq.message.edit_text(text, parse_mode="Markdown")

        if ENABLE_CHARTS:
            from .utils.charts import plot_candles
            with tempfile.TemporaryDirectory() as tmpd:
                path = os.path.join(tmpd, "chart.png")
                out = plot_candles(df, path)
                if out and os.path.exists(out):
                    await bot.send_photo(cq.message.chat.id, InputFile(out))
                    logger.info("Chart sent")
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        await cq.message.edit_text(f"❌ Analysis error:\n{e}\n\nPress /start to retry")

    await state_storage.clear(user_id)


# ------------------------------------------------------------------------------
# RUN BOT
# ------------------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN is required")

    logger.info(f"Starting bot (PO_ENABLE_SCRAPE={PO_ENABLE_SCRAPE})")
    loop = asyncio.get_event_loop()
    loop.create_task(auto_update_availability())

    if METRICS_ENABLED:
        loop.create_task(start_metrics_server())

    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    main()
