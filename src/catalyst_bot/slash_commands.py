"""
Discord Slash Commands Handler
================================

Implements application commands for:

Admin controls:
- /admin report [date] - Generate and post admin report
- /admin set <parameter> <value> - Update bot parameter
- /admin rollback - Rollback to previous configuration
- /admin stats - Show current parameter values

Public commands:
- /check <ticker> - Quick ticker lookup with price and recent alerts
- /research <ticker> [question] - LLM-powered deep dive analysis
- /ask <question> - Natural language query (LLM-powered)
- /compare <ticker1> <ticker2> - Side-by-side comparison
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .admin_controls import (
    _get_current_parameters,
    build_admin_components,
    build_admin_embed,
    generate_admin_report,
    save_admin_report,
)
from .config_updater import (
    apply_parameter_changes,
    rollback_changes,
    validate_parameter,
)
from .logging_utils import get_logger
from .market import get_last_price_change
from .validation import validate_ticker

log = get_logger("slash_commands")


# ======================== Response Types ========================

RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_CHANNEL_MESSAGE = 4
RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE = 5


# ======================== Command Handlers ========================


def handle_admin_report_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /admin report [date] command.

    Generates and posts admin report for specified date (default: yesterday).
    """
    try:
        # Extract options
        options = interaction_data.get("data", {}).get("options", [])

        # Parse date if provided
        target_date = None
        for opt in options:
            if opt.get("name") == "date":
                date_str = opt.get("value", "")
                try:
                    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    return {
                        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                        "data": {
                            "content": "Invalid date format. Use YYYY-MM-DD (e.g., 2025-10-03)",
                            "flags": 64,  # Ephemeral
                        },
                    }

        # Default to yesterday if not specified
        if target_date is None:
            from datetime import timedelta

            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        log.info(f"slash_admin_report date={target_date}")

        # Generate report
        report = generate_admin_report(target_date)
        save_admin_report(report)

        # Build embed and components
        embed = build_admin_embed(report)
        report_id = report.date.isoformat()
        components = build_admin_components(report_id)

        # Return response with embed and buttons
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "embeds": [embed],
                "components": components,
            },
        }

    except Exception as e:
        log.error(f"admin_report_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Failed to generate admin report: {str(e)}",
                "flags": 64,
            },
        }


def handle_admin_set_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /admin set <parameter> <value> command.

    Updates a bot parameter in real-time.
    """
    try:
        # Extract options
        options = interaction_data.get("data", {}).get("options", [])

        parameter = None
        value = None

        for opt in options:
            if opt.get("name") == "parameter":
                parameter = opt.get("value", "").strip().upper()
            elif opt.get("name") == "value":
                value = opt.get("value", "").strip()

        if not parameter or not value:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Both parameter and value are required.",
                    "flags": 64,
                },
            }

        log.info(f"slash_admin_set param={parameter} value={value}")

        # Validate parameter
        is_valid, error = validate_parameter(parameter, value)
        if not is_valid:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": f"Validation failed for {parameter}: {error}",
                    "flags": 64,
                },
            }

        # Apply change
        changes = {parameter: value}
        success, message = apply_parameter_changes(changes)

        if success:
            # Build success embed
            embed = {
                "title": "Parameter Updated",
                "description": f"Successfully updated `{parameter}` to `{value}`",
                "color": 0x2ECC71,  # Green
                "fields": [
                    {
                        "name": "Parameter",
                        "value": parameter,
                        "inline": True,
                    },
                    {
                        "name": "New Value",
                        "value": str(value),
                        "inline": True,
                    },
                ],
                "footer": {"text": "Configuration backup created automatically"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "embeds": [embed],
                },
            }
        else:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": f"Failed to update parameter: {message}",
                    "flags": 64,
                },
            }

    except Exception as e:
        log.error(f"admin_set_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Error updating parameter: {str(e)}",
                "flags": 64,
            },
        }


def handle_admin_rollback_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /admin rollback command (alias for /admin revert).

    Rollback to previous configuration.
    """
    return handle_admin_revert_command(interaction_data)


