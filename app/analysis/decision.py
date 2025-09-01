from __future__ import annotations
import pandas as pd

def signal_from_indicators(df: pd.DataFrame, ind: dict) -> tuple[str, list[str]]:
    notes = []
    score = 0

    rsi = ind["RSI"]
    if rsi < 30:
        score += 1; notes.append(f"RSI={rsi} (oversold)")
    elif rsi > 70:
        score -= 1; notes.append(f"RSI={rsi} (overbought)")

    if ind["EMA_cross_up"]:
        score += 1; notes.append("EMA fast crossed above slow")
    if ind["EMA_cross_down"]:
        score -= 1; notes.append("EMA fast crossed below slow")

    if ind["MACD"] > ind["MACD_signal"]:
        score += 0.5; notes.append("MACD > Signal")
    else:
        score -= 0.5; notes.append("MACD < Signal")

    close = float(df['Close'].iloc[-1])
    if close <= ind["BB_lower"]:
        score += 0.5; notes.append("Price near lower Bollinger")
    elif close >= ind["BB_upper"]:
        score -= 0.5; notes.append("Price near upper Bollinger")

    if score > 0.5: action = "BUY"
    elif score < -0.5: action = "SELL"
    else: action = "HOLD"

    return action, notes

def simple_ta_signal(df: pd.DataFrame) -> tuple[str, list[str]]:
    notes = []
    # Very basic candlestick pattern: bullish/bearish engulfing
    o, h, l, c = [df[x].iloc[-2:] for x in ["Open", "High", "Low", "Close"]]
    bullish_engulfing = (c.iloc[0] < o.iloc[0]) and (c.iloc[1] > o.iloc[1]) and (o.iloc[1] < c.iloc[0]) and (c.iloc[1] > o.iloc[0])
    bearish_engulfing = (c.iloc[0] > o.iloc[0]) and (c.iloc[1] < o.iloc[1]) and (o.iloc[1] > c.iloc[0]) and (c.iloc[1] < o.iloc[0])
    action = "HOLD"
    if bullish_engulfing:
        action = "BUY"; notes.append("Bullish engulfing")
    elif bearish_engulfing:
        action = "SELL"; notes.append("Bearish engulfing")
    # Support/Resistance (rough pivot)
    last_close = float(df['Close'].iloc[-1])
    pivot = (float(h.iloc[0]) + float(l.iloc[0]) + float(c.iloc[0])) / 3
    if last_close > pivot: notes.append("Above pivot")
    else: notes.append("Below pivot")
    return action, notes
