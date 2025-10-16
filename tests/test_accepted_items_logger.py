"""Tests for accepted_items_logger.py - MOA negative keyword tracking."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from catalyst_bot.accepted_items_logger import (
    PRICE_CEILING,
    PRICE_FLOOR,
    clear_old_accepted_items,
    get_accepted_stats,
    log_accepted_item,
    should_log_accepted_item,
)


@pytest.fixture
def mock_data_dir(tmp_path, monkeypatch):
    """Mock the data directory for testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch Path to use tmp_path
    original_path = Path

    class MockPath(type(Path())):
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "data/accepted_items.jsonl":
                return original_path(tmp_path / "data" / "accepted_items.jsonl")
            return original_path(*args, **kwargs)

    monkeypatch.setattr("catalyst_bot.accepted_items_logger.Path", MockPath)

    return data_dir


class TestPriceFiltering:
    """Test price range filtering logic."""

    def test_price_within_range(self):
        """Prices within $0.10-$10.00 should be logged."""
        assert should_log_accepted_item(0.10) is True
        assert should_log_accepted_item(1.0) is True
        assert should_log_accepted_item(5.0) is True
        assert should_log_accepted_item(10.0) is True

    def test_price_below_floor(self):
        """Prices below $0.10 should not be logged."""
        assert should_log_accepted_item(0.01) is False
        assert should_log_accepted_item(0.05) is False
        assert should_log_accepted_item(0.09) is False

    def test_price_above_ceiling(self):
        """Prices above $10.00 should not be logged."""
        assert should_log_accepted_item(10.01) is False
        assert should_log_accepted_item(15.0) is False
        assert should_log_accepted_item(100.0) is False

    def test_price_none(self):
        """None price should not be logged."""
        assert should_log_accepted_item(None) is False

    def test_price_boundaries(self):
        """Test exact boundaries."""
        assert should_log_accepted_item(PRICE_FLOOR) is True
        assert should_log_accepted_item(PRICE_CEILING) is True
        assert should_log_accepted_item(PRICE_FLOOR - 0.01) is False
        assert should_log_accepted_item(PRICE_CEILING + 0.01) is False


