"""Advanced multi-panel financial charts using mplfinance.

This module generates professional-grade stock charts with multiple panels:
- Price candlesticks with VWAP and moving averages
- Volume bars
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)

Supports multiple timeframes (1D, 5D, 1M, 3M, 1Y) with dark theme styling.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("charts_advanced")


try:
    from .validation import validate_ticker, validate_timeframe
except Exception:
    # Fallback if validation module not available
    def validate_ticker(t, allow_empty=False):
        if not t:
            return None if not allow_empty else ""
        return str(t).strip().upper() or None

    def validate_timeframe(tf):
        if not tf:
            return None
        return str(tf).strip().upper()


log = get_logger("charts_advanced")


# Timeframe configurations: (period_days, interval, bars_to_show)
# Note: These are now fetched via market.get_intraday() which uses Tiingo when configured
TIMEFRAME_CONFIG = {
    "1D": {
        "days": 1,
        "interval": "5min",
        "bars": 192,
    },  # 1 day with premarket+regular+afterhours (4am-8pm = 16h = 192 bars)
    "5D": {"days": 5, "interval": "5min", "bars": 960},  # 5 days with extended hours
    "1M": {
        "days": 90,
        "interval": "1d",
        "bars": 22,
    },  # 1 month of daily bars (fetch 90 days for MA-50)
    "3M": {"days": 90, "interval": "1d", "bars": 90},  # 3 months of daily bars
    "1Y": {"days": 365, "interval": "1d", "bars": 252},  # 1 year of daily bars
}


def _compute_rsi(series, period: int = 14):
    """Compute RSI (Relative Strength Index) for a price series."""
    try:
        pass

        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        log.warning("rsi_compute_failed err=%s", str(e))
        return None


def _compute_macd(series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Compute MACD (Moving Average Convergence Divergence)."""
    try:
        pass

        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram
    except Exception as e:
        log.warning("macd_compute_failed err=%s", str(e))
        return None, None, None


def _compute_vwap(df):
    """Compute VWAP (Volume Weighted Average Price)."""
    try:
        close = df["Close"]
        volume = df["Volume"]

        # Check if volume is effectively zero
        vol_sum = volume.sum()
        if vol_sum == 0 or vol_sum < 1e-6:
            return None

        vwap = (close * volume).cumsum() / volume.cumsum()
        return vwap
    except Exception as e:
        log.warning("vwap_compute_failed err=%s", str(e))
        return None


def _fetch_data_for_timeframe(ticker: str, timeframe: str) -> Optional[Any]:
    """Fetch OHLCV data for the specified timeframe.

    Uses market.get_intraday() which respects Tiingo API configuration
    for intraday timeframes (1D, 5D, 1M), and yfinance for daily (3M, 1Y).

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        One of: 1D, 5D, 1M, 3M, 1Y

    Returns
    -------
    pd.DataFrame or None
        DataFrame with OHLCV data and DatetimeIndex
    """
    try:
        import pandas as pd

        ticker = ticker.strip().upper()
        if timeframe not in TIMEFRAME_CONFIG:
            log.warning("invalid_timeframe tf=%s", timeframe)
            return None

        TIMEFRAME_CONFIG[timeframe]

        # Map timeframe to interval
        if timeframe == "1D":
            interval = "5min"  # Use 5-minute bars for better data density
            output_size = "full"  # Get full day's data (78 bars for 6.5hr trading day)
        elif timeframe == "5D":
            interval = "5min"  # 5-minute bars for 5-day view
            output_size = "full"  # Get full 5 days of data
        elif timeframe == "1M":
            interval = "1d"  # Daily bars for 1-month view
            output_size = "full"
        elif timeframe in ["3M", "1Y"]:
            interval = "1d"  # Daily bars for longer timeframes
            output_size = "full"
        else:
            interval = "5min"
            output_size = "compact"

        log.info("fetch_data ticker=%s tf=%s interval=%s", ticker, timeframe, interval)

        # For intraday timeframes, use market.get_intraday() (supports Tiingo)
        if timeframe in ["1D", "5D"]:
            try:
                from . import market

                df = market.get_intraday(
                    ticker, interval=interval, output_size=output_size, prepost=True
                )

                if df is not None and not df.empty:
                    # Ensure proper column names (handle multi-ticker response)
                    if isinstance(df.columns, pd.MultiIndex):
                        log.info(
                            "dropping_multiindex_intraday ticker=%s cols_before=%s nlevels=%d",
                            ticker,
                            df.columns.tolist()[:3],
                            df.columns.nlevels,
                        )
                        if df.columns.nlevels > 1:
                            df.columns = df.columns.droplevel(1)
                            log.info(
                                "dropped_multiindex_intraday ticker=%s cols_after=%s",
                                ticker,
                                df.columns.tolist(),
                            )
                        else:
                            log.warning(
                                "unexpected_single_level_multiindex ticker=%s", ticker
                            )
                            # Attempt to flatten anyway using level 0
                            df.columns = df.columns.get_level_values(0)

                    log.info(
                        "fetch_data_success source=market.get_intraday ticker=%s tf=%s rows=%d",
                        ticker,
                        timeframe,
                        len(df),
                    )
                    return df
                else:
                    log.warning(
                        "no_data_from_market_intraday ticker=%s tf=%s",
                        ticker,
                        timeframe,
                    )
            except Exception as e:
                log.warning(
                    "market_intraday_failed ticker=%s tf=%s err=%s",
                    ticker,
                    timeframe,
                    str(e),
                )

        # For daily timeframes or intraday fallback, use yfinance directly
        try:
            import yfinance as yf

            if timeframe == "1M":
                period = "3mo"  # Fetch 3 months to have enough data for MA-50
                yf_interval = "1d"
            elif timeframe == "3M":
                period = "3mo"
                yf_interval = "1d"
            elif timeframe == "1Y":
                period = "1y"
                yf_interval = "1d"
            elif timeframe == "1D":
                period = "5d"  # Fetch 5 days to ensure we have recent trading day data
                yf_interval = "5m"
            elif timeframe == "5D":
                period = "10d"  # Fetch 10 days to ensure we have 5 full trading days
                yf_interval = "5m"
            else:
                period = "1mo"
                yf_interval = "1h"

            df = yf.download(
                tickers=ticker,
                period=period,
                interval=yf_interval,
                progress=False,
                auto_adjust=False,
            )

            if df is None or df.empty:
                log.warning("no_data_from_yfinance ticker=%s tf=%s", ticker, timeframe)
                return None

            # Ensure proper column names (handle multi-ticker response)
            if isinstance(df.columns, pd.MultiIndex):
                log.info(
                    "dropping_multiindex ticker=%s cols_before=%s nlevels=%d",
                    ticker,
                    df.columns.tolist()[:3],
                    df.columns.nlevels,
                )
                # yfinance returns ('Price', 'Ticker') structure - keep only Price level
                if df.columns.nlevels > 1:
                    df.columns = df.columns.droplevel(1)
                    log.info(
                        "dropped_multiindex ticker=%s cols_after=%s",
                        ticker,
                        df.columns.tolist(),
                    )
                else:
                    log.warning("unexpected_single_level_multiindex ticker=%s", ticker)
                    # Attempt to flatten anyway using level 0
                    df.columns = df.columns.get_level_values(0)

            # Ensure DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            log.info(
                "fetch_data_success source=yfinance ticker=%s tf=%s rows=%d",
                ticker,
                timeframe,
                len(df),
            )

            return df

        except Exception as e:
            log.warning(
                "yfinance_fallback_failed ticker=%s tf=%s err=%s",
                ticker,
                timeframe,
                str(e),
            )
            return None

    except Exception as e:
        log.warning(
            "fetch_data_failed ticker=%s tf=%s err=%s", ticker, timeframe, str(e)
        )
        return None


