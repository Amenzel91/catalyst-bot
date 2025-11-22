"""
Broker Interface Module

This module defines the abstract base class and type definitions for all broker
implementations. It provides a standardized interface for interacting with different
brokers (Alpaca, Interactive Brokers, TD Ameritrade, etc.).

The interface follows these principles:
- Type safety with comprehensive dataclasses
- Async-first design for non-blocking operations
- Standardized error handling
- Consistent return types across all brokers
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# ============================================================================
# Enumerations
# ============================================================================


class OrderSide(str, Enum):
    """Order side: buy or sell"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type definitions"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    """Time in force options"""
    DAY = "day"  # Good for day
    GTC = "gtc"  # Good till cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class OrderStatus(str, Enum):
    """Order status lifecycle"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(str, Enum):
    """Position side: long or short"""
    LONG = "long"
    SHORT = "short"


class AccountStatus(str, Enum):
    """Account status"""
    ACTIVE = "active"
    CLOSED = "closed"
    RESTRICTED = "restricted"
    SUSPENDED = "suspended"


# ============================================================================
# Type Definitions
# ============================================================================


@dataclass
class Order:
    """
    Represents a trading order.

    This is the standardized order representation across all brokers.
    Each broker implementation should convert from their native format
    to this common format.
    """

    # Identity
    order_id: str  # Broker's order ID
    client_order_id: Optional[str] = None  # Our internal ID

    # Order details
    ticker: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: int = 0
    filled_quantity: int = 0

    # Pricing
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    filled_avg_price: Optional[Decimal] = None

    # Execution
    time_in_force: TimeInForce = TimeInForce.DAY
    status: OrderStatus = OrderStatus.PENDING

    # Timestamps
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Bracket order support
    parent_order_id: Optional[str] = None
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None

    # Additional metadata
    extended_hours: bool = False
    metadata: Dict = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if order is still active (not filled/cancelled/rejected)"""
        return self.status in {
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        }

    def is_filled(self) -> bool:
        """Check if order is completely filled"""
        return self.status == OrderStatus.FILLED

    def remaining_quantity(self) -> int:
        """Calculate remaining unfilled quantity"""
        return self.quantity - self.filled_quantity


@dataclass
class Position:
    """
    Represents an open trading position.

    This is the standardized position representation across all brokers.
    """

    # Identity
    ticker: str
    side: PositionSide

    # Quantities
    quantity: int  # Number of shares/contracts
    available_quantity: int  # Quantity available to close (not in pending orders)

    # Pricing
    entry_price: Decimal  # Average entry price
    current_price: Decimal  # Current market price
    cost_basis: Decimal  # Total cost basis
    market_value: Decimal  # Current market value

    # P&L
    unrealized_pnl: Decimal  # Unrealized profit/loss
    unrealized_pnl_pct: Decimal  # Unrealized P&L percentage

    # Timestamps
    opened_at: datetime
    updated_at: datetime

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def get_exposure(self) -> Decimal:
        """Calculate position exposure (market value)"""
        return self.market_value

    def get_pnl_ratio(self) -> float:
        """Calculate P&L ratio relative to cost basis"""
        if self.cost_basis == 0:
            return 0.0
        return float(self.unrealized_pnl / self.cost_basis)


@dataclass
class Account:
    """
    Represents broker account information.

    This is the standardized account representation across all brokers.
    """

    # Identity
    account_id: str
    account_number: str
    status: AccountStatus

    # Balances
    cash: Decimal  # Available cash
    portfolio_value: Decimal  # Total portfolio value
    equity: Decimal  # Total equity (cash + positions)
    buying_power: Decimal  # Available buying power

    # Margin information (if applicable)
    initial_margin: Optional[Decimal] = None
    maintenance_margin: Optional[Decimal] = None

    # P&L tracking
    total_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")

    # Risk metrics
    leverage: Decimal = Decimal("1.0")

    # Account flags
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    transfers_blocked: bool = False
    account_blocked: bool = False

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def get_available_capital(self) -> Decimal:
        """Get available capital for new positions"""
        return min(self.cash, self.buying_power)

    def get_total_exposure(self) -> Decimal:
        """Calculate total portfolio exposure"""
        return self.portfolio_value - self.cash

    def is_tradeable(self) -> bool:
        """Check if account can place trades"""
        return (
            self.status == AccountStatus.ACTIVE
            and not self.trading_blocked
            and not self.account_blocked
        )


