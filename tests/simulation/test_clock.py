"""
Tests for SimulationClock.
"""

import time as real_time
from datetime import datetime, timedelta, timezone

from catalyst_bot.simulation import SimulationClock


class TestSimulationClockBasics:
    """Basic clock functionality tests."""

    def test_clock_initialization(self, simulation_start_time, simulation_end_time):
        """Test clock initializes with correct parameters."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=6.0,
            end_time=simulation_end_time,
        )

        assert clock.start_time == simulation_start_time
        assert clock.end_time == simulation_end_time
        assert clock.speed_multiplier == 6.0
        assert not clock._paused

    def test_clock_adds_timezone_if_missing(self):
        """Test clock adds UTC timezone to naive datetime."""
        naive_time = datetime(2024, 11, 12, 9, 0, 0)
        clock = SimulationClock(start_time=naive_time)

        assert clock.start_time.tzinfo == timezone.utc

    def test_clock_now_returns_start_time_initially(self, simulation_start_time):
        """Test now() returns approximately start_time immediately after init."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=1.0,
        )

        now = clock.now()
        diff = abs((now - simulation_start_time).total_seconds())

        # Should be within 1 second of start time
        assert diff < 1.0


class TestInstantMode:
    """Tests for instant mode (speed_multiplier=0)."""

    def test_instant_mode_starts_at_start_time(
        self, instant_clock, simulation_start_time
    ):
        """Test instant mode clock starts at start_time."""
        assert instant_clock.now() == simulation_start_time

    def test_instant_mode_sleep_advances_time(
        self, instant_clock, simulation_start_time
    ):
        """Test sleep() advances time in instant mode."""
        instant_clock.sleep(60)  # Sleep 60 virtual seconds

        expected = simulation_start_time + timedelta(seconds=60)
        assert instant_clock.now() == expected

    def test_instant_mode_sleep_does_not_wait(self, instant_clock):
        """Test sleep() doesn't actually wait in instant mode."""
        start = real_time.monotonic()
        instant_clock.sleep(3600)  # Sleep 1 virtual hour
        elapsed = real_time.monotonic() - start

        # Should complete nearly instantly (< 0.1 seconds)
        assert elapsed < 0.1

    def test_instant_mode_multiple_sleeps_accumulate(
        self, instant_clock, simulation_start_time
    ):
        """Test multiple sleeps accumulate correctly."""
        instant_clock.sleep(30)
        instant_clock.sleep(30)
        instant_clock.sleep(60)

        expected = simulation_start_time + timedelta(seconds=120)
        assert instant_clock.now() == expected


