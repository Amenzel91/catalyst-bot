"""
volume_profile.py
==================

Volume Profile indicator implementation.

Volume Profile shows the amount of volume traded at different price levels over
a specific time period. It helps identify:
- Value areas (price levels with high trading activity)
- Point of Control (POC) - the price level with the highest volume
- Low volume nodes (price levels with low trading activity - potential breakout zones)
- High volume nodes (price levels with high trading activity - potential support/resistance)

This is different from a regular volume histogram which shows volume over time.
Volume Profile shows volume distributed across price levels.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def calculate_volume_profile(
    prices: List[float],
    volumes: List[float],
    bins: int = 20,
    high: Optional[float] = None,
    low: Optional[float] = None,
) -> Tuple[List[float], List[float]]:
    """Calculate volume profile (volume distribution across price levels).

    Parameters
    ----------
    prices : List[float]
        List of prices (typically closing prices)
    volumes : List[float]
        List of volumes corresponding to each price
    bins : int, optional
        Number of price bins to divide the range into, by default 20
    high : Optional[float], optional
        Highest price for the range. If None, uses max(prices)
    low : Optional[float], optional
        Lowest price for the range. If None, uses min(prices)

    Returns
    -------
    Tuple[List[float], List[float]]
        (price_levels, volume_at_price)
        - price_levels: Center price of each bin
        - volume_at_price: Total volume traded at each price level

    Examples
    --------
    >>> prices = [100, 101, 102, 101, 100, 99, 100, 101, 102, 103]
    >>> volumes = [1000, 1500, 2000, 1800, 1200, 900, 1100, 1600, 2100, 1700]
    >>> price_levels, vol_at_price = calculate_volume_profile(prices, volumes, bins=5)
    >>> len(price_levels) == 5
    True
    >>> len(vol_at_price) == 5
    True
    """
    if not prices or not volumes or len(prices) != len(volumes):
        return [], []

    if len(prices) < bins:
        bins = len(prices)

    prices_arr = np.array(prices, dtype=float)
    volumes_arr = np.array(volumes, dtype=float)

    # Determine price range
    price_high = high if high is not None else float(np.max(prices_arr))
    price_low = low if low is not None else float(np.min(prices_arr))

    if price_high <= price_low:
        return [], []

    # Create price bins
    bin_edges = np.linspace(price_low, price_high, bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Initialize volume array for each bin
    volume_at_price = np.zeros(bins)

    # Distribute volume across price bins
    for price, volume in zip(prices_arr, volumes_arr):
        # Find which bin this price belongs to
        bin_idx = np.digitize(price, bin_edges) - 1

        # Handle edge cases
        if bin_idx < 0:
            bin_idx = 0
        elif bin_idx >= bins:
            bin_idx = bins - 1

        volume_at_price[bin_idx] += volume

    return bin_centers.tolist(), volume_at_price.tolist()


def find_point_of_control(
    price_levels: List[float], volume_at_price: List[float]
) -> Optional[float]:
    """Find the Point of Control (POC) - the price level with highest volume.

    The POC is considered a significant support/resistance level as it represents
    the price where the most trading activity occurred.

    Parameters
    ----------
    price_levels : List[float]
        Price levels from calculate_volume_profile()
    volume_at_price : List[float]
        Volume at each price level

    Returns
    -------
    Optional[float]
        The price level with maximum volume (POC), or None if no data

    Examples
    --------
    >>> price_levels = [100, 101, 102, 103, 104]
    >>> volumes = [1000, 2500, 3000, 2000, 1500]
    >>> poc = find_point_of_control(price_levels, volumes)
    >>> poc == 102
    True
    """
    if (
        not price_levels
        or not volume_at_price
        or len(price_levels) != len(volume_at_price)
    ):
        return None

    max_idx = np.argmax(volume_at_price)
    return float(price_levels[max_idx])


def calculate_value_area(
    price_levels: List[float],
    volume_at_price: List[float],
    value_area_pct: float = 0.70,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Calculate the Value Area (price range containing specified % of volume).

    The Value Area typically contains 70% of the total volume and represents
    the "fair value" range where most trading occurred. It's bounded by the
    Value Area High (VAH) and Value Area Low (VAL).

    Parameters
    ----------
    price_levels : List[float]
        Price levels from calculate_volume_profile()
    volume_at_price : List[float]
        Volume at each price level
    value_area_pct : float, optional
        Percentage of total volume to include (0.70 = 70%), by default 0.70

    Returns
    -------
    Tuple[Optional[float], Optional[float], Optional[float]]
        (value_area_high, point_of_control, value_area_low)
        Returns (None, None, None) if insufficient data

    Examples
    --------
    >>> price_levels = [100, 101, 102, 103, 104]
    >>> volumes = [1000, 2000, 3000, 2500, 1500]
    >>> vah, poc, val = calculate_value_area(price_levels, volumes, value_area_pct=0.70)
    >>> vah > val
    True
    >>> poc == 102
    True
    """
    if (
        not price_levels
        or not volume_at_price
        or len(price_levels) != len(volume_at_price)
    ):
        return None, None, None

    volume_arr = np.array(volume_at_price)
    price_arr = np.array(price_levels)

    # Find POC
    poc_idx = np.argmax(volume_arr)
    poc = float(price_arr[poc_idx])

    # Calculate target volume (value_area_pct of total)
    total_volume = np.sum(volume_arr)
    target_volume = total_volume * value_area_pct

    # Start from POC and expand outward until we capture target volume
    included = {poc_idx}
    current_volume = volume_arr[poc_idx]

    # Expand outward from POC
    while current_volume < target_volume:
        # Find adjacent indices
        below_idx = None
        above_idx = None

        for idx in included:
            if idx > 0 and (idx - 1) not in included:
                below_idx = idx - 1
            if idx < len(volume_arr) - 1 and (idx + 1) not in included:
                above_idx = idx + 1

        if below_idx is None and above_idx is None:
            # No more indices to add
            break

        # Add the adjacent level with higher volume
        below_vol = volume_arr[below_idx] if below_idx is not None else 0
        above_vol = volume_arr[above_idx] if above_idx is not None else 0

        if below_vol >= above_vol and below_idx is not None:
            included.add(below_idx)
            current_volume += below_vol
        elif above_idx is not None:
            included.add(above_idx)
            current_volume += above_vol
        else:
            break

    # Find VAH and VAL
    included_indices = sorted(included)
    if not included_indices:
        return None, None, None

    val_idx = included_indices[0]
    vah_idx = included_indices[-1]

    val = float(price_arr[val_idx])
    vah = float(price_arr[vah_idx])

    return vah, poc, val


