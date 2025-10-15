"""
Tests for False Positive Analysis System

Tests:
- Accepted item logging
- Outcome classification
- Pattern analysis
- Penalty recommendations

Author: Claude Code (Agent 4: False Positive Analysis)
Date: 2025-10-12
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from catalyst_bot.accepted_items_logger import log_accepted_item
from catalyst_bot.false_positive_analyzer import (
    analyze_keyword_patterns,
    analyze_source_patterns,
    calculate_precision_recall,
    generate_keyword_penalties,
)
from catalyst_bot.false_positive_tracker import classify_outcome


class TestAcceptedItemsLogger:
    """Test accepted items logging."""

    def test_log_accepted_item(self):
        """Test logging an accepted item."""
        item = {
            "ticker": "AAPL",
            "title": "Apple announces new product",
            "source": "news_api",
            "summary": "Apple Inc. announced...",
        }

        # Log the item (will write to data/accepted_items.jsonl)
        log_accepted_item(
            item=item,
            price=150.0,
            score=2.5,
            sentiment=0.8,
            keywords=["product", "announcement"],
        )

        # Verify file exists and has correct content
        log_path = Path("data/accepted_items.jsonl")
        assert log_path.exists()

        # Read the last line (our entry)
        with open(log_path, "r") as f:
            lines = f.readlines()
            last_line = lines[-1]
            logged = json.loads(last_line)

        assert logged["ticker"] == "AAPL"
        assert logged["price"] == 150.0
        assert logged["cls"]["score"] == 2.5
        assert logged["cls"]["sentiment"] == 0.8
        assert logged["cls"]["keywords"] == ["product", "announcement"]
        assert logged["accepted"] is True

    def test_log_accepted_item_no_ticker(self):
        """Test that items without tickers are not logged."""
        item = {
            "title": "News without ticker",
            "source": "news_api",
        }

        # Get current line count
        log_path = Path("data/accepted_items.jsonl")
        lines_before = 0
        if log_path.exists():
            with open(log_path, "r") as f:
                lines_before = len(f.readlines())

        # Try to log item without ticker
        log_accepted_item(item=item, price=100.0)

        # Verify no new line was added
        lines_after = 0
        if log_path.exists():
            with open(log_path, "r") as f:
                lines_after = len(f.readlines())

        assert lines_after == lines_before


class TestOutcomeClassification:
    """Test outcome classification logic."""

    def test_classify_success_1h(self):
        """Test SUCCESS classification for 1h threshold."""
        outcomes = {
            "1h": {"return_pct": 2.5},  # > 2%
            "4h": {"return_pct": 1.0},
            "1d": {"return_pct": 3.0},
        }

        classification, max_return = classify_outcome(outcomes)
        assert classification == "SUCCESS"
        assert max_return == 3.0

    def test_classify_success_4h(self):
        """Test SUCCESS classification for 4h threshold."""
        outcomes = {
            "1h": {"return_pct": 1.0},
            "4h": {"return_pct": 3.5},  # > 3%
            "1d": {"return_pct": 2.0},
        }

        classification, max_return = classify_outcome(outcomes)
        assert classification == "SUCCESS"
        assert max_return == 3.5

    def test_classify_success_1d(self):
        """Test SUCCESS classification for 1d threshold."""
        outcomes = {
            "1h": {"return_pct": 1.0},
            "4h": {"return_pct": 2.0},
            "1d": {"return_pct": 5.5},  # > 5%
        }

        classification, max_return = classify_outcome(outcomes)
        assert classification == "SUCCESS"
        assert max_return == 5.5

    def test_classify_failure_negative(self):
        """Test FAILURE classification for negative returns."""
        outcomes = {
            "1h": {"return_pct": -1.0},
            "4h": {"return_pct": -2.0},
            "1d": {"return_pct": -1.5},
        }

        classification, max_return = classify_outcome(outcomes)
        assert classification == "FAILURE"
        assert max_return == -1.0

    def test_classify_failure_minimal(self):
        """Test FAILURE classification for minimal positive returns."""
        outcomes = {
            "1h": {"return_pct": 0.5},
            "4h": {"return_pct": 0.8},
            "1d": {"return_pct": 0.9},  # All < 1%
        }

        classification, max_return = classify_outcome(outcomes)
        assert classification == "FAILURE"
        assert max_return == 0.9

    def test_classify_failure_borderline(self):
        """Test FAILURE classification for borderline returns."""
        outcomes = {
            "1h": {"return_pct": 1.5},  # Below 2% threshold
            "4h": {"return_pct": 2.5},  # Below 3% threshold
            "1d": {"return_pct": 4.0},  # Below 5% threshold
        }

        classification, max_return = classify_outcome(outcomes)
        assert classification == "FAILURE"
        assert max_return == 4.0


class TestPatternAnalysis:
    """Test pattern analysis functions."""

    def test_calculate_precision_recall(self):
        """Test precision/recall calculation."""
        outcomes = [
            {"classification": "SUCCESS"},
            {"classification": "SUCCESS"},
            {"classification": "FAILURE"},
            {"classification": "FAILURE"},
            {"classification": "FAILURE"},
        ]

        result = calculate_precision_recall(outcomes)

        assert result["total_accepts"] == 5
        assert result["success_count"] == 2
        assert result["failure_count"] == 3
        assert result["precision"] == 0.4
        assert result["false_positive_rate"] == 0.6

    def test_analyze_keyword_patterns(self):
        """Test keyword pattern analysis."""
        outcomes = [
            {
                "keywords": ["merger", "acquisition"],
                "classification": "FAILURE",
                "max_return_pct": -1.0,
                "ticker": "AAPL",
            },
            {
                "keywords": ["merger", "partnership"],
                "classification": "FAILURE",
                "max_return_pct": 0.5,
                "ticker": "GOOGL",
            },
            {
                "keywords": ["merger", "earnings"],
                "classification": "SUCCESS",
                "max_return_pct": 5.0,
                "ticker": "MSFT",
            },
            {
                "keywords": ["acquisition"],
                "classification": "FAILURE",
                "max_return_pct": -2.0,
                "ticker": "TSLA",
            },
        ]

        result = analyze_keyword_patterns(outcomes)

        # Check merger keyword
        assert "merger" in result
        merger_stats = result["merger"]
        assert merger_stats["occurrences"] == 3
        assert merger_stats["failures"] == 2
        assert merger_stats["successes"] == 1
        assert merger_stats["failure_rate"] > 0.6

    def test_analyze_source_patterns(self):
        """Test source pattern analysis."""
        outcomes = [
            {
                "source": "sec_8k",
                "classification": "FAILURE",
                "max_return_pct": -1.0,
            },
            {
                "source": "sec_8k",
                "classification": "FAILURE",
                "max_return_pct": 0.5,
            },
            {
                "source": "news_api",
                "classification": "SUCCESS",
                "max_return_pct": 5.0,
            },
        ]

        result = analyze_source_patterns(outcomes)

        assert "sec_8k" in result
        assert result["sec_8k"]["total"] == 2
        assert result["sec_8k"]["failures"] == 2
        assert result["sec_8k"]["failure_rate"] == 1.0

        assert "news_api" in result
        assert result["news_api"]["total"] == 1
        assert result["news_api"]["successes"] == 1
        assert result["news_api"]["failure_rate"] == 0.0

    def test_generate_keyword_penalties(self):
        """Test keyword penalty generation."""
        keyword_stats = {
            "bad_keyword": {
                "occurrences": 10,
                "failures": 9,
                "successes": 1,
                "failure_rate": 0.9,
                "avg_return": -2.0,
                "examples": [],
            },
            "ok_keyword": {
                "occurrences": 10,
                "failures": 3,
                "successes": 7,
                "failure_rate": 0.3,
                "avg_return": 3.0,
                "examples": [],
            },
        }

        penalties = generate_keyword_penalties(keyword_stats)

        # Should only penalize bad_keyword (failure_rate >= 0.5)
        assert len(penalties) == 1
        assert penalties[0]["keyword"] == "bad_keyword"
        assert penalties[0]["recommended_penalty"] < 0
        assert penalties[0]["confidence"] == 0.9


class TestIntegration:
    """Integration tests for the full system."""

    def test_end_to_end_workflow(self):
        """Test complete workflow from logging to analysis."""
        # Get initial line count
        log_path = Path("data/accepted_items.jsonl")
        lines_before = 0
        if log_path.exists():
            with open(log_path, "r") as f:
                lines_before = len(f.readlines())

        # 1. Log some accepted items
        for i in range(3):
            item = {
                "ticker": f"TICK{i}",
                "title": f"Test item {i}",
                "source": "test_source",
            }
            log_accepted_item(
                item=item,
                price=100.0,
                score=2.0,
                sentiment=0.5,
                keywords=["test", "keyword"],
            )

        # 2. Verify log file exists
        assert log_path.exists()

        # 3. Verify 3 new items were added
        with open(log_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == lines_before + 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
