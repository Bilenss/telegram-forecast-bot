# Пары, видимые пользователю
ACTIVE_FIN = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD", "AUD/USD", "NZD/USD",
    "EUR/GBP", "EUR/JPY", "GBP/JPY", "EUR/AUD", "EUR/CAD", "GBP/CAD",
    "AUD/JPY", "CAD/JPY", "CHF/JPY", "AUD/CAD", "AUD/NZD", "NZD/JPY",
    "EUR/NZD", "GBP/NZD",
]

ACTIVE_OTC = [
    "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "USD/CHF OTC", "USD/CAD OTC", "AUD/USD OTC", "NZD/USD OTC",
    "EUR/GBP OTC", "EUR/JPY OTC", "GBP/JPY OTC", "EUR/AUD OTC", "EUR/CAD OTC", "GBP/CAD OTC",
    "AUD/JPY OTC", "CAD/JPY OTC", "CHF/JPY OTC", "AUD/CAD OTC", "AUD/NZD OTC", "NZD/JPY OTC",
    "EUR/NZD OTC", "GBP/NZD OTC",
]

# Маппинг в тикеры Yahoo для фолбэка
YF_TICKERS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
    "USD/CAD": "USDCAD=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/AUD": "EURAUD=X",
    "EUR/CAD": "EURCAD=X",
    "GBP/CAD": "GBPCAD=X",
    "AUD/JPY": "AUDJPY=X",
    "CAD/JPY": "CADJPY=X",
    "CHF/JPY": "CHFJPY=X",
    "AUD/CAD": "AUDCAD=X",
    "AUD/NZD": "AUDNZD=X",
    "NZD/JPY": "NZDJPY=X",
    "EUR/NZD": "EURNZD=X",
    "GBP/NZD": "GBPNZD=X",
}


def to_yf_ticker(pair: str) -> str | None:
    base = pair.replace(" OTC", "")
    return YF_TICKERS.get(base)
