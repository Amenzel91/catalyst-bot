from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("charts")


log = get_logger("charts_post")


def _build_quickchart_config(dataset: list, ticker: str) -> Dict[str, Any]:
    # Minimal candlestick config (Chart.js financial plugin)
    return {
        "type": "candlestick",
        "data": {"datasets": [{"label": ticker, "data": dataset}]},
        "options": {
            "scales": {
                "x": {"type": "timeseries", "time": {"unit": "hour"}},
                "y": {"position": "right"},
            },
            "plugins": {"legend": {"display": False}, "title": {"display": False}},
        },
    }


def get_quickchart_png_path(
    ticker: str,
    *,
    bars: int = int(os.getenv("QUICKCHART_BARS", "50")),
    out_dir: str | Path = os.getenv("QUICKCHART_IMAGE_DIR", "out/charts"),
) -> Optional[Path]:
    """POST the Chart.js config to QUICKCHART_BASE_URL /chart and save PNG locally.
    Returns the file Path on success, or None on failure.
    """
    try:
        import pandas as pd  # noqa: F401

        from . import market
    except Exception:
        return None

    nt = (ticker or "").strip().upper()
    if not nt:
        return None

    # Fetch compact intraday data (5-minute bars)
    df = market.get_intraday(nt, interval="5min", output_size="compact", prepost=True)
    if df is None or getattr(df, "empty", False):
        return None

    # Ensure DatetimeIndex
    try:
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
    except Exception:
        pass

    tail = df.tail(bars)
    if tail is None or getattr(tail, "empty", False):
        return None

    dataset = []
    last_ts = None
    for ts, row in tail.iterrows():
        try:
            # Use .item() to extract scalar from pandas Series safely
            o = (
                row["Open"].item()
                if hasattr(row["Open"], "item")
                else float(row["Open"])
            )
            h = (
                row["High"].item()
                if hasattr(row["High"], "item")
                else float(row["High"])
            )
            low = (
                row["Low"].item() if hasattr(row["Low"], "item") else float(row["Low"])
            )
            c = (
                row["Close"].item()
                if hasattr(row["Close"], "item")
                else float(row["Close"])
            )
            dataset.append(
                {
                    "x": ts.strftime("%Y-%m-%dT%H:%M"),
                    "o": o,
                    "h": h,
                    "low": low,  # renamed from 'l' to 'low' to avoid ambiguous variable name
                    "c": c,
                }
            )
            last_ts = ts
        except Exception:
            continue
    if not dataset:
        return None

    cfg = _build_quickchart_config(dataset, nt)

    raw = os.getenv("QUICKCHART_BASE_URL", "https://quickchart.io").rstrip("/")
    chart_endpoint = f"{raw}/chart" if not raw.endswith("/chart") else raw

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (
        last_ts.strftime("%Y%m%d-%H%M")
        if last_ts is not None
        else datetime.utcnow().strftime("%Y%m%d-%H%M")
    )
    out_file = out_dir / f"{nt}_{stamp}.png"

    try:
        r = requests.post(chart_endpoint, json={"chart": cfg}, timeout=15)
        if not r.ok or not r.content:
            # Log response body for debugging 500 errors
            error_body = r.text[:200] if hasattr(r, "text") else ""
            log.info(
                "quickchart_post_chart_fail status=%s error=%s",
                getattr(r, "status_code", "?"),
                error_body,
            )
            return None
        out_file.write_bytes(r.content)
        log.info("quickchart_saved path=%s bytes=%d", out_file, len(r.content))
        return out_file
    except Exception as e:
        log.info("quickchart_post_chart_exc err=%s", str(e))
        return None
