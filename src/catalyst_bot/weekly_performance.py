"""
Weekly Performance Reporter
============================

Generates weekly performance summaries analyzing:
- Best/worst catalyst types (keywords)
- Sector performance trends
- Parameter effectiveness over time
- Alert accuracy metrics

Sends comprehensive reports every Sunday at configured time.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, date as date_cls, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logging_utils import get_logger

log = get_logger("weekly_performance")


def _get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def analyze_weekly_performance(lookback_days: int = 7) -> Dict[str, Any]:
    """
    Analyze performance over the past week.

    Parameters
    ----------
    lookback_days : int
        Number of days to analyze (default: 7)

    Returns
    -------
    dict
        Weekly performance statistics
    """
    try:
        root = _get_repo_root()
        events_path = root / "data" / "events.jsonl"

        if not events_path.exists():
            log.warning("events_file_not_found")
            return {}

        # Load events from the past week
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        events = []

        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    ts_str = event.get("ts") or event.get("timestamp") or ""
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                    if ts >= cutoff:
                        events.append(event)
                except Exception:
                    continue

        if not events:
            log.info("no_weekly_events found=0")
            return {"total_alerts": 0, "period_days": lookback_days}

        # Analyze by keyword category
        keyword_stats = analyze_keyword_performance(events)

        # Analyze by confidence tier
        confidence_stats = analyze_confidence_tiers(events)

        # Analyze by price range
        price_stats = analyze_price_ranges(events)

        # Calculate overall metrics
        from .market import get_last_price_change

        total_profit = 0
        total_trades = 0
        winning_trades = 0

        for event in events:
            ticker = event.get("ticker")
            entry_price = event.get("price")

            if not ticker or not entry_price:
                continue

            try:
                last, _ = get_last_price_change(ticker)
                if last:
                    pct_return = ((last - entry_price) / entry_price) * 100
                    total_profit += pct_return
                    total_trades += 1
                    if pct_return > 5:  # Default hit threshold
                        winning_trades += 1
            except Exception:
                continue

        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0
        avg_return = (total_profit / total_trades) if total_trades > 0 else 0

        return {
            "period_days": lookback_days,
            "total_alerts": len(events),
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "total_profit": total_profit,
            "keyword_stats": keyword_stats,
            "confidence_stats": confidence_stats,
            "price_stats": price_stats,
        }

    except Exception as e:
        log.error(f"weekly_analysis_failed err={e}")
        return {}


def analyze_keyword_performance(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Analyze performance by keyword category."""
    from .market import get_last_price_change

    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"hits": 0, "misses": 0, "total_return": 0.0, "count": 0}
    )

    for event in events:
        ticker = event.get("ticker")
        entry_price = event.get("price")
        keywords = event.get("cls", {}).get("keywords", [])

        if not ticker or not entry_price or not keywords:
            continue

        try:
            last, _ = get_last_price_change(ticker)
            if not last:
                continue

            pct_return = ((last - entry_price) / entry_price) * 100

            # Update stats for each keyword
            for keyword in keywords:
                stats[keyword]["count"] += 1
                stats[keyword]["total_return"] += pct_return

                if pct_return > 5:  # Hit threshold
                    stats[keyword]["hits"] += 1
                elif pct_return < -5:  # Miss threshold
                    stats[keyword]["misses"] += 1

        except Exception:
            continue

    # Build sorted list
    result = []
    for keyword, data in stats.items():
        if data["count"] == 0:
            continue

        hit_rate = data["hits"] / data["count"]
        avg_return = data["total_return"] / data["count"]

        result.append(
            {
                "keyword": keyword,
                "count": data["count"],
                "hit_rate": hit_rate,
                "avg_return": avg_return,
                "hits": data["hits"],
                "misses": data["misses"],
            }
        )

    # Sort by hit rate descending
    result.sort(key=lambda x: x["hit_rate"], reverse=True)
    return result


