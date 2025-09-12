# app/keyboards_inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Iterable, Mapping, List, Union

def mode_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="📈 Technical Analysis", callback_data="mode:ta"),
        InlineKeyboardButton(text="📊 Indicators",         callback_data="mode:ind"),
    )
    return kb

def category_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="✅ ACTIVE FIN", callback_data="category:fin"),
        InlineKeyboardButton(text="🛠 OTC",        callback_data="category:otc"),
    )
    return kb

def pairs_kb(pairs: Union[Iterable[str], Mapping[str, dict]]) -> InlineKeyboardMarkup:
    """
    Рендерит пары по 3 в ряд.
    Принимает:
      - список строк: ["EURUSD","GBPUSD",...]
      - dict: {"EURUSD": {"po": "EURUSD"}, ...} — берём КЛЮЧ как отображаемое имя
    В callback_data передаём человекочитаемое имя: 'pair:EURUSD'
    """
    # нормализуем к списку отображаемых имён
    if isinstance(pairs, dict):
        names: List[str] = list(pairs.keys())
    else:
        names = list(pairs)

    kb = InlineKeyboardMarkup(row_width=3)
    buttons: List[InlineKeyboardButton] = []
    for name in names:
        text = name if len(name) <= 30 else (name[:27] + "…")
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"pair:{name}"))

    # по 3 в ряд
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i:i+3])

    # опциональные кнопки навигации (в main.py нет хендлеров back:*, можно заменить на 'restart' при желании)
    kb.add(InlineKeyboardButton(text="⬅️ Back", callback_data="restart"))
    return kb

def timeframe_kb(category: str) -> InlineKeyboardMarkup:
    """
    Таймфреймы в формате, который любит ваш фетчер: 1m/5m/15m/30m/1h/4h.
    Для fin убираем экзотические секунды.
    """
    # Базовый набор
    all_tfs = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h"]
    # Если нужно, можно отличать fin/otc
    if category == "fin":
        # обычно без слишком коротких "2m/3m", но оставим гибкость
        pass

    kb = InlineKeyboardMarkup(row_width=4)
    buttons = [InlineKeyboardButton(text=tf.upper(), callback_data=f"timeframe:{tf}") for tf in all_tfs]

    # по 4 в ряд
    for i in range(0, len(buttons), 4):
        kb.row(*buttons[i:i+4])

    kb.add(
        InlineKeyboardButton(text="🔄 New",   callback_data="restart"),
        InlineKeyboardButton(text="🏁 Start", callback_data="restart"),
    )
    return kb