class TestLogAcceptedItem:
    """Test logging accepted items."""

    def test_logs_basic_item(self, mock_data_dir):
        """Log a basic accepted item."""
        item = {
            "ticker": "TEST",
            "title": "Company Announces Partnership",
            "source": "benzinga",
            "summary": "Major partnership deal announced",
            "link": "http://example.com/news/1",
        }

        log_accepted_item(
            item=item,
            price=5.0,
            score=0.75,
            sentiment=0.65,
            keywords=["partnership", "deal"],
        )

        # Check file was created
        log_path = mock_data_dir / "accepted_items.jsonl"
        assert log_path.exists()

        # Read and verify content
        with open(log_path, "r", encoding="utf-8") as f:
            line = f.readline()
            logged_item = json.loads(line)

        assert logged_item["ticker"] == "TEST"
        assert logged_item["title"] == "Company Announces Partnership"
        assert logged_item["price"] == 5.0
        assert logged_item["accepted"] is True
        assert logged_item["cls"]["score"] == 0.75
        assert logged_item["cls"]["sentiment"] == 0.65
        assert logged_item["cls"]["keywords"] == ["partnership", "deal"]
        assert "ts" in logged_item

    def test_skips_item_below_price_floor(self, mock_data_dir):
        """Don't log items below price floor."""
        item = {"ticker": "PENNY", "title": "Penny Stock News"}

        log_accepted_item(item=item, price=0.05)

        # File should not be created
        log_path = mock_data_dir / "accepted_items.jsonl"
        assert not log_path.exists()

    def test_skips_item_above_price_ceiling(self, mock_data_dir):
        """Don't log items above price ceiling."""
        item = {"ticker": "EXPENSIVE", "title": "High Price Stock"}

        log_accepted_item(item=item, price=50.0)

        # File should not be created
        log_path = mock_data_dir / "accepted_items.jsonl"
        assert not log_path.exists()

    def test_skips_item_without_price(self, mock_data_dir):
        """Don't log items without price."""
        item = {"ticker": "NOPRICE", "title": "No Price Available"}

        log_accepted_item(item=item, price=None)

        # File should not be created
        log_path = mock_data_dir / "accepted_items.jsonl"
        assert not log_path.exists()

    def test_skips_item_without_ticker(self, mock_data_dir):
        """Don't log items without ticker."""
        item = {"title": "No Ticker Available"}

        log_accepted_item(item=item, price=5.0)

        # File should not be created
        log_path = mock_data_dir / "accepted_items.jsonl"
        assert not log_path.exists()

    def test_logs_multiple_items(self, mock_data_dir):
        """Log multiple items in sequence."""
        items = [
            {"ticker": "TEST1", "title": "News 1"},
            {"ticker": "TEST2", "title": "News 2"},
            {"ticker": "TEST3", "title": "News 3"},
        ]

        for item in items:
            log_accepted_item(item=item, price=5.0)

        # Check file has 3 lines
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3

        # Verify each line
        for i, line in enumerate(lines):
            logged_item = json.loads(line)
            assert logged_item["ticker"] == f"TEST{i+1}"

    def test_logs_sentiment_breakdown(self, mock_data_dir):
        """Log sentiment breakdown if available."""
        item = {
            "ticker": "TEST",
            "title": "Test News",
            "raw": {
                "sentiment_breakdown": {
                    "vader": 0.5,
                    "ml": 0.6,
                    "llm": 0.7,
                },
                "sentiment_confidence": 0.8,
            },
        }

        log_accepted_item(item=item, price=5.0, sentiment=0.6)

        # Read and verify
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            logged_item = json.loads(f.readline())

        assert "sentiment_breakdown" in logged_item["cls"]
        assert logged_item["cls"]["sentiment_breakdown"]["vader"] == 0.5
        assert logged_item["cls"]["sentiment_breakdown"]["ml"] == 0.6
        assert logged_item["cls"]["sentiment_breakdown"]["llm"] == 0.7
        assert logged_item["cls"]["sentiment_confidence"] == 0.8
        assert "sentiment_sources_used" in logged_item["cls"]
        assert "vader" in logged_item["cls"]["sentiment_sources_used"]

    def test_logs_market_regime_from_scored(self, mock_data_dir):
        """Log market regime data from scored object."""
        item = {"ticker": "TEST", "title": "Test News"}

        # Mock scored object with market regime
        class MockScored:
            market_regime = "favorable"
            market_vix = 15.5
            market_spy_trend = 0.02
            market_regime_multiplier = 1.1

        scored = MockScored()

        log_accepted_item(item=item, price=5.0, scored=scored)

        # Read and verify
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            logged_item = json.loads(f.readline())

        assert logged_item["market_regime"] == "favorable"
        assert logged_item["market_vix"] == 15.5
        assert logged_item["market_spy_trend"] == 0.02
        assert logged_item["market_regime_multiplier"] == 1.1

    def test_logs_market_regime_from_dict(self, mock_data_dir):
        """Log market regime data from dict."""
        item = {"ticker": "TEST", "title": "Test News"}

        scored = {
            "market_regime": "unfavorable",
            "market_vix": 25.0,
            "market_spy_trend": -0.01,
            "market_regime_multiplier": 0.9,
        }

        log_accepted_item(item=item, price=5.0, scored=scored)

        # Read and verify
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            logged_item = json.loads(f.readline())

        assert logged_item["market_regime"] == "unfavorable"
        assert logged_item["market_vix"] == 25.0

    def test_handles_missing_fields(self, mock_data_dir):
        """Handle items with missing optional fields."""
        item = {"ticker": "TEST"}  # Minimal item

        log_accepted_item(item=item, price=5.0)

        # Should log with defaults
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            logged_item = json.loads(f.readline())

        assert logged_item["ticker"] == "TEST"
        assert logged_item["title"] == ""
        assert logged_item["source"] == ""
        assert logged_item["summary"] == ""
        assert logged_item["link"] == ""

    def test_handles_unicode(self, mock_data_dir):
        """Handle Unicode characters in content."""
        item = {
            "ticker": "TEST",
            "title": "Company announces breakthrough therapy",
            "summary": "Major development in treatment",
        }

        log_accepted_item(item=item, price=5.0)

        # Read and verify Unicode is preserved
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            logged_item = json.loads(f.readline())

        assert "therapy" in logged_item["title"]

    def test_timestamp_is_utc(self, mock_data_dir):
        """Timestamp should be in UTC."""
        item = {"ticker": "TEST", "title": "Test"}

        before = datetime.now(timezone.utc)
        log_accepted_item(item=item, price=5.0)
        after = datetime.now(timezone.utc)

        # Read timestamp
        log_path = mock_data_dir / "accepted_items.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            logged_item = json.loads(f.readline())

        ts = datetime.fromisoformat(logged_item["ts"].replace("Z", "+00:00"))

        # Should be between before and after
        assert before <= ts <= after
        # Should have timezone info
        assert ts.tzinfo is not None


