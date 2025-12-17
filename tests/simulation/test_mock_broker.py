"""
Tests for MockBroker.
"""

from catalyst_bot.simulation import MockBroker, OrderSide, OrderStatus, OrderType


class TestMockBrokerBasics:
    """Basic functionality tests."""

    def test_initialization(self, instant_clock):
        """Test broker initializes correctly."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="adaptive",
            clock=instant_clock,
        )

        assert broker.cash == 10000.0
        assert broker.starting_cash == 10000.0
        assert len(broker.positions) == 0

    def test_custom_settings(self, instant_clock):
        """Test broker with custom settings."""
        broker = MockBroker(
            starting_cash=50000.0,
            slippage_model="fixed",
            slippage_pct=1.0,
            max_volume_pct=10.0,
            clock=instant_clock,
        )

        assert broker.starting_cash == 50000.0
        assert broker.slippage_model == "fixed"
        assert broker.slippage_pct == 1.0
        assert broker.max_volume_pct == 10.0


class TestPriceUpdates:
    """Tests for price update functionality."""

    def test_update_price(self, instant_clock):
        """Test updating price for a ticker."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)

        broker.update_price("AAPL", 150.0, volume=1000000)

        assert broker.prices["AAPL"] == 150.0
        assert broker.daily_volumes["AAPL"] == 1000000

    def test_position_price_updates(self, instant_clock):
        """Test position price updates with market data."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)

        # Buy a position
        broker.update_price("AAPL", 150.0, volume=1000000)
        broker.submit_order("AAPL", OrderSide.BUY, 10)

        # Update price
        broker.update_price("AAPL", 155.0)

        # Position should reflect new price
        position = broker.get_position("AAPL")
        assert position.current_price == 155.0


class TestOrderSubmission:
    """Tests for order submission."""

    def test_market_order_buy(self, instant_clock):
        """Test market buy order."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        order = broker.submit_order("AAPL", OrderSide.BUY, 10)

        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 10
        assert order.filled_price == 100.0

        # Check position was created
        position = broker.get_position("AAPL")
        assert position is not None
        assert position.quantity == 10
        assert position.avg_cost == 100.0

        # Check cash was deducted
        assert broker.cash == 9000.0  # 10000 - (10 * 100)

    def test_market_order_sell(self, instant_clock):
        """Test market sell order."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        # First buy
        broker.submit_order("AAPL", OrderSide.BUY, 10)
        assert broker.cash == 9000.0

        # Then sell at higher price
        broker.update_price("AAPL", 110.0)
        order = broker.submit_order("AAPL", OrderSide.SELL, 10)

        assert order.status == OrderStatus.FILLED
        assert order.filled_price == 110.0

        # Check position is closed
        assert broker.get_position("AAPL") is None

        # Check cash increased
        assert broker.cash == 10100.0  # 9000 + (10 * 110)

    def test_limit_order_pending(self, instant_clock):
        """Test limit order stays pending."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)
        broker.update_price("AAPL", 100.0, volume=1000000)

        # Limit buy below current price
        order = broker.submit_order(
            "AAPL",
            OrderSide.BUY,
            10,
            order_type=OrderType.LIMIT,
            limit_price=95.0,
        )

        assert order.status == OrderStatus.PENDING
        assert broker.get_position("AAPL") is None

    def test_limit_order_fills_on_price_move(self, instant_clock):
        """Test limit order fills when price reaches limit."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        # Limit buy below current price
        order = broker.submit_order(
            "AAPL",
            OrderSide.BUY,
            10,
            order_type=OrderType.LIMIT,
            limit_price=95.0,
        )
        assert order.status == OrderStatus.PENDING

        # Price drops to limit
        broker.update_price("AAPL", 95.0)

        # Order should now be filled
        assert order.status == OrderStatus.FILLED
        assert order.filled_price == 95.0


class TestOrderValidation:
    """Tests for order validation."""

    def test_insufficient_funds(self, instant_clock):
        """Test order rejected for insufficient funds."""
        broker = MockBroker(starting_cash=1000.0, clock=instant_clock)
        broker.update_price("AAPL", 100.0, volume=1000000)

        # Try to buy more than we can afford
        order = broker.submit_order("AAPL", OrderSide.BUY, 100)

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient funds" in order.rejection_reason

    def test_insufficient_shares(self, instant_clock):
        """Test sell order rejected for insufficient shares."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)
        broker.update_price("AAPL", 100.0, volume=1000000)

        # Try to sell without position
        order = broker.submit_order("AAPL", OrderSide.SELL, 10)

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient shares" in order.rejection_reason

    def test_no_price_data(self, instant_clock):
        """Test order rejected without price data."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)

        order = broker.submit_order("AAPL", OrderSide.BUY, 10)

        assert order.status == OrderStatus.REJECTED
        assert "No price data" in order.rejection_reason

    def test_volume_constraint(self, instant_clock):
        """Test order rejected for exceeding volume constraint."""
        broker = MockBroker(
            starting_cash=1000000.0,
            max_volume_pct=5.0,
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000)  # Low volume

        # Try to buy more than 5% of volume (50 shares)
        order = broker.submit_order("AAPL", OrderSide.BUY, 100)

        assert order.status == OrderStatus.REJECTED
        assert "Volume constraint" in order.rejection_reason


class TestSlippage:
    """Tests for slippage models."""

    def test_no_slippage(self, instant_clock):
        """Test no slippage model."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        order = broker.submit_order("AAPL", OrderSide.BUY, 10)

        assert order.filled_price == 100.0

    def test_fixed_slippage(self, instant_clock):
        """Test fixed slippage model."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="fixed",
            slippage_pct=1.0,  # 1%
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        order = broker.submit_order("AAPL", OrderSide.BUY, 10)

        # Buy should have positive slippage (pay more)
        assert order.filled_price == 101.0

    def test_adaptive_slippage_penny_stock(self, instant_clock):
        """Test adaptive slippage is higher for penny stocks."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="adaptive",
            slippage_pct=0.5,
            clock=instant_clock,
        )
        broker.update_price("PENNY", 0.50, volume=1000000)
        broker.update_price("AAPL", 150.0, volume=1000000)

        penny_order = broker.submit_order("PENNY", OrderSide.BUY, 100)
        aapl_order = broker.submit_order("AAPL", OrderSide.BUY, 10)

        # Penny stock should have higher slippage rate
        penny_slippage = (penny_order.filled_price - 0.50) / 0.50
        aapl_slippage = (aapl_order.filled_price - 150.0) / 150.0

        assert penny_slippage > aapl_slippage


