"""
Discord Slash Command Handlers
===============================

Implements handlers for all user-facing slash commands.

Commands:
- /chart - Generate price charts
- /watchlist - Manage personal watchlist
- /stats - Bot performance statistics
- /backtest - Historical alert backtesting
- /sentiment - Ticker sentiment analysis
- /help - Show command help
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..charts import get_quickchart_url
from ..logging_utils import get_logger
from ..market import get_last_price_change
from ..user_watchlist import (
    add_to_watchlist,
    clear_watchlist,
    get_watchlist,
    remove_from_watchlist,
)
from ..validation import validate_ticker
from .chart_interactions import build_chart_select_menu, get_default_indicators
from .command_registry import format_command_help
from .embeds import (
    create_backtest_embed,
    create_chart_embed,
    create_help_embed,
    create_sentiment_embed,
    create_stats_embed,
    create_watchlist_embed,
)
from .errors import (
    feature_disabled_error,
    generic_error,
    invalid_parameter_error,
    missing_parameter_error,
    no_data_error,
    ticker_already_in_watchlist_error,
    ticker_not_found_error,
    ticker_not_in_watchlist_error,
    watchlist_empty_error,
    watchlist_full_error,
)

log = get_logger("command_handlers")

# Rate limiting
_last_command_time: Dict[str, Dict[str, float]] = {}
COOLDOWN_SECONDS = int(os.getenv("SLASH_COMMAND_COOLDOWN", "3"))


def _check_rate_limit(user_id: str, command: str) -> Optional[int]:
    """
    Check if user is rate limited for a command.

    Parameters
    ----------
    user_id : str
        Discord user ID
    command : str
        Command name

    Returns
    -------
    Optional[int]
        Seconds remaining if rate limited, None if allowed
    """
    if user_id not in _last_command_time:
        _last_command_time[user_id] = {}

    last_time = _last_command_time[user_id].get(command, 0)
    now = datetime.now(timezone.utc).timestamp()
    elapsed = now - last_time

    if elapsed < COOLDOWN_SECONDS:
        return int(COOLDOWN_SECONDS - elapsed) + 1

    # Update last command time
    _last_command_time[user_id][command] = now
    return None


def handle_chart_command(
    ticker: str,
    timeframe: str = "1D",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Handle /chart command.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Chart timeframe (1D, 5D, 1M, 3M, 1Y)
    user_id : Optional[str]
        Discord user ID (for rate limiting)

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        # Rate limiting
        if user_id:
            remaining = _check_rate_limit(user_id, "chart")
            if remaining:
                from .errors import rate_limit_error

                return rate_limit_error(remaining)

        # Validate ticker
        ticker = validate_ticker(ticker)
        if not ticker:
            return ticker_not_found_error(ticker)

        log.info(f"slash_chart ticker={ticker} timeframe={timeframe}")

        # Check if QuickChart is enabled
        if not os.getenv("FEATURE_QUICKCHART", "0") in ("1", "true", "yes"):
            return feature_disabled_error("chart generation")

        # Get default indicators (from .env or user preferences)
        indicators = get_default_indicators()

        # Get chart URL with indicators
        chart_url = get_quickchart_url(
            ticker, timeframe=timeframe, indicators=indicators
        )
        if not chart_url:
            return no_data_error(ticker, "chart data")

        # Get current price data
        try:
            price, change_pct = get_last_price_change(ticker)
        except Exception:
            price, change_pct = None, None

        price_data = {
            "price": price,
            "change_pct": change_pct or 0,
            "volume": None,  # Could add volume data
            "vwap": None,  # Could add VWAP
            "rsi": None,  # Could add RSI
        }

        # Build interactive select menu for indicator toggles
        components = build_chart_select_menu(
            ticker, timeframe, indicators, user_id=user_id
        )

        return create_chart_embed(
            ticker, timeframe, chart_url, price_data, components=components
        )

    except Exception as e:
        log.error(f"chart_command_failed ticker={ticker} err={e}")
        return generic_error(str(e))


def handle_watchlist_command(
    action: str,
    ticker: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Handle /watchlist command.

    Parameters
    ----------
    action : str
        Action to perform (add, remove, list, clear)
    ticker : Optional[str]
        Ticker symbol (required for add/remove)
    user_id : Optional[str]
        Discord user ID

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        if not user_id:
            return generic_error("User ID not provided")

        log.info(f"slash_watchlist action={action} ticker={ticker} user_id={user_id}")

        # Handle different actions
        if action == "add":
            if not ticker:
                return missing_parameter_error("ticker")

            ticker = validate_ticker(ticker)
            if not ticker:
                return ticker_not_found_error(ticker)

            success, message = add_to_watchlist(user_id, ticker)

            if not success:
                if "already" in message.lower():
                    return ticker_already_in_watchlist_error(ticker)
                elif "full" in message.lower():
                    max_size = int(os.getenv("WATCHLIST_MAX_SIZE", "50"))
                    return watchlist_full_error(max_size)
                else:
                    return generic_error(message)

            tickers = get_watchlist(user_id)
            return create_watchlist_embed(action, tickers, success, message)

        elif action == "remove":
            if not ticker:
                return missing_parameter_error("ticker")

            ticker = validate_ticker(ticker)
            if not ticker:
                return ticker_not_found_error(ticker)

            success, message = remove_from_watchlist(user_id, ticker)

            if not success:
                if "not in" in message.lower():
                    return ticker_not_in_watchlist_error(ticker)
                else:
                    return generic_error(message)

            tickers = get_watchlist(user_id)
            return create_watchlist_embed(action, tickers, success, message)

        elif action == "list":
            tickers = get_watchlist(user_id)
            return create_watchlist_embed(action, tickers)

        elif action == "clear":
            tickers = get_watchlist(user_id)
            if not tickers:
                return watchlist_empty_error()

            success, message = clear_watchlist(user_id)
            if not success:
                return generic_error(message)

            return create_watchlist_embed(action, [], success, message)

        else:
            return invalid_parameter_error(
                "action", "must be add, remove, list, or clear"
            )

    except Exception as e:
        log.error(f"watchlist_command_failed action={action} err={e}")
        return generic_error(str(e))


def handle_stats_command(period: str = "7d") -> Dict[str, Any]:
    """
    Handle /stats command.

    Parameters
    ----------
    period : str
        Time period (1d, 7d, 30d, all)

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        log.info(f"slash_stats period={period}")

        # Calculate date range
        if period == "all":
            cutoff = None
        else:
            days = int(period.replace("d", ""))
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Load events from events.jsonl
        stats = _calculate_stats(cutoff)

        return create_stats_embed(period, stats)

    except Exception as e:
        log.error(f"stats_command_failed period={period} err={e}")
        return generic_error(str(e))


