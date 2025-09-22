"""
Additional configuration flags for sector and session features.

These constants complement the existing configuration in Catalyst Bot.
They provide feature flags and defaults for sector information, market
session display and low‑beta relaxation.  Environment variables are
interpreted as follows:

* ``FEATURE_SECTOR_INFO`` (``0`` or ``1``): enables adding a sector field
  to alerts when set to ``1``.
* ``FEATURE_MARKET_TIME`` (``0`` or ``1``): enables adding a session field
  based on the market session when set to ``1``.
* ``FEATURE_SECTOR_RELAX`` (``0`` or ``1``): enables expanding the
  neutral band for low‑beta sectors when set to ``1``.
* ``LOW_BETA_SECTORS``: a comma‑separated list of ``sector:bps`` entries
  defining per‑sector neutral band adjustments in basis points.  Sectors
  are matched case‑insensitively.  Example: ``utilities:5,consumer
  staples:7``.  If a sector is listed without a value, it defaults to
  zero.
* ``DEFAULT_NEUTRAL_BAND_BPS``: the neutral band expansion (basis
  points) applied to all sectors not listed in ``LOW_BETA_SECTORS``.
* ``SECTOR_FALLBACK_LABEL``: text to display when sector information
  cannot be determined for a ticker.  Defaults to ``"Unknown"``.

Note that these values are not validated; callers should perform any
necessary type conversions or defaulting.
"""

import os

FEATURE_SECTOR_INFO: bool = os.getenv("FEATURE_SECTOR_INFO", "0") == "1"
FEATURE_MARKET_TIME: bool = os.getenv("FEATURE_MARKET_TIME", "0") == "1"
FEATURE_SECTOR_RELAX: bool = os.getenv("FEATURE_SECTOR_RELAX", "0") == "1"
LOW_BETA_SECTORS: str = os.getenv("LOW_BETA_SECTORS", "")
DEFAULT_NEUTRAL_BAND_BPS: int = int(os.getenv("DEFAULT_NEUTRAL_BAND_BPS", "0"))
SECTOR_FALLBACK_LABEL: str = os.getenv("SECTOR_FALLBACK_LABEL", "Unknown")

# -----------------------------------------------------------------------------
# Auto analyzer and log reporter configuration
#
# These flags and settings control the Wave 4 Auto Analyzer and Log Reporter
# functionality.  See README_PATCH_C.md for usage details.

# Enable automatic invocation of the analyzer at scheduled times
FEATURE_AUTO_ANALYZER: bool = os.getenv("FEATURE_AUTO_ANALYZER", "0") == "1"

# Enable daily (or scheduled) log summary reporting
FEATURE_LOG_REPORTER: bool = os.getenv("FEATURE_LOG_REPORTER", "0") == "1"

# Flexible schedules for analyzer and reporter; comma‑separated list of
# HH:MM (24‑hour) times in UTC.  Overrides ANALYZER_UTC_HOUR/MINUTE if nonempty.
ANALYZER_SCHEDULES: str = os.getenv("ANALYZER_SCHEDULES", "")

# Fallback schedule when ANALYZER_SCHEDULES is empty: UTC hour and minute
ANALYZER_UTC_HOUR: int = int(os.getenv("ANALYZER_UTC_HOUR", "23"))
ANALYZER_UTC_MINUTE: int = int(os.getenv("ANALYZER_UTC_MINUTE", "55"))

# Time zone for report timestamps and date windows (e.g. "America/Chicago");
# defaults to UTC.  Set to any valid IANA time zone.
REPORT_TIMEZONE: str = os.getenv("REPORT_TIMEZONE", "UTC")

# Number of days to include in each report window (e.g. 1 for 24‑hours or
# 7 for weekly summaries)
REPORT_DAYS: int = int(os.getenv("REPORT_DAYS", "1"))

# Comma‑separated list of log categories to include in the summary; order
# determines display order.  Unknown categories are ignored.
LOG_REPORT_CATEGORIES: list[str] = [
    c.strip()
    for c in os.getenv(
        "LOG_REPORT_CATEGORIES",
        "items,deduped,skipped_no_ticker,skipped_price_gate,skipped_instr,"
        "skipped_by_source,skipped_low_score,skipped_sent_gate,skipped_cat_gate,skipped_seen",
    ).split(",")
    if c.strip()
]

# Destination for the admin log report.  Supported values: "embed" (default)
# for posting to the admin webhook; "file" to write to ADMIN_LOG_FILE_PATH;
# other values may be implemented externally.  When set to "embed", the
# report should be formatted as a Discord embed.
ADMIN_LOG_DESTINATION: str = os.getenv("ADMIN_LOG_DESTINATION", "embed")

# File path used when ADMIN_LOG_DESTINATION == "file"; ignored otherwise.
ADMIN_LOG_FILE_PATH: str = os.getenv("ADMIN_LOG_FILE_PATH", "log_report.md")

# Retention period for log entries in days.  Entries older than this
# threshold should be discarded or archived.
LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", "7"))
