from __future__ import annotations

import time
from collections import defaultdict, deque, OrderedDict
import threading
from typing import Deque, Dict, Tuple


class RateLimiter:
    def __init__(self, max_keys=10000) -> None:
        self._hits = OrderedDict()
        self._lock = threading.Lock()
        self.max_keys = max_keys

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            if key not in self._hits and len(self._hits) >= self.max_keys:
                # Fail closed while active keys occupy capacity; expired keys can
                # be reclaimed without evicting an attacker's current limit.
                stale = [k for k, (expiry, _) in self._hits.items() if expiry <= now]
                for k in stale:
                    del self._hits[k]
                if len(self._hits) >= self.max_keys:
                    return False
            expiry, bucket = self._hits.get(key, (0, deque()))
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            self._hits[key] = (now + window_seconds, bucket)
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


runtime_limiter = RateLimiter()


def limit_operation(kind, user_id, limit):
    from fastapi import HTTPException
    if not runtime_limiter.allow(f'{kind}:{user_id}', limit, 60):
        raise HTTPException(429, 'Too many requests; retry later', headers={'Retry-After':'60'})


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
