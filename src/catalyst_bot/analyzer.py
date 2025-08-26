from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import get_settings
from .logging_utils import get_logger, setup_logging

log = get_logger("analyzer")


@dataclass
class EventRow:
    ts: datetime
    title: str
    source: str
    ticker: Optional[str]


def _parse_iso(ts: str) -> datetime:
    """Robust ISO parse (assumes Z/UTC or offset)."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _prior_trading_day(utc_now: datetime) -> datetime:
    # Simple weekend logic: Sat/Sun -> Friday; otherwise yesterday
    d = (utc_now - timedelta(days=1)).date()
    if d.weekday() == 6:  # Sunday -> Friday
        d = d - timedelta(days=2)
    elif d.weekday() == 5:  # Saturday -> Friday
        d = d - timedelta(days=1)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _load_events_for_date(path: Path, date_utc: datetime) -> List[EventRow]:
    out: List[EventRow] = []
    if not path.exists():
        return out
    target = date_utc.date()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ts = obj.get("ts")
            title = (obj.get("title") or "").strip()
            if not ts or not title:
                continue
            try:
                when = _parse_iso(ts)
            except Exception:
                continue
            if when.date() != target:
                continue
            out.append(
                EventRow(
                    ts=when,
                    title=title,
                    source=obj.get("source") or "",
                    ticker=obj.get("ticker"),
                )
            )
    return out


def _classify_title(title: str, keyword_categories: Dict[str, List[str]]) -> List[str]:
    """Return list of categories hit by the title, once per category."""
    lt = (title or "").lower()
    hits: List[str] = []
    for cat, phrases in (keyword_categories or {}).items():
        try:
            if any((p or "").lower() in lt for p in phrases):
                hits.append(cat)
        except Exception:
            continue
    return hits


def _compute_weights(
    events: List[EventRow],
    keyword_categories: Dict[str, List[str]],
    default_weight: float,
) -> Dict[str, float]:
    """
    Deterministic weights:
      weight(cat) = default_weight * (1 + count(cat) / max(1, total_hits))
    This keeps a floor at default_weight and adds a small, normalized boost.
    """
    counts = Counter()
    total_hits = 0
    for ev in events:
        hits = _classify_title(ev.title, keyword_categories)
        total_hits += len(hits)
        counts.update(hits)

    if total_hits == 0:
        return {cat: float(default_weight) for cat in keyword_categories.keys()}

    weights: Dict[str, float] = {}
    for cat in keyword_categories.keys():
        c = counts.get(cat, 0)
        w = float(default_weight) * (1.0 + (c / total_hits))
        weights[cat] = round(w, 4)
    return weights


def main(argv: Optional[List[str]] = None) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)

    parser = argparse.ArgumentParser(
        description="Post-close analyzer to update keyword weights."
    )
    parser.add_argument(
        "--date",
        type=str,
        help="UTC date YYYY-MM-DD (default: prior trading day)",
    )
    args = parser.parse_args(argv)

    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            log.warning("invalid --date format; use YYYY-MM-DD")
            return 2
    else:
        target = _prior_trading_day(datetime.now(timezone.utc))

    data_dir = settings.data_dir
    out_dir = settings.out_dir

    events_path = data_dir / "events.jsonl"
    events = _load_events_for_date(events_path, target)
    log.info(
        "analyzer_load date=%s events=%s from=%s",
        target.date().isoformat(),
        len(events),
        str(events_path),
    )

    # compute weights
    kw_cats = settings.keyword_categories
    default_w = settings.keyword_default_weight
    weights = _compute_weights(events, kw_cats, default_w)

    # write artifacts
    os.makedirs(out_dir / "analyzer", exist_ok=True)
    stats_path = data_dir / "analyzer" / "keyword_stats.json"
    os.makedirs(stats_path.parent, exist_ok=True)

    # CSV summary
    csv_path = out_dir / "analyzer" / (f"summary_{target.date().isoformat()}.csv")
    try:
        import csv

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            wcsv = csv.writer(f)
            wcsv.writerow(["ts_utc", "source", "ticker", "title"])
            for ev in events:
                wcsv.writerow([ev.ts.isoformat(), ev.source, ev.ticker or "", ev.title])
        log.info("analyzer_csv path=%s", str(csv_path))
    except Exception as err:
        log.warning("analyzer_csv_failed err=%s", str(err))

    # JSON weights for classifier dynamic load
    try:
        with stats_path.open("w", encoding="utf-8") as f:
            json.dump(weights, f, indent=2, sort_keys=True)
        log.info(
            "analyzer_weights path=%s categories=%s", str(stats_path), len(weights)
        )
    except Exception as err:
        log.warning("analyzer_weights_failed err=%s", str(err))

    # console summary
    log.info("analyzer_result date=%s weights=%s", target.date().isoformat(), weights)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
