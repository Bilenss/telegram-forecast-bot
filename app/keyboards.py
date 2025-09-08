# app/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def mode_keyboard(lang):
    """Клавиатура выбора режима анализа"""
    d = {"ru": ["📊 Технический анализ", "📈 Индикаторы"],
         "en": ["📊 Technical analysis", "📈 Indicators"]}
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for it in d["ru" if lang == "ru" else "en"]:
        kb.add(KeyboardButton(it))
    return kb

def category_keyboard(lang):
    """Клавиатура выбора категории с кнопкой "Назад" """
    d = {"ru": ["💰 ACTIVE FIN", "⏱️ ACTIVE OTC"],
         "en": ["💰 ACTIVE FIN", "⏱️ ACTIVE OTC"]}
    back_text = "⬅️ Назад" if lang == "ru" else "⬅️ Back"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for it in d["ru" if lang == "ru" else "en"]:
        kb.add(KeyboardButton(it))
    kb.add(KeyboardButton(back_text))
    return kb

def pairs_keyboard(pairs, lang="en"):
    """Клавиатура выбора валютной пары с кнопкой "Назад" """
    back_text = "⬅️ Назад" if lang == "ru" else "⬅️ Back"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for name in pairs.keys():
        kb.add(KeyboardButton(name))
    kb.add(KeyboardButton(back_text))
    return kb

def timeframe_keyboard(lang, po_available=True):
    """Клавиатура выбора таймфрейма с кнопкой "Назад" """
    timeframes = ["30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h"]
    back_text = "⬅️ Назад" if lang == "ru" else "⬅️ Back"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    
    # Добавляем кнопки таймфреймов по 3 в ряд
    for i in range(0, len(timeframes), 3):
        row_buttons = []
        for j in range(3):
            if i + j < len(timeframes):
                row_buttons.append(KeyboardButton(timeframes[i + j]))
        kb.row(*row_buttons)
    
    # Добавляем кнопку "Назад"
    kb.add(KeyboardButton(back_text))
    return kb

def restart_keyboard(lang="en"):
    """Клавиатура с кнопкой "Начать заново" после получения прогноза"""
    restart_text = "🔄 Начать заново" if lang == "ru" else "🔄 Start over"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(KeyboardButton(restart_text))
    return kb