def find_volume_nodes(
    price_levels: List[float], volume_at_price: List[float], threshold_pct: float = 0.3
) -> Tuple[List[float], List[float]]:
    """Identify high and low volume nodes.

    High Volume Nodes (HVN) are price levels with significantly above-average volume.
    Low Volume Nodes (LVN) are price levels with significantly below-average volume.

    HVNs often act as support/resistance. LVNs represent areas of price rejection
    and can indicate potential breakout zones.

    Parameters
    ----------
    price_levels : List[float]
        Price levels from calculate_volume_profile()
    volume_at_price : List[float]
        Volume at each price level
    threshold_pct : float, optional
        Percentage threshold for node detection (0.3 = 30%), by default 0.3

    Returns
    -------
    Tuple[List[float], List[float]]
        (high_volume_nodes, low_volume_nodes)
        Lists of price levels representing HVN and LVN

    Examples
    --------
    >>> price_levels = [100, 101, 102, 103, 104]
    >>> volumes = [1000, 500, 3000, 600, 1200]
    >>> hvn, lvn = find_volume_nodes(price_levels, volumes, threshold_pct=0.5)
    >>> 102 in hvn  # High volume at 102
    True
    >>> 101 in lvn or 103 in lvn  # Low volume at 101 or 103
    True
    """
    if (
        not price_levels
        or not volume_at_price
        or len(price_levels) != len(volume_at_price)
    ):
        return [], []

    volume_arr = np.array(volume_at_price)
    price_arr = np.array(price_levels)

    # Calculate average volume
    avg_volume = np.mean(volume_arr)

    # Calculate thresholds
    hvn_threshold = avg_volume * (1 + threshold_pct)
    lvn_threshold = avg_volume * (1 - threshold_pct)

    # Find high and low volume nodes
    hvn_indices = np.where(volume_arr >= hvn_threshold)[0]
    lvn_indices = np.where(volume_arr <= lvn_threshold)[0]

    hvn = price_arr[hvn_indices].tolist()
    lvn = price_arr[lvn_indices].tolist()

    return hvn, lvn


