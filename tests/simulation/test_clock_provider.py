"""
Tests for clock_provider module.
"""

import time as real_time
from datetime import datetime, timedelta, timezone

import pytest

from catalyst_bot.simulation.clock_provider import (
    get_clock,
    get_simulation_run_id,
    get_status,
    init_clock,
    is_past_end,
    is_simulation_mode,
    jump_to,
    jump_to_time_cst,
    now,
    pause,
    reset,
    resume,
    set_speed,
    sleep,
)


class TestProductionMode:
    """Tests for production (real time) mode."""

    def test_init_production_mode(self):
        """Test initializing in production mode."""
        init_clock(simulation_mode=False)

        assert is_simulation_mode() is False
        assert get_clock() is None

    def test_now_returns_real_time_in_production(self):
        """Test now() returns real time in production mode."""
        init_clock(simulation_mode=False)

        before = datetime.now(timezone.utc)
        result = now()
        after = datetime.now(timezone.utc)

        assert before <= result <= after

    def test_sleep_waits_in_production(self):
        """Test sleep() actually waits in production mode."""
        init_clock(simulation_mode=False)

        start = real_time.monotonic()
        sleep(0.1)  # 100ms
        elapsed = real_time.monotonic() - start

        assert elapsed >= 0.09  # Should wait at least 90ms

    def test_is_past_end_false_in_production(self):
        """Test is_past_end always returns False in production."""
        init_clock(simulation_mode=False)

        assert is_past_end() is False


class TestSimulationMode:
    """Tests for simulation mode."""

    def test_init_simulation_mode_requires_start_time(self):
        """Test simulation mode requires start_time."""
        with pytest.raises(ValueError, match="start_time required"):
            init_clock(simulation_mode=True)

    def test_init_simulation_mode(self):
        """Test initializing in simulation mode."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)

        init_clock(
            simulation_mode=True,
            start_time=start,
            speed_multiplier=6.0,
        )

        assert is_simulation_mode() is True
        assert get_clock() is not None

    def test_now_returns_simulation_time(self):
        """Test now() returns simulation time in sim mode."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)

        init_clock(
            simulation_mode=True,
            start_time=start,
            speed_multiplier=0,  # Instant
        )

        result = now()
        assert result == start

    def test_sleep_advances_simulation_time(self):
        """Test sleep() advances simulation time."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)

        init_clock(
            simulation_mode=True,
            start_time=start,
            speed_multiplier=0,  # Instant
        )

        sleep(60)  # 60 virtual seconds

        expected = start + timedelta(seconds=60)
        assert now() == expected

    def test_simulation_run_id(self):
        """Test simulation run ID is tracked."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)

        init_clock(
            simulation_mode=True,
            start_time=start,
            run_id="test_run_123",
        )

        assert get_simulation_run_id() == "test_run_123"


class TestSimulationControls:
    """Tests for simulation control functions."""

    @pytest.fixture(autouse=True)
    def setup_simulation(self):
        """Set up simulation mode for control tests."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 11, 12, 22, 0, 0, tzinfo=timezone.utc)  # Later end time

        init_clock(
            simulation_mode=True,
            start_time=start,
            speed_multiplier=0,
            end_time=end,
        )

    def test_pause_and_resume(self):
        """Test pause and resume functions."""
        pause()
        clock = get_clock()
        assert clock._paused is True

        resume()
        assert clock._paused is False

    def test_jump_to(self):
        """Test jump_to function."""
        target = datetime(2024, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        jump_to(target)

        assert now() == target

    def test_jump_to_time_cst(self):
        """Test jump_to_time_cst function."""
        # Jump to 10:30 CST = 16:30 UTC
        jump_to_time_cst(10, 30)

        current = now()
        assert current.hour == 16
        assert current.minute == 30

    def test_set_speed(self):
        """Test set_speed function."""
        set_speed(10.0)

        clock = get_clock()
        assert clock.speed_multiplier == 10.0

    def test_is_past_end_in_simulation(self):
        """Test is_past_end in simulation mode."""
        assert is_past_end() is False

        # Jump past end (end is 22:00 UTC from fixture)
        end = datetime(2024, 11, 12, 23, 0, 0, tzinfo=timezone.utc)
        jump_to(end)

        assert is_past_end() is True


class TestGetStatus:
    """Tests for get_status function."""

    def test_production_status(self):
        """Test status in production mode."""
        init_clock(simulation_mode=False)

        status = get_status()

        assert status["mode"] == "production"
        assert "current_time" in status

    def test_simulation_status(self):
        """Test status in simulation mode."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)

        init_clock(
            simulation_mode=True,
            start_time=start,
            speed_multiplier=6.0,
            run_id="test_123",
        )

        status = get_status()

        assert status["mode"] == "simulation"
        assert status["run_id"] == "test_123"
        assert status["speed_multiplier"] == 6.0


class TestReset:
    """Tests for reset function."""

    def test_reset_clears_state(self):
        """Test reset clears all state."""
        start = datetime(2024, 11, 12, 9, 0, 0, tzinfo=timezone.utc)

        init_clock(
            simulation_mode=True,
            start_time=start,
            run_id="test_123",
        )

        assert is_simulation_mode() is True

        reset()

        assert is_simulation_mode() is False
        assert get_clock() is None
        assert get_simulation_run_id() is None


class TestControlsNoOpInProduction:
    """Test control functions are no-op in production mode."""

    @pytest.fixture(autouse=True)
    def setup_production(self):
        """Set up production mode."""
        init_clock(simulation_mode=False)

    def test_pause_no_op(self):
        """Test pause is no-op in production."""
        pause()  # Should not raise

    def test_resume_no_op(self):
        """Test resume is no-op in production."""
        resume()  # Should not raise

    def test_jump_to_no_op(self):
        """Test jump_to is no-op in production."""
        target = datetime(2024, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        jump_to(target)  # Should not raise

    def test_set_speed_no_op(self):
        """Test set_speed is no-op in production."""
        set_speed(100.0)  # Should not raise


class TestSleepEdgeCases:
    """Tests for sleep edge cases."""

    def test_sleep_zero_returns_immediately(self):
        """Test sleep(0) returns immediately."""
        init_clock(simulation_mode=False)

        start = real_time.monotonic()
        sleep(0)
        elapsed = real_time.monotonic() - start

        assert elapsed < 0.01

    def test_sleep_negative_returns_immediately(self):
        """Test sleep with negative value returns immediately."""
        init_clock(simulation_mode=False)

        start = real_time.monotonic()
        sleep(-10)
        elapsed = real_time.monotonic() - start

        assert elapsed < 0.01
