"""
MOA (Missed Opportunities Analyzer) Discord Reporter
======================================================

Posts nightly MOA analysis completion summaries to Discord after analysis runs.
Combines MOA keyword boosts and false positive penalties into a unified report.

Features:
- Top 10 recommendations (MOA boosts + FP penalties)
- Flash catalyst insights (>5% moves in 15-30min)
- Sector performance analysis
- RVOL correlation insights
- Rich Discord embeds with visual formatting

Author: Claude Code
Date: 2025-11-04
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .logging_utils import get_logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("moa_reporter")


def _load_moa_report() -> Optional[Dict[str, Any]]:
    """Load full MOA report from data/moa/analysis_report.json.

    Returns
    -------
    dict or None
        Full MOA report with recommendations, keyword stats, and top missed opportunities
    """
    import json
    report_path = Path(__file__).resolve().parents[2] / "data" / "moa" / "analysis_report.json"

    if not report_path.exists():
        log.debug(f"moa_report_not_found path={report_path}")
        return None

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"moa_report_load_failed err={e}")
        return None


def _load_fp_report() -> Optional[Dict[str, Any]]:
    """Load full False Positive report from data/false_positives/analysis_report.json.

    Returns
    -------
    dict or None
        Full FP report with recommendations
    """
    import json
    report_path = Path(__file__).resolve().parents[2] / "data" / "false_positives" / "analysis_report.json"

    if not report_path.exists():
        log.debug(f"fp_report_not_found path={report_path}")
        return None

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"fp_report_load_failed err={e}")
        return None


def merge_recommendations(
    moa_recs: List[Dict[str, Any]],
    fp_recs: List[Dict[str, Any]],
    min_confidence: float = 0.6,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """Merge MOA boosts and FP penalties into unified recommendation list.

    Parameters
    ----------
    moa_recs : list of dict
        MOA keyword boost recommendations
    fp_recs : list of dict
        False positive penalty recommendations
    min_confidence : float
        Minimum confidence threshold (default: 0.6)
    top_n : int
        Number of top recommendations to return (default: 10)

    Returns
    -------
    list of dict
        Merged recommendations sorted by confidence, limited to top_n
    """
    all_recs = []

    # Add MOA boosts
    for rec in moa_recs or []:
        if rec.get("confidence", 0) >= min_confidence:
            all_recs.append({
                "type": "boost",
                "keyword": rec.get("keyword", "unknown"),
                "weight": rec.get("recommended_weight", 1.0),
                "confidence": rec.get("confidence", 0.0),
                "evidence": rec.get("evidence", {}),
            })

    # Add FP penalties
    for rec in fp_recs or []:
        if rec.get("confidence", 0) >= min_confidence:
            all_recs.append({
                "type": "penalty",
                "keyword": rec.get("keyword", "unknown"),
                "penalty": rec.get("recommended_penalty", -0.5),
                "confidence": rec.get("confidence", 0.0),
                "evidence": rec.get("evidence", {}),
            })

    # Sort by confidence (desc), then by abs(weight/penalty) (desc)
    sorted_recs = sorted(
        all_recs,
        key=lambda x: (
            x["confidence"],
            abs(x.get("weight", x.get("penalty", 0)))
        ),
        reverse=True
    )

    return sorted_recs[:top_n]


def build_moa_completion_embed(
    moa_result: Optional[Dict[str, Any]] = None,
    fp_result: Optional[Dict[str, Any]] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Build Discord embed for MOA completion report.

    Parameters
    ----------
    moa_result : dict, optional
        MOA analysis results from run_historical_moa_analysis()
    fp_result : dict, optional
        False positive analysis results
    top_n : int
        Number of top recommendations to show (default: 10)

    Returns
    -------
    dict
        Discord embed structure
    """
    # Load full reports from disk (the return values only contain summaries)
    moa_full_report = _load_moa_report()
    fp_full_report = _load_fp_report()

    # Extract data from full reports
    moa_summary = moa_full_report.get("summary", {}) if moa_full_report else {}
    moa_recs = moa_full_report.get("recommendations", []) if moa_full_report else []
    moa_top_missed = moa_full_report.get("top_missed_opportunities", []) if moa_full_report else []
    moa_keyword_stats = moa_full_report.get("keyword_stats", {}) if moa_full_report else {}

    fp_summary = fp_full_report.get("summary", {}) if fp_full_report else {}
    fp_recs = fp_full_report.get("recommendations", []) if fp_full_report else []

    # Merge recommendations
    merged_recs = merge_recommendations(moa_recs, fp_recs, min_confidence=0.6, top_n=top_n)

    # Build embed fields
    fields = []

    # 1. Summary Section
    summary_text = []
    if moa_summary:
        total_outcomes = moa_summary.get("total_outcomes", 0)
        missed_opps = moa_summary.get("missed_opportunities", 0)
        miss_rate = moa_summary.get("miss_rate_pct", 0.0)
        avg_return = moa_summary.get("avg_missed_return_pct", 0.0)
        summary_text.append(f"**MOA Analysis:**")
        summary_text.append(f"• Outcomes Analyzed: **{total_outcomes:,}**")
        summary_text.append(f"• Missed Opportunities: **{missed_opps}** ({miss_rate:.1f}% miss rate)")
        summary_text.append(f"• Avg Missed Return: **+{avg_return:.1f}%**")

    if fp_summary:
        total_fps = fp_summary.get("total_false_positives", 0)
        failure_rate = fp_summary.get("failure_rate_pct", 0.0)
        summary_text.append(f"\n**False Positive Analysis:**")
        summary_text.append(f"• False Positives: **{total_fps}** ({failure_rate:.1f}% failure rate)")

    if summary_text:
        fields.append({
            "name": "📊 Analysis Summary",
            "value": "\n".join(summary_text),
            "inline": False
        })

    # 2. Top Missed Opportunities (Tickers & Returns)
    if moa_top_missed:
        missed_text = []
        for i, opp in enumerate(moa_top_missed[:5], 1):  # Top 5
            ticker = opp.get("ticker", "???")
            return_pct = opp.get("max_return_pct", 0.0)
            keywords = opp.get("keywords", [])
            reason = opp.get("rejection_reason", "unknown")

            # Show first 2 keywords only
            kw_display = ", ".join(keywords[:2]) if keywords else "none"
            if len(keywords) > 2:
                kw_display += f" +{len(keywords)-2} more"

            missed_text.append(
                f"{i}. **${ticker}** → +{return_pct:.1f}%\n"
                f"   Keywords: {kw_display}\n"
                f"   Rejected: {reason.replace('_', ' ').title()}"
            )

        fields.append({
            "name": "🎯 Top 5 Missed Opportunities (Biggest Winners We Skipped)",
            "value": "\n\n".join(missed_text),
            "inline": False
        })

    # 3. Top Keyword Recommendations
    if merged_recs:
        recs_text = []
        for i, rec in enumerate(merged_recs, 1):
            keyword = rec["keyword"]
            confidence = rec["confidence"]
            evidence = rec.get("evidence", {})

            if rec["type"] == "boost":
                weight = rec["weight"]
                occurrences = evidence.get("occurrences", 0)
                success_rate = evidence.get("success_rate", 0.0)
                avg_return = evidence.get("avg_return_pct", 0.0)

                # Get example tickers if available
                examples = evidence.get("examples", [])
                example_tickers = [ex.get("ticker") for ex in examples[:2] if ex.get("ticker")]
                ticker_str = f" | Ex: {', '.join(example_tickers)}" if example_tickers else ""

                recs_text.append(
                    f"{i}. ✅ **{keyword.upper()}** → Weight: {weight:.2f} (Conf: {confidence:.0%})\n"
                    f"   {occurrences} occurrences | {success_rate:.0%} success | +{avg_return:.1f}% avg{ticker_str}"
                )
            else:  # penalty
                penalty = rec["penalty"]
                failure_rate = evidence.get("failure_rate", 0.0)
                avg_return = evidence.get("avg_return", 0.0)
                recs_text.append(
                    f"{i}. ❌ **{keyword.upper()}** → Penalty: {penalty:.2f} (Conf: {confidence:.0%})\n"
                    f"   {failure_rate:.0%} failure rate | {avg_return:+.1f}% avg return"
                )

        fields.append({
            "name": f"💰 Top {min(len(merged_recs), top_n)} Keyword Recommendations (Auto-Applied at Confidence ≥ 60%)",
            "value": "\n\n".join(recs_text[:top_n]),
            "inline": False
        })

    # 4. Flash Catalysts (if available)
    flash_catalysts = {}
    if moa_full_report and "intraday_analysis" in moa_full_report:
        intraday = moa_full_report["intraday_analysis"]
        flash_catalysts = intraday.get("flash_catalysts", {})

    if flash_catalysts and flash_catalysts.get("count", 0) > 0:
        flash_text = []
        count = flash_catalysts.get("count", 0)
        threshold = flash_catalysts.get("threshold_pct", 5.0)
        flash_text.append(f"**{count} flash moves detected** (>{threshold}% in <30min)")

        examples = flash_catalysts.get("examples", [])[:3]  # Top 3
        for ex in examples:
            ticker = ex.get("ticker", "")
            timeframe = ex.get("timeframe", "")
            return_pct = ex.get("return_pct", 0.0)
            keywords = ex.get("keywords", [])
            kw_str = ", ".join(keywords[:2]) if keywords else "N/A"
            flash_text.append(f"• **{ticker}** +{return_pct:.1f}% in {timeframe} | Keywords: {kw_str}")

        fields.append({
            "name": "⚡ Flash Catalysts (15m-30m Moves)",
            "value": "\n".join(flash_text),
            "inline": False
        })

    # 5. Sector Insights (if available)
    sector_analysis = {}
    if moa_full_report and "sector_analysis" in moa_full_report:
        sector_analysis = moa_full_report["sector_analysis"].get("sector_performance", {})

    if sector_analysis:
        # Get top 3 sectors by miss rate
        sorted_sectors = sorted(
            sector_analysis.items(),
            key=lambda x: x[1].get("miss_rate", 0),
            reverse=True
        )[:3]

        sector_text = []
        for sector, stats in sorted_sectors:
            miss_rate = stats.get("miss_rate", 0.0)
            missed = stats.get("missed_opportunities", 0)
            avg_return = stats.get("avg_return_missed", 0.0)
            sector_text.append(
                f"• **{sector}**: {miss_rate:.0%} miss rate | {missed} missed | +{avg_return:.1f}% avg"
            )

        if sector_text:
            fields.append({
                "name": "📈 Hot Sectors (Highest Miss Rates)",
                "value": "\n".join(sector_text),
                "inline": False
            })

    # 6. Report Links
    report_paths = []
    if moa_full_report:
        report_paths.append("• MOA: `data/moa/analysis_report.json`")
    if fp_full_report:
        report_paths.append("• False Positives: `data/false_positives/analysis_report.json`")

    if report_paths:
        fields.append({
            "name": "🔗 Full Reports",
            "value": "\n".join(report_paths),
            "inline": False
        })

    # If no data at all, show helpful message
    if not fields:
        fields.append({
            "name": "ℹ️ No Analysis Data Available",
            "value": (
                "No MOA analysis reports found. This could mean:\n"
                "• MOA nightly analysis hasn't run yet (scheduled for 7:30 PM CST)\n"
                "• No rejected items with price outcomes to analyze\n"
                "• Report files not found in data/moa/ directory"
            ),
            "inline": False
        })

    # Build embed
    embed = {
        "title": "📊 MOA Nightly Analysis Complete",
        "description": "7:30 PM CST | After-Hours Market Analysis",
        "color": 0x2ECC71,  # Green
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "MOA Auto-Learning System | Keyword weights updated automatically"
        }
    }

    return embed


