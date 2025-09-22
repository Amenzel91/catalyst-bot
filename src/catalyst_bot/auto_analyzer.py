"""
Auto Analyzer and log reporter entry points.

This module exposes helpers for scheduling the analyzer and report
generation.  It delegates the actual analysis and delivery work to
callables supplied by the caller, enabling integration with existing
runner code without circular imports.  No network calls are
performed here.

Key functions:

* ``run_scheduled_tasks(now, logs, analyze_fn, report_fn)``: Invoke
  ``analyze_fn`` at the configured schedule when
  ``FEATURE_AUTO_ANALYZER`` is enabled and emit a report when
  ``FEATURE_LOG_REPORTER`` is enabled.  ``analyze_fn`` should take
  no arguments and perform a single analyzer run.  ``report_fn``
  should accept a Markdown string and deliver it to the desired
  destination.

* ``emit_report(logs)``: Manually build and return a digest for the
  current log entries regardless of schedule.  You can supply a
  ``report_fn`` to deliver it; if omitted, the digest is returned.

Use these helpers in your runner to keep scheduling and reporting logic
encapsulated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List

from . import log_reporter
from .config_extras import FEATURE_AUTO_ANALYZER


def run_scheduled_tasks(
    now: datetime,
    logs: List[Dict[str, object]],
    analyze_fn: Callable[[], None] | None = None,
    report_fn: Callable[[str], None] | None = None,
) -> None:
    """Run the analyzer and emit a log report if configured.

    This helper should be called periodically (e.g. every minute) from
    your runner.  It checks both the auto analyzer and log reporter
    feature flags and schedules.  The passed ``analyze_fn`` is invoked
    when the analyzer is scheduled.  If ``report_fn`` is provided, it
    will be used to deliver the digest; otherwise the digest is simply
    returned by ``emit_report`` and ignored.

    Parameters
    ----------
    now: datetime
        Current time (timezone aware).  Naive datetimes are treated as
        UTC.
    logs: List[Dict[str, object]]
        Mutable list of log entries.  Each entry should have a
        ``timestamp`` (datetime) and ``category`` (str).  Entries are
        rotated according to ``LOG_RETENTION_DAYS``.
    analyze_fn: Callable[[], None] or None, optional
        Function to call when the analyzer is scheduled.  May be
        ``None`` if the caller handles analysis elsewhere.
    report_fn: Callable[[str], None] or None, optional
        Function to call with the Markdown digest when a report is
        scheduled.  If ``None``, the digest is built but not delivered.

    Returns
    -------
    None
    """
    # Normalize now to timezone aware UTC
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Run analyzer if enabled and scheduled
    if FEATURE_AUTO_ANALYZER and log_reporter.should_emit_report(now):
        if analyze_fn is not None:
            analyze_fn()

    # Emit report if scheduled
    if log_reporter.should_emit_report(now):
        digest = emit_report(logs)
        if report_fn is not None and digest:
            report_fn(digest)

    # Rotate logs regardless of whether we emitted a report
    logs[:] = log_reporter.rotate_logs(logs, now)


def emit_report(
    logs: List[Dict[str, object]],
    now: datetime | None = None,
    report_fn: Callable[[str], None] | None = None,
) -> str:
    """Build and optionally deliver a digest of the current logs.

    This helper computes the report window based on ``REPORT_TIMEZONE`` and
    ``REPORT_DAYS``, aggregates statistics using
    ``LOG_REPORT_CATEGORIES``, builds a Markdown digest and (if
    ``report_fn`` is provided) calls it with the digest.  It returns
    the digest regardless of whether it is delivered.

    ``logs`` are not rotated by this function; call
    ``log_reporter.rotate_logs`` separately if desired.

    Parameters
    ----------
    logs: List[Dict[str, object]]
        Current log entries.
    now: datetime, optional
        Current time.  Defaults to ``datetime.now(timezone.utc)``.
    report_fn: Callable[[str], None] or None, optional
        Callback to deliver the digest.  If ``None``, the digest is just
        returned.

    Returns
    -------
    str
        The Markdown digest.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    # compute window
    start, end = log_reporter.get_report_range(now)
    stats = log_reporter.get_log_stats(logs)
    digest = log_reporter.build_digest(stats, start, end)
    if report_fn is not None:
        report_fn(digest)
    return digest
