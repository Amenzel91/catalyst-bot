"""
MockBroker - Simulated broker for paper trading without API calls.

Simulates:
- Order placement and fills
- Position tracking
- Portfolio value
- Slippage and volume constraints

Usage:
    from catalyst_bot.simulation import SimulationClock
    from catalyst_bot.simulation.mock_broker import MockBroker, OrderSide

    clock = SimulationClock(start_time=..., speed_multiplier=0)
    broker = MockBroker(
        starting_cash=10000.0,
        slippage_model="adaptive",
        clock=clock
    )

    # Update prices (call periodically with market data)
    broker.update_price("AAPL", 150.50, volume=1000000)

    # Place an order
    order = broker.submit_order("AAPL", OrderSide.BUY, 100)

    # Get portfolio value
    value = broker.get_portfolio_value()
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .clock import SimulationClock

log = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status states."""

    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OrderSide(Enum):
    """Order side (buy or sell)."""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"


@dataclass
class SimulatedOrder:
    """A simulated order."""

    order_id: str
    ticker: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        )


@dataclass
class SimulatedPosition:
    """A simulated position."""

    ticker: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        """Current market value of position."""
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        """Total cost basis of position."""
        return self.quantity * self.avg_cost

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return (self.current_price - self.avg_cost) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.avg_cost == 0:
            return 0.0
        return ((self.current_price - self.avg_cost) / self.avg_cost) * 100


