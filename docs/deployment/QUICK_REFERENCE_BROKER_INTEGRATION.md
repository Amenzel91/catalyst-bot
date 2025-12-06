# Broker Integration Quick Reference

## File Locations

### Core Components
```
/home/user/catalyst-bot/src/catalyst_bot/broker/broker_interface.py    (891 lines)
/home/user/catalyst-bot/src/catalyst_bot/broker/alpaca_client.py       (1,057 lines)
/home/user/catalyst-bot/src/catalyst_bot/execution/order_executor.py   (917 lines)
/home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py (1,147 lines)
```

### Documentation
```
/home/user/catalyst-bot/src/catalyst_bot/broker/README.md
/home/user/catalyst-bot/docs/broker-integration-scaffolding-complete.md
/home/user/catalyst-bot/docs/BROKER_INTEGRATION_CHECKLIST.md
```

### Example & Tests
```
/home/user/catalyst-bot/src/catalyst_bot/broker/integration_example.py
```

## Quick Import Reference

```python
# Broker components
from catalyst_bot.broker import (
    AlpacaBrokerClient,
    BrokerInterface,
    Order,
    Position,
    Account,
    BracketOrder,
    BracketOrderParams,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    PositionSide,
    AccountStatus,
)

# Execution components
from catalyst_bot.execution import (
    OrderExecutor,
    TradingSignal,
    ExecutionResult,
    PositionSizingConfig,
)

# Portfolio components
from catalyst_bot.portfolio import (
    PositionManager,
    ManagedPosition,
    ClosedPosition,
    PortfolioMetrics,
)
```

## Common Operations

### Connect to Broker
```python
broker = AlpacaBrokerClient(paper_trading=True)
await broker.connect()

# Check connection
is_connected = await broker.is_connected()

# Get account
account = await broker.get_account()
print(f"Buying Power: ${account.buying_power}")
```

### Place Orders
```python
# Market order
order = await broker.place_order(
    ticker="AAPL",
    side=OrderSide.BUY,
    quantity=10,
    order_type=OrderType.MARKET,
)

# Bracket order (entry + stop + target)
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
```

### Execute Signals
```python
# Create signal
signal = TradingSignal(
    signal_id="sig_001",
    ticker="AAPL",
    action="buy",
    confidence=0.85,
    current_price=Decimal("150.00"),
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
)

# Execute
executor = OrderExecutor(broker=broker)
result = await executor.execute_signal(signal, use_bracket_order=True)
```

### Manage Positions
```python
manager = PositionManager(broker=broker)

# Open position
position = await manager.open_position(
    order=filled_order,
    signal_id="sig_001",
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
)

# Update prices
await manager.update_position_prices({"AAPL": Decimal("155.00")})

# Auto-close triggered
closed = await manager.auto_close_triggered_positions()

# Get metrics
metrics = manager.calculate_portfolio_metrics()
```

## Database Queries

```bash
# Open database
sqlite3 /home/user/catalyst-bot/data/trading.db

# Recent orders
SELECT ticker, side, quantity, status, submitted_at
FROM executed_orders
ORDER BY submitted_at DESC
LIMIT 10;

# Open positions
SELECT ticker, quantity, entry_price, current_price, unrealized_pnl
FROM positions;

# Closed positions with P&L
SELECT ticker, realized_pnl, realized_pnl_pct, exit_reason, closed_at
FROM closed_positions
ORDER BY closed_at DESC
LIMIT 10;

# Performance summary
SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winners,
    AVG(realized_pnl) as avg_pnl,
    SUM(realized_pnl) as total_pnl
FROM closed_positions
WHERE closed_at >= datetime('now', '-30 days');
```

## Testing Commands

```bash
# Test broker connection
python -c "
import asyncio
from catalyst_bot.broker import AlpacaBrokerClient

async def test():
    broker = AlpacaBrokerClient(paper_trading=True)
    await broker.connect()
    account = await broker.get_account()
    print(f'Connected! Balance: \${account.cash}')
    await broker.disconnect()

asyncio.run(test())
"

# Run integration example
python -m catalyst_bot.broker.integration_example

# Test individual components
python -m catalyst_bot.broker.alpaca_client
python -m catalyst_bot.execution.order_executor
python -m catalyst_bot.portfolio.position_manager
```

