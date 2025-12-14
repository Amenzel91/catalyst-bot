# Trading Simulation Environment - Implementation Plan

## Executive Summary

This document outlines the implementation plan for a comprehensive trading simulation environment that allows running historical trading days through the Catalyst-Bot system for **bug discovery and feature testing**.

### Goals
- Simulate complete trading days using reconstructed historical data
- Fire alerts exactly as they would during live trading
- Execute simulated paper trades with mocked broker (no API calls)
- Support time acceleration (1x, 6x, 60x speed) with presets
- Jump to specific times for stress testing (morning news, SEC filings)
- Mark all generated data as simulation to prevent analytics pollution
- Control everything via feature flags in `.env`

### Non-Goals
- This is NOT a backtesting system for generating trading performance data
- This is NOT for parameter optimization or strategy discovery
- This focuses on functional testing, not statistical analysis

---

## Confirmed Decisions (from design review)

### Primary Use Case
- **Quick sanity checks** after code changes: 1-hour simulated period at 6x speed (~10 min real time)
- **Bug discovery** and **feature testing** - NOT performance analysis

### Test Configuration
| Setting | Value |
|---------|-------|
| **Default Test Date** | November 12, 2024 (Tuesday, normal market day) |
| **Default Speed** | 6x (1 hour sim = 10 min real) |
| **Time Presets** | `morning` (8:45-9:45am EST), `sec` (3:30-4:30pm EST) |

### Component Behavior During Simulation
| Component | Behavior | Notes |
|-----------|----------|-------|
| **LLM (Gemini)** | LIVE | Test actual classification |
| **Local Sentiment** | LIVE | VADER/FinBERT are fast |
| **External Sentiment APIs** | MOCKED | Pre-fetched, stored data |
| **Discord Alerts** | LIVE | Fires to test channels |
| **Charts** | DISABLED | Skip generation |
| **Broker** | MOCKED | Full position monitoring |
| **Heartbeat** | Normal intervals | Same as production |

### Data Handling
- **Incomplete data**: Skip ticker entirely with WARNING, don't process partial
- **Missing prices**: Log warning explaining why ticker was skipped
- **Pre-flight check**: Verify all APIs reachable before starting

### Logging & Output
- **Format**: JSONL (machine) + Markdown (human)
- **Severity Levels**: CRITICAL, WARNING, NOTICE
- **Warning Thresholds**: Configurable via `.env`, defaults match production

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SIMULATION MODE                               │
│  (SIMULATION_MODE=1 in .env)                                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SimulationController                             │
│  - Manages simulation lifecycle                                      │
│  - Controls SimulationClock                                         │
│  - Coordinates all mock components                                   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ SimulationClock │    │  EventReplayer  │    │  MockBroker     │
│ - Virtual time  │    │  - News feeds   │    │  - Order fills  │
│ - Acceleration  │    │  - SEC filings  │    │  - Positions    │
│ - Jump-to-time  │    │  - Price data   │    │  - Portfolio    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Existing Bot Components                           │
│  runner.py → feeds.py → classify.py → alerts.py → trading_engine   │
│  (Modified to use injected clock and data sources)                  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SimulationOutputManager                           │
│  - Marks all data with simulation_run_id                            │
│  - Routes alerts to test channel OR local log                       │
│  - Writes to separate simulation database                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Infrastructure

### 1.1 SimulationClock

The foundation of the simulation - a virtual clock that replaces `datetime.now()` and `time.sleep()` throughout the system.

**File:** `src/catalyst_bot/simulation/clock.py`

```python
"""
SimulationClock - Virtual time management for trading simulations.

Provides:
- Virtual time that can be accelerated (1x, 10x, 100x)
- Jump-to-time functionality for stress testing specific periods
- Drop-in replacement for datetime.now() and time.sleep()
- Thread-safe operations
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, List
import threading
import time as real_time

class SimulationClock:
    """
    Virtual clock for simulation mode.

    Usage:
        clock = SimulationClock(
            start_time=datetime(2025, 1, 15, 4, 0, tzinfo=timezone.utc),  # 4am UTC = premarket
            speed_multiplier=10.0  # 10x speed
        )

        # Get current virtual time
        now = clock.now()

        # Sleep in virtual time (returns immediately at high speed)
        clock.sleep(30)  # 30 virtual seconds

        # Jump to specific time
        clock.jump_to(datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc))  # Jump to 9:30 ET
    """

    def __init__(
        self,
        start_time: datetime,
        speed_multiplier: float = 1.0,
        end_time: Optional[datetime] = None
    ):
        self._start_time = start_time
        self._current_time = start_time
        self._speed_multiplier = speed_multiplier
        self._end_time = end_time
        self._paused = False
        self._lock = threading.RLock()

        # Callbacks for time-based events
        self._time_callbacks: List[tuple] = []  # (trigger_time, callback, called)

        # Real time tracking for acceleration
        self._real_start = real_time.monotonic()

    def now(self) -> datetime:
        """Get current virtual time."""
        with self._lock:
            if self._speed_multiplier == 0 or self._paused:
                return self._current_time

            # Calculate elapsed real time since last update
            real_elapsed = real_time.monotonic() - self._real_start
            virtual_elapsed = real_elapsed * self._speed_multiplier

            new_time = self._start_time + timedelta(seconds=virtual_elapsed)

            # Don't exceed end time
            if self._end_time and new_time > self._end_time:
                return self._end_time

            return new_time

    def sleep(self, seconds: float) -> None:
        """
        Sleep for virtual seconds.

        At 10x speed, sleeping 30 virtual seconds takes 3 real seconds.
        At 0 speed (instant mode), returns immediately.
        """
        if self._speed_multiplier == 0:
            # Instant mode - just advance time
            with self._lock:
                self._current_time += timedelta(seconds=seconds)
            return

        real_sleep = seconds / self._speed_multiplier
        real_time.sleep(real_sleep)

    def jump_to(self, target_time: datetime) -> None:
        """
        Jump to a specific time instantly.

        Useful for stress testing specific periods (e.g., 8am CST news rush).
        """
        with self._lock:
            if target_time < self._current_time:
                raise ValueError(f"Cannot jump backwards: {target_time} < {self._current_time}")

            self._current_time = target_time
            # Reset real time tracking
            self._start_time = target_time
            self._real_start = real_time.monotonic()

            # Fire any callbacks that should have triggered
            self._check_callbacks()

    def jump_to_market_open(self) -> None:
        """Jump to market open (9:30 AM ET) on current simulation day."""
        current = self.now()
        market_open = current.replace(hour=14, minute=30, second=0, microsecond=0)  # 9:30 ET = 14:30 UTC
        if market_open > current:
            self.jump_to(market_open)

    def jump_to_time_cst(self, hour: int, minute: int = 0) -> None:
        """Jump to specific CST time on current simulation day."""
        current = self.now()
        # CST = UTC-6
        utc_hour = (hour + 6) % 24
        target = current.replace(hour=utc_hour, minute=minute, second=0, microsecond=0)
        if target > current:
            self.jump_to(target)

    def set_speed(self, multiplier: float) -> None:
        """Change simulation speed (1.0 = realtime, 10.0 = 10x, 0 = instant)."""
        with self._lock:
            # Capture current time before speed change
            current = self.now()
            self._current_time = current
            self._start_time = current
            self._real_start = real_time.monotonic()
            self._speed_multiplier = multiplier

    def pause(self) -> None:
        """Pause the simulation clock."""
        with self._lock:
            self._current_time = self.now()
            self._paused = True

    def resume(self) -> None:
        """Resume the simulation clock."""
        with self._lock:
            self._start_time = self._current_time
            self._real_start = real_time.monotonic()
            self._paused = False

    def register_callback(self, trigger_time: datetime, callback: Callable) -> None:
        """Register a callback to fire at a specific virtual time."""
        with self._lock:
            self._time_callbacks.append((trigger_time, callback, False))
            self._time_callbacks.sort(key=lambda x: x[0])

    def _check_callbacks(self) -> None:
        """Check and fire any pending callbacks."""
        current = self.now()
        for i, (trigger_time, callback, called) in enumerate(self._time_callbacks):
            if not called and trigger_time <= current:
                self._time_callbacks[i] = (trigger_time, callback, True)
                callback(trigger_time)

    @property
    def is_market_open(self) -> bool:
        """Check if virtual time is during regular market hours."""
        current = self.now()
        # Convert to ET (UTC-5 or UTC-4 depending on DST)
        # Simplified: assume UTC-5
        et_hour = (current.hour - 5) % 24

        if current.weekday() >= 5:  # Weekend
            return False

        # Regular hours: 9:30 AM - 4:00 PM ET
        if et_hour < 9 or (et_hour == 9 and current.minute < 30):
            return False
        if et_hour >= 16:
            return False

        return True

    @property
    def market_status(self) -> str:
        """Get current market status based on virtual time."""
        current = self.now()
        et_hour = (current.hour - 5) % 24

        if current.weekday() >= 5:
            return "closed"

        if 4 <= et_hour < 9 or (et_hour == 9 and current.minute < 30):
            return "pre_market"
        elif 9 <= et_hour < 16 or (et_hour == 9 and current.minute >= 30):
            return "regular"
        elif 16 <= et_hour < 20:
            return "after_hours"
        else:
            return "closed"
```

### 1.2 Clock Provider (Dependency Injection)

**File:** `src/catalyst_bot/simulation/clock_provider.py`