@dataclass
class BracketOrderParams:
    """
    Parameters for creating a bracket order.

    A bracket order consists of:
    - Entry order (market or limit)
    - Stop-loss order
    - Take-profit order
    """

    # Entry order
    ticker: str
    side: OrderSide
    quantity: int
    entry_type: OrderType = OrderType.MARKET
    entry_limit_price: Optional[Decimal] = None

    # Stop-loss order
    stop_loss_price: Decimal = Decimal("0")
    stop_loss_type: OrderType = OrderType.STOP

    # Take-profit order
    take_profit_price: Decimal = Decimal("0")
    take_profit_type: OrderType = OrderType.LIMIT

    # Common parameters
    time_in_force: TimeInForce = TimeInForce.GTC
    extended_hours: bool = False

    # Metadata
    client_order_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class BracketOrder:
    """
    Represents a complete bracket order with all three legs.
    """

    entry_order: Order
    stop_loss_order: Order
    take_profit_order: Order

    def get_all_order_ids(self) -> List[str]:
        """Get all order IDs in the bracket"""
        return [
            self.entry_order.order_id,
            self.stop_loss_order.order_id,
            self.take_profit_order.order_id,
        ]

    def is_entry_filled(self) -> bool:
        """Check if entry order is filled"""
        return self.entry_order.is_filled()

    def get_active_exit_order(self) -> Optional[Order]:
        """Get the active exit order (stop or target)"""
        if self.stop_loss_order.is_active():
            return self.stop_loss_order
        if self.take_profit_order.is_active():
            return self.take_profit_order
        return None


# ============================================================================
# Custom Exceptions
# ============================================================================


class BrokerError(Exception):
    """Base exception for all broker-related errors"""
    pass


class BrokerConnectionError(BrokerError):
    """Raised when connection to broker fails"""
    pass


class BrokerAuthenticationError(BrokerError):
    """Raised when authentication fails"""
    pass


class OrderRejectedError(BrokerError):
    """Raised when broker rejects an order"""
    pass


class InsufficientFundsError(BrokerError):
    """Raised when account has insufficient funds"""
    pass


class PositionNotFoundError(BrokerError):
    """Raised when position doesn't exist"""
    pass


class OrderNotFoundError(BrokerError):
    """Raised when order doesn't exist"""
    pass


class RateLimitError(BrokerError):
    """Raised when broker rate limit is hit"""
    pass


# ============================================================================
# Abstract Base Class
# ============================================================================


