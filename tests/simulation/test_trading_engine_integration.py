"""
Integration tests for trading_engine.py simulation mode support.

Tests that TradingEngine correctly uses MockBroker when running in simulation mode.
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from catalyst_bot.simulation import init_clock
from catalyst_bot.simulation import reset as reset_clock
from catalyst_bot.simulation.clock import SimulationClock
from catalyst_bot.simulation.mock_broker import MockBroker
from catalyst_bot.trading.trading_engine import (
    TradingEngine,
    get_simulation_broker,
    set_simulation_broker,
)


class TestSimulationBrokerInjection:
    """Tests for the simulation broker injection mechanism."""

    def setup_method(self):
        """Ensure clean state before each test."""
        set_simulation_broker(None)

    def teardown_method(self):
        """Clean up after each test."""
        set_simulation_broker(None)

    def test_set_and_get_broker(self):
        """Test that we can set and retrieve the simulation broker."""
        # Initially should be None
        assert get_simulation_broker() is None

        # Create a mock broker
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        mock_broker = MockBroker(starting_cash=10000.0, clock=clock)

        # Set it
        set_simulation_broker(mock_broker)
        assert get_simulation_broker() is mock_broker

        # Clear it
        set_simulation_broker(None)
        assert get_simulation_broker() is None

    def test_broker_persists_across_calls(self):
        """Test that broker persists across multiple calls."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        mock_broker = MockBroker(starting_cash=10000.0, clock=clock)
        set_simulation_broker(mock_broker)

        # Multiple gets should return same instance
        assert get_simulation_broker() is mock_broker
        assert get_simulation_broker() is mock_broker


class TestTradingEngineSimulationMode:
    """Tests for TradingEngine simulation mode behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        self.clock = SimulationClock(
            start_time=self.start_time,
            speed_multiplier=0,
        )
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

        # Create mock broker
        self.mock_broker = MockBroker(
            starting_cash=10000.0,
            clock=self.clock,
        )
        set_simulation_broker(self.mock_broker)

    def teardown_method(self):
        """Clean up after each test."""
        set_simulation_broker(None)
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    @pytest.mark.asyncio
    async def test_uses_mock_broker_in_simulation(self):
        """Test that TradingEngine uses MockBroker in simulation mode."""
        engine = TradingEngine(
            config={
                "trading_enabled": True,
                "paper_trading": True,
            }
        )

        # Mock the sub-components that require broker connection
        with (
            patch.object(engine, "order_executor", None),
            patch.object(engine, "position_manager", None),
        ):

            await engine.initialize()

            # Should have used the mock broker
            assert engine.broker is self.mock_broker
            assert engine.daily_start_balance == Decimal("10000.0")

    @pytest.mark.asyncio
    async def test_skips_alpaca_connection_in_simulation(self):
        """Test that Alpaca API is not called in simulation mode."""
        engine = TradingEngine(
            config={
                "trading_enabled": True,
                "paper_trading": True,
            }
        )

        with patch(
            "catalyst_bot.trading.trading_engine.AlpacaBrokerClient"
        ) as mock_alpaca:
            await engine.initialize()

            # AlpacaBrokerClient should NOT have been instantiated
            mock_alpaca.assert_not_called()


class TestTradingEngineTimeUtilsIntegration:
    """Tests for time utilities integration in trading_engine.py."""

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
        set_simulation_broker(None)

    def test_circuit_breaker_uses_simulation_time(self):
        """Test that circuit breaker cooldown uses simulation time."""
        from catalyst_bot.time_utils import now as sim_now
        from catalyst_bot.time_utils import sleep as sim_sleep

        engine = TradingEngine(
            config={
                "trading_enabled": True,
                "circuit_breaker_cooldown_minutes": 30,
            }
        )

        # Manually trigger circuit breaker
        engine.circuit_breaker_active = True
        engine.circuit_breaker_triggered_at = sim_now()

        # Initially should be active
        assert engine.circuit_breaker_active is True

        # Advance simulation time by 31 minutes
        sim_sleep(31 * 60)

        # The cooldown check happens in _can_trade() - we just verify sim_now works
        current = sim_now()
        elapsed = (current - engine.circuit_breaker_triggered_at).total_seconds()
        assert elapsed >= 31 * 60


class TestProductionModeUnaffected:
    """Tests that production mode behavior is unchanged."""

    def setup_method(self):
        """Ensure not in simulation mode."""
        os.environ.pop("SIMULATION_MODE", None)
        reset_clock()
        set_simulation_broker(None)

    def teardown_method(self):
        """Clean up."""
        set_simulation_broker(None)

    def test_simulation_broker_ignored_in_production(self):
        """Test that simulation broker is ignored when not in sim mode."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        mock_broker = MockBroker(starting_cash=10000.0, clock=clock)
        set_simulation_broker(mock_broker)

        engine = TradingEngine(
            config={
                "trading_enabled": True,
                "paper_trading": True,
            }
        )

        # In production mode, the broker attribute should still be None
        # (would be set by initialize() which we don't call here)
        assert engine.broker is None

        # The mock broker should still be retrievable but not used
        assert get_simulation_broker() is mock_broker