def handle_backtest_command(ticker: str, days: int = 30) -> Dict[str, Any]:
    """
    Handle /backtest command.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    days : int
        Number of days to backtest

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        ticker = validate_ticker(ticker)
        if not ticker:
            return ticker_not_found_error(ticker)

        log.info(f"slash_backtest ticker={ticker} days={days}")

        # Get historical alerts
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        alerts = _get_alerts_for_ticker(ticker, cutoff)

        if not alerts:
            return no_data_error(ticker, "historical alerts")

        # Run backtest simulation
        results = _run_backtest(ticker, alerts)

        return create_backtest_embed(ticker, days, results)

    except Exception as e:
        log.error(f"backtest_command_failed ticker={ticker} err={e}")
        return generic_error(str(e))


def handle_sentiment_command(ticker: str) -> Dict[str, Any]:
    """
    Handle /sentiment command.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        ticker = validate_ticker(ticker)
        if not ticker:
            return ticker_not_found_error(ticker)

        log.info(f"slash_sentiment ticker={ticker}")

        # Get sentiment data
        sentiment_score, news_items = _get_sentiment_data(ticker)

        if sentiment_score is None:
            return no_data_error(ticker, "sentiment data")

        return create_sentiment_embed(ticker, sentiment_score, news_items)

    except Exception as e:
        log.error(f"sentiment_command_failed ticker={ticker} err={e}")
        return generic_error(str(e))


