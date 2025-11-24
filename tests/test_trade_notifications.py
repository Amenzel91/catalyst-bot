"""
Tests for Discord Trade Notification System
============================================

Tests for:
- discord_threads.py - Thread creation and embed builders
- trade_notifications.py - Notification manager and database operations
"""

import os
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before imports
os.environ["DISCORD_TRADE_NOTIFICATIONS"] = "1"
os.environ["DISCORD_BOT_TOKEN"] = "test-token-for-testing"


class TestEmbedBuilders:
    """Test embed building functions."""

    def test_build_trade_entry_embed_basic(self):
        """Test basic trade entry embed creation."""
        from src.catalyst_bot.discord_threads import build_trade_entry_embed

        embed = build_trade_entry_embed(
            ticker="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.25,
        )

        assert embed["title"] == "🟢 Trade Entry: AAPL"
        assert embed["color"] == 0x3498DB  # COLOR_NEUTRAL (blue)
        assert len(embed["fields"]) >= 3

        # Check position field
        position_field = next(f for f in embed["fields"] if f["name"] == "📊 Position")
        assert "LONG" in position_field["value"]
        assert "100" in position_field["value"]

        # Check entry price field
        price_field = next(f for f in embed["fields"] if f["name"] == "💰 Entry Price")
        assert "$150.25" in price_field["value"]

    def test_build_trade_entry_embed_short(self):
        """Test short position entry embed."""
        from src.catalyst_bot.discord_threads import build_trade_entry_embed

        embed = build_trade_entry_embed(
            ticker="TSLA",
            side="SHORT",
            quantity=50,
            entry_price=200.00,
        )

        assert embed["title"] == "🔴 Trade Entry: TSLA"
        position_field = next(f for f in embed["fields"] if f["name"] == "📊 Position")
        assert "SHORT" in position_field["value"]

    def test_build_trade_entry_embed_with_stops(self):
        """Test entry embed with stop loss and take profit."""
        from src.catalyst_bot.discord_threads import build_trade_entry_embed

        embed = build_trade_entry_embed(
            ticker="NVDA",
            side="BUY",
            quantity=25,
            entry_price=500.00,
            stop_loss=475.00,
            take_profit=550.00,
        )

        field_names = [f["name"] for f in embed["fields"]]
        assert "🛑 Stop Loss" in field_names
        assert "🎯 Take Profit" in field_names
        assert "⚖️ Risk/Reward" in field_names

        # Check R:R calculation (risk=$25, reward=$50 -> 1:2)
        rr_field = next(f for f in embed["fields"] if f["name"] == "⚖️ Risk/Reward")
        assert "1:2.0" in rr_field["value"]

    def test_build_trade_entry_embed_with_strategy(self):
        """Test entry embed with strategy and confidence."""
        from src.catalyst_bot.discord_threads import build_trade_entry_embed

        embed = build_trade_entry_embed(
            ticker="AMD",
            side="BUY",
            quantity=100,
            entry_price=120.00,
            strategy="momentum_breakout",
            signal_confidence=0.85,
        )

        field_names = [f["name"] for f in embed["fields"]]
        assert "🤖 Strategy" in field_names
        assert "📈 Signal Confidence" in field_names

        conf_field = next(f for f in embed["fields"] if f["name"] == "📈 Signal Confidence")
        assert "85%" in conf_field["value"]

    def test_build_trade_exit_embed_profit(self):
        """Test profitable trade exit embed."""
        from src.catalyst_bot.discord_threads import build_trade_exit_embed

        embed = build_trade_exit_embed(
            ticker="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.00,
            exit_price=165.00,
            realized_pnl=1500.00,
            realized_pnl_pct=10.0,
            hold_duration_seconds=7200,  # 2 hours
            exit_reason="take_profit",
        )

        assert "BIG WIN" in embed["title"]
        assert embed["color"] == 0x2ECC71  # COLOR_BULLISH (green)

        pnl_field = next(f for f in embed["fields"] if f["name"] == "💵 Realized P&L")
        assert "+$1,500.00" in pnl_field["value"]
        assert "+10.00%" in pnl_field["value"]

        duration_field = next(f for f in embed["fields"] if f["name"] == "⏱️ Hold Duration")
        assert "2h" in duration_field["value"]

    def test_build_trade_exit_embed_loss(self):
        """Test losing trade exit embed."""
        from src.catalyst_bot.discord_threads import build_trade_exit_embed

        embed = build_trade_exit_embed(
            ticker="TSLA",
            side="BUY",
            quantity=50,
            entry_price=200.00,
            exit_price=180.00,
            realized_pnl=-1000.00,
            realized_pnl_pct=-10.0,
            hold_duration_seconds=3600,
            exit_reason="stop_loss",
        )

        assert "BIG LOSS" in embed["title"]
        assert embed["color"] == 0xE74C3C  # COLOR_BEARISH (red)

        pnl_field = next(f for f in embed["fields"] if f["name"] == "💵 Realized P&L")
        assert "-$1,000.00" in pnl_field["value"]
        assert "-10.00%" in pnl_field["value"]

    def test_build_trade_exit_embed_small_profit(self):
        """Test small profit trade exit embed."""
        from src.catalyst_bot.discord_threads import build_trade_exit_embed

        embed = build_trade_exit_embed(
            ticker="AMD",
            side="BUY",
            quantity=100,
            entry_price=100.00,
            exit_price=100.50,
            realized_pnl=50.00,
            realized_pnl_pct=0.5,
            hold_duration_seconds=300,  # 5 minutes
            exit_reason="manual",
        )

        assert "SMALL WIN" in embed["title"]

    def test_build_trade_exit_embed_duration_formats(self):
        """Test various duration formats."""
        from src.catalyst_bot.discord_threads import build_trade_exit_embed

        # Seconds only
        embed = build_trade_exit_embed(
            ticker="TEST",
            side="BUY",
            quantity=1,
            entry_price=100.00,
            exit_price=100.00,
            realized_pnl=0,
            realized_pnl_pct=0,
            hold_duration_seconds=45,
            exit_reason="manual",
        )
        duration_field = next(f for f in embed["fields"] if f["name"] == "⏱️ Hold Duration")
        assert "45s" in duration_field["value"]

        # Minutes and seconds
        embed = build_trade_exit_embed(
            ticker="TEST",
            side="BUY",
            quantity=1,
            entry_price=100.00,
            exit_price=100.00,
            realized_pnl=0,
            realized_pnl_pct=0,
            hold_duration_seconds=125,  # 2m 5s
            exit_reason="manual",
        )
        duration_field = next(f for f in embed["fields"] if f["name"] == "⏱️ Hold Duration")
        assert "2m" in duration_field["value"]


