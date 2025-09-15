"""Backtest Event Scraper
=========================

This module provides a simple utility for generating historical event
streams suitable for backtesting.  It reads an input JSONL file of
events (in the same format that the live bot writes) and filters the
entries according to a user‑supplied date range and optional
ticker/source filters.  The resulting subset is written to an output
JSONL file which can then be passed directly to the backtest CLI.

Unlike the live ingestion pipeline, this scraper does **not** fetch
fresh data from Finviz, GlobeNewswire or the SEC.  Instead it acts on
existing event logs recorded by the bot.  This design keeps the
scraping process deterministic and avoids repeated network fetches
which may be rate‑limited by third parties.

Example usage::

    python -m catalyst_bot.backtest.scraper \
        --in data/events.jsonl \
        --start 2025-07-01 \
        --end 2025-07-31 \
        --tickers AAPL,MSFT \
        --sources sec_8k,globenewswire_public \
        --out data/events_july.jsonl

This will extract all events between 2025‑07‑01 and 2025‑07‑31 UTC for
the specified tickers and sources, writing them to ``data/events_july.jsonl``.

You can also omit ``--tickers`` or ``--sources`` to include all
tickers or sources, respectively.  Dates are interpreted as
midnight‑to‑midnight in UTC; events outside the range are excluded.

``--start`` and ``--end`` are inclusive on the start date and
exclusive on the end date.  If you only specify ``--start``, all
events from that date forward are included.  If you only specify
``--end``, all events before that date are included.

The input file must be a JSON lines (JSONL) file containing one JSON
object per line.  Each object should have at least a ``ts`` or
``ts_utc`` field (ISO 8601 timestamp), and may include ``ticker`` and
``source`` fields to enable filtering.  Any additional fields are
preserved verbatim in the output.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Iterator, List, Optional, Sequence

from ..logging_utils import get_logger

log = get_logger("backtest.scraper")


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for the event scraper.

    Parameters
    ----------
    argv : list of str, optional
        Optional list of arguments to parse instead of ``sys.argv``.

    Returns
    -------
    argparse.Namespace
        The parsed arguments with attributes ``in`` (input path),
        ``out`` (output path), ``start`` (start date), ``end`` (end
        date), ``tickers`` (list of uppercase symbols or None) and
        ``sources`` (list of lower‑case source strings or None).
    """
    parser = argparse.ArgumentParser(
        description="Filter historical events for backtesting."
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        default="data/events.jsonl",
        help="Path to the input JSONL events file (default: data/events.jsonl)",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default="data/events_filtered.jsonl",
        help="Path for the filtered output JSONL file (default: data/events_filtered.jsonl)",
    )
    parser.add_argument(
        "--start",
        default="",
        help="Inclusive start date (YYYY-MM-DD).  Events before this date are excluded.",
    )
    parser.add_argument(
        "--end",
        default="",
        help=(
            "Exclusive end date (YYYY-MM-DD). "
            "Events on or after this date are excluded."
        ),
    )
    parser.add_argument(
        "--tickers",
        default="",
        help=(
            "Comma-separated list of tickers to include (case-insensitive). "
            "If omitted, all tickers are included."
        ),
    )
    parser.add_argument(
        "--sources",
        default="",
        help=(
            "Comma-separated list of source keys to include (case-insensitive). "
            "If omitted, all sources are included."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "If set, do not write any output file; "
            "just report the number of events that would be included."
        ),
    )
    return parser.parse_args(argv)


def _load_events(path: str) -> Iterator[dict]:
    """Yield events from a JSONL file.

    Parameters
    ----------
    path : str
        The file path to load.

    Yields
    ------
    dict
        Each event dictionary parsed from a line of the file.  Lines that
        cannot be parsed as JSON are skipped silently.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    yield d
                except Exception:
                    # Skip malformed lines but log occasionally
                    log.debug("skipping malformed JSON line in %s", path)
                    continue
    except Exception as exc:
        log.error("failed to read events from %s: %s", path, exc)
        return


def _str_to_date(s: str) -> Optional[datetime]:
    """Convert a YYYY-MM-DD string to a timezone-aware datetime at midnight.

    If the string is empty, returns ``None``.  Raises ValueError on
    invalid formats.
    """
    if not s:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _event_within_range(
    ev: dict, start: Optional[datetime], end: Optional[datetime]
) -> bool:
    """Check whether an event falls within a date range.

    Parameters
    ----------
    ev : dict
        The event dictionary.  It should have a ``ts`` or ``ts_utc``
        string representing an ISO 8601 timestamp.

    start : datetime or None
        Inclusive lower bound.  If None, events before any date are
        included.

    end : datetime or None
        Exclusive upper bound.  If None, events up to any date are
        included.

    Returns
    -------
    bool
        True if the event timestamp is within the specified range.
    """
    ts_val = ev.get("ts") or ev.get("ts_utc") or ev.get("timestamp")
    if not ts_val:
        return False
    try:
        ts = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except Exception:
        return False
    if start and ts < start:
        return False
    if end and ts >= end:
        return False
    return True


def _event_matches_filters(
    ev: dict,
    tickers: Optional[set[str]],
    sources: Optional[set[str]],
) -> bool:
    """Determine if an event matches ticker/source filters.

    Parameters
    ----------
    ev : dict
        The event dictionary.  It may include ``ticker`` and ``source`` keys.

    tickers : set[str] or None
        If a non-empty set, only events whose primary ticker (upper‑case) is
        contained in this set are included.  If None, all tickers are allowed.

    sources : set[str] or None
        If a non-empty set, only events whose source key (lower‑case) is
        contained in this set are included.  If None, all sources are allowed.

    Returns
    -------
    bool
        True if the event should be included.
    """
    if tickers:
        t = (ev.get("ticker") or "").strip().upper()
        if not t or t not in tickers:
            return False
    if sources:
        s = (ev.get("source") or ev.get("source_host") or "").strip().lower()
        if not s or s not in sources:
            return False
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    start_dt = _str_to_date(args.start)
    end_dt = _str_to_date(args.end)
    tickers: Optional[set[str]] = None
    if args.tickers.strip():
        tickers = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
    sources: Optional[set[str]] = None
    if args.sources.strip():
        sources = {s.strip().lower() for s in args.sources.split(",") if s.strip()}
    in_path = args.in_path
    out_path = args.out_path
    count_in = 0
    count_out = 0
    events_out: List[dict] = []
    for ev in _load_events(in_path):
        count_in += 1
        if not _event_within_range(ev, start_dt, end_dt):
            continue
        if not _event_matches_filters(ev, tickers, sources):
            continue
        events_out.append(ev)
        count_out += 1
    log.info(
        "read %d events from %s and selected %d within range",
        count_in,
        in_path,
        count_out,
    )
    if args.dry_run:
        print(f"Would write {count_out} events to {out_path}")
        return 0
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            for ev in events_out:
                fh.write(json.dumps(ev, separators=(",", ":")) + "\n")
        log.info("wrote %d events to %s", count_out, out_path)
    except Exception as exc:
        log.error("failed to write events to %s: %s", out_path, exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
