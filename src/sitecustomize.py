"""
Site Hooks for Catalyst-Bot (import-time integration)

Why this file?
--------------
Python automatically imports `sitecustomize` if present on sys.path.
We use this to *safely* and *reversibly* attach integrations without modifying
your existing modules:

1) Hook alerts.send_alert_safe(...)  -> suppress re-alerts via SeenStore (TTL)
2) Hook feeds.extract_ticker(...)    -> fallback to ticker_resolver on None
3) Sanitize tickers before classify  -> drop obvious junk tickers
4) (Optional) Rate-limit Discord posts to prevent bursts

Toggle with env flags:
- FEATURE_SITE_HOOKS            (default: "true")
- HOOK_SEEN_ALERTS              (default: "true")
- HOOK_TICKER_RESOLVER          (default: "true")
- HOOK_TICKER_SANITY            (default: "true")
- HOOK_ALERTS_RATE_LIMIT        (default: "false")  # opt-in
- HOOK_FALLBACK_LOG_EVERY_N     (default: "100")    # throttle INFO logs
- HOOK_SANITIZED_LOG_EVERY_N    (default: "50")     # throttle INFO logs
- ALERTS_RATE_WINDOW_SECS       (default: "60")     # if limiter on
- ALERTS_RATE_MAX               (default: "4")      # if limiter on
"""

from __future__ import annotations

import atexit
import json
import os
import sys
import time
import types

try:
    # Prefer project logger if available
    from catalyst_bot.logging_utils import get_logger  # type: ignore
except Exception:  # pragma: no cover - fallback
    import logging  # noqa: F401

    def get_logger(name: str):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        return logging.getLogger(name)  # type: ignore


log = get_logger("site_hooks")


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _emit_raw_json(event: str, **fields) -> None:
    """
    Atexit-safe: write a minimal JSON line to stderr without using logging.
    This avoids 'I/O operation on closed file' from closed logging handlers.
    """
    try:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": "INFO",
            "name": "site_hooks",
            "msg": event,
        }
        if fields:
            payload.update(fields)
        sys.__stderr__.write(json.dumps(payload) + "\n")
        sys.__stderr__.flush()
    except Exception:
        # Last resort: swallow
        pass


# ---- Lazy import helper to avoid early import of the module being run with -m ----
def _resolve_from_source(*args, **kwargs):
    """
    Lazily import the resolver at call time to prevent Python's -m runtime warning:
    "'catalyst_bot.ticker_resolver' found in sys.modules after import of package..."
    """
    from catalyst_bot.ticker_resolver import resolve_from_source as _rfs  # type: ignore
    return _rfs(*args, **kwargs)


# Be a good citizen: allow disabling entirely
if not _flag("FEATURE_SITE_HOOKS", "true"):
    log.info("site_hooks_disabled")
