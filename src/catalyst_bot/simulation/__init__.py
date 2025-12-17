"""
Catalyst-Bot Simulation Environment

Provides time-accelerated trading day simulations for testing
and validation without affecting production systems.

Quick Start:
    # Run default simulation (Nov 12 2024, morning preset, 6x speed)
    python -m catalyst_bot.simulation.cli

    # Test SEC filing period
    python -m catalyst_bot.simulation.cli --preset sec

    # Full day at instant speed
    python -m catalyst_bot.simulation.cli --preset full --speed 0

Programmatic Usage:
    from catalyst_bot.simulation import SimulationController

    controller = SimulationController(
        simulation_date="2024-11-12",
        time_preset="morning",
        speed_multiplier=6.0
    )
    results = await controller.run()

Time Functions (use instead of datetime/time):
    from catalyst_bot.simulation.clock_provider import now, sleep

    current = now()  # Returns simulation time (or real time in production)
    sleep(60)  # Sleeps 60 virtual seconds (faster in simulation)

Configuration:
    Set SIMULATION_MODE=1 in .env to enable simulation mode.
    See SimulationConfig for all configuration options.
"""

# Core components - Phase 1
from .clock import SimulationClock
from .clock_provider import (
    get_clock,
    get_simulation_run_id,
    get_status,
    init_clock,
    init_from_env,
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
from .config import TIME_PRESETS, SimulationConfig

# Controller - Phase 5
from .controller import SimulationController, SimulationSetupError

# Data fetcher - Phase 4
from .data_fetcher import HistoricalDataFetcher

# Event system - Phase 3
from .event_queue import EventQueue, EventReplayer, EventType, SimulationEvent

# Logger - Phase 4
from .logger import Severity, SimulationLogger

# Mock broker - Phase 3
from .mock_broker import (
    MockBroker,
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedOrder,
    SimulatedPosition,
)
from .mock_feeds import MockFeedProvider

# Data layer - Phase 2
from .mock_market_data import MockMarketDataFeed

__all__ = [
    # Clock
    "SimulationClock",
    # Clock provider functions
    "init_clock",
    "init_from_env",
    "now",
    "sleep",
    "is_simulation_mode",
    "get_clock",
    "get_simulation_run_id",
    "is_past_end",
    "get_status",
    "pause",
    "resume",
    "jump_to",
    "jump_to_time_cst",
    "set_speed",
    "reset",
    # Config
    "SimulationConfig",
    "TIME_PRESETS",
    # Data layer
    "MockMarketDataFeed",
    "MockFeedProvider",
    # Event system
    "EventQueue",
    "EventReplayer",
    "EventType",
    "SimulationEvent",
    # Mock broker
    "MockBroker",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "SimulatedOrder",
    "SimulatedPosition",
    # Data fetcher
    "HistoricalDataFetcher",
    # Logger
    "SimulationLogger",
    "Severity",
    # Controller
    "SimulationController",
    "SimulationSetupError",
]

__version__ = "0.1.0"
