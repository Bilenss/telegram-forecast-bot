from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from .pairs import ACTIVE_FIN, ACTIVE_OTC

def start_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="📊 Тех. анализ")
    kb.button(text="📈 Индикаторы")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)

def market_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="💰 ACTIVE FIN")
    kb.button(text="⏱️ ACTIVE OTC")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def pairs_kb(market: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    items = ACTIVE_FIN if market == "FIN" else ACTIVE_OTC
    for p in items:
        kb.row(KeyboardButton(text=p))
    kb.row(KeyboardButton(text="⬅️ Назад"))
    return kb.as_markup(resize_keyboard=True)
