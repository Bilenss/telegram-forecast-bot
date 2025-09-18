# Your existing configuration
DEFAULT_LANG = "en"
CACHE_TTL_SECONDS = 600
ENABLE_CHARTS = False
PAIR_TIMEFRAME = "15m"

# PocketOption settings
PO_ENABLE_SCRAPE = True
PO_PROXY_FIRST = True
PO_PROXY = 'http://smart-ghk1ife420xz_area-US_state-Newyork:******@us.smartproxy.net:3120'
PO_BROWSER_ORDER = 'chromium'
PO_HTTPX_TIMEOUT = 10.0
# Increased timeout to give the browser more time to load
PO_NAV_TIMEOUT_MS = 30000  
PO_IDLE_TIMEOUT_MS = 3000
PO_WAIT_EXTRA_MS = 0
PO_SCRAPE_DEADLINE = 30
PO_ENTRY_URL = 'https://pocketoption.com/en/cabinet/try-demo/'
PO_FAST_FAIL_SEC = 45
PO_STRICT_ONLY = True
PO_HTTP_API_URL = 'https://try-demo-eu.po.market/api/chart/historic'
PO_WS_URL = 'https://try-demo-eu.po.market/socket.io'
PO_BROWSER_WS_URL = 'wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket'
PO_FETCH_ORDER = ['po', 'interceptor', 'ocr']
PO_USE_INTERCEPTOR = True
PO_USE_OCR = False
PO_USE_WS_FETCHER = True

# Bot settings
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN_HERE" 
LOG_LEVEL = "DEBUG"