## Environment Setup

```bash
# Alpaca credentials (paper trading)
export ALPACA_API_KEY="PK..."
export ALPACA_API_SECRET="..."

# Install dependencies
pip install aiohttp

# Verify installation
python -c "import aiohttp; print('aiohttp installed')"
```

## Error Handling

```python
from catalyst_bot.broker import (
    BrokerError,
    OrderRejectedError,
    InsufficientFundsError,
    RateLimitError,
)

try:
    order = await broker.place_order(...)
except InsufficientFundsError:
    print("Not enough buying power")
except OrderRejectedError as e:
    print(f"Order rejected: {e}")
except RateLimitError:
    print("Rate limit hit, waiting...")
    await asyncio.sleep(60)
except BrokerError as e:
    print(f"Broker error: {e}")
```

## Implementation TODOs

### High Priority
1. `AlpacaBrokerClient._request()` - Add rate limit checking
2. `AlpacaBrokerClient._parse_account()` - Convert response to Account
3. `AlpacaBrokerClient._parse_order()` - Convert response to Order
4. `OrderExecutor.calculate_position_size()` - Implement Kelly criterion
5. `PositionManager._fetch_current_prices()` - Integrate market data

### Medium Priority
1. `OrderExecutor.execute_signal()` - Add price fetching fallback
2. `PositionManager.update_position_prices()` - Add WebSocket support
3. `PositionManager.get_closed_positions()` - Parse SQL rows
4. All error handling TODO comments
5. All logging TODO comments

### Low Priority
1. WebSocket integration for real-time prices
2. Additional broker implementations
3. Advanced position sizing (Kelly)
4. Risk manager integration
5. Performance dashboard

## Key Configuration

```python
# Position sizing configuration
config = PositionSizingConfig(
    max_position_size_pct=0.10,      # 10% max per position
    min_position_size_dollars=100,    # $100 minimum
    max_position_size_dollars=10000,  # $10k maximum
    risk_per_trade_pct=0.02,         # Risk 2% per trade
    max_leverage=1.0,                 # No leverage
)

# Initialize components
broker = AlpacaBrokerClient(paper_trading=True)
executor = OrderExecutor(broker=broker, position_sizing_config=config)
manager = PositionManager(broker=broker)
```

## Performance Metrics

```python
# Portfolio metrics
metrics = manager.calculate_portfolio_metrics(account_value=account.equity)
print(f"Total Positions: {metrics.total_positions}")
print(f"Total Exposure: ${metrics.total_exposure}")
print(f"Unrealized P&L: ${metrics.total_unrealized_pnl}")
print(f"Largest Position: {metrics.largest_position_pct*100:.1f}%")

# Performance stats
stats = manager.get_performance_stats(days=30)
print(f"Total Trades: {stats['total_trades']}")
print(f"Win Rate: {stats['win_rate']*100:.1f}%")
print(f"Total P&L: ${stats['total_pnl']:.2f}")
print(f"Best Trade: ${stats['best_trade']:.2f}")
```

## Monitoring Loop Example

```python
async def monitor_positions():
    """Monitor positions every minute"""
    while True:
        # Update prices
        await manager.update_position_prices()

        # Auto-close triggered positions
        closed = await manager.auto_close_triggered_positions()

        # Check pending orders
        filled = await executor.monitor_pending_orders()

        # Log status
        metrics = manager.calculate_portfolio_metrics()
        logger.info(f"P&L: ${metrics.total_unrealized_pnl:.2f}")

        # Wait 1 minute
        await asyncio.sleep(60)
```

## Useful Links

- **Alpaca API Docs**: https://alpaca.markets/docs/api-references/trading-api/
- **Paper Trading Setup**: https://alpaca.markets/docs/trading/paper-trading/
- **Alpaca Dashboard**: https://app.alpaca.markets/paper/dashboard/overview

## Support Files

- Main README: `src/catalyst_bot/broker/README.md`
- Complete Guide: `docs/broker-integration-scaffolding-complete.md`
- Checklist: `docs/BROKER_INTEGRATION_CHECKLIST.md`
- Example: `src/catalyst_bot/broker/integration_example.py`

---

**Total Code: 4,656 lines**
**Status: Scaffolding Complete - Ready for Implementation**
