# Broker Integration Components

This directory contains the complete broker integration system for paper and live trading.

## Components

### 1. BrokerInterface (`broker_interface.py`)

Abstract base class defining the standard interface for all broker implementations.

**Key Features:**
- Type-safe dataclasses for Orders, Positions, and Account
- Standardized enumerations (OrderType, OrderStatus, etc.)
- Abstract methods that all brokers must implement
- Custom exception hierarchy for error handling

**Usage:**
```python
from catalyst_bot.broker import BrokerInterface, Order, OrderSide, OrderType

# All broker implementations follow this interface
class MyBroker(BrokerInterface):
    async def place_order(self, ticker, side, quantity, order_type):
        # Implementation here
        pass
```

### 2. AlpacaBrokerClient (`alpaca_client.py`)

Complete implementation of BrokerInterface for Alpaca Markets.

**Key Features:**
- REST API integration
- Paper and live trading support
- Bracket order support (entry + stop loss + take profit)
- Rate limiting and retry logic
- Comprehensive error handling

**Configuration:**
```bash
# Environment variables
export ALPACA_API_KEY="your_api_key"
export ALPACA_API_SECRET="your_api_secret"
```

**Usage:**
```python
from catalyst_bot.broker import AlpacaBrokerClient, OrderSide, OrderType
from decimal import Decimal

# Initialize (paper trading)
broker = AlpacaBrokerClient(paper_trading=True)
await broker.connect()

# Get account info
account = await broker.get_account()
print(f"Buying Power: ${account.buying_power}")

# Place market order
order = await broker.place_order(
    ticker="AAPL",
    side=OrderSide.BUY,
    quantity=10,
    order_type=OrderType.MARKET,
)

# Place bracket order (entry + stop + target)
from catalyst_bot.broker import BracketOrderParams

bracket = await broker.place_bracket_order(
    BracketOrderParams(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        entry_type=OrderType.LIMIT,
        entry_limit_price=Decimal("150.00"),
        stop_loss_price=Decimal("145.00"),
        take_profit_price=Decimal("160.00"),
    )
)

# Get positions
positions = await broker.get_positions()
for pos in positions:
    print(f"{pos.ticker}: {pos.quantity} shares, P&L: ${pos.unrealized_pnl}")

# Close position
await broker.close_position("AAPL")

# Disconnect
await broker.disconnect()
```

### 3. OrderExecutor (`../execution/order_executor.py`)

Converts trading signals into broker orders with proper position sizing.

**Key Features:**
- Signal to order conversion
- Multiple position sizing methods:
  - Percentage of portfolio
  - Risk-based sizing (based on stop-loss distance)
  - Kelly criterion (optional)
- Bracket order creation
- Order monitoring and fill tracking
- Database logging of all executions

**Database Schema:**
```sql
CREATE TABLE executed_orders (
    order_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    signal_id TEXT,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    filled_avg_price REAL,
    submitted_at TIMESTAMP NOT NULL,
    filled_at TIMESTAMP,
    ...
);
```

**Usage:**
```python
from catalyst_bot.execution import OrderExecutor, TradingSignal, PositionSizingConfig
from decimal import Decimal
from datetime import datetime

# Initialize
executor = OrderExecutor(
    broker=broker,
    position_sizing_config=PositionSizingConfig(
        max_position_size_pct=0.10,  # 10% max per position
        risk_per_trade_pct=0.02,     # 2% risk per trade
    ),
)

# Create trading signal
signal = TradingSignal(
    signal_id="sig_001",
    ticker="AAPL",
    timestamp=datetime.now(),
    action="buy",
    confidence=0.85,
    current_price=Decimal("150.00"),
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
    position_size_pct=0.05,  # 5% of portfolio
    signal_type="momentum",
    strategy="catalyst_v1",
)

# Execute signal
result = await executor.execute_signal(signal, use_bracket_order=True)

if result.success:
    print(f"Order placed: {result.quantity} shares")
    if result.bracket_order:
        print(f"Entry: {result.bracket_order.entry_order.order_id}")
        print(f"Stop: {result.bracket_order.stop_loss_order.order_id}")
        print(f"Target: {result.bracket_order.take_profit_order.order_id}")
else:
    print(f"Execution failed: {result.error_message}")

# Monitor pending orders
filled_orders = await executor.monitor_pending_orders()
print(f"Filled: {len(filled_orders)} orders")

# Get execution statistics
stats = await executor.get_execution_stats(days=30)
print(f"Total Orders: {stats['total_orders']}")
print(f"Fill Rate: {stats['fill_rate']*100:.1f}%")
```