```python
"""
ClockProvider - Global clock instance management.

Allows swapping between real clock and simulation clock via feature flag.
"""

from datetime import datetime, timezone
from typing import Optional
import time as real_time

from .clock import SimulationClock

# Global clock instance
_clock: Optional[SimulationClock] = None
_simulation_mode: bool = False


def init_clock(
    simulation_mode: bool = False,
    start_time: Optional[datetime] = None,
    speed_multiplier: float = 1.0,
    end_time: Optional[datetime] = None
) -> None:
    """
    Initialize the global clock.

    Call this at application startup based on SIMULATION_MODE env var.
    """
    global _clock, _simulation_mode

    _simulation_mode = simulation_mode

    if simulation_mode:
        if start_time is None:
            raise ValueError("start_time required for simulation mode")

        _clock = SimulationClock(
            start_time=start_time,
            speed_multiplier=speed_multiplier,
            end_time=end_time
        )
    else:
        _clock = None


def now() -> datetime:
    """
    Get current time (virtual or real based on mode).

    Use this instead of datetime.now() throughout the codebase.
    """
    if _simulation_mode and _clock:
        return _clock.now()
    return datetime.now(timezone.utc)


def sleep(seconds: float) -> None:
    """
    Sleep for specified seconds (virtual or real based on mode).

    Use this instead of time.sleep() throughout the codebase.
    """
    if _simulation_mode and _clock:
        _clock.sleep(seconds)
    else:
        real_time.sleep(seconds)


def get_clock() -> Optional[SimulationClock]:
    """Get the simulation clock instance (None if in live mode)."""
    return _clock if _simulation_mode else None


def is_simulation_mode() -> bool:
    """Check if running in simulation mode."""
    return _simulation_mode
```

### 1.3 Feature Flags Configuration

**Additions to `.env.example`:**

```ini
# ============================================================================
# SIMULATION MODE CONFIGURATION
# ============================================================================

# Master switch for simulation mode (0=live, 1=simulation)
SIMULATION_MODE=0

# Simulation date to replay (YYYY-MM-DD format)
# Default: 2024-11-12 (Tuesday, good test day with normal market conditions)
SIMULATION_DATE=2024-11-12

# Simulation speed multiplier
# 1.0 = real-time, 6.0 = 6x speed (default), 60.0 = 60x, 0 = instant
SIMULATION_SPEED=6.0

# Time preset (overrides start/end times)
# Options: "morning" (8:45-9:45 EST), "sec" (3:30-4:30 EST),
#          "open", "close", "full"
SIMULATION_PRESET=morning

# Jump to specific time on simulation start (HH:MM in CST)
# Only used if SIMULATION_PRESET is empty
SIMULATION_START_TIME_CST=

# End simulation at specific time (HH:MM in CST)
# Only used if SIMULATION_PRESET is empty
SIMULATION_END_TIME_CST=

# Simulation run ID (auto-generated if empty)
SIMULATION_RUN_ID=

# ============================================================================
# COMPONENT BEHAVIOR
# ============================================================================

# LLM classification (Gemini) - LIVE by default to test actual behavior
SIMULATION_LLM_ENABLED=1

# Local sentiment (VADER/FinBERT) - LIVE, these are fast
SIMULATION_LOCAL_SENTIMENT=1

# External sentiment APIs - MOCKED (use pre-fetched data)
SIMULATION_EXTERNAL_SENTIMENT=0

# Chart generation - DISABLED by default
SIMULATION_CHARTS_ENABLED=0

# ============================================================================
# SIMULATION DATA SOURCES
# ============================================================================

# Historical price data source: "tiingo", "yfinance", "cached"
SIMULATION_PRICE_SOURCE=tiingo

# Historical news data source: "finnhub", "cached"
SIMULATION_NEWS_SOURCE=finnhub

# Cache directory for simulation data
SIMULATION_CACHE_DIR=data/simulation_cache

# Skip tickers with incomplete data (recommended: 1)
SIMULATION_SKIP_INCOMPLETE=1

# ============================================================================
# SIMULATION OUTPUT CONFIGURATION
# ============================================================================

# Where to send alerts during simulation
# "discord_test" = fire to test channels (default)
# "local_only" = log only, no Discord
# "disabled" = silent
SIMULATION_ALERT_OUTPUT=discord_test

# Separate database for simulation data
SIMULATION_DB_PATH=data/simulation.db

# Log directory for simulation runs
SIMULATION_LOG_DIR=data/simulation_logs

# ============================================================================
# SIMULATION BROKER CONFIGURATION
# ============================================================================

# Starting cash for simulated portfolio
SIMULATION_STARTING_CASH=10000.0

# Slippage model: "none", "fixed", "adaptive"
SIMULATION_SLIPPAGE_MODEL=adaptive

# Fixed slippage percentage (if using fixed model)
SIMULATION_SLIPPAGE_PCT=0.5

# Maximum percentage of daily volume per trade
SIMULATION_MAX_VOLUME_PCT=5.0
```

### 1.4 Configuration Class Updates

**File:** `src/catalyst_bot/simulation/config.py`

```python
"""
Simulation-specific configuration.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import os
import random


def _b(key: str, default: bool = False) -> bool:
    """Parse boolean from environment."""
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes", "y", "on")


# Time presets for common testing scenarios
TIME_PRESETS = {
    "morning": {"start": "07:45", "end": "08:45"},  # 8:45-9:45 EST = 7:45-8:45 CST (news rush)
    "sec": {"start": "14:30", "end": "15:30"},      # 3:30-4:30 EST = 2:30-3:30 CST (SEC filings)
    "open": {"start": "08:30", "end": "09:30"},     # Market open hour
    "close": {"start": "14:00", "end": "15:00"},    # Market close hour
    "full": {"start": "04:00", "end": "17:00"},     # Full trading day
}


@dataclass
class SimulationConfig:
    """Configuration for simulation mode."""

    # Core settings
    enabled: bool = False
    simulation_date: Optional[str] = "2024-11-12"  # Default: Nov 12, 2024 (good test day)
    speed_multiplier: float = 6.0  # Default: 6x (1hr sim = 10min real)
    start_time_cst: Optional[str] = None
    end_time_cst: Optional[str] = None
    time_preset: Optional[str] = None  # "morning", "sec", "open", "close", "full"
    run_id: Optional[str] = None

    # Data sources
    price_source: str = "tiingo"
    news_source: str = "finnhub"
    cache_dir: Path = Path("data/simulation_cache")

    # Output - Discord alerts fire to test channels by default
    alert_output: str = "discord_test"  # "discord_test", "local_only", "disabled"
    db_path: Path = Path("data/simulation.db")
    log_dir: Path = Path("data/simulation_logs")

    # Component behavior
    llm_enabled: bool = True        # LIVE - test actual classification
    local_sentiment: bool = True    # LIVE - VADER/FinBERT
    external_sentiment: bool = False  # MOCKED - use pre-fetched data
    charts_enabled: bool = False    # DISABLED - skip generation

    # Broker simulation
    starting_cash: float = 10000.0
    slippage_model: str = "adaptive"
    slippage_pct: float = 0.5
    max_volume_pct: float = 5.0

    # Warning thresholds (default to production values)
    skip_incomplete_data: bool = True  # Skip tickers with missing data

    @classmethod
    def from_env(cls) -> "SimulationConfig":
        """Load configuration from environment variables."""
        return cls(
            enabled=_b("SIMULATION_MODE", False),
            simulation_date=os.getenv("SIMULATION_DATE", "2024-11-12"),
            speed_multiplier=float(os.getenv("SIMULATION_SPEED", "6.0")),
            start_time_cst=os.getenv("SIMULATION_START_TIME_CST") or None,
            end_time_cst=os.getenv("SIMULATION_END_TIME_CST") or None,
            time_preset=os.getenv("SIMULATION_PRESET") or None,
            run_id=os.getenv("SIMULATION_RUN_ID") or None,
            price_source=os.getenv("SIMULATION_PRICE_SOURCE", "tiingo"),
            news_source=os.getenv("SIMULATION_NEWS_SOURCE", "finnhub"),
            cache_dir=Path(os.getenv("SIMULATION_CACHE_DIR", "data/simulation_cache")),
            alert_output=os.getenv("SIMULATION_ALERT_OUTPUT", "discord_test"),
            db_path=Path(os.getenv("SIMULATION_DB_PATH", "data/simulation.db")),
            log_dir=Path(os.getenv("SIMULATION_LOG_DIR", "data/simulation_logs")),
            llm_enabled=_b("SIMULATION_LLM_ENABLED", True),
            local_sentiment=_b("SIMULATION_LOCAL_SENTIMENT", True),
            external_sentiment=_b("SIMULATION_EXTERNAL_SENTIMENT", False),
            charts_enabled=_b("SIMULATION_CHARTS_ENABLED", False),
            starting_cash=float(os.getenv("SIMULATION_STARTING_CASH", "10000.0")),
            slippage_model=os.getenv("SIMULATION_SLIPPAGE_MODEL", "adaptive"),
            slippage_pct=float(os.getenv("SIMULATION_SLIPPAGE_PCT", "0.5")),
            max_volume_pct=float(os.getenv("SIMULATION_MAX_VOLUME_PCT", "5.0")),
            skip_incomplete_data=_b("SIMULATION_SKIP_INCOMPLETE", True),
        )

    def apply_preset(self) -> None:
        """Apply time preset if specified."""
        if self.time_preset and self.time_preset in TIME_PRESETS:
            preset = TIME_PRESETS[self.time_preset]
            self.start_time_cst = preset["start"]
            self.end_time_cst = preset["end"]

    def get_simulation_date(self) -> datetime:
        """Get simulation date, picking random recent trading day if not specified."""
        if self.simulation_date:
            return datetime.strptime(self.simulation_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        # Pick random trading day from last 30 days
        today = datetime.now(timezone.utc).date()
        candidates = []

        for i in range(1, 31):
            day = today - timedelta(days=i)
            # Skip weekends
            if day.weekday() < 5:
                candidates.append(day)

        selected = random.choice(candidates)
        return datetime.combine(selected, datetime.min.time()).replace(tzinfo=timezone.utc)

    def get_start_time(self, sim_date: datetime) -> datetime:
        """Get start time for simulation."""
        if self.start_time_cst:
            hour, minute = map(int, self.start_time_cst.split(":"))
            # CST = UTC-6
            utc_hour = (hour + 6) % 24
            return sim_date.replace(hour=utc_hour, minute=minute, second=0, microsecond=0)

        # Default: 4am ET (premarket start) = 9am UTC
        return sim_date.replace(hour=9, minute=0, second=0, microsecond=0)

    def get_end_time(self, sim_date: datetime) -> datetime:
        """Get end time for simulation."""
        if self.end_time_cst:
            hour, minute = map(int, self.end_time_cst.split(":"))
            utc_hour = (hour + 6) % 24
            return sim_date.replace(hour=utc_hour, minute=minute, second=0, microsecond=0)

        # Default: 5pm ET (after hours end) = 10pm UTC
        return sim_date.replace(hour=22, minute=0, second=0, microsecond=0)

    def generate_run_id(self) -> str:
        """Generate unique simulation run ID."""
        if self.run_id:
            return self.run_id

        import uuid
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"sim_{timestamp}_{short_uuid}"
```

