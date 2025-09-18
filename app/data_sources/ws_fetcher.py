import asyncio
import logging
import httpx
import pandas as pd
import socketio
from ..config import PO_WS_URL, PO_ENTRY_URL

logger = logging.getLogger(__name__)

class WebSocketFetcher:
    """
    Fetches real-time market data from PocketOption's WebSocket.
    """
    def __init__(self):
        self.sio = socketio.AsyncClient(reconnection=True, logger=False, engineio_logger=False)
        self.url = PO_WS_URL
        self._buffers = {}
        self._lock = asyncio.Lock()
        self._connected = False
        self._setup_handlers()

    def _setup_handlers(self):
        @self.sio.event
        async def connect():
            logger.info("WS connected")

        @self.sio.on("candles")
        async def on_candles(msg):
            logger.debug("Raw candles event: %s", str(msg)[:500])
            key = f"{msg[0]}_{msg[1]}"
            self._buffers[key] = msg[2]

        @self.sio.event
        async def disconnect():
            logger.info("WS disconnected")

    async def connect(self):
        async with self._lock:
            if self._connected:
                return
            # prime cookies
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(PO_ENTRY_URL, headers=headers)
                cookie_str = "; ".join(f"{k}={v}" for k,v in r.cookies.items())
            try:
                await self.sio.connect(self.url, transports=["websocket"], headers={"Cookie": cookie_str, "User-Agent": "Mozilla/5.0"})
                self._connected = True
            except Exception as e:
                logger.error("WS connect failed: %s", e)
                raise

    async def fetch(self, symbol: str, timeframe: str, otc: bool=False, count: int=100) -> pd.DataFrame:
        key = f"{symbol}_{timeframe}"
        try:
            await self.connect()
        except Exception:
            return pd.DataFrame()
        self._buffers.pop(key, None)
        try:
            await self.sio.emit("get_candles", [symbol, timeframe, count])
        except Exception as e:
            logger.error("WS emit error: %s", e)
            return pd.DataFrame()
        for _ in range(100):  # wait up to 10s
            if key in self._buffers:
                break
            await asyncio.sleep(0.1)
        raw = self._buffers.pop(key, [])
        if not raw:
            logger.warning("No WS candles for %s after wait", key)
            return pd.DataFrame()
        df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    async def close(self):
        if self._connected:
            await self.sio.disconnect()
            self._connected = False
