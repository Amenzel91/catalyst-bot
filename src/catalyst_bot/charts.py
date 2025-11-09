from __future__ import annotations

import importlib.util
import json
import os
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger

log = get_logger("charts")

# Import chart_panels for enhanced multi-panel support (Phase 3)
try:
    from . import chart_panels

    HAS_CHART_PANELS = True
except ImportError:
    HAS_CHART_PANELS = False
    log.warning("chart_panels_import_failed - multi-panel enhancements unavailable")

# WeBull/Binance Dark Theme Constants
WEBULL_STYLE = {
    "base_mpl_style": "dark_background",
    "facecolor": "#1b1f24",
    "edgecolor": "#2c2e31",
    "figcolor": "#1b1f24",
    "marketcolors": {
        "candle": {"up": "#3dc985", "down": "#ef4f60"},
        "edge": {"up": "#3dc985", "down": "#ef4f60"},
        "wick": {"up": "#3dc985", "down": "#ef4f60"},
        "volume": {"up": "#3dc98570", "down": "#ef4f6070"},
        "alpha": 1.0,
    },
    "gridcolor": "#2c2e31",
    "gridstyle": "--",
    "gridaxis": "both",
    "y_on_right": True,
    "rc": {
        "axes.labelcolor": "#cccccc",
        "axes.edgecolor": "#2c2e31",
        "xtick.color": "#cccccc",
        "ytick.color": "#cccccc",
        "axes.titlecolor": "#ffffff",
        "axes.labelsize": 12,
        "axes.titlesize": 16,
        "font.size": 12,
    },
}

# Discord Native Integration Colors
DISCORD_COLORS = {
    "positive": "#43B581",
    "negative": "#F04747",
    "blurple": "#5865F2",
    "background": "#36393F",
    "text": "#DCDDDE",
    "subtle_grid": "#4E5058",
}

# Indicator panel colors
INDICATOR_COLORS = {
    "vwap": "#FF9800",
    "rsi": "#00BCD4",
    "macd_line": "#2196F3",
    "macd_signal": "#FF5722",
    "bb_upper": "#9C27B0",
    "bb_lower": "#9C27B0",
    "bb_middle": "#9C27B0",
    "support": "#4CAF50",
    "resistance": "#F44336",
    "fibonacci": "#FFD700",  # Gold color for Fib levels
    "volume_profile": "#26C6DA",  # Light Cyan (regular volume bars)
    "volume_profile_hvn": "#4CAF50",  # Green (High Volume Nodes)
    "volume_profile_lvn": "#F44336",  # Red (Low Volume Nodes)
    "volume_profile_poc": "#FF9800",  # Orange (Point of Control)
    "volume_profile_vah": "#9C27B0",  # Purple (Value Area High)
    "volume_profile_val": "#9C27B0",  # Purple (Value Area Low)
    "triangle_ascending": "#00FF00",      # Bright Green (bullish)
    "triangle_descending": "#FF0000",     # Bright Red (bearish)
    "triangle_symmetrical": "#FFA500",    # Orange (neutral)
    "hs_pattern": "#FF1493",              # Deep Pink (reversal)
    "hs_neckline": "#FFD700",             # Gold (key level)
    "double_top": "#DC143C",              # Crimson (bearish reversal)
    "double_bottom": "#32CD32",           # Lime Green (bullish reversal)
}

# Detect packages without importing them up-front
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
HAS_MPLFINANCE = importlib.util.find_spec("mplfinance") is not None

# Legacy/test-facing flag expected by tests/test_chart_guard.py
CHARTS_OK = bool(HAS_MATPLOTLIB and HAS_MPLFINANCE)

# --- QuickChart support ----------------------------------------------------
# QuickChart lets us generate candlestick charts on demand via a simple HTTP
# endpoint.  When FEATURE_QUICKCHART is enabled, alerts will call
# get_quickchart_url() to obtain an image URL instead of embedding a
# base64 chart or falling back to Finviz.  The helper functions below
# build a minimal Chart.js configuration and return a URL that Discord
# can fetch directly.  We avoid importing heavy dependencies at module
# import time; yfinance and pandas are imported lazily inside the
# function so that environments without those libraries can still load
# this module.


def create_webull_style():
    """Create mplfinance style dict based on WeBull dark theme.

    Returns
    -------
    dict
        mplfinance style configuration with WeBull colors and formatting.

    Notes
    -----
    This function converts the WEBULL_STYLE constant into the specific
    format required by mplfinance.make_mpf_style(). Respects environment
    variables for custom text sizing.

    Examples
    --------
    >>> style = create_webull_style()
    >>> # Use with mplfinance
    >>> mpf.plot(df, type='candle', style=style)
    """
    try:
        import mplfinance as mpf

        # Load text sizing from environment
        label_size = int(os.getenv("CHART_AXIS_LABEL_SIZE", "12"))
        title_size = int(os.getenv("CHART_TITLE_SIZE", "16"))

        return mpf.make_mpf_style(
            base_mpf_style="nightclouds",
            marketcolors=mpf.make_marketcolors(
                up=WEBULL_STYLE["marketcolors"]["candle"]["up"],
                down=WEBULL_STYLE["marketcolors"]["candle"]["down"],
                edge={
                    "up": WEBULL_STYLE["marketcolors"]["edge"]["up"],
                    "down": WEBULL_STYLE["marketcolors"]["edge"]["down"],
                },
                wick={
                    "up": WEBULL_STYLE["marketcolors"]["wick"]["up"],
                    "down": WEBULL_STYLE["marketcolors"]["wick"]["down"],
                },
                volume={
                    "up": WEBULL_STYLE["marketcolors"]["volume"]["up"],
                    "down": WEBULL_STYLE["marketcolors"]["volume"]["down"],
                },
            ),
            facecolor=WEBULL_STYLE["facecolor"],
            edgecolor=WEBULL_STYLE["edgecolor"],
            gridcolor=WEBULL_STYLE["gridcolor"],
            gridstyle=WEBULL_STYLE["gridstyle"],
            y_on_right=WEBULL_STYLE["y_on_right"],
            rc={
                "axes.labelcolor": WEBULL_STYLE["rc"]["axes.labelcolor"],
                "xtick.color": WEBULL_STYLE["rc"]["xtick.color"],
                "ytick.color": WEBULL_STYLE["rc"]["ytick.color"],
                "axes.titlecolor": WEBULL_STYLE["rc"]["axes.titlecolor"],
                "axes.labelsize": label_size,
                "axes.titlesize": title_size,
                "font.size": label_size,
                "axes.edgecolor": WEBULL_STYLE["rc"]["axes.edgecolor"],
            },
        )
    except Exception as err:
        log.warning("webull_style_failed err=%s", str(err))
        return "yahoo"


def apply_sr_lines(support_levels: List[Dict], resistance_levels: List[Dict]) -> Dict:
    """Convert support/resistance levels to mplfinance hlines dict.

    Parameters
    ----------
    support_levels : List[Dict]
        Support levels from indicators.support_resistance.detect_support_resistance()
        Each dict has keys: price, strength, touches, last_touch_ago
    resistance_levels : List[Dict]
        Resistance levels with same structure

    Returns
    -------
    Dict
        hlines parameter for mplfinance.plot() with format:
        {'s0': dict(y=price, color='#4CAF50', linestyle='-', linewidth=2), ...}

    Examples
    --------
    >>> support = [{'price': 100.0, 'strength': 75.0, 'touches': 3}]
    >>> resistance = [{'price': 110.0, 'strength': 85.0, 'touches': 5}]
    >>> hlines = apply_sr_lines(support, resistance)
    >>> mpf.plot(df, hlines=hlines)
    """
    hlines = {}

    # Add support levels (green lines)
    for i, level in enumerate(support_levels):
        price = level.get("price", 0)
        strength = level.get("strength", 50)
        if price > 0:
            # Thicker lines for stronger levels
            linewidth = 2 + min(strength / 50, 2)
            hlines[f"s{i}"] = dict(
                y=price,
                color=INDICATOR_COLORS["support"],
                linestyle="-",
                linewidth=linewidth,
                alpha=0.7,
            )

    # Add resistance levels (red lines)
    for i, level in enumerate(resistance_levels):
        price = level.get("price", 0)
        strength = level.get("strength", 50)
        if price > 0:
            linewidth = 2 + min(strength / 50, 2)
            hlines[f"r{i}"] = dict(
                y=price,
                color=INDICATOR_COLORS["resistance"],
                linestyle="-",
                linewidth=linewidth,
                alpha=0.7,
            )

    return hlines


