import pandas as pd

def _trend(a: pd.Series) -> float:
    if a is None or len(a) < 3:
        return 0.0
    n = min(5, len(a) // 2)
    return float(a.tail(n).mean() - a.tail(2 * n).head(n).mean())

def decide_indicators(df: pd.DataFrame) -> tuple[str, str]:
    if df is None or df.empty:
        return "NEUTRAL", "Нет данных для анализа"
    last = df.iloc[-1]
    expl = []
    score = 0
    if last.get("rsi") is not None:
        if last.rsi < 30:
            score += 1; expl.append(f"RSI={last.rsi:.1f} (перепроданность)")
        elif last.rsi > 70:
            score -= 1; expl.append(f"RSI={last.rsi:.1f} (перекупленность)")
    if last.get("macd_hist") is not None:
        t = _trend(df["macd_hist"])
        if t > 0: score += 0.5; expl.append("MACD гист. растет")
        elif t < 0: score -= 0.5; expl.append("MACD гист. падает")
    if last.get("ema50") is not None:
        if last.close > last.ema50:
            score += 0.5; expl.append("Цена выше EMA50")
        else:
            score -= 0.5; expl.append("Цена ниже EMA50")
    if {"bb_low", "bb_high"}.issubset(df.columns):
        if last.close <= last.bb_low:
            score += 0.25; expl.append("Касание нижней Bollinger")
        elif last.close >= last.bb_high:
            score -= 0.25; expl.append("Касание верхней Bollinger")
    if score > 0.5:
        return "BUY", "; ".join(expl)
    if score < -0.5:
        return "SELL", "; ".join(expl)
    return "NEUTRAL", "; ".join(expl) or "Сигналов недостаточно"

def decide_technicals(df: pd.DataFrame) -> tuple[str, str]:
    if df is None or df.empty:
        return "NEUTRAL", "Нет данных для анализа"
    last = df.iloc[-1]
    expl = []
    score = 0
    prev = df.iloc[-2]
    if last.ema20 > last.ema50 and prev.ema20 <= prev.ema50:
        score += 1; expl.append("Бычий кросс EMA20/50")
    if last.ema20 < last.ema50 and prev.ema20 >= prev.ema50:
        score -= 1; expl.append("Медвежий кросс EMA20/50")
    last_body = abs(last.close - last.open)
    prev_body = abs(prev.close - prev.open)
    if last.close > last.open and prev.close < prev.open and last_body > prev_body:
        score += 0.5; expl.append("Бычье поглощение")
    if last.close < last.open and prev.close > prev.open and last_body > prev_body:
        score -= 0.5; expl.append("Медвежье поглощение")
    window = df.tail(50)
    if last.close <= window.low.min() * 1.003:
        score += 0.25; expl.append("У локальной поддержки")
    if last.close >= window.high.max() * 0.997:
        score -= 0.25; expl.append("У локального сопротивления")
    if score > 0.5:
        return "BUY", "; ".join(expl)
    if score < -0.5:
        return "SELL", "; ".join(expl)
    return "NEUTRAL", "; ".join(expl) or "Сигналов недостаточно"
