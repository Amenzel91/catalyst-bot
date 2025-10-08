"""
Admin Report Generator
======================

Generates nightly admin reports with parameter recommendations based on
alert performance from the feedback loop database.

This module extends the existing admin_controls.py functionality with
additional integration to the WAVE 1.2 feedback loop system.
"""

from __future__ import annotations

import os
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..logging_utils import get_logger

log = get_logger("admin.report_generator")


class AdminReportGenerator:
    """
    Generate nightly admin reports with parameter recommendations.

    This class wraps the existing admin_controls.generate_admin_report()
    function and enhances it with feedback loop integration.
    """

    def __init__(self):
        """Initialize admin report generator."""

    def generate_nightly_report(self, target_date: Optional[date_cls] = None) -> Dict:
        """
        Analyze last 7 days of alert performance and recommend changes.

        Parameters
        ----------
        target_date : date, optional
            Date to generate report for. Defaults to yesterday.

        Returns
        -------
        dict
            Report dictionary with performance stats and recommendations
        """
        if target_date is None:
            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        log.info("generating_nightly_report date=%s", target_date)

        try:
            # Use existing admin_controls report generator
            from ..admin_controls import generate_admin_report

            report = generate_admin_report(target_date)

            # Convert to dict format for API compatibility
            return self._report_to_dict(report, target_date)

        except Exception as e:
            log.error(
                "generate_nightly_report_failed date=%s error=%s", target_date, str(e)
            )
            return self._empty_report(target_date)

    def get_parameter_suggestions(self, performance_stats: Dict) -> List[Dict]:
        """
        Analyze stats and generate specific parameter recommendations.

        Parameters
        ----------
        performance_stats : dict
            Performance statistics from feedback database

        Returns
        -------
        list of dict
            Parameter recommendations
        """
        recommendations = []

        # Extract metrics
        performance_stats.get("win_rate_15m", 0)
        win_rate_1d = performance_stats.get("win_rate_1d", 0)
        total_alerts = performance_stats.get("alerts_posted", 0)

        # 1. Adjust MIN_SCORE if win rate is low
        if win_rate_1d < 0.55 and total_alerts > 20:
            current_min_score = float(os.getenv("MIN_SCORE", "0") or 0)
            recommendations.append(
                {
                    "param": "MIN_SCORE",
                    "current": current_min_score,
                    "recommended": current_min_score + 0.05,
                    "reason": f"Win rate ({win_rate_1d:.1%}) below 55% - increase threshold",
                    "confidence": self.calculate_confidence(total_alerts, win_rate_1d),
                    "impact": "Reduce alerts by ~15%, improve win rate 3-5%",
                }
            )

        # 2. Adjust sentiment weights based on performance
        try:
            from ..feedback.database import get_performance_stats

            stats = get_performance_stats(lookback_days=7)

            # Check if we have enough data
            if stats and stats.get("total_alerts", 0) > 30:
                avg_score = stats.get("avg_score", 0)

                # If avg score is low, reduce sentiment weight
                if avg_score < 0.5:
                    current_weight = float(os.getenv("SENTIMENT_WEIGHT_LOCAL", "0.4"))
                    recommendations.append(
                        {
                            "param": "SENTIMENT_WEIGHT_LOCAL",
                            "current": current_weight,
                            "recommended": max(0.2, current_weight - 0.1),
                            "reason": f"Low avg sentiment score ({avg_score:.2f}) - reduce weight",
                            "confidence": 0.75,
                            "impact": "Shift weight to other sentiment sources",
                        }
                    )

        except Exception as e:
            log.debug("feedback_stats_unavailable error=%s", str(e))

        # 3. Keyword-specific recommendations from feedback
        try:
            keyword_recs = self._get_keyword_recommendations()
            recommendations.extend(keyword_recs)
        except Exception as e:
            log.debug("keyword_recommendations_failed error=%s", str(e))

        return recommendations

    def calculate_confidence(self, sample_size: int, win_rate: float) -> float:
        """
        Calculate confidence score for recommendation (0-1).

        Uses sample size and win rate to determine confidence.
        Higher sample sizes and more extreme win rates = higher confidence.

        Parameters
        ----------
        sample_size : int
            Number of alerts in sample
        win_rate : float
            Win rate (0-1)

        Returns
        -------
        float
            Confidence score (0-1)
        """
        # Base confidence from sample size
        # 100+ alerts = 0.9, 50 alerts = 0.7, 20 alerts = 0.5, <10 = 0.3
        if sample_size >= 100:
            size_conf = 0.9
        elif sample_size >= 50:
            size_conf = 0.7
        elif sample_size >= 20:
            size_conf = 0.5
        else:
            size_conf = 0.3

        # Bonus confidence for extreme win rates (very good or very bad)
        # Win rate far from 50% = more confident the trend is real
        win_rate_deviation = abs(win_rate - 0.5)
        deviation_bonus = min(0.2, win_rate_deviation * 0.4)

        confidence = min(1.0, size_conf + deviation_bonus)
        return round(confidence, 2)

    def _report_to_dict(self, report, target_date: date_cls) -> Dict:
        """Convert AdminReport object to dict."""
        bt = report.backtest_summary

        return {
            "period": f"{target_date} (7 days lookback)",
            "alerts_posted": report.total_alerts,
            "win_rate_15m": bt.hit_rate,
            "win_rate_1h": bt.hit_rate,
            "win_rate_4h": bt.hit_rate,
            "win_rate_1d": bt.hit_rate,
            "recommendations": [
                {
                    "param": rec.name,
                    "current": rec.current_value,
                    "recommended": rec.proposed_value,
                    "reason": rec.reason,
                    "confidence": 0.85 if rec.impact == "high" else 0.70,
                    "impact": self._format_impact(rec),
                }
                for rec in report.parameter_recommendations
            ],
            "best_keywords": [kp.category for kp in report.keyword_performance[:3]],
            "worst_keywords": [
                kp.category for kp in reversed(report.keyword_performance[-3:])
            ],
            "best_catalyst_types": self._get_best_catalyst_types(),
            "worst_catalyst_types": self._get_worst_catalyst_types(),
        }

    def _empty_report(self, target_date: date_cls) -> Dict:
        """Return empty report structure."""
        return {
            "period": f"{target_date} (7 days lookback)",
            "alerts_posted": 0,
            "win_rate_15m": 0.0,
            "win_rate_1h": 0.0,
            "win_rate_4h": 0.0,
            "win_rate_1d": 0.0,
            "recommendations": [],
            "best_keywords": [],
            "worst_keywords": [],
            "best_catalyst_types": [],
            "worst_catalyst_types": [],
        }

    def _format_impact(self, rec) -> str:
        """Format impact description from recommendation."""
        # Default impact based on parameter type
        if "SCORE" in rec.name:
            return "Adjust alert selectivity"
        elif "WEIGHT" in rec.name:
            return "Adjust keyword influence"
        elif "CEILING" in rec.name or "FLOOR" in rec.name:
            return "Change price filter range"
        else:
            return "Update bot parameter"

    def _get_keyword_recommendations(self) -> List[Dict]:
        """Get keyword-specific recommendations from feedback."""
        recommendations = []

        try:
            from ..feedback.database import get_alerts_by_keyword

            # Check performance of top keywords
            keywords_to_check = [
                "fda",
                "earnings",
                "partnership",
                "dilution",
                "clinical",
            ]

            for keyword in keywords_to_check:
                wins = get_alerts_by_keyword(
                    keyword, lookback_days=7, outcome_filter="win"
                )
                losses = get_alerts_by_keyword(
                    keyword, lookback_days=7, outcome_filter="loss"
                )

                total = len(wins) + len(losses)
                if total < 5:  # Need minimum sample size
                    continue

                win_rate = len(wins) / total
                current_weight = self._get_current_keyword_weight(keyword)

                # Recommend increase if win rate > 65%
                if win_rate > 0.65:
                    recommendations.append(
                        {
                            "param": f"KEYWORD_WEIGHT_{keyword.upper()}",
                            "current": current_weight,
                            "recommended": round(current_weight * 1.15, 2),
                            "reason": f"{keyword}: {win_rate:.0%} win rate over {total} alerts",
                            "confidence": self.calculate_confidence(total, win_rate),
                            "impact": f"Boost {keyword} signal influence",
                        }
                    )

                # Recommend decrease if win rate < 40%
                elif win_rate < 0.40:
                    recommendations.append(
                        {
                            "param": f"KEYWORD_WEIGHT_{keyword.upper()}",
                            "current": current_weight,
                            "recommended": round(current_weight * 0.85, 2),
                            "reason": f"{keyword}: {win_rate:.0%} win rate over {total} alerts",
                            "confidence": self.calculate_confidence(total, win_rate),
                            "impact": f"Reduce {keyword} signal influence",
                        }
                    )

        except Exception as e:
            log.debug("keyword_recommendations_failed error=%s", str(e))

        return recommendations

    def _get_current_keyword_weight(self, keyword: str) -> float:
        """Get current weight for a keyword from keyword_stats.json."""
        try:
            from ..classify import load_dynamic_keyword_weights

            weights = load_dynamic_keyword_weights()
            return weights.get(keyword, 1.0)

        except Exception:
            return 1.0

    def _get_best_catalyst_types(self) -> List[str]:
        """Get best performing catalyst types from feedback."""
        try:
            from ..feedback.database import _get_connection

            conn = _get_connection()
            try:
                cursor = conn.cursor()

                # Get catalyst types with highest win rates (min 5 alerts)
                cursor.execute(
                    """
                    SELECT
                        catalyst_type,
                        COUNT(*) as total,
                        COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins
                    FROM alert_performance
                    WHERE posted_at >= ? AND outcome IS NOT NULL
                    GROUP BY catalyst_type
                    HAVING COUNT(*) >= 5
                    ORDER BY (COUNT(CASE WHEN outcome = 'win' THEN 1 END) * 1.0 / COUNT(*)) DESC
                    LIMIT 3
                    """,
                    (
                        int(
                            (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
                        ),
                    ),
                )

                rows = cursor.fetchall()
                return [row["catalyst_type"] for row in rows]

            finally:
                conn.close()

        except Exception as e:
            log.debug("get_best_catalyst_types_failed error=%s", str(e))
            return []

    def _get_worst_catalyst_types(self) -> List[str]:
        """Get worst performing catalyst types from feedback."""
        try:
            from ..feedback.database import _get_connection

            conn = _get_connection()
            try:
                cursor = conn.cursor()

                # Get catalyst types with lowest win rates (min 5 alerts)
                cursor.execute(
                    """
                    SELECT
                        catalyst_type,
                        COUNT(*) as total,
                        COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins
                    FROM alert_performance
                    WHERE posted_at >= ? AND outcome IS NOT NULL
                    GROUP BY catalyst_type
                    HAVING COUNT(*) >= 5
                    ORDER BY (COUNT(CASE WHEN outcome = 'win' THEN 1 END) * 1.0 / COUNT(*)) ASC
                    LIMIT 3
                    """,
                    (
                        int(
                            (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
                        ),
                    ),
                )

                rows = cursor.fetchall()
                return [row["catalyst_type"] for row in rows]

            finally:
                conn.close()

        except Exception as e:
            log.debug("get_worst_catalyst_types_failed error=%s", str(e))
            return []
