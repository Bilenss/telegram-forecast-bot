# app/data_sources/ws_fetcher.py
import asyncio
import logging

import pandas as pd
import socketio

from ..config import PO_WS_URL

logger = logging.getLogger(__name__)

class WebSocketFetcher:
    def __init__(self):
        # включаем логирование socketio, чтобы видеть handshake
        self.sio = socketio.AsyncClient(
            reconnection=True,
            logger=True,
            engineio_logger=True
        )
        self.url = PO_WS_URL
        self._buffers: dict[str, list] = {}
        self._lock = asyncio.Lock()
        self._connected = False
        self._setup_handlers()

    def _setup_handlers(self):
        @self.sio.event
        async def connect():
            logger.info("WS connected to %s", self.url)

        @self.sio.on("candles")
        async def on_candles(msg):
            # msg = [symbol, timeframe, [[ts,o,h,l,c], ...]]
            key = f"{msg[0]}_{msg[1]}"
            self._buffers[key] = msg[2]
            logger.debug("Received %d candles for %s", len(msg[2]), key)

        @self.sio.event
        async def disconnect():
            logger.info("WS disconnected")

    async def connect(self):
        async with self._lock:
            if not self._connected:
                try:
                    await self.sio.connect(self.url, transports=["websocket"])
                    self._connected = True
                except Exception as e:
                    logger.error("WS connect error: %s", e)
                    raise

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
        except:
            return pd.DataFrame()

        # очищаем буфер
        self._buffers.pop(key, None)
        # посылаем команду получение свечей
        try:
            await self.sio.emit("get_candles", [symbol, timeframe, count])
        except Exception as e:
            logger.error("WS emit error: %s", e)
            return pd.DataFrame()

        # ждём ответа
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
