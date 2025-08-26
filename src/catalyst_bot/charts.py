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
    Render (or stub) an intraday chart. If matplotlib/mplfinance are missing,
    skip gracefully and return None. This keeps runtime stable on minimal envs.
    """
    if not CHARTS_OK:
        log.info(
            "charts_skip reason=deps_missing mpl=%s mpf=%s",
            HAS_MATPLOTLIB,
            HAS_MPLFINANCE,
        )
        return None

    # Lazy import inside the function (only when we actually need to draw)
    import mplfinance as mpf  # noqa: F401
    from matplotlib import pyplot as plt  # noqa: F401

    try:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Placeholder artifact so upstream pipeline has a file to attach.
        # (Swap to real charting when mplfinance is available everywhere.)
        path = out_path / f"{ticker}_placeholder.txt"
        path.write_text("chart placeholder\n", encoding="utf-8")
        return path
    except Exception as err:  # pragma: no cover (best-effort)
        log.info("charts_render_failed err=%s", str(err))
        return None
