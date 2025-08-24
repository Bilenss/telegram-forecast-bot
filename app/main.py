from __future__ import annotations
import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from .states import Dialog
from .keyboards import start_kb, market_kb, pairs_kb
from .pairs import ACTIVE_FIN, ACTIVE_OTC, to_yf_ticker
from .config import settings
from .utils.logging import logger
from .utils.cache import cache
from .utils.charts import save_chart
from .analysis.indicators import enrich_indicators
from .analysis.decision import decide_indicators, decide_technicals
from .data_sources.fallback_quotes import fetch_yf_ohlc
from .data_sources.pocketoption_scraper import fetch_po_ohlc

MODE_TECH = "TECH"
MODE_INDI = "INDI"

MARKET_FIN = "FIN"
MARKET_OTC = "OTC"

async def get_series(pair: str, interval: str = None):
    interval = interval or settings.timeframe

    cache_key = ("series", pair, interval)
    if cache_key in cache:
        return cache[cache_key]

    # 1) Попытка PocketOption (скрапинг)
    pair_slug = pair.replace(" ", "_").lower()
    df = await fetch_po_ohlc(pair_slug, interval=interval, lookback=600)

    # 2) Фолбэк: Yahoo Finance (тот же базовый инструмент)
    if df is None:
        yf_ticker = to_yf_ticker(pair)
        if yf_ticker:
            df = fetch_yf_ohlc(yf_ticker, interval=interval, lookback=600)

    if df is None:
        return None

    cache[cache_key] = df
    return df


async def handle_forecast(message: Message, state: FSMContext, mode: str, market: str, pair: str):
    await message.answer("Получаю данные…", reply_markup=ReplyKeyboardRemove())

    df = await get_series(pair, settings.timeframe)
    if df is None or df.empty:
        await message.answer("Не удалось получить котировки для выбранной пары. Попробуйте другую или позже.")
        return

    # Подготовка индикаторов
    raw = df.copy()
    df = enrich_indicators(raw)

    # Решение
    if mode == MODE_INDI:
        decision, expl = decide_indicators(df)
    else:
        decision, expl = decide_technicals(df)

    # График
    chart_path = save_chart(df.tail(300), out_dir="/tmp/charts", title=f"{pair}_{settings.timeframe}")

    text = (
        f"👉 <b>Прогноз:</b> <code>{decision}</code>\n"
        f"📈 <b>Обоснование:</b> {expl or '—'}\n"
        f"⏱️ Таймфрейм: {settings.timeframe}\n"
        f"🧪 Источник: {'PocketOption (best-effort)' if settings.po_enable_scrape else 'Публичные котировки (fallback)'}"
    )

    if chart_path and os.path.exists(chart_path):
        await message.answer_photo(photo=FSInputFile(chart_path), caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


async def on_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Dialog.choose_mode)
    await message.answer("Выберите тип анализа:", reply_markup=start_kb())

async def on_choose_mode(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if "индик" in text:
        await state.update_data(mode=MODE_INDI)
    else:
        await state.update_data(mode=MODE_TECH)
    await state.set_state(Dialog.choose_market)
    await message.answer("Выберите тип актива:", reply_markup=market_kb())

async def on_choose_market(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if "otc" in text:
        await state.update_data(market=MARKET_OTC)
    else:
        await state.update_data(market=MARKET_FIN)
    data = await state.get_data()
    market = data.get("market", MARKET_FIN)
    await state.set_state(Dialog.choose_pair)
    await message.answer("Выберите пару:", reply_markup=pairs_kb(market))

async def on_choose_pair(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(Dialog.choose_market)
        await message.answer("Выберите тип актива:", reply_markup=market_kb())
        return

    data = await state.get_data()
    mode = data.get("mode", MODE_TECH)
    market = data.get("market", MARKET_FIN)
    pair = message.text.strip()

    # Простая валидация пары
    allowed = (ACTIVE_FIN if market == MARKET_FIN else ACTIVE_OTC)
    if pair not in allowed:
        await message.answer("Пожалуйста, выберите пару с клавиатуры.")
        return

    try:
        await handle_forecast(message, state, mode, market, pair)
    except Exception as e:
        logger.exception("Forecast error")
        await message.answer("Произошла ошибка при анализе. Попробуйте еще раз позже.")

def setup_router(dp: Dispatcher):
    dp.message.register(on_start, CommandStart())
    dp.message.register(on_choose_mode, Dialog.choose_mode)
    dp.message.register(on_choose_market, Dialog.choose_market)
    dp.message.register(on_choose_pair, Dialog.choose_pair)

async def main():
    token = settings.telegram_token
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN is not set")

    bot = Bot(token)
    dp = Dispatcher()
    setup_router(dp)

    logger.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
