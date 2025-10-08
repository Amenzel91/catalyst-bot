"""
Weekly Performance Report
=========================

Generates comprehensive weekly performance reports with statistics,
best/worst performers, and recommendations.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..logging_utils import get_logger
from .database import _get_connection
from .weight_adjuster import analyze_keyword_performance

log = get_logger("feedback.weekly_report")


def generate_weekly_report(
    target_date: Optional[datetime] = None,
) -> Dict:
    """
    Generate comprehensive weekly performance report.

    Parameters
    ----------
    target_date : datetime, optional
        End date for the report. Defaults to now.

    Returns
    -------
    dict
        Report data including stats, top performers, recommendations
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc)

    # Calculate date range (last 7 days)
    end_date = target_date
    start_date = end_date - timedelta(days=7)

    log.info(
        "generating_weekly_report start=%s end=%s",
        start_date.date(),
        end_date.date(),
    )

    report = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Get overall statistics
    report["overview"] = _get_overview_stats(start_date, end_date)

    # Get best/worst catalyst types
    report["catalyst_performance"] = _get_catalyst_performance(start_date, end_date)

    # Get best/worst tickers
    report["ticker_performance"] = _get_ticker_performance(start_date, end_date)

    # Get daily breakdown
    report["daily_stats"] = _get_daily_stats(start_date, end_date)

    # Get keyword recommendations
    report["keyword_recommendations"] = analyze_keyword_performance(lookback_days=7)

    log.info("weekly_report_generated")

    return report


def _get_overview_stats(start_date: datetime, end_date: datetime) -> Dict:
    """Get overall performance statistics."""
    conn = _get_connection()
    try:
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_alerts,
                COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins,
                COUNT(CASE WHEN outcome = 'loss' THEN 1 END) as losses,
                COUNT(CASE WHEN outcome = 'neutral' THEN 1 END) as neutral,
                AVG(CASE WHEN outcome IS NOT NULL THEN outcome_score END) as avg_score,
                AVG(CASE WHEN price_change_1d IS NOT NULL THEN price_change_1d END) as avg_return,
                MAX(price_change_1d) as best_return,
                MIN(price_change_1d) as worst_return
            FROM alert_performance
            WHERE posted_at >= ? AND posted_at < ?
            """,
            (start_ts, end_ts),
        )

        row = cursor.fetchone()
        stats = dict(row) if row else {}

        # Calculate win rate
        total_scored = (
            (stats.get("wins", 0) or 0)
            + (stats.get("losses", 0) or 0)
            + (stats.get("neutral", 0) or 0)
        )
        if total_scored > 0:
            stats["win_rate"] = (stats.get("wins", 0) or 0) / total_scored
        else:
            stats["win_rate"] = 0.0

        return stats

    except Exception as e:
        log.error("get_overview_stats_failed error=%s", str(e))
        return {}
    finally:
        conn.close()


def _get_catalyst_performance(start_date: datetime, end_date: datetime) -> Dict:
    """Get performance breakdown by catalyst type."""
    conn = _get_connection()
    try:
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                catalyst_type,
                COUNT(*) as alert_count,
                COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins,
                COUNT(CASE WHEN outcome = 'loss' THEN 1 END) as losses,
                AVG(CASE WHEN outcome IS NOT NULL THEN outcome_score END) as avg_score,
                AVG(CASE WHEN price_change_1d IS NOT NULL THEN price_change_1d END) as avg_return
            FROM alert_performance
            WHERE posted_at >= ? AND posted_at < ?
            AND outcome IS NOT NULL
            GROUP BY catalyst_type
            HAVING COUNT(*) >= 3
            ORDER BY avg_score DESC
            """,
            (start_ts, end_ts),
        )

        rows = cursor.fetchall()

        results = []
        for row in rows:
            data = dict(row)
            # Calculate win rate
            total = data["wins"] + data["losses"]
            data["win_rate"] = data["wins"] / total if total > 0 else 0.0
            results.append(data)

        # Split into best and worst
        best = results[:5] if len(results) > 0 else []
        worst = results[-3:] if len(results) > 3 else []

        return {"best": best, "worst": worst}

    except Exception as e:
        log.error("get_catalyst_performance_failed error=%s", str(e))
        return {"best": [], "worst": []}
    finally:
        conn.close()


