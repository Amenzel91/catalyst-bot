"""
Discord Thread Management for Trade Notifications
==================================================

Creates and manages Discord threads for paper trading updates.
Threads are created under original alert messages to keep channels clean.

Usage:
    from catalyst_bot.discord_threads import (
        create_trade_thread,
        post_to_thread,
        send_trade_entry_embed,
        send_trade_exit_embed,
    )

    # Create thread under an alert message
    thread_id = await create_trade_thread(
        channel_id="123456789",
        message_id="987654321",
        ticker="AAPL",
    )

    # Post trade entry
    await send_trade_entry_embed(
        thread_id=thread_id,
        ticker="AAPL",
        side="BUY",
        quantity=100,
        entry_price=150.25,
        stop_loss=145.00,
        take_profit=160.00,
    )

    # Post trade exit
    await send_trade_exit_embed(
        thread_id=thread_id,
        ticker="AAPL",
        side="SELL",
        quantity=100,
        entry_price=150.25,
        exit_price=158.50,
        realized_pnl=825.00,
        realized_pnl_pct=5.5,
        hold_duration_minutes=240,
        exit_reason="take_profit",
    )

Environment Variables:
    DISCORD_BOT_TOKEN - Required for thread creation (Bot API)
    DISCORD_TRADE_NOTIFICATIONS - Set to "1" to enable (default: disabled)
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

import aiohttp

from .logging_utils import get_logger

log = get_logger("discord_threads")

# Discord API base URL
DISCORD_API_BASE = "https://discord.com/api/v10"

# Embed colors matching existing system (from commands/embeds.py)
COLOR_BULLISH = 0x2ECC71  # Green - profitable trades
COLOR_BEARISH = 0xE74C3C  # Red - losing trades
COLOR_NEUTRAL = 0x3498DB  # Blue - trade entry
COLOR_WARNING = 0xF39C12  # Yellow - stop loss hit


def _is_enabled() -> bool:
    """Check if trade notifications are enabled."""
    return os.getenv("DISCORD_TRADE_NOTIFICATIONS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_bot_token() -> Optional[str]:
    """Get Discord bot token from environment."""
    return os.getenv("DISCORD_BOT_TOKEN")


async def create_trade_thread(
    channel_id: str,
    message_id: str,
    ticker: str,
    *,
    auto_archive_duration: int = 1440,  # 24 hours
) -> Optional[str]:
    """
    Create a Discord thread under an alert message for trade updates.

    Parameters
    ----------
    channel_id : str
        The channel where the original alert was posted
    message_id : str
        The message ID of the original alert (thread parent)
    ticker : str
        Stock ticker symbol for thread name
    auto_archive_duration : int
        Minutes until thread auto-archives (60, 1440, 4320, 10080)
        Default: 1440 (24 hours)

    Returns
    -------
    str or None
        Thread ID if created successfully, None on failure

    Notes
    -----
    Discord API endpoint: POST /channels/{channel_id}/messages/{message_id}/threads
    Requires bot token with MANAGE_THREADS permission.
    """
    if not _is_enabled():
        log.debug("trade_notifications_disabled skipping_thread_creation")
        return None

    bot_token = _get_bot_token()
    if not bot_token:
        log.warning("discord_bot_token_missing cannot_create_thread")
        return None

    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/threads"

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "name": f"📈 Paper Trade: {ticker}",
        "auto_archive_duration": auto_archive_duration,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    thread_id = data.get("id")
                    log.info(
                        "thread_created thread_id=%s ticker=%s parent_msg=%s",
                        thread_id,
                        ticker,
                        message_id,
                    )
                    return thread_id
                else:
                    error_text = await resp.text()
                    log.error(
                        "thread_creation_failed status=%d error=%s",
                        resp.status,
                        error_text[:200],
                    )
                    return None
    except Exception as e:
        log.error("thread_creation_exception err=%s", str(e))
        return None


async def post_to_thread(
    thread_id: str,
    embed: Dict[str, Any],
    *,
    content: Optional[str] = None,
) -> Optional[str]:
    """
    Post an embed to a Discord thread.

    Parameters
    ----------
    thread_id : str
        The thread ID to post to
    embed : dict
        Discord embed object
    content : str, optional
        Optional text content alongside embed

    Returns
    -------
    str or None
        Message ID if posted successfully, None on failure
    """
    if not _is_enabled():
        return None

    bot_token = _get_bot_token()
    if not bot_token:
        log.warning("discord_bot_token_missing cannot_post_to_thread")
        return None

    url = f"{DISCORD_API_BASE}/channels/{thread_id}/messages"

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {"embeds": [embed]}
    if content:
        payload["content"] = content

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    message_id = data.get("id")
                    log.info("thread_message_posted thread=%s msg=%s", thread_id, message_id)
                    return message_id
                else:
                    error_text = await resp.text()
                    log.error(
                        "thread_post_failed status=%d thread=%s error=%s",
                        resp.status,
                        thread_id,
                        error_text[:200],
                    )
                    return None
    except Exception as e:
        log.error("thread_post_exception thread=%s err=%s", thread_id, str(e))
        return None


def build_trade_entry_embed(
    ticker: str,
    side: str,
    quantity: int,
    entry_price: float | Decimal,
    stop_loss: Optional[float | Decimal] = None,
    take_profit: Optional[float | Decimal] = None,
    strategy: Optional[str] = None,
    signal_confidence: Optional[float] = None,
    alert_headline: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a Discord embed for trade entry notification.

    Parameters
    ----------
    ticker : str
        Stock symbol
    side : str
        Trade side ("BUY" or "SELL"/"SHORT")
    quantity : int
        Number of shares
    entry_price : float or Decimal
        Entry price per share
    stop_loss : float or Decimal, optional
        Stop loss price
    take_profit : float or Decimal, optional
        Take profit target
    strategy : str, optional
        Strategy name that triggered the trade
    signal_confidence : float, optional
        ML model confidence (0-1)
    alert_headline : str, optional
        Original alert headline

    Returns
    -------
    dict
        Discord embed object ready for posting
    """
    entry_price = float(entry_price)
    position_value = quantity * entry_price

    # Determine emoji and color based on side
    if side.upper() in ("BUY", "LONG"):
        side_emoji = "🟢"
        side_text = "LONG"
    else:
        side_emoji = "🔴"
        side_text = "SHORT"

    embed = {
        "title": f"{side_emoji} Trade Entry: {ticker}",
        "color": COLOR_NEUTRAL,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [
            {
                "name": "📊 Position",
                "value": f"**{side_text}** {quantity:,} shares",
                "inline": True,
            },
            {
                "name": "💰 Entry Price",
                "value": f"${entry_price:,.2f}",
                "inline": True,
            },
            {
                "name": "💵 Position Value",
                "value": f"${position_value:,.2f}",
                "inline": True,
            },
        ],
        "footer": {
            "text": "Paper Trading • Entry Notification",
        },
    }

    # Add stop loss and take profit if provided
    if stop_loss is not None:
        stop_loss = float(stop_loss)
        risk_pct = abs((stop_loss - entry_price) / entry_price * 100)
        embed["fields"].append({
            "name": "🛑 Stop Loss",
            "value": f"${stop_loss:,.2f} ({risk_pct:.1f}% risk)",
            "inline": True,
        })

    if take_profit is not None:
        take_profit = float(take_profit)
        reward_pct = abs((take_profit - entry_price) / entry_price * 100)
        embed["fields"].append({
            "name": "🎯 Take Profit",
            "value": f"${take_profit:,.2f} ({reward_pct:.1f}% reward)",
            "inline": True,
        })

    # Calculate R:R ratio if both provided
    if stop_loss is not None and take_profit is not None:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk > 0:
            rr_ratio = reward / risk
            embed["fields"].append({
                "name": "⚖️ Risk/Reward",
                "value": f"1:{rr_ratio:.1f}",
                "inline": True,
            })

    # Add strategy if provided
    if strategy:
        embed["fields"].append({
            "name": "🤖 Strategy",
            "value": strategy,
            "inline": True,
        })

    # Add confidence if provided
    if signal_confidence is not None:
        conf_pct = signal_confidence * 100
        conf_bar = "█" * int(conf_pct / 10) + "░" * (10 - int(conf_pct / 10))
        embed["fields"].append({
            "name": "📈 Signal Confidence",
            "value": f"{conf_bar} {conf_pct:.0f}%",
            "inline": True,
        })

    # Add alert headline as description if provided
    if alert_headline:
        embed["description"] = f"*{alert_headline[:200]}*"

    return embed


