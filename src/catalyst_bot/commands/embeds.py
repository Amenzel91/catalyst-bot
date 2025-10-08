"""
Discord Embed Templates
========================

Rich embed builders for command responses.

Color Codes:
- Green (bullish): 0x2ECC71
- Red (bearish): 0xE74C3C
- Blue (neutral): 0x3498DB
- Yellow (warning): 0xF39C12
- Gray (info): 0x95A5A6
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Discord response types
RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_CHANNEL_MESSAGE = 4
RESPONSE_TYPE_DEFERRED_CHANNEL_MESSAGE = 5

# Embed color codes
COLOR_BULLISH = 0x2ECC71  # Green
COLOR_BEARISH = 0xE74C3C  # Red
COLOR_NEUTRAL = 0x3498DB  # Blue
COLOR_WARNING = 0xF39C12  # Yellow
COLOR_INFO = 0x95A5A6  # Gray


def create_chart_embed(
    ticker: str,
    timeframe: str,
    chart_url: str,
    price_data: Dict[str, Any],
    components: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Create an embed for a chart response.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    timeframe : str
        Chart timeframe (1D, 5D, etc.)
    chart_url : str
        URL to the chart image
    price_data : Dict[str, Any]
        Price data with keys: price, change_pct, volume, vwap, rsi
    components : Optional[List[Dict[str, Any]]]
        Discord components (e.g., select menus for indicator toggles)

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    change_pct = price_data.get("change_pct", 0)
    color = COLOR_BULLISH if change_pct > 0 else COLOR_BEARISH

    # Format price data
    price = price_data.get("price")
    price_str = f"${price:.2f}" if price else "N/A"
    change_str = f"{change_pct:+.2f}%" if change_pct else "N/A"
    volume = price_data.get("volume")
    volume_str = f"{volume:,}" if volume else "N/A"

    fields = [
        {
            "name": "Price",
            "value": price_str,
            "inline": True,
        },
        {
            "name": "Change",
            "value": change_str,
            "inline": True,
        },
        {
            "name": "Volume",
            "value": volume_str,
            "inline": True,
        },
    ]

    # Add VWAP if available
    vwap = price_data.get("vwap")
    if vwap:
        fields.append(
            {
                "name": "VWAP",
                "value": f"${vwap:.2f}",
                "inline": True,
            }
        )

    # Add RSI if available
    rsi = price_data.get("rsi")
    if rsi:
        fields.append(
            {
                "name": "RSI(14)",
                "value": f"{rsi:.1f}",
                "inline": True,
            }
        )

    embed = {
        "title": f"{ticker} - {timeframe} Chart",
        "description": f"Current Price: {price_str} ({change_str})",
        "color": color,
        "image": {"url": chart_url},
        "fields": fields,
        "footer": {"text": "Catalyst-Bot"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    response_data = {
        "embeds": [embed],
        "flags": 64,  # EPHEMERAL (only visible to user)
    }

    # Add components if provided (e.g., select menus)
    if components:
        response_data["components"] = components

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": response_data,
    }


def create_watchlist_embed(
    action: str,
    tickers: List[str],
    success: bool = True,
    message: str = "",
) -> Dict[str, Any]:
    """
    Create an embed for a watchlist response.

    Parameters
    ----------
    action : str
        Action performed (add, remove, list, clear)
    tickers : List[str]
        List of tickers in watchlist
    success : bool
        Whether action was successful
    message : str
        Additional message

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    if action == "add":
        title = "Watchlist Updated"
        description = f"Added {tickers[0] if tickers else 'ticker'} to your watchlist"
        color = COLOR_BULLISH
    elif action == "remove":
        title = "Watchlist Updated"
        description = (
            f"Removed {tickers[0] if tickers else 'ticker'} from your watchlist"
        )
        color = COLOR_NEUTRAL
    elif action == "clear":
        title = "Watchlist Cleared"
        description = "All tickers removed from your watchlist"
        color = COLOR_WARNING
    else:  # list
        title = "Your Watchlist"
        description = f"{len(tickers)} ticker(s) on your watchlist"
        color = COLOR_INFO

    fields = []

    # Show tickers for list action
    if action == "list":
        if tickers:
            # Group tickers into chunks of 10 for display
            chunks = [tickers[i : i + 10] for i in range(0, len(tickers), 10)]
            for i, chunk in enumerate(chunks):
                field_name = "Tickers" if i == 0 else "Tickers (cont.)"
                field_value = ", ".join(chunk)
                fields.append(
                    {
                        "name": field_name,
                        "value": field_value,
                        "inline": False,
                    }
                )
        else:
            fields.append(
                {
                    "name": "Watchlist",
                    "value": "Your watchlist is empty. Use `/watchlist add` to add tickers.",
                    "inline": False,
                }
            )
    else:
        # Show current count for add/remove/clear
        fields.append(
            {
                "name": "Total Tickers",
                "value": str(len(tickers)),
                "inline": True,
            }
        )

    if message:
        fields.append(
            {
                "name": "Note",
                "value": message,
                "inline": False,
            }
        )

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": "Use /watchlist list to see all tickers"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "embeds": [embed],
            "flags": 64,  # EPHEMERAL
        },
    }


