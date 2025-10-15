"""
Test BacktestEngine with Configurable Data Source
==================================================

Tests that BacktestEngine can load data from custom sources and apply filters.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_bot.backtesting import BacktestEngine  # noqa: E402


class TestConfigurableDataSource:
    """Test configurable data source functionality."""

    @pytest.fixture
    def custom_events_file(self, tmp_path):
        """Create custom events.jsonl file for testing."""
        events_path = tmp_path / "custom_events.jsonl"

        # Create mock events with different characteristics
        now = datetime.now(timezone.utc)
        events = [
            {
                "ticker": "AAPL",
                "ts": (now - timedelta(days=i)).isoformat(),
                "cls": {
                    "score": 0.5 + (i * 0.05),
                    "sentiment": 0.3,
                    "keywords": ["earnings"],
                },
                "source": "test_source",
            }
            for i in range(5)
        ]

        # Add events with different characteristics for filtering
        events.extend(
            [
                {
                    "ticker": "TSLA",
                    "ts": (now - timedelta(days=i)).isoformat(),
                    "cls": {
                        "score": 0.2,
                        "sentiment": 0.7,
                        "keywords": ["fda", "approval"],
                    },
                    "source": "fda_source",
                }
                for i in range(3)
            ]
        )

        with open(events_path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_path

    def test_default_data_source(self):
        """Test that default data source is used when not specified."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-01-31",
            initial_capital=10000.0,
        )

        # Should default to "data/events.jsonl"
        assert engine.data_source == "data/events.jsonl"
        assert engine.data_filter is None

    def test_custom_data_source(self, custom_events_file):
        """Test that custom data source is used when specified."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-12-31",
            initial_capital=10000.0,
            data_source=str(custom_events_file),
        )

        assert engine.data_source == str(custom_events_file)

        # Load alerts - should use custom file
        alerts = engine.load_historical_alerts()

        # Should load all events from custom file (within date range)
        assert len(alerts) == 8  # 5 AAPL + 3 TSLA events

    def test_data_filter_applied(self, custom_events_file):
        """Test that data filter is applied to loaded alerts."""

        # Filter to only include AAPL events
        def ticker_filter(alert):
            return alert.get("ticker") == "AAPL"

        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-12-31",
            initial_capital=10000.0,
            data_source=str(custom_events_file),
            data_filter=ticker_filter,
        )

        alerts = engine.load_historical_alerts()

        # Should only have AAPL events
        assert len(alerts) == 5
        assert all(alert["ticker"] == "AAPL" for alert in alerts)

    def test_score_filter_applied(self, custom_events_file):
        """Test filtering by minimum score."""

        # Filter to only include high-score events
        def score_filter(alert):
            score = alert.get("cls", {}).get("score", 0.0)
            return score >= 0.6

        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-12-31",
            initial_capital=10000.0,
            data_source=str(custom_events_file),
            data_filter=score_filter,
        )

        alerts = engine.load_historical_alerts()

        # Should only have events with score >= 0.6
        assert all(alert["cls"]["score"] >= 0.6 for alert in alerts)

    def test_keyword_filter_applied(self, custom_events_file):
        """Test filtering by specific keywords."""

        # Filter to only include FDA-related events
        def keyword_filter(alert):
            keywords = alert.get("cls", {}).get("keywords", [])
            return "fda" in keywords

        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-12-31",
            initial_capital=10000.0,
            data_source=str(custom_events_file),
            data_filter=keyword_filter,
        )

        alerts = engine.load_historical_alerts()

        # Should only have FDA events
        assert len(alerts) == 3
        assert all("fda" in alert["cls"]["keywords"] for alert in alerts)

    def test_combined_filter(self, custom_events_file):
        """Test combining multiple filter conditions."""

        # Complex filter: AAPL with score >= 0.55
        def combined_filter(alert):
            is_aapl = alert.get("ticker") == "AAPL"
            score = alert.get("cls", {}).get("score", 0.0)
            return is_aapl and score >= 0.55

        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-12-31",
            initial_capital=10000.0,
            data_source=str(custom_events_file),
            data_filter=combined_filter,
        )

        alerts = engine.load_historical_alerts()

        # Should only have AAPL events with score >= 0.55
        assert all(alert["ticker"] == "AAPL" for alert in alerts)
        assert all(alert["cls"]["score"] >= 0.55 for alert in alerts)

    def test_no_filter_loads_all(self, custom_events_file):
        """Test that without filter, all alerts are loaded."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-12-31",
            initial_capital=10000.0,
            data_source=str(custom_events_file),
            data_filter=None,  # Explicitly no filter
        )

        alerts = engine.load_historical_alerts()

        # Should load all events
        assert len(alerts) == 8

    def test_nonexistent_file(self):
        """Test handling of nonexistent data source."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-01-31",
            initial_capital=10000.0,
            data_source="nonexistent/path/events.jsonl",
        )

        alerts = engine.load_historical_alerts()

        # Should return empty list without crashing
        assert alerts == []

    def test_backward_compatibility(self):
        """Test that existing code without new parameters still works."""
        # Old-style initialization (no data_source or data_filter)
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-01-31",
            initial_capital=10000.0,
            strategy_params={"min_score": 0.25},
        )

        # Should use default values
        assert engine.data_source == "data/events.jsonl"
        assert engine.data_filter is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
