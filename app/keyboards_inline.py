# app/keyboards_inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def mode_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📈 Technical Analysis", callback_data="mode:ta"),
        InlineKeyboardButton("📊 Indicators",        callback_data="mode:ind"),
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
    Рисует кнопки пар в сетке 3 колонки,
    callback_data='pair:<PO_CODE>'
    """
    kb = InlineKeyboardMarkup(row_width=3)
    for display_name, info in pairs.items():
        cb = f"pair:{info['po']}"
        kb.insert(InlineKeyboardButton(display_name, callback_data=cb))

    # «Назад» ведёт к выбору категории
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back:category"))
    return kb

def timeframe_kb(category: str) -> InlineKeyboardMarkup:
    """
    Для FIN: все tf кроме '30s', но с '4h' в конце.
    Для OTC: полный список, включая '30s' и '4h'.
    """
    all_tfs = ["30s","1m","2m","3m","5m","10m","15m","30m","1h","4h"]
    if category == "fin":
        all_tfs.remove("30s")

    kb = InlineKeyboardMarkup(row_width=3)
    for tf in all_tfs:
        kb.insert(InlineKeyboardButton(tf, callback_data=f"timeframe:{tf}"))

    # «Назад» ведёт к выбору пары
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back:pair"))
    return kb
