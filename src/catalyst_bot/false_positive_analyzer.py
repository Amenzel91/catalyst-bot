"""
False Positive Analyzer - Pattern Analysis for Failed Alerts

Analyzes outcomes.jsonl to identify patterns in false positives:
- Which keywords generate the most failures?
- Which sources have the highest false positive rates?
- What score ranges correlate with failures?
- Time-of-day patterns?
- Sector patterns?

Generates keyword penalty recommendations (opposite of MOA boost recommendations).

Author: Claude Code (Agent 4: False Positive Analysis)
Date: 2025-10-12
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .logging_utils import get_logger

log = get_logger("false_positive_analyzer")

# Configuration
MIN_OCCURRENCES = 3  # Minimum occurrences for statistical significance


def _repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def _ensure_fp_dirs() -> Tuple[Path, Path]:
    """Ensure false_positives directories exist and return paths."""
    root = _repo_root()
    fp_dir = root / "data" / "false_positives"
    fp_dir.mkdir(parents=True, exist_ok=True)
    return root, fp_dir


def load_outcomes() -> List[Dict[str, Any]]:
    """
    Load outcomes from data/false_positives/outcomes.jsonl.

    Returns:
        List of outcome dictionaries
    """
    _, fp_dir = _ensure_fp_dirs()
    outcomes_path = fp_dir / "outcomes.jsonl"

    if not outcomes_path.exists():
        log.warning(f"outcomes_not_found path={outcomes_path}")
        return []

    outcomes = []
    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    outcome = json.loads(line)
                    outcomes.append(outcome)
                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        log.info(f"loaded_outcomes count={len(outcomes)}")
        return outcomes

    except Exception as e:
        log.error(f"load_outcomes_failed err={e}")
        return []


def calculate_precision_recall(outcomes: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate precision and false positive rate.

    Precision = successful_accepts / total_accepts
    False Positive Rate = failures / total_accepts

    Args:
        outcomes: List of outcome dictionaries

    Returns:
        Dict with precision, false_positive_rate, success_count, failure_count
    """
    if not outcomes:
        return {
            "precision": 0.0,
            "false_positive_rate": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "total_accepts": 0,
        }

    success_count = sum(1 for o in outcomes if o.get("classification") == "SUCCESS")
    failure_count = sum(1 for o in outcomes if o.get("classification") == "FAILURE")
    total = len(outcomes)

    precision = success_count / total if total > 0 else 0.0
    false_positive_rate = failure_count / total if total > 0 else 0.0

    return {
        "precision": round(precision, 3),
        "false_positive_rate": round(false_positive_rate, 3),
        "success_count": success_count,
        "failure_count": failure_count,
        "total_accepts": total,
    }


