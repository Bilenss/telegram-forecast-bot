# app/keyboards_inline.py
# -*- coding: utf-8 -*-

from typing import Sequence, Iterable
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

def get_mode_keyboard() -> InlineKeyboardMarkup:
    """
    Single button: Analysis
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Analysis", callback_data="analysis")
    kb.adjust(1)
    return kb.as_markup()

def get_category_keyboard() -> InlineKeyboardMarkup:
    """
    Two categories + Back/Restart
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Financial", callback_data="fin")
    kb.button(text="OTC", callback_data="otc")
    kb.adjust(2)
    kb.button(text="⬅️ Back", callback_data="back")
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.adjust(2)
    return kb.as_markup()

def get_pairs_keyboard(pairs: Sequence[str]) -> InlineKeyboardMarkup:
    """
    List of pairs + Back/Restart
    """
    kb = InlineKeyboardBuilder()
    for p in pairs:
        kb.button(text=p, callback_data=p)
    kb.adjust(2 if len(pairs) > 1 else 1)
    kb.button(text="⬅️ Back", callback_data="back")
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.adjust(2)
    return kb.as_markup()

def get_timeframe_keyboard() -> InlineKeyboardMarkup:
    """
    Timeframes grid + Back/Restart
    """
    tfs: Iterable[str] = ("1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h")
    kb = InlineKeyboardBuilder()
    for tf in tfs:
        kb.button(text=tf, callback_data=tf)
    kb.adjust(4)
    kb.button(text="⬅️ Back", callback_data="back")
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.adjust(2)
    return kb.as_markup()

def get_restart_keyboard() -> InlineKeyboardMarkup:
    """
    Restart + Back
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Restart", callback_data="restart")
    kb.button(text="⬅️ Back", callback_data="back")
    kb.adjust(2)
    return kb.as_markup()
