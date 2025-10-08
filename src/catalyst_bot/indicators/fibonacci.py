"""
fibonacci.py
=============

Fibonacci Retracement levels indicator.

Fibonacci retracements are horizontal lines that indicate where support and
resistance are likely to occur. They are based on Fibonacci numbers and each
level is associated with a percentage representing how much of a prior move
the price has retraced.

The most common Fibonacci retracement levels are:
- 0% (swing low)
- 23.6%
- 38.2% (shallow retracement)
- 50% (not a Fibonacci ratio, but widely used)
- 61.8% (golden ratio - most significant level)
- 78.6%
- 100% (swing high)

These levels are used by traders to identify potential reversal points.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

# Standard Fibonacci ratios
FIBONACCI_RATIOS = {
    "0%": 0.0,
    "23.6%": 0.236,
    "38.2%": 0.382,
    "50%": 0.5,
    "61.8%": 0.618,
    "78.6%": 0.786,
    "100%": 1.0,
}


def calculate_fibonacci_levels(
    high: float, low: float, ratios: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """Calculate Fibonacci retracement levels from a swing high and low.

    Formula: level = low + (high - low) * ratio

    Parameters
    ----------
    high : float
        The swing high price
    low : float
        The swing low price
    ratios : Optional[Dict[str, float]], optional
        Custom Fibonacci ratios to use. If None, uses standard ratios.
        Keys are labels (e.g., "61.8%"), values are ratios (e.g., 0.618)

    Returns
    -------
    Dict[str, float]
        Dictionary mapping level names to price levels
        Example: {"0%": 100.0, "23.6%": 111.8, "38.2%": 119.1, ...}

    Examples
    --------
    >>> levels = calculate_fibonacci_levels(150.0, 100.0)
    >>> levels["50%"]
    125.0
    >>> levels["61.8%"]
    130.9
    """
    if ratios is None:
        ratios = FIBONACCI_RATIOS

    if high <= low:
        raise ValueError(f"High ({high}) must be greater than low ({low})")

    range_val = high - low
    levels = {}

    for name, ratio in ratios.items():
        # Calculate retracement level from low (uptrend convention)
        level = low + (range_val * ratio)
        levels[name] = round(level, 2)

    return levels


def find_swing_points(
    prices: List[float], lookback: int = 20, min_bars: int = 5
) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    """Automatically detect swing high and swing low from price data.

    A swing high is a peak where the price is higher than surrounding prices.
    A swing low is a trough where the price is lower than surrounding prices.

    Parameters
    ----------
    prices : List[float]
        List of prices (typically closing prices)
    lookback : int, optional
        Number of periods to look back for swing detection, by default 20
    min_bars : int, optional
        Minimum number of bars on each side of a swing point, by default 5

    Returns
    -------
    Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]
        (swing_high, swing_low, high_index, low_index)
        Returns (None, None, None, None) if insufficient data or no swings found

    Examples
    --------
    >>> prices = [100, 105, 110, 108, 106, 104, 107, 112, 115, 113]
    >>> high, low, h_idx, l_idx = find_swing_points(prices, lookback=10, min_bars=2)
    >>> high > low
    True
    """
    if not prices or len(prices) < lookback or len(prices) < min_bars * 2 + 1:
        return None, None, None, None

    prices_arr = np.array(prices, dtype=float)

    # Use the most recent 'lookback' periods
    recent_prices = prices_arr[-lookback:]

    # Find local maxima (swing highs)
    swing_highs = []
    for i in range(min_bars, len(recent_prices) - min_bars):
        is_high = True
        # Check if this is higher than surrounding bars
        for j in range(1, min_bars + 1):
            if (
                recent_prices[i] <= recent_prices[i - j]
                or recent_prices[i] <= recent_prices[i + j]
            ):
                is_high = False
                break
        if is_high:
            swing_highs.append((recent_prices[i], i))

    # Find local minima (swing lows)
    swing_lows = []
    for i in range(min_bars, len(recent_prices) - min_bars):
        is_low = True
        # Check if this is lower than surrounding bars
        for j in range(1, min_bars + 1):
            if (
                recent_prices[i] >= recent_prices[i - j]
                or recent_prices[i] >= recent_prices[i + j]
            ):
                is_low = False
                break
        if is_low:
            swing_lows.append((recent_prices[i], i))

    # If no swings found, use overall high/low
    if not swing_highs or not swing_lows:
        high_idx = int(np.argmax(recent_prices))
        low_idx = int(np.argmin(recent_prices))
        swing_high = float(recent_prices[high_idx])
        swing_low = float(recent_prices[low_idx])

        # Adjust indices to absolute position
        abs_high_idx = len(prices_arr) - lookback + high_idx
        abs_low_idx = len(prices_arr) - lookback + low_idx

        return swing_high, swing_low, abs_high_idx, abs_low_idx

    # Take the most recent swing high and low
    most_recent_high = max(swing_highs, key=lambda x: x[1])
    most_recent_low = min(swing_lows, key=lambda x: x[1])

    swing_high = float(most_recent_high[0])
    swing_low = float(most_recent_low[0])

    # Adjust indices to absolute position in original array
    abs_high_idx = len(prices_arr) - lookback + most_recent_high[1]
    abs_low_idx = len(prices_arr) - lookback + most_recent_low[1]

    return swing_high, swing_low, abs_high_idx, abs_low_idx


def get_nearest_fibonacci_level(
    current_price: float, fib_levels: Dict[str, float], tolerance: float = 0.005
) -> Optional[str]:
    """Find the nearest Fibonacci level to the current price.

    Parameters
    ----------
    current_price : float
        The current price to check
    fib_levels : Dict[str, float]
        Fibonacci levels from calculate_fibonacci_levels()
    tolerance : float, optional
        Percentage tolerance for "at level" detection (0.005 = 0.5%), by default 0.005

    Returns
    -------
    Optional[str]
        The name of the nearest Fibonacci level if within tolerance, else None

    Examples
    --------
    >>> levels = {"50%": 125.0, "61.8%": 119.1, "78.6%": 110.7}
    >>> get_nearest_fibonacci_level(125.5, levels, tolerance=0.01)
    '50%'
    """
    if not fib_levels:
        return None

    min_distance = float("inf")
    nearest_level = None

    for name, level in fib_levels.items():
        # Calculate percentage distance
        distance = abs(current_price - level) / level if level != 0 else float("inf")

        if distance < min_distance:
            min_distance = distance
            nearest_level = name

    # Only return if within tolerance
    if min_distance <= tolerance:
        return nearest_level

    return None


def calculate_fibonacci_extensions(
    high: float, low: float, custom_ratios: Optional[List[float]] = None
) -> Dict[str, float]:
    """Calculate Fibonacci extension levels beyond the swing range.

    Extension levels are used for profit targets. Common levels are 127.2%, 161.8%, 200%, 261.8%.

    Parameters
    ----------
    high : float
        The swing high price
    low : float
        The swing low price
    custom_ratios : Optional[List[float]], optional
        Custom extension ratios (e.g., [1.272, 1.618, 2.0, 2.618])
        If None, uses standard extension levels

    Returns
    -------
    Dict[str, float]
        Dictionary mapping extension level names to price levels

    Examples
    --------
    >>> exts = calculate_fibonacci_extensions(150.0, 100.0)
    >>> exts["161.8%"] > 150.0  # Extensions go beyond the high
    True
    """
    if custom_ratios is None:
        custom_ratios = [1.272, 1.618, 2.0, 2.618]

    if high <= low:
        raise ValueError(f"High ({high}) must be greater than low ({low})")

    range_val = high - low
    extensions = {}

    for ratio in custom_ratios:
        # Extension levels extend beyond the high
        level = high + (range_val * (ratio - 1.0))
        label = f"{ratio * 100:.1f}%"
        extensions[label] = round(level, 2)

    return extensions


def calculate_fibonacci_fan_lines(
    high: float, low: float, high_index: int, low_index: int, num_periods: int = 50
) -> Dict[str, List[Tuple[int, float]]]:
    """Calculate Fibonacci fan lines (trend lines from swing low through Fib levels).

    Fan lines are diagonal lines that can act as support/resistance. They are drawn
    from a swing low (or high) through key Fibonacci retracement levels.

    Parameters
    ----------
    high : float
        The swing high price
    low : float
        The swing low price
    high_index : int
        Index of the swing high
    low_index : int
        Index of the swing low
    num_periods : int, optional
        Number of periods forward to project the fan lines, by default 50

    Returns
    -------
    Dict[str, List[Tuple[int, float]]]
        Dictionary mapping Fibonacci levels to lists of (index, price) tuples
        representing the fan line coordinates

    Examples
    --------
    >>> fan = calculate_fibonacci_fan_lines(150.0, 100.0, 20, 10, num_periods=30)
    >>> "38.2%" in fan
    True
    """
    if high <= low:
        raise ValueError(f"High ({high}) must be greater than low ({low})")

    # Determine if trend is up (low before high) or down (high before low)
    trend_up = low_index < high_index

    # Calculate key Fibonacci levels
    range_val = high - low
    key_ratios = [0.382, 0.5, 0.618]

    fan_lines = {}

    for ratio in key_ratios:
        label = f"{ratio * 100:.1f}%"
        fib_level = high - (range_val * ratio)

        # Create line from swing point through Fibonacci level
        if trend_up:
            # Line from low through Fib level
            x1, y1 = low_index, low
            x2, y2 = high_index, fib_level
        else:
            # Line from high through Fib level
            x1, y1 = high_index, high
            x2, y2 = low_index, fib_level

        # Calculate slope
        if x2 != x1:
            slope = (y2 - y1) / (x2 - x1)
        else:
            slope = 0

        # Project line forward
        line_points = []
        start_idx = max(x1, x2)

        for i in range(num_periods):
            idx = start_idx + i
            price = y2 + slope * (idx - x2)
            line_points.append((idx, round(price, 2)))

        fan_lines[label] = line_points

    return fan_lines


__all__ = [
    "FIBONACCI_RATIOS",
    "calculate_fibonacci_levels",
    "find_swing_points",
    "get_nearest_fibonacci_level",
    "calculate_fibonacci_extensions",
    "calculate_fibonacci_fan_lines",
]