def calculate_volume_weighted_average_price_from_profile(
    price_levels: List[float], volume_at_price: List[float]
) -> Optional[float]:
    """Calculate VWAP from volume profile data.

    This is different from intraday VWAP. This calculates the volume-weighted
    average price across the profiled price levels.

    Parameters
    ----------
    price_levels : List[float]
        Price levels from calculate_volume_profile()
    volume_at_price : List[float]
        Volume at each price level

    Returns
    -------
    Optional[float]
        Volume-weighted average price, or None if no data

    Examples
    --------
    >>> price_levels = [100, 101, 102]
    >>> volumes = [1000, 2000, 1000]
    >>> vwap = calculate_volume_weighted_average_price_from_profile(price_levels, volumes)
    >>> 100 < vwap < 102
    True
    """
    if (
        not price_levels
        or not volume_at_price
        or len(price_levels) != len(volume_at_price)
    ):
        return None

    price_arr = np.array(price_levels)
    volume_arr = np.array(volume_at_price)

    total_volume = np.sum(volume_arr)

    if total_volume == 0:
        return None

    vwap = np.sum(price_arr * volume_arr) / total_volume
    return float(vwap)


def analyze_volume_distribution(volume_at_price: List[float]) -> Dict[str, float]:
    """Analyze the distribution characteristics of the volume profile.

    Parameters
    ----------
    volume_at_price : List[float]
        Volume at each price level

    Returns
    -------
    Dict[str, float]
        Dictionary with:
        - 'concentration': How concentrated the volume is (0-1, higher = more concentrated)
        - 'skewness': Distribution skew (-1 to 1, negative = skewed down, positive = skewed up)
        - 'balance': Balance of volume (0-1, 0.5 = balanced)

    Examples
    --------
    >>> volumes = [1000, 2000, 5000, 2000, 1000]  # Normal distribution
    >>> stats = analyze_volume_distribution(volumes)
    >>> 0 < stats['concentration'] < 1
    True
    """
    if not volume_at_price:
        return {"concentration": 0, "skewness": 0, "balance": 0.5}

    volume_arr = np.array(volume_at_price)
    n = len(volume_arr)

    # Calculate concentration (Herfindahl index)
    total_vol = np.sum(volume_arr)
    if total_vol == 0:
        concentration = 0
    else:
        shares = volume_arr / total_vol
        concentration = float(np.sum(shares**2))

    # Calculate skewness
    if n < 3:
        skewness = 0
    else:
        mean_vol = np.mean(volume_arr)
        std_vol = np.std(volume_arr)
        if std_vol == 0:
            skewness = 0
        else:
            skewness = float(np.mean(((volume_arr - mean_vol) / std_vol) ** 3))
            # Normalize to -1 to 1 range
            skewness = np.clip(skewness / 3, -1, 1)

    # Calculate balance (where is the volume weighted center)
    if total_vol == 0:
        balance = 0.5
    else:
        weights = volume_arr / total_vol
        positions = np.arange(n)
        weighted_center = np.sum(positions * weights)
        balance = float(weighted_center / (n - 1)) if n > 1 else 0.5

    return {
        "concentration": float(concentration),
        "skewness": float(skewness),
        "balance": float(balance),
    }


def generate_horizontal_volume_bars(
    price_levels: List[float], volume_at_price: List[float], normalize: bool = True
) -> List[Dict[str, float]]:
    """Generate horizontal volume bar data for chart overlay.

    Creates data suitable for rendering as horizontal bars on the right
    side of a price chart (WeBull-style volume profile visualization).

    Parameters
    ----------
    price_levels : List[float]
        Price levels from calculate_volume_profile()
    volume_at_price : List[float]
        Volume at each price level
    normalize : bool, optional
        Normalize bars to 0-100 scale, by default True

    Returns
    -------
    List[Dict[str, float]]
        List of dicts with keys: 'price', 'volume', 'normalized_volume'

    Examples
    --------
    >>> price_levels = [100, 101, 102, 103, 104]
    >>> volumes = [1000, 2000, 3000, 2500, 1500]
    >>> bars = generate_horizontal_volume_bars(price_levels, volumes)
    >>> len(bars) == 5
    True
    >>> all('normalized_volume' in bar for bar in bars)
    True
    """
    if (
        not price_levels
        or not volume_at_price
        or len(price_levels) != len(volume_at_price)
    ):
        return []

    volume_arr = np.array(volume_at_price)
    max_volume = np.max(volume_arr) if len(volume_arr) > 0 else 1.0

    bars = []
    for price, volume in zip(price_levels, volume_at_price):
        normalized = (volume / max_volume * 100) if max_volume > 0 else 0
        bars.append(
            {
                "price": float(price),
                "volume": float(volume),
                "normalized_volume": float(normalized),
            }
        )

    return bars