def handle_admin_revert_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /admin revert command.

    Revert to the most recent configuration backup.
    """
    try:
        log.info("slash_admin_revert")

        # Check if we have any backups
        from .config_updater import _get_backup_dir

        backup_dir = _get_backup_dir()
        backups = sorted(backup_dir.glob("env_*.backup"), reverse=True)

        if not backups:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": (
                        "❌ No configuration backups found. "
                        "Make a change first to create a backup."
                    ),
                    "flags": 64,
                },
            }

        # Get the most recent backup details
        most_recent = backups[0]
        # Parse timestamp from filename: env_YYYYMMDD_HHMMSS.backup
        try:
            timestamp_str = most_recent.stem.replace("env_", "")
            backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            time_ago = datetime.now() - backup_time
            if time_ago.days > 0:
                time_str = f"{time_ago.days} day(s) ago"
            elif time_ago.seconds > 3600:
                time_str = f"{time_ago.seconds // 3600} hour(s) ago"
            else:
                time_str = f"{time_ago.seconds // 60} minute(s) ago"
        except Exception:
            time_str = "unknown time"

        # Rollback to most recent backup
        success, message = rollback_changes()

        if success:
            embed = {
                "title": "✅ Configuration Reverted",
                "description": f"Successfully reverted to backup from {time_str}",
                "color": 0x2ECC71,  # Green
                "fields": [
                    {
                        "name": "Backup File",
                        "value": most_recent.name,
                        "inline": True,
                    },
                    {
                        "name": "Total Backups",
                        "value": str(len(backups)),
                        "inline": True,
                    },
                ],
                "footer": {"text": "Bot will use reverted settings immediately"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "embeds": [embed],
                },
            }
        else:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": f"❌ Rollback failed: {message}",
                    "flags": 64,
                },
            }

    except Exception as e:
        log.error(f"admin_revert_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"❌ Error during revert: {str(e)}",
                "flags": 64,
            },
        }


def handle_admin_stats_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /admin stats command.

    Shows current parameter values and recent change history.
    """
    try:
        log.info("slash_admin_stats")

        # Get current parameters
        params = _get_current_parameters()

        # Build fields for key parameters
        fields = [
            {
                "name": "Sentiment Thresholds",
                "value": (
                    f"MIN_SCORE: {params.get('MIN_SCORE', 'N/A')}\n"
                    f"MIN_SENT_ABS: {params.get('MIN_SENT_ABS', 'N/A')}"
                ),
                "inline": True,
            },
            {
                "name": "Price Filters",
                "value": (
                    f"PRICE_CEILING: ${params.get('PRICE_CEILING', 'N/A')}\n"
                    f"PRICE_FLOOR: ${params.get('PRICE_FLOOR', 'N/A')}"
                ),
                "inline": True,
            },
            {
                "name": "Alert Limits",
                "value": (
                    f"MAX_ALERTS_PER_CYCLE: {params.get('MAX_ALERTS_PER_CYCLE', 'N/A')}\n"
                    f"MIN_INTERVAL_MS: {params.get('ALERTS_MIN_INTERVAL_MS', 'N/A')}"
                ),
                "inline": True,
            },
            {
                "name": "Confidence Thresholds",
                "value": (
                    f"CONFIDENCE_HIGH: {params.get('CONFIDENCE_HIGH', 'N/A')}\n"
                    f"CONFIDENCE_MODERATE: {params.get('CONFIDENCE_MODERATE', 'N/A')}"
                ),
                "inline": True,
            },
            {
                "name": "Analyzer Thresholds",
                "value": (
                    f"HIT_UP_PCT: {params.get('ANALYZER_HIT_UP_THRESHOLD_PCT', 'N/A')}%\n"
                    f"HIT_DOWN_PCT: {params.get('ANALYZER_HIT_DOWN_THRESHOLD_PCT', 'N/A')}%"
                ),
                "inline": True,
            },
            {
                "name": "Breakout Scanner",
                "value": (
                    f"MIN_AVG_VOL: {params.get('BREAKOUT_MIN_AVG_VOL', 'N/A')}\n"
                    f"MIN_RELVOL: {params.get('BREAKOUT_MIN_RELVOL', 'N/A')}"
                ),
                "inline": True,
            },
        ]

        # Add recent changes
        try:
            from .config_updater import get_change_history

            history = get_change_history(limit=3)

            if history:
                history_text = ""
                for entry in history:
                    ts = entry.get("timestamp", "Unknown")
                    # Parse timestamp and show relative time
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        elapsed = datetime.now(timezone.utc) - dt
                        if elapsed.days > 0:
                            time_str = f"{elapsed.days}d ago"
                        elif elapsed.seconds > 3600:
                            time_str = f"{elapsed.seconds // 3600}h ago"
                        else:
                            time_str = f"{elapsed.seconds // 60}m ago"
                    except Exception:
                        time_str = ts[:10]

                    changes = entry.get("changes", {})
                    params_changed = ", ".join(list(changes.keys())[:3])
                    if len(changes) > 3:
                        params_changed += f" +{len(changes) - 3} more"

                    history_text += f"• {time_str}: {params_changed}\n"

                fields.append(
                    {
                        "name": "Recent Changes",
                        "value": history_text,
                        "inline": False,
                    }
                )
        except Exception:
            pass

        embed = {
            "title": "📊 Current Bot Configuration",
            "color": 0x3498DB,  # Blue
            "fields": fields,
            "footer": {
                "text": "Use /admin set to update parameters | /admin revert to rollback"
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "embeds": [embed],
                "flags": 64,  # Ephemeral
            },
        }

    except Exception as e:
        log.error(f"admin_stats_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Error fetching stats: {str(e)}",
                "flags": 64,
            },
        }