def build_trade_exit_embed(
    ticker: str,
    side: str,
    quantity: int,
    entry_price: float | Decimal,
    exit_price: float | Decimal,
    realized_pnl: float | Decimal,
    realized_pnl_pct: float | Decimal,
    hold_duration_seconds: int,
    exit_reason: str,
    max_gain_pct: Optional[float] = None,
    max_drawdown_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build a Discord embed for trade exit notification.

    Parameters
    ----------
    ticker : str
        Stock symbol
    side : str
        Original trade side ("BUY"/"LONG" or "SELL"/"SHORT")
    quantity : int
        Number of shares closed
    entry_price : float or Decimal
        Original entry price
    exit_price : float or Decimal
        Exit price per share
    realized_pnl : float or Decimal
        Realized profit/loss in dollars
    realized_pnl_pct : float or Decimal
        Realized P&L as percentage
    hold_duration_seconds : int
        How long position was held
    exit_reason : str
        Why position was closed (stop_loss, take_profit, manual, timeout)
    max_gain_pct : float, optional
        Maximum unrealized gain during trade
    max_drawdown_pct : float, optional
        Maximum unrealized loss during trade

    Returns
    -------
    dict
        Discord embed object ready for posting
    """
    entry_price = float(entry_price)
    exit_price = float(exit_price)
    realized_pnl = float(realized_pnl)
    realized_pnl_pct = float(realized_pnl_pct)

    # Determine if profitable
    is_profitable = realized_pnl >= 0

    # Choose color and emoji based on outcome
    if is_profitable:
        if realized_pnl_pct >= 5:
            color = COLOR_BULLISH
            result_emoji = "🚀"
            result_text = "BIG WIN"
        elif realized_pnl_pct >= 1:
            color = COLOR_BULLISH
            result_emoji = "✅"
            result_text = "WIN"
        else:
            color = COLOR_BULLISH
            result_emoji = "📈"
            result_text = "SMALL WIN"
    else:
        if realized_pnl_pct <= -5:
            color = COLOR_BEARISH
            result_emoji = "💔"
            result_text = "BIG LOSS"
        elif realized_pnl_pct <= -1:
            color = COLOR_BEARISH
            result_emoji = "❌"
            result_text = "LOSS"
        else:
            color = COLOR_WARNING
            result_emoji = "📉"
            result_text = "SMALL LOSS"

    # Exit reason emoji
    exit_emojis = {
        "stop_loss": "🛑",
        "take_profit": "🎯",
        "manual": "👤",
        "timeout": "⏰",
        "signal": "📊",
    }
    exit_emoji = exit_emojis.get(exit_reason.lower(), "📤")

    # Format hold duration
    hours, remainder = divmod(hold_duration_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        duration_str = f"{hours}h {minutes}m"
    elif minutes > 0:
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = f"{seconds}s"

    # P&L formatting with sign
    pnl_sign = "+" if realized_pnl >= 0 else ""
    pnl_pct_sign = "+" if realized_pnl_pct >= 0 else ""

    embed = {
        "title": f"{result_emoji} Trade Exit: {ticker} - {result_text}",
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [
            {
                "name": "💵 Realized P&L",
                "value": f"**{pnl_sign}${realized_pnl:,.2f}** ({pnl_pct_sign}{realized_pnl_pct:.2f}%)",
                "inline": True,
            },
            {
                "name": f"{exit_emoji} Exit Reason",
                "value": exit_reason.replace("_", " ").title(),
                "inline": True,
            },
            {
                "name": "⏱️ Hold Duration",
                "value": duration_str,
                "inline": True,
            },
            {
                "name": "📥 Entry",
                "value": f"${entry_price:,.2f}",
                "inline": True,
            },
            {
                "name": "📤 Exit",
                "value": f"${exit_price:,.2f}",
                "inline": True,
            },
            {
                "name": "📊 Shares",
                "value": f"{quantity:,}",
                "inline": True,
            },
        ],
        "footer": {
            "text": "Paper Trading • Exit Notification",
        },
    }

    # Add max gain/drawdown if provided (shows trade quality)
    if max_gain_pct is not None:
        embed["fields"].append({
            "name": "📈 Max Unrealized Gain",
            "value": f"+{max_gain_pct:.2f}%",
            "inline": True,
        })

    if max_drawdown_pct is not None:
        embed["fields"].append({
            "name": "📉 Max Drawdown",
            "value": f"{max_drawdown_pct:.2f}%",
            "inline": True,
        })

    return embed


async def send_trade_entry_embed(
    thread_id: str,
    ticker: str,
    side: str,
    quantity: int,
    entry_price: float | Decimal,
    **kwargs,
) -> Optional[str]:
    """
    Send a trade entry notification to a Discord thread.

    Convenience wrapper around build_trade_entry_embed + post_to_thread.

    Parameters
    ----------
    thread_id : str
        Thread ID to post to
    ticker : str
        Stock symbol
    side : str
        Trade side ("BUY" or "SELL")
    quantity : int
        Number of shares
    entry_price : float or Decimal
        Entry price
    **kwargs
        Additional arguments passed to build_trade_entry_embed
        (stop_loss, take_profit, strategy, signal_confidence, alert_headline)

    Returns
    -------
    str or None
        Message ID if posted successfully
    """
    embed = build_trade_entry_embed(
        ticker=ticker,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        **kwargs,
    )
    return await post_to_thread(thread_id, embed)


async def send_trade_exit_embed(
    thread_id: str,
    ticker: str,
    side: str,
    quantity: int,
    entry_price: float | Decimal,
    exit_price: float | Decimal,
    realized_pnl: float | Decimal,
    realized_pnl_pct: float | Decimal,
    hold_duration_seconds: int,
    exit_reason: str,
    **kwargs,
) -> Optional[str]:
    """
    Send a trade exit notification to a Discord thread.

    Convenience wrapper around build_trade_exit_embed + post_to_thread.

    Parameters
    ----------
    thread_id : str
        Thread ID to post to
    ticker : str
        Stock symbol
    side : str
        Original trade side
    quantity : int
        Number of shares closed
    entry_price : float or Decimal
        Original entry price
    exit_price : float or Decimal
        Exit price
    realized_pnl : float or Decimal
        Realized P&L in dollars
    realized_pnl_pct : float or Decimal
        Realized P&L percentage
    hold_duration_seconds : int
        How long position was held
    exit_reason : str
        Why position was closed
    **kwargs
        Additional arguments (max_gain_pct, max_drawdown_pct)

    Returns
    -------
    str or None
        Message ID if posted successfully
    """
    embed = build_trade_exit_embed(
        ticker=ticker,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_pnl=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        hold_duration_seconds=hold_duration_seconds,
        exit_reason=exit_reason,
        **kwargs,
    )
    return await post_to_thread(thread_id, embed)


# ============================================================================
# Database Schema Extension for Discord Message Tracking
# ============================================================================
#
# To enable thread-based trade notifications, add these columns to the
# alert_performance table (or create a new alert_discord_mapping table):
#
# ALTER TABLE alert_performance ADD COLUMN discord_message_id TEXT;
# ALTER TABLE alert_performance ADD COLUMN discord_channel_id TEXT;
# ALTER TABLE alert_performance ADD COLUMN discord_thread_id TEXT;
#
# Or create a new mapping table:
#
# CREATE TABLE alert_discord_mapping (
#     alert_id TEXT PRIMARY KEY,
#     discord_message_id TEXT NOT NULL,
#     discord_channel_id TEXT NOT NULL,
#     discord_thread_id TEXT,
#     created_at INTEGER NOT NULL,
#     FOREIGN KEY (alert_id) REFERENCES alert_performance(alert_id)
# );
#
# CREATE INDEX idx_alert_discord_message ON alert_discord_mapping(discord_message_id);
# ============================================================================


# ============================================================================
# Integration Example
# ============================================================================
#
# In your paper trading workflow:
#
# 1. When alert triggers a trade:
#
#    async def on_trade_signal(alert_id: str, signal: TradingSignal):
#        # Get Discord message info for this alert
#        mapping = get_alert_discord_mapping(alert_id)
#
#        # Create thread if doesn't exist
#        if mapping and not mapping.thread_id:
#            thread_id = await create_trade_thread(
#                channel_id=mapping.channel_id,
#                message_id=mapping.message_id,
#                ticker=signal.ticker,
#            )
#            save_thread_id(alert_id, thread_id)
#
#        # Post entry notification
#        await send_trade_entry_embed(
#            thread_id=thread_id,
#            ticker=signal.ticker,
#            side=signal.action,
#            quantity=position.quantity,
#            entry_price=position.entry_price,
#            stop_loss=signal.stop_loss_price,
#            take_profit=signal.take_profit_price,
#            strategy=signal.strategy,
#        )
#
# 2. When position closes:
#
#    async def on_position_closed(closed: ClosedPosition):
#        mapping = get_alert_discord_mapping(closed.signal_id)
#
#        if mapping and mapping.thread_id:
#            await send_trade_exit_embed(
#                thread_id=mapping.thread_id,
#                ticker=closed.ticker,
#                side=closed.side.value,
#                quantity=closed.quantity,
#                entry_price=closed.entry_price,
#                exit_price=closed.exit_price,
#                realized_pnl=closed.realized_pnl,
#                realized_pnl_pct=closed.realized_pnl_pct,
#                hold_duration_seconds=closed.hold_duration_seconds,
#                exit_reason=closed.exit_reason,
#            )
# ============================================================================