---

## Phase 2: Historical Data Reconstruction

### 2.1 Data Fetcher for Historical Days

**File:** `src/catalyst_bot/simulation/data_fetcher.py`

```python
"""
HistoricalDataFetcher - Reconstruct a trading day from APIs.

Fetches:
- Intraday price data (1-minute bars)
- News articles published that day
- SEC filings from that day
- Market metadata (float, volume, etc.)
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import hashlib
import logging

log = logging.getLogger(__name__)


class HistoricalDataFetcher:
    """
    Fetch and cache historical trading data for simulation.

    Usage:
        fetcher = HistoricalDataFetcher(cache_dir=Path("data/simulation_cache"))

        # Fetch all data for a specific day
        data = await fetcher.fetch_day(
            date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            tickers=["AAPL", "TSLA", "NVDA"]  # Optional: limit to specific tickers
        )

        # Data structure:
        # {
        #     "date": "2025-01-15",
        #     "price_bars": {"AAPL": [...], "TSLA": [...]},
        #     "news_items": [...],
        #     "sec_filings": [...],
        #     "metadata": {...}
        # }
    """

    def __init__(
        self,
        cache_dir: Path,
        price_source: str = "tiingo",
        news_source: str = "finnhub"
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.price_source = price_source
        self.news_source = news_source

    async def fetch_day(
        self,
        date: datetime,
        tickers: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Fetch all data for a trading day.

        Args:
            date: The trading day to fetch
            tickers: Optional list of tickers to focus on (fetches all if None)
            use_cache: Whether to use cached data if available

        Returns:
            Complete data package for simulation replay
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = self._cache_key(date_str, tickers)
        cache_file = self.cache_dir / f"{cache_key}.json"

        # Check cache first
        if use_cache and cache_file.exists():
            log.info(f"Loading cached simulation data for {date_str}")
            with open(cache_file) as f:
                return json.load(f)

        log.info(f"Fetching historical data for {date_str}")

        # Fetch all data components
        data = {
            "date": date_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "price_bars": {},
            "news_items": [],
            "sec_filings": [],
            "metadata": {
                "price_source": self.price_source,
                "news_source": self.news_source,
            }
        }

        # 1. Fetch news items for the day
        data["news_items"] = await self._fetch_news(date)

        # 2. Extract tickers from news if not provided
        if tickers is None:
            tickers = self._extract_tickers_from_news(data["news_items"])
            log.info(f"Extracted {len(tickers)} tickers from news: {tickers[:10]}...")

        # 3. Fetch price data for all tickers
        data["price_bars"] = await self._fetch_prices(date, tickers)

        # 4. Fetch SEC filings
        data["sec_filings"] = await self._fetch_sec_filings(date)

        # 5. Fetch metadata for tickers
        data["ticker_metadata"] = await self._fetch_ticker_metadata(tickers)

        # Cache the data
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

        log.info(f"Cached simulation data: {len(data['news_items'])} news, "
                 f"{len(data['price_bars'])} tickers, {len(data['sec_filings'])} SEC filings")

        return data

    async def _fetch_news(self, date: datetime) -> List[Dict]:
        """Fetch news articles from the specified day."""
        news_items = []

        if self.news_source == "finnhub":
            news_items = await self._fetch_finnhub_news(date)
        elif self.news_source == "cached":
            news_items = self._load_cached_news(date)

        # Sort by timestamp
        news_items.sort(key=lambda x: x.get("timestamp", ""))

        return news_items

    async def _fetch_finnhub_news(self, date: datetime) -> List[Dict]:
        """Fetch news from Finnhub API for a specific date."""
        # Import Finnhub client
        from ..finnhub_client import get_finnhub_client

        client = get_finnhub_client()
        if not client:
            log.warning("Finnhub client not available, returning empty news")
            return []

        date_str = date.strftime("%Y-%m-%d")
        next_day = (date + timedelta(days=1)).strftime("%Y-%m-%d")

        try:
            # Fetch general market news
            news = client.general_news("general", _from=date_str, to=next_day)

            items = []
            for article in news:
                items.append({
                    "id": str(article.get("id")),
                    "timestamp": datetime.fromtimestamp(
                        article.get("datetime", 0),
                        tz=timezone.utc
                    ).isoformat(),
                    "title": article.get("headline", ""),
                    "summary": article.get("summary", ""),
                    "source": article.get("source", "finnhub"),
                    "url": article.get("url", ""),
                    "related_tickers": article.get("related", "").split(","),
                    "category": article.get("category", ""),
                })

            return items

        except Exception as e:
            log.error(f"Failed to fetch Finnhub news: {e}")
            return []

    async def _fetch_prices(self, date: datetime, tickers: List[str]) -> Dict[str, List[Dict]]:
        """Fetch intraday price bars for all tickers."""
        from ..market import get_intraday

        price_bars = {}
        date_str = date.strftime("%Y-%m-%d")

        for ticker in tickers:
            try:
                # Fetch 1-minute bars for the day
                bars = await self._fetch_ticker_bars(ticker, date)
                if bars:
                    price_bars[ticker] = bars
            except Exception as e:
                log.warning(f"Failed to fetch prices for {ticker}: {e}")

        return price_bars

    async def _fetch_ticker_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Fetch intraday bars for a single ticker."""
        if self.price_source == "tiingo":
            return await self._fetch_tiingo_bars(ticker, date)
        elif self.price_source == "yfinance":
            return await self._fetch_yfinance_bars(ticker, date)
        else:
            return []

    async def _fetch_tiingo_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Fetch from Tiingo IEX API."""
        import aiohttp
        from ..config import get_settings

        settings = get_settings()
        api_key = settings.tiingo_api_key

        if not api_key:
            return []

        date_str = date.strftime("%Y-%m-%d")
        url = f"https://api.tiingo.com/iex/{ticker}/prices"
        params = {
            "startDate": date_str,
            "endDate": date_str,
            "resampleFreq": "1min",
            "token": api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        return []

                    data = await resp.json()

                    bars = []
                    for bar in data:
                        bars.append({
                            "timestamp": bar.get("date"),
                            "open": bar.get("open"),
                            "high": bar.get("high"),
                            "low": bar.get("low"),
                            "close": bar.get("close"),
                            "volume": bar.get("volume"),
                        })

                    return bars

        except Exception as e:
            log.warning(f"Tiingo fetch failed for {ticker}: {e}")
            return []

    async def _fetch_yfinance_bars(self, ticker: str, date: datetime) -> List[Dict]:
        """Fetch from yfinance."""
        import yfinance as yf

        date_str = date.strftime("%Y-%m-%d")
        next_day = (date + timedelta(days=1)).strftime("%Y-%m-%d")

        try:
            df = yf.download(
                ticker,
                start=date_str,
                end=next_day,
                interval="1m",
                progress=False
            )

            if df.empty:
                return []

            bars = []
            for timestamp, row in df.iterrows():
                bars.append({
                    "timestamp": timestamp.isoformat(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                })

            return bars

        except Exception as e:
            log.warning(f"yfinance fetch failed for {ticker}: {e}")
            return []

    async def _fetch_sec_filings(self, date: datetime) -> List[Dict]:
        """Fetch SEC filings from the specified day."""
        # This would integrate with your existing SEC feed code
        # For now, return empty - can be populated from sec_events.jsonl
        return []

    async def _fetch_ticker_metadata(self, tickers: List[str]) -> Dict[str, Dict]:
        """Fetch metadata (float, avg volume, sector) for tickers."""
        from ..float_data import get_float_data_batch

        metadata = {}

        try:
            float_data = await get_float_data_batch(tickers)
            for ticker, data in float_data.items():
                metadata[ticker] = {
                    "float_shares": data.get("float_shares"),
                    "shares_outstanding": data.get("shares_outstanding"),
                    "avg_volume": data.get("avg_volume"),
                    "sector": data.get("sector"),
                    "industry": data.get("industry"),
                }
        except Exception as e:
            log.warning(f"Failed to fetch ticker metadata: {e}")

        return metadata

    def _extract_tickers_from_news(self, news_items: List[Dict]) -> List[str]:
        """Extract unique tickers mentioned in news."""
        tickers = set()

        for item in news_items:
            related = item.get("related_tickers", [])
            if isinstance(related, str):
                related = [t.strip() for t in related.split(",") if t.strip()]
            tickers.update(related)

        return list(tickers)[:100]  # Limit to 100 tickers

    def _cache_key(self, date_str: str, tickers: Optional[List[str]]) -> str:
        """Generate cache key for a data fetch."""
        key_parts = [date_str, self.price_source, self.news_source]

        if tickers:
            ticker_hash = hashlib.md5(",".join(sorted(tickers)).encode()).hexdigest()[:8]
            key_parts.append(ticker_hash)

        return "_".join(key_parts)
```