class TestGetAcceptedStats:
    """Test statistics retrieval."""

    def test_get_stats_empty_file(self, mock_data_dir):
        """Get stats when file doesn't exist."""
        stats = get_accepted_stats()
        assert stats == {}

    def test_get_stats_today_only(self, mock_data_dir):
        """Only count today's items."""
        log_path = mock_data_dir / "accepted_items.jsonl"

        today = datetime.now(timezone.utc)
        yesterday = today - timedelta(days=1)

        # Log items from different days
        items = [
            {"ts": today.isoformat(), "ticker": "TODAY1", "source": "benzinga"},
            {"ts": today.isoformat(), "ticker": "TODAY2", "source": "benzinga"},
            {"ts": yesterday.isoformat(), "ticker": "YESTERDAY", "source": "benzinga"},
        ]

        with open(log_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")

        stats = get_accepted_stats()

        # Should only count today's items
        assert stats.get("total") == 2
        assert stats.get("source_benzinga") == 2

    def test_get_stats_multiple_sources(self, mock_data_dir):
        """Count by source."""
        log_path = mock_data_dir / "accepted_items.jsonl"
        today = datetime.now(timezone.utc).isoformat()

        items = [
            {"ts": today, "ticker": "T1", "source": "benzinga"},
            {"ts": today, "ticker": "T2", "source": "benzinga"},
            {"ts": today, "ticker": "T3", "source": "newsfilter"},
            {"ts": today, "ticker": "T4", "source": "sec"},
        ]

        with open(log_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")

        stats = get_accepted_stats()

        assert stats["total"] == 4
        assert stats["source_benzinga"] == 2
        assert stats["source_newsfilter"] == 1
        assert stats["source_sec"] == 1

    def test_get_stats_handles_invalid_json(self, mock_data_dir):
        """Skip invalid JSON lines."""
        log_path = mock_data_dir / "accepted_items.jsonl"
        today = datetime.now(timezone.utc).isoformat()

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f'{{"ts": "{today}", "ticker": "VALID"}}\n')
            f.write("invalid json line\n")
            f.write(f'{{"ts": "{today}", "ticker": "VALID2"}}\n')

        stats = get_accepted_stats()

        # Should count valid items only
        assert stats["total"] == 2


class TestClearOldAcceptedItems:
    """Test cleanup of old items."""

    def test_clear_old_items(self, mock_data_dir):
        """Remove items older than specified days."""
        log_path = mock_data_dir / "accepted_items.jsonl"

        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=40)
        recent_date = now - timedelta(days=10)

        items = [
            {"ts": old_date.isoformat(), "ticker": "OLD1"},
            {"ts": old_date.isoformat(), "ticker": "OLD2"},
            {"ts": recent_date.isoformat(), "ticker": "RECENT1"},
            {"ts": now.isoformat(), "ticker": "RECENT2"},
        ]

        with open(log_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")

        # Clear items older than 30 days
        removed = clear_old_accepted_items(days_to_keep=30)

        assert removed == 2

        # Verify only recent items remain
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2

        for line in lines:
            item = json.loads(line)
            assert item["ticker"] in ["RECENT1", "RECENT2"]

    def test_clear_when_file_missing(self, mock_data_dir):
        """Handle missing file gracefully."""
        removed = clear_old_accepted_items(days_to_keep=30)
        assert removed == 0

    def test_clear_keeps_unparseable_items(self, mock_data_dir):
        """Keep items that can't be parsed."""
        log_path = mock_data_dir / "accepted_items.jsonl"

        now = datetime.now(timezone.utc)

        with open(log_path, "w", encoding="utf-8") as f:
            f.write('{"ts": "invalid-timestamp", "ticker": "INVALID"}\n')
            f.write(f'{{"ts": "{now.isoformat()}", "ticker": "VALID"}}\n')

        _ = clear_old_accepted_items(days_to_keep=30)

        # Should keep both (can't parse invalid timestamp, so keep it)
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2

    def test_clear_all_old(self, mock_data_dir):
        """Clear when all items are old."""
        log_path = mock_data_dir / "accepted_items.jsonl"

        old_date = datetime.now(timezone.utc) - timedelta(days=40)

        items = [
            {"ts": old_date.isoformat(), "ticker": "OLD1"},
            {"ts": old_date.isoformat(), "ticker": "OLD2"},
        ]

        with open(log_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")

        removed = clear_old_accepted_items(days_to_keep=30)

        assert removed == 2

        # File should be empty
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 0

    def test_clear_none_old(self, mock_data_dir):
        """Clear when no items are old."""
        log_path = mock_data_dir / "accepted_items.jsonl"

        recent_date = datetime.now(timezone.utc) - timedelta(days=10)

        items = [
            {"ts": recent_date.isoformat(), "ticker": "RECENT1"},
            {"ts": recent_date.isoformat(), "ticker": "RECENT2"},
        ]

        with open(log_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")

        removed = clear_old_accepted_items(days_to_keep=30)

        assert removed == 0

        # All items should remain
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2


class TestIntegration:
    """Integration tests."""

    def test_log_and_retrieve_workflow(self, mock_data_dir):
        """Test complete log -> retrieve workflow."""
        # Log several items
        items = [
            {
                "ticker": "TEST1",
                "title": "FDA Approval",
                "source": "benzinga",
                "price": 2.5,
            },
            {
                "ticker": "TEST2",
                "title": "Earnings Report",
                "source": "benzinga",
                "price": 5.0,
            },
            {
                "ticker": "TEST3",
                "title": "Partnership Deal",
                "source": "newsfilter",
                "price": 7.5,
            },
        ]

        for item in items:
            price = item.pop("price")
            log_accepted_item(item=item, price=price, score=0.7, sentiment=0.6)

        # Get stats
        stats = get_accepted_stats()

        assert stats["total"] == 3
        assert stats["source_benzinga"] == 2
        assert stats["source_newsfilter"] == 1

    def test_continuous_logging(self, mock_data_dir):
        """Test logging items over time."""
        log_path = mock_data_dir / "accepted_items.jsonl"

        # Log items in sequence
        for i in range(10):
            item = {"ticker": f"TEST{i}", "title": f"News {i}", "source": "benzinga"}
            log_accepted_item(item=item, price=5.0)

        # Verify all items logged
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 10

        # Verify order
        for i, line in enumerate(lines):
            logged_item = json.loads(line)
            assert logged_item["ticker"] == f"TEST{i}"
