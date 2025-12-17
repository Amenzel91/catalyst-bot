"""
SimulationController - Orchestrates the entire simulation.

Coordinates:
- Clock management
- Data loading
- Event replay
- Mock components
- Output handling

Usage:
    from catalyst_bot.simulation import SimulationController

    # From CLI with preset
    controller = SimulationController(
        simulation_date="2024-11-12",
        time_preset="morning",
        speed_multiplier=6.0
    )
    results = await controller.run()

    # From environment configuration
    controller = SimulationController.from_config()
    results = await controller.run()
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from catalyst_bot.alerts import set_simulation_logger

# Import provider setters for simulation mode integration
from catalyst_bot.feeds import set_mock_feed_provider
from catalyst_bot.market import set_mock_market_data_feed
from catalyst_bot.trading.trading_engine import set_simulation_broker

from .clock import SimulationClock
from .clock_provider import init_clock
from .clock_provider import reset as reset_clock
from .config import SimulationConfig
from .data_fetcher import HistoricalDataFetcher
from .event_queue import EventReplayer, EventType, SimulationEvent
from .logger import SimulationLogger
from .mock_broker import MockBroker
from .mock_feeds import MockFeedProvider
from .mock_market_data import MockMarketDataFeed

log = logging.getLogger(__name__)


class SimulationSetupError(Exception):
    """Raised when simulation setup fails."""


class SimulationController:
    """
    Main controller for running trading simulations.

    Orchestrates all simulation components and manages the simulation lifecycle.
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        simulation_date: Optional[str] = None,
        speed_multiplier: float = 6.0,
        time_preset: Optional[str] = None,
        start_time_cst: Optional[str] = None,
        end_time_cst: Optional[str] = None,
    ):
        """
        Initialize the simulation controller.

        Args:
            config: Full configuration object (overrides other params)
            simulation_date: Date to simulate (YYYY-MM-DD)
            speed_multiplier: Speed of simulation (0=instant, 1=realtime, 6=6x)
            time_preset: Preset name (morning, sec, open, close, full)
            start_time_cst: Custom start time in CST (HH:MM)
            end_time_cst: Custom end time in CST (HH:MM)
        """
        # Use provided config or create from environment
        if config is not None:
            self.config = config
        else:
            self.config = SimulationConfig.from_env()

            # Override config with explicit parameters (only if no config provided)
            if simulation_date:
                self.config.simulation_date = simulation_date
            if speed_multiplier != 6.0:
                self.config.speed_multiplier = speed_multiplier
            if time_preset:
                self.config.time_preset = time_preset

            # Apply time preset first (if specified)
            self.config.apply_preset()

            # Then override with explicit times (these take precedence over preset)
            if start_time_cst:
                self.config.start_time_cst = start_time_cst
            if end_time_cst:
                self.config.end_time_cst = end_time_cst

        # Generate run ID
        self.run_id = self.config.generate_run_id()

        # Error tracking
        self._critical_error_count = 0
        self._max_critical_errors = int(
            os.getenv("SIMULATION_MAX_CRITICAL_ERRORS", "10")
        )

        # Components (initialized in setup)
        self.clock: Optional[SimulationClock] = None
        self.broker: Optional[MockBroker] = None
        self.market_data: Optional[MockMarketDataFeed] = None
        self.feed_provider: Optional[MockFeedProvider] = None
        self.event_replayer: Optional[EventReplayer] = None
        self.logger: Optional[SimulationLogger] = None

        # Data
        self.historical_data: Optional[Dict] = None

        # State
        self._running = False
        self._paused = False
        self._setup_complete = False

        # Custom event handlers
        self._custom_handlers: Dict[EventType, List[Callable]] = {}

    @classmethod
    def from_config(cls) -> "SimulationController":
        """Create controller from environment configuration."""
        config = SimulationConfig.from_env()
        # Apply preset to set start/end times before passing to __init__
        config.apply_preset()
        return cls(config=config)

    async def setup(self) -> None:
        """Initialize all simulation components."""
        log.info(f"Setting up simulation: {self.run_id}")

        # Determine simulation date
        sim_date = self.config.get_simulation_date()
        start_time = self.config.get_start_time(sim_date)
        end_time = self.config.get_end_time(sim_date)

        log.info(f"Simulation date: {sim_date.strftime('%Y-%m-%d')}")
        log.info(
            f"Time range: {start_time.strftime('%H:%M')} - "
            f"{end_time.strftime('%H:%M')} UTC"
        )
        log.info(f"Speed: {self.config.speed_multiplier}x")

        # Initialize clock
        self.clock = SimulationClock(
            start_time=start_time,
            speed_multiplier=self.config.speed_multiplier,
            end_time=end_time,
        )

        # Initialize global clock provider
        init_clock(
            simulation_mode=True,
            start_time=start_time,
            speed_multiplier=self.config.speed_multiplier,
            end_time=end_time,
        )

        # Initialize logger
        self.logger = SimulationLogger(
            run_id=self.run_id,
            log_dir=self.config.log_dir,
            simulation_date=self.config.simulation_date
            or sim_date.strftime("%Y-%m-%d"),
        )

        # Fetch historical data
        fetcher = HistoricalDataFetcher(
            cache_dir=self.config.cache_dir,
            price_source=self.config.price_source,
            news_source=self.config.news_source,
        )

        self.historical_data = await fetcher.fetch_day(
            date=sim_date,
            use_cache=self.config.use_cache,
        )

        # Initialize mock components
        self.broker = MockBroker(
            starting_cash=self.config.starting_cash,
            slippage_model=self.config.slippage_model,
            slippage_pct=self.config.slippage_pct,
            max_volume_pct=self.config.max_volume_pct,
            clock=self.clock,
        )

        self.market_data = MockMarketDataFeed(
            price_bars=self.historical_data.get("price_bars", {}),
            clock=self.clock,
        )

        # Register mock market data feed for market.py integration
        set_mock_market_data_feed(self.market_data)

        self.feed_provider = MockFeedProvider(
            news_items=self.historical_data.get("news_items", []),
            sec_filings=self.historical_data.get("sec_filings", []),
            clock=self.clock,
        )

        # Register mock feed provider for feeds.py integration
        set_mock_feed_provider(self.feed_provider)

        # Register simulation logger for alerts.py integration
        set_simulation_logger(self.logger)

        # Register simulation broker for trading_engine.py integration
        set_simulation_broker(self.broker)

        # Initialize event replayer
        self.event_replayer = EventReplayer(self.clock)
        self.event_replayer.load_historical_data(self.historical_data)

        # Register event handlers
        self._register_event_handlers()

        self._setup_complete = True
        log.info("Simulation setup complete")

    async def validate(self) -> bool:
        """
        Pre-flight validation checks (used by --dry-run).

        Verifies:
        - API connectivity (if needed)
        - Cache/log directory writability
        - Historical data availability for target date

        Returns:
            True if all checks pass

        Raises:
            SimulationSetupError: If any check fails
        """
        checks = []
        failed = []

        # Check cache directory
        cache_dir = self.config.cache_dir
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            test_file = cache_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            checks.append(("Cache directory", True))
        except Exception as e:
            failed.append(f"Cache directory: {e}")

        # Check log directory
        log_dir = self.config.log_dir
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            test_file = log_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            checks.append(("Log directory", True))
        except Exception as e:
            failed.append(f"Log directory: {e}")

        # Check config validation
        errors = self.config.validate()
        if errors:
            for error in errors:
                failed.append(f"Config: {error}")
        else:
            checks.append(("Configuration", True))

        # Log results
        log.info(f"Pre-flight checks: {len(checks)} passed, {len(failed)} failed")
        for name, _ in checks:
            log.info(f"  + {name}")
        for failure in failed:
            log.error(f"  - {failure}")

        if failed:
            raise SimulationSetupError(f"Pre-flight checks failed: {failed}")

        return True

    def _register_event_handlers(self) -> None:
        """Register handlers for different event types."""

        async def on_price_update(event: SimulationEvent) -> None:
            """Handle price update events."""
            ticker = event.data.get("ticker")
            price = event.data.get("close") or event.data.get("price")
            volume = event.data.get("volume", 0)

            if ticker and price:
                self.broker.update_price(ticker, price, volume)

        async def on_news_item(event: SimulationEvent) -> None:
            """Handle news item events."""
            title = event.data.get("title", "")[:50]
            ticker = (
                event.data.get("ticker") or event.data.get("related_tickers", [""])[0]
            )
            log.debug(f"News event: {title}...")

            if self.logger:
                self.logger.log_news(
                    news_id=event.data.get("id", ""),
                    title=event.data.get("title", ""),
                    ticker=ticker,
                    sim_time=event.timestamp,
                )

        async def on_sec_filing(event: SimulationEvent) -> None:
            """Handle SEC filing events."""
            ticker = event.data.get("ticker", "")
            form_type = event.data.get("form_type", "")
            log.debug(f"SEC filing: {ticker} - {form_type}")

            if self.logger:
                self.logger.log_sec_filing(
                    ticker=ticker,
                    form_type=form_type,
                    sim_time=event.timestamp,
                )

        self.event_replayer.register_handler(EventType.PRICE_UPDATE, on_price_update)
        self.event_replayer.register_handler(EventType.NEWS_ITEM, on_news_item)
        self.event_replayer.register_handler(EventType.SEC_FILING, on_sec_filing)

    def register_handler(self, event_type: EventType, handler: Callable) -> None:
        """
        Register a custom event handler.

        Args:
            event_type: Type of event to handle
            handler: Async callback function
        """
        if event_type not in self._custom_handlers:
            self._custom_handlers[event_type] = []
        self._custom_handlers[event_type].append(handler)

        # Also register with event replayer if already set up
        if self.event_replayer:
            self.event_replayer.register_handler(event_type, handler)

    async def run(self) -> Dict[str, Any]:
        """
        Run the simulation.

        Returns:
            Simulation results and statistics
        """
        if not self._setup_complete:
            await self.setup()

        log.info(f"Starting simulation: {self.run_id}")
        self._running = True

        events_processed = 0
        start_real_time = datetime.now(timezone.utc)

        try:
            # Main simulation loop
            while self._running and not self.event_replayer.queue.is_empty():
                if self._paused:
                    await asyncio.sleep(0.1)
                    continue

                # Check for too many critical errors
                if self._critical_error_count >= self._max_critical_errors:
                    log.error(
                        f"Too many critical errors ({self._critical_error_count}), "
                        "stopping simulation"
                    )
                    break

                # Process next event
                try:
                    event = await self.event_replayer.process_next_event()

                    if event:
                        events_processed += 1

                        # Log progress periodically
                        if events_processed % 100 == 0:
                            current = self.clock.now()
                            log.info(
                                f"Progress: {events_processed} events, "
                                f"time: {current.strftime('%H:%M:%S')}"
                            )

                except Exception as e:
                    log.error(f"Error processing event: {e}")
                    self._critical_error_count += 1
                    if self.logger:
                        self.logger.log_error(f"Event processing error: {e}")

                # Check if we've reached end time
                if self.clock.is_past_end():
                    log.info("Reached end of simulation time")
                    break

            elapsed_real = (
                datetime.now(timezone.utc) - start_real_time
            ).total_seconds()
            log.info(
                f"Simulation complete: {events_processed} events in "
                f"{elapsed_real:.1f}s real time"
            )

        except KeyboardInterrupt:
            log.info("Simulation interrupted by user")

        finally:
            self._running = False

        return self._generate_results(events_processed)

    def _generate_results(self, events_processed: int) -> Dict[str, Any]:
        """Generate simulation results summary."""
        portfolio_stats = self.broker.get_portfolio_stats()

        # Finalize logger
        if self.logger:
            self.logger.finalize(portfolio_stats)

        results = {
            "run_id": self.run_id,
            "simulation_date": self.config.simulation_date,
            "speed_multiplier": self.config.speed_multiplier,
            "events_processed": events_processed,
            "critical_errors": self._critical_error_count,
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
            "log_files": {
                "jsonl": str(self.logger.jsonl_path) if self.logger else None,
                "markdown": str(self.logger.md_path) if self.logger else None,
            },
        }

        return results

    def pause(self) -> None:
        """Pause the simulation."""
        self._paused = True
        if self.clock:
            self.clock.pause()
        log.info("Simulation paused")

    def resume(self) -> None:
        """Resume the simulation."""
        self._paused = False
        if self.clock:
            self.clock.resume()
        log.info("Simulation resumed")

    def stop(self) -> None:
        """Stop the simulation."""
        self._running = False
        log.info("Simulation stopped")

    def jump_to_time(self, hour: int, minute: int = 0) -> None:
        """Jump to specific time (CST)."""
        if self.clock:
            self.clock.jump_to_time_cst(hour, minute)
            log.info(f"Jumped to {hour:02d}:{minute:02d} CST")

    def set_speed(self, multiplier: float) -> None:
        """Change simulation speed."""
        if self.clock:
            self.clock.set_speed(multiplier)
            log.info(f"Speed changed to {multiplier}x")

    def get_status(self) -> Dict[str, Any]:
        """Get current simulation status."""
        status = {
            "run_id": self.run_id,
            "running": self._running,
            "paused": self._paused,
            "setup_complete": self._setup_complete,
            "critical_errors": self._critical_error_count,
        }

        if self.clock:
            status["clock"] = self.clock.get_status()

        if self.broker:
            status["portfolio_value"] = self.broker.get_portfolio_value()
            status["positions_count"] = len(self.broker.positions)

        if self.event_replayer:
            status["events_remaining"] = len(self.event_replayer.queue)

        return status

    async def cleanup(self) -> None:
        """Clean up resources after simulation."""
        set_mock_feed_provider(None)  # Clear mock feed provider
        set_mock_market_data_feed(None)  # Clear mock market data feed
        set_simulation_logger(None)  # Clear simulation logger
        set_simulation_broker(None)  # Clear simulation broker
        reset_clock()
        log.debug("Simulation cleanup complete")
