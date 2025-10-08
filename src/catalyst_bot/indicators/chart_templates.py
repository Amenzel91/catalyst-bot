"""
chart_templates.py
==================

Predefined chart templates for different trading strategies and use cases.

Chart templates provide pre-configured combinations of indicators optimized
for specific trading styles. Each template includes:
- Selected technical indicators
- Appropriate timeframes
- Color schemes and styling
- Annotation preferences

Available templates:
- Breakout: For identifying and trading breakouts
- Swing Trading: For multi-day position trading
- Scalping: For short-term intraday trading
- Earnings: For trading around earnings events
- Momentum: For trending markets
- Mean Reversion: For range-bound markets
"""

from __future__ import annotations

from typing import Dict, List, Optional

# Template definitions
CHART_TEMPLATES = {
    "breakout": {
        "name": "Breakout Chart",
        "description": "Bollinger Bands + Volume Profile + Support/Resistance for breakout detection",  # noqa: E501
        "indicators": ["bollinger", "volume_profile", "sr"],
        "timeframes": ["1D", "4H"],
        "settings": {
            "bollinger_period": 20,
            "bollinger_std": 2.0,
            "volume_bins": 20,
            "sr_sensitivity": 0.02,
            "sr_max_levels": 5,
        },
        "annotations": {
            "show_labels": True,
            "highlight_poc": True,
            "mark_levels": True,
        },
        "use_case": "Identify when price breaks out of consolidation with volume confirmation",
    },
    "swing": {
        "name": "Swing Trading Chart",
        "description": "Fibonacci + Support/Resistance + RSI for swing position entry/exit",
        "indicators": ["fibonacci", "sr", "rsi"],
        "timeframes": ["1D", "1W"],
        "settings": {
            "fibonacci_lookback": 30,
            "sr_sensitivity": 0.025,
            "sr_max_levels": 4,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
        },
        "annotations": {
            "show_labels": True,
            "show_fib_levels": True,
            "mark_levels": True,
        },
        "use_case": "Identify swing highs/lows and plan multi-day positions",
    },
    "scalping": {
        "name": "Scalping Chart",
        "description": "VWAP + EMA crossovers + Volume for short-term trades",
        "indicators": ["vwap", "ema", "volume"],
        "timeframes": ["5M", "15M"],
        "settings": {
            "ema_fast": 9,
            "ema_slow": 21,
            "show_volume_bars": True,
            "volume_ma_period": 20,
        },
        "annotations": {
            "show_labels": False,  # Less clutter for fast trading
            "highlight_crosses": True,
            "mark_vwap": True,
        },
        "use_case": "Quick intraday entries and exits with tight risk management",
    },
    "earnings": {
        "name": "Earnings Chart",
        "description": "Bollinger Bands + Volume + Recent High/Low for earnings volatility",
        "indicators": ["bollinger", "volume", "highs_lows"],
        "timeframes": ["1D"],
        "settings": {
            "bollinger_period": 20,
            "bollinger_std": 2.5,  # Wider bands for earnings volatility
            "volume_ma_period": 30,
            "lookback_highs_lows": 60,  # 60-day high/low
        },
        "annotations": {
            "show_labels": True,
            "mark_earnings_date": True,
            "show_historical_moves": True,
        },
        "use_case": "Analyze earnings volatility and expected move ranges",
    },
    "momentum": {
        "name": "Momentum Chart",
        "description": "MACD + RSI + Volume for trending momentum plays",
        "indicators": ["macd", "rsi", "volume"],
        "timeframes": ["1D", "4H"],
        "settings": {
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_period": 14,
            "volume_ma_period": 20,
        },
        "annotations": {
            "show_labels": True,
            "highlight_divergence": True,
            "mark_crosses": True,
        },
        "use_case": "Ride strong trends with momentum confirmation",
    },
    "mean_reversion": {
        "name": "Mean Reversion Chart",
        "description": "Bollinger Bands + RSI + Support/Resistance for range trading",
        "indicators": ["bollinger", "rsi", "sr"],
        "timeframes": ["1D", "4H"],
        "settings": {
            "bollinger_period": 20,
            "bollinger_std": 2.0,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "sr_sensitivity": 0.015,  # Tighter for range
            "sr_max_levels": 6,
        },
        "annotations": {
            "show_labels": True,
            "mark_levels": True,
            "highlight_extremes": True,
        },
        "use_case": "Trade bounces in range-bound markets",
    },
    "volume_analysis": {
        "name": "Volume Analysis Chart",
        "description": "Volume Profile + Volume bars + VWAP for institutional activity",
        "indicators": ["volume_profile", "volume", "vwap"],
        "timeframes": ["1D", "30M"],
        "settings": {
            "volume_bins": 25,
            "volume_ma_period": 20,
            "show_poc": True,
            "show_value_area": True,
        },
        "annotations": {
            "show_labels": True,
            "highlight_poc": True,
            "mark_vwap": True,
            "show_hvn_lvn": True,
        },
        "use_case": "Identify institutional support/resistance and volume patterns",
    },
    "fibonacci_trader": {
        "name": "Fibonacci Trader Chart",
        "description": "Fibonacci retracements/extensions + Support/Resistance",
        "indicators": ["fibonacci", "fibonacci_ext", "sr"],
        "timeframes": ["1D", "4H"],
        "settings": {
            "fibonacci_lookback": 40,
            "show_extensions": True,
            "extension_ratios": [1.272, 1.618, 2.0],
            "sr_sensitivity": 0.02,
            "sr_max_levels": 3,
        },
        "annotations": {
            "show_labels": True,
            "show_fib_levels": True,
            "show_fib_extensions": True,
            "mark_levels": False,  # Less clutter
        },
        "use_case": "Precise retracement entries and extension targets",
    },
}


