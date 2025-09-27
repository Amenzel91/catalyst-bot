"""
config_extras.py
================

This module defines additional configuration options introduced in the
Backtesting and Analysis Improvements Patch.  It is intended to be
imported by the main configuration module to extend the ``Settings``
dataclass with new fields without modifying the core configuration
directly.  If you integrate these fields into your existing config,
copy the attributes into your Settings definition or import this
module and update ``__all__`` accordingly.

The new settings include feature flags for vectorized backtesting,
missed trade analysis, machine‑learning based alert ranking, and
paper trading, as well as thresholds and file paths used by these
features.  Defaults are chosen to be disabled or neutral so that
existing functionality is unaffected until explicitly enabled.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Legacy configuration flags for sector information and log reporting
#
# The constants below mirror the original Catalyst Bot configuration extras.  They
# are imported by modules such as ``log_reporter`` and ``auto_analyzer``.  To
# preserve backwards compatibility, these names remain top‑level attributes
# alongside the new ``ExtraSettings`` dataclass.  They read from the
# environment at import time and provide defaults consistent with the
# pre‑patch implementation.

# Sector and market time features
FEATURE_SECTOR_INFO: bool = os.getenv("FEATURE_SECTOR_INFO", "0") == "1"
FEATURE_MARKET_TIME: bool = os.getenv("FEATURE_MARKET_TIME", "0") == "1"
FEATURE_SECTOR_RELAX: bool = os.getenv("FEATURE_SECTOR_RELAX", "0") == "1"
LOW_BETA_SECTORS: str = os.getenv("LOW_BETA_SECTORS", "")
DEFAULT_NEUTRAL_BAND_BPS: int = int(os.getenv("DEFAULT_NEUTRAL_BAND_BPS", "0"))
SECTOR_FALLBACK_LABEL: str = os.getenv("SECTOR_FALLBACK_LABEL", "Unknown")

# Auto analyzer and log reporter configuration
FEATURE_AUTO_ANALYZER: bool = os.getenv("FEATURE_AUTO_ANALYZER", "0") == "1"
FEATURE_LOG_REPORTER: bool = os.getenv("FEATURE_LOG_REPORTER", "0") == "1"
ANALYZER_SCHEDULES: str = os.getenv("ANALYZER_SCHEDULES", "")
ANALYZER_UTC_HOUR: int = int(os.getenv("ANALYZER_UTC_HOUR", "23"))
ANALYZER_UTC_MINUTE: int = int(os.getenv("ANALYZER_UTC_MINUTE", "55"))
REPORT_TIMEZONE: str = os.getenv("REPORT_TIMEZONE", "UTC")
REPORT_DAYS: int = int(os.getenv("REPORT_DAYS", "1"))
LOG_REPORT_CATEGORIES: list[str] = [
    c.strip()
    for c in os.getenv(
        "LOG_REPORT_CATEGORIES",
        "items,deduped,skipped_no_ticker,skipped_price_gate,skipped_instr,"
        "skipped_by_source,skipped_low_score,skipped_sent_gate,skipped_cat_gate,skipped_seen",
    ).split(",")
    if c.strip()
]
# Destination for the admin log report.  Supported values: "embed" (default) for
# posting to the admin webhook; "file" to write to ADMIN_LOG_FILE_PATH.
ADMIN_LOG_DESTINATION: str = os.getenv("ADMIN_LOG_DESTINATION", "embed")
# File path used when ADMIN_LOG_DESTINATION == "file"; ignored otherwise.
ADMIN_LOG_FILE_PATH: str = os.getenv("ADMIN_LOG_FILE_PATH", "log_report.md")
# Retention period for log entries in days.  Entries older than this threshold
# should be discarded or archived.
LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", "7"))


def _env_bool(var: str, default: bool = False) -> bool:
    import os

    val = os.getenv(var)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(var: str, default: float) -> float:
    import os

    try:
        return float(os.getenv(var, "")) if os.getenv(var) else default
    except Exception:
        return default


@dataclass
class ExtraSettings:
    """Additional settings for patch features.

    These fields mirror environment variables described in the patch
    documentation.  See the README or patch notes for details.
    """

    # Vectorized backtest and risk metrics
    feature_vector_backtest: bool = field(
        default_factory=lambda: _env_bool("FEATURE_VECTOR_BACKTEST", False)
    )
    backtest_commission: float = field(
        default_factory=lambda: _env_float("BACKTEST_COMMISSION", 0.0)
    )
    backtest_slippage: float = field(
        default_factory=lambda: _env_float("BACKTEST_SLIPPAGE", 0.0)
    )
    # Missed trade analysis
    feature_missed_trade_analysis: bool = field(
        default_factory=lambda: _env_bool("FEATURE_MISSED_TRADE_ANALYSIS", False)
    )
    missed_threshold: float = field(
        default_factory=lambda: _env_float("MISSED_THRESHOLD", 0.05)
    )
    missed_window_days: int = int(_env_float("MISSED_WINDOW_DAYS", 3))
    # Composite indicator score
    feature_composite_indicators: bool = field(
        default_factory=lambda: _env_bool("FEATURE_COMPOSITE_INDICATORS", False)
    )
    composite_score_threshold: float = field(
        default_factory=lambda: _env_float("COMPOSITE_SCORE_THRESHOLD", 0.0)
    )
    # Machine learning alert ranking
    feature_ml_alert_ranking: bool = field(
        default_factory=lambda: _env_bool("FEATURE_ML_ALERT_RANKING", False)
    )
    confidence_high: float = field(
        default_factory=lambda: _env_float("CONFIDENCE_HIGH", 0.8)
    )
    confidence_moderate: float = field(
        default_factory=lambda: _env_float("CONFIDENCE_MODERATE", 0.6)
    )
    ml_model_path: str = field(
        default_factory=lambda: os.getenv(
            "ML_MODEL_PATH", "data/models/trade_classifier.pkl"
        )
    )  # type: ignore
    # Paper trading
    feature_paper_trading: bool = field(
        default_factory=lambda: _env_bool("FEATURE_PAPER_TRADING", False)
    )


__all__ = ["ExtraSettings"]
