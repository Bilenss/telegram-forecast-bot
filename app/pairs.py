PAIRS_FIN = {
    "EUR/USD": {"po": "EURUSD", "yf": "EURUSD=X"},
    "GBP/USD": {"po": "GBPUSD", "yf": "GBPUSD=X"},
    "USD/JPY": {"po": "USDJPY", "yf": "JPY=X"},  # yfinance ticker is JPY=X (USD/JPY inverse handled by price scale)
    "CAD/JPY": {"po": "CADJPY", "yf": "CADJPY=X"},
    "AUD/USD": {"po": "AUDUSD", "yf": "AUDUSD=X"},
    "USD/CHF": {"po": "USDCHF", "yf": "CHF=X"},
}

PAIRS_OTC = { k + " OTC": {"po": v["po"], "yf": None, "otc": True} for k,v in PAIRS_FIN.items() }

def all_pairs(category: str):
    return PAIRS_FIN if category == "fin" else PAIRS_OTC