def analyze_keyword_patterns(outcomes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Analyze which keywords correlate with false positives.

    Args:
        outcomes: List of outcomes

    Returns:
        Dict mapping keyword -> stats (occurrences, failure_rate, avg_return)
    """
    keyword_stats = defaultdict(
        lambda: {
            "total": 0,
            "failures": 0,
            "successes": 0,
            "total_return": 0.0,
            "examples": [],
        }
    )

    for outcome in outcomes:
        keywords = outcome.get("keywords", [])
        classification = outcome.get("classification", "FAILURE")
        max_return = outcome.get("max_return_pct", 0.0)
        ticker = outcome.get("ticker", "")

        for kw in keywords:
            kw_lower = str(kw).lower()
            keyword_stats[kw_lower]["total"] += 1

            if classification == "FAILURE":
                keyword_stats[kw_lower]["failures"] += 1
            else:
                keyword_stats[kw_lower]["successes"] += 1

            keyword_stats[kw_lower]["total_return"] += max_return

            # Store example (limit to 3)
            examples = keyword_stats[kw_lower]["examples"]
            if len(examples) < 3:
                examples.append(
                    {
                        "ticker": ticker,
                        "return_pct": round(max_return, 2),
                        "classification": classification,
                    }
                )

    # Calculate failure rates
    results = {}
    for kw, stats in keyword_stats.items():
        total = stats["total"]

        if total >= MIN_OCCURRENCES:
            failure_rate = stats["failures"] / total if total > 0 else 0.0
            avg_return = stats["total_return"] / total if total > 0 else 0.0

            results[kw] = {
                "occurrences": total,
                "failures": stats["failures"],
                "successes": stats["successes"],
                "failure_rate": round(failure_rate, 3),
                "avg_return": round(avg_return, 2),
                "examples": stats["examples"],
            }

    log.info(
        f"analyzed_keywords "
        f"total_unique={len(keyword_stats)} "
        f"significant={len(results)} "
        f"min_occurrences={MIN_OCCURRENCES}"
    )

    return results


def analyze_source_patterns(outcomes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Analyze which sources have high false positive rates.

    Args:
        outcomes: List of outcomes

    Returns:
        Dict mapping source -> stats
    """
    source_stats = defaultdict(
        lambda: {
            "total": 0,
            "failures": 0,
            "successes": 0,
            "total_return": 0.0,
        }
    )

    for outcome in outcomes:
        source = outcome.get("source", "UNKNOWN")
        classification = outcome.get("classification", "FAILURE")
        max_return = outcome.get("max_return_pct", 0.0)

        source_stats[source]["total"] += 1
        source_stats[source]["total_return"] += max_return

        if classification == "FAILURE":
            source_stats[source]["failures"] += 1
        else:
            source_stats[source]["successes"] += 1

    # Calculate rates
    results = {}
    for source, stats in source_stats.items():
        total = stats["total"]

        results[source] = {
            "total": total,
            "failures": stats["failures"],
            "successes": stats["successes"],
            "failure_rate": round(stats["failures"] / total, 3) if total > 0 else 0.0,
            "avg_return": round(stats["total_return"] / total, 2) if total > 0 else 0.0,
        }

    log.info(f"analyzed_sources count={len(results)}")
    return results


def analyze_score_correlation(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze correlation between classification scores and outcomes.

    Args:
        outcomes: List of outcomes

    Returns:
        Dict with score range analysis
    """
    score_buckets = defaultdict(lambda: {"total": 0, "failures": 0, "successes": 0})

    for outcome in outcomes:
        score = outcome.get("score", 0.0)
        classification = outcome.get("classification", "FAILURE")

        # Bucket scores into ranges
        if score < 1.0:
            bucket = "0.0-1.0"
        elif score < 2.0:
            bucket = "1.0-2.0"
        elif score < 3.0:
            bucket = "2.0-3.0"
        else:
            bucket = "3.0+"

        score_buckets[bucket]["total"] += 1
        if classification == "FAILURE":
            score_buckets[bucket]["failures"] += 1
        else:
            score_buckets[bucket]["successes"] += 1

    # Calculate failure rates
    results = {}
    for bucket, stats in score_buckets.items():
        total = stats["total"]
        results[bucket] = {
            "total": total,
            "failures": stats["failures"],
            "successes": stats["successes"],
            "failure_rate": round(stats["failures"] / total, 3) if total > 0 else 0.0,
        }

    log.info(f"analyzed_score_correlation buckets={len(results)}")
    return results


def analyze_time_patterns(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze time-of-day patterns for false positives.

    Args:
        outcomes: List of outcomes

    Returns:
        Dict with time-of-day analysis
    """
    time_buckets = defaultdict(lambda: {"total": 0, "failures": 0, "successes": 0})

    for outcome in outcomes:
        ts_str = outcome.get("acceptance_ts", "")
        if not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            hour = ts.hour

            # Bucket into market hours
            if hour < 9:
                bucket = "pre-market (before 9am)"
            elif hour < 12:
                bucket = "morning (9am-12pm)"
            elif hour < 15:
                bucket = "midday (12pm-3pm)"
            elif hour < 16:
                bucket = "afternoon (3pm-4pm)"
            else:
                bucket = "after-hours (4pm+)"

            classification = outcome.get("classification", "FAILURE")

            time_buckets[bucket]["total"] += 1
            if classification == "FAILURE":
                time_buckets[bucket]["failures"] += 1
            else:
                time_buckets[bucket]["successes"] += 1

        except Exception:
            continue

    # Calculate failure rates
    results = {}
    for bucket, stats in time_buckets.items():
        total = stats["total"]
        results[bucket] = {
            "total": total,
            "failures": stats["failures"],
            "successes": stats["successes"],
            "failure_rate": round(stats["failures"] / total, 3) if total > 0 else 0.0,
        }

    log.info(f"analyzed_time_patterns buckets={len(results)}")
    return results


def generate_keyword_penalties(
    keyword_stats: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate keyword penalty recommendations based on false positive analysis.

    Args:
        keyword_stats: Keyword statistics from analyze_keyword_patterns

    Returns:
        List of penalty recommendations sorted by severity
    """
    penalties = []

    for keyword, stats in keyword_stats.items():
        occurrences = stats["occurrences"]
        failure_rate = stats["failure_rate"]
        avg_return = stats["avg_return"]

        # Only penalize keywords with high failure rates
        if failure_rate < 0.5:  # Less than 50% failure rate
            continue

        # Calculate penalty magnitude
        # Base penalty starts at -0.5
        base_penalty = -0.5

        # Increase penalty for very high failure rates
        if failure_rate >= 0.8:
            failure_penalty = -0.5  # Additional -0.5 for 80%+ failure
        elif failure_rate >= 0.7:
            failure_penalty = -0.3  # Additional -0.3 for 70%+ failure
        else:
            failure_penalty = -0.1  # Additional -0.1 for 50%+ failure

        # Increase penalty for negative average returns
        if avg_return < -2.0:
            return_penalty = -0.3
        elif avg_return < 0:
            return_penalty = -0.2
        else:
            return_penalty = 0.0

        recommended_penalty = base_penalty + failure_penalty + return_penalty
        recommended_penalty = max(-2.0, recommended_penalty)  # Cap at -2.0

        # Calculate confidence based on sample size
        if occurrences >= 10:
            confidence = 0.9
        elif occurrences >= 5:
            confidence = 0.7
        else:
            confidence = 0.5

        penalties.append(
            {
                "keyword": keyword,
                "recommended_penalty": round(recommended_penalty, 2),
                "confidence": confidence,
                "evidence": {
                    "occurrences": occurrences,
                    "failure_rate": failure_rate,
                    "avg_return": avg_return,
                    "examples": stats.get("examples", []),
                },
            }
        )

    # Sort by penalty magnitude (most negative first)
    penalties.sort(key=lambda x: x["recommended_penalty"])

    log.info(f"generated_penalties count={len(penalties)}")
    return penalties


def run_false_positive_analysis() -> Dict[str, Any]:
    """
    Run complete false positive analysis.

    Returns:
        Analysis results dictionary
    """
    start_time = time.time()
    log.info("false_positive_analysis_start")

    try:
        # Load outcomes
        outcomes = load_outcomes()

        if not outcomes:
            return {
                "status": "no_data",
                "message": "No outcomes found in data/false_positives/outcomes.jsonl",
            }

        # Calculate precision/recall
        precision_recall = calculate_precision_recall(outcomes)

        # Analyze patterns
        keyword_patterns = analyze_keyword_patterns(outcomes)
        source_patterns = analyze_source_patterns(outcomes)
        score_correlation = analyze_score_correlation(outcomes)
        time_patterns = analyze_time_patterns(outcomes)

        # Generate penalty recommendations
        keyword_penalties = generate_keyword_penalties(keyword_patterns)

        # Build report
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_accepts": len(outcomes),
                "successes": precision_recall["success_count"],
                "failures": precision_recall["failure_count"],
                "precision": precision_recall["precision"],
                "false_positive_rate": precision_recall["false_positive_rate"],
            },
            "keyword_analysis": keyword_patterns,
            "source_analysis": source_patterns,
            "score_correlation": score_correlation,
            "time_patterns": time_patterns,
            "keyword_penalties": keyword_penalties,
        }

        # Save report
        _, fp_dir = _ensure_fp_dirs()
        report_path = fp_dir / "analysis_report.json"

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        elapsed = time.time() - start_time

        log.info(
            f"false_positive_analysis_complete "
            f"outcomes={len(outcomes)} "
            f"precision={precision_recall['precision']:.1%} "
            f"false_positive_rate={precision_recall['false_positive_rate']:.1%} "
            f"penalties={len(keyword_penalties)} "
            f"elapsed={elapsed:.1f}s"
        )

        return {
            "status": "success",
            "report_path": str(report_path),
            "summary": report["summary"],
            "penalties_count": len(keyword_penalties),
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as e:
        log.error(f"false_positive_analysis_failed err={e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# CLI entry point
def main():
    """Run false positive analysis from command line."""
    print("Running False Positive Analysis...")
    print("=" * 60)

    result = run_false_positive_analysis()

    print(f"\nStatus: {result['status']}")

    if result["status"] == "success":
        print("\nSummary:")
        summary = result["summary"]
        print(f"  Total accepts: {summary['total_accepts']}")
        print(f"  Successes: {summary['successes']}")
        print(f"  Failures: {summary['failures']}")
        print(f"  Precision: {summary['precision']:.1%}")
        print(f"  False Positive Rate: {summary['false_positive_rate']:.1%}")

        print(f"\nKeyword Penalties: {result['penalties_count']} recommendations")
        print(f"\nFull report saved to: {result['report_path']}")

        return 0
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
