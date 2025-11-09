"""
chart_indicators_integration.py
================================

Integration layer between advanced indicators and QuickChart chart generation.

This module provides functions to enhance Chart.js configurations with
advanced technical indicators like Bollinger Bands, Fibonacci levels,
Support/Resistance, and Volume Profile.

Each function takes a base Chart.js config and returns an enhanced config
with the requested indicator added as annotations and/or datasets.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    from .indicators import (
        cache_indicator,
        calculate_bollinger_bands,
        calculate_fibonacci_levels,
        calculate_value_area,
        calculate_volume_profile,
        detect_support_resistance,
        find_point_of_control,
        find_swing_points,
        get_cached_indicator,
    )
    from .logging_utils import get_logger
except ImportError:
    # Fallback for testing
    def get_logger(x):
        return None


log = get_logger("chart_indicators") if get_logger else None


def add_bollinger_bands_to_config(
    config: Dict[str, Any],
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0,
    ticker: Optional[str] = None,
) -> Dict[str, Any]:
    """Add Bollinger Bands to a Chart.js configuration.

    Parameters
    ----------
    config : Dict[str, Any]
        Base Chart.js configuration
    prices : List[float]
        Price data (closing prices)
    period : int, optional
        Period for the moving average, by default 20
    std_dev : float, optional
        Number of standard deviations, by default 2.0
    ticker : Optional[str], optional
        Ticker symbol for caching, by default None

    Returns
    -------
    Dict[str, Any]
        Enhanced Chart.js configuration with Bollinger Bands
    """
    # Check cache first
    if ticker:
        cache_params = {"period": period, "std_dev": std_dev, "indicator": "bollinger"}
        cached = get_cached_indicator(ticker, "bollinger_bands", cache_params)
        if cached:
            upper, middle, lower = cached
        else:
            upper, middle, lower = calculate_bollinger_bands(prices, period, std_dev)
            cache_indicator(
                ticker, "bollinger_bands", cache_params, (upper, middle, lower), ttl=60
            )
    else:
        upper, middle, lower = calculate_bollinger_bands(prices, period, std_dev)

    if not upper or not middle or not lower:
        return config

    # Convert to chart data format
    def to_chart_data(values: List[float]) -> List[Optional[float]]:
        """Convert values to chart data, replacing nan with None"""
        import math

        return [None if math.isnan(v) else v for v in values]

    # Add datasets for Bollinger Bands
    datasets = config.get("data", {}).get("datasets", [])

    # Upper band
    datasets.append(
        {
            "label": "BB Upper",
            "type": "line",
            "data": to_chart_data(upper),
            "borderColor": "#2196F3",  # Blue
            "backgroundColor": "rgba(33, 150, 243, 0.05)",
            "borderWidth": 1,
            "pointRadius": 0,
            "borderDash": [5, 5],
            "fill": False,
            "order": 2,
        }
    )

    # Middle band (SMA)
    datasets.append(
        {
            "label": "BB Middle (SMA)",
            "type": "line",
            "data": to_chart_data(middle),
            "borderColor": "#2196F3",  # Blue
            "backgroundColor": "rgba(33, 150, 243, 0.1)",
            "borderWidth": 2,
            "pointRadius": 0,
            "fill": False,
            "order": 2,
        }
    )

    # Lower band
    datasets.append(
        {
            "label": "BB Lower",
            "type": "line",
            "data": to_chart_data(lower),
            "borderColor": "#2196F3",  # Blue
            "backgroundColor": "rgba(33, 150, 243, 0.05)",
            "borderWidth": 1,
            "pointRadius": 0,
            "borderDash": [5, 5],
            "fill": False,
            "order": 2,
        }
    )

    config["data"]["datasets"] = datasets

    return config


def add_fibonacci_to_config(
    config: Dict[str, Any],
    prices: List[float],
    lookback: int = 20,
    ticker: Optional[str] = None,
) -> Dict[str, Any]:
    """Add Fibonacci retracement levels to a Chart.js configuration.

    Parameters
    ----------
    config : Dict[str, Any]
        Base Chart.js configuration
    prices : List[float]
        Price data
    lookback : int, optional
        Lookback period for swing detection, by default 20
    ticker : Optional[str], optional
        Ticker symbol for caching, by default None

    Returns
    -------
    Dict[str, Any]
        Enhanced Chart.js configuration with Fibonacci levels
    """
    # Find swing points
    swing_high, swing_low, _, _ = find_swing_points(prices, lookback=lookback)

    if not swing_high or not swing_low or swing_high <= swing_low:
        return config

    # Calculate Fibonacci levels
    fib_levels = calculate_fibonacci_levels(swing_high, swing_low)

    # Add as horizontal line annotations
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    # Color gradient from green to red
    colors = {
        "0%": "#4CAF50",  # Green
        "23.6%": "#8BC34A",  # Light green
        "38.2%": "#CDDC39",  # Lime
        "50%": "#FFC107",  # Amber
        "61.8%": "#FF9800",  # Orange (Golden ratio)
        "78.6%": "#FF5722",  # Deep orange
        "100%": "#F44336",  # Red
    }

    for level_name, level_price in fib_levels.items():
        annotation_id = f"fib_{level_name.replace('%', 'pct').replace('.', '_')}"
        annotations[annotation_id] = {
            "type": "line",
            "yMin": level_price,
            "yMax": level_price,
            "borderColor": colors.get(level_name, "#9E9E9E"),
            "borderWidth": 2 if level_name == "61.8%" else 1,  # Highlight golden ratio
            "borderDash": [3, 3] if level_name not in ["0%", "100%"] else [],
            "label": {
                "display": True,
                "content": f"Fib {level_name}: ${level_price:.2f}",
                "position": "end",
                "backgroundColor": colors.get(level_name, "#9E9E9E"),
                "color": "white",
                "font": {
                    "size": 10,
                    "weight": "bold" if level_name == "61.8%" else "normal",
                },
            },
        }

    return config


def add_support_resistance_to_config(
    config: Dict[str, Any],
    prices: List[float],
    volumes: Optional[List[float]] = None,
    sensitivity: float = 0.02,
    max_levels: int = 5,
    ticker: Optional[str] = None,
) -> Dict[str, Any]:
    """Add support and resistance levels to a Chart.js configuration.

    Parameters
    ----------
    config : Dict[str, Any]
        Base Chart.js configuration
    prices : List[float]
        Price data
    volumes : Optional[List[float]], optional
        Volume data for strength weighting, by default None
    sensitivity : float, optional
        Clustering sensitivity (0.02 = 2%), by default 0.02
    max_levels : int, optional
        Maximum levels to display, by default 5
    ticker : Optional[str], optional
        Ticker symbol for caching, by default None

    Returns
    -------
    Dict[str, Any]
        Enhanced Chart.js configuration with S/R levels
    """
    # Detect support and resistance
    support_levels, resistance_levels = detect_support_resistance(
        prices, volumes, sensitivity=sensitivity, max_levels=max_levels
    )

    if not support_levels and not resistance_levels:
        return config

    # Add as horizontal line annotations
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    # Add support levels (green)
    for i, level in enumerate(support_levels):
        annotation_id = f"support_{i}"
        strength = level.get("strength", 50)

        # Line thickness based on strength
        line_width = int(1 + (strength / 100) * 2)  # 1-3 pixels

        annotations[annotation_id] = {
            "type": "line",
            "yMin": level["price"],
            "yMax": level["price"],
            "borderColor": "#4CAF50",  # Green
            "borderWidth": line_width,
            "label": {
                "display": True,
                "content": f"S{i+1}: ${level['price']:.2f} ({level['touches']} touches)",
                "position": "start",
                "backgroundColor": "#4CAF50",
                "color": "white",
                "font": {"size": 9},
            },
        }

    # Add resistance levels (red)
    for i, level in enumerate(resistance_levels):
        annotation_id = f"resistance_{i}"
        strength = level.get("strength", 50)

        # Line thickness based on strength
        line_width = int(1 + (strength / 100) * 2)  # 1-3 pixels

        annotations[annotation_id] = {
            "type": "line",
            "yMin": level["price"],
            "yMax": level["price"],
            "borderColor": "#F44336",  # Red
            "borderWidth": line_width,
            "label": {
                "display": True,
                "content": f"R{i+1}: ${level['price']:.2f} ({level['touches']} touches)",
                "position": "start",
                "backgroundColor": "#F44336",
                "color": "white",
                "font": {"size": 9},
            },
        }

    return config


def add_volume_profile_to_config(
    config: Dict[str, Any],
    prices: List[float],
    volumes: List[float],
    bins: int = 20,
    ticker: Optional[str] = None,
) -> Dict[str, Any]:
    """Add volume profile overlay to a Chart.js configuration.

    Note: Volume profile requires custom Chart.js plugin or horizontal bar overlay.
    This implementation adds POC and Value Area annotations.

    Parameters
    ----------
    config : Dict[str, Any]
        Base Chart.js configuration
    prices : List[float]
        Price data
    volumes : List[float]
        Volume data
    bins : int, optional
        Number of price bins, by default 20
    ticker : Optional[str], optional
        Ticker symbol for caching, by default None

    Returns
    -------
    Dict[str, Any]
        Enhanced Chart.js configuration with volume profile annotations
    """
    # Calculate volume profile
    price_levels, volume_at_price = calculate_volume_profile(prices, volumes, bins=bins)

    if not price_levels or not volume_at_price:
        return config

    # Find POC (Point of Control)
    poc = find_point_of_control(price_levels, volume_at_price)

    # Calculate Value Area
    vah, _, val = calculate_value_area(price_levels, volume_at_price)

    # Add annotations
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    # POC - thick orange line
    if poc:
        annotations["poc"] = {
            "type": "line",
            "yMin": poc,
            "yMax": poc,
            "borderColor": "#FF9800",  # Orange
            "borderWidth": 3,
            "label": {
                "display": True,
                "content": f"POC: ${poc:.2f}",
                "position": "center",
                "backgroundColor": "#FF9800",
                "color": "white",
                "font": {"size": 11, "weight": "bold"},
            },
        }

    # Value Area High
    if vah:
        annotations["vah"] = {
            "type": "line",
            "yMin": vah,
            "yMax": vah,
            "borderColor": "#9C27B0",  # Purple
            "borderWidth": 1,
            "borderDash": [5, 5],
            "label": {
                "display": True,
                "content": f"VAH: ${vah:.2f}",
                "position": "end",
                "backgroundColor": "#9C27B0",
                "color": "white",
                "font": {"size": 9},
            },
        }

    # Value Area Low
    if val:
        annotations["val"] = {
            "type": "line",
            "yMin": val,
            "yMax": val,
            "borderColor": "#9C27B0",  # Purple
            "borderWidth": 1,
            "borderDash": [5, 5],
            "label": {
                "display": True,
                "content": f"VAL: ${val:.2f}",
                "position": "end",
                "backgroundColor": "#9C27B0",
                "color": "white",
                "font": {"size": 9},
            },
        }

    return config


def generate_chart_with_toggles(
    ticker: str,
    timeframe: str,
    prices: List[float],
    volumes: Optional[List[float]] = None,
    indicators: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate a Chart.js configuration with toggleable indicators.

    This is an alias for generate_advanced_chart() that emphasizes
    the ability to toggle indicators on/off dynamically.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe (e.g., "1D", "5D", "1M")
    prices : List[float]
        Price data
    volumes : Optional[List[float]], optional
        Volume data, by default None
    indicators : Optional[List[str]], optional
        List of indicators to add: ['bollinger', 'fibonacci', 'sr', 'volume_profile']
        If None, uses environment variable CHART_DEFAULT_INDICATORS

    Returns
    -------
    Dict[str, Any]
        Chart.js configuration with requested indicators

    Examples
    --------
    >>> prices = [100, 102, 101, 103, 105]
    >>> config = generate_chart_with_toggles("AAPL", "1D", prices, indicators=['sr'])
    >>> "support_" in str(config) or "resistance_" in str(config)
    True
    """
    return generate_advanced_chart(ticker, timeframe, prices, volumes, indicators)


