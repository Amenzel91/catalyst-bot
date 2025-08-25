from __future__ import annotations
from typing import Optional
from pathlib import Path
from .logging_utils import get_logger
log = get_logger("charts")

try:
    import matplotlib  # type: ignore
    import mplfinance as mpf  # type: ignore
    CHARTS_OK = True
except Exception as e:
    CHARTS_OK = False
    log.info(f"charts_disabled reason={e!s}")

def render_chart_if_possible(ticker: str, ohlcv_df) -> Optional[Path]:
    """
    Renders a dark candlestick chart with VWAP if libs are available.
    Returns the saved Path or None if charts are disabled.
    """
    if not CHARTS_OK or ohlcv_df is None:
        return None
    outdir = Path("out/charts")
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{ticker}_latest.png"
    try:
        ap = []
        # vwap if exists
        if "vwap" in ohlcv_df.columns:
            ap = [ mpf.make_addplot(ohlcv_df["vwap"]) ]
        mpf.plot(
            ohlcv_df.tail(120),
            type="candle",
            volume=True,
            figratio=(16,9),
            style="nightclouds",
            addplot=ap,
            savefig=str(out),
        )
        return out
    except Exception as e:
        log.warning(f"chart_error ticker={ticker} err={e!s}")
        return None
