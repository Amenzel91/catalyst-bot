"""
Multi-Window Analysis Proof of Concept (Ticket #6)

Tests multi-timeframe analysis (7-day, 30-day, 90-day) on existing MOA data
to validate the approach before integration.

Expected Impact: +15% precision by catching temporal patterns
"""

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Configuration
MOA_DB_PATH = Path("data/keyword_review.db")
FEEDBACK_DB_PATH = Path("data/feedback/alert_performance.db")
OUTPUT_PATH = Path("data/moa/multi_window_poc_results.json")

# Analysis windows
WINDOWS = {
    "7d": {"days": 7, "weight": 0.50, "name": "Short-term (7-day)"},
    "30d": {"days": 30, "weight": 0.30, "name": "Standard (30-day)"},
    "90d": {"days": 90, "weight": 0.20, "name": "Long-term (90-day)"}
}

# Success thresholds
SUCCESS_THRESHOLD_PCT = 10.0  # MOA: 10% return = success
MIN_OCCURRENCES = 10  # Minimum observations per window


def fetch_moa_outcomes(db_path: Path, lookback_days: int) -> List[Dict[str, Any]]:
    """
    Fetch MOA outcomes (missed opportunities) from outcomes.jsonl.

    Args:
        db_path: Ignored (kept for compatibility)
        lookback_days: Number of days to look back

    Returns:
        List of outcome dictionaries
    """
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        print(f"ERROR: Outcomes file not found: {outcomes_path}")
        return []

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    outcomes = []

    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    outcome_data = json.loads(line)

                    # Parse rejection timestamp
                    rejection_ts_str = outcome_data.get("rejection_ts")
                    if not rejection_ts_str:
                        continue

                    rejection_ts = datetime.fromisoformat(rejection_ts_str.replace("Z", "+00:00"))

                    # Filter by date
                    if rejection_ts < cutoff_date:
                        continue

                    # Extract keywords
                    cls_data = outcome_data.get("cls", {})
                    keywords = cls_data.get("keywords", [])

                    # Get max return
                    max_return_pct = outcome_data.get("max_return_pct", 0.0)

                    outcome = {
                        "ticker": outcome_data.get("ticker"),
                        "rejected_at": rejection_ts_str,
                        "keywords": keywords,
                        "max_return_pct": max_return_pct,
                        "is_success": max_return_pct >= SUCCESS_THRESHOLD_PCT
                    }

                    outcomes.append(outcome)

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"  Warning: Failed to parse outcome: {e}")
                    continue

    except Exception as e:
        print(f"ERROR: Failed to load outcomes: {e}")
        return []

    print(f"  Fetched {len(outcomes)} MOA outcomes ({lookback_days}d window)")
    return outcomes


def fetch_feedback_outcomes(db_path: Path, lookback_days: int) -> List[Dict[str, Any]]:
    """
    Fetch feedback loop outcomes (accepted alerts) from database.

    Args:
        db_path: Path to alert_performance.db
        lookback_days: Number of days to look back

    Returns:
        List of outcome dictionaries
    """
    if not db_path.exists():
        print(f"  Feedback DB not found (expected for new feature): {db_path}")
        return []

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query alert outcomes
    query = """
        SELECT
            ticker,
            alert_timestamp,
            keywords,
            outcome_1d,
            max_return_pct_1d
        FROM alerts
        WHERE alert_timestamp >= ?
        AND outcome_1d IS NOT NULL
        ORDER BY alert_timestamp DESC
    """

    try:
        cursor.execute(query, (cutoff_date.isoformat(),))
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        # Table might not exist yet
        print(f"  Feedback table not ready yet (new feature)")
        conn.close()
        return []

    outcomes = []

    for row in rows:
        # Parse keywords JSON
        try:
            keywords = json.loads(row["keywords"]) if row["keywords"] else []
        except:
            keywords = []

        outcome = {
            "ticker": row["ticker"],
            "alert_timestamp": row["alert_timestamp"],
            "keywords": keywords,
            "max_return_pct": row["max_return_pct_1d"] or 0.0,
            "outcome": row["outcome_1d"],
            "is_success": row["outcome_1d"] == "WIN"
        }

        outcomes.append(outcome)

    conn.close()

    print(f"  Fetched {len(outcomes)} feedback outcomes ({lookback_days}d window)")
    return outcomes


