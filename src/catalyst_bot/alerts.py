from __future__ import annotations
import time
from typing import Optional
import requests
from .logging_utils import get_logger
log = get_logger("alerts")

def _post_json(url: str, payload: dict, timeout: int = 10) -> int:
    r = requests.post(url, json=payload, timeout=timeout)
    if r.status_code in (429, 500, 502, 503, 504):
        ra = int(r.headers.get("Retry-After", "1"))
        time.sleep(min(ra, 5))
    return r.status_code

def send_discord(webhook: str, content: str, retry: int = 3) -> bool:
    if not webhook:
        log.info("webhook_missing skip_send")
        return False
    payload = {"content": content[:1900]}  # safety
    for attempt in range(1, retry + 1):
        try:
            code = _post_json(webhook, payload)
            if 200 <= code < 300:
                return True
            log.warning(f"discord_send status={code} attempt={attempt}")
            time.sleep(min(2 ** attempt, 8))
        except Exception as e:
            log.warning(f"discord_send_error attempt={attempt} err={e!s}")
            time.sleep(min(2 ** attempt, 8))
    return False
