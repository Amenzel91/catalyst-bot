"""
MOA Historical Analyzer - Uses bootstrapped outcomes data

Analyzes historical outcomes.jsonl to identify missed opportunities and
generate keyword weight recommendations.

This version reads pre-calculated outcomes from the bootstrapper instead
of fetching live prices.

Phase 3 (Agent 3): Added sector context analysis to identify which sectors
have best catalyst response rates.

Author: Claude Code (MOA Phase 2.5B)
Date: 2025-10-11
Updated: 2025-10-12 (Agent 3: Sector Analysis)
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .llm_usage_monitor import get_monitor
from .logging_utils import get_logger

log = get_logger("moa_historical")

# Configuration
SUCCESS_THRESHOLD_PCT = 10.0  # >10% price increase = missed opportunity
MIN_OCCURRENCES = (
    3  # Minimum occurrences for statistical significance (lowered for small dataset)
)
TIMEFRAME_PRIORITY = [
    "7d",
    "1d",
    "4h",
    "1h",
    "30m",
    "15m",
]  # Priority order for choosing best timeframe
FLASH_CATALYST_THRESHOLD_PCT = 5.0  # >5% move in 15-30 minutes = flash catalyst
INTRADAY_TIMEFRAMES = ["15m", "30m", "1h"]  # Short-term timeframes for timing analysis


def _repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def _ensure_moa_dirs() -> Tuple[Path, Path]:
    """Ensure MOA directories exist and return paths."""
    root = _repo_root()
    moa_dir = root / "data" / "moa"
    moa_dir.mkdir(parents=True, exist_ok=True)
    return root, moa_dir


def load_outcomes() -> List[Dict[str, Any]]:
    """
    Load outcomes from data/moa/outcomes.jsonl.

    Deduplicates by (ticker, rejection_ts) to handle cases where the
    bootstrapper was run multiple times with overlapping date ranges.

    Returns:
        List of outcome dictionaries with rejection data and price outcomes
    """
    _, moa_dir = _ensure_moa_dirs()
    outcomes_path = moa_dir / "outcomes.jsonl"

    if not outcomes_path.exists():
        log.warning(f"outcomes_not_found path={outcomes_path}")
        return []

    outcomes = []
    seen_keys = set()  # Track (ticker, rejection_ts) to detect duplicates
    duplicate_count = 0

    try:
        with open(outcomes_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    outcome = json.loads(line)

                    # Create deduplication key from ticker and rejection timestamp
                    ticker = outcome.get("ticker", "")
                    rejection_ts = outcome.get("rejection_ts", "")
                    dedupe_key = (ticker, rejection_ts)

                    # Skip if we've already seen this ticker+timestamp combination
                    if dedupe_key in seen_keys:
                        duplicate_count += 1
                        log.debug(
                            f"duplicate_outcome_skipped ticker={ticker} ts={rejection_ts}"
                        )
                        continue

                    seen_keys.add(dedupe_key)
                    outcomes.append(outcome)

                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        if duplicate_count > 0:
            log.info(
                f"loaded_outcomes_with_dedup count={len(outcomes)} "
                f"duplicates_removed={duplicate_count}"
            )
        else:
            log.info(f"loaded_outcomes count={len(outcomes)}")

        return outcomes

    except Exception as e:
        log.error(f"load_outcomes_failed err={e}")
        return []


def load_rejected_items() -> Dict[str, Dict[str, Any]]:
    """
    Load rejected items from data/rejected_items.jsonl.

    Returns:
        Dict mapping (ticker, rejection_ts) -> rejected item data
    """
    root, _ = _ensure_moa_dirs()
    rejected_path = root / "data" / "rejected_items.jsonl"

    if not rejected_path.exists():
        log.warning(f"rejected_items_not_found path={rejected_path}")
        return {}

    items = {}
    try:
        with open(rejected_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(line)
                    ticker = item.get("ticker", "")
                    ts = item.get("ts", "")
                    if ticker and ts:
                        key = (ticker, ts)
                        items[key] = item
                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        log.info(f"loaded_rejected_items count={len(items)}")
        return items

    except Exception as e:
        log.error(f"load_rejected_items_failed err={e}")
        return {}


def identify_missed_opportunities(
    outcomes: List[Dict[str, Any]],
    threshold_pct: float = SUCCESS_THRESHOLD_PCT,
) -> List[Dict[str, Any]]:
    """
    Identify outcomes that represent missed opportunities.

    Args:
        outcomes: List of outcome dictionaries
        threshold_pct: Success threshold percentage

    Returns:
        List of missed opportunity dictionaries
    """
    missed_opps = []

    for outcome in outcomes:
        # Check if this is a missed opportunity
        is_missed = outcome.get("is_missed_opportunity", False)
        max_return = outcome.get("max_return_pct", 0.0)

        # Also manually check in case is_missed_opportunity wasn't set
        if not is_missed and max_return >= threshold_pct:
            is_missed = True

        if is_missed:
            missed_opps.append(outcome)

    log.info(
        f"identified_missed_opportunities "
        f"total={len(outcomes)} missed={len(missed_opps)} "
        f"rate={len(missed_opps)/len(outcomes)*100:.1f}%"
    )

    return missed_opps


def merge_rejection_data(
    outcomes: List[Dict[str, Any]], rejected_items: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merge outcome data with rejected item metadata (keywords, sentiment, etc.).

    Args:
        outcomes: List of outcome dictionaries
        rejected_items: Dict of rejected items keyed by (ticker, ts)

    Returns:
        List of merged dictionaries with both outcome and rejection data
    """
    merged = []

    for outcome in outcomes:
        ticker = outcome.get("ticker", "")
        rejection_ts = outcome.get("rejection_ts", "")
        key = (ticker, rejection_ts)

        rejected_item = rejected_items.get(key)

        if rejected_item:
            # Merge outcome and rejection data
            merged_item = {
                **outcome,
                "cls": rejected_item.get("cls", {}),
                "title": rejected_item.get("title", ""),
                "source": rejected_item.get("source", ""),
                "summary": rejected_item.get("summary", ""),
            }
            merged.append(merged_item)
        else:
            # No rejection data found, use outcome only
            log.debug(f"no_rejection_data_found ticker={ticker} ts={rejection_ts}")
            merged.append(outcome)

    keyword_count = sum(1 for m in merged if m.get("cls", {}).get("keywords"))
    log.info(f"merged_data total={len(merged)} with_keywords={keyword_count}")
    return merged


