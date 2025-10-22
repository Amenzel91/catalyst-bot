"""
Volume-Price Divergence Detection
===================================

Detects divergence patterns between price movement and volume to identify:
1. Weak rallies (price up, volume down) - bearish signal
2. Strong selloff reversals (price down, volume down) - bullish signal
3. Confirmed rallies (price up, volume up) - bullish confirmation
4. Confirmed selloffs (price down, volume up) - bearish confirmation

Classic technical analysis signal that helps filter false breakouts and
identify potential reversal points.

Key Insight:
- Volume confirms price moves. When they diverge, it signals lack of conviction
- Price rising on declining volume = weak hands, likely reversal
- Price falling on low volume = capitulation/exhaustion, potential bottom

Author: Claude Code
Date: 2025-10-21
"""

from __future__ import annotations

from typing import Dict, Optional

from .config import get_settings
from .logging_utils import get_logger

log = get_logger("volume_price_divergence")


def detect_divergence(
    ticker: str,
    price_change_pct: float,
    volume_change_pct: float,
    min_price_move: float = 0.02,  # 2% minimum price change
    min_volume_move: float = 0.30,  # 30% minimum volume change
) -> Optional[Dict]:
    """
    Detect volume-price divergence patterns.

    Args:
        ticker: Stock ticker symbol
        price_change_pct: Today's price change vs yesterday (0.05 = +5%)
        volume_change_pct: Today's volume vs 20-day average (-0.30 = -30%)
        min_price_move: Minimum price change threshold (default: 2%)
        min_volume_move: Minimum volume change threshold (default: 30%)

    Returns:
        Dict with divergence analysis:
        {
            "divergence_type": str ("WEAK_RALLY" | "STRONG_SELLOFF_REVERSAL" |
                                   "CONFIRMED_RALLY" | "CONFIRMED_SELLOFF" | None),
            "sentiment_adjustment": float (-0.15 to +0.15),
            "signal_strength": str ("STRONG" | "MODERATE" | "WEAK"),
            "price_change": float,
            "volume_change": float,
            "interpretation": str
        }
        Returns None if insufficient signal or feature disabled
    """
    settings = get_settings()

    # Check feature flag
    import os

    if os.getenv("FEATURE_VOLUME_PRICE_DIVERGENCE", "1") != "1":
        return None

    # Get thresholds from settings or environment
    min_price_move = float(
        os.getenv("MIN_PRICE_MOVE_PCT", str(min_price_move))
    )
    min_volume_move = float(
        os.getenv("MIN_VOLUME_MOVE_PCT", str(min_volume_move))
    )

    # Check if moves meet minimum thresholds
    price_move_significant = abs(price_change_pct) >= min_price_move
    volume_move_significant = abs(volume_change_pct) >= min_volume_move

    if not (price_move_significant and volume_move_significant):
        # Insufficient signal - no clear divergence
        return None

    # Classify divergence pattern
    divergence_type = None
    sentiment_adjustment = 0.0
    signal_strength = "WEAK"
    interpretation = ""

    # Calculate signal strength based on magnitude
    price_magnitude = abs(price_change_pct)
    volume_magnitude = abs(volume_change_pct)

    # Price up, Volume down = WEAK RALLY (bearish)
    if price_change_pct > min_price_move and volume_change_pct < -min_volume_move:
        divergence_type = "WEAK_RALLY"

        # Stronger signal = larger divergence
        if price_magnitude > 0.05 and volume_magnitude > 0.50:  # >5% price, >50% vol drop
            signal_strength = "STRONG"
            sentiment_adjustment = -0.15
        elif price_magnitude > 0.03 and volume_magnitude > 0.40:  # >3% price, >40% vol
            signal_strength = "MODERATE"
            sentiment_adjustment = -0.12
        else:
            signal_strength = "WEAK"
            sentiment_adjustment = -0.10

        interpretation = (
            f"Price rising +{price_change_pct*100:.1f}% on declining volume "
            f"({volume_change_pct*100:.1f}%) suggests weak buying pressure. "
            "Potential reversal signal."
        )

    # Price down, Volume down = STRONG SELLOFF REVERSAL (bullish)
    elif price_change_pct < -min_price_move and volume_change_pct < -min_volume_move:
        divergence_type = "STRONG_SELLOFF_REVERSAL"

        # Stronger signal = larger divergence
        if price_magnitude > 0.05 and volume_magnitude > 0.50:  # >5% drop, >50% vol drop
            signal_strength = "STRONG"
            sentiment_adjustment = +0.12
        elif price_magnitude > 0.03 and volume_magnitude > 0.40:  # >3% drop, >40% vol
            signal_strength = "MODERATE"
            sentiment_adjustment = +0.10
        else:
            signal_strength = "WEAK"
            sentiment_adjustment = +0.08

        interpretation = (
            f"Selling {price_change_pct*100:.1f}% on low volume "
            f"({volume_change_pct*100:.1f}%) suggests exhaustion. "
            "Potential bottom/reversal signal."
        )

    # Price up, Volume up = CONFIRMED RALLY (bullish)
    elif price_change_pct > min_price_move and volume_change_pct > min_volume_move:
        divergence_type = "CONFIRMED_RALLY"

        # Stronger signal = more volume confirmation
        if price_magnitude > 0.05 and volume_magnitude > 1.0:  # >5% price, >100% vol
            signal_strength = "STRONG"
            sentiment_adjustment = +0.15
        elif price_magnitude > 0.03 and volume_magnitude > 0.50:  # >3% price, >50% vol
            signal_strength = "MODERATE"
            sentiment_adjustment = +0.12
        else:
            signal_strength = "WEAK"
            sentiment_adjustment = +0.10

        interpretation = (
            f"Strong buying pressure confirmed: price +{price_change_pct*100:.1f}% "
            f"on high volume (+{volume_change_pct*100:.1f}%). "
            "Bullish momentum signal."
        )

    # Price down, Volume up = CONFIRMED SELLOFF (bearish)
    elif price_change_pct < -min_price_move and volume_change_pct > min_volume_move:
        divergence_type = "CONFIRMED_SELLOFF"

        # Stronger signal = more volume on selloff
        if price_magnitude > 0.05 and volume_magnitude > 1.0:  # >5% drop, >100% vol
            signal_strength = "STRONG"
            sentiment_adjustment = -0.15
        elif price_magnitude > 0.03 and volume_magnitude > 0.50:  # >3% drop, >50% vol
            signal_strength = "MODERATE"
            sentiment_adjustment = -0.12
        else:
            signal_strength = "WEAK"
            sentiment_adjustment = -0.10

        interpretation = (
            f"Heavy selling pressure: price {price_change_pct*100:.1f}% "
            f"on high volume (+{volume_change_pct*100:.1f}%). "
            "Confirmed breakdown signal."
        )

    else:
        # No clear divergence pattern
        return None

    # Log divergence detection
    log.info(
        "divergence_detected ticker=%s type=%s strength=%s "
        "price_change=%.2f%% volume_change=%.2f%% adjustment=%.3f",
        ticker,
        divergence_type,
        signal_strength,
        price_change_pct * 100,
        volume_change_pct * 100,
        sentiment_adjustment,
    )

    return {
        "divergence_type": divergence_type,
        "sentiment_adjustment": sentiment_adjustment,
        "signal_strength": signal_strength,
        "price_change": round(price_change_pct, 4),
        "volume_change": round(volume_change_pct, 4),
        "interpretation": interpretation,
    }


