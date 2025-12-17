"""
Integration tests for alerts.py simulation mode support.

Tests that send_alert_safe() correctly routes alerts to the simulation logger
when running in simulation mode instead of posting to Discord.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from catalyst_bot.alerts import (
    get_simulation_logger,
    send_alert_safe,
    set_simulation_logger,
)
from catalyst_bot.simulation import init_clock
from catalyst_bot.simulation import reset as reset_clock


class TestSimulationLoggerInjection:
    """Tests for the simulation logger injection mechanism."""

    def teardown_method(self):
        """Clean up after each test."""
        set_simulation_logger(None)

    def test_set_and_get_logger(self):
        """Test that we can set and retrieve the simulation logger."""
        # Initially should be None
        assert get_simulation_logger() is None

        # Create a mock logger
        mock_logger = MagicMock()

        # Set it
        set_simulation_logger(mock_logger)
        assert get_simulation_logger() is mock_logger

        # Clear it
        set_simulation_logger(None)
        assert get_simulation_logger() is None

    def test_logger_persists_across_calls(self):
        """Test that logger persists across multiple calls."""
        mock_logger = MagicMock()
        set_simulation_logger(mock_logger)

        # Multiple gets should return same instance
        assert get_simulation_logger() is mock_logger
        assert get_simulation_logger() is mock_logger


class TestSendAlertSafeSimulationMode:
    """Tests for send_alert_safe() simulation mode behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )
        self.mock_logger = MagicMock()
        set_simulation_logger(self.mock_logger)

    def teardown_method(self):
        """Clean up after each test."""
        set_simulation_logger(None)
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    def test_routes_to_simulation_logger(self):
        """Test that alerts are routed to simulation logger in sim mode."""
        item_dict = {
            "ticker": "AAPL",
            "title": "Test News Title",
            "source": "test_source",
            "link": "https://example.com/news",
        }
        scored = MagicMock()
        scored.total_score = 0.85
        scored.tags = ["earnings", "catalyst"]

        result = send_alert_safe(
            item_dict=item_dict,
            scored=scored,
            last_price=150.0,
            last_change_pct=2.5,
        )

        # Should return True (success)
        assert result is True

        # Logger should have been called
        self.mock_logger.log_alert.assert_called_once()

        # Verify call arguments
        call_kwargs = self.mock_logger.log_alert.call_args[1]
        assert call_kwargs["ticker"] == "AAPL"
        assert call_kwargs["title"] == "Test News Title"
        assert call_kwargs["score"] == 0.85
        assert call_kwargs["price"] == 150.0
        assert call_kwargs["change_pct"] == 2.5
        assert call_kwargs["source"] == "test_source"

    def test_skips_discord_in_simulation_mode(self):
        """Test that Discord is not called in simulation mode."""
        item_dict = {
            "ticker": "MSFT",
            "title": "Another Test",
            "source": "test",
        }

        with patch("catalyst_bot.alerts.post_discord_json") as mock_discord:
            result = send_alert_safe(
                item_dict=item_dict,
                scored=None,
                last_price=300.0,
            )

            # Should succeed
            assert result is True

            # Discord should NOT have been called
            mock_discord.assert_not_called()

    def test_handles_dict_scored_item(self):
        """Test handling of dict-style scored item."""
        item_dict = {
            "ticker": "TSLA",
            "title": "Tesla News",
            "source": "pr_newswire",
        }
        scored = {
            "total_score": 0.72,
            "relevance": 0.8,
            "tags": ["electric_vehicle"],
        }

        result = send_alert_safe(
            item_dict=item_dict,
            scored=scored,
            last_price=200.0,
        )

        assert result is True
        call_kwargs = self.mock_logger.log_alert.call_args[1]
        assert call_kwargs["score"] == 0.72

    def test_handles_relevance_fallback(self):
        """Test that relevance is used as fallback for score."""
        item_dict = {
            "ticker": "NVDA",
            "title": "GPU News",
            "source": "test",
        }
        scored = MagicMock()
        scored.total_score = None  # No total_score
        scored.relevance = 0.65
        scored.tags = []
        # Remove total_score attribute
        del scored.total_score

        result = send_alert_safe(
            item_dict=item_dict,
            scored=scored,
            last_price=500.0,
        )

        assert result is True
        call_kwargs = self.mock_logger.log_alert.call_args[1]
        assert call_kwargs["score"] == 0.65

    def test_handles_logger_error_gracefully(self):
        """Test that logger errors are handled gracefully."""
        self.mock_logger.log_alert.side_effect = Exception("Logger error")

        item_dict = {
            "ticker": "AMD",
            "title": "Test",
            "source": "test",
        }

        # Should still return True (success) even if logger fails
        result = send_alert_safe(
            item_dict=item_dict,
            scored=None,
            last_price=100.0,
        )

        assert result is True


class TestProductionModeUnaffected:
    """Tests that production mode behavior is unchanged."""

    def setup_method(self):
        """Ensure not in simulation mode."""
        os.environ.pop("SIMULATION_MODE", None)
        reset_clock()
        set_simulation_logger(None)

    def teardown_method(self):
        """Clean up."""
        set_simulation_logger(None)

    def test_simulation_logger_ignored_in_production(self):
        """Test that simulation logger is ignored when not in sim mode."""
        # Even if a logger is set, it should be ignored in production
        mock_logger = MagicMock()
        set_simulation_logger(mock_logger)

        item_dict = {
            "ticker": "TEST",
            "title": "Production Test",
            "source": "test",
        }

        # This will fail (no webhook) but shouldn't use sim logger
        result = send_alert_safe(
            item_dict=item_dict,
            scored=None,
            last_price=10.0,
        )

        # Should return False (no webhook configured)
        assert result is False

        # Simulation logger should NOT have been called
        mock_logger.log_alert.assert_not_called()


class TestAlertTimeUtilsIntegration:
    """Tests for time utilities integration in alerts.py."""

    def setup_method(self):
        """Set up simulation environment."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up."""
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)
        set_simulation_logger(None)

    def test_relative_time_uses_simulation_clock(self):
        """Test that relative time calculations use simulation clock."""
        from catalyst_bot.alerts import _format_time_ago

        # News published 30 minutes before simulation start (14:00 vs 14:30)
        pub_time_str = "2024-11-12T14:00:00+00:00"

        result = _format_time_ago(pub_time_str)

        # Should show 30 minutes ago (relative to simulation time)
        assert "30min ago" in result

    def test_freshness_check_uses_simulation_time(self):
        """Test freshness validation uses simulation time."""
        from catalyst_bot.time_utils import now as sim_now

        # Verify sim_now returns simulation time
        current = sim_now()
        assert current.year == 2024
        assert current.month == 11
        assert current.day == 12
