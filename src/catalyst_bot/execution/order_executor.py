"""
Order Executor Module

This module converts trading signals into broker orders and manages order execution.

Key responsibilities:
- Convert TradingSignal to broker Order
- Calculate position sizing
- Create bracket orders with stop-loss and take-profit
- Monitor order fills
- Log execution to database
- Handle execution errors and retries

Database Schema:
    CREATE TABLE IF NOT EXISTS executed_orders (
        order_id TEXT PRIMARY KEY,
        client_order_id TEXT,
        ticker TEXT NOT NULL,
        signal_id TEXT,  -- Link to trading signal
        side TEXT NOT NULL,
        order_type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        filled_quantity INTEGER,
        limit_price REAL,
        stop_price REAL,
        filled_avg_price REAL,
        status TEXT NOT NULL,
        submitted_at TIMESTAMP NOT NULL,
        filled_at TIMESTAMP,
        cancelled_at TIMESTAMP,
        error_message TEXT,
        metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_executed_orders_ticker
        ON executed_orders(ticker);
    CREATE INDEX IF NOT EXISTS idx_executed_orders_status
        ON executed_orders(status);
    CREATE INDEX IF NOT EXISTS idx_executed_orders_signal_id
        ON executed_orders(signal_id);
"""

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from ..broker.broker_interface import (
    BracketOrder,
    BracketOrderParams,
    BrokerError,
    BrokerInterface,
    InsufficientFundsError,
    Order,
    OrderRejectedError,
    OrderSide,
    OrderType,
    TimeInForce,
)
from ..config import get_settings
from ..logging_utils import get_logger

logger = get_logger(__name__)


# ============================================================================
# Type Definitions
# ============================================================================


@dataclass
class TradingSignal:
    """
    Represents a trading signal from the analysis system.

    This is the input to the OrderExecutor. The signal contains all the
    information needed to execute a trade.
    """

    # Identity
    signal_id: str
    ticker: str
    timestamp: datetime

    # Trading decision
    action: str  # "buy", "sell", "hold"
    confidence: float  # 0.0 to 1.0

    # Entry parameters
    entry_price: Optional[Decimal] = None  # Suggested entry price
    current_price: Optional[Decimal] = None  # Current market price

    # Risk management
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    position_size_pct: float = 0.05  # Position size as % of portfolio

    # Signal metadata
    signal_type: str = "momentum"  # momentum, breakout, mean_reversion, etc.
    timeframe: str = "intraday"  # intraday, swing, position
    strategy: str = "default"  # Which strategy generated this signal

    # Additional context
    metadata: Dict = field(default_factory=dict)

    def is_actionable(self) -> bool:
        """Check if signal is actionable (not hold)"""
        return self.action in {"buy", "sell"}

    def get_side(self) -> OrderSide:
        """Convert action to OrderSide"""
        return OrderSide.BUY if self.action == "buy" else OrderSide.SELL


@dataclass
class PositionSizingConfig:
    """
    Configuration for position sizing calculations.
    """

    # Risk parameters
    max_position_size_pct: float = 0.20  # Max 20% per position
    min_position_size_dollars: Decimal = Decimal("100")  # Minimum $100
    max_position_size_dollars: Decimal = Decimal("10000")  # Maximum $10,000

    # Risk per trade
    risk_per_trade_pct: float = 0.02  # Risk 2% per trade
    max_leverage: float = 1.0  # No leverage by default

    # Order size constraints
    min_shares: int = 1
    max_shares: int = 1000


@dataclass
class ExecutionResult:
    """
    Result of order execution.
    """

    success: bool
    order: Optional[Order] = None
    bracket_order: Optional[BracketOrder] = None
    error_message: Optional[str] = None
    quantity: int = 0
    estimated_cost: Decimal = Decimal("0")

    # Execution metadata
    signal_id: Optional[str] = None
    execution_time: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)


# ============================================================================
# Order Executor
# ============================================================================