---

## Phase 3: Event Replay Engine

### 3.1 EventQueue and Replayer

**File:** `src/catalyst_bot/simulation/event_queue.py`

```python
"""
EventQueue - Priority queue for simulation events.

Maintains chronological ordering of all events (price updates, news, SEC filings)
and delivers them at the appropriate virtual time.
"""

import heapq
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import logging

log = logging.getLogger(__name__)


class EventType(Enum):
    """Types of simulation events."""
    PRICE_UPDATE = "price_update"
    NEWS_ITEM = "news_item"
    SEC_FILING = "sec_filing"
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"
    CUSTOM = "custom"


@dataclass(order=True)
class SimulationEvent:
    """
    A single event in the simulation timeline.

    Events are ordered by timestamp for priority queue.
    """
    timestamp: datetime
    priority: int = field(compare=True, default=0)  # Lower = higher priority
    event_type: EventType = field(compare=False, default=EventType.CUSTOM)
    data: Dict[str, Any] = field(compare=False, default_factory=dict)

    @classmethod
    def price_update(cls, timestamp: datetime, ticker: str, price: float,
                     volume: int = 0, **kwargs) -> "SimulationEvent":
        """Create a price update event."""
        return cls(
            timestamp=timestamp,
            priority=1,  # Price updates are high priority
            event_type=EventType.PRICE_UPDATE,
            data={
                "ticker": ticker,
                "price": price,
                "volume": volume,
                **kwargs
            }
        )

    @classmethod
    def news_item(cls, timestamp: datetime, title: str, ticker: str = None,
                  **kwargs) -> "SimulationEvent":
        """Create a news item event."""
        return cls(
            timestamp=timestamp,
            priority=0,  # News is highest priority (triggers alerts)
            event_type=EventType.NEWS_ITEM,
            data={
                "title": title,
                "ticker": ticker,
                **kwargs
            }
        )

    @classmethod
    def sec_filing(cls, timestamp: datetime, ticker: str, form_type: str,
                   **kwargs) -> "SimulationEvent":
        """Create an SEC filing event."""
        return cls(
            timestamp=timestamp,
            priority=0,
            event_type=EventType.SEC_FILING,
            data={
                "ticker": ticker,
                "form_type": form_type,
                **kwargs
            }
        )


class EventQueue:
    """
    Priority queue for simulation events.

    Usage:
        queue = EventQueue()

        # Add events
        queue.push(SimulationEvent.news_item(...))
        queue.push(SimulationEvent.price_update(...))

        # Get next event
        event = queue.pop()

        # Peek without removing
        next_event = queue.peek()

        # Get all events up to a time
        events = queue.pop_until(some_datetime)
    """

    def __init__(self):
        self._heap: List[SimulationEvent] = []
        self._event_count = 0

    def push(self, event: SimulationEvent) -> None:
        """Add an event to the queue."""
        heapq.heappush(self._heap, event)
        self._event_count += 1

    def pop(self) -> Optional[SimulationEvent]:
        """Remove and return the next event."""
        if self._heap:
            return heapq.heappop(self._heap)
        return None

    def peek(self) -> Optional[SimulationEvent]:
        """Return the next event without removing it."""
        if self._heap:
            return self._heap[0]
        return None

    def pop_until(self, until_time: datetime) -> List[SimulationEvent]:
        """Pop all events up to and including the specified time."""
        events = []
        while self._heap and self._heap[0].timestamp <= until_time:
            events.append(heapq.heappop(self._heap))
        return events

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._heap) == 0

    def __len__(self) -> int:
        return len(self._heap)

    @property
    def total_events_processed(self) -> int:
        """Total events that have been added."""
        return self._event_count


class EventReplayer:
    """
    Replay historical events through the simulation.

    Converts raw historical data into simulation events and feeds them
    to the bot at the appropriate virtual times.
    """

    def __init__(self, clock: "SimulationClock"):
        self.clock = clock
        self.queue = EventQueue()
        self._handlers: Dict[EventType, List[Callable]] = {et: [] for et in EventType}

    def load_historical_data(self, data: Dict[str, Any]) -> None:
        """
        Load historical data package and queue all events.

        Args:
            data: Output from HistoricalDataFetcher.fetch_day()
        """
        # Queue news items
        for item in data.get("news_items", []):
            timestamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            self.queue.push(SimulationEvent.news_item(
                timestamp=timestamp,
                title=item.get("title", ""),
                ticker=item.get("related_tickers", [""])[0] if item.get("related_tickers") else None,
                summary=item.get("summary", ""),
                source=item.get("source", ""),
                url=item.get("url", ""),
                raw=item
            ))

        # Queue SEC filings
        for filing in data.get("sec_filings", []):
            timestamp = datetime.fromisoformat(filing["timestamp"].replace("Z", "+00:00"))
            self.queue.push(SimulationEvent.sec_filing(
                timestamp=timestamp,
                ticker=filing.get("ticker", ""),
                form_type=filing.get("form_type", ""),
                raw=filing
            ))

        # Queue price updates (sample to reduce volume - every 5 minutes)
        for ticker, bars in data.get("price_bars", {}).items():
            for i, bar in enumerate(bars):
                if i % 5 == 0:  # Every 5th bar (5-minute intervals)
                    timestamp = datetime.fromisoformat(bar["timestamp"].replace("Z", "+00:00"))
                    self.queue.push(SimulationEvent.price_update(
                        timestamp=timestamp,
                        ticker=ticker,
                        price=bar["close"],
                        volume=bar["volume"],
                        open=bar["open"],
                        high=bar["high"],
                        low=bar["low"]
                    ))

        log.info(f"Loaded {len(self.queue)} events into replay queue")

    def register_handler(self, event_type: EventType, handler: Callable) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    async def process_next_event(self) -> Optional[SimulationEvent]:
        """
        Process the next event in the queue.

        Waits until the event's timestamp (in virtual time) then dispatches it.
        """
        event = self.queue.peek()
        if not event:
            return None

        # Wait until event time (in virtual time)
        current = self.clock.now()
        if event.timestamp > current:
            wait_seconds = (event.timestamp - current).total_seconds()
            self.clock.sleep(wait_seconds)

        # Pop and dispatch
        event = self.queue.pop()
        await self._dispatch_event(event)

        return event

    async def process_events_until(self, until_time: datetime) -> int:
        """
        Process all events up to specified time.

        Returns number of events processed.
        """
        count = 0
        events = self.queue.pop_until(until_time)

        for event in events:
            await self._dispatch_event(event)
            count += 1

        return count

    async def _dispatch_event(self, event: SimulationEvent) -> None:
        """Dispatch event to registered handlers."""
        handlers = self._handlers.get(event.event_type, [])

        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                log.error(f"Handler error for {event.event_type}: {e}")
```

---

## Phase 4: Mock Components

### 4.1 Mock Broker

**File:** `src/catalyst_bot/simulation/mock_broker.py`

