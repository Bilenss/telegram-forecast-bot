from aiogram.dispatcher.filters.state import StatesGroup, State

class ForecastStates(StatesGroup):
    Language = State()
    Mode = State()         # indicators | ta
    Category = State()     # fin | otc
    Pair = State()         # EUR/USD ...
    Timeframe = State()    # 15s,30s,1m,5m,15m,1h
