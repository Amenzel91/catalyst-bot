"""
bollinger.py
============

Bollinger Bands indicator implementation.

Bollinger Bands are volatility bands placed above and below a moving average.
Volatility is based on the standard deviation, which changes as volatility
increases and decreases. The bands automatically widen when volatility increases
and narrow when volatility decreases.

Formula:
    Middle Band = 20-period Simple Moving Average (SMA)
    Upper Band = Middle Band + (2 × 20-period standard deviation)
    Lower Band = Middle Band - (2 × 20-period standard deviation)

The default parameters (20 periods, 2 standard deviations) are the most commonly
used settings, developed by John Bollinger.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


def calculate_bollinger_bands(
    prices: List[float], period: int = 20, std_dev: float = 2.0
) -> Tuple[List[float], List[float], List[float]]:
    """Calculate Bollinger Bands for a price series.

    Parameters
    ----------
    prices : List[float]
        List of closing prices
    period : int, optional
        Period for the moving average and standard deviation, by default 20
    std_dev : float, optional
        Number of standard deviations for the bands, by default 2.0

    Returns
    -------
    Tuple[List[float], List[float], List[float]]
        Three lists: (upper_band, middle_band, lower_band)
        For indices where there is insufficient data, returns NaN

    Examples
    --------
    >>> prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109]
    >>> upper, middle, lower = calculate_bollinger_bands(prices, period=5, std_dev=2.0)
    >>> len(upper) == len(prices)
    True
    >>> all(upper[i] >= middle[i] >= lower[i] for i in range(5, len(prices)))
    True
    """
    if not prices or len(prices) < period:
        # Return empty lists if insufficient data
        return [], [], []

    prices_arr = np.array(prices, dtype=float)
    n = len(prices_arr)

    # Initialize output arrays with NaN
    upper_band = np.full(n, np.nan)
    middle_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)

    # Calculate for each position starting from 'period'
    for i in range(period - 1, n):
        # Get the window of prices
        window = prices_arr[i - period + 1 : i + 1]

        # Calculate SMA (middle band)
        sma = np.mean(window)

        # Calculate standard deviation
        std = np.std(window, ddof=0)  # Population std dev

        # Calculate bands
        middle_band[i] = sma
        upper_band[i] = sma + (std_dev * std)
        lower_band[i] = sma - (std_dev * std)

    return upper_band.tolist(), middle_band.tolist(), lower_band.tolist()


def get_bollinger_position(
    current_price: float, upper: float, middle: float, lower: float
) -> Optional[str]:
    """Determine the position of current price relative to Bollinger Bands.

    Parameters
    ----------
    current_price : float
        Current price to evaluate
    upper : float
        Upper Bollinger Band value
    middle : float
        Middle Bollinger Band value (SMA)
    lower : float
        Lower Bollinger Band value

    Returns
    -------
    Optional[str]
        Position description:
        - "Above Upper Band" - Price is above the upper band (potentially overbought)
        - "Near Upper Band" - Price is within 5% of upper band
        - "Above Middle" - Price is between middle and upper bands
        - "At Middle" - Price is near the middle band
        - "Below Middle" - Price is between middle and lower bands
        - "Near Lower Band" - Price is within 5% of lower band
        - "Below Lower Band" - Price is below the lower band (potentially oversold)
        None if any value is NaN
    """
    if np.isnan(upper) or np.isnan(middle) or np.isnan(lower):
        return None

    band_width = upper - lower
    threshold = band_width * 0.05  # 5% threshold

    if current_price > upper:
        return "Above Upper Band"
    elif current_price >= upper - threshold:
        return "Near Upper Band"
    elif current_price > middle + threshold:
        return "Above Middle"
    elif abs(current_price - middle) <= threshold:
        return "At Middle"
    elif current_price > lower + threshold:
        return "Below Middle"
    elif current_price >= lower:
        return "Near Lower Band"
    else:
        return "Below Lower Band"


def calculate_bandwidth(upper: float, middle: float, lower: float) -> Optional[float]:
    """Calculate Bollinger Band Width as a percentage of the middle band.

    BandWidth is a measure of volatility. When bands are narrow (low volatility),
    it often precedes a sharp price move. Wide bands indicate high volatility.

    Parameters
    ----------
    upper : float
        Upper Bollinger Band value
    middle : float
        Middle Bollinger Band value
    lower : float
        Lower Bollinger Band value

    Returns
    -------
    Optional[float]
        BandWidth as a percentage, or None if middle is 0 or any value is NaN
    """
    if np.isnan(upper) or np.isnan(middle) or np.isnan(lower) or middle == 0:
        return None

    bandwidth = ((upper - lower) / middle) * 100
    return bandwidth


def detect_bollinger_squeeze(
    bandwidths: List[float], lookback: int = 20, threshold_percentile: float = 10
) -> bool:
    """Detect a Bollinger Band squeeze (low volatility period).

    A squeeze occurs when bandwidth is at or near its lowest level over the
    lookback period, suggesting an imminent volatility expansion.

    Parameters
    ----------
    bandwidths : List[float]
        List of bandwidth values (from calculate_bandwidth)
    lookback : int, optional
        Number of periods to look back, by default 20
    threshold_percentile : float, optional
        Percentile threshold for squeeze detection (0-100), by default 10

    Returns
    -------
    bool
        True if current bandwidth is in the lowest threshold_percentile over
        the lookback period, False otherwise
    """
    if len(bandwidths) < lookback:
        return False

    # Get recent bandwidths
    recent = bandwidths[-lookback:]

    # Filter out NaN values
    valid = [bw for bw in recent if not np.isnan(bw)]

    if not valid:
        return False

    # Calculate the threshold
    threshold_value = np.percentile(valid, threshold_percentile)

    # Check if current bandwidth is at or below threshold
    current = bandwidths[-1]
    if np.isnan(current):
        return False

    return current <= threshold_value


__all__ = [
    "calculate_bollinger_bands",
    "get_bollinger_position",
    "calculate_bandwidth",
    "detect_bollinger_squeeze",
]