# ======================== Public Command Handlers ========================


def handle_check_ticker_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /check <ticker> command.

    Quick ticker lookup with current price, change, and recent alerts.
    """
    try:
        # Extract ticker from options
        options = interaction_data.get("data", {}).get("options", [])
        ticker = None

        for opt in options:
            if opt.get("name") == "ticker":
                ticker = opt.get("value", "").strip().upper()

        if not ticker:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Please provide a ticker symbol.",
                    "flags": 64,
                },
            }

        # Validate ticker
        ticker = validate_ticker(ticker)
        if not ticker:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Invalid ticker symbol.",
                    "flags": 64,
                },
            }

        log.info(f"slash_check_ticker ticker={ticker}")

        # Get current price
        try:
            price, change_pct = get_last_price_change(ticker)
        except Exception:
            price, change_pct = None, None

        # Load recent alerts from events.jsonl
        recent_alerts = _get_recent_alerts_for_ticker(ticker, days=7)

        # Build embed
        if price:
            price_str = f"${price:.2f}"
            change_str = f"{change_pct:+.2f}%" if change_pct else "N/A"
            color = 0x2ECC71 if (change_pct and change_pct > 0) else 0xE74C3C
        else:
            price_str = "N/A"
            change_str = "N/A"
            color = 0x95A5A6  # Gray

        fields = [
            {
                "name": "Current Price",
                "value": price_str,
                "inline": True,
            },
            {
                "name": "Change",
                "value": change_str,
                "inline": True,
            },
        ]

        # Add recent alerts summary
        if recent_alerts:
            alerts_summary = f"{len(recent_alerts)} alert(s) in past 7 days\n"
            for alert in recent_alerts[:3]:  # Show up to 3 most recent
                date_str = alert.get("date", "Unknown")
                reason = alert.get("reason", "N/A")[:50]
                alerts_summary += f"• {date_str}: {reason}\n"

            if len(recent_alerts) > 3:
                alerts_summary += f"... and {len(recent_alerts) - 3} more"

            fields.append(
                {
                    "name": "Recent Alerts",
                    "value": alerts_summary,
                    "inline": False,
                }
            )
        else:
            fields.append(
                {
                    "name": "Recent Alerts",
                    "value": "No alerts in past 7 days",
                    "inline": False,
                }
            )

        embed = {
            "title": f"📊 {ticker} Quick Check",
            "color": color,
            "fields": fields,
            "footer": {"text": "Use /research for detailed analysis"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "embeds": [embed],
            },
        }

    except Exception as e:
        log.error(f"check_ticker_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Error checking ticker: {str(e)}",
                "flags": 64,
            },
        }


def handle_research_ticker_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /research <ticker> [question] command.

    LLM-powered deep dive analysis.
    """
    try:
        # Check if LLM is enabled
        if not os.getenv("FEATURE_LLM_CLASSIFIER", "0") in ("1", "true", "yes", "on"):
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": (
                        "LLM features are currently disabled. "
                        "Enable with FEATURE_LLM_CLASSIFIER=1"
                    ),
                    "flags": 64,
                },
            }

        # Extract options
        options = interaction_data.get("data", {}).get("options", [])
        ticker = None
        question = None

        for opt in options:
            if opt.get("name") == "ticker":
                ticker = opt.get("value", "").strip().upper()
            elif opt.get("name") == "question":
                question = opt.get("value", "").strip()

        if not ticker:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Please provide a ticker symbol.",
                    "flags": 64,
                },
            }

        ticker = validate_ticker(ticker)
        if not ticker:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Invalid ticker symbol.",
                    "flags": 64,
                },
            }

        log.info(f"slash_research_ticker ticker={ticker} question={question}")

        # Defer response (LLM can take a few seconds)
        # Return type 5 immediately, then use followup webhook to send actual response
        return {
            "type": RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE,
        }

        # TODO: Send followup after LLM completes
        # This requires webhook followup implementation

    except Exception as e:
        log.error(f"research_ticker_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Error during research: {str(e)}",
                "flags": 64,
            },
        }


