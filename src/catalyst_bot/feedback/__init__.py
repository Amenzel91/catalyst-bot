"""
Feedback Loop System
====================

Real-time alert performance tracking and keyword weight auto-adjustment.

This module provides:
- Alert performance database tracking
- Price/volume monitoring over multiple timeframes
- Outcome scoring (win/loss/neutral)
- Keyword weight recommendations based on real outcomes
- Weekly performance reports
"""

from .database import (
    get_alert_performance,
    get_alerts_by_keyword,
    get_pending_updates,
    get_performance_stats,
    init_database,
    record_alert,
    update_outcome,
    update_performance,
)
from .outcome_scorer import calculate_outcome, score_pending_alerts
from .price_tracker import run_tracker_loop, track_alert_performance
from .weekly_report import generate_weekly_report
from .weight_adjuster import analyze_keyword_performance, apply_weight_adjustments

__all__ = [
    "init_database",
    "record_alert",
    "update_performance",
    "update_outcome",
    "get_alert_performance",
    "get_alerts_by_keyword",
    "get_pending_updates",
    "get_performance_stats",
    "track_alert_performance",
    "run_tracker_loop",
    "calculate_outcome",
    "score_pending_alerts",
    "analyze_keyword_performance",
    "apply_weight_adjustments",
    "generate_weekly_report",
]