class BrokerInterface(ABC):
    """
    Abstract base class for all broker implementations.

    This interface defines the contract that all broker implementations must
    follow. It ensures consistency across different broker integrations and
    makes it easy to swap brokers or support multiple brokers simultaneously.

    Implementation Requirements:
    - All methods should be async where appropriate
    - All errors should raise appropriate BrokerError subclasses
    - All return types should use the standardized dataclasses
    - Connection management should be handled internally
    - Rate limiting should be handled internally
    - Retry logic should be implemented for transient errors
    """

    def __init__(self, config: Dict):
        """
        Initialize broker client.

        Args:
            config: Configuration dictionary containing:
                - api_key: API key for broker
                - api_secret: API secret for broker
                - base_url: Base URL for broker API (optional)
                - paper_trading: Whether to use paper trading (optional)
                - rate_limit: Rate limit configuration (optional)
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # TODO: Initialize connection parameters
        # TODO: Set up rate limiting
        # TODO: Initialize retry logic
        # TODO: Set up authentication

    # ========================================================================
    # Connection Management
    # ========================================================================

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to broker API.

        Returns:
            True if connection successful, False otherwise

        Raises:
            BrokerConnectionError: If connection fails
            BrokerAuthenticationError: If authentication fails
        """
        # TODO: Implement connection logic
        # TODO: Test authentication
        # TODO: Initialize WebSocket connections if needed
        # TODO: Set up heartbeat/keepalive
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Disconnect from broker API and clean up resources.
        """
        # TODO: Close WebSocket connections
        # TODO: Cancel pending tasks
        # TODO: Clean up resources
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """
        Check if currently connected to broker.

        Returns:
            True if connected, False otherwise
        """
        # TODO: Check connection status
        # TODO: Verify authentication is still valid
        pass

    # ========================================================================
    # Account Information
    # ========================================================================

    @abstractmethod
    async def get_account(self) -> Account:
        """
        Get current account information.

        Returns:
            Account object with current account details

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch account information from broker API
        # TODO: Convert broker response to Account dataclass
        # TODO: Handle errors and retries
        pass

    @abstractmethod
    async def get_buying_power(self) -> Decimal:
        """
        Get current buying power.

        Returns:
            Available buying power as Decimal

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch buying power from broker API
        # TODO: Handle margin vs cash accounts differently
        pass

    # ========================================================================
    # Position Management
    # ========================================================================

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch all positions from broker API
        # TODO: Convert broker response to Position dataclasses
        # TODO: Calculate unrealized P&L for each position
        pass

    @abstractmethod
    async def get_position(self, ticker: str) -> Optional[Position]:
        """
        Get position for specific ticker.

        Args:
            ticker: Stock symbol

        Returns:
            Position object if position exists, None otherwise

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch specific position from broker API
        # TODO: Handle case where position doesn't exist
        pass

    @abstractmethod
    async def close_position(
        self,
        ticker: str,
        quantity: Optional[int] = None,
    ) -> Order:
        """
        Close an existing position.

        Args:
            ticker: Stock symbol
            quantity: Quantity to close (None = close entire position)

        Returns:
            Order object for the closing order

        Raises:
            PositionNotFoundError: If position doesn't exist
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch current position
        # TODO: Determine quantity to close
        # TODO: Create market order to close position
        # TODO: Submit order to broker
        pass

    # ========================================================================
    # Order Management
    # ========================================================================

    @abstractmethod
    async def place_order(
        self,
        ticker: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        extended_hours: bool = False,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """
        Place a single order.

        Args:
            ticker: Stock symbol
            side: Order side (buy/sell)
            quantity: Number of shares
            order_type: Type of order
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: Time in force
            extended_hours: Allow extended hours trading
            client_order_id: Client-specified order ID

        Returns:
            Order object with order details

        Raises:
            OrderRejectedError: If broker rejects order
            InsufficientFundsError: If insufficient buying power
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Validate order parameters
        # TODO: Check buying power
        # TODO: Convert parameters to broker's format
        # TODO: Submit order to broker API
        # TODO: Convert response to Order dataclass
        # TODO: Handle errors (insufficient funds, invalid parameters, etc.)
        pass

    @abstractmethod
    async def place_bracket_order(
        self,
        params: BracketOrderParams,
    ) -> BracketOrder:
        """
        Place a bracket order (entry + stop loss + take profit).

        Args:
            params: Bracket order parameters

        Returns:
            BracketOrder object with all three orders

        Raises:
            OrderRejectedError: If broker rejects order
            InsufficientFundsError: If insufficient buying power
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Validate bracket order parameters
        # TODO: Check buying power
        # TODO: Submit bracket order to broker
        # TODO: Some brokers support native bracket orders (use that)
        # TODO: Others require submitting three separate orders (implement that)
        # TODO: Link orders together via parent_order_id
        # TODO: Return BracketOrder with all three orders
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Broker's order ID

        Returns:
            True if cancelled successfully, False otherwise

        Raises:
            OrderNotFoundError: If order doesn't exist
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Submit cancellation request to broker API
        # TODO: Handle case where order is already filled
        # TODO: Handle case where order doesn't exist
        pass

    @abstractmethod
    async def cancel_all_orders(self) -> int:
        """
        Cancel all open orders.

        Returns:
            Number of orders cancelled

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch all open orders
        # TODO: Cancel each order
        # TODO: Handle partial failures gracefully
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """
        Get details of a specific order.

        Args:
            order_id: Broker's order ID

        Returns:
            Order object with current order details

        Raises:
            OrderNotFoundError: If order doesn't exist
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch order details from broker API
        # TODO: Convert to Order dataclass
        # TODO: Handle case where order doesn't exist
        pass

    @abstractmethod
    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
    ) -> List[Order]:
        """
        Get list of orders.

        Args:
            status: Filter by order status (None = all orders)
            limit: Maximum number of orders to return

        Returns:
            List of Order objects

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        # TODO: Fetch orders from broker API
        # TODO: Filter by status if specified
        # TODO: Convert to Order dataclasses
        pass

    # ========================================================================
    # Market Data (Optional - may use separate data provider)
    # ========================================================================

    async def get_current_price(self, ticker: str) -> Optional[Decimal]:
        """
        Get current price for a ticker.

        This is optional - may use separate market data provider.

        Args:
            ticker: Stock symbol

        Returns:
            Current price as Decimal, or None if not available
        """
        # TODO: Fetch current price from broker API
        # NOTE: This may not be needed if using separate data provider
        self.logger.warning(
            "get_current_price not implemented - using separate data provider"
        )
        return None

    # ========================================================================
    # Utility Methods
    # ========================================================================

    async def health_check(self) -> Dict:
        """
        Perform health check on broker connection.

        Returns:
            Dictionary with health check results:
            - connected: bool
            - authenticated: bool
            - latency_ms: float
            - rate_limit_remaining: int
            - last_error: Optional[str]
        """
        # TODO: Implement health check
        # TODO: Test connection
        # TODO: Measure latency
        # TODO: Check rate limits
        return {
            "connected": await self.is_connected(),
            "authenticated": False,
            "latency_ms": 0.0,
            "rate_limit_remaining": 0,
            "last_error": None,
        }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of BrokerInterface.

    This demonstrates how to implement and use a broker client.
    """

    import asyncio

    # Example: Creating a mock broker implementation
    class MockBroker(BrokerInterface):
        """Mock broker for testing"""

        async def connect(self) -> bool:
            self.logger.info("Connected to mock broker")
            return True

        async def disconnect(self) -> None:
            self.logger.info("Disconnected from mock broker")

        async def is_connected(self) -> bool:
            return True

        async def get_account(self) -> Account:
            return Account(
                account_id="mock123",
                account_number="123456",
                status=AccountStatus.ACTIVE,
                cash=Decimal("100000"),
                portfolio_value=Decimal("100000"),
                equity=Decimal("100000"),
                buying_power=Decimal("100000"),
            )

        async def get_buying_power(self) -> Decimal:
            return Decimal("100000")

        async def get_positions(self) -> List[Position]:
            return []

        async def get_position(self, ticker: str) -> Optional[Position]:
            return None

        async def close_position(
            self, ticker: str, quantity: Optional[int] = None
        ) -> Order:
            raise NotImplementedError()

        async def place_order(
            self,
            ticker: str,
            side: OrderSide,
            quantity: int,
            order_type: OrderType = OrderType.MARKET,
            limit_price: Optional[Decimal] = None,
            stop_price: Optional[Decimal] = None,
            time_in_force: TimeInForce = TimeInForce.DAY,
            extended_hours: bool = False,
            client_order_id: Optional[str] = None,
        ) -> Order:
            return Order(
                order_id="mock_order_123",
                ticker=ticker,
                side=side,
                order_type=order_type,
                quantity=quantity,
                status=OrderStatus.SUBMITTED,
                submitted_at=datetime.now(),
            )

        async def place_bracket_order(
            self, params: BracketOrderParams
        ) -> BracketOrder:
            raise NotImplementedError()

        async def cancel_order(self, order_id: str) -> bool:
            return True

        async def cancel_all_orders(self) -> int:
            return 0

        async def get_order(self, order_id: str) -> Order:
            raise OrderNotFoundError(f"Order {order_id} not found")

        async def get_orders(
            self, status: Optional[OrderStatus] = None, limit: int = 100
        ) -> List[Order]:
            return []

    async def demo():
        """Demo function showing broker usage"""

        # Initialize broker
        broker = MockBroker(config={
            "api_key": "test_key",
            "api_secret": "test_secret",
        })

        # Connect
        await broker.connect()

        # Get account info
        account = await broker.get_account()
        print(f"Account balance: ${account.cash}")
        print(f"Buying power: ${account.buying_power}")

        # Place an order
        order = await broker.place_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        print(f"Placed order: {order.order_id}")

        # Get positions
        positions = await broker.get_positions()
        print(f"Open positions: {len(positions)}")

        # Disconnect
        await broker.disconnect()

    # Run demo
    asyncio.run(demo())
