"""
Tests for time_utils module.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


class TestProductionMode:
    """Tests for production mode (SIMULATION_MODE not set)."""

    def test_is_simulation_false_by_default(self):
        """Test is_simulation returns False when env var not set."""
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SIMULATION_MODE", None)
            # Need to reimport to reset cached state
            import importlib

            import catalyst_bot.time_utils as tu

            tu._simulation_clock_provider = None  # Reset cache
            importlib.reload(tu)

            assert tu.is_simulation() is False

    def test_now_returns_utc_datetime(self):
        """Test now() returns UTC datetime in production mode."""
        from catalyst_bot.time_utils import now

        result = now()

        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_now_is_close_to_real_time(self):
        """Test now() returns approximately current time."""
        from catalyst_bot.time_utils import now

        before = datetime.now(timezone.utc)
        result = now()
        after = datetime.now(timezone.utc)

        assert before <= result <= after

    def test_sleep_actually_waits(self):
        """Test sleep() actually waits in production mode."""
        import time

        from catalyst_bot.time_utils import sleep

        t0 = time.time()
        sleep(0.1)
        elapsed = time.time() - t0

        assert elapsed >= 0.09  # Allow small margin

    def test_sleep_zero_returns_immediately(self):
        """Test sleep(0) returns immediately."""
        import time

        from catalyst_bot.time_utils import sleep

        t0 = time.time()
        sleep(0)
        elapsed = time.time() - t0

        assert elapsed < 0.01

    def test_sleep_negative_returns_immediately(self):
        """Test sleep with negative value returns immediately."""
        import time

        from catalyst_bot.time_utils import sleep

        t0 = time.time()
        sleep(-1)
        elapsed = time.time() - t0

        assert elapsed < 0.01

    def test_time_returns_float(self):
        """Test time() returns float timestamp."""
        from catalyst_bot.time_utils import time

        result = time()

        assert isinstance(result, float)
        assert result > 0

    def test_monotonic_returns_float(self):
        """Test monotonic() returns float."""
        from catalyst_bot.time_utils import monotonic

        result = monotonic()

        assert isinstance(result, float)
        assert result > 0

    def test_get_simulation_status_none_in_production(self):
        """Test get_simulation_status returns None in production."""
        from catalyst_bot.time_utils import get_simulation_status

        result = get_simulation_status()

        assert result is None


class TestSimulationMode:
    """Tests for simulation mode."""

    @pytest.fixture(autouse=True)
    def setup_simulation(self):
        """Set up simulation mode for each test."""
        # Set environment variable
        os.environ["SIMULATION_MODE"] = "1"

        # Initialize simulation clock
        from catalyst_bot.simulation import init_clock, reset

        start_time = datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc)
        init_clock(
            simulation_mode=True,
            start_time=start_time,
            speed_multiplier=0,  # Instant mode
        )

        # Reset time_utils cache
        import catalyst_bot.time_utils as tu

        tu._simulation_clock_provider = None

        yield

        # Cleanup
        reset()
        os.environ.pop("SIMULATION_MODE", None)
        tu._simulation_clock_provider = None

    def test_is_simulation_true(self):
        """Test is_simulation returns True when enabled."""
        from catalyst_bot.time_utils import is_simulation

        assert is_simulation() is True

    def test_now_returns_simulation_time(self):
        """Test now() returns simulation time."""
        from catalyst_bot.time_utils import now

        result = now()

        # Should be the simulation start time
        assert result.year == 2024
        assert result.month == 11
        assert result.day == 12
        assert result.hour == 14
        assert result.minute == 30

    def test_sleep_advances_virtual_time(self):
        """Test sleep() advances virtual time in instant mode."""
        from catalyst_bot.time_utils import now, sleep

        t1 = now()
        sleep(3600)  # 1 hour
        t2 = now()

        elapsed = (t2 - t1).total_seconds()
        assert elapsed == 3600

    def test_sleep_instant_mode_is_immediate(self):
        """Test sleep() returns immediately in instant mode."""
        import time

        from catalyst_bot.time_utils import sleep

        real_t0 = time.time()
        sleep(3600)  # 1 hour virtual time
        real_elapsed = time.time() - real_t0

        # Should be near-instant in real time
        assert real_elapsed < 0.1

    def test_time_returns_simulation_timestamp(self):
        """Test time() returns simulation timestamp as float."""
        from catalyst_bot.time_utils import now, time

        result = time()

        # Should match now().timestamp()
        expected = now().timestamp()
        assert abs(result - expected) < 0.001

    def test_get_simulation_status_returns_dict(self):
        """Test get_simulation_status returns status dict."""
        from catalyst_bot.time_utils import get_simulation_status

        result = get_simulation_status()

        assert isinstance(result, dict)
        assert "current_time" in result
        assert "speed_multiplier" in result


class TestSleepInterruptible:
    """Tests for sleep_interruptible function."""

    def test_completes_normally(self):
        """Test sleep completes normally when not interrupted."""
        from catalyst_bot.time_utils import sleep_interruptible

        result = sleep_interruptible(0.1)

        assert result is True

    def test_returns_false_when_interrupted(self):
        """Test returns False when stop flag is set."""
        from catalyst_bot.time_utils import sleep_interruptible

        stop_flag = False

        def get_stop():
            nonlocal stop_flag
            stop_flag = True  # Set flag on first check
            return stop_flag

        result = sleep_interruptible(1.0, get_stop)

        assert result is False

    def test_zero_duration_returns_true(self):
        """Test zero duration returns True immediately."""
        from catalyst_bot.time_utils import sleep_interruptible

        result = sleep_interruptible(0)

        assert result is True
