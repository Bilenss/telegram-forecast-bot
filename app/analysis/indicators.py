# app/analysis/indicators.py
from __future__ import annotations
import pandas as pd
import numpy as np

def compute_indicators(df: pd.DataFrame):
    """Вычисление технических индикаторов без pandas-ta"""
    out = {}
    close = df['Close']
    
    # RSI вручную
    def calculate_rsi(prices, window=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    rsi = calculate_rsi(close)
    out["RSI"] = round(float(rsi.iloc[-1]), 2)

    # EMA вручную
    def calculate_ema(prices, span):
        return prices.ewm(span=span, adjust=False).mean()
    
    ema_fast = calculate_ema(close, 9)
    ema_slow = calculate_ema(close, 21)
    
    # EMA cross
    cross_up = ema_fast.iloc[-2] < ema_slow.iloc[-2] and ema_fast.iloc[-1] > ema_slow.iloc[-1]
    cross_down = ema_fast.iloc[-2] > ema_slow.iloc[-2] and ema_fast.iloc[-1] < ema_slow.iloc[-1]
    
    out["EMA_fast"] = round(float(ema_fast.iloc[-1]), 6)
    out["EMA_slow"] = round(float(ema_slow.iloc[-1]), 6)
    out["EMA_cross_up"] = bool(cross_up)
    out["EMA_cross_down"] = bool(cross_down)

    # MACD вручную
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        ema_fast = calculate_ema(prices, fast)
        ema_slow = calculate_ema(prices, slow)
        macd_line = ema_fast - ema_slow
        macd_signal = calculate_ema(macd_line, signal)
        macd_hist = macd_line - macd_signal
        return macd_line, macd_signal, macd_hist
    
    macd_line, macd_signal, macd_hist = calculate_macd(close)
    
    out["MACD"] = round(float(macd_line.iloc[-1]), 6)
    out["MACD_signal"] = round(float(macd_signal.iloc[-1]), 6)
    out["MACD_hist"] = round(float(macd_hist.iloc[-1]), 6)

    # Bollinger Bands вручную
    def calculate_bollinger_bands(prices, window=20, std_dev=2):
        sma = prices.rolling(window=window).mean()
        std = prices.rolling(window=window).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return upper_band, sma, lower_band
    
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close)
    
    out["BB_upper"] = round(float(bb_upper.iloc[-1]), 6)
    out["BB_middle"] = round(float(bb_middle.iloc[-1]), 6)
    out["BB_lower"] = round(float(bb_lower.iloc[-1]), 6)

    return out