```python
"""
MockBroker - Simulated broker for paper trading without API calls.

Simulates:
- Order placement and fills
- Position tracking
- Portfolio value
- Slippage and volume constraints
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum
import logging
import uuid

log = logging.getLogger(__name__)


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class SimulatedOrder:
    """A simulated order."""
    order_id: str
    ticker: str
    side: OrderSide
    quantity: int
    limit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


@dataclass
class SimulatedPosition:
    """A simulated position."""
    ticker: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_cost) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return ((self.current_price - self.avg_cost) / self.avg_cost) * 100


class MockBroker:
    """
    Simulated broker that processes orders without API calls.

    Features:
    - Market and limit orders
    - Slippage simulation (adaptive based on price/volume)
    - Volume constraints (max % of daily volume)
    - Position tracking
    - Portfolio P&L calculation

    Usage:
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="adaptive",
            max_volume_pct=5.0
        )

        # Place an order
        order = broker.submit_order("AAPL", OrderSide.BUY, 100)

        # Update prices (call periodically with market data)
        broker.update_price("AAPL", 150.50)

        # Get portfolio value
        value = broker.get_portfolio_value()
    """

    def __init__(
        self,
        starting_cash: float = 10000.0,
        slippage_model: str = "adaptive",
        slippage_pct: float = 0.5,
        max_volume_pct: float = 5.0,
        clock: Optional["SimulationClock"] = None
    ):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.slippage_model = slippage_model
        self.slippage_pct = slippage_pct
        self.max_volume_pct = max_volume_pct
        self.clock = clock

        # State
        self.positions: Dict[str, SimulatedPosition] = {}
        self.orders: Dict[str, SimulatedOrder] = {}
        self.order_history: List[SimulatedOrder] = []
        self.prices: Dict[str, float] = {}
        self.daily_volumes: Dict[str, int] = {}

        # Tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

    def _now(self) -> datetime:
        """Get current time (virtual or real)."""
        if self.clock:
            return self.clock.now()
        return datetime.now(timezone.utc)

    def update_price(self, ticker: str, price: float, volume: int = 0) -> None:
        """Update current price for a ticker."""
        self.prices[ticker] = price

        if volume:
            self.daily_volumes[ticker] = volume

        # Update position current price
        if ticker in self.positions:
            self.positions[ticker].current_price = price

        # Check for limit order fills
        self._check_limit_orders(ticker, price)

    def submit_order(
        self,
        ticker: str,
        side: OrderSide,
        quantity: int,
        limit_price: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> SimulatedOrder:
        """
        Submit an order for execution.

        Market orders fill immediately at current price + slippage.
        Limit orders queue until price is reached.
        """
        order_id = f"sim_{uuid.uuid4().hex[:8]}"

        order = SimulatedOrder(
            order_id=order_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            created_at=self._now()
        )

        self.orders[order_id] = order

        # Validate order
        rejection = self._validate_order(order)
        if rejection:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = rejection
            log.warning(f"Order rejected: {rejection}")
            return order

        # Market orders fill immediately
        if limit_price is None:
            current_price = self.prices.get(ticker)
            if current_price:
                self._fill_order(order, current_price)

        return order

    def _validate_order(self, order: SimulatedOrder) -> Optional[str]:
        """Validate order and return rejection reason if invalid."""
        ticker = order.ticker

        # Check if we have price data
        if ticker not in self.prices:
            return f"No price data for {ticker}"

        price = self.prices[ticker]

        # Check buying power for buys
        if order.side == OrderSide.BUY:
            cost = order.quantity * price
            if cost > self.cash:
                return f"Insufficient funds: need ${cost:.2f}, have ${self.cash:.2f}"

        # Check position for sells
        if order.side == OrderSide.SELL:
            position = self.positions.get(ticker)
            if not position or position.quantity < order.quantity:
                available = position.quantity if position else 0
                return f"Insufficient shares: need {order.quantity}, have {available}"

        # Check volume constraint
        daily_vol = self.daily_volumes.get(ticker, 0)
        if daily_vol > 0:
            max_shares = int(daily_vol * (self.max_volume_pct / 100))
            if order.quantity > max_shares:
                return f"Volume constraint: max {max_shares} shares ({self.max_volume_pct}% of volume)"

        return None

    def _fill_order(self, order: SimulatedOrder, market_price: float) -> None:
        """Fill an order at the given price with slippage."""
        # Calculate fill price with slippage
        slippage = self._calculate_slippage(order, market_price)

        if order.side == OrderSide.BUY:
            fill_price = market_price * (1 + slippage)
        else:
            fill_price = market_price * (1 - slippage)

        order.filled_price = fill_price
        order.filled_quantity = order.quantity
        order.filled_at = self._now()
        order.status = OrderStatus.FILLED

        # Update cash and positions
        if order.side == OrderSide.BUY:
            cost = order.quantity * fill_price
            self.cash -= cost

            # Update or create position
            if order.ticker in self.positions:
                pos = self.positions[order.ticker]
                total_cost = (pos.avg_cost * pos.quantity) + cost
                pos.quantity += order.quantity
                pos.avg_cost = total_cost / pos.quantity
            else:
                self.positions[order.ticker] = SimulatedPosition(
                    ticker=order.ticker,
                    quantity=order.quantity,
                    avg_cost=fill_price,
                    current_price=market_price
                )

        else:  # SELL
            proceeds = order.quantity * fill_price
            self.cash += proceeds

            pos = self.positions[order.ticker]
            pnl = (fill_price - pos.avg_cost) * order.quantity
            self.total_pnl += pnl
            self.total_trades += 1

            if pnl > 0:
                self.winning_trades += 1

            pos.quantity -= order.quantity
            if pos.quantity <= 0:
                del self.positions[order.ticker]

        self.order_history.append(order)
        log.info(f"Order filled: {order.side.value} {order.quantity} {order.ticker} @ ${fill_price:.2f}")

    def _calculate_slippage(self, order: SimulatedOrder, price: float) -> float:
        """Calculate slippage based on model."""
        if self.slippage_model == "none":
            return 0.0

        elif self.slippage_model == "fixed":
            return self.slippage_pct / 100

        elif self.slippage_model == "adaptive":
            # Higher slippage for:
            # - Lower priced stocks
            # - Larger orders relative to volume
            # - Less liquid names

            base_slippage = self.slippage_pct / 100

            # Price factor: penny stocks get more slippage
            if price < 1.0:
                base_slippage *= 3.0
            elif price < 5.0:
                base_slippage *= 2.0
            elif price < 10.0:
                base_slippage *= 1.5

            # Volume factor
            daily_vol = self.daily_volumes.get(order.ticker, 0)
            if daily_vol > 0:
                order_pct = order.quantity / daily_vol
                if order_pct > 0.01:  # >1% of volume
                    base_slippage *= (1 + order_pct * 10)

            return min(base_slippage, 0.15)  # Cap at 15%

        return 0.0

    def _check_limit_orders(self, ticker: str, price: float) -> None:
        """Check if any limit orders should fill."""
        for order in self.orders.values():
            if order.ticker != ticker or order.status != OrderStatus.PENDING:
                continue

            if order.limit_price is None:
                continue

            # Buy limit fills when price <= limit
            if order.side == OrderSide.BUY and price <= order.limit_price:
                self._fill_order(order, price)

            # Sell limit fills when price >= limit
            elif order.side == OrderSide.SELL and price >= order.limit_price:
                self._fill_order(order, price)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        order = self.orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def get_position(self, ticker: str) -> Optional[SimulatedPosition]:
        """Get position for a ticker."""
        return self.positions.get(ticker)

    def get_all_positions(self) -> Dict[str, SimulatedPosition]:
        """Get all positions."""
        return self.positions.copy()

    def get_portfolio_value(self) -> float:
        """Get total portfolio value (cash + positions)."""
        positions_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash + positions_value

    def get_portfolio_stats(self) -> Dict[str, Any]:
        """Get portfolio statistics."""
        total_value = self.get_portfolio_value()

        return {
            "starting_cash": self.starting_cash,
            "current_cash": self.cash,
            "positions_value": total_value - self.cash,
            "total_value": total_value,
            "total_return": total_value - self.starting_cash,
            "total_return_pct": ((total_value / self.starting_cash) - 1) * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0,
            "realized_pnl": self.total_pnl,
            "num_positions": len(self.positions),
        }

    def reset(self) -> None:
        """Reset broker to initial state."""
        self.cash = self.starting_cash
        self.positions.clear()
        self.orders.clear()
        self.order_history.clear()
        self.prices.clear()
        self.daily_volumes.clear()
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
```

### 4.2 Mock Market Data Feed

**File:** `src/catalyst_bot/simulation/mock_market_data.py`

```python
"""
MockMarketDataFeed - Provides historical prices during simulation.

Replaces live market data API calls with historical data lookup.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import logging

log = logging.getLogger(__name__)


class MockMarketDataFeed:
    """
    Simulated market data feed using historical data.

    Provides the same interface as the real market data providers,
    but returns historical prices based on the simulation clock.
    """

    def __init__(
        self,
        price_bars: Dict[str, List[Dict]],
        clock: "SimulationClock"
    ):
        """
        Initialize with historical price data.

        Args:
            price_bars: Dict mapping ticker -> list of OHLCV bars
            clock: SimulationClock for time-aware lookups
        """
        self.clock = clock

        # Index price data by timestamp for fast lookup
        self._price_index: Dict[str, Dict[datetime, Dict]] = {}
        self._load_price_data(price_bars)

        # Cache latest prices
        self._latest_prices: Dict[str, float] = {}

    def _load_price_data(self, price_bars: Dict[str, List[Dict]]) -> None:
        """Index price data by timestamp."""
        for ticker, bars in price_bars.items():
            self._price_index[ticker] = {}

            for bar in bars:
                timestamp = datetime.fromisoformat(
                    bar["timestamp"].replace("Z", "+00:00")
                )
                self._price_index[ticker][timestamp] = bar

    def get_last_price(self, ticker: str) -> Optional[float]:
        """
        Get the most recent price as of current simulation time.

        Returns:
            Last traded price, or None if no data available
        """
        current_time = self.clock.now()

        if ticker not in self._price_index:
            return None

        # Find most recent bar before current time
        bars = self._price_index[ticker]
        best_time = None
        best_bar = None

        for bar_time, bar in bars.items():
            if bar_time <= current_time:
                if best_time is None or bar_time > best_time:
                    best_time = bar_time
                    best_bar = bar

        if best_bar:
            price = best_bar["close"]
            self._latest_prices[ticker] = price
            return price

        return None

    def get_last_price_snapshot(self, ticker: str) -> Optional[Tuple[float, float]]:
        """
        Get price snapshot (last, previous close).

        Returns:
            Tuple of (last_price, previous_close) or None
        """
        price = self.get_last_price(ticker)
        if price is None:
            return None

        # Get previous bar for prev_close
        current_time = self.clock.now()
        bars = sorted(self._price_index.get(ticker, {}).items(), key=lambda x: x[0])

        prev_close = price  # Default to same
        for i, (bar_time, bar) in enumerate(bars):
            if bar_time > current_time and i > 0:
                prev_close = bars[i-1][1]["close"]
                break

        return (price, prev_close)

    def get_ohlcv(self, ticker: str) -> Optional[Dict]:
        """Get current OHLCV bar."""
        current_time = self.clock.now()

        if ticker not in self._price_index:
            return None

        bars = self._price_index[ticker]
        best_time = None
        best_bar = None

        for bar_time, bar in bars.items():
            if bar_time <= current_time:
                if best_time is None or bar_time > best_time:
                    best_time = bar_time
                    best_bar = bar

        return best_bar

    def batch_get_prices(self, tickers: List[str]) -> Dict[str, Tuple[float, float]]:
        """
        Get prices for multiple tickers.

        Returns:
            Dict mapping ticker -> (last_price, change_pct)
        """
        results = {}

        for ticker in tickers:
            snapshot = self.get_last_price_snapshot(ticker)
            if snapshot:
                last, prev = snapshot
                change_pct = ((last / prev) - 1) * 100 if prev else 0.0
                results[ticker] = (last, change_pct)

        return results

    def get_available_tickers(self) -> List[str]:
        """Get list of tickers with price data."""
        return list(self._price_index.keys())
```

