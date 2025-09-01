import time
from typing import Any, Dict, Tuple

class TTLCache:
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self.store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str):
        now = time.time()
        if key in self.store:
            ts, val = self.store[key]
            if now - ts < self.ttl:
                return val
            else:
                self.store.pop(key, None)
        return None

    def set(self, key: str, value: Any):
        self.store[key] = (time.time(), value)
