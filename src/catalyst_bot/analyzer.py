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
from uuid import uuid4

from .alerts import post_admin_summary_md
from .approval import get_pending_plan, promote_if_approved, write_pending_plan
from .classifier import load_keyword_weights
from .classify_bridge import classify_text
from .config import get_settings
from .earnings import load_earnings_calendar
from .logging_utils import get_logger
from .market import get_last_price_change

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
    """Run one analyzer pass for the specified (or inferred) UTC date.

    In addition to the simple CSV summary and baseline keyword weights,
    this enhanced analyzer computes per-category hit/miss/neutral statistics
    based on price moves, generates proposed weight adjustments, records
    newly observed keywords, writes a Markdown report, and emits a
    pending changes file for admin review.
    """
    settings = _get_settings_safe()
    data_dir, out_dir, analyzer_dir = _paths()

    today_utc = datetime.now(timezone.utc).date()
    target = for_date or today_utc

    # Load events for the day
    events_path = data_dir / "events.jsonl"
    events = _load_events_for_date(events_path, target)

    # Load earnings calendar and determine upcoming earnings for tickers in events.
    # This checks the cached CSV saved by jobs/earnings_pull.py.  Only the
    # earliest upcoming report date per ticker is used.
    earnings_today: Dict[str, date_cls] = {}
    earnings_week: Dict[str, date_cls] = {}
    try:
        earn_map = load_earnings_calendar(
            getattr(settings, "earnings_calendar_cache", "data/earnings_calendar.csv")
        )
        if earn_map:
            for e in events:
                ticker = str(e.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                edate = earn_map.get(ticker)
                if not edate:
                    continue
                # Determine relation to target date
                try:
                    delta = (edate - target).days
                except Exception:
                    continue
                if delta == 0:
                    earnings_today[ticker] = edate
                elif 0 < delta <= 7:
                    # Only include one entry per ticker for the week
                    earnings_week.setdefault(ticker, edate)
    except Exception:
        # fall back silently on errors
        earnings_today = {}
        earnings_week = {}

    log.info(
        "analyzer_load date=%s events=%d from=%s",
        target.isoformat(),
        len(events),
        str(events_path),
    )

    # Load keyword weights (fallbacks to defaults) for classification
    keyword_weights: Dict[str, float] = load_keyword_weights(
        os.path.join(str(data_dir), "keyword_weights.json")
    )

    # Configure hit thresholds from environment
    try:
        hit_up = float(os.getenv("ANALYZER_HIT_UP_THRESHOLD_PCT", "5").strip())
    except Exception:
        hit_up = 5.0
    try:
        hit_down = float(os.getenv("ANALYZER_HIT_DOWN_THRESHOLD_PCT", "-5").strip())
    except Exception:
        hit_down = -5.0

    # Aggregate stats per category: [hits, misses, neutrals]
    category_stats: Dict[str, List[int]] = {}
    weight_proposals: Dict[str, float] = {}
    unknown_keywords: Dict[str, int] = {}

    for e in events:
        title = str(e.get("title") or "")
        ticker = str(e.get("ticker") or "").upper()
        if not ticker:
            continue

        # Classify title to get tags (unify bridge when enabled)
        try:
            if getattr(get_settings(), "feature_classifier_unify", False):
                out = classify_text(title)
                tags = list(out.get("tags") or [])
            else:
                from .classifier import classify as legacy_classify

                cls = legacy_classify(title, keyword_weights)
                tags = list(cls.get("tags", []))
        except Exception:
            tags = []

        # Determine categories matched by tags
        keyword_categories = getattr(settings, "keyword_categories", {}) or {}
        matched_cats = set()
        for cat, kws in keyword_categories.items():
            if not isinstance(kws, (list, tuple, set)):
                continue
            if any(kw in tags for kw in kws):
                matched_cats.add(cat)
        if not matched_cats:
            matched_cats = {"uncategorized"}

        # Record unknown keywords
        for kw in tags:
            if kw not in keyword_weights:
                unknown_keywords[kw] = unknown_keywords.get(kw, 0) + 1

        # Fetch last price change percentage
        _, change_pct = get_last_price_change(ticker)
        if change_pct is not None and change_pct >= hit_up:
            outcome = 1
        elif change_pct is not None and change_pct <= hit_down:
            outcome = -1
        else:
            outcome = 0

        # Update category statistics
        for cat in matched_cats:
            stats = category_stats.setdefault(cat, [0, 0, 0])
            if outcome > 0:
                stats[0] += 1
            elif outcome < 0:
                stats[1] += 1
            else:
                stats[2] += 1

    # Compute proposed new weights
    for cat, counts in category_stats.items():
        hits, misses, neutrals = counts
        total = hits + misses
        if total == 0:
            continue
        old_weight = 1.0
        # Pull existing weight from keyword_stats.json if present
        kw_stats_path = analyzer_dir / "keyword_stats.json"
        try:
            if kw_stats_path.exists():
                raw = json.loads(kw_stats_path.read_text(encoding="utf-8"))
                val = raw.get(cat)
                if isinstance(val, (int, float)):
                    old_weight = float(val)
        except Exception:
            pass
        score = (hits - misses) / total
        delta = old_weight * 0.1 * score
        new_weight = max(0.5, min(old_weight + delta, 3.0))
        weight_proposals[cat] = new_weight

    # Write standard CSV summary and baseline weights (unchanged)
    csv_path = _write_csv_summary(out_dir, target, events)
    baseline_weights = {
        k: 1.0 for k in (getattr(settings, "keyword_categories", {}) or {}).keys()
    }
    weights_path = _write_keyword_weights(analyzer_dir, baseline_weights)

    # Write report and pending change files
    report_path = _write_markdown_report(
        out_dir,
        target,
        events,
        category_stats,
        weight_proposals,
        unknown_keywords,
        earnings_today=earnings_today,
        earnings_week=earnings_week,
    )
    pending_path = _write_pending_changes(
        analyzer_dir,
        target,
        weight_proposals,
        unknown_keywords,
    )

    # --- Optional: append report enrichments (Top movers / Anomalies) ---
    try:
        if (os.getenv("FEATURE_REPORT_ENRICH", "") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            # Use list(events) so we don't exhaust the iterator
            _append_enrichments(str(report_path), list(events))
    except Exception:
        pass

    # --- Optional: approval loop (file-based) ---
    try:
        # Determine whether the approval loop is enabled.  Prefer the
        # configuration setting from Settings, but fall back to the
        # environment variable FEATURE_APPROVAL_LOOP for backward
        # compatibility.  Any truthy value in {"1", "true", "yes", "on"}
        # will enable the loop.
        enable_loop: bool = False
        try:
            enable_loop = getattr(get_settings(), "feature_approval_loop", False)
        except Exception:
            enable_loop = False
        if not enable_loop:
            env_val = (os.getenv("FEATURE_APPROVAL_LOOP", "") or "").strip().lower()
            if env_val in {"1", "true", "yes", "on"}:
                enable_loop = True
        if enable_loop:
            # Write a pending plan if we have proposals and none exists yet
            if weight_proposals and not get_pending_plan():
                plan_id = _make_plan_id(for_date or target)
                write_pending_plan(
                    {"weights": weight_proposals, "new_keywords": unknown_keywords},
                    plan_id,
                )
            # Promote if an approval marker file is present
            promote_if_approved()
    except Exception:
        pass

    # Optional: post admin summary embed
    try:
        if getattr(get_settings(), "feature_admin_embed", False):
            post_admin_summary_md(str(report_path))
    except Exception:
        pass

    log.info(
        "analyzer_result date=%s events=%d categories=%d pending=%s report=%s",
        target.isoformat(),
        len(events),
        len(weight_proposals),
        str(pending_path),
        str(report_path),
    )
    return AnalyzeResult(
        date=target,
        weights=baseline_weights,
        csv_path=csv_path,
        weights_path=weights_path,
        events_count=len(events),
    )


def _maybe_append_backtest_section(report_path: str) -> None:
    """
    Placeholder for appending backtest metrics to the report.
    Future versions may implement this; currently no-op.
    """
    _ = report_path
    return


def _append_enrichments(report_path: str, events: List[Dict[str, object]]) -> None:
    """
    Append Top Movers and Anomalies sections to the report.
    Uses existing price fetchers; gracefully degrades on errors.
    """
    try:
        top_n = int(os.getenv("REPORT_TOP_MOVERS_N", "10"))
    except Exception:
        top_n = 10
    try:
        threshold = float(os.getenv("REPORT_ANOMALY_ABS_PCT", "8.0"))
    except Exception:
        threshold = 8.0

    per_ticker: Dict[str, float] = {}
    for ev in events:
        tkr = str((ev.get("ticker") or "")).strip().upper()
        if not tkr or tkr in per_ticker:
            continue
        try:
            res = get_last_price_change(tkr)
            change_pct = None
            if isinstance(res, tuple):
                _, change_pct = res
            else:
                change_pct = res
            if change_pct is None:
                continue
            per_ticker[tkr] = float(change_pct)
        except Exception:
            continue
    if not per_ticker:
        return
    movers = sorted(per_ticker.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
    anomalies = [(t, c) for t, c in movers if abs(c) >= threshold]

    lines: List[str] = []
    lines.append("\n## Top Movers")
    for t, c in movers:
        sign = "+" if c >= 0 else ""
        lines.append(f"- `{t}` {sign}{c:.2f}%")
    if anomalies:
        lines.append("\n## Anomalies")
        for t, c in anomalies:
            sign = "+" if c >= 0 else ""
            lines.append(f"- `{t}` anomaly {sign}{c:.2f}%")

    try:
        with open(report_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except Exception:
        pass


def _make_plan_id(target_date: date_cls) -> str:
    """
    Generate a plan identifier string based on the target date.
    """
    return f"plan-{target_date.isoformat()}"


def _write_markdown_report(
    out_dir: Path,
    target: date_cls,
    events: Iterable[Dict[str, object]],
    category_stats: Dict[str, List[int]],
    weight_proposals: Dict[str, float],
    unknown_keywords: Dict[str, int],
    *,
    earnings_today: Optional[Dict[str, date_cls]] = None,
    earnings_week: Optional[Dict[str, date_cls]] = None,
) -> Path:
    """
    Generate a daily Markdown report summarizing event counts,
    category hit/miss/neutral statistics, proposed weight changes, and
    newly discovered keywords. The report is written to
    out/analyzer/summary_<date>.md.
    """
    path = out_dir / f"summary_{target.isoformat()}.md"
    try:
        lines: List[str] = []
        lines.append(f"# Daily Analyzer Report – {target.isoformat()}")
        total_events = len(list(events))
        lines.append("")
        lines.append(f"**Total events processed:** {total_events}")
        lines.append("")
        if category_stats:
            lines.append("## Category Performance")
            lines.append("| Category | Hits | Misses | Neutrals |")
            lines.append("|---|---:|---:|---:|")
            for cat, counts in sorted(category_stats.items()):
                hits, misses, neutrals = counts
                lines.append(f"| {cat} | {hits} | {misses} | {neutrals} |")
            lines.append("")
        if weight_proposals:
            lines.append("## Proposed Weight Adjustments")
            lines.append(
                "These weights adjust the influence of each category based on hit/miss ratios."
            )
            lines.append("| Category | Proposed Weight |")
            lines.append("|---|---:|")
            for cat, w in sorted(weight_proposals.items()):
                lines.append(f"| {cat} | {w:.3f} |")
            lines.append("")
        if unknown_keywords:
            lines.append("## Newly Discovered Keywords")
            lines.append(
                "The following keywords were observed in news titles "
                "but are not currently present in the keyword weights file. "
                "Consider adding them with an appropriate weight."
            )
            lines.append("| Keyword | Count |")
            lines.append("|---|---:|")
            for kw, cnt in sorted(unknown_keywords.items(), key=lambda x: -x[1]):
                lines.append(f"| {kw} | {cnt} |")
            lines.append("")

        # Append earnings calendar highlights when provided
        try:
            et = earnings_today or {}
            ew = earnings_week or {}
            if et or ew:
                lines.append("## Upcoming Earnings")
                lines.append("| Ticker | Report Date | Relative |")
                lines.append("|---|---|---|")
                for t, d in sorted(et.items()):
                    lines.append(f"| {t} | {d.isoformat()} | Today |")
                for t, d in sorted(ew.items()):
                    # Avoid duplicating tickers already listed under today
                    if t in et:
                        continue
                    lines.append(f"| {t} | {d.isoformat()} | This Week |")
                lines.append("")
        except Exception:
            # If anything goes wrong, skip earnings section
            pass
        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass
    return path


def _write_pending_changes(
    analyzer_dir: Path,
    target: date_cls,
    weight_proposals: Dict[str, float],
    unknown_keywords: Dict[str, int],
) -> Path:
    """
    Write a pending changes JSON file. The filename includes a short plan ID.
    The file contains the date, proposed weight adjustments, and new keywords
    for the admin to review before applying changes to keyword_stats.json.
    """
    plan_id = uuid4().hex[:8]
    pending_data = {
        "plan_id": plan_id,
        "date": target.isoformat(),
        "weights": weight_proposals,
        "new_keywords": unknown_keywords,
    }
    try:
        path = analyzer_dir / f"pending_{plan_id}.json"
        path.write_text(
            json.dumps(pending_data, indent=2, sort_keys=True), encoding="utf-8"
        )
        return path
    except Exception:
        return analyzer_dir / f"pending_{plan_id}.json"


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

    # Import here to avoid circulars; prefer a dedicated "run once" helper.
    try:
        # Try to find a run_analyzer_once function on this module. If
        # defined, call it with the provided settings. Otherwise, fall back
        # to analyze_once() which performs a single pass using the inferred
        # date and writes outputs.
        run_once = globals().get("run_analyzer_once")
        if callable(run_once):
            run_once(settings)
        else:
            analyze_once()
        return True
    except Exception:
        # Bubble up to runner for traceback logging
        raise
    # Should not reach here
    return False


def run_analyzer_once(settings) -> AnalyzeResult:
    """Execute a single analyzer run using the provided settings.

    This helper mirrors the legacy entrypoint expected by the runner. It
    currently ignores the incoming settings, as all configuration is
    resolved within `analyze_once`. In future iterations the settings
    object may control sentiment/score thresholds and other parameters.
    It returns the `AnalyzeResult` from `analyze_once` for convenience.
    """
    # Respect explicit date overrides via settings if provided in the future.
    return analyze_once()
