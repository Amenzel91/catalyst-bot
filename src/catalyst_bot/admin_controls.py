"""
Interactive Admin Controls for Catalyst Bot
===========================================

Generates nightly admin embeds with backtest results, parameter recommendations,
and interactive buttons for adjusting bot configuration in real-time.

Features:
- Backtest performance summary (win rate, P&L, Sharpe/Sortino)
- Keyword performance analysis (top/worst performers)
- Recommended parameter adjustments based on performance
- Interactive Discord buttons for approval/rejection
- Custom parameter adjustment modals
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .backtest.metrics import BacktestSummary, summarize_returns
from .backtest.simulator import simulate_trades
from .logging_utils import get_logger
from .market import get_last_price_change

log = get_logger("admin_controls")


# ======================== Data Models ========================


@dataclass
class ParameterRecommendation:
    """Represents a recommended parameter change."""
    name: str
    current_value: float | str
    proposed_value: float | str
    reason: str
    impact: str  # "high", "medium", "low"


@dataclass
class KeywordPerformance:
    """Performance metrics for a keyword category."""
    category: str
    hits: int
    misses: int
    neutrals: int
    hit_rate: float
    avg_return: float
    current_weight: float
    proposed_weight: float


@dataclass
class AdminReport:
    """Complete admin report with all metrics and recommendations."""
    date: date_cls
    backtest_summary: BacktestSummary
    keyword_performance: List[KeywordPerformance]
    parameter_recommendations: List[ParameterRecommendation]
    total_alerts: int
    total_revenue: float  # Simulated P&L


# ======================== Configuration ========================


def _get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def _get_current_parameters() -> Dict[str, Any]:
    """Load current bot parameters from environment."""
    return {
        # Sentiment thresholds
        "MIN_SCORE": float(os.getenv("MIN_SCORE", "0") or 0),
        "MIN_SENT_ABS": float(os.getenv("MIN_SENT_ABS", "0") or 0),

        # Alert rate limits
        "ALERTS_MIN_INTERVAL_MS": int(os.getenv("ALERTS_MIN_INTERVAL_MS", "300")),
        "MAX_ALERTS_PER_CYCLE": int(os.getenv("MAX_ALERTS_PER_CYCLE", "40")),

        # Price filters
        "PRICE_CEILING": float(os.getenv("PRICE_CEILING", "10")),
        "PRICE_FLOOR": float(os.getenv("PRICE_FLOOR", "0.1")),

        # Analyzer thresholds
        "ANALYZER_HIT_UP_THRESHOLD_PCT": float(os.getenv("ANALYZER_HIT_UP_THRESHOLD_PCT", "5")),
        "ANALYZER_HIT_DOWN_THRESHOLD_PCT": float(os.getenv("ANALYZER_HIT_DOWN_THRESHOLD_PCT", "-5")),

        # Confidence tiers
        "CONFIDENCE_HIGH": float(os.getenv("CONFIDENCE_HIGH", "0.8")),
        "CONFIDENCE_MODERATE": float(os.getenv("CONFIDENCE_MODERATE", "0.6")),

        # Sentiment component weights
        "SENTIMENT_WEIGHT_LOCAL": float(os.getenv("SENTIMENT_WEIGHT_LOCAL", "0.4")),
        "SENTIMENT_WEIGHT_EXT": float(os.getenv("SENTIMENT_WEIGHT_EXT", "0.3")),
        "SENTIMENT_WEIGHT_SEC": float(os.getenv("SENTIMENT_WEIGHT_SEC", "0.2")),
        "SENTIMENT_WEIGHT_ANALYST": float(os.getenv("SENTIMENT_WEIGHT_ANALYST", "0.05")),
        "SENTIMENT_WEIGHT_EARNINGS": float(os.getenv("SENTIMENT_WEIGHT_EARNINGS", "0.05")),

        # Breakout scanner
        "BREAKOUT_MIN_AVG_VOL": int(os.getenv("BREAKOUT_MIN_AVG_VOL", "300000")),
        "BREAKOUT_MIN_RELVOL": float(os.getenv("BREAKOUT_MIN_RELVOL", "1.5")),
    }


# ======================== Data Loading ========================


def _load_events_for_date(target_date: date_cls) -> List[Dict[str, Any]]:
    """Load events for a specific date from events.jsonl."""
    root = _get_repo_root()
    events_path = root / "data" / "events.jsonl"

    if not events_path.exists():
        return []

    events = []
    try:
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ts_str = str(obj.get("ts") or obj.get("timestamp") or "")
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.date() == target_date:
                    events.append(obj)
            except Exception:
                continue
    except Exception as e:
        log.warning(f"failed_to_load_events date={target_date} err={e}")

    return events


def _load_keyword_weights() -> Dict[str, float]:
    """Load current keyword weights from analyzer data."""
    root = _get_repo_root()
    weights_path = root / "data" / "analyzer" / "keyword_stats.json"

    if not weights_path.exists():
        return {}

    try:
        return json.loads(weights_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ======================== Backtest Analysis ========================


def _compute_backtest_summary(events: List[Dict[str, Any]]) -> BacktestSummary:
    """Compute backtest metrics from historical events."""
    trades = []

    for event in events:
        ticker = str(event.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        # Try to get entry and exit prices
        entry_price = event.get("price")
        if entry_price is None:
            continue

        try:
            # Get current price as exit
            last, prev = get_last_price_change(ticker)
            if last is None:
                continue

            trades.append({
                "symbol": ticker,
                "entry_price": float(entry_price),
                "exit_price": float(last),
                "quantity": 1.0,
                "direction": "long",
            })
        except Exception:
            continue

    # Run backtest simulation
    if not trades:
        return BacktestSummary(
            n=0, hits=0, hit_rate=0.0, avg_return=0.0,
            max_drawdown=0.0, sharpe=0.0, sortino=0.0,
            profit_factor=0.0, avg_win_loss=0.0, trade_count=0
        )

    commission = float(os.getenv("BACKTEST_COMMISSION", "0.0") or 0.0)
    slippage = float(os.getenv("BACKTEST_SLIPPAGE", "0.0") or 0.0)

    try:
        _, summary = simulate_trades(trades, commission=commission, slippage=slippage)
        return summary
    except Exception as e:
        log.warning(f"backtest_simulation_failed err={e}")
        # Fallback: manual summary
        returns = [
            (t["exit_price"] - t["entry_price"]) / t["entry_price"]
            for t in trades
        ]
        return summarize_returns(returns)


# ======================== Keyword Analysis ========================


def _analyze_keyword_performance(
    events: List[Dict[str, Any]],
    current_weights: Dict[str, float]
) -> List[KeywordPerformance]:
    """Analyze performance of each keyword category."""
    from .config import get_settings

    settings = get_settings()
    categories = getattr(settings, "keyword_categories", {})

    # Track stats per category: {category: [hits, misses, neutrals, total_return]}
    stats: Dict[str, List[float]] = {}

    hit_up = float(os.getenv("ANALYZER_HIT_UP_THRESHOLD_PCT", "5"))
    hit_down = float(os.getenv("ANALYZER_HIT_DOWN_THRESHOLD_PCT", "-5"))

    for event in events:
        ticker = str(event.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        # Get event's keyword tags
        cls_data = event.get("cls", {})
        keywords = cls_data.get("keywords", [])

        # Determine which categories matched
        matched_categories = set()
        for cat, cat_keywords in categories.items():
            if any(kw in keywords for kw in cat_keywords):
                matched_categories.add(cat)

        if not matched_categories:
            continue

        # Get price change
        entry_price = event.get("price")
        if entry_price is None:
            continue

        try:
            last, _ = get_last_price_change(ticker)
            if last is None:
                continue

            pct_change = ((last - entry_price) / entry_price) * 100

            # Classify as hit/miss/neutral
            is_hit = pct_change >= hit_up
            is_miss = pct_change <= hit_down

            # Update stats for each matched category
            for cat in matched_categories:
                if cat not in stats:
                    stats[cat] = [0, 0, 0, 0]  # hits, misses, neutrals, total_return

                if is_hit:
                    stats[cat][0] += 1
                elif is_miss:
                    stats[cat][1] += 1
                else:
                    stats[cat][2] += 1

                stats[cat][3] += pct_change

        except Exception:
            continue

    # Build performance objects
    performances = []
    for cat, (hits, misses, neutrals, total_return) in stats.items():
        total = hits + misses + neutrals
        if total == 0:
            continue

        hit_rate = hits / total
        avg_return = total_return / total
        current_weight = current_weights.get(cat, 1.0)

        # Propose weight adjustment based on performance
        # If hit_rate > 60%, increase weight by 20%
        # If hit_rate < 40%, decrease weight by 20%
        # Otherwise keep same
        if hit_rate > 0.6:
            proposed_weight = current_weight * 1.2
        elif hit_rate < 0.4:
            proposed_weight = current_weight * 0.8
        else:
            proposed_weight = current_weight

        performances.append(KeywordPerformance(
            category=cat,
            hits=hits,
            misses=misses,
            neutrals=neutrals,
            hit_rate=hit_rate,
            avg_return=avg_return,
            current_weight=current_weight,
            proposed_weight=round(proposed_weight, 2)
        ))

    # Sort by hit_rate descending
    performances.sort(key=lambda x: x.hit_rate, reverse=True)
    return performances


# ======================== Parameter Recommendations ========================


def _generate_parameter_recommendations(
    backtest: BacktestSummary,
    keyword_perf: List[KeywordPerformance],
    current_params: Dict[str, Any]
) -> List[ParameterRecommendation]:
    """Generate recommended parameter adjustments based on performance."""
    recommendations = []

    # 1. Adjust MIN_SCORE based on hit rate
    if backtest.hit_rate < 0.5 and backtest.n > 10:
        # Low hit rate: increase minimum score to be more selective
        current_min_score = current_params.get("MIN_SCORE", 0)
        if current_min_score < 0.3:
            recommendations.append(ParameterRecommendation(
                name="MIN_SCORE",
                current_value=current_min_score,
                proposed_value=0.3,
                reason=f"Hit rate is low ({backtest.hit_rate:.1%}). Increase selectivity.",
                impact="high"
            ))

    # 2. Adjust PRICE_CEILING based on avg return
    if backtest.avg_return < 0 and backtest.n > 10:
        # Negative returns: consider lowering price ceiling
        current_ceiling = current_params.get("PRICE_CEILING", 10)
        if current_ceiling > 5:
            recommendations.append(ParameterRecommendation(
                name="PRICE_CEILING",
                current_value=current_ceiling,
                proposed_value=5.0,
                reason=f"Avg return is negative ({backtest.avg_return:.2%}). Focus on lower-priced stocks.",
                impact="medium"
            ))

    # 3. Adjust analyzer thresholds based on volatility
    if backtest.max_drawdown > 0.15:  # > 15% drawdown
        current_threshold = current_params.get("ANALYZER_HIT_UP_THRESHOLD_PCT", 5)
        recommendations.append(ParameterRecommendation(
            name="ANALYZER_HIT_UP_THRESHOLD_PCT",
            current_value=current_threshold,
            proposed_value=7.0,
            reason=f"High volatility detected (max DD: {backtest.max_drawdown:.1%}). Raise hit threshold.",
            impact="medium"
        ))

    # 4. Adjust confidence thresholds based on Sharpe ratio
    if backtest.sharpe < 0.5 and backtest.n > 10:
        current_high = current_params.get("CONFIDENCE_HIGH", 0.8)
        recommendations.append(ParameterRecommendation(
            name="CONFIDENCE_HIGH",
            current_value=current_high,
            proposed_value=0.85,
            reason=f"Low Sharpe ratio ({backtest.sharpe:.2f}). Be more conservative with 'Strong Alerts'.",
            impact="high"
        ))

    # 5. Keyword weight recommendations (top 3 changes)
    for kp in keyword_perf[:3]:
        if abs(kp.proposed_weight - kp.current_weight) > 0.1:
            recommendations.append(ParameterRecommendation(
                name=f"KEYWORD_WEIGHT_{kp.category.upper()}",
                current_value=kp.current_weight,
                proposed_value=kp.proposed_weight,
                reason=f"{kp.category}: {kp.hit_rate:.1%} hit rate, {kp.avg_return:+.1f}% avg return",
                impact="medium" if kp.hits + kp.misses > 5 else "low"
            ))

    return recommendations


# ======================== Admin Report Generation ========================


def generate_admin_report(target_date: Optional[date_cls] = None) -> AdminReport:
    """Generate complete admin report for a given date."""
    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    log.info(f"generating_admin_report date={target_date}")

    # Load data
    events = _load_events_for_date(target_date)
    keyword_weights = _load_keyword_weights()
    current_params = _get_current_parameters()

    # Compute metrics
    backtest_summary = _compute_backtest_summary(events)
    keyword_performance = _analyze_keyword_performance(events, keyword_weights)
    recommendations = _generate_parameter_recommendations(
        backtest_summary, keyword_performance, current_params
    )

    # Calculate total P&L (simulated)
    total_revenue = backtest_summary.avg_return * backtest_summary.n * 100  # Assume $100 per trade

    return AdminReport(
        date=target_date,
        backtest_summary=backtest_summary,
        keyword_performance=keyword_performance,
        parameter_recommendations=recommendations,
        total_alerts=len(events),
        total_revenue=total_revenue
    )


# ======================== Discord Embed Building ========================


def _get_performance_comparisons(current_date: date_cls) -> Optional[Dict[str, float]]:
    """Get performance comparisons (yesterday and average) from previous reports.

    Parameters
    ----------
    current_date : date
        Current report date

    Returns
    -------
    dict or None
        {
            "yesterday_hit_rate": float,
            "yesterday_avg_return": float,
            "avg_hit_rate": float,
            "avg_avg_return": float
        }
    """
    try:
        # Load recent reports (past 30 days)
        report_dir = Path("out/admin_reports")
        if not report_dir.exists():
            return None

        # Find yesterday's report
        yesterday = current_date - timedelta(days=1)
        yesterday_path = report_dir / f"report_{yesterday.isoformat()}.json"

        yesterday_data = None
        if yesterday_path.exists():
            with open(yesterday_path, "r") as f:
                yesterday_report = json.load(f)
                yesterday_data = {
                    "yesterday_hit_rate": yesterday_report["backtest"].get("hit_rate", 0),
                    "yesterday_avg_return": yesterday_report["backtest"].get("avg_return", 0)
                }

        # Calculate average from past 30 days
        all_reports = []
        for days_back in range(1, 31):
            past_date = current_date - timedelta(days=days_back)
            past_path = report_dir / f"report_{past_date.isoformat()}.json"

            if past_path.exists():
                try:
                    with open(past_path, "r") as f:
                        past_report = json.load(f)
                        bt = past_report.get("backtest", {})
                        if bt.get("n", 0) > 0:  # Only include days with trades
                            all_reports.append({
                                "hit_rate": bt.get("hit_rate", 0),
                                "avg_return": bt.get("avg_return", 0)
                            })
                except Exception:
                    continue

        avg_data = None
        if all_reports:
            avg_data = {
                "avg_hit_rate": sum(r["hit_rate"] for r in all_reports) / len(all_reports),
                "avg_avg_return": sum(r["avg_return"] for r in all_reports) / len(all_reports)
            }

        # Combine results
        if yesterday_data or avg_data:
            result = {}
            if yesterday_data:
                result.update(yesterday_data)
            if avg_data:
                result.update(avg_data)
            return result

        return None

    except Exception as e:
        log.warning(f"comparison_load_failed err={e}")
        return None


def build_admin_embed(report: AdminReport) -> Dict[str, Any]:
    """Build Discord embed with admin report and interactive buttons."""
    bt = report.backtest_summary

    # Determine embed color based on performance
    if bt.hit_rate >= 0.6:
        color = 0x2ECC71  # Green
    elif bt.hit_rate >= 0.4:
        color = 0xF39C12  # Orange
    else:
        color = 0xE74C3C  # Red

    # Get comparison data (yesterday + average)
    comparisons = _get_performance_comparisons(report.date)

    # Calculate misses
    misses = bt.n - bt.hits

    # Build description with context
    description_parts = []

    # Add zero-data messaging if applicable
    if bt.n == 0:
        description_parts.append("📭 **No signals today**")
        description_parts.append("System is monitoring normally\n")

    # Add date range context
    lookback_days = int(os.getenv("ANALYZER_LOOKBACK_DAYS", "7"))
    date_range = f"Data from: {report.date} (past {lookback_days} days)"
    description_parts.append(date_range)

    description = "\n".join(description_parts) if description_parts else None

    # Build performance field with comparisons
    perf_value = (
        f"**Total Alerts:** {report.total_alerts}\n"
        f"**Trades:** {bt.n}\n"
    )

    # Win rate with comparison
    if comparisons and comparisons.get("yesterday_hit_rate") is not None:
        yesterday_hr = comparisons["yesterday_hit_rate"]
        avg_hr = comparisons.get("avg_hit_rate", 0)
        hr_diff_yesterday = bt.hit_rate - yesterday_hr
        hr_diff_avg = bt.hit_rate - avg_hr

        perf_value += (
            f"**Win Rate:** {bt.hit_rate:.1%} ({bt.hits}W / {misses}L)\n"
            f"  ↳ Yesterday: {hr_diff_yesterday:+.1%} | Avg: {hr_diff_avg:+.1%}\n"
        )
    else:
        perf_value += f"**Win Rate:** {bt.hit_rate:.1%} ({bt.hits}W / {misses}L)\n"

    # Avg return with comparison
    if comparisons and comparisons.get("yesterday_avg_return") is not None:
        yesterday_ar = comparisons["yesterday_avg_return"]
        avg_ar = comparisons.get("avg_avg_return", 0)
        ar_diff_yesterday = bt.avg_return - yesterday_ar
        ar_diff_avg = bt.avg_return - avg_ar

        perf_value += (
            f"**Avg Return:** {bt.avg_return:+.2%}\n"
            f"  ↳ Yesterday: {ar_diff_yesterday:+.2%} | Avg: {ar_diff_avg:+.2%}\n"
        )
    else:
        perf_value += f"**Avg Return:** {bt.avg_return:+.2%}\n"

    perf_value += f"**Simulated P&L:** ${report.total_revenue:+,.2f}"

    # Build fields
    fields = [
        {
            "name": "📊 Daily Performance",
            "value": perf_value,
            "inline": False
        },
        {
            "name": "📈 Risk Metrics",
            "value": (
                f"**Max Drawdown:** {bt.max_drawdown:.2%}\n"
                f"**Sharpe Ratio:** {bt.sharpe:.2f}\n"
                f"**Sortino Ratio:** {bt.sortino:.2f}\n"
                f"**Profit Factor:** {bt.profit_factor:.2f}"
            ),
            "inline": True
        }
    ]

    # Add top keyword performers
    if report.keyword_performance:
        top_keywords = report.keyword_performance[:3]
        kw_text = "\n".join([
            f"**{kp.category}:** {kp.hit_rate:.1%} ({kp.hits}/{kp.hits+kp.misses+kp.neutrals})"
            for kp in top_keywords
        ])
        fields.append({
            "name": "🏆 Top Keywords",
            "value": kw_text or "No data",
            "inline": True
        })

    # Add top 1-2 recommendations preview
    if report.parameter_recommendations:
        high_impact = [r for r in report.parameter_recommendations if r.impact == "high"]
        top_recs = report.parameter_recommendations[:2]  # Top 2 recommendations

        rec_text = ""
        for rec in top_recs:
            impact_emoji = "🔴" if rec.impact == "high" else "🟡" if rec.impact == "medium" else "🟢"
            rec_text += f"{impact_emoji} **{rec.name}:** {rec.current_value} → {rec.proposed_value}\n"
            rec_text += f"  ↳ {rec.reason}\n"

        if len(report.parameter_recommendations) > 2:
            rec_text += f"\n_+{len(report.parameter_recommendations) - 2} more (click View Details)_"

        fields.append({
            "name": "⚙️ Top Recommendations",
            "value": rec_text.strip(),
            "inline": False
        })

    embed = {
        "title": f"🤖 Nightly Admin Report – {report.date}",
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"Click buttons below to review and apply changes • Today at {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    if description:
        embed["description"] = description

    return embed


def build_admin_components(report_id: str) -> List[Dict[str, Any]]:
    """Build interactive Discord buttons for admin controls."""
    return [
        {
            "type": 1,  # Action Row
            "components": [
                {
                    "type": 2,  # Button
                    "style": 1,  # Primary (blurple)
                    "label": "View Details",
                    "custom_id": f"admin_details_{report_id}",
                    "emoji": {"name": "📊"}
                },
                {
                    "type": 2,
                    "style": 3,  # Success (green)
                    "label": "Approve Changes",
                    "custom_id": f"admin_approve_{report_id}",
                    "emoji": {"name": "✅"}
                },
                {
                    "type": 2,
                    "style": 4,  # Danger (red)
                    "label": "Reject Changes",
                    "custom_id": f"admin_reject_{report_id}",
                    "emoji": {"name": "❌"}
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary (gray)
                    "label": "Custom Adjust",
                    "custom_id": f"admin_custom_{report_id}",
                    "emoji": {"name": "⚙️"}
                }
            ]
        }
    ]


# ======================== Report Persistence ========================


def save_admin_report(report: AdminReport) -> Path:
    """Save admin report to disk for later reference."""
    root = _get_repo_root()
    reports_dir = root / "out" / "admin_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / f"report_{report.date}.json"

    data = {
        "date": report.date.isoformat(),
        "backtest": {
            "n": report.backtest_summary.n,
            "hits": report.backtest_summary.hits,
            "hit_rate": report.backtest_summary.hit_rate,
            "avg_return": report.backtest_summary.avg_return,
            "max_drawdown": report.backtest_summary.max_drawdown,
            "sharpe": report.backtest_summary.sharpe,
            "sortino": report.backtest_summary.sortino,
            "profit_factor": report.backtest_summary.profit_factor,
            "avg_win_loss": report.backtest_summary.avg_win_loss,
            "trade_count": report.backtest_summary.trade_count
        },
        "keyword_performance": [
            {
                "category": kp.category,
                "hits": kp.hits,
                "misses": kp.misses,
                "neutrals": kp.neutrals,
                "hit_rate": kp.hit_rate,
                "avg_return": kp.avg_return,
                "current_weight": kp.current_weight,
                "proposed_weight": kp.proposed_weight
            }
            for kp in report.keyword_performance
        ],
        "recommendations": [
            {
                "name": rec.name,
                "current_value": rec.current_value,
                "proposed_value": rec.proposed_value,
                "reason": rec.reason,
                "impact": rec.impact
            }
            for rec in report.parameter_recommendations
        ],
        "total_alerts": report.total_alerts,
        "total_revenue": report.total_revenue
    }

    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info(f"saved_admin_report path={report_path}")
    return report_path


def load_admin_report(report_id: str) -> Optional[AdminReport]:
    """Load a saved admin report by ID (date)."""
    root = _get_repo_root()
    report_path = root / "out" / "admin_reports" / f"report_{report_id}.json"

    if not report_path.exists():
        return None

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))

        backtest_summary = BacktestSummary(
            n=data["backtest"]["n"],
            hits=data["backtest"]["hits"],
            hit_rate=data["backtest"]["hit_rate"],
            avg_return=data["backtest"]["avg_return"],
            max_drawdown=data["backtest"]["max_drawdown"],
            sharpe=data["backtest"]["sharpe"],
            sortino=data["backtest"]["sortino"],
            profit_factor=data["backtest"]["profit_factor"],
            avg_win_loss=data["backtest"].get("avg_win_loss", 0.0),
            trade_count=data["backtest"].get("trade_count", data["backtest"]["n"])
        )

        keyword_performance = [
            KeywordPerformance(**kp)
            for kp in data["keyword_performance"]
        ]

        recommendations = [
            ParameterRecommendation(**rec)
            for rec in data["recommendations"]
        ]

        return AdminReport(
            date=datetime.fromisoformat(data["date"]).date(),
            backtest_summary=backtest_summary,
            keyword_performance=keyword_performance,
            parameter_recommendations=recommendations,
            total_alerts=data["total_alerts"],
            total_revenue=data["total_revenue"]
        )
    except Exception as e:
        log.warning(f"failed_to_load_report id={report_id} err={e}")
        return None
