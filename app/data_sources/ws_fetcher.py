import asyncio
import logging

import httpx
import pandas as pd
import socketio

from ..config import PO_WS_URL, PO_ENTRY_URL

logger = logging.getLogger(__name__)

class WebSocketFetcher:
    def __init__(self):
        self.sio = socketio.AsyncClient(
            reconnection=True,
            logger=False,
            engineio_logger=False,
        )
        self.url = PO_WS_URL
        self._lock = asyncio.Lock()
        self._connected = False
        self._buffers: dict[str, list] = {}
        self._setup_handlers()

    def _setup_handlers(self):
        @self.sio.event
        async def connect():
            logger.info("WS connected, session established")

        @self.sio.on("candles")
        async def on_candles(msg):
            # msg = [symbol, timeframe, [[ts,o,h,l,c], …]]
            key = f"{msg[0]}_{msg[1]}"
            self._buffers[key] = msg[2]
            logger.debug("Buffered %d candles for %s", len(msg[2]), key)

        @self.sio.event
        async def disconnect():
            logger.info("WS disconnected by server")

    async def connect(self):
        async with self._lock:
            if self._connected:
                return
            # 1) Примим куки демо-страницы через HTTP
            headers = {"User-Agent": "Mozilla/5.0"}
            cookie_str = ""
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(PO_ENTRY_URL, headers=headers)
                # собираем все куки в одну строку
                cookie_str = "; ".join(f"{k}={v}" for k, v in resp.cookies.items())

            # 2) Передаём полученные куки в WS-handshake
            ws_headers = {
                "User-Agent": "Mozilla/5.0",
                "Cookie": cookie_str
            }
            await self.sio.connect(
                self.url,
                transports=["websocket"],
                headers=ws_headers
            )
            self._connected = True

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        otc: bool = False,
        count: int = 100
    ) -> pd.DataFrame:
        key = f"{symbol}_{timeframe}"
        try:
            await self.connect()
        except Exception as e:
            logger.error("WS connect failed: %s", e)
            return pd.DataFrame()

        self._buffers.pop(key, None)

        try:
            await self.sio.emit("get_candles", [symbol, timeframe, count])
        except Exception as e:
            logger.error("WS emit failed: %s", e)
            return pd.DataFrame()

        # ждём до 5 секунд, пока не придут свечи
        for _ in range(50):
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