def calculate_price_change(ticker: str) -> Optional[float]:
    """
    Calculate price change percentage (today vs yesterday).

    Args:
        ticker: Stock ticker symbol

    Returns:
        Price change percentage (0.05 = +5%), or None if unavailable
    """
    try:
        import yfinance as yf

        ticker_obj = yf.Ticker(ticker)

        # Get last 2 days of price data
        hist = ticker_obj.history(period="2d", interval="1d")

        if hist is None or hist.empty or len(hist) < 2:
            log.debug("price_change_insufficient_data ticker=%s", ticker)
            return None

        if "Close" not in hist.columns:
            log.debug("price_change_no_close_column ticker=%s", ticker)
            return None

        # Calculate price change
        current_price = float(hist["Close"].iloc[-1])
        previous_price = float(hist["Close"].iloc[-2])

        if previous_price == 0:
            return None

        price_change_pct = (current_price - previous_price) / previous_price

        log.debug(
            "price_change_calculated ticker=%s current=%.4f prev=%.4f change=%.2f%%",
            ticker,
            current_price,
            previous_price,
            price_change_pct * 100,
        )

        return price_change_pct

    except Exception as e:
        log.debug(
            "price_change_calculation_failed ticker=%s err=%s",
            ticker,
            str(e.__class__.__name__),
        )
        return None


def calculate_volume_change_from_rvol(rvol_data: Dict) -> Optional[float]:
    """
    Calculate volume change percentage from RVol data.

    Since RVol = current_volume / avg_volume, we can derive:
    volume_change_pct = (rvol - 1.0)

    Args:
        rvol_data: RVol calculation results from calculate_rvol_intraday()

    Returns:
        Volume change percentage (-0.30 = -30%), or None if unavailable
    """
    if not rvol_data:
        return None

    rvol = rvol_data.get("rvol")
    if rvol is None:
        return None

    # RVol = 1.5 means 50% more volume than average = +0.50
    # RVol = 0.7 means 30% less volume than average = -0.30
    volume_change_pct = rvol - 1.0

    return volume_change_pct


# Public API
__all__ = [
    "detect_divergence",
    "calculate_price_change",
    "calculate_volume_change_from_rvol",
]
