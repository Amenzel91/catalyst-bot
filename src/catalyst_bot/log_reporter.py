"""
Utilities for summarising logs and scheduling reports for Catalyst Bot.

This module centralises the logic for determining when to emit a log
report, computing summary statistics from raw log entries, rotating old
logs based on a retention policy, and building human‑readable
Markdown digests.  It is designed to be environment agnostic: no
network calls or external side effects are performed here.  The caller
is responsible for invoking these helpers at the appropriate times and
delivering the resulting report to the desired destination (e.g.
Discord embed, file, email, etc.).

The scheduling logic supports both a simple daily schedule (via
``ANALYZER_UTC_HOUR`` and ``ANALYZER_UTC_MINUTE``) and a flexible,
comma‑separated list of times (``ANALYZER_SCHEDULES``).  The time
comparison is done in UTC.  You can adjust the time zone of the
generated report using ``REPORT_TIMEZONE`` and the length of the
reporting window via ``REPORT_DAYS``.  Old log entries are pruned
according to ``LOG_RETENTION_DAYS`` to keep the digest size bounded.

Usage example::

    from datetime import datetime, timezone
    from catalyst_bot import log_reporter, config_extras

    # assume logs is a list of dicts with ``timestamp`` and ``category`` keys
    now = datetime.now(timezone.utc)
    if log_reporter.should_emit_report(now):
        window_start, window_end = log_reporter.get_report_range(now)
        stats = log_reporter.get_log_stats(logs)
        digest = log_reporter.build_digest(stats, window_start, window_end)
        # deliver digest via your preferred channel
        log_reporter.deliver_report(digest)
        # rotate logs to keep only recent entries
        logs[:] = log_reporter.rotate_logs(logs, now)

All configuration values are read from :mod:`catalyst_bot.config_extras`.
If you need to customise categories or other behaviour, update
``config_extras.py`` or set the corresponding environment variables.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - zoneinfo is available in Python 3.9+
    ZoneInfo = None  # type: ignore

from .config_extras import (
    ADMIN_LOG_DESTINATION,
    ADMIN_LOG_FILE_PATH,
    ANALYZER_SCHEDULES,
    ANALYZER_UTC_HOUR,
    ANALYZER_UTC_MINUTE,
    FEATURE_LOG_REPORTER,
    LOG_REPORT_CATEGORIES,
    LOG_RETENTION_DAYS,
    REPORT_DAYS,
    REPORT_TIMEZONE,
)


def _parse_time_pair(part: str) -> Tuple[int, int]:
    """Parse a ``HH:MM`` time string into a (hour, minute) tuple.

    Invalid formats raise ``ValueError``.
    """
    part = part.strip()
    if not part:
        raise ValueError("empty time string")
    if ":" not in part:
        raise ValueError(f"Invalid time format: {part}")
    hh, mm = part.split(":", 1)
    return int(hh), int(mm)


def _parse_schedules(schedule_str: str) -> List[Tuple[int, int]]:
    """Parse a comma‑separated list of ``HH:MM`` times into a list of tuples."""
    schedule_str = schedule_str.strip()
    schedules: List[Tuple[int, int]] = []
    if not schedule_str:
        return schedules
    for part in schedule_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            schedules.append(_parse_time_pair(part))
        except ValueError:
            # Ignore invalid entries silently
            continue
    return schedules


def should_emit_report(now: datetime) -> bool:
    """Return ``True`` if a log report should be emitted at the given time.

    The function first checks the ``FEATURE_LOG_REPORTER`` flag.  If the
    feature is disabled, it returns ``False`` immediately.  Otherwise,
    it looks at ``ANALYZER_SCHEDULES``; if it is non‑empty, the report
    will be emitted at any of the listed ``HH:MM`` times (UTC).  If
    ``ANALYZER_SCHEDULES`` is empty, the fallback schedule defined by
    ``ANALYZER_UTC_HOUR`` and ``ANALYZER_UTC_MINUTE`` is used.

    Parameters
    ----------
    now: datetime
        The current time (assumed to be timezone‑aware and in UTC).

    Returns
    -------
    bool
        Whether a report should be emitted at this moment.
    """
    if not FEATURE_LOG_REPORTER:
        return False
    # ensure timezone aware
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_utc = now.astimezone(timezone.utc)
    schedules = _parse_schedules(ANALYZER_SCHEDULES)
    if schedules:
        for hh, mm in schedules:
            if now_utc.hour == hh and now_utc.minute == mm:
                return True
        return False
    # fallback to single schedule
    return now_utc.hour == ANALYZER_UTC_HOUR and now_utc.minute == ANALYZER_UTC_MINUTE


def _get_timezone(tz_name: str):
    """Return a tzinfo object for the given IANA time zone name.

    If the time zone name cannot be resolved, UTC is returned.
    """
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def get_report_range(now: datetime) -> Tuple[datetime, datetime]:
    """Compute the start and end timestamps for the reporting window.

    ``REPORT_TIMEZONE`` and ``REPORT_DAYS`` determine the window.  The
    end of the window is ``now`` converted to the report time zone.  The
    start is ``REPORT_DAYS`` days earlier.  Both returned datetimes are
    timezone‑aware in the report time zone.

    Parameters
    ----------
    now: datetime
        The current time (timezone aware).  Naive datetimes are
        treated as UTC.

    Returns
    -------
    Tuple[datetime, datetime]
        (window_start, window_end) in ``REPORT_TIMEZONE``.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    tzinfo = _get_timezone(REPORT_TIMEZONE)
    end = now.astimezone(tzinfo)
    start = end - timedelta(days=REPORT_DAYS)
    return start, end