def create_stats_embed(
    period: str,
    stats: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create an embed for bot statistics.

    Parameters
    ----------
    period : str
        Time period (1d, 7d, 30d, all)
    stats : Dict[str, Any]
        Statistics data

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    period_labels = {
        "1d": "Today",
        "7d": "This Week",
        "30d": "This Month",
        "all": "All Time",
    }
    period_label = period_labels.get(period, "Unknown")

    fields = [
        {
            "name": "Total Alerts",
            "value": str(stats.get("total_alerts", 0)),
            "inline": True,
        },
        {
            "name": "Unique Tickers",
            "value": str(stats.get("unique_tickers", 0)),
            "inline": True,
        },
        {
            "name": "Avg Score",
            "value": f"{stats.get('avg_score', 0):.2f}",
            "inline": True,
        },
    ]

    # Add win rate if available
    win_rate = stats.get("win_rate")
    if win_rate is not None:
        fields.append(
            {
                "name": "Win Rate",
                "value": f"{win_rate:.1f}%",
                "inline": True,
            }
        )

    # Add avg return if available
    avg_return = stats.get("avg_return")
    if avg_return is not None:
        fields.append(
            {
                "name": "Avg Return",
                "value": f"{avg_return:+.2f}%",
                "inline": True,
            }
        )

    # Best/worst catalyst
    best_catalyst = stats.get("best_catalyst")
    if best_catalyst:
        fields.append(
            {
                "name": "Best Alert",
                "value": best_catalyst,
                "inline": False,
            }
        )

    worst_catalyst = stats.get("worst_catalyst")
    if worst_catalyst:
        fields.append(
            {
                "name": "Worst Alert",
                "value": worst_catalyst,
                "inline": False,
            }
        )

    # System stats
    uptime = stats.get("uptime")
    if uptime:
        fields.append(
            {
                "name": "Uptime",
                "value": uptime,
                "inline": True,
            }
        )

    gpu_usage = stats.get("gpu_usage")
    if gpu_usage:
        fields.append(
            {
                "name": "GPU Usage",
                "value": gpu_usage,
                "inline": True,
            }
        )

    embed = {
        "title": f"Bot Statistics - {period_label}",
        "color": COLOR_INFO,
        "fields": fields,
        "footer": {"text": "Statistics based on posted alerts"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "embeds": [embed],
        },
    }


def create_backtest_embed(
    ticker: str,
    days: int,
    results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create an embed for backtest results.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    days : int
        Number of days backtested
    results : Dict[str, Any]
        Backtest results

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    total_alerts = results.get("total_alerts", 0)
    wins = results.get("wins", 0)
    losses = results.get("losses", 0)
    win_rate = (wins / total_alerts * 100) if total_alerts > 0 else 0
    avg_return = results.get("avg_return", 0)

    color = COLOR_BULLISH if avg_return > 0 else COLOR_BEARISH

    fields = [
        {
            "name": "Total Alerts",
            "value": str(total_alerts),
            "inline": True,
        },
        {
            "name": "Win Rate",
            "value": f"{win_rate:.1f}%",
            "inline": True,
        },
        {
            "name": "Avg Return",
            "value": f"{avg_return:+.2f}%",
            "inline": True,
        },
        {
            "name": "Wins",
            "value": str(wins),
            "inline": True,
        },
        {
            "name": "Losses",
            "value": str(losses),
            "inline": True,
        },
    ]

    # Add best/worst trade
    best_return = results.get("best_return")
    if best_return:
        fields.append(
            {
                "name": "Best Trade",
                "value": f"{best_return:+.2f}%",
                "inline": True,
            }
        )

    worst_return = results.get("worst_return")
    if worst_return:
        fields.append(
            {
                "name": "Worst Trade",
                "value": f"{worst_return:+.2f}%",
                "inline": True,
            }
        )

    embed = {
        "title": f"{ticker} - Backtest Results",
        "description": f"Analysis of past {days} days",
        "color": color,
        "fields": fields,
        "footer": {"text": "Past performance does not guarantee future results"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "embeds": [embed],
        },
    }


def create_sentiment_embed(
    ticker: str,
    sentiment_score: float,
    news_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Create an embed for sentiment analysis.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    sentiment_score : float
        Sentiment score (-1 to 1)
    news_items : List[Dict[str, Any]]
        Recent news items

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    # Determine sentiment label and color
    if sentiment_score > 0.3:
        sentiment_label = "Bullish"
        color = COLOR_BULLISH
    elif sentiment_score < -0.3:
        sentiment_label = "Bearish"
        color = COLOR_BEARISH
    else:
        sentiment_label = "Neutral"
        color = COLOR_NEUTRAL

    # Create sentiment gauge (visual representation)
    gauge_length = 10
    filled = int((sentiment_score + 1) / 2 * gauge_length)
    gauge = "█" * filled + "░" * (gauge_length - filled)

    fields = [
        {
            "name": "Sentiment Score",
            "value": f"{sentiment_score:.2f}",
            "inline": True,
        },
        {
            "name": "Classification",
            "value": sentiment_label,
            "inline": True,
        },
        {
            "name": "Gauge",
            "value": f"`{gauge}`",
            "inline": False,
        },
    ]

    # Add recent news
    if news_items:
        news_text = ""
        for i, item in enumerate(news_items[:3], 1):  # Show up to 3 items
            title = item.get("title", "")[:80]  # Truncate long titles
            source = item.get("source", "Unknown")
            news_text += f"{i}. **{title}** - {source}\n"

        fields.append(
            {
                "name": "Recent News",
                "value": news_text,
                "inline": False,
            }
        )
    else:
        fields.append(
            {
                "name": "Recent News",
                "value": "No recent news found",
                "inline": False,
            }
        )

    embed = {
        "title": f"{ticker} - Sentiment Analysis",
        "description": f"Current sentiment: **{sentiment_label}**",
        "color": color,
        "fields": fields,
        "footer": {"text": "Based on recent news and social sentiment"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "embeds": [embed],
        },
    }


def create_help_embed(commands_help: str) -> Dict[str, Any]:
    """
    Create an embed for the help command.

    Parameters
    ----------
    commands_help : str
        Formatted help text

    Returns
    -------
    Dict[str, Any]
        Discord interaction response
    """
    embed = {
        "title": "Catalyst-Bot Commands",
        "description": "Here are all available slash commands:",
        "color": COLOR_INFO,
        "fields": [
            {
                "name": "/chart",
                "value": "Generate a price chart for any ticker with customizable timeframes",
                "inline": False,
            },
            {
                "name": "/watchlist",
                "value": "Manage your personal watchlist (add, remove, list, clear)",
                "inline": False,
            },
            {
                "name": "/stats",
                "value": "View bot performance statistics and metrics",
                "inline": False,
            },
            {
                "name": "/backtest",
                "value": "Run a backtest on historical alerts for any ticker",
                "inline": False,
            },
            {
                "name": "/sentiment",
                "value": "Get current sentiment analysis for a ticker",
                "inline": False,
            },
            {
                "name": "/help",
                "value": "Show this help message",
                "inline": False,
            },
        ],
        "footer": {"text": "Type any command to see available options"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "type": RESPONSE_TYPE_CHANNEL_MESSAGE,
        "data": {
            "embeds": [embed],
            "flags": 64,  # EPHEMERAL
        },
    }