def post_moa_completion_report(
    moa_result: Optional[Dict[str, Any]] = None,
    fp_result: Optional[Dict[str, Any]] = None,
    top_n: int = 10,
) -> bool:
    """Post MOA completion report to Discord admin channel.

    Parameters
    ----------
    moa_result : dict, optional
        MOA analysis results
    fp_result : dict, optional
        False positive analysis results
    top_n : int
        Number of top recommendations to show (default: 10)

    Returns
    -------
    bool
        True if posted successfully, False otherwise
    """
    # Check if feature is enabled
    if os.getenv("FEATURE_MOA_DISCORD_REPORT", "1").strip().lower() not in ("1", "true", "yes", "on"):
        log.debug("moa_discord_report_disabled")
        return False

    # Build embed
    embed = build_moa_completion_embed(moa_result, fp_result, top_n)

    # Try posting via Bot API first (preferred for rich embeds)
    try:
        success = _post_via_bot_api(embed)
        if success:
            log.info("moa_report_posted_via_bot_api")
            return True
    except Exception as e:
        log.warning("moa_bot_api_post_failed err=%s", str(e))

    # Fallback to webhook
    try:
        success = _post_via_webhook(embed)
        if success:
            log.info("moa_report_posted_via_webhook")
            return True
    except Exception as e:
        log.warning("moa_webhook_post_failed err=%s", str(e))

    log.error("moa_report_post_failed")
    return False


