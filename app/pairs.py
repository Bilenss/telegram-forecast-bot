# Mapping human-readable names -> canonical symbols & yfinance tickers.
# For PocketOption we keep a 'po' symbol as-is; for fallback we use yfinance.
PAIRS_FIN = {
    "EUR/USD": {"po": "EURUSD", "yf": "EURUSD=X"},
    "GBP/USD": {"po": "GBPUSD", "yf": "GBPUSD=X"},
    "USD/JPY": {"po": "USDJPY", "yf": "JPY=X"},  # yfinance uses JPY=X (USD/JPY inverted handling below)
    "CAD/JPY": {"po": "CADJPY", "yf": "CADJPY=X"},
    "AUD/USD": {"po": "AUDUSD", "yf": "AUDUSD=X"},
    "USD/CHF": {"po": "USDCHF", "yf": "CHF=X"},
}

# OTC pairs map to the same underlying symbol, but with a different flag and no fallback (yf = None).
PAIRS_OTC = {
    k + " OTC": {"po": v["po"], "yf": None, "otc": True}
    for k, v in PAIRS_FIN.items()
}

def all_pairs(category: str):
    return PAIRS_FIN if category == "fin" else PAIRS_OTC