def get_template(template_name: str) -> Optional[Dict]:
    """Get a chart template by name.

    Parameters
    ----------
    template_name : str
        Name of the template (case-insensitive)

    Returns
    -------
    Optional[Dict]
        Template configuration dict, or None if not found

    Examples
    --------
    >>> template = get_template("breakout")
    >>> template['name']
    'Breakout Chart'
    >>> "bollinger" in template['indicators']
    True
    """
    return CHART_TEMPLATES.get(template_name.lower())


def list_templates() -> List[Dict[str, str]]:
    """List all available chart templates.

    Returns
    -------
    List[Dict[str, str]]
        List of dicts with template 'name', 'description', and 'use_case'

    Examples
    --------
    >>> templates = list_templates()
    >>> len(templates) > 0
    True
    >>> all('name' in t for t in templates)
    True
    """
    result = []
    for key, template in CHART_TEMPLATES.items():
        result.append(
            {
                "id": key,
                "name": template["name"],
                "description": template["description"],
                "use_case": template["use_case"],
            }
        )
    return result


def get_template_indicators(template_name: str) -> List[str]:
    """Get the list of indicators for a template.

    Parameters
    ----------
    template_name : str
        Name of the template

    Returns
    -------
    List[str]
        List of indicator names, or empty list if template not found

    Examples
    --------
    >>> indicators = get_template_indicators("scalping")
    >>> "vwap" in indicators
    True
    """
    template = get_template(template_name)
    return template["indicators"] if template else []


def get_template_settings(template_name: str) -> Dict:
    """Get the settings for a template.

    Parameters
    ----------
    template_name : str
        Name of the template

    Returns
    -------
    Dict
        Settings dict, or empty dict if template not found

    Examples
    --------
    >>> settings = get_template_settings("breakout")
    >>> settings.get('bollinger_period')
    20
    """
    template = get_template(template_name)
    return template["settings"] if template else {}