def identify_hvn_lvn(
    price_levels: List[float],
    volume_at_price: List[float],
    hvn_threshold: float = 1.3,
    lvn_threshold: float = 0.7,
) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    """Identify High Volume Nodes (HVN) and Low Volume Nodes (LVN).

    HVNs are price levels with significantly above-average volume.
    LVNs are price levels with significantly below-average volume.

    Parameters
    ----------
    price_levels : List[float]
        Price levels from calculate_volume_profile()
    volume_at_price : List[float]
        Volume at each price level
    hvn_threshold : float, optional
        Multiplier for average volume to qualify as HVN, by default 1.3
    lvn_threshold : float, optional
        Multiplier for average volume to qualify as LVN, by default 0.7

    Returns
    -------
    Tuple[List[Dict[str, float]], List[Dict[str, float]]]
        (hvn_list, lvn_list) where each dict has 'price', 'volume', 'ratio'

    Examples
    --------
    >>> price_levels = [100, 101, 102, 103, 104]
    >>> volumes = [1000, 500, 3000, 600, 1200]
    >>> hvn, lvn = identify_hvn_lvn(price_levels, volumes)
    >>> len(hvn) > 0 or len(lvn) > 0
    True
    """
    if (
        not price_levels
        or not volume_at_price
        or len(price_levels) != len(volume_at_price)
    ):
        return [], []

    volume_arr = np.array(volume_at_price)
    avg_volume = np.mean(volume_arr)

    if avg_volume == 0:
        return [], []

    hvn_list = []
    lvn_list = []

    for price, volume in zip(price_levels, volume_at_price):
        volume_ratio = volume / avg_volume

        if volume_ratio >= hvn_threshold:
            hvn_list.append(
                {
                    "price": float(price),
                    "volume": float(volume),
                    "ratio": float(volume_ratio),
                }
            )
        elif volume_ratio <= lvn_threshold:
            lvn_list.append(
                {
                    "price": float(price),
                    "volume": float(volume),
                    "ratio": float(volume_ratio),
                }
            )

    return hvn_list, lvn_list


def render_volume_profile_data(
    prices: List[float], volumes: List[float], bins: int = 25
) -> Dict[str, Any]:
    """Generate complete volume profile data for chart rendering.

    Convenience function that calculates volume profile and all
    associated metrics (POC, VAH, VAL, HVN, LVN, bars).

    Parameters
    ----------
    prices : List[float]
        Price data
    volumes : List[float]
        Volume data
    bins : int, optional
        Number of price bins, by default 25

    Returns
    -------
    Dict[str, Any]
        Complete volume profile data:
        {
            'price_levels': [...],
            'volume_at_price': [...],
            'poc': float,
            'vah': float,
            'val': float,
            'hvn': [...],
            'lvn': [...],
            'horizontal_bars': [...]
        }

    Examples
    --------
    >>> prices = [100, 102, 101, 103, 105] * 5
    >>> volumes = [1000, 1500, 1200, 1800, 2000] * 5
    >>> vp_data = render_volume_profile_data(prices, volumes)
    >>> 'poc' in vp_data and 'hvn' in vp_data
    True
    """
    # Calculate volume profile
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=bins)

    if not price_levels:
        return {
            "price_levels": [],
            "volume_at_price": [],
            "poc": None,
            "vah": None,
            "val": None,
            "hvn": [],
            "lvn": [],
            "horizontal_bars": [],
        }

    # Calculate key metrics
    poc = find_point_of_control(price_levels, volume_at_price)
    vah, _, val = calculate_value_area(price_levels, volume_at_price)

    # Identify nodes
    hvn, lvn = identify_hvn_lvn(price_levels, volume_at_price)

    # Generate bars
    horizontal_bars = generate_horizontal_volume_bars(price_levels, volume_at_price)

    return {
        "price_levels": price_levels,
        "volume_at_price": volume_at_price,
        "poc": poc,
        "vah": vah,
        "val": val,
        "hvn": hvn,
        "lvn": lvn,
        "horizontal_bars": horizontal_bars,
    }


__all__ = [
    "calculate_volume_profile",
    "find_point_of_control",
    "calculate_value_area",
    "find_volume_nodes",
    "calculate_volume_weighted_average_price_from_profile",
    "analyze_volume_distribution",
    "generate_horizontal_volume_bars",
    "identify_hvn_lvn",
    "render_volume_profile_data",
]