class OrderExecutor:
    """
    Executes trading signals by placing orders with the broker.

    This class is responsible for:
    1. Converting signals to orders
    2. Calculating appropriate position sizes
    3. Creating bracket orders with risk management
    4. Monitoring order fills
    5. Logging all execution to database
    6. Handling errors and retries
    """

    def __init__(
        self,
        broker: BrokerInterface,
        db_path: Optional[Path] = None,
        position_sizing_config: Optional[PositionSizingConfig] = None,
    ):
        """
        Initialize OrderExecutor.

        Args:
            broker: Broker client implementing BrokerInterface
            db_path: Path to SQLite database
            position_sizing_config: Position sizing configuration
        """
        self.broker = broker
        self.logger = get_logger(__name__)

        # Database setup
        settings = get_settings()
        self.db_path = db_path or settings.data_dir / "trading.db"
        self._init_database()

        # Position sizing configuration
        self.sizing_config = position_sizing_config or PositionSizingConfig()

        # Execution tracking
        self._pending_orders: Dict[str, Order] = {}
        self._filled_orders: Dict[str, Order] = {}

        self.logger.info(
            f"Initialized OrderExecutor (db={self.db_path}, "
            f"max_position_pct={self.sizing_config.max_position_size_pct})"
        )

    # ========================================================================
    # Database Management
    # ========================================================================

    def _init_database(self) -> None:
        """
        Initialize database schema for order execution tracking.
        """
        try:
            # Ensure directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                # Create executed_orders table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS executed_orders (
                        order_id TEXT PRIMARY KEY,
                        client_order_id TEXT,
                        ticker TEXT NOT NULL,
                        signal_id TEXT,
                        side TEXT NOT NULL,
                        order_type TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        filled_quantity INTEGER,
                        limit_price REAL,
                        stop_price REAL,
                        filled_avg_price REAL,
                        status TEXT NOT NULL,
                        submitted_at TIMESTAMP NOT NULL,
                        filled_at TIMESTAMP,
                        cancelled_at TIMESTAMP,
                        error_message TEXT,
                        metadata JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Create indexes
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_executed_orders_ticker
                    ON executed_orders(ticker)
                """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_executed_orders_status
                    ON executed_orders(status)
                """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_executed_orders_signal_id
                    ON executed_orders(signal_id)
                """
                )

                conn.commit()
                self.logger.info("Database initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    def _save_order_to_db(
        self,
        order: Order,
        signal_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Save order to database.

        Args:
            order: Order object to save
            signal_id: Associated trading signal ID
            error_message: Error message if execution failed
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO executed_orders (
                        order_id, client_order_id, ticker, signal_id,
                        side, order_type, quantity, filled_quantity,
                        limit_price, stop_price, filled_avg_price,
                        status, submitted_at, filled_at, cancelled_at,
                        error_message, metadata, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order.order_id,
                        order.client_order_id,
                        order.ticker,
                        signal_id,
                        order.side.value,
                        order.order_type.value,
                        order.quantity,
                        order.filled_quantity,
                        float(order.limit_price) if order.limit_price else None,
                        float(order.stop_price) if order.stop_price else None,
                        (
                            float(order.filled_avg_price)
                            if order.filled_avg_price
                            else None
                        ),
                        order.status.value,
                        order.submitted_at.isoformat() if order.submitted_at else None,
                        order.filled_at.isoformat() if order.filled_at else None,
                        order.cancelled_at.isoformat() if order.cancelled_at else None,
                        error_message,
                        json.dumps(order.metadata),
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                self.logger.debug(f"Saved order {order.order_id} to database")

        except Exception as e:
            self.logger.error(f"Failed to save order to database: {e}")

    # ========================================================================
    # Position Sizing
    # ========================================================================

    def calculate_position_size(
        self,
        signal: TradingSignal,
        account_value: Decimal,
        current_price: Decimal,
    ) -> int:
        """
        Calculate appropriate position size based on signal and account.

        Uses multiple sizing methods:
        1. Percentage of portfolio
        2. Risk-based sizing (based on stop loss distance)
        3. Kelly criterion (if win rate data available)

        Args:
            signal: Trading signal
            account_value: Current account value
            current_price: Current stock price

        Returns:
            Number of shares to trade
        """
        # TODO: Implement position sizing logic

        # Method 1: Percentage of portfolio
        position_value_pct = min(
            signal.position_size_pct,
            self.sizing_config.max_position_size_pct,
        )
        shares_from_pct = int(
            (account_value * Decimal(str(position_value_pct))) / current_price
        )

        # Method 2: Risk-based sizing
        shares_from_risk = self._calculate_risk_based_size(
            signal, account_value, current_price
        )

        # TODO: Method 3: Kelly criterion (if historical data available)
        # shares_from_kelly = self._calculate_kelly_size(signal, account_value, current_price)

        # Use the most conservative (smallest) size
        shares = min(shares_from_pct, shares_from_risk)

        # Apply constraints
        shares = max(shares, self.sizing_config.min_shares)
        shares = min(shares, self.sizing_config.max_shares)

        # Check minimum dollar amount
        position_value = shares * current_price
        if position_value < self.sizing_config.min_position_size_dollars:
            shares = (
                int(self.sizing_config.min_position_size_dollars / current_price) + 1
            )

        # Check maximum dollar amount
        if position_value > self.sizing_config.max_position_size_dollars:
            shares = int(self.sizing_config.max_position_size_dollars / current_price)

        self.logger.info(
            f"Calculated position size for {signal.ticker}: {shares} shares "
            f"(${position_value:.2f}, {position_value_pct*100:.1f}% of portfolio)"
        )

        return shares

    def _calculate_risk_based_size(
        self,
        signal: TradingSignal,
        account_value: Decimal,
        current_price: Decimal,
    ) -> int:
        """
        Calculate position size based on risk per trade.

        Formula: shares = (account_value * risk_pct) / (entry_price - stop_loss_price)

        Args:
            signal: Trading signal
            account_value: Current account value
            current_price: Current stock price

        Returns:
            Number of shares
        """
        if not signal.stop_loss_price:
            # No stop loss defined, fall back to percentage sizing
            return int(
                (account_value * Decimal(str(self.sizing_config.max_position_size_pct)))
                / current_price
            )

        # Calculate risk per share
        entry_price = signal.entry_price or current_price
        risk_per_share = abs(entry_price - signal.stop_loss_price)

        if risk_per_share == 0:
            return int(
                (account_value * Decimal(str(self.sizing_config.max_position_size_pct)))
                / current_price
            )

        # Calculate shares based on risk
        max_risk_dollars = account_value * Decimal(
            str(self.sizing_config.risk_per_trade_pct)
        )
        shares = int(max_risk_dollars / risk_per_share)

        return shares

    # ========================================================================
    # Signal Execution
    # ========================================================================

    def _round_price_for_alpaca(self, price: Optional[Decimal]) -> Optional[Decimal]:
        """
        Round price according to Alpaca's pricing rules.

        Alpaca Rules:
        - Stocks >= $1.00: Penny increments only (e.g., $8.83, not $8.829999)
        - Stocks < $1.00: Sub-penny increments allowed (e.g., $0.8392)

        Args:
            price: Price to round (can be None)

        Returns:
            Rounded price, or None if input was None
        """
        if price is None:
            return None

        if price >= Decimal("1.00"):
            # Stocks >= $1: Round to 2 decimal places (penny increment)
            return price.quantize(Decimal("0.01"))
        else:
            # Stocks < $1: Round to 4 decimal places (sub-penny allowed)
            return price.quantize(Decimal("0.0001"))

    async def execute_signal(
        self,
        signal: TradingSignal,
        use_bracket_order: bool = True,
        extended_hours: bool = False,
    ) -> ExecutionResult:
        """
        Execute a trading signal.

        Args:
            signal: Trading signal to execute
            use_bracket_order: Whether to use bracket orders (entry + stop + target)
            extended_hours: Whether to enable extended hours trading (pre-market/after-hours)

        Returns:
            ExecutionResult with execution details
        """
        self.logger.info(
            f"Executing signal: {signal.ticker} {signal.action} "
            f"(confidence={signal.confidence:.2f}, extended_hours={extended_hours})"
        )

        try:
            # Validate signal
            if not signal.is_actionable():
                return ExecutionResult(
                    success=False,
                    error_message="Signal is not actionable (action=hold)",
                    signal_id=signal.signal_id,
                )

            # Get account information
            account = await self.broker.get_account()

            # Check if account can trade
            if not account.is_tradeable():
                return ExecutionResult(
                    success=False,
                    error_message="Account is not tradeable",
                    signal_id=signal.signal_id,
                )

            # Get current price
            current_price = signal.current_price or signal.entry_price
            if not current_price:
                # TODO: Fetch current price from market data provider
                return ExecutionResult(
                    success=False,
                    error_message="Unable to determine current price",
                    signal_id=signal.signal_id,
                )

            # Calculate position size
            quantity = self.calculate_position_size(
                signal=signal,
                account_value=account.equity,
                current_price=current_price,
            )

            if quantity <= 0:
                return ExecutionResult(
                    success=False,
                    error_message="Position size too small",
                    signal_id=signal.signal_id,
                )

            # Estimate cost
            estimated_cost = current_price * quantity

            # Check buying power
            if estimated_cost > account.buying_power:
                self.logger.warning(
                    f"Insufficient buying power: need ${estimated_cost}, "
                    f"have ${account.buying_power}"
                )
                return ExecutionResult(
                    success=False,
                    error_message="Insufficient buying power",
                    signal_id=signal.signal_id,
                    quantity=quantity,
                    estimated_cost=estimated_cost,
                )

            # Execute order
            # Note: Alpaca doesn't support bracket orders during extended hours
            # Fall back to simple orders when trading pre-market/after-hours
            if (
                use_bracket_order
                and signal.stop_loss_price
                and signal.take_profit_price
                and not extended_hours
            ):
                result = await self._execute_bracket_order(
                    signal, quantity, extended_hours=extended_hours
                )
            else:
                if extended_hours and use_bracket_order:
                    self.logger.info(
                        f"Using simple order instead of bracket for {signal.ticker} "
                        "(extended hours trading - bracket orders not supported)"
                    )
                result = await self._execute_simple_order(
                    signal, quantity, extended_hours=extended_hours
                )

            # Log execution
            self.logger.info(
                f"Executed {signal.ticker}: success={result.success}, "
                f"quantity={result.quantity}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Failed to execute signal for {signal.ticker}: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

    async def _execute_simple_order(
        self,
        signal: TradingSignal,
        quantity: int,
        extended_hours: bool = False,
    ) -> ExecutionResult:
        """
        Execute a simple market order.

        Args:
            signal: Trading signal
            quantity: Number of shares
            extended_hours: Whether to enable extended hours trading

        Returns:
            ExecutionResult
        """
        try:
            # Generate client order ID
            client_order_id = f"signal_{signal.signal_id}_{uuid.uuid4().hex[:8]}"

            # Determine order type and time in force based on extended hours
            # Alpaca requirement: Extended hours must use DAY limit orders (no GTC, no market)
            if extended_hours:
                order_type = OrderType.LIMIT
                time_in_force = TimeInForce.DAY
                # Use current price as limit for extended hours limit order
                raw_price = signal.current_price or signal.entry_price
                limit_price = self._round_price_for_alpaca(raw_price)
            else:
                order_type = OrderType.MARKET
                time_in_force = TimeInForce.DAY
                limit_price = None

            # Place order
            order = await self.broker.place_order(
                ticker=signal.ticker,
                side=signal.get_side(),
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                time_in_force=time_in_force,
                extended_hours=extended_hours,
                client_order_id=client_order_id,
            )

            # Save to database
            self._save_order_to_db(order, signal_id=signal.signal_id)

            # Track order
            self._pending_orders[order.order_id] = order

            return ExecutionResult(
                success=True,
                order=order,
                quantity=quantity,
                estimated_cost=Decimal(str(quantity))
                * (signal.current_price or Decimal("0")),
                signal_id=signal.signal_id,
            )

        except InsufficientFundsError as e:
            self.logger.error(f"Insufficient funds: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

        except OrderRejectedError as e:
            self.logger.error(f"Order rejected: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

        except BrokerError as e:
            self.logger.error(f"Broker error: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

    async def _execute_bracket_order(
        self,
        signal: TradingSignal,
        quantity: int,
        extended_hours: bool = False,
    ) -> ExecutionResult:
        """
        Execute a bracket order (entry + stop loss + take profit).

        Args:
            signal: Trading signal
            quantity: Number of shares
            extended_hours: Whether to enable extended hours trading

        Returns:
            ExecutionResult
        """
        try:
            # Validate bracket order parameters
            if not signal.stop_loss_price or not signal.take_profit_price:
                raise ValueError(
                    "Stop loss and take profit prices required for bracket order"
                )

            # Generate client order ID
            client_order_id = f"bracket_{signal.signal_id}_{uuid.uuid4().hex[:8]}"

            # Determine order parameters based on extended hours
            # Alpaca requirement: Extended hours must use DAY limit orders
            if extended_hours:
                # Extended hours: MUST use DAY limit orders
                entry_type = OrderType.LIMIT
                raw_entry_price = signal.entry_price or signal.current_price
                entry_limit_price = self._round_price_for_alpaca(raw_entry_price)
                time_in_force = TimeInForce.DAY
            else:
                # Regular hours: Can use GTC and market/limit orders
                entry_type = OrderType.LIMIT if signal.entry_price else OrderType.MARKET
                entry_limit_price = self._round_price_for_alpaca(signal.entry_price)
                time_in_force = TimeInForce.GTC

            # Round stop-loss and take-profit prices for Alpaca compliance
            stop_loss_price = self._round_price_for_alpaca(signal.stop_loss_price)
            take_profit_price = self._round_price_for_alpaca(signal.take_profit_price)

            # Create bracket order parameters
            params = BracketOrderParams(
                ticker=signal.ticker,
                side=signal.get_side(),
                quantity=quantity,
                entry_type=entry_type,
                entry_limit_price=entry_limit_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                time_in_force=time_in_force,
                extended_hours=extended_hours,
                client_order_id=client_order_id,
            )

            # Place bracket order
            bracket_order = await self.broker.place_bracket_order(params)

            # Save all orders to database
            self._save_order_to_db(
                bracket_order.entry_order, signal_id=signal.signal_id
            )
            self._save_order_to_db(
                bracket_order.stop_loss_order, signal_id=signal.signal_id
            )
            self._save_order_to_db(
                bracket_order.take_profit_order, signal_id=signal.signal_id
            )

            # Track orders
            self._pending_orders[bracket_order.entry_order.order_id] = (
                bracket_order.entry_order
            )
            self._pending_orders[bracket_order.stop_loss_order.order_id] = (
                bracket_order.stop_loss_order
            )
            self._pending_orders[bracket_order.take_profit_order.order_id] = (
                bracket_order.take_profit_order
            )

            return ExecutionResult(
                success=True,
                bracket_order=bracket_order,
                quantity=quantity,
                estimated_cost=Decimal(str(quantity))
                * (signal.entry_price or signal.current_price or Decimal("0")),
                signal_id=signal.signal_id,
            )

        except InsufficientFundsError as e:
            self.logger.error(f"Insufficient funds: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

        except OrderRejectedError as e:
            self.logger.error(f"Order rejected: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

        except BrokerError as e:
            self.logger.error(f"Broker error: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                signal_id=signal.signal_id,
            )

    # ========================================================================
    # Order Monitoring
    # ========================================================================

    async def monitor_pending_orders(self) -> List[Order]:
        """
        Monitor all pending orders and update their status.

        Returns:
            List of newly filled orders
        """
        filled_orders = []

        for order_id in list(self._pending_orders.keys()):
            try:
                # Fetch latest order status
                updated_order = await self.broker.get_order(order_id)

                # Update database
                self._save_order_to_db(updated_order)

                # Check if filled
                if updated_order.is_filled():
                    self.logger.info(
                        f"Order filled: {order_id} - {updated_order.ticker} "
                        f"{updated_order.filled_quantity} @ ${updated_order.filled_avg_price}"
                    )
                    filled_orders.append(updated_order)
                    self._filled_orders[order_id] = updated_order
                    del self._pending_orders[order_id]

                # Check if cancelled/rejected
                elif not updated_order.is_active():
                    self.logger.warning(
                        f"Order no longer active: {order_id} - status={updated_order.status}"
                    )
                    del self._pending_orders[order_id]

                else:
                    # Still pending, update tracking
                    self._pending_orders[order_id] = updated_order

            except Exception as e:
                self.logger.error(f"Failed to monitor order {order_id}: {e}")

        return filled_orders

    async def wait_for_fill(
        self,
        order_id: str,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> Optional[Order]:
        """
        Wait for an order to be filled.

        Args:
            order_id: Order ID to wait for
            timeout: Maximum time to wait (seconds)
            poll_interval: How often to check (seconds)

        Returns:
            Filled order, or None if timeout
        """
        elapsed = 0.0

        while elapsed < timeout:
            try:
                order = await self.broker.get_order(order_id)

                if order.is_filled():
                    self.logger.info(f"Order {order_id} filled")
                    self._save_order_to_db(order)
                    return order

                if not order.is_active():
                    self.logger.warning(
                        f"Order {order_id} no longer active: status={order.status}"
                    )
                    return None

            except Exception as e:
                self.logger.error(f"Error checking order {order_id}: {e}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        self.logger.warning(f"Timeout waiting for order {order_id} to fill")
        return None

    # ========================================================================
    # Utility Methods
    # ========================================================================

    async def get_execution_stats(self, days: int = 30) -> Dict:
        """
        Get execution statistics for the last N days.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with execution statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # TODO: Calculate execution statistics
                # - Total orders executed
                # - Fill rate
                # - Average fill time
                # - Rejected orders
                # - Total volume traded

                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_orders,
                        SUM(CASE WHEN status = 'filled' THEN 1 ELSE 0 END) as filled_orders,
                        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_orders,
                        AVG(quantity) as avg_quantity,
                        SUM(quantity * COALESCE(filled_avg_price, 0)) as total_volume
                    FROM executed_orders
                    WHERE created_at >= datetime('now', '-' || ? || ' days')
                    """,
                    (days,),
                )

                row = cursor.fetchone()

                return {
                    "total_orders": row[0] or 0,
                    "filled_orders": row[1] or 0,
                    "rejected_orders": row[2] or 0,
                    "fill_rate": (row[1] / row[0]) if row[0] else 0.0,
                    "avg_quantity": row[3] or 0.0,
                    "total_volume": row[4] or 0.0,
                }

        except Exception as e:
            self.logger.error(f"Failed to get execution stats: {e}")
            return {}


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of OrderExecutor.

    This demonstrates how to execute trading signals.
    """

    from decimal import Decimal

    from ..broker.alpaca_client import AlpacaBrokerClient

    async def demo():
        """Demo function showing order execution"""

        # Initialize broker (paper trading)
        broker = AlpacaBrokerClient(paper_trading=True)
        await broker.connect()

        # Initialize order executor
        executor = OrderExecutor(
            broker=broker,
            position_sizing_config=PositionSizingConfig(
                max_position_size_pct=0.10,  # 10% max per position
                risk_per_trade_pct=0.02,  # 2% risk per trade
            ),
        )

        # Create a trading signal
        signal = TradingSignal(
            signal_id="test_signal_001",
            ticker="AAPL",
            timestamp=datetime.now(),
            action="buy",
            confidence=0.85,
            current_price=Decimal("150.00"),
            entry_price=Decimal("150.00"),
            stop_loss_price=Decimal("145.00"),  # 3.3% stop
            take_profit_price=Decimal("160.00"),  # 6.7% profit target
            position_size_pct=0.05,  # 5% of portfolio
            signal_type="momentum",
            timeframe="intraday",
            strategy="catalyst_momentum_v1",
        )

        # Execute signal with bracket order
        result = await executor.execute_signal(
            signal=signal,
            use_bracket_order=True,
        )

        print("\nExecution Result:")
        print(f"  Success: {result.success}")
        print(f"  Quantity: {result.quantity}")
        print(f"  Estimated Cost: ${result.estimated_cost}")

        if result.bracket_order:
            print(f"  Entry Order: {result.bracket_order.entry_order.order_id}")
            print(f"  Stop Loss: {result.bracket_order.stop_loss_order.order_id}")
            print(f"  Take Profit: {result.bracket_order.take_profit_order.order_id}")

        # Monitor pending orders
        print("\nMonitoring pending orders...")
        for i in range(5):
            await asyncio.sleep(2)
            filled = await executor.monitor_pending_orders()
            if filled:
                print(f"  Filled: {len(filled)} orders")

        # Get execution stats
        stats = await executor.get_execution_stats(days=30)
        print("\nExecution Statistics (30 days):")
        print(f"  Total Orders: {stats.get('total_orders', 0)}")
        print(f"  Fill Rate: {stats.get('fill_rate', 0)*100:.1f}%")
        print(f"  Total Volume: ${stats.get('total_volume', 0):.2f}")

        # Disconnect
        await broker.disconnect()

    # Run demo
    asyncio.run(demo())