def get_recommended_timeframes(template_name: str) -> List[str]:
    """Get recommended timeframes for a template.

    Parameters
    ----------
    template_name : str
        Name of the template

    Returns
    -------
    List[str]
        List of timeframe strings (e.g., ["1D", "4H"])

    Examples
    --------
    >>> timeframes = get_recommended_timeframes("swing")
    >>> "1D" in timeframes
    True
    """
    template = get_template(template_name)
    return template["timeframes"] if template else []


def suggest_template(
    trading_style: str, market_condition: Optional[str] = None
) -> List[str]:
    """Suggest chart templates based on trading style and market conditions.

    Parameters
    ----------
    trading_style : str
        Trading style: "day", "swing", "position", "scalp"
    market_condition : Optional[str], optional
        Market condition: "trending", "ranging", "volatile", or None

    Returns
    -------
    List[str]
        List of suggested template names (IDs)

    Examples
    --------
    >>> suggestions = suggest_template("swing", "trending")
    >>> "swing" in suggestions or "momentum" in suggestions
    True
    >>> suggestions = suggest_template("day", "ranging")
    >>> "mean_reversion" in suggestions
    True
    """
    suggestions = []

    # Map trading styles to templates
    style_map = {
        "day": ["scalping", "momentum", "volume_analysis"],
        "swing": ["swing", "fibonacci_trader", "mean_reversion"],
        "position": ["swing", "momentum", "fibonacci_trader"],
        "scalp": ["scalping", "volume_analysis"],
    }

    # Start with style-based suggestions
    base_suggestions = style_map.get(trading_style.lower(), [])
    suggestions.extend(base_suggestions)

    # Refine based on market condition
    if market_condition:
        condition = market_condition.lower()

        if condition == "trending":
            # Add momentum-focused templates
            if "momentum" not in suggestions:
                suggestions.insert(0, "momentum")
            if "fibonacci_trader" not in suggestions:
                suggestions.append("fibonacci_trader")

        elif condition == "ranging":
            # Add mean reversion templates
            if "mean_reversion" not in suggestions:
                suggestions.insert(0, "mean_reversion")
            if "volume_analysis" not in suggestions:
                suggestions.append("volume_analysis")

        elif condition == "volatile":
            # Add volatility-focused templates
            if "breakout" not in suggestions:
                suggestions.insert(0, "breakout")
            if "earnings" not in suggestions:
                suggestions.append("earnings")

        elif condition == "breakout":
            if "breakout" not in suggestions:
                suggestions.insert(0, "breakout")
            if "volume_analysis" not in suggestions:
                suggestions.append("volume_analysis")

    # Remove duplicates while preserving order
    seen = set()
    suggestions = [x for x in suggestions if not (x in seen or seen.add(x))]

    return suggestions


def customize_template(
    template_name: str,
    custom_settings: Optional[Dict] = None,
    custom_indicators: Optional[List[str]] = None,
) -> Optional[Dict]:
    """Create a customized version of a template.

    Parameters
    ----------
    template_name : str
        Base template name
    custom_settings : Optional[Dict], optional
        Settings to override, by default None
    custom_indicators : Optional[List[str]], optional
        Indicators to use (overrides default), by default None

    Returns
    -------
    Optional[Dict]
        Customized template, or None if base template not found

    Examples
    --------
    >>> custom = customize_template(
    ...     "breakout",
    ...     custom_settings={"bollinger_std": 3.0}
    ... )
    >>> custom['settings']['bollinger_std']
    3.0
    """
    template = get_template(template_name)

    if not template:
        return None

    # Create a copy
    customized = template.copy()
    customized["settings"] = template["settings"].copy()

    # Apply custom settings
    if custom_settings:
        customized["settings"].update(custom_settings)

    # Apply custom indicators
    if custom_indicators:
        customized["indicators"] = custom_indicators

    # Mark as customized
    customized["name"] = f"{template['name']} (Customized)"
    customized["is_custom"] = True

    return customized


__all__ = [
    "CHART_TEMPLATES",
    "get_template",
    "list_templates",
    "get_template_indicators",
    "get_template_settings",
    "get_recommended_timeframes",
    "suggest_template",
    "customize_template",
]