def generate_advanced_chart(
    ticker: str,
    timeframe: str,
    prices: List[float],
    volumes: Optional[List[float]] = None,
    indicators: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a Chart.js configuration with advanced indicators.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe (e.g., "1D", "5D", "1M")
    prices : List[float]
        Price data
    volumes : Optional[List[float]], optional
        Volume data, by default None
    indicators : Optional[List[str]], optional
        List of indicators to add: ['bollinger', 'fibonacci', 'sr', 'volume_profile']
        If None, uses environment variable CHART_DEFAULT_INDICATORS

    Returns
    -------
    Dict[str, Any]
        Chart.js configuration with requested indicators

    Examples
    --------
    >>> prices = [100, 102, 101, 103, 105]
    >>> config = generate_advanced_chart("AAPL", "1D", prices, indicators=['bollinger'])
    >>> "BB Upper" in str(config)
    True
    """
    if indicators is None:
        # Read from environment
        default_indicators = os.getenv("CHART_DEFAULT_INDICATORS", "bollinger,sr")
        indicators = [i.strip() for i in default_indicators.split(",")]

    # Create base config (simplified)
    config = {
        "type": "line",
        "data": {
            "labels": list(range(len(prices))),
            "datasets": [
                {
                    "label": ticker,
                    "data": prices,
                    "borderColor": "#2196F3",
                    "backgroundColor": "rgba(33, 150, 243, 0.1)",
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "fill": False,
                    "order": 1,
                }
            ],
        },
        "options": {
            "responsive": True,
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"{ticker} - {timeframe}",
                    "color": "#FFFFFF",
                    "font": {"size": 16, "weight": "bold"},
                },
                "legend": {"display": True, "labels": {"color": "#CCCCCC"}},
            },
            "scales": {
                "y": {
                    "position": "right",
                    "ticks": {"color": "#CCCCCC"},
                    "grid": {"color": "#2A2A2A"},
                },
                "x": {"ticks": {"color": "#CCCCCC"}, "grid": {"color": "#2A2A2A"}},
            },
        },
    }

    # Read settings from environment
    bollinger_period = int(os.getenv("CHART_BOLLINGER_PERIOD", "20"))
    bollinger_std = float(os.getenv("CHART_BOLLINGER_STD", "2.0"))
    sr_sensitivity = float(os.getenv("CHART_SR_SENSITIVITY", "0.02"))
    sr_max_levels = int(os.getenv("CHART_SR_MAX_LEVELS", "5"))
    volume_bins = int(os.getenv("CHART_VOLUME_BINS", "20"))

    # Add requested indicators
    if "bollinger" in indicators and os.getenv("CHART_SHOW_BOLLINGER", "1") == "1":
        config = add_bollinger_bands_to_config(
            config,
            prices,
            period=bollinger_period,
            std_dev=bollinger_std,
            ticker=ticker,
        )

    if "fibonacci" in indicators and os.getenv("CHART_SHOW_FIBONACCI", "1") == "1":
        config = add_fibonacci_to_config(config, prices, ticker=ticker)

    if "sr" in indicators and os.getenv("CHART_SHOW_SUPPORT_RESISTANCE", "1") == "1":
        config = add_support_resistance_to_config(
            config,
            prices,
            volumes,
            sensitivity=sr_sensitivity,
            max_levels=sr_max_levels,
            ticker=ticker,
        )

    if (
        "volume_profile" in indicators
        and volumes
        and os.getenv("CHART_SHOW_VOLUME_PROFILE", "0") == "1"
    ):
        config = add_volume_profile_to_config(
            config, prices, volumes, bins=volume_bins, ticker=ticker
        )

    # Add pattern detection (Phase 4)
    if "patterns" in indicators and os.getenv("CHART_PATTERN_RECOGNITION", "1") == "1":
        try:
            from .indicators.cache import cache_patterns, get_cached_patterns
            from .indicators.patterns import (
                detect_all_patterns,
                detect_channels,
                detect_double_tops_bottoms,
                detect_flags_pennants,
                detect_head_shoulders,
                detect_triangles,
            )

            # Check cache first
            cached_patterns = get_cached_patterns(ticker, timeframe)
            if cached_patterns:
                patterns = cached_patterns
            else:
                # Detect patterns based on individual toggles
                patterns = []
                min_confidence = float(os.getenv("CHART_PATTERN_SENSITIVITY", "0.6"))
                lookback = int(os.getenv("CHART_PATTERN_LOOKBACK_MAX", "100"))
                highs = prices.copy() if not volumes else None  # Placeholder
                lows = prices.copy() if not volumes else None  # Placeholder

                # Triangle patterns
                if os.getenv("CHART_PATTERNS_TRIANGLES", "1") == "1":
                    patterns.extend(
                        detect_triangles(prices, highs or prices, lows or prices, lookback=lookback)
                    )

                # Head & Shoulders patterns
                if os.getenv("CHART_PATTERNS_HEAD_SHOULDERS", "1") == "1":
                    patterns.extend(
                        detect_head_shoulders(prices, min_confidence=min_confidence, lookback=lookback)
                    )

                # Double Tops/Bottoms patterns
                if os.getenv("CHART_PATTERNS_DOUBLE_TOPS", "1") == "1":
                    patterns.extend(
                        detect_double_tops_bottoms(prices, lookback=lookback)
                    )

                # Channel patterns
                if os.getenv("CHART_PATTERNS_CHANNELS", "1") == "1":
                    patterns.extend(
                        detect_channels(prices, highs or prices, lows or prices, lookback=lookback)
                    )

                # Flags & Pennants patterns
                if os.getenv("CHART_PATTERNS_FLAGS", "1") == "1" and volumes:
                    patterns.extend(
                        detect_flags_pennants(prices, volumes=volumes, lookback=lookback)
                    )

                # Filter by minimum confidence
                patterns = [p for p in patterns if p.get("confidence", 0) >= min_confidence]

                # Cache results
                cache_patterns(ticker, patterns, timeframe)

            # Add pattern annotations
            if patterns:
                config = add_pattern_annotations_to_config(config, patterns)

        except ImportError:
            # Pattern detection not available
            if log:
                log.warning("Pattern detection requested but not available")

    return config


def add_pattern_annotations_to_config(
    config: Dict[str, Any], patterns: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Add pattern annotations to a Chart.js configuration.

    Draws pattern shapes and labels for detected chart patterns including
    triangles, head & shoulders, double tops/bottoms, channels, and flags.

    Parameters
    ----------
    config : Dict[str, Any]
        Base Chart.js configuration
    patterns : List[Dict[str, Any]]
        List of detected patterns from patterns.detect_all_patterns()

    Returns
    -------
    Dict[str, Any]
        Enhanced Chart.js configuration with pattern annotations

    Examples
    --------
    >>> config = {"type": "line", "data": {"datasets": []}}
    >>> patterns = [{"type": "ascending_triangle", "confidence": 0.8}]
    >>> enhanced = add_pattern_annotations_to_config(config, patterns)
    >>> "annotations" in enhanced.get("options", {}).get("plugins", {}).get("annotation", {})
    True
    """
    if not patterns:
        return config

    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    # Pattern colors from environment
    pattern_colors = {
        "triangle": os.getenv("CHART_PATTERN_TRIANGLE_COLOR", "#FFC107"),
        "head_shoulders": os.getenv("CHART_PATTERN_HS_COLOR", "#E91E63"),
        "double": os.getenv("CHART_PATTERN_DOUBLE_COLOR", "#9C27B0"),
        "channel": os.getenv("CHART_PATTERN_CHANNEL_COLOR", "#00BCD4"),
        "flag": os.getenv("CHART_PATTERN_FLAG_COLOR", "#4CAF50"),
    }

    for i, pattern in enumerate(patterns):
        pattern_type = pattern.get("type", "")
        confidence = pattern.get("confidence", 0)

        # Determine color based on pattern type
        if "triangle" in pattern_type:
            color = pattern_colors["triangle"]
        elif "head_shoulders" in pattern_type:
            color = pattern_colors["head_shoulders"]
        elif "double" in pattern_type:
            color = pattern_colors["double"]
        elif "channel" in pattern_type:
            color = pattern_colors["channel"]
        elif "flag" in pattern_type or "pennant" in pattern_type:
            color = pattern_colors["flag"]
        else:
            color = "#757575"  # Gray default

        # Add pattern-specific annotations
        if "triangle" in pattern_type:
            config = draw_triangle_pattern(config, pattern, color, i)
        elif "head_shoulders" in pattern_type:
            config = draw_head_shoulders_pattern(config, pattern, color, i)
        elif "double" in pattern_type:
            config = draw_double_pattern(config, pattern, color, i)
        elif "channel" in pattern_type:
            config = draw_channel_pattern(config, pattern, color, i)

        # Add label with confidence
        label_id = f"pattern_label_{i}"
        start_idx = pattern.get("start_idx", 0)
        annotations[label_id] = {
            "type": "label",
            "xValue": start_idx,
            "yValue": pattern.get("key_levels", {}).get("current_price", 0),
            "content": f"{pattern_type.replace('_', ' ').title()} ({confidence:.0%})",
            "backgroundColor": color,
            "color": "white",
            "font": {"size": 10, "weight": "bold"},
            "padding": 4,
            "borderRadius": 4,
        }

    return config


def draw_triangle_pattern(
    config: Dict[str, Any], pattern: Dict[str, Any], color: str, index: int
) -> Dict[str, Any]:
    """Draw triangle pattern trendlines on chart.

    Parameters
    ----------
    config : Dict[str, Any]
        Chart.js configuration
    pattern : Dict[str, Any]
        Triangle pattern data
    color : str
        Line color
    index : int
        Pattern index for unique IDs

    Returns
    -------
    Dict[str, Any]
        Enhanced configuration
    """
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    key_levels = pattern.get("key_levels", {})
    start_idx = pattern.get("start_idx", 0)
    end_idx = pattern.get("end_idx", 0)

    # Draw resistance line (if flat)
    if "resistance" in key_levels:
        annotations[f"triangle_resistance_{index}"] = {
            "type": "line",
            "xMin": start_idx,
            "xMax": end_idx,
            "yMin": key_levels["resistance"],
            "yMax": key_levels["resistance"],
            "borderColor": color,
            "borderWidth": 2,
            "borderDash": [5, 5],
        }

    # Draw support line (if flat)
    if "support" in key_levels:
        annotations[f"triangle_support_{index}"] = {
            "type": "line",
            "xMin": start_idx,
            "xMax": end_idx,
            "yMin": key_levels["support"],
            "yMax": key_levels["support"],
            "borderColor": color,
            "borderWidth": 2,
            "borderDash": [5, 5],
        }

    return config


def draw_head_shoulders_pattern(
    config: Dict[str, Any], pattern: Dict[str, Any], color: str, index: int
) -> Dict[str, Any]:
    """Draw head and shoulders pattern markers.

    Parameters
    ----------
    config : Dict[str, Any]
        Chart.js configuration
    pattern : Dict[str, Any]
        H&S pattern data
    color : str
        Marker color
    index : int
        Pattern index for unique IDs

    Returns
    -------
    Dict[str, Any]
        Enhanced configuration
    """
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    key_levels = pattern.get("key_levels", {})

    # Mark shoulders and head
    for label, position in [
        ("LS", key_levels.get("left_shoulder")),
        ("H", key_levels.get("head")),
        ("RS", key_levels.get("right_shoulder")),
    ]:
        if position and isinstance(position, tuple) and len(position) == 2:
            idx, price = position
            annotations[f"hs_{label}_{index}"] = {
                "type": "point",
                "xValue": idx,
                "yValue": price,
                "backgroundColor": color,
                "borderColor": color,
                "borderWidth": 2,
                "radius": 6,
                "label": {
                    "display": True,
                    "content": label,
                    "position": "top" if label == "H" else "bottom",
                },
            }

    # Draw neckline
    if "neckline" in key_levels:
        annotations[f"hs_neckline_{index}"] = {
            "type": "line",
            "yMin": key_levels["neckline"],
            "yMax": key_levels["neckline"],
            "borderColor": color,
            "borderWidth": 2,
            "borderDash": [10, 5],
        }

    return config


def draw_double_pattern(
    config: Dict[str, Any], pattern: Dict[str, Any], color: str, index: int
) -> Dict[str, Any]:
    """Draw double top/bottom pattern markers.

    Parameters
    ----------
    config : Dict[str, Any]
        Chart.js configuration
    pattern : Dict[str, Any]
        Double top/bottom pattern data
    color : str
        Marker color
    index : int
        Pattern index

    Returns
    -------
    Dict[str, Any]
        Enhanced configuration
    """
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    key_levels = pattern.get("key_levels", {})
    pattern_type = pattern.get("type", "")

    # Mark the two peaks/troughs
    if "double_top" in pattern_type:
        for label, position in [
            ("Peak1", key_levels.get("peak1")),
            ("Peak2", key_levels.get("peak2")),
        ]:
            if position and isinstance(position, tuple) and len(position) == 2:
                idx, price = position
                annotations[f"double_{label}_{index}"] = {
                    "type": "point",
                    "xValue": idx,
                    "yValue": price,
                    "backgroundColor": color,
                    "borderColor": color,
                    "borderWidth": 2,
                    "radius": 5,
                }
    else:  # double_bottom
        for label, position in [
            ("Trough1", key_levels.get("trough1")),
            ("Trough2", key_levels.get("trough2")),
        ]:
            if position and isinstance(position, tuple) and len(position) == 2:
                idx, price = position
                annotations[f"double_{label}_{index}"] = {
                    "type": "point",
                    "xValue": idx,
                    "yValue": price,
                    "backgroundColor": color,
                    "borderColor": color,
                    "borderWidth": 2,
                    "radius": 5,
                }

    return config


def draw_channel_pattern(
    config: Dict[str, Any], pattern: Dict[str, Any], color: str, index: int
) -> Dict[str, Any]:
    """Draw channel pattern boundary lines.

    Parameters
    ----------
    config : Dict[str, Any]
        Chart.js configuration
    pattern : Dict[str, Any]
        Channel pattern data
    color : str
        Line color
    index : int
        Pattern index

    Returns
    -------
    Dict[str, Any]
        Enhanced configuration
    """
    annotations = (
        config.setdefault("options", {})
        .setdefault("plugins", {})
        .setdefault("annotation", {})
        .setdefault("annotations", {})
    )

    key_levels = pattern.get("key_levels", {})
    start_idx = pattern.get("start_idx", 0)
    end_idx = pattern.get("end_idx", 0)

    # Calculate channel boundaries based on slopes
    upper_slope = key_levels.get("upper_slope", 0)
    lower_slope = key_levels.get("lower_slope", 0)
    channel_width = key_levels.get("channel_width", 0)
    current_price = key_levels.get("current_price", 0)

    # Draw upper channel line
    annotations[f"channel_upper_{index}"] = {
        "type": "line",
        "xMin": start_idx,
        "xMax": end_idx,
        "yMin": current_price + channel_width / 2,
        "yMax": current_price + channel_width / 2 + upper_slope * (end_idx - start_idx),
        "borderColor": color,
        "borderWidth": 2,
        "borderDash": [5, 5],
    }

    # Draw lower channel line
    annotations[f"channel_lower_{index}"] = {
        "type": "line",
        "xMin": start_idx,
        "xMax": end_idx,
        "yMin": current_price - channel_width / 2,
        "yMax": current_price - channel_width / 2 + lower_slope * (end_idx - start_idx),
        "borderColor": color,
        "borderWidth": 2,
        "borderDash": [5, 5],
    }

    return config


__all__ = [
    "add_bollinger_bands_to_config",
    "add_fibonacci_to_config",
    "add_support_resistance_to_config",
    "add_volume_profile_to_config",
    "generate_advanced_chart",
    "generate_chart_with_toggles",
    "add_pattern_annotations_to_config",
    "draw_triangle_pattern",
    "draw_head_shoulders_pattern",
    "draw_double_pattern",
    "draw_channel_pattern",
]
