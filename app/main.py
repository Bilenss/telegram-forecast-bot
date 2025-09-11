from __future__ import annotations
import asyncio
import os
import tempfile
from typing import Any, Dict, Optional, Tuple

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.contrib.fsm_storage.memory import MemoryStorage  # не используется для FSM, но dp требует storage

from .config import (
    TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, PO_STRICT_ONLY,
    ENABLE_CHARTS, LOG_LEVEL
)
from .keyboards_inline import mode_kb, category_kb, pairs_kb, timeframe_kb
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import get_available_pairs, availability_checker, get_pair_info
from .analysis.indicators import compute_indicators
from .analysis.decision import signal_from_indicators, simple_ta_signal
from .data_sources.fetchers import CompositeFetcher

# ------------------------------------------------------------------------------
# ЛОГИРОВАНИЕ / ГЛОБАЛЬНЫЕ ОБЪЕКТЫ
# ------------------------------------------------------------------------------
logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
# dp по-прежнему требует storage, но FSM мы не используем — работаем через свой state_storage
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)
_fetcher = CompositeFetcher()


# ------------------------------------------------------------------------------
# ПРОСТОЕ IN-MEMORY ХРАНИЛИЩЕ СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ
# ------------------------------------------------------------------------------
class InMemoryStateStorage:
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
# ФОРМАТИРОВАНИЕ СООБЩЕНИЯ
# ------------------------------------------------------------------------------
def format_forecast_message(mode, timeframe, action, data, notes=None, lang="en"):
    tf_upper = str(timeframe).upper()

    if mode == "ind":
        message_parts = [
            f"🎯 **FORECAST for {tf_upper}**",
            "",
            f"💡 Recommendation: **{action}**",
            "",
            "📊 **Indicators:**",
            f"• RSI: {data.get('RSI', 0):.1f}",
            f"• EMA fast: {data.get('EMA_fast', 0):.5f}",
            f"• EMA slow: {data.get('EMA_slow', 0):.5f}",
            f"• MACD: {data.get('MACD', 0):.5f}",
            f"• MACD signal: {data.get('MACD_signal', 0):.5f}",
        ]
    else:
        message_parts = [
            f"🎯 **FORECAST for {tf_upper}**",
            "",
            f"💡 Recommendation: **{action}**",
            "",
            "📊 **Technical Analysis:**",
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


# ------------------------------------------------------------------------------
# ЗАГРУЗКА ДАННЫХ
# ------------------------------------------------------------------------------
async def load_ohlc(pair_info: dict, timeframe: str, category: str):
    if not PO_ENABLE_SCRAPE:
        raise RuntimeError("PocketOption scraping is required (set PO_ENABLE_SCRAPE=1)")

    if not pair_info or 'po' not in pair_info:
        raise RuntimeError(f"Invalid pair info: {pair_info}")

    otc = (category == "otc")
    logger.info(f"Fetching {pair_info['po']} data, otc={otc}, timeframe={timeframe}")

    try:
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
            # бэкап на случай неготовых утилит
            if 'close' in df.columns:
                df.columns = ['Open', 'High', 'Low', 'Close']

        logger.info(f"DataFrame columns: {df.columns.tolist()}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch OHLC: {e}")
        raise


# ------------------------------------------------------------------------------
# АНАЛИЗ + РЕНДЕР ТЕКСТА
# ------------------------------------------------------------------------------
async def run_analysis(df, timeframe: str, mode: str) -> Tuple[str, Optional[str]]:
    """
    Возвращает (text_markdown, action)
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


# ------------------------------------------------------------------------------
# ФОНОВОЕ ОБНОВЛЕНИЕ ДОСТУПНОСТИ ПАР
# ------------------------------------------------------------------------------
async def auto_update_availability():
    while True:
        try:
            await availability_checker.update_availability()
            logger.info("Pairs availability updated")
        except Exception as e:
            logger.error(f"Failed to update availability: {e}")

        await asyncio.sleep(300)


# ------------------------------------------------------------------------------
# ХЕНДЛЕРЫ: ИНЛАЙН-ФЛОУ
# ------------------------------------------------------------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(m: Message):
    await state_storage.clear(m.from_user.id)
    await state_storage.set(m.from_user.id, {"lang": "en"})
    await m.answer("Choose mode:", reply_markup=mode_kb())


@dp.callback_query_handler(lambda c: c.data.startswith("mode:"))
async def on_mode(cq: CallbackQuery):
    await cq.answer()
    _, mode = cq.data.split(":", 1)  # "ta" или "ind"
    await state_storage.update(cq.from_user.id, mode=mode)
    await cq.message.edit_text("Choose category:", reply_markup=category_kb())


@dp.callback_query_handler(lambda c: c.data.startswith("category:"))
async def on_category(cq: CallbackQuery):
    await cq.answer()
    _, category = cq.data.split(":", 1)  # "fin" | "otc"
    user_id = cq.from_user.id

    await state_storage.update(user_id, category=category)

    # получаем доступные пары динамически
    pairs = await get_available_pairs(category)
    if not pairs:
        await cq.message.edit_text("No pairs available at the moment. Please try later.")
        await state_storage.clear(user_id)
        return

    await cq.message.edit_text("Choose pair:", reply_markup=pairs_kb(pairs))


@dp.callback_query_handler(lambda c: c.data.startswith("pair:"))
async def on_pair(cq: CallbackQuery):
    await cq.answer()
    _, pair_human = cq.data.split(":", 1)  # человекочитаемое название из кнопки
    user_id = cq.from_user.id

    # проверяем доступность в реальном времени
    is_available = await availability_checker.is_available(pair_human)
    if not is_available:
        st = await state_storage.get(user_id)
        category = st.get("category", "fin")
        pairs = await get_available_pairs(category)
        await cq.message.edit_text("⚠️ This pair became unavailable\n\nChoose another pair:",
                                   reply_markup=pairs_kb(pairs))
        return

    await state_storage.update(user_id, pair=pair_human)

    st = await state_storage.get(user_id)
    category = st.get("category", "fin")
    # timeframes зависят от категории: отдаём в конструктор
    await cq.message.edit_text("Choose timeframe:", reply_markup=timeframe_kb(category))


@dp.callback_query_handler(lambda c: c.data.startswith("timeframe:"))
async def on_timeframe(cq: CallbackQuery):
    await cq.answer()
    _, timeframe = cq.data.split(":", 1)
    user_id = cq.from_user.id

    st = await state_storage.get(user_id)
    mode = st.get("mode", "ind")
    category = st.get("category", "fin")
    pair_human = st.get("pair")

    if not pair_human:
        await cq.message.edit_text("Error: pair is not selected. Press /start")
        await state_storage.clear(user_id)
        return

    pair_info = get_pair_info(pair_human)
    if not pair_info:
        await cq.message.edit_text(f"Error: Invalid pair {pair_human}. Press /start")
        await state_storage.clear(user_id)
        return

    await state_storage.update(user_id, timeframe=timeframe)

    # Визуально покажем "обработку"
    try:
        await cq.message.edit_text("⏳ Analyzing data...")
    except Exception:
        # сообщение могло быть уже изменено параллельным апдейтом — игнорируем
        pass

    # --- кэш на фрейм ---
    cache_key = f"{pair_info['po']}_{timeframe}_{category}"
    df = cache.get(cache_key)

    try:
        if df is None:
            logger.info(f"Loading OHLC data for {pair_human} ({pair_info}) on {timeframe}")
            df = await load_ohlc(pair_info, timeframe=timeframe, category=category)
            if df is not None and len(df) > 0:
                cache.set(cache_key, df)
                logger.info(f"Cached data for {cache_key}")
        else:
            logger.info(f"Using cached data for {cache_key}")

        if df is None or len(df) == 0:
            raise RuntimeError("No data received from PocketOption")

        # анализ + ответ
        text, action = await run_analysis(df, timeframe=timeframe, mode=mode)

        await cq.message.edit_text(text, parse_mode="Markdown")

        # график — отдельным сообщением
        if ENABLE_CHARTS and df is not None and len(df) > 0:
            try:
                from .utils.charts import plot_candles
                with tempfile.TemporaryDirectory() as tmpd:
                    p = os.path.join(tmpd, "chart.png")
                    out = plot_candles(df, p)
                    if out and os.path.exists(out):
                        await bot.send_photo(chat_id=cq.message.chat.id, photo=InputFile(out))
                        logger.info("Chart sent successfully")
            except Exception as e:
                logger.error(f"Chart error: {e}")

    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        await cq.message.edit_text(f"❌ Analysis error\n\nReason: {str(e)}\n\nPress /start to try again")

    # очищаем состояние (один прогноз — один сценарий)
    await state_storage.clear(user_id)


# ------------------------------------------------------------------------------
# СТАРТ
# ------------------------------------------------------------------------------
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
    loop.create_task(auto_update_availability())

    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


if __name__ == "__main__":
    main()