def add_indicator_panels(df, indicators: Optional[List[str]] = None):
    """Create mplfinance addplot list for multi-panel indicator layout.

    Parameters
    ----------
    df : pandas.DataFrame
        OHLCV data with DatetimeIndex. Must contain indicator columns
        if requesting indicators (vwap, rsi, macd, macd_signal, bb_upper, etc.)
    indicators : Optional[List[str]]
        List of indicator names to display. Supported values:
        'vwap', 'rsi', 'macd', 'bollinger'

    Returns
    -------
    List
        List of mplfinance.make_addplot() objects for multi-panel display

    Examples
    --------
    >>> df['vwap'] = calculate_vwap(df)
    >>> df['rsi'] = calculate_rsi(df['Close'])
    >>> apds = add_indicator_panels(df, indicators=['vwap', 'rsi'])
    >>> mpf.plot(df, addplot=apds, panel_ratios=(6, 1.5))
    """
    if indicators is None:
        indicators = []

    try:
        import mplfinance as mpf
    except Exception:
        return []

    apds = []
    panel_num = 0

    # VWAP overlay on price panel (panel 0)
    if "vwap" in indicators and "vwap" in df.columns:
        try:
            apds.append(
                mpf.make_addplot(
                    df["vwap"],
                    panel=0,
                    color=INDICATOR_COLORS["vwap"],
                    width=2,
                    label="VWAP",
                )
            )
        except Exception as err:
            log.warning("vwap_addplot_failed err=%s", str(err))

    # Bollinger Bands overlay on price panel (panel 0)
    if "bollinger" in indicators:
        if "bb_upper" in df.columns:
            try:
                apds.append(
                    mpf.make_addplot(
                        df["bb_upper"],
                        panel=0,
                        color=INDICATOR_COLORS["bb_upper"],
                        linestyle="--",
                        width=1,
                        alpha=0.7,
                    )
                )
            except Exception:
                pass
        if "bb_lower" in df.columns:
            try:
                apds.append(
                    mpf.make_addplot(
                        df["bb_lower"],
                        panel=0,
                        color=INDICATOR_COLORS["bb_lower"],
                        linestyle="--",
                        width=1,
                        alpha=0.7,
                    )
                )
            except Exception:
                pass
        if "bb_middle" in df.columns:
            try:
                apds.append(
                    mpf.make_addplot(
                        df["bb_middle"],
                        panel=0,
                        color=INDICATOR_COLORS["bb_middle"],
                        width=1,
                        alpha=0.5,
                    )
                )
            except Exception:
                pass

    # RSI panel (panel 2 - panel 1 is volume)
    if "rsi" in indicators and "rsi" in df.columns:
        panel_num = 2
        try:
            apds.append(
                mpf.make_addplot(
                    df["rsi"],
                    panel=panel_num,
                    color=INDICATOR_COLORS["rsi"],
                    ylabel="RSI",
                    ylim=(0, 100),
                    width=2,
                )
            )
        except Exception as err:
            log.warning("rsi_addplot_failed err=%s", str(err))

    # MACD panel (panel 3 if RSI exists, else panel 2 - panel 1 is volume)
    if "macd" in indicators:
        if "rsi" in indicators and "rsi" in df.columns:
            panel_num = 3
        else:
            panel_num = 2

        if "macd" in df.columns:
            try:
                apds.append(
                    mpf.make_addplot(
                        df["macd"],
                        panel=panel_num,
                        color=INDICATOR_COLORS["macd_line"],
                        ylabel="MACD",
                        width=2,
                    )
                )
            except Exception:
                pass
        if "macd_signal" in df.columns:
            try:
                apds.append(
                    mpf.make_addplot(
                        df["macd_signal"],
                        panel=panel_num,
                        color=INDICATOR_COLORS["macd_signal"],
                        width=2,
                    )
                )
            except Exception:
                pass

    return apds


def add_poc_vah_val_lines(ax, df, ticker):
    """Add POC/VAH/VAL horizontal lines to price chart.

    POC = Point of Control (highest volume price)
    VAH/VAL = Value Area bounds (70% of volume)

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Price panel axis to add lines to
    df : pandas.DataFrame
        OHLCV data with Close and Volume columns
    ticker : str
        Ticker symbol for logging

    Notes
    -----
    Lines are drawn using ax.axhline() with different styles:
    - POC: Solid line, width=3, most prominent
    - VAH/VAL: Dashed lines, width=2, value area bounds
    """
    try:
        from .indicators.volume_profile import render_volume_profile_data

        # Validate Volume column
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            log.warning("volume_profile_no_volume ticker=%s", ticker)
            return

        # Calculate volume profile
        prices = df['Close'].values.tolist()
        volumes = df['Volume'].values.tolist()
        vp_data = render_volume_profile_data(prices, volumes, bins=20)

        poc = vp_data.get('poc')
        vah = vp_data.get('vah')
        val = vp_data.get('val')

        # Draw POC line (most important - thickest)
        if poc:
            ax.axhline(y=poc, color=INDICATOR_COLORS['volume_profile_poc'],
                       linestyle='-', linewidth=3, alpha=0.9, label=f'POC ${poc:.2f}')
            log.debug("poc_line_added ticker=%s price=%.2f", ticker, poc)

        # Draw VAH/VAL lines (value area bounds - dashed)
        if vah:
            ax.axhline(y=vah, color=INDICATOR_COLORS['volume_profile_vah'],
                       linestyle='--', linewidth=2, alpha=0.7, label=f'VAH ${vah:.2f}')
            log.debug("vah_line_added ticker=%s price=%.2f", ticker, vah)

        if val:
            ax.axhline(y=val, color=INDICATOR_COLORS['volume_profile_val'],
                       linestyle='--', linewidth=2, alpha=0.7, label=f'VAL ${val:.2f}')
            log.debug("val_line_added ticker=%s price=%.2f", ticker, val)

        if poc and vah and val:
            log.info("volume_profile_lines_added ticker=%s poc=%.2f vah=%.2f val=%.2f",
                     ticker, poc, vah, val)

    except Exception as err:
        log.warning("poc_vah_val_calc_failed ticker=%s err=%s", ticker, str(err))


def add_volume_profile_bars(ax, df, ticker, bins=20):
    """Add horizontal volume profile bars to right side of price chart.

    Creates WeBull-style volume profile visualization with horizontal bars
    showing volume distribution across price levels. High Volume Nodes (HVN)
    are colored green, Low Volume Nodes (LVN) are red, and regular bars are cyan.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Price panel axis to add volume bars to
    df : pandas.DataFrame
        OHLCV data with Close and Volume columns
    ticker : str
        Ticker symbol for logging
    bins : int, optional
        Number of price bins for volume profile calculation, by default 20

    Notes
    -----
    - Uses inset_axes to create a 15% wide panel on the right side
    - Bars are colored based on HVN/LVN classification
    - Transparent background to avoid obscuring price action
    - Bars are horizontally oriented (barh) spanning price levels

    Examples
    --------
    >>> fig, axes = mpf.plot(df, returnfig=True)
    >>> add_volume_profile_bars(axes[0], df, 'AAPL', bins=20)
    """
    try:
        from mpl_toolkits.axes_grid1.inset_locator import inset_axes
        from .indicators.volume_profile import render_volume_profile_data

        # Validate Volume column
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            log.warning("volume_profile_bars_no_volume ticker=%s", ticker)
            return

        # Calculate volume profile
        prices = df['Close'].values.tolist()
        volumes = df['Volume'].values.tolist()
        vp_data = render_volume_profile_data(prices, volumes, bins=bins)

        if not vp_data['horizontal_bars']:
            log.warning("volume_profile_no_bars ticker=%s", ticker)
            return

        # Extract bar data
        bar_prices = [bar['price'] for bar in vp_data['horizontal_bars']]
        bar_volumes = [bar['normalized_volume'] for bar in vp_data['horizontal_bars']]

        # Get HVN/LVN for coloring
        hvn_prices = {node['price'] for node in vp_data['hvn']}
        lvn_prices = {node['price'] for node in vp_data['lvn']}

        # Color bars based on HVN/LVN
        colors = []
        for price in bar_prices:
            if price in hvn_prices:
                colors.append(INDICATOR_COLORS['volume_profile_hvn'])
            elif price in lvn_prices:
                colors.append(INDICATOR_COLORS['volume_profile_lvn'])
            else:
                colors.append(INDICATOR_COLORS['volume_profile'])

        # Calculate bar height (distance between price levels)
        if len(bar_prices) > 1:
            bar_height = bar_prices[1] - bar_prices[0]
        else:
            bar_height = 1

        # Create inset axis on right side (15% of chart width)
        vp_ax = inset_axes(
            ax,
            width="15%",
            height="100%",
            loc='center right',
            bbox_to_anchor=(0.05, 0, 1, 1),
            bbox_transform=ax.transAxes,
            borderpad=0
        )

        # Draw horizontal bars
        vp_ax.barh(
            bar_prices,
            bar_volumes,
            height=bar_height * 0.95,  # Slight gap between bars
            color=colors,
            alpha=0.6,
            edgecolor='none'
        )

        # Hide VP axis labels and ticks
        vp_ax.set_xticks([])
        vp_ax.set_yticks([])
        vp_ax.set_facecolor('none')
        vp_ax.patch.set_alpha(0)

        # Remove axis spines
        for spine in vp_ax.spines.values():
            spine.set_visible(False)

        # Match price panel y-limits
        vp_ax.set_ylim(ax.get_ylim())

        log.info(
            "volume_profile_bars_added ticker=%s bars=%d hvn=%d lvn=%d",
            ticker, len(bar_prices), len(hvn_prices), len(lvn_prices)
        )

    except Exception as err:
        log.warning("volume_profile_bars_failed ticker=%s err=%s", ticker, str(err))


