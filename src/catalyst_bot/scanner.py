"""Proactive breakout scanner for Catalyst‑Bot.

This module provides a simple interface to query the Finviz Elite screener
export and return candidate tickers exhibiting breakout characteristics.
The scanner focuses on low‑priced equities (sub‑$10) with unusually high
volume and recent positive price performance.  Results are returned in
`event`-like dictionaries that can be merged into the normal feed pipeline
and scored/classified like any other event.

The core helper ``scan_breakouts_under_10`` accepts minimum average
volume and relative volume thresholds.  It fetches a Finviz screener
export using those filters and applies additional heuristics to refine
the list.  You must enable FEATURE_BREAKOUT_SCANNER in your environment
and supply a valid Finviz Elite cookie via FINVIZ_AUTH_TOKEN to run
the scan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import get_settings
from .finviz_elite import export_screener

def _ts_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_breakouts_under_10(
    *, min_avg_vol: float = 300_000.0, min_relvol: float = 1.5
) -> List[Dict[str, object]]:
    """Return a list of breakout candidate events under $10.

    Parameters
    ----------
    min_avg_vol : float, optional
        Minimum average daily volume required for a ticker to be considered.  Use
        a value of zero to disable this filter.  Defaults to 300,000.
    min_relvol : float, optional
        Minimum relative volume (compared to average) required.  Values > 1
        indicate higher than normal trading activity.  Defaults to 1.5.

    Returns
    -------
    List[Dict[str, object]]
        A list of event‑shaped dicts with keys ``title``, ``link``, ``source``,
        ``ts`` and ``ticker``.  The ``title`` includes the ticker and price
        information; the ``link`` points to the Finviz quote page.

    Notes
    -----
    This scanner relies on Finviz Elite’s CSV export feature.  It will
    silently return an empty list if the export fails or no results meet
    the thresholds.  The thresholds should be tuned based on personal
    preference and market conditions.
    """
    settings = get_settings()
    if not getattr(settings, "feature_breakout_scanner", False):
        return []

    # Build Finviz filter string for sub‑$10 tickers with unusual volume
    # Filters reference: https://finviz.com/screener.ashx?v=152&f=sh_price_u10,sh_avgvol_o300,sh_relvol_o1.5
    f_parts = []
    f_parts.append("sh_price_u10")
    if min_avg_vol > 0:
        # Finviz filter uses thousands (k) for volume; divide by 1000 and round
        try:
            k = int(min_avg_vol / 1000)
            # To require >300k, the filter is sh_avgvol_o300
            f_parts.append(f"sh_avgvol_o{k}")
        except Exception:
            pass
    if min_relvol > 0:
        # Finviz uses one decimal place for relative volume: e.g. sh_relvol_o1.5
        try:
            rel_str = ("%.1f" % float(min_relvol)).rstrip("0").rstrip(".")
            f_parts.append(f"sh_relvol_o{rel_str}")
        except Exception:
            pass
    filters = ",".join(f_parts)

    # Fetch screener export rows.  Provide auth via settings; rely on env in export_screener
    try:
        rows = export_screener(filters)
    except Exception:
        return []
    out: List[Dict[str, object]] = []
    for row in rows:
        try:
            sym = row.get("ticker")
            if not sym:
                continue
            price = row.get("price")
            if price is None:
                continue
            # Guard: price must be <= 10
            try:
                if float(price) > 10.0:
                    continue
            except Exception:
                continue
            avgvol = row.get("avgvol")
            if (min_avg_vol > 0) and (avgvol is not None):
                try:
                    if float(avgvol) < float(min_avg_vol):
                        continue
                except Exception:
                    pass
            relvol = row.get("relvolume") or row.get("relvol") or row.get("rel_volume")
            if (min_relvol > 0) and (relvol is not None):
                try:
                    if float(relvol) < float(min_relvol):
                        continue
                except Exception:
                    pass
            # Compose event: include a reason string for context
            ticker = str(sym).upper()
            title = f"{ticker} breakout candidate at ${price}"
            url = f"https://finviz.com/quote.ashx?t={ticker}"
            evt = {
                "id": f"breakout:{ticker}:{_ts_now_iso()}",
                "ticker": ticker,
                "title": title,
                "link": url,
                "canonical_url": url,
                "source": "finviz_breakout",
                "source_host": "finviz.com",
                "published": _ts_now_iso(),
            }
            out.append(evt)
        except Exception:
            continue
    return out