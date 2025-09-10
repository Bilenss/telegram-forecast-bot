# app/analysis/decision.py
"""
Decision making based on indicators and technical analysis
All messages in English
"""
import pandas as pd
from typing import Tuple, List

def signal_from_indicators(df: pd.DataFrame, ind: dict) -> Tuple[str, List[str]]:
    """Generate signal from indicators"""
    action = "HOLD"
    notes = []
    
    # RSI analysis
    rsi = ind.get('RSI', 50)
    if rsi > 70:
        notes.append("RSI overbought")
        action = "SELL"
    elif rsi < 30:
        notes.append("RSI oversold")
        action = "BUY"
    elif rsi > 60:
        notes.append("RSI moderately high")
        if action == "HOLD":
            action = "WEAK SELL"
    elif rsi < 40:
        notes.append("RSI moderately low")
        if action == "HOLD":
            action = "WEAK BUY"
    
    # EMA crossover
    ema_fast = ind.get('EMA_fast', 0)
    ema_slow = ind.get('EMA_slow', 0)
    
    if ema_fast > ema_slow:
        notes.append("Upward EMA trend")
        if action in ["HOLD", "WEAK SELL"]:
            action = "WEAK BUY"
    elif ema_fast < ema_slow:
        notes.append("Downward EMA trend")
        if action in ["HOLD", "WEAK BUY"]:
            action = "WEAK SELL"
    
    # MACD analysis
    macd = ind.get('MACD', 0)
    macd_signal = ind.get('MACD_signal', 0)
    
    if macd > macd_signal:
        notes.append("MACD above signal line")
        if action == "WEAK SELL":
            action = "HOLD"
        elif action in ["HOLD", "WEAK BUY"]:
            action = "BUY"
    elif macd < macd_signal:
        notes.append("MACD below signal line")
        if action == "WEAK BUY":
            action = "HOLD"
        elif action in ["HOLD", "WEAK SELL"]:
            action = "SELL"
    
    # Overall score
    score = 0
    if "oversold" in " ".join(notes).lower():
        score += 2
    if "overbought" in " ".join(notes).lower():
        score -= 2
    if "upward" in " ".join(notes).lower():
        score += 1
    if "downward" in " ".join(notes).lower():
        score -= 1
    
    # Final decision
    if score >= 2:
        action = "STRONG BUY"
    elif score == 1:
        action = "BUY"
    elif score == 0:
        action = "HOLD"
    elif score == -1:
        action = "SELL"
    else:
        action = "STRONG SELL"
    
    return action, notes

def simple_ta_signal(df: pd.DataFrame) -> Tuple[str, List[str]]:
    """
    Simple technical analysis based on price patterns
    Returns improved English messages
    """
    if df is None or len(df) < 20:
        return "HOLD", ["Insufficient data for analysis"]
    
    notes = []
    score = 0
    
    # Get recent prices
    recent = df.tail(10)
    closes = recent['Close'].values
    
    # 1. Trend Analysis (Improved messages)
    if len(closes) >= 3:
        if closes[-1] > closes[-2] > closes[-3]:
            notes.append("Strong uptrend detected (3 consecutive rises)")
            score += 2
        elif closes[-1] < closes[-2] < closes[-3]:
            notes.append("Strong downtrend detected (3 consecutive falls)")
            score -= 2
        elif closes[-1] > closes[-3]:
            notes.append("Overall upward movement")
            score += 1
        elif closes[-1] < closes[-3]:
            notes.append("Overall downward movement")
            score -= 1
        else:
            notes.append("Sideways consolidation")
    
    # 2. Support/Resistance Analysis
    high_20 = df.tail(20)['High'].max()
    low_20 = df.tail(20)['Low'].min()
    current = closes[-1]
    range_size = high_20 - low_20
    
    if range_size > 0:
        position = (current - low_20) / range_size
        
        if position > 0.8:
            notes.append("Price near resistance level")
            score -= 1
        elif position < 0.2:
            notes.append("Price near support level")
            score += 1
        elif 0.4 < position < 0.6:
            notes.append("Price in middle of range")
    
    # 3. Volatility Analysis
    volatility = df.tail(10)['Close'].std()
    avg_price = df.tail(10)['Close'].mean()
    vol_ratio = (volatility / avg_price) * 100 if avg_price > 0 else 0
    
    if vol_ratio > 2:
        notes.append("High volatility detected")
    elif vol_ratio < 0.5:
        notes.append("Low volatility period")
    else:
        notes.append("Normal market volatility")
    
    # 4. Moving Average Analysis
    if len(df) >= 20:
        ma_20 = df.tail(20)['Close'].mean()
        if current > ma_20 * 1.02:
            notes.append("Price significantly above MA20")
            score += 1
        elif current < ma_20 * 0.98:
            notes.append("Price significantly below MA20")
            score -= 1
        else:
            notes.append("Price near MA20")
    
    # 5. Pattern Recognition
    if len(recent) >= 3:
        # Hammer pattern
        last_candle = recent.iloc[-1]
        body = abs(last_candle['Close'] - last_candle['Open'])
        lower_shadow = min(last_candle['Open'], last_candle['Close']) - last_candle['Low']
        
        if lower_shadow > body * 2:
            notes.append("Bullish hammer pattern detected")
            score += 1
        
        # Shooting star
        upper_shadow = last_candle['High'] - max(last_candle['Open'], last_candle['Close'])
        if upper_shadow > body * 2:
            notes.append("Bearish shooting star pattern")
            score -= 1
    
    # Generate final signal based on score
    if score >= 3:
        action = "STRONG BUY"
    elif score == 2:
        action = "BUY"
    elif score == 1:
        action = "WEAK BUY"
    elif score == -1:
        action = "WEAK SELL"
    elif score == -2:
        action = "SELL"
    elif score <= -3:
        action = "STRONG SELL"
    else:
        action = "HOLD"
    
    # Add final summary note
    if not notes:
        notes.append("Market analysis complete")
    
    return action, notes
