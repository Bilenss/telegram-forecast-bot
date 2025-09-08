# app/analysis/decision.py
from __future__ import annotations
import pandas as pd

def signal_from_indicators(df: pd.DataFrame, ind: dict) -> tuple[str, list[str]]:
    """Улучшенный алгоритм с более чувствительными сигналами"""
    notes = []
    score = 0

    rsi = ind["RSI"]
    
    # RSI сигналы (более чувствительные)
    if rsi < 35:  # было 30
        score += 2; notes.append(f"RSI={rsi:.1f} (сильная перепроданность)")
    elif rsi < 45:  # новый уровень
        score += 1; notes.append(f"RSI={rsi:.1f} (умеренная перепроданность)")
    elif rsi > 65:  # было 70
        score -= 2; notes.append(f"RSI={rsi:.1f} (сильная перекупленность)")
    elif rsi > 55:  # новый уровень
        score -= 1; notes.append(f"RSI={rsi:.1f} (умеренная перекупленность)")

    # EMA пересечения (больший вес)
    if ind["EMA_cross_up"]:
        score += 2; notes.append("EMA: бычий сигнал (быстрая выше медленной)")
    if ind["EMA_cross_down"]:
        score -= 2; notes.append("EMA: медвежий сигнал (быстрая ниже медленной)")

    # Текущее положение EMA
    if ind["EMA_fast"] > ind["EMA_slow"]:
        score += 1; notes.append("EMA: восходящий тренд")
    else:
        score -= 1; notes.append("EMA: нисходящий тренд")

    # MACD сигналы (более чувствительные)
    macd_hist = ind["MACD_hist"]
    if macd_hist > 0.0001:  # положительная гистограмма
        score += 1; notes.append("MACD: бычий импульс")
    elif macd_hist < -0.0001:  # отрицательная гистограмма
        score -= 1; notes.append("MACD: медвежий импульс")

    # MACD линия vs сигнальная
    if ind["MACD"] > ind["MACD_signal"]:
        score += 1; notes.append("MACD выше сигнальной линии")
    else:
        score -= 1; notes.append("MACD ниже сигнальной линии")

    # Решение (понижен порог)
    action = "HOLD"
    if score >= 3:  # было 2
        action = "BUY"
    elif score <= -3:  # было -2
        action = "SELL"
    elif score >= 1:  # новый уровень
        action = "WEAK BUY"
    elif score <= -1:  # новый уровень
        action = "WEAK SELL"

    # Добавляем общий счет в заметки
    notes.append(f"Общий счет: {score}")
    
    return action, notes

def simple_ta_signal(df: pd.DataFrame) -> tuple[str, list[str]]:
    """Улучшенный технический анализ с дополнительными паттернами"""
    notes = []
    score = 0
    
    # Проверяем последние 3 свечи для большей надежности
    if len(df) < 3:
        return "HOLD", ["Недостаточно данных для анализа"]
    
    o, h, l, c = [df[x].iloc[-3:] for x in ["Open", "High", "Low", "Close"]]

    # Паттерны поглощения (последние 2 свечи)
    bullish_engulfing = (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] > o.iloc[-1]) and \
                       (o.iloc[-1] < c.iloc[-2]) and (c.iloc[-1] > o.iloc[-2])
    bearish_engulfing = (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-1] < o.iloc[-1]) and \
                       (o.iloc[-1] > c.iloc[-2]) and (c.iloc[-1] < o.iloc[-2])

    if bullish_engulfing:
        score += 3; notes.append("Бычье поглощение")
    elif bearish_engulfing:
        score -= 3; notes.append("Медвежье поглощение")

    # Молот и доджи
    last_candle = len(df) - 1
    body_size = abs(c.iloc[-1] - o.iloc[-1])
    total_range = h.iloc[-1] - l.iloc[-1]
    
    if total_range > 0:
        body_ratio = body_size / total_range
        
        # Доджи (маленькое тело)
        if body_ratio < 0.1:
            notes.append("Доджи - разворотный сигнал")
            
        # Молот (длинная нижняя тень)
        lower_shadow = min(o.iloc[-1], c.iloc[-1]) - l.iloc[-1]
        upper_shadow = h.iloc[-1] - max(o.iloc[-1], c.iloc[-1])
        
        if lower_shadow > body_size * 2 and upper_shadow < body_size:
            score += 2; notes.append("Молот - бычий сигнал")

    # Тренд последних 3 свечей
    closes = c.values
    if closes[-1] > closes[-2] > closes[-3]:
        score += 2; notes.append("Восходящий тренд (3 свечи)")
    elif closes[-1] < closes[-2] < closes[-3]:
        score -= 2; notes.append("Нисходящий тренд (3 свечи)")

    # Пивот-уровни
    pivot = (float(h.iloc[-2]) + float(l.iloc[-2]) + float(c.iloc[-2])) / 3
    last_close = float(c.iloc[-1])
    
    if last_close > pivot * 1.001:  # 0.1% выше пивота
        score += 1; notes.append("Выше дневного пивота")
    elif last_close < pivot * 0.999:  # 0.1% ниже пивота
        score -= 1; notes.append("Ниже дневного пивота")

    # Волатильность
    recent_volatility = (h.iloc[-3:] - l.iloc[-3:]).mean()
    avg_volatility = (df['High'] - df['Low']).mean()
    
    if recent_volatility > avg_volatility * 1.5:
        notes.append("Высокая волатильность")
    elif recent_volatility < avg_volatility * 0.5:
        notes.append("Низкая волатильность")

    # Финальное решение
    action = "HOLD"
    if score >= 3:
        action = "BUY"
    elif score <= -3:
        action = "SELL"
    elif score >= 1:
        action = "WEAK BUY"
    elif score <= -1:
        action = "WEAK SELL"

    notes.append(f"ТА счет: {score}")
    return action, notes
