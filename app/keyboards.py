# app/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

def mode_keyboard(lang="en"):
    """Analysis mode selection keyboard - English only"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("📊 Technical analysis"))
    kb.add(KeyboardButton("📈 Indicators"))
    return kb

def category_keyboard(lang="en"):
    """Asset category keyboard with Back button - English only"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("💰 ACTIVE FIN"))
    kb.add(KeyboardButton("⏱️ ACTIVE OTC"))
    kb.add(KeyboardButton("⬅️ Back"))
    return kb

def pairs_keyboard(pairs, lang="en"):
    """Currency pair keyboard with Back button - English only"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Add pairs
    for name in pairs.keys():
        kb.add(KeyboardButton(name))
    
    # Add Back button
    kb.add(KeyboardButton("⬅️ Back"))
    return kb

def timeframe_keyboard(lang="en", po_available=True):
    """Timeframe keyboard with Back button - English only"""
    timeframes = ["30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h"]
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    
    # Add timeframe buttons in rows of 3
    for i in range(0, len(timeframes), 3):
        row_buttons = []
        for j in range(3):
            if i + j < len(timeframes):
                row_buttons.append(KeyboardButton(timeframes[i + j]))
        kb.row(*row_buttons)
    
    # Add Back button
    kb.add(KeyboardButton("⬅️ Back"))
    return kb

def restart_keyboard(lang="en"):
    """Keyboard with New forecast button after getting forecast - English only"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(KeyboardButton("🔄 New forecast"))
    kb.add(KeyboardButton("/start"))
    return kb

def remove_keyboard():
    """Remove keyboard"""
    return ReplyKeyboardRemove()
