from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Mapping

from ..models import NewsItem
from .metrics import HitDefinition, summarize_backtest

try:
    from . import simulator as sim  # optional
except Exception:
    sim = None  # type: ignore


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Catalyst backtest CLI")
    p.add_argument("--events", default="data/events.jsonl", help="Path to JSONL events")
    p.add_argument("--start", default="", help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default="", help="End date (YYYY-MM-DD)")
    p.add_argument("--out", default="out/backtest/run", help="Output directory")
    p.add_argument(
        "--ihit", type=float, default=0.08, help="Intraday high hit threshold"
    )
    p.add_argument("--nchit", type=float, default=0.03, help="Next close hit threshold")
    return p.parse_args()


def _read_events(path: str, start: str = "", end: str = "") -> List[Mapping]:
    items: List[Mapping] = []
    sdt = datetime.fromisoformat(start) if start else None
    edt = datetime.fromisoformat(end) if end else None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts_val = d.get("ts") or d.get("ts_utc") or d.get("timestamp")
                if not ts_val:
                    continue
                try:
                    ts = datetime.fromisoformat(
                        str(ts_val).replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except Exception:
                    continue
                if sdt and ts < sdt.replace(tzinfo=timezone.utc):
                    continue
                if edt and ts > edt.replace(tzinfo=timezone.utc):
                    continue
                items.append(d)
    except Exception:
        pass
    return items


def _event_to_newsitem(ev: Mapping) -> NewsItem:
    return NewsItem(
        ts_utc=ev.get("ts") or ev.get("ts_utc") or ev.get("timestamp"),
        title=ev.get("title") or "",
        canonical_url=ev.get("link") or ev.get("canonical_url") or "",
        source_host=ev.get("source") or ev.get("source_host") or "",
        ticker=(ev.get("ticker") or "").strip() or None,
        raw=dict(ev),
    )


def _row_simplify(r: Mapping) -> Mapping:
    """Simplify simulator rows or TradeSimResult objects to a metrics-friendly shape.

    Parameters
    ----------
    r : Mapping or TradeSimResult
        A result entry produced by the backtest simulator.  The simulator may
        return either dictionaries (for legacy formats) or ``TradeSimResult``
        instances.  This helper normalises both into a flat dictionary
        containing the ticker symbol and return metrics expected by the
        backtest metrics summariser.

    Returns
    -------
    dict
        A dictionary with keys ``ticker``, ``realized_return``,
        ``intraday_high_return`` and ``next_day_close_return``.  Missing
        values default to 0.0.
    """
    # If the result is a TradeSimResult dataclass, extract fields directly.
    # We intentionally avoid importing TradeSimResult here; instead we
    # detect dataclass-like objects by checking for attributes ``item``
    # and ``returns`` below.  Importing the type solely to check its
    # existence would cause an unused variable assignment and trigger
    # flake8 F841.
    # Check for dataclass attributes typical of TradeSimResult
    if hasattr(r, "item") and hasattr(r, "returns"):
        ticker = None
        try:
            ticker = getattr(r.item, "ticker", None)
        except Exception:
            ticker = None
        returns_dict = {}
        try:
            returns_dict = getattr(r, "returns", {}) or {}
        except Exception:
            returns_dict = {}
        # In backtests we use the midpoint return as realised return
        mid = returns_dict.get("mid", 0.0) if isinstance(returns_dict, dict) else 0.0
        return {
            "ticker": ticker,
            "realized_return": float(mid or 0.0),
            "intraday_high_return": 0.0,
            "next_day_close_return": 0.0,
        }
    # Otherwise treat as mapping (dictionary-like)
    try:
        get = r.get  # type: ignore[attr-defined]
    except Exception:
        # Not a mapping; return defaults
        return {
            "ticker": None,
            "realized_return": 0.0,
            "intraday_high_return": 0.0,
            "next_day_close_return": 0.0,
        }
    return {
        "ticker": get("ticker"),
        "realized_return": float(get("realized_return", 0.0) or 0.0),
        "intraday_high_return": float(get("intraday_high_return", 0.0) or 0.0),
        "next_day_close_return": float(get("next_day_close_return", 0.0) or 0.0),
    }


def main() -> int:
    args = _parse_args()
    os.makedirs(args.out, exist_ok=True)
    events = _read_events(args.events, args.start, args.end)
    # Convert events to NewsItem for downstream metrics, but pass the raw
    # event dicts to the simulator.  ``simulate_events`` expects a list of
    # dictionaries and will convert them internally.  We still convert
    # NewsItem objects for summarizing non-backtest metrics.
    [_event_to_newsitem(e) for e in events]
    results_list: List[Mapping] = []
    if sim is not None and events and hasattr(sim, "simulate_events"):
        # Run the simulator with the raw event dictionaries.  Results may be
        # TradeSimResult objects with a ``provider`` attribute indicating
        # which price provider served the fill.
        results_list = sim.simulate_events(events)  # type: ignore[arg-type]
    # Compute provider usage counts if available.
    provider_usage: Mapping[str, int] = {}
    if results_list:
        try:
            if hasattr(sim, "summarize_provider_usage"):
                provider_usage = sim.summarize_provider_usage(results_list)  # type: ignore
        except Exception:
            provider_usage = {}
    # Simplify TradeSimResult or mapping to a dictionary for metrics.
    rows = [_row_simplify(r) for r in results_list]
    rule = HitDefinition(intraday_high_min=args.ihit, next_close_min=args.nchit)
    summary = summarize_backtest(rows, rule)
    # Build markdown summary including provider usage if present
    md_lines = [
        "# Backtest Summary",
        f"- N: {summary.n}",
        f"- Hits: {summary.hits}",
        f"- Hit rate: {summary.hit_rate:.3f}",
        f"- Avg return: {summary.avg_return:.4f}",
        f"- Max drawdown: {summary.max_drawdown:.4f}",
    ]
    if provider_usage:
        usage_parts = [
            f"{k}={v}"
            for k, v in sorted(provider_usage.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        md_lines.append(f"- Provider usage: {', '.join(usage_parts)}")
    md = "\\n".join(md_lines) + "\\n"
    Path(os.path.join(args.out, "summary.md")).write_text(md, encoding="utf-8")
    # Include provider usage in JSON output if available
    summary_dict = summary.__dict__.copy()
    if provider_usage:
        summary_dict["provider_usage"] = provider_usage
    Path(os.path.join(args.out, "summary.json")).write_text(
        json.dumps(summary_dict, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
