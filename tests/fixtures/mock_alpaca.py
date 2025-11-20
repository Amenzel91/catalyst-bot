"""Mock Alpaca API client and data models for testing."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any
from unittest.mock import Mock


class MockAccount:
    """Mock Alpaca account object."""

    def __init__(
        self,
        account_number: str = "test-account-001",
        cash: float = 100000.00,
        portfolio_value: float = 100000.00,
        buying_power: float = 400000.00,
        status: str = "ACTIVE",
    ):
        self.account_number = account_number
        self.cash = Decimal(str(cash))
        self.portfolio_value = Decimal(str(portfolio_value))
        self.buying_power = Decimal(str(buying_power))
        self.equity = Decimal(str(portfolio_value))
        self.last_equity = Decimal(str(portfolio_value))
        self.long_market_value = Decimal("0")
        self.short_market_value = Decimal("0")
        self.initial_margin = Decimal("0")
        self.maintenance_margin = Decimal("0")
        self.daytrade_count = 0
        self.pattern_day_trader = False
        self.trading_blocked = False
        self.transfers_blocked = False
        self.account_blocked = False
        self.status = status
        self.created_at = datetime.now(timezone.utc).isoformat()


class MockPosition:
    """Mock Alpaca position object."""

    def __init__(
        self,
        symbol: str = "AAPL",
        qty: int = 100,
        side: str = "long",
        avg_entry_price: float = 170.00,
        current_price: float = 175.00,
    ):
        self.symbol = symbol
        self.qty = qty
        self.side = side
        self.avg_entry_price = Decimal(str(avg_entry_price))
        self.current_price = Decimal(str(current_price))
        self.market_value = Decimal(str(current_price * qty))
        self.cost_basis = Decimal(str(avg_entry_price * qty))
        self.unrealized_pl = self.market_value - self.cost_basis
        self.unrealized_plpc = (
            (self.current_price - self.avg_entry_price) / self.avg_entry_price
        )
        self.lastday_price = Decimal(str(current_price * 0.99))
        self.change_today = (self.current_price - self.lastday_price) / self.lastday_price


class MockOrder:
    """Mock Alpaca order object."""

    def __init__(
        self,
        symbol: str = "AAPL",
        qty: int = 100,
        side: str = "buy",
        order_type: str = "market",
        status: str = "filled",
        filled_avg_price: Optional[float] = None,
        order_id: Optional[str] = None,
    ):
        self.id = order_id or f"order-{uuid.uuid4()}"
        self.client_order_id = f"client-{uuid.uuid4()}"
        self.symbol = symbol
        self.qty = qty
        self.side = side
        self.type = order_type
        self.time_in_force = "day"
        self.limit_price = None
        self.stop_price = None
        self.status = status
        self.filled_qty = qty if status == "filled" else 0
        self.filled_avg_price = (
            Decimal(str(filled_avg_price)) if filled_avg_price else None
        )
        self.submitted_at = datetime.now(timezone.utc).isoformat()
        self.filled_at = (
            datetime.now(timezone.utc).isoformat() if status == "filled" else None
        )
        self.canceled_at = None
        self.failed_at = None
        self.replaced_by = None
        self.replaces = None
        self.order_class = "simple"
        self.legs = None


class MockAlpacaClient:
    """
    Mock Alpaca Trading Client for testing.

    Simulates the Alpaca API without making real HTTP requests.
    """

    def __init__(
        self,
        api_key: str = "test_key",
        api_secret: str = "test_secret",
        paper: bool = True,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper

        # Internal state
        self._account = MockAccount()
        self._positions: Dict[str, MockPosition] = {}
        self._orders: Dict[str, MockOrder] = {}
        self._order_history: List[MockOrder] = []

        # Configuration
        self.simulate_latency = False
        self.fail_next_order = False
        self.failure_reason = "Simulated API error"

    def get_account(self) -> MockAccount:
        """Get account information."""
        return self._account

    def get_all_positions(self) -> List[MockPosition]:
        """Get all open positions."""
        return list(self._positions.values())

    def get_open_position(self, symbol: str) -> MockPosition:
        """Get position for a specific symbol."""
        if symbol not in self._positions:
            raise Exception(f"Position for {symbol} not found")
        return self._positions[symbol]

    def close_position(self, symbol: str) -> MockOrder:
        """Close a position."""
        if symbol not in self._positions:
            raise Exception(f"Position for {symbol} not found")

        position = self._positions[symbol]
        order = MockOrder(
            symbol=symbol,
            qty=abs(position.qty),
            side="sell" if position.side == "long" else "buy",
            order_type="market",
            status="filled",
            filled_avg_price=float(position.current_price),
        )

        # Remove position
        del self._positions[symbol]

        # Update account cash
        self._account.cash += order.filled_avg_price * order.qty

        return order

    def submit_order(self, order_data: Any) -> MockOrder:
        """
        Submit an order.

        Args:
            order_data: Order request object with attributes:
                - symbol: str
                - qty: int
                - side: str (buy/sell)
                - type: str (market/limit/stop)
                - time_in_force: str
                - limit_price: Optional[float]
                - stop_price: Optional[float]
                - order_class: Optional[str] (simple/bracket/oco/oto)
                - take_profit: Optional[dict]
                - stop_loss: Optional[dict]

        Returns:
            MockOrder object
        """
        # Simulate failure if configured
        if self.fail_next_order:
            self.fail_next_order = False
            raise Exception(self.failure_reason)

        # Extract order parameters
        symbol = order_data.symbol
        qty = order_data.qty
        side = order_data.side
        order_type = order_data.type

        # Determine fill price
        if order_type == "market":
            # Use current market price (mock at $150 for simplicity)
            filled_price = 150.00
        elif order_type == "limit":
            filled_price = float(order_data.limit_price)
        elif order_type == "stop":
            filled_price = float(order_data.stop_price)
        else:
            filled_price = 150.00

        # Create order
        order = MockOrder(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            status="filled",
            filled_avg_price=filled_price,
        )

        # Update positions
        if side == "buy":
            if symbol in self._positions:
                # Add to existing position
                pos = self._positions[symbol]
                new_qty = pos.qty + qty
                new_avg_price = (
                    (pos.avg_entry_price * pos.qty) + (filled_price * qty)
                ) / new_qty
                pos.qty = new_qty
                pos.avg_entry_price = Decimal(str(new_avg_price))
            else:
                # Create new position
                self._positions[symbol] = MockPosition(
                    symbol=symbol,
                    qty=qty,
                    side="long",
                    avg_entry_price=filled_price,
                    current_price=filled_price,
                )

            # Deduct cash
            self._account.cash -= Decimal(str(filled_price * qty))

        elif side == "sell":
            if symbol in self._positions:
                pos = self._positions[symbol]
                if pos.qty >= qty:
                    pos.qty -= qty
                    if pos.qty == 0:
                        del self._positions[symbol]
                else:
                    raise Exception(f"Insufficient position to sell {qty} shares of {symbol}")

            # Add cash
            self._account.cash += Decimal(str(filled_price * qty))

        # Store order
        self._orders[order.id] = order
        self._order_history.append(order)

        return order

    def get_order_by_id(self, order_id: str) -> MockOrder:
        """Get order by ID."""
        if order_id not in self._orders:
            raise Exception(f"Order {order_id} not found")
        return self._orders[order_id]

    def cancel_order_by_id(self, order_id: str) -> None:
        """Cancel an order."""
        if order_id not in self._orders:
            raise Exception(f"Order {order_id} not found")

        order = self._orders[order_id]
        order.status = "canceled"
        order.canceled_at = datetime.now(timezone.utc).isoformat()

    def get_orders(self, status: str = "all") -> List[MockOrder]:
        """Get orders with optional status filter."""
        if status == "all":
            return self._order_history
        return [o for o in self._order_history if o.status == status]

    # Helper methods for testing

    def set_position_price(self, symbol: str, price: float):
        """Update the current price of a position (for testing)."""
        if symbol in self._positions:
            self._positions[symbol].current_price = Decimal(str(price))

    def reset(self):
        """Reset client to initial state."""
        self._account = MockAccount()
        self._positions.clear()
        self._orders.clear()
        self._order_history.clear()
        self.fail_next_order = False


# Factory functions for creating mock objects

def create_mock_account(**kwargs) -> MockAccount:
    """Create a mock account with custom attributes."""
    return MockAccount(**kwargs)


def create_mock_position(**kwargs) -> MockPosition:
    """Create a mock position with custom attributes."""
    return MockPosition(**kwargs)


def create_mock_order(**kwargs) -> MockOrder:
    """Create a mock order with custom attributes."""
    return MockOrder(**kwargs)
