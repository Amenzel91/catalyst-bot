"""
Pytest fixtures for simulation tests.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from catalyst_bot.simulation import SimulationClock, SimulationConfig
from catalyst_bot.simulation import reset as reset_clock_provider

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def simulation_start_time() -> datetime:
    """Standard simulation start time for tests."""
    return datetime(2024, 11, 12, 14, 45, 0, tzinfo=timezone.utc)  # 8:45 CST


@pytest.fixture
def simulation_end_time() -> datetime:
    """Standard simulation end time for tests."""
    return datetime(2024, 11, 12, 15, 45, 0, tzinfo=timezone.utc)  # 9:45 CST


@pytest.fixture
def instant_clock(simulation_start_time, simulation_end_time) -> SimulationClock:
    """SimulationClock at instant speed (0) for fast tests."""
    return SimulationClock(
        start_time=simulation_start_time,
        speed_multiplier=0,
        end_time=simulation_end_time,
    )


@pytest.fixture
def fast_clock(simulation_start_time, simulation_end_time) -> SimulationClock:
    """SimulationClock at 60x speed for tests that need time progression."""
    return SimulationClock(
        start_time=simulation_start_time,
        speed_multiplier=60.0,
        end_time=simulation_end_time,
    )


@pytest.fixture
def realtime_clock(simulation_start_time) -> SimulationClock:
    """SimulationClock at 1x speed (realtime)."""
    return SimulationClock(
        start_time=simulation_start_time,
        speed_multiplier=1.0,
    )


@pytest.fixture
def default_config() -> SimulationConfig:
    """Default simulation configuration."""
    return SimulationConfig(
        enabled=True,
        simulation_date="2024-11-12",
        speed_multiplier=6.0,
        time_preset="morning",
    )


@pytest.fixture
def minimal_config() -> SimulationConfig:
    """Minimal simulation configuration."""
    return SimulationConfig(enabled=True)


@pytest.fixture(autouse=True)
def reset_global_clock():
    """Reset global clock provider after each test."""
    yield
    reset_clock_provider()


# Sample data fixtures


@pytest.fixture
def sample_prices() -> dict:
    """Load sample price data from fixtures."""
    with open(FIXTURES_DIR / "sample_prices.json") as f:
        return json.load(f)


@pytest.fixture
def sample_news() -> list:
    """Load sample news items from fixtures."""
    with open(FIXTURES_DIR / "sample_news.json") as f:
        return json.load(f)


@pytest.fixture
def sample_sec() -> list:
    """Load sample SEC filings from fixtures."""
    with open(FIXTURES_DIR / "sample_sec.json") as f:
        return json.load(f)


@pytest.fixture
def sample_historical_data(sample_prices, sample_news, sample_sec) -> dict:
    """Complete historical data package for simulation tests."""
    return {
        "date": "2024-11-12",
        "fetched_at": "2024-11-12T14:30:00+00:00",
        "price_bars": sample_prices,
        "news_items": sample_news,
        "sec_filings": sample_sec,
        "metadata": {
            "price_source": "test",
            "news_source": "test",
        },
        "ticker_metadata": {
            "AAPL": {
                "float_shares": 15000000000,
                "avg_volume": 50000000,
                "sector": "Technology",
            },
            "TSLA": {
                "float_shares": 3000000000,
                "avg_volume": 100000000,
                "sector": "Consumer Cyclical",
            },
            "NVDA": {
                "float_shares": 2400000000,
                "avg_volume": 40000000,
                "sector": "Technology",
            },
            "ABCD": {
                "float_shares": 50000000,
                "avg_volume": 500000,
                "sector": "Healthcare",
            },
        },
    }
