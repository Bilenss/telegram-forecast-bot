import pandas as pd
import pandas_ta as ta

DEFAULT_RSI = 14

def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df["ema20"] = ta.ema(df["close"], length=20)
    df["ema50"] = ta.ema(df["close"], length=50)
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None:
        df["bb_low"] = bb[bb.columns[0]]
        df["bb_mid"] = bb[bb.columns[1]]
        df["bb_high"] = bb[bb.columns[2]]
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df["macd"] = macd[macd.columns[0]]
        df["macd_signal"] = macd[macd.columns[1]]
        df["macd_hist"] = macd[macd.columns[2]]
    df["rsi"] = ta.rsi(df["close"], length=DEFAULT_RSI)
    return df.dropna()
