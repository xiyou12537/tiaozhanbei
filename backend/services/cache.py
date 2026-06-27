"""
Simple in-memory cache with TTL for storing circuit data and task results.

In a production system this would be Redis or a database.
For local single-user use, a plain dict with expiration is sufficient.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


class SessionCache:
    """Dict-based cache with per-key TTL (seconds)."""

    def __init__(self, default_ttl: int = 3600):
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl or self._default_ttl
        self._store[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear_expired(self) -> int:
        now = time.time()
        expired = [k for k, (t, _) in self._store.items() if now > t]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)


# Global cache instance (module-level singleton — fine for single-user localhost)
cache = SessionCache(default_ttl=3600)  # 1 hour