def _get_ticker_performance(start_date: datetime, end_date: datetime) -> Dict:
    """Get performance breakdown by ticker."""
    conn = _get_connection()
    try:
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                ticker,
                COUNT(*) as alert_count,
                AVG(CASE WHEN price_change_1d IS NOT NULL THEN price_change_1d END) as avg_return,
                MAX(price_change_1d) as best_return,
                MIN(price_change_1d) as worst_return
            FROM alert_performance
            WHERE posted_at >= ? AND posted_at < ?
            AND price_change_1d IS NOT NULL
            GROUP BY ticker
            HAVING COUNT(*) >= 2
            ORDER BY avg_return DESC
            """,
            (start_ts, end_ts),
        )

        rows = cursor.fetchall()
        results = [dict(row) for row in rows]

        # Split into top gainers and losers
        top_gainers = results[:10]
        top_losers = sorted(results, key=lambda x: x["avg_return"])[:10]

        return {"top_gainers": top_gainers, "top_losers": top_losers}

    except Exception as e:
        log.error("get_ticker_performance_failed error=%s", str(e))
        return {"top_gainers": [], "top_losers": []}
    finally:
        conn.close()


def _get_daily_stats(start_date: datetime, end_date: datetime) -> List[Dict]:
    """Get statistics broken down by day."""
    conn = _get_connection()
    try:
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                DATE(posted_at, 'unixepoch') as date,
                COUNT(*) as alert_count,
                COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins,
                AVG(CASE WHEN price_change_1d IS NOT NULL THEN price_change_1d END) as avg_return
            FROM alert_performance
            WHERE posted_at >= ? AND posted_at < ?
            GROUP BY DATE(posted_at, 'unixepoch')
            ORDER BY date
            """,
            (start_ts, end_ts),
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    except Exception as e:
        log.error("get_daily_stats_failed error=%s", str(e))
        return []
    finally:
        conn.close()


def send_weekly_report_if_scheduled() -> bool:
    """
    Send weekly report if it's the scheduled day/time.

    Checks FEEDBACK_WEEKLY_REPORT_DAY and FEEDBACK_WEEKLY_REPORT_HOUR
    from environment.

    Returns
    -------
    bool
        True if report was sent
    """
    # Check if weekly reports are enabled
    if not os.getenv("FEEDBACK_WEEKLY_REPORT", "0").strip() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False

    now = datetime.now(timezone.utc)

    # Get configured day and hour (default: Sunday at 23:00 UTC)
    try:
        target_day = int(os.getenv("FEEDBACK_WEEKLY_REPORT_DAY", "6"))  # 6 = Sunday
        target_hour = int(os.getenv("FEEDBACK_WEEKLY_REPORT_HOUR", "23"))
    except Exception:
        target_day = 6
        target_hour = 23

    # Check if it's the right day and hour
    if now.weekday() != target_day or now.hour != target_hour:
        return False

    log.info("weekly_report_scheduled_time_reached")

    # Generate and send report
    report = generate_weekly_report()
    return _send_report_to_discord(report)


def _send_report_to_discord(report: Dict) -> bool:
    """Send weekly report to Discord admin channel."""
    try:
        from ..config import get_settings

        settings = get_settings()
        admin_webhook = settings.admin_webhook_url

        if not admin_webhook:
            log.warning("no_admin_webhook_for_weekly_report")
            return False

        # Build embed
        embed = _build_report_embed(report)

        import requests

        payload = {
            "username": "Weekly Performance Report",
            "embeds": [embed],
        }

        response = requests.post(admin_webhook, json=payload, timeout=10)
        response.raise_for_status()

        log.info("weekly_report_sent_to_discord")
        return True

    except Exception as e:
        log.error("send_weekly_report_failed error=%s", str(e))
        return False


