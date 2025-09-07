# app/states.py
from aiogram.dispatcher.filters.state import StatesGroup, State

class ForecastStates(StatesGroup):
    # Убрали Language state - язык устанавливается автоматически
    Mode = State()         # indicators | ta
    Category = State()     # fin | otc
    Pair = State()         # EUR/USD ...
    Timeframe = State()    # 30s,1m,2m,3m,5m,10m,15m,30m,1h