def generate_multi_panel_chart(
    ticker: str,
    timeframe: str = "1D",
    *,
    out_dir: str | Path = "out/charts",
    style: str = "dark",
    catalyst_event: Optional[Dict[str, Any]] = None,
    trade_plan: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Generate a multi-panel financial chart with price, volume, RSI, and MACD.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        One of: 1D, 5D, 1M, 3M, 1Y (default: 1D)
    out_dir : str | Path
        Directory to save the chart image
    style : str
        Chart style: 'dark' or 'light' (default: 'dark')
    catalyst_event : Optional[Dict[str, Any]]
        Optional catalyst event metadata for annotation. Should contain:
        - 'timestamp': datetime or ISO string of the event
        - 'label': str label for the annotation (e.g., "FDA Approval")
        - 'type': 'positive' or 'negative' (determines color)
    trade_plan : Optional[Dict[str, Any]]
        Optional trade plan data for drawing entry/stop/target levels. Should contain:
        - 'entry': float entry price
        - 'stop': float stop-loss price
        - 'target_1': float target price
        - 'rr_ratio': float risk/reward ratio

    Returns
    -------
    Path or None
        Path to the saved PNG file, or None on failure
    """
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)

        import matplotlib.pyplot as plt
        import mplfinance as mpf
        import pandas as pd

    except Exception as e:
        log.warning("import_failed err=%s", str(e))
        return None

    # Validate ticker to prevent injection attacks
    ticker = validate_ticker(ticker)
    if not ticker:
        log.warning("chart_generation_failed reason=invalid_ticker")
        return None

    # Validate timeframe
    timeframe = validate_timeframe(timeframe) or "1D"

    # Fetch data
    df = _fetch_data_for_timeframe(ticker, timeframe)
    if df is None or df.empty:
        return None

    # Debug: Log data shape after fetch
    log.info("data_fetched ticker=%s tf=%s rows=%d", ticker, timeframe, len(df))

    try:
        # Clean data: ensure all OHLCV columns are numeric and drop NaN rows
        # First, ensure columns are not MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            log.info(
                "cleaning_multiindex ticker=%s tf=%s cols_before=%s nlevels=%d",
                ticker,
                timeframe,
                df.columns.tolist()[:3],
                df.columns.nlevels,
            )
            # yfinance returns ('Price', 'Ticker') structure - drop ticker level
            if df.columns.nlevels > 1:
                df.columns = df.columns.droplevel(1)
                log.info(
                    "cleaned_multiindex ticker=%s tf=%s cols_after=%s",
                    ticker,
                    timeframe,
                    df.columns.tolist(),
                )
            else:
                log.warning(
                    "unexpected_single_level_multiindex ticker=%s tf=%s",
                    ticker,
                    timeframe,
                )
                # Attempt to flatten anyway using level 0
                df.columns = df.columns.get_level_values(0)

        # Convert OHLCV columns to numeric, coercing errors to NaN
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col].squeeze(), errors="coerce")
                except Exception as col_err:
                    log.warning(
                        "column_conversion_failed col=%s err=%s", col, str(col_err)
                    )

        # Drop rows with any NaN values in OHLCV columns
        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        # Debug: Log data shape after cleaning
        log.info("data_cleaned ticker=%s tf=%s rows=%d", ticker, timeframe, len(df))

        if df.empty:
            log.warning("no_data_after_cleaning ticker=%s tf=%s", ticker, timeframe)
            return None

        # Filter 1D/5D charts to show most recent trading day
        if timeframe in ["1D", "5D"]:
            try:
                import pytz

                et_tz = pytz.timezone("America/New_York")
                now_et = datetime.now(et_tz)

                # Determine the most recent trading day start (4 AM ET)
                # If it's currently a trading day (Mon-Fri) and after 4 AM, use today
                # Otherwise use the most recent trading day

                current_hour = now_et.hour
                current_weekday = now_et.weekday()  # 0=Monday, 6=Sunday

                # If it's weekend or before 4 AM on a weekday, find last trading day
                if current_weekday >= 5:  # Saturday or Sunday
                    # Go back to Friday
                    days_back = current_weekday - 4
                    trading_day = now_et - timedelta(days=days_back)
                elif current_hour < 4:
                    # Before 4 AM, use previous day (or Friday if Monday)
                    if current_weekday == 0:  # Monday before 4 AM
                        trading_day = now_et - timedelta(days=3)  # Friday
                    else:
                        trading_day = now_et - timedelta(days=1)
                else:
                    # After 4 AM on a weekday
                    trading_day = now_et

                # Set start to 4 AM ET of the trading day
                day_start = trading_day.replace(
                    hour=4, minute=0, second=0, microsecond=0
                )

                # For 1D: show the most recent full trading day
                # For 5D: show last 5 trading days
                if timeframe == "1D":
                    # Filter to the most recent trading day with data
                    try:
                        if df.index.tz is None:
                            df.index = df.index.tz_localize("UTC").tz_convert(et_tz)
                        else:
                            df.index = df.index.tz_convert(et_tz)

                        # Get unique trading days sorted by most recent
                        df_dates = df.index.date
                        unique_dates = sorted(set(df_dates), reverse=True)

                        if len(unique_dates) >= 1:
                            # Use the most recent day with data (always show last trading day)
                            most_recent_date = unique_dates[0]
                            df_filtered = df[df.index.date == most_recent_date]

                            log.info(
                                "1d_filter ticker=%s date=%s filtered_rows=%d total_dates=%d",
                                ticker,
                                most_recent_date,
                                len(df_filtered),
                                len(unique_dates),
                            )

                            if len(df_filtered) >= 3:
                                df = df_filtered
                                log.info(
                                    "using_most_recent_trading_day ticker=%s date=%s rows=%d",
                                    ticker,
                                    most_recent_date,
                                    len(df),
                                )
                            else:
                                log.warning(
                                    "insufficient_data_for_1d ticker=%s date=%s rows=%d (need >=3)",
                                    ticker,
                                    most_recent_date,
                                    len(df_filtered),
                                )

                    except Exception as ex:
                        log.debug("1d_filtering_error err=%s", str(ex))

            except Exception as e:
                log.warning("date_filtering_failed ticker=%s err=%s", ticker, str(e))
                # Continue with unfiltered data

    except Exception as e:
        log.warning("data_cleaning_failed ticker=%s err=%s", ticker, str(e))
        return None

    try:
        # Compute indicators
        vwap = _compute_vwap(df)
        rsi = _compute_rsi(df["Close"], period=14)
        macd_line, signal_line, histogram = _compute_macd(df["Close"])

        # Compute moving averages for 1M and longer timeframes
        ma_20 = None
        ma_50 = None
        if timeframe in ["1M", "3M", "1Y"]:
            ma_20 = df["Close"].rolling(window=20).mean()
            ma_50 = df["Close"].rolling(window=50).mean()

        # Debug: Log data shape before limiting bars
        log.info(
            "data_before_limit ticker=%s tf=%s rows=%d", ticker, timeframe, len(df)
        )

        # Limit display to most recent bars (after computing indicators with full data)
        config = TIMEFRAME_CONFIG.get(timeframe, {})
        max_bars = config.get("bars")
        if max_bars and len(df) > max_bars:
            # Keep only the most recent N bars for display
            df = df.tail(max_bars)
            # Also trim indicators to match
            if vwap is not None:
                vwap = vwap.tail(max_bars)
            if rsi is not None:
                rsi = rsi.tail(max_bars)
            if macd_line is not None:
                macd_line = macd_line.tail(max_bars)
            if signal_line is not None:
                signal_line = signal_line.tail(max_bars)
            if histogram is not None:
                histogram = histogram.tail(max_bars)
            if ma_20 is not None:
                ma_20 = ma_20.tail(max_bars)
            if ma_50 is not None:
                ma_50 = ma_50.tail(max_bars)

        # Handle outlier wicks to prevent chart distortion
        # Calculate y-limits AFTER limiting bars so we use actual displayed data
        try:
            all_prices = pd.concat([df["High"], df["Low"]])

            # Use tighter percentiles for intraday charts to reduce extreme wicks
            if timeframe in ["1D", "5D", "1M"]:
                p_low = 0.02  # 2nd percentile
                p_high = 0.98  # 98th percentile
            else:
                p_low = 0.05  # 5th percentile
                p_high = 0.95  # 95th percentile

            p_lower = all_prices.quantile(p_low)
            p_upper = all_prices.quantile(p_high)
            price_range = p_upper - p_lower

            # Store for later use in setting y-axis limits
            price_lower = max(0, p_lower - price_range * 0.08)  # Add 8% padding below
            price_upper = p_upper + price_range * 0.08  # Add 8% padding above

            log.info(
                "outlier_calc ticker=%s tf=%s p_low=%.2f p_high=%.2f range=%.2f ylim=%.2f-%.2f",
                ticker,
                timeframe,
                p_lower,
                p_upper,
                price_range,
                price_lower,
                price_upper,
            )
        except Exception as e:
            log.warning("outlier_calculation_failed err=%s", str(e))
            price_lower, price_upper = None, None

        # Build additional plots for main panel
        addplot_main = []

        # VWAP overlay (orange line)
        if vwap is not None:
            addplot_main.append(
                mpf.make_addplot(vwap, color="#FF9800", width=1.5, panel=0)
            )

        # Moving averages (only on longer timeframes)
        if ma_20 is not None:
            addplot_main.append(
                mpf.make_addplot(ma_20, color="#2196F3", width=1, panel=0)
            )
        if ma_50 is not None:
            addplot_main.append(
                mpf.make_addplot(ma_50, color="#9C27B0", width=1, panel=0)
            )

        # RSI panel (panel=1 since volume is removed)
        if rsi is not None:
            addplot_main.append(
                mpf.make_addplot(
                    rsi, color="#00BCD4", width=2, panel=1, ylim=(0, 100)
                )  # ylabel set later with color
            )
            # Add RSI reference lines at 30 and 70
            addplot_main.append(
                mpf.make_addplot(
                    [30] * len(df), color="#888888", linestyle="--", width=1, panel=1
                )
            )
            addplot_main.append(
                mpf.make_addplot(
                    [70] * len(df), color="#888888", linestyle="--", width=1, panel=1
                )
            )

        # MACD panel (panel=2 since volume is removed)
        if macd_line is not None and signal_line is not None:
            addplot_main.append(
                mpf.make_addplot(
                    macd_line, color="#4CAF50", width=1.5, panel=2
                )  # ylabel set later with color
            )
            addplot_main.append(
                mpf.make_addplot(signal_line, color="#F44336", width=1, panel=2)
            )
            if histogram is not None:
                # Histogram as bar chart
                try:
                    colors = [
                        "#4CAF50" if float(val) >= 0 else "#F44336" for val in histogram
                    ]
                except (ValueError, TypeError):
                    colors = "#4CAF50"  # Default color if conversion fails
                addplot_main.append(
                    mpf.make_addplot(
                        histogram, type="bar", color=colors, alpha=0.3, panel=2
                    )
                )

        # Define custom dark style
        if style == "dark":
            mc = mpf.make_marketcolors(
                up="#26A69A",  # Green for up candles
                down="#EF5350",  # Red for down candles
                edge="inherit",
                wick="inherit",
                volume="#546E7A",  # Blue-gray for volume
                alpha=0.9,
            )
            s = mpf.make_mpf_style(
                marketcolors=mc,
                gridcolor="#2A2A2A",
                gridstyle="--",
                y_on_right=True,
                facecolor="#1E1E1E",
                figcolor="#121212",
                edgecolor="#2A2A2A",
            )
        else:
            s = "yahoo"  # Light theme fallback

        # Create output directory
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"{ticker}_{timeframe}_{timestamp}.png"
        save_path = out_path / filename

        # Determine interval display name from config
        tf_config = TIMEFRAME_CONFIG.get(timeframe, {})
        interval_display = tf_config.get("interval", "5min")
        if interval_display == "1min":
            interval_display = "1m"
        elif interval_display == "5min":
            interval_display = "5m"
        elif interval_display == "15min":
            interval_display = "15m"
        elif interval_display == "1h":
            interval_display = "1h"
        elif interval_display == "1d":
            interval_display = "1D"

        # Debug: Log final data shape before plotting
        log.info("plotting ticker=%s tf=%s rows=%d", ticker, timeframe, len(df))

        # Plot the chart with multiple panels
        # Build plot kwargs (conditionally include addplot to avoid mplfinance validator error)
        plot_kwargs = {
            "type": "candle",
            "style": s,
            "volume": False,  # Volume removed - shown in Discord embed instead
            "returnfig": True,
            "figsize": (17.4, 10.41),  # Match Discord embed aspect ratio (1740x1041px)
            "panel_ratios": (3, 1, 1),  # Price, RSI, MACD
            "ylabel": "",  # Remove default ylabel, we'll customize it
            "warn_too_much_data": 1000,
            "tight_layout": True,  # Use mplfinance's tight_layout to minimize margins
            "scale_padding": {"left": 0.02, "right": 2.15, "top": 0.02, "bottom": 0.25},  # Full padding for complete price decimals
        }

        # Only add addplot if we have indicators (avoids "None" validator error)
        if addplot_main:
            plot_kwargs["addplot"] = addplot_main

        fig, axes = mpf.plot(df, **plot_kwargs)

        # Get price panel (first axis)
        price_ax = axes[0]

        # Get current price from the latest data point
        current_price = df["Close"].iloc[-1]

        # Add title INSIDE the chart area (top-left of price panel) - LARGE & HIGH CONTRAST
        # Include ticker, timeframe, and current price
        price_ax.text(
            0.008,
            0.97,  # Top-left corner in axes coordinates
            f"{ticker}  {timeframe}  ({interval_display})  ${current_price:.2f}",
            transform=price_ax.transAxes,
            fontsize=14,  # Increased from 11
            color="#FFFFFF",
            ha="left",
            va="top",
            fontweight="bold",
            bbox=dict(
                facecolor="#000000",  # Pure black background for maximum contrast
                edgecolor="#FFFFFF",  # White border
                linewidth=2,
                alpha=0.95,  # More opaque
                pad=6,  # More padding
                boxstyle="round,pad=0.4",
            ),
            zorder=1000,
            clip_on=False,
        )

        # Apply y-axis limits to price panel to handle outlier wicks
        if price_lower is not None and price_upper is not None:
            try:
                price_ax.set_ylim(price_lower, price_upper)
                price_ax.autoscale(False)  # Disable autoscaling to preserve ylim
                log.debug(
                    "set_ylim ticker=%s range=%.2f-%.2f",
                    ticker,
                    price_lower,
                    price_upper,
                )
            except Exception as e:
                log.warning("set_ylim_failed err=%s", str(e))

        # Add PM/Day/AH background shading for intraday charts
        if timeframe in ["1D", "5D"] and not df.empty:
            try:
                import pytz
                from matplotlib.dates import date2num

                et_tz = pytz.timezone("America/New_York")

                # Iterate through dates in the dataframe
                dates_in_data = df.index.normalize().unique()

                for date in dates_in_data:
                    # Convert to ET timezone
                    if hasattr(date, "tz_localize"):
                        date_et = (
                            date.tz_localize(et_tz)
                            if date.tz is None
                            else date.tz_convert(et_tz)
                        )
                    else:
                        date_et = date

                    # Define market hours in ET
                    pm_start = date_et.replace(hour=4, minute=0)
                    market_open = date_et.replace(hour=9, minute=30)
                    market_close = date_et.replace(hour=16, minute=0)
                    ah_end = date_et.replace(hour=20, minute=0)

                    # Pre-market: 4:00 - 9:30 (black background)
                    price_ax.axvspan(
                        date2num(pm_start),
                        date2num(market_open),
                        facecolor="#000000",
                        alpha=0.3,
                        zorder=0,
                    )

                    # Regular hours: 9:30 - 16:00 (grey background - default)
                    # No shading needed, this is the base color

                    # After-hours: 16:00 - 20:00 (black background)
                    price_ax.axvspan(
                        date2num(market_close),
                        date2num(ah_end),
                        facecolor="#000000",
                        alpha=0.3,
                        zorder=0,
                    )
            except Exception as e:
                log.debug("pm_ah_shading_failed err=%s", str(e))

        # Add current price text overlay on right axis
        try:
            # Safety check: ensure DataFrame has data before accessing
            if df.empty or len(df) < 1:
                log.debug("skipping_price_overlay_empty_dataframe ticker=%s", ticker)
            else:
                current_price = df["Close"].iloc[-1]

                # Add horizontal line at current price
                price_ax.axhline(
                    y=current_price,
                    color="#FFFFFF",
                    linestyle="--",
                    linewidth=1,
                    alpha=0.5,
                )

                # Add price label on right side - LARGER & HIGH CONTRAST
                price_ax.text(
                    1.01,
                    current_price,
                    f"${current_price:.2f}",
                    transform=price_ax.get_yaxis_transform(),
                    fontsize=12,  # Increased from 10
                    color="#FFFFFF",
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.5",
                        facecolor="#000000",  # Pure black
                        edgecolor="#FFFFFF",  # White border
                        linewidth=2,
                        alpha=0.95,
                    ),
                    va="center",
                    ha="left",
                )
        except Exception as e:
            log.debug("current_price_overlay_failed err=%s", str(e))

        # Add trade plan annotations (Entry/Stop/Target levels)
        if trade_plan:
            try:
                entry = trade_plan.get("entry")
                stop = trade_plan.get("stop")
                target = trade_plan.get("target_1")

                if entry and stop and target:
                    # Entry level (white dashed)
                    price_ax.axhline(
                        y=entry,
                        color="#FFFFFF",
                        linestyle=":",
                        linewidth=1.5,
                        alpha=0.7,
                    )
                    price_ax.text(
                        1.01,
                        entry,
                        f"Entry ${entry:.2f}",
                        transform=price_ax.get_yaxis_transform(),
                        fontsize=10,
                        color="#FFFFFF",
                        fontweight="bold",
                        bbox=dict(
                            boxstyle="round,pad=0.4",
                            facecolor="#4A90E2",  # Blue
                            edgecolor="#FFFFFF",
                            linewidth=1.5,
                            alpha=0.9,
                        ),
                        va="center",
                        ha="left",
                    )

                    # Stop-loss level (red)
                    price_ax.axhline(
                        y=stop,
                        color="#E74C3C",
                        linestyle="--",
                        linewidth=1.5,
                        alpha=0.7,
                    )
                    price_ax.text(
                        1.01,
                        stop,
                        f"Stop ${stop:.2f}",
                        transform=price_ax.get_yaxis_transform(),
                        fontsize=10,
                        color="#FFFFFF",
                        fontweight="bold",
                        bbox=dict(
                            boxstyle="round,pad=0.4",
                            facecolor="#E74C3C",  # Red
                            edgecolor="#FFFFFF",
                            linewidth=1.5,
                            alpha=0.9,
                        ),
                        va="center",
                        ha="left",
                    )

                    # Target level (green)
                    price_ax.axhline(
                        y=target,
                        color="#2ECC71",
                        linestyle="--",
                        linewidth=1.5,
                        alpha=0.7,
                    )
                    price_ax.text(
                        1.01,
                        target,
                        f"Target ${target:.2f}",
                        transform=price_ax.get_yaxis_transform(),
                        fontsize=10,
                        color="#FFFFFF",
                        fontweight="bold",
                        bbox=dict(
                            boxstyle="round,pad=0.4",
                            facecolor="#2ECC71",  # Green
                            edgecolor="#FFFFFF",
                            linewidth=1.5,
                            alpha=0.9,
                        ),
                        va="center",
                        ha="left",
                    )

                    log.debug(
                        "trade_plan_annotations_added ticker=%s entry=%.2f stop=%.2f target=%.2f",
                        ticker,
                        entry,
                        stop,
                        target,
                    )
            except Exception as e:
                log.debug("trade_plan_annotations_failed ticker=%s err=%s", ticker, str(e))

        # Add VWAP value overlay on right axis
        if vwap is not None:
            try:
                # Safety check: ensure VWAP has data before accessing
                if not vwap.empty and len(vwap) >= 1:
                    vwap_current = vwap.iloc[-1]
                    price_ax.text(
                        1.01,
                        vwap_current,
                        f"VWAP ${vwap_current:.2f}",
                        transform=price_ax.get_yaxis_transform(),
                        fontsize=11,  # Increased from 9
                        color="#FFFFFF",  # White text for better contrast
                        fontweight="bold",
                        bbox=dict(
                            boxstyle="round,pad=0.5",
                            facecolor="#FF9800",  # Bright orange background
                            edgecolor="#FFFFFF",  # White border
                            linewidth=2,
                            alpha=0.95,
                        ),
                        va="center",
                        ha="left",
                    )
            except Exception as e:
                log.debug("vwap_overlay_failed err=%s", str(e))

        # Add catalyst event annotation if provided
        if catalyst_event:
            try:
                from dateutil import parser as date_parser

                # Extract event details
                event_ts = catalyst_event.get("timestamp")
                event_label = catalyst_event.get("label", "Catalyst Event")
                event_type = catalyst_event.get("type", "positive")

                # Parse timestamp (supports datetime objects and ISO strings)
                if isinstance(event_ts, str):
                    event_dt = date_parser.isoparse(event_ts)
                elif hasattr(event_ts, "tzinfo"):
                    event_dt = event_ts
                else:
                    event_dt = None

                if event_dt and not df.empty:
                    # Find the closest data point to the event timestamp
                    # Convert event time to UTC for comparison (df index is in UTC)
                    if event_dt.tzinfo is not None:
                        event_dt_utc = event_dt.astimezone(pytz.UTC)
                    else:
                        event_dt_utc = pytz.UTC.localize(event_dt)

                    # Find the nearest timestamp in the data
                    time_diffs = abs(df.index - event_dt_utc)
                    closest_idx = time_diffs.argmin()
                    closest_time = df.index[closest_idx]
                    closest_price = df["Close"].iloc[closest_idx]

                    # Choose color based on event type
                    if event_type == "negative":
                        arrow_color = "#FF4444"  # Red for negative events
                        label_bg = "#FF4444"
                    else:
                        arrow_color = "#4CAF50"  # Green for positive events
                        label_bg = "#4CAF50"

                    # Add annotation with arrow pointing to the event
                    # Place annotation above the price for positive, below for negative
                    y_offset = 40 if event_type == "positive" else -40

                    price_ax.annotate(
                        event_label,
                        xy=(closest_time, closest_price),
                        xytext=(0, y_offset),
                        textcoords="offset points",
                        fontsize=10,
                        color="#FFFFFF",
                        fontweight="bold",
                        bbox=dict(
                            boxstyle="round,pad=0.6",
                            facecolor=label_bg,
                            edgecolor="#FFFFFF",
                            linewidth=2.5,
                            alpha=0.95,
                        ),
                        arrowprops=dict(
                            arrowstyle="->",
                            color=arrow_color,
                            linewidth=3,
                            shrinkA=0,
                            shrinkB=5,
                        ),
                        zorder=1000,
                        ha="center",
                        va="bottom" if event_type == "positive" else "top",
                    )

                    log.info(
                        "catalyst_annotation_added ticker=%s event=%s time=%s",
                        ticker,
                        event_label[:20],
                        closest_time,
                    )
            except Exception as e:
                log.warning("catalyst_annotation_failed err=%s", str(e))

        # Improve time label contrast and formatting, hide left y-axis on indicator panels
        try:
            import matplotlib.dates as mdates

            # Customize axes
            # axes[0] = Price panel
            # axes[1] = RSI panel (if RSI was added)
            # axes[2] = MACD panel (if both RSI and MACD were added)
            # OR axes[1] = MACD panel (if only MACD was added)

            for i, ax in enumerate(axes):
                # Make time labels brighter and larger for better contrast
                ax.tick_params(axis="x", colors="#FFFFFF", labelsize=10)
                # Make tick labels bold
                for label in ax.get_xticklabels():
                    label.set_fontweight("bold")

                # Panel 0 = Price (show y-axis labels)
                # Panel 2 = RSI (hide y-axis labels, using custom text annotations)
                # Panel 4 = MACD (hide y-axis labels, using custom text annotations)
                if i == 0:
                    # Price panel: Show y-axis on right - BRIGHTER & LARGER
                    ax.yaxis.set_label_position("right")
                    ax.yaxis.tick_right()
                    ax.tick_params(axis="y", colors="#FFFFFF", labelsize=10)
                    ax.yaxis.set_ticks_position("right")
                    # Make tick labels bold
                    for label in ax.get_yticklabels():
                        label.set_fontweight("bold")
                elif i in [2, 4]:
                    # RSI and MACD panels: Hide y-axis tick labels (using custom annotations)
                    ax.yaxis.set_label_position("right")
                    ax.yaxis.tick_right()
                    ax.tick_params(axis="y", labelsize=0)  # Hide tick labels
                    ax.yaxis.set_ticks_position("right")
                else:
                    # Hidden panels: Just hide everything
                    ax.yaxis.set_label_position("right")
                    ax.yaxis.tick_right()
                    ax.tick_params(axis="y", labelsize=0)
                    ax.yaxis.set_ticks_position("right")

                # Remove top spine for cleaner, modern look (professional charts use minimal spines)
                ax.spines['top'].set_visible(False)

                # Improve x-axis label formatting based on timeframe
                if timeframe == "1Y":
                    # Year view: Show year markers and monthly ticks
                    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

                elif timeframe == "3M":
                    # 3 month view: Show month/day format
                    locator = mdates.AutoDateLocator(maxticks=10)
                    ax.xaxis.set_major_locator(locator)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

                elif timeframe == "1M":
                    # 1 month view: Use AutoDateLocator for smart spacing
                    locator = mdates.AutoDateLocator(maxticks=8)
                    ax.xaxis.set_major_locator(locator)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

                elif timeframe in ["1D", "5D"]:
                    # Intraday: Use AutoDateLocator for time format
                    locator = mdates.AutoDateLocator(maxticks=8)
                    ax.xaxis.set_major_locator(locator)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

                # Rotate labels for better readability
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")

        except Exception as e:
            log.debug("axis_formatting_failed err=%s", str(e))

        # Note: Final margin adjustment done after panel annotations below
        # (This early adjustment is skipped to avoid double-adjustment)

        # For 1D/5D charts: Let matplotlib auto-scale to actual data range
        # (Setting xlim to full trading day compresses afternoon-only data too much)
        # TODO: Consider adding xlim with padding when we have full-day data
        if False and timeframe in ["1D", "5D"] and not df.empty and len(df) >= 10:
            try:
                import pytz
                from matplotlib.dates import date2num

                et_tz = pytz.timezone("America/New_York")

                # Get the date range in the data
                first_date = df.index[0]
                last_date = df.index[-1]

                # Convert to ET
                if hasattr(first_date, "tz_convert"):
                    first_date_et = first_date.tz_convert(et_tz)
                    last_date_et = last_date.tz_convert(et_tz)
                else:
                    first_date_et = first_date
                    last_date_et = last_date

                # Set chart to span from 4:00 AM to 8:00 PM ET for the date range
                day_start = first_date_et.replace(
                    hour=4, minute=0, second=0, microsecond=0
                )
                day_end = last_date_et.replace(
                    hour=20, minute=0, second=0, microsecond=0
                )

                log.info(
                    "xlim_set ticker=%s data_range=%s_to_%s chart_range=%s_to_%s",
                    ticker,
                    first_date_et,
                    last_date_et,
                    day_start,
                    day_end,
                )

                # Apply to price axis
                price_ax.set_xlim(date2num(day_start), date2num(day_end))

            except Exception as e:
                log.debug("xlim_adjustment_failed err=%s", str(e))

        # Add text annotations for RSI and MACD panels
        try:
            # RSI panel annotations
            # mplfinance creates 6 axes: 0=Price, 1=hidden, 2=RSI, 3=hidden, 4=MACD, 5=MACD overlay
            if len(axes) >= 5:
                # axes[2] is RSI, axes[4] is MACD
                if len(axes) == 6:  # All panels present
                    rsi_ax = axes[2]
                    macd_ax = axes[4]

                    # RSI label (vertical text on right edge, outside panel)
                    rsi_ax.text(
                        1.03,
                        0.5,
                        "RSI",
                        transform=rsi_ax.transAxes,
                        fontsize=11,
                        color="#00BCD4",
                        rotation=270,
                        va="center",
                        ha="left",
                        fontweight="bold",
                        clip_on=False,
                        zorder=1000,
                    )

                    # RSI tick labels (30 and 70) - USE DATA COORDINATES for proper alignment
                    rsi_ax.text(
                        1.03,
                        30,  # Actual RSI value of 30
                        "30",
                        transform=rsi_ax.get_yaxis_transform(),  # Use y-axis data coordinates
                        fontsize=10,
                        color="#FFFFFF",
                        fontweight="bold",
                        va="center",
                        ha="left",
                        clip_on=False,
                        zorder=1000,
                    )
                    rsi_ax.text(
                        1.03,
                        70,  # Actual RSI value of 70
                        "70",
                        transform=rsi_ax.get_yaxis_transform(),  # Use y-axis data coordinates
                        fontsize=10,
                        color="#FFFFFF",
                        fontweight="bold",
                        va="center",
                        ha="left",
                        clip_on=False,
                        zorder=1000,
                    )

                    # MACD label (vertical text on right edge, level with RSI label)
                    macd_ax.text(
                        1.03,
                        0.5,
                        "MACD",
                        transform=macd_ax.transAxes,
                        fontsize=11,
                        color="#4CAF50",
                        rotation=270,
                        va="center",
                        ha="left",
                        fontweight="bold",
                        clip_on=False,
                    )

                    # Add RSI current value box (if RSI has data)
                    if rsi is not None:
                        rsi_current = (
                            rsi.dropna().iloc[-1] if not rsi.dropna().empty else None
                        )
                        if rsi_current is not None:
                            # Determine color based on RSI level
                            if rsi_current >= 70:
                                rsi_color = "#EF5350"  # Red (overbought)
                            elif rsi_current <= 30:
                                rsi_color = "#26A69A"  # Green (oversold)
                            else:
                                rsi_color = "#00BCD4"  # Cyan (neutral)

                            rsi_ax.text(
                                0.015,
                                0.95,
                                f"RSI {rsi_current:.1f}",
                                transform=rsi_ax.transAxes,
                                fontsize=13,  # Increased from 11
                                color="#FFFFFF",
                                bbox=dict(
                                    boxstyle="round,pad=0.6",
                                    facecolor=rsi_color,
                                    edgecolor="#FFFFFF",  # White border for extra pop
                                    linewidth=2.5,
                                    alpha=1.0,  # Fully opaque
                                ),
                                va="top",
                                ha="left",
                                fontweight="bold",
                                zorder=1000,
                            )

                elif len(axes) == 4:  # Only MACD panel (axes[2])
                    macd_ax = axes[2]

                    # MACD label (vertical text on right edge)
                    macd_ax.text(
                        1.03,
                        0.5,
                        "MACD",
                        transform=macd_ax.transAxes,
                        fontsize=11,
                        color="#4CAF50",
                        rotation=270,
                        va="center",
                        ha="left",
                        fontweight="bold",
                        clip_on=False,
                    )

        except Exception as e:
            log.warning("panel_annotations_failed err=%s", str(e))

        # DEFINITIVE SOLUTION - Minimize margins while preserving axis labels
        # Research: "Label cutoff happens when tight_layout=True or very low scale_padding values
        # clip y-axis labels or x-axis date labels. If you see partially visible numbers or dates,
        # increase scale_padding values slightly or adjust specific sides"
        try:
            # Set subplot boundaries near extremes, but leave adequate room for labels
            # Axis labels are on RIGHT (price) and BOTTOM (time), so those need more margin
            # left=0.02: minimal left margin
            # right=0.33: 67% margin on right for complete price box with full decimals
            # top=0.98: 2% margin on top
            # bottom=0.10: 10% margin on bottom for x-axis time labels (looks good now)
            # hspace=0.03: minimal vertical space between panels
            fig.subplots_adjust(left=0.02, right=0.33, top=0.98, bottom=0.10, hspace=0.03)

            log.debug("applied minimal-margin layout with label visibility")
        except Exception as e:
            log.warning("layout_adjustment_failed err=%s", str(e))

        # Save with fixed figsize - no bbox cropping to maintain aspect ratio
        # DPI 100: figsize (17.4, 10.41) * 100 = 1740x1041px (landscape, fits Discord)
        fig.savefig(
            save_path,
            facecolor="#121212",
            edgecolor="none",
            dpi=100,
            pad_inches=0,
        )
        plt.close(fig)

        log.info(
            "chart_generated ticker=%s tf=%s path=%s size=%d",
            ticker,
            timeframe,
            save_path,
            save_path.stat().st_size,
        )

        return save_path

    except Exception as e:
        log.warning(
            "chart_generation_failed ticker=%s tf=%s err=%s", ticker, timeframe, str(e)
        )
        return None


def generate_all_timeframes(
    ticker: str,
    *,
    out_dir: str | Path = "out/charts",
    style: str = "dark",
) -> Dict[str, Optional[Path]]:
    """Generate charts for all timeframes.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    out_dir : str | Path
        Directory to save chart images
    style : str
        Chart style: 'dark' or 'light'

    Returns
    -------
    Dict[str, Optional[Path]]
        Mapping of timeframe -> chart path (or None if failed)
    """
    results = {}

    for tf in TIMEFRAME_CONFIG.keys():
        log.info("generating_chart ticker=%s tf=%s", ticker, tf)
        path = generate_multi_panel_chart(
            ticker, timeframe=tf, out_dir=out_dir, style=style
        )
        results[tf] = path

    return results