class TestTradeNotificationManager:
    """Test the TradeNotificationManager class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        # Create tables
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE alert_performance (
                id INTEGER PRIMARY KEY,
                alert_id TEXT UNIQUE NOT NULL,
                ticker TEXT NOT NULL,
                source TEXT NOT NULL,
                catalyst_type TEXT NOT NULL,
                keywords TEXT,
                posted_at INTEGER NOT NULL,
                posted_price REAL,
                discord_message_id TEXT,
                discord_channel_id TEXT,
                discord_thread_id TEXT,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE trade_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                entry_message_id TEXT,
                exit_message_id TEXT,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                realized_pnl REAL,
                realized_pnl_pct REAL,
                entry_notified_at INTEGER NOT NULL,
                exit_notified_at INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                UNIQUE(alert_id, position_id)
            )
            """
        )
        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        db_path.unlink(missing_ok=True)

    def test_manager_initialization(self, temp_db):
        """Test manager initialization."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        manager = TradeNotificationManager(db_path=temp_db)
        assert manager.db_path == temp_db

    def test_get_alert_discord_info(self, temp_db):
        """Test looking up Discord info for an alert."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        # Insert test alert
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            INSERT INTO alert_performance
            (alert_id, ticker, source, catalyst_type, posted_at, updated_at,
             discord_message_id, discord_channel_id)
            VALUES ('aid:test123', 'AAPL', 'finviz', 'news', 1700000000, 1700000000,
                    '1234567890', '0987654321')
            """
        )
        conn.commit()
        conn.close()

        manager = TradeNotificationManager(db_path=temp_db)
        info = manager.get_alert_discord_info("aid:test123")

        assert info is not None
        assert info.alert_id == "aid:test123"
        assert info.message_id == "1234567890"
        assert info.channel_id == "0987654321"
        assert info.thread_id is None

    def test_get_alert_discord_info_not_found(self, temp_db):
        """Test lookup returns None for non-existent alert."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        manager = TradeNotificationManager(db_path=temp_db)
        info = manager.get_alert_discord_info("aid:nonexistent")

        assert info is None

    def test_save_thread_id(self, temp_db):
        """Test saving thread ID to alert."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        # Insert test alert
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            INSERT INTO alert_performance
            (alert_id, ticker, source, catalyst_type, posted_at, updated_at,
             discord_message_id, discord_channel_id)
            VALUES ('aid:test123', 'AAPL', 'finviz', 'news', 1700000000, 1700000000,
                    '1234567890', '0987654321')
            """
        )
        conn.commit()
        conn.close()

        manager = TradeNotificationManager(db_path=temp_db)
        manager.save_thread_id("aid:test123", "thread_111222333")

        # Verify thread was saved
        info = manager.get_alert_discord_info("aid:test123")
        assert info.thread_id == "thread_111222333"

    def test_save_trade_notification(self, temp_db):
        """Test saving trade notification record."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        manager = TradeNotificationManager(db_path=temp_db)

        notif_id = manager.save_trade_notification(
            alert_id="aid:test123",
            position_id="pos-uuid-001",
            thread_id="thread_111",
            ticker="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.25,
            entry_message_id="msg_001",
        )

        assert notif_id > 0

        # Retrieve and verify
        notif = manager.get_trade_notification("pos-uuid-001")
        assert notif is not None
        assert notif.ticker == "AAPL"
        assert notif.side == "BUY"
        assert notif.quantity == 100
        assert notif.entry_price == 150.25
        assert notif.status == "open"

    def test_update_trade_exit(self, temp_db):
        """Test updating trade with exit info."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        manager = TradeNotificationManager(db_path=temp_db)

        # Create initial notification
        manager.save_trade_notification(
            alert_id="aid:test123",
            position_id="pos-uuid-001",
            thread_id="thread_111",
            ticker="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.00,
        )

        # Update with exit
        manager.update_trade_exit(
            position_id="pos-uuid-001",
            exit_price=165.00,
            realized_pnl=1500.00,
            realized_pnl_pct=10.0,
            exit_message_id="msg_002",
        )

        # Verify update
        notif = manager.get_trade_notification("pos-uuid-001")
        assert notif.exit_price == 165.00
        assert notif.realized_pnl == 1500.00
        assert notif.realized_pnl_pct == 10.0
        assert notif.status == "closed"

    def test_get_notification_stats(self, temp_db):
        """Test notification statistics."""
        from src.catalyst_bot.trade_notifications import TradeNotificationManager

        manager = TradeNotificationManager(db_path=temp_db)

        # Create some notifications
        for i in range(5):
            manager.save_trade_notification(
                alert_id=f"aid:test{i}",
                position_id=f"pos-{i}",
                thread_id="thread_111",
                ticker="AAPL",
                side="BUY",
                quantity=100,
                entry_price=100.00,
            )

        # Close 3 with profits, 2 with losses
        for i in range(3):
            manager.update_trade_exit(
                position_id=f"pos-{i}",
                exit_price=110.00,
                realized_pnl=1000.00,
                realized_pnl_pct=10.0,
            )

        stats = manager.get_notification_stats()
        assert stats["total_notifications"] == 5
        assert stats["closed_positions"] == 3
        assert stats["open_positions"] == 2
        assert stats["wins"] == 3