def analyze_window(outcomes: List[Dict[str, Any]], window_name: str) -> Dict[str, Any]:
    """
    Analyze keyword performance for a single time window.

    Args:
        outcomes: List of outcome dictionaries
        window_name: Window identifier (e.g., "7d", "30d")

    Returns:
        Analysis results dictionary
    """
    keyword_stats = defaultdict(lambda: {
        "occurrences": 0,
        "successes": 0,
        "failures": 0,
        "total_return": 0.0
    })

    # Aggregate keyword statistics
    for outcome in outcomes:
        keywords = outcome.get("keywords", [])
        is_success = outcome.get("is_success", False)
        return_pct = outcome.get("max_return_pct", 0.0)

        for keyword in keywords:
            kw_lower = keyword.lower()
            keyword_stats[kw_lower]["occurrences"] += 1
            keyword_stats[kw_lower]["total_return"] += return_pct

            if is_success:
                keyword_stats[kw_lower]["successes"] += 1
            else:
                keyword_stats[kw_lower]["failures"] += 1

    # Calculate metrics for each keyword
    keyword_analysis = {}

    for keyword, stats in keyword_stats.items():
        if stats["occurrences"] < MIN_OCCURRENCES:
            continue

        success_rate = stats["successes"] / stats["occurrences"]
        avg_return = stats["total_return"] / stats["occurrences"]

        keyword_analysis[keyword] = {
            "occurrences": stats["occurrences"],
            "success_rate": round(success_rate, 3),
            "avg_return_pct": round(avg_return, 2),
            "successes": stats["successes"],
            "failures": stats["failures"]
        }

    return {
        "window": window_name,
        "total_outcomes": len(outcomes),
        "keywords_analyzed": len(keyword_analysis),
        "keyword_stats": keyword_analysis
    }