### 4. PositionManager (`../portfolio/position_manager.py`)

Manages open positions, tracks P&L, and monitors risk levels.

**Key Features:**
- Real-time position tracking
- P&L calculation (unrealized and realized)
- Stop-loss and take-profit monitoring
- Auto-close on risk triggers
- Portfolio-level metrics
- Position history and performance analytics
- Database persistence

**Database Schema:**
```sql
CREATE TABLE positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    opened_at TIMESTAMP NOT NULL,
    ...
);

CREATE TABLE closed_positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    realized_pnl REAL NOT NULL,
    realized_pnl_pct REAL NOT NULL,
    exit_reason TEXT,
    closed_at TIMESTAMP NOT NULL,
    ...
);
```

**Usage:**
```python
from catalyst_bot.portfolio import PositionManager
from decimal import Decimal

# Initialize
manager = PositionManager(broker=broker)

# Open position from filled order
position = await manager.open_position(
    order=filled_order,
    signal_id="sig_001",
    strategy="catalyst_v1",
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
)

# Update prices (should be called periodically)
await manager.update_position_prices({
    "AAPL": Decimal("155.00"),
    "MSFT": Decimal("352.00"),
})

# Check for triggered stops
stop_losses = await manager.check_stop_losses()
take_profits = await manager.check_take_profits()

# Auto-close triggered positions
closed = await manager.auto_close_triggered_positions()
for pos in closed:
    print(f"Closed {pos.ticker}: P&L ${pos.realized_pnl:.2f}")

# Get portfolio metrics
account = await broker.get_account()
metrics = manager.calculate_portfolio_metrics(account_value=account.equity)

print(f"Total Positions: {metrics.total_positions}")
print(f"Total Exposure: ${metrics.total_exposure}")
print(f"Unrealized P&L: ${metrics.total_unrealized_pnl}")
print(f"Positions at Stop: {metrics.positions_at_stop_loss}")

# Get performance statistics
stats = manager.get_performance_stats(days=30)
print(f"Total Trades: {stats['total_trades']}")
print(f"Win Rate: {stats['win_rate']*100:.1f}%")
print(f"Total P&L: ${stats['total_pnl']:.2f}")
```

## Complete Integration Example

See `integration_example.py` for a complete working example that demonstrates:
1. Connecting to broker
2. Processing trading signals
3. Executing orders with position sizing
4. Managing positions
5. Monitoring stop-losses and take-profits
6. Generating performance reports

**Run the example:**
```bash
# Set up credentials
export ALPACA_API_KEY="your_paper_trading_key"
export ALPACA_API_SECRET="your_paper_trading_secret"

# Run example
python -m catalyst_bot.broker.integration_example
```

## Trading Workflow

### 1. Signal Generation
```python
# Your signal generation logic produces TradingSignal objects
signal = TradingSignal(
    signal_id="unique_id",
    ticker="AAPL",
    action="buy",
    confidence=0.85,
    current_price=Decimal("150.00"),
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
)
```

### 2. Order Execution
```python
# OrderExecutor handles position sizing and order placement
result = await executor.execute_signal(signal, use_bracket_order=True)
```

### 3. Position Management
```python
# PositionManager tracks the position
if result.success and result.bracket_order.entry_order.is_filled():
    position = await manager.open_position(
        order=result.bracket_order.entry_order,
        signal_id=signal.signal_id,
        stop_loss_price=signal.stop_loss_price,
        take_profit_price=signal.take_profit_price,
    )
```

### 4. Monitoring Loop
```python
# Periodic monitoring (e.g., every minute)
while trading:
    # Update prices
    await manager.update_position_prices()

    # Auto-close triggered positions
    closed = await manager.auto_close_triggered_positions()

    # Check pending orders
    filled = await executor.monitor_pending_orders()

    await asyncio.sleep(60)
```

