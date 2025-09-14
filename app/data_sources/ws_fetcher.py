# app/data_sources/ws_fetcher.py
import asyncio
import pandas as pd
import socketio

from ..config import PO_WS_URL

class WebSocketFetcher:
    def __init__(self):
        self.url = PO_WS_URL
        self.sio = socketio.AsyncClient(
            ssl_verify=False,
            reconnection=True,
            logger=False,
            engineio_logger=False,
        )
        self._buffers: dict[str, list] = {}
        self._lock = asyncio.Lock()
        self._connected = False

    async def _handler(self):
        @self.sio.on("candles")
        async def on_candles(msg):
            # msg = [ symbol, timeframe, [ [ts, o, h, l, c], … ] ]
            key = f"{msg[0]}_{msg[1]}"
            self._buffers[key] = msg[2]

    async def connect(self):
        async with self._lock:
            if not self._connected:
                await self.sio.connect(self.url, transports=["websocket"])
                await self._handler()
                self._connected = True

    async def fetch(self, symbol: str, timeframe: str, otc: bool=False, count: int=100) -> pd.DataFrame:
        # Подключаемся по факту первого запроса
        await self.connect()

        key = f"{symbol}_{timeframe}"
        # Сбрасываем предыдущие данные
        self._buffers.pop(key, None)

        # Запрос последних count баров
        await self.sio.emit("get_candles", [symbol, timeframe, count])

        # Ждём, пока придут данные
        for _ in range(50):
            if key in self._buffers:
                break
            await asyncio.sleep(0.1)

        candles = self._buffers.pop(key, [])
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles, columns=["timestamp","open","high","low","close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    async def close(self):
        if self._connected:
            await self.sio.disconnect()
            self._connected = False