def add_triangle_patterns(ax, df, ticker):
    """
    Detect and overlay triangle patterns on price chart.

    Draws trendlines for detected triangles with pattern-specific colors.
    Adds text annotations showing pattern type and breakout direction.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Price panel axis to add patterns to
    df : pandas.DataFrame
        OHLCV data with Close, High, and Low columns
    ticker : str
        Ticker symbol for logging

    Notes
    -----
    Triangle patterns include:
    - Ascending: Flat resistance, rising support (bullish)
    - Descending: Falling resistance, flat support (bearish)
    - Symmetrical: Converging lines (neutral until breakout)

    Each pattern includes:
    - Upper trendline (resistance)
    - Lower trendline (support)
    - Text annotation with pattern name and confidence
    """
    try:
        from .indicators.patterns import detect_triangles

        # Validate required columns
        if not all(col in df.columns for col in ['Close', 'High', 'Low']):
            log.warning("triangle_patterns_missing_columns ticker=%s", ticker)
            return

        # Extract price data as lists
        prices = df['Close'].values.tolist()
        highs = df['High'].values.tolist()
        lows = df['Low'].values.tolist()

        # Detect patterns
        patterns = detect_triangles(prices, highs, lows, min_touches=3, lookback=20)

        if not patterns:
            log.debug("triangle_patterns_none_detected ticker=%s", ticker)
            return

        # Get x-axis indices for plotting
        x_values = list(range(len(df)))

        # Draw each detected pattern
        for pattern in patterns:
            pattern_type = pattern.get('type', 'unknown')
            start_idx = pattern.get('start_idx', 0)
            end_idx = pattern.get('end_idx', len(df) - 1)
            confidence = pattern.get('confidence', 0.0)
            key_levels = pattern.get('key_levels', {})

            # Select color based on pattern type
            if pattern_type == 'ascending_triangle':
                color = INDICATOR_COLORS['triangle_ascending']
                label = f'Ascending Triangle ({confidence:.0%})'
            elif pattern_type == 'descending_triangle':
                color = INDICATOR_COLORS['triangle_descending']
                label = f'Descending Triangle ({confidence:.0%})'
            elif pattern_type == 'symmetrical_triangle':
                color = INDICATOR_COLORS['triangle_symmetrical']
                label = f'Symmetrical Triangle ({confidence:.0%})'
            else:
                color = '#FFFFFF'
                label = f'Triangle Pattern ({confidence:.0%})'

            # Calculate trendlines
            pattern_x = x_values[start_idx:end_idx + 1]

            # For ascending triangle: flat resistance, rising support
            if pattern_type == 'ascending_triangle':
                resistance = key_levels.get('resistance', 0)
                support_slope = key_levels.get('support_slope', 0)

                # Draw flat resistance line
                ax.hlines(
                    y=resistance,
                    xmin=start_idx,
                    xmax=end_idx,
                    colors=color,
                    linestyles='--',
                    linewidth=2,
                    alpha=0.8
                )

                # Draw rising support line (use linear approximation)
                # Start from first low in pattern area
                support_start = lows[start_idx]
                support_end = support_start + support_slope * (end_idx - start_idx)
                ax.plot(
                    [start_idx, end_idx],
                    [support_start, support_end],
                    color=color,
                    linestyle='--',
                    linewidth=2,
                    alpha=0.8
                )

                # Add annotation at midpoint
                mid_idx = (start_idx + end_idx) // 2
                mid_price = (resistance + support_start + support_slope * (mid_idx - start_idx)) / 2
                ax.text(
                    mid_idx,
                    mid_price,
                    label,
                    fontsize=9,
                    color=color,
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                    ha='center'
                )

            # For descending triangle: falling resistance, flat support
            elif pattern_type == 'descending_triangle':
                support = key_levels.get('support', 0)
                resistance_slope = key_levels.get('resistance_slope', 0)

                # Draw flat support line
                ax.hlines(
                    y=support,
                    xmin=start_idx,
                    xmax=end_idx,
                    colors=color,
                    linestyles='--',
                    linewidth=2,
                    alpha=0.8
                )

                # Draw falling resistance line
                resistance_start = highs[start_idx]
                resistance_end = resistance_start + resistance_slope * (end_idx - start_idx)
                ax.plot(
                    [start_idx, end_idx],
                    [resistance_start, resistance_end],
                    color=color,
                    linestyle='--',
                    linewidth=2,
                    alpha=0.8
                )

                # Add annotation at midpoint
                mid_idx = (start_idx + end_idx) // 2
                mid_price = (support + resistance_start + resistance_slope * (mid_idx - start_idx)) / 2
                ax.text(
                    mid_idx,
                    mid_price,
                    label,
                    fontsize=9,
                    color=color,
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                    ha='center'
                )

            # For symmetrical triangle: converging lines
            elif pattern_type == 'symmetrical_triangle':
                high_slope = key_levels.get('high_slope', 0)
                low_slope = key_levels.get('low_slope', 0)

                # Draw upper trendline (falling)
                upper_start = highs[start_idx]
                upper_end = upper_start + high_slope * (end_idx - start_idx)
                ax.plot(
                    [start_idx, end_idx],
                    [upper_start, upper_end],
                    color=color,
                    linestyle='--',
                    linewidth=2,
                    alpha=0.8
                )

                # Draw lower trendline (rising)
                lower_start = lows[start_idx]
                lower_end = lower_start + low_slope * (end_idx - start_idx)
                ax.plot(
                    [start_idx, end_idx],
                    [lower_start, lower_end],
                    color=color,
                    linestyle='--',
                    linewidth=2,
                    alpha=0.8
                )

                # Add annotation at midpoint
                mid_idx = (start_idx + end_idx) // 2
                mid_upper = upper_start + high_slope * (mid_idx - start_idx)
                mid_lower = lower_start + low_slope * (mid_idx - start_idx)
                mid_price = (mid_upper + mid_lower) / 2
                ax.text(
                    mid_idx,
                    mid_price,
                    label,
                    fontsize=9,
                    color=color,
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                    ha='center'
                )

        log.info("triangle_patterns_added ticker=%s count=%d", ticker, len(patterns))

    except Exception as err:
        log.warning("triangle_patterns_failed ticker=%s err=%s", ticker, str(err))