def get_log_stats(log_entries: List[Dict[str, object]]) -> Dict[str, int]:
    """Aggregate log entries by category.

    Only categories listed in ``LOG_REPORT_CATEGORIES`` are tallied; all
    other categories are ignored.  The returned dictionary preserves
    the order of ``LOG_REPORT_CATEGORIES``.

    Parameters
    ----------
    log_entries: List[Dict[str, object]]
        A list of log entry dictionaries.  Each entry must have a
        ``category`` key whose value is a string.

    Returns
    -------
    Dict[str, int]
        A mapping from category to count.
    """
    counts: Dict[str, int] = {cat: 0 for cat in LOG_REPORT_CATEGORIES}
    for entry in log_entries:
        cat = entry.get("category")
        if isinstance(cat, str) and cat in counts:
            counts[cat] += 1
    return counts


def rotate_logs(
    log_entries: List[Dict[str, object]], now: datetime
) -> List[Dict[str, object]]:
    """Prune log entries older than ``LOG_RETENTION_DAYS``.

    This helper returns a new list containing only those entries whose
    ``timestamp`` (expected to be a datetime) is within the
    retention window.  Naive timestamps are assumed to be UTC.

    Parameters
    ----------
    log_entries: List[Dict[str, object]]
        A list of log entry dicts with a ``timestamp`` key.
    now: datetime
        Current time (timezone aware).  Naive datetimes are treated as UTC.

    Returns
    -------
    List[Dict[str, object]]
        Filtered list of log entries within retention.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    threshold = now - timedelta(days=LOG_RETENTION_DAYS)
    result: List[Dict[str, object]] = []
    for entry in log_entries:
        ts = entry.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= threshold:
            result.append(entry)
    return result


def build_digest(stats: Dict[str, int], start: datetime, end: datetime) -> str:
    """Build a Markdown digest string from aggregated statistics.

    The digest begins with a heading indicating the time range and
    continues with a bullet list of counts.  Categories with zero
    counts are still included for completeness.  The caller is free
    to format this digest as a Discord embed or any other markup.

    Parameters
    ----------
    stats: Dict[str, int]
        Mapping of categories to counts.
    start: datetime
        Start of the reporting window (timezone aware).
    end: datetime
        End of the reporting window (timezone aware).

    Returns
    -------
    str
        A Markdown formatted summary.
    """
    # Format timestamps in ISO 8601 with offset
    start_str = start.isoformat()
    end_str = end.isoformat()
    lines = []
    lines.append(f"**Log Summary** (from {start_str} to {end_str})")
    lines.append("")
    for cat in LOG_REPORT_CATEGORIES:
        count = stats.get(cat, 0)
        lines.append(f"- **{cat}**: {count}")
    return "\n".join(lines)


def deliver_report(digest: str) -> None:
    """Deliver the report to the configured destination.

    When ``ADMIN_LOG_DESTINATION`` is ``"embed"``, the digest is
    returned as‑is so the caller can post it to the admin webhook as a
    Discord embed.  When set to ``"file"``, the digest is written to
    ``ADMIN_LOG_FILE_PATH``.  Other destinations are ignored.

    Parameters
    ----------
    digest: str
        The Markdown report to deliver.

    Returns
    -------
    None
    """
    if ADMIN_LOG_DESTINATION == "file":
        try:
            # ensure directory exists
            path = ADMIN_LOG_FILE_PATH
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(digest)
        except Exception:
            # swallow exceptions; caller may log an error
            pass
    # For "embed" and other destinations, do nothing here; caller
    # should handle posting the digest to Discord or other services.