### 5. Performance Tracking
```python
# Get portfolio summary
metrics = manager.calculate_portfolio_metrics()
stats = manager.get_performance_stats(days=30)

# Log or report metrics
logger.info(f"P&L: ${metrics.total_unrealized_pnl:.2f}")
logger.info(f"Win Rate: {stats['win_rate']*100:.1f}%")
```

## Error Handling

All components use custom exceptions for clear error handling:

```python
from catalyst_bot.broker import (
    BrokerError,
    BrokerConnectionError,
    BrokerAuthenticationError,
    OrderRejectedError,
    InsufficientFundsError,
    RateLimitError,
)

try:
    order = await broker.place_order(...)
except InsufficientFundsError:
    logger.error("Not enough buying power")
except OrderRejectedError as e:
    logger.error(f"Order rejected: {e}")
except RateLimitError:
    logger.warning("Rate limit hit, retrying...")
    await asyncio.sleep(60)
except BrokerError as e:
    logger.error(f"Broker error: {e}")
```

## Database Schema

All components use SQLite for persistence. The database is automatically created at:
- Default: `data/trading.db`
- Configurable via `db_path` parameter

**Tables:**
- `executed_orders`: All orders submitted to broker
- `positions`: Currently open positions
- `closed_positions`: Historical closed positions

**Access the database:**
```bash
sqlite3 data/trading.db

# Query recent orders
SELECT ticker, side, quantity, status, submitted_at
FROM executed_orders
ORDER BY submitted_at DESC
LIMIT 10;

# Query open positions
SELECT ticker, quantity, entry_price, current_price, unrealized_pnl
FROM positions;

# Query closed positions with P&L
SELECT ticker, realized_pnl, realized_pnl_pct, exit_reason, closed_at
FROM closed_positions
ORDER BY closed_at DESC
LIMIT 10;
```

## Testing

### Paper Trading

All components support paper trading through Alpaca's paper trading API:

```python
broker = AlpacaBrokerClient(paper_trading=True)  # Paper trading
broker = AlpacaBrokerClient(paper_trading=False)  # Live trading (use with caution!)
```

### Unit Testing

TODO: Each component includes example usage in its `__main__` block. Run individually:

```bash
# Test broker interface
python -m catalyst_bot.broker.alpaca_client

# Test order executor
python -m catalyst_bot.execution.order_executor

# Test position manager
python -m catalyst_bot.portfolio.position_manager
```

## Next Steps (TODOs)

### Immediate
1. **Fill in TODO comments** in all files with actual implementations
2. **Test with paper trading** using real Alpaca credentials
3. **Add comprehensive unit tests** for each component
4. **Integrate with signal generation** from existing catalyst_bot analysis

### Phase 2
1. **Add risk manager** (max drawdown, correlation checks, etc.)
2. **Add performance analyzer** (Sharpe ratio, max drawdown, etc.)
3. **Add WebSocket support** for real-time price updates
4. **Add additional brokers** (Interactive Brokers, TD Ameritrade, etc.)

### Phase 3
1. **Add strategy backtesting** integration
2. **Add paper trading simulator** (no broker required)
3. **Add performance dashboard** (web UI)
4. **Add ML-based position sizing**

## Dependencies

Required packages:
```txt
aiohttp>=3.8.0  # For async HTTP requests
```

Optional packages:
```txt
alpaca-trade-api>=3.0.0  # Official Alpaca SDK (alternative to our implementation)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Trading Signal                           │
│              (from catalyst_bot analysis)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    OrderExecutor                             │
│  - Position sizing                                           │
│  - Signal → Order conversion                                 │
│  - Bracket order creation                                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  BrokerInterface                             │
│            (AlpacaBrokerClient)                              │
│  - Order placement                                           │
│  - Position retrieval                                        │
│  - Account management                                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  PositionManager                             │
│  - Position tracking                                         │
│  - P&L calculation                                           │
│  - Stop-loss monitoring                                      │
│  - Performance analytics                                     │
└─────────────────────────────────────────────────────────────┘
```

## Support

For questions or issues:
1. Check the example code in `integration_example.py`
2. Review the inline documentation and docstrings
3. Check the TODO comments for implementation guidance
4. Refer to Alpaca API documentation: https://alpaca.markets/docs/

## License

This code is part of the catalyst-bot project.
