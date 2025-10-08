"""
Discord Select Menu Interactions for Chart Indicators
======================================================

Phase 2: WeBull Chart Enhancement Plan - Interactive Indicator Toggles

This module handles Discord select menu (dropdown) interactions for toggling
chart indicators on/off dynamically. Users can select from 5 indicator types:
- Support/Resistance Levels
- Bollinger Bands
- Fibonacci Retracement Levels
- Volume Profile (POC, VAH, VAL)
- Chart Patterns (future enhancement)

Architecture:
1. build_chart_select_menu() - Creates Discord component structure
2. handle_chart_indicator_toggle() - Processes user selections
3. parse_indicator_selection() - Extracts selected indicators from interaction
4. regenerate_chart_with_indicators() - Creates new chart with selected indicators

Usage:
    # In chart command handler
    components = build_chart_select_menu("AAPL", "1D", ["sr", "bollinger"])

    # In interaction endpoint
    if interaction.custom_id.startswith("chart_toggle_"):
        response = handle_chart_indicator_toggle(interaction)
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

try:
    from ..chart_indicators_integration import generate_advanced_chart
    from ..chart_sessions import (
        get_user_indicator_preferences,
        set_user_indicator_preferences,
    )
    from ..charts import get_quickchart_url
    from ..logging_utils import get_logger
    from ..market import get_last_price_change
    from .embeds import create_chart_embed
except ImportError:
    # Fallback for testing
    import logging

    def get_logger(name):
        return logging.getLogger(name)

    def get_quickchart_url(ticker, timeframe="1D", indicators=None):
        return f"https://example.com/chart/{ticker}"

    def generate_advanced_chart(
        ticker, timeframe, prices, volumes=None, indicators=None
    ):
        return {}

    def get_last_price_change(ticker):
        return 100.0, 2.5

    def create_chart_embed(ticker, timeframe, chart_url, price_data, components=None):
        return {
            "type": 4,
            "data": {
                "embeds": [{"title": f"{ticker} Chart"}],
                "components": components or [],
            },
        }

    def get_user_indicator_preferences(user_id, ticker):
        return None

    def set_user_indicator_preferences(user_id, ticker, indicators):
        pass


log = get_logger("chart_interactions")


# Indicator metadata
INDICATOR_OPTIONS = [
    {
        "label": "Support/Resistance",
        "value": "sr",
        "description": "Key price levels",
        "emoji": {"name": "📏"},
    },
    {
        "label": "Bollinger Bands",
        "value": "bollinger",
        "description": "Volatility bands (20, 2σ)",
        "emoji": {"name": "📈"},
    },
    {
        "label": "Fibonacci Levels",
        "value": "fibonacci",
        "description": "Retracement levels",
        "emoji": {"name": "🔢"},
    },
    {
        "label": "Volume Profile",
        "value": "volume_profile",
        "description": "POC + Value Area",
        "emoji": {"name": "📊"},
    },
    {
        "label": "Chart Patterns",
        "value": "patterns",
        "description": "Auto-detected patterns",
        "emoji": {"name": "🔺"},
    },
]


def get_default_indicators() -> List[str]:
    """
    Get default indicators from environment configuration.

    Returns
    -------
    List[str]
        List of default indicator codes (e.g., ["sr", "bollinger"])

    Examples
    --------
    >>> # With CHART_DEFAULT_INDICATORS=sr,bollinger,vwap
    >>> get_default_indicators()
    ['sr', 'bollinger']
    """
    default_str = os.getenv("CHART_DEFAULT_INDICATORS", "sr,bollinger")
    indicators = [i.strip() for i in default_str.split(",") if i.strip()]

    # Filter to only valid indicators
    valid_codes = {opt["value"] for opt in INDICATOR_OPTIONS}
    return [ind for ind in indicators if ind in valid_codes]


def build_chart_select_menu(
    ticker: str,
    timeframe: str = "1D",
    default_indicators: Optional[List[str]] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build Discord select menu component for indicator toggles.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Chart timeframe (1D, 5D, 1M, etc.)
    default_indicators : Optional[List[str]]
        List of indicators to enable by default
    user_id : Optional[str]
        Discord user ID (for loading preferences)

    Returns
    -------
    List[Dict[str, Any]]
        Discord components array with select menu

    Examples
    --------
    >>> menu = build_chart_select_menu("AAPL", "1D", ["sr", "bollinger"])
    >>> menu[0]["components"][0]["custom_id"]
    'chart_toggle_AAPL_1D'
    """
    # Check if dropdowns are enabled
    if os.getenv("CHART_ENABLE_DROPDOWNS", "1") != "1":
        return []

    # Get default indicators
    if default_indicators is None:
        # Try to load user preferences first
        if user_id:
            user_prefs = get_user_indicator_preferences(user_id, ticker)
            if user_prefs:
                default_indicators = user_prefs
            else:
                default_indicators = get_default_indicators()
        else:
            default_indicators = get_default_indicators()

    # Build options with default states
    options = []
    for opt in INDICATOR_OPTIONS:
        option = opt.copy()
        option["default"] = opt["value"] in default_indicators
        options.append(option)

    max_options = int(os.getenv("CHART_DROPDOWN_MAX_OPTIONS", "5"))

    # Build select menu component
    select_menu = {
        "type": 1,  # Action Row
        "components": [
            {
                "type": 3,  # Select Menu
                "custom_id": f"chart_toggle_{ticker}_{timeframe}",
                "placeholder": "📊 Toggle Indicators",
                "min_values": 0,  # Can deselect all
                "max_values": min(len(options), max_options),
                "options": options,
            }
        ],
    }

    return [select_menu]


