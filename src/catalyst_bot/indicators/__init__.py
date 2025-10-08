"""
indicators.__init__.py
=======================

Advanced technical indicators for chart generation and analysis.

This package provides professional-grade technical indicators including:
- Bollinger Bands
- Fibonacci Retracements
- Support & Resistance Detection
- Volume Profile
- Multiple Timeframe Analysis
- Chart Templates
- Indicator Caching

All indicators are designed to work with pandas DataFrames and integrate
seamlessly with the QuickChart chart generation system.
"""

from .bollinger import (
    calculate_bandwidth,
    calculate_bollinger_bands,
    get_bollinger_position,
)
from .cache import cache_indicator, get_cache, get_cached_indicator
from .chart_templates import (
    get_template,
    get_template_indicators,
    list_templates,
    suggest_template,
)
from .fibonacci import (
    calculate_fibonacci_extensions,
    calculate_fibonacci_levels,
    find_swing_points,
    get_nearest_fibonacci_level,
)
from .mtf_analysis import (
    analyze_multiple_timeframes,
    calculate_mtf_score,
    detect_momentum_divergence,
    detect_trend,
    find_mtf_support_resistance,
)
from .support_resistance import (
    analyze_level_breakout,
    detect_support_resistance,
    get_nearest_sr_level,
    is_price_at_level,
)
from .volume_profile import (
    calculate_value_area,
    calculate_volume_profile,
    find_point_of_control,
    find_volume_nodes,
)

__all__ = [
    # Bollinger Bands
    "calculate_bollinger_bands",
    "get_bollinger_position",
    "calculate_bandwidth",
    # Fibonacci
    "calculate_fibonacci_levels",
    "find_swing_points",
    "get_nearest_fibonacci_level",
    "calculate_fibonacci_extensions",
    # Support & Resistance
    "detect_support_resistance",
    "get_nearest_sr_level",
    "is_price_at_level",
    "analyze_level_breakout",
    # Volume Profile
    "calculate_volume_profile",
    "find_point_of_control",
    "calculate_value_area",
    "find_volume_nodes",
    # MTF Analysis
    "detect_trend",
    "analyze_multiple_timeframes",
    "find_mtf_support_resistance",
    "detect_momentum_divergence",
    "calculate_mtf_score",
    # Chart Templates
    "get_template",
    "list_templates",
    "get_template_indicators",
    "suggest_template",
    # Cache
    "get_cache",
    "get_cached_indicator",
    "cache_indicator",
]
