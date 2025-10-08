# -*- coding: utf-8 -*-
"""Market hours detection for Catalyst Bot.

Provides functions to detect current market status and adjust bot features
based on market hours and holidays.
"""

from __future__ import annotations

import os
from datetime import datetime, time
from typing import Dict, Literal
from zoneinfo import ZoneInfo

# Market status types
MarketStatus = Literal["pre_market", "regular", "after_hours", "closed"]

# US Stock Market holidays (2025) - dates in MM-DD format
MARKET_HOLIDAYS_2025 = [
    "01-01",  # New Year's Day
    "01-20",  # MLK Day (3rd Monday in January)
    "02-17",  # Presidents Day (3rd Monday in February)
    "04-18",  # Good Friday
    "05-26",  # Memorial Day (last Monday in May)
    "06-19",  # Juneteenth
    "07-04",  # Independence Day
    "09-01",  # Labor Day (1st Monday in September)
    "11-27",  # Thanksgiving (4th Thursday in November)
    "12-25",  # Christmas
]

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


def is_market_holiday(dt: datetime) -> bool:
    """
    Check if the given date is a market holiday.

    Parameters
    ----------
    dt : datetime
        The datetime to check (will be converted to ET).

    Returns
    -------
    bool
        True if the date is a market holiday, False otherwise.
    """
    # Convert to Eastern Time
    dt_et = dt.astimezone(ET)

    # Format as MM-DD
    date_str = dt_et.strftime("%m-%d")

    return date_str in MARKET_HOLIDAYS_2025


def is_weekend(dt: datetime) -> bool:
    """
    Check if the given date is a weekend.

    Parameters
    ----------
    dt : datetime
        The datetime to check.

    Returns
    -------
    bool
        True if the date is Saturday (5) or Sunday (6), False otherwise.
    """
    dt_et = dt.astimezone(ET)
    return dt_et.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def get_market_status(dt: datetime | None = None) -> MarketStatus:
    """
    Determine the current market status.

    Market hours (Eastern Time):
    - Pre-market: 4:00 AM - 9:30 AM ET
    - Regular: 9:30 AM - 4:00 PM ET
    - After-hours: 4:00 PM - 8:00 PM ET
    - Closed: 8:00 PM - 4:00 AM ET, weekends, and holidays

    Parameters
    ----------
    dt : datetime, optional
        The datetime to check. If None, uses current UTC time.

    Returns
    -------
    MarketStatus
        One of "pre_market", "regular", "after_hours", or "closed".
    """
    if dt is None:
        from datetime import timezone

        dt = datetime.now(timezone.utc)

    # Convert to Eastern Time
    dt_et = dt.astimezone(ET)

    # Check if weekend or holiday
    if is_weekend(dt_et) or is_market_holiday(dt_et):
        return "closed"

    # Get the time component
    current_time = dt_et.time()

    # Define market hours boundaries
    pre_market_start = time(4, 0)  # 4:00 AM ET
    regular_start = time(9, 30)  # 9:30 AM ET
    regular_end = time(16, 0)  # 4:00 PM ET
    after_hours_end = time(20, 0)  # 8:00 PM ET

    # Determine market status based on time
    if pre_market_start <= current_time < regular_start:
        return "pre_market"
    elif regular_start <= current_time < regular_end:
        return "regular"
    elif regular_end <= current_time < after_hours_end:
        return "after_hours"
    else:
        return "closed"


def is_preopen_warmup(dt: datetime | None = None) -> bool:
    """
    Check if we're in the pre-open warmup period.

    The warmup period starts 2 hours before market open (7:30 AM ET)
    and allows features to be gradually enabled before the market opens.

    Parameters
    ----------
    dt : datetime, optional
        The datetime to check. If None, uses current UTC time.

    Returns
    -------
    bool
        True if in warmup period, False otherwise.
    """
    if dt is None:
        from datetime import timezone

        dt = datetime.now(timezone.utc)

    # Convert to Eastern Time
    dt_et = dt.astimezone(ET)

    # Don't warmup on weekends or holidays
    if is_weekend(dt_et) or is_market_holiday(dt_et):
        return False

    current_time = dt_et.time()

    # Warmup period: 7:30 AM - 9:30 AM ET (2 hours before market open)
    warmup_hours = int(os.getenv("PREOPEN_WARMUP_HOURS", "2"))
    # Calculate warmup start time (default: 2 hours before 9:30 AM = 7:30 AM)
    warmup_hour = 9 - warmup_hours
    warmup_minute = 30
    warmup_start = time(warmup_hour, warmup_minute)
    regular_start = time(9, 30)

    return warmup_start <= current_time < regular_start


def get_feature_config(status: MarketStatus) -> Dict[str, bool]:
    """
    Get the feature configuration based on market status.

    Features controlled:
    - llm_enabled: LLM classification
    - charts_enabled: Chart generation
    - breakout_enabled: Breakout scanner

    Parameters
    ----------
    status : MarketStatus
        The current market status.

    Returns
    -------
    Dict[str, bool]
        Dictionary with feature flags.
    """
    # Read configuration from environment
    closed_disable_llm = os.getenv("CLOSED_DISABLE_LLM", "1") == "1"
    closed_disable_charts = os.getenv("CLOSED_DISABLE_CHARTS", "1") == "1"
    closed_disable_breakout = os.getenv("CLOSED_DISABLE_BREAKOUT", "1") == "1"

    if status == "regular":
        # Market open: all features enabled
        return {
            "llm_enabled": True,
            "charts_enabled": True,
            "breakout_enabled": True,
        }
    elif status in ("pre_market", "after_hours"):
        # Extended hours: LLM enabled, charts disabled, breakout enabled
        return {
            "llm_enabled": True,
            "charts_enabled": False,
            "breakout_enabled": True,
        }
    else:  # closed
        # Market closed: respect configuration
        return {
            "llm_enabled": not closed_disable_llm,
            "charts_enabled": not closed_disable_charts,
            "breakout_enabled": not closed_disable_breakout,
        }


def get_cycle_seconds(status: MarketStatus) -> int:
    """
    Get the recommended cycle time in seconds based on market status.

    Parameters
    ----------
    status : MarketStatus
        The current market status.

    Returns
    -------
    int
        Cycle time in seconds.
    """
    if status == "regular":
        return int(os.getenv("MARKET_OPEN_CYCLE_SEC", "60"))
    elif status in ("pre_market", "after_hours"):
        return int(os.getenv("EXTENDED_HOURS_CYCLE_SEC", "90"))
    else:  # closed
        return int(os.getenv("MARKET_CLOSED_CYCLE_SEC", "180"))


def get_market_info(dt: datetime | None = None) -> Dict[str, object]:
    """
    Get comprehensive market information for the given datetime.

    Parameters
    ----------
    dt : datetime, optional
        The datetime to check. If None, uses current UTC time.

    Returns
    -------
    Dict[str, object]
        Dictionary containing:
        - status: MarketStatus
        - cycle_seconds: int
        - features: Dict[str, bool]
        - is_warmup: bool
        - is_weekend: bool
        - is_holiday: bool
    """
    if dt is None:
        from datetime import timezone

        dt = datetime.now(timezone.utc)

    status = get_market_status(dt)

    return {
        "status": status,
        "cycle_seconds": get_cycle_seconds(status),
        "features": get_feature_config(status),
        "is_warmup": is_preopen_warmup(dt),
        "is_weekend": is_weekend(dt),
        "is_holiday": is_market_holiday(dt),
    }
