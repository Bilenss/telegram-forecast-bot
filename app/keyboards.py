# app/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def mode_keyboard(lang):
    d = {"ru": ["📊 Технический анализ", "📈 Индикаторы"],
         "en": ["📊 Technical analysis", "📈 Indicators"]}
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for it in d["ru" if lang == "ru" else "en"]:
        kb.add(KeyboardButton(it))
    return kb

def category_keyboard(lang):
    d = {"ru": ["💰 ACTIVE FIN", "⏱️ ACTIVE OTC"],
         "en": ["💰 ACTIVE FIN", "⏱️ ACTIVE OTC"]}
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for it in d["ru" if lang == "ru" else "en"]:
        kb.add(KeyboardButton(it))
    return kb

def pairs_keyboard(pairs):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for name in pairs.keys():
        kb.add(KeyboardButton(name))
    return kb

def timeframe_keyboard(lang, po_available=True):
    """Обновленная клавиатура с новыми таймфреймами"""
    # Новые таймфреймы как требовалось
    timeframes = ["30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h"]
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    
    # Добавляем кнопки по 3 в ряд
    for i in range(0, len(timeframes), 3):
        row_buttons = []
        for j in range(3):
            if i + j < len(timeframes):
                row_buttons.append(KeyboardButton(timeframes[i + j]))
        kb.row(*row_buttons)
    
    return kb
