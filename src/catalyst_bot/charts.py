"""Chart rendering for the catalyst bot.

This module uses ``mplfinance`` to produce dark‑themed candlestick
charts with an overlayed VWAP line. Charts are saved as PNG files
into the ``out/charts`` directory defined in the configuration.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # Use non‑interactive backend suitable for headless servers

try:
    import mplfinance as mpf  # type: ignore
except Exception:  # pragma: no cover
    mpf = None  # type: ignore
import pandas as pd
from pathlib import Path
from typing import Optional

from .config import get_settings
from .market import get_intraday


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute the Volume Weighted Average Price (VWAP) for a DataFrame."""
    cumulative_vol = df["volume"].cumsum()
    cumulative_vp = (df["close"] * df["volume"]).cumsum()
    return cumulative_vp / cumulative_vol


def render_chart(
    symbol: str,
    interval: str = "5min",
    output_size: str = "compact",
    filename: Optional[str] = None,
) -> Optional[str]:
    """Fetch intraday data for ``symbol`` and render a candlestick chart.

    Parameters
    ----------
    symbol : str
        Ticker to chart.
    interval : str
        Intraday interval for the data (default '5min').
    output_size : str
        'compact' or 'full' session. Full sessions produce larger files.
    filename : Optional[str]
        If provided, overrides the auto‑generated filename.

    Returns
    -------
    Optional[str]
        Path to the saved PNG file relative to the project root, or
        ``None`` if rendering fails.
    """
    settings = get_settings()
    # If mplfinance is unavailable, skip chart rendering
    if mpf is None:
        return None
    df = get_intraday(symbol, interval=interval, output_size=output_size)
    if df is None or df.empty:
        return None
    # Compute VWAP and add as a column for plotting
    vwap = compute_vwap(df)
    df_copy = df.copy()
    df_copy["vwap"] = vwap
    # Rename columns to the names expected by mplfinance
    df_copy = df_copy.rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    # Determine filename
    if filename is None:
        ts_str = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol.upper()}_{ts_str}.png"
    out_path = settings.out_dir / "charts" / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Define additional plots (VWAP line)
    add_plots = [mpf.make_addplot(df_copy["vwap"], color="orange", width=1)]

    # Plot candlestick chart with dark theme
    try:
        mpf.plot(
            df_copy,
            type="candle",
            style="nightclouds",
            volume=True,
            addplot=add_plots,
            ylabel="Price",
            ylabel_lower="Volume",
            figratio=(16, 9),
            figscale=1.2,
            datetime_format="%H:%M",
            tight_layout=True,
            savefig=dict(fname=str(out_path), dpi=150, bbox_inches="tight"),
        )
        return str(out_path.relative_to(settings.base_dir))
    except Exception:
        return None