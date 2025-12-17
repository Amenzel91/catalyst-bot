"""
Simulation-specific configuration.

Provides SimulationConfig dataclass for managing all simulation settings,
including time presets, data sources, and component behavior.

Environment Variables:
    SIMULATION_MODE: Enable simulation mode (0/1)
    SIMULATION_DATE: Date to simulate (YYYY-MM-DD)
    SIMULATION_PRESET: Time preset (morning, sec, open, close, full)
    SIMULATION_SPEED: Speed multiplier (default 6.0)
    SIMULATION_START_TIME_CST: Custom start time (HH:MM)
    SIMULATION_END_TIME_CST: Custom end time (HH:MM)
    SIMULATION_LLM_ENABLED: Use live LLM (default 1)
    SIMULATION_LOCAL_SENTIMENT: Use local sentiment (default 1)
    SIMULATION_EXTERNAL_SENTIMENT: Use external APIs (default 0)
    SIMULATION_CHARTS_ENABLED: Generate charts (default 0)
    SIMULATION_PRICE_SOURCE: Price data source (tiingo/yfinance/cached)
    SIMULATION_NEWS_SOURCE: News source (finnhub/cached)
    SIMULATION_ALERT_OUTPUT: Alert destination (discord_test/local_only/disabled)
    SIMULATION_STARTING_CASH: Starting portfolio cash (default 10000)
    SIMULATION_SLIPPAGE_MODEL: Slippage model (adaptive/fixed/none)
    SIMULATION_SLIPPAGE_PCT: Slippage percentage (default 0.5)
    SIMULATION_MAX_VOLUME_PCT: Max order volume % (default 5.0)
"""