### 4.3 Mock News Feed

**File:** `src/catalyst_bot/simulation/mock_feeds.py`

```python
"""
MockFeedProvider - Provides historical news/SEC data during simulation.

Replaces live RSS/API feeds with historical data replay.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging

log = logging.getLogger(__name__)


class MockFeedProvider:
    """
    Simulated feed provider using historical data.

    Returns news items and SEC filings that would have been
    available at the current simulation time.
    """

    def __init__(
        self,
        news_items: List[Dict],
        sec_filings: List[Dict],
        clock: "SimulationClock"
    ):
        self.clock = clock

        # Index items by timestamp
        self._news_items = sorted(
            news_items,
            key=lambda x: x.get("timestamp", "")
        )
        self._sec_filings = sorted(
            sec_filings,
            key=lambda x: x.get("timestamp", "")
        )

        # Track what's been "seen" this simulation
        self._seen_news_ids = set()
        self._seen_sec_ids = set()

        # Pointer to current position in timeline
        self._news_pointer = 0
        self._sec_pointer = 0

    def get_new_items(self) -> List[Dict]:
        """
        Get news items that have "arrived" since last check.

        Returns items with timestamps <= current simulation time
        that haven't been returned before.
        """
        current_time = self.clock.now()
        new_items = []

        # Find news items up to current time
        while self._news_pointer < len(self._news_items):
            item = self._news_items[self._news_pointer]
            item_time = datetime.fromisoformat(
                item["timestamp"].replace("Z", "+00:00")
            )

            if item_time <= current_time:
                item_id = item.get("id") or item.get("url") or item.get("title")

                if item_id not in self._seen_news_ids:
                    self._seen_news_ids.add(item_id)
                    new_items.append(item)

                self._news_pointer += 1
            else:
                break

        return new_items

    def get_new_sec_filings(self) -> List[Dict]:
        """
        Get SEC filings that have "arrived" since last check.
        """
        current_time = self.clock.now()
        new_filings = []

        while self._sec_pointer < len(self._sec_filings):
            filing = self._sec_filings[self._sec_pointer]
            filing_time = datetime.fromisoformat(
                filing["timestamp"].replace("Z", "+00:00")
            )

            if filing_time <= current_time:
                filing_id = filing.get("accession_number") or filing.get("url")

                if filing_id not in self._seen_sec_ids:
                    self._seen_sec_ids.add(filing_id)
                    new_filings.append(filing)

                self._sec_pointer += 1
            else:
                break

        return new_filings

    def peek_next_item_time(self) -> Optional[datetime]:
        """Get timestamp of next upcoming item (for scheduling)."""
        times = []

        if self._news_pointer < len(self._news_items):
            times.append(datetime.fromisoformat(
                self._news_items[self._news_pointer]["timestamp"].replace("Z", "+00:00")
            ))

        if self._sec_pointer < len(self._sec_filings):
            times.append(datetime.fromisoformat(
                self._sec_filings[self._sec_pointer]["timestamp"].replace("Z", "+00:00")
            ))

        return min(times) if times else None

    def reset(self) -> None:
        """Reset to beginning of timeline."""
        self._seen_news_ids.clear()
        self._seen_sec_ids.clear()
        self._news_pointer = 0
        self._sec_pointer = 0
```

---

## Phase 5: Simulation Controller & CLI

### 5.1 Main Simulation Controller

**File:** `src/catalyst_bot/simulation/controller.py`

```python
"""
SimulationController - Orchestrates the entire simulation.

Coordinates:
- Clock management
- Data loading
- Event replay
- Mock components
- Output handling
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any
import logging
import asyncio

from .config import SimulationConfig
from .clock import SimulationClock
from .clock_provider import init_clock, now, get_clock
from .data_fetcher import HistoricalDataFetcher
from .event_queue import EventReplayer, EventType
from .mock_broker import MockBroker
from .mock_market_data import MockMarketDataFeed
from .mock_feeds import MockFeedProvider

log = logging.getLogger(__name__)


class SimulationController:
    """
    Main controller for running trading simulations.

    Usage:
        # From CLI
        controller = SimulationController.from_config()
        await controller.run()

        # Programmatic
        controller = SimulationController(
            simulation_date="2025-01-15",
            speed_multiplier=10.0
        )
        await controller.run()
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        simulation_date: Optional[str] = None,
        speed_multiplier: float = 10.0,
        start_time_cst: Optional[str] = None,
        end_time_cst: Optional[str] = None
    ):
        self.config = config or SimulationConfig.from_env()

        # Override config with explicit parameters
        if simulation_date:
            self.config.simulation_date = simulation_date
        if speed_multiplier:
            self.config.speed_multiplier = speed_multiplier
        if start_time_cst:
            self.config.start_time_cst = start_time_cst
        if end_time_cst:
            self.config.end_time_cst = end_time_cst

        # Generate run ID
        self.run_id = self.config.generate_run_id()

        # Components (initialized in setup)
        self.clock: Optional[SimulationClock] = None
        self.broker: Optional[MockBroker] = None
        self.market_data: Optional[MockMarketDataFeed] = None
        self.feed_provider: Optional[MockFeedProvider] = None
        self.event_replayer: Optional[EventReplayer] = None

        # Data
        self.historical_data: Optional[Dict] = None

        # State
        self._running = False
        self._paused = False

    @classmethod
    def from_config(cls) -> "SimulationController":
        """Create controller from environment configuration."""
        config = SimulationConfig.from_env()
        return cls(config=config)

    async def setup(self) -> None:
        """Initialize all simulation components."""
        log.info(f"Setting up simulation: {self.run_id}")

        # Determine simulation date
        sim_date = self.config.get_simulation_date()
        start_time = self.config.get_start_time(sim_date)
        end_time = self.config.get_end_time(sim_date)

        log.info(f"Simulation date: {sim_date.strftime('%Y-%m-%d')}")
        log.info(f"Time range: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} UTC")
        log.info(f"Speed: {self.config.speed_multiplier}x")

        # Initialize clock
        self.clock = SimulationClock(
            start_time=start_time,
            speed_multiplier=self.config.speed_multiplier,
            end_time=end_time
        )

        # Initialize global clock provider
        init_clock(
            simulation_mode=True,
            start_time=start_time,
            speed_multiplier=self.config.speed_multiplier,
            end_time=end_time
        )

        # Fetch historical data
        fetcher = HistoricalDataFetcher(
            cache_dir=self.config.cache_dir,
            price_source=self.config.price_source,
            news_source=self.config.news_source
        )

        self.historical_data = await fetcher.fetch_day(sim_date)

        # Initialize mock components
        self.broker = MockBroker(
            starting_cash=self.config.starting_cash,
            slippage_model=self.config.slippage_model,
            slippage_pct=self.config.slippage_pct,
            max_volume_pct=self.config.max_volume_pct,
            clock=self.clock
        )

        self.market_data = MockMarketDataFeed(
            price_bars=self.historical_data.get("price_bars", {}),
            clock=self.clock
        )

        self.feed_provider = MockFeedProvider(
            news_items=self.historical_data.get("news_items", []),
            sec_filings=self.historical_data.get("sec_filings", []),
            clock=self.clock
        )

        # Initialize event replayer
        self.event_replayer = EventReplayer(self.clock)
        self.event_replayer.load_historical_data(self.historical_data)

        # Register event handlers
        self._register_event_handlers()

        log.info("Simulation setup complete")

    def _register_event_handlers(self) -> None:
        """Register handlers for different event types."""

        async def on_price_update(event):
            """Handle price update events."""
            ticker = event.data.get("ticker")
            price = event.data.get("price")
            volume = event.data.get("volume", 0)

            if ticker and price:
                self.broker.update_price(ticker, price, volume)

        async def on_news_item(event):
            """Handle news item events - this is where alerts would fire."""
            # This will integrate with the main bot's alert pipeline
            log.debug(f"News event: {event.data.get('title', '')[:50]}...")

        async def on_sec_filing(event):
            """Handle SEC filing events."""
            log.debug(f"SEC filing: {event.data.get('ticker')} - {event.data.get('form_type')}")

        self.event_replayer.register_handler(EventType.PRICE_UPDATE, on_price_update)
        self.event_replayer.register_handler(EventType.NEWS_ITEM, on_news_item)
        self.event_replayer.register_handler(EventType.SEC_FILING, on_sec_filing)

    async def run(self) -> Dict[str, Any]:
        """
        Run the simulation.

        Returns:
            Simulation results and statistics
        """
        await self.setup()

        log.info(f"Starting simulation: {self.run_id}")
        self._running = True

        events_processed = 0

        try:
            # Main simulation loop
            while self._running and not self.event_replayer.queue.is_empty():
                if self._paused:
                    await asyncio.sleep(0.1)
                    continue

                # Process next event
                event = await self.event_replayer.process_next_event()

                if event:
                    events_processed += 1

                    # Log progress periodically
                    if events_processed % 100 == 0:
                        current = self.clock.now()
                        log.info(f"Progress: {events_processed} events, "
                                f"time: {current.strftime('%H:%M:%S')}")

                # Check if we've reached end time
                if self.clock.now() >= self.config.get_end_time(
                    self.config.get_simulation_date()
                ):
                    break

            log.info(f"Simulation complete: {events_processed} events processed")

        except KeyboardInterrupt:
            log.info("Simulation interrupted by user")

        finally:
            self._running = False

        return self._generate_results(events_processed)

    def _generate_results(self, events_processed: int) -> Dict[str, Any]:
        """Generate simulation results summary."""
        portfolio_stats = self.broker.get_portfolio_stats()

        return {
            "run_id": self.run_id,
            "simulation_date": self.config.simulation_date,
            "speed_multiplier": self.config.speed_multiplier,
            "events_processed": events_processed,
            "portfolio": portfolio_stats,
            "positions": {
                ticker: {
                    "quantity": pos.quantity,
                    "avg_cost": pos.avg_cost,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                }
                for ticker, pos in self.broker.positions.items()
            },
            "orders": len(self.broker.order_history),
        }

    def pause(self) -> None:
        """Pause the simulation."""
        self._paused = True
        self.clock.pause()
        log.info("Simulation paused")

    def resume(self) -> None:
        """Resume the simulation."""
        self._paused = False
        self.clock.resume()
        log.info("Simulation resumed")

    def stop(self) -> None:
        """Stop the simulation."""
        self._running = False
        log.info("Simulation stopped")

    def jump_to_time(self, hour: int, minute: int = 0) -> None:
        """Jump to specific time (CST)."""
        self.clock.jump_to_time_cst(hour, minute)
        log.info(f"Jumped to {hour:02d}:{minute:02d} CST")

    def set_speed(self, multiplier: float) -> None:
        """Change simulation speed."""
        self.clock.set_speed(multiplier)
        log.info(f"Speed changed to {multiplier}x")
```

