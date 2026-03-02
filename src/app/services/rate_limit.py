from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class RateLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        bucket = self._hits[key]
        while bucket and (now - bucket[0]) > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


class LoginLockout:
    def __init__(self) -> None:
        self._failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._locks: Dict[str, float] = {}

    def register_failure(self, email: str, *, max_failures: int, window_seconds: int, lock_seconds: int) -> None:
        now = time.time()
        bucket = self._failures[email]
        while bucket and (now - bucket[0]) > window_seconds:
            bucket.popleft()
        bucket.append(now)
        if len(bucket) >= max_failures:
            self._locks[email] = now + lock_seconds
            bucket.clear()

    def is_locked(self, email: str) -> Tuple[bool, float]:
        now = time.time()
        until = self._locks.get(email, 0.0)
        if until > now:
            return True, until
        if email in self._locks:
            self._locks.pop(email, None)
        return False, 0.0

