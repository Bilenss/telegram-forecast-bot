import os
import mplfinance as mpf
import pandas as pd
from .logging import setup

logger = setup()

def plot_candles(df: pd.DataFrame, out_path: str):
    try:
        mpf.plot(
            df.tail(200),
            type='candle',
            style='classic',
            volume=False,
            savefig=dict(fname=out_path, dpi=150, bbox_inches='tight'),
        )
        return out_path
    except Exception as e:
        logger.error(f"Chart error: {e}")
        return ""
