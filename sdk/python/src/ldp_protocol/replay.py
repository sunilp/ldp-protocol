"""Replay detection for LDP messages."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone


class ReplayGuard:
    """Guards against replayed messages using a bounded LRU cache."""

    def __init__(self, capacity: int = 10_000, window_secs: int = 60) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._capacity = capacity
        self._window_secs = window_secs

    def check(
        self, message_id: str, nonce: str | None, timestamp: str
    ) -> str | None:
        """Check if a message should be accepted. Returns error string if rejected, None if OK."""
        # 1. Timestamp freshness
        try:
            msg_time = datetime.fromisoformat(timestamp)
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = abs((now - msg_time).total_seconds())
            if diff > self._window_secs:
                return f"Message timestamp too old: {diff:.0f}s > {self._window_secs}s window"
        except (ValueError, TypeError):
            pass

        # 2. Nonce deduplication (only when nonce is present)
        if nonce is not None:
            key = f"{message_id}:{nonce}"
            while len(self._seen) >= self._capacity:
                self._seen.popitem(last=False)
            if key in self._seen:
                return "Duplicate message_id + nonce pair"
            self._seen[key] = datetime.now(timezone.utc).timestamp()

        return None