def parse_indicator_selection(
    interaction_data: Dict[str, Any]
) -> tuple[str, str, List[str]]:
    """
    Parse indicator selection from Discord interaction data.

    Parameters
    ----------
    interaction_data : Dict[str, Any]
        Discord interaction payload

    Returns
    -------
    tuple[str, str, List[str]]
        (ticker, timeframe, selected_indicators)

    Examples
    --------
    >>> data = {
    ...     "custom_id": "chart_toggle_AAPL_1D",
    ...     "values": ["sr", "bollinger"]
    ... }
    >>> ticker, tf, indicators = parse_indicator_selection(data)
    >>> ticker
    'AAPL'
    >>> indicators
    ['sr', 'bollinger']
    """
    custom_id = interaction_data.get("custom_id", "")
    selected_values = interaction_data.get("values", [])

    # Extract ticker and timeframe from custom_id
    # Format: chart_toggle_{ticker}_{timeframe}
    parts = custom_id.replace("chart_toggle_", "").split("_")

    if len(parts) >= 2:
        ticker = parts[0]
        timeframe = "_".join(parts[1:])  # Handle timeframes with underscores
    else:
        ticker = parts[0] if parts else "UNKNOWN"
        timeframe = "1D"

    return ticker, timeframe, selected_values


def regenerate_chart_with_indicators(
    ticker: str,
    timeframe: str,
    indicators: List[str],
    user_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Regenerate chart with selected indicators.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Chart timeframe
    indicators : List[str]
        List of indicator codes to include
    user_id : Optional[str]
        Discord user ID (for caching preferences)

    Returns
    -------
    tuple[Optional[str], Optional[Dict[str, Any]]]
        (chart_url, price_data) or (None, None) on error

    Examples
    --------
    >>> url, data = regenerate_chart_with_indicators("AAPL", "1D", ["sr"])
    >>> url is not None
    True
    """
    start_time = time.time()

    try:
        # Save user preferences
        if user_id:
            set_user_indicator_preferences(user_id, ticker, indicators)

        # Generate chart with QuickChart
        chart_url = get_quickchart_url(
            ticker, timeframe=timeframe, indicators=indicators
        )

        if not chart_url:
            log.error(f"chart_regen_failed ticker={ticker} indicators={indicators}")
            return None, None

        # Get current price data
        try:
            price, change_pct = get_last_price_change(ticker)
        except Exception as e:
            log.warning(f"price_fetch_failed ticker={ticker} err={e}")
            price, change_pct = None, None

        price_data = {
            "price": price,
            "change_pct": change_pct or 0,
            "volume": None,
            "vwap": None,
            "rsi": None,
        }

        elapsed = time.time() - start_time
        log.info(
            f"chart_regenerated ticker={ticker} indicators={len(indicators)} "
            f"elapsed={elapsed:.2f}s"
        )

        return chart_url, price_data

    except Exception as e:
        log.error(f"chart_regen_error ticker={ticker} err={e}", exc_info=True)
        return None, None


def handle_chart_indicator_toggle(interaction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle chart indicator toggle interaction from Discord.

    This is the main entry point for processing select menu interactions.

    Parameters
    ----------
    interaction : Dict[str, Any]
        Discord interaction payload

    Returns
    -------
    Dict[str, Any]
        Discord interaction response

    Examples
    --------
    >>> interaction = {
    ...     "type": 3,  # Message Component
    ...     "data": {
    ...         "custom_id": "chart_toggle_AAPL_1D",
    ...         "values": ["sr", "bollinger"]
    ...     },
    ...     "user": {"id": "123456789"}
    ... }
    >>> response = handle_chart_indicator_toggle(interaction)
    >>> response["type"]
    7
    """
    try:
        interaction_data = interaction.get("data", {})
        user_id = interaction.get("user", {}).get("id") or interaction.get(
            "member", {}
        ).get("user", {}).get("id")

        # Parse selection
        ticker, timeframe, selected_indicators = parse_indicator_selection(
            interaction_data
        )

        log.info(
            f"chart_toggle ticker={ticker} timeframe={timeframe} "
            f"indicators={selected_indicators} user_id={user_id}"
        )

        # Regenerate chart with selected indicators
        chart_url, price_data = regenerate_chart_with_indicators(
            ticker, timeframe, selected_indicators, user_id=user_id
        )

        if not chart_url:
            return {
                "type": 4,  # Channel message with source
                "data": {
                    "content": f"❌ Failed to regenerate chart for {ticker}. Please try again.",
                    "flags": 64,  # Ephemeral
                },
            }

        # Build new select menu with updated defaults
        components = build_chart_select_menu(
            ticker, timeframe, selected_indicators, user_id=user_id
        )

        # Create updated embed
        embed_response = create_chart_embed(
            ticker, timeframe, chart_url, price_data, components=components
        )

        # Add indicator list to description
        if selected_indicators:
            indicator_names = []
            for ind_code in selected_indicators:
                for opt in INDICATOR_OPTIONS:
                    if opt["value"] == ind_code:
                        indicator_names.append(opt["label"])
                        break

            indicator_str = ", ".join(indicator_names)

            # Update embed description
            if "data" in embed_response and "embeds" in embed_response["data"]:
                for embed in embed_response["data"]["embeds"]:
                    current_desc = embed.get("description", "")
                    embed["description"] = (
                        f"**Indicators:** {indicator_str}\n\n{current_desc}"
                    )
        else:
            # No indicators selected
            if "data" in embed_response and "embeds" in embed_response["data"]:
                for embed in embed_response["data"]["embeds"]:
                    current_desc = embed.get("description", "")
                    embed["description"] = (
                        f"**Indicators:** None (clean candlesticks)\n\n{current_desc}"
                    )

        # Return type 7 (update message) to edit the existing message
        return {
            "type": 7,  # Update message
            "data": embed_response.get("data", {}),
        }

    except Exception as e:
        log.error(f"chart_toggle_error err={e}", exc_info=True)
        return {
            "type": 4,
            "data": {
                "content": f"❌ An error occurred while updating the chart: {str(e)}",
                "flags": 64,
            },
        }


__all__ = [
    "build_chart_select_menu",
    "handle_chart_indicator_toggle",
    "parse_indicator_selection",
    "regenerate_chart_with_indicators",
    "get_default_indicators",
]
