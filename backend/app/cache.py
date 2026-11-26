"""A tiny in-memory cache where every entry expires after a time-to-live."""

import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

MISSING = object()


class TTLCache:
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._data: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any:
        """Return the cached value, or MISSING if absent or expired."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return MISSING
            expires_at, value = entry
            if self._clock() >= expires_at:
                del self._data[key]
                return MISSING
            return value

    def set(self, key: Hashable, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            return
        with self._lock:
            self._data[key] = (self._clock() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
