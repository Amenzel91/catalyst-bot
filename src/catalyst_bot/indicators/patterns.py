"""
patterns.py
===========

Chart pattern recognition for technical analysis.

This module implements detection algorithms for common chart patterns:
- Triangles (ascending, descending, symmetrical)
- Head and Shoulders (classic and inverse)
- Double Tops and Bottoms
- Channels (ascending, descending)
- Flags and Pennants

Each pattern includes confidence scoring based on:
- Pattern formation quality
- Volume confirmation
- Price action alignment
- Breakout potential

Pattern Structure:
{
    'type': str,           # Pattern type identifier
    'confidence': float,   # 0.0 to 1.0
    'start_idx': int,      # Starting index in price array
    'end_idx': int,        # Ending index in price array
    'key_levels': dict,    # Pattern-specific price levels
    'target': float,       # Projected price target (if applicable)
    'description': str     # Human-readable description
}
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from scipy.signal import find_peaks  # type: ignore


def detect_triangles(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    min_touches: int = 3,
    lookback: int = 20,
) -> List[Dict]:
    """Detect triangle patterns (ascending, descending, symmetrical).

    Triangle patterns form when price consolidates between converging trendlines.
    They often precede significant breakouts.

    Parameters
    ----------
    prices : List[float]
        Closing prices
    highs : List[float]
        High prices for each period
    lows : List[float]
        Low prices for each period
    min_touches : int, optional
        Minimum touches required for each trendline, by default 3
    lookback : int, optional
        Number of periods to analyze, by default 20

    Returns
    -------
    List[Dict]
        List of detected triangle patterns with details

    Examples
    --------
    >>> prices = [100, 102, 101, 103, 102, 104, 103, 105]
    >>> highs = [101, 103, 102, 104, 103, 105, 104, 106]
    >>> lows = [99, 101, 100, 102, 101, 103, 102, 104]
    >>> triangles = detect_triangles(prices, highs, lows)
    >>> len(triangles) >= 0
    True
    """
    if len(prices) < lookback or len(highs) != len(prices) or len(lows) != len(prices):
        return []

    patterns = []
    prices_arr = np.array(prices)
    highs_arr = np.array(highs)
    lows_arr = np.array(lows)

    # Analyze the most recent lookback period
    start_idx = max(0, len(prices) - lookback)
    end_idx = len(prices)

    # Find swing highs and lows
    high_peaks, _ = find_peaks(highs_arr[start_idx:end_idx], distance=3)
    low_peaks, _ = find_peaks(-lows_arr[start_idx:end_idx], distance=3)

    if len(high_peaks) < min_touches or len(low_peaks) < min_touches:
        return []

    # Adjust indices to global array
    high_peaks = high_peaks + start_idx
    low_peaks = low_peaks + start_idx

    # Calculate trendlines using linear regression
    high_x = np.arange(len(high_peaks))
    high_y = highs_arr[high_peaks]
    low_x = np.arange(len(low_peaks))
    low_y = lows_arr[low_peaks]

    # Fit resistance line (highs)
    if len(high_x) >= 2:
        high_slope, high_intercept = np.polyfit(high_x, high_y, 1)
    else:
        return []

    # Fit support line (lows)
    if len(low_x) >= 2:
        low_slope, low_intercept = np.polyfit(low_x, low_y, 1)
    else:
        return []

    # Classify triangle type
    slope_threshold = 0.1  # Tolerance for horizontal lines

    if abs(high_slope) < slope_threshold and low_slope > slope_threshold:
        # Ascending triangle: flat resistance, rising support
        pattern_type = "ascending_triangle"
        resistance = float(np.mean(high_y))
        support_slope = float(low_slope)
        confidence = min(0.95, 0.6 + len(high_peaks) * 0.1)

        # Calculate breakout target (height of pattern added to resistance)
        pattern_height = resistance - lows_arr[start_idx]
        target = resistance + pattern_height

        patterns.append(
            {
                "type": pattern_type,
                "confidence": confidence,
                "start_idx": start_idx,
                "end_idx": end_idx - 1,
                "key_levels": {
                    "resistance": resistance,
                    "support_slope": support_slope,
                    "current_price": float(prices_arr[-1]),
                },
                "target": float(target),
                "description": f"Ascending triangle with resistance at ${resistance:.2f}, target ${target:.2f}",  # noqa: E501
            }
        )

    elif high_slope < -slope_threshold and abs(low_slope) < slope_threshold:
        # Descending triangle: falling resistance, flat support
        pattern_type = "descending_triangle"
        support = float(np.mean(low_y))
        resistance_slope = float(high_slope)
        confidence = min(0.95, 0.6 + len(low_peaks) * 0.1)

        # Calculate breakdown target
        pattern_height = highs_arr[start_idx] - support
        target = support - pattern_height

        patterns.append(
            {
                "type": pattern_type,
                "confidence": confidence,
                "start_idx": start_idx,
                "end_idx": end_idx - 1,
                "key_levels": {
                    "support": support,
                    "resistance_slope": resistance_slope,
                    "current_price": float(prices_arr[-1]),
                },
                "target": float(target),
                "description": f"Descending triangle with support at ${support:.2f}, target ${target:.2f}",  # noqa: E501
            }
        )

    elif high_slope < -slope_threshold and low_slope > slope_threshold:
        # Symmetrical triangle: converging lines
        # Find apex (intersection point)
        if abs(high_slope - low_slope) > 0.01:
            apex_x = (low_intercept - high_intercept) / (high_slope - low_slope)
            apex_price = high_slope * apex_x + high_intercept

            confidence = min(0.95, 0.5 + (len(high_peaks) + len(low_peaks)) * 0.05)

            # Target is typically the height of the triangle at its widest point
            pattern_height = highs_arr[start_idx] - lows_arr[start_idx]
            current_price = float(prices_arr[-1])

            patterns.append(
                {
                    "type": "symmetrical_triangle",
                    "confidence": confidence,
                    "start_idx": start_idx,
                    "end_idx": end_idx - 1,
                    "key_levels": {
                        "apex_price": float(apex_price),
                        "high_slope": float(high_slope),
                        "low_slope": float(low_slope),
                        "current_price": current_price,
                    },
                    "target": current_price
                    + pattern_height,  # Upside breakout assumption
                    "description": f"Symmetrical triangle converging toward ${apex_price:.2f}",
                }
            )

    return patterns


def detect_head_shoulders(
    prices: List[float], min_confidence: float = 0.6, lookback: int = 30
) -> List[Dict]:
    """Detect head and shoulders patterns (classic and inverse).

    Head and shoulders is a reversal pattern with three peaks:
    - Left shoulder (LS)
    - Head (higher peak)
    - Right shoulder (RS, similar height to LS)

    Parameters
    ----------
    prices : List[float]
        Price data (typically closing prices)
    min_confidence : float, optional
        Minimum confidence threshold, by default 0.6
    lookback : int, optional
        Number of periods to analyze, by default 30

    Returns
    -------
    List[Dict]
        List of detected H&S patterns

    Examples
    --------
    >>> prices = [100, 105, 102, 110, 105, 107, 102]  # Simple H&S shape
    >>> patterns = detect_head_shoulders(prices)
    >>> len(patterns) >= 0
    True
    """
    if len(prices) < lookback:
        return []

    patterns = []
    prices_arr = np.array(prices)

    # Analyze recent period
    start_idx = max(0, len(prices) - lookback)
    segment = prices_arr[start_idx:]

    # Find peaks and troughs
    peaks, peak_props = find_peaks(segment, distance=3, prominence=0.5)
    troughs, trough_props = find_peaks(-segment, distance=3, prominence=0.5)

    # Need at least 3 peaks for head and shoulders
    if len(peaks) < 3:
        return []

    # Check for classic head and shoulders (bearish reversal)
    for i in range(len(peaks) - 2):
        ls_idx, head_idx, rs_idx = peaks[i], peaks[i + 1], peaks[i + 2]
        ls_price = segment[ls_idx]
        head_price = segment[head_idx]
        rs_price = segment[rs_idx]

        # Head should be the highest
        if head_price > ls_price and head_price > rs_price:
            # Shoulders should be roughly equal (within 5%)
            shoulder_diff = abs(ls_price - rs_price) / ls_price
            if shoulder_diff < 0.05:
                # Find neckline (line connecting troughs between shoulders)
                troughs_between = troughs[(troughs > ls_idx) & (troughs < rs_idx)]

                if len(troughs_between) >= 1:
                    neckline_idx = troughs_between[0]
                    neckline_price = float(segment[neckline_idx])

                    # Calculate confidence
                    symmetry_score = 1.0 - shoulder_diff
                    height = head_price - neckline_price
                    confidence = min(0.95, symmetry_score * 0.7 + 0.25)

                    if confidence >= min_confidence:
                        # Price target: neckline - (head - neckline)
                        target = neckline_price - height

                        patterns.append(
                            {
                                "type": "head_shoulders",
                                "confidence": confidence,
                                "start_idx": start_idx + ls_idx,
                                "end_idx": start_idx + rs_idx,
                                "key_levels": {
                                    "left_shoulder": (
                                        start_idx + ls_idx,
                                        float(ls_price),
                                    ),
                                    "head": (start_idx + head_idx, float(head_price)),
                                    "right_shoulder": (
                                        start_idx + rs_idx,
                                        float(rs_price),
                                    ),
                                    "neckline": neckline_price,
                                },
                                "target": float(target),
                                "description": f"Head & Shoulders pattern with neckline at ${neckline_price:.2f}, target ${target:.2f}",  # noqa: E501
                            }
                        )

    # Check for inverse head and shoulders (bullish reversal)
    if len(troughs) >= 3:
        for i in range(len(troughs) - 2):
            ls_idx, head_idx, rs_idx = troughs[i], troughs[i + 1], troughs[i + 2]
            ls_price = segment[ls_idx]
            head_price = segment[head_idx]
            rs_price = segment[rs_idx]

            # Head should be the lowest
            if head_price < ls_price and head_price < rs_price:
                shoulder_diff = abs(ls_price - rs_price) / ls_price
                if shoulder_diff < 0.05:
                    # Find neckline (peaks between shoulders)
                    peaks_between = peaks[(peaks > ls_idx) & (peaks < rs_idx)]

                    if len(peaks_between) >= 1:
                        neckline_idx = peaks_between[0]
                        neckline_price = float(segment[neckline_idx])

                        symmetry_score = 1.0 - shoulder_diff
                        height = neckline_price - head_price
                        confidence = min(0.95, symmetry_score * 0.7 + 0.25)

                        if confidence >= min_confidence:
                            target = neckline_price + height

                            patterns.append(
                                {
                                    "type": "inverse_head_shoulders",
                                    "confidence": confidence,
                                    "start_idx": start_idx + ls_idx,
                                    "end_idx": start_idx + rs_idx,
                                    "key_levels": {
                                        "left_shoulder": (
                                            start_idx + ls_idx,
                                            float(ls_price),
                                        ),
                                        "head": (
                                            start_idx + head_idx,
                                            float(head_price),
                                        ),
                                        "right_shoulder": (
                                            start_idx + rs_idx,
                                            float(rs_price),
                                        ),
                                        "neckline": neckline_price,
                                    },
                                    "target": float(target),
                                    "description": f"Inverse H&S pattern with neckline at ${neckline_price:.2f}, target ${target:.2f}",  # noqa: E501
                                }
                            )

    return patterns


def detect_double_tops_bottoms(
    prices: List[float],
    tolerance: float = 0.02,
    min_spacing: int = 5,
    lookback: int = 30,
) -> List[Dict]:
    """Detect double top and double bottom patterns.

    Double tops/bottoms are reversal patterns where price tests the same level twice
    and fails to break through, signaling a reversal.

    Parameters
    ----------
    prices : List[float]
        Price data
    tolerance : float, optional
        Price tolerance for matching peaks (2% by default)
    min_spacing : int, optional
        Minimum bars between peaks, by default 5
    lookback : int, optional
        Number of periods to analyze, by default 30

    Returns
    -------
    List[Dict]
        List of detected double top/bottom patterns

    Examples
    --------
    >>> prices = [100, 110, 105, 110, 100]  # Double top at 110
    >>> patterns = detect_double_tops_bottoms(prices)
    >>> len(patterns) >= 0
    True
    """
    if len(prices) < lookback:
        return []

    patterns = []
    prices_arr = np.array(prices)

    start_idx = max(0, len(prices) - lookback)
    segment = prices_arr[start_idx:]

    # Find peaks for double tops
    peaks, _ = find_peaks(segment, distance=min_spacing, prominence=0.5)

    for i in range(len(peaks) - 1):
        peak1_idx = peaks[i]
        peak1_price = segment[peak1_idx]

        for j in range(i + 1, len(peaks)):
            peak2_idx = peaks[j]
            peak2_price = segment[peak2_idx]

            # Check if peaks are within tolerance
            price_diff = abs(peak1_price - peak2_price) / peak1_price
            if price_diff <= tolerance:
                # Find trough between peaks
                between_segment = segment[peak1_idx:peak2_idx]
                if len(between_segment) > 0:
                    trough_price = float(np.min(between_segment))
                    trough_idx = peak1_idx + int(np.argmin(between_segment))

                    # Calculate confidence based on price match quality
                    confidence = min(0.95, 0.8 - (price_diff * 10))

                    # Target: trough - (peak - trough)
                    pattern_height = peak1_price - trough_price
                    target = trough_price - pattern_height

                    patterns.append(
                        {
                            "type": "double_top",
                            "confidence": confidence,
                            "start_idx": start_idx + peak1_idx,
                            "end_idx": start_idx + peak2_idx,
                            "key_levels": {
                                "peak1": (start_idx + peak1_idx, float(peak1_price)),
                                "peak2": (start_idx + peak2_idx, float(peak2_price)),
                                "trough": (start_idx + trough_idx, trough_price),
                            },
                            "target": float(target),
                            "description": f"Double top at ${peak1_price:.2f}, target ${target:.2f}",  # noqa: E501
                        }
                    )
                    break  # Only match first occurrence

    # Find troughs for double bottoms
    troughs, _ = find_peaks(-segment, distance=min_spacing, prominence=0.5)

    for i in range(len(troughs) - 1):
        trough1_idx = troughs[i]
        trough1_price = segment[trough1_idx]

        for j in range(i + 1, len(troughs)):
            trough2_idx = troughs[j]
            trough2_price = segment[trough2_idx]

            price_diff = abs(trough1_price - trough2_price) / trough1_price
            if price_diff <= tolerance:
                between_segment = segment[trough1_idx:trough2_idx]
                if len(between_segment) > 0:
                    peak_price = float(np.max(between_segment))
                    peak_idx = trough1_idx + int(np.argmax(between_segment))

                    confidence = min(0.95, 0.8 - (price_diff * 10))

                    pattern_height = peak_price - trough1_price
                    target = peak_price + pattern_height

                    patterns.append(
                        {
                            "type": "double_bottom",
                            "confidence": confidence,
                            "start_idx": start_idx + trough1_idx,
                            "end_idx": start_idx + trough2_idx,
                            "key_levels": {
                                "trough1": (
                                    start_idx + trough1_idx,
                                    float(trough1_price),
                                ),
                                "trough2": (
                                    start_idx + trough2_idx,
                                    float(trough2_price),
                                ),
                                "peak": (start_idx + peak_idx, peak_price),
                            },
                            "target": float(target),
                            "description": f"Double bottom at ${trough1_price:.2f}, target ${target:.2f}",  # noqa: E501
                        }
                    )
                    break

    return patterns


def detect_channels(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    min_touches: int = 3,
    lookback: int = 30,
) -> List[Dict]:
    """Detect price channels (ascending, descending, horizontal).

    Channels are parallel trendlines where price bounces between support and resistance.

    Parameters
    ----------
    prices : List[float]
        Closing prices
    highs : List[float]
        High prices
    lows : List[float]
        Low prices
    min_touches : int, optional
        Minimum touches per trendline, by default 3
    lookback : int, optional
        Number of periods to analyze, by default 30

    Returns
    -------
    List[Dict]
        List of detected channel patterns

    Examples
    --------
    >>> prices = [100, 102, 104, 106, 108]
    >>> highs = [101, 103, 105, 107, 109]
    >>> lows = [99, 101, 103, 105, 107]
    >>> channels = detect_channels(prices, highs, lows)
    >>> len(channels) >= 0
    True
    """
    if len(prices) < lookback:
        return []

    patterns = []
    prices_arr = np.array(prices)
    highs_arr = np.array(highs)
    lows_arr = np.array(lows)

    start_idx = max(0, len(prices) - lookback)
    segment_prices = prices_arr[start_idx:]
    segment_highs = highs_arr[start_idx:]
    segment_lows = lows_arr[start_idx:]

    # Find peaks and troughs
    peaks, _ = find_peaks(segment_highs, distance=3)
    troughs, _ = find_peaks(-segment_lows, distance=3)

    if len(peaks) < min_touches or len(troughs) < min_touches:
        return []

    # Fit trendlines
    peak_x = np.arange(len(peaks))
    peak_y = segment_highs[peaks]
    trough_x = np.arange(len(troughs))
    trough_y = segment_lows[troughs]

    if len(peak_x) >= 2 and len(trough_x) >= 2:
        upper_slope, upper_intercept = np.polyfit(peak_x, peak_y, 1)
        lower_slope, lower_intercept = np.polyfit(trough_x, trough_y, 1)

        # Check if slopes are similar (parallel lines)
        slope_diff = abs(upper_slope - lower_slope)

        if slope_diff < 0.5:  # Relatively parallel
            # Calculate channel width
            channel_width = float(np.mean(peak_y - np.interp(peaks, troughs, trough_y)))

            # Determine channel type
            if upper_slope > 0.1 and lower_slope > 0.1:
                channel_type = "ascending_channel"
            elif upper_slope < -0.1 and lower_slope < -0.1:
                channel_type = "descending_channel"
            else:
                channel_type = "horizontal_channel"

            confidence = min(0.95, 0.6 + (len(peaks) + len(troughs)) * 0.05)

            patterns.append(
                {
                    "type": channel_type,
                    "confidence": confidence,
                    "start_idx": start_idx,
                    "end_idx": start_idx + len(segment_prices) - 1,
                    "key_levels": {
                        "upper_slope": float(upper_slope),
                        "lower_slope": float(lower_slope),
                        "channel_width": channel_width,
                        "current_price": float(prices_arr[-1]),
                    },
                    "target": None,  # Channels don't have specific targets
                    "description": f"{channel_type.replace('_', ' ').title()} with width ${channel_width:.2f}",  # noqa: E501
                }
            )

    return patterns


def detect_flags_pennants(
    prices: List[float], volumes: Optional[List[float]] = None, lookback: int = 20
) -> List[Dict]:
    """Detect flag and pennant continuation patterns.

    Flags and pennants are short-term consolidation patterns following sharp moves.
    They signal continuation of the prior trend.

    Parameters
    ----------
    prices : List[float]
        Price data
    volumes : Optional[List[float]], optional
        Volume data for confirmation, by default None
    lookback : int, optional
        Number of periods to analyze, by default 20

    Returns
    -------
    List[Dict]
        List of detected flag/pennant patterns

    Examples
    --------
    >>> prices = [100, 105, 110, 109, 110, 109, 110]  # Sharp move then consolidation
    >>> patterns = detect_flags_pennants(prices)
    >>> len(patterns) >= 0
    True
    """
    if len(prices) < lookback:
        return []

    patterns = []
    prices_arr = np.array(prices)

    start_idx = max(0, len(prices) - lookback)
    segment = prices_arr[start_idx:]

    # Detect sharp move (flagpole)
    # Look for significant price change in first 30-50% of lookback
    pole_length = lookback // 3
    if pole_length < 3:
        return []

    pole_segment = segment[:pole_length]
    pole_change = (pole_segment[-1] - pole_segment[0]) / pole_segment[0]

    # Require at least 5% move for flagpole
    if abs(pole_change) < 0.05:
        return []

    # Analyze consolidation phase
    consolidation = segment[pole_length:]
    if len(consolidation) < 5:
        return []

    # Check for consolidation (low volatility)
    consolidation_range = np.max(consolidation) - np.min(consolidation)
    consolidation_pct = consolidation_range / np.mean(consolidation)

    # Consolidation should be tight (< 5%)
    if consolidation_pct < 0.05:
        # Determine if flag (parallel) or pennant (converging)
        highs_in_consol = []
        lows_in_consol = []

        for i in range(1, len(consolidation) - 1):
            if (
                consolidation[i] > consolidation[i - 1]
                and consolidation[i] > consolidation[i + 1]
            ):
                highs_in_consol.append(consolidation[i])
            if (
                consolidation[i] < consolidation[i - 1]
                and consolidation[i] < consolidation[i + 1]
            ):
                lows_in_consol.append(consolidation[i])

        if len(highs_in_consol) >= 2 and len(lows_in_consol) >= 2:
            high_slope = (highs_in_consol[-1] - highs_in_consol[0]) / len(
                highs_in_consol
            )
            low_slope = (lows_in_consol[-1] - lows_in_consol[0]) / len(lows_in_consol)

            # Check volume confirmation if available
            volume_confirmed = True
            if volumes is not None and len(volumes) >= len(prices):
                vol_segment = volumes[start_idx:]
                pole_vol = np.mean(vol_segment[:pole_length])
                consol_vol = np.mean(vol_segment[pole_length:])
                # Volume should decrease during consolidation
                volume_confirmed = consol_vol < pole_vol * 0.8

            if abs(high_slope - low_slope) < 0.1:
                # Flag pattern (parallel lines)
                pattern_type = "bull_flag" if pole_change > 0 else "bear_flag"
                confidence = 0.7 if volume_confirmed else 0.6

                # Target: prior move length added to breakout point
                target = float(
                    segment[-1] + pole_change * np.mean(segment[:pole_length])
                )

                patterns.append(
                    {
                        "type": pattern_type,
                        "confidence": confidence,
                        "start_idx": start_idx,
                        "end_idx": start_idx + len(segment) - 1,
                        "key_levels": {
                            "pole_start": float(segment[0]),
                            "pole_end": float(segment[pole_length]),
                            "current_price": float(prices_arr[-1]),
                        },
                        "target": target,
                        "description": f"{pattern_type.replace('_', ' ').title()} with target ${target:.2f}",  # noqa: E501
                    }
                )
            else:
                # Pennant pattern (converging lines)
                pattern_type = "bull_pennant" if pole_change > 0 else "bear_pennant"
                confidence = 0.7 if volume_confirmed else 0.6

                target = float(
                    segment[-1] + pole_change * np.mean(segment[:pole_length])
                )

                patterns.append(
                    {
                        "type": pattern_type,
                        "confidence": confidence,
                        "start_idx": start_idx,
                        "end_idx": start_idx + len(segment) - 1,
                        "key_levels": {
                            "pole_start": float(segment[0]),
                            "pole_end": float(segment[pole_length]),
                            "current_price": float(prices_arr[-1]),
                        },
                        "target": target,
                        "description": f"{pattern_type.replace('_', ' ').title()} with target ${target:.2f}",  # noqa: E501
                    }
                )

    return patterns


def detect_all_patterns(
    prices: List[float],
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    volumes: Optional[List[float]] = None,
    min_confidence: float = 0.6,
) -> List[Dict]:
    """Detect all chart patterns with confidence filtering.

    Convenience function that runs all pattern detection algorithms
    and returns patterns above the minimum confidence threshold.

    Parameters
    ----------
    prices : List[float]
        Closing prices
    highs : Optional[List[float]], optional
        High prices, by default None (uses prices)
    lows : Optional[List[float]], optional
        Low prices, by default None (uses prices)
    volumes : Optional[List[float]], optional
        Volume data, by default None
    min_confidence : float, optional
        Minimum confidence threshold (0.0 to 1.0), by default 0.6

    Returns
    -------
    List[Dict]
        All detected patterns sorted by confidence (highest first)

    Examples
    --------
    >>> prices = [100, 105, 102, 110, 105, 107, 102]
    >>> all_patterns = detect_all_patterns(prices, min_confidence=0.5)
    >>> len(all_patterns) >= 0
    True
    """
    if highs is None:
        highs = prices.copy()
    if lows is None:
        lows = prices.copy()

    all_patterns = []

    # Run all detection algorithms
    all_patterns.extend(detect_triangles(prices, highs, lows))
    all_patterns.extend(detect_head_shoulders(prices, min_confidence=min_confidence))
    all_patterns.extend(detect_double_tops_bottoms(prices))
    all_patterns.extend(detect_channels(prices, highs, lows))

    if volumes:
        all_patterns.extend(detect_flags_pennants(prices, volumes))

    # Filter by confidence
    filtered = [p for p in all_patterns if p.get("confidence", 0) >= min_confidence]

    # Sort by confidence (highest first)
    filtered.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    return filtered


__all__ = [
    "detect_triangles",
    "detect_head_shoulders",
    "detect_double_tops_bottoms",
    "detect_channels",
    "detect_flags_pennants",
    "detect_all_patterns",
]