def handle_ask_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /ask <question> command.

    Natural language query using LLM.
    """
    try:
        if not os.getenv("FEATURE_LLM_CLASSIFIER", "0") in ("1", "true", "yes", "on"):
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "LLM features are currently disabled.",
                    "flags": 64,
                },
            }

        # Extract question
        options = interaction_data.get("data", {}).get("options", [])
        question = None

        for opt in options:
            if opt.get("name") == "question":
                question = opt.get("value", "").strip()

        if not question:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Please provide a question.",
                    "flags": 64,
                },
            }

        log.info(f"slash_ask question='{question[:50]}...'")

        # Defer response
        return {
            "type": RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE,
        }

    except Exception as e:
        log.error(f"ask_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Error processing question: {str(e)}",
                "flags": 64,
            },
        }


def handle_compare_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /compare <ticker1> <ticker2> command.

    Side-by-side ticker comparison.
    """
    try:
        # Extract tickers
        options = interaction_data.get("data", {}).get("options", [])
        ticker1 = None
        ticker2 = None

        for opt in options:
            if opt.get("name") == "ticker1":
                ticker1 = opt.get("value", "").strip().upper()
            elif opt.get("name") == "ticker2":
                ticker2 = opt.get("value", "").strip().upper()

        if not ticker1 or not ticker2:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Please provide two ticker symbols.",
                    "flags": 64,
                },
            }

        ticker1 = validate_ticker(ticker1)
        ticker2 = validate_ticker(ticker2)

        if not ticker1 or not ticker2:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Invalid ticker symbol(s).",
                    "flags": 64,
                },
            }

        log.info(f"slash_compare ticker1={ticker1} ticker2={ticker2}")

        # Get prices
        try:
            price1, change1 = get_last_price_change(ticker1)
        except Exception:
            price1, change1 = None, None

        try:
            price2, change2 = get_last_price_change(ticker2)
        except Exception:
            price2, change2 = None, None

        # Get recent alerts
        alerts1 = _get_recent_alerts_for_ticker(ticker1, days=7)
        alerts2 = _get_recent_alerts_for_ticker(ticker2, days=7)

        # Build comparison embed
        fields = [
            {
                "name": f"{ticker1} - Price",
                "value": f"${price1:.2f}" if price1 else "N/A",
                "inline": True,
            },
            {
                "name": f"{ticker2} - Price",
                "value": f"${price2:.2f}" if price2 else "N/A",
                "inline": True,
            },
            {
                "name": "---",
                "value": "\u200b",  # Zero-width space for spacing
                "inline": False,
            },
            {
                "name": f"{ticker1} - Change",
                "value": f"{change1:+.2f}%" if change1 else "N/A",
                "inline": True,
            },
            {
                "name": f"{ticker2} - Change",
                "value": f"{change2:+.2f}%" if change2 else "N/A",
                "inline": True,
            },
            {
                "name": "---",
                "value": "\u200b",
                "inline": False,
            },
            {
                "name": f"{ticker1} - Alerts (7d)",
                "value": f"{len(alerts1)} alert(s)",
                "inline": True,
            },
            {
                "name": f"{ticker2} - Alerts (7d)",
                "value": f"{len(alerts2)} alert(s)",
                "inline": True,
            },
        ]

        embed = {
            "title": f"📊 {ticker1} vs {ticker2}",
            "color": 0x3498DB,  # Blue
            "fields": fields,
            "footer": {"text": "LLM-powered comparison coming soon!"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "embeds": [embed],
            },
        }

    except Exception as e:
        log.error(f"compare_command_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Error comparing tickers: {str(e)}",
                "flags": 64,
            },
        }


