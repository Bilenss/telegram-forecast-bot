# app/analysis/indicators.py
from __future__ import annotations
import pandas as pd
import ta

def compute_indicators(df: pd.DataFrame):
    """Вычисление технических индикаторов с библиотекой ta"""
    out = {}
    close = df['Close']
    high = df['High']
    low = df['Low']
    
    # RSI
    rsi = ta.momentum.RSIIndicator(close=close, window=14)
    out["RSI"] = round(float(rsi.rsi().iloc[-1]), 2)

    # EMA cross
    ema_fast = ta.trend.EMAIndicator(close=close, window=9)
    ema_slow = ta.trend.EMAIndicator(close=close, window=21)
    
    ema_fast_values = ema_fast.ema_indicator()
    ema_slow_values = ema_slow.ema_indicator()
    
    cross_up = ema_fast_values.iloc[-2] < ema_slow_values.iloc[-2] and ema_fast_values.iloc[-1] > ema_slow_values.iloc[-1]
    cross_down = ema_fast_values.iloc[-2] > ema_slow_values.iloc[-2] and ema_fast_values.iloc[-1] < ema_slow_values.iloc[-1]
    
    out["EMA_fast"] = round(float(ema_fast_values.iloc[-1]), 6)
    out["EMA_slow"] = round(float(ema_slow_values.iloc[-1]), 6)
    out["EMA_cross_up"] = bool(cross_up)
    out["EMA_cross_down"] = bool(cross_down)

    # MACD
    macd = ta.trend.MACD(close=close, window_fast=12, window_slow=26, window_sign=9)
    out["MACD"] = round(float(macd.macd().iloc[-1]), 6)
    out["MACD_signal"] = round(float(macd.macd_signal().iloc[-1]), 6)
    out["MACD_hist"] = round(float(macd.macd_diff().iloc[-1]), 6)

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
    out["BB_upper"] = round(float(bb.bollinger_hband().iloc[-1]), 6)
    out["BB_middle"] = round(float(bb.bollinger_mavg().iloc[-1]), 6)
    out["BB_lower"] = round(float(bb.bollinger_lband().iloc[-1]), 6)

    return out