@pytest.mark.asyncio
class TestAsyncThreadOperations:
    """Test async thread creation and posting."""

    async def test_create_trade_thread_disabled(self):
        """Test thread creation when disabled."""
        with patch.dict(os.environ, {"DISCORD_TRADE_NOTIFICATIONS": "0"}):
            from src.catalyst_bot.discord_threads import create_trade_thread

            result = await create_trade_thread(
                channel_id="123",
                message_id="456",
                ticker="AAPL",
            )
            assert result is None

    async def test_create_trade_thread_no_token(self):
        """Test thread creation without bot token."""
        with patch.dict(os.environ, {"DISCORD_TRADE_NOTIFICATIONS": "1", "DISCORD_BOT_TOKEN": ""}):
            from src.catalyst_bot.discord_threads import create_trade_thread

            result = await create_trade_thread(
                channel_id="123",
                message_id="456",
                ticker="AAPL",
            )
            assert result is None

    async def test_create_trade_thread_success(self):
        """Test successful thread creation."""
        with patch.dict(os.environ, {"DISCORD_TRADE_NOTIFICATIONS": "1", "DISCORD_BOT_TOKEN": "test-token"}):
            from src.catalyst_bot.discord_threads import create_trade_thread

            mock_response = MagicMock()
            mock_response.status = 201
            mock_response.json = AsyncMock(return_value={"id": "thread_999"})

            with patch("aiohttp.ClientSession") as mock_session:
                mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session.return_value)
                mock_session.return_value.__aexit__ = AsyncMock()
                mock_session.return_value.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_session.return_value.post.return_value.__aexit__ = AsyncMock()

                result = await create_trade_thread(
                    channel_id="123456",
                    message_id="789012",
                    ticker="AAPL",
                )

                assert result == "thread_999"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