def add_hs_patterns(ax, df, ticker):
    """
    Detect and overlay Head & Shoulders patterns on price chart.

    Marks:
    - Left shoulder, head, right shoulder (circle markers)
    - Neckline (horizontal line)
    - Breakout projection (dashed line)

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Price panel axis to add patterns to
    df : pandas.DataFrame
        OHLCV data with Close column
    ticker : str
        Ticker symbol for logging

    Notes
    -----
    Head & Shoulders patterns include:
    - Classic H&S: Bearish reversal pattern (three peaks, middle highest)
    - Inverse H&S: Bullish reversal pattern (three troughs, middle lowest)

    Each pattern includes:
    - Shoulder and head markers (circles)
    - Neckline (horizontal gold line)
    - Text annotation with pattern name and confidence
    - Price target projection
    """
    try:
        from .indicators.patterns import detect_head_shoulders

        # Validate required columns
        if 'Close' not in df.columns:
            log.warning("hs_patterns_missing_columns ticker=%s", ticker)
            return

        # Extract price data as list
        prices = df['Close'].values.tolist()

        # Detect patterns
        patterns = detect_head_shoulders(prices, min_confidence=0.6, lookback=30)

        if not patterns:
            log.debug("hs_patterns_none_detected ticker=%s", ticker)
            return

        # Get x-axis indices for plotting
        x_values = list(range(len(df)))

        # Draw each detected pattern
        for pattern in patterns:
            pattern_type = pattern.get('type', 'unknown')
            confidence = pattern.get('confidence', 0.0)
            key_levels = pattern.get('key_levels', {})
            target = pattern.get('target', None)

            # Extract shoulder and head positions
            ls_idx, ls_price = key_levels.get('left_shoulder', (0, 0))
            head_idx, head_price = key_levels.get('head', (0, 0))
            rs_idx, rs_price = key_levels.get('right_shoulder', (0, 0))
            neckline = key_levels.get('neckline', 0)

            # Select color based on pattern type
            if pattern_type == 'head_shoulders':
                color = INDICATOR_COLORS['hs_pattern']
                label = f'H&S ({confidence:.0%})'
            elif pattern_type == 'inverse_head_shoulders':
                color = INDICATOR_COLORS['hs_pattern']
                label = f'Inverse H&S ({confidence:.0%})'
            else:
                color = '#FFFFFF'
                label = f'H&S Pattern ({confidence:.0%})'

            # Mark left shoulder
            ax.scatter(
                ls_idx,
                ls_price,
                color=color,
                s=100,
                alpha=0.8,
                marker='o',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Mark head
            ax.scatter(
                head_idx,
                head_price,
                color=color,
                s=150,
                alpha=0.8,
                marker='o',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Mark right shoulder
            ax.scatter(
                rs_idx,
                rs_price,
                color=color,
                s=100,
                alpha=0.8,
                marker='o',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Draw neckline
            ax.hlines(
                y=neckline,
                xmin=ls_idx,
                xmax=rs_idx,
                colors=INDICATOR_COLORS['hs_neckline'],
                linestyles='-',
                linewidth=2.5,
                alpha=0.8,
                zorder=4
            )

            # Draw projected target if available
            if target:
                ax.hlines(
                    y=target,
                    xmin=rs_idx,
                    xmax=min(rs_idx + (rs_idx - ls_idx), len(df) - 1),
                    colors=color,
                    linestyles='--',
                    linewidth=2,
                    alpha=0.6,
                    zorder=3
                )

            # Add annotation at head position
            ax.text(
                head_idx,
                head_price + (head_price * 0.02),  # Slightly above head
                label,
                fontsize=9,
                color=color,
                bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                ha='center'
            )

        log.info("hs_patterns_added ticker=%s count=%d", ticker, len(patterns))

    except Exception as err:
        log.warning("hs_patterns_failed ticker=%s err=%s", ticker, str(err))


def add_double_patterns(ax, df, ticker):
    """
    Detect and overlay Double Top/Bottom patterns on price chart.

    Marks:
    - Two peaks/troughs (circles)
    - Support/resistance line between them
    - Breakout projection

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Price panel axis to add patterns to
    df : pandas.DataFrame
        OHLCV data with Close column
    ticker : str
        Ticker symbol for logging

    Notes
    -----
    Double patterns include:
    - Double Top: Bearish reversal (two peaks at similar levels)
    - Double Bottom: Bullish reversal (two troughs at similar levels)

    Each pattern includes:
    - Peak/trough markers (circles)
    - Support/resistance line
    - Text annotation with pattern name and confidence
    - Price target projection
    """
    try:
        from .indicators.patterns import detect_double_tops_bottoms

        # Validate required columns
        if 'Close' not in df.columns:
            log.warning("double_patterns_missing_columns ticker=%s", ticker)
            return

        # Extract price data as list
        prices = df['Close'].values.tolist()

        # Detect patterns
        all_patterns = detect_double_tops_bottoms(
            prices,
            tolerance=0.02,
            min_spacing=5,
            lookback=30
        )

        if not all_patterns:
            log.debug("double_patterns_none_detected ticker=%s", ticker)
            return

        # Separate tops and bottoms
        tops = [p for p in all_patterns if p.get('type') == 'double_top']
        bottoms = [p for p in all_patterns if p.get('type') == 'double_bottom']

        # Draw double tops in red
        for pattern in tops:
            confidence = pattern.get('confidence', 0.0)
            key_levels = pattern.get('key_levels', {})
            target = pattern.get('target', None)

            # Extract peak positions
            peak1_idx, peak1_price = key_levels.get('peak1', (0, 0))
            peak2_idx, peak2_price = key_levels.get('peak2', (0, 0))
            trough_idx, trough_price = key_levels.get('trough', (0, 0))

            color = INDICATOR_COLORS['double_top']
            label = f'Double Top ({confidence:.0%})'

            # Mark first peak
            ax.scatter(
                peak1_idx,
                peak1_price,
                color=color,
                s=120,
                alpha=0.8,
                marker='v',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Mark second peak
            ax.scatter(
                peak2_idx,
                peak2_price,
                color=color,
                s=120,
                alpha=0.8,
                marker='v',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Draw resistance line between peaks
            ax.hlines(
                y=(peak1_price + peak2_price) / 2,
                xmin=peak1_idx,
                xmax=peak2_idx,
                colors=color,
                linestyles='-',
                linewidth=2.5,
                alpha=0.7,
                zorder=4
            )

            # Draw support line at trough
            ax.hlines(
                y=trough_price,
                xmin=peak1_idx,
                xmax=peak2_idx,
                colors=color,
                linestyles='--',
                linewidth=2,
                alpha=0.5,
                zorder=3
            )

            # Draw projected target if available
            if target:
                ax.hlines(
                    y=target,
                    xmin=peak2_idx,
                    xmax=min(peak2_idx + (peak2_idx - peak1_idx), len(df) - 1),
                    colors=color,
                    linestyles='--',
                    linewidth=2,
                    alpha=0.6,
                    zorder=3
                )

            # Add annotation at midpoint
            mid_idx = (peak1_idx + peak2_idx) // 2
            mid_price = (peak1_price + peak2_price) / 2
            ax.text(
                mid_idx,
                mid_price + (mid_price * 0.02),
                label,
                fontsize=9,
                color=color,
                bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                ha='center'
            )

        # Draw double bottoms in green
        for pattern in bottoms:
            confidence = pattern.get('confidence', 0.0)
            key_levels = pattern.get('key_levels', {})
            target = pattern.get('target', None)

            # Extract trough positions
            trough1_idx, trough1_price = key_levels.get('trough1', (0, 0))
            trough2_idx, trough2_price = key_levels.get('trough2', (0, 0))
            peak_idx, peak_price = key_levels.get('peak', (0, 0))

            color = INDICATOR_COLORS['double_bottom']
            label = f'Double Bottom ({confidence:.0%})'

            # Mark first trough
            ax.scatter(
                trough1_idx,
                trough1_price,
                color=color,
                s=120,
                alpha=0.8,
                marker='^',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Mark second trough
            ax.scatter(
                trough2_idx,
                trough2_price,
                color=color,
                s=120,
                alpha=0.8,
                marker='^',
                edgecolors='white',
                linewidths=1.5,
                zorder=5
            )

            # Draw support line between troughs
            ax.hlines(
                y=(trough1_price + trough2_price) / 2,
                xmin=trough1_idx,
                xmax=trough2_idx,
                colors=color,
                linestyles='-',
                linewidth=2.5,
                alpha=0.7,
                zorder=4
            )

            # Draw resistance line at peak
            ax.hlines(
                y=peak_price,
                xmin=trough1_idx,
                xmax=trough2_idx,
                colors=color,
                linestyles='--',
                linewidth=2,
                alpha=0.5,
                zorder=3
            )

            # Draw projected target if available
            if target:
                ax.hlines(
                    y=target,
                    xmin=trough2_idx,
                    xmax=min(trough2_idx + (trough2_idx - trough1_idx), len(df) - 1),
                    colors=color,
                    linestyles='--',
                    linewidth=2,
                    alpha=0.6,
                    zorder=3
                )

            # Add annotation at midpoint
            mid_idx = (trough1_idx + trough2_idx) // 2
            mid_price = (trough1_price + trough2_price) / 2
            ax.text(
                mid_idx,
                mid_price - (mid_price * 0.02),  # Slightly below for bottoms
                label,
                fontsize=9,
                color=color,
                bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                ha='center'
            )

        log.info(
            "double_patterns_added ticker=%s tops=%d bottoms=%d",
            ticker,
            len(tops),
            len(bottoms)
        )

    except Exception as err:
        log.warning("double_patterns_failed ticker=%s err=%s", ticker, str(err))


def detect_gaps(df, expected_interval_minutes=15):
    """Detect time gaps in DataFrame index (missing candles).

    Identifies periods where data is missing based on expected time intervals.
    Distinguishes between market closed periods (weekends, holidays) and
    data gaps during trading hours that should be filled.

    Parameters
    ----------
    df : pandas.DataFrame
        OHLCV data with DatetimeIndex
    expected_interval_minutes : int, optional
        Expected time interval between candles in minutes, by default 15

    Returns
    -------
    List[Tuple[pd.Timestamp, pd.Timestamp, float]]
        List of gaps as (start_time, end_time, duration_minutes) tuples

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({'Close': [100, 101, 102]},
    ...                   index=pd.to_datetime(['2024-01-01 09:30', '2024-01-01 09:45', '2024-01-01 10:15']))
    >>> gaps = detect_gaps(df, expected_interval_minutes=15)
    >>> len(gaps)
    1
    """
    try:
        import pandas as pd

        gaps = []
        if df is None or df.empty or len(df) < 2:
            return gaps

        # Allow 50% tolerance for interval detection (e.g., 15min → 22.5min max)
        max_gap_minutes = expected_interval_minutes * 1.5

        for i in range(1, len(df)):
            time_diff_seconds = (df.index[i] - df.index[i - 1]).total_seconds()
            time_diff_minutes = time_diff_seconds / 60

            if time_diff_minutes > max_gap_minutes:
                gaps.append((df.index[i - 1], df.index[i], time_diff_minutes))
                log.debug(
                    "gap_detected start=%s end=%s duration_min=%.1f",
                    df.index[i - 1],
                    df.index[i],
                    time_diff_minutes,
                )

        return gaps
    except Exception as err:
        log.warning("gap_detection_failed err=%s", str(err))
        return []


def fill_gaps(df, method="forward_fill", expected_interval_minutes=15):
    """Fill gaps in OHLCV data with appropriate values.

    Fills missing time periods in the data to create smooth visualizations
    without confusing gaps. Uses forward fill (last known price) by default,
    with volume set to 0 for filled periods.

    Parameters
    ----------
    df : pandas.DataFrame
        OHLCV data with DatetimeIndex (must have Open, High, Low, Close, Volume columns)
    method : str, optional
        Fill method: "forward_fill", "interpolate", or "flat_line", by default "forward_fill"
    expected_interval_minutes : int, optional
        Expected time interval between candles in minutes, by default 15

    Returns
    -------
    pandas.DataFrame
        DataFrame with gaps filled, includes new 'filled' boolean column marking filled rows

    Notes
    -----
    - Forward fill: Uses last known OHLC prices, sets volume to 0
    - Interpolate: Linear interpolation for prices (experimental, use with caution)
    - Flat line: Same as forward fill but can be styled differently

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({'Open': [100, 102], 'High': [101, 103], 'Low': [99, 101],
    ...                    'Close': [100, 102], 'Volume': [1000, 1500]},
    ...                   index=pd.to_datetime(['2024-01-01 09:30', '2024-01-01 10:15']))
    >>> filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)
    >>> len(filled) > len(df)
    True
    """
    try:
        import pandas as pd

        if df is None or df.empty:
            return df

        # Detect gaps first
        gaps = detect_gaps(df, expected_interval_minutes)

        if not gaps:
            # No gaps, add 'filled' column as False for all rows
            df["filled"] = False
            return df

        log.info(
            "filling_gaps count=%d method=%s interval_min=%d",
            len(gaps),
            method,
            expected_interval_minutes,
        )

        # Create complete date range with expected frequency
        freq_str = f"{expected_interval_minutes}min"
        full_range = pd.date_range(
            start=df.index.min(), end=df.index.max(), freq=freq_str
        )

        # Reindex to full range
        df_filled = df.reindex(full_range)

        # Mark originally filled vs new rows
        df_filled["filled"] = df_filled["Close"].isna()

        if method == "forward_fill":
            # Forward fill OHLC prices (use last known price)
            df_filled[["Open", "High", "Low", "Close"]] = df_filled[
                ["Open", "High", "Low", "Close"]
            ].ffill()

            # Set volume to 0 for filled periods (don't fabricate volume)
            df_filled.loc[df_filled["filled"], "Volume"] = 0.0

        elif method == "interpolate":
            # Linear interpolation for price (experimental)
            df_filled["Close"] = df_filled["Close"].interpolate(method="linear")
            df_filled["Open"] = df_filled["Open"].interpolate(method="linear")
            df_filled["High"] = df_filled["High"].interpolate(method="linear")
            df_filled["Low"] = df_filled["Low"].interpolate(method="linear")

            # Set volume to 0 for filled periods
            df_filled.loc[df_filled["filled"], "Volume"] = 0.0

        elif method == "flat_line":
            # Same as forward_fill (can be styled differently in visualization)
            df_filled[["Open", "High", "Low", "Close"]] = df_filled[
                ["Open", "High", "Low", "Close"]
            ].ffill()
            df_filled.loc[df_filled["filled"], "Volume"] = 0.0

        # Fill any remaining NaNs (edge cases)
        df_filled = df_filled.ffill().bfill()

        log.info(
            "gaps_filled original_rows=%d filled_rows=%d new_rows=%d",
            len(df),
            len(df_filled),
            len(df_filled) - len(df),
        )

        return df_filled

    except Exception as err:
        log.warning("gap_filling_failed err=%s", str(err))
        # Return original df with filled column set to False
        df["filled"] = False
        return df


def optimize_for_mobile(fig, axes):
    """Optimize chart for mobile display (320px minimum width).

    Ensures text remains readable at small screen sizes by adjusting
    spacing, tick density, and label formatting.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure object from mplfinance.plot(returnfig=True)
    axes : list
        List of axis objects from mplfinance.plot(returnfig=True)

    Notes
    -----
    This modifies the figure in-place. Call before saving.
    """
    try:
        from matplotlib.ticker import MaxNLocator

        # Reduce number of x-axis ticks for readability
        for ax in axes:
            if hasattr(ax, "xaxis"):
                ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
            if hasattr(ax, "yaxis"):
                ax.yaxis.set_major_locator(MaxNLocator(nbins=8))

        # Adjust spacing to prevent label overlap
        fig.tight_layout(pad=1.5)
    except Exception as err:
        log.warning("mobile_optimize_failed err=%s", str(err))


def render_chart_with_panels(
    ticker: str,
    df,
    indicators: Optional[List[str]] = None,
    support_levels: Optional[List[Dict]] = None,
    resistance_levels: Optional[List[Dict]] = None,
    fib_levels: Optional[Dict[str, float]] = None,
    out_dir: Path | str = "out/charts",
) -> Optional[Path]:
    """Render multi-panel chart with WeBull styling and indicators.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    df : pandas.DataFrame
        OHLCV data with DatetimeIndex
    indicators : Optional[List[str]]
        Indicators to display: ['vwap', 'rsi', 'macd', 'bollinger', 'fibonacci']
    support_levels : Optional[List[Dict]]
        Support levels from detect_support_resistance()
    resistance_levels : Optional[List[Dict]]
        Resistance levels from detect_support_resistance()
    fib_levels : Optional[Dict[str, float]]
        Fibonacci retracement levels from calculate_fibonacci_levels()
    out_dir : Path | str
        Output directory for chart PNG

    Returns
    -------
    Optional[Path]
        Path to generated chart PNG or None on failure

    Examples
    --------
    >>> df = market.get_intraday('AAPL')
    >>> path = render_chart_with_panels('AAPL', df, indicators=['vwap', 'rsi'])
    """
    if not CHARTS_OK:
        log.info("charts_skip reason=deps_missing")
        return None

    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import mplfinance as mpf
        from matplotlib import pyplot as plt
    except Exception as err:
        log.info("charts_import_failed err=%s", str(err))
        return None

    # Create output directory
    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    sym = (ticker or "").strip().upper()
    if not sym:
        return None

    indicators = indicators or []
    support_levels = support_levels or []
    resistance_levels = resistance_levels or []
    fib_levels = fib_levels or {}

    try:
        # Validate DataFrame
        if df is None or getattr(df, "empty", False):
            raise ValueError("no_data")

        # Apply gap filling if enabled
        fill_enabled = os.getenv("CHART_FILL_EXTENDED_HOURS", "1") == "1"
        if fill_enabled and len(df) > 1:
            fill_method = os.getenv("CHART_FILL_METHOD", "forward_fill")
            # Determine interval from index (5min, 15min, etc.)
            try:
                import pandas as pd
                if len(df) >= 2:
                    time_diff = (df.index[1] - df.index[0]).total_seconds() / 60
                    expected_interval = int(time_diff)
                    df = fill_gaps(df, method=fill_method, expected_interval_minutes=expected_interval)
                    log.debug("gap_filling_applied ticker=%s method=%s interval=%d", sym, fill_method, expected_interval)
            except Exception as err:
                log.warning("gap_filling_failed ticker=%s err=%s", sym, str(err))
                # Continue with original df
                pass

        # Create WeBull style
        webull_style = create_webull_style()

        # Build indicator panels
        apds = add_indicator_panels(df, indicators)

        # Build S/R lines
        hlines = apply_sr_lines(support_levels, resistance_levels)

        # Determine panel ratios based on indicators
        # Use chart_panels module if available for adaptive ratios
        if HAS_CHART_PANELS:
            panel_ratios = chart_panels.calculate_panel_ratios(indicators)
            log.debug("using_chart_panels_ratios ratios=%s", panel_ratios)
        else:
            # Fallback: manual calculation
            num_panels = 2  # price + volume (always present)
            if "rsi" in indicators and "rsi" in df.columns:
                num_panels += 1
            if "macd" in indicators and "macd" in df.columns:
                num_panels += 1

            # Build panel ratios to match actual panel count
            panel_ratios = [6, 1.5]  # price, volume
            if num_panels >= 3:
                panel_ratios.append(1.25)  # RSI
            if num_panels >= 4:
                panel_ratios.append(1.25)  # MACD

        # Determine candle type from environment (default: candle)
        # Options: candle, heikin-ashi, ohlc, line
        candle_type = os.getenv("CHART_CANDLE_TYPE", "candle").lower().strip()
        if candle_type not in ("candle", "heikin-ashi", "ohlc", "line"):
            log.warning(
                "invalid_candle_type value=%s defaulting to candle", candle_type
            )
            candle_type = "candle"

        # Render chart (only pass kwargs if they have values)
        plot_kwargs = {
            "type": candle_type,
            "style": webull_style,
            "volume": True,
            "panel_ratios": tuple(panel_ratios),
            "figsize": (16, 10),
            "returnfig": True,
        }

        # Only add addplot if we have plots
        if apds:
            plot_kwargs["addplot"] = apds

        # Note: hlines parameter removed due to mplfinance validator issues
        # S/R lines will be added manually after chart creation

        fig, axes = mpf.plot(df, **plot_kwargs)

        # Add S/R lines manually using axhline (more reliable than hlines param)
        if hlines:
            try:
                # Get the price panel (panel 0)
                if hasattr(axes, "__iter__"):
                    price_ax = axes[0] if len(axes) > 0 else axes
                else:
                    price_ax = axes

                # Add each S/R line
                for key, val in hlines.items():
                    y_val = float(val["y"])
                    color = val.get("color", "#FFFFFF")
                    linestyle = val.get("linestyle", "--")
                    linewidth = val.get("linewidth", 1.5)
                    alpha = val.get("alpha", 0.7)

                    price_ax.axhline(
                        y=y_val,
                        color=color,
                        linestyle=linestyle,
                        linewidth=linewidth,
                        alpha=alpha,
                    )
                log.debug("added_sr_lines count=%d", len(hlines))
            except Exception as err:
                log.warning("sr_lines_failed err=%s", str(err))

        # Add Fibonacci retracement levels manually using axhline
        if fib_levels:
            try:
                # Get the price panel (panel 0)
                if hasattr(axes, "__iter__"):
                    price_ax = axes[0] if len(axes) > 0 else axes
                else:
                    price_ax = axes

                # Add each Fibonacci level as a horizontal line
                for level_name, price in fib_levels.items():
                    price_ax.axhline(
                        y=price,
                        color=INDICATOR_COLORS["fibonacci"],
                        linestyle="--",
                        linewidth=1.5,
                        alpha=0.6,
                        label=f"Fib {level_name}",
                    )
                log.info("fibonacci_lines_added ticker=%s count=%d", sym, len(fib_levels))
            except Exception as err:
                log.warning("fibonacci_lines_failed ticker=%s err=%s", sym, str(err))

        # Add triangle patterns if requested
        indicators_lower = [ind.lower() for ind in indicators]
        if "patterns" in indicators_lower or "triangles" in indicators_lower:
            try:
                # Get the price panel (panel 0)
                if hasattr(axes, "__iter__") and len(axes) > 0:
                    price_ax = axes[0]
                else:
                    price_ax = axes

                add_triangle_patterns(price_ax, df, sym)
            except Exception as err:
                log.warning("triangle_patterns_failed ticker=%s err=%s", sym, str(err))

        # Add Head & Shoulders and Double Top/Bottom patterns
        if "patterns" in indicators_lower or "hs" in indicators_lower:
            try:
                # Get the price panel (panel 0)
                if hasattr(axes, "__iter__") and len(axes) > 0:
                    price_ax = axes[0]
                else:
                    price_ax = axes

                add_hs_patterns(price_ax, df, sym)
                add_double_patterns(price_ax, df, sym)
            except Exception as err:
                log.warning("hs_double_patterns_failed ticker=%s err=%s", sym, str(err))

        # Add POC/VAH/VAL lines if requested
        show_poc = os.getenv("CHART_VOLUME_PROFILE_SHOW_POC", "1") == "1"

        log.debug("poc_vah_val_check ticker=%s indicators=%s show_poc=%s",
                  sym, indicators_lower, show_poc)

        if ('volume_profile' in indicators_lower or 'vp' in indicators_lower) and show_poc:
            log.debug("poc_vah_val_trigger ticker=%s", sym)
            try:
                if hasattr(axes, "__iter__") and len(axes) > 0:
                    price_ax = axes[0]
                else:
                    price_ax = axes

                add_poc_vah_val_lines(price_ax, df, sym)
            except Exception as err:
                log.warning("poc_vah_val_failed ticker=%s err=%s", sym, str(err))

        # Add volume profile horizontal bars if requested
        show_bars = os.getenv("CHART_VOLUME_PROFILE_SHOW_BARS", "1") == "1"
        if ('volume_profile' in indicators_lower or 'vp' in indicators_lower) and show_bars:
            try:
                if hasattr(axes, "__iter__") and len(axes) > 0:
                    price_ax = axes[0]
                else:
                    price_ax = axes

                bins = int(os.getenv("CHART_VOLUME_PROFILE_BINS", "20"))
                add_volume_profile_bars(price_ax, df, sym, bins=bins)
            except Exception as err:
                log.warning("volume_profile_bars_failed ticker=%s err=%s", sym, str(err))

        # Apply enhanced panel styling if chart_panels is available
        if HAS_CHART_PANELS:
            # Create panel configs for styling
            panel_configs = []
            panel_idx = 0

            # Price panel (always present)
            panel_configs.append(chart_panels.get_panel_config("price", panel_idx))
            panel_idx += 1

            # Volume panel (always present)
            panel_configs.append(chart_panels.get_panel_config("volume", panel_idx))
            panel_idx += 1

            # RSI panel if present
            if "rsi" in indicators and "rsi" in df.columns:
                panel_configs.append(chart_panels.get_panel_config("rsi", panel_idx))
                panel_idx += 1

            # MACD panel if present
            if "macd" in indicators and "macd" in df.columns:
                panel_configs.append(chart_panels.get_panel_config("macd", panel_idx))

            # Apply styling
            chart_panels.apply_panel_styling(fig, axes, panel_configs)
            log.debug("applied_panel_styling num_configs=%d", len(panel_configs))

        # Optimize for mobile
        optimize_for_mobile(fig, axes)

        # Save figure
        img_path = out_path / f"{sym}_panels.png"
        fig.savefig(img_path, format="png", bbox_inches="tight", dpi=100)
        plt.close(fig)

        log.info("chart_panels_saved ticker=%s path=%s", sym, img_path)
        return img_path

    except Exception as err:
        log.warning("chart_panels_failed ticker=%s err=%s", sym, str(err))
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _quickchart_url_yfinance(ticker: str, bars: int = 50) -> Optional[str]:
    """
    Build a QuickChart URL for a candlestick chart of the most recent
    intraday trading session.  When intraday data is unavailable, fall back
    to a daily line chart covering the past month.  This helper uses
    ``yfinance`` to download OHLC data and constructs a Chart.js
    configuration accordingly.  The resulting config is URL‑encoded and
    returned as a link to the QuickChart API.  If no data can be
    retrieved, ``None`` is returned.
    """
    log.info(
        "quickchart_yf_start ticker=%s bars=%d base=%s",
        ticker,
        bars,
        os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io"),
    )
    try:
        import json
        import urllib.parse

        import pandas as pd  # noqa: F401
        import yfinance as yf  # noqa: F401

        nt = (ticker or "").strip().upper()
        if not nt:
            return None

        # Helper to assemble a QuickChart URL from a Chart.js config.  Always
        # respect QUICKCHART_BASE_URL if provided; otherwise default to
        # https://quickchart.io/chart.  The config dict must be JSON‑serializable.
        def _encode_config(cfg: Dict[str, Any]) -> str:
            cfg_json = json.dumps(cfg, separators=(",", ":"))
            encoded = urllib.parse.quote(cfg_json, safe="")
            raw = os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io")
            base = raw.rstrip("/")
            chart_base = base if base.endswith("/chart") else f"{base}/chart"
            return f"{chart_base}?c={encoded}"

        # Attempt to fetch 1‑day, 5‑minute intraday data.  Explicitly disable
        # auto adjustment to avoid Series return types.  This call may
        # return an empty DataFrame for illiquid tickers or during extended
        # hours.
        data = yf.download(
            tickers=nt,
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=False,
        )
        dataset: list[Dict[str, Any]] = []
        if data is not None and not data.empty:
            df = data.tail(bars)
            for ts, row in df.iterrows():
                try:
                    x = ts.strftime("%Y-%m-%d %H:%M")

                    # Extract scalar values; handle Series fallback
                    def _scalar(val: Any) -> Any:
                        if hasattr(val, "iloc"):
                            try:
                                return val.iloc[0]
                            except Exception:
                                pass
                        return val

                    o = float(_scalar(row["Open"]))
                    h = float(_scalar(row["High"]))
                    low = float(_scalar(row["Low"]))
                    c = float(_scalar(row["Close"]))
                    dataset.append({"x": x, "o": o, "h": h, "l": low, "c": c})
                except Exception:
                    continue
        # Build candlestick config when intraday bars exist
        if dataset:
            cfg = {
                "type": "candlestick",
                "data": {"datasets": [{"label": nt, "data": dataset}]},
                "options": {
                    "title": {"display": True, "text": f"{nt} Intraday"},
                    "legend": {"display": False},
                    "layout": {
                        "padding": {"left": 0, "right": 0, "top": 0, "bottom": 0}
                    },
                },
            }
            return _encode_config(cfg)
        # Intraday failed: attempt daily close prices for the past month
        try:
            daily = yf.download(
                tickers=nt,
                period="1mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
            )
        except Exception:
            daily = None
        line_data: list[Dict[str, Any]] = []
        if daily is not None and not daily.empty:
            for ts, row in daily.iterrows():
                try:
                    # Use date string (without time) for the x‑axis
                    dstr = ts.strftime("%Y-%m-%d")
                    close = float(row["Close"])
                    line_data.append({"x": dstr, "y": close})
                except Exception:
                    continue
        if line_data:
            cfg = {
                "type": "line",
                "data": {"datasets": [{"label": nt, "data": line_data}]},
                "options": {
                    "title": {"display": True, "text": f"{nt} Daily"},
                    "legend": {"display": False},
                    "layout": {
                        "padding": {"left": 0, "right": 0, "top": 0, "bottom": 0}
                    },
                },
            }
            return _encode_config(cfg)
        return None
    except Exception:
        # Propagate as None on unexpected errors
        return None


def render_intraday_chart(
    ticker: str,
    out_dir: Path | str = "out/charts",
) -> Optional[Path]:
    """
    Render an intraday candlestick chart for the given ticker.

    When Matplotlib and mplfinance are available (see CHARTS_OK), this
    helper fetches recent intraday OHLC data via the market.get_intraday()
    helper and draws a candlestick chart using mplfinance.  A simple VWAP
    overlay is added when volume data is present.  The resulting PNG is
    saved to ``out_dir`` and the path is returned.

    If dependencies are missing or any error occurs, a placeholder file is
    created and returned instead.  On critical import failures, None is
    returned so callers can skip attachments entirely.
    """
    log.info(
        "charts_render_start ticker=%s CHARTS_OK=%s has_mpl=%s has_mpf=%s",
        ticker,
        (HAS_MATPLOTLIB and HAS_MPLFINANCE),
        HAS_MATPLOTLIB,
        HAS_MPLFINANCE,
    )
    # Respect dependency guard: skip entirely when chart libs are missing.
    if not CHARTS_OK:
        log.info(
            "charts_skip reason=deps_missing mpl=%s mpf=%s",
            HAS_MATPLOTLIB,
            HAS_MPLFINANCE,
        )
        return None

    # Do all heavy imports lazily inside the function to avoid startup cost.
    try:
        import matplotlib

        # Use a non-interactive backend; Agg works in headless environments.
        matplotlib.use("Agg", force=True)
        import mplfinance as mpf  # type: ignore
        from matplotlib import pyplot as plt  # type: ignore
    except Exception as err:
        # Log and skip chart generation if imports fail unexpectedly
        log.info("charts_import_failed err=%s", str(err))
        return None

    # Create output directory
    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If directory cannot be created, fallback to tmp
        return None

    # Normalize ticker
    sym = (ticker or "").strip().upper()
    if not sym:
        return None

    try:
        # Fetch a compact intraday dataset (5-minute bars) via market helper.
        # Import within the function to avoid circular imports at module load.
        import pandas as pd  # lazy import for datetime conversion

        from . import market

        # Try intraday data first (5-minute bars with pre/post market)
        df = market.get_intraday(
            sym, interval="5min", output_size="compact", prepost=True
        )
        try:
            log.info(
                "charts_render_df ticker=%s interval=5min rows=%s cols=%s",
                sym,
                getattr(df, "shape", ("-", "-"))[0],
                list(getattr(df, "columns", [])),
            )
        except Exception:
            pass

        # Fallback: If intraday data is empty, try daily data
        if df is None or getattr(df, "empty", False):
            log.info("charts_intraday_empty ticker=%s trying_daily_fallback", sym)
            df = market.get_intraday(
                sym, interval="1d", output_size="compact", prepost=False
            )
            try:
                log.info(
                    "charts_render_df ticker=%s interval=1d rows=%s cols=%s",
                    sym,
                    getattr(df, "shape", ("-", "-"))[0],
                    list(getattr(df, "columns", [])),
                )
            except Exception:
                pass

            # If daily also fails, give up
            if df is None or getattr(df, "empty", False):
                raise ValueError("no_chart_data_available")

        # Flatten MultiIndex columns if present (yfinance sometimes returns these)
        if hasattr(df.columns, 'levels'):
            # MultiIndex columns like ('Open', 'TICKER') -> 'Open'
            df.columns = df.columns.get_level_values(0)

        # Ensure the index is datetimes; mplfinance expects a DatetimeIndex
        # If the index isn't a DatetimeIndex, attempt to coerce
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass

        # Ensure required columns are numeric and clean
        required_cols = ['Open', 'High', 'Low', 'Close']
        for col in required_cols:
            if col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except Exception:
                    pass

        # Check if Volume column exists and is numeric
        has_volume = False
        if 'Volume' in df.columns:
            try:
                df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
                # Check if we have any valid volume data
                if df['Volume'].notna().any() and df['Volume'].sum() > 0:
                    has_volume = True
                    log.debug("charts_volume_available ticker=%s rows_with_vol=%d", sym, df['Volume'].notna().sum())
                else:
                    log.debug("charts_volume_empty ticker=%s", sym)
            except Exception as e:
                log.debug("charts_volume_parse_failed ticker=%s err=%s", sym, str(e))
        else:
            log.debug("charts_no_volume_column ticker=%s", sym)

        # Apply gap filling if enabled
        fill_enabled = os.getenv("CHART_FILL_EXTENDED_HOURS", "1") == "1"
        if fill_enabled and len(df) > 1:
            fill_method = os.getenv("CHART_FILL_METHOD", "forward_fill")
            # Determine interval from index (5min, 15min, etc.)
            try:
                import pandas as pd
                if len(df) >= 2:
                    time_diff = (df.index[1] - df.index[0]).total_seconds() / 60
                    expected_interval = int(time_diff)
                    df = fill_gaps(df, method=fill_method, expected_interval_minutes=expected_interval)
                    log.debug("gap_filling_applied ticker=%s method=%s interval=%d", sym, fill_method, expected_interval)
            except Exception as err:
                log.warning("gap_filling_failed ticker=%s err=%s", sym, str(err))
                # Continue with original df
                pass

        # Compute VWAP series for overlay when volume data is available
        vwap_series = None
        if has_volume:
            try:
                close = df["Close"]
                vol = df["Volume"]
                vol_total = vol.sum()
                if vol_total > 0:
                    vwap_series = (close * vol).cumsum() / vol.cumsum()
            except Exception:
                vwap_series = None

        # Compose additional plots: VWAP overlay if available
        add_plots = []
        if vwap_series is not None:
            try:
                add_plots.append(mpf.make_addplot(vwap_series, color="orange"))
            except Exception:
                pass

        # Generate candlestick chart with WeBull style
        # Check if WeBull style is enabled via environment
        use_webull = os.getenv("CHART_STYLE", "webull").lower() == "webull"
        chart_style = create_webull_style() if use_webull else "yahoo"

        # Determine candle type from environment (default: candle)
        # Options: candle, heikin-ashi, ohlc, line
        candle_type = os.getenv("CHART_CANDLE_TYPE", "candle").lower().strip()
        if candle_type not in ("candle", "heikin-ashi", "ohlc", "line"):
            log.warning(
                "invalid_candle_type value=%s defaulting to candle", candle_type
            )
            candle_type = "candle"

        try:
            # Build plot kwargs (conditionally include volume and addplot to avoid mplfinance validator errors)
            plot_kwargs = {
                "type": candle_type,
                "style": chart_style,
                "volume": has_volume,  # Only show volume subplot if we have volume data
                "returnfig": True,
                "figsize": (12, 7),
            }

            # Only add addplot if we have plots (avoids "None" validator error)
            if add_plots:
                plot_kwargs["addplot"] = add_plots

            fig, axes = mpf.plot(df, **plot_kwargs)
        except Exception as err:
            # Fallback: treat as failure and write placeholder
            raise err

        # Save figure as PNG
        img_path = out_path / f"{sym}.png"
        try:
            fig.savefig(img_path, format="png", bbox_inches="tight")
            plt.close(fig)
            return img_path
        except Exception as err:
            # If saving fails, fall through to placeholder
            raise err

    except Exception as err:
        # On any error, log and produce a simple placeholder
        try:
            placeholder_path = out_path / f"{sym}_placeholder.txt"
            placeholder_path.write_text("chart placeholder\n", encoding="utf-8")
            log.info("charts_render_failed ticker=%s err=%s", sym, str(err))
            return placeholder_path
        except Exception:
            # If even placeholder write fails, return None
            log.info("charts_render_failed_no_write ticker=%s err=%s", sym, str(err))
            return None


# ---------------------------------------------------------------------------
# QuickChart support


def _build_quickchart_config(dataset: list, ticker: str) -> Dict[str, Any]:
    """
    Construct a Chart.js configuration dictionary for a candlestick chart.

    Parameters
    ----------
    dataset : list
        A list of dictionaries with keys ``t``, ``o``, ``h``, ``l``, ``c``.
    ticker : str
        The primary ticker symbol used as the dataset label.

    Returns
    -------
    Dict[str, Any]
        A JSON‑serializable Chart.js configuration.
    """
    return {
        "type": "candlestick",
        "data": {
            "datasets": [
                {
                    "label": ticker,
                    "data": dataset,
                    # Set colours explicitly for up/down candles
                    "upColor": "#2ECC71",
                    "downColor": "#E74C3C",
                    "borderColor": "#999999",
                    "borderWidth": 1,
                }
            ]
        },
        "options": {
            "scales": {
                "x": {
                    "type": "timeseries",
                    "time": {"unit": "hour"},
                    "grid": {"display": False},
                    "display": True,
                },
                "y": {
                    "position": "right",
                    "display": True,
                },
            },
            "plugins": {
                "legend": {"display": False},
                "title": {"display": False},
            },
        },
    }


def get_quickchart_url(ticker: str, *, bars: int = 50) -> Optional[str]:
    """
    Generate a QuickChart image URL for a ticker using recent intraday data.

    This helper fetches up to ``bars`` most recent 5‑minute OHLC records for
    ``ticker`` via ``market.get_intraday()``.  It then builds a Chart.js
    configuration for a candlestick chart and URL‑encodes it for use with
    QuickChart’s image API.  If data is unavailable or an error occurs,
    returns ``None``.

    Note: The QuickChart API is accessed by the Discord client, not the bot
    itself, so no external HTTP request is made from this function.
    """
    base_env = os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io")
    log.info("quickchart_build_start ticker=%s bars=%d base=%s", ticker, bars, base_env)
    try:
        import pandas as pd

        from . import market  # lazy import to avoid circular deps

        nt = (ticker or "").strip().upper()
        if not nt:
            return None
        # Fetch compact intraday data (5‑minute bars).  Use a generous
        # output_size to ensure we have enough history.
        df = market.get_intraday(
            nt, interval="5min", output_size="compact", prepost=True
        )
        # If no intraday data is available from our primary providers, fall back to
        # a yfinance-based helper.  Some illiquid tickers lack recent 5‑minute
        # bars in the main feed; yfinance can often supply them.  See patch 03
        # notes for details.
        if df is None or getattr(df, "empty", False):
            try:
                return _quickchart_url_yfinance(nt, bars=bars)
            except Exception:
                return None
        # Ensure index is datetime for formatting
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                return None
        # Take the last ``bars`` rows for the chart
        tail = df.tail(bars)
        dataset: list = []
        for ts, row in tail.iterrows():
            try:
                # Extract individual OHLC values with descriptive variable names
                # Use .item() to extract scalar from pandas Series safely
                open_price = (
                    row["Open"].item()
                    if hasattr(row["Open"], "item")
                    else float(row["Open"])
                )
                high_price = (
                    row["High"].item()
                    if hasattr(row["High"], "item")
                    else float(row["High"])
                )
                low_price = (
                    row["Low"].item()
                    if hasattr(row["Low"], "item")
                    else float(row["Low"])
                )
                close_price = (
                    row["Close"].item()
                    if hasattr(row["Close"], "item")
                    else float(row["Close"])
                )
            except Exception:
                # Skip rows with missing or invalid data
                continue
            # Format timestamp as ISO 8601 for Chart.js (omit milliseconds)
            tstr = ts.strftime("%Y-%m-%dT%H:%M")
            dataset.append(
                {
                    "t": tstr,
                    "o": open_price,
                    "h": high_price,
                    "l": low_price,
                    "c": close_price,
                }
            )
        log.info("quickchart_dataset ticker=%s rows=%d", nt, len(dataset))
        if not dataset:
            log.info("quickchart_no_dataset ticker=%s", nt)
            return None
        cfg = _build_quickchart_config(dataset, nt)
        cfg_json = json.dumps(cfg, separators=(",", ":"))
        encoded = urllib.parse.quote(cfg_json, safe="")
        # Build base URL
        # Build base URL (normalize path so we always hit /chart)
        raw_base = os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io")
        base = raw_base.rstrip("/")
        chart_base = base if base.endswith("/chart") else f"{base}/chart"
        base_url = f"{chart_base}?c={encoded}"

        log.info("quickchart_cfg_len bytes=%d url_len=%d", len(cfg_json), len(base_url))

        # Decide whether to shorten the URL
        try:
            threshold = int(
                os.getenv("QUICKCHART_SHORTEN_THRESHOLD", "1900").strip() or 1900
            )
        except Exception:
            threshold = 1900
        try:
            if len(base_url) > threshold:
                # Use the QuickChart /create endpoints to shorten the config.
                import requests

                # Include API key in the request body when provided.  The
                # QUICKCHART_API_KEY improves rate limits on the hosted API.
                api_key = os.getenv("QUICKCHART_API_KEY")
                payload = {"chart": cfg}
                if api_key:
                    payload["key"] = api_key
                # Build potential /create endpoints based on the same base host.
                create_endpoints = []
                if base.endswith("/chart"):
                    # e.g., http://localhost:8080/chart/create
                    create_endpoints.append(f"{base}/create")
                    # e.g., http://localhost:8080/create (strip /chart)
                    parent = base.rsplit("/chart", 1)[0]
                    create_endpoints.append(f"{parent}/create")
                else:
                    # e.g., https://quickchart.io/chart/create
                    create_endpoints.append(f"{base}/chart/create")
                    # fallback /create at same root
                    create_endpoints.append(f"{base}/create")
                short_url = None
                for create_endpoint in create_endpoints:
                    try:
                        resp = requests.post(
                            create_endpoint,
                            json=payload,
                            timeout=10,
                        )
                        # Expect JSON {"success": true, "url": "https://..."}
                        if resp.ok:
                            try:
                                data = resp.json()
                            except Exception:
                                data = {}
                            url = data.get("url") or data.get("shortUrl") or None
                            if isinstance(url, str) and url.startswith("http"):
                                short_url = url
                                break
                    except Exception:
                        continue
                if short_url:
                    return short_url
        except Exception as e:
            # Fall back to original long URL on any failure
            log.warning("quickchart_create_failed err=%s", str(e))
        log.info("quickchart_return_base_url url_len=%d", len(base_url))
        return base_url
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Enhanced Multi-Panel Support with chart_panels Integration (Phase 3)


def render_multipanel_chart(
    ticker: str,
    timeframe: str = "1D",
    indicators: Optional[List[str]] = None,
    out_dir: Path | str = "out/charts",
) -> Optional[Path]:
    """
    Render a WeBull-style multi-panel chart using chart_panels configuration.

    This function provides enhanced multi-panel rendering that uses the
    chart_panels module for adaptive panel ratios, professional styling,
    and proper indicator placement according to WeBull standards.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol.
    timeframe : str, optional
        Chart timeframe (default: "1D").
    indicators : Optional[List[str]], optional
        List of indicator names to include. Supported values:
        - "vwap": Volume-Weighted Average Price
        - "bollinger"/"bb": Bollinger Bands
        - "rsi": Relative Strength Index
        - "macd": MACD with signal and histogram
        - "sr"/"support_resistance": Support/Resistance levels
        - "fibonacci"/"fib": Fibonacci retracements
        Default: ["vwap", "rsi", "macd"]
    out_dir : Path | str, optional
        Output directory for the chart image (default: "out/charts").

    Returns
    -------
    Optional[Path]
        Path to the generated chart PNG, or None on error.

    Examples
    --------
    >>> # Generate 4-panel chart with VWAP, RSI, and MACD
    >>> path = render_multipanel_chart("AAPL", indicators=["vwap", "rsi", "macd"])

    >>> # Generate 3-panel chart (price + volume + RSI only)
    >>> path = render_multipanel_chart("TSLA", indicators=["vwap", "rsi"])

    >>> # Generate 2-panel chart (price + volume only)
    >>> path = render_multipanel_chart("SPY", indicators=["vwap"])

    Notes
    -----
    - Panel ratios are calculated adaptively based on active indicators
    - Uses chart_panels module for configuration (see CHART_PANEL_RATIOS in .env)
    - RSI panel includes reference lines at 30 (oversold) and 70 (overbought)
    - MACD panel includes line, signal, and histogram
    - Support/Resistance levels are displayed as horizontal lines on price panel
    """
    log.info(
        "multipanel_enhanced_start ticker=%s timeframe=%s indicators=%s",
        ticker,
        timeframe,
        indicators,
    )

    # Check dependencies
    if not CHARTS_OK:
        log.info("multipanel_enhanced_skip reason=deps_missing")
        return None

    # Default indicators from environment or fallback
    if indicators is None:
        default_str = os.getenv("CHART_DEFAULT_INDICATORS", "vwap,rsi,macd")
        indicators = [ind.strip() for ind in default_str.split(",") if ind.strip()]

    # Use existing render_chart_with_panels which already has good implementation
    # Just need to fetch data and pass it through
    try:
        import pandas as pd

        from . import market

        # Normalize ticker
        sym = (ticker or "").strip().upper()
        if not sym:
            return None

        # Fetch intraday data
        df = market.get_intraday(
            sym, interval="5min", output_size="compact", prepost=True
        )
        if df is None or getattr(df, "empty", False):
            log.info("multipanel_enhanced_no_data ticker=%s", sym)
            return None

        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Calculate indicators and add to DataFrame
        indicators_lower = [ind.lower() for ind in indicators]

        # VWAP
        if "vwap" in indicators_lower:
            try:
                close = df["Close"]
                vol = df["Volume"]
                vol_total = vol.sum()
                if vol_total > 0:
                    df["vwap"] = (close * vol).cumsum() / vol.cumsum()
            except Exception as err:
                log.warning("vwap_calc_failed err=%s", str(err))

        # Bollinger Bands
        if "bollinger" in indicators_lower or "bb" in indicators_lower:
            try:
                from .indicators import calculate_bollinger_bands

                bb = calculate_bollinger_bands(df, period=20, std_dev=2)
                if bb:
                    df["bb_upper"] = bb["upper"]
                    df["bb_middle"] = bb["middle"]
                    df["bb_lower"] = bb["lower"]
            except Exception as err:
                log.warning("bb_calc_failed err=%s", str(err))

        # RSI
        if "rsi" in indicators_lower:
            try:
                delta = df["Close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df["rsi"] = 100 - (100 / (1 + rs))
            except Exception as err:
                log.warning("rsi_calc_failed err=%s", str(err))

        # MACD
        if "macd" in indicators_lower:
            try:
                ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
                ema_26 = df["Close"].ewm(span=26, adjust=False).mean()
                macd_line = ema_12 - ema_26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()

                df["macd"] = macd_line
                df["macd_signal"] = signal_line
                df["macd_histogram"] = macd_line - signal_line
            except Exception as err:
                log.warning("macd_calc_failed err=%s", str(err))

        # Support/Resistance
        support_levels = []
        resistance_levels = []
        if "sr" in indicators_lower or "support_resistance" in indicators_lower:
            try:
                from .indicators import detect_support_resistance

                sr = detect_support_resistance(df)
                if sr:
                    support_levels = sr.get("support", [])
                    resistance_levels = sr.get("resistance", [])
            except Exception as err:
                log.warning("sr_calc_failed err=%s", str(err))

        # Fibonacci Retracement Levels
        fib_levels = {}
        if "fibonacci" in indicators_lower or "fib" in indicators_lower:
            try:
                from .indicators.fibonacci import calculate_fibonacci_levels, find_swing_points

                # Find swing points from closing prices
                # Convert Series to list using .values.tolist() for compatibility
                close_prices = df["Close"].values.tolist() if hasattr(df["Close"], "values") else list(df["Close"])
                swing_high, swing_low, h_idx, l_idx = find_swing_points(close_prices)

                if swing_high and swing_low:
                    # Calculate Fibonacci levels
                    fib_levels = calculate_fibonacci_levels(swing_high, swing_low)
                    log.info(
                        "fibonacci_levels ticker=%s high=%.2f low=%.2f levels=%d",
                        sym,
                        swing_high,
                        swing_low,
                        len(fib_levels),
                    )
                else:
                    log.warning("fibonacci_no_swing_points ticker=%s", sym)
            except Exception as err:
                log.warning("fibonacci_calc_failed ticker=%s err=%s", sym, str(err))

        # Use the existing render_chart_with_panels function
        return render_chart_with_panels(
            ticker=sym,
            df=df,
            indicators=indicators,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            fib_levels=fib_levels,
            out_dir=out_dir,
        )

    except Exception as err:
        log.error("multipanel_enhanced_failed ticker=%s err=%s", ticker, str(err))
        return None