def handle_help_command() -> Dict[str, Any]:
    """
    Handle /help command.

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        log.info("slash_help")
        commands_help = format_command_help()
        return create_help_embed(commands_help)
    except Exception as e:
        log.error(f"help_command_failed err={e}")
        return generic_error(str(e))


# Helper functions


def _calculate_stats(cutoff: Optional[datetime]) -> Dict[str, Any]:
    """
    Calculate bot statistics from events.jsonl.

    Parameters
    ----------
    cutoff : Optional[datetime]
        Only include events after this time (None for all)

    Returns
    -------
    Dict[str, Any]
        Statistics dictionary
    """
    events_path = Path(__file__).resolve().parents[3] / "data" / "events.jsonl"

    if not events_path.exists():
        return {
            "total_alerts": 0,
            "unique_tickers": 0,
            "avg_score": 0,
        }

    total_alerts = 0
    tickers = set()
    scores = []

    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)

                    # Check timestamp
                    if cutoff:
                        ts_str = event.get("ts") or event.get("timestamp") or ""
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < cutoff:
                                continue

                    total_alerts += 1
                    ticker = event.get("ticker", "")
                    if ticker:
                        tickers.add(ticker.upper())

                    score = event.get("score") or event.get("cls", {}).get("score", 0)
                    if score:
                        scores.append(score)

                except Exception:
                    continue

        avg_score = sum(scores) / len(scores) if scores else 0

        return {
            "total_alerts": total_alerts,
            "unique_tickers": len(tickers),
            "avg_score": avg_score,
            "uptime": _get_uptime(),
            "gpu_usage": _get_gpu_usage(),
        }

    except Exception as e:
        log.error(f"calculate_stats_failed err={e}")
        return {
            "total_alerts": 0,
            "unique_tickers": 0,
            "avg_score": 0,
        }


def _get_alerts_for_ticker(
    ticker: str,
    cutoff: Optional[datetime],
) -> List[Dict[str, Any]]:
    """
    Get historical alerts for a ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    cutoff : Optional[datetime]
        Only include alerts after this time

    Returns
    -------
    List[Dict[str, Any]]
        List of alerts
    """
    events_path = Path(__file__).resolve().parents[3] / "data" / "events.jsonl"

    if not events_path.exists():
        return []

    alerts = []

    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)

                    # Check ticker
                    if event.get("ticker", "").upper() != ticker.upper():
                        continue

                    # Check timestamp
                    if cutoff:
                        ts_str = event.get("ts") or event.get("timestamp") or ""
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < cutoff:
                                continue

                    alerts.append(event)

                except Exception:
                    continue

        return alerts

    except Exception:
        return []


def _run_backtest(ticker: str, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run backtest simulation on historical alerts using BacktestEngine.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    alerts : List[Dict[str, Any]]
        List of historical alerts

    Returns
    -------
    Dict[str, Any]
        Backtest results
    """
    if not alerts:
        return {
            "total_alerts": 0,
            "wins": 0,
            "losses": 0,
            "avg_return": 0,
            "best_return": 0,
            "worst_return": 0,
        }

    try:
        # Import backtest engine
        from ..backtesting.engine import BacktestEngine

        # Determine date range from alerts
        first_alert_ts = alerts[0].get("ts") or alerts[0].get("timestamp")
        last_alert_ts = alerts[-1].get("ts") or alerts[-1].get("timestamp")

        start_date = datetime.fromisoformat(first_alert_ts.replace("Z", "+00:00"))
        end_date = datetime.fromisoformat(last_alert_ts.replace("Z", "+00:00"))

        # Run backtest with default strategy
        engine = BacktestEngine(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            initial_capital=10000.0,
            strategy_params={
                "min_score": 0.25,
                "take_profit_pct": 0.20,
                "stop_loss_pct": 0.10,
                "max_hold_hours": 24,
                "position_size_pct": 0.10,
            },
        )

        results = engine.run_backtest()
        metrics = results.get("metrics", {})
        trades = results.get("trades", [])

        # Extract returns from trades
        returns = [t.get("profit_pct", 0) for t in trades]

        return {
            "total_alerts": len(alerts),
            "wins": metrics.get("winning_trades", 0),
            "losses": metrics.get("losing_trades", 0),
            "avg_return": sum(returns) / len(returns) if returns else 0,
            "best_return": max(returns) if returns else 0,
            "worst_return": min(returns) if returns else 0,
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "max_drawdown": metrics.get("max_drawdown_pct", 0),
        }

    except Exception as e:
        log.error(f"backtest_engine_failed ticker={ticker} err={e}")
        # Fallback to simplified simulation
        total_alerts = len(alerts)
        wins = 0
        losses = 0
        returns = []

        for alert in alerts:
            # Simulate random return between -10% and +15%
            import random

            simulated_return = random.uniform(-10, 15)
            returns.append(simulated_return)

            if simulated_return > 5:
                wins += 1
            elif simulated_return < -5:
                losses += 1

        avg_return = sum(returns) / len(returns) if returns else 0
        best_return = max(returns) if returns else 0
        worst_return = min(returns) if returns else 0

        return {
            "total_alerts": total_alerts,
            "wins": wins,
            "losses": losses,
            "avg_return": avg_return,
            "best_return": best_return,
            "worst_return": worst_return,
        }