import os
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _b(key: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes", "y", "on")


# Time presets for common testing scenarios
# Times are in CST (Central Standard Time, UTC-6)
TIME_PRESETS = {
    "morning": {
        "start": "07:45",
        "end": "08:45",
        "description": "8:45-9:45 EST - News rush, high activity",
    },
    "sec": {
        "start": "14:30",
        "end": "15:30",
        "description": "3:30-4:30 EST - SEC filing window",
    },
    "open": {
        "start": "08:30",
        "end": "09:30",
        "description": "9:30-10:30 EST - Market open hour",
    },
    "close": {
        "start": "14:00",
        "end": "15:00",
        "description": "3:00-4:00 EST - Market close hour",
    },
    "full": {
        "start": "04:00",
        "end": "17:00",
        "description": "5:00am-6:00pm EST - Full trading day",
    },
}


@dataclass
class SimulationConfig:
    """Configuration for simulation mode."""

    # Core settings
    enabled: bool = False
    simulation_date: Optional[str] = (
        "2024-11-12"  # Default: Nov 12, 2024 (good test day)
    )
    speed_multiplier: float = 6.0  # Default: 6x (1hr sim = 10min real)
    start_time_cst: Optional[str] = None
    end_time_cst: Optional[str] = None
    time_preset: Optional[str] = None  # "morning", "sec", "open", "close", "full"
    run_id: Optional[str] = None

    # Data sources
    price_source: str = "tiingo"  # "tiingo", "yfinance", "cached"
    news_source: str = "finnhub"  # "finnhub", "cached"
    cache_dir: Path = field(default_factory=lambda: Path("data/simulation_cache"))

    # Output - Discord alerts fire to test channels by default
    alert_output: str = "discord_test"  # "discord_test", "local_only", "disabled"
    db_path: Path = field(default_factory=lambda: Path("data/simulation.db"))
    log_dir: Path = field(default_factory=lambda: Path("data/simulation_logs"))

    # Component behavior
    llm_enabled: bool = True  # LIVE - test actual classification
    local_sentiment: bool = True  # LIVE - VADER/FinBERT
    external_sentiment: bool = False  # MOCKED - use pre-fetched data
    charts_enabled: bool = False  # DISABLED - skip generation

    # Broker simulation
    starting_cash: float = 10000.0
    slippage_model: str = "adaptive"  # "adaptive", "fixed", "none"
    slippage_pct: float = 0.5
    max_volume_pct: float = 5.0

    # Data handling
    skip_incomplete_data: bool = True  # Skip tickers with missing data
    use_cache: bool = True  # Use cached data (--no-cache sets to False)

    # Error handling
    max_critical_errors: int = 10  # Abort after N critical errors (0 = unlimited)
    retry_attempts: int = 1  # Retry transient failures
    min_data_completeness: float = 0.5  # Minimum data ratio before abort

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
            max_critical_errors=int(os.getenv("SIMULATION_MAX_CRITICAL_ERRORS", "10")),
            retry_attempts=int(os.getenv("SIMULATION_RETRY_ATTEMPTS", "1")),
            min_data_completeness=float(
                os.getenv("SIMULATION_MIN_DATA_COMPLETENESS", "0.5")
            ),
        )

    def apply_preset(self) -> None:
        """Apply time preset if specified (sets start/end times)."""
        if self.time_preset and self.time_preset in TIME_PRESETS:
            preset = TIME_PRESETS[self.time_preset]
            self.start_time_cst = preset["start"]
            self.end_time_cst = preset["end"]

    def get_simulation_date(self) -> datetime:
        """
        Get simulation date as datetime.

        If simulation_date is not specified, picks a random recent trading day.

        Returns:
            Simulation date as UTC datetime
        """
        if self.simulation_date:
            return datetime.strptime(self.simulation_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

        # Pick random trading day from last 30 days
        today = datetime.now(timezone.utc).date()
        candidates = []

        for i in range(1, 31):
            day = today - timedelta(days=i)
            # Skip weekends (0=Monday, 5=Saturday, 6=Sunday)
            if day.weekday() < 5:
                candidates.append(day)

        selected = random.choice(candidates)
        return datetime.combine(selected, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

    def get_start_time(self, sim_date: datetime) -> datetime:
        """
        Get start time for simulation.

        Args:
            sim_date: The simulation date

        Returns:
            Start datetime in UTC
        """
        if self.start_time_cst:
            hour, minute = map(int, self.start_time_cst.split(":"))
            # CST = UTC-6, so add 6 hours to get UTC
            utc_hour = (hour + 6) % 24
            # Handle day rollover
            day_offset = (hour + 6) // 24
            result = sim_date.replace(
                hour=utc_hour, minute=minute, second=0, microsecond=0
            )
            if day_offset > 0:
                result += timedelta(days=day_offset)
            return result

        # Default: 4am ET (premarket start) = 9am UTC
        return sim_date.replace(hour=9, minute=0, second=0, microsecond=0)

    def get_end_time(self, sim_date: datetime) -> datetime:
        """
        Get end time for simulation.

        Args:
            sim_date: The simulation date

        Returns:
            End datetime in UTC
        """
        if self.end_time_cst:
            hour, minute = map(int, self.end_time_cst.split(":"))
            # CST = UTC-6, so add 6 hours to get UTC
            utc_hour = (hour + 6) % 24
            day_offset = (hour + 6) // 24
            result = sim_date.replace(
                hour=utc_hour, minute=minute, second=0, microsecond=0
            )
            if day_offset > 0:
                result += timedelta(days=day_offset)
            return result

        # Default: 5pm ET (after hours end) = 10pm UTC
        return sim_date.replace(hour=22, minute=0, second=0, microsecond=0)

    def generate_run_id(self) -> str:
        """
        Generate unique simulation run ID.

        Returns:
            Run ID in format: sim_YYYYMMDD_HHMMSS_xxxxxx
        """
        if self.run_id:
            return self.run_id

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"sim_{timestamp}_{short_uuid}"

    def get_preset_info(self) -> Optional[dict]:
        """
        Get information about the current time preset.

        Returns:
            Dict with preset details or None if no preset
        """
        if self.time_preset and self.time_preset in TIME_PRESETS:
            preset = TIME_PRESETS[self.time_preset]
            return {
                "name": self.time_preset,
                "start_cst": preset["start"],
                "end_cst": preset["end"],
                "description": preset["description"],
            }
        return None

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of errors.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Validate speed
        if self.speed_multiplier < 0:
            errors.append("speed_multiplier must be >= 0")

        # Validate date format
        if self.simulation_date:
            try:
                datetime.strptime(self.simulation_date, "%Y-%m-%d")
            except ValueError:
                errors.append(
                    f"Invalid simulation_date format: {self.simulation_date} "
                    "(expected YYYY-MM-DD)"
                )

        # Validate time format
        for name, value in [
            ("start_time_cst", self.start_time_cst),
            ("end_time_cst", self.end_time_cst),
        ]:
            if value:
                try:
                    hour, minute = map(int, value.split(":"))
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError()
                except ValueError:
                    errors.append(f"Invalid {name} format: {value} (expected HH:MM)")

        # Validate preset
        if self.time_preset and self.time_preset not in TIME_PRESETS:
            errors.append(
                f"Invalid time_preset: {self.time_preset} "
                f"(valid: {', '.join(TIME_PRESETS.keys())})"
            )

        # Validate slippage model
        valid_slippage = ["adaptive", "fixed", "none"]
        if self.slippage_model not in valid_slippage:
            errors.append(
                f"Invalid slippage_model: {self.slippage_model} "
                f"(valid: {', '.join(valid_slippage)})"
            )

        # Validate alert output
        valid_outputs = ["discord_test", "local_only", "disabled"]
        if self.alert_output not in valid_outputs:
            errors.append(
                f"Invalid alert_output: {self.alert_output} "
                f"(valid: {', '.join(valid_outputs)})"
            )

        # Validate percentages
        if not 0 <= self.slippage_pct <= 100:
            errors.append("slippage_pct must be between 0 and 100")
        if not 0 < self.max_volume_pct <= 100:
            errors.append("max_volume_pct must be between 0 and 100")
        if not 0 <= self.min_data_completeness <= 1:
            errors.append("min_data_completeness must be between 0 and 1")

        # Validate cash
        if self.starting_cash <= 0:
            errors.append("starting_cash must be positive")

        return errors

    def to_dict(self) -> dict:
        """
        Convert config to dictionary for serialization.

        Returns:
            Dict representation of config
        """
        return {
            "enabled": self.enabled,
            "simulation_date": self.simulation_date,
            "speed_multiplier": self.speed_multiplier,
            "start_time_cst": self.start_time_cst,
            "end_time_cst": self.end_time_cst,
            "time_preset": self.time_preset,
            "run_id": self.run_id,
            "price_source": self.price_source,
            "news_source": self.news_source,
            "cache_dir": str(self.cache_dir),
            "alert_output": self.alert_output,
            "db_path": str(self.db_path),
            "log_dir": str(self.log_dir),
            "llm_enabled": self.llm_enabled,
            "local_sentiment": self.local_sentiment,
            "external_sentiment": self.external_sentiment,
            "charts_enabled": self.charts_enabled,
            "starting_cash": self.starting_cash,
            "slippage_model": self.slippage_model,
            "slippage_pct": self.slippage_pct,
            "max_volume_pct": self.max_volume_pct,
            "skip_incomplete_data": self.skip_incomplete_data,
            "use_cache": self.use_cache,
            "max_critical_errors": self.max_critical_errors,
            "retry_attempts": self.retry_attempts,
            "min_data_completeness": self.min_data_completeness,
        }