def extract_keywords_from_missed_opps(
    missed_opps: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Extract and analyze keywords from missed opportunities.

    Args:
        missed_opps: List of missed opportunity items

    Returns:
        Dict mapping keyword -> stats (occurrences, success_rate, avg_return)
    """
    keyword_stats = defaultdict(
        lambda: {"occurrences": 0, "successes": 0, "total_return": 0.0, "examples": []}
    )

    for item in missed_opps:
        keywords = item.get("cls", {}).get("keywords", [])
        max_return = item.get("max_return_pct", 0.0)
        ticker = item.get("ticker", "")
        rejection_reason = item.get("rejection_reason", "")

        # Track stats for each keyword
        for kw in keywords:
            kw_lower = str(kw).lower()
            keyword_stats[kw_lower]["occurrences"] += 1

            if max_return >= SUCCESS_THRESHOLD_PCT:
                keyword_stats[kw_lower]["successes"] += 1

            keyword_stats[kw_lower]["total_return"] += max_return

            # Store example (limit to 3 per keyword)
            examples = keyword_stats[kw_lower]["examples"]
            if len(examples) < 3:
                examples.append(
                    {
                        "ticker": ticker,
                        "return_pct": round(max_return, 2),
                        "rejection_reason": rejection_reason,
                    }
                )

    # Calculate success rates and average returns
    results = {}
    for kw, stats in keyword_stats.items():
        occurrences = stats["occurrences"]

        if occurrences >= MIN_OCCURRENCES:
            results[kw] = {
                "occurrences": occurrences,
                "successes": stats["successes"],
                "success_rate": round(stats["successes"] / occurrences, 3),
                "avg_return": round(stats["total_return"] / occurrences, 2),
                "examples": stats["examples"],
            }

    log.info(
        f"extracted_keywords "
        f"total_unique={len(keyword_stats)} "
        f"significant={len(results)} "
        f"min_occurrences={MIN_OCCURRENCES}"
    )

    return results


def analyze_rejection_reasons(
    outcomes: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze which rejection reasons led to missed opportunities.

    Args:
        outcomes: List of all outcomes

    Returns:
        Dict mapping rejection_reason -> stats
    """
    reason_stats = defaultdict(
        lambda: {
            "total": 0,
            "missed_opportunities": 0,
            "avg_return_all": 0.0,
            "avg_return_missed": 0.0,
            "total_return": 0.0,
            "missed_return": 0.0,
        }
    )

    for outcome in outcomes:
        reason = outcome.get("rejection_reason", "UNKNOWN")
        max_return = outcome.get("max_return_pct", 0.0)
        is_missed = outcome.get("is_missed_opportunity", False)

        reason_stats[reason]["total"] += 1
        reason_stats[reason]["total_return"] += max_return

        if is_missed:
            reason_stats[reason]["missed_opportunities"] += 1
            reason_stats[reason]["missed_return"] += max_return

    # Calculate averages
    results = {}
    for reason, stats in reason_stats.items():
        total = stats["total"]
        missed = stats["missed_opportunities"]

        results[reason] = {
            "total": total,
            "missed_opportunities": missed,
            "miss_rate": round(missed / total, 3) if total > 0 else 0.0,
            "avg_return_all": (
                round(stats["total_return"] / total, 2) if total > 0 else 0.0
            ),
            "avg_return_missed": (
                round(stats["missed_return"] / missed, 2) if missed > 0 else 0.0
            ),
        }

    log.info(f"analyzed_rejection_reasons count={len(results)}")
    return results


def analyze_intraday_timing(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze intraday timing patterns (15m, 30m, 1h) to identify optimal entry/exit windows.

    Args:
        outcomes: List of all outcomes with intraday data

    Returns:
        Dict with timing analysis including when catalysts typically peak
    """
    timing_stats = {
        "15m": {"count": 0, "total_return": 0.0, "positive_count": 0, "returns": []},
        "30m": {"count": 0, "total_return": 0.0, "positive_count": 0, "returns": []},
        "1h": {"count": 0, "total_return": 0.0, "positive_count": 0, "returns": []},
    }

    peak_timing_analysis = []  # Which timeframe had the best return for each outcome

    for outcome in outcomes:
        outcomes_data = outcome.get("outcomes", {})
        ticker = outcome.get("ticker", "")

        # Collect intraday returns
        timeframe_returns = {}
        for tf in ["15m", "30m", "1h"]:
            if tf in outcomes_data:
                return_pct = outcomes_data[tf].get("return_pct", 0.0)
                timing_stats[tf]["count"] += 1
                timing_stats[tf]["total_return"] += return_pct
                timing_stats[tf]["returns"].append(return_pct)

                if return_pct > 0:
                    timing_stats[tf]["positive_count"] += 1

                timeframe_returns[tf] = return_pct

        # Determine which timeframe peaked for this catalyst
        if timeframe_returns:
            peak_tf = max(timeframe_returns.items(), key=lambda x: x[1])
            peak_timing_analysis.append(
                {
                    "ticker": ticker,
                    "peak_timeframe": peak_tf[0],
                    "peak_return": peak_tf[1],
                    "all_returns": timeframe_returns,
                }
            )

    # Calculate statistics
    results = {
        "timeframe_stats": {},
        "peak_timing_distribution": defaultdict(int),
        "optimal_window_recommendation": "",
    }

    for tf, stats in timing_stats.items():
        if stats["count"] > 0:
            avg_return = stats["total_return"] / stats["count"]
            positive_rate = stats["positive_count"] / stats["count"]

            results["timeframe_stats"][tf] = {
                "count": stats["count"],
                "avg_return_pct": round(avg_return, 2),
                "positive_rate": round(positive_rate, 3),
                "median_return_pct": (
                    round(sorted(stats["returns"])[len(stats["returns"]) // 2], 2)
                    if stats["returns"]
                    else 0.0
                ),
            }

    # Analyze when catalysts typically peak
    for item in peak_timing_analysis:
        peak_tf = item["peak_timeframe"]
        results["peak_timing_distribution"][peak_tf] += 1

    # Determine optimal window
    if results["peak_timing_distribution"]:
        most_common_peak = max(
            results["peak_timing_distribution"].items(), key=lambda x: x[1]
        )[0]
        results["optimal_window_recommendation"] = most_common_peak

    # Convert defaultdict to regular dict for JSON serialization
    results["peak_timing_distribution"] = dict(results["peak_timing_distribution"])

    log.info(
        f"analyzed_intraday_timing "
        f"15m_count={timing_stats['15m']['count']} "
        f"30m_count={timing_stats['30m']['count']} "
        f"1h_count={timing_stats['1h']['count']}"
    )

    return results


def identify_flash_catalysts(
    outcomes: List[Dict[str, Any]],
    threshold_pct: float = FLASH_CATALYST_THRESHOLD_PCT,
) -> List[Dict[str, Any]]:
    """
    Identify 'flash catalysts' - stocks that move >5% in first 15-30 minutes.

    Args:
        outcomes: List of outcome dictionaries
        threshold_pct: Threshold for flash catalyst classification

    Returns:
        List of flash catalyst dictionaries with metadata
    """
    flash_catalysts = []

    for outcome in outcomes:
        outcomes_data = outcome.get("outcomes", {})

        # Check 15m and 30m timeframes
        for tf in ["15m", "30m"]:
            if tf in outcomes_data:
                return_pct = outcomes_data[tf].get("return_pct", 0.0)

                if abs(return_pct) >= threshold_pct:
                    flash_catalysts.append(
                        {
                            "ticker": outcome.get("ticker", ""),
                            "rejection_ts": outcome.get("rejection_ts", ""),
                            "rejection_reason": outcome.get("rejection_reason", ""),
                            "timeframe": tf,
                            "return_pct": return_pct,
                            "direction": "UP" if return_pct > 0 else "DOWN",
                            "keywords": outcome.get("cls", {}).get("keywords", []),
                            "title": outcome.get("title", ""),
                        }
                    )
                    break  # Only count once per outcome (prefer shorter timeframe)

    log.info(
        f"identified_flash_catalysts "
        f"count={len(flash_catalysts)} "
        f"threshold={threshold_pct}%"
    )

    return flash_catalysts


def analyze_intraday_keyword_correlation(
    outcomes: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze which keywords correlate with fast 15m/30m moves.

    Args:
        outcomes: List of outcomes with keyword and intraday data

    Returns:
        Dict mapping keyword -> intraday performance stats
    """
    keyword_intraday_stats = defaultdict(
        lambda: {
            "15m": {"count": 0, "total_return": 0.0, "max_return": 0.0},
            "30m": {"count": 0, "total_return": 0.0, "max_return": 0.0},
        }
    )

    for outcome in outcomes:
        keywords = outcome.get("cls", {}).get("keywords", [])
        outcomes_data = outcome.get("outcomes", {})

        if not keywords:
            continue

        for tf in ["15m", "30m"]:
            if tf in outcomes_data:
                return_pct = outcomes_data[tf].get("return_pct", 0.0)

                for kw in keywords:
                    kw_lower = str(kw).lower()
                    keyword_intraday_stats[kw_lower][tf]["count"] += 1
                    keyword_intraday_stats[kw_lower][tf]["total_return"] += return_pct
                    keyword_intraday_stats[kw_lower][tf]["max_return"] = max(
                        keyword_intraday_stats[kw_lower][tf]["max_return"], return_pct
                    )

    # Calculate averages and filter significant keywords
    results = {}
    for kw, stats in keyword_intraday_stats.items():
        kw_results = {}
        has_data = False

        for tf in ["15m", "30m"]:
            if stats[tf]["count"] >= MIN_OCCURRENCES:
                has_data = True
                avg_return = stats[tf]["total_return"] / stats[tf]["count"]
                kw_results[tf] = {
                    "count": stats[tf]["count"],
                    "avg_return_pct": round(avg_return, 2),
                    "max_return_pct": round(stats[tf]["max_return"], 2),
                }

        if has_data:
            results[kw] = kw_results

    log.info(f"analyzed_intraday_keyword_correlation keywords={len(results)}")
    return results


def analyze_sector_performance(
    outcomes: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze which sectors have best catalyst response rates.

    Args:
        outcomes: List of all outcomes with sector context

    Returns:
        Dict mapping sector -> performance stats
    """
    sector_stats = defaultdict(
        lambda: {
            "total": 0,
            "missed_opportunities": 0,
            "total_return": 0.0,
            "missed_return": 0.0,
            "hot_sector_count": 0,  # Count when sector was outperforming SPY
            "cold_sector_count": 0,  # Count when sector was underperforming SPY
        }
    )

    for outcome in outcomes:
        sector_context = outcome.get("sector_context", {})
        sector = sector_context.get("sector")

        if not sector:
            continue

        max_return = outcome.get("max_return_pct", 0.0)
        is_missed = outcome.get("is_missed_opportunity", False)
        sector_vs_spy = sector_context.get("sector_vs_spy")

        sector_stats[sector]["total"] += 1
        sector_stats[sector]["total_return"] += max_return

        if is_missed:
            sector_stats[sector]["missed_opportunities"] += 1
            sector_stats[sector]["missed_return"] += max_return

        # Track hot vs cold sector performance
        if sector_vs_spy is not None:
            if sector_vs_spy > 0:
                sector_stats[sector]["hot_sector_count"] += 1
            else:
                sector_stats[sector]["cold_sector_count"] += 1

    # Calculate statistics
    results = {}
    for sector, stats in sector_stats.items():
        total = stats["total"]
        missed = stats["missed_opportunities"]

        if total < MIN_OCCURRENCES:
            continue

        results[sector] = {
            "total": total,
            "missed_opportunities": missed,
            "miss_rate": round(missed / total, 3) if total > 0 else 0.0,
            "avg_return_all": (
                round(stats["total_return"] / total, 2) if total > 0 else 0.0
            ),
            "avg_return_missed": (
                round(stats["missed_return"] / missed, 2) if missed > 0 else 0.0
            ),
            "hot_sector_rate": (
                round(stats["hot_sector_count"] / total, 3) if total > 0 else 0.0
            ),
        }

    log.info(f"analyzed_sector_performance sectors={len(results)}")
    return results


def analyze_rvol_correlation(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze correlation between RVOL and catalyst success.

    Determines if high relative volume leads to better catalyst outcomes.

    Args:
        outcomes: List of outcomes with RVOL data

    Returns:
        Dict with RVOL category performance stats
    """
    rvol_stats = defaultdict(
        lambda: {
            "total": 0,
            "missed_opportunities": 0,
            "total_return": 0.0,
            "missed_return": 0.0,
        }
    )

    for outcome in outcomes:
        rvol_category = outcome.get("rvol_category")

        if not rvol_category:
            continue

        max_return = outcome.get("max_return_pct", 0.0)
        is_missed = outcome.get("is_missed_opportunity", False)

        rvol_stats[rvol_category]["total"] += 1
        rvol_stats[rvol_category]["total_return"] += max_return

        if is_missed:
            rvol_stats[rvol_category]["missed_opportunities"] += 1
            rvol_stats[rvol_category]["missed_return"] += max_return

    # Calculate statistics
    results = {}
    for category, stats in rvol_stats.items():
        total = stats["total"]
        missed = stats["missed_opportunities"]

        if total < MIN_OCCURRENCES:
            continue

        results[category] = {
            "total": total,
            "missed_opportunities": missed,
            "miss_rate": round(missed / total, 3) if total > 0 else 0.0,
            "avg_return_all": (
                round(stats["total_return"] / total, 2) if total > 0 else 0.0
            ),
            "avg_return_missed": (
                round(stats["missed_return"] / missed, 2) if missed > 0 else 0.0
            ),
        }

    # Generate recommendation
    recommendation = ""
    if "HIGH" in results and "LOW" in results:
        high_miss_rate = results["HIGH"]["miss_rate"]
        low_miss_rate = results["LOW"]["miss_rate"]

        if high_miss_rate > low_miss_rate * 1.2:
            recommendation = (
                "High RVOL catalysts show significantly better success rates. "
                "Prioritize catalysts with RVOL > 2.0 for best outcomes."
            )
        elif low_miss_rate > high_miss_rate * 1.2:
            recommendation = (
                "Low RVOL catalysts surprisingly perform better. "
                "Volume may not be a strong predictor for this dataset."
            )
        else:
            recommendation = (
                "RVOL shows minimal correlation with catalyst success. "
                "Focus on other factors (keywords, sector, timing)."
            )

    log.info(f"analyzed_rvol_correlation categories={len(results)}")

    return {
        "rvol_categories": results,
        "recommendation": recommendation,
    }


def analyze_regime_performance(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze missed opportunity rates by market regime.

    Identifies which market regimes have highest success rates for catalysts.

    Args:
        outcomes: List of outcomes with market regime data

    Returns:
        Dict mapping regime -> performance stats
    """
    regime_stats = defaultdict(
        lambda: {
            "total": 0,
            "missed_opportunities": 0,
            "total_return": 0.0,
            "missed_return": 0.0,
            "avg_vix": [],
        }
    )

    for outcome in outcomes:
        regime = outcome.get("market_regime")

        if not regime:
            continue

        max_return = outcome.get("max_return_pct", 0.0)
        is_missed = outcome.get("is_missed_opportunity", False)
        vix = outcome.get("market_vix")

        regime_stats[regime]["total"] += 1
        regime_stats[regime]["total_return"] += max_return

        if is_missed:
            regime_stats[regime]["missed_opportunities"] += 1
            regime_stats[regime]["missed_return"] += max_return

        # Track VIX levels for this regime
        if vix is not None:
            regime_stats[regime]["avg_vix"].append(vix)

    # Calculate statistics
    results = {}
    for regime, stats in regime_stats.items():
        total = stats["total"]
        missed = stats["missed_opportunities"]

        if total < MIN_OCCURRENCES:
            continue

        # Calculate average VIX for this regime
        avg_vix = (
            sum(stats["avg_vix"]) / len(stats["avg_vix"]) if stats["avg_vix"] else None
        )

        results[regime] = {
            "total": total,
            "missed_opportunities": missed,
            "miss_rate": round(missed / total, 3) if total > 0 else 0.0,
            "avg_return_all": (
                round(stats["total_return"] / total, 2) if total > 0 else 0.0
            ),
            "avg_return_missed": (
                round(stats["missed_return"] / missed, 2) if missed > 0 else 0.0
            ),
            "avg_vix": round(avg_vix, 2) if avg_vix is not None else None,
        }

    # Generate recommendation based on regime performance
    recommendation = ""
    if results:
        # Find regime with highest miss rate
        best_regime = max(results.items(), key=lambda x: x[1]["miss_rate"])
        worst_regime = min(results.items(), key=lambda x: x[1]["miss_rate"])

        if best_regime[1]["miss_rate"] > worst_regime[1]["miss_rate"] * 1.3:
            recommendation = (
                f"{best_regime[0]} regime shows highest catalyst success rate "
                f"({best_regime[1]['miss_rate']*100:.1f}%). "
                f"Consider prioritizing catalysts during this market condition."
            )
        else:
            recommendation = (
                "Market regime shows minimal impact on catalyst success. "
                "Focus on other factors (keywords, sector, timing)."
            )

    log.info(f"analyzed_regime_performance regimes={len(results)}")

    return {
        "regime_categories": results,
        "recommendation": recommendation,
    }


def analyze_sector_timing_correlation(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze correlation between sector strength and catalyst success.

    Determines if hot sectors (outperforming SPY) lead to better catalyst outcomes.

    Args:
        outcomes: List of outcomes with sector context

    Returns:
        Dict with hot vs cold sector comparison
    """
    hot_sector_outcomes = []
    cold_sector_outcomes = []

    for outcome in outcomes:
        sector_context = outcome.get("sector_context", {})
        sector_vs_spy = sector_context.get("sector_vs_spy")

        if sector_vs_spy is None:
            continue

        max_return = outcome.get("max_return_pct", 0.0)
        is_missed = outcome.get("is_missed_opportunity", False)

        outcome_data = {
            "max_return": max_return,
            "is_missed": is_missed,
            "sector": sector_context.get("sector"),
            "sector_vs_spy": sector_vs_spy,
        }

        if sector_vs_spy > 0:
            hot_sector_outcomes.append(outcome_data)
        else:
            cold_sector_outcomes.append(outcome_data)

    # Calculate statistics
    def calc_stats(outcomes_list):
        if not outcomes_list:
            return {
                "count": 0,
                "missed_count": 0,
                "miss_rate": 0.0,
                "avg_return": 0.0,
            }

        missed_count = sum(1 for o in outcomes_list if o["is_missed"])
        total_return = sum(o["max_return"] for o in outcomes_list)

        return {
            "count": len(outcomes_list),
            "missed_count": missed_count,
            "miss_rate": round(missed_count / len(outcomes_list), 3),
            "avg_return": round(total_return / len(outcomes_list), 2),
        }

    results = {
        "hot_sectors": calc_stats(hot_sector_outcomes),
        "cold_sectors": calc_stats(cold_sector_outcomes),
        "recommendation": "",
    }

    # Generate recommendation
    hot_miss_rate = results["hot_sectors"]["miss_rate"]
    cold_miss_rate = results["cold_sectors"]["miss_rate"]

    if hot_miss_rate > cold_miss_rate * 1.2:
        results["recommendation"] = (
            "Hot sectors show significantly higher catalyst success rates. "
            "Consider prioritizing catalysts in sectors outperforming SPY."
        )
    elif cold_miss_rate > hot_miss_rate * 1.2:
        results["recommendation"] = (
            "Cold sectors show higher catalyst success rates (contrarian signal). "
            "Sector weakness may create oversold bounce opportunities."
        )
    else:
        results["recommendation"] = (
            "Sector momentum shows minimal impact on catalyst success. "
            "Focus on other factors (keywords, timing, etc.)."
        )

    log.info(
        f"analyzed_sector_timing hot={results['hot_sectors']['count']} "
        f"cold={results['cold_sectors']['count']}"
    )

    return results


def calculate_weight_recommendations(
    keyword_stats: Dict[str, Dict[str, Any]],
    intraday_keyword_stats: Dict[str, Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate keyword weight recommendations based on historical performance.

    Args:
        keyword_stats: Keyword statistics from missed opportunities
        intraday_keyword_stats: Optional intraday (15m/30m) keyword performance stats

    Returns:
        List of recommendation dictionaries
    """
    recommendations = []

    for keyword, stats in keyword_stats.items():
        occurrences = stats["occurrences"]
        success_rate = stats["success_rate"]
        avg_return = stats["avg_return"]

        # Calculate recommended weight based on performance
        # Base weight starts at 1.0
        # Add bonus for high success rate
        # Add bonus for high average return

        base_weight = 1.0

        # Success rate bonus (0 to +1.0)
        success_bonus = success_rate * 1.0

        # Average return bonus (0 to +0.5)
        # Normalize by dividing by 50% (so 50%+ return gets max bonus)
        return_bonus = min(avg_return / 50.0, 1.0) * 0.5

        # Intraday bonus (0 to +0.3) if keyword shows strong 15m/30m performance
        intraday_bonus = 0.0
        intraday_info = {}
        if intraday_keyword_stats and keyword in intraday_keyword_stats:
            intraday_stats = intraday_keyword_stats[keyword]

            # Check for strong intraday performance
            for tf in ["15m", "30m"]:
                if tf in intraday_stats:
                    tf_avg = intraday_stats[tf].get("avg_return_pct", 0.0)
                    if tf_avg >= FLASH_CATALYST_THRESHOLD_PCT:
                        intraday_bonus = 0.3
                        intraday_info[tf] = intraday_stats[tf]
                        break
                    elif tf_avg >= 3.0:
                        intraday_bonus = 0.15
                        intraday_info[tf] = intraday_stats[tf]

        recommended_weight = round(
            base_weight + success_bonus + return_bonus + intraday_bonus, 2
        )
        recommended_weight = max(0.5, min(recommended_weight, 3.0))

        # Calculate confidence based on sample size and success rate
        if occurrences >= 10 and success_rate >= 0.7:
            confidence = 0.9
        elif occurrences >= 5 and success_rate >= 0.6:
            confidence = 0.75
        elif occurrences >= MIN_OCCURRENCES and success_rate >= 0.5:
            confidence = 0.6
        else:
            confidence = 0.5

        evidence = {
            "occurrences": occurrences,
            "success_rate": success_rate,
            "avg_return_pct": avg_return,
            "examples": stats.get("examples", []),
        }

        # Add intraday evidence if available
        if intraday_info:
            evidence["intraday_performance"] = intraday_info

        recommendations.append(
            {
                "keyword": keyword,
                "recommended_weight": recommended_weight,
                "confidence": confidence,
                "evidence": evidence,
            }
        )

    # Sort by confidence (highest first), then by avg_return
    recommendations.sort(
        key=lambda x: (x["confidence"], x["evidence"]["avg_return_pct"]), reverse=True
    )

    log.info(f"generated_recommendations count={len(recommendations)}")
    return recommendations


def save_analysis_report(
    report: Dict[str, Any],
) -> Path:
    """
    Save analysis report to data/moa/analysis_report.json.

    Args:
        report: Analysis report dictionary

    Returns:
        Path to saved report file
    """
    _, moa_dir = _ensure_moa_dirs()
    report_path = moa_dir / "analysis_report.json"

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        log.info(f"saved_analysis_report path={report_path}")
        return report_path

    except Exception as e:
        log.error(f"save_analysis_report_failed err={e}")
        raise


def run_historical_moa_analysis() -> Dict[str, Any]:
    """
    Run complete MOA analysis using historical outcomes data.

    Returns:
        Analysis results dictionary
    """
    start_time = time.time()
    log.info("moa_historical_analysis_start")

    try:
        # 1. Load outcomes and rejected items
        outcomes = load_outcomes()
        if not outcomes:
            return {
                "status": "no_data",
                "message": "No outcomes found in data/moa/outcomes.jsonl",
            }

        rejected_items = load_rejected_items()

        # 2. Merge outcomes with rejection metadata
        merged_data = merge_rejection_data(outcomes, rejected_items)

        # 3. Identify missed opportunities
        missed_opps = identify_missed_opportunities(merged_data)

        if not missed_opps:
            log.warning("no_missed_opportunities")
            return {
                "status": "no_opportunities",
                "message": "No missed opportunities identified (none with >10% return)",
                "total_outcomes": len(outcomes),
            }

        # 4. Extract keywords from missed opportunities
        keyword_stats = extract_keywords_from_missed_opps(missed_opps)

        # 5. Analyze rejection reasons
        rejection_analysis = analyze_rejection_reasons(merged_data)

        # 6. Analyze intraday timing patterns (15m/30m/1h)
        intraday_timing = analyze_intraday_timing(merged_data)

        # 7. Identify flash catalysts (>5% moves in 15-30 minutes)
        flash_catalysts = identify_flash_catalysts(merged_data)

        # 8. Analyze intraday keyword correlations
        intraday_keyword_stats = analyze_intraday_keyword_correlation(merged_data)

        # 9. Agent 3: Analyze sector performance
        sector_analysis = analyze_sector_performance(merged_data)

        # 10. Agent 3: Analyze sector timing correlation (hot vs cold sectors)
        sector_timing = analyze_sector_timing_correlation(merged_data)

        # 11. Agent 1: Analyze RVOL correlation with catalyst success
        rvol_analysis = analyze_rvol_correlation(merged_data)

        # 12. Analyze market regime performance
        regime_analysis = analyze_regime_performance(merged_data)

        # 13. Generate weight recommendations (with intraday data)
        recommendations = calculate_weight_recommendations(
            keyword_stats, intraday_keyword_stats
        )

        # 12. Build comprehensive report
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_outcomes": len(outcomes),
                "missed_opportunities": len(missed_opps),
                "miss_rate_pct": round(len(missed_opps) / len(outcomes) * 100, 2),
                "avg_missed_return_pct": (
                    round(
                        sum(o.get("max_return_pct", 0.0) for o in missed_opps)
                        / len(missed_opps),
                        2,
                    )
                    if missed_opps
                    else 0.0
                ),
            },
            "rejection_analysis": rejection_analysis,
            "keyword_stats": keyword_stats,
            "recommendations": recommendations,
            "rvol_analysis": rvol_analysis,
            "regime_analysis": regime_analysis,
            "sector_analysis": {
                "sector_performance": sector_analysis,
                "sector_timing_correlation": sector_timing,
            },
            "intraday_analysis": {
                "timing_patterns": intraday_timing,
                "flash_catalysts": {
                    "count": len(flash_catalysts),
                    "threshold_pct": FLASH_CATALYST_THRESHOLD_PCT,
                    "examples": sorted(
                        flash_catalysts,
                        key=lambda x: abs(x["return_pct"]),
                        reverse=True,
                    )[
                        :15
                    ],  # Top 15 flash catalysts by magnitude
                },
                "keyword_correlations": intraday_keyword_stats,
            },
            "top_missed_opportunities": sorted(
                [
                    {
                        "ticker": o.get("ticker"),
                        "rejection_ts": o.get("rejection_ts"),
                        "rejection_reason": o.get("rejection_reason"),
                        "max_return_pct": o.get("max_return_pct"),
                        "keywords": o.get("cls", {}).get("keywords", []),
                    }
                    for o in missed_opps
                ],
                key=lambda x: x["max_return_pct"],
                reverse=True,
            )[
                :20
            ],  # Top 20 missed opportunities
        }

        # 11. Save report
        report_path = save_analysis_report(report)

        elapsed = time.time() - start_time
        log.info(
            f"moa_historical_analysis_complete "
            f"elapsed={elapsed:.2f}s "
            f"outcomes={len(outcomes)} "
            f"missed={len(missed_opps)} "
            f"keywords={len(keyword_stats)} "
            f"recommendations={len(recommendations)} "
            f"flash_catalysts={len(flash_catalysts)} "
            f"sectors_analyzed={len(sector_analysis)}"
        )

        return {
            "status": "success",
            "report_path": str(report_path),
            "summary": report["summary"],
            "rejection_analysis": rejection_analysis,
            "recommendations_count": len(recommendations),
            "rvol_summary": rvol_analysis,
            "regime_summary": regime_analysis,
            "sector_summary": {
                "sectors_analyzed": len(sector_analysis),
                "hot_vs_cold": sector_timing,
            },
            "intraday_summary": {
                "flash_catalysts_count": len(flash_catalysts),
                "optimal_window": intraday_timing.get(
                    "optimal_window_recommendation", "N/A"
                ),
                "timeframes_analyzed": list(
                    intraday_timing.get("timeframe_stats", {}).keys()
                ),
            },
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as e:
        log.error(f"moa_historical_analysis_failed err={e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# CLI entry point
def main():
    """Run MOA historical analysis from command line."""
    print("Running MOA Historical Analysis...")
    print("=" * 60)

    result = run_historical_moa_analysis()

    print(f"\nStatus: {result['status']}")

    if result["status"] == "success":
        print("\nSummary:")
        summary = result["summary"]
        print(f"  Total outcomes: {summary['total_outcomes']}")
        print(f"  Missed opportunities: {summary['missed_opportunities']}")
        print(f"  Miss rate: {summary['miss_rate_pct']}%")
        print(f"  Avg missed return: {summary['avg_missed_return_pct']}%")

        print("\nRejection Analysis:")
        for reason, stats in result["rejection_analysis"].items():
            print(
                f"  {reason}: {stats['missed_opportunities']}/{stats['total']} "
                f"({stats['miss_rate']*100:.1f}% miss rate, "
                f"avg return: {stats['avg_return_missed']:.1f}%)"
            )

        print("\nRVOL Analysis:")
        rvol = result.get("rvol_summary", {})
        rvol_categories = rvol.get("rvol_categories", {})
        if rvol_categories:
            for category, stats in rvol_categories.items():
                print(
                    f"  {category} RVOL: {stats.get('total', 0)} catalysts "
                    f"({stats.get('miss_rate', 0)*100:.1f}% miss rate, "
                    f"avg return: {stats.get('avg_return_missed', 0):.1f}%)"
                )
            recommendation = rvol.get("recommendation", "")
            if recommendation:
                print(f"  Recommendation: {recommendation}")

        print("\nMarket Regime Analysis:")
        regime = result.get("regime_summary", {})
        regime_categories = regime.get("regime_categories", {})
        if regime_categories:
            for regime_name, stats in regime_categories.items():
                avg_vix = stats.get("avg_vix")
                vix_str = f" (avg VIX: {avg_vix:.2f})" if avg_vix is not None else ""
                print(
                    f"  {regime_name}: {stats.get('total', 0)} catalysts "
                    f"({stats.get('miss_rate', 0)*100:.1f}% miss rate, "
                    f"avg return: {stats.get('avg_return_missed', 0):.1f}%){vix_str}"
                )
            recommendation = regime.get("recommendation", "")
            if recommendation:
                print(f"  Recommendation: {recommendation}")
        else:
            print("  No regime data available in outcomes")

        print("\nSector Analysis:")
        sector = result.get("sector_summary", {})
        print(f"  Sectors analyzed: {sector.get('sectors_analyzed', 0)}")
        hot_vs_cold = sector.get("hot_vs_cold", {})
        if hot_vs_cold:
            hot = hot_vs_cold.get("hot_sectors", {})
            cold = hot_vs_cold.get("cold_sectors", {})
            print(
                f"  Hot sectors (outperforming SPY): {hot.get('count', 0)} "
                f"({hot.get('miss_rate', 0)*100:.1f}% miss rate)"
            )
            print(
                f"  Cold sectors (underperforming SPY): {cold.get('count', 0)} "
                f"({cold.get('miss_rate', 0)*100:.1f}% miss rate)"
            )
            recommendation = hot_vs_cold.get("recommendation", "")
            if recommendation:
                print(f"  Recommendation: {recommendation}")

        print("\nIntraday Analysis (15m/30m):")
        intraday = result.get("intraday_summary", {})
        print(
            f"  Flash catalysts (>5% in 15-30min): {intraday.get('flash_catalysts_count', 0)}"
        )
        print(f"  Optimal entry window: {intraday.get('optimal_window', 'N/A')}")
        print(
            f"  Timeframes with data: {', '.join(intraday.get('timeframes_analyzed', []))}"
        )

        print(
            f"\nRecommendations: {result['recommendations_count']} keyword weight adjustments"
        )
        print(f"\nFull report saved to: {result['report_path']}")

        # Generate LLM usage report
        print("\n" + "=" * 60)
        print("LLM USAGE REPORT")
        print("=" * 60)
        try:
            monitor = get_monitor()
            summary = monitor.get_daily_stats()
            monitor.print_summary(summary)
        except Exception as e:
            print(f"Failed to generate LLM usage report: {e}")
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")

    print("\n" + "=" * 60)
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
