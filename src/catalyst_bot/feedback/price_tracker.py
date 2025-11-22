"""
Price Tracking System
=====================

Background task that monitors price and volume changes for tracked alerts.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

from ..logging_utils import get_logger
from ..market import get_last_price_snapshot
from .database import get_pending_updates, update_performance

log = get_logger("feedback.price_tracker")

try:
    import yfinance as yf
except Exception:
    yf = None


def get_current_price_volume(ticker: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Fetch current price and volume for a ticker.

    Uses the existing market.py infrastructure to get price, then
    queries yfinance for volume data.

    Parameters
    ----------
    ticker : str
        Ticker symbol

    Returns
    -------
    tuple of (price, volume) or (None, None)
        Current price and volume, or None if unavailable
    """
    try:
        # Get price using existing infrastructure
        # get_last_price_snapshot returns Tuple[Optional[float], Optional[float]] = (last, prev)
        last_price, _prev_close = get_last_price_snapshot(ticker)
        price = last_price

        # Get volume from yfinance
        volume = None
        if yf:
            try:
                ticker_obj = yf.Ticker(ticker)
                # Get most recent volume from history
                hist = ticker_obj.history(period="1d", interval="5m")
                if not hist.empty and "Volume" in hist.columns:
                    volume = float(hist["Volume"].iloc[-1])
            except Exception as ve:
                log.debug("volume_fetch_failed ticker=%s error=%s", ticker, str(ve))

        return price, volume

    except Exception as e:
        log.warning(
            "get_current_price_volume_failed ticker=%s error=%s", ticker, str(e)
        )
        return None, None


def track_alert_performance() -> int:
    """
    Track performance for all pending alerts.

    This function:
    1. Queries pending alerts (posted within last 24 hours)
    2. Determines which timeframes need updates based on time elapsed
    3. Fetches current price and volume
    4. Calculates percentage changes
    5. Updates the database

    Returns
    -------
    int
        Number of alerts updated
    """
    log.debug("track_alert_performance_start")

    pending = get_pending_updates(max_age_hours=24)
    if not pending:
        log.debug("no_pending_alerts_to_track")
        return 0

    now = time.time()
    updated_count = 0

    for alert in pending:
        alert_id = alert["alert_id"]
        ticker = alert["ticker"]
        posted_at = alert["posted_at"]
        posted_price = alert.get("posted_price")

        time_elapsed = now - posted_at

        # Determine which timeframes to update
        timeframes_to_check = []

        # 15 minutes (900 seconds)
        if time_elapsed >= 900 and alert["price_15m"] is None:
            timeframes_to_check.append("15m")

        # 1 hour (3600 seconds)
        if time_elapsed >= 3600 and alert["price_1h"] is None:
            timeframes_to_check.append("1h")

        # 4 hours (14400 seconds)
        if time_elapsed >= 14400 and alert["price_4h"] is None:
            timeframes_to_check.append("4h")

        # 1 day (86400 seconds)
        if time_elapsed >= 86400 and alert["price_1d"] is None:
            timeframes_to_check.append("1d")

        if not timeframes_to_check:
            continue

        # Fetch current price and volume
        current_price, current_volume = get_current_price_volume(ticker)

        if current_price is None:
            log.debug(
                "price_unavailable_skipping alert_id=%s ticker=%s",
                alert_id,
                ticker,
            )
            continue

        # Calculate price change
        price_change = None
        if posted_price and posted_price > 0:
            price_change = ((current_price - posted_price) / posted_price) * 100

        # Calculate volume change (if we have reference volume)
        # For now, we'll store absolute volume and calculate change later
        # when we have baseline volume data
        volume_change = None

        # Update all applicable timeframes
        for tf in timeframes_to_check:
            success = update_performance(
                alert_id=alert_id,
                timeframe=tf,
                price=current_price,
                volume=current_volume,
                price_change=price_change,
                volume_change=volume_change,
            )

            if success:
                updated_count += 1
                log.info(
                    "performance_tracked alert_id=%s ticker=%s timeframe=%s "
                    "price=%.2f change=%.2f%%",
                    alert_id,
                    ticker,
                    tf,
                    current_price,
                    price_change or 0.0,
                )

    log.info("track_alert_performance_complete updated=%d", updated_count)
    return updated_count


def run_tracker_loop() -> None:
    """
    Run the price tracker in a continuous loop.

    This function is designed to be run in a background thread.
    It tracks alert performance every FEEDBACK_TRACKING_INTERVAL seconds.

    The loop can be stopped by setting the environment variable
    FEEDBACK_STOP_TRACKER=1.
    """
    try:
        interval = int(os.getenv("FEEDBACK_TRACKING_INTERVAL", "900"))
    except Exception:
        interval = 900  # 15 minutes default

    log.info("starting_price_tracker_loop interval=%d", interval)

    while True:
        try:
            # Check for stop signal
            if os.getenv("FEEDBACK_STOP_TRACKER", "0").strip() in ("1", "true", "yes"):
                log.info("tracker_stop_signal_received")
                break

            # Track performance
            track_alert_performance()

            # Sleep until next interval
            time.sleep(interval)

        except KeyboardInterrupt:
            log.info("tracker_interrupted")
            break
        except Exception as e:
            log.error("tracker_loop_error error=%s", str(e))
            # Sleep a bit before retrying to avoid tight error loops
            time.sleep(60)

    log.info("price_tracker_loop_stopped")
