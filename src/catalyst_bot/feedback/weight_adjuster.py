"""
Keyword Weight Auto-Adjustment
===============================

Analyzes keyword performance and generates weight recommendations.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from ..logging_utils import get_logger
from .database import get_alerts_by_keyword

log = get_logger("feedback.weight_adjuster")


def analyze_keyword_performance(
    lookback_days: int = 7,
) -> Dict[str, Dict]:
    """
    Analyze performance of each keyword over the lookback period.

    Parameters
    ----------
    lookback_days : int, optional
        Number of days to analyze (default: 7)

    Returns
    -------
    dict
        Keyword performance data with recommendations
        Format: {keyword: {alert_count, win_rate, avg_score, current_weight,
                           recommended_weight, reason}}
    """
    log.info("analyzing_keyword_performance lookback_days=%d", lookback_days)

    # Get all keywords from config
    from ..config import get_settings

    settings = get_settings()

    # Flatten keyword_categories to get all keywords
    all_keywords = []
    for category, keywords in settings.keyword_categories.items():
        all_keywords.extend(keywords)

    # Also check for dynamic keywords in analyzer output
    try:
        dynamic_weights_path = Path("out/dynamic_keyword_weights.json")
        if dynamic_weights_path.exists():
            with open(dynamic_weights_path, "r") as f:
                dynamic_weights = json.load(f)
                all_keywords.extend(dynamic_weights.keys())
    except Exception:
        pass

    # Remove duplicates
    all_keywords = list(set(all_keywords))

    results = {}

    for keyword in all_keywords:
        # Get all alerts with this keyword
        alerts = get_alerts_by_keyword(keyword, lookback_days=lookback_days)

        if not alerts:
            continue

        # Count outcomes
        total = len(alerts)
        wins = sum(1 for a in alerts if a.get("outcome") == "win")
        losses = sum(1 for a in alerts if a.get("outcome") == "loss")
        neutral = sum(1 for a in alerts if a.get("outcome") == "neutral")

        # Calculate win rate (only from scored alerts)
        scored = wins + losses + neutral
        win_rate = wins / scored if scored > 0 else 0.0

        # Calculate average score
        scores = [
            a.get("outcome_score") for a in alerts if a.get("outcome_score") is not None
        ]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Get current weight (default to 1.0)
        current_weight = settings.keyword_default_weight

        # Check dynamic weights
        try:
            dynamic_weights_path = Path("out/dynamic_keyword_weights.json")
            if dynamic_weights_path.exists():
                with open(dynamic_weights_path, "r") as f:
                    dynamic_weights = json.load(f)
                    current_weight = dynamic_weights.get(keyword, current_weight)
        except Exception:
            pass

        # Calculate recommended weight adjustment
        recommended_weight, reason = _calculate_weight_adjustment(
            win_rate, avg_score, current_weight, total
        )

        results[keyword] = {
            "alert_count": total,
            "win_rate": win_rate,
            "avg_score": avg_score,
            "current_weight": current_weight,
            "recommended_weight": recommended_weight,
            "reason": reason,
            "wins": wins,
            "losses": losses,
            "neutral": neutral,
        }

    log.info(
        "keyword_performance_analyzed keywords=%d lookback_days=%d",
        len(results),
        lookback_days,
    )

    return results


def _calculate_weight_adjustment(
    win_rate: float,
    avg_score: float,
    current_weight: float,
    sample_size: int,
) -> tuple[float, str]:
    """
    Calculate recommended weight based on performance.

    Logic:
    - High win rate (>60%) + positive avg score: increase weight
    - Low win rate (<40%) + negative avg score: decrease weight
    - Small sample size: minimal adjustments
    - Large sample size: more confident adjustments

    Parameters
    ----------
    win_rate : float
        Win rate (0.0 to 1.0)
    avg_score : float
        Average outcome score (-1.0 to +1.0)
    current_weight : float
        Current keyword weight
    sample_size : int
        Number of alerts

    Returns
    -------
    tuple of (recommended_weight, reason)
    """
    # Minimum sample size before making adjustments
    min_samples = int(os.getenv("FEEDBACK_MIN_SAMPLES", "20"))

    if sample_size < min_samples:
        return (
            current_weight,
            f"Insufficient data (need {min_samples}, have {sample_size})",
        )

    # Calculate confidence factor based on sample size
    # More samples = more confident adjustments
    confidence = min(1.0, sample_size / 50.0)

    # Determine adjustment magnitude
    adjustment = 0.0

    if win_rate > 0.60 and avg_score > 0.3:
        # Strong performer - increase weight
        adjustment = 0.15 * confidence
        reason = f"High win rate ({win_rate:.1%}) and positive score ({avg_score:.2f})"

    elif win_rate > 0.55 and avg_score > 0.2:
        # Good performer - modest increase
        adjustment = 0.10 * confidence
        reason = f"Good win rate ({win_rate:.1%}) and positive score"

    elif win_rate < 0.35 and avg_score < -0.2:
        # Poor performer - decrease weight
        adjustment = -0.30 * confidence
        reason = f"Low win rate ({win_rate:.1%}) and negative score ({avg_score:.2f})"

    elif win_rate < 0.40 and avg_score < 0.0:
        # Below average - modest decrease
        adjustment = -0.15 * confidence
        reason = f"Below average performance (win rate: {win_rate:.1%})"

    else:
        # Neutral performance - minimal change
        adjustment = 0.0
        reason = "Neutral performance, maintaining current weight"

    recommended_weight = max(0.5, min(2.0, current_weight + adjustment))

    return recommended_weight, reason


def apply_weight_adjustments(
    recommendations: Dict[str, Dict],
    auto_apply: bool = False,
) -> bool:
    """
    Apply weight adjustments to configuration.

    Parameters
    ----------
    recommendations : dict
        Keyword performance recommendations from analyze_keyword_performance
    auto_apply : bool, optional
        If True, update .env file directly. If False, log to admin channel.

    Returns
    -------
    bool
        True if adjustments were applied successfully
    """
    if not recommendations:
        log.info("no_weight_adjustments_to_apply")
        return False

    # Filter to only keywords with changed weights
    changes = {
        kw: data
        for kw, data in recommendations.items()
        if abs(data["recommended_weight"] - data["current_weight"]) > 0.05
    }

    if not changes:
        log.info("no_significant_weight_changes")
        return False

    log.info(
        "applying_weight_adjustments count=%d auto_apply=%s", len(changes), auto_apply
    )

    # Log all changes to admin_changes.jsonl
    _log_weight_changes(changes)

    if auto_apply:
        # Update dynamic keyword weights file
        return _update_dynamic_weights(changes)
    else:
        # Send recommendations to admin channel
        return _send_recommendations_to_admin(changes)


def _log_weight_changes(changes: Dict[str, Dict]) -> None:
    """Log weight changes to admin_changes.jsonl."""
    try:
        log_dir = Path("data")
        log_dir.mkdir(exist_ok=True)

        log_path = log_dir / "admin_changes.jsonl"

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "keyword_weight_adjustment",
            "changes": {
                kw: {
                    "current": data["current_weight"],
                    "recommended": data["recommended_weight"],
                    "reason": data["reason"],
                    "stats": {
                        "alert_count": data["alert_count"],
                        "win_rate": data["win_rate"],
                        "avg_score": data["avg_score"],
                    },
                }
                for kw, data in changes.items()
            },
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        log.info("weight_changes_logged path=%s count=%d", log_path, len(changes))

    except Exception as e:
        log.error("log_weight_changes_failed error=%s", str(e))


def _update_dynamic_weights(changes: Dict[str, Dict]) -> bool:
    """Update dynamic keyword weights file."""
    try:
        output_dir = Path("out")
        output_dir.mkdir(exist_ok=True)

        weights_path = output_dir / "dynamic_keyword_weights.json"

        # Load existing weights
        existing_weights = {}
        if weights_path.exists():
            try:
                with open(weights_path, "r") as f:
                    existing_weights = json.load(f)
            except Exception:
                pass

        # Apply changes
        for keyword, data in changes.items():
            existing_weights[keyword] = data["recommended_weight"]

        # Write updated weights
        with open(weights_path, "w") as f:
            json.dump(existing_weights, f, indent=2)

        log.info(
            "dynamic_weights_updated path=%s keywords=%d",
            weights_path,
            len(existing_weights),
        )

        return True

    except Exception as e:
        log.error("update_dynamic_weights_failed error=%s", str(e))
        return False


def _send_recommendations_to_admin(changes: Dict[str, Dict]) -> bool:
    """Send weight recommendations to admin webhook."""
    try:
        from ..config import get_settings

        settings = get_settings()
        admin_webhook = settings.admin_webhook_url

        if not admin_webhook:
            log.warning("no_admin_webhook_configured")
            return False

        # Build embed
        embed = _build_recommendations_embed(changes)

        import requests

        payload = {
            "username": "Feedback Loop",
            "embeds": [embed],
        }

        response = requests.post(admin_webhook, json=payload, timeout=10)
        response.raise_for_status()

        log.info("recommendations_sent_to_admin count=%d", len(changes))
        return True

    except Exception as e:
        log.error("send_recommendations_failed error=%s", str(e))
        return False


def _build_recommendations_embed(changes: Dict[str, Dict]) -> Dict:
    """Build Discord embed for weight recommendations."""
    # Sort by absolute change magnitude
    sorted_changes = sorted(
        changes.items(),
        key=lambda x: abs(x[1]["recommended_weight"] - x[1]["current_weight"]),
        reverse=True,
    )

    # Build field list (max 25 fields for Discord)
    fields = []

    for keyword, data in sorted_changes[:20]:  # Limit to top 20
        current = data["current_weight"]
        recommended = data["recommended_weight"]
        delta = recommended - current

        # Format field value
        value_parts = [
            f"Current: {current:.2f} → Recommended: {recommended:.2f} ({delta:+.2f})",
            f"Win Rate: {data['win_rate']:.1%} | Score: {data['avg_score']:+.2f}",
            f"Alerts: {data['alert_count']} ({data['wins']}W/{data['losses']}L/{data['neutral']}N)",
            f"Reason: {data['reason']}",
        ]

        # Choose color based on change direction
        # (Will be applied to entire embed, so just note it)
        fields.append(
            {
                "name": f"{'📈' if delta > 0 else '📉'} {keyword}",
                "value": "\n".join(value_parts),
                "inline": False,
            }
        )

    # Determine embed color based on overall trend
    total_positive = sum(
        1 for _, d in changes.items() if d["recommended_weight"] > d["current_weight"]
    )
    total_negative = len(changes) - total_positive

    if total_positive > total_negative:
        color = 0x2ECC71  # Green
    elif total_negative > total_positive:
        color = 0xE74C3C  # Red
    else:
        color = 0x95A5A6  # Gray

    embed = {
        "title": "Keyword Weight Recommendations",
        "description": (
            f"Based on {len(changes)} keywords with significant performance changes.\n"
            f"Positive adjustments: {total_positive} | Negative adjustments: {total_negative}"
        ),
        "color": color,
        "fields": fields,
        "footer": {
            "text": "Set FEEDBACK_AUTO_ADJUST=1 to apply automatically",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return embed