def _build_report_embed(report: Dict) -> Dict:
    """Build Discord embed for weekly report."""
    overview = report.get("overview", {})
    catalyst_perf = report.get("catalyst_performance", {})
    ticker_perf = report.get("ticker_performance", {})
    daily_stats = report.get("daily_stats", [])

    # Build overview description
    total_alerts = overview.get("total_alerts", 0)
    win_rate = overview.get("win_rate", 0.0)
    avg_return = overview.get("avg_return", 0.0)
    best_return = overview.get("best_return", 0.0)
    worst_return = overview.get("worst_return", 0.0)

    # Find best and worst days
    best_day = None
    worst_day = None
    if daily_stats:
        best_day = max(daily_stats, key=lambda x: x.get("avg_return", 0.0))
        worst_day = min(daily_stats, key=lambda x: x.get("avg_return", 0.0))

    start_date = datetime.fromisoformat(report["start_date"]).strftime("%b %d")
    end_date = datetime.fromisoformat(report["end_date"]).strftime("%b %d")

    description = f"""
**Overview**
• Alerts Posted: {total_alerts}
• Win Rate: {win_rate:.1%}
• Avg Return: {avg_return:+.2f}%
• Best Return: {best_return:+.2f}%
• Worst Return: {worst_return:+.2f}%
"""

    if best_day and worst_day:
        description += f"""
• Best Day: {best_day.get('date')} ({best_day.get('avg_return', 0):+.1f}%)
• Worst Day: {worst_day.get('date')} ({worst_day.get('avg_return', 0):+.1f}%)
"""

    fields = []

    # Best catalyst types
    best_catalysts = catalyst_perf.get("best", [])
    if best_catalysts:
        catalyst_lines = []
        for i, cat in enumerate(best_catalysts[:3], 1):
            catalyst_lines.append(
                f"{i}. **{cat['catalyst_type']}**: "
                f"{cat['win_rate']:.0%} win rate, {cat['avg_return']:+.1f}% avg"
            )

        fields.append(
            {
                "name": "🏆 Best Catalyst Types",
                "value": "\n".join(catalyst_lines),
                "inline": False,
            }
        )

    # Worst catalyst types
    worst_catalysts = catalyst_perf.get("worst", [])
    if worst_catalysts:
        catalyst_lines = []
        for i, cat in enumerate(worst_catalysts[:3], 1):
            catalyst_lines.append(
                f"{i}. **{cat['catalyst_type']}**: "
                f"{cat['win_rate']:.0%} win rate, {cat['avg_return']:+.1f}% avg"
            )

        fields.append(
            {
                "name": "⚠️ Worst Catalyst Types",
                "value": "\n".join(catalyst_lines),
                "inline": False,
            }
        )

    # Top gainers
    top_gainers = ticker_perf.get("top_gainers", [])
    if top_gainers:
        gainer_lines = []
        for ticker_data in top_gainers[:5]:
            gainer_lines.append(
                f"**{ticker_data['ticker']}**: {ticker_data['avg_return']:+.1f}% "
                f"({ticker_data['alert_count']} alerts)"
            )

        fields.append(
            {
                "name": "📈 Top Gaining Tickers",
                "value": "\n".join(gainer_lines),
                "inline": True,
            }
        )

    # Top losers
    top_losers = ticker_perf.get("top_losers", [])
    if top_losers:
        loser_lines = []
        for ticker_data in top_losers[:5]:
            loser_lines.append(
                f"**{ticker_data['ticker']}**: {ticker_data['avg_return']:+.1f}% "
                f"({ticker_data['alert_count']} alerts)"
            )

        fields.append(
            {
                "name": "📉 Top Losing Tickers",
                "value": "\n".join(loser_lines),
                "inline": True,
            }
        )

    # Keyword recommendations summary
    keyword_recs = report.get("keyword_recommendations", {})
    if keyword_recs:
        # Count positive/negative adjustments
        positive_adj = sum(
            1
            for kw_data in keyword_recs.values()
            if kw_data["recommended_weight"] > kw_data["current_weight"]
        )
        negative_adj = sum(
            1
            for kw_data in keyword_recs.values()
            if kw_data["recommended_weight"] < kw_data["current_weight"]
        )

        if positive_adj > 0 or negative_adj > 0:
            rec_text = f"• Increase weight: {positive_adj} keywords\n"
            rec_text += f"• Decrease weight: {negative_adj} keywords\n"
            rec_text += "\n*See separate keyword recommendations message*"

            fields.append(
                {
                    "name": "💡 Keyword Recommendations",
                    "value": rec_text,
                    "inline": False,
                }
            )

    # Determine color based on overall performance
    if win_rate > 0.55:
        color = 0x2ECC71  # Green
    elif win_rate < 0.45:
        color = 0xE74C3C  # Red
    else:
        color = 0x95A5A6  # Gray

    embed = {
        "title": f"📊 Weekly Performance Report ({start_date} - {end_date})",
        "description": description.strip(),
        "color": color,
        "fields": fields,
        "footer": {
            "text": "Catalyst-Bot Feedback Loop",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return embed
