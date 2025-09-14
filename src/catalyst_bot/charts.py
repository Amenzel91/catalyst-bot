from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

from .logging_utils import get_logger

log = get_logger("charts")

# Detect packages without importing them up-front
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
HAS_MPLFINANCE = importlib.util.find_spec("mplfinance") is not None

# Legacy/test-facing flag expected by tests/test_chart_guard.py
CHARTS_OK = bool(HAS_MATPLOTLIB and HAS_MPLFINANCE)


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

        # Generate candlestick chart; disable volume panel for clarity
        try:
            fig, axes = mpf.plot(
                df,
                type="candle",
                style="yahoo",
                volume=False,
                addplot=add_plots if add_plots else None,
                returnfig=True,
                figsize=(6, 4),
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