# ======================== Helper Functions ========================


def _get_recent_alerts_for_ticker(ticker: str, days: int = 7) -> List[Dict[str, Any]]:
    """Load recent alerts for a ticker from events.jsonl."""
    import json
    from pathlib import Path

    try:
        events_path = Path(__file__).resolve().parents[2] / "data" / "events.jsonl"

        if not events_path.exists():
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        alerts = []

        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)

                    # Check if ticker matches
                    if event.get("ticker", "").upper() != ticker.upper():
                        continue

                    # Check timestamp
                    ts_str = event.get("ts") or event.get("timestamp") or ""
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                    if ts >= cutoff:
                        alerts.append(
                            {
                                "date": ts.strftime("%Y-%m-%d"),
                                "reason": event.get("title", "Unknown"),
                                "sentiment": event.get("cls", {}).get("sentiment", 0),
                            }
                        )

                except Exception:
                    continue

        # Sort by date descending
        alerts.sort(key=lambda x: x["date"], reverse=True)
        return alerts

    except Exception as e:
        log.error(f"load_recent_alerts_failed ticker={ticker} err={e}")
        return []


# ======================== Main Command Router ========================


def handle_slash_command(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route slash command to appropriate handler.

    Parameters
    ----------
    interaction_data : dict
        Discord interaction payload

    Returns
    -------
    dict
        Discord interaction response
    """
    try:
        data = interaction_data.get("data", {})
        command_name = data.get("name", "")

        # Parse subcommands (e.g., /admin report)
        options = data.get("options", [])
        if options and options[0].get("type") == 1:  # SUB_COMMAND
            subcommand = options[0].get("name", "")
            # Update interaction data to have subcommand as main command
            interaction_data["data"]["options"] = options[0].get("options", [])
        else:
            subcommand = None

        log.info(f"slash_command command={command_name} subcommand={subcommand}")

        # Route to handler
        if command_name == "admin":
            if subcommand == "report":
                return handle_admin_report_command(interaction_data)
            elif subcommand == "set":
                return handle_admin_set_command(interaction_data)
            elif subcommand == "rollback":
                return handle_admin_rollback_command(interaction_data)
            elif subcommand == "revert":
                return handle_admin_revert_command(interaction_data)
            elif subcommand == "stats":
                return handle_admin_stats_command(interaction_data)
            else:
                return {
                    "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                    "data": {
                        "content": f"Unknown admin subcommand: {subcommand}",
                        "flags": 64,
                    },
                }
        elif command_name == "check":
            return handle_check_ticker_command(interaction_data)
        elif command_name == "research":
            return handle_research_ticker_command(interaction_data)
        elif command_name == "ask":
            return handle_ask_command(interaction_data)
        elif command_name == "compare":
            return handle_compare_command(interaction_data)
        # WAVE 7.1: User-facing slash commands
        elif command_name == "chart":
            return _handle_chart_slash(interaction_data)
        elif command_name == "watchlist":
            return _handle_watchlist_slash(interaction_data)
        elif command_name == "stats":
            return _handle_stats_slash(interaction_data)
        elif command_name == "backtest":
            return _handle_backtest_slash(interaction_data)
        elif command_name == "sentiment":
            return _handle_sentiment_slash(interaction_data)
        elif command_name == "help":
            return _handle_help_slash(interaction_data)
        else:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": f"Unknown command: {command_name}",
                    "flags": 64,
                },
            }

    except Exception as e:
        log.error(f"slash_command_handler_failed err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Command failed: {str(e)}",
                "flags": 64,
            },
        }


# ======================== WAVE 7.1: User Command Wrappers ========================


def _handle_chart_slash(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle /chart command by extracting parameters and calling handler."""
    from .commands.handlers import handle_chart_command

    options = interaction_data.get("data", {}).get("options", [])
    ticker = None
    timeframe = "1D"
    user_id = interaction_data.get("member", {}).get("user", {}).get("id")

    for opt in options:
        if opt.get("name") == "ticker":
            ticker = opt.get("value", "")
        elif opt.get("name") == "timeframe":
            timeframe = opt.get("value", "1D")

    if not ticker:
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": "Please provide a ticker symbol.",
                "flags": 64,
            },
        }

    return handle_chart_command(ticker, timeframe, user_id)


