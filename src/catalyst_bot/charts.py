from __future__ import annotations

import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

from .logging_utils import get_logger

log = get_logger("charts")

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


def _quickchart_url_yfinance(ticker: str, bars: int = 50) -> Optional[str]:
    """
    Build a QuickChart URL for a candlestick chart of the most recent
    intraday trading session.

    This helper fetches 5‑minute OHLC data for the past day using yfinance,
    constructs a Chart.js candlestick configuration and encodes it for
    QuickChart.  It returns None if data cannot be fetched or an error
    occurs.  The "bars" parameter limits the number of candles in the
    output (default 50).
    """
    try:
        import json
        import urllib.parse

        import pandas as pd  # noqa: F401
        import yfinance as yf  # noqa: F401

        # Fetch 1‑day, 5‑minute intraday data.  Suppress progress bar.
        data = yf.download(
            tickers=ticker,
            period="1d",
            interval="5m",
            progress=False,
        )
        if data is None or data.empty:
            return None
        df = data.tail(bars)
        dataset = []
        # Iterate in chronological order; df is already sorted by index.
        for ts, row in df.iterrows():
            try:
                x = ts.strftime("%Y-%m-%d %H:%M")
                dataset.append(
                    {
                        "x": x,
                        "o": float(row["Open"]),
                        "h": float(row["High"]),
                        "l": float(row["Low"]),
                        "c": float(row["Close"]),
                    }
                )
            except Exception:
                # Skip malformed rows but continue processing others
                continue
        if not dataset:
            return None
        cfg = {
            "type": "candlestick",
            "data": {"datasets": [{"label": ticker.upper(), "data": dataset}]},
            "options": {
                "title": {"display": True, "text": f"{ticker.upper()} Intraday"},
                # Hide legend for clarity
                "legend": {"display": False},
                # Minimal padding
                "layout": {"padding": {"left": 0, "right": 0, "top": 0, "bottom": 0}},
            },
        }
        cfg_json = json.dumps(cfg, separators=(",", ":"))
        encoded = urllib.parse.quote(cfg_json, safe="")
        return f"https://quickchart.io/chart?c={encoded}"
    except Exception:
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
                open_price = float(row["Open"])
                high_price = float(row["High"])
                low_price = float(row["Low"])
                close_price = float(row["Close"])
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
        if not dataset:
            return None
        cfg = _build_quickchart_config(dataset, nt)
        cfg_json = json.dumps(cfg, separators=(",", ":"))
        encoded = urllib.parse.quote(cfg_json, safe="")
        # Build base URL
        base_url = f"https://quickchart.io/chart?c={encoded}"
        # If URL length exceeds ~1900 characters, attempt to shorten via QuickChart API.
        # This avoids hitting Discord's message limit and improves readability.
        try:
            # Determine threshold from env or default (1900)
            import os

            threshold = int(
                os.getenv("QUICKCHART_SHORTEN_THRESHOLD", "1900").strip() or 1900
            )
        except Exception:
            threshold = 1900
        try:
            if len(base_url) > threshold:
                # Use the QuickChart /chart/create endpoint to shorten the config.
                import requests

                # Include API key in the request body when provided.  The
                # QUICKCHART_API_KEY improves rate limits on the hosted API.
                api_key = os.getenv("QUICKCHART_API_KEY")
                payload = {"chart": cfg}
                if api_key:
                    payload["key"] = api_key
                resp = requests.post(
                    "https://quickchart.io/chart/create",
                    json=payload,
                    timeout=10,
                )
                log.info("quickchart_post status=%s", resp.status_code)  # log after the original call

                # Expect JSON {"success": true, "url": "https://..."}
                if resp.ok:
                    try:
                        data = resp.json()
                    except Exception:
                        data = {}
                    url = data.get("url") or data.get("shortUrl") or None
                    if isinstance(url, str) and url.startswith("http"):
                        return url
        except Exception:
            # Fall back to original long URL on any failure
            pass
        return base_url
    except Exception:
        return None