class TestPositionManagement:
    """Tests for position management."""

    def test_position_averaging(self, instant_clock):
        """Test position averaging on multiple buys."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        # Buy 10 at 100
        broker.submit_order("AAPL", OrderSide.BUY, 10)

        # Buy 10 more at 110
        broker.update_price("AAPL", 110.0)
        broker.submit_order("AAPL", OrderSide.BUY, 10)

        position = broker.get_position("AAPL")
        assert position.quantity == 20
        # Average cost should be (10*100 + 10*110) / 20 = 105
        assert position.avg_cost == 105.0

    def test_partial_sell(self, instant_clock):
        """Test selling partial position."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        broker.submit_order("AAPL", OrderSide.BUY, 20)
        broker.submit_order("AAPL", OrderSide.SELL, 10)

        position = broker.get_position("AAPL")
        assert position.quantity == 10

    def test_position_pnl(self, instant_clock):
        """Test position P&L calculation."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        broker.submit_order("AAPL", OrderSide.BUY, 10)

        # Price goes up
        broker.update_price("AAPL", 110.0)

        position = broker.get_position("AAPL")
        assert position.unrealized_pnl == 100.0  # 10 * (110 - 100)
        assert position.unrealized_pnl_pct == 10.0  # 10%


class TestPortfolioStats:
    """Tests for portfolio statistics."""

    def test_portfolio_value(self, instant_clock):
        """Test portfolio value calculation."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        broker.submit_order("AAPL", OrderSide.BUY, 10)
        broker.update_price("AAPL", 110.0)

        # Cash: 9000, Position: 10 * 110 = 1100
        value = broker.get_portfolio_value()
        assert value == 10100.0

    def test_portfolio_stats(self, instant_clock):
        """Test portfolio statistics."""
        broker = MockBroker(
            starting_cash=10000.0,
            slippage_model="none",
            clock=instant_clock,
        )
        broker.update_price("AAPL", 100.0, volume=1000000)

        # Make a winning trade
        broker.submit_order("AAPL", OrderSide.BUY, 10)
        broker.update_price("AAPL", 110.0)
        broker.submit_order("AAPL", OrderSide.SELL, 10)

        stats = broker.get_portfolio_stats()
        assert stats["total_trades"] == 1
        assert stats["winning_trades"] == 1
        assert stats["realized_pnl"] == 100.0
        assert stats["win_rate"] == 100.0


class TestOrderCancellation:
    """Tests for order cancellation."""

    def test_cancel_pending_order(self, instant_clock):
        """Test cancelling a pending order."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)
        broker.update_price("AAPL", 100.0, volume=1000000)

        order = broker.submit_order(
            "AAPL",
            OrderSide.BUY,
            10,
            order_type=OrderType.LIMIT,
            limit_price=95.0,
        )

        result = broker.cancel_order(order.order_id)
        assert result is True
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_filled_order(self, instant_clock):
        """Test cannot cancel filled order."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)
        broker.update_price("AAPL", 100.0, volume=1000000)

        order = broker.submit_order("AAPL", OrderSide.BUY, 10)
        result = broker.cancel_order(order.order_id)

        assert result is False
        assert order.status == OrderStatus.FILLED


class TestReset:
    """Tests for broker reset."""

    def test_reset(self, instant_clock):
        """Test resetting broker state."""
        broker = MockBroker(starting_cash=10000.0, clock=instant_clock)
        broker.update_price("AAPL", 100.0, volume=1000000)
        broker.submit_order("AAPL", OrderSide.BUY, 10)

        broker.reset()

        assert broker.cash == 10000.0
        assert len(broker.positions) == 0
        assert len(broker.orders) == 0
        assert broker.total_trades == 0
