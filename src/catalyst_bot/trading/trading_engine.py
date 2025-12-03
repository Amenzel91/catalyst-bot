"""
Trading Engine Module

This module orchestrates the complete trading workflow for the Catalyst Bot.

Flow:
1. Receive scored item from runner.py
2. Generate trading signal (via SignalGenerator - Agent 1)
3. Execute order (via OrderExecutor)
4. Track position (via PositionManager)
5. Monitor and update positions periodically

The TradingEngine acts as the central coordinator between all trading components,
ensuring proper risk management, error handling, and Discord alerting.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Internal imports - Broker
from ..broker.broker_interface import (
    BrokerInterface,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    BrokerError,
    BrokerConnectionError,
    InsufficientFundsError,
)
from ..broker.alpaca_client import AlpacaBrokerClient

# Internal imports - Execution & Portfolio
from ..execution.order_executor import (
    OrderExecutor,
    TradingSignal,
    PositionSizingConfig,
    ExecutionResult,
)
from ..portfolio.position_manager import (
    PositionManager,
    ManagedPosition,
    ClosedPosition,
    PortfolioMetrics,
)

# Internal imports - Core
from ..config import get_settings
from ..logging_utils import get_logger
from ..classify import ScoredItem  # Keyword scoring output
from .market_data import MarketDataFeed  # Market data provider (Agent 3)

logger = get_logger(__name__)


# ============================================================================
# Type Definitions
# ============================================================================

@dataclass
class TradingEngineConfig:
    """Configuration for TradingEngine."""

    # Feature flags
    trading_enabled: bool = True
    paper_trading: bool = True
    send_discord_alerts: bool = True

    # Risk limits
    max_portfolio_exposure_pct: float = 50.0
    max_daily_loss_pct: float = 10.0
    min_account_balance: Decimal = Decimal("1000.00")

    # Position sizing
    position_size_base_pct: float = 2.0
    position_size_max_pct: float = 5.0

    # Execution
    order_timeout_seconds: float = 60.0
    max_retry_attempts: int = 3

    # Circuit breaker
    circuit_breaker_cooldown_minutes: int = 60

    # Database
    db_path: Optional[Path] = None


# ============================================================================
# Trading Engine
# ============================================================================

class TradingEngine:
    """
    Orchestrates the complete trading workflow.

    Flow:
    1. Receive scored item from runner.py
    2. Generate trading signal (via SignalGenerator)
    3. Execute order (via OrderExecutor)
    4. Track position (via PositionManager)
    5. Monitor and update positions periodically
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize trading engine with all sub-components.

        Creates:
        - AlpacaBrokerClient (paper trading mode)
        - OrderExecutor
        - PositionManager
        - SignalGenerator (will be implemented by Agent 1)
        - MarketDataFeed (will be implemented by Agent 3)

        Args:
            config: Optional configuration dictionary
        """
        self.logger = get_logger(__name__)
        settings = get_settings()

        # Parse configuration
        config = config or {}
        self.config = TradingEngineConfig(
            trading_enabled=config.get("trading_enabled",
                getattr(settings, "feature_paper_trading", False)),
            paper_trading=config.get("paper_trading",
                getattr(settings, "alpaca_paper_mode", True)),
            send_discord_alerts=config.get("send_discord_alerts",
                getattr(settings, "trading_discord_alerts", True)),
            max_portfolio_exposure_pct=config.get("max_portfolio_exposure_pct",
                getattr(settings, "max_portfolio_exposure_pct", 50.0)),
            max_daily_loss_pct=config.get("max_daily_loss_pct",
                getattr(settings, "max_daily_loss_pct", 10.0)),
            position_size_base_pct=config.get("position_size_base_pct",
                getattr(settings, "position_size_base_pct", 2.0)),
            position_size_max_pct=config.get("position_size_max_pct",
                getattr(settings, "position_size_max_pct", 5.0)),
            db_path=config.get("db_path"),
        )

        # Initialize broker client
        self.broker: Optional[AlpacaBrokerClient] = None
        self.order_executor: Optional[OrderExecutor] = None
        self.position_manager: Optional[PositionManager] = None
        self.signal_generator = None  # Will be set after SignalGenerator is implemented
        self.market_data_feed: Optional[MarketDataFeed] = None  # Market data provider (Agent 3)

        # Circuit breaker state
        self.circuit_breaker_active = False
        self.circuit_breaker_triggered_at: Optional[datetime] = None
        self.daily_start_balance: Optional[Decimal] = None

        # Trading state
        self._initialized = False
        self._last_position_update: Optional[datetime] = None

        self.logger.info(
            f"Initialized TradingEngine (paper_trading={self.config.paper_trading}, "
            f"trading_enabled={self.config.trading_enabled})"
        )

    # ========================================================================
    # Initialization & Shutdown
    # ========================================================================

    async def initialize(self) -> bool:
        """
        Connect to broker and initialize components.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Check if trading is enabled
            if not self.config.trading_enabled:
                self.logger.info("Trading engine disabled via configuration")
                return False

            # Verify paper trading mode
            if not self.config.paper_trading:
                self.logger.error("CRITICAL: Live trading not yet supported!")
                return False

            # Initialize broker client
            self.logger.info("Initializing Alpaca broker client...")
            self.broker = AlpacaBrokerClient(
                api_key=os.getenv("ALPACA_API_KEY"),
                api_secret=os.getenv("ALPACA_SECRET") or os.getenv("ALPACA_API_SECRET"),
                paper_trading=True,
            )

            # Connect to broker
            await self.broker.connect()

            # Verify account
            account = await self.broker.get_account()
            self.logger.info(
                f"Connected to Alpaca: equity=${account.equity}, "
                f"buying_power=${account.buying_power}"
            )

            # Store daily start balance for circuit breaker
            self.daily_start_balance = account.equity

            # Initialize order executor
            self.logger.info("Initializing OrderExecutor...")
            sizing_config = PositionSizingConfig(
                max_position_size_pct=self.config.position_size_max_pct / 100.0,
                risk_per_trade_pct=self.config.position_size_base_pct / 100.0,
            )
            self.order_executor = OrderExecutor(
                broker=self.broker,
                db_path=self.config.db_path,
                position_sizing_config=sizing_config,
            )

            # Initialize position manager
            self.logger.info("Initializing PositionManager...")
            self.position_manager = PositionManager(
                broker=self.broker,
                db_path=self.config.db_path,
            )

            # Initialize market data feed (Agent 3)
            self.logger.info("Initializing MarketDataFeed...")
            self.market_data_feed = MarketDataFeed()

            # TODO: Initialize SignalGenerator (Agent 1 will implement)
            # from .signal_generator import SignalGenerator
            # self.signal_generator = SignalGenerator()

            self._initialized = True
            self.logger.info("TradingEngine initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize TradingEngine: {e}", exc_info=True)
            return False

    async def shutdown(self) -> None:
        """Gracefully shutdown (close connections, save state)."""
        try:
            self.logger.info("Shutting down TradingEngine...")

            # Close any remaining positions if configured
            # (For now, we keep positions open)

            # Disconnect from broker
            if self.broker:
                await self.broker.disconnect()

            self._initialized = False
            self.logger.info("TradingEngine shutdown complete")

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)

    # ========================================================================
    # Main Trading Flow
    # ========================================================================

    async def process_scored_item(
        self,
        scored_item: ScoredItem,
        ticker: str,
        current_price: Decimal,
    ) -> Optional[str]:
        """
        Main entry point from runner.py.

        Called after Discord alert is sent successfully.

        Args:
            scored_item: Scored item from classification system
            ticker: Stock ticker symbol
            current_price: Current market price

        Returns:
            Position ID if trade executed, None otherwise
        """
        try:
            # 1. Check if trading enabled
            if not self._check_trading_enabled():
                return None

            # 2. Generate signal (stub for now - Agent 1 will implement)
            signal = self._generate_signal_stub(scored_item, ticker, current_price)
            if not signal:
                self.logger.debug(f"No actionable signal for {ticker}")
                return None

            self.logger.info(
                f"Generated signal: {ticker} {signal.action} "
                f"confidence={signal.confidence:.2f}"
            )

            # 3. Handle CLOSE signal specially
            if signal.action.upper() == "CLOSE":
                await self._handle_close_signal(ticker)
                return None

            # 4. Check risk limits
            account = await self.broker.get_account()
            if not self._check_risk_limits(signal, account.equity):
                self.logger.warning(f"Risk limits exceeded for {ticker}, rejecting trade")
                return None

            # 5. Execute signal
            position = await self._execute_signal(signal)
            if position:
                self.logger.info(
                    f"trade_executed ticker={ticker} position_id={position.position_id}"
                )
                await self._send_position_alert(position, "opened")
                return position.position_id

            return None

        except Exception as e:
            self.logger.error(
                f"execution_failed ticker={ticker} err={str(e)}",
                exc_info=True
            )
            return None

    async def update_positions(self) -> Dict:
        """
        Update all open positions with current prices.

        Called at end of each bot cycle.

        Returns:
            Portfolio metrics dictionary
        """
        try:
            if not self._initialized or not self.position_manager:
                return {"positions": 0, "pnl": 0.0}

            # 1. Fetch current prices for all open positions
            positions = self.position_manager.get_all_positions()
            if not positions:
                return {"positions": 0, "pnl": 0.0}

            # 2. Update prices (using broker API for now - Agent 3 will implement MarketDataFeed)
            price_updates = await self._fetch_current_prices(positions)
            await self.position_manager.update_position_prices(price_updates)

            # 3. Check stop-loss and take-profit triggers
            triggered_stops = await self.position_manager.check_stop_losses()
            triggered_profits = await self.position_manager.check_take_profits()

            # 4. Auto-close triggered positions
            closed = await self.position_manager.auto_close_triggered_positions()

            # 5. Send Discord alerts for closed positions
            for closed_position in closed:
                await self._send_position_alert(closed_position, "closed")

            # 6. Update circuit breaker
            await self._update_circuit_breaker()

            # 7. Return metrics
            account = await self.broker.get_account()
            metrics = self.position_manager.calculate_portfolio_metrics(account.equity)

            self._last_position_update = datetime.now()

            return {
                "positions": metrics.total_positions,
                "exposure": float(metrics.total_exposure),
                "pnl": float(metrics.total_unrealized_pnl),
                "triggered_stops": len(triggered_stops),
                "triggered_profits": len(triggered_profits),
                "closed_positions": len(closed),
            }

        except Exception as e:
            self.logger.error(f"Failed to update positions: {e}", exc_info=True)
            return {"positions": 0, "pnl": 0.0, "error": str(e)}

    # ========================================================================
    # Risk Management
    # ========================================================================

    def _check_trading_enabled(self) -> bool:
        """
        Verify trading is enabled and safe to execute.

        Returns:
            True if trading should proceed, False otherwise
        """
        # Check feature flag
        if not self.config.trading_enabled:
            self.logger.debug("Trading disabled via configuration")
            return False

        # Check initialization
        if not self._initialized:
            self.logger.warning("TradingEngine not initialized")
            return False

        # Check broker connection (simple check - don't await here)
        if not self.broker:
            self.logger.warning("Broker not initialized")
            return False

        # Check circuit breaker
        if self.circuit_breaker_active:
            # Check if cooldown period has expired
            if self.circuit_breaker_triggered_at:
                cooldown = timedelta(minutes=self.config.circuit_breaker_cooldown_minutes)
                if datetime.now() - self.circuit_breaker_triggered_at > cooldown:
                    self.logger.info("Circuit breaker cooldown expired, resetting")
                    self.circuit_breaker_active = False
                    self.circuit_breaker_triggered_at = None
                else:
                    self.logger.debug("Circuit breaker active, trading disabled")
                    return False
            else:
                self.logger.debug("Circuit breaker active, trading disabled")
                return False

        return True

    def _check_risk_limits(self, signal: TradingSignal, account_value: Decimal) -> bool:
        """
        Check if signal passes risk management checks.

        Args:
            signal: Trading signal to validate
            account_value: Current account value

        Returns:
            True if signal passes all checks, False otherwise
        """
        try:
            # Calculate position value
            position_value = (
                account_value * Decimal(str(signal.position_size_pct))
            )

            # Check minimum account balance
            if account_value < self.config.min_account_balance:
                self.logger.warning(
                    f"Account balance too low: ${account_value} < ${self.config.min_account_balance}"
                )
                return False

            # Check position size within limits
            max_position_value = account_value * Decimal(str(self.config.position_size_max_pct / 100.0))
            if position_value > max_position_value:
                self.logger.warning(
                    f"Position size too large: ${position_value} > ${max_position_value}"
                )
                return False

            # Check max portfolio exposure
            if self.position_manager:
                current_exposure = self.position_manager.get_portfolio_exposure()
                max_exposure = account_value * Decimal(str(self.config.max_portfolio_exposure_pct / 100.0))

                if current_exposure + position_value > max_exposure:
                    self.logger.warning(
                        f"Portfolio exposure limit exceeded: "
                        f"${current_exposure + position_value} > ${max_exposure}"
                    )
                    return False

            # Check buying power (will be validated by OrderExecutor too)
            # This is a pre-check to avoid unnecessary API calls

            return True

        except Exception as e:
            self.logger.error(f"Error checking risk limits: {e}", exc_info=True)
            return False

    async def _update_circuit_breaker(self) -> None:
        """
        Check daily P&L and trigger circuit breaker if needed.

        Circuit breaker stops all trading if daily loss exceeds threshold.
        """
        try:
            if not self.daily_start_balance:
                return

            # Get current account value
            account = await self.broker.get_account()
            current_value = account.equity

            # Calculate daily P&L
            daily_pnl = current_value - self.daily_start_balance
            daily_pnl_pct = (daily_pnl / self.daily_start_balance) * 100

            # Check if loss limit exceeded
            if daily_pnl_pct < -self.config.max_daily_loss_pct:
                if not self.circuit_breaker_active:
                    self.circuit_breaker_active = True
                    self.circuit_breaker_triggered_at = datetime.now()

                    self.logger.error(
                        f"CIRCUIT BREAKER TRIGGERED: Daily loss {daily_pnl_pct:.2f}% "
                        f"exceeds limit {self.config.max_daily_loss_pct}%"
                    )

                    # Send admin alert
                    await self._send_admin_alert(
                        f"=¨ CIRCUIT BREAKER ACTIVATED\n\n"
                        f"Daily Loss: {daily_pnl_pct:.2f}%\n"
                        f"P&L: ${daily_pnl:.2f}\n"
                        f"Current Balance: ${current_value:.2f}\n"
                        f"Trading disabled for {self.config.circuit_breaker_cooldown_minutes} minutes"
                    )

        except Exception as e:
            self.logger.error(f"Error updating circuit breaker: {e}", exc_info=True)

    # ========================================================================
    # Signal Execution
    # ========================================================================

    async def _execute_signal(self, signal: TradingSignal) -> Optional[ManagedPosition]:
        """
        Execute a trading signal.

        Args:
            signal: Trading signal to execute

        Returns:
            ManagedPosition object if successful, None otherwise
        """
        try:
            # Determine if we should use extended hours trading
            # Import here to avoid circular dependency
            from ..market_hours import is_extended_hours
            from ..config import get_settings

            settings = get_settings()
            use_extended_hours = (
                settings.trading_extended_hours and
                is_extended_hours()
            )

            if use_extended_hours:
                self.logger.info(
                    f"Extended hours trading enabled for {signal.ticker} "
                    f"(pre-market/after-hours mode)"
                )

            # Execute order
            result: ExecutionResult = await self.order_executor.execute_signal(
                signal=signal,
                use_bracket_order=True,  # Always use bracket orders for risk management
                extended_hours=use_extended_hours,
            )

            if not result.success:
                self.logger.warning(
                    f"Order execution failed for {signal.ticker}: {result.error_message}"
                )
                return None

            # Wait for order fill (with timeout)
            if result.bracket_order:
                entry_order = result.bracket_order.entry_order
            else:
                entry_order = result.order

            filled_order = await self.order_executor.wait_for_fill(
                order_id=entry_order.order_id,
                timeout=self.config.order_timeout_seconds,
            )

            if not filled_order:
                self.logger.warning(
                    f"Order {entry_order.order_id} not filled within timeout"
                )
                return None

            # Open position in PositionManager
            position = await self.position_manager.open_position(
                order=filled_order,
                signal_id=signal.signal_id,
                strategy="catalyst_keyword_v1",
                stop_loss_price=signal.stop_loss_price,
                take_profit_price=signal.take_profit_price,
            )

            return position

        except InsufficientFundsError as e:
            self.logger.warning(f"Insufficient funds for {signal.ticker}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to execute signal for {signal.ticker}: {e}", exc_info=True)
            return None

    async def _handle_close_signal(self, ticker: str) -> bool:
        """
        Handle a CLOSE signal by closing existing position.

        Args:
            ticker: Ticker symbol to close

        Returns:
            True if position closed, False otherwise
        """
        try:
            # Find open position for ticker
            position = self.position_manager.get_position_by_ticker(ticker)
            if not position:
                self.logger.debug(f"No open position found for {ticker}")
                return False

            # Close position immediately (market order)
            closed = await self.position_manager.close_position(
                position_id=position.position_id,
                exit_reason="close_signal",
            )

            if closed:
                self.logger.info(
                    f"Closed position for {ticker}: P&L=${closed.realized_pnl:.2f}"
                )
                await self._send_position_alert(closed, "closed_signal")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to handle close signal for {ticker}: {e}", exc_info=True)
            return False

    # ========================================================================
    # Market Data (MarketDataFeed - Agent 3)
    # ========================================================================

    async def _fetch_current_prices(
        self,
        positions: List[ManagedPosition]
    ) -> Dict[str, Decimal]:
        """
        Fetch current prices for positions using MarketDataFeed.

        Uses efficient batch price fetching (10-20x faster than sequential)
        with smart caching to avoid API rate limiting.

        Args:
            positions: List of positions to fetch prices for

        Returns:
            Dictionary of ticker -> current_price (Decimal)
        """
        if not positions:
            return {}

        try:
            # Extract tickers from positions
            tickers = [position.ticker for position in positions]

            # Use MarketDataFeed for efficient batch fetching
            if self.market_data_feed:
                prices = await self.market_data_feed.get_current_prices(tickers)
                self.logger.debug(
                    f"Fetched prices for {len(prices)}/{len(tickers)} positions "
                    f"(cache stats: {self.market_data_feed.get_cache_stats()})"
                )
                return prices
            else:
                # Fallback to broker API if MarketDataFeed not available
                self.logger.warning("MarketDataFeed not initialized, using broker API fallback")
                prices = {}
                for position in positions:
                    try:
                        broker_position = await self.broker.get_position(position.ticker)
                        if broker_position:
                            prices[position.ticker] = broker_position.current_price
                    except Exception as e:
                        self.logger.debug(
                            f"Failed to fetch price for {position.ticker}: {e}"
                        )
                return prices

        except Exception as e:
            self.logger.error(
                f"Failed to fetch current prices: {e}",
                exc_info=True
            )
            return {}

    # ========================================================================
    # Signal Generation (Stub for Agent 1)
    # ========================================================================

    def _generate_signal_stub(
        self,
        scored_item: ScoredItem,
        ticker: str,
        current_price: Decimal,
    ) -> Optional[TradingSignal]:
        """
        Stub signal generator.

        This will be replaced by SignalGenerator (Agent 1).
        For now, it generates simple signals based on score threshold.

        Args:
            scored_item: Scored item from classification
            ticker: Stock ticker
            current_price: Current price

        Returns:
            TradingSignal if actionable, None otherwise
        """
        try:
            # Only generate signals for high-confidence items
            if scored_item.total_score < 2.0:
                return None

            # Simple buy signal
            signal = TradingSignal(
                signal_id=f"stub_{ticker}_{datetime.now().timestamp()}",
                ticker=ticker,
                timestamp=datetime.now(),
                action="buy",
                confidence=min(scored_item.total_score / 5.0, 1.0),
                entry_price=current_price,
                current_price=current_price,
                stop_loss_price=current_price * Decimal("0.95"),  # 5% stop
                take_profit_price=current_price * Decimal("1.10"),  # 10% target
                position_size_pct=0.03,  # 3% of portfolio
                signal_type="keyword",
                timeframe="intraday",
                strategy="catalyst_stub",
                metadata={
                    "score": scored_item.total_score,
                    "sentiment": scored_item.sentiment,
                    "keywords": scored_item.keyword_hits,
                },
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating signal stub: {e}", exc_info=True)
            return None

    # ========================================================================
    # Discord Alerts
    # ========================================================================

    async def _send_position_alert(
        self,
        position,
        event_type: str,
    ) -> None:
        """
        Send Discord alert for position events.

        Args:
            position: ManagedPosition or ClosedPosition
            event_type: Event type (opened, closed, stop_loss, take_profit)
        """
        try:
            if not self.config.send_discord_alerts:
                return

            # Format alert based on event type
            if event_type == "opened":
                message = self._format_position_opened_alert(position)
            elif event_type in ["closed", "closed_signal"]:
                message = self._format_position_closed_alert(position, event_type)
            else:
                message = f"Position event: {event_type} - {position.ticker}"

            # Send via existing Discord infrastructure
            await self._send_discord_message(message)

        except Exception as e:
            self.logger.error(f"Failed to send position alert: {e}", exc_info=True)

    def _format_position_opened_alert(self, position: ManagedPosition) -> str:
        """Format Discord alert for opened position."""
        return (
            f"=5 **POSITION OPENED**\n"
            f"Ticker: **{position.ticker}**\n"
            f"Side: {position.side.value.upper()}\n"
            f"Quantity: {position.quantity} shares\n"
            f"Entry: ${position.entry_price:.2f}\n"
            f"Stop Loss: ${position.stop_loss_price:.2f}\n"
            f"Take Profit: ${position.take_profit_price:.2f}\n"
            f"Cost: ${position.cost_basis:.2f}\n"
            f"Position ID: `{position.position_id[:8]}...`"
        )

    def _format_position_closed_alert(
        self,
        position: ClosedPosition,
        event_type: str,
    ) -> str:
        """Format Discord alert for closed position."""
        emoji = "=â" if position.realized_pnl > 0 else "=4"
        reason_label = "SIGNAL" if event_type == "closed_signal" else position.exit_reason.upper()

        return (
            f"{emoji} **POSITION CLOSED - {reason_label}**\n"
            f"Ticker: **{position.ticker}**\n"
            f"Entry: ${position.entry_price:.2f}\n"
            f"Exit: ${position.exit_price:.2f}\n"
            f"P&L: **${position.realized_pnl:.2f}** ({position.realized_pnl_pct*100:.2f}%)\n"
            f"Duration: {position.get_hold_duration_hours():.1f} hours\n"
            f"Position ID: `{position.position_id[:8]}...`"
        )

    async def _send_discord_message(self, message: str) -> None:
        """
        Send message to Discord.

        Uses existing Discord webhook infrastructure from runner.py.

        Args:
            message: Message text to send
        """
        try:
            # Import Discord sending function from runner
            # For now, we'll use a simple webhook POST
            import aiohttp

            webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
            if not webhook_url:
                self.logger.warning("No Discord webhook URL configured")
                return

            async with aiohttp.ClientSession() as session:
                await session.post(
                    webhook_url,
                    json={"content": message},
                    timeout=aiohttp.ClientTimeout(total=10),
                )

        except Exception as e:
            self.logger.error(f"Failed to send Discord message: {e}", exc_info=True)

    async def _send_admin_alert(self, message: str) -> None:
        """
        Send admin alert to Discord.

        Args:
            message: Alert message
        """
        try:
            import aiohttp

            admin_webhook_url = os.getenv("DISCORD_ADMIN_WEBHOOK")
            if not admin_webhook_url:
                # Fall back to main webhook
                admin_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

            if not admin_webhook_url:
                self.logger.warning("No admin webhook URL configured")
                return

            async with aiohttp.ClientSession() as session:
                await session.post(
                    admin_webhook_url,
                    json={"content": f"**TRADING ENGINE ALERT**\n{message}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )

        except Exception as e:
            self.logger.error(f"Failed to send admin alert: {e}", exc_info=True)

    # ========================================================================
    # Utility Methods
    # ========================================================================

    async def get_portfolio_metrics(self) -> Dict:
        """
        Get current portfolio metrics.

        Returns:
            Dictionary with portfolio metrics
        """
        try:
            if not self._initialized or not self.position_manager:
                return {}

            account = await self.broker.get_account()
            metrics = self.position_manager.calculate_portfolio_metrics(account.equity)

            return {
                "total_positions": metrics.total_positions,
                "long_positions": metrics.long_positions,
                "short_positions": metrics.short_positions,
                "total_exposure": float(metrics.total_exposure),
                "net_exposure": float(metrics.net_exposure),
                "total_unrealized_pnl": float(metrics.total_unrealized_pnl),
                "total_unrealized_pnl_pct": float(metrics.total_unrealized_pnl_pct),
                "account_value": float(account.equity),
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
            }

        except Exception as e:
            self.logger.error(f"Failed to get portfolio metrics: {e}", exc_info=True)
            return {}

    def get_status(self) -> Dict:
        """
        Get current trading engine status.

        Returns:
            Status dictionary
        """
        return {
            "initialized": self._initialized,
            "trading_enabled": self.config.trading_enabled,
            "circuit_breaker_active": self.circuit_breaker_active,
            "broker_connected": bool(self.broker),
            "last_position_update": (
                self._last_position_update.isoformat()
                if self._last_position_update else None
            ),
        }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of TradingEngine.
    """

    from decimal import Decimal

    async def demo():
        """Demo function showing trading engine usage"""

        # Initialize trading engine
        engine = TradingEngine()

        # Initialize components
        success = await engine.initialize()
        if not success:
            print("Failed to initialize trading engine")
            return

        print("Trading engine initialized successfully")

        # Get portfolio metrics
        metrics = await engine.get_portfolio_metrics()
        print(f"\nPortfolio Metrics:")
        print(f"  Account Value: ${metrics.get('account_value', 0):.2f}")
        print(f"  Buying Power: ${metrics.get('buying_power', 0):.2f}")
        print(f"  Positions: {metrics.get('total_positions', 0)}")
        print(f"  Exposure: ${metrics.get('total_exposure', 0):.2f}")

        # Update positions
        update_result = await engine.update_positions()
        print(f"\nPosition Update:")
        print(f"  Positions: {update_result.get('positions', 0)}")
        print(f"  P&L: ${update_result.get('pnl', 0):.2f}")

        # Shutdown
        await engine.shutdown()
        print("\nTrading engine shutdown complete")

    # Run demo
    asyncio.run(demo())