else:
    # Throttled counters (resolver + sanitization)
    _fallback_hits = 0
    _fallback_log_every = max(1, _int("HOOK_FALLBACK_LOG_EVERY_N", 100))

    _sanitized_hits = 0
    _sanitized_log_every = max(1, _int("HOOK_SANITIZED_LOG_EVERY_N", 50))

    def _log_fallback_hit(**extra_fields):
        """Emit an INFO message every N hits; retain total for exit summary."""
        global _fallback_hits
        _fallback_hits += 1
        if _fallback_hits % _fallback_log_every == 0:
            log.info("ticker_resolver_fallback_hit", extra=extra_fields)

    def _log_sanitized_drop(**extra_fields):
        """Emit an INFO message every N sanitized drops to reduce log noise."""
        global _sanitized_hits
        _sanitized_hits += 1
        if _sanitized_hits % _sanitized_log_every == 0:
            log.info("ticker_sanitized_drop", extra=extra_fields)

    @atexit.register
    def _exit_summary() -> None:
        # Do NOT use logging here; handlers may be closed.
        if _fallback_hits:
            _emit_raw_json("ticker_resolver_fallback_summary", hits=_fallback_hits)
        if _sanitized_hits:
            _emit_raw_json("ticker_sanitized_summary", drops=_sanitized_hits)

    # ---------------------------------------------------------------
    # Hook 1: alerts.send_alert_safe -> persistent 'seen' suppression
    # ---------------------------------------------------------------
    if _flag("HOOK_SEEN_ALERTS", "true"):
        try:
            from catalyst_bot import alerts  # type: ignore
            from catalyst_bot.alert_guard import build_alert_id

            try:
                from catalyst_bot.seen_store import should_filter  # type: ignore
            except Exception:  # pragma: no cover

                def should_filter(_id: str) -> bool:
                    return False

            if isinstance(getattr(alerts, "send_alert_safe", None), types.FunctionType):
                _orig_send = alerts.send_alert_safe

                def _wrapped_send_alert_safe(payload, *args, **kwargs):
                    try:
                        item_id = build_alert_id(payload)
                        if item_id and should_filter(item_id):
                            log.info("alert_suppressed_seen", extra={"id": item_id})
                            return {"status": "suppressed_seen", "id": item_id}
                    except Exception as e:  # non-fatal
                        log.debug("alert_seen_guard_error", extra={"error": str(e)})
                    return _orig_send(payload, *args, **kwargs)

                alerts.send_alert_safe = _wrapped_send_alert_safe  # type: ignore
                log.info(
                    "site_hooks_alerts_patched",
                    extra={"target": "send_alert_safe"},
                )
            else:
                log.debug(
                    "site_hooks_alerts_noop",
                    extra={"reason": "send_alert_safe_missing"},
                )
        except Exception as e:  # pragma: no cover
            # Be quiet in tool contexts (black/flake8/pre-commit)
            log.debug("site_hooks_alerts_failed", extra={"error": str(e)})

    # ----------------------------------------------------------------
    # Hook 2: feeds.extract_ticker -> ticker_resolver as a safe fallback
    # + Hook 3: Ticker sanitation
    # ----------------------------------------------------------------
    if _flag("HOOK_TICKER_RESOLVER", "true") or _flag("HOOK_TICKER_SANITY", "true"):
        try:
            from catalyst_bot import feeds  # type: ignore
            from catalyst_bot.ticker_sanity import sanitize_ticker

            fn = getattr(feeds, "extract_ticker", None)
            if isinstance(fn, types.FunctionType):
                _orig_extract = fn

                def _wrapped_extract_ticker(*args, **kwargs):
                    # Try original first
                    try:
                        orig = _orig_extract(*args, **kwargs)
                    except Exception as e:
                        log.debug(
                            "extract_ticker_orig_error",
                            extra={"error": str(e)},
                        )
                        orig = None

                    title = kwargs.get("title")
                    link = kwargs.get("link")
                    source_host = kwargs.get("source_host")
                    if not title and args:
                        try:
                            title = args[0]
                        except Exception:
                            title = None

                    res = orig
                    if not res and _flag("HOOK_TICKER_RESOLVER", "true"):
                        try:
                            r = _resolve_from_source(title or "", link, source_host)
                            if getattr(r, "ticker", None):
                                _log_fallback_hit(
                                    method=getattr(r, "method", None),
                                    title=(title or "")[:80],
                                    link=(link or "")[:120],
                                )
                                res = r.ticker
                        except Exception as e:  # non-fatal
                            log.debug(
                                "ticker_resolver_fallback_error",
                                extra={"error": str(e)},
                            )

                    if res and _flag("HOOK_TICKER_SANITY", "true"):
                        cleaned = sanitize_ticker(res)
                        if cleaned is None:
                            _log_sanitized_drop(
                                reason="failed_rules",
                                raw=str(res)[:24],
                                title=(title or "")[:80],
                            )
                            return None
                        if cleaned != res:
                            log.info(
                                "ticker_sanitized_adjust",
                                extra={"raw": str(res), "cleaned": cleaned},
                            )
                        return cleaned

                    return res

                setattr(feeds, "extract_ticker", _wrapped_extract_ticker)
                log.info("site_hooks_feeds_patched", extra={"target": "extract_ticker"})
            else:
                log.debug(
                    "site_hooks_feeds_noop",
                    extra={"reason": "extract_ticker_missing"},
                )
        except Exception as e:  # pragma: no cover
            log.debug("site_hooks_feeds_failed", extra={"error": str(e)})

    # ---------------------------------------------------------------
    # Hook 4 (optional): Alerts rate limiter (per ticker/channel)
    # ---------------------------------------------------------------
    if _flag("HOOK_ALERTS_RATE_LIMIT", "false"):
        try:
            from catalyst_bot import alerts  # type: ignore
            from catalyst_bot.alerts_rate_limit import (
                limiter_allow,
                limiter_key_from_payload,
            )

            post_fn = getattr(alerts, "post_discord_json", None)
            if isinstance(post_fn, types.FunctionType):
                _orig_post = post_fn

                def _wrapped_post_discord_json(payload: dict, *args, **kwargs):
                    try:
                        key = limiter_key_from_payload(payload)
                        if not limiter_allow(key):
                            log.info("alert_rate_limited", extra={"key": key})
                            return {"status": "rate_limited", "key": key}
                    except Exception as e:
                        log.debug("alert_rate_limit_error", extra={"error": str(e)})
                    return _orig_post(payload, *args, **kwargs)

                alerts.post_discord_json = _wrapped_post_discord_json  # type: ignore
                log.info("site_hooks_alerts_limiter_patched", extra={"target": "post"})
            else:
                log.debug(
                    "site_hooks_alerts_limiter_noop",
                    extra={"reason": "post_missing"},
                )
        except Exception as e:  # pragma: no cover
            log.debug("site_hooks_alerts_limiter_failed", extra={"error": str(e)})
