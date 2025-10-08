"""
chart_panels.py
===============

Multi-panel layout configuration for WeBull-style charts.

This module provides panel configuration and styling for professional
multi-panel chart layouts matching WeBull's aesthetic. It defines panel
ratios, colors, y-axis configurations, and adaptive layout logic.

Features:
- PanelConfig dataclass for panel settings
- Panel-specific color schemes
- Adaptive panel ratio calculation
- Support for 2-4 panel layouts
- Integration with mplfinance rendering
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .logging_utils import get_logger

log = get_logger("chart_panels")


@dataclass
class PanelConfig:
    """
    Configuration for a single chart panel.

    Attributes
    ----------
    panel_index : int
        The panel's position in the layout (0-based, 0 is top).
    name : str
        Display name for the panel (e.g., "Price", "Volume", "RSI").
    ratio : float
        Height ratio relative to other panels (e.g., 6.0 for main price panel).
    ylabel : str
        Y-axis label text.
    ylim : Optional[Tuple[float, float]]
        Y-axis limits (min, max). None for auto-scaling.
    color : str
        Primary color for this panel's indicators (hex color code).
    bgcolor : str
        Background color for the panel (hex color code).
    show_yaxis : bool
        Whether to display the y-axis labels.
    show_grid : bool
        Whether to show grid lines in this panel.
    """

    panel_index: int
    name: str
    ratio: float
    ylabel: str
    ylim: Optional[Tuple[float, float]] = None
    color: str = "#FFFFFF"
    bgcolor: str = "#1b1f24"
    show_yaxis: bool = True
    show_grid: bool = True


# Panel color schemes matching WeBull/Binance aesthetics
PANEL_COLORS = {
    "price": "#FFFFFF",  # White for price data
    "volume": "#8884d8",  # Muted blue-purple
    "rsi": "#00BCD4",  # Cyan
    "macd_line": "#2196F3",  # Blue
    "macd_signal": "#FF5722",  # Orange-red
    "macd_histogram": "#9E9E9E",  # Gray
    "vwap": "#FF9800",  # Orange
    "bollinger": "#2196F3",  # Blue
    "support": "#4CAF50",  # Green
    "resistance": "#F44336",  # Red
    "fibonacci": "#9C27B0",  # Purple
}

# Volume bar colors
VOLUME_COLORS = {
    "up": "#3dc98570",  # Green with transparency (70%)
    "down": "#ef4f6070",  # Red with transparency (70%)
}

# Default panel ratios (WeBull-style 4-panel layout)
DEFAULT_PANEL_RATIOS = {
    "price": 6.0,  # 60% of height
    "volume": 1.5,  # 15% of height
    "rsi": 1.25,  # 12.5% of height
    "macd": 1.25,  # 12.5% of height
}


def get_panel_config(indicator_name: str, panel_index: int = 0) -> PanelConfig:
    """
    Get the configuration for a specific indicator panel.

    Parameters
    ----------
    indicator_name : str
        Name of the indicator ("price", "volume", "rsi", "macd").
    panel_index : int, optional
        The panel index in the layout (default: 0).

    Returns
    -------
    PanelConfig
        Configuration object for the panel.

    Examples
    --------
    >>> config = get_panel_config("rsi", panel_index=2)
    >>> config.ylabel
    'RSI'
    >>> config.ylim
    (0, 100)
    """
    # Read environment variable overrides
    try:
        ratio = float(os.getenv(f"CHART_{indicator_name.upper()}_RATIO", "0") or "0")
    except ValueError:
        ratio = 0.0

    if ratio == 0:
        ratio = DEFAULT_PANEL_RATIOS.get(indicator_name, 1.0)

    # Panel-specific configurations
    configs = {
        "price": PanelConfig(
            panel_index=panel_index,
            name="Price",
            ratio=ratio,
            ylabel="Price ($)",
            ylim=None,  # Auto-scale
            color=PANEL_COLORS["price"],
            bgcolor="#1b1f24",
            show_yaxis=True,
            show_grid=True,
        ),
        "volume": PanelConfig(
            panel_index=panel_index,
            name="Volume",
            ratio=ratio,
            ylabel="",  # No label for cleaner look
            ylim=None,  # Auto-scale
            color=PANEL_COLORS["volume"],
            bgcolor="#1b1f24",
            show_yaxis=False,  # Hide y-axis for cleaner appearance
            show_grid=False,
        ),
        "rsi": PanelConfig(
            panel_index=panel_index,
            name="RSI",
            ratio=ratio,
            ylabel="RSI",
            ylim=(0, 100),  # Fixed range for RSI
            color=PANEL_COLORS["rsi"],
            bgcolor="#1b1f24",
            show_yaxis=True,
            show_grid=True,
        ),
        "macd": PanelConfig(
            panel_index=panel_index,
            name="MACD",
            ratio=ratio,
            ylabel="MACD",
            ylim=None,  # Auto-scale
            color=PANEL_COLORS["macd_line"],
            bgcolor="#1b1f24",
            show_yaxis=True,
            show_grid=True,
        ),
    }

    return configs.get(indicator_name.lower(), configs["price"])


def calculate_panel_ratios(indicators: List[str]) -> Tuple[float, ...]:
    """
    Calculate adaptive panel ratios based on active indicators.

    This function determines the optimal panel layout based on which
    indicators are enabled. It supports 2-4 panel layouts:
    - 2 panels: Price + Volume only
    - 3 panels: Price + Volume + (RSI or MACD)
    - 4 panels: Price + Volume + RSI + MACD

    Parameters
    ----------
    indicators : List[str]
        List of active indicator names (e.g., ["vwap", "rsi", "macd"]).

    Returns
    -------
    Tuple[float, ...]
        Panel ratios as a tuple (e.g., (6.0, 1.5, 1.25, 1.25)).

    Examples
    --------
    >>> calculate_panel_ratios(["vwap", "rsi", "macd"])
    (6.0, 1.5, 1.25, 1.25)

    >>> calculate_panel_ratios(["vwap"])
    (6.0, 1.5)

    >>> calculate_panel_ratios(["vwap", "rsi"])
    (6.0, 1.5, 2.5)
    """
    # Read custom ratios from environment
    env_ratios = os.getenv("CHART_PANEL_RATIOS", "").strip()
    if env_ratios:
        try:
            custom_ratios = tuple(float(x.strip()) for x in env_ratios.split(","))
            log.info("chart_panels_custom_ratios ratios=%s", custom_ratios)
            return custom_ratios
        except Exception as err:
            log.warning("chart_panels_invalid_env_ratios err=%s", str(err))

    # Normalize indicator names
    indicators_lower = [ind.lower() for ind in indicators]

    # Determine which oscillator panels are active
    has_rsi = "rsi" in indicators_lower
    has_macd = "macd" in indicators_lower

    # Always include price panel
    price_ratio = get_panel_config("price").ratio
    volume_ratio = get_panel_config("volume").ratio

    # Build ratio tuple based on active indicators
    if has_rsi and has_macd:
        # 4-panel layout: Price, Volume, RSI, MACD
        rsi_ratio = get_panel_config("rsi").ratio
        macd_ratio = get_panel_config("macd").ratio
        ratios = (price_ratio, volume_ratio, rsi_ratio, macd_ratio)
    elif has_rsi:
        # 3-panel layout: Price, Volume, RSI (give RSI more space)
        rsi_ratio = get_panel_config("rsi").ratio + get_panel_config("macd").ratio
        ratios = (price_ratio, volume_ratio, rsi_ratio)
    elif has_macd:
        # 3-panel layout: Price, Volume, MACD (give MACD more space)
        macd_ratio = get_panel_config("rsi").ratio + get_panel_config("macd").ratio
        ratios = (price_ratio, volume_ratio, macd_ratio)
    else:
        # 2-panel layout: Price and Volume only
        ratios = (price_ratio, volume_ratio)

    log.info(
        "chart_panels_calculated has_rsi=%s has_macd=%s ratios=%s",
        has_rsi,
        has_macd,
        ratios,
    )
    return ratios


def create_panel_layout(num_panels: int) -> Tuple[float, ...]:
    """
    Create panel ratios for a specific number of panels.

    This is a simplified helper that returns pre-defined ratios for
    common panel counts. For adaptive layout based on indicators, use
    ``calculate_panel_ratios()`` instead.

    Parameters
    ----------
    num_panels : int
        Number of panels (2, 3, or 4).

    Returns
    -------
    Tuple[float, ...]
        Panel ratios.

    Raises
    ------
    ValueError
        If num_panels is not in the range [2, 4].

    Examples
    --------
    >>> create_panel_layout(4)
    (6.0, 1.5, 1.25, 1.25)

    >>> create_panel_layout(2)
    (6.0, 1.5)
    """
    if num_panels == 2:
        return (
            get_panel_config("price").ratio,
            get_panel_config("volume").ratio,
        )
    elif num_panels == 3:
        return (
            get_panel_config("price").ratio,
            get_panel_config("volume").ratio,
            get_panel_config("rsi").ratio + get_panel_config("macd").ratio,
        )
    elif num_panels == 4:
        return (
            get_panel_config("price").ratio,
            get_panel_config("volume").ratio,
            get_panel_config("rsi").ratio,
            get_panel_config("macd").ratio,
        )
    else:
        raise ValueError(f"num_panels must be 2, 3, or 4 (got {num_panels})")


def get_panel_spacing() -> float:
    """
    Get the spacing between panels.

    Returns
    -------
    float
        Panel spacing as a fraction of figure height (default: 0.05).
    """
    try:
        spacing = float(os.getenv("CHART_PANEL_SPACING", "0.05") or "0.05")
    except ValueError:
        spacing = 0.05
    return spacing


def get_panel_borders_enabled() -> bool:
    """
    Check if panel borders are enabled.

    Returns
    -------
    bool
        True if panel borders should be drawn.
    """
    try:
        enabled = int(os.getenv("CHART_PANEL_BORDERS", "1") or "1")
    except ValueError:
        enabled = 1
    return bool(enabled)


def get_panel_color_scheme() -> Dict[str, str]:
    """
    Get the color scheme for all panels.

    This reads environment variable overrides for panel colors and
    returns a dictionary mapping indicator names to hex color codes.

    Returns
    -------
    Dict[str, str]
        Mapping of indicator names to color codes.

    Examples
    --------
    >>> colors = get_panel_color_scheme()
    >>> colors["rsi"]
    '#00BCD4'
    """
    # Read environment overrides
    colors = PANEL_COLORS.copy()

    env_overrides = {
        "CHART_RSI_COLOR": "rsi",
        "CHART_MACD_LINE_COLOR": "macd_line",
        "CHART_MACD_SIGNAL_COLOR": "macd_signal",
        "CHART_VOLUME_UP_COLOR": "volume_up",
        "CHART_VOLUME_DOWN_COLOR": "volume_down",
    }

    for env_key, color_key in env_overrides.items():
        env_val = os.getenv(env_key, "").strip()
        if env_val:
            colors[color_key] = env_val

    # Add volume colors to the main color dict
    colors["volume_up"] = os.getenv("CHART_VOLUME_UP_COLOR", VOLUME_COLORS["up"])
    colors["volume_down"] = os.getenv("CHART_VOLUME_DOWN_COLOR", VOLUME_COLORS["down"])

    return colors


def is_panel_enabled(panel_name: str) -> bool:
    """
    Check if a specific panel is enabled via environment variable.

    Parameters
    ----------
    panel_name : str
        Name of the panel ("rsi", "macd", "volume").

    Returns
    -------
    bool
        True if the panel is enabled.

    Examples
    --------
    >>> is_panel_enabled("rsi")
    True
    """
    env_key = f"CHART_{panel_name.upper()}_PANEL"
    try:
        enabled = int(os.getenv(env_key, "1") or "1")
    except ValueError:
        enabled = 1
    return bool(enabled)


def get_rsi_reference_lines() -> List[Dict]:
    """
    Get RSI reference lines (30/70 levels for oversold/overbought).

    Returns
    -------
    List[Dict]
        List of reference line configurations for RSI panel.

    Examples
    --------
    >>> lines = get_rsi_reference_lines()
    >>> len(lines)
    2
    >>> lines[0]['y']
    70
    """
    return [
        {
            "y": 70,
            "color": "#F44336",  # Red for overbought
            "linestyle": "--",
            "linewidth": 1,
            "alpha": 0.5,
            "label": "Overbought",
        },
        {
            "y": 30,
            "color": "#4CAF50",  # Green for oversold
            "linestyle": "--",
            "linewidth": 1,
            "alpha": 0.5,
            "label": "Oversold",
        },
    ]


def get_macd_reference_lines() -> List[Dict]:
    """
    Get MACD reference lines (zero line).

    Returns
    -------
    List[Dict]
        List of reference line configurations for MACD panel.

    Examples
    --------
    >>> lines = get_macd_reference_lines()
    >>> lines[0]['y']
    0
    """
    return [
        {
            "y": 0,
            "color": "#666666",  # Gray zero line
            "linestyle": "-",
            "linewidth": 0.5,
            "alpha": 0.5,
            "label": "Zero",
        }
    ]


def apply_panel_styling(fig, axes, panel_configs: List[PanelConfig]):
    """
    Apply panel-specific styling to chart axes.

    This function applies visual styling to each panel including:
    - Y-axis labels
    - Grid lines
    - Reference lines (RSI 30/70, MACD zero line)
    - Panel borders

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Figure object from mplfinance
    axes : list or np.ndarray
        List or array of axis objects
    panel_configs : List[PanelConfig]
        Panel configurations to apply

    Notes
    -----
    This modifies the figure in-place.

    Examples
    --------
    >>> fig, axes = mpf.plot(df, returnfig=True)
    >>> configs = [get_panel_config("price", 0), get_panel_config("rsi", 1)]
    >>> apply_panel_styling(fig, axes, configs)
    """
    try:
        import numpy as np

        # Handle both list and ndarray
        if isinstance(axes, np.ndarray):
            axes_list = axes.flatten().tolist()
        else:
            axes_list = list(axes)

        borders_enabled = get_panel_borders_enabled()

        for config in panel_configs:
            if config.panel_index >= len(axes_list):
                continue

            ax = axes_list[config.panel_index]

            # Apply y-axis label
            if config.ylabel:
                ax.set_ylabel(config.ylabel, color="#cccccc", fontsize=11)

            # Apply y-axis limits if specified
            if config.ylim:
                ax.set_ylim(config.ylim)

            # Apply grid settings
            if config.show_grid:
                ax.grid(True, color="#2c2e31", linestyle="--", linewidth=0.5, alpha=0.5)
            else:
                ax.grid(False)

            # Add reference lines for RSI panel
            if config.name == "RSI":
                for ref_line in get_rsi_reference_lines():
                    ax.axhline(
                        y=ref_line["y"],
                        color=ref_line["color"],
                        linestyle=ref_line["linestyle"],
                        linewidth=ref_line["linewidth"],
                        alpha=ref_line["alpha"],
                    )

            # Add reference lines for MACD panel
            if config.name == "MACD":
                for ref_line in get_macd_reference_lines():
                    ax.axhline(
                        y=ref_line["y"],
                        color=ref_line["color"],
                        linestyle=ref_line["linestyle"],
                        linewidth=ref_line["linewidth"],
                        alpha=ref_line["alpha"],
                    )

            # Apply panel borders if enabled
            if borders_enabled:
                for spine in ax.spines.values():
                    spine.set_edgecolor("#2c2e31")
                    spine.set_linewidth(1.0)
            else:
                for spine in ax.spines.values():
                    spine.set_visible(False)

    except Exception as err:
        log.warning("panel_styling_failed err=%s", str(err))
