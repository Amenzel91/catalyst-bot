from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

from .logging_utils import get_logger

log = get_logger("charts")

# Detect availability without importing at module import time
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
HAS_MPLFINANCE = importlib.util.find_spec("mplfinance") is not None


def render_intraday_chart(
    ticker: str,
    out_dir: Path | str = "out/charts",
) -> Optional[Path]:
    """
    Render (or stub) an intraday chart. If matplotlib/mplfinance are missing,
    skip gracefully and return None. This keeps runtime stable on minimal envs.
    """
    if not (HAS_MATPLOTLIB and HAS_MPLFINANCE):
        log.info(
            "charts_skip reason=deps_missing mpl=%s mpf=%s",
            HAS_MATPLOTLIB,
            HAS_MPLFINANCE,
        )
        return None

    # Lazy import inside the function to avoid module-level F401
    import mplfinance as mpf  # noqa: WPS433
    from matplotlib import pyplot as plt  # noqa: WPS433

    # Touch the names so flake8 doesn't flag as unused
    _ = (plt, mpf)

    try:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Placeholder artifact so upstream pipeline has a file to attach
        path = out_path / f"{ticker}_placeholder.txt"
        path.write_text("chart placeholder\n", encoding="utf-8")
        return path
    except Exception as err:  # pragma: no cover (best-effort)
        log.info("charts_render_failed err=%s", str(err))
        return None
