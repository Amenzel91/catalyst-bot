"""
Test suite for Rejected Items Logger - MOA Enhancement #5

Tests cover sentiment breakdown collection:
- Sentiment breakdown dict with individual source scores
- Sentiment confidence tracking
- Backward compatibility with existing code
- Handling partial sentiment data (only some sources available)

Author: Claude Code (MOA Data Collection Enhancements)
Date: 2025-10-11
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from catalyst_bot.rejected_items_logger import (
    clear_old_rejected_items,
    get_rejection_stats,
    log_rejected_item,
    should_log_rejected_item,
)


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


class TestSentimentBreakdownLogging:
    """Test sentiment breakdown collection (Enhancement #5)."""

    def test_sentiment_breakdown_dict_populated(self, temp_data_dir, monkeypatch):
        """Test that sentiment_breakdown dict is populated with individual source scores."""
        # Override log path
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News",
            "source": "test_source",
            "raw": {
                "sentiment_breakdown": {
                    "vader": 0.75,
                    "ml": 0.65,
                    "llm": 0.80,
                    "earnings": None,
                },
                "sentiment_confidence": 0.85,
            },
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.73,
        )

        # Read logged item
        assert log_path.exists()
        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        # Verify sentiment breakdown is included
        assert "sentiment_breakdown" in logged["cls"]
        breakdown = logged["cls"]["sentiment_breakdown"]
        assert breakdown["vader"] == 0.75
        assert breakdown["ml"] == 0.65
        assert breakdown["llm"] == 0.80
        assert breakdown["earnings"] is None

    def test_sentiment_confidence_tracked(self, temp_data_dir, monkeypatch):
        """Test that sentiment_confidence is tracked."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News",
            "source": "test_source",
            "raw": {
                "sentiment_breakdown": {"vader": 0.75, "ml": 0.70},
                "sentiment_confidence": 0.92,
            },
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.725,
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        assert "sentiment_confidence" in logged["cls"]
        assert logged["cls"]["sentiment_confidence"] == 0.92

    def test_sentiment_sources_used_tracking(self, temp_data_dir, monkeypatch):
        """Test that sentiment_sources_used list is populated."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News",
            "source": "test_source",
            "raw": {
                "sentiment_breakdown": {
                    "vader": 0.75,
                    "ml": 0.65,
                    "llm": None,
                    "earnings": 0.80,
                },
                "sentiment_confidence": 0.85,
            },
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.73,
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        # Should list only sources with non-None values
        assert "sentiment_sources_used" in logged["cls"]
        sources = logged["cls"]["sentiment_sources_used"]
        assert "vader" in sources
        assert "ml" in sources
        assert "earnings" in sources
        assert "llm" not in sources  # Was None

    def test_partial_sentiment_data_only_vader(self, temp_data_dir, monkeypatch):
        """Test with only VADER sentiment available (partial data)."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News",
            "source": "test_source",
            "raw": {
                "sentiment_breakdown": {
                    "vader": 0.65,
                    "ml": None,
                    "llm": None,
                    "earnings": None,
                },
                "sentiment_confidence": 0.50,  # Low confidence with only one source
            },
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.65,
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        assert logged["cls"]["sentiment_breakdown"]["vader"] == 0.65
        assert logged["cls"]["sentiment_sources_used"] == ["vader"]
        assert logged["cls"]["sentiment_confidence"] == 0.50

    def test_partial_sentiment_data_vader_and_ml(self, temp_data_dir, monkeypatch):
        """Test with VADER and ML sentiment (partial data, no LLM)."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News",
            "source": "test_source",
            "raw": {
                "sentiment_breakdown": {
                    "vader": 0.70,
                    "ml": 0.75,
                    "llm": None,
                    "earnings": None,
                },
                "sentiment_confidence": 0.80,
            },
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.725,
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        assert logged["cls"]["sentiment_breakdown"]["vader"] == 0.70
        assert logged["cls"]["sentiment_breakdown"]["ml"] == 0.75
        assert set(logged["cls"]["sentiment_sources_used"]) == {"vader", "ml"}

    def test_backward_compatibility_no_raw_field(self, temp_data_dir, monkeypatch):
        """Test backward compatibility when item has no 'raw' field (old code)."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        # Old-style item without 'raw' field
        item = {"ticker": "TEST", "title": "Test News", "source": "test_source"}

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.70,
            keywords=["test", "keyword"],
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        # Should still work with basic sentiment
        assert logged["cls"]["sentiment"] == 0.70
        assert logged["cls"]["score"] == 0.60
        assert logged["cls"]["keywords"] == ["test", "keyword"]

        # Should not have breakdown fields
        assert "sentiment_breakdown" not in logged["cls"]
        assert "sentiment_confidence" not in logged["cls"]

    def test_backward_compatibility_empty_raw_field(self, temp_data_dir, monkeypatch):
        """Test backward compatibility when raw field is empty."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News",
            "source": "test_source",
            "raw": {},  # Empty raw dict
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.70,
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        # Should work without breakdown
        assert logged["cls"]["sentiment"] == 0.70
        assert "sentiment_breakdown" not in logged["cls"]

    def test_all_sentiment_sources_available(self, temp_data_dir, monkeypatch):
        """Test with all sentiment sources available (best case)."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "TEST",
            "title": "Test News - Earnings Beat",
            "source": "test_source",
            "raw": {
                "sentiment_breakdown": {
                    "vader": 0.75,
                    "ml": 0.70,
                    "llm": 0.80,
                    "earnings": 0.85,
                },
                "sentiment_confidence": 0.95,  # High confidence with all sources
            },
        }

        log_rejected_item(
            item=item,
            rejection_reason="LOW_SCORE",
            price=5.00,
            score=0.60,
            sentiment=0.775,
        )

        with open(log_path, "r") as f:
            logged = json.loads(f.readline())

        breakdown = logged["cls"]["sentiment_breakdown"]
        assert breakdown["vader"] == 0.75
        assert breakdown["ml"] == 0.70
        assert breakdown["llm"] == 0.80
        assert breakdown["earnings"] == 0.85

        sources = logged["cls"]["sentiment_sources_used"]
        assert set(sources) == {"vader", "ml", "llm", "earnings"}
        assert logged["cls"]["sentiment_confidence"] == 0.95


class TestPriceRangeFiltering:
    """Test price range filtering functionality."""

    def test_should_log_within_range(self):
        """Test that prices within range return True."""
        assert should_log_rejected_item(5.00) is True
        assert should_log_rejected_item(0.10) is True
        assert should_log_rejected_item(10.00) is True

    def test_should_not_log_below_floor(self):
        """Test that prices below floor return False."""
        assert should_log_rejected_item(0.05) is False
        assert should_log_rejected_item(0.01) is False

    def test_should_not_log_above_ceiling(self):
        """Test that prices above ceiling return False."""
        assert should_log_rejected_item(15.00) is False
        assert should_log_rejected_item(100.00) is False

    def test_should_not_log_none_price(self):
        """Test that None price returns False."""
        assert should_log_rejected_item(None) is False

    def test_log_rejected_item_filters_high_price(self, temp_data_dir, monkeypatch):
        """Test that items with high prices are not logged."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {
            "ticker": "EXPENSIVE",
            "title": "High Price Stock",
            "source": "test_source",
        }

        log_rejected_item(
            item=item,
            rejection_reason="HIGH_PRICE",
            price=50.00,  # Above ceiling
            score=0.80,
        )

        # File should not be created
        assert not log_path.exists()

    def test_log_rejected_item_filters_low_price(self, temp_data_dir, monkeypatch):
        """Test that items with low prices are not logged."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        item = {"ticker": "PENNY", "title": "Penny Stock", "source": "test_source"}

        log_rejected_item(
            item=item,
            rejection_reason="LOW_PRICE",
            price=0.05,  # Below floor
            score=0.80,
        )

        # File should not be created
        assert not log_path.exists()


class TestRejectionStats:
    """Test rejection statistics functionality."""

    def test_get_rejection_stats_today(self, temp_data_dir, monkeypatch):
        """Test getting rejection stats for today."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        today = datetime.now(timezone.utc).date().isoformat()

        # Write test data
        with open(log_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "ts": f"{today}T10:00:00+00:00",
                        "ticker": "TEST1",
                        "rejection_reason": "LOW_SCORE",
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": f"{today}T11:00:00+00:00",
                        "ticker": "TEST2",
                        "rejection_reason": "LOW_SCORE",
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": f"{today}T12:00:00+00:00",
                        "ticker": "TEST3",
                        "rejection_reason": "HIGH_PRICE",
                    }
                )
                + "\n"
            )

        stats = get_rejection_stats()

        assert stats["LOW_SCORE"] == 2
        assert stats["HIGH_PRICE"] == 1

    def test_get_rejection_stats_empty_file(self, temp_data_dir, monkeypatch):
        """Test stats with empty file."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        log_path.touch()  # Create empty file

        stats = get_rejection_stats()
        assert stats == {}

    def test_get_rejection_stats_missing_file(self, temp_data_dir, monkeypatch):
        """Test stats when file doesn't exist."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        stats = get_rejection_stats()
        assert stats == {}


class TestClearOldRejectedItems:
    """Test clearing old rejected items."""

    def test_clear_old_items_removes_old_entries(self, temp_data_dir, monkeypatch):
        """Test that old entries are removed."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        # Create old and recent items
        old_date = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()
        recent_date = datetime.now(timezone.utc).isoformat()

        with open(log_path, "w") as f:
            f.write(json.dumps({"ts": old_date, "ticker": "OLD"}) + "\n")
            f.write(json.dumps({"ts": recent_date, "ticker": "NEW"}) + "\n")

        removed = clear_old_rejected_items(days_to_keep=30)

        assert removed == 1

        # Verify only recent item remains
        with open(log_path, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            assert "NEW" in lines[0]

    def test_clear_old_items_missing_file(self, temp_data_dir, monkeypatch):
        """Test clearing when file doesn't exist."""
        log_path = temp_data_dir / "rejected_items.jsonl"
        monkeypatch.setattr(
            "catalyst_bot.rejected_items_logger.Path",
            lambda x: log_path if "rejected_items" in x else Path(x),
        )

        removed = clear_old_rejected_items(days_to_keep=30)
        assert removed == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
