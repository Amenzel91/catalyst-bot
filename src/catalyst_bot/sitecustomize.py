"""
Runtime shims loaded by Python (sitecustomize):
1) Bridge alerts.send_alert_safe(payload) <-> legacy kwargs signature.
2) Suppress duplicate alerts within this process using a small TTL cache.
   - Toggle with env HOOK_SEEN_ALERTS=true|false (default true)
   - TTL via SEEN_TTL_SECONDS (default 900 = 15min)
"""

from __future__ import annotations
import os
import time
import types

# ------------------- config helpers -------------------
def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1","true","yes","on"}

def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

# ------------------- seen cache (process-local) -------------------
_SEEN_ENABLED = _flag("HOOK_SEEN_ALERTS", "true")
_SEEN_TTL = max(60, _int("SEEN_TTL_SECONDS", 900))  # >=60s
_seen: dict[str, float] = {}  # key -> expiry epoch

def _now() -> float:
    return time.time()

def _gc_seen() -> None:
    # lazy cleanup when cache grows
    if len(_seen) > 4096:
        t = _now()
        for k, exp in list(_seen.items()):
            if exp <= t:
                _seen.pop(k, None)

def _mk_key(payload: dict) -> str:
    # compact key from typical fields (works for both new/legacy forms)
    it = payload.get("item") or {}
    src = (it.get("source") or "").strip().lower()
    tkr = (it.get("ticker") or "").strip().upper()
    # title may be in item or payload.scored; keep it simple and robust
    title = (it.get("title") or it.get("summary") or "").strip().lower()
    if not title:
        # fall back to link/id if no title
        title = (it.get("link") or it.get("id") or "").strip().lower()
    return f"{src}::{tkr}::{title[:160]}"

def _seen_check_and_mark(payload: dict) -> bool:
    """Return True if we've seen it recently and should suppress."""
    if not _SEEN_ENABLED:
        return False
    key = _mk_key(payload)
    t = _now()
    exp = _seen.get(key)
    if exp and exp > t:
        return True
    _seen[key] = t + _SEEN_TTL
    _gc_seen()
    return False

# ------------------- send_alert_safe wrapper -------------------
try:
    import catalyst_bot.alerts as _alerts
except Exception:
    _alerts = None

if _alerts and isinstance(getattr(_alerts, "send_alert_safe", None), types.FunctionType):
    _orig_send = _alerts.send_alert_safe  # keep the original

    def _wrapped_send_alert_safe(*args, **kwargs):
        """
        Accept either:
          - send_alert_safe(payload_dict)
          - send_alert_safe(item_dict=..., scored=..., last_price=..., last_change_pct=...,
                            record_only=..., webhook_url=...)
        Forward to underlying impl regardless of signature,
        with a pre-send seen-suppression.
        """
        # New-style: positional dict or kw 'payload'
        payload = None
        if args and isinstance(args[0], dict) and not kwargs:
            payload = args[0]
        elif "payload" in kwargs and isinstance(kwargs["payload"], dict):
            payload = kwargs["payload"]

        if payload is not None:
            # process-local duplicate suppression
            if _seen_check_and_mark(payload):
                # mimic a no-op "ok" to keep pipeline flowing quietly
                return True
            # try new-style first; fallback to legacy
            try:
                return _orig_send(payload)
            except TypeError:
                return _orig_send(
                    item_dict=payload.get("item"),
                    scored=payload.get("scored"),
                    last_price=payload.get("last_price"),
                    last_change_pct=payload.get("last_change_pct"),
                    record_only=payload.get("record_only", False),
                    webhook_url=payload.get("webhook_url"),
                )

        # Legacy kwargs
        if kwargs:
            # condense to payload so we can do seen-suppression
            payload = {
                "item": kwargs.get("item_dict") or kwargs.get("item"),
                "scored": kwargs.get("scored"),
                "last_price": kwargs.get("last_price"),
                "last_change_pct": kwargs.get("last_change_pct"),
                "record_only": kwargs.get("record_only", False),
                "webhook_url": kwargs.get("webhook_url"),
            }
            if _seen_check_and_mark(payload):
                return True
            # try legacy first; fallback to new-style
            try:
                return _orig_send(**kwargs)
            except TypeError:
                return _orig_send(payload)

        raise TypeError("send_alert_safe: no usable arguments")

    _alerts.send_alert_safe = _wrapped_send_alert_safe
