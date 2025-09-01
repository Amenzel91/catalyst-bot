"""Daily analyzer for Catalyst Bot.

- Reads events (if any) from data/events.jsonl for a given date.
- Emits a CSV summary under out/analyzer/.
- Writes dynamic keyword weights to data/analyzer/keyword_stats.json.
- Exposes a helper hook run_analyzer_once_if_scheduled() for the runner loop.

This is intentionally lightweight so it never blocks the main pipeline.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .logging_utils import get_logger

log = get_logger("analyzer")


# ------------------------------- Paths -------------------------------------


def _repo_root() -> Path:
    # .../catalyst-bot/src/catalyst_bot/analyzer.py -> repo root
    return Path(__file__).resolve().parents[2]


def _paths() -> Tuple[Path, Path, Path]:
    root = _repo_root()
    data_dir = root / "data"
    out_dir = root / "out" / "analyzer"
    analyzer_dir = data_dir / "analyzer"
    out_dir.mkdir(parents=True, exist_ok=True)
    analyzer_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, out_dir, analyzer_dir


# ----------------------------- Settings ------------------------------------


def _get_settings_safe():
    """Try to import get_settings from settings, then config; else stub."""
    try:
        from .settings import get_settings  # type: ignore

        return get_settings()
    except Exception:
        try:
            from .config import get_settings  # type: ignore

            return get_settings()
        except Exception:
            # Minimal stub so analyzer never blocks the runner
            class _S:
                log_level = "INFO"
                keyword_categories = {
                    "fda": [],
                    "clinical": [],
                    "partnership": [],
                    "uplisting": [],
                    "dilution": [],
                    "going_concern": [],
                }

            return _S()


# ------------------------------- IO ----------------------------------------


def _load_events_for_date(
    events_path: Path, target: date_cls
) -> List[Dict[str, object]]:
    """Load events for the given date from a JSONL file."""
    out: List[Dict[str, object]] = []
    if not events_path.exists():
        return out

    try:
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ts_str = str(obj.get("ts") or obj.get("timestamp") or "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                continue
            if ts.date() == target:
                out.append(obj)
    except Exception:
        return []

    return out


def _write_csv_summary(
    out_dir: Path, target: date_cls, events: Iterable[Dict[str, object]]
) -> Path:
    path = out_dir / f"summary_{target.isoformat()}.csv"
    try:
        with path.open("w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["date", "events_count"])
            events_list = list(events)
            w.writerow([target.isoformat(), len(events_list)])
    except Exception:
        pass
    return path


def _write_keyword_weights(analyzer_dir: Path, weights: Dict[str, float]) -> Path:
    path = analyzer_dir / "keyword_stats.json"
    try:
        path.write_text(json.dumps(weights, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass
    return path


# --------------------------- Core analyzer ----------------------------------


@dataclass
class AnalyzeResult:
    date: date_cls
    weights: Dict[str, float]
    csv_path: Path
    weights_path: Path
    events_count: int


def analyze_once(for_date: Optional[date_cls] = None) -> AnalyzeResult:
    """Run one analyzer pass for the specified (or inferred) UTC date."""
    settings = _get_settings_safe()
    data_dir, out_dir, analyzer_dir = _paths()

    today_utc = datetime.now(timezone.utc).date()
    target = for_date or today_utc

    events_path = data_dir / "events.jsonl"
    events = _load_events_for_date(events_path, target)

    log.info(
        "analyzer_load date=%s events=%d from=%s",
        target.isoformat(),
        len(events),
        str(events_path),
    )

    # Baseline: one weight per configured keyword category (all 1.0).
    keyword_categories = getattr(settings, "keyword_categories", {}) or {}
    weights = {k: 1.0 for k in keyword_categories.keys()} or {
        "fda": 1.0,
        "clinical": 1.0,
        "partnership": 1.0,
        "uplisting": 1.0,
        "dilution": 1.0,
        "going_concern": 1.0,
    }

    csv_path = _write_csv_summary(out_dir, target, events)
    log.info("analyzer_csv path=%s", str(csv_path))

    weights_path = _write_keyword_weights(analyzer_dir, weights)
    log.info("analyzer_weights path=%s categories=%d", str(weights_path), len(weights))

    log.info("analyzer_result date=%s weights=%s", target.isoformat(), weights)
    return AnalyzeResult(
        date=target,
        weights=weights,
        csv_path=csv_path,
        weights_path=weights_path,
        events_count=len(events),
    )


# ---------------------- Runner integration hook -----------------------------


def _scheduled_minute_token(dt_utc: datetime, hour: int, minute: int) -> str:
    return f"{dt_utc.date().isoformat()}-{hour:02d}{minute:02d}"


def _already_ran_marker_path(analyzer_dir: Path) -> Path:
    return analyzer_dir / "last_run_marker.txt"


def run_analyzer_once_if_scheduled(settings) -> bool:
    """
    Run the analyzer once when the current UTC clock matches the configured schedule.
    Returns True if it ran, False otherwise.
    """
    from datetime import datetime, timezone

    # Allow both config properties and env fallbacks
    hour = getattr(settings, "analyzer_run_utc_hour", None)
    minute = getattr(settings, "analyzer_run_utc_minute", None)

    try:
        if hour is None:
            hour = int(os.getenv("ANALYZER_UTC_HOUR", "1"))
        if minute is None:
            minute = int(os.getenv("ANALYZER_UTC_MINUTE", "0"))
    except Exception:
        hour, minute = 1, 0  # safe default 01:00 UTC

    now_dt = datetime.now(timezone.utc)
    if now_dt.hour != int(hour) or now_dt.minute != int(minute):
        return False

    # Import here to avoid circulars
    try:
        # If you have a dedicated "run once" entrypoint, use it:
        run_once = globals().get("run_analyzer_once")
        if callable(run_once):
            run_once(settings)
            return True
    except Exception:
        # Bubble up to runner for traceback logging
        raise

    return False
