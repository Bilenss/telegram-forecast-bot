from __future__ import annotations
import pandas as pd

def signal_from_indicators(df: pd.DataFrame, ind: dict) -> tuple[str, list[str]]:
    notes = []
    score = 0

    rsi = ind["RSI"]
    if rsi < 30:
        score += 1; notes.append(f"RSI={rsi} (перепроданность)")
    elif rsi > 70:
        score -= 1; notes.append(f"RSI={rsi} (перекупленность)")

    if ind["EMA_cross_up"]:
        score += 1; notes.append("EMA: быст. пересёк медл. СНИЗУ ВВЕРХ")
    if ind["EMA_cross_down"]:
        score -= 1; notes.append("EMA: быст. пересёк медл. СВЕРХУ ВНИЗ")

    if ind["MACD_hist"] > 0:
        score += 1; notes.append("MACD гистограмма > 0")
    elif ind["MACD_hist"] < 0:
        score -= 1; notes.append("MACD гистограмма < 0")

    action = "HOLD"
    if score >= 2: action = "BUY"
    if score <= -2: action = "SELL"
    return action, notes

def simple_ta_signal(df: pd.DataFrame) -> tuple[str, list[str]]:
    # Бычье/медвежье поглощение + пивот
    notes = []
    o, h, l, c = [df[x].iloc[-2:] for x in ["Open", "High", "Low", "Close"]]

    bullish_engulfing = (c.iloc[0] < o.iloc[0]) and (c.iloc[1] > o.iloc[1]) and (o.iloc[1] < c.iloc[0]) and (c.iloc[1] > o.iloc[0])
    bearish_engulfing = (c.iloc[0] > o.iloc[0]) and (c.iloc[1] < o.iloc[1]) and (o.iloc[1] > c.iloc[0]) and (c.iloc[1] < o.iloc[0])

    action = "HOLD"
    if bullish_engulfing:
        action = "BUY"; notes.append("Бычье поглощение")
    elif bearish_engulfing:
        action = "SELL"; notes.append("Медвежье поглощение")

    last_close = float(df['Close'].iloc[-1])
    pivot = (float(h.iloc[0]) + float(l.iloc[0]) + float(c.iloc[0])) / 3
    if last_close > pivot: notes.append("Выше пивота")
    else: notes.append("Ниже пивота")
    return action, notes
