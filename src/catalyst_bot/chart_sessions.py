"""
Chart Session Management
=========================

In-memory session storage for tracking user indicator preferences per ticker.

This module provides a simple TTL-based cache for storing user preferences
when toggling chart indicators via Discord select menus. Sessions automatically
expire after CHART_SESSION_TTL seconds (default: 3600 = 1 hour).

Architecture:
- In-memory dictionary keyed by (user_id, ticker)
- Automatic expiration using timestamp comparison
- Periodic cleanup to prevent memory bloat
- Thread-safe for concurrent access

Usage:
    from chart_sessions import set_user_indicator_preferences, get_user_indicator_preferences

    # Save user preferences
    set_user_indicator_preferences("user_123", "AAPL", ["sr", "bollinger"])

    # Load user preferences
    prefs = get_user_indicator_preferences("user_123", "AAPL")
    # Returns: ["sr", "bollinger"] or None if expired/not found
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from .logging_utils import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


log = get_logger("chart_sessions")


# Session storage
# Key: (user_id, ticker)
# Value: {
#     "indicators": List[str],
#     "timestamp": float,
#     "access_count": int
# }
_SESSION_STORE: Dict[Tuple[str, str], Dict[str, Any]] = {}

# Lock for thread safety
_STORE_LOCK = threading.RLock()

# Last cleanup timestamp
_LAST_CLEANUP = time.time()


def _get_session_ttl() -> int:
    """Get session TTL from environment (default: 3600 seconds = 1 hour)."""
    return int(os.getenv("CHART_SESSION_TTL", "3600"))


def _should_cleanup() -> bool:
    """Check if we should run cleanup (every 5 minutes)."""
    cleanup_interval = 300  # 5 minutes
    return (time.time() - _LAST_CLEANUP) > cleanup_interval


def _cleanup_expired_sessions() -> int:
    """
    Remove expired sessions from the store.

    Returns
    -------
    int
        Number of sessions removed
    """
    global _LAST_CLEANUP

    with _STORE_LOCK:
        ttl = _get_session_ttl()
        now = time.time()
        expired_keys = []

        for key, session in _SESSION_STORE.items():
            age = now - session["timestamp"]
            if age > ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del _SESSION_STORE[key]

        _LAST_CLEANUP = now

        if expired_keys:
            log.info(
                f"session_cleanup removed={len(expired_keys)} total={len(_SESSION_STORE)}"
            )

        return len(expired_keys)


def set_user_indicator_preferences(
    user_id: str,
    ticker: str,
    indicators: List[str],
) -> None:
    """
    Save user's indicator preferences for a ticker.

    Parameters
    ----------
    user_id : str
        Discord user ID
    ticker : str
        Stock ticker symbol
    indicators : List[str]
        List of indicator codes (e.g., ["sr", "bollinger"])

    Examples
    --------
    >>> set_user_indicator_preferences("123456", "AAPL", ["sr", "bollinger"])
    >>> prefs = get_user_indicator_preferences("123456", "AAPL")
    >>> prefs
    ['sr', 'bollinger']
    """
    with _STORE_LOCK:
        key = (user_id, ticker.upper())

        # Update or create session
        if key in _SESSION_STORE:
            _SESSION_STORE[key]["indicators"] = indicators
            _SESSION_STORE[key]["timestamp"] = time.time()
            _SESSION_STORE[key]["access_count"] += 1
        else:
            _SESSION_STORE[key] = {
                "indicators": indicators,
                "timestamp": time.time(),
                "access_count": 1,
            }

        log.debug(
            f"session_saved user_id={user_id} ticker={ticker} "
            f"indicators={len(indicators)} total_sessions={len(_SESSION_STORE)}"
        )

        # Trigger cleanup if needed
        if _should_cleanup() and os.getenv("CHART_SESSION_AUTO_CLEANUP", "1") == "1":
            _cleanup_expired_sessions()


def get_user_indicator_preferences(
    user_id: str,
    ticker: str,
) -> Optional[List[str]]:
    """
    Get user's indicator preferences for a ticker.

    Parameters
    ----------
    user_id : str
        Discord user ID
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Optional[List[str]]
        List of indicator codes, or None if not found/expired

    Examples
    --------
    >>> set_user_indicator_preferences("123456", "AAPL", ["sr"])
    >>> prefs = get_user_indicator_preferences("123456", "AAPL")
    >>> prefs
    ['sr']
    >>> prefs = get_user_indicator_preferences("123456", "TSLA")
    >>> prefs is None
    True
    """
    with _STORE_LOCK:
        key = (user_id, ticker.upper())

        if key not in _SESSION_STORE:
            return None

        session = _SESSION_STORE[key]
        ttl = _get_session_ttl()
        age = time.time() - session["timestamp"]

        # Check if expired
        if age > ttl:
            log.debug(
                f"session_expired user_id={user_id} ticker={ticker} age={age:.0f}s"
            )
            del _SESSION_STORE[key]
            return None

        # Update access count
        session["access_count"] += 1

        log.debug(
            f"session_loaded user_id={user_id} ticker={ticker} "
            f"indicators={len(session['indicators'])} age={age:.0f}s"
        )

        return session["indicators"]


def clear_user_sessions(user_id: str) -> int:
    """
    Clear all sessions for a specific user.

    Parameters
    ----------
    user_id : str
        Discord user ID

    Returns
    -------
    int
        Number of sessions cleared

    Examples
    --------
    >>> set_user_indicator_preferences("123456", "AAPL", ["sr"])
    >>> set_user_indicator_preferences("123456", "TSLA", ["bollinger"])
    >>> clear_user_sessions("123456")
    2
    """
    with _STORE_LOCK:
        keys_to_remove = [key for key in _SESSION_STORE if key[0] == user_id]

        for key in keys_to_remove:
            del _SESSION_STORE[key]

        if keys_to_remove:
            log.info(f"session_cleared user_id={user_id} count={len(keys_to_remove)}")

        return len(keys_to_remove)


def get_session_stats() -> Dict[str, Any]:
    """
    Get session storage statistics.

    Returns
    -------
    Dict[str, Any]
        Statistics including total sessions, unique users, memory usage

    Examples
    --------
    >>> stats = get_session_stats()
    >>> "total_sessions" in stats
    True
    """
    with _STORE_LOCK:
        total_sessions = len(_SESSION_STORE)
        unique_users = len(set(key[0] for key in _SESSION_STORE.keys()))
        unique_tickers = len(set(key[1] for key in _SESSION_STORE.keys()))

        # Calculate average access count
        access_counts = [s["access_count"] for s in _SESSION_STORE.values()]
        avg_access = sum(access_counts) / len(access_counts) if access_counts else 0

        # Calculate oldest session age
        now = time.time()
        ages = [now - s["timestamp"] for s in _SESSION_STORE.values()]
        oldest_age = max(ages) if ages else 0

        return {
            "total_sessions": total_sessions,
            "unique_users": unique_users,
            "unique_tickers": unique_tickers,
            "avg_access_count": avg_access,
            "oldest_session_age_seconds": oldest_age,
            "ttl_seconds": _get_session_ttl(),
        }


def force_cleanup() -> int:
    """
    Force cleanup of expired sessions immediately.

    Returns
    -------
    int
        Number of sessions removed

    Examples
    --------
    >>> force_cleanup()
    0
    """
    return _cleanup_expired_sessions()


__all__ = [
    "set_user_indicator_preferences",
    "get_user_indicator_preferences",
    "clear_user_sessions",
    "get_session_stats",
    "force_cleanup",
]
