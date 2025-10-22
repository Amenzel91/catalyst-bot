"""Pre-market price action sentiment source for Catalyst Bot.

This module provides sentiment analysis based on pre-market price movements,
which serve as a leading indicator of institutional reaction before retail
trading begins.

Pre-market moves (4:00-9:30 AM ET) show how institutions are positioning
before the market opens. Large pre-market moves often predict intraday
momentum and can be used to boost or reduce sentiment scores.

The sentiment calculation follows a scaled approach:
- PM change > +15%: sentiment = +0.9 (extreme bullish pre-market)
- PM change > +10%: sentiment = +0.7 (very strong bullish)
- PM change > +5%: sentiment = +0.5 (strong bullish)
- PM change < -15%: sentiment = -0.9 (extreme bearish)
- PM change < -10%: sentiment = -0.7 (very strong bearish)
- PM change < -5%: sentiment = -0.5 (strong bearish)
- PM change between -5% and +5%: linear scaling

This sentiment is only calculated during:
1. Pre-market hours (4:00-9:30 AM ET)
2. First 30 minutes of regular trading (9:30-10:00 AM ET)

Outside these windows, None is returned to avoid stale data.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from .config import get_settings
from .logging_utils import get_logger
from .market_hours import get_market_status

log = get_logger("premarket_sentiment")

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


def is_premarket_period(dt: Optional[datetime] = None) -> bool:
    """
    Check if the given time is within the pre-market analysis window.

    Pre-market analysis is valid during:
    - Pre-market hours: 4:00 AM - 9:30 AM ET
    - Early trading: 9:30 AM - 10:00 AM ET (first 30 min)

    Outside these windows, pre-market data becomes stale.

    Parameters
    ----------
    dt : datetime, optional
        The datetime to check. If None, uses current UTC time.

    Returns
    -------
    bool
        True if within pre-market analysis window, False otherwise.
    """
    if dt is None:
        from datetime import timezone
        dt = datetime.now(timezone.utc)

    # Convert to Eastern Time
    dt_et = dt.astimezone(ET)

    # Check market status first (handles weekends/holidays)
    status = get_market_status(dt)

    # Pre-market period: during pre_market status
    if status == "pre_market":
        return True

    # Early trading period: first 30 minutes of regular hours
    if status == "regular":
        current_time = dt_et.time()
        market_open = time(9, 30)
        early_cutoff = time(10, 0)

        if market_open <= current_time < early_cutoff:
            return True

    return False


def calculate_premarket_sentiment(
    premarket_price: float,
    previous_close: float,
) -> float:
    """
    Calculate sentiment score from pre-market price change.

    The sentiment follows a piecewise linear function:
    - Linear scaling between thresholds
    - Caps at ±0.9 for extreme moves (>±15%)
    - Returns 0.0 for moves between -5% and +5%

    Formula:
    --------
    pm_change_pct = (pm_price - prev_close) / prev_close * 100

    if pm_change >= 15:
        sentiment = 0.9
    elif pm_change >= 10:
        sentiment = 0.7 + 0.2 * (pm_change - 10) / 5
    elif pm_change >= 5:
        sentiment = 0.5 + 0.2 * (pm_change - 5) / 5
    elif pm_change >= 0:
        sentiment = 0.0 + 0.5 * pm_change / 5
    else:
        # Mirror logic for negative moves
        sentiment = -calculate_premarket_sentiment(-pm_change)

    Parameters
    ----------
    premarket_price : float
        Current pre-market price
    previous_close : float
        Previous day's closing price

    Returns
    -------
    float
        Sentiment score in range [-0.9, 0.9]
    """
    if previous_close <= 0:
        return 0.0

    # Calculate percentage change
    pm_change_pct = ((premarket_price - previous_close) / previous_close) * 100.0

    # Positive moves
    if pm_change_pct >= 15.0:
        return 0.9
    elif pm_change_pct >= 10.0:
        # Linear interpolation between 0.7 and 0.9
        return 0.7 + 0.2 * ((pm_change_pct - 10.0) / 5.0)
    elif pm_change_pct >= 5.0:
        # Linear interpolation between 0.5 and 0.7
        return 0.5 + 0.2 * ((pm_change_pct - 5.0) / 5.0)
    elif pm_change_pct > 0:
        # Linear interpolation between 0.0 and 0.5
        return 0.5 * (pm_change_pct / 5.0)

    # Negative moves (mirror the positive logic)
    elif pm_change_pct <= -15.0:
        return -0.9
    elif pm_change_pct <= -10.0:
        # Linear interpolation between -0.7 and -0.9
        return -0.7 - 0.2 * ((abs(pm_change_pct) - 10.0) / 5.0)
    elif pm_change_pct <= -5.0:
        # Linear interpolation between -0.5 and -0.7
        return -0.5 - 0.2 * ((abs(pm_change_pct) - 5.0) / 5.0)
    else:
        # Linear interpolation between 0.0 and -0.5
        return -0.5 * (abs(pm_change_pct) / 5.0)


def get_premarket_sentiment(
    ticker: str,
    dt: Optional[datetime] = None,
) -> Optional[Tuple[float, Dict[str, float]]]:
    """
    Get pre-market sentiment for a ticker.

    This function:
    1. Checks if we're in the pre-market analysis window
    2. Fetches current pre-market price and previous close
    3. Calculates sentiment score based on price change
    4. Returns None if outside pre-market window or data unavailable

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    dt : datetime, optional
        The datetime to check. If None, uses current UTC time.

    Returns
    -------
    Optional[Tuple[float, Dict[str, float]]]
        If successful, returns (sentiment_score, metadata) where:
        - sentiment_score: float in range [-0.9, 0.9]
        - metadata: Dict with keys:
            - premarket_price: Current pre-market price
            - previous_close: Previous day's closing price
            - premarket_change_pct: Percentage change
            - is_premarket_hours: Whether in pre-market window

        Returns None if:
        - Outside pre-market analysis window
        - Unable to fetch price data
        - Feature disabled

    Examples
    --------
    >>> # During pre-market hours (7:00 AM ET)
    >>> result = get_premarket_sentiment("AAPL")
    >>> if result:
    ...     sentiment, metadata = result
    ...     print(f"PM sentiment: {sentiment:.2f}")
    ...     print(f"PM price: ${metadata['premarket_price']:.2f}")
    ...     print(f"PM change: {metadata['premarket_change_pct']:.2f}%")

    >>> # Outside pre-market hours (11:00 AM ET)
    >>> result = get_premarket_sentiment("AAPL")
    >>> print(result)  # None
    """
    try:
        settings = get_settings()
    except Exception:
        settings = None

    # Check if feature is enabled
    if settings and not getattr(settings, "feature_premarket_sentiment", False):
        return None

    # Check if we're in the pre-market analysis window
    if not is_premarket_period(dt):
        return None

    # Fetch current price and previous close
    try:
        from .market import get_last_price_snapshot

        last_price, prev_close = get_last_price_snapshot(ticker, retries=1)

        if last_price is None or prev_close is None:
            log.debug(
                "premarket_no_price ticker=%s last=%s prev=%s",
                ticker,
                last_price,
                prev_close,
            )
            return None

        # Calculate sentiment
        sentiment = calculate_premarket_sentiment(last_price, prev_close)

        # Calculate percentage change
        pm_change_pct = ((last_price - prev_close) / prev_close) * 100.0

        # Build metadata
        metadata: Dict[str, float] = {
            "premarket_price": float(last_price),
            "previous_close": float(prev_close),
            "premarket_change_pct": float(pm_change_pct),
            "is_premarket_hours": 1.0,  # Boolean as float for consistency
        }

        log.debug(
            "premarket_sentiment ticker=%s pm_price=%.2f prev_close=%.2f "
            "pm_change_pct=%.2f sentiment=%.3f",
            ticker,
            last_price,
            prev_close,
            pm_change_pct,
            sentiment,
        )

        return sentiment, metadata

    except Exception as e:
        log.debug(
            "premarket_sentiment_error ticker=%s err=%s",
            ticker,
            e.__class__.__name__,
        )
        return None


def get_premarket_description(pm_change_pct: float) -> str:
    """
    Generate a human-readable description of pre-market movement.

    Parameters
    ----------
    pm_change_pct : float
        Pre-market percentage change

    Returns
    -------
    str
        Description like "Strong pre-market rally (+8.5%)"
    """
    abs_change = abs(pm_change_pct)

    if pm_change_pct >= 15.0:
        return f"Extreme pre-market surge (+{pm_change_pct:.1f}%)"
    elif pm_change_pct >= 10.0:
        return f"Very strong pre-market rally (+{pm_change_pct:.1f}%)"
    elif pm_change_pct >= 5.0:
        return f"Strong pre-market rally (+{pm_change_pct:.1f}%)"
    elif pm_change_pct >= 2.0:
        return f"Moderate pre-market gain (+{pm_change_pct:.1f}%)"
    elif pm_change_pct > 0.5:
        return f"Slight pre-market gain (+{pm_change_pct:.1f}%)"
    elif pm_change_pct <= -15.0:
        return f"Extreme pre-market collapse ({pm_change_pct:.1f}%)"
    elif pm_change_pct <= -10.0:
        return f"Very strong pre-market decline ({pm_change_pct:.1f}%)"
    elif pm_change_pct <= -5.0:
        return f"Strong pre-market decline ({pm_change_pct:.1f}%)"
    elif pm_change_pct <= -2.0:
        return f"Moderate pre-market decline ({pm_change_pct:.1f}%)"
    elif pm_change_pct < -0.5:
        return f"Slight pre-market decline ({pm_change_pct:.1f}%)"
    else:
        return f"Flat pre-market ({pm_change_pct:+.1f}%)"


# Public API
__all__ = [
    "get_premarket_sentiment",
    "calculate_premarket_sentiment",
    "is_premarket_period",
    "get_premarket_description",
]
