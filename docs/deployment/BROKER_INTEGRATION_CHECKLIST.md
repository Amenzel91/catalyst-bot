# Broker Integration Implementation Checklist

This checklist guides you through implementing the broker integration components using Claude Code or Codex CLI.

## Phase 1: Setup and Testing

### 1.1 Environment Setup
- [ ] Set up Alpaca paper trading account at https://alpaca.markets
- [ ] Get paper trading API credentials
- [ ] Set environment variables:
  ```bash
  export ALPACA_API_KEY="PK..."
  export ALPACA_API_SECRET="..."
  ```
- [ ] Install dependencies:
  ```bash
  pip install aiohttp
  ```

### 1.2 Verify Scaffolding
- [ ] Review `/home/user/catalyst-bot/src/catalyst_bot/broker/broker_interface.py`
- [ ] Review `/home/user/catalyst-bot/src/catalyst_bot/broker/alpaca_client.py`
- [ ] Review `/home/user/catalyst-bot/src/catalyst_bot/execution/order_executor.py`
- [ ] Review `/home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py`
- [ ] Read `/home/user/catalyst-bot/src/catalyst_bot/broker/README.md`

## Phase 2: Alpaca Broker Client Implementation

### 2.1 Connection Management (`alpaca_client.py`)
- [ ] Implement `_test_connection()` method
  - Make test request to `/v2/account`
  - Parse response and verify authentication
  - Handle 401 authentication errors

- [ ] Complete `_request()` method
  - Add rate limit checking before requests
  - Implement exponential backoff for retries
  - Parse rate limit headers from response
  - Handle 429 rate limit errors

- [ ] Implement `_update_rate_limits()` method
  - Parse `X-RateLimit-Remaining` header
  - Parse `X-RateLimit-Reset` header
  - Update internal tracking

### 2.2 Account Operations (`alpaca_client.py`)
- [ ] Complete `_parse_account()` method
  - Convert string values to Decimal
  - Parse ISO 8601 timestamps
  - Map Alpaca status to AccountStatus enum
  - Handle missing fields gracefully

### 2.3 Position Management (`alpaca_client.py`)
- [ ] Complete `_parse_position()` method
  - Map all Alpaca position fields
  - Calculate P&L percentages
  - Handle long/short positions
  - Parse timestamps

### 2.4 Order Management (`alpaca_client.py`)
- [ ] Complete `place_order()` method
  - Validate order parameters
  - Build request payload
  - Handle insufficient funds errors
  - Handle order rejection errors

- [ ] Complete `place_bracket_order()` method
  - Build bracket order payload with `order_class: "bracket"`
  - Add `take_profit` and `stop_loss` objects
  - Parse response with legs[] array
  - Extract and return all three orders

- [ ] Complete `_parse_order()` method
  - Map all Alpaca order fields
  - Parse timestamps (ISO 8601)
  - Handle optional fields
  - Parse order legs for bracket orders

### 2.5 Utility Methods (`alpaca_client.py`)
- [ ] Complete `_parse_timestamp()` method
  - Handle ISO 8601 format: "2021-01-01T12:00:00.000000Z"
  - Handle timezone conversion
  - Return None for invalid timestamps

## Phase 3: Order Executor Implementation

### 3.1 Position Sizing (`order_executor.py`)
- [ ] Complete `calculate_position_size()` method
  - Implement percentage-based sizing
  - Implement risk-based sizing using stop-loss distance
  - Add Kelly criterion sizing (optional)
  - Apply min/max constraints

- [ ] Complete `_calculate_risk_based_size()` method
  - Calculate risk per share (entry - stop loss)
  - Calculate max risk dollars (account * risk_pct)
  - Calculate shares = max_risk / risk_per_share

### 3.2 Signal Execution (`order_executor.py`)
- [ ] Complete `execute_signal()` method
  - Validate signal is actionable
  - Check account is tradeable
  - Fetch current price if not provided
  - Calculate position size
  - Check buying power
  - Execute order (simple or bracket)

- [ ] Implement price fetching
  - Add method to get current price for ticker
  - Integrate with market data provider
  - Handle price fetch failures gracefully

### 3.3 Order Monitoring (`order_executor.py`)
- [ ] Complete `monitor_pending_orders()` method
  - Fetch latest status for each pending order
  - Update database with new status
  - Move filled orders to filled tracking
  - Remove cancelled/rejected orders

## Phase 4: Position Manager Implementation

### 4.1 Position Management (`position_manager.py`)
- [ ] Complete `open_position()` method
  - Validate order is filled
  - Calculate initial position metrics
  - Determine position side from order
  - Save to database and cache

- [ ] Complete `close_position()` method
  - Fetch current position
  - Close via broker API
  - Wait for fill (implement polling)
  - Calculate realized P&L
  - Save to closed_positions table
  - Remove from open positions

### 4.2 Price Updates (`position_manager.py`)
- [ ] Complete `update_position_prices()` method
  - Fetch prices for all open positions
  - Update each position's current_price
  - Recalculate market_value and unrealized_pnl
  - Save updates to database

- [ ] Complete `_fetch_current_prices()` method
  - Integrate with market data provider
  - Fetch prices for all tickers
  - Handle fetch failures gracefully
  - Return dict of ticker -> price

### 4.3 Database Operations (`position_manager.py`)
- [ ] Complete `get_closed_positions()` query
  - Parse SQL rows to ClosedPosition objects
  - Map column indices to fields
  - Handle NULL values

