from __future__ import annotations

import json
import random
import time
from typing import Any, Dict, List, Optional

import requests

from .logging_utils import get_logger

log = get_logger("alerts")

JSON = Dict[str, Any]


def _sleep_with_jitter(attempt: int) -> None:
    """Exponential backoff with small jitter, capped."""
    base = min(2**attempt, 16)
    time.sleep(base + random.uniform(0, 0.25))


def _parse_retry_after(header_val: Optional[str]) -> Optional[float]:
    if not header_val:
        return None
    try:
        return float(header_val)
    except Exception:
        return None


def send_discord(
    webhook_url: str,
    content: str,
    embeds: Optional[List[JSON]] = None,
    timeout: int = 10,
    max_attempts: int = 4,
) -> bool:
    """
    Send a Discord webhook message with retries and rate-limit handling.
    Returns True on success, False on non-fatal failures. Never raises.
    """
    if not webhook_url:
        log.info("webhook_missing skip_send")
        return False

    payload: JSON = {"content": content}
    if embeds:
        payload["embeds"] = embeds

    headers = {"Content-Type": "application/json"}

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                webhook_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=timeout,
            )
        except Exception as err:
            if attempt >= max_attempts:
                log.warning(
                    "webhook_http_error attempt=%s err=%s",
                    attempt,
                    str(err),
                )
                return False
            _sleep_with_jitter(attempt)
            continue

        # success
        if 200 <= resp.status_code < 300:
            return True

        # 429 rate limit: respect Retry-After
        if resp.status_code == 429:
            ra = _parse_retry_after(resp.headers.get("Retry-After"))
            if attempt >= max_attempts:
                log.warning(
                    "webhook_rate_limited attempts=%s retry_after=%s",
                    attempt,
                    ra,
                )
                return False
            time.sleep(min(ra or 2.0, 10.0))
            continue

        # 5xx: retry with backoff
        if 500 <= resp.status_code < 600:
            if attempt >= max_attempts:
                log.warning(
                    "webhook_5xx status=%s attempts=%s",
                    resp.status_code,
                    attempt,
                )
                return False
            _sleep_with_jitter(attempt)
            continue

        # 4xx (not 429): don't retry
        log.warning(
            "webhook_4xx status=%s body=%s",
            resp.status_code,
            resp.text[:200],
        )
        return False

    return False
