from __future__ import annotations
import pandas as pd
import pandas_ta as ta

def compute_indicators(df: pd.DataFrame):
    out = {}
    close = df['Close']
    # RSI
    rsi = ta.rsi(close, length=14)
    out["RSI"] = round(float(rsi.iloc[-1]), 2)

    # EMA cross
    ema_fast = ta.ema(close, length=9)
    ema_slow = ta.ema(close, length=21)
    cross_up = ema_fast.iloc[-2] < ema_slow.iloc[-2] and ema_fast.iloc[-1] > ema_slow.iloc[-1]
    cross_down = ema_fast.iloc[-2] > ema_slow.iloc[-2] and ema_fast.iloc[-1] < ema_slow.iloc[-1]
    out["EMA_fast"] = round(float(ema_fast.iloc[-1]), 6)
    out["EMA_slow"] = round(float(ema_slow.iloc[-1]), 6)
    out["EMA_cross_up"] = bool(cross_up)
    out["EMA_cross_down"] = bool(cross_down)

    # MACD
    macd = ta.macd(close)
    out["MACD"] = round(float(macd['MACD_12_26_9'].iloc[-1]), 6)
    out["MACD_signal"] = round(float(macd['MACDs_12_26_9'].iloc[-1]), 6)
    out["MACD_hist"] = round(float(macd['MACDh_12_26_9'].iloc[-1]), 6)

    # Bollinger
    bb = ta.bbands(close, length=20, std=2)
    out["BB_upper"] = round(float(bb['BBU_20_2.0'].iloc[-1]), 6)
    out["BB_middle"] = round(float(bb['BBM_20_2.0'].iloc[-1]), 6)
    out["BB_lower"] = round(float(bb['BBL_20_2.0'].iloc[-1]), 6)

    return out
