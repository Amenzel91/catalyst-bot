"""
Per-User Watchlist Management
==============================

Discord user-specific watchlist storage and management for slash commands.
Each user has their own watchlist stored as JSON in data/watchlists/{user_id}.json.

This is separate from the bot-wide watchlist.csv used for price ceiling bypasses.

Features:
- Add/remove tickers per user
- List all tickers
- Clear watchlist
- Filter alerts by watchlist
- Optional DM notifications
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .logging_utils import get_logger

log = get_logger("user_watchlist")

# Configuration
WATCHLIST_DIR = Path(__file__).resolve().parents[2] / "data" / "watchlists"
MAX_WATCHLIST_SIZE = int(os.getenv("WATCHLIST_MAX_SIZE", "50"))


def _get_watchlist_path(user_id: str) -> Path:
    """
    Get path to user's watchlist file.

    Parameters
    ----------
    user_id : str
        Discord user ID

    Returns
    -------
    Path
        Path to watchlist JSON file
    """
    # Ensure watchlist directory exists
    WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)
    return WATCHLIST_DIR / f"{user_id}.json"


def _load_watchlist(user_id: str) -> List[str]:
    """
    Load user's watchlist from disk.

    Parameters
    ----------
    user_id : str
        Discord user ID

    Returns
    -------
    List[str]
        List of ticker symbols
    """
    path = _get_watchlist_path(user_id)

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tickers", [])
    except Exception as e:
        log.error(f"watchlist_load_failed user_id={user_id} err={e}")
        return []


def _save_watchlist(user_id: str, tickers: List[str]) -> bool:
    """
    Save user's watchlist to disk.

    Parameters
    ----------
    user_id : str
        Discord user ID
    tickers : List[str]
        List of ticker symbols

    Returns
    -------
    bool
        True if successful
    """
    path = _get_watchlist_path(user_id)

    try:
        data = {
            "user_id": user_id,
            "tickers": tickers,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True
    except Exception as e:
        log.error(f"watchlist_save_failed user_id={user_id} err={e}")
        return False


def add_to_watchlist(user_id: str, ticker: str) -> tuple[bool, str]:
    """
    Add a ticker to user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID
    ticker : str
        Ticker symbol to add

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    ticker = ticker.strip().upper()

    if not ticker:
        return False, "Invalid ticker symbol"

    # Load current watchlist
    tickers = _load_watchlist(user_id)

    # Check if already in watchlist
    if ticker in tickers:
        return False, f"{ticker} is already in your watchlist"

    # Check max size
    if len(tickers) >= MAX_WATCHLIST_SIZE:
        return False, f"Watchlist is full (max {MAX_WATCHLIST_SIZE} tickers)"

    # Add ticker
    tickers.append(ticker)

    # Save
    if _save_watchlist(user_id, tickers):
        log.info(
            f"watchlist_add user_id={user_id} ticker={ticker} total={len(tickers)}"
        )
        return True, f"Added {ticker} to watchlist"
    else:
        return False, "Failed to save watchlist"


def remove_from_watchlist(user_id: str, ticker: str) -> tuple[bool, str]:
    """
    Remove a ticker from user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID
    ticker : str
        Ticker symbol to remove

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    ticker = ticker.strip().upper()

    # Load current watchlist
    tickers = _load_watchlist(user_id)

    # Check if in watchlist
    if ticker not in tickers:
        return False, f"{ticker} is not in your watchlist"

    # Remove ticker
    tickers.remove(ticker)

    # Save
    if _save_watchlist(user_id, tickers):
        log.info(
            f"watchlist_remove user_id={user_id} ticker={ticker} total={len(tickers)}"
        )
        return True, f"Removed {ticker} from watchlist"
    else:
        return False, "Failed to save watchlist"


def get_watchlist(user_id: str) -> List[str]:
    """
    Get user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID

    Returns
    -------
    List[str]
        List of ticker symbols
    """
    return _load_watchlist(user_id)


def clear_watchlist(user_id: str) -> tuple[bool, str]:
    """
    Clear user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    # Save empty list
    if _save_watchlist(user_id, []):
        log.info(f"watchlist_clear user_id={user_id}")
        return True, "Watchlist cleared"
    else:
        return False, "Failed to clear watchlist"


def is_ticker_in_watchlist(user_id: str, ticker: str) -> bool:
    """
    Check if a ticker is in user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID
    ticker : str
        Ticker symbol

    Returns
    -------
    bool
        True if ticker is in watchlist
    """
    tickers = _load_watchlist(user_id)
    return ticker.upper() in tickers


def get_watchlist_alerts(user_id: str, alerts: List[dict]) -> List[dict]:
    """
    Filter alerts by user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID
    alerts : List[dict]
        List of alert dictionaries

    Returns
    -------
    List[dict]
        Filtered alerts
    """
    watchlist = _load_watchlist(user_id)

    if not watchlist:
        return []

    # Filter alerts
    filtered = [
        alert for alert in alerts if alert.get("ticker", "").upper() in watchlist
    ]

    return filtered


def get_all_watchlists() -> dict[str, List[str]]:
    """
    Get all user watchlists.

    Returns
    -------
    dict[str, List[str]]
        Dictionary mapping user_id to list of tickers
    """
    if not WATCHLIST_DIR.exists():
        return {}

    watchlists = {}

    for path in WATCHLIST_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                user_id = data.get("user_id") or path.stem
                tickers = data.get("tickers", [])
                watchlists[user_id] = tickers
        except Exception:
            continue

    return watchlists


def get_users_watching_ticker(ticker: str) -> List[str]:
    """
    Get all user IDs that have a ticker in their watchlist.

    Parameters
    ----------
    ticker : str
        Ticker symbol

    Returns
    -------
    List[str]
        List of user IDs
    """
    ticker = ticker.upper()
    all_watchlists = get_all_watchlists()

    user_ids = [
        user_id for user_id, tickers in all_watchlists.items() if ticker in tickers
    ]

    return user_ids


def get_watchlist_stats(user_id: str) -> dict:
    """
    Get statistics about user's watchlist.

    Parameters
    ----------
    user_id : str
        Discord user ID

    Returns
    -------
    dict
        Statistics dictionary
    """
    tickers = _load_watchlist(user_id)

    return {
        "total_tickers": len(tickers),
        "max_size": MAX_WATCHLIST_SIZE,
        "remaining_slots": MAX_WATCHLIST_SIZE - len(tickers),
        "tickers": tickers,
    }
