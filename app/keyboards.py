# app/keyboards.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

def mode_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Keyboard for selecting analysis mode"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📈 Technical Analysis"),
        KeyboardButton("📊 Indicators")
    )
    return kb

def category_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Keyboard for selecting asset category"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("✅ ACTIVE FIN"),
        KeyboardButton("🛠 OTC")
    )
    kb.add(KeyboardButton("⬅️ Back"))
    return kb

def pairs_keyboard(pairs: dict, lang: str = "en") -> ReplyKeyboardMarkup:
    """
    Show all currency pairs in a 3-column keyboard grid.
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    buttons = [KeyboardButton(name) for name in pairs.keys()]
    kb.add(*buttons)
    kb.add(KeyboardButton("⬅️ Back"))
    return kb

def timeframe_keyboard(lang: str, category: str, po_available: bool = True) -> ReplyKeyboardMarkup:
    """
    Возвращает ReplyKeyboard с таймфреймами.
    Для категории 'fin' убираем 30s, добавляем 4h.
    """
    all_tfs = ["30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h"]
    
    if category.lower() == "fin":
        all_tfs = [tf for tf in all_tfs if tf != "30s"]

    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.add(*[KeyboardButton(tf) for tf in all_tfs])
    kb.add(KeyboardButton("⬅️ Back"))
    return kb

def restart_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Keyboard shown after forecast with options to restart"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(KeyboardButton("🔄 New forecast"))
    kb.add(KeyboardButton("/start"))
    return kb

def remove_keyboard() -> ReplyKeyboardRemove:
    """Removes the keyboard from chat"""
    return ReplyKeyboardRemove()
