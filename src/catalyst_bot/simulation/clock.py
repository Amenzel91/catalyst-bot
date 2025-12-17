"""
SimulationClock - Virtual clock for time-accelerated simulations.

Provides deterministic time control for replaying historical trading days
at configurable speeds (1x realtime, 6x, 60x, or instant).

Example:
    clock = SimulationClock(
        start_time=datetime(2024, 11, 12, 9, 0, tzinfo=timezone.utc),
        speed_multiplier=6.0,  # 6x speed: 1 hour sim = 10 minutes real
        end_time=datetime(2024, 11, 12, 16, 0, tzinfo=timezone.utc)
    )

    # Get current virtual time
    current = clock.now()  # Returns simulation time

    # Sleep in virtual time (respects speed multiplier)
    clock.sleep(60)  # Sleeps 10 real seconds at 6x speed

    # Jump to specific time
    clock.jump_to_time_cst(9, 30)  # Jump to 9:30 CST
"""

import logging
import time as _real_time
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)


class SimulationClock:
    """
    Virtual clock for time-accelerated simulations.

    Maintains a virtual time that advances faster (or slower) than real time.
    All time-sensitive operations should use this clock in simulation mode.

    Attributes:
        start_time: When the simulation begins (virtual time)
        end_time: When the simulation ends (virtual time, optional)
        speed_multiplier: How fast virtual time passes (1.0 = realtime, 6.0 = 6x, 0 = instant)
        _real_start: Real-world time when simulation started
        _paused: Whether the clock is currently paused
        _pause_start: Real-world time when pause began
        _total_pause_time: Accumulated pause duration
    """

    def __init__(
        self,
        start_time: datetime,
        speed_multiplier: float = 1.0,
        end_time: Optional[datetime] = None,
    ):
        """
        Initialize a simulation clock.

        Args:
            start_time: The virtual time to start at (should be timezone-aware UTC)
            speed_multiplier: Speed factor (1.0 = realtime, 6.0 = 6x faster, 0 = instant)
            end_time: Optional end time for the simulation
        """
        # Ensure timezone-aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        self.start_time = start_time
        self.end_time = end_time
        self.speed_multiplier = speed_multiplier

        # Real-world anchor for calculating elapsed time
        self._real_start = _real_time.monotonic()

        # Pause tracking
        self._paused = False
        self._pause_start: Optional[float] = None
        self._total_pause_time = 0.0

        # For instant mode (speed=0), track virtual time directly
        self._instant_time = start_time if speed_multiplier == 0 else None

        log.debug(
            f"SimulationClock initialized: start={start_time.isoformat()}, "
            f"speed={speed_multiplier}x, end={end_time.isoformat() if end_time else 'None'}"
        )

    def now(self) -> datetime:
        """
        Get the current virtual time.

        Returns:
            Current simulation time as a timezone-aware datetime
        """
        if self._instant_time is not None:
            current = self._instant_time
        else:
            if self._paused:
                # Return time at pause start
                real_elapsed = (
                    self._pause_start - self._real_start - self._total_pause_time
                )
            else:
                real_elapsed = (
                    _real_time.monotonic() - self._real_start - self._total_pause_time
                )

            # Virtual time = real time * speed multiplier
            virtual_elapsed = real_elapsed * self.speed_multiplier
            current = self.start_time + timedelta(seconds=virtual_elapsed)

        # Clamp to end time if specified
        if self.end_time and current > self.end_time:
            return self.end_time

        return current

    def sleep(self, virtual_seconds: float) -> None:
        """
        Sleep for a duration in virtual time.

        At 6x speed, sleeping 60 virtual seconds only takes 10 real seconds.
        At instant speed (0), returns immediately but advances virtual time.

        Args:
            virtual_seconds: Duration to sleep in virtual (simulation) time
        """
        if virtual_seconds <= 0:
            return

        if self.speed_multiplier == 0:
            # Instant mode: just advance the virtual time
            if self._instant_time is not None:
                self._instant_time += timedelta(seconds=virtual_seconds)
            return

        # Calculate real sleep duration
        real_sleep = virtual_seconds / self.speed_multiplier

        # Handle pause during sleep
        remaining = real_sleep
        while remaining > 0 and not self.is_past_end():
            if self._paused:
                _real_time.sleep(0.1)  # Check pause status periodically
                continue

            # Sleep in small chunks to allow interrupt
            chunk = min(remaining, 0.5)
            _real_time.sleep(chunk)
            remaining -= chunk

    def is_past_end(self) -> bool:
        """
        Check if simulation has passed the end time.

        Returns:
            True if current virtual time >= end_time
        """
        if self.end_time is None:
            return False
        return self.now() >= self.end_time

    def pause(self) -> None:
        """Pause the clock (virtual time stops advancing)."""
        if not self._paused:
            self._paused = True
            self._pause_start = _real_time.monotonic()
            log.debug("SimulationClock paused")

    def resume(self) -> None:
        """Resume the clock after a pause."""
        if self._paused and self._pause_start is not None:
            pause_duration = _real_time.monotonic() - self._pause_start
            self._total_pause_time += pause_duration
            self._paused = False
            self._pause_start = None
            log.debug(f"SimulationClock resumed (paused for {pause_duration:.2f}s)")

    def jump_to(self, target_time: datetime) -> None:
        """
        Jump to a specific virtual time.

        Useful for skipping to market open, SEC filing window, etc.

        Args:
            target_time: The virtual time to jump to
        """
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)

        if self.speed_multiplier == 0:
            # Instant mode: just set the time directly
            self._instant_time = target_time
        else:
            # Calculate what real_start would need to be for now() to return target_time
            # virtual_time = start_time + (real_elapsed * speed)
            # target_time = start_time + (real_elapsed * speed)
            # real_elapsed = (target_time - start_time) / speed
            virtual_offset = (target_time - self.start_time).total_seconds()
            needed_real_elapsed = virtual_offset / self.speed_multiplier

            # Reset the real start to match
            self._real_start = _real_time.monotonic() - needed_real_elapsed
            self._total_pause_time = 0.0

        log.debug(f"SimulationClock jumped to {target_time.isoformat()}")

    def jump_to_time_cst(self, hour: int, minute: int = 0, second: int = 0) -> None:
        """
        Jump to a specific time of day in CST (Central Standard Time).

        Maintains the current simulation date, just changes the time.

        Args:
            hour: Hour in CST (0-23)
            minute: Minute (0-59)
            second: Second (0-59)
        """
        current = self.now()

        # CST is UTC-6 (offset not needed for calculation, just for reference)
        utc_hour = (hour + 6) % 24

        # If adding 6 hours rolls over to next day, adjust
        day_offset = (hour + 6) // 24

        target = current.replace(
            hour=utc_hour, minute=minute, second=second, microsecond=0
        )

        if day_offset > 0:
            target += timedelta(days=day_offset)

        self.jump_to(target)

    def set_speed(self, multiplier: float) -> None:
        """
        Change the simulation speed.

        Args:
            multiplier: New speed multiplier (0 = instant, 1 = realtime, 6 = 6x, etc.)
        """
        if multiplier == self.speed_multiplier:
            return

        # Capture current virtual time before changing speed
        current = self.now()

        if multiplier == 0:
            # Switching to instant mode
            self._instant_time = current
        else:
            # Switching from instant or changing speed
            if self._instant_time is not None:
                # Coming from instant mode, set up real-time tracking
                self._instant_time = None

            # Reset real_start so now() returns current time at new speed
            virtual_offset = (current - self.start_time).total_seconds()
            needed_real_elapsed = virtual_offset / multiplier
            self._real_start = _real_time.monotonic() - needed_real_elapsed
            self._total_pause_time = 0.0

        self.speed_multiplier = multiplier
        log.debug(f"SimulationClock speed changed to {multiplier}x")

    def elapsed_virtual(self) -> timedelta:
        """
        Get total virtual time elapsed since simulation start.

        Returns:
            timedelta representing elapsed virtual time
        """
        return self.now() - self.start_time

    def elapsed_real(self) -> float:
        """
        Get total real time elapsed since simulation start.

        Returns:
            Elapsed real time in seconds
        """
        return _real_time.monotonic() - self._real_start - self._total_pause_time

    def remaining(self) -> Optional[timedelta]:
        """
        Get remaining virtual time until end_time.

        Returns:
            timedelta until end, or None if no end_time set
        """
        if self.end_time is None:
            return None
        remaining = self.end_time - self.now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    def get_status(self) -> dict:
        """
        Get clock status for monitoring/debugging.

        Returns:
            Dict with clock state information
        """
        return {
            "current_time": self.now().isoformat(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "speed_multiplier": self.speed_multiplier,
            "is_paused": self._paused,
            "elapsed_virtual_seconds": self.elapsed_virtual().total_seconds(),
            "elapsed_real_seconds": self.elapsed_real(),
            "remaining_seconds": (
                self.remaining().total_seconds() if self.remaining() else None
            ),
            "is_past_end": self.is_past_end(),
        }
