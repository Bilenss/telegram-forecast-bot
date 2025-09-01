from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def lang_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("RU"), KeyboardButton("EN"))
    return kb

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

# 🔁 Обновлённая функция с фильтрацией по доступности PO-скрапинга
def timeframe_keyboard(lang, po_available=True):
    lbl = ["15s", "30s", "1m", "5m", "15m", "1h"] if po_available else ["1m", "5m", "15m", "1h"]
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    for it in lbl:
        kb.add(KeyboardButton(it))
    return kb
