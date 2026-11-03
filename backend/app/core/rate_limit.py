"""In-process sliding-window rate limiting (SEC-08).

Limits are per process. When several API processes run behind a reverse proxy, also enforce limits at the
proxy (see docs/security_guide.md). Keys combine the limit name with a client identifier (user id or IP).
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Record a hit. Returns ``None`` if allowed, otherwise the seconds to wait."""
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, math.ceil(events[0] + window_seconds - now))
            events.append(now)
            self._calls += 1
            if self._calls % 1000 == 0:
                self._prune(now)
            return None

    def _prune(self, now: float, max_window: int = 86_400) -> None:
        stale = [k for k, ev in self._events.items() if not ev or ev[-1] < now - max_window]
        for key in stale:
            del self._events[key]

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