def analyze_confidence_tiers(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Analyze performance by confidence tier."""
    from .market import get_last_price_change

    tiers = {"high": [], "moderate": [], "low": []}

    for event in events:
        ticker = event.get("ticker")
        entry_price = event.get("price")
        confidence = event.get("cls", {}).get("confidence", 0)

        if not ticker or not entry_price:
            continue

        try:
            last, _ = get_last_price_change(ticker)
            if not last:
                continue

            pct_return = ((last - entry_price) / entry_price) * 100

            # Classify by tier
            if confidence >= 0.8:
                tier = "high"
            elif confidence >= 0.6:
                tier = "moderate"
            else:
                tier = "low"

            tiers[tier].append(pct_return)

        except Exception:
            continue

    # Calculate stats for each tier
    result = {}
    for tier, returns in tiers.items():
        if not returns:
            continue

        hits = sum(1 for r in returns if r > 5)
        misses = sum(1 for r in returns if r < -5)

        result[tier] = {
            "count": len(returns),
            "hit_rate": hits / len(returns),
            "avg_return": sum(returns) / len(returns),
            "hits": hits,
            "misses": misses,
        }

    return result


def analyze_price_ranges(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Analyze performance by price range."""
    from .market import get_last_price_change

    ranges = {
        "under_1": [],  # < $1
        "1_to_3": [],  # $1-3
        "3_to_5": [],  # $3-5
        "5_to_10": [],  # $5-10
        "over_10": [],  # > $10
    }

    for event in events:
        ticker = event.get("ticker")
        entry_price = event.get("price")

        if not ticker or not entry_price:
            continue

        try:
            last, _ = get_last_price_change(ticker)
            if not last:
                continue

            pct_return = ((last - entry_price) / entry_price) * 100

            # Classify by price range
            if entry_price < 1:
                range_key = "under_1"
            elif entry_price < 3:
                range_key = "1_to_3"
            elif entry_price < 5:
                range_key = "3_to_5"
            elif entry_price < 10:
                range_key = "5_to_10"
            else:
                range_key = "over_10"

            ranges[range_key].append(pct_return)

        except Exception:
            continue

    # Calculate stats for each range
    result = {}
    for range_key, returns in ranges.items():
        if not returns:
            continue

        hits = sum(1 for r in returns if r > 5)
        misses = sum(1 for r in returns if r < -5)

        result[range_key] = {
            "count": len(returns),
            "hit_rate": hits / len(returns),
            "avg_return": sum(returns) / len(returns),
            "hits": hits,
            "misses": misses,
        }

    return result


def build_weekly_report_embed(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Build Discord embed for weekly performance report."""
    if not stats or stats.get("total_alerts", 0) == 0:
        return {
            "title": "Weekly Performance Report",
            "description": "No alerts fired this week.",
            "color": 0x95A5A6,  # Gray
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Determine color based on win rate
    win_rate = stats.get("win_rate", 0)
    if win_rate >= 0.6:
        color = 0x2ECC71  # Green
    elif win_rate >= 0.4:
        color = 0xF39C12  # Orange
    else:
        color = 0xE74C3C  # Red

    fields = []

    # Overall performance
    fields.append(
        {
            "name": "📊 Weekly Summary",
            "value": (
                f"**Total Alerts:** {stats['total_alerts']}\n"
                f"**Trades Analyzed:** {stats['total_trades']}\n"
                f"**Win Rate:** {stats['win_rate']:.1%}\n"
                f"**Avg Return:** {stats['avg_return']:+.2f}%\n"
                f"**Total Profit:** {stats['total_profit']:+.1f}%"
            ),
            "inline": False,
        }
    )

    # Best keywords
    keyword_stats = stats.get("keyword_stats", [])
    if keyword_stats:
        best_keywords = keyword_stats[:3]
        worst_keywords = keyword_stats[-3:]

        best_text = "\n".join(
            [
                f"**{kw['keyword']}:** {kw['hit_rate']:.0%} ({kw['hits']}/{kw['count']}), {kw['avg_return']:+.1f}%"
                for kw in best_keywords
            ]
        )

        fields.append({"name": "🏆 Top Catalysts", "value": best_text, "inline": True})

        worst_text = "\n".join(
            [
                f"**{kw['keyword']}:** {kw['hit_rate']:.0%} ({kw['hits']}/{kw['count']}), {kw['avg_return']:+.1f}%"
                for kw in worst_keywords
            ]
        )

        fields.append(
            {"name": "⚠️ Underperforming", "value": worst_text, "inline": True}
        )

    # Confidence tiers
    confidence_stats = stats.get("confidence_stats", {})
    if confidence_stats:
        conf_text = ""
        for tier in ["high", "moderate", "low"]:
            if tier in confidence_stats:
                data = confidence_stats[tier]
                conf_text += (
                    f"**{tier.title()}:** {data['hit_rate']:.0%} "
                    f"({data['hits']}/{data['count']}), "
                    f"{data['avg_return']:+.1f}%\n"
                )

        if conf_text:
            fields.append(
                {"name": "💎 Confidence Tiers", "value": conf_text, "inline": True}
            )

    # Price ranges
    price_stats = stats.get("price_stats", {})
    if price_stats:
        price_labels = {
            "under_1": "< $1",
            "1_to_3": "$1-3",
            "3_to_5": "$3-5",
            "5_to_10": "$5-10",
            "over_10": "> $10",
        }

        price_text = ""
        for range_key in ["under_1", "1_to_3", "3_to_5", "5_to_10", "over_10"]:
            if range_key in price_stats:
                data = price_stats[range_key]
                label = price_labels[range_key]
                price_text += (
                    f"**{label}:** {data['hit_rate']:.0%} "
                    f"({data['hits']}/{data['count']}), "
                    f"{data['avg_return']:+.1f}%\n"
                )

        if price_text:
            fields.append(
                {"name": "💰 Price Ranges", "value": price_text, "inline": True}
            )

    embed = {
        "title": f"📈 Weekly Performance Report ({stats['period_days']} days)",
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"Analysis Period: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} (past {stats['period_days']} days)"
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return embed


def post_weekly_report() -> bool:
    """Post weekly performance report to Discord."""
    try:
        # Check if enabled
        if not os.getenv("FEATURE_WEEKLY_REPORTS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            log.info("weekly_reports_disabled")
            return False

        log.info("generating_weekly_report")

        # Analyze performance
        stats = analyze_weekly_performance(lookback_days=7)

        # Build embed
        embed = build_weekly_report_embed(stats)

        # Post to Discord
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DISCORD_ADMIN_CHANNEL_ID")

        if bot_token and channel_id:
            import requests

            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            headers = {
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json",
            }
            payload = {"embeds": [embed]}

            response = requests.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code in (200, 201):
                log.info("weekly_report_posted")
                return True
            else:
                log.warning(f"weekly_report_post_failed status={response.status_code}")
                return False
        else:
            log.warning("discord_credentials_missing")
            return False

    except Exception as e:
        log.error(f"weekly_report_failed err={e}")
        return False


def should_send_weekly_report(now: datetime) -> bool:
    """
    Determine if it's time to send the weekly report.

    Weekly reports are sent every Sunday at the configured time.
    """
    # Normalize to UTC
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Check if it's Sunday (weekday == 6)
    if now.weekday() != 6:
        return False

    # Get schedule from environment (default: same as admin reports)
    try:
        target_hour = int(os.getenv("WEEKLY_REPORT_UTC_HOUR", "21"))
        target_minute = int(os.getenv("WEEKLY_REPORT_UTC_MINUTE", "0"))
    except ValueError:
        target_hour, target_minute = 21, 0

    # Within 5-minute window of target time
    target_time = now.replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )
    time_diff = abs((now - target_time).total_seconds())

    # Send if within 5 minutes of target time
    return time_diff <= 300  # 5 minutes


def send_weekly_report_if_scheduled(now: Optional[datetime] = None) -> bool:
    """
    Send weekly report if it's the scheduled time.

    Parameters
    ----------
    now : datetime, optional
        Current time. Defaults to datetime.now(timezone.utc).

    Returns
    -------
    bool
        True if report was sent
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if should_send_weekly_report(now):
        log.info("triggering_weekly_report")
        return post_weekly_report()

    return False
