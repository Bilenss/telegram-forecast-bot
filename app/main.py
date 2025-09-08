from __future__ import annotations
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext

from .config import (
    TELEGRAM_TOKEN, DEFAULT_LANG, CACHE_TTL_SECONDS,
    PO_ENABLE_SCRAPE, PO_STRICT_ONLY,
    ENABLE_CHARTS, LOG_LEVEL
)
from .states import ForecastStates as ST
from .keyboards import (
    mode_keyboard, category_keyboard, pairs_keyboard, 
    timeframe_keyboard, restart_keyboard, remove_keyboard
)
from .utils.cache import TTLCache
from .utils.logging import setup
from .pairs import all_pairs
from .analysis.fast_prediction import fast_predictor
from .data_sources.pocketoption_scraper import fetch_po_ohlc_async

logger = setup(LOG_LEVEL)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)

@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message, state: FSMContext):
    await state.finish()
    await state.update_data(lang=DEFAULT_LANG)
    
    welcome_text = "Hello! Choose analysis mode:" if DEFAULT_LANG == "en" else "Привет! Выберите режим анализа:"
    await m.answer(welcome_text, reply_markup=mode_keyboard(DEFAULT_LANG))
    await ST.Mode.set()

@dp.message_handler(lambda m: "⬅️" in m.text, state="*")
async def handle_back(m: types.Message, state: FSMContext):
    """Обработка кнопки Назад"""
    current_state = await state.get_state()
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    if current_state == "ForecastStates:Category":
        # Возврат к выбору режима
        welcome_text = "Choose analysis mode:" if lang == "en" else "Выберите режим анализа:"
        await m.answer(welcome_text, reply_markup=mode_keyboard(lang))
        await ST.Mode.set()
    
    elif current_state == "ForecastStates:Pair":
        # Возврат к выбору категории
        category_text = "Choose asset category:" if lang == "en" else "Выберите категорию актива:"
        await m.answer(category_text, reply_markup=category_keyboard(lang))
        await ST.Category.set()
    
    elif current_state == "ForecastStates:Timeframe":
        # Возврат к выбору пары
        cat = data.get("category", "fin")
        pairs = all_pairs(cat)
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
        await ST.Pair.set()
    
    else:
        # По умолчанию возврат к старту
        await cmd_start(m, state)

@dp.message_handler(lambda m: "🔄" in m.text, state="*")
async def handle_restart(m: types.Message, state: FSMContext):
    """Обработка кнопки Новый прогноз"""
    await cmd_start(m, state)

@dp.message_handler(state=ST.Mode)
async def set_mode(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    mode = "ta" if "Тех" in m.text or "Technical" in m.text else "ind"
    await state.update_data(mode=mode)
    
    category_text = "Choose asset category:" if lang == "en" else "Выберите категорию актива:"
    await m.answer(category_text, reply_markup=category_keyboard(lang))
    await ST.Category.set()

@dp.message_handler(state=ST.Category)
async def set_category(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    cat = "fin" if "FIN" in m.text else "otc"
    await state.update_data(category=cat)
    
    pairs = all_pairs(cat)
    pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
    await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
    await ST.Pair.set()

@dp.message_handler(state=ST.Pair)
async def set_pair(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    cat = data.get("category", "fin")
    pairs = all_pairs(cat)
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return
    
    if m.text not in pairs:
        pair_text = "Choose pair:" if lang == "en" else "Выберите валютную пару:"
        await m.answer(pair_text, reply_markup=pairs_keyboard(pairs, lang))
        return
        
    await state.update_data(pair=m.text)
    tf_text = "Choose timeframe:" if lang == "en" else "Выберите таймфрейм:"
    await m.answer(tf_text, reply_markup=timeframe_keyboard(lang, po_available=True))
    await ST.Timeframe.set()

@dp.message_handler(state=ST.Timeframe)
async def set_timeframe(m: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    mode = data.get("mode", "ind")
    cat = data.get("category", "fin")
    pair_human = data.get("pair")
    tf = m.text.strip().lower()
    
    # Проверяем, не нажата ли кнопка "Назад"
    if "⬅️" in m.text:
        await handle_back(m, state)
        return

    # ВАЖНО: Убираем клавиатуру сразу после выбора
    processing_text = "⏳ Analyzing PocketOption data..." if lang == "en" else "⏳ Анализирую данные PocketOption..."
    processing_msg = await m.answer(processing_text, reply_markup=remove_keyboard())

    pairs = all_pairs(cat)
    pair_info = pairs.get(pair_human)
    
    if not pair_info:
        await processing_msg.edit_text(f"Error: Invalid pair {pair_human}")
        await m.answer("Press /start to begin again", reply_markup=restart_
