"""
clock_provider - Global clock management for simulation/production modes.

Provides a unified interface for time operations that works in both
live (production) and simulation modes. Other modules should import
time functions from here instead of using datetime/time directly.

Usage:
    from catalyst_bot.simulation.clock_provider import now, sleep, is_simulation_mode

    # Get current time (returns UTC datetime)
    current_time = now()

    # Sleep for duration (respects simulation speed)
    sleep(60)  # Sleep 60 seconds (or faster in simulation)

    # Check mode
    if is_simulation_mode():
        print("Running in simulation")

Setup (called once at startup):
    # For production mode (default)
    init_clock(simulation_mode=False)

    # For simulation mode
    init_clock(
        simulation_mode=True,
        start_time=datetime(2024, 11, 12, 9, 0, tzinfo=timezone.utc),
        speed_multiplier=6.0,
        end_time=datetime(2024, 11, 12, 16, 0, tzinfo=timezone.utc)
    )
"""

import logging
import time as _real_time
from datetime import datetime, timezone
from typing import Optional

from .clock import SimulationClock

log = logging.getLogger(__name__)

# Global clock instance
_clock: Optional[SimulationClock] = None
_simulation_mode: bool = False
_simulation_run_id: Optional[str] = None


def init_clock(
    simulation_mode: bool = False,
    start_time: Optional[datetime] = None,
    speed_multiplier: float = 6.0,
    end_time: Optional[datetime] = None,
    run_id: Optional[str] = None,
) -> None:
    """
    Initialize the global clock.

    Must be called once at application startup before using any time functions.

    Args:
        simulation_mode: True for simulation, False for production
        start_time: Start time for simulation (required if simulation_mode=True)
        speed_multiplier: Simulation speed (only used in simulation mode)
        end_time: Optional end time for simulation
        run_id: Optional simulation run ID for tracking

    Raises:
        ValueError: If simulation_mode=True but start_time not provided
    """
    global _clock, _simulation_mode, _simulation_run_id

    _simulation_mode = simulation_mode
    _simulation_run_id = run_id

    if simulation_mode:
        if start_time is None:
            raise ValueError("start_time required when simulation_mode=True")

        _clock = SimulationClock(
            start_time=start_time,
            speed_multiplier=speed_multiplier,
            end_time=end_time,
        )
        log.info(
            f"Clock initialized in SIMULATION mode: {start_time.isoformat()} "
            f"at {speed_multiplier}x speed"
        )
    else:
        _clock = None
        log.debug("Clock initialized in PRODUCTION mode (real time)")


def init_from_env() -> None:
    """
    Initialize clock from environment variables.

    Environment Variables:
        SIMULATION_MODE: "1" or "true" to enable simulation
        SIMULATION_DATE: Date to simulate (YYYY-MM-DD)
        SIMULATION_PRESET: Time preset (morning, sec, open, close, full)
        SIMULATION_START_TIME_CST: Custom start time (HH:MM)
        SIMULATION_END_TIME_CST: Custom end time (HH:MM)
        SIMULATION_SPEED: Speed multiplier (default 6.0)
        SIMULATION_RUN_ID: Optional run identifier
    """
    from .config import SimulationConfig

    config = SimulationConfig.from_env()

    if not config.enabled:
        init_clock(simulation_mode=False)
        return

    # Apply preset if specified
    config.apply_preset()

    sim_date = config.get_simulation_date()
    start_time = config.get_start_time(sim_date)
    end_time = config.get_end_time(sim_date)
    run_id = config.generate_run_id()

    init_clock(
        simulation_mode=True,
        start_time=start_time,
        speed_multiplier=config.speed_multiplier,
        end_time=end_time,
        run_id=run_id,
    )


def now() -> datetime:
    """
    Get the current time (UTC).

    In production mode, returns the real current time.
    In simulation mode, returns the virtual simulation time.

    Returns:
        Current time as a timezone-aware UTC datetime
    """
    if _simulation_mode and _clock is not None:
        return _clock.now()
    return datetime.now(timezone.utc)


def sleep(seconds: float) -> None:
    """
    Sleep for the specified duration.

    In production mode, sleeps for real time.
    In simulation mode, sleeps for virtual time (respecting speed multiplier).

    Args:
        seconds: Duration to sleep in seconds
    """
    if seconds <= 0:
        return

    if _simulation_mode and _clock is not None:
        _clock.sleep(seconds)
    else:
        _real_time.sleep(seconds)


def is_simulation_mode() -> bool:
    """
    Check if running in simulation mode.

    Returns:
        True if simulation mode is active, False for production
    """
    return _simulation_mode


def get_clock() -> Optional[SimulationClock]:
    """
    Get the underlying SimulationClock (if in simulation mode).

    Returns:
        SimulationClock instance or None if in production mode
    """
    return _clock


def get_simulation_run_id() -> Optional[str]:
    """
    Get the current simulation run ID.

    Returns:
        Run ID string or None if not in simulation mode
    """
    return _simulation_run_id


def is_past_end() -> bool:
    """
    Check if simulation has passed its end time.

    Returns:
        True if past end time (or False in production mode)
    """
    if _simulation_mode and _clock is not None:
        return _clock.is_past_end()
    return False


def get_status() -> dict:
    """
    Get current clock status.

    Returns:
        Dict with mode and clock state information
    """
    base_status = {
        "mode": "simulation" if _simulation_mode else "production",
        "current_time": now().isoformat(),
        "run_id": _simulation_run_id,
    }

    if _simulation_mode and _clock is not None:
        base_status.update(_clock.get_status())

    return base_status


# Convenience functions for advanced simulation control


def pause() -> None:
    """Pause the simulation clock (no effect in production mode)."""
    if _simulation_mode and _clock is not None:
        _clock.pause()


def resume() -> None:
    """Resume the simulation clock (no effect in production mode)."""
    if _simulation_mode and _clock is not None:
        _clock.resume()


def jump_to(target_time: datetime) -> None:
    """
    Jump to a specific time (only works in simulation mode).

    Args:
        target_time: The time to jump to
    """
    if _simulation_mode and _clock is not None:
        _clock.jump_to(target_time)


def jump_to_time_cst(hour: int, minute: int = 0) -> None:
    """
    Jump to a specific time in CST (only works in simulation mode).

    Args:
        hour: Hour in CST (0-23)
        minute: Minute (0-59)
    """
    if _simulation_mode and _clock is not None:
        _clock.jump_to_time_cst(hour, minute)


def set_speed(multiplier: float) -> None:
    """
    Change simulation speed (only works in simulation mode).

    Args:
        multiplier: New speed (0 = instant, 1 = realtime, 6 = 6x, etc.)
    """
    if _simulation_mode and _clock is not None:
        _clock.set_speed(multiplier)


def reset() -> None:
    """
    Reset the clock provider to uninitialized state.

    Primarily for testing purposes.
    """
    global _clock, _simulation_mode, _simulation_run_id
    _clock = None
    _simulation_mode = False
    _simulation_run_id = None