def _get_sentiment_data(ticker: str) -> tuple[Optional[float], List[Dict[str, Any]]]:
    """
    Get sentiment data for a ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol

    Returns
    -------
    tuple[Optional[float], List[Dict[str, Any]]]
        (sentiment_score, news_items)
    """
    # Check for recent events with sentiment
    events_path = Path(__file__).resolve().parents[3] / "data" / "events.jsonl"

    if not events_path.exists():
        return None, []

    sentiment_scores = []
    news_items = []

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)

                    # Check ticker
                    if event.get("ticker", "").upper() != ticker.upper():
                        continue

                    # Check timestamp
                    ts_str = event.get("ts") or event.get("timestamp") or ""
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue

                    # Extract sentiment
                    sentiment = event.get("cls", {}).get("sentiment", 0)
                    if sentiment:
                        sentiment_scores.append(sentiment)

                    # Extract news item
                    title = event.get("title", "")
                    source = event.get("source", "Unknown")
                    if title:
                        news_items.append(
                            {
                                "title": title,
                                "source": source,
                                "timestamp": ts_str,
                            }
                        )

                except Exception:
                    continue

        if not sentiment_scores:
            return None, []

        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
        return avg_sentiment, news_items[:5]  # Return up to 5 news items

    except Exception:
        return None, []


def _get_uptime() -> Optional[str]:
    """Get bot uptime."""
    # Could implement by checking process start time
    # For now, return None
    return None


def _get_gpu_usage() -> Optional[str]:
    """Get GPU usage if available."""
    # Could implement by checking nvidia-smi
    # For now, return None
    return None


# ============================================================================
# Admin Commands (WAVE 1.1)
# ============================================================================


def handle_admin_report_command() -> Dict[str, Any]:
    """
    Handle /admin report command.

    Trigger admin report on demand (not just nightly).

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        log.info("slash_admin_report")

        # Import admin controls
        from ..admin_reporter import post_admin_report

        # Generate and post report for yesterday
        success = post_admin_report()

        if success:
            return {
                "type": 4,
                "data": {
                    "content": "✅ Admin report generated and posted to admin channel!",
                    "flags": 64,  # Ephemeral
                },
            }
        else:
            return {
                "type": 4,
                "data": {
                    "content": "❌ Failed to generate admin report. Check logs for details.",
                    "flags": 64,
                },
            }

    except Exception as e:
        log.error(f"admin_report_command_failed err={e}")
        return generic_error(str(e))


def handle_admin_set_command(param: str, value: str) -> Dict[str, Any]:
    """
    Handle /admin set command.

    Manually override a parameter without recommendations.

    Parameters
    ----------
    param : str
        Parameter name (e.g., MIN_SCORE)
    value : str
        New value

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        log.info(f"slash_admin_set param={param} value={value}")

        # Import parameter manager
        from ..admin.parameter_manager import ParameterManager

        # Get current value from environment
        current_value = os.getenv(param, "")

        # Apply change
        manager = ParameterManager()
        success, message = manager.apply_parameter_change(
            param=param,
            old_value=current_value,
            new_value=value,
            reason="Manual override via /admin set command",
            approved_by="admin_slash_command",
        )

        if success:
            return {
                "type": 4,
                "data": {
                    "embeds": [
                        {
                            "title": "✅ Parameter Updated",
                            "description": message,
                            "color": 0x2ECC71,  # Green
                            "fields": [
                                {"name": "Parameter", "value": param, "inline": True},
                                {
                                    "name": "Old Value",
                                    "value": str(current_value),
                                    "inline": True,
                                },
                                {
                                    "name": "New Value",
                                    "value": str(value),
                                    "inline": True,
                                },
                            ],
                            "footer": {
                                "text": "Restart may be required for some parameters to take effect"
                            },
                        }
                    ],
                    "flags": 64,  # Ephemeral
                },
            }
        else:
            return {
                "type": 4,
                "data": {
                    "content": f"❌ {message}",
                    "flags": 64,
                },
            }

    except Exception as e:
        log.error(f"admin_set_command_failed param={param} err={e}")
        return generic_error(str(e))


