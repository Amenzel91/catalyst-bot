"""After-market price action sentiment source for Catalyst Bot.

This module provides sentiment analysis based on after-market price movements,
which serve as a leading indicator of institutional reaction to earnings releases
and material news that drops after market close.

After-market moves (4:00-8:00 PM ET) show how institutions are positioning
after the regular trading session. Large after-market moves often follow
earnings releases and can predict next-day momentum.

The sentiment calculation follows a scaled approach:
- AM change > +15%: sentiment = +0.9 (extreme bullish after-market)
- AM change > +10%: sentiment = +0.7 (very strong bullish)
- AM change > +5%: sentiment = +0.5 (strong bullish)
- AM change < -15%: sentiment = -0.9 (extreme bearish)
- AM change < -10%: sentiment = -0.7 (very strong bearish)
- AM change < -5%: sentiment = -0.5 (strong bearish)
- AM change between -5% and +5%: linear scaling

This sentiment is only calculated during:
1. After-market hours (4:00-8:00 PM ET)
2. First 30 minutes of pre-market next day (4:00-4:30 AM ET)

Outside these windows, None is returned to avoid stale data.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from .config import get_settings
from .logging_utils import get_logger
from .market_hours import get_market_status

log = get_logger("aftermarket_sentiment")

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


def is_aftermarket_period(dt: Optional[datetime] = None) -> bool:
    """
    Check if the given time is within the after-market analysis window.

    After-market analysis is valid during:
    - After-market hours: 4:00 PM - 8:00 PM ET
    - Early pre-market: 4:00 AM - 4:30 AM ET (next morning continuation)

    Outside these windows, after-market data becomes stale.

    Parameters
    ----------
    dt : datetime, optional
        The datetime to check. If None, uses current UTC time.

    Returns
    -------
    bool
        True if within after-market analysis window, False otherwise.
    """
    if dt is None:
        from datetime import timezone
        dt = datetime.now(timezone.utc)

    # Convert to Eastern Time
    dt_et = dt.astimezone(ET)

    # Check market status first (handles weekends/holidays)
    status = get_market_status(dt)

    # After-market period: during after_hours status
    if status == "after_hours":
        return True

    # Early pre-market period: first 30 minutes (continuation signal)
    if status == "pre_market":
        current_time = dt_et.time()
        premarket_start = time(4, 0)
        early_cutoff = time(4, 30)

        if premarket_start <= current_time < early_cutoff:
            return True

    return False


def calculate_aftermarket_sentiment(
    aftermarket_price: float,
    previous_close: float,
) -> float:
    """
    Calculate sentiment score from after-market price change.

    The sentiment follows a piecewise linear function:
    - Linear scaling between thresholds
    - Caps at ±0.9 for extreme moves (>±15%)
    - Returns 0.0 for moves between -5% and +5%

    Formula:
    --------
    am_change_pct = (am_price - prev_close) / prev_close * 100

    if am_change >= 15:
        sentiment = 0.9
    elif am_change >= 10:
        sentiment = 0.7 + 0.2 * (am_change - 10) / 5
    elif am_change >= 5:
        sentiment = 0.5 + 0.2 * (am_change - 5) / 5
    elif am_change >= 0:
        sentiment = 0.0 + 0.5 * am_change / 5
    else:
        # Mirror logic for negative moves
        sentiment = -calculate_aftermarket_sentiment(-am_change)

    Parameters
    ----------
    aftermarket_price : float
        Current after-market price
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
    am_change_pct = ((aftermarket_price - previous_close) / previous_close) * 100.0

    # Positive moves
    if am_change_pct >= 15.0:
        return 0.9
    elif am_change_pct >= 10.0:
        # Linear interpolation between 0.7 and 0.9
        return 0.7 + 0.2 * ((am_change_pct - 10.0) / 5.0)
    elif am_change_pct >= 5.0:
        # Linear interpolation between 0.5 and 0.7
        return 0.5 + 0.2 * ((am_change_pct - 5.0) / 5.0)
    elif am_change_pct > 0:
        # Linear interpolation between 0.0 and 0.5
        return 0.5 * (am_change_pct / 5.0)

    # Negative moves (mirror the positive logic)
    elif am_change_pct <= -15.0:
        return -0.9
    elif am_change_pct <= -10.0:
        # Linear interpolation between -0.7 and -0.9
        return -0.7 - 0.2 * ((abs(am_change_pct) - 10.0) / 5.0)
    elif am_change_pct <= -5.0:
        # Linear interpolation between -0.5 and -0.7
        return -0.5 - 0.2 * ((abs(am_change_pct) - 5.0) / 5.0)
    else:
        # Linear interpolation between 0.0 and -0.5
        return -0.5 * (abs(am_change_pct) / 5.0)


