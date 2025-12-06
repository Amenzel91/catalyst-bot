# Paper Trading Bot Implementation Tickets

**Project:** Catalyst Bot Enhancement - Paper Trading with RL
**Created:** 2025-11-20
**Total Estimated Timeline:** 16-24 weeks (4-6 months)

---

## Table of Contents

1. [Epic 1: Broker Integration & Order Execution](#epic-1-broker-integration--order-execution)
2. [Epic 2: Risk Management & Safety Systems](#epic-2-risk-management--safety-systems)
3. [Epic 3: RL Training Infrastructure](#epic-3-rl-training-infrastructure)

---

# Epic 1: Broker Integration & Order Execution

## Epic 1: Broker Integration & Order Execution (Foundation)
**Priority:** P0 (Critical Path)
**Estimated Effort:** 4 weeks
**Dependencies:** None

### Overview
Establish the foundational trading infrastructure by integrating with Alpaca's paper trading API, implementing order execution logic, and creating position/portfolio tracking systems. This epic provides the core capabilities needed before adding risk management or machine learning components.

### Stories
- Story 1.1: Alpaca Broker Client Implementation
- Story 1.2: Order Execution Engine
- Story 1.3: Position Manager & Database Schema
- Story 1.4: Portfolio Tracker & Performance Analytics
- Story 1.5: Integration with Existing Alert System

---

### Story 1.1: Alpaca Broker Client Implementation
**Priority:** P0
**Estimated Effort:** 3-4 days
**Dependencies:** None

**Description:**
Create a robust wrapper around the Alpaca API for paper trading. This client will handle all broker interactions including order submission, account queries, position retrieval, and error handling. The implementation must include automatic retry logic, rate limiting, and comprehensive logging.

**Tasks:**

- [ ] Task 1.1.1: Set up Alpaca paper trading account and API credentials
- [ ] Task 1.1.2: Implement AlpacaBrokerClient base class
- [ ] Task 1.1.3: Add order placement methods (market, limit, bracket orders)
- [ ] Task 1.1.4: Implement position and account query methods
- [ ] Task 1.1.5: Add error handling and retry logic
- [ ] Task 1.1.6: Create comprehensive unit tests

#### Task 1.1.2: Implement AlpacaBrokerClient Base Class
**File:** `/home/user/catalyst-bot/src/catalyst_bot/broker/alpaca_client.py`
**Estimated Effort:** 1 day

**Implementation:**
Create a comprehensive broker client that wraps the Alpaca API with production-ready error handling, retry logic, and logging. The client should support both paper and live trading modes (configurable) and handle all common broker operations.

**Code Scaffold:**
```python
"""
Alpaca broker client for paper and live trading.
"""
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopLossRequest,
    TakeProfitRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.common.exceptions import APIError
import time

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """Standardized order representation."""
    order_id: str
    symbol: str
    qty: float
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit', 'stop', 'bracket'
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = 'pending'
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


@dataclass
class Position:
    """Standardized position representation."""
    symbol: str
    qty: float
    side: str  # 'long' or 'short'
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float  # Unrealized P&L percentage


@dataclass
class Account:
    """Account information."""
    account_id: str
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float
    last_equity: float
    initial_margin: float
    maintenance_margin: float
    daytrade_count: int
    daytrading_buying_power: float


class AlpacaBrokerClient:
    """
    Production-ready Alpaca broker client with error handling and retry logic.

    Features:
    - Automatic retry on rate limits (429 errors)
    - Exponential backoff on failures
    - Order validation before submission
    - Position synchronization
    - Comprehensive logging

    Usage:
        client = AlpacaBrokerClient(
            api_key=os.getenv('ALPACA_API_KEY'),
            secret_key=os.getenv('ALPACA_SECRET'),
            paper=True
        )

        order = client.place_market_order('AAPL', 10, 'buy')
        positions = client.get_positions()
        account = client.get_account()
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize Alpaca client.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: True for paper trading, False for live
            max_retries: Maximum retry attempts on failures
            retry_delay: Initial delay between retries (seconds)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Initialize Alpaca client
        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )

        logger.info(f"Alpaca client initialized (paper={paper})")

    def _retry_on_error(self, func, *args, **kwargs):
        """
        Execute function with retry logic.

        Handles:
        - 429 (rate limit): Wait and retry
        - 5xx (server errors): Exponential backoff
        - Network errors: Retry with backoff
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)

            except APIError as e:
                last_error = e

                if e.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Rate limited by Alpaca (429). "
                        f"Waiting {wait_time}s before retry {attempt + 1}/{self.max_retries}"
                    )
                    time.sleep(wait_time)

                elif 500 <= e.status_code < 600:
                    # Server error - exponential backoff
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.error(
                        f"Alpaca server error ({e.status_code}). "
                        f"Retrying in {wait_time}s ({attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(wait_time)

                else:
                    # Client error - don't retry
                    logger.error(f"Alpaca API error: {e}")
                    raise

            except Exception as e:
                last_error = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.error(
                    f"Error calling Alpaca API: {e}. "
                    f"Retrying in {wait_time}s ({attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)

        # All retries exhausted
        logger.error(f"All {self.max_retries} retry attempts failed")
        raise last_error

    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        time_in_force: str = 'day'
    ) -> Order:
        """
        Place a market order.

        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            qty: Number of shares
            side: 'buy' or 'sell'
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Order object with order details
        """
        logger.info(f"Placing market order: {side.upper()} {qty} {symbol}")

        # Validate inputs
        assert side in ['buy', 'sell'], f"Invalid side: {side}"
        assert qty > 0, f"Invalid quantity: {qty}"

        # Create order request
        order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL
        tif = TimeInForce[time_in_force.upper()]

        market_order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=tif
        )

        # Submit order with retry logic
        alpaca_order = self._retry_on_error(
            self.client.submit_order,
            market_order
        )

        # Convert to standardized format
        order = self._alpaca_order_to_order(alpaca_order)

        logger.info(
            f"Market order placed: {order.order_id} - "
            f"{side.upper()} {qty} {symbol} @ MARKET"
        )

        return order

    def place_limit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        limit_price: float,
        time_in_force: str = 'day'
    ) -> Order:
        """
        Place a limit order.

        Args:
            symbol: Stock ticker
            qty: Number of shares
            side: 'buy' or 'sell'
            limit_price: Limit price
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Order object
        """
        logger.info(
            f"Placing limit order: {side.upper()} {qty} {symbol} @ ${limit_price}"
        )

        # Validate inputs
        assert side in ['buy', 'sell'], f"Invalid side: {side}"
        assert qty > 0, f"Invalid quantity: {qty}"
        assert limit_price > 0, f"Invalid limit price: {limit_price}"

        # Create order request
        order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL
        tif = TimeInForce[time_in_force.upper()]

        limit_order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            limit_price=limit_price,
            time_in_force=tif
        )

        # Submit order with retry logic
        alpaca_order = self._retry_on_error(
            self.client.submit_order,
            limit_order
        )

        order = self._alpaca_order_to_order(alpaca_order)

        logger.info(
            f"Limit order placed: {order.order_id} - "
            f"{side.upper()} {qty} {symbol} @ ${limit_price}"
        )

        return order

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        entry_price: float,
        take_profit_price: float,
        stop_loss_price: float
    ) -> Dict[str, Order]:
        """
        Place a bracket order (entry + take profit + stop loss).

        Args:
            symbol: Stock ticker
            qty: Number of shares
            side: 'buy' or 'sell'
            entry_price: Entry limit price
            take_profit_price: Take profit limit price
            stop_loss_price: Stop loss price

        Returns:
            Dict with 'entry', 'take_profit', 'stop_loss' orders
        """
        # TODO: Implement bracket order logic
        # Alpaca supports bracket orders via order_class='bracket'
        raise NotImplementedError("Bracket orders not yet implemented")

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        logger.info(f"Cancelling order: {order_id}")

        try:
            self._retry_on_error(self.client.cancel_order_by_id, order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Order:
        """
        Get order details.

        Args:
            order_id: Order ID

        Returns:
            Order object
        """
        alpaca_order = self._retry_on_error(
            self.client.get_order_by_id,
            order_id
        )

        return self._alpaca_order_to_order(alpaca_order)

    def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        Get list of orders.

        Args:
            status: Filter by status ('open', 'closed', 'all')
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        request = GetOrdersRequest(
            status=status,
            limit=limit
        )

        alpaca_orders = self._retry_on_error(
            self.client.get_orders,
            request
        )

        return [self._alpaca_order_to_order(o) for o in alpaca_orders]

    def get_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects
        """
        alpaca_positions = self._retry_on_error(self.client.get_all_positions)

        positions = [self._alpaca_position_to_position(p) for p in alpaca_positions]

        logger.debug(f"Retrieved {len(positions)} open positions")

        return positions

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock ticker

        Returns:
            Position object or None if no position
        """
        try:
            alpaca_position = self._retry_on_error(
                self.client.get_open_position,
                symbol
            )
            return self._alpaca_position_to_position(alpaca_position)

        except APIError as e:
            if e.status_code == 404:
                return None
            raise

    def get_account(self) -> Account:
        """
        Get account information.

        Returns:
            Account object
        """
        alpaca_account = self._retry_on_error(self.client.get_account)

        account = Account(
            account_id=alpaca_account.id,
            cash=float(alpaca_account.cash),
            portfolio_value=float(alpaca_account.portfolio_value),
            buying_power=float(alpaca_account.buying_power),
            equity=float(alpaca_account.equity),
            last_equity=float(alpaca_account.last_equity),
            initial_margin=float(alpaca_account.initial_margin),
            maintenance_margin=float(alpaca_account.maintenance_margin),
            daytrade_count=alpaca_account.daytrade_count,
            daytrading_buying_power=float(alpaca_account.daytrading_buying_power)
        )

        logger.debug(
            f"Account: ${account.portfolio_value:.2f} value, "
            f"${account.cash:.2f} cash, ${account.buying_power:.2f} buying power"
        )

        return account

    def close_position(self, symbol: str, qty: Optional[float] = None) -> Order:
        """
        Close a position (market order).

        Args:
            symbol: Stock ticker
            qty: Number of shares to close (None = close all)

        Returns:
            Order object for the closing order
        """
        position = self.get_position(symbol)

        if not position:
            raise ValueError(f"No open position for {symbol}")

        # Determine quantity and side
        qty_to_close = qty if qty else abs(position.qty)
        side = 'sell' if position.side == 'long' else 'buy'

        logger.info(f"Closing {qty_to_close} shares of {symbol} position")

        return self.place_market_order(symbol, qty_to_close, side)

    def close_all_positions(self) -> List[Order]:
        """
        Close all open positions.

        Returns:
            List of closing orders
        """
        positions = self.get_positions()

        if not positions:
            logger.info("No positions to close")
            return []

        logger.info(f"Closing {len(positions)} positions")

        orders = []
        for position in positions:
            try:
                order = self.close_position(position.symbol)
                orders.append(order)
            except Exception as e:
                logger.error(f"Failed to close position {position.symbol}: {e}")

        return orders

    def _alpaca_order_to_order(self, alpaca_order) -> Order:
        """Convert Alpaca order to standardized Order."""
        return Order(
            order_id=alpaca_order.id,
            symbol=alpaca_order.symbol,
            qty=float(alpaca_order.qty),
            side=alpaca_order.side.value,
            order_type=alpaca_order.type.value,
            limit_price=float(alpaca_order.limit_price) if alpaca_order.limit_price else None,
            stop_price=float(alpaca_order.stop_price) if alpaca_order.stop_price else None,
            status=alpaca_order.status.value,
            filled_qty=float(alpaca_order.filled_qty) if alpaca_order.filled_qty else 0.0,
            filled_avg_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
            submitted_at=alpaca_order.submitted_at,
            filled_at=alpaca_order.filled_at
        )

    def _alpaca_position_to_position(self, alpaca_position) -> Position:
        """Convert Alpaca position to standardized Position."""
        return Position(
            symbol=alpaca_position.symbol,
            qty=float(alpaca_position.qty),
            side='long' if float(alpaca_position.qty) > 0 else 'short',
            avg_entry_price=float(alpaca_position.avg_entry_price),
            current_price=float(alpaca_position.current_price),
            market_value=float(alpaca_position.market_value),
            unrealized_pl=float(alpaca_position.unrealized_pl),
            unrealized_plpc=float(alpaca_position.unrealized_plpc)
        )
```

**Acceptance Criteria:**
- [ ] Client connects to Alpaca paper trading API successfully
- [ ] Market orders execute without errors
- [ ] Limit orders submit correctly
- [ ] Position queries return accurate data
- [ ] Account queries return correct balances
- [ ] Retry logic handles 429 rate limits automatically
- [ ] All broker operations logged comprehensively
- [ ] Error handling prevents crashes on API failures

**Tests Required:**
- Unit tests:
  - Test market order submission
  - Test limit order submission
  - Test order cancellation
  - Test position retrieval
  - Test account retrieval
  - Test retry logic on simulated failures
  - Test rate limit handling
- Integration tests:
  - Connect to Alpaca paper API
  - Submit real paper trading orders
  - Verify order execution
  - Verify position tracking

**Dependencies:** None

---

### Story 1.2: Order Execution Engine
**Priority:** P0
**Estimated Effort:** 4-5 days
**Dependencies:** Story 1.1

**Description:**
Build the order execution engine that converts trading signals into executed orders. This engine sits between the strategy layer and the broker API, handling order parameter calculation, submission, fill monitoring, and execution confirmation. Must integrate with existing alert system and trade plan calculation.

**Tasks:**

- [ ] Task 1.2.1: Create OrderExecutor base class
- [ ] Task 1.2.2: Implement signal-to-order conversion logic
- [ ] Task 1.2.3: Add position sizing calculator
- [ ] Task 1.2.4: Implement order monitoring and fill tracking
- [ ] Task 1.2.5: Add execution result logging and database storage
- [ ] Task 1.2.6: Integrate with existing trade_plan.py module

#### Task 1.2.1: Create OrderExecutor Base Class
**File:** `/home/user/catalyst-bot/src/catalyst_bot/execution/order_executor.py`
**Estimated Effort:** 2 days

**Implementation:**
Create a comprehensive order execution engine that bridges trading signals and broker API. The executor should handle the complete order lifecycle: validation, submission, monitoring, and confirmation. Must integrate with existing `trade_plan.py` for stop-loss/take-profit calculation and `rvol.py` for volatility-adjusted sizing.

**Code Scaffold:**
```python
"""
Order execution engine for converting signals to executed trades.
"""
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import asyncio

from catalyst_bot.broker.alpaca_client import AlpacaBrokerClient, Order, Account
from catalyst_bot.trade_plan import calculate_trade_plan
from catalyst_bot.rvol import get_rvol
from catalyst_bot.market import get_current_price

logger = logging.getLogger(__name__)


class SignalAction(Enum):
    """Trading signal actions."""
    BUY = 'buy'
    SELL = 'sell'
    HOLD = 'hold'


@dataclass
class TradingSignal:
    """
    Trading signal from strategy/alert system.
    """
    ticker: str
    action: SignalAction
    confidence: float  # 0.0 to 1.0
    catalyst_score: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_pct: Optional[float] = None  # Percentage of portfolio
    metadata: Optional[Dict] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ExecutionResult:
    """
    Result of order execution.
    """
    success: bool
    signal: TradingSignal
    order: Optional[Order]
    position_size: float
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    error_message: Optional[str] = None
    execution_time: float = 0.0  # seconds
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class PositionSizingMethod(Enum):
    """Position sizing methods."""
    FIXED_PERCENTAGE = 'fixed_pct'
    KELLY_CRITERION = 'kelly'
    VOLATILITY_ADJUSTED = 'volatility'
    SIGNAL_CONFIDENCE = 'confidence'


class OrderExecutor:
    """
    Order execution engine - converts signals to executed trades.

    Responsibilities:
    1. Validate trading signals
    2. Calculate position sizes
    3. Determine entry/stop/target prices
    4. Submit orders to broker
    5. Monitor order fills
    6. Log execution results

    Usage:
        executor = OrderExecutor(
            broker_client=alpaca_client,
            sizing_method=PositionSizingMethod.VOLATILITY_ADJUSTED,
            max_position_pct=0.10
        )

        signal = TradingSignal(
            ticker='AAPL',
            action=SignalAction.BUY,
            confidence=0.85,
            catalyst_score=0.92
        )

        result = await executor.execute_signal(signal)
    """

    def __init__(
        self,
        broker_client: AlpacaBrokerClient,
        sizing_method: PositionSizingMethod = PositionSizingMethod.FIXED_PERCENTAGE,
        max_position_pct: float = 0.10,
        default_position_pct: float = 0.05,
        use_limit_orders: bool = True,
        order_timeout: int = 60,
        min_confidence: float = 0.70
    ):
        """
        Initialize order executor.

        Args:
            broker_client: Alpaca broker client
            sizing_method: Method for position sizing
            max_position_pct: Maximum position size (% of portfolio)
            default_position_pct: Default position size if not specified
            use_limit_orders: Use limit orders (vs market orders)
            order_timeout: Timeout for order fills (seconds)
            min_confidence: Minimum signal confidence to execute
        """
        self.broker = broker_client
        self.sizing_method = sizing_method
        self.max_position_pct = max_position_pct
        self.default_position_pct = default_position_pct
        self.use_limit_orders = use_limit_orders
        self.order_timeout = order_timeout
        self.min_confidence = min_confidence

        logger.info(
            f"OrderExecutor initialized: {sizing_method.value} sizing, "
            f"max {max_position_pct*100}% position, "
            f"min {min_confidence} confidence"
        )

    async def execute_signal(self, signal: TradingSignal) -> ExecutionResult:
        """
        Execute a trading signal.

        Flow:
        1. Validate signal
        2. Get account info
        3. Calculate position size
        4. Determine entry/stop/target prices
        5. Submit order
        6. Monitor for fill
        7. Return execution result

        Args:
            signal: Trading signal to execute

        Returns:
            ExecutionResult with order details
        """
        start_time = datetime.now()

        logger.info(
            f"Executing signal: {signal.action.value.upper()} {signal.ticker} "
            f"(confidence={signal.confidence:.2f}, score={signal.catalyst_score:.2f})"
        )

        # 1. Validate signal
        is_valid, reason = self._validate_signal(signal)
        if not is_valid:
            logger.warning(f"Signal rejected: {reason}")
            return ExecutionResult(
                success=False,
                signal=signal,
                order=None,
                position_size=0,
                entry_price=0,
                stop_loss=None,
                take_profit=None,
                error_message=reason,
                execution_time=0
            )

        # 2. Get account info
        try:
            account = self.broker.get_account()
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return ExecutionResult(
                success=False,
                signal=signal,
                order=None,
                position_size=0,
                entry_price=0,
                stop_loss=None,
                take_profit=None,
                error_message=f"Account query failed: {e}",
                execution_time=0
            )

        # 3. Calculate position size
        position_size = self._calculate_position_size(signal, account)

        if position_size == 0:
            logger.warning(f"Position size calculated as 0 for {signal.ticker}")
            return ExecutionResult(
                success=False,
                signal=signal,
                order=None,
                position_size=0,
                entry_price=0,
                stop_loss=None,
                take_profit=None,
                error_message="Position size is 0",
                execution_time=0
            )

        # 4. Calculate order parameters
        order_params = await self._calculate_order_params(signal, position_size)

        # 5. Submit order
        try:
            order = await self._submit_order(
                signal.ticker,
                position_size,
                signal.action.value,
                order_params
            )
        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            return ExecutionResult(
                success=False,
                signal=signal,
                order=None,
                position_size=position_size,
                entry_price=order_params.get('entry_price', 0),
                stop_loss=order_params.get('stop_loss'),
                take_profit=order_params.get('take_profit'),
                error_message=f"Order submission failed: {e}",
                execution_time=(datetime.now() - start_time).total_seconds()
            )

        # 6. Monitor for fill (with timeout)
        filled_order = await self._monitor_order_fill(order)

        if not filled_order:
            logger.warning(f"Order {order.order_id} not filled within timeout")
            # Try to cancel
            self.broker.cancel_order(order.order_id)
            return ExecutionResult(
                success=False,
                signal=signal,
                order=order,
                position_size=position_size,
                entry_price=order_params.get('entry_price', 0),
                stop_loss=order_params.get('stop_loss'),
                take_profit=order_params.get('take_profit'),
                error_message="Order not filled (timeout)",
                execution_time=(datetime.now() - start_time).total_seconds()
            )

        # 7. Success!
        execution_time = (datetime.now() - start_time).total_seconds()

        result = ExecutionResult(
            success=True,
            signal=signal,
            order=filled_order,
            position_size=position_size,
            entry_price=filled_order.filled_avg_price,
            stop_loss=order_params.get('stop_loss'),
            take_profit=order_params.get('take_profit'),
            error_message=None,
            execution_time=execution_time
        )

        logger.info(
            f"Order executed successfully: {filled_order.order_id} - "
            f"{signal.action.value.upper()} {position_size} {signal.ticker} "
            f"@ ${filled_order.filled_avg_price:.2f} "
            f"(execution time: {execution_time:.2f}s)"
        )

        return result

    def _validate_signal(self, signal: TradingSignal) -> Tuple[bool, str]:
        """
        Validate trading signal before execution.

        Checks:
        - Action is BUY or SELL (not HOLD)
        - Confidence meets minimum threshold
        - Ticker is valid

        Returns:
            (is_valid, reason_if_invalid)
        """
        # Must be actionable (not HOLD)
        if signal.action == SignalAction.HOLD:
            return False, "Signal action is HOLD"

        # Check confidence threshold
        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence:.2f} below minimum {self.min_confidence}"

        # Ticker must be set
        if not signal.ticker:
            return False, "No ticker specified"

        return True, "Valid"

    def _calculate_position_size(
        self,
        signal: TradingSignal,
        account: Account
    ) -> float:
        """
        Calculate position size in shares.

        Methods:
        1. FIXED_PERCENTAGE: Use default_position_pct of portfolio
        2. KELLY_CRITERION: Use Kelly formula (requires win rate data)
        3. VOLATILITY_ADJUSTED: Adjust based on stock's RVOL
        4. SIGNAL_CONFIDENCE: Scale by signal confidence

        Args:
            signal: Trading signal
            account: Account information

        Returns:
            Number of shares to trade
        """
        # Get current price
        try:
            current_price = get_current_price(signal.ticker)
        except Exception as e:
            logger.error(f"Failed to get price for {signal.ticker}: {e}")
            return 0

        if current_price <= 0:
            logger.error(f"Invalid price for {signal.ticker}: ${current_price}")
            return 0

        # Determine position size percentage
        if self.sizing_method == PositionSizingMethod.FIXED_PERCENTAGE:
            position_pct = signal.position_size_pct or self.default_position_pct

        elif self.sizing_method == PositionSizingMethod.SIGNAL_CONFIDENCE:
            # Scale by confidence: confidence * default_pct
            position_pct = signal.confidence * self.default_position_pct

        elif self.sizing_method == PositionSizingMethod.VOLATILITY_ADJUSTED:
            # Adjust for volatility (higher RVOL = smaller position)
            try:
                rvol = get_rvol(signal.ticker)
                # If RVOL is high (>2.0), reduce position size
                vol_adjustment = min(1.0, 2.0 / max(rvol, 0.5))
                position_pct = self.default_position_pct * vol_adjustment
            except Exception:
                position_pct = self.default_position_pct

        elif self.sizing_method == PositionSizingMethod.KELLY_CRITERION:
            # TODO: Implement Kelly Criterion (needs historical win rate)
            position_pct = self.default_position_pct

        else:
            position_pct = self.default_position_pct

        # Cap at maximum
        position_pct = min(position_pct, self.max_position_pct)

        # Calculate dollar amount
        dollar_amount = account.buying_power * position_pct

        # Convert to shares
        shares = int(dollar_amount / current_price)

        logger.info(
            f"Position size for {signal.ticker}: {shares} shares "
            f"({position_pct*100:.1f}% of portfolio, ${dollar_amount:.2f})"
        )

        return shares

    async def _calculate_order_params(
        self,
        signal: TradingSignal,
        position_size: float
    ) -> Dict:
        """
        Calculate order parameters (entry/stop/target prices).

        Uses existing trade_plan.py module for stop-loss and
        take-profit calculation based on ATR.

        Args:
            signal: Trading signal
            position_size: Number of shares

        Returns:
            Dict with entry_price, stop_loss, take_profit
        """
        # Get current market price
        current_price = get_current_price(signal.ticker)

        # Calculate entry price
        if self.use_limit_orders:
            # Place limit order slightly better than market
            if signal.action == SignalAction.BUY:
                entry_price = current_price * 1.001  # 0.1% above market
            else:
                entry_price = current_price * 0.999  # 0.1% below market
        else:
            # Market order
            entry_price = current_price

        # Calculate stop-loss and take-profit using existing trade_plan module
        try:
            trade_plan = calculate_trade_plan(
                ticker=signal.ticker,
                entry_price=entry_price,
                side='long' if signal.action == SignalAction.BUY else 'short'
            )

            stop_loss = trade_plan.get('stop_loss')
            take_profit = trade_plan.get('take_profit')

        except Exception as e:
            logger.warning(f"Failed to calculate trade plan for {signal.ticker}: {e}")
            # Fallback: simple percentage stops
            if signal.action == SignalAction.BUY:
                stop_loss = entry_price * 0.95  # 5% stop
                take_profit = entry_price * 1.10  # 10% target
            else:
                stop_loss = entry_price * 1.05
                take_profit = entry_price * 0.90

        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'order_type': 'limit' if self.use_limit_orders else 'market'
        }

    async def _submit_order(
        self,
        ticker: str,
        qty: float,
        side: str,
        order_params: Dict
    ) -> Order:
        """
        Submit order to broker.

        Args:
            ticker: Stock ticker
            qty: Number of shares
            side: 'buy' or 'sell'
            order_params: Dict with entry_price, order_type, etc.

        Returns:
            Order object
        """
        if order_params['order_type'] == 'market':
            order = self.broker.place_market_order(ticker, qty, side)
        else:
            order = self.broker.place_limit_order(
                ticker, qty, side, order_params['entry_price']
            )

        return order

    async def _monitor_order_fill(self, order: Order) -> Optional[Order]:
        """
        Monitor order until filled or timeout.

        Args:
            order: Order to monitor

        Returns:
            Filled order or None if timeout
        """
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < self.order_timeout:
            # Check order status
            updated_order = self.broker.get_order(order.order_id)

            if updated_order.status == 'filled':
                logger.info(f"Order {order.order_id} filled @ ${updated_order.filled_avg_price:.2f}")
                return updated_order

            elif updated_order.status in ['cancelled', 'expired', 'rejected']:
                logger.warning(f"Order {order.order_id} {updated_order.status}")
                return None

            # Wait before checking again
            await asyncio.sleep(1)

        # Timeout
        return None
```

**Acceptance Criteria:**
- [ ] Signals converted to orders correctly
- [ ] Position sizing calculated based on account balance
- [ ] Entry/stop/target prices calculated using existing trade_plan.py
- [ ] Orders submitted to broker without errors
- [ ] Order fills monitored until confirmed or timeout
- [ ] Execution results logged with timestamps
- [ ] Failed executions handled gracefully

**Tests Required:**
- Unit tests:
  - Test signal validation logic
  - Test position sizing calculations (all methods)
  - Test order parameter calculation
  - Mock broker to test execution flow
  - Test timeout handling
- Integration tests:
  - Execute paper trades end-to-end
  - Verify orders submitted correctly
  - Verify fill monitoring works

**Dependencies:** Task 1.1.2

---

### Story 1.3: Position Manager & Database Schema
**Priority:** P0
**Estimated Effort:** 3-4 days
**Dependencies:** Story 1.2

**Description:**
Create position tracking system with SQLite database for storing open and closed positions. Must track entry price, current P&L, stop-losses, and provide position lifecycle management. This module will be used by the risk manager and portfolio tracker.

**Tasks:**

- [ ] Task 1.3.1: Design position database schema
- [ ] Task 1.3.2: Implement PositionManager class
- [ ] Task 1.3.3: Add real-time P&L calculation
- [ ] Task 1.3.4: Implement stop-loss monitoring
- [ ] Task 1.3.5: Add position CRUD operations
- [ ] Task 1.3.6: Create database migration scripts

#### Task 1.3.1: Design Position Database Schema
**File:** `/home/user/catalyst-bot/src/catalyst_bot/portfolio/schema.sql`
**Estimated Effort:** 0.5 days

**Implementation:**
Design comprehensive database schema for tracking positions, trades, and portfolio state. Schema should support both open positions (active) and historical positions (closed), with full audit trail.

**Code Scaffold:**
```sql
-- Position tracking database schema
-- File: src/catalyst_bot/portfolio/schema.sql

-- Open positions table
CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    trailing_stop_price REAL,
    entry_order_id TEXT,
    opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    strategy TEXT,  -- Which strategy/RL agent opened this
    signal_confidence REAL,  -- Original signal confidence
    catalyst_score REAL,  -- Original catalyst score
    rvol REAL,  -- RVOL at entry
    atr REAL,  -- ATR at entry (for stop calculation)
    metadata JSON  -- Additional context (alert ID, etc.)
);

CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_opened_at ON positions(opened_at);
CREATE INDEX idx_positions_strategy ON positions(strategy);

-- Closed positions table (historical)
CREATE TABLE IF NOT EXISTS closed_positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    realized_pnl_pct REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    entry_order_id TEXT,
    exit_order_id TEXT,
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hold_duration_seconds INTEGER,  -- How long position was held
    exit_reason TEXT,  -- 'stop_loss', 'take_profit', 'manual', 'time_exit', 'signal'
    strategy TEXT,
    signal_confidence REAL,
    catalyst_score REAL,
    rvol REAL,
    atr REAL,
    max_unrealized_pnl REAL,  -- Peak unrealized P&L during hold
    max_unrealized_pnl_pct REAL,
    max_drawdown_pct REAL,  -- Max drawdown while open
    metadata JSON
);

CREATE INDEX idx_closed_positions_ticker ON closed_positions(ticker);
CREATE INDEX idx_closed_positions_closed_at ON closed_positions(closed_at);
CREATE INDEX idx_closed_positions_strategy ON closed_positions(strategy);
CREATE INDEX idx_closed_positions_exit_reason ON closed_positions(exit_reason);

-- Orders table (full order history)
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    broker_order_id TEXT UNIQUE,  -- Alpaca order ID
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    order_type TEXT NOT NULL CHECK(order_type IN ('market', 'limit', 'stop', 'bracket')),
    quantity REAL NOT NULL,
    limit_price REAL,
    stop_price REAL,
    filled_quantity REAL DEFAULT 0,
    filled_avg_price REAL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'submitted', 'filled', 'partial', 'cancelled', 'rejected')),
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    position_id TEXT,  -- Link to position
    strategy TEXT,
    metadata JSON,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE INDEX idx_orders_ticker ON orders(ticker);
CREATE INDEX idx_orders_broker_order_id ON orders(broker_order_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_submitted_at ON orders(submitted_at);
CREATE INDEX idx_orders_position_id ON orders(position_id);

-- Portfolio snapshots (daily)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL UNIQUE,
    portfolio_value REAL NOT NULL,
    cash_balance REAL NOT NULL,
    equity_value REAL NOT NULL,
    open_positions_count INTEGER NOT NULL DEFAULT 0,
    total_unrealized_pnl REAL NOT NULL DEFAULT 0,
    total_realized_pnl_today REAL NOT NULL DEFAULT 0,
    daily_return_pct REAL,
    cumulative_return_pct REAL,
    sharpe_ratio_30d REAL,  -- Rolling 30-day Sharpe
    max_drawdown_pct REAL,
    win_rate_30d REAL,  -- Win rate over last 30 days
    profit_factor_30d REAL,
    metadata JSON
);

CREATE INDEX idx_snapshots_date ON portfolio_snapshots(snapshot_date);

-- Trade execution log (detailed)
CREATE TABLE IF NOT EXISTS execution_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('buy', 'sell', 'hold')),
    signal_confidence REAL,
    catalyst_score REAL,
    order_id TEXT,
    position_id TEXT,
    execution_success INTEGER CHECK(execution_success IN (0, 1)),
    error_message TEXT,
    execution_time_seconds REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    position_size INTEGER,
    metadata JSON,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE INDEX idx_execution_log_timestamp ON execution_log(timestamp);
CREATE INDEX idx_execution_log_ticker ON execution_log(ticker);

-- Performance metrics (aggregated)
CREATE TABLE IF NOT EXISTS performance_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL CHECK(period IN ('daily', 'weekly', 'monthly', 'all_time')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    total_trades INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    win_rate REAL,
    avg_win REAL,
    avg_loss REAL,
    largest_win REAL,
    largest_loss REAL,
    total_pnl REAL,
    total_return_pct REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    max_drawdown_pct REAL,
    profit_factor REAL,  -- Gross profit / Gross loss
    expectancy REAL,  -- (Win% * AvgWin) - (Loss% * AvgLoss)
    avg_hold_time_hours REAL,
    best_ticker TEXT,
    worst_ticker TEXT,
    metadata JSON,
    UNIQUE(period, period_start, period_end)
);

CREATE INDEX idx_metrics_period ON performance_metrics(period);
CREATE INDEX idx_metrics_start ON performance_metrics(period_start);

-- Stop-loss events (for analysis)
CREATE TABLE IF NOT EXISTS stop_loss_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trigger_price REAL NOT NULL,
    stop_loss_price REAL NOT NULL,
    entry_price REAL NOT NULL,
    loss_amount REAL NOT NULL,
    loss_pct REAL NOT NULL,
    hold_duration_seconds INTEGER,
    triggered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    was_trailing INTEGER CHECK(was_trailing IN (0, 1)),
    metadata JSON,
    FOREIGN KEY (position_id) REFERENCES closed_positions(position_id)
);

CREATE INDEX idx_stop_events_ticker ON stop_loss_events(ticker);
CREATE INDEX idx_stop_events_triggered_at ON stop_loss_events(triggered_at);
```

**Acceptance Criteria:**
- [ ] Schema supports all position lifecycle states
- [ ] Indexes created for query performance
- [ ] Foreign key relationships maintained
- [ ] JSON metadata fields for flexibility
- [ ] Historical audit trail preserved
- [ ] Performance metrics aggregation supported

**Tests Required:**
- Schema validation:
  - All tables created successfully
  - Indexes created
  - Constraints enforced
  - Foreign keys work

**Dependencies:** None

#### Task 1.3.2: Implement PositionManager Class
**File:** `/home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py`
**Estimated Effort:** 2 days

**Implementation:**
Create position manager that tracks open positions, calculates real-time P&L, monitors stop-losses, and handles position lifecycle. Must sync with broker API and maintain accurate state in database.

**Code Scaffold:**
```python
"""
Position manager for tracking and managing open positions.
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import sqlite3
import json
import logging

from catalyst_bot.broker.alpaca_client import AlpacaBrokerClient, Position as BrokerPosition
from catalyst_bot.market import get_current_price
from catalyst_bot.execution.order_executor import ExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """
    Internal position representation.
    """
    position_id: str
    ticker: str
    side: str  # 'long' or 'short'
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    entry_order_id: Optional[str] = None
    opened_at: datetime = None
    updated_at: datetime = None
    strategy: Optional[str] = None
    signal_confidence: Optional[float] = None
    catalyst_score: Optional[float] = None
    rvol: Optional[float] = None
    atr: Optional[float] = None
    metadata: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for database storage."""
        d = asdict(self)
        d['opened_at'] = self.opened_at.isoformat() if self.opened_at else None
        d['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        d['metadata'] = json.dumps(self.metadata) if self.metadata else None
        return d


@dataclass
class ClosedPosition:
    """Closed position with exit details."""
    position_id: str
    ticker: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    realized_pnl_pct: float
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    entry_order_id: Optional[str]
    exit_order_id: Optional[str]
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int
    exit_reason: str
    strategy: Optional[str] = None
    signal_confidence: Optional[float] = None
    catalyst_score: Optional[float] = None
    rvol: Optional[float] = None
    atr: Optional[float] = None
    max_unrealized_pnl: Optional[float] = None
    max_unrealized_pnl_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    metadata: Optional[Dict] = None


class PositionManager:
    """
    Manage position lifecycle and tracking.

    Responsibilities:
    1. Create positions from filled orders
    2. Track real-time P&L for open positions
    3. Monitor stop-loss and take-profit triggers
    4. Close positions and record history
    5. Sync with broker positions
    6. Calculate portfolio exposure

    Usage:
        pm = PositionManager(
            db_path='data/positions.db',
            broker_client=alpaca_client
        )

        # Open position from execution result
        position = pm.open_position(execution_result)

        # Update all positions with current prices
        pm.update_positions()

        # Check for stop-loss hits
        triggered = pm.check_stop_losses()

        # Close position
        pm.close_position(position_id, exit_price, 'manual')
    """

    def __init__(
        self,
        db_path: str,
        broker_client: AlpacaBrokerClient,
        enable_trailing_stops: bool = True,
        trailing_stop_activation_pct: float = 0.05,  # Activate after 5% profit
        trailing_stop_distance_pct: float = 0.03  # Trail 3% below peak
    ):
        """
        Initialize position manager.

        Args:
            db_path: Path to SQLite database
            broker_client: Alpaca broker client
            enable_trailing_stops: Enable trailing stop logic
            trailing_stop_activation_pct: Profit % to activate trailing stop
            trailing_stop_distance_pct: Distance to trail below peak
        """
        self.db_path = db_path
        self.broker = broker_client
        self.enable_trailing_stops = enable_trailing_stops
        self.trailing_activation = trailing_stop_activation_pct
        self.trailing_distance = trailing_stop_distance_pct

        # Initialize database
        self._init_database()

        # Cache of open positions
        self._positions_cache: Dict[str, Position] = {}
        self._load_positions_cache()

        logger.info(f"PositionManager initialized with {len(self._positions_cache)} open positions")

    def _init_database(self):
        """Initialize database with schema."""
        # Read and execute schema.sql
        schema_path = 'src/catalyst_bot/portfolio/schema.sql'
        try:
            with open(schema_path) as f:
                schema_sql = f.read()

            conn = sqlite3.connect(self.db_path)
            conn.executescript(schema_sql)
            conn.commit()
            conn.close()

            logger.info(f"Database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _load_positions_cache(self):
        """Load open positions from database into cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM positions")
        rows = cursor.fetchall()

        for row in rows:
            position = self._row_to_position(row, cursor.description)
            self._positions_cache[position.position_id] = position

        conn.close()

        logger.debug(f"Loaded {len(self._positions_cache)} positions into cache")

    def open_position(self, execution_result: ExecutionResult) -> Position:
        """
        Create new position from execution result.

        Args:
            execution_result: Result from OrderExecutor

        Returns:
            Position object
        """
        if not execution_result.success:
            raise ValueError("Cannot open position from failed execution")

        # Generate position ID
        position_id = f"{execution_result.order.order_id}_{datetime.now().timestamp()}"

        signal = execution_result.signal

        # Create position
        position = Position(
            position_id=position_id,
            ticker=signal.ticker,
            side='long' if signal.action.value == 'buy' else 'short',
            quantity=execution_result.position_size,
            entry_price=execution_result.entry_price,
            current_price=execution_result.entry_price,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            stop_loss_price=execution_result.stop_loss,
            take_profit_price=execution_result.take_profit,
            entry_order_id=execution_result.order.order_id,
            opened_at=execution_result.timestamp,
            updated_at=execution_result.timestamp,
            strategy=signal.metadata.get('strategy') if signal.metadata else None,
            signal_confidence=signal.confidence,
            catalyst_score=signal.catalyst_score,
            metadata=signal.metadata
        )

        # Save to database
        self._save_position(position)

        # Add to cache
        self._positions_cache[position_id] = position

        logger.info(
            f"Position opened: {position_id} - "
            f"{position.side.upper()} {position.quantity} {position.ticker} "
            f"@ ${position.entry_price:.2f}"
        )

        return position

    def update_positions(self, price_data: Optional[Dict[str, float]] = None):
        """
        Update all open positions with current prices and P&L.

        Args:
            price_data: Optional dict of {ticker: price}. If None, fetches from market.
        """
        if not self._positions_cache:
            return

        logger.debug(f"Updating {len(self._positions_cache)} positions")

        for position in self._positions_cache.values():
            try:
                # Get current price
                if price_data and position.ticker in price_data:
                    current_price = price_data[position.ticker]
                else:
                    current_price = get_current_price(position.ticker)

                # Calculate P&L
                if position.side == 'long':
                    unrealized_pnl = (current_price - position.entry_price) * position.quantity
                else:  # short
                    unrealized_pnl = (position.entry_price - current_price) * position.quantity

                unrealized_pnl_pct = (unrealized_pnl / (position.entry_price * position.quantity)) * 100

                # Update position
                position.current_price = current_price
                position.unrealized_pnl = unrealized_pnl
                position.unrealized_pnl_pct = unrealized_pnl_pct
                position.updated_at = datetime.now()

                # Update trailing stop if enabled and activated
                if self.enable_trailing_stops:
                    self._update_trailing_stop(position)

                # Save updated position
                self._update_position_in_db(position)

            except Exception as e:
                logger.error(f"Failed to update position {position.position_id}: {e}")

    def _update_trailing_stop(self, position: Position):
        """Update trailing stop price if profit threshold reached."""
        if position.unrealized_pnl_pct < self.trailing_activation * 100:
            return  # Not profitable enough yet

        # Calculate trailing stop
        if position.side == 'long':
            new_trailing_stop = position.current_price * (1 - self.trailing_distance)
            # Only move stop up, never down
            if position.trailing_stop_price is None or new_trailing_stop > position.trailing_stop_price:
                position.trailing_stop_price = new_trailing_stop
                logger.info(
                    f"Trailing stop updated for {position.ticker}: ${new_trailing_stop:.2f} "
                    f"(profit: {position.unrealized_pnl_pct:.2f}%)"
                )
        else:  # short
            new_trailing_stop = position.current_price * (1 + self.trailing_distance)
            if position.trailing_stop_price is None or new_trailing_stop < position.trailing_stop_price:
                position.trailing_stop_price = new_trailing_stop
                logger.info(
                    f"Trailing stop updated for {position.ticker}: ${new_trailing_stop:.2f}"
                )

    def check_stop_losses(self) -> List[Position]:
        """
        Check all positions for stop-loss triggers.

        Returns:
            List of positions that hit stop-loss
        """
        triggered = []

        for position in self._positions_cache.values():
            # Check fixed stop-loss
            if position.stop_loss_price:
                if position.side == 'long' and position.current_price <= position.stop_loss_price:
                    triggered.append(position)
                    logger.warning(
                        f"Stop-loss triggered for {position.ticker}: "
                        f"${position.current_price:.2f} <= ${position.stop_loss_price:.2f}"
                    )
                elif position.side == 'short' and position.current_price >= position.stop_loss_price:
                    triggered.append(position)
                    logger.warning(f"Stop-loss triggered for {position.ticker} (short)")

            # Check trailing stop
            if position.trailing_stop_price:
                if position.side == 'long' and position.current_price <= position.trailing_stop_price:
                    triggered.append(position)
                    logger.warning(
                        f"Trailing stop triggered for {position.ticker}: "
                        f"${position.current_price:.2f} <= ${position.trailing_stop_price:.2f}"
                    )
                elif position.side == 'short' and position.current_price >= position.trailing_stop_price:
                    triggered.append(position)

        return triggered

    def check_take_profits(self) -> List[Position]:
        """
        Check all positions for take-profit triggers.

        Returns:
            List of positions that hit take-profit
        """
        triggered = []

        for position in self._positions_cache.values():
            if not position.take_profit_price:
                continue

            if position.side == 'long' and position.current_price >= position.take_profit_price:
                triggered.append(position)
                logger.info(
                    f"Take-profit triggered for {position.ticker}: "
                    f"${position.current_price:.2f} >= ${position.take_profit_price:.2f}"
                )
            elif position.side == 'short' and position.current_price <= position.take_profit_price:
                triggered.append(position)
                logger.info(f"Take-profit triggered for {position.ticker} (short)")

        return triggered

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: str,
        exit_order_id: Optional[str] = None
    ) -> ClosedPosition:
        """
        Close a position and record to history.

        Args:
            position_id: Position to close
            exit_price: Exit price
            exit_reason: Reason for exit ('stop_loss', 'take_profit', 'manual', etc.)
            exit_order_id: Exit order ID

        Returns:
            ClosedPosition object
        """
        if position_id not in self._positions_cache:
            raise ValueError(f"Position not found: {position_id}")

        position = self._positions_cache[position_id]

        # Calculate realized P&L
        if position.side == 'long':
            realized_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            realized_pnl = (position.entry_price - exit_price) * position.quantity

        realized_pnl_pct = (realized_pnl / (position.entry_price * position.quantity)) * 100

        # Calculate hold duration
        hold_duration = (datetime.now() - position.opened_at).total_seconds()

        # Create closed position
        closed = ClosedPosition(
            position_id=position_id,
            ticker=position.ticker,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            stop_loss_price=position.stop_loss_price,
            take_profit_price=position.take_profit_price,
            entry_order_id=position.entry_order_id,
            exit_order_id=exit_order_id,
            opened_at=position.opened_at,
            closed_at=datetime.now(),
            hold_duration_seconds=int(hold_duration),
            exit_reason=exit_reason,
            strategy=position.strategy,
            signal_confidence=position.signal_confidence,
            catalyst_score=position.catalyst_score,
            rvol=position.rvol,
            atr=position.atr,
            max_unrealized_pnl=position.unrealized_pnl,  # Current is max at close
            max_unrealized_pnl_pct=position.unrealized_pnl_pct,
            metadata=position.metadata
        )

        # Save to closed_positions table
        self._save_closed_position(closed)

        # Remove from open positions
        self._delete_position_from_db(position_id)
        del self._positions_cache[position_id]

        logger.info(
            f"Position closed: {position_id} - "
            f"{position.ticker} @ ${exit_price:.2f} - "
            f"P&L: ${realized_pnl:.2f} ({realized_pnl_pct:.2f}%) - "
            f"Reason: {exit_reason}"
        )

        return closed

    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID."""
        return self._positions_cache.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """Get all open positions."""
        return list(self._positions_cache.values())

    def get_positions_by_ticker(self, ticker: str) -> List[Position]:
        """Get all positions for a ticker."""
        return [p for p in self._positions_cache.values() if p.ticker == ticker]

    def get_total_exposure(self) -> float:
        """
        Calculate total portfolio exposure (sum of position values).

        Returns:
            Total exposure in dollars
        """
        return sum(
            abs(p.current_price * p.quantity)
            for p in self._positions_cache.values()
        )

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self._positions_cache.values())

    def sync_with_broker(self):
        """
        Sync positions with broker (reconciliation).

        Compares local positions with broker positions and logs discrepancies.
        """
        try:
            broker_positions = self.broker.get_positions()
            broker_tickers = {p.symbol: p for p in broker_positions}
            local_tickers = {p.ticker: p for p in self._positions_cache.values()}

            # Check for missing positions
            for ticker in local_tickers:
                if ticker not in broker_tickers:
                    logger.warning(f"Position {ticker} in local but not in broker")

            for ticker in broker_tickers:
                if ticker not in local_tickers:
                    logger.warning(f"Position {ticker} in broker but not in local")

            # Check for quantity mismatches
            for ticker in set(local_tickers) & set(broker_tickers):
                local_qty = local_tickers[ticker].quantity
                broker_qty = abs(broker_positions[ticker].qty)

                if abs(local_qty - broker_qty) > 0.01:
                    logger.warning(
                        f"Quantity mismatch for {ticker}: "
                        f"local={local_qty}, broker={broker_qty}"
                    )

        except Exception as e:
            logger.error(f"Failed to sync with broker: {e}")

    def _save_position(self, position: Position):
        """Save position to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO positions (
                position_id, ticker, side, quantity, entry_price, current_price,
                unrealized_pnl, unrealized_pnl_pct, stop_loss_price, take_profit_price,
                trailing_stop_price, entry_order_id, opened_at, updated_at,
                strategy, signal_confidence, catalyst_score, rvol, atr, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            position.position_id, position.ticker, position.side, position.quantity,
            position.entry_price, position.current_price, position.unrealized_pnl,
            position.unrealized_pnl_pct, position.stop_loss_price, position.take_profit_price,
            position.trailing_stop_price, position.entry_order_id,
            position.opened_at.isoformat() if position.opened_at else None,
            position.updated_at.isoformat() if position.updated_at else None,
            position.strategy, position.signal_confidence, position.catalyst_score,
            position.rvol, position.atr,
            json.dumps(position.metadata) if position.metadata else None
        ))

        conn.commit()
        conn.close()

    def _update_position_in_db(self, position: Position):
        """Update position in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE positions SET
                current_price = ?,
                unrealized_pnl = ?,
                unrealized_pnl_pct = ?,
                trailing_stop_price = ?,
                updated_at = ?
            WHERE position_id = ?
        """, (
            position.current_price,
            position.unrealized_pnl,
            position.unrealized_pnl_pct,
            position.trailing_stop_price,
            position.updated_at.isoformat() if position.updated_at else None,
            position.position_id
        ))

        conn.commit()
        conn.close()

    def _delete_position_from_db(self, position_id: str):
        """Delete position from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM positions WHERE position_id = ?", (position_id,))
        conn.commit()
        conn.close()

    def _save_closed_position(self, closed: ClosedPosition):
        """Save closed position to history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO closed_positions (
                position_id, ticker, side, quantity, entry_price, exit_price,
                realized_pnl, realized_pnl_pct, stop_loss_price, take_profit_price,
                entry_order_id, exit_order_id, opened_at, closed_at,
                hold_duration_seconds, exit_reason, strategy, signal_confidence,
                catalyst_score, rvol, atr, max_unrealized_pnl, max_unrealized_pnl_pct,
                max_drawdown_pct, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            closed.position_id, closed.ticker, closed.side, closed.quantity,
            closed.entry_price, closed.exit_price, closed.realized_pnl,
            closed.realized_pnl_pct, closed.stop_loss_price, closed.take_profit_price,
            closed.entry_order_id, closed.exit_order_id,
            closed.opened_at.isoformat() if closed.opened_at else None,
            closed.closed_at.isoformat() if closed.closed_at else None,
            closed.hold_duration_seconds, closed.exit_reason, closed.strategy,
            closed.signal_confidence, closed.catalyst_score, closed.rvol, closed.atr,
            closed.max_unrealized_pnl, closed.max_unrealized_pnl_pct,
            closed.max_drawdown_pct,
            json.dumps(closed.metadata) if closed.metadata else None
        ))

        conn.commit()
        conn.close()

    def _row_to_position(self, row, description) -> Position:
        """Convert database row to Position object."""
        # TODO: Implement row parsing
        pass
```

**Acceptance Criteria:**
- [ ] Positions created from execution results
- [ ] Real-time P&L calculated accurately
- [ ] Stop-loss monitoring detects triggers
- [ ] Take-profit monitoring works
- [ ] Trailing stops update correctly
- [ ] Positions closed and saved to history
- [ ] Database operations atomic and reliable
- [ ] Sync with broker detects discrepancies

**Tests Required:**
- Unit tests:
  - Test position creation
  - Test P&L calculation (long and short)
  - Test stop-loss detection
  - Test trailing stop updates
  - Test position closing
- Integration tests:
  - Full position lifecycle (open → update → close)
  - Database persistence
  - Broker sync

**Dependencies:** Task 1.1.2, Task 1.2.1

---

### Story 1.4: Portfolio Tracker & Performance Analytics
**Priority:** P0
**Estimated Effort:** 2-3 days
**Dependencies:** Story 1.3

**Description:**
Build portfolio tracker that calculates real-time portfolio value, daily/cumulative P&L, and performance metrics (Sharpe ratio, max drawdown, win rate, etc.). This provides visibility into overall trading performance and feeds into risk management decisions.

**Tasks:**

- [ ] Task 1.4.1: Implement PortfolioTracker class
- [ ] Task 1.4.2: Add performance metrics calculation
- [ ] Task 1.4.3: Create daily snapshot system
- [ ] Task 1.4.4: Build performance analytics queries
- [ ] Task 1.4.5: Add trade log export functionality

---

### Story 1.5: Integration with Existing Alert System
**Priority:** P0
**Estimated Effort:** 2-3 days
**Dependencies:** Stories 1.1-1.4

**Description:**
Connect the new trading infrastructure to the existing catalyst alert system. Create signal router that converts catalyst alerts into trading signals, applies confidence filtering, and routes to execution engine. Must preserve existing alert functionality while adding trading capability.

**Tasks:**

- [ ] Task 1.5.1: Create SignalRouter class
- [ ] Task 1.5.2: Implement alert-to-signal conversion
- [ ] Task 1.5.3: Add confidence threshold filtering
- [ ] Task 1.5.4: Integrate with existing alerts.py module
- [ ] Task 1.5.5: Add paper trading mode toggle
- [ ] Task 1.5.6: End-to-end integration tests

---

# Epic 2: Risk Management & Safety Systems

## Epic 2: Risk Management & Safety Systems
**Priority:** P0 (Critical Path)
**Estimated Effort:** 4 weeks
**Dependencies:** Epic 1

### Overview
Implement comprehensive three-tiered risk management system to prevent catastrophic losses and ensure safe trading operations. This includes position-level, portfolio-level, and system-level controls with circuit breakers, kill switches, and emergency protocols.

### Stories
- Story 2.1: Position-Level Risk Controls
- Story 2.2: Portfolio-Level Risk Manager
- Story 2.3: Circuit Breakers & Kill Switch
- Story 2.4: Position Sizing Algorithms (Kelly Criterion)
- Story 2.5: Risk Monitoring & Alerting

---

### Story 2.1: Position-Level Risk Controls
**Priority:** P0
**Estimated Effort:** 3-4 days
**Dependencies:** Epic 1

**Description:**
Implement position-level risk controls that validate each trade before execution. This includes position size limits, stop-loss requirements, price reasonableness checks, and validation of entry parameters. These controls are the first line of defense against bad trades.

**Tasks:**

- [ ] Task 2.1.1: Create PositionRiskManager class
- [ ] Task 2.1.2: Implement position size validation
- [ ] Task 2.1.3: Add stop-loss requirement enforcement
- [ ] Task 2.1.4: Implement price reasonableness checks
- [ ] Task 2.1.5: Add trade validation rules
- [ ] Task 2.1.6: Create comprehensive unit tests

#### Task 2.1.1: Create PositionRiskManager Class
**File:** `/home/user/catalyst-bot/src/catalyst_bot/risk/position_risk.py`
**Estimated Effort:** 2 days

**Implementation:**
Create position-level risk manager that validates trades before execution. Must check position size limits, stop-loss presence, price validity, and other position-specific constraints.

**Code Scaffold:**
```python
"""
Position-level risk management.
"""
from typing import Tuple, Optional
from dataclasses import dataclass
import logging

from catalyst_bot.execution.order_executor import TradingSignal, SignalAction
from catalyst_bot.broker.alpaca_client import Account
from catalyst_bot.market import get_current_price, get_day_range

logger = logging.getLogger(__name__)


@dataclass
class PositionRiskParams:
    """Position-level risk parameters."""
    max_position_pct: float = 0.10  # 10% max per position
    min_position_value: float = 100.0  # Minimum $100 per trade
    require_stop_loss: bool = True
    max_price_deviation_pct: float = 0.05  # 5% from current price
    min_stop_loss_pct: float = 0.02  # Minimum 2% stop distance
    max_stop_loss_pct: float = 0.20  # Maximum 20% stop distance


class PositionRiskManager:
    """
    Position-level risk controls.

    Validates:
    1. Position size within limits
    2. Stop-loss is set and reasonable
    3. Entry price is reasonable
    4. Account has sufficient balance
    5. Trade meets minimum size requirements

    Usage:
        risk_mgr = PositionRiskManager(params=PositionRiskParams())

        allowed, reason = risk_mgr.validate_trade(signal, account, position_size)
        if not allowed:
            logger.warning(f"Trade rejected: {reason}")
    """

    def __init__(self, params: Optional[PositionRiskParams] = None):
        """
        Initialize position risk manager.

        Args:
            params: Risk parameters (uses defaults if None)
        """
        self.params = params or PositionRiskParams()
        logger.info(f"PositionRiskManager initialized with params: {self.params}")

    def validate_trade(
        self,
        signal: TradingSignal,
        account: Account,
        position_size: float,
        entry_price: float
    ) -> Tuple[bool, str]:
        """
        Validate trade against position-level rules.

        Args:
            signal: Trading signal
            account: Account information
            position_size: Proposed position size (shares)
            entry_price: Proposed entry price

        Returns:
            (approved, reason_if_rejected)
        """
        # 1. Check position size limits
        allowed, reason = self._check_position_size(
            signal.ticker, position_size, entry_price, account
        )
        if not allowed:
            return False, reason

        # 2. Check stop-loss presence and validity
        if self.params.require_stop_loss:
            allowed, reason = self._check_stop_loss(signal, entry_price)
            if not allowed:
                return False, reason

        # 3. Check entry price reasonableness
        allowed, reason = self._check_entry_price(signal.ticker, entry_price)
        if not allowed:
            return False, reason

        # 4. Check account balance
        allowed, reason = self._check_account_balance(
            position_size, entry_price, account
        )
        if not allowed:
            return False, reason

        # 5. Check minimum position value
        position_value = position_size * entry_price
        if position_value < self.params.min_position_value:
            return False, f"Position value ${position_value:.2f} below minimum ${self.params.min_position_value:.2f}"

        return True, "Approved"

    def _check_position_size(
        self,
        ticker: str,
        position_size: float,
        entry_price: float,
        account: Account
    ) -> Tuple[bool, str]:
        """
        Validate position size against limits.

        Checks:
        - Position value doesn't exceed max_position_pct of portfolio
        - Position size is positive
        """
        if position_size <= 0:
            return False, "Position size must be positive"

        position_value = position_size * entry_price
        max_position_value = account.portfolio_value * self.params.max_position_pct

        if position_value > max_position_value:
            return False, (
                f"Position value ${position_value:.2f} exceeds maximum "
                f"${max_position_value:.2f} ({self.params.max_position_pct*100:.1f}% of portfolio)"
            )

        return True, "Position size OK"

    def _check_stop_loss(
        self,
        signal: TradingSignal,
        entry_price: float
    ) -> Tuple[bool, str]:
        """
        Validate stop-loss is set and reasonable.

        Checks:
        - Stop-loss is present
        - Stop-loss distance is between min and max thresholds
        - Stop-loss direction is correct (below entry for longs, above for shorts)
        """
        if signal.stop_loss is None:
            return False, "Stop-loss required but not set"

        # Calculate stop distance
        if signal.action == SignalAction.BUY:
            # Long position - stop should be below entry
            if signal.stop_loss >= entry_price:
                return False, f"Stop-loss ${signal.stop_loss:.2f} must be below entry ${entry_price:.2f} for long"

            stop_distance_pct = (entry_price - signal.stop_loss) / entry_price

        else:  # SELL (short)
            # Short position - stop should be above entry
            if signal.stop_loss <= entry_price:
                return False, f"Stop-loss ${signal.stop_loss:.2f} must be above entry ${entry_price:.2f} for short"

            stop_distance_pct = (signal.stop_loss - entry_price) / entry_price

        # Check stop distance is reasonable
        if stop_distance_pct < self.params.min_stop_loss_pct:
            return False, (
                f"Stop-loss too tight: {stop_distance_pct*100:.1f}% "
                f"(min {self.params.min_stop_loss_pct*100:.1f}%)"
            )

        if stop_distance_pct > self.params.max_stop_loss_pct:
            return False, (
                f"Stop-loss too wide: {stop_distance_pct*100:.1f}% "
                f"(max {self.params.max_stop_loss_pct*100:.1f}%)"
            )

        return True, "Stop-loss OK"

    def _check_entry_price(
        self,
        ticker: str,
        entry_price: float
    ) -> Tuple[bool, str]:
        """
        Validate entry price is reasonable compared to current market.

        Checks:
        - Entry price is positive
        - Entry price is within max_price_deviation_pct of current price
        - Entry price is within today's trading range
        """
        if entry_price <= 0:
            return False, "Entry price must be positive"

        try:
            current_price = get_current_price(ticker)
        except Exception as e:
            logger.error(f"Failed to get current price for {ticker}: {e}")
            return False, f"Cannot validate entry price: {e}"

        # Check deviation from current price
        deviation_pct = abs(entry_price - current_price) / current_price

        if deviation_pct > self.params.max_price_deviation_pct:
            return False, (
                f"Entry price ${entry_price:.2f} deviates {deviation_pct*100:.1f}% "
                f"from current ${current_price:.2f} "
                f"(max {self.params.max_price_deviation_pct*100:.1f}%)"
            )

        # Check if within day's range (if available)
        try:
            day_low, day_high = get_day_range(ticker)
            if not (day_low <= entry_price <= day_high):
                logger.warning(
                    f"Entry price ${entry_price:.2f} outside day range "
                    f"${day_low:.2f}-${day_high:.2f}"
                )
                # Warning only, not rejection
        except Exception:
            pass  # Day range not available

        return True, "Entry price OK"

    def _check_account_balance(
        self,
        position_size: float,
        entry_price: float,
        account: Account
    ) -> Tuple[bool, str]:
        """
        Validate account has sufficient balance.

        Checks:
        - Buying power sufficient for position
        - Includes buffer for commissions/fees
        """
        position_value = position_size * entry_price

        # Add 0.1% buffer for commissions
        required_cash = position_value * 1.001

        if required_cash > account.buying_power:
            return False, (
                f"Insufficient buying power: ${account.buying_power:.2f} "
                f"< ${required_cash:.2f} required"
            )

        return True, "Account balance OK"
```

**Acceptance Criteria:**
- [ ] Position size validated against max percentage
- [ ] Stop-loss presence enforced
- [ ] Stop-loss distance checked (min/max)
- [ ] Entry price reasonableness validated
- [ ] Account balance checked
- [ ] Minimum position value enforced
- [ ] All validations logged
- [ ] Rejection reasons are clear and actionable

**Tests Required:**
- Unit tests:
  - Test position size validation (pass and fail cases)
  - Test stop-loss validation (missing, too tight, too wide, wrong direction)
  - Test entry price validation (too far from market)
  - Test account balance checks
  - Test minimum position value
- Integration tests:
  - Validate with real signal data
  - Test edge cases

**Dependencies:** Epic 1

---

### Story 2.2: Portfolio-Level Risk Manager
**Priority:** P0
**Estimated Effort:** 4-5 days
**Dependencies:** Story 2.1

**Description:**
Implement portfolio-level risk management that monitors overall exposure, daily losses, drawdowns, and position correlation. This is the second tier of defense and can halt trading when portfolio-level limits are exceeded.

**Tasks:**

- [ ] Task 2.2.1: Create PortfolioRiskManager class
- [ ] Task 2.2.2: Implement total exposure monitoring
- [ ] Task 2.2.3: Add daily loss tracking and limits
- [ ] Task 2.2.4: Implement max drawdown monitoring
- [ ] Task 2.2.5: Add position correlation checks
- [ ] Task 2.2.6: Create risk status dashboard

---

### Story 2.3: Circuit Breakers & Kill Switch
**Priority:** P0
**Estimated Effort:** 3-4 days
**Dependencies:** Story 2.2

**Description:**
Implement emergency stop mechanisms including circuit breakers (automatic trading halt on adverse conditions) and kill switch (immediate shutdown). Must include Discord/email notifications and require manual approval to resume trading.

**Tasks:**

- [ ] Task 2.3.1: Implement circuit breaker logic
- [ ] Task 2.3.2: Create kill switch mechanism
- [ ] Task 2.3.3: Add emergency position closing
- [ ] Task 2.3.4: Implement notification system
- [ ] Task 2.3.5: Create manual override controls
- [ ] Task 2.3.6: Add circuit breaker recovery procedures

---

### Story 2.4: Position Sizing Algorithms
**Priority:** P1
**Estimated Effort:** 2-3 days
**Dependencies:** Story 2.1

**Description:**
Implement sophisticated position sizing algorithms including Kelly Criterion (fractional), volatility-adjusted sizing, and confidence-based sizing. These algorithms dynamically adjust position sizes based on strategy performance and market conditions.

**Tasks:**

- [ ] Task 2.4.1: Implement Kelly Criterion calculator
- [ ] Task 2.4.2: Add win rate tracking for Kelly input
- [ ] Task 2.4.3: Implement volatility-adjusted sizing
- [ ] Task 2.4.4: Add confidence-based sizing
- [ ] Task 2.4.5: Create position sizing backtester
- [ ] Task 2.4.6: Add position sizing analytics

---

### Story 2.5: Risk Monitoring & Alerting
**Priority:** P1
**Estimated Effort:** 2-3 days
**Dependencies:** Stories 2.1-2.3

**Description:**
Build comprehensive risk monitoring dashboard and alerting system. Tracks all risk metrics in real-time, generates alerts when thresholds are approached, and logs all risk decisions for audit trail.

**Tasks:**

- [ ] Task 2.5.1: Create RiskMonitor class
- [ ] Task 2.5.2: Implement real-time metrics tracking
- [ ] Task 2.5.3: Add alert threshold system
- [ ] Task 2.5.4: Create risk event logging
- [ ] Task 2.5.5: Build risk dashboard (Streamlit)
- [ ] Task 2.5.6: Add risk report generation

---

# Epic 3: RL Training Infrastructure

## Epic 3: RL Training Infrastructure
**Priority:** P1 (High Priority)
**Estimated Effort:** 6 weeks
**Dependencies:** Epics 1 & 2

### Overview
Build reinforcement learning training infrastructure using Stable-Baselines3 and FinRL. Create custom Gym environment with Catalyst Bot features, train multiple RL agents (PPO, SAC, A2C), and validate through walk-forward testing. This epic enables automated strategy learning and optimization.

### Stories
- Story 3.1: RL Environment Design (Gym Compatible)
- Story 3.2: Historical Data Pipeline for RL
- Story 3.3: Agent Training Infrastructure
- Story 3.4: Walk-Forward Validation System
- Story 3.5: RL Agent Deployment & Integration

---

### Story 3.1: RL Environment Design
**Priority:** P1
**Estimated Effort:** 5-6 days
**Dependencies:** Epics 1 & 2

**Description:**
Design and implement custom Gym-compatible environment for training RL agents. Environment must include market state (OHLCV, indicators), account state (balance, positions), catalyst features (score, sentiment), and reward function based on Sharpe ratio. Must integrate with existing indicator calculations and respect transaction costs.

**Tasks:**

- [ ] Task 3.1.1: Design state space (33+ features)
- [ ] Task 3.1.2: Design action space (continuous position sizing)
- [ ] Task 3.1.3: Implement reward function (Sharpe-based)
- [ ] Task 3.1.4: Create CatalystTradingEnv class
- [ ] Task 3.1.5: Add transaction cost modeling
- [ ] Task 3.1.6: Integrate with existing indicators (RVOL, VWAP, ATR)
- [ ] Task 3.1.7: Test environment with random agent

#### Task 3.1.4: Create CatalystTradingEnv Class
**File:** `/home/user/catalyst-bot/src/catalyst_bot/ml/trading_env.py`
**Estimated Effort:** 3 days

**Implementation:**
Create custom Gym environment that simulates trading with Catalyst Bot features. Environment should support both training (historical data) and live inference. Must calculate realistic rewards and handle transaction costs.

**Code Scaffold:**
```python
"""
Custom Gym environment for RL trading agent training.
"""
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
import logging

from catalyst_bot.rvol import calculate_rvol
from catalyst_bot.vwap_calculator import calculate_vwap
from catalyst_bot.indicator_utils import calculate_atr, calculate_rsi, calculate_macd

logger = logging.getLogger(__name__)


class CatalystTradingEnv(gym.Env):
    """
    Custom Gym environment for training RL trading agents.

    State Space (33 features):
    - Account state (3): cash_balance, shares_held, portfolio_value
    - Price data (4): close, high, low, volume
    - Technical indicators (8): RVOL, RSI, MACD, MACD_signal, VWAP, ATR, SMA_20, EMA_50
    - Catalyst features (8): catalyst_score, sentiment, is_earnings, is_merger,
                              is_fda, is_offering, is_insider, news_velocity
    - Historical returns (10): return_1d, return_5d, return_10d, return_20d, volatility_20d,
                                max_drawdown_20d, sharpe_20d, beta, volume_trend, price_momentum

    Action Space (continuous):
    - Single value in [-1, 1]
    - -1 = sell all / short max
    - 0 = hold
    - +1 = buy max / close short

    Reward:
    - Sharpe ratio based (risk-adjusted returns)
    - Penalize transaction costs
    - Bonus for maintaining position (reduce churning)

    Usage:
        # Create environment
        env = CatalystTradingEnv(df=historical_data, initial_balance=100000)

        # Train agent
        from stable_baselines3 import PPO
        model = PPO("MlpPolicy", env, verbose=1)
        model.learn(total_timesteps=200000)

        # Evaluate
        obs, info = env.reset()
        for _ in range(1000):
            action, _ = model.predict(obs)
            obs, reward, done, truncated, info = env.step(action)
    """

    metadata = {'render_modes': ['human']}

    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 100000.0,
        commission_pct: float = 0.001,  # 0.1% per trade
        slippage_pct: float = 0.0005,  # 0.05% slippage
        lookback_window: int = 20,
        reward_scaling: float = 100.0
    ):
        """
        Initialize trading environment.

        Args:
            df: Historical data with columns: date, ticker, open, high, low, close, volume,
                catalyst_score, sentiment, and indicator columns
            initial_balance: Starting cash balance
            commission_pct: Commission as percentage of trade value
            slippage_pct: Slippage as percentage of price
            lookback_window: Number of periods for reward calculation
            reward_scaling: Scale rewards for better learning
        """
        super().__init__()

        self.df = df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.lookback_window = lookback_window
        self.reward_scaling = reward_scaling

        # State tracking
        self.current_step = 0
        self.cash_balance = initial_balance
        self.shares_held = 0
        self.portfolio_value = initial_balance
        self.total_trades = 0
        self.last_action = 0

        # History for reward calculation
        self.portfolio_history = []
        self.return_history = []

        # Define observation space (33 features)
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(33,),
            dtype=np.float32
        )

        # Define action space (continuous [-1, 1])
        self.action_space = spaces.Box(
            low=-1,
            high=1,
            shape=(1,),
            dtype=np.float32
        )

        logger.info(
            f"CatalystTradingEnv initialized: "
            f"{len(df)} steps, ${initial_balance:,.0f} initial balance"
        )

    def reset(self, seed: Optional[int] = None) -> Tuple[np.ndarray, Dict]:
        """
        Reset environment to initial state.

        Returns:
            (observation, info)
        """
        super().reset(seed=seed)

        self.current_step = self.lookback_window  # Start after lookback
        self.cash_balance = self.initial_balance
        self.shares_held = 0
        self.portfolio_value = self.initial_balance
        self.total_trades = 0
        self.last_action = 0

        self.portfolio_history = [self.initial_balance]
        self.return_history = []

        observation = self._get_observation()
        info = self._get_info()

        return observation, info

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Execute one time step.

        Args:
            action: Action value in [-1, 1]

        Returns:
            (observation, reward, done, truncated, info)
        """
        # Get current price
        current_price = self.df.loc[self.current_step, 'close']

        # Execute action
        self._execute_action(action[0], current_price)

        # Update portfolio value
        self.portfolio_value = self.cash_balance + (self.shares_held * current_price)
        self.portfolio_history.append(self.portfolio_value)

        # Calculate return
        if len(self.portfolio_history) > 1:
            ret = (self.portfolio_value - self.portfolio_history[-2]) / self.portfolio_history[-2]
            self.return_history.append(ret)

        # Calculate reward
        reward = self._calculate_reward()

        # Move to next step
        self.current_step += 1

        # Check if done
        done = self.current_step >= len(self.df) - 1
        truncated = False

        # Get observation and info
        observation = self._get_observation() if not done else np.zeros(33, dtype=np.float32)
        info = self._get_info()

        return observation, reward, done, truncated, info

    def _execute_action(self, action: float, current_price: float):
        """
        Execute trading action.

        Args:
            action: Action value in [-1, 1]
            current_price: Current market price
        """
        # Determine target position
        # action = 1 means buy with all cash
        # action = -1 means sell all shares
        # action = 0 means hold

        # Apply slippage
        if action > 0:  # Buying
            execution_price = current_price * (1 + self.slippage_pct)
        elif action < 0:  # Selling
            execution_price = current_price * (1 - self.slippage_pct)
        else:
            return  # No action

        # Calculate target shares based on action
        if action > 0:  # Buy
            # Use available cash to buy
            max_shares = self.cash_balance / execution_price
            target_shares = self.shares_held + (max_shares * action)
            shares_to_buy = target_shares - self.shares_held

            if shares_to_buy > 0:
                cost = shares_to_buy * execution_price
                commission = cost * self.commission_pct
                total_cost = cost + commission

                if total_cost <= self.cash_balance:
                    self.shares_held += shares_to_buy
                    self.cash_balance -= total_cost
                    self.total_trades += 1
                    self.last_action = action

        elif action < 0:  # Sell
            shares_to_sell = abs(action) * self.shares_held

            if shares_to_sell > 0:
                proceeds = shares_to_sell * execution_price
                commission = proceeds * self.commission_pct
                total_proceeds = proceeds - commission

                self.shares_held -= shares_to_sell
                self.cash_balance += total_proceeds
                self.total_trades += 1
                self.last_action = action

    def _calculate_reward(self) -> float:
        """
        Calculate reward based on Sharpe ratio.

        Reward components:
        1. Sharpe ratio of recent returns (main component)
        2. Transaction cost penalty
        3. Holding bonus (reduce churning)
        """
        # Need sufficient history for Sharpe
        if len(self.return_history) < 2:
            return 0.0

        # Calculate Sharpe ratio from recent returns
        recent_returns = self.return_history[-self.lookback_window:]

        if len(recent_returns) < 2:
            return 0.0

        mean_return = np.mean(recent_returns)
        std_return = np.std(recent_returns)

        if std_return == 0:
            sharpe = 0.0
        else:
            # Annualized Sharpe (assuming daily data)
            sharpe = (mean_return / std_return) * np.sqrt(252)

        reward = sharpe

        # Penalize transaction costs
        # Check if action changed position significantly
        if abs(self.last_action) > 0.1:  # Threshold to count as a trade
            reward -= 0.01  # Small penalty for trading

        # Bonus for holding position (reduce churning)
        if abs(self.last_action) < 0.1 and self.shares_held > 0:
            reward += 0.005  # Small bonus for holding

        # Scale reward
        reward *= self.reward_scaling

        return reward

    def _get_observation(self) -> np.ndarray:
        """
        Get current observation (state).

        Returns:
            33-feature observation vector
        """
        row = self.df.loc[self.current_step]
        current_price = row['close']

        # Account state (3)
        account_state = np.array([
            self.cash_balance / self.initial_balance,  # Normalized cash
            self.shares_held * current_price / self.initial_balance,  # Normalized position value
            self.portfolio_value / self.initial_balance  # Normalized portfolio value
        ], dtype=np.float32)

        # Price data (4)
        price_state = np.array([
            row['close'] / row['close'],  # Normalized to 1 (reference)
            row['high'] / row['close'],
            row['low'] / row['close'],
            np.log(row['volume'] + 1) / 20  # Log-scaled volume
        ], dtype=np.float32)

        # Technical indicators (8)
        indicators = np.array([
            row.get('rvol', 1.0),
            row.get('rsi', 50.0) / 100.0,  # Normalize to [0, 1]
            row.get('macd', 0.0) / current_price,
            row.get('macd_signal', 0.0) / current_price,
            row.get('vwap', current_price) / current_price,
            row.get('atr', 1.0) / current_price,
            row.get('sma_20', current_price) / current_price,
            row.get('ema_50', current_price) / current_price
        ], dtype=np.float32)

        # Catalyst features (8)
        catalyst_state = np.array([
            row.get('catalyst_score', 0.0),
            row.get('sentiment', 0.0),
            float(row.get('is_earnings', False)),
            float(row.get('is_merger', False)),
            float(row.get('is_fda', False)),
            float(row.get('is_offering', False)),
            float(row.get('is_insider', False)),
            row.get('news_velocity', 0.0) / 10.0  # Normalize
        ], dtype=np.float32)

        # Historical returns (10)
        returns = np.array([
            self._get_return(1),
            self._get_return(5),
            self._get_return(10),
            self._get_return(20),
            self._get_volatility(20),
            self._get_max_drawdown(20),
            self._get_sharpe(20),
            row.get('beta', 0.0),
            self._get_volume_trend(),
            self._get_price_momentum()
        ], dtype=np.float32)

        # Concatenate all features
        observation = np.concatenate([
            account_state,
            price_state,
            indicators,
            catalyst_state,
            returns
        ])

        return observation

    def _get_return(self, lookback: int) -> float:
        """Calculate return over lookback periods."""
        if self.current_step < lookback:
            return 0.0

        current_price = self.df.loc[self.current_step, 'close']
        past_price = self.df.loc[self.current_step - lookback, 'close']

        return (current_price - past_price) / past_price

    def _get_volatility(self, lookback: int) -> float:
        """Calculate volatility over lookback periods."""
        if self.current_step < lookback:
            return 0.0

        prices = self.df.loc[self.current_step - lookback:self.current_step, 'close']
        returns = prices.pct_change().dropna()

        return returns.std() if len(returns) > 1 else 0.0

    def _get_max_drawdown(self, lookback: int) -> float:
        """Calculate max drawdown over lookback periods."""
        if self.current_step < lookback:
            return 0.0

        prices = self.df.loc[self.current_step - lookback:self.current_step, 'close']
        cummax = prices.cummax()
        drawdown = (prices - cummax) / cummax

        return drawdown.min()

    def _get_sharpe(self, lookback: int) -> float:
        """Calculate Sharpe ratio over lookback periods."""
        if self.current_step < lookback:
            return 0.0

        prices = self.df.loc[self.current_step - lookback:self.current_step, 'close']
        returns = prices.pct_change().dropna()

        if len(returns) < 2:
            return 0.0

        mean_return = returns.mean()
        std_return = returns.std()

        return (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0.0

    def _get_volume_trend(self) -> float:
        """Calculate volume trend (recent vs average)."""
        if self.current_step < 20:
            return 0.0

        recent_volume = self.df.loc[self.current_step - 5:self.current_step, 'volume'].mean()
        avg_volume = self.df.loc[self.current_step - 20:self.current_step, 'volume'].mean()

        return (recent_volume - avg_volume) / avg_volume if avg_volume > 0 else 0.0

    def _get_price_momentum(self) -> float:
        """Calculate price momentum."""
        if self.current_step < 20:
            return 0.0

        return self._get_return(20)

    def _get_info(self) -> Dict:
        """Get info dictionary."""
        return {
            'step': self.current_step,
            'portfolio_value': self.portfolio_value,
            'cash_balance': self.cash_balance,
            'shares_held': self.shares_held,
            'total_trades': self.total_trades,
            'total_return': (self.portfolio_value - self.initial_balance) / self.initial_balance
        }

    def render(self, mode='human'):
        """Render environment state."""
        if mode == 'human':
            print(f"Step: {self.current_step}")
            print(f"Portfolio Value: ${self.portfolio_value:,.2f}")
            print(f"Cash: ${self.cash_balance:,.2f}")
            print(f"Shares: {self.shares_held:.2f}")
            print(f"Total Return: {((self.portfolio_value - self.initial_balance) / self.initial_balance * 100):.2f}%")
            print("---")
```

**Acceptance Criteria:**
- [ ] Environment compatible with Stable-Baselines3
- [ ] 33-feature state space implemented
- [ ] Continuous action space [-1, 1]
- [ ] Sharpe-based reward function
- [ ] Transaction costs modeled realistically
- [ ] Integrates with existing Catalyst indicators
- [ ] Random agent can interact with environment
- [ ] Episode termination handled correctly

**Tests Required:**
- Unit tests:
  - Test state space calculation
  - Test action execution (buy/sell)
  - Test reward calculation
  - Test reset functionality
- Integration tests:
  - Train simple RL agent (1000 steps)
  - Verify environment doesn't crash
  - Test with real historical data

**Dependencies:** Epics 1 & 2

---

### Story 3.2: Historical Data Pipeline for RL
**Priority:** P1
**Estimated Effort:** 3-4 days
**Dependencies:** Story 3.1

**Description:**
Build data pipeline that prepares historical market data for RL training. Must fetch OHLCV data, calculate all indicators, add catalyst scores, and create train/validation/test splits with proper temporal ordering. Should integrate with existing data sources.

**Tasks:**

- [ ] Task 3.2.1: Create data fetcher for historical OHLCV
- [ ] Task 3.2.2: Implement indicator calculation pipeline
- [ ] Task 3.2.3: Add catalyst score enrichment
- [ ] Task 3.2.4: Create train/val/test split logic
- [ ] Task 3.2.5: Implement data caching system
- [ ] Task 3.2.6: Add data quality validation

---

### Story 3.3: Agent Training Infrastructure
**Priority:** P1
**Estimated Effort:** 5-6 days
**Dependencies:** Stories 3.1, 3.2

**Description:**
Build training infrastructure for RL agents using Stable-Baselines3. Support training multiple algorithms (PPO, SAC, A2C), hyperparameter tuning, TensorBoard logging, and model versioning. Create ensemble agent that combines multiple trained models.

**Tasks:**

- [ ] Task 3.3.1: Create training script for PPO
- [ ] Task 3.3.2: Create training script for SAC
- [ ] Task 3.3.3: Create training script for A2C
- [ ] Task 3.3.4: Implement hyperparameter tuning (Optuna)
- [ ] Task 3.3.5: Add TensorBoard integration
- [ ] Task 3.3.6: Create ensemble agent (weighted voting)
- [ ] Task 3.3.7: Add model versioning and storage

---

### Story 3.4: Walk-Forward Validation System
**Priority:** P1
**Estimated Effort:** 4-5 days
**Dependencies:** Story 3.3

**Description:**
Implement walk-forward optimization system for validating RL agents. This prevents overfitting by training on rolling windows and testing on subsequent out-of-sample periods. Critical for ensuring strategy will generalize to live trading.

**Tasks:**

- [ ] Task 3.4.1: Implement walk-forward optimization logic
- [ ] Task 3.4.2: Create out-of-sample evaluation
- [ ] Task 3.4.3: Add performance aggregation across windows
- [ ] Task 3.4.4: Implement parameter stability tracking
- [ ] Task 3.4.5: Create walk-forward visualization
- [ ] Task 3.4.6: Add overfitting detection metrics

---

### Story 3.5: RL Agent Deployment & Integration
**Priority:** P1
**Estimated Effort:** 4-5 days
**Dependencies:** Stories 3.3, 3.4, Epics 1 & 2

**Description:**
Integrate trained RL agents with live trading system. Create inference pipeline that converts real-time market data into observations, gets agent predictions, and converts actions to trading signals. Must respect all risk controls and support model hot-swapping.

**Tasks:**

- [ ] Task 3.5.1: Create RL inference engine
- [ ] Task 3.5.2: Implement real-time observation generation
- [ ] Task 3.5.3: Add action-to-signal conversion
- [ ] Task 3.5.4: Integrate with signal router
- [ ] Task 3.5.5: Add model hot-swapping (zero downtime)
- [ ] Task 3.5.6: Create RL agent monitoring dashboard
- [ ] Task 3.5.7: End-to-end paper trading test

---

## Summary Statistics

### Epic Priority Levels
- **P0 (Critical)**: 2 epics (Epics 1 & 2)
- **P1 (High)**: 1 epic (Epic 3)

### Total Effort Estimates
- Epic 1: 4 weeks
- Epic 2: 4 weeks
- Epic 3: 6 weeks
- **Total: 14 weeks (3.5 months)**

### Story Breakdown
- Epic 1: 5 stories, ~15 tasks
- Epic 2: 5 stories, ~20 tasks
- Epic 3: 5 stories, ~20 tasks
- **Total: 15 stories, ~55 tasks**

### Critical Path
```
Epic 1 (Foundation) → Epic 2 (Risk) → Epic 3 (RL)
     4 weeks            4 weeks         6 weeks
```

### Parallel Work Opportunities
- After Epic 1 Story 1.3 completes:
  - Can start Epic 2 (Risk Management)
  - Can start Epic 3 Story 3.1 (RL Environment)

### Key Milestones
1. **Week 4**: Basic paper trading working (Epic 1)
2. **Week 8**: Risk management operational (Epic 2)
3. **Week 14**: RL agents trained and integrated (Epic 3)
4. **Week 16-24**: Paper trading validation, optimization, monitoring

---

## Next Steps

1. **Review and Approve**: Review this ticket structure with stakeholders
2. **Prioritize**: Confirm Epic priorities and dependencies
3. **Resource Planning**: Assign developers to Epics
4. **Setup**: Create Alpaca paper trading account, setup development environment
5. **Begin Development**: Start with Epic 1, Story 1.1 (Alpaca Broker Client)
6. **Weekly Check-ins**: Review progress, adjust estimates, address blockers

---

## References

- Implementation Plan: `/home/user/catalyst-bot/docs/paper-trading-bot-implementation-plan.md`
- Backtesting Research: `/home/user/catalyst-bot/docs/backtesting-framework-research.md`
- Architecture Patterns: `/home/user/catalyst-bot/research/trading-bot-architecture-patterns.md`
- Existing Codebase: `/home/user/catalyst-bot/src/catalyst_bot/`

---

**Document Version**: 1.0
**Created**: 2025-11-20
**Last Updated**: 2025-11-20
**Status**: Ready for Review