### 5.2 CLI Entry Point

**File:** `src/catalyst_bot/simulation/cli.py`

```python
"""
Simulation CLI - Command-line interface for running simulations.

Usage:
    # Run with defaults (Nov 12 2024, morning preset, 6x speed)
    python -m catalyst_bot.simulation.cli

    # Use preset for specific testing scenario
    python -m catalyst_bot.simulation.cli --preset morning  # 8:45-9:45 EST news rush
    python -m catalyst_bot.simulation.cli --preset sec      # 3:30-4:30 EST SEC filings

    # Custom time range
    python -m catalyst_bot.simulation.cli --start-time 08:00 --end-time 10:00

    # Maximum speed (instant)
    python -m catalyst_bot.simulation.cli --speed 0
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from .controller import SimulationController
from .config import SimulationConfig, TIME_PRESETS


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for simulation."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run trading day simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Presets:
    morning   8:45-9:45 EST  News rush, high activity
    sec       3:30-4:30 EST  SEC filing window
    open      9:30-10:30 EST Market open hour
    close     3:00-4:00 EST  Market close hour
    full      4:00am-5:00pm  Full trading day

Examples:
    # Quick morning test (default)
    python -m catalyst_bot.simulation.cli

    # Test SEC filing period
    python -m catalyst_bot.simulation.cli --preset sec

    # Custom date and time
    python -m catalyst_bot.simulation.cli --date 2024-11-12 --start-time 08:00

    # Maximum speed (instant)
    python -m catalyst_bot.simulation.cli --speed 0

    # Local-only alerts (no Discord)
    python -m catalyst_bot.simulation.cli --alerts local
        """
    )

    parser.add_argument(
        "--date",
        type=str,
        default="2024-11-12",
        help="Simulation date (YYYY-MM-DD). Default: 2024-11-12"
    )

    parser.add_argument(
        "--preset",
        choices=list(TIME_PRESETS.keys()),
        default="morning",
        help="Time preset (morning, sec, open, close, full). Default: morning"
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=6.0,
        help="Speed multiplier (1=realtime, 6=6x, 0=instant). Default: 6"
    )

    parser.add_argument(
        "--start-time",
        type=str,
        dest="start_time",
        help="Start time in CST (HH:MM). Overrides preset."
    )

    parser.add_argument(
        "--end-time",
        type=str,
        dest="end_time",
        help="End time in CST (HH:MM). Overrides preset."
    )

    parser.add_argument(
        "--cash",
        type=float,
        default=10000.0,
        help="Starting cash. Default: 10000"
    )

    parser.add_argument(
        "--alerts",
        choices=["discord", "local", "disabled"],
        default="discord",
        help="Alert output mode. Default: discord (test channels)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    return parser.parse_args()


async def run_simulation(args: argparse.Namespace) -> int:
    """Run the simulation with given arguments."""

    # Create controller with preset support
    controller = SimulationController(
        simulation_date=args.date,
        speed_multiplier=args.speed,
        time_preset=args.preset if not (args.start_time or args.end_time) else None,
        start_time_cst=args.start_time,
        end_time_cst=args.end_time
    )

    # Override config
    controller.config.starting_cash = args.cash
    controller.config.alert_output = {
        "discord": "discord_test",
        "local": "local_only",
        "disabled": "disabled"
    }.get(args.alerts, "discord_test")

    try:
        # Run simulation
        results = await controller.run()

        # Print results
        print("\n" + "=" * 60)
        print("SIMULATION RESULTS")
        print("=" * 60)
        print(f"Run ID: {results['run_id']}")
        print(f"Date: {results['simulation_date']}")
        print(f"Events Processed: {results['events_processed']}")
        print()
        print("Portfolio:")
        portfolio = results['portfolio']
        print(f"  Starting Cash: ${portfolio['starting_cash']:,.2f}")
        print(f"  Final Value:   ${portfolio['total_value']:,.2f}")
        print(f"  Return:        ${portfolio['total_return']:,.2f} ({portfolio['total_return_pct']:.2f}%)")
        print(f"  Total Trades:  {portfolio['total_trades']}")
        print(f"  Win Rate:      {portfolio['win_rate']:.1f}%")
        print()

        if results['positions']:
            print("Open Positions:")
            for ticker, pos in results['positions'].items():
                print(f"  {ticker}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f} "
                      f"(P&L: ${pos['unrealized_pnl']:.2f})")

        return 0

    except KeyboardInterrupt:
        print("\nSimulation cancelled")
        return 1
    except Exception as e:
        print(f"\nSimulation failed: {e}")
        logging.exception("Simulation error")
        return 1


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    return asyncio.run(run_simulation(args))


if __name__ == "__main__":
    sys.exit(main())
```

### 5.3 Simulation Logger

**File:** `src/catalyst_bot/simulation/logger.py`