def _handle_watchlist_slash(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle /watchlist command by extracting parameters and calling handler."""
    from .commands.handlers import handle_watchlist_command

    options = interaction_data.get("data", {}).get("options", [])
    action = None
    ticker = None
    user_id = interaction_data.get("member", {}).get("user", {}).get("id")

    for opt in options:
        if opt.get("name") == "action":
            action = opt.get("value", "")
        elif opt.get("name") == "ticker":
            ticker = opt.get("value", "")

    if not action:
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": "Please specify an action.",
                "flags": 64,
            },
        }

    return handle_watchlist_command(action, ticker, user_id)


def _handle_stats_slash(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle /stats command by extracting parameters and calling handler."""
    from .commands.handlers import handle_stats_command

    options = interaction_data.get("data", {}).get("options", [])
    period = "7d"

    for opt in options:
        if opt.get("name") == "period":
            period = opt.get("value", "7d")

    return handle_stats_command(period)


def _handle_backtest_slash(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle /backtest command by extracting parameters and calling handler."""
    options = interaction_data.get("data", {}).get("options", [])
    ticker = None
    start_date = None
    end_date = None
    strategy = "default"

    for opt in options:
        if opt.get("name") == "ticker":
            ticker = opt.get("value", "")
        elif opt.get("name") == "start_date":
            start_date = opt.get("value", "")
        elif opt.get("name") == "end_date":
            end_date = opt.get("value", "")
        elif opt.get("name") == "strategy":
            strategy = opt.get("value", "default")

    if not ticker:
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": "Please provide a ticker symbol.",
                "flags": 64,
            },
        }

    return handle_backtest_command_v2(ticker, start_date, end_date, strategy)


def _handle_sentiment_slash(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle /sentiment command by extracting parameters and calling handler."""
    from .commands.handlers import handle_sentiment_command

    options = interaction_data.get("data", {}).get("options", [])
    ticker = None

    for opt in options:
        if opt.get("name") == "ticker":
            ticker = opt.get("value", "")

    if not ticker:
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": "Please provide a ticker symbol.",
                "flags": 64,
            },
        }

    return handle_sentiment_command(ticker)


