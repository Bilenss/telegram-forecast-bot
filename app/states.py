from aiogram.fsm.state import StatesGroup, State

class Dialog(StatesGroup):
    choose_mode = State()       # technical / indicators
    choose_market = State()     # FIN / OTC
    choose_pair = State()       # currency pair
