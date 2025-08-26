"""
Alerts Rate Limiter (opt-in)

Purpose
-------
Prevent Discord bursts by limiting posts per key (usually per ticker) within a
time window. The hook in sitecustomize wraps alerts.post_discord_json when
HOOK_ALERTS_RATE_LIMIT=true.

Config (env)
------------
- ALERTS_RATE_WINDOW_SECS (default 60)
- ALERTS_RATE_MAX         (default 4)

Public helpers
--------------
- limiter_key_from_payload(payload: dict) -> str
- limiter_allow(key: str) -> bool

You can also probe the limiter directly via `_RL.allow("KEY")` in ad-hoc tests.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Deque, Dict

try:
    from catalyst_bot.logging_utils import get_logger  # type: ignore
except Exception:  # pragma: no cover
    import logging

    def get_logger(name: str):
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
        )
        return logging.getLogger(name)


log = get_logger("alerts_rate_limit")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


_WINDOW = max(1, _int("ALERTS_RATE_WINDOW_SECS", 60))
_MAX = max(1, _int("ALERTS_RATE_MAX", 4))


class _RateLimiter:
    def __init__(self, window_secs: int, max_hits: int):
        self.window = window_secs
        self.max_hits = max_hits
        self._buckets: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        dq = self._buckets.setdefault(key, deque())
        # purge old
        while dq and (now - dq[0] > self.window):
            dq.popleft()
        if len(dq) >= self.max_hits:
            return False
        dq.append(now)
        return True


_RL = _RateLimiter(_WINDOW, _MAX)


def limiter_key_from_payload(payload: dict) -> str:
    # Prefer ticker; otherwise fold to a hashed-ish stable string via title/url presence
    tkr = str(payload.get("ticker") or "").strip().upper()
    if tkr:
        return f"ticker:{tkr}"
    title = str(payload.get("title") or "").strip()
    if title:
        return f"title:{title[:48]}"
    link = str(payload.get("canonical_link") or payload.get("url") or "").strip()
    if link:
        return f"link:{link[:48]}"
    return "misc:default"


def limiter_allow(key: str) -> bool:
    ok = _RL.allow(key)
    if not ok:
        log.info(
            "rate_limit_triggered", extra={"key": key, "window": _WINDOW, "max": _MAX}
        )
    return ok