class MockBroker:
    """
    Simulated broker that processes orders without API calls.

    Features:
    - Market and limit orders
    - Slippage simulation (adaptive, fixed, or none)
    - Volume constraints (max % of daily volume)
    - Position tracking with P&L
    - Portfolio value calculation
    """

    def __init__(
        self,
        starting_cash: float = 10000.0,
        slippage_model: str = "adaptive",
        slippage_pct: float = 0.5,
        max_volume_pct: float = 5.0,
        clock: Optional[SimulationClock] = None,
    ):
        """
        Initialize mock broker.

        Args:
            starting_cash: Initial cash balance
            slippage_model: "adaptive", "fixed", or "none"
            slippage_pct: Base slippage percentage
            max_volume_pct: Maximum order size as % of daily volume
            clock: SimulationClock for timestamps
        """
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.slippage_model = slippage_model
        self.slippage_pct = slippage_pct
        self.max_volume_pct = max_volume_pct
        self.clock = clock

        # State tracking
        self.positions: Dict[str, SimulatedPosition] = {}
        self.orders: Dict[str, SimulatedOrder] = {}
        self.order_history: List[SimulatedOrder] = []

        # Market data
        self.prices: Dict[str, float] = {}
        self.daily_volumes: Dict[str, int] = {}

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self._peak_value = starting_cash

    def _now(self) -> datetime:
        """Get current time (virtual or real)."""
        if self.clock:
            return self.clock.now()
        return datetime.now(timezone.utc)

    def update_price(self, ticker: str, price: float, volume: int = 0) -> None:
        """
        Update current price for a ticker.

        Should be called periodically with market data updates.

        Args:
            ticker: Stock ticker symbol
            price: Current price
            volume: Daily volume (optional, for volume constraints)
        """
        self.prices[ticker] = price

        if volume > 0:
            self.daily_volumes[ticker] = volume

        # Update position current price
        if ticker in self.positions:
            self.positions[ticker].current_price = price

        # Check for limit order fills
        self._check_limit_orders(ticker, price)

        # Update drawdown tracking
        self._update_drawdown()

    def submit_order(
        self,
        ticker: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> SimulatedOrder:
        """
        Submit an order for execution.

        Market orders fill immediately at current price + slippage.
        Limit orders queue until price is reached.

        Args:
            ticker: Stock ticker symbol
            side: Buy or sell
            quantity: Number of shares
            order_type: Market or limit
            limit_price: Limit price (required for limit orders)

        Returns:
            SimulatedOrder with status
        """
        order_id = f"sim_{uuid.uuid4().hex[:8]}"

        order = SimulatedOrder(
            order_id=order_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            created_at=self._now(),
        )

        self.orders[order_id] = order

        # Validate order
        rejection = self._validate_order(order)
        if rejection:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = rejection
            log.warning(f"Order rejected: {rejection}")
            self.order_history.append(order)
            return order

        # Market orders fill immediately
        if order_type == OrderType.MARKET:
            current_price = self.prices.get(ticker)
            if current_price:
                self._fill_order(order, current_price)
            else:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = f"No price data for {ticker}"

        return order

    def _validate_order(self, order: SimulatedOrder) -> Optional[str]:
        """
        Validate order and return rejection reason if invalid.

        Args:
            order: Order to validate

        Returns:
            Rejection reason string, or None if valid
        """
        ticker = order.ticker

        # Check if we have price data
        if ticker not in self.prices:
            return f"No price data for {ticker}"

        price = self.prices[ticker]

        # Check buying power for buys
        if order.side == OrderSide.BUY:
            cost = order.quantity * price
            if cost > self.cash:
                return (
                    f"Insufficient funds: need ${cost:.2f}, " f"have ${self.cash:.2f}"
                )

        # Check position for sells
        if order.side == OrderSide.SELL:
            position = self.positions.get(ticker)
            if not position or position.quantity < order.quantity:
                available = position.quantity if position else 0
                return (
                    f"Insufficient shares: need {order.quantity}, " f"have {available}"
                )

        # Check volume constraint
        daily_vol = self.daily_volumes.get(ticker, 0)
        if daily_vol > 0:
            max_shares = int(daily_vol * (self.max_volume_pct / 100))
            if order.quantity > max_shares:
                return (
                    f"Volume constraint: max {max_shares} shares "
                    f"({self.max_volume_pct}% of volume)"
                )

        return None

    def _fill_order(self, order: SimulatedOrder, market_price: float) -> None:
        """
        Fill an order at the given price with slippage.

        Args:
            order: Order to fill
            market_price: Current market price
        """
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
                pos.current_price = market_price
            else:
                self.positions[order.ticker] = SimulatedPosition(
                    ticker=order.ticker,
                    quantity=order.quantity,
                    avg_cost=fill_price,
                    current_price=market_price,
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
            elif pnl < 0:
                self.losing_trades += 1

            pos.quantity -= order.quantity
            if pos.quantity <= 0:
                del self.positions[order.ticker]

        self.order_history.append(order)
        log.info(
            f"Order filled: {order.side.value} {order.quantity} "
            f"{order.ticker} @ ${fill_price:.2f}"
        )

    def _calculate_slippage(self, order: SimulatedOrder, price: float) -> float:
        """
        Calculate slippage based on model.

        Args:
            order: Order being filled
            price: Current market price

        Returns:
            Slippage as decimal (0.01 = 1%)
        """
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
                    base_slippage *= 1 + order_pct * 10

            return min(base_slippage, 0.15)  # Cap at 15%

        return 0.0

    def _check_limit_orders(self, ticker: str, price: float) -> None:
        """
        Check if any limit orders should fill.

        Args:
            ticker: Ticker with updated price
            price: New price
        """
        for order in list(self.orders.values()):
            if order.ticker != ticker or order.status != OrderStatus.PENDING:
                continue

            if order.order_type != OrderType.LIMIT or order.limit_price is None:
                continue

            # Buy limit fills when price <= limit
            if order.side == OrderSide.BUY and price <= order.limit_price:
                self._fill_order(order, price)

            # Sell limit fills when price >= limit
            elif order.side == OrderSide.SELL and price >= order.limit_price:
                self._fill_order(order, price)

    def _update_drawdown(self) -> None:
        """Update max drawdown tracking."""
        current_value = self.get_portfolio_value()
        if current_value > self._peak_value:
            self._peak_value = current_value
        else:
            drawdown = (self._peak_value - current_value) / self._peak_value
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled, False if not found or not cancellable
        """
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
        total_return = total_value - self.starting_cash

        return {
            "starting_cash": self.starting_cash,
            "current_cash": self.cash,
            "positions_value": total_value - self.cash,
            "total_value": total_value,
            "total_return": total_return,
            "total_return_pct": (total_return / self.starting_cash) * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": (
                self.winning_trades / self.total_trades * 100
                if self.total_trades > 0
                else 0
            ),
            "realized_pnl": self.total_pnl,
            "max_drawdown_pct": self.max_drawdown * 100,
            "num_positions": len(self.positions),
        }

    def get_order(self, order_id: str) -> Optional[SimulatedOrder]:
        """Get order by ID."""
        return self.orders.get(order_id)

    def get_pending_orders(self) -> List[SimulatedOrder]:
        """Get all pending orders."""
        return [o for o in self.orders.values() if o.status == OrderStatus.PENDING]

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
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self._peak_value = self.starting_cash
        log.debug("MockBroker reset to initial state")
