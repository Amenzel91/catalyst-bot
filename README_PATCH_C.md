Patch C – Auto Analyzer & Log Reporter
=====================================

This patch rounds out Wave 4 by introducing flexible scheduling for the
analyzer and a robust log reporter.  It adds new configuration keys
to `config_extras.py`, two helper modules (`log_reporter.py` and
`auto_analyzer.py`), and guidelines for integration.  The goal is to
automate analysis runs and deliver concise summaries of log activity
without cluttering the existing codebase.

Key features
------------

* **Flexible scheduling:** Define one or more analysis/report times via
  `ANALYZER_SCHEDULES` (comma‑separated list of `HH:MM` in UTC) or
  fall back to `ANALYZER_UTC_HOUR` and `ANALYZER_UTC_MINUTE` for a
  single daily run.  Scheduling checks occur in UTC.

* **Time zone and day window:** Use `REPORT_TIMEZONE` to specify the
  time zone for report timestamps and `REPORT_DAYS` to set the number
  of days included in the summary (e.g. set `REPORT_DAYS=7` for a
  weekly digest).  Windows always end at the time the report is
  generated.

* **Adjustable categories:** `LOG_REPORT_CATEGORIES` controls which
  counters appear in the summary and in what order.  Default
  categories include: `items`, `deduped`, `skipped_no_ticker`,
  `skipped_price_gate`, `skipped_instr`, `skipped_by_source`,
  `skipped_low_score`, `skipped_sent_gate`, `skipped_cat_gate`,
  `skipped_seen`.  Unknown categories are ignored.

* **Alternate delivery:** Set `ADMIN_LOG_DESTINATION` to `embed` (default)
  to produce a Markdown digest for a Discord embed, or `file` to
  write the digest to `ADMIN_LOG_FILE_PATH`.  Other destinations can
  be implemented externally.  The `deliver_report` helper performs no
  network calls.

* **Manual trigger:** The `auto_analyzer.emit_report(logs, now,
  report_fn)` function builds a digest on demand and optionally
  delivers it via the provided callback.  Use this for ad‑hoc
  summaries or debugging.

* **Retention and rotation:** Logs older than `LOG_RETENTION_DAYS` are
  pruned whenever `run_scheduled_tasks` is called, preventing
  indefinite growth.  Set this to a sensible number of days based on
  your log volume.

Configuration
-------------

Add the following entries to your `.env` (or update your
`env.example.ini`) to configure Patch C.  All values shown here are
defaults; adjust as needed:

```ini
FEATURE_AUTO_ANALYZER=0
FEATURE_LOG_REPORTER=0
# Use a comma‑separated list of HH:MM times in UTC, or leave empty to
# fall back to the single time below
ANALYZER_SCHEDULES=
ANALYZER_UTC_HOUR=23
ANALYZER_UTC_MINUTE=55
REPORT_TIMEZONE=UTC
REPORT_DAYS=1
LOG_REPORT_CATEGORIES=items,deduped,skipped_no_ticker,skipped_price_gate,skipped_instr,skipped_by_source,skipped_low_score,skipped_sent_gate,skipped_cat_gate,skipped_seen
ADMIN_LOG_DESTINATION=embed
ADMIN_LOG_FILE_PATH=log_report.md
LOG_RETENTION_DAYS=7
```

Integration steps
-----------------

1. **Import and schedule:** In your runner or scheduler loop, call
   `auto_analyzer.run_scheduled_tasks(now, logs, analyze_fn,
   report_fn)` once per minute.  Pass in the current time (`now`),
   your in‑memory list of log entries (`logs`), a callback to run the
   analyzer once (`analyze_fn`), and a callback to deliver reports
   (`report_fn`).  Ensure that `logs` is a mutable list of dicts
   containing at least `timestamp` (datetime) and `category` (str).

2. **Manual reports:** To generate a report on demand, call
   `auto_analyzer.emit_report(logs, now, report_fn)`.  This will
   return the digest and, if provided, deliver it via `report_fn`.

3. **Define categories:** The reporter will ignore any log entries
   whose `category` is not listed in `LOG_REPORT_CATEGORIES`.  Update
   this environment variable to include all categories you care about.

4. **Retention management:** If you accumulate logs in memory or a
   database, call `auto_analyzer.run_scheduled_tasks` regularly to
   rotate out old entries based on `LOG_RETENTION_DAYS`.  If you
   persist logs elsewhere, ensure that your storage layer enforces
   similar retention.

5. **Delivery:** The provided `deliver_report` helper writes the
   digest to disk when `ADMIN_LOG_DESTINATION=file`.  For `embed`
   (Discord), pass the digest through your existing `post_discord_json`
   function with the appropriate embed structure.  Other delivery
   mechanisms (e.g. email, Slack) can be implemented by writing your
   own `report_fn`.

With these additions, you can automate your analyzer runs, collect
meaningful statistics from your logs, and ensure that the results are
easily consumable.  Tweak the environment variables to fit your
deployment schedule and reporting needs.