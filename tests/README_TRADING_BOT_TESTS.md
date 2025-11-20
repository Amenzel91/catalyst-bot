# Paper Trading Bot - Test Infrastructure

**Created:** January 2025
**Framework:** pytest 7.x
**Total Test Scaffolds:** ~3,174 lines across 6 test modules

---

## Overview

This directory contains comprehensive test scaffolds for the Paper Trading Bot implementation. All tests are ready to be populated with actual implementations as the trading bot components are developed.

## Directory Structure

```
tests/
├── conftest.py                          # Shared fixtures (extended with trading fixtures)
├── fixtures/                            # Test data and mocks
│   ├── __init__.py
│   ├── mock_alpaca.py                  # Mock Alpaca API client (~358 lines)
│   ├── mock_market_data.py             # Mock market data provider (~253 lines)
│   ├── sample_alerts.py                # Sample trading alerts (~187 lines)
│   └── test_data_generator.py          # Test data generators (~255 lines)
├── broker/                              # Broker integration tests
│   ├── __init__.py
│   └── test_alpaca_client.py           # Alpaca API tests (~475 lines)
├── execution/                           # Order execution tests
│   ├── __init__.py
│   └── test_order_executor.py          # Order execution tests (~499 lines)
├── portfolio/                           # Portfolio management tests
│   ├── __init__.py
│   └── test_position_manager.py        # Position manager tests (~494 lines)
├── risk/                                # Risk management tests
│   ├── __init__.py
│   └── test_risk_manager.py            # Risk manager tests (~538 lines)
├── ml/                                  # Machine learning tests
│   ├── __init__.py
│   └── test_trading_env.py             # RL environment tests (~546 lines)
└── integration/                         # End-to-end tests
    ├── __init__.py
    └── test_end_to_end.py              # E2E integration tests (~622 lines)
```

## Test Categories

### 1. Unit Tests (60% of test suite)

**Broker Tests** (`tests/broker/test_alpaca_client.py`):
- Account information retrieval
- Position management (get, close)
- Order submission (market, limit, stop)
- Order management (get, cancel)
- Error handling and retry logic
- Rate limiting

**Execution Tests** (`tests/execution/test_order_executor.py`):
- Signal processing and filtering
- Position sizing (fixed, percentage, Kelly Criterion)
- Risk validation integration
- Bracket order creation
- Alert metadata processing
- Database persistence

**Portfolio Tests** (`tests/portfolio/test_position_manager.py`):
- Position opening/closing
- P&L calculation (realized and unrealized)
- Stop-loss and take-profit detection
- Position tracking and retrieval
- Database operations
- Portfolio statistics

**Risk Tests** (`tests/risk/test_risk_manager.py`):
- Position size limits
- Daily loss limits
- Circuit breaker logic
- Kelly Criterion calculation
- Portfolio risk aggregation
- Risk reporting

**ML Tests** (`tests/ml/test_trading_env.py`):
- Environment initialization and reset
- State space construction
- Action space validation
- Step function mechanics
- Reward calculation
- Episode metrics

### 2. Integration Tests (30% of test suite)

Located in individual test files with `@pytest.mark.integration` decorator.

### 3. End-to-End Tests (10% of test suite)

**E2E Tests** (`tests/integration/test_end_to_end.py`):
- Complete profitable trade flow
- Stop-loss triggered trade flow
- Circuit breaker activation
- Real-time data pipeline
- Multiple concurrent alerts
- System recovery from errors
- Complete trading day simulation

## Test Fixtures

### Shared Fixtures (conftest.py)

```python
test_config          # Trading bot configuration
test_db              # Temporary SQLite database
mock_account         # Mock Alpaca account
mock_position        # Mock Alpaca position
mock_order           # Mock Alpaca order
sample_alert         # Sample trading alert
sample_market_data   # Sample OHLCV data
reset_random_seed    # Deterministic random seed
```

### Mock Objects

**MockAlpacaClient** - Full Alpaca API simulation:
- Account management
- Position tracking
- Order execution
- State management
- Error simulation

**MockMarketDataProvider** - Market data simulation:
- Live quotes
- Historical bars
- Intraday data
- Quote streams

**Sample Alert Generators**:
- `create_breakout_alert()`
- `create_earnings_alert()`
- `create_insider_buying_alert()`
- `create_analyst_upgrade_alert()`
- `create_merger_acquisition_alert()`

**Test Data Generators**:
- `generate_market_data()` - Realistic OHLCV data
- `generate_trade_history()` - Synthetic trade logs
- `generate_portfolio_snapshot()` - Portfolio states
- `generate_backtesting_results()` - Complete backtest results

## Running Tests

### Run All Tests
```bash
pytest tests/
```