class TestSpeedMultiplier:
    """Tests for different speed multipliers."""

    def test_6x_speed_advances_faster(self, simulation_start_time):
        """Test 6x speed advances 6 times faster than realtime."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=6.0,
        )

        # Wait a short real time
        real_time.sleep(0.1)  # 100ms real

        now = clock.now()
        virtual_elapsed = (now - simulation_start_time).total_seconds()

        # At 6x speed, 0.1s real = ~0.6s virtual (with some tolerance)
        assert 0.4 < virtual_elapsed < 0.8

    def test_60x_speed_for_fast_tests(self, fast_clock, simulation_start_time):
        """Test 60x speed works for fast test scenarios."""
        # Wait 50ms real time
        real_time.sleep(0.05)

        now = fast_clock.now()
        virtual_elapsed = (now - simulation_start_time).total_seconds()

        # At 60x speed, 0.05s real = ~3s virtual
        assert 2.0 < virtual_elapsed < 4.0


class TestJumpTo:
    """Tests for jump_to and jump_to_time_cst."""

    def test_jump_to_specific_time(self, instant_clock, simulation_start_time):
        """Test jumping to a specific datetime."""
        # Jump forward 30 minutes (within simulation bounds)
        target = simulation_start_time + timedelta(minutes=30)
        instant_clock.jump_to(target)

        assert instant_clock.now() == target

    def test_jump_to_time_cst(self, instant_clock):
        """Test jumping to a specific CST time."""
        # Jump to 9:30 CST = 15:30 UTC
        instant_clock.jump_to_time_cst(9, 30)

        now = instant_clock.now()
        assert now.hour == 15
        assert now.minute == 30

    def test_jump_forward_in_non_instant_mode(self, fast_clock, simulation_start_time):
        """Test jump_to works in non-instant mode."""
        # Jump forward 30 minutes (within simulation bounds)
        target = simulation_start_time + timedelta(minutes=30)
        fast_clock.jump_to(target)

        # now() should return approximately target
        diff = abs((fast_clock.now() - target).total_seconds())
        assert diff < 1.0


class TestPauseResume:
    """Tests for pause/resume functionality."""

    def test_pause_stops_time_advancement(self, fast_clock, simulation_start_time):
        """Test pause prevents time from advancing."""
        fast_clock.pause()

        # Wait some real time
        real_time.sleep(0.1)

        # Virtual time should not have advanced much
        virtual_elapsed = (fast_clock.now() - simulation_start_time).total_seconds()
        assert virtual_elapsed < 0.5  # Should be nearly zero

    def test_resume_continues_time(self, fast_clock, simulation_start_time):
        """Test resume continues time advancement."""
        fast_clock.pause()
        real_time.sleep(0.05)
        fast_clock.resume()

        # Wait more time
        real_time.sleep(0.05)

        # Time should now be advancing
        virtual_elapsed = (fast_clock.now() - simulation_start_time).total_seconds()
        assert virtual_elapsed > 1.0  # Should have advanced

    def test_pause_resume_multiple_times(self, fast_clock, simulation_start_time):
        """Test multiple pause/resume cycles work correctly."""
        fast_clock.pause()
        real_time.sleep(0.02)
        fast_clock.resume()

        fast_clock.pause()
        real_time.sleep(0.02)
        fast_clock.resume()

        # Should still be tracking time correctly
        assert fast_clock.now() > simulation_start_time


class TestEndTime:
    """Tests for end time handling."""

    def test_is_past_end_false_initially(self, instant_clock):
        """Test is_past_end returns False at start."""
        assert not instant_clock.is_past_end()

    def test_is_past_end_true_after_end(self, instant_clock, simulation_end_time):
        """Test is_past_end returns True after reaching end."""
        instant_clock.jump_to(simulation_end_time + timedelta(minutes=1))
        assert instant_clock.is_past_end()

    def test_now_clamped_to_end_time(self, instant_clock, simulation_end_time):
        """Test now() doesn't exceed end_time."""
        # Advance way past end
        instant_clock.sleep(7200)  # 2 hours

        assert instant_clock.now() == simulation_end_time

    def test_no_end_time_means_no_limit(self, simulation_start_time):
        """Test clock without end_time has no limit."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=0,
        )

        # Advance 24 hours
        clock.sleep(86400)

        assert not clock.is_past_end()
        expected = simulation_start_time + timedelta(days=1)
        assert clock.now() == expected


class TestSetSpeed:
    """Tests for changing speed dynamically."""

    def test_set_speed_changes_multiplier(self, instant_clock):
        """Test set_speed updates the speed multiplier."""
        instant_clock.set_speed(10.0)
        assert instant_clock.speed_multiplier == 10.0

    def test_set_speed_preserves_current_time(self, fast_clock, simulation_start_time):
        """Test changing speed preserves current virtual time."""
        # Let some time pass
        real_time.sleep(0.05)

        time_before = fast_clock.now()
        fast_clock.set_speed(1.0)  # Change to realtime
        time_after = fast_clock.now()

        # Times should be very close (within 0.5 seconds)
        diff = abs((time_after - time_before).total_seconds())
        assert diff < 0.5

    def test_switch_to_instant_mode(self, fast_clock):
        """Test switching from realtime to instant mode."""
        real_time.sleep(0.02)
        time_before = fast_clock.now()

        fast_clock.set_speed(0)

        # Should preserve time (within small tolerance due to timing)
        time_after = fast_clock.now()
        diff = abs((time_after - time_before).total_seconds())
        assert diff < 0.1  # Within 100ms

        # Now advancing should be instant
        fast_clock.sleep(60)
        expected = time_after + timedelta(seconds=60)
        assert fast_clock.now() == expected


class TestElapsedTime:
    """Tests for elapsed time tracking."""

    def test_elapsed_virtual(self, instant_clock, simulation_start_time):
        """Test elapsed_virtual returns correct duration."""
        instant_clock.sleep(120)

        elapsed = instant_clock.elapsed_virtual()
        assert elapsed == timedelta(seconds=120)

    def test_elapsed_real(self, instant_clock):
        """Test elapsed_real tracks real time."""
        real_time.monotonic()
        instant_clock.sleep(1000)  # Instant, no real time
        elapsed_real = instant_clock.elapsed_real()

        # Should be very small (the sleep was instant)
        assert elapsed_real < 0.1

    def test_remaining_with_end_time(self, instant_clock):
        """Test remaining() returns correct duration."""
        # Start: 14:45, End: 15:45 = 1 hour = 3600 seconds
        remaining = instant_clock.remaining()
        assert remaining == timedelta(hours=1)

    def test_remaining_after_advancement(self, instant_clock):
        """Test remaining() updates after time advances."""
        instant_clock.sleep(1800)  # 30 minutes

        remaining = instant_clock.remaining()
        assert remaining == timedelta(minutes=30)


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_returns_dict(self, instant_clock):
        """Test get_status returns a dictionary."""
        status = instant_clock.get_status()
        assert isinstance(status, dict)

    def test_get_status_contains_expected_keys(self, instant_clock):
        """Test get_status contains all expected keys."""
        status = instant_clock.get_status()

        expected_keys = [
            "current_time",
            "start_time",
            "end_time",
            "speed_multiplier",
            "is_paused",
            "elapsed_virtual_seconds",
            "elapsed_real_seconds",
            "remaining_seconds",
            "is_past_end",
        ]

        for key in expected_keys:
            assert key in status
