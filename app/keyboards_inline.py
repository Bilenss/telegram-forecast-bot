# app/keyboards_inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..config import PO_FETCH_ORDER

def mode_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📈 Technical Analysis", callback_data="mode:ta"),
        InlineKeyboardButton("📊 Indicators",         callback_data="mode:ind"),
    )
    return kb

def category_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ ACTIVE FIN", callback_data="category:fin"),
        InlineKeyboardButton("🛠 OTC",         callback_data="category:otc"),
    )
    return kb

def pairs_kb(pairs: dict) -> InlineKeyboardMarkup:
    """
    Разбиваем пары на строки по 3 и даём callback_data 'pair:EURUSD'
    """
    kb = InlineKeyboardMarkup(row_width=3)
    for name in pairs:
        kb.insert(InlineKeyboardButton(name, callback_data=f"pair:{pairs[name]['po']}"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back:pairs"))
    return kb

def timeframe_kb(category: str) -> InlineKeyboardMarkup:
    all_tfs = ["30s","1m","2m","3m","5m","10m","15m","30m","1h","4h"]
    if category == "fin":
        all_tfs = [tf for tf in all_tfs if tf != "30s"]
    kb = InlineKeyboardMarkup(row_width=3)
    for tf in all_tfs:
        kb.insert(InlineKeyboardButton(tf, callback_data=f"timeframe:{tf}"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back:timeframe"))
    return kb