### Run Specific Test Categories
```bash
# Unit tests only
pytest -m "not integration and not e2e"

# Integration tests
pytest -m integration

# End-to-end tests
pytest -m e2e

# Specific module
pytest tests/broker/
pytest tests/risk/
```

### Run with Coverage
```bash
pytest --cov=catalyst_bot --cov-report=html --cov-report=term
```

### Run Fast Tests Only
```bash
pytest -m "not slow"
```

## Test Markers

Tests use pytest markers for categorization:

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.e2e          # End-to-end tests
@pytest.mark.slow         # Slow-running tests (>5 seconds)
@pytest.mark.broker       # Broker-related tests
@pytest.mark.risk         # Risk management tests
@pytest.mark.ml           # Machine learning tests
```

## Implementation Status

**Status:** ⚠️ SCAFFOLDS READY - Implementation Required

All test files contain:
- ✅ Test function signatures
- ✅ Docstrings with test scenarios
- ✅ TODO comments for implementation
- ✅ Mock fixtures and data generators
- ✅ Parametrized test examples
- ✅ AAA (Arrange-Act-Assert) structure

Most test assertions are commented out with `pass` placeholders, waiting for actual component implementation.

## Next Steps

1. **Implement Core Components**:
   - `catalyst_bot/broker/alpaca_client.py`
   - `catalyst_bot/execution/order_executor.py`
   - `catalyst_bot/portfolio/position_manager.py`
   - `catalyst_bot/risk/risk_manager.py`
   - `catalyst_bot/ml/trading_env.py`

2. **Uncomment Test Assertions**:
   - Remove `pass` placeholders
   - Uncomment assertion statements
   - Update imports with actual modules

3. **Run Tests**:
   - Start with unit tests
   - Progress to integration tests
   - Validate with E2E tests

4. **Achieve Coverage Targets**:
   - Overall: 85%+
   - Broker: 90%+
   - Execution: 90%+
   - Portfolio: 85%+
   - Risk: 95%+
   - ML: 80%+

## Test Development Guidelines

### Writing New Tests

1. **Use Existing Fixtures**: Leverage shared fixtures from conftest.py
2. **Follow AAA Pattern**: Arrange, Act, Assert structure
3. **Clear Test Names**: `test_<component>_<scenario>_<expected_outcome>`
4. **Add Markers**: Categorize with appropriate pytest markers
5. **Document Scenarios**: Use docstrings to explain test scenarios

### Example Test Structure

```python
def test_position_manager_calculates_pnl_correctly(test_db):
    """
    Test P&L calculation for a winning trade.

    GIVEN a position opened at $100
    WHEN the price rises to $110
    THEN unrealized P&L should be $10 per share
    """
    # ARRANGE
    position_manager = PositionManager(test_db)
    position = position_manager.open_position("AAPL", 100, 100.00)

    # ACT
    position_manager.update_price("AAPL", 110.00)
    pnl = position_manager.calculate_unrealized_pnl("AAPL")

    # ASSERT
    assert pnl == 1000.00  # ($110 - $100) * 100 shares
```

## Mock Usage Patterns

### Using MockAlpacaClient

```python
def test_order_submission(mock_alpaca_client):
    # Create order request
    order_request = Mock()
    order_request.symbol = "AAPL"
    order_request.qty = 100
    order_request.side = "buy"
    order_request.type = "market"

    # Submit order
    order = mock_alpaca_client.submit_order(order_request)

    # Verify
    assert order.status == "filled"
    assert order.symbol == "AAPL"
```

### Simulating Errors

```python
def test_api_error_handling(mock_alpaca_client):
    # Configure mock to fail
    mock_alpaca_client.fail_next_order = True
    mock_alpaca_client.failure_reason = "API timeout"

    # Attempt order
    with pytest.raises(Exception, match="API timeout"):
        mock_alpaca_client.submit_order(order_request)
```

## Testing Strategy Reference

For complete testing strategy, see:
- **Full Document**: `/home/user/catalyst-bot/docs/paper-trading-bot-testing-strategy.md`
- **Implementation Plan**: `/home/user/catalyst-bot/docs/paper-trading-bot-implementation-plan.md`

---

## Summary

This test infrastructure provides:

- **~3,174 lines** of test scaffolds across 6 modules
- **150+ test functions** ready for implementation
- **Comprehensive mock objects** for external dependencies
- **Realistic test data generators** for market data and alerts
- **Clear test organization** following pytest best practices
- **Integration with CI/CD** ready for automated testing

**The scaffolds are production-ready and waiting for component implementation to begin active testing.**

---

**Questions or Issues?**
Refer to the comprehensive testing strategy document for detailed guidance on test implementation, coverage requirements, and best practices.
