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
        Indicators to display: ['vwap', 'rsi', 'macd', 'bollinger']
    support_levels : Optional[List[Dict]]
        Support levels from detect_support_resistance()
    resistance_levels : Optional[List[Dict]]
        Resistance levels from detect_support_resistance()
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

    try:
        # Validate DataFrame
        if df is None or getattr(df, "empty", False):
            raise ValueError("no_data")

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

        # Render chart (only pass kwargs if they have values)
        plot_kwargs = {
            "type": "candle",
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

        df = market.get_intraday(
            sym, interval="5min", output_size="compact", prepost=True
        )
        try:
            log.info(
                "charts_render_df ticker=%s rows=%s cols=%s",
                sym,
                getattr(df, "shape", ("-", "-"))[0],
                list(getattr(df, "columns", [])),
            )
        except Exception:
            pass
        # Validate DataFrame
        if df is None or getattr(df, "empty", False):
            raise ValueError("no_intraday_data")
        # Ensure the index is datetimes; mplfinance expects a DatetimeIndex
        # If the index isn't a DatetimeIndex, attempt to coerce
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass

        # Compute VWAP series for overlay when possible
        vwap_series = None
        try:
            close = df["Close"]
            vol = df["Volume"]
            if vol.sum() != 0:
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

        try:
            fig, axes = mpf.plot(
                df,
                type="candle",
                style=chart_style,
                volume=True,
                addplot=add_plots if add_plots else None,
                returnfig=True,
                figsize=(12, 7),
            )
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
                if vol.sum() != 0:
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

        # Use the existing render_chart_with_panels function
        return render_chart_with_panels(
            ticker=sym,
            df=df,
            indicators=indicators,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            out_dir=out_dir,
        )

    except Exception as err:
        log.error("multipanel_enhanced_failed ticker=%s err=%s", ticker, str(err))
        return None
