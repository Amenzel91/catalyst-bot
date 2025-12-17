"""
Time utilities that support both production and simulation modes.

This module provides drop-in replacements for datetime.now() and time.sleep()
that automatically use the simulation clock when running in simulation mode.

Usage:
    from catalyst_bot.time_utils import now, sleep, is_simulation

    # Instead of datetime.now(timezone.utc)
    current_time = now()

    # Instead of time.sleep(seconds)
    sleep(60)

    # Check if we're in simulation mode
    if is_simulation():
        print("Running in simulation")

In production mode, these functions behave exactly like their standard library
counterparts. In simulation mode (when SIMULATION_MODE=1), they delegate to
the simulation clock for virtual time management.
"""

import os
import time as _real_time
from datetime import datetime, timezone
from typing import Optional

# Lazy import to avoid circular dependencies
_simulation_clock_provider = None


def _get_simulation_provider():
    """Lazily import the simulation clock provider."""
    global _simulation_clock_provider
    if _simulation_clock_provider is None:
        try:
            from catalyst_bot.simulation import clock_provider

            _simulation_clock_provider = clock_provider
        except ImportError:
            # Simulation module not available
            _simulation_clock_provider = False
    return _simulation_clock_provider


def is_simulation() -> bool:
    """
    Check if we're running in simulation mode.

    Returns:
        True if SIMULATION_MODE=1 and simulation clock is initialized
    """
    if os.getenv("SIMULATION_MODE", "0") != "1":
        return False

    provider = _get_simulation_provider()
    if provider and provider is not False:
        return provider.is_simulation_mode()
    return False


def now() -> datetime:
    """
    Get the current time (simulation-aware).

    In simulation mode, returns the virtual simulation time.
    In production mode, returns datetime.now(timezone.utc).

    Returns:
        Current datetime with UTC timezone
    """
    if is_simulation():
        provider = _get_simulation_provider()
        if provider:
            return provider.now()

    return datetime.now(timezone.utc)


def sleep(seconds: float) -> None:
    """
    Sleep for the specified duration (simulation-aware).

    In simulation mode, this advances virtual time (returns immediately
    in instant mode, or waits proportionally in accelerated mode).
    In production mode, this calls time.sleep() normally.

    Args:
        seconds: Duration to sleep in seconds
    """
    if seconds <= 0:
        return

    if is_simulation():
        provider = _get_simulation_provider()
        if provider:
            provider.sleep(seconds)
            return

    _real_time.sleep(seconds)


def sleep_interruptible(seconds: float, stop_flag_getter=None) -> bool:
    """
    Sleep with the ability to wake early if a stop flag is set.

    This is useful for main loops that need to respond to shutdown signals.

    Args:
        seconds: Maximum duration to sleep
        stop_flag_getter: Callable that returns True when sleep should stop early

    Returns:
        True if sleep completed normally, False if interrupted by stop flag
    """
    if seconds <= 0:
        return True

    if is_simulation():
        provider = _get_simulation_provider()
        if provider:
            # In simulation mode, just sleep the full duration
            # (instant mode will return immediately anyway)
            provider.sleep(seconds)
            return True

    # In production mode, sleep in small increments checking stop flag
    if stop_flag_getter is None:
        _real_time.sleep(seconds)
        return True

    end_time = _real_time.time() + seconds
    while _real_time.time() < end_time:
        if stop_flag_getter():
            return False
        _real_time.sleep(min(0.2, end_time - _real_time.time()))

    return True


def get_simulation_status() -> Optional[dict]:
    """
    Get detailed simulation status if in simulation mode.

    Returns:
        Status dict with clock info, or None if not in simulation mode
    """
    if not is_simulation():
        return None

    provider = _get_simulation_provider()
    if provider:
        return provider.get_status()
    return None


def monotonic() -> float:
    """
    Get monotonic time (for measuring elapsed time).

    Note: This always returns real monotonic time, even in simulation mode.
    For virtual elapsed time in simulation, use the clock directly.

    Returns:
        Monotonic time in seconds
    """
    return _real_time.monotonic()


# Convenience re-exports
def time() -> float:
    """
    Get current time as a float (seconds since epoch).

    In simulation mode, returns virtual time as float.
    In production mode, returns time.time().
    """
    if is_simulation():
        return now().timestamp()
    return _real_time.time()
