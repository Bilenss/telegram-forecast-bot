# app/utils/dataframe_fix.py
"""Утилита для исправления названий колонок в DataFrame"""

import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def fix_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Исправляет названия колонок OHLC данных
    Приводит к стандартному формату: Open, High, Low, Close
    """
    if df is None or df.empty:
        return df
    
    # Словарь возможных вариантов названий
    column_mapping = {
        # Для Open
        'open': 'Open', 'o': 'Open', 'OPEN': 'Open', 'Open': 'Open',
        # Для High  
        'high': 'High', 'h': 'High', 'HIGH': 'High', 'High': 'High',
        # Для Low
        'low': 'Low', 'l': 'Low', 'LOW': 'Low', 'Low': 'Low',
        # Для Close
        'close': 'Close', 'c': 'Close', 'CLOSE': 'Close', 'Close': 'Close',
        # Для Volume (если есть)
        'volume': 'Volume', 'v': 'Volume', 'VOLUME': 'Volume', 'Volume': 'Volume'
    }
    
    # Создаем новый словарь для переименования
    rename_dict = {}
    
    for col in df.columns:
        if col in column_mapping:
            rename_dict[col] = column_mapping[col]
    
    # Переименовываем колонки если нужно
    if rename_dict:
        df = df.rename(columns=rename_dict)
        logger.debug(f"Renamed columns: {rename_dict}")
    
    # Проверяем наличие обязательных колонок
    required_columns = ['Open', 'High', 'Low', 'Close']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        logger.warning(f"Missing required columns: {missing_columns}")
        logger.warning(f"Available columns: {df.columns.tolist()}")
    
    return df

def validate_ohlc_data(df: pd.DataFrame) -> bool:
    """
    Проверяет корректность OHLC данных
    """
    if df is None or df.empty:
        return False
    
    required_columns = ['Open', 'High', 'Low', 'Close']
    
    # Проверяем наличие колонок
    if not all(col in df.columns for col in required_columns):
        return False
    
    # Проверяем логическую корректность данных
    try:
        # High должен быть >= max(Open, Close)
        # Low должен быть <= min(Open, Close)
        invalid_rows = (
            (df['High'] < df['Open']) | 
            (df['High'] < df['Close']) |
            (df['Low'] > df['Open']) |
            (df['Low'] > df['Close'])
        )
        
        if invalid_rows.any():
            logger.warning(f"Found {invalid_rows.sum()} invalid OHLC rows")
            # Исправляем некорректные данные
            df.loc[invalid_rows, 'High'] = df.loc[invalid_rows, ['Open', 'Close']].max(axis=1)
            df.loc[invalid_rows, 'Low'] = df.loc[invalid_rows, ['Open', 'Close']].min(axis=1)
            
    except Exception as e:
        logger.error(f"Error validating OHLC data: {e}")
        return False
    
    return True