```python
"""
SimulationLogger - Dual-format logging for simulation analysis.

Outputs:
- JSONL file: Machine-readable, structured events for LLM analysis
- Markdown file: Human-readable summary report
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum
import logging

log = logging.getLogger(__name__)


class Severity(Enum):
    """Severity levels for simulation events."""
    CRITICAL = "CRITICAL"  # Breaks simulation or requires immediate attention
    WARNING = "WARNING"    # Unexpected behavior but continues
    NOTICE = "NOTICE"      # Informational, worth noting


class SimulationLogger:
    """
    Dual-format logger for simulation runs.

    Creates:
    - {run_id}.jsonl: Line-by-line JSON events
    - {run_id}.md: Human-readable markdown summary
    """

    def __init__(
        self,
        run_id: str,
        log_dir: Path,
        simulation_date: str
    ):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.simulation_date = simulation_date

        # File paths
        self.jsonl_path = self.log_dir / f"{run_id}.jsonl"
        self.md_path = self.log_dir / f"{run_id}.md"

        # Tracking for summary
        self.events: List[Dict] = []
        self.alerts_fired: List[Dict] = []
        self.trades_executed: List[Dict] = []
        self.warnings: List[Dict] = []
        self.errors: List[Dict] = []
        self.skipped_tickers: List[Dict] = []

        # Initialize files
        self._init_files()

    def _init_files(self):
        """Initialize log files with headers."""
        # Write markdown header
        with open(self.md_path, "w") as f:
            f.write(f"# Simulation Report: {self.run_id}\n\n")
            f.write(f"**Date Simulated:** {self.simulation_date}\n")
            f.write(f"**Run Started:** {datetime.now(timezone.utc).isoformat()}\n\n")
            f.write("---\n\n")

    def log_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        severity: Optional[Severity] = None,
        sim_time: Optional[datetime] = None
    ):
        """
        Log a simulation event.

        Args:
            event_type: Type of event (alert, trade, skip, error, etc.)
            data: Event data
            severity: Optional severity level
            sim_time: Simulation time when event occurred
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sim_time": sim_time.isoformat() if sim_time else None,
            "run_id": self.run_id,
            "event_type": event_type,
            "severity": severity.value if severity else None,
            **data
        }

        # Write to JSONL
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(event) + "\n")

        # Track for summary
        self.events.append(event)

        if event_type == "alert":
            self.alerts_fired.append(event)
        elif event_type == "trade":
            self.trades_executed.append(event)
        elif event_type == "skip":
            self.skipped_tickers.append(event)
        elif severity == Severity.WARNING:
            self.warnings.append(event)
        elif severity == Severity.CRITICAL:
            self.errors.append(event)

    def log_alert(
        self,
        ticker: str,
        headline: str,
        classification: str,
        confidence: float,
        sim_time: datetime,
        **kwargs
    ):
        """Log an alert that was fired."""
        self.log_event("alert", {
            "ticker": ticker,
            "headline": headline,
            "classification": classification,
            "confidence": confidence,
            **kwargs
        }, sim_time=sim_time)

    def log_trade(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
        sim_time: datetime,
        **kwargs
    ):
        """Log a trade execution."""
        self.log_event("trade", {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            **kwargs
        }, sim_time=sim_time)

    def log_skip(
        self,
        ticker: str,
        reason: str,
        sim_time: Optional[datetime] = None
    ):
        """Log a skipped ticker with reason."""
        self.log_event("skip", {
            "ticker": ticker,
            "reason": reason
        }, severity=Severity.WARNING, sim_time=sim_time)

    def log_warning(self, message: str, context: Optional[Dict] = None):
        """Log a warning."""
        self.log_event("warning", {
            "message": message,
            **(context or {})
        }, severity=Severity.WARNING)

    def log_error(self, message: str, context: Optional[Dict] = None):
        """Log a critical error."""
        self.log_event("error", {
            "message": message,
            **(context or {})
        }, severity=Severity.CRITICAL)

    def finalize(self, portfolio_stats: Dict[str, Any]):
        """Write final summary to markdown file."""
        with open(self.md_path, "a") as f:
            # Quick Glance Section
            f.write("## Quick Glance\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Events Processed | {len(self.events)} |\n")
            f.write(f"| Alerts Fired | {len(self.alerts_fired)} |\n")
            f.write(f"| Trades Executed | {len(self.trades_executed)} |\n")
            f.write(f"| Tickers Skipped | {len(self.skipped_tickers)} |\n")
            f.write(f"| Warnings | {len(self.warnings)} |\n")
            f.write(f"| Errors | {len(self.errors)} |\n")
            f.write("\n")

            # Errors Section (if any)
            if self.errors:
                f.write("## ❌ Errors (CRITICAL)\n\n")
                for error in self.errors:
                    f.write(f"- **{error.get('message', 'Unknown error')}**\n")
                    if error.get('context'):
                        f.write(f"  - Context: {error.get('context')}\n")
                f.write("\n")

            # Warnings Section (if any)
            if self.warnings:
                f.write("## ⚠️ Warnings\n\n")
                for warning in self.warnings[:20]:  # Limit to 20
                    f.write(f"- {warning.get('message', 'Unknown warning')}\n")
                if len(self.warnings) > 20:
                    f.write(f"- ... and {len(self.warnings) - 20} more\n")
                f.write("\n")

            # Skipped Tickers
            if self.skipped_tickers:
                f.write("## Skipped Tickers\n\n")
                reasons = {}
                for skip in self.skipped_tickers:
                    reason = skip.get('reason', 'Unknown')
                    reasons[reason] = reasons.get(reason, 0) + 1

                f.write(f"| Reason | Count |\n")
                f.write(f"|--------|-------|\n")
                for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                    f.write(f"| {reason} | {count} |\n")
                f.write("\n")

            # Alerts Summary
            if self.alerts_fired:
                f.write("## Alerts Fired\n\n")
                f.write(f"| Time | Ticker | Classification | Headline |\n")
                f.write(f"|------|--------|----------------|----------|\n")
                for alert in self.alerts_fired[:50]:  # Limit to 50
                    sim_time = alert.get('sim_time', '')[:8] if alert.get('sim_time') else ''
                    f.write(f"| {sim_time} | {alert.get('ticker', '')} | "
                           f"{alert.get('classification', '')} | "
                           f"{alert.get('headline', '')[:50]}... |\n")
                f.write("\n")

            # Portfolio Summary
            f.write("## Portfolio Summary\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Starting Cash | ${portfolio_stats.get('starting_cash', 0):,.2f} |\n")
            f.write(f"| Final Value | ${portfolio_stats.get('total_value', 0):,.2f} |\n")
            f.write(f"| Return | ${portfolio_stats.get('total_return', 0):,.2f} "
                   f"({portfolio_stats.get('total_return_pct', 0):.2f}%) |\n")
            f.write(f"| Total Trades | {portfolio_stats.get('total_trades', 0)} |\n")
            f.write(f"| Win Rate | {portfolio_stats.get('win_rate', 0):.1f}% |\n")
            f.write("\n")

            f.write("---\n")
            f.write(f"*Report generated at {datetime.now(timezone.utc).isoformat()}*\n")

        log.info(f"Simulation report written to {self.md_path}")
```

---

## Phase 6: Integration with Existing Bot

### 6.1 Modifications to runner.py

The main integration point is modifying `runner.py` to use the clock provider and mock components when in simulation mode.

**Key Changes:**

1. **Import clock provider instead of datetime/time:**
```python
# At top of runner.py
from .simulation.clock_provider import now, sleep, is_simulation_mode, get_clock

# Replace datetime.now(timezone.utc) with now()
# Replace time.sleep(x) with sleep(x)
```

2. **Inject mock components:**
```python
# In _cycle() or main loop
if is_simulation_mode():
    # Use mock market data
    from .simulation.mock_market_data import MockMarketDataFeed
    market_data = get_simulation_market_data()

    # Use mock broker
    from .simulation.mock_broker import MockBroker
    broker = get_simulation_broker()
```

3. **Mark output as simulation:**
```python
# When logging events
if is_simulation_mode():
    event["simulation_run_id"] = get_simulation_run_id()
    event["is_simulation"] = True
```

### 6.2 Files to Modify

| File | Changes Required |
|------|-----------------|
| `runner.py` | Replace time functions with clock_provider |
| `market.py` | Add simulation mode check, use mock data |
| `feeds.py` | Add simulation mode check, use mock feeds |
| `trading_engine.py` | Use mock broker in simulation mode |
| `alerts.py` | Route to test channel or log in simulation |
| `accepted_items_logger.py` | Add simulation_run_id to records |
| `rejected_items_logger.py` | Add simulation_run_id to records |

---

## File Structure

```
src/catalyst_bot/simulation/
├── __init__.py
├── cli.py                 # Command-line interface
├── clock.py               # SimulationClock class
├── clock_provider.py      # Global clock management
├── config.py              # SimulationConfig + TIME_PRESETS
├── controller.py          # SimulationController orchestration
├── data_fetcher.py        # HistoricalDataFetcher
├── event_queue.py         # EventQueue and EventReplayer
├── health_check.py        # Pre-flight API health checks
├── logger.py              # SimulationLogger (JSONL + Markdown)
├── mock_broker.py         # MockBroker (simulated trading)
├── mock_market_data.py    # MockMarketDataFeed
├── mock_feeds.py          # MockFeedProvider
└── mock_sentiment.py      # Mocked external sentiment APIs
```

**Output Files Generated:**
```
data/simulation_logs/
├── sim_20241112_143000_abc123.jsonl   # Machine-readable event log
└── sim_20241112_143000_abc123.md      # Human-readable summary

data/simulation_cache/
└── 2024-11-12_tiingo_finnhub.json     # Cached historical data
```

---

## Usage Examples

### Basic Usage (Most Common)

```bash
# Quick morning test (default: Nov 12 2024, 8:45-9:45 EST, 6x speed)
# Takes ~10 minutes real time
python -m catalyst_bot.simulation.cli

# Test SEC filing period
python -m catalyst_bot.simulation.cli --preset sec

# Full day simulation at instant speed
python -m catalyst_bot.simulation.cli --preset full --speed 0

# Local-only alerts (no Discord)
python -m catalyst_bot.simulation.cli --alerts local
```

### Custom Time Windows

```bash
# Custom date and time range
python -m catalyst_bot.simulation.cli --date 2024-11-12 --start-time 08:00 --end-time 10:00

# Real-time speed (for debugging)
python -m catalyst_bot.simulation.cli --speed 1

# Maximum speed with verbose logging
python -m catalyst_bot.simulation.cli --speed 0 -v
```

### Environment Variables

```bash
# Enable simulation mode for regular bot run
export SIMULATION_MODE=1
export SIMULATION_DATE=2024-11-12
export SIMULATION_PRESET=morning
export SIMULATION_SPEED=6.0
python -m catalyst_bot.runner --loop
```

### Programmatic Usage

```python
from catalyst_bot.simulation import SimulationController

async def test_new_feature():
    # Quick sanity check after code changes
    controller = SimulationController(
        simulation_date="2024-11-12",
        time_preset="morning",
        speed_multiplier=6.0
    )

    results = await controller.run()

    # Check for errors
    if results.get("errors"):
        print(f"FAILED: {results['errors']}")
        return False

    print(f"Feature test passed: {results['events_processed']} events, "
          f"{results['alerts_fired']} alerts")
    return True
```

---

## Implementation Priority

### Phase 1: Core Infrastructure (MVP)
1. SimulationClock and clock_provider
2. SimulationConfig with .env flags + TIME_PRESETS
3. Pre-flight health check
4. CLI entry point with preset support

### Phase 2: Data Layer
1. HistoricalDataFetcher (Tiingo prices, Finnhub news)
2. MockMarketDataFeed
3. MockFeedProvider
4. Data caching system

### Phase 3: Execution Layer
1. MockBroker with adaptive slippage
2. EventQueue and EventReplayer
3. SimulationController
4. Position monitoring (matching production)

### Phase 4: Output & Integration
1. SimulationLogger (JSONL + Markdown)
2. Integration with runner.py
3. Alert routing (test channels)
4. Output marking (simulation_run_id)

### Phase 5: Polish
1. SEC filing replay
2. Mocked external sentiment APIs
3. Error recovery and graceful degradation
4. Additional test date scenarios

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Data Retention | Cache indefinitely, clear manually if needed |
| Parallel Runs | Single run at a time (simplicity) |
| CI Integration | Future consideration |
| Visualization | Markdown report + JSONL for LLM analysis |
