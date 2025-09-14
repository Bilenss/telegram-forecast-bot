import asyncio
import pandas as pd
import socketio
from ..config import PO_WS_URL

class WebSocketFetcher:
    def __init__(self):
        self.url = PO_WS_URL
        self.sio = socketio.AsyncClient(
            reconnection=True,
            logger=False,
            engineio_logger=False,
        )
        self._buffers: dict[str, list] = {}
        self._connected = False
        self._lock = asyncio.Lock()
        self._setup_handlers()

    def _setup_handlers(self):
        @self.sio.event
        async def connect():
            # автоматически вызывается после подключения
            pass

        @self.sio.on("candles")
        async def on_candles(msg):
            # msg = [symbol, timeframe, [[ts,o,h,l,c], ...]]
            key = f"{msg[0]}_{msg[1]}"
            self._buffers[key] = msg[2]

    async def connect(self):
        async with self._lock:
            if not self._connected:
                await self.sio.connect(self.url, transports=["websocket"])
                self._connected = True

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        otc: bool = False,
        count: int = 100
    ) -> pd.DataFrame:
        """
        Посылаем get_candles и ждём, пока придёт ответ в on_candles.
        """
        await self.connect()
        key = f"{symbol}_{timeframe}"

        # очистим старые данные
        self._buffers.pop(key, None)
        # запрашиваем
        await self.sio.emit("get_candles", [symbol, timeframe, count])

        # ждём до 5 секунд, пока придут данные
        for _ in range(50):
            if key in self._buffers:
                break
            await asyncio.sleep(0.1)

        raw = self._buffers.pop(key, [])
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    async def close(self):
        if self._connected:
            await self.sio.disconnect()
            self._connected = False
