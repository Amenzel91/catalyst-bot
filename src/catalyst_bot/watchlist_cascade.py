"""Dynamic watchlist cascade for Catalyst‑Bot.

This module manages a stateful watchlist where each ticker carries a
"state" (HOT, WARM, COOL) and a timestamp of when it was last
promoted.  The state decays over time according to configurable
durations so that high‑priority names eventually cool off if no new
signals arrive.

The cascade operates independently of the static watchlist CSV.  A
separate JSON file (path defined by ``WATCHLIST_STATE_FILE`` or
``data/watchlist_state.json`` by default) persists the state across
bot restarts.  See ``catalyst_bot.config.Settings`` for the
environment knobs controlling the feature and durations.

Phase 1 Enhancement (2025-11-20):
    When ``FEATURE_WATCHLIST_PERFORMANCE=1`` is set, the cascade also
    logs promotions to a SQLite database (watchlist_performance.db) for
    detailed tracking and analysis. This logging is optional and does
    not affect core cascade functionality if disabled or on error.

Typical usage::

    from catalyst_bot.watchlist_cascade import (
        load_state,
        save_state,
        decay_state,
        promote_ticker,
        get_counts,
    )

    settings = get_settings()
    state = load_state(settings.watchlist_state_file)
    now = datetime.utcnow()
    state = decay_state(
        state,
        now,
        hot_days=settings.watchlist_hot_days,
        warm_days=settings.watchlist_warm_days,
        cool_days=settings.watchlist_cool_days,
    )

    # Basic promotion (Phase 0 - existing behavior)
    promote_ticker(state, "AAPL", state_name="HOT")

    # Enhanced promotion with context (Phase 1 - optional)
    context = {
        "trigger_reason": "FDA approval catalyst",
        "trigger_title": "FDA approves...",
        "catalyst_type": "fda_approval",
        "trigger_score": 0.85,
        "trigger_sentiment": 0.7,
        "trigger_price": 150.50,
        "trigger_volume": 5000000,
    }
    promote_ticker(state, "AAPL", state_name="HOT", context=context)

    save_state(settings.watchlist_state_file, state)

The timestamp stored in the state file is ISO 8601 in UTC.  Durations
are interpreted as whole days.  The cascade never deletes entries
automatically; COOL names persist indefinitely until re‑promoted.

"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

STATE_VERSION = 1


def _now_utc() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


def load_state(path: str | None) -> Dict[str, Dict[str, str]]:
    """Load the cascade state from ``path``.

    The returned mapping has uppercase tickers as keys and dict values
    with keys ``state`` and ``ts`` (ISO8601).  Unknown fields are
    preserved to allow forward compatibility.

    Missing or unreadable files yield an empty dict.
    """
    if not path:
        return {}
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        # Ensure keys are uppercase and values are dicts
        out: Dict[str, Dict[str, str]] = {}
        for k, v in data.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            tick = k.strip().upper()
            st = str(v.get("state") or "").strip().upper()
            ts = str(v.get("ts") or "").strip()
            if tick:
                out[tick] = {"state": st or "", "ts": ts or ""}
        return out
    except Exception:
        return {}


def save_state(path: str | None, state: Dict[str, Dict[str, str]]) -> None:
    """Persist the cascade state to ``path``.

    When ``path`` is falsy, the save operation is skipped.  The
    directory tree is created if it does not exist.  Any exceptions
    during writing are silently ignored.
    """
    if not path:
        return
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(path, mode="w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        # ignore failures
        pass


def decay_state(
    state: Dict[str, Dict[str, str]],
    now: datetime,
    *,
    hot_days: int,
    warm_days: int,
    cool_days: int,
) -> Dict[str, Dict[str, str]]:
    """Return a new state mapping with decayed states.

    Entries transition from HOT→WARM→COOL based on the number of
    days elapsed since their timestamp (``ts``).  Durations for each
    state are provided via ``hot_days``, ``warm_days`` and
    ``cool_days``.  Once an entry reaches COOL, it remains COOL
    indefinitely; the cascade does not remove entries automatically.

    Parameters
    ----------
    state : Dict[str, Dict[str, str]]
        Existing state mapping to decay.  This mapping is not modified
        in place; a shallow copy is made.
    now : datetime
        Current time in UTC.  Must be timezone‑aware.
    hot_days : int
        Number of days to keep an entry in HOT state before demoting
        to WARM.
    warm_days : int
        Number of days to keep an entry in WARM state before demoting
        to COOL.  The demotion occurs after ``hot_days + warm_days``
        days in total.
    cool_days : int
        Number of days to keep an entry in COOL state before it could
        be removed.  Currently entries are never auto‑removed, but
        this parameter is accepted for future expansion.

    Returns
    -------
    Dict[str, Dict[str, str]]
        A new mapping with updated ``state`` fields where needed.
    """
    out: Dict[str, Dict[str, str]] = {}
    for tick, meta in state.items():
        # copy meta to avoid mutating input
        new_meta = dict(meta) if isinstance(meta, dict) else {}
        st = new_meta.get("state", "").upper() or ""
        ts_str = new_meta.get("ts", "") or ""
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = None
        if not st or not ts:
            # Nothing to decay if state or timestamp missing
            out[tick] = new_meta
            continue
        # Compute days elapsed
        days = (now - ts).days
        # Demote state based on thresholds
        if st == "HOT" and hot_days >= 0 and days > hot_days:
            new_meta["state"] = "WARM"
        elif (
            st == "WARM"
            and hot_days >= 0
            and warm_days >= 0
            and days > (hot_days + warm_days)
        ):
            new_meta["state"] = "COOL"
        # Note: COOL entries stay COOL; removal logic could be added here
        out[tick] = new_meta
    return out


def promote_ticker(
    state: Dict[str, Dict[str, str]],
    ticker: str,
    *,
    state_name: str = "HOT",
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Promote ``ticker`` to ``state_name`` with current timestamp.

    Tickers are normalised to uppercase.  The state mapping is
    modified in place.  ``state_name`` must be one of HOT, WARM or
    COOL (case‑insensitive).  Any other value is ignored.  The
    timestamp is set to the current UTC time.

    Phase 1 Enhancement:
        When ``context`` is provided and ``FEATURE_WATCHLIST_PERFORMANCE=1``
        is enabled, this function also logs the promotion to the SQLite
        database with rich trigger context for analysis. Database logging
        errors are silently ignored to preserve backward compatibility.

    Parameters
    ----------
    state : Dict[str, Dict[str, str]]
        The watchlist state mapping to modify.
    ticker : str
        Ticker symbol to promote.  It will be normalised to
        uppercase and stripped of whitespace.
    state_name : str, optional
        Target state for the ticker.  Defaults to "HOT".
    context : dict, optional
        Rich context about why ticker was promoted. Supports keys:
        - trigger_reason (str): Short reason (e.g., "FDA approval catalyst")
        - trigger_title (str): Alert/news title
        - trigger_summary (str): Longer summary
        - catalyst_type (str): Category (fda_approval, earnings, etc.)
        - trigger_score (float): Alert score (0.0-1.0)
        - trigger_sentiment (float): Sentiment (-1.0 to +1.0)
        - trigger_price (float): Price at trigger
        - trigger_volume (float): Volume at trigger
        - alert_id (str): Link to original alert
        - tags (list[str]): Tags for categorization
        - metadata (dict): Additional key-value pairs

    Examples
    --------
    Basic promotion (backward compatible)::

        promote_ticker(state, "AAPL", state_name="HOT")

    Enhanced promotion with context::

        context = {
            "trigger_reason": "FDA approval catalyst",
            "trigger_title": "AAPL: FDA approves new drug XYZ",
            "catalyst_type": "fda_approval",
            "trigger_score": 0.85,
            "trigger_sentiment": 0.7,
            "trigger_price": 150.50,
            "trigger_volume": 5000000,
        }
        promote_ticker(state, "AAPL", state_name="HOT", context=context)
    """
    if not ticker:
        return
    tick = ticker.strip().upper()
    if not tick:
        return
    st = state_name.strip().upper()
    if st not in {"HOT", "WARM", "COOL"}:
        return
    ts = _now_utc().isoformat()
    # Update or create entry
    meta = state.get(tick) or {}
    meta["state"] = st
    meta["ts"] = ts
    state[tick] = meta

    # Phase 1: Optional database logging
    if context:
        _log_promotion_to_database(tick, st, context)


