# app/keyboards_inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_mode_keyboard(lang="en"):
    """Analysis mode selection keyboard - English only"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Technical analysis", callback_data="ta"),
        InlineKeyboardButton("📈 Indicators", callback_data="ind")
    )
    return keyboard


def get_category_keyboard(lang="en"):
    """Asset category keyboard with Back button - English only"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💰 ACTIVE FIN", callback_data="fin"),
        InlineKeyboardButton("⏱️ ACTIVE OTC", callback_data="otc")
    )
    keyboard.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    return keyboard


def get_pairs_keyboard(pairs, lang="en"):
    """Currency pair keyboard with Back button - English only"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Add pairs in rows of 2
    pair_buttons = []
    for name in pairs.keys():
        # Truncate long pair names if needed
        display_name = name[:15] + "..." if len(name) > 15 else name
        pair_buttons.append(InlineKeyboardButton(display_name, callback_data=name))
    
    # Add buttons in pairs
    for i in range(0, len(pair_buttons), 2):
        if i + 1 < len(pair_buttons):
            keyboard.row(pair_buttons[i], pair_buttons[i + 1])
        else:
            keyboard.row(pair_buttons[i])
    
    # Add Back button
    keyboard.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    return keyboard


def get_timeframe_keyboard(lang="en", po_available=True):
    """Timeframe keyboard with Back button - English only"""
    timeframes = [
        ("30s", "30s"), ("1m", "1m"), ("2m", "2m"),
        ("3m", "3m"), ("5m", "5m"), ("10m", "10m"),
        ("15m", "15m"), ("30m", "30m"), ("1h", "1h")
    ]
    
    keyboard = InlineKeyboardMarkup(row_width=3)
    
    # Add timeframe buttons in rows of 3
    for i in range(0, len(timeframes), 3):
        row_buttons = []
        for j in range(3):
            if i + j < len(timeframes):
                display, data = timeframes[i + j]
                row_buttons.append(InlineKeyboardButton(display, callback_data=data))
        keyboard.row(*row_buttons)
    
    # Add Back button
    keyboard.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    return keyboard


def get_restart_keyboard(lang="en"):
    """Keyboard with New forecast button after getting forecast - English only"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔄 New forecast", callback_data="restart"),
        InlineKeyboardButton("📊 Start over", callback_data="restart")
    )
    return keyboard


def get_confirmation_keyboard(lang="en"):
    """Confirmation keyboard for important actions"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Yes", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ No", callback_data="confirm_no")
    )
    return keyboard


def get_settings_keyboard(lang="en"):
    """Settings keyboard for user preferences"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🎨 Theme", callback_data="settings_theme"),
        InlineKeyboardButton("📈 Default TF", callback_data="settings_timeframe")
    )
    keyboard.add(
        InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications"),
        InlineKeyboardButton("💾 Export Data", callback_data="settings_export")
    )
    keyboard.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    return keyboard


def get_help_keyboard(lang="en"):
    """Help keyboard with useful links"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📚 Guide", callback_data="help_guide"),
        InlineKeyboardButton("❓ FAQ", callback_data="help_faq")
    )
    keyboard.add(
        InlineKeyboardButton("💬 Support", url="https://t.me/support"),
        InlineKeyboardButton("📊 Channel", url="https://t.me/trading_channel")
    )
    keyboard.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    return keyboard