def _handle_help_slash(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle /help command by calling handler."""
    from .commands.handlers import handle_help_command

    return handle_help_command()


# ======================== WAVE BETA 2: Backtest Enhancement ========================


def handle_backtest_command_v2(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    strategy: str = "default",
) -> Dict[str, Any]:
    """
    Handle /backtest command with full BacktestEngine integration.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    start_date : str, optional
        Start date (YYYY-MM-DD), defaults to 30 days ago
    end_date : str, optional
        End date (YYYY-MM-DD), defaults to today
    strategy : str
        Strategy name ('default', 'aggressive', 'conservative')

    Returns
    -------
    Dict[str, Any]
        Discord interaction response with backtest results
    """
    try:
        # Validate ticker
        ticker = validate_ticker(ticker)
        if not ticker:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": f"Invalid ticker symbol: {ticker}",
                    "flags": 64,
                },
            }

        # Set default dates
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not start_date:
            start_dt = datetime.now(timezone.utc) - timedelta(days=30)
            start_date = start_dt.strftime("%Y-%m-%d")

        # Validate dates
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return {
                "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
                "data": {
                    "content": "Invalid date format. Use YYYY-MM-DD",
                    "flags": 64,
                },
            }

        log.info(
            f"backtest_command ticker={ticker} start={start_date} "
            f"end={end_date} strategy={strategy}"
        )

        # Import backtest engine
        from .backtesting.engine import BacktestEngine

        # Define strategy parameters
        strategy_params = _get_strategy_params(strategy)

        # Run backtest
        engine = BacktestEngine(
            start_date=start_date,
            end_date=end_date,
            initial_capital=10000.0,
            strategy_params=strategy_params,
        )

        results = engine.run_backtest()

        # Format results into Discord embed
        embed = format_backtest_embed(ticker, start_date, end_date, results, strategy)

        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "embeds": [embed],
            },
        }

    except Exception as e:
        log.error(f"backtest_command_failed ticker={ticker} err={e}")
        return {
            "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
            "data": {
                "content": f"Backtest failed: {str(e)}",
                "flags": 64,
            },
        }


def format_backtest_embed(
    ticker: str,
    start_date: str,
    end_date: str,
    results: Dict[str, Any],
    strategy: str,
) -> Dict[str, Any]:
    """
    Format backtest results into Discord embed optimized for mobile.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    start_date : str
        Backtest start date
    end_date : str
        Backtest end date
    results : Dict[str, Any]
        Backtest results from BacktestEngine
    strategy : str
        Strategy name

    Returns
    -------
    Dict[str, Any]
        Discord embed object
    """
    metrics = results.get("metrics", {})
    trades = results.get("trades", [])

    # Determine embed color based on performance
    total_return = metrics.get("total_return_pct", 0)
    if total_return > 10:
        color = 0x2ECC71  # Green
    elif total_return > 0:
        color = 0xF39C12  # Orange
    else:
        color = 0xE74C3C  # Red

    # Build fields
    fields = []

    # Performance Summary
    win_rate = metrics.get("win_rate", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    max_dd = metrics.get("max_drawdown_pct", 0)

    perf_value = (
        f"**Return:** {total_return:+.2f}%\n"
        f"**Win Rate:** {win_rate:.1f}%\n"
        f"**Sharpe:** {sharpe:.2f}\n"
        f"**Max DD:** {max_dd:.2f}%"
    )

    fields.append(
        {
            "name": "📊 Performance",
            "value": perf_value,
            "inline": True,
        }
    )

    # Trade Statistics
    total_trades = metrics.get("total_trades", 0)
    winning_trades = metrics.get("winning_trades", 0)
    losing_trades = metrics.get("losing_trades", 0)
    avg_return = metrics.get("avg_return", 0)

    trade_value = (
        f"**Total:** {total_trades}\n"
        f"**Wins:** {winning_trades} ✅\n"
        f"**Losses:** {losing_trades} ❌\n"
        f"**Avg Return:** {avg_return:+.2f}%"
    )

    fields.append(
        {
            "name": "📈 Trades",
            "value": trade_value,
            "inline": True,
        }
    )

    # Risk Metrics (Sortino, Calmar, Profit Factor)
    sortino = metrics.get("sortino_ratio", 0)
    profit_factor = metrics.get("profit_factor", 0)
    calmar = (total_return / max_dd) if max_dd > 0 else 0

    risk_value = (
        f"**Sortino:** {sortino:.2f}\n"
        f"**Calmar:** {calmar:.2f}\n"
        f"**Profit Factor:** {profit_factor:.2f}"
    )

    fields.append(
        {
            "name": "⚖️ Risk Metrics",
            "value": risk_value,
            "inline": True,
        }
    )

    # Best/Worst Trades
    if trades:
        sorted_trades = sorted(
            trades, key=lambda t: t.get("profit_pct", 0), reverse=True
        )

        best_trade = sorted_trades[0] if sorted_trades else None
        worst_trade = sorted_trades[-1] if sorted_trades else None

        if best_trade:
            best_value = (
                f"**{best_trade.get('ticker', 'N/A')}**\n"
                f"Entry: ${best_trade.get('entry_price', 0):.2f}\n"
                f"Exit: ${best_trade.get('exit_price', 0):.2f}\n"
                f"Return: {best_trade.get('profit_pct', 0):+.2f}%\n"
                f"Reason: {best_trade.get('exit_reason', 'N/A')}"
            )

            fields.append(
                {
                    "name": "🏆 Best Trade",
                    "value": best_value,
                    "inline": True,
                }
            )

        if worst_trade and worst_trade != best_trade:
            worst_value = (
                f"**{worst_trade.get('ticker', 'N/A')}**\n"
                f"Entry: ${worst_trade.get('entry_price', 0):.2f}\n"
                f"Exit: ${worst_trade.get('exit_price', 0):.2f}\n"
                f"Return: {worst_trade.get('profit_pct', 0):+.2f}%\n"
                f"Reason: {worst_trade.get('exit_reason', 'N/A')}"
            )

            fields.append(
                {
                    "name": "💀 Worst Trade",
                    "value": worst_value,
                    "inline": True,
                }
            )

    # Trade distribution
    if total_trades > 0:
        neutrals = total_trades - winning_trades - losing_trades
        dist_value = (
            f"✅ Wins: {winning_trades} ({winning_trades/total_trades*100:.0f}%)\n"
            f"❌ Losses: {losing_trades} ({losing_trades/total_trades*100:.0f}%)\n"
            f"⚪ Neutral: {neutrals} ({neutrals/total_trades*100:.0f}%)"
        )

        fields.append(
            {
                "name": "📊 Trade Distribution",
                "value": dist_value,
                "inline": False,
            }
        )

    # Catalyst performance (if available)
    catalyst_perf = metrics.get("catalyst_performance", {})
    if catalyst_perf:
        top_catalysts = sorted(
            catalyst_perf.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True
        )[:3]

        if top_catalysts:
            cat_lines = []
            for cat, perf in top_catalysts:
                cat_lines.append(
                    f"**{cat}:** {perf.get('win_rate', 0):.1%} "
                    f"({perf.get('total_trades', 0)} trades)"
                )

            fields.append(
                {
                    "name": "🎯 Top Catalysts",
                    "value": "\n".join(cat_lines),
                    "inline": False,
                }
            )

    # Build embed
    embed = {
        "title": f"📊 Backtest: {ticker}",
        "description": (
            f"**Period:** {start_date} to {end_date}\n"
            f"**Strategy:** {strategy.capitalize()}\n"
            f"**Initial Capital:** $10,000"
        ),
        "color": color,
        "fields": fields,
        "footer": {
            "text": "Note: Results include realistic slippage and commission modeling"
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return embed


def _get_strategy_params(strategy: str) -> Dict[str, Any]:
    """
    Get strategy parameters based on strategy name.

    Parameters
    ----------
    strategy : str
        Strategy name ('default', 'aggressive', 'conservative')

    Returns
    -------
    Dict[str, Any]
        Strategy parameters
    """
    if strategy == "aggressive":
        return {
            "min_score": 0.20,
            "min_sentiment": None,
            "take_profit_pct": 0.30,  # 30% take profit
            "stop_loss_pct": 0.15,  # 15% stop loss
            "max_hold_hours": 48,
            "position_size_pct": 0.15,  # 15% position size
            "max_daily_volume_pct": 0.08,
        }
    elif strategy == "conservative":
        return {
            "min_score": 0.35,
            "min_sentiment": 0.3,
            "take_profit_pct": 0.15,  # 15% take profit
            "stop_loss_pct": 0.08,  # 8% stop loss
            "max_hold_hours": 12,
            "position_size_pct": 0.05,  # 5% position size
            "max_daily_volume_pct": 0.03,
        }
    else:  # default
        return {
            "min_score": 0.25,
            "min_sentiment": None,
            "take_profit_pct": 0.20,  # 20% take profit
            "stop_loss_pct": 0.10,  # 10% stop loss
            "max_hold_hours": 24,
            "position_size_pct": 0.10,  # 10% position size
            "max_daily_volume_pct": 0.05,
        }