def get_aftermarket_sentiment(
    ticker: str,
    dt: Optional[datetime] = None,
) -> Optional[Tuple[float, Dict[str, float]]]:
    """
    Get after-market sentiment for a ticker.

    This function:
    1. Checks if we're in the after-market analysis window
    2. Fetches current after-market price and previous close
    3. Calculates sentiment score based on price change
    4. Returns None if outside after-market window or data unavailable

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
            - aftermarket_price: Current after-market price
            - previous_close: Previous day's closing price
            - aftermarket_change_pct: Percentage change
            - is_aftermarket_hours: Whether in after-market window

        Returns None if:
        - Outside after-market analysis window
        - Unable to fetch price data
        - Feature disabled

    Examples
    --------
    >>> # During after-market hours (6:00 PM ET)
    >>> result = get_aftermarket_sentiment("AAPL")
    >>> if result:
    ...     sentiment, metadata = result
    ...     print(f"AM sentiment: {sentiment:.2f}")
    ...     print(f"AM price: ${metadata['aftermarket_price']:.2f}")
    ...     print(f"AM change: {metadata['aftermarket_change_pct']:.2f}%")

    >>> # Outside after-market hours (11:00 AM ET)
    >>> result = get_aftermarket_sentiment("AAPL")
    >>> print(result)  # None
    """
    try:
        settings = get_settings()
    except Exception:
        settings = None

    # Check if feature is enabled
    if settings and not getattr(settings, "feature_aftermarket_sentiment", False):
        return None

    # Check if we're in the after-market analysis window
    if not is_aftermarket_period(dt):
        return None

    # Fetch current price and previous close
    try:
        from .market import get_last_price_snapshot

        last_price, prev_close = get_last_price_snapshot(ticker, retries=1)

        if last_price is None or prev_close is None:
            log.debug(
                "aftermarket_no_price ticker=%s last=%s prev=%s",
                ticker,
                last_price,
                prev_close,
            )
            return None

        # Calculate sentiment
        sentiment = calculate_aftermarket_sentiment(last_price, prev_close)

        # Calculate percentage change
        am_change_pct = ((last_price - prev_close) / prev_close) * 100.0

        # Build metadata
        metadata: Dict[str, float] = {
            "aftermarket_price": float(last_price),
            "previous_close": float(prev_close),
            "aftermarket_change_pct": float(am_change_pct),
            "is_aftermarket_hours": 1.0,  # Boolean as float for consistency
        }

        log.debug(
            "aftermarket_sentiment ticker=%s am_price=%.2f prev_close=%.2f "
            "am_change_pct=%.2f sentiment=%.3f",
            ticker,
            last_price,
            prev_close,
            am_change_pct,
            sentiment,
        )

        return sentiment, metadata

    except Exception as e:
        log.debug(
            "aftermarket_sentiment_error ticker=%s err=%s",
            ticker,
            e.__class__.__name__,
        )
        return None


def get_aftermarket_description(am_change_pct: float) -> str:
    """
    Generate a human-readable description of after-market movement.

    Parameters
    ----------
    am_change_pct : float
        After-market percentage change

    Returns
    -------
    str
        Description like "Strong after-market rally (+8.5%)"
    """
    abs_change = abs(am_change_pct)

    if am_change_pct >= 15.0:
        return f"Extreme after-market surge (+{am_change_pct:.1f}%)"
    elif am_change_pct >= 10.0:
        return f"Very strong after-market rally (+{am_change_pct:.1f}%)"
    elif am_change_pct >= 5.0:
        return f"Strong after-market rally (+{am_change_pct:.1f}%)"
    elif am_change_pct >= 2.0:
        return f"Moderate after-market gain (+{am_change_pct:.1f}%)"
    elif am_change_pct > 0.5:
        return f"Slight after-market gain (+{am_change_pct:.1f}%)"
    elif am_change_pct <= -15.0:
        return f"Extreme after-market collapse ({am_change_pct:.1f}%)"
    elif am_change_pct <= -10.0:
        return f"Very strong after-market decline ({am_change_pct:.1f}%)"
    elif am_change_pct <= -5.0:
        return f"Strong after-market decline ({am_change_pct:.1f}%)"
    elif am_change_pct <= -2.0:
        return f"Moderate after-market decline ({am_change_pct:.1f}%)"
    elif am_change_pct < -0.5:
        return f"Slight after-market decline ({am_change_pct:.1f}%)"
    else:
        return f"Flat after-market ({am_change_pct:+.1f}%)"


# Public API
__all__ = [
    "get_aftermarket_sentiment",
    "calculate_aftermarket_sentiment",
    "is_aftermarket_period",
    "get_aftermarket_description",
]
