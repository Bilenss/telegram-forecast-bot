PAIRS_FIN = {
    "EUR/USD": {"po": "EURUSD"},
    "GBP/USD": {"po": "GBPUSD"},
    "USD/JPY": {"po": "USDJPY"},
    "CAD/JPY": {"po": "CADJPY"},
    "AUD/USD": {"po": "AUDUSD"},
    "USD/CHF": {"po": "USDCHF"},
}

PAIRS_OTC = {
    k + " OTC": {"po": v["po"], "otc": True}
    for k, v in PAIRS_FIN.items()
}

def all_pairs(category: str):
    return PAIRS_FIN if category == "fin" else PAIRS_OTC
