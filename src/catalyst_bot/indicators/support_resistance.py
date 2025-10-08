"""
support_resistance.py
=====================

Automatic support and resistance level detection.

Support and resistance are price levels where the price tends to stop and reverse.
Support is a price level where demand is strong enough to prevent further decline.
Resistance is a price level where selling is strong enough to prevent further rise.

This module implements an algorithm to automatically detect these levels based on:
1. Local peaks and troughs (turning points)
2. Clustering of nearby levels
3. Volume confirmation
4. Recency weighting
5. Touch count (how many times price tested the level)

The algorithm identifies the strongest levels that are most likely to act as
support or resistance in the future.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np


def detect_support_resistance(
    prices: List[float],
    volumes: Optional[List[float]] = None,
    sensitivity: float = 0.02,
    min_touches: int = 2,
    max_levels: int = 5,
    lookback: int = 50,
    window: int = 2,
) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    """Detect support and resistance levels from price and volume data.

    Algorithm:
    1. Find local peaks (resistance candidates) and troughs (support candidates)
    2. Cluster nearby levels within sensitivity threshold
    3. Weight by volume at those price levels
    4. Filter to levels with minimum touch count
    5. Return top max_levels strongest levels

    Parameters
    ----------
    prices : List[float]
        List of prices (typically closing prices)
    volumes : Optional[List[float]], optional
        List of volume data for strength weighting. If None, uses equal weights.
    sensitivity : float, optional
        Clustering threshold as a percentage (0.02 = 2%), by default 0.02
    min_touches : int, optional
        Minimum number of touches required for a valid level, by default 2
    max_levels : int, optional
        Maximum number of levels to return for each (support/resistance), by default 5
    lookback : int, optional
        Number of recent periods to analyze, by default 50
    window : int, optional
        Number of bars on each side to check for extrema, by default 2

    Returns
    -------
    Tuple[List[Dict[str, float]], List[Dict[str, float]]]
        (support_levels, resistance_levels)
        Each level is a dict with keys:
        - 'price': The price level
        - 'strength': Strength score (0-100)
        - 'touches': Number of times price tested this level
        - 'last_touch_ago': Bars since last touch

    Examples
    --------
    >>> prices = [100, 105, 103, 108, 107, 105, 104, 106, 103, 102, 104]
    >>> volumes = [1000] * len(prices)
    >>> support, resistance = detect_support_resistance(prices, volumes, sensitivity=0.03)
    >>> len(support) > 0
    True
    >>> len(resistance) > 0
    True
    """
    if not prices:
        return [], []

    # Use only recent data
    recent_prices = prices[-lookback:] if len(prices) > lookback else prices
    recent_volumes = (
        volumes[-lookback:] if volumes and len(volumes) > lookback else volumes
    )

    if len(recent_prices) < 3:
        return [], []

    prices_arr = np.array(recent_prices, dtype=float)

    # Use volumes if provided, otherwise equal weight
    if recent_volumes and len(recent_volumes) == len(recent_prices):
        volumes_arr = np.array(recent_volumes, dtype=float)
    else:
        volumes_arr = np.ones(len(recent_prices))

    # Find local peaks (resistance candidates)
    resistance_candidates = _find_local_extrema(
        prices_arr, find_max=True, window=window
    )

    # Find local troughs (support candidates)
    support_candidates = _find_local_extrema(prices_arr, find_max=False, window=window)

    # Cluster and rank support levels
    support_levels = _cluster_and_rank_levels(
        support_candidates,
        prices_arr,
        volumes_arr,
        sensitivity=sensitivity,
        min_touches=min_touches,
        max_levels=max_levels,
    )

    # Cluster and rank resistance levels
    resistance_levels = _cluster_and_rank_levels(
        resistance_candidates,
        prices_arr,
        volumes_arr,
        sensitivity=sensitivity,
        min_touches=min_touches,
        max_levels=max_levels,
    )

    return support_levels, resistance_levels


def _find_local_extrema(
    prices: np.ndarray, find_max: bool = True, window: int = 3
) -> List[Tuple[int, float]]:
    """Find local maxima or minima in price series.

    Parameters
    ----------
    prices : np.ndarray
        Array of prices
    find_max : bool, optional
        If True, find maxima; if False, find minima, by default True
    window : int, optional
        Number of bars on each side to check, by default 3

    Returns
    -------
    List[Tuple[int, float]]
        List of (index, price) tuples for extrema
    """
    extrema = []
    n = len(prices)

    for i in range(window, n - window):
        is_extrema = True

        if find_max:
            # Check if this is a local maximum
            for j in range(1, window + 1):
                if prices[i] < prices[i - j] or prices[i] < prices[i + j]:
                    is_extrema = False
                    break
        else:
            # Check if this is a local minimum
            for j in range(1, window + 1):
                if prices[i] > prices[i - j] or prices[i] > prices[i + j]:
                    is_extrema = False
                    break

        if is_extrema:
            extrema.append((i, float(prices[i])))

    return extrema


def _cluster_and_rank_levels(
    candidates: List[Tuple[int, float]],
    prices: np.ndarray,
    volumes: np.ndarray,
    sensitivity: float,
    min_touches: int,
    max_levels: int,
) -> List[Dict[str, float]]:
    """Cluster nearby price levels and rank by strength.

    Parameters
    ----------
    candidates : List[Tuple[int, float]]
        List of (index, price) tuples
    prices : np.ndarray
        Full price array
    volumes : np.ndarray
        Full volume array
    sensitivity : float
        Clustering threshold as percentage
    min_touches : int
        Minimum touches to be considered valid
    max_levels : int
        Maximum number of levels to return

    Returns
    -------
    List[Dict[str, float]]
        Ranked list of levels with metadata
    """
    if not candidates:
        return []

    # Cluster nearby levels
    clusters = defaultdict(list)

    for idx, price in candidates:
        # Find which cluster this belongs to
        found_cluster = False

        for cluster_price in list(clusters.keys()):
            # Check if within sensitivity threshold
            if abs(price - cluster_price) / cluster_price <= sensitivity:
                clusters[cluster_price].append((idx, price))
                found_cluster = True
                break

        if not found_cluster:
            # Start new cluster
            clusters[price] = [(idx, price)]

    # Calculate strength for each cluster
    level_scores = []

    for cluster_price, touches in clusters.items():
        if len(touches) < min_touches:
            continue

        # Calculate average price for this cluster
        avg_price = np.mean([p for _, p in touches])

        # Count touches
        touch_count = len(touches)

        # Calculate recency score (more recent = higher score)
        indices = [idx for idx, _ in touches]
        last_touch_idx = max(indices)
        bars_ago = len(prices) - last_touch_idx - 1
        recency_score = 1.0 / (1.0 + bars_ago)  # Decays with time

        # Calculate volume strength at this level
        volume_strength = 0.0
        for idx, _ in touches:
            if idx < len(volumes):
                volume_strength += volumes[idx]

        # Normalize volume strength
        avg_volume = np.mean(volumes) if len(volumes) > 0 else 1.0
        volume_score = (
            volume_strength / (touch_count * avg_volume) if avg_volume > 0 else 1.0
        )
        volume_score = (
            min(volume_score, 3.0) / 3.0
        )  # Cap at 3x average and normalize to 0-1

        # Calculate overall strength (0-100)
        # Formula: weighted combination of touch count, recency, and volume
        touch_weight = 0.5
        recency_weight = 0.3
        volume_weight = 0.2

        # Normalize touch count (assume max meaningful touches is 10)
        touch_score = min(touch_count / 10.0, 1.0)

        strength = (
            touch_score * touch_weight
            + recency_score * recency_weight
            + volume_score * volume_weight
        ) * 100

        level_scores.append(
            {
                "price": round(avg_price, 2),
                "strength": round(strength, 2),
                "touches": touch_count,
                "last_touch_ago": bars_ago,
            }
        )

    # Sort by strength (highest first)
    level_scores.sort(key=lambda x: x["strength"], reverse=True)

    # Return top levels
    return level_scores[:max_levels]


def get_nearest_sr_level(
    current_price: float,
    support_levels: List[Dict[str, float]],
    resistance_levels: List[Dict[str, float]],
) -> Optional[Dict[str, any]]:
    """Find the nearest support or resistance level to current price.

    Parameters
    ----------
    current_price : float
        Current price
    support_levels : List[Dict[str, float]]
        Support levels from detect_support_resistance()
    resistance_levels : List[Dict[str, float]]
        Resistance levels from detect_support_resistance()

    Returns
    -------
    Optional[Dict[str, any]]
        Dictionary with:
        - 'type': 'support' or 'resistance'
        - 'level': The level dict
        - 'distance': Percentage distance to level
        None if no levels available
    """
    all_levels = []

    for level in support_levels:
        distance = abs(current_price - level["price"]) / current_price
        all_levels.append({"type": "support", "level": level, "distance": distance})

    for level in resistance_levels:
        distance = abs(current_price - level["price"]) / current_price
        all_levels.append({"type": "resistance", "level": level, "distance": distance})

    if not all_levels:
        return None

    # Find nearest
    nearest = min(all_levels, key=lambda x: x["distance"])
    return nearest


def is_price_at_level(
    current_price: float, level_price: float, tolerance: float = 0.005
) -> bool:
    """Check if current price is at a support/resistance level.

    Parameters
    ----------
    current_price : float
        Current price
    level_price : float
        The support or resistance level price
    tolerance : float, optional
        Percentage tolerance (0.005 = 0.5%), by default 0.005

    Returns
    -------
    bool
        True if price is within tolerance of the level
    """
    if level_price == 0:
        return False

    distance = abs(current_price - level_price) / level_price
    return distance <= tolerance


def analyze_level_breakout(
    prices: List[float], level_price: float, level_type: str, confirmation_bars: int = 2
) -> Optional[str]:
    """Analyze if a support/resistance level has been broken.

    Parameters
    ----------
    prices : List[float]
        Recent price data
    level_price : float
        The support or resistance level
    level_type : str
        'support' or 'resistance'
    confirmation_bars : int, optional
        Number of bars above/below level required for confirmation, by default 2

    Returns
    -------
    Optional[str]
        'broken' if level clearly broken
        'testing' if price is at the level
        'holding' if level is holding
        None if not enough data
    """
    if len(prices) < confirmation_bars:
        return None

    recent = prices[-confirmation_bars:]

    if level_type == "resistance":
        # Check if broken to the upside
        if all(p > level_price for p in recent):
            return "broken"
        # Check if testing resistance
        elif any(abs(p - level_price) / level_price < 0.01 for p in recent):
            return "testing"
        else:
            return "holding"

    elif level_type == "support":
        # Check if broken to the downside
        if all(p < level_price for p in recent):
            return "broken"
        # Check if testing support
        elif any(abs(p - level_price) / level_price < 0.01 for p in recent):
            return "testing"
        else:
            return "holding"

    return None


__all__ = [
    "detect_support_resistance",
    "get_nearest_sr_level",
    "is_price_at_level",
    "analyze_level_breakout",
]
