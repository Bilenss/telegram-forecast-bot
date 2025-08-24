from cachetools import TTLCache

# Кэш OHLC-серий: ключ = (source, pair, timeframe)
cache = TTLCache(maxsize=256, ttl=60)
