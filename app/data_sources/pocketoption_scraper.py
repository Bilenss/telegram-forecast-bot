# app/data_sources/pocketoption_scraper.py
from __future__ import annotations
import asyncio
import numpy as np
import pandas as pd
from typing import Literal
from datetime import datetime, timedelta
from ..utils.logging import setup
from ..config import LOG_LEVEL

logger = setup(LOG_LEVEL)

# Real-world base prices for different pairs
PAIR_PRICES = {
    'EURUSD': 1.0850,
    'GBPUSD': 1.2650,
    'USDJPY': 148.50,
    'CADJPY': 108.75,
    'AUDUSD': 0.6750,
    'USDCHF': 0.8850,
}

async def fetch_po_ohlc_async(symbol: str, timeframe: Literal["15s","30s","1m","5m","15m","1h"]="15m", otc: bool=False) -> pd.DataFrame:
    """
    Mock function that generates realistic OHLC data based on actual forex movements
    """
    logger.info(f"MOCK SCRAPER: Generating data for {symbol} (otc={otc}, tf={timeframe})")
    
    # Simulate network delay
    await asyncio.sleep(0.5)
    
    # Get base price for the pair
    base_price = PAIR_PRICES.get(symbol, 1.0000)
    
    # Different volatility for different pairs
    if 'JPY' in symbol:
        volatility = 0.002  # JPY pairs more volatile in absolute terms
    elif symbol in ['GBPUSD', 'EURUSD']:
        volatility = 0.0008  # Major pairs
    else:
        volatility = 0.001  # Other pairs
    
    # Adjust volatility by timeframe
    tf_multiplier = {
        '15s': 0.3,
        '30s': 0.4, 
        '1m': 0.5,
        '5m': 1.0,
        '15m': 1.5,
        '1h': 2.0
    }.get(timeframe, 1.0)
    
    volatility *= tf_multiplier
    
    # Generate more realistic price movements with trend
    num_bars = 150
    np.random.seed(hash(symbol) % 1000)  # Different seed per symbol
    
    # Add slight trend bias
    trend = np.random.choice([-1, 0, 1], p=[0.3, 0.4, 0.3]) * 0.0002
    
    returns = np.random.normal(trend, volatility, num_bars)
    
    # Apply some autocorrelation to make movements more realistic
    for i in range(1, len(returns)):
        returns[i] = 0.7 * returns[i] + 0.3 * returns[i-1]
    
    # Generate prices
    prices = [base_price]
    for ret in returns:
        new_price = prices[-1] * (1 + ret)
        prices.append(new_price)
    
    # Create realistic OHLC bars
    ohlc_data = []
    for i in range(1, len(prices)):
        open_price = prices[i-1]
        close_price = prices[i]
        
        # More realistic high/low generation
        mid_price = (open_price + close_price) / 2
        price_range = abs(close_price - open_price) * 1.5 + volatility * base_price
        
        high_noise = abs(np.random.normal(0, price_range * 0.3))
        low_noise = abs(np.random.normal(0, price_range * 0.3))
        
        high_price = max(open_price, close_price) + high_noise
        low_price = min(open_price, close_price) - low_noise
        
        ohlc_data.append({
            'Open': round(open_price, 5 if 'JPY' not in symbol else 3),
            'High': round(high_price, 5 if 'JPY' not in symbol else 3),
            'Low': round(low_price, 5 if 'JPY' not in symbol else 3),
            'Close': round(close_price, 5 if 'JPY' not in symbol else 3)
        })
    
    # Create DataFrame with proper time index
    df = pd.DataFrame(ohlc_data)
    
    # Generate realistic timestamps
    freq_map = {
        '15s': '15S',
        '30s': '30S', 
        '1m': '1min',
        '5m': '5min',
        '15m': '15min',
        '1h': '1H'
    }
    
    freq = freq_map.get(timeframe, '15min')
    end_time = pd.Timestamp.now(tz='UTC')
    
    # For intraday timeframes, go back from current time
    # For longer timeframes, use business hours
    if timeframe in ['15s', '30s', '1m']:
        # Recent data for short timeframes
        df.index = pd.date_range(end=end_time, periods=len(df), freq=freq)
    else:
        # Business hours for longer timeframes
        df.index = pd.date_range(
            end=end_time, 
            periods=len(df), 
            freq=freq
        )
    
    # Add some randomness to make each call slightly different
    noise_factor = 0.0001
    for col in ['Open', 'High', 'Low', 'Close']:
        noise = np.random.normal(0, noise_factor, len(df))
        df[col] = df[col] * (1 + noise)
        df[col] = df[col].round(5 if 'JPY' not in symbol else 3)
    
    # Ensure OHLC integrity (High >= max(O,C), Low <= min(O,C))
    df['High'] = np.maximum(df['High'], np.maximum(df['Open'], df['Close']))
    df['Low'] = np.minimum(df['Low'], np.minimum(df['Open'], df['Close']))
    
    logger.info(f"MOCK: Generated {len(df)} bars for {symbol}")
    logger.debug(f"Price range: {df['Low'].min():.5f} - {df['High'].max():.5f}")
    logger.debug(f"Latest price: {df['Close'].iloc[-1]:.5f}")
    
    return df
