"""
Trade Notification Manager
===========================

Manages Discord thread-based notifications for paper trading activity.
Integrates with the position management system to post entry/exit embeds.

This module bridges:
- Alert system (discord_message_id from sent alerts)
- Position management (open/close events)
- Discord threads (trade update notifications)

Usage:
    from catalyst_bot.trade_notifications import TradeNotificationManager

    # Initialize
    manager = TradeNotificationManager()

    # When a trade opens from an alert
    await manager.notify_trade_entry(
        alert_id="aid:abc123",
        position_id="pos-uuid-here",
        ticker="AAPL",
        side="BUY",
        quantity=100,
        entry_price=150.25,
        stop_loss=145.00,
        take_profit=160.00,
    )

    # When the trade closes
    await manager.notify_trade_exit(
        position_id="pos-uuid-here",
        exit_price=158.50,
        realized_pnl=825.00,
        realized_pnl_pct=5.5,
        hold_duration_seconds=14400,
        exit_reason="take_profit",
    )

Environment Variables:
    DISCORD_BOT_TOKEN - Required for thread creation
    DISCORD_TRADE_NOTIFICATIONS - Set to "1" to enable
    FEEDBACK_DB_PATH - Path to feedback database (default: data/feedback/alert_performance.db)
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .discord_threads import (
    create_trade_thread,
    send_trade_entry_embed,
    send_trade_exit_embed,
)
from .logging_utils import get_logger

log = get_logger("trade_notifications")

# Default database path (same as feedback database)
DEFAULT_DB_PATH = Path("data/feedback/alert_performance.db")


@dataclass
class AlertDiscordInfo:
    """Discord message info for an alert."""

    alert_id: str
    message_id: str
    channel_id: str
    thread_id: Optional[str] = None


@dataclass
class TradeNotification:
    """Trade notification record."""

    id: int
    alert_id: str
    position_id: str
    thread_id: str
    ticker: str
    side: str
    quantity: int
    entry_price: float
    exit_price: Optional[float]
    realized_pnl: Optional[float]
    realized_pnl_pct: Optional[float]
    entry_message_id: Optional[str]
    exit_message_id: Optional[str]
    entry_notified_at: int
    exit_notified_at: Optional[int]
    status: str


class TradeNotificationManager:
    """
    Manages Discord trade notifications with thread support.

    Responsibilities:
    - Look up Discord message info for alerts
    - Create threads under alert messages for trade updates
    - Post entry/exit embeds to threads
    - Track notification status in database
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the trade notification manager.

        Parameters
        ----------
        db_path : Path, optional
            Path to the feedback database. Defaults to FEEDBACK_DB_PATH env var
            or data/feedback/alert_performance.db
        """
        if db_path is None:
            db_path_str = os.getenv("FEEDBACK_DB_PATH", str(DEFAULT_DB_PATH))
            db_path = Path(db_path_str).resolve()

        self.db_path = db_path
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Ensure required tables exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Check if trade_notifications table exists
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='trade_notifications'
                """
            )
            if not cursor.fetchone():
                log.warning(
                    "trade_notifications_table_missing run_migration_004 to create"
                )

            # Check if alert_performance has discord columns
            cursor.execute("PRAGMA table_info(alert_performance)")
            columns = {row[1] for row in cursor.fetchall()}

            if "discord_message_id" not in columns:
                log.warning(
                    "discord_columns_missing run_migration_004 to add discord tracking"
                )

        finally:
            conn.close()

    def _is_enabled(self) -> bool:
        """Check if trade notifications are enabled."""
        return os.getenv("DISCORD_TRADE_NOTIFICATIONS", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def get_alert_discord_info(self, alert_id: str) -> Optional[AlertDiscordInfo]:
        """
        Get Discord message info for an alert.

        Parameters
        ----------
        alert_id : str
            The alert ID to look up

        Returns
        -------
        AlertDiscordInfo or None
            Discord message/channel/thread IDs if found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT alert_id, discord_message_id, discord_channel_id, discord_thread_id
                FROM alert_performance
                WHERE alert_id = ?
                """,
                (alert_id,),
            )
            row = cursor.fetchone()

            if row and row["discord_message_id"]:
                return AlertDiscordInfo(
                    alert_id=row["alert_id"],
                    message_id=row["discord_message_id"],
                    channel_id=row["discord_channel_id"],
                    thread_id=row["discord_thread_id"],
                )
            return None
        finally:
            conn.close()

    def save_thread_id(self, alert_id: str, thread_id: str) -> None:
        """
        Save thread ID for an alert.

        Parameters
        ----------
        alert_id : str
            The alert ID
        thread_id : str
            The Discord thread ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alert_performance
                SET discord_thread_id = ?
                WHERE alert_id = ?
                """,
                (thread_id, alert_id),
            )
            conn.commit()
            log.info("thread_id_saved alert_id=%s thread_id=%s", alert_id, thread_id)
        finally:
            conn.close()

    def save_trade_notification(
        self,
        alert_id: str,
        position_id: str,
        thread_id: str,
        ticker: str,
        side: str,
        quantity: int,
        entry_price: float,
        entry_message_id: Optional[str] = None,
    ) -> int:
        """
        Save a trade notification record.

        Returns
        -------
        int
            The notification ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trade_notifications (
                    alert_id, position_id, thread_id, ticker, side, quantity,
                    entry_price, entry_message_id, entry_notified_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                ON CONFLICT(alert_id, position_id) DO UPDATE SET
                    entry_message_id = excluded.entry_message_id,
                    entry_notified_at = excluded.entry_notified_at
                """,
                (
                    alert_id,
                    position_id,
                    thread_id,
                    ticker,
                    side,
                    quantity,
                    float(entry_price),
                    entry_message_id,
                    int(time.time()),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def get_trade_notification(self, position_id: str) -> Optional[TradeNotification]:
        """
        Get trade notification by position ID.

        Parameters
        ----------
        position_id : str
            The position ID to look up

        Returns
        -------
        TradeNotification or None
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM trade_notifications
                WHERE position_id = ?
                """,
                (position_id,),
            )
            row = cursor.fetchone()

            if row:
                return TradeNotification(
                    id=row["id"],
                    alert_id=row["alert_id"],
                    position_id=row["position_id"],
                    thread_id=row["thread_id"],
                    ticker=row["ticker"],
                    side=row["side"],
                    quantity=row["quantity"],
                    entry_price=row["entry_price"],
                    exit_price=row["exit_price"],
                    realized_pnl=row["realized_pnl"],
                    realized_pnl_pct=row["realized_pnl_pct"],
                    entry_message_id=row["entry_message_id"],
                    exit_message_id=row["exit_message_id"],
                    entry_notified_at=row["entry_notified_at"],
                    exit_notified_at=row["exit_notified_at"],
                    status=row["status"],
                )
            return None
        finally:
            conn.close()

    def update_trade_exit(
        self,
        position_id: str,
        exit_price: float,
        realized_pnl: float,
        realized_pnl_pct: float,
        exit_message_id: Optional[str] = None,
    ) -> None:
        """Update trade notification with exit info."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE trade_notifications
                SET exit_price = ?,
                    realized_pnl = ?,
                    realized_pnl_pct = ?,
                    exit_message_id = ?,
                    exit_notified_at = ?,
                    status = 'closed'
                WHERE position_id = ?
                """,
                (
                    float(exit_price),
                    float(realized_pnl),
                    float(realized_pnl_pct),
                    exit_message_id,
                    int(time.time()),
                    position_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def notify_trade_entry(
        self,
        alert_id: str,
        position_id: str,
        ticker: str,
        side: str,
        quantity: int,
        entry_price: float | Decimal,
        stop_loss: Optional[float | Decimal] = None,
        take_profit: Optional[float | Decimal] = None,
        strategy: Optional[str] = None,
        signal_confidence: Optional[float] = None,
        alert_headline: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send trade entry notification to Discord thread.

        Creates a thread under the original alert message if one doesn't exist,
        then posts the trade entry embed.

        Parameters
        ----------
        alert_id : str
            The alert ID that triggered this trade
        position_id : str
            Unique position identifier
        ticker : str
            Stock symbol
        side : str
            Trade side ("BUY" or "SELL")
        quantity : int
            Number of shares
        entry_price : float or Decimal
            Entry price per share
        stop_loss : float or Decimal, optional
            Stop loss price
        take_profit : float or Decimal, optional
            Take profit target
        strategy : str, optional
            Strategy name
        signal_confidence : float, optional
            ML model confidence
        alert_headline : str, optional
            Original alert headline

        Returns
        -------
        str or None
            Entry message ID if posted, None if disabled or failed
        """
        if not self._is_enabled():
            log.debug("trade_notifications_disabled skipping_entry alert_id=%s", alert_id)
            return None

        # Get Discord info for this alert
        discord_info = self.get_alert_discord_info(alert_id)
        if not discord_info:
            log.warning(
                "no_discord_info_for_alert alert_id=%s cannot_create_thread", alert_id
            )
            return None

        # Create thread if it doesn't exist
        thread_id = discord_info.thread_id
        if not thread_id:
            log.info(
                "creating_trade_thread alert_id=%s ticker=%s",
                alert_id,
                ticker,
            )
            thread_id = await create_trade_thread(
                channel_id=discord_info.channel_id,
                message_id=discord_info.message_id,
                ticker=ticker,
            )
            if thread_id:
                self.save_thread_id(alert_id, thread_id)
            else:
                log.error("failed_to_create_thread alert_id=%s", alert_id)
                return None

        # Send entry embed
        entry_message_id = await send_trade_entry_embed(
            thread_id=thread_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            signal_confidence=signal_confidence,
            alert_headline=alert_headline,
        )

        # Save notification record
        if entry_message_id:
            self.save_trade_notification(
                alert_id=alert_id,
                position_id=position_id,
                thread_id=thread_id,
                ticker=ticker,
                side=side,
                quantity=quantity,
                entry_price=float(entry_price),
                entry_message_id=entry_message_id,
            )
            log.info(
                "trade_entry_notified alert_id=%s position_id=%s ticker=%s",
                alert_id,
                position_id,
                ticker,
            )

        return entry_message_id

    async def notify_trade_exit(
        self,
        position_id: str,
        exit_price: float | Decimal,
        realized_pnl: float | Decimal,
        realized_pnl_pct: float | Decimal,
        hold_duration_seconds: int,
        exit_reason: str,
        max_gain_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
    ) -> Optional[str]:
        """
        Send trade exit notification to Discord thread.

        Looks up the trade notification record and posts exit embed to the same thread.

        Parameters
        ----------
        position_id : str
            Position identifier (must match entry notification)
        exit_price : float or Decimal
            Exit price per share
        realized_pnl : float or Decimal
            Realized profit/loss in dollars
        realized_pnl_pct : float or Decimal
            Realized P&L as percentage
        hold_duration_seconds : int
            How long position was held
        exit_reason : str
            Why position was closed
        max_gain_pct : float, optional
            Maximum unrealized gain during trade
        max_drawdown_pct : float, optional
            Maximum unrealized loss during trade

        Returns
        -------
        str or None
            Exit message ID if posted, None if disabled or failed
        """
        if not self._is_enabled():
            log.debug("trade_notifications_disabled skipping_exit position_id=%s", position_id)
            return None

        # Get trade notification record
        notif = self.get_trade_notification(position_id)
        if not notif:
            log.warning(
                "no_entry_notification_found position_id=%s cannot_post_exit",
                position_id,
            )
            return None

        # Send exit embed to same thread
        exit_message_id = await send_trade_exit_embed(
            thread_id=notif.thread_id,
            ticker=notif.ticker,
            side=notif.side,
            quantity=notif.quantity,
            entry_price=notif.entry_price,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            hold_duration_seconds=hold_duration_seconds,
            exit_reason=exit_reason,
            max_gain_pct=max_gain_pct,
            max_drawdown_pct=max_drawdown_pct,
        )

        # Update notification record
        if exit_message_id:
            self.update_trade_exit(
                position_id=position_id,
                exit_price=float(exit_price),
                realized_pnl=float(realized_pnl),
                realized_pnl_pct=float(realized_pnl_pct),
                exit_message_id=exit_message_id,
            )
            log.info(
                "trade_exit_notified position_id=%s pnl=%.2f pnl_pct=%.2f%%",
                position_id,
                float(realized_pnl),
                float(realized_pnl_pct),
            )

        return exit_message_id

    def get_open_notifications(self, limit: int = 100) -> list[TradeNotification]:
        """Get all open trade notifications (positions without exit)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM trade_notifications
                WHERE status = 'open'
                ORDER BY entry_notified_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

            return [
                TradeNotification(
                    id=row["id"],
                    alert_id=row["alert_id"],
                    position_id=row["position_id"],
                    thread_id=row["thread_id"],
                    ticker=row["ticker"],
                    side=row["side"],
                    quantity=row["quantity"],
                    entry_price=row["entry_price"],
                    exit_price=row["exit_price"],
                    realized_pnl=row["realized_pnl"],
                    realized_pnl_pct=row["realized_pnl_pct"],
                    entry_message_id=row["entry_message_id"],
                    exit_message_id=row["exit_message_id"],
                    entry_notified_at=row["entry_notified_at"],
                    exit_notified_at=row["exit_notified_at"],
                    status=row["status"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_notification_stats(self) -> dict:
        """Get notification statistics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Total counts
            cursor.execute("SELECT COUNT(*) FROM trade_notifications")
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM trade_notifications WHERE status = 'open'"
            )
            open_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM trade_notifications WHERE status = 'closed'"
            )
            closed_count = cursor.fetchone()[0]

            # P&L stats for closed trades
            cursor.execute(
                """
                SELECT
                    COUNT(*) as trades,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl_pct) as avg_pnl_pct,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses
                FROM trade_notifications
                WHERE status = 'closed' AND realized_pnl IS NOT NULL
                """
            )
            pnl_row = cursor.fetchone()

            return {
                "total_notifications": total,
                "open_positions": open_count,
                "closed_positions": closed_count,
                "total_pnl": pnl_row[1] or 0,
                "avg_pnl_pct": pnl_row[2] or 0,
                "wins": pnl_row[3] or 0,
                "losses": pnl_row[4] or 0,
                "win_rate": (
                    (pnl_row[3] / pnl_row[0] * 100) if pnl_row[0] else 0
                ),
            }
        finally:
            conn.close()


# Singleton instance for convenience
_manager: Optional[TradeNotificationManager] = None


def get_notification_manager() -> TradeNotificationManager:
    """Get or create the singleton notification manager."""
    global _manager
    if _manager is None:
        _manager = TradeNotificationManager()
    return _manager


# ============================================================================
# Integration with Position Manager
# ============================================================================
#
# Add these hooks to src/catalyst_bot/portfolio/position_manager.py:
#
# At the end of open_position():
#
#     # Notify Discord (async)
#     if signal_id:  # Only for signal-triggered trades
#         from ..trade_notifications import get_notification_manager
#         import asyncio
#
#         manager = get_notification_manager()
#         asyncio.create_task(
#             manager.notify_trade_entry(
#                 alert_id=signal_id,  # signal_id should be the alert_id
#                 position_id=position.position_id,
#                 ticker=position.ticker,
#                 side=position.side.value,
#                 quantity=position.quantity,
#                 entry_price=position.entry_price,
#                 stop_loss=position.stop_loss_price,
#                 take_profit=position.take_profit_price,
#                 strategy=position.strategy,
#             )
#         )
#
# At the end of close_position():
#
#     # Notify Discord (async)
#     from ..trade_notifications import get_notification_manager
#     import asyncio
#
#     manager = get_notification_manager()
#     asyncio.create_task(
#         manager.notify_trade_exit(
#             position_id=closed.position_id,
#             exit_price=closed.exit_price,
#             realized_pnl=closed.realized_pnl,
#             realized_pnl_pct=closed.realized_pnl_pct,
#             hold_duration_seconds=closed.hold_duration_seconds,
#             exit_reason=closed.exit_reason,
#         )
#     )
# ============================================================================