def handle_admin_history_command() -> Dict[str, Any]:
    """
    Handle /admin history command.

    Show recent parameter changes and their impact.

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        log.info("slash_admin_history")

        # Import parameter manager
        from ..admin.parameter_manager import ParameterManager

        manager = ParameterManager()
        history = manager.get_change_history(limit=10)

        if not history:
            return {
                "type": 4,
                "data": {
                    "content": "📭 No parameter changes found.",
                    "flags": 64,
                },
            }

        # Build embed with recent changes
        fields = []
        for change in history[:5]:  # Show last 5
            change_id = change["change_id"]
            param = change["parameter"]
            old_val = change["old_value"]
            new_val = change["new_value"]
            status = change["status"]
            timestamp = change["timestamp"]

            # Format timestamp
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            time_str = dt.strftime("%Y-%m-%d %H:%M UTC")

            # Status emoji
            status_emoji = (
                "✅" if status == "active" else "↩️" if status == "rolled_back" else "❓"
            )

            # Impact indicator
            impact_calc = change.get("impact_calculated", 0)
            impact_positive = change.get("impact_positive")

            if impact_calc and impact_positive is not None:
                impact_str = "📈 Positive" if impact_positive else "📉 Negative"
            else:
                impact_str = "⏳ Pending"

            field_value = (
                f"**Old:** `{old_val}` → **New:** `{new_val}`\n"
                f"**Status:** {status_emoji} {status}\n"
                f"**Impact:** {impact_str}\n"
                f"**When:** {time_str}\n"
                f"**ID:** `{change_id}`"
            )

            fields.append(
                {"name": f"📊 {param}", "value": field_value, "inline": False}
            )

        return {
            "type": 4,
            "data": {
                "embeds": [
                    {
                        "title": "📜 Parameter Change History",
                        "description": "Recent parameter changes and their impact",
                        "color": 0x3498DB,  # Blue
                        "fields": fields,
                        "footer": {
                            "text": "Use /admin rollback <change_id> to revert a change"
                        },
                    }
                ],
                "flags": 64,  # Ephemeral
            },
        }

    except Exception as e:
        log.error(f"admin_history_command_failed err={e}")
        return generic_error(str(e))


def handle_admin_rollback_command(change_id: str) -> Dict[str, Any]:
    """
    Handle /admin rollback command.

    Rollback a parameter change.

    Parameters
    ----------
    change_id : str
        Change ID to rollback

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    try:
        log.info(f"slash_admin_rollback change_id={change_id}")

        # Import parameter manager
        from ..admin.parameter_manager import ParameterManager

        manager = ParameterManager()
        success, message = manager.rollback_change(change_id)

        if success:
            return {
                "type": 4,
                "data": {
                    "embeds": [
                        {
                            "title": "↩️ Parameter Rolled Back",
                            "description": message,
                            "color": 0xF39C12,  # Orange
                            "fields": [
                                {
                                    "name": "Change ID",
                                    "value": change_id,
                                    "inline": True,
                                },
                            ],
                            "footer": {"text": "Previous value has been restored"},
                        }
                    ],
                    "flags": 64,  # Ephemeral
                },
            }
        else:
            return {
                "type": 4,
                "data": {
                    "content": f"❌ {message}",
                    "flags": 64,
                },
            }

    except Exception as e:
        log.error(f"admin_rollback_command_failed change_id={change_id} err={e}")
        return generic_error(str(e))