def calculate_weighted_recommendations(window_results: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Calculate weighted composite recommendations across all windows.

    Args:
        window_results: Dictionary of window_name -> analysis results

    Returns:
        Weighted recommendations
    """
    # Collect all keywords across windows
    all_keywords = set()
    for window_data in window_results.values():
        all_keywords.update(window_data["keyword_stats"].keys())

    weighted_recommendations = {}

    for keyword in all_keywords:
        weighted_success = 0.0
        weighted_return = 0.0
        total_weight = 0.0

        window_presence = []

        for window_name, window_data in window_results.items():
            window_config = WINDOWS[window_name]
            weight = window_config["weight"]

            if keyword in window_data["keyword_stats"]:
                stats = window_data["keyword_stats"][keyword]
                weighted_success += stats["success_rate"] * weight
                weighted_return += stats["avg_return_pct"] * weight
                total_weight += weight
                window_presence.append(window_name)

        if total_weight > 0:
            # Calculate trend indicator
            trend = "stable"
            if "7d" in window_presence and "90d" in window_presence:
                short_term = window_results["7d"]["keyword_stats"][keyword]["success_rate"]
                long_term = window_results["90d"]["keyword_stats"][keyword]["success_rate"]

                if short_term > long_term * 1.2:
                    trend = "improving"
                elif short_term < long_term * 0.8:
                    trend = "declining"

            weighted_recommendations[keyword] = {
                "weighted_success_rate": round(weighted_success, 3),
                "weighted_avg_return": round(weighted_return, 2),
                "windows_present": window_presence,
                "trend": trend
            }

    # Sort by weighted success rate
    sorted_keywords = sorted(
        weighted_recommendations.items(),
        key=lambda x: x[1]["weighted_success_rate"],
        reverse=True
    )

    return {
        "total_keywords": len(weighted_recommendations),
        "recommendations": dict(sorted_keywords[:50])  # Top 50
    }


def detect_divergent_signals(window_results: Dict[str, Dict]) -> List[Dict]:
    """
    Identify keywords with divergent signals across windows.

    Args:
        window_results: Dictionary of window_name -> analysis results

    Returns:
        List of keywords with divergent signals
    """
    divergent = []

    # Compare 7-day vs 90-day for divergence
    if "7d" not in window_results or "90d" not in window_results:
        return divergent

    short_term = window_results["7d"]["keyword_stats"]
    long_term = window_results["90d"]["keyword_stats"]

    # Find keywords present in both windows
    common_keywords = set(short_term.keys()) & set(long_term.keys())

    for keyword in common_keywords:
        st_success = short_term[keyword]["success_rate"]
        lt_success = long_term[keyword]["success_rate"]

        # Check for significant divergence (>30% difference)
        divergence = abs(st_success - lt_success)

        if divergence >= 0.3:
            divergent.append({
                "keyword": keyword,
                "7d_success_rate": round(st_success, 3),
                "90d_success_rate": round(lt_success, 3),
                "divergence": round(divergence, 3),
                "signal": "bullish" if st_success > lt_success else "bearish"
            })

    # Sort by divergence
    divergent.sort(key=lambda x: x["divergence"], reverse=True)

    return divergent


def main():
    """Run multi-window analysis proof of concept."""
    print("=" * 80)
    print("Multi-Window Analysis Proof of Concept (Ticket #6)")
    print("=" * 80)
    print()

    # Results container
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "windows": {},
        "weighted_recommendations": {},
        "divergent_signals": []
    }

    # Analyze each window
    for window_name, window_config in WINDOWS.items():
        print(f"Analyzing {window_config['name']}...")

        # Fetch data from both sources
        moa_outcomes = fetch_moa_outcomes(MOA_DB_PATH, window_config["days"])
        feedback_outcomes = fetch_feedback_outcomes(FEEDBACK_DB_PATH, window_config["days"])

        # Combine outcomes
        all_outcomes = moa_outcomes + feedback_outcomes

        print(f"  Total outcomes: {len(all_outcomes)}")

        # Analyze window
        window_results = analyze_window(all_outcomes, window_name)
        results["windows"][window_name] = window_results

        print(f"  Keywords analyzed: {window_results['keywords_analyzed']}")
        print()

    # Calculate weighted recommendations
    print("Calculating weighted recommendations...")
    results["weighted_recommendations"] = calculate_weighted_recommendations(results["windows"])
    print(f"  Total keywords: {results['weighted_recommendations']['total_keywords']}")
    print()

    # Detect divergent signals
    print("Detecting divergent signals...")
    results["divergent_signals"] = detect_divergent_signals(results["windows"])
    print(f"  Divergent keywords found: {len(results['divergent_signals'])}")
    print()

    # Save results
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {OUTPUT_PATH}")
    print()

    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for window_name, window_data in results["windows"].items():
        window_config = WINDOWS[window_name]
        print(f"\n{window_config['name']} (weight: {window_config['weight']:.0%})")
        print(f"  Outcomes: {window_data['total_outcomes']}")
        print(f"  Keywords: {window_data['keywords_analyzed']}")

    print(f"\nWeighted Recommendations: {results['weighted_recommendations']['total_keywords']} keywords")
    print(f"Divergent Signals: {len(results['divergent_signals'])} keywords")

    # Show top 5 weighted recommendations
    if results["weighted_recommendations"]["recommendations"]:
        print("\nTop 5 Weighted Recommendations:")
        for i, (keyword, stats) in enumerate(list(results["weighted_recommendations"]["recommendations"].items())[:5], 1):
            print(f"  {i}. '{keyword}'")
            print(f"     Success Rate: {stats['weighted_success_rate']:.1%}")
            print(f"     Avg Return: {stats['weighted_avg_return']:.1f}%")
            print(f"     Trend: {stats['trend']}")
            print(f"     Windows: {', '.join(stats['windows_present'])}")

    # Show top 5 divergent signals
    if results["divergent_signals"]:
        print("\nTop 5 Divergent Signals:")
        for i, signal in enumerate(results["divergent_signals"][:5], 1):
            print(f"  {i}. '{signal['keyword']}' ({signal['signal']})")
            print(f"     7d: {signal['7d_success_rate']:.1%}, 90d: {signal['90d_success_rate']:.1%}")
            print(f"     Divergence: {signal['divergence']:.1%}")

    print()
    print("=" * 80)
    print("Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
