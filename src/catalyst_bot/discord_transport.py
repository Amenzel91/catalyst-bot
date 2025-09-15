from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Tuple

import requests  # runtime dep

# --- Small per-webhook soft rate limiter (header-aware) ---
_RL_LOCK = threading.Lock()
_RL_STATE: Dict[str, Dict[str, float]] = {}


def _min_interval_seconds() -> float:
    try:
        ms = int((os.getenv("ALERTS_MIN_INTERVAL_MS") or "450").strip() or "450")
    except Exception:
        ms = 450
    # keep within sane bounds
    ms = max(0, min(ms, 2000))
    return ms / 1000.0


def _rl_pre_wait(url: str) -> None:
    """Sleep if a previous call asked us to, and always schedule a small spacing."""
    now = time.time()
    wait = 0.0
    with _RL_LOCK:
        st = _RL_STATE.get(url) or {}
        next_ok_at = float(st.get("next_ok_at", 0.0))
        if next_ok_at > now:
            wait = next_ok_at - now
        # always space out successive posts a bit
        st["next_ok_at"] = max(next_ok_at, now) + _min_interval_seconds()
        _RL_STATE[url] = st
    if wait > 0:
        time.sleep(wait)


def _rl_note_headers(url: str, headers: Any, is_429: bool = False) -> None:
    """
    Respect Discord's rate-limit headers.
    - On 429: always pause for Reset-After / Retry-After.
    - On success: optionally pause if Remaining <= 0,
      controlled by ALERTS_RESPECT_RL_ON_SUCCESS (default ON).
    """
    try:
        reset_after = headers.get("X-RateLimit-Reset-After")
        if reset_after is None and is_429:
            reset_after = headers.get("Retry-After")
        if reset_after is None:
            return

        should_pace = bool(is_429)
        if not should_pace:
            # store env var in a local variable to shorten the line
            env_val = os.getenv("ALERTS_RESPECT_RL_ON_SUCCESS", "1").strip().lower()
            if env_val in {"1", "true", "yes", "on"}:
                rem = headers.get("X-RateLimit-Remaining")
                try:
                    if rem is not None and float(rem) <= 0:
                        should_pace = True
                except Exception:
                    # If the header is malformed, ignore
                    pass
        if not should_pace:
            return

        wait_s = float(reset_after)
        # If a proxy sends ms, scale to seconds
        if wait_s > 1000:
            wait_s = wait_s / 1000.0
        with _RL_LOCK:
            st = _RL_STATE.get(url) or {}
            st["next_ok_at"] = max(
                float(st.get("next_ok_at", 0.0)), time.time() + wait_s + 0.05
            )
            _RL_STATE[url] = st
    except Exception:
        return


def post_discord_with_backoff(
    url: str, payload: dict, session=None
) -> Tuple[bool, int | None]:
    """
    Do a header-aware POST with a soft pre-wait and a single retry on 429.
    Returns (ok, status_code).
    """
    _rl_pre_wait(url)

    def _do_post():
        resp = (session or requests).post(url, json=payload, timeout=10)
        _rl_note_headers(url, resp.headers, is_429=(resp.status_code == 429))
        return resp

    resp = _do_post()
    status = getattr(resp, "status_code", None)
    if status is not None and 200 <= status < 300:
        return True, status

    # Handle rate limit: back off then retry once
    if status == 429:
        hdr = resp.headers
        wait = hdr.get("X-RateLimit-Reset-After") or hdr.get("Retry-After") or 1.0
        try:
            wait = float(wait)
            if wait > 1000:
                wait = wait / 1000.0
        except Exception:
            wait = 1.0
        time.sleep(min(max(wait, 0.5), 5.0))
        resp2 = _do_post()
        status2 = getattr(resp2, "status_code", None)
        return (status2 is not None and 200 <= status2 < 300), status2

    return False, status
