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
    """Simplify simulator rows to a metrics-friendly shape with defaults."""
    return {
        "ticker": r.get("ticker"),
        "realized_return": float(r.get("realized_return", 0.0) or 0.0),
        "intraday_high_return": float(r.get("intraday_high_return", 0.0) or 0.0),
        "next_day_close_return": float(r.get("next_day_close_return", 0.0) or 0.0),
    }


def main() -> int:
    args = _parse_args()
    os.makedirs(args.out, exist_ok=True)
    events = _read_events(args.events, args.start, args.end)
    news = [_event_to_newsitem(e) for e in events]
    results: List[Mapping] = []
    if sim is not None and news and hasattr(sim, "simulate_events"):
        results = sim.simulate_events(news)
    rows = [_row_simplify(r) for r in results]
    rule = HitDefinition(intraday_high_min=args.ihit, next_close_min=args.nchit)
    summary = summarize_backtest(rows, rule)
    md = (
        f"# Backtest Summary\\n"
        f"- N: {summary.n}\\n"
        f"- Hits: {summary.hits}\\n"
        f"- Hit rate: {summary.hit_rate:.3f}\\n"
        f"- Avg return: {summary.avg_return:.4f}\\n"
        f"- Max drawdown: {summary.max_drawdown:.4f}\\n"
    )
    Path(os.path.join(args.out, "summary.md")).write_text(md, encoding="utf-8")
    Path(os.path.join(args.out, "summary.json")).write_text(
        json.dumps(summary.__dict__, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
