from __future__ import annotations
import asyncio
import os
import requests  # ✅ добавлен импорт для /net
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import CommandStart, Command
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
from .data_sources.fallback_quotes import (
    fetch_yf_ohlc,
    fetch_av_ohlc,
    fetch_yahoo_direct_ohlc,
    get_last_notes  # ✅ добавлено
)
from .data_sources.pocketoption_scraper import fetch_po_ohlc

MODE_TECH = "TECH"
MODE_INDI = "INDI"

MARKET_FIN = "FIN"
MARKET_OTC = "OTC"


async def get_series(pair: str, interval: str = None):
    interval = interval or settings.timeframe
    debug = []

    cache_key = ("series", pair, interval)
    if cache_key in cache:
        debug.append("cache:hit")
        return cache[cache_key], "cache", debug
    else:
        debug.append("cache:miss")

    # 1) PocketOption
    pair_slug = pair.replace(" ", "_").lower()
    df = await fetch_po_ohlc(pair_slug, interval=interval, lookback=600)
    if df is not None and not df.empty:
        debug.append(f"po:rows={len(df)}")
        logger.info(f"SOURCE=PO pair={pair} interval={interval} rows={len(df)}")
        cache[cache_key] = df
        return df, "PocketOption (best-effort)", debug
    else:
        debug.append("po:none")

    # 2) Yahoo Finance (yfinance)
    yf_ticker = to_yf_ticker(pair)
    if yf_ticker:
        df = fetch_yf_ohlc(yf_ticker, interval=interval, lookback=600)
        if df is not None and not df.empty:
            debug.append(f"yf:{yf_ticker}:rows={len(df)}")
            logger.info(f"SOURCE=Yahoo(yfinance) pair={pair} yf={yf_ticker} interval={interval} rows={len(df)}")
            cache[cache_key] = df
            return df, "Yahoo Finance (yfinance)", debug
        else:
            debug.append(f"yf:{yf_ticker}:none")

    # 2b) Прямой Yahoo Chart API
    if yf_ticker:
        df = fetch_yahoo_direct_ohlc(yf_ticker, interval=interval, lookback=600)
        if df is not None and not df.empty:
            debug.append(f"yhd:{yf_ticker}:rows={len(df)}")
            logger.info(f"SOURCE=Yahoo(chart) pair={pair} yf={yf_ticker} interval={interval} rows={len(df)}")
            cache[cache_key] = df
            return df, "Yahoo Finance (direct)", debug
        else:
            debug.append(f"yhd:{yf_ticker}:none")

    # 3) Alpha Vantage
    df = fetch_av_ohlc(pair, interval=interval, lookback=600)
    if df is not None and not df.empty:
        debug.append(f"av:rows={len(df)}")
        logger.info(f"SOURCE=AlphaVantage pair={pair} interval={interval} rows={len(df)}")
        cache[cache_key] = df
        return df, "Alpha Vantage", debug
    else:
        debug.append("av:none")

    logger.warning(f"SOURCE=NONE pair={pair} interval={interval}")
    return None, None, debug


async def handle_forecast(message: Message, state: FSMContext, mode: str, market: str, pair: str):
    await message.answer("Получаю данные…", reply_markup=ReplyKeyboardRemove())

    df, src, debug = await get_series(pair, settings.timeframe)
    if df is None or df.empty:
        dbg = " | ".join(debug[-5:]) if debug else "n/a"
        await message.answer(
            "Не удалось получить котировки для выбранной пары.\n"
            f"Диагностика: {dbg}\n"
            "Попробуйте другую пару или позже."
        )
        return

    raw = df.copy()
    df = enrich_indicators(raw)

    if mode == MODE_INDI:
        decision, expl = decide_indicators(df)
    else:
        decision, expl = decide_technicals(df)

    chart_path = save_chart(df.tail(300), out_dir="/tmp/charts", title=f"{pair}_{settings.timeframe}")

    text = (
        f"👉 <b>Прогноз:</b> <code>{decision}</code>\n"
        f"📈 <b>Обоснование:</b> {expl or '—'}\n"
        f"⏱️ Таймфрейм: {settings.timeframe}\n"
        f"🧪 Источник: {src or ('PocketOption (best-effort)' if settings.po_enable_scrape else 'Публичные котировки (fallback)')}"
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

    allowed = (ACTIVE_FIN if market == MARKET_FIN else ACTIVE_OTC)
    if pair not in allowed:
        await message.answer("Пожалуйста, выберите пару с клавиатуры.")
        return

    try:
        await handle_forecast(message, state, mode, market, pair)
    except Exception:
        logger.exception("Forecast error")
        await message.answer("Произошла ошибка при анализе. Попробуйте еще раз позже.")


async def on_diag(message: Message):
    has_key = bool(os.getenv("ALPHAVANTAGE_KEY"))
    timeframe = settings.timeframe
    pair = "EUR/USD"

    df_po, src_po, _ = await get_series(pair, timeframe)

    from .data_sources.fallback_quotes import fetch_yf_ohlc, fetch_av_ohlc, fetch_yahoo_direct_ohlc
    df_yf = fetch_yf_ohlc("EURUSD=X", interval=timeframe, lookback=100) or None
    df_yhd = fetch_yahoo_direct_ohlc("EURUSD=X", interval=timeframe, lookback=100) or None
    df_av = fetch_av_ohlc("EUR/USD", interval=timeframe, lookback=100) or None
    notes = get_last_notes()

    text = (
        "<b>Диагностика</b>\n"
        f"PAIR_TIMEFRAME: <code>{timeframe}</code>\n"
        f"ALPHAVANTAGE_KEY: <code>{'set' if has_key else 'missing'}</code>\n"
        f"Yahoo EURUSD=X rows: <code>{len(df_yf) if df_yf is not None else 0}</code>\n"
        f"YahooDirect EURUSD=X rows: <code>{len(df_yhd) if df_yhd is not None else 0}</code>\n"
        f"AlphaVantage EUR/USD rows: <code>{len(df_av) if df_av is not None else 0}</code>\n"
        f"Notes: <code>{notes}</code>\n"
        "Примечание: значения >0 означают, что источник отдаёт бары.\n"
    )
    await message.answer(text, parse_mode="HTML")


async def on_net(message: Message):
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=10)
        await message.answer(f"NET OK: <code>{r.text}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"NET ERROR: <code>{type(e).__name__}: {e}</code>", parse_mode="HTML")


def setup_router(dp: Dispatcher):
    dp.message.register(on_start, CommandStart())
    dp.message.register(on_diag, Command("diag"))
    dp.message.register(on_net, Command("net"))  # ✅ добавлено
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
