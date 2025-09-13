# app/keyboards_inline.py
# -*- coding: utf-8 -*-

from typing import Iterable, Sequence
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_mode_keyboard() -> InlineKeyboardMarkup:
    """
    Two buttons: Indicators (ind) and Technical analysis (ta)
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Indicators", callback_data="ind")
    kb.button(text="Technical", callback_data="ta")
    kb.adjust(2)
    return kb.as_markup()


def get_category_keyboard() -> InlineKeyboardMarkup:
    """
    Two main categories + Back/Restart row
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Financial", callback_data="fin")
    kb.button(text="OTC", callback_data="otc")
    kb.adjust(2)
    # Control row
    kb.button(text="⬅️ Back", callback_data="back")
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.adjust(2)
    return kb.as_markup()


def get_pairs_keyboard(pairs: Sequence[str]) -> InlineKeyboardMarkup:
    """
    Pairs list as buttons, 2 columns. Then Back/Restart.
    `pairs` should be a sequence of human-readable pair names (strings).
    """
    kb = InlineKeyboardBuilder()

    for p in pairs:
        # callback_data — это сам текст пары (как и ожидалось в set_pair)
        kb.button(text=p, callback_data=p)

    # Разместим по 2 в строке
    if len(pairs) > 1:
        kb.adjust(2)
    else:
        kb.adjust(1)

    # Управляющие кнопки
    kb.button(text="⬅️ Back", callback_data="back")
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.adjust(2)

    return kb.as_markup()


def get_timeframe_keyboard() -> InlineKeyboardMarkup:
    """
    Timeframes grid + Back/Restart row.
    Отредактируй набор под свои нужды.
    """
    tfs: Iterable[str] = ("1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h")
    kb = InlineKeyboardBuilder()

    for tf in tfs:
        kb.button(text=tf, callback_data=tf)

    # по 4 кнопки в строке
    kb.adjust(4)

    # Управляющие кнопки
    kb.button(text="⬅️ Back", callback_data="back")
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.adjust(2)

    return kb.as_markup()


def get_restart_keyboard() -> InlineKeyboardMarkup:
    """
    Minimal control keyboard with Restart (+ optionally Back).
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.button(text="⬅️ Back", callback_data="back")
    kb.adjust(2)
    return kb.as_markup()