def _post_via_bot_api(embed: Dict[str, Any]) -> bool:
    """Post embed to Discord using Bot API (supports buttons).

    Parameters
    ----------
    embed : dict
        Discord embed structure

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    import requests

    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DISCORD_ADMIN_CHANNEL_ID")

    if not bot_token or not channel_id:
        log.debug("bot_api_credentials_missing")
        return False

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }
    payload = {"embeds": [embed]}

    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()

    return response.status_code == 200


def _post_via_webhook(embed: Dict[str, Any]) -> bool:
    """Post embed to Discord using webhook (fallback).

    Parameters
    ----------
    embed : dict
        Discord embed structure

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    import requests

    webhook_url = os.getenv("DISCORD_ADMIN_WEBHOOK")

    if not webhook_url:
        log.debug("webhook_url_missing")
        return False

    payload = {"embeds": [embed]}

    response = requests.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()

    return response.status_code == 204


if __name__ == "__main__":
    # Test with mock data
    mock_moa_result = {
        "summary": {
            "total_outcomes": 523,
            "missed_opportunities": 147,
            "miss_rate_pct": 28.1,
            "avg_missed_return_pct": 18.5,
        },
        "recommendations": [
            {
                "keyword": "fda approval",
                "recommended_weight": 2.37,
                "confidence": 0.9,
                "evidence": {
                    "occurrences": 12,
                    "success_rate": 0.833,
                    "avg_return_pct": 24.5,
                }
            },
            {
                "keyword": "clinical trial",
                "recommended_weight": 1.85,
                "confidence": 0.85,
                "evidence": {
                    "occurrences": 10,
                    "success_rate": 0.80,
                    "avg_return_pct": 18.2,
                }
            }
        ],
        "intraday_analysis": {
            "flash_catalysts": {
                "count": 18,
                "threshold_pct": 5.0,
                "examples": [
                    {"ticker": "ACME", "timeframe": "15m", "return_pct": 12.5, "keywords": ["breakthrough", "partnership"]},
                ]
            }
        },
        "sector_analysis": {
            "sector_performance": {
                "Technology": {"miss_rate": 0.375, "missed_opportunities": 15, "avg_return_missed": 14.2},
                "Healthcare": {"miss_rate": 0.320, "missed_opportunities": 12, "avg_return_missed": 16.8},
            }
        }
    }

    mock_fp_result = {
        "summary": {
            "total_false_positives": 23,
            "failure_rate_pct": 15.3,
        },
        "recommendations": [
            {
                "keyword": "tech contracts",
                "recommended_penalty": -1.2,
                "confidence": 0.75,
                "evidence": {
                    "failure_rate": 0.75,
                    "avg_return": -3.4,
                }
            }
        ]
    }

    # Build and print embed
    embed = build_moa_completion_embed(mock_moa_result, mock_fp_result, top_n=10)
    import json
    print(json.dumps(embed, indent=2))
