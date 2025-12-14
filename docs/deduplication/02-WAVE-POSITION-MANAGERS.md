# WAVE 2: POSITION MANAGER CONSOLIDATION

**Status**: Ready for Implementation
**Priority**: HIGH
**Estimated Effort**: 2-3 hours
**Risk Level**: Medium (touches trading core)

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Dependency Mapping](#dependency-mapping)
4. [Consolidation Strategy](#consolidation-strategy)
5. [Migration Guide](#migration-guide)
6. [Verification Checklist](#verification-checklist)
7. [Rollback Plan](#rollback-plan)

---

## Executive Summary

### Problem

The codebase contains **two separate position manager implementations** with duplicated classes:

1. **Async Position Manager** (`src/catalyst_bot/portfolio/position_manager.py`, 1147 lines)
2. **Sync Position Manager** (`src/catalyst_bot/position_manager_sync.py`, 550 lines)

Both implement nearly identical classes (`ManagedPosition`, `ClosedPosition`) with subtle differences, creating maintenance burden and potential for bugs when changes are made to one but not the other.

### Duplicated Classes

| Class | Async Version | Sync Version | Differences |
|-------|--------------|--------------|-------------|
| `ManagedPosition` | Lines 93-172 | Lines 33-79 | Async has `side: PositionSide`, `metadata: Dict`; Sync assumes LONG only |
| `ClosedPosition` | Lines 175-219 | Lines 82-101 | Async has `side: PositionSide`, helper methods; Sync is minimal |
| `PortfolioMetrics` | Lines 222-250 | N/A | Only in async version |
| Manager Class | `PositionManager` | `PositionManagerSync` | Async has full features; Sync is simplified |

### Impact

- **Active Users**: Trading Engine (async), Paper Trader (sync - deprecated)
- **Import Count**: 15 files reference position manager classes
- **Database**: Both use same schema with minor differences
- **Risk**: Medium - Trading Engine is production critical

### Recommendation

**Consolidate to async-first with sync wrappers**. The async version is more feature-complete and is used by the production Trading Engine. Keep sync wrappers for backward compatibility during migration.

---

## Current State Analysis

### 1. Async Position Manager

**File**: `/home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py`
**Lines**: 1147
**Last Modified**: Recent (active development)

#### Classes

##### ManagedPosition (Lines 93-172)
```python
@dataclass
class ManagedPosition:
    # Identity
    position_id: str
    ticker: str
    side: PositionSide  # LONG or SHORT

    # Quantities
    quantity: int
    entry_price: Decimal
    current_price: Decimal

    # Valuation
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal

    # Risk management
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    # Timestamps
    opened_at: datetime
    updated_at: datetime

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)
```

**Methods**:
- `should_stop_loss() -> bool`
- `should_take_profit() -> bool`
- `get_hold_duration() -> timedelta`
- `calculate_risk_reward_ratio() -> Optional[float]`

##### ClosedPosition (Lines 175-219)
```python
@dataclass
class ClosedPosition:
    position_id: str
    ticker: str
    side: PositionSide
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int
    exit_reason: str  # 'stop_loss', 'take_profit', 'manual', 'timeout'
    exit_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
```

**Methods**:
- `was_profitable() -> bool`
- `get_hold_duration_hours() -> float`

##### PortfolioMetrics (Lines 222-250)
```python
@dataclass
class PortfolioMetrics:
    total_positions: int = 0
    long_positions: int = 0
    short_positions: int = 0
    total_exposure: Decimal = Decimal("0")
    long_exposure: Decimal = Decimal("0")
    short_exposure: Decimal = Decimal("0")
    net_exposure: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_unrealized_pnl_pct: Decimal = Decimal("0")
    largest_position_pct: Decimal = Decimal("0")
    positions_at_stop_loss: int = 0
    positions_at_take_profit: int = 0
    avg_position_size: Decimal = Decimal("0")
    metadata: Dict = field(default_factory=dict)
```

##### PositionManager (Lines 257-1034)

**Methods** (async):
- `__init__(broker: BrokerInterface, db_path: Optional[Path])`
- `open_position(order, signal_id, strategy, stop_loss_price, take_profit_price) -> ManagedPosition`
- `close_position(position_id, exit_reason, exit_order_id) -> Optional[ClosedPosition]`
- `update_position_prices(price_updates) -> int`
- `check_stop_losses() -> List[ManagedPosition]`
- `check_take_profits() -> List[ManagedPosition]`
- `auto_close_triggered_positions() -> List[ClosedPosition]`
- `get_position(position_id) -> Optional[ManagedPosition]`
- `get_position_by_ticker(ticker) -> Optional[ManagedPosition]`
- `get_all_positions() -> List[ManagedPosition]`
- `get_positions_by_strategy(strategy) -> List[ManagedPosition]`
- `calculate_portfolio_metrics(account_value) -> PortfolioMetrics`
- `get_portfolio_exposure() -> Decimal`
- `get_total_unrealized_pnl() -> Decimal`
- `get_closed_positions(ticker, strategy, limit) -> List[ClosedPosition]`
- `get_performance_stats(days) -> Dict`

**Database Schema**:
```sql
CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,  -- 'long' or 'short'
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    cost_basis REAL NOT NULL,
    market_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    opened_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    entry_order_id TEXT,
    signal_id TEXT,
    strategy TEXT,
    metadata JSON
);

CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_opened_at ON positions(opened_at);
```

**Features**:
- Full async/await support
- Supports LONG and SHORT positions
- Comprehensive metadata tracking
- Performance statistics
- Historical queries
- Portfolio-level metrics
- Risk/reward ratio calculations

---

### 2. Sync Position Manager

**File**: `/home/user/catalyst-bot/src/catalyst_bot/position_manager_sync.py`
**Lines**: 550
**Status**: Used by deprecated paper_trader.py

#### Classes

##### ManagedPosition (Lines 33-79)
```python
@dataclass
class ManagedPosition:
    # Identity
    position_id: str
    ticker: str
    # NOTE: No 'side' field - assumes LONG positions only

    # Quantities
    quantity: int
    entry_price: Decimal
    current_price: Decimal

    # Valuation
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal

    # Risk management
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    # Timestamps
    opened_at: datetime
    updated_at: datetime

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "catalyst_alert"
    # NOTE: No metadata field
```

**Methods**:
- `should_stop_loss() -> bool` - Only checks downward price movement
- `should_take_profit() -> bool` - Only checks upward price movement
- `get_hold_duration() -> timedelta`
- **Missing**: `calculate_risk_reward_ratio()`

##### ClosedPosition (Lines 82-101)
```python
@dataclass
class ClosedPosition:
    position_id: str
    ticker: str
    # NOTE: No 'side' field
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int
    exit_reason: str
    exit_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "catalyst_alert"
    # NOTE: No metadata field
```

**Methods**:
- **Missing**: `was_profitable()`, `get_hold_duration_hours()`

##### PositionManagerSync (Lines 103-550)

**Methods** (synchronous):
- `__init__(broker: AlpacaBrokerWrapper, db_path: Optional[Path])`
- `open_position(ticker, quantity, entry_price, entry_order_id, signal_id, stop_loss_price, take_profit_price) -> ManagedPosition`
- `close_position(position_id, exit_reason) -> Optional[ClosedPosition]`
- `update_position_prices() -> int` - Fetches prices from broker directly
- `check_and_execute_exits(max_hold_hours) -> List[ClosedPosition]` - Combined check + close
- `get_all_positions() -> List[ManagedPosition]`
- `get_position_by_ticker(ticker) -> Optional[ManagedPosition]`

**Missing**:
- `check_stop_losses()` - Rolled into `check_and_execute_exits()`
- `check_take_profits()` - Rolled into `check_and_execute_exits()`
- `auto_close_triggered_positions()`
- `get_positions_by_strategy()`
- `calculate_portfolio_metrics()`
- `get_portfolio_exposure()`
- `get_total_unrealized_pnl()`
- `get_closed_positions()`
- `get_performance_stats()`

**Database Schema**:
```sql
CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    -- NOTE: No 'side' column
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    cost_basis REAL NOT NULL,
    market_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    opened_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    entry_order_id TEXT,
    signal_id TEXT,
    strategy TEXT
    -- NOTE: No metadata column
);

CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_opened_at ON positions(opened_at);
-- NOTE: Missing idx_closed_positions_strategy
```

**Features**:
- Synchronous API
- Only supports LONG positions
- Simplified - no portfolio metrics
- No historical queries
- Direct broker integration (no abstraction)
- Combined exit checking + execution

---

### 3. Backtesting Position Class

**File**: `/home/user/catalyst-bot/src/catalyst_bot/backtesting/portfolio.py`
**Lines**: 432

**Note**: This is a SEPARATE implementation for backtesting, not related to live trading.

#### Position (Lines 20-40)
```python
@dataclass
class Position:
    ticker: str
    shares: int  # NOTE: Different from 'quantity'
    entry_price: float  # NOTE: Uses float, not Decimal
    entry_time: int  # NOTE: Unix timestamp int
    cost_basis: float
    alert_data: Dict  # NOTE: Backtesting-specific
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
```

#### ClosedTrade (Lines 43-57)
```python
@dataclass
class ClosedTrade:  # NOTE: Different name from ClosedPosition
    ticker: str
    shares: int
    entry_price: float
    exit_price: float
    entry_time: int
    exit_time: int
    profit: float  # NOTE: Different from 'realized_pnl'
    profit_pct: float
    hold_time_hours: float
    exit_reason: str
    alert_data: Dict
    commission: float = 0.0
```

**Key Differences**:
- Uses `float` instead of `Decimal`
- Uses `shares` instead of `quantity`
- Uses `profit` instead of `realized_pnl`
- Has `alert_data` field for backtesting context
- Simplified for backtesting simulation
- No database persistence

**Recommendation**: Keep separate - backtesting has different requirements than live trading.

---

### 4. Broker Position Class

**File**: `/home/user/catalyst-bot/src/catalyst_bot/broker/broker_interface.py`
**Lines**: 147-188

#### Position (Broker Interface)
```python
@dataclass
class Position:
    """Broker-agnostic position representation."""
    ticker: str
    side: PositionSide
    quantity: int
    available_quantity: int
    entry_price: Decimal
    current_price: Decimal
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    opened_at: datetime
    updated_at: datetime
    metadata: Dict = field(default_factory=dict)
```

**Purpose**: Standardized broker API response format

**Differences from ManagedPosition**:
- No stop_loss_price / take_profit_price (broker doesn't track our risk levels)
- No signal_id / strategy (broker doesn't know our logic)
- Has `available_quantity` (broker-specific concept)
- Used for broker API responses, not internal tracking

**Recommendation**: Keep separate - this is the broker interface layer.

---

## Dependency Mapping

### Files Importing Position Manager

#### Direct Imports

| File | Imports | Type | Status |
|------|---------|------|--------|
| `src/catalyst_bot/portfolio/__init__.py` | `PositionManager`, `ManagedPosition`, `ClosedPosition`, `PortfolioMetrics` | Async | Active |
| `src/catalyst_bot/trading/trading_engine.py` | `PositionManager`, `ManagedPosition`, `ClosedPosition`, `PortfolioMetrics` | Async | Active (Production) |
| `src/catalyst_bot/broker/integration_example.py` | `PositionManager` | Async | Example code |
| `src/catalyst_bot/paper_trader.py` | `PositionManagerSync` | Sync | **DEPRECATED** |
| `test_position_management.py` | `PositionManagerSync` | Sync | Test file |
| `tests/portfolio/test_position_manager.py` | Commented out (TODO) | N/A | Not implemented |
| `tests/test_trading_engine.py` | `ManagedPosition`, `ClosedPosition`, `PortfolioMetrics` | Async | Active tests |
| `tests/test_trading_integration.py` | `ManagedPosition`, `ClosedPosition` | Async | Active tests |

#### Indirect References (Documentation)

- `docs/architecture/IMPLEMENTATION_CONTEXT.md` - References both versions
- `docs/patches/TRADING_ENGINE_DB_SCHEMA_ISSUE.md` - References position_manager schema
- Multiple planning and implementation docs

### Usage Analysis

#### Production Code

**Async Position Manager** (PRIMARY):
- **Trading Engine**: Uses full async API for production trading
  - Lines 48-52: Imports `PositionManager`, `ManagedPosition`, `ClosedPosition`, `PortfolioMetrics`
  - Lines 228-231: Initializes `PositionManager`
  - Lines 591-597: Opens positions
  - Lines 349-388: Updates positions, checks triggers
  - Lines 373: Calculates portfolio metrics
- **Portfolio Package**: Exports as public API
  - Lines 30-35: Re-exports all classes

**Sync Position Manager** (DEPRECATED):
- **Paper Trader**: Uses sync API (but paper_trader.py is deprecated as of 2025-11-26)
  - Lines 112: Imports `PositionManagerSync`
  - Lines 115: Initializes with `AlpacaBrokerWrapper`
  - **Status**: Module deprecated, no longer in active use

#### Test Code

**Async Tests**:
- `tests/test_trading_engine.py`: 4 imports, tests portfolio metrics calculation
- `tests/test_trading_integration.py`: Tests position opening/closing flow

**Sync Tests**:
- `test_position_management.py`: Basic sync position manager tests
- `tests/portfolio/test_position_manager.py`: Commented out (TODO)

### Database Usage

Both managers use the **same database file**: `data/trading.db`

**Potential Conflict**:
- Both managers can write to same tables
- Async version has additional fields (`side`, `metadata`)
- Sync version omits these fields on insert
- If both are used simultaneously, schema inconsistency could occur

**Current Status**: No conflict - paper_trader (sync) is deprecated

---

## Consolidation Strategy

### Recommended Approach: Async-First with Sync Wrappers

#### Phase 1: Immediate (Low Risk)

**Goal**: Eliminate duplicate classes

**Actions**:

1. **Add sync wrapper methods to async PositionManager**
   ```python
   # In position_manager.py
   class PositionManager:
       # ... existing async methods ...

       def open_position_sync(self, *args, **kwargs) -> ManagedPosition:
           """Synchronous wrapper for open_position."""
           import asyncio
           return asyncio.run(self.open_position(*args, **kwargs))

       def close_position_sync(self, *args, **kwargs) -> Optional[ClosedPosition]:
           """Synchronous wrapper for close_position."""
           import asyncio
           return asyncio.run(self.close_position(*args, **kwargs))

       # ... etc for all async methods
   ```

2. **Create compatibility alias**
   ```python
   # In position_manager_sync.py (NEW VERSION - minimal)
   """
   DEPRECATED: Compatibility shim for sync position manager.

   Use catalyst_bot.portfolio.PositionManager instead.
   """
   from catalyst_bot.portfolio.position_manager import (
       PositionManager as _AsyncPositionManager,
       ManagedPosition,
       ClosedPosition,
   )
   import warnings

   class PositionManagerSync:
       """Deprecated: Use PositionManager with sync wrappers instead."""

       def __init__(self, *args, **kwargs):
           warnings.warn(
               "PositionManagerSync is deprecated. "
               "Use PositionManager from catalyst_bot.portfolio instead.",
               DeprecationWarning,
               stacklevel=2
           )
           self._manager = _AsyncPositionManager(*args, **kwargs)

       def open_position(self, *args, **kwargs):
           return self._manager.open_position_sync(*args, **kwargs)

       # ... delegate all methods to sync wrappers
   ```

3. **Update imports**
   - Change `test_position_management.py` to import from `catalyst_bot.portfolio`
   - Add deprecation warnings

**Benefits**:
- No breaking changes
- Single source of truth
- Backward compatible
- Low risk

**Timeline**: 1 hour

---

#### Phase 2: Migration (Medium Risk)

**Goal**: Migrate all code to async version

**Actions**:

1. **Update test_position_management.py**
   ```python
   # Change from:
   from catalyst_bot.position_manager_sync import PositionManagerSync

   # To:
   from catalyst_bot.portfolio import PositionManager

   # Update test methods to use async/await
   async def test_open_position():
       manager = PositionManager(...)
       position = await manager.open_position(...)
       assert position.ticker == "AAPL"
   ```

2. **Remove paper_trader.py usage** (already deprecated)
   - Confirm no active usage
   - Add migration note to deprecation docstring

3. **Update documentation**
   - Update all references to point to async version
   - Add migration guide

**Benefits**:
- Clean codebase
- Single implementation
- All features available everywhere

**Timeline**: 1 hour

---

#### Phase 3: Cleanup (Low Risk)

**Goal**: Remove legacy code

**Actions**:

1. **Archive position_manager_sync.py**
   ```bash
   mv src/catalyst_bot/position_manager_sync.py \
      src/catalyst_bot/position_manager_sync.py.DEPRECATED_2025-12-14
   ```

2. **Update package exports**
   - Remove from any `__init__.py` that exports it

3. **Update documentation**
   - Remove references to sync version
   - Update architecture diagrams

**Benefits**:
- Cleaner codebase
- Less confusion
- Reduced maintenance burden

**Timeline**: 30 minutes

---

### Alternative Approach: Sync-First with Async Wrappers

**Not Recommended** because:
- Trading Engine (production) uses async
- Async version is more feature-complete
- Modern Python is async-first
- Broker interfaces are async

Would require:
- Rewriting Trading Engine to use sync
- Loss of features (portfolio metrics, etc.)
- Going against Python ecosystem trends

---

## Migration Guide

### Step-by-Step Migration

#### For Code Currently Using Sync Version

**Before**:
```python
from catalyst_bot.position_manager_sync import (
    PositionManagerSync,
    ManagedPosition,
    ClosedPosition,
)

manager = PositionManagerSync(broker=broker)
position = manager.open_position(
    ticker="AAPL",
    quantity=100,
    entry_price=Decimal("150.00"),
)
```

**After (Option 1 - Keep Sync API)**:
```python
from catalyst_bot.portfolio import (
    PositionManager,
    ManagedPosition,
    ClosedPosition,
)

manager = PositionManager(broker=broker)
position = manager.open_position_sync(  # Note: _sync suffix
    ticker="AAPL",
    quantity=100,
    entry_price=Decimal("150.00"),
)
```

**After (Option 2 - Convert to Async)**:
```python
from catalyst_bot.portfolio import (
    PositionManager,
    ManagedPosition,
    ClosedPosition,
)

manager = PositionManager(broker=broker)
position = await manager.open_position(  # Note: await
    ticker="AAPL",
    quantity=100,
    entry_price=Decimal("150.00"),
)
```

#### For Code Currently Using Async Version

**No changes required!** Already using the canonical version.

#### Import Statement Changes

| Old Import | New Import | Notes |
|------------|------------|-------|
| `from catalyst_bot.position_manager_sync import PositionManagerSync` | `from catalyst_bot.portfolio import PositionManager` | Use `_sync` methods or convert to async |
| `from catalyst_bot.position_manager_sync import ManagedPosition` | `from catalyst_bot.portfolio import ManagedPosition` | No API changes |
| `from catalyst_bot.position_manager_sync import ClosedPosition` | `from catalyst_bot.portfolio import ClosedPosition` | No API changes |
| `from catalyst_bot.portfolio.position_manager import ...` | `from catalyst_bot.portfolio import ...` | Shorter import path |

#### API Differences to Address

**Missing in Sync Version (now available)**:

1. **PositionSide enum support**:
   ```python
   # Old (sync): Assumed LONG only
   position = manager.open_position(ticker="AAPL", ...)

   # New: Explicit side
   from catalyst_bot.broker.broker_interface import PositionSide
   position = manager.open_position(
       order=order,  # Order object contains side
       ...
   )
   ```

2. **Metadata field**:
   ```python
   # Now available
   position.metadata = {"catalyst": "earnings", "confidence": 0.85}
   ```

3. **Portfolio metrics**:
   ```python
   # Now available
   metrics = manager.calculate_portfolio_metrics(account_value=account.equity)
   print(f"Total exposure: ${metrics.total_exposure}")
   print(f"Win rate: {metrics.total_unrealized_pnl_pct}%")
   ```

4. **Performance statistics**:
   ```python
   # Now available
   stats = manager.get_performance_stats(days=30)
   print(f"Win rate: {stats['win_rate']}%")
   ```

#### Database Migration

**No database migration needed!** The async version schema is a superset:

```sql
-- Existing data from sync version will work fine
-- New columns (side, metadata) will be NULL for old records
-- This is acceptable
```

If you want to backfill:
```sql
-- Optional: Set default side for old positions
UPDATE positions SET side = 'long' WHERE side IS NULL;

-- Optional: Set empty metadata for old positions
UPDATE positions SET metadata = '{}' WHERE metadata IS NULL;
```

#### Mixed Async/Sync Usage

**Pattern 1: Sync wrapper in async context**
```python
# Don't do this - creates nested event loops
async def my_async_function():
    manager = PositionManager(broker=broker)
    position = manager.open_position_sync(...)  # BAD!

# Do this instead
async def my_async_function():
    manager = PositionManager(broker=broker)
    position = await manager.open_position(...)  # GOOD!
```

**Pattern 2: Async in sync context**
```python
# OK - but prefer async throughout
def my_sync_function():
    manager = PositionManager(broker=broker)
    position = manager.open_position_sync(...)  # OK

# Better - convert calling code to async
async def my_async_function():
    manager = PositionManager(broker=broker)
    position = await manager.open_position(...)  # BETTER!
```

---

## Verification Checklist

### Pre-Migration Verification

- [ ] **Backup database**
  ```bash
  cp data/trading.db data/trading.db.backup.$(date +%Y%m%d)
  ```

- [ ] **Document current state**
  ```bash
  # Count positions in database
  sqlite3 data/trading.db "SELECT COUNT(*) FROM positions;"
  sqlite3 data/trading.db "SELECT COUNT(*) FROM closed_positions;"
  ```

- [ ] **Identify all imports**
  ```bash
  grep -r "position_manager_sync" src/ tests/
  grep -r "PositionManagerSync" src/ tests/
  ```

- [ ] **Run existing tests**
  ```bash
  pytest tests/test_trading_engine.py -v
  pytest tests/test_trading_integration.py -v
  pytest test_position_management.py -v
  ```

### Phase 1 Verification (Sync Wrappers Added)

- [ ] **Verify async methods still work**
  ```bash
  pytest tests/test_trading_engine.py::TestPositionManagement -v
  ```

- [ ] **Test sync wrapper methods**
  ```python
  # In Python REPL or test file
  from catalyst_bot.portfolio import PositionManager
  manager = PositionManager(broker=mock_broker)

  # Should work without await
  position = manager.open_position_sync(...)
  assert position is not None
  ```

- [ ] **Verify backward compatibility**
  ```bash
  # Old code should still work with deprecation warning
  pytest test_position_management.py -v -W default::DeprecationWarning
  ```

- [ ] **Check database writes**
  ```sql
  -- Verify schema matches
  .schema positions
  .schema closed_positions

  -- Verify data integrity
  SELECT * FROM positions LIMIT 5;
  ```

### Phase 2 Verification (Migration Complete)

- [ ] **All tests passing**
  ```bash
  pytest tests/test_trading_engine.py -v
  pytest tests/test_trading_integration.py -v
  pytest tests/portfolio/ -v
  ```

- [ ] **No sync manager imports remain**
  ```bash
  grep -r "position_manager_sync" src/ --exclude="*.DEPRECATED*"
  # Should return no results
  ```

- [ ] **Trading Engine integration test**
  ```bash
  pytest tests/test_trading_engine.py::TestExecuteSignal -v
  ```

- [ ] **Position lifecycle test**
  ```python
  # Full lifecycle test
  async def test_full_lifecycle():
      engine = TradingEngine()
      await engine.initialize()

      # Open position
      position = await engine.position_manager.open_position(...)
      assert position.position_id is not None

      # Update prices
      await engine.update_positions()

      # Close position
      closed = await engine.position_manager.close_position(...)
      assert closed.realized_pnl is not None
  ```

### Phase 3 Verification (Cleanup)

- [ ] **Legacy file archived**
  ```bash
  ls -la src/catalyst_bot/position_manager_sync.py.DEPRECATED*
  # Should exist

  ls src/catalyst_bot/position_manager_sync.py
  # Should not exist
  ```

- [ ] **No broken imports**
  ```bash
  python -m py_compile src/catalyst_bot/**/*.py
  # Should compile without errors
  ```

- [ ] **Documentation updated**
  - [ ] Architecture diagrams reference single implementation
  - [ ] API docs reference only async version
  - [ ] Migration guide published

### Integration Tests

#### Test Position Opening
```python
async def test_position_opening():
    """Verify position opening works with async manager."""
    from catalyst_bot.portfolio import PositionManager
    from catalyst_bot.broker.broker_interface import Order, OrderSide, OrderStatus
    from decimal import Decimal

    manager = PositionManager(broker=mock_broker)

    filled_order = Order(
        order_id="test_123",
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        filled_quantity=100,
        filled_avg_price=Decimal("150.00"),
        status=OrderStatus.FILLED,
    )

    position = await manager.open_position(
        order=filled_order,
        signal_id="signal_001",
        stop_loss_price=Decimal("145.00"),
        take_profit_price=Decimal("160.00"),
    )

    assert position.ticker == "AAPL"
    assert position.quantity == 100
    assert position.entry_price == Decimal("150.00")
    assert position.stop_loss_price == Decimal("145.00")
```

#### Test Position Closing
```python
async def test_position_closing():
    """Verify position closing calculates P&L correctly."""
    # Open position
    position = await manager.open_position(...)

    # Update price
    await manager.update_position_prices({
        "AAPL": Decimal("155.00")
    })

    # Close position
    closed = await manager.close_position(
        position_id=position.position_id,
        exit_reason="manual"
    )

    assert closed.realized_pnl > 0  # Profit
    assert closed.exit_price == Decimal("155.00")
    assert closed.exit_reason == "manual"
```

#### Test Portfolio Metrics
```python
async def test_portfolio_metrics():
    """Verify portfolio metrics calculation."""
    # Open multiple positions
    pos1 = await manager.open_position(...)
    pos2 = await manager.open_position(...)

    # Calculate metrics
    metrics = manager.calculate_portfolio_metrics(
        account_value=Decimal("100000.00")
    )

    assert metrics.total_positions == 2
    assert metrics.total_exposure > 0
    assert metrics.long_positions == 2
    assert metrics.short_positions == 0
```

#### Test Database Persistence
```python
async def test_database_persistence():
    """Verify positions persist across manager instances."""
    # Create manager and open position
    manager1 = PositionManager(broker=broker, db_path=test_db)
    position = await manager1.open_position(...)
    position_id = position.position_id

    # Create new manager instance
    manager2 = PositionManager(broker=broker, db_path=test_db)

    # Should load position from database
    loaded_position = manager2.get_position(position_id)
    assert loaded_position is not None
    assert loaded_position.ticker == position.ticker
```

### Manual Verification Steps

1. **Start Trading Engine in test mode**
   ```bash
   python -m catalyst_bot.trading.trading_engine
   ```

2. **Verify console output shows**:
   - PositionManager initialized
   - Database schema created
   - No errors or warnings

3. **Check database**:
   ```bash
   sqlite3 data/trading.db
   > .tables
   # Should show: positions, closed_positions
   > .schema positions
   # Should match async version schema
   ```

4. **Simulate trade execution**:
   - Generate test signal
   - Execute via Trading Engine
   - Verify position created
   - Update prices
   - Verify P&L calculated
   - Close position
   - Verify recorded in closed_positions

---

## Rollback Plan

### If Issues Occur During Migration

#### Phase 1 Rollback (Sync Wrappers)

**If sync wrappers cause issues**:

1. **Revert position_manager.py**
   ```bash
   git checkout HEAD~1 src/catalyst_bot/portfolio/position_manager.py
   ```

2. **Restore original sync manager**
   ```bash
   git checkout HEAD~1 src/catalyst_bot/position_manager_sync.py
   ```

3. **Run tests to verify**
   ```bash
   pytest tests/test_trading_engine.py -v
   ```

**Time to rollback**: 5 minutes

#### Phase 2 Rollback (Migration)

**If async migration breaks tests**:

1. **Revert test file changes**
   ```bash
   git checkout HEAD~1 test_position_management.py
   ```

2. **Restore paper_trader.py if modified**
   ```bash
   git checkout HEAD~1 src/catalyst_bot/paper_trader.py
   ```

3. **Run original tests**
   ```bash
   pytest test_position_management.py -v
   ```

**Time to rollback**: 5 minutes

#### Phase 3 Rollback (Cleanup)

**If cleanup breaks imports**:

1. **Restore archived file**
   ```bash
   mv src/catalyst_bot/position_manager_sync.py.DEPRECATED* \
      src/catalyst_bot/position_manager_sync.py
   ```

2. **Verify imports work**
   ```bash
   python -c "from catalyst_bot.position_manager_sync import PositionManagerSync"
   ```

**Time to rollback**: 2 minutes

### Emergency Rollback (Complete)

**If severe issues arise**:

```bash
# Restore entire repository to pre-migration state
git reset --hard <commit-before-migration>

# Restore database if corrupted
cp data/trading.db.backup.* data/trading.db

# Verify system operational
pytest tests/test_trading_engine.py -v
```

**Time to rollback**: 10 minutes

### Rollback Decision Criteria

**Rollback if**:
- Trading Engine fails to initialize
- Position opening/closing fails in production
- Database corruption detected
- Tests fail that previously passed
- Performance degrades significantly (>2x slower)

**Do NOT rollback if**:
- Deprecation warnings appear (expected)
- Documentation out of sync (fix docs, not code)
- Non-critical tests fail (fix tests, not core code)

---

## Success Metrics

### Phase 1 Success (Sync Wrappers)

- [ ] All existing tests pass
- [ ] Deprecation warnings appear for sync usage
- [ ] Trading Engine still works in production
- [ ] No database corruption
- [ ] Code coverage maintained or improved

### Phase 2 Success (Migration)

- [ ] No imports of `position_manager_sync` in active code
- [ ] All tests converted to async or use sync wrappers
- [ ] Trading Engine integration tests pass
- [ ] Performance equal or better than before
- [ ] Documentation updated

### Phase 3 Success (Cleanup)

- [ ] Single source of truth for position management
- [ ] Codebase reduced by ~550 lines
- [ ] No deprecated code in production
- [ ] Clear API documentation
- [ ] Architecture diagrams updated

---

## Timeline

| Phase | Tasks | Duration | Risk |
|-------|-------|----------|------|
| **Phase 1** | Add sync wrappers to async manager | 1 hour | Low |
| | Create compatibility shim | 30 min | Low |
| | Update tests | 30 min | Low |
| **Phase 2** | Migrate test code | 1 hour | Medium |
| | Update documentation | 30 min | Low |
| | Integration testing | 1 hour | Medium |
| **Phase 3** | Archive legacy code | 15 min | Low |
| | Update package exports | 15 min | Low |
| | Final documentation | 30 min | Low |
| **Total** | | **5.5 hours** | **Medium** |

---

## Related Documentation

- [Wave 1: Broker Client Consolidation](./01-WAVE-BROKER-CLIENTS.md)
- [Wave 3: Data Class Consolidation](./03-WAVE-DATA-CLASSES.md)
- [Trading Engine Architecture](../architecture/trading-engine-architecture.md)
- [Position Management Database Schema](../architecture/database-schemas-documentation.md)

---

## Appendix

### A. Complete API Comparison

#### PositionManager (Async)

```python
class PositionManager:
    def __init__(broker: BrokerInterface, db_path: Optional[Path]) -> None

    # Position Management
    async def open_position(order, signal_id, strategy, stop_loss_price, take_profit_price) -> ManagedPosition
    async def close_position(position_id, exit_reason, exit_order_id) -> Optional[ClosedPosition]
    async def update_position_prices(price_updates) -> int

    # Risk Monitoring
    async def check_stop_losses() -> List[ManagedPosition]
    async def check_take_profits() -> List[ManagedPosition]
    async def auto_close_triggered_positions() -> List[ClosedPosition]

    # Queries
    def get_position(position_id) -> Optional[ManagedPosition]
    def get_position_by_ticker(ticker) -> Optional[ManagedPosition]
    def get_all_positions() -> List[ManagedPosition]
    def get_positions_by_strategy(strategy) -> List[ManagedPosition]

    # Portfolio Metrics
    def calculate_portfolio_metrics(account_value) -> PortfolioMetrics
    def get_portfolio_exposure() -> Decimal
    def get_total_unrealized_pnl() -> Decimal

    # Historical Analysis
    def get_closed_positions(ticker, strategy, limit) -> List[ClosedPosition]
    def get_performance_stats(days) -> Dict
```

#### PositionManagerSync (Legacy)

```python
class PositionManagerSync:
    def __init__(broker: AlpacaBrokerWrapper, db_path: Optional[Path]) -> None

    # Position Management
    def open_position(ticker, quantity, entry_price, entry_order_id, signal_id, stop_loss_price, take_profit_price) -> ManagedPosition
    def close_position(position_id, exit_reason) -> Optional[ClosedPosition]
    def update_position_prices() -> int  # No price_updates param

    # Combined Risk Check + Execute
    def check_and_execute_exits(max_hold_hours) -> List[ClosedPosition]

    # Queries
    def get_all_positions() -> List[ManagedPosition]
    def get_position_by_ticker(ticker) -> Optional[ManagedPosition]

    # MISSING:
    # - check_stop_losses()
    # - check_take_profits()
    # - auto_close_triggered_positions()
    # - get_positions_by_strategy()
    # - calculate_portfolio_metrics()
    # - get_portfolio_exposure()
    # - get_total_unrealized_pnl()
    # - get_closed_positions()
    # - get_performance_stats()
```

### B. Database Schema Differences

#### Async Version (Complete)

```sql
CREATE TABLE positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,           -- 'long' or 'short'
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    cost_basis REAL NOT NULL,
    market_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    opened_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    entry_order_id TEXT,
    signal_id TEXT,
    strategy TEXT,
    metadata JSON                  -- Additional tracking
);

CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_opened_at ON positions(opened_at);
CREATE INDEX idx_closed_positions_strategy ON closed_positions(strategy);
```

#### Sync Version (Simplified)

```sql
CREATE TABLE positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    -- NO side column (assumes LONG)
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    cost_basis REAL NOT NULL,
    market_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    opened_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    entry_order_id TEXT,
    signal_id TEXT,
    strategy TEXT
    -- NO metadata column
);

CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_opened_at ON positions(opened_at);
-- MISSING: idx_closed_positions_strategy
```

### C. Code Snippets for Common Tasks

#### Opening a Position

**Async**:
```python
from catalyst_bot.portfolio import PositionManager
from decimal import Decimal

manager = PositionManager(broker=broker)
position = await manager.open_position(
    order=filled_order,
    signal_id="signal_123",
    strategy="momentum_v1",
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
)
```

**Sync** (legacy):
```python
from catalyst_bot.position_manager_sync import PositionManagerSync
from decimal import Decimal

manager = PositionManagerSync(broker=broker_wrapper)
position = manager.open_position(
    ticker="AAPL",
    quantity=100,
    entry_price=Decimal("150.00"),
    signal_id="signal_123",
    stop_loss_price=Decimal("145.00"),
    take_profit_price=Decimal("160.00"),
)
```

#### Checking Stop Losses

**Async**:
```python
# Separate check and execution
triggered = await manager.check_stop_losses()
for position in triggered:
    print(f"Stop loss hit: {position.ticker}")

closed = await manager.auto_close_triggered_positions()
```

**Sync** (legacy):
```python
# Combined check and execution
closed = manager.check_and_execute_exits(max_hold_hours=24)
for position in closed:
    if position.exit_reason == "stop_loss":
        print(f"Stop loss hit: {position.ticker}")
```

#### Getting Portfolio Metrics

**Async**:
```python
account = await broker.get_account()
metrics = manager.calculate_portfolio_metrics(account.equity)

print(f"Total positions: {metrics.total_positions}")
print(f"Total exposure: ${metrics.total_exposure}")
print(f"Unrealized P&L: ${metrics.total_unrealized_pnl}")
print(f"Long/Short: {metrics.long_positions}/{metrics.short_positions}")
```

**Sync** (legacy):
```python
# NOT AVAILABLE - must calculate manually
positions = manager.get_all_positions()
total_exposure = sum(p.market_value for p in positions)
total_pnl = sum(p.unrealized_pnl for p in positions)

print(f"Total positions: {len(positions)}")
print(f"Total exposure: ${total_exposure}")
print(f"Unrealized P&L: ${total_pnl}")
```

---

**End of Wave 2 Documentation**