def get_counts(state: Dict[str, Dict[str, str]]) -> Dict[str, int]:
    """Return counts of each state (HOT, WARM, COOL).

    Missing or unknown states are ignored.  The returned dict
    includes keys for states present in the input; absent states are
    omitted rather than reported as zero.
    """
    counts: Dict[str, int] = {}
    for meta in state.values():
        st = str(meta.get("state") or "").upper()
        if not st:
            continue
        counts[st] = counts.get(st, 0) + 1
    return counts


def _log_promotion_to_database(
    ticker: str, state: str, context: Dict[str, Any]
) -> None:
    """Log ticker promotion to database (Phase 1 feature).

    This function is called internally by promote_ticker when context is
    provided. It checks if the feature is enabled and attempts to log to
    the database. All errors are silently caught to preserve backward
    compatibility.

    Parameters
    ----------
    ticker : str
        Uppercase ticker symbol
    state : str
        State (HOT, WARM, or COOL)
    context : dict
        Promotion context with trigger details
    """
    try:
        # Check if feature is enabled
        try:
            from .config import get_settings

            settings = get_settings()
            if not getattr(settings, "feature_watchlist_performance", False):
                return
        except Exception:
            # Feature flag check failed, silently skip
            return

        # Import database module
        try:
            from . import watchlist_db
        except ImportError:
            # Database module not available, silently skip
            return

        # Ensure database is initialized
        try:
            watchlist_db.init_database()
        except Exception:
            # Database initialization failed, silently skip
            return

        # Extract context fields
        trigger_reason = context.get("trigger_reason")
        trigger_title = context.get("trigger_title")
        trigger_summary = context.get("trigger_summary")
        catalyst_type = context.get("catalyst_type")
        trigger_score = context.get("trigger_score")
        trigger_sentiment = context.get("trigger_sentiment")
        trigger_price = context.get("trigger_price")
        trigger_volume = context.get("trigger_volume")
        alert_id = context.get("alert_id")
        tags = context.get("tags")
        metadata = context.get("metadata")

        # Get check interval based on state (from config or defaults)
        try:
            if state == "HOT":
                check_interval = getattr(
                    settings, "watchlist_hot_monitor_interval_sec", 300
                )
            elif state == "WARM":
                check_interval = getattr(
                    settings, "watchlist_warm_monitor_interval_sec", 900
                )
            else:  # COOL
                check_interval = getattr(
                    settings, "watchlist_cool_monitor_interval_sec", 1800
                )
        except Exception:
            # Default intervals
            check_interval = 300 if state == "HOT" else 900 if state == "WARM" else 1800

        # Add ticker to database
        watchlist_db.add_ticker(
            ticker=ticker,
            state=state,
            trigger_reason=trigger_reason,
            trigger_title=trigger_title,
            trigger_summary=trigger_summary,
            catalyst_type=catalyst_type,
            trigger_score=trigger_score,
            trigger_sentiment=trigger_sentiment,
            trigger_price=trigger_price,
            trigger_volume=trigger_volume,
            alert_id=alert_id,
            check_interval_seconds=check_interval,
            tags=tags,
            metadata=metadata,
        )

        # Record initial snapshot if price is available
        if trigger_price is not None:
            watchlist_db.record_snapshot(
                ticker=ticker,
                price=trigger_price,
                volume=trigger_volume,
                snapshot_metadata={"reason": "promotion", "state": state},
            )

    except Exception:
        # All errors silently ignored for backward compatibility
        pass
