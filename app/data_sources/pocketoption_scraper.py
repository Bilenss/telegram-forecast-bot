from __future__ import annotations
import asyncio
import json
import re
from contextlib import asynccontextmanager
from typing import Optional

import pandas as pd
from playwright.async_api import async_playwright
from ..utils.user_agents import random_ua
from ..config import settings

# ВНИМАНИЕ: Структура DOM/скриптов на pocketoption.com может меняться.
# Этот скрапер реализует "best-effort" стратегию:
# 1) Загружает публичную страницу платформы
# 2) Ждет и пытается вытащить данные свечей из встраиваемых JSON/ресурсов
# 3) Если не удалось — возвращает None, и бот переключится на фолбэк (Yahoo Finance)

@asynccontextmanager
async def _browser():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random_ua(),
            proxy={"server": settings.https_proxy or settings.http_proxy} if (settings.http_proxy or settings.https_proxy) else None,
        )
        page = await context.new_page()
        try:
            yield page
        finally:
            await context.close()
            await browser.close()


async def fetch_po_ohlc(pair_slug: str, interval: str = "1m", lookback: int = 500) -> Optional[pd.DataFrame]:
    if not settings.po_enable_scrape:
        return None

    url = "https://pocketoption.com/ru/"  # публичная страница; при необходимости замените на конкретную страницу графика/символа

    async with _browser() as page:
        await page.route("**/*", lambda route: route.continue_())
        await page.goto(url, wait_until="domcontentloaded")

        # небольшая рандомная задержка
        await page.wait_for_timeout(1500)

        # Попытка извлечь потенциальные встраиваемые состояния/данные из HTML
        html = await page.content()

        # Грубый поиск JSON с candles внутри исходника
        m = re.search(r"\{[^{}]*\"candles\"\s*:\s*\[.*?\]\} ", html, flags=re.DOTALL)
        if m:
            try:
                blob = json.loads(m.group(0))
                candles = blob.get("candles")
                if candles:
                    df = pd.DataFrame(candles)[-lookback:]
                    # ожидаем ключи: time, open, high, low, close, volume
                    cols = {c: c for c in ["open","high","low","close","volume"] if c in df.columns}
                    if "time" in df.columns:
                        df = df.rename(columns=cols).set_index(pd.to_datetime(df["time"], unit="s"))
                        df.index.name = "time"
                        return df[["open","high","low","close","volume"]]
            except Exception:
                pass

        # Если ничего не нашли — возвращаем None (переключение на фолбэк)
        return None