- [ ] Test all database operations
  - Insert positions
  - Update positions
  - Query positions
  - Delete positions
  - Query performance stats

## Phase 5: Integration and Testing

### 5.1 Unit Testing
- [ ] Test `BrokerInterface` with mock implementation
- [ ] Test `AlpacaBrokerClient` with paper trading
  - Connection and authentication
  - Account retrieval
  - Position retrieval
  - Order placement (market orders)
  - Order placement (bracket orders)
  - Order cancellation

- [ ] Test `OrderExecutor`
  - Position sizing calculations
  - Signal validation
  - Order execution
  - Database logging

- [ ] Test `PositionManager`
  - Position opening
  - Position closing
  - Price updates
  - Stop-loss detection
  - Take-profit detection
  - Portfolio metrics calculation

### 5.2 Integration Testing
- [ ] Run `integration_example.py` demo
- [ ] Test complete workflow:
  1. Connect to broker
  2. Process trading signal
  3. Execute order with position sizing
  4. Track position
  5. Update prices
  6. Monitor stop-loss/take-profit
  7. Close position
  8. Calculate performance

### 5.3 Error Handling Testing
- [ ] Test insufficient funds scenario
- [ ] Test order rejection scenario
- [ ] Test rate limiting scenario
- [ ] Test connection failures
- [ ] Test authentication failures
- [ ] Test position not found scenario
- [ ] Test invalid order parameters

## Phase 6: Catalyst Bot Integration

### 6.1 Signal Conversion
- [ ] Create adapter to convert catalyst analysis to TradingSignal
- [ ] Map catalyst confidence to signal confidence
- [ ] Calculate appropriate stop-loss levels
- [ ] Calculate appropriate take-profit levels
- [ ] Set position sizing parameters

### 6.2 Configuration
- [ ] Add broker settings to `config.py`:
  ```python
  @dataclass
  class Settings:
      # Broker settings
      trading_enabled: bool = False
      paper_trading: bool = True
      max_position_pct: float = 0.10
      risk_per_trade_pct: float = 0.02
      auto_close_enabled: bool = True
  ```

### 6.3 Integration Points
- [ ] Add broker initialization to `runner.py`
- [ ] Add signal processing to analysis pipeline
- [ ] Add position monitoring loop
- [ ] Add performance reporting
- [ ] Add Discord notifications for trades

## Phase 7: Production Readiness

### 7.1 Additional Features
- [ ] Add WebSocket support for real-time prices
- [ ] Add risk manager component
  - Max drawdown monitoring
  - Correlation checks
  - Daily loss limits

- [ ] Add performance analyzer
  - Sharpe ratio calculation
  - Sortino ratio calculation
  - Maximum drawdown tracking
  - Win/loss streaks

- [ ] Add trading dashboard (optional)
  - Web UI for monitoring
  - Real-time position display
  - Performance charts

### 7.2 Safety Features
- [ ] Add pre-trade validation
  - Check market hours
  - Verify ticker exists
  - Check halts/restrictions

- [ ] Add kill switch
  - Emergency stop all trading
  - Close all positions
  - Cancel all orders

- [ ] Add position limits
  - Max positions per ticker
  - Max total positions
  - Max portfolio exposure

### 7.3 Monitoring and Alerting
- [ ] Set up health monitoring
  - Broker connection status
  - Order fill rates
  - Position P&L

- [ ] Add Discord/Slack alerts
  - Order fills
  - Position closures
  - Stop-loss triggers
  - Error conditions

## Implementation Priority

### High Priority (Week 1)
1. ✅ Alpaca connection and authentication
2. ✅ Account and position retrieval
3. ✅ Basic order placement (market orders)
4. ✅ Position tracking
5. ✅ Database operations

### Medium Priority (Week 2)
1. ✅ Bracket orders
2. ✅ Position sizing algorithms
3. ✅ Stop-loss/take-profit monitoring
4. ✅ Performance analytics
5. ✅ Integration with catalyst signals

### Low Priority (Week 3+)
1. ⏳ WebSocket real-time prices
2. ⏳ Risk manager
3. ⏳ Performance analyzer
4. ⏳ Trading dashboard
5. ⏳ Additional broker integrations

## Success Criteria

The implementation is complete when:
- [ ] All TODOs in code are implemented
- [ ] All unit tests pass
- [ ] Integration example runs successfully
- [ ] Can place orders in paper trading
- [ ] Can track positions and P&L
- [ ] Can close positions automatically on triggers
- [ ] Performance stats are accurate
- [ ] Database persistence works correctly
- [ ] Error handling works as expected
- [ ] Documentation is updated with any changes

## Getting Help

If you encounter issues:
1. Check the inline TODO comments for implementation guidance
2. Review the example usage in each file's `__main__` block
3. Read the comprehensive documentation in `README.md`
4. Refer to Alpaca API docs: https://alpaca.markets/docs/api-references/trading-api/
5. Check the integration example: `integration_example.py`

## Quick Reference

**Test Connection:**
```bash
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
```

**Run Integration Example:**
```bash
python -m catalyst_bot.broker.integration_example
```

**Check Database:**
```bash
sqlite3 data/trading.db "SELECT * FROM executed_orders LIMIT 5;"
sqlite3 data/trading.db "SELECT * FROM positions;"
sqlite3 data/trading.db "SELECT * FROM closed_positions ORDER BY closed_at DESC LIMIT 10;"
```
