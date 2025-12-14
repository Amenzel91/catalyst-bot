# WAVE 7: TYPE DEFINITIONS CONSOLIDATION

**Status:** Analysis Complete
**Priority:** HIGH - Critical for type safety and maintainability
**Complexity:** HIGH - Multiple duplicate classes with different field sets
**Risk:** MEDIUM - Tests and production code depend on these types

## Executive Summary

This wave addresses duplicate type definitions across the codebase, consolidating 6 major groups of duplicate classes. These duplications create confusion, maintenance burden, and potential type safety issues.

**Key Issues:**
- Position classes duplicated across backtesting and broker modules
- ManagedPosition/ClosedPosition duplicated in sync/async versions
- Two separate LLM monitoring systems (LLMUsageMonitor vs LLMMonitor)
- Two routing systems (HybridLLMRouter vs LLMRouter)
- Trade result types with overlapping purposes

**Impact:**
- 400+ lines of duplicate type definitions
- Inconsistent field names and types across modules
- Missing fields in simplified versions causing feature gaps
- Confusion about which class to use where

---

## 1. POSITION CLASS DUPLICATION

### Current State Analysis

#### Backtesting Position (/home/user/catalyst-bot/src/catalyst_bot/backtesting/portfolio.py:19-39)

```python
@dataclass
class Position:
    """Represents an open position."""

    ticker: str
    shares: int
    entry_price: float
    entry_time: int
    cost_basis: float
    alert_data: Dict
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0

    def update_price(self, current_price: float) -> None:
        """Update position with current market price."""
        self.current_price = current_price
        self.unrealized_pnl = (current_price - self.entry_price) * self.shares
        self.unrealized_pnl_pct = (
            (current_price - self.entry_price) / self.entry_price
        ) * 100
```

**Purpose:** Simple position tracking for backtesting
**Type Safety:** Uses float for prices (less precise)
**Fields:** 10 total
**Methods:** 1 (update_price)

#### Broker Position (/home/user/catalyst-bot/src/catalyst_bot/broker/broker_interface.py:146-187)

```python
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
```

**Purpose:** Production broker interface position
**Type Safety:** Uses Decimal for precision
**Fields:** 14 total
**Methods:** 2 (get_exposure, get_pnl_ratio)

### Field-by-Field Comparison

| Field | Backtesting | Broker | Notes |
|-------|-------------|--------|-------|
| **Identity** |
| ticker | ✓ (str) | ✓ (str) | Same |
| side | ✗ | ✓ (PositionSide) | **Missing in backtesting** |
| **Quantities** |
| shares | ✓ (int) | ✗ | Different naming |
| quantity | ✗ | ✓ (int) | Different naming |
| available_quantity | ✗ | ✓ (int) | **Missing in backtesting** |
| **Pricing** |
| entry_price | ✓ (float) | ✓ (Decimal) | **Different types** |
| current_price | ✓ (float) | ✓ (Decimal) | **Different types** |
| cost_basis | ✓ (float) | ✓ (Decimal) | **Different types** |
| market_value | ✗ | ✓ (Decimal) | **Missing in backtesting** |
| **P&L** |
| unrealized_pnl | ✓ (float) | ✓ (Decimal) | **Different types** |
| unrealized_pnl_pct | ✓ (float) | ✓ (Decimal) | **Different types** |
| **Timestamps** |
| entry_time | ✓ (int/Unix) | ✗ | Different naming |
| opened_at | ✗ | ✓ (datetime) | Different naming |
| updated_at | ✗ | ✓ (datetime) | **Missing in backtesting** |
| **Metadata** |
| alert_data | ✓ (Dict) | ✗ | Backtesting-specific |
| metadata | ✗ | ✓ (Dict) | Broker-specific |

**Key Differences:**
1. **Type Safety:** Broker uses Decimal for financial precision, backtesting uses float
2. **Missing Fields:** Backtesting missing `side`, `available_quantity`, `market_value`, `updated_at`
3. **Naming Inconsistency:** `shares` vs `quantity`, `entry_time` vs `opened_at`
4. **Metadata Strategy:** `alert_data` vs `metadata`

### Dependency Mapping

#### Backtesting Position

**Direct Imports:**
```python
# /home/user/catalyst-bot/src/catalyst_bot/backtesting/__init__.py:38
from .portfolio import Portfolio, Position

# /home/user/catalyst-bot/src/catalyst_bot/backtesting/engine.py:28
from .portfolio import ClosedTrade, Portfolio, Position
```

**Usage:**
- Created in: `backtesting/portfolio.py:140` (Portfolio.open_position)
- Modified in: `backtesting/portfolio.py:255` (Portfolio.update_position_prices)
- Accessed in: `backtesting/portfolio.py:196` (Portfolio.close_position)
- Stored in: `Portfolio._positions` dict

**Call Sites:**
- Portfolio class manages lifecycle
- Engine uses Portfolio, not Position directly
- No external modules import backtesting Position

#### Broker Position

**Direct Imports:**
```python
# /home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py:78
from ..broker.broker_interface import (
    BrokerInterface,
    Order,
    Position as BrokerPosition,  # Aliased to avoid conflict
    PositionSide,
)

# Tests import as BrokerPosition
# /home/user/catalyst-bot/tests/test_trading_engine.py:17
from catalyst_bot.broker.broker_interface import Account, Position as BrokerPosition

# /home/user/catalyst-bot/tests/test_trading_integration.py:19
from catalyst_bot.broker.broker_interface import Account, Position as BrokerPosition
```

**Usage:**
- Returned by: `BrokerInterface.get_positions()` (abstract method)
- Returned by: `BrokerInterface.get_position(ticker)` (abstract method)
- Used by: PositionManager to track broker positions
- Aliased as BrokerPosition to distinguish from ManagedPosition

**Call Sites:**
- BrokerInterface abstract methods return this type
- Position manager imports to interact with broker
- Tests use to mock broker responses

### Consolidation Strategy

**Recommendation:** Create unified `Position` in `types/positions.py`, use TypeAlias for backward compatibility

#### Step 1: Create Canonical Position

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/types/positions.py` (new file)

```python
"""
Canonical Position Types
========================

Unified position definitions for backtesting, broker, and position management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional


class PositionSide(str, Enum):
    """Position side: long or short"""
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """
    Canonical position representation.

    Used across:
    - Backtesting (with alert_data in metadata)
    - Broker interface (standardized broker positions)
    - Position management (with additional tracking)

    Type Safety:
    - Uses Decimal for all financial values
    - Uses datetime for timestamps
    - Supports both shares and quantity naming via property
    """

    # Identity
    ticker: str
    side: PositionSide = PositionSide.LONG  # Default to long for backtesting compatibility

    # Quantities
    quantity: int = 0  # Canonical field name
    available_quantity: Optional[int] = None  # For broker positions

    # Pricing (all Decimal for precision)
    entry_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    market_value: Decimal = Decimal("0")

    # P&L
    unrealized_pnl: Decimal = Decimal("0")
    unrealized_pnl_pct: Decimal = Decimal("0")

    # Timestamps
    opened_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Metadata (flexible for different use cases)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Backward compatibility properties
    @property
    def shares(self) -> int:
        """Alias for quantity (backtesting compatibility)"""
        return self.quantity

    @shares.setter
    def shares(self, value: int) -> None:
        self.quantity = value

    @property
    def entry_time(self) -> int:
        """Unix timestamp (backtesting compatibility)"""
        return int(self.opened_at.timestamp())

    @property
    def alert_data(self) -> Dict:
        """Alert data (backtesting compatibility)"""
        return self.metadata.get("alert_data", {})

    @alert_data.setter
    def alert_data(self, value: Dict) -> None:
        self.metadata["alert_data"] = value

    # Methods
    def update_price(self, current_price: Decimal) -> None:
        """
        Update position with current market price.

        Recalculates:
        - market_value
        - unrealized_pnl
        - unrealized_pnl_pct
        """
        self.current_price = Decimal(str(current_price))
        self.market_value = self.current_price * self.quantity

        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.quantity

        if self.cost_basis > 0:
            self.unrealized_pnl_pct = (self.unrealized_pnl / self.cost_basis) * 100
        else:
            self.unrealized_pnl_pct = Decimal("0")

        self.updated_at = datetime.now()

    def get_exposure(self) -> Decimal:
        """Calculate position exposure (market value)"""
        return self.market_value

    def get_pnl_ratio(self) -> float:
        """Calculate P&L ratio relative to cost basis"""
        if self.cost_basis == 0:
            return 0.0
        return float(self.unrealized_pnl / self.cost_basis)
```

#### Step 2: Maintain Backward Compatibility

```python
# /home/user/catalyst-bot/src/catalyst_bot/backtesting/portfolio.py

from ..types.positions import Position as CanonicalPosition

# TypeAlias for backward compatibility
Position = CanonicalPosition

# No code changes needed - Position has shares property and alert_data property
```

```python
# /home/user/catalyst-bot/src/catalyst_bot/broker/broker_interface.py

from ..types.positions import Position, PositionSide

# Remove duplicate Position definition (lines 146-187)
# Export from canonical types
```

### Migration Guide

#### Phase 1: Create Canonical Types (Week 1)

1. **Create types module:**
   ```bash
   mkdir -p src/catalyst_bot/types
   touch src/catalyst_bot/types/__init__.py
   touch src/catalyst_bot/types/positions.py
   ```

2. **Implement Position:**
   - Copy broker Position as base (more comprehensive)
   - Add backtesting compatibility properties (shares, entry_time, alert_data)
   - Add side default value (LONG for backtesting)
   - Ensure all methods work with both naming conventions

3. **Add tests:**
   ```bash
   touch tests/types/test_positions.py
   ```

#### Phase 2: Update Broker Interface (Week 1)

1. **Update imports:**
   ```python
   # broker/broker_interface.py
   from ..types.positions import Position, PositionSide
   ```

2. **Remove duplicate:**
   - Delete lines 146-187 (Position class)
   - Delete lines 65-68 (PositionSide enum)

3. **Update __init__.py:**
   ```python
   # broker/__init__.py
   from catalyst_bot.types.positions import Position, PositionSide
   ```

4. **Run tests:**
   ```bash
   pytest tests/test_trading_engine.py tests/test_trading_integration.py -v
   ```

#### Phase 3: Update Backtesting (Week 2)

1. **Update portfolio.py:**
   ```python
   from ..types.positions import Position

   # Remove Position definition (lines 19-39)
   ```

2. **Update usage:**
   - No changes needed - Position has shares property
   - alert_data property provides backward compatibility

3. **Test backtesting:**
   ```bash
   pytest src/catalyst_bot/backtesting/test_*.py -v
   ```

#### Phase 4: Update Position Manager (Week 2)

1. **Update imports:**
   ```python
   # portfolio/position_manager.py
   from ..types.positions import Position
   from ..broker.broker_interface import BrokerInterface, Order
   ```

2. **Use Position instead of BrokerPosition alias:**
   - Find/replace `BrokerPosition` → `Position`

#### Phase 5: Deprecation Warnings (Week 3)

Add deprecation warnings for old import paths:

```python
# backtesting/portfolio.py (temporary compatibility)
import warnings

def __getattr__(name):
    if name == "Position":
        warnings.warn(
            "Importing Position from backtesting.portfolio is deprecated. "
            "Use 'from catalyst_bot.types.positions import Position' instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from ..types.positions import Position
        return Position
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### Verification Plan

#### Type Checking

```bash
# Run mypy on updated modules
mypy src/catalyst_bot/types/positions.py
mypy src/catalyst_bot/broker/broker_interface.py
mypy src/catalyst_bot/backtesting/portfolio.py
mypy src/catalyst_bot/portfolio/position_manager.py
```

#### Runtime Tests

```bash
# Test backtesting
pytest src/catalyst_bot/backtesting/ -v

# Test broker interface
pytest tests/test_trading_engine.py tests/test_trading_integration.py -v

# Test position manager
pytest tests/portfolio/test_position_manager.py -v

# Integration tests
pytest tests/integration/test_end_to_end.py -v
```

#### Integration Verification

```python
# Test script: verify_position_consolidation.py
from catalyst_bot.types.positions import Position, PositionSide
from decimal import Decimal
from datetime import datetime

def test_backward_compatibility():
    """Verify all compatibility properties work"""

    # Create position
    pos = Position(
        ticker="AAPL",
        quantity=100,
        entry_price=Decimal("150.00"),
        current_price=Decimal("155.00"),
        cost_basis=Decimal("15000.00"),
        side=PositionSide.LONG
    )

    # Test backtesting compatibility
    assert pos.shares == 100  # property works
    assert pos.entry_time > 0  # Unix timestamp works

    pos.alert_data = {"score": 0.95}
    assert pos.alert_data["score"] == 0.95

    # Test broker compatibility
    assert pos.quantity == 100
    assert pos.side == PositionSide.LONG
    assert isinstance(pos.entry_price, Decimal)

    # Test methods
    pos.update_price(Decimal("160.00"))
    assert pos.unrealized_pnl == Decimal("1000.00")

    exposure = pos.get_exposure()
    assert exposure == Decimal("16000.00")

    ratio = pos.get_pnl_ratio()
    assert abs(ratio - 0.0667) < 0.001

    print("✓ All compatibility tests passed")

if __name__ == "__main__":
    test_backward_compatibility()
```

---

## 2. MANAGEDPOSITION DUPLICATION

### Current State Analysis

#### Async ManagedPosition (/home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py:92-171)

```python
@dataclass
class ManagedPosition:
    """
    Represents a managed trading position with additional metadata.

    This extends the broker's Position with our tracking information.
    """

    # Identity
    position_id: str
    ticker: str
    side: PositionSide

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
    opened_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def should_stop_loss(self) -> bool:
        """Check if current price has hit stop loss"""
        if not self.stop_loss_price:
            return False

        if self.side == PositionSide.LONG:
            return self.current_price <= self.stop_loss_price
        else:  # SHORT
            return self.current_price >= self.stop_loss_price

    def should_take_profit(self) -> bool:
        """Check if current price has hit take profit"""
        if not self.take_profit_price:
            return False

        if self.side == PositionSide.LONG:
            return self.current_price >= self.take_profit_price
        else:  # SHORT
            return self.current_price <= self.take_profit_price

    def get_hold_duration(self) -> timedelta:
        """Get how long position has been held"""
        return datetime.now() - self.opened_at

    def calculate_risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio"""
        if not self.stop_loss_price or not self.take_profit_price:
            return None

        if self.side == PositionSide.LONG:
            risk = abs(self.entry_price - self.stop_loss_price)
            reward = abs(self.take_profit_price - self.entry_price)
        else:  # SHORT
            risk = abs(self.stop_loss_price - self.entry_price)
            reward = abs(self.entry_price - self.take_profit_price)

        if risk == 0:
            return None

        return float(reward / risk)
```

**Features:**
- Full async version (19 fields)
- Has `side` field (PositionSide)
- 4 methods including risk/reward calculation
- Complete metadata tracking

#### Sync ManagedPosition (/home/user/catalyst-bot/src/catalyst_bot/position_manager_sync.py:32-79)

```python
@dataclass
class ManagedPosition:
    """Represents a managed trading position with P&L tracking."""

    # Identity
    position_id: str
    ticker: str
    # NOTE: Missing `side` field!

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
    opened_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "catalyst_alert"

    def should_stop_loss(self) -> bool:
        """Check if current price has hit stop loss."""
        if not self.stop_loss_price:
            return False
        return self.current_price <= self.stop_loss_price

    def should_take_profit(self) -> bool:
        """Check if current price has hit take profit."""
        if not self.take_profit_price:
            return False
        return self.current_price >= self.take_profit_price

    def get_hold_duration(self) -> timedelta:
        """Get how long position has been held."""
        return datetime.now() - self.opened_at
```

**Features:**
- Simplified sync version (17 fields)
- **Missing `side` field** - assumes LONG only
- **Missing `metadata` field**
- **Missing `calculate_risk_reward_ratio()` method**
- **Incorrect stop loss logic** - doesn't account for SHORT positions

### Field-by-Field Comparison

| Field | Async | Sync | Notes |
|-------|-------|------|-------|
| position_id | ✓ | ✓ | Same |
| ticker | ✓ | ✓ | Same |
| **side** | ✓ (PositionSide) | ✗ | **Missing in sync - critical bug** |
| quantity | ✓ | ✓ | Same |
| entry_price | ✓ | ✓ | Same |
| current_price | ✓ | ✓ | Same |
| cost_basis | ✓ | ✓ | Same |
| market_value | ✓ | ✓ | Same |
| unrealized_pnl | ✓ | ✓ | Same |
| unrealized_pnl_pct | ✓ | ✓ | Same |
| stop_loss_price | ✓ | ✓ | Same |
| take_profit_price | ✓ | ✓ | Same |
| opened_at | ✓ | ✓ | Same |
| updated_at | ✓ | ✓ | Same |
| entry_order_id | ✓ | ✓ | Same |
| signal_id | ✓ | ✓ | Same |
| strategy | ✓ (Optional[str]) | ✓ (str with default) | Different types |
| **metadata** | ✓ | ✗ | **Missing in sync** |

**Methods Comparison:**

| Method | Async | Sync | Notes |
|--------|-------|------|-------|
| should_stop_loss() | ✓ (side-aware) | ✓ (LONG only) | **Sync version broken for SHORT** |
| should_take_profit() | ✓ (side-aware) | ✓ (LONG only) | **Sync version broken for SHORT** |
| get_hold_duration() | ✓ | ✓ | Same |
| **calculate_risk_reward_ratio()** | ✓ | ✗ | **Missing in sync** |

### Critical Bugs in Sync Version

#### Bug 1: Missing `side` Field

**Impact:** Cannot distinguish LONG from SHORT positions

**Broken Scenarios:**
```python
# Sync version assumes LONG position
pos = ManagedPosition(ticker="SPY", quantity=100, ...)

# No way to indicate SHORT position
# Stop loss logic will be incorrect for SHORT
```

#### Bug 2: Incorrect Stop Loss Logic

**Async (Correct):**
```python
def should_stop_loss(self) -> bool:
    if not self.stop_loss_price:
        return False

    if self.side == PositionSide.LONG:
        return self.current_price <= self.stop_loss_price  # Below stop
    else:  # SHORT
        return self.current_price >= self.stop_loss_price  # Above stop
```

**Sync (Broken):**
```python
def should_stop_loss(self) -> bool:
    if not self.stop_loss_price:
        return False
    return self.current_price <= self.stop_loss_price  # LONG only!
```

**Problem:** For SHORT positions, stop loss triggers when price goes UP, not down.

### Dependency Mapping

#### Async ManagedPosition

**Direct Imports:**
```python
# tests/test_trading_engine.py:19
from catalyst_bot.portfolio.position_manager import ManagedPosition, ClosedPosition

# tests/test_trading_integration.py:21
from catalyst_bot.portfolio.position_manager import ManagedPosition, ClosedPosition
```

**Usage:**
- Created in: `portfolio/position_manager.py:514` (PositionManager.open_position)
- Modified in: `portfolio/position_manager.py:665` (update_position_prices)
- Database: Saved to `positions` table
- Returned by: PositionManager.get_position(), get_all_positions()

#### Sync ManagedPosition

**Direct Imports:**
```python
# src/catalyst_bot/paper_trader.py:112
from .position_manager_sync import PositionManagerSync
# (imports class, which uses ManagedPosition internally)
```

**Usage:**
- Created in: `position_manager_sync.py:324` (PositionManagerSync.open_position)
- Modified in: `position_manager_sync.py:448` (update_position_prices)
- Database: Saved to `positions` table
- Used by: paper_trader.py for live trading

**Critical Issue:** Paper trading assumes LONG-only positions due to missing `side` field.

### Consolidation Strategy

**Recommendation:** Use async ManagedPosition as canonical, deprecate sync version

#### Step 1: Move to Canonical Types

```python
# /home/user/catalyst-bot/src/catalyst_bot/types/positions.py

@dataclass
class ManagedPosition:
    """
    Managed trading position with risk management.

    Extends Position with:
    - Position ID for database tracking
    - Stop loss and take profit levels
    - Entry/signal tracking
    - Risk/reward calculations
    """

    # Identity
    position_id: str
    ticker: str
    side: PositionSide

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
    opened_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def should_stop_loss(self) -> bool:
        """Check if current price has hit stop loss"""
        if not self.stop_loss_price:
            return False

        if self.side == PositionSide.LONG:
            return self.current_price <= self.stop_loss_price
        else:  # SHORT
            return self.current_price >= self.stop_loss_price

    def should_take_profit(self) -> bool:
        """Check if current price has hit take profit"""
        if not self.take_profit_price:
            return False

        if self.side == PositionSide.LONG:
            return self.current_price >= self.take_profit_price
        else:  # SHORT
            return self.current_price <= self.take_profit_price

    def get_hold_duration(self) -> timedelta:
        """Get how long position has been held"""
        return datetime.now() - self.opened_at

    def calculate_risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio"""
        if not self.stop_loss_price or not self.take_profit_price:
            return None

        if self.side == PositionSide.LONG:
            risk = abs(self.entry_price - self.stop_loss_price)
            reward = abs(self.take_profit_price - self.entry_price)
        else:  # SHORT
            risk = abs(self.stop_loss_price - self.entry_price)
            reward = abs(self.entry_price - self.take_profit_price)

        if risk == 0:
            return None

        return float(reward / risk)

    @classmethod
    def from_broker_position(
        cls,
        broker_position: Position,
        position_id: str,
        stop_loss_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
        entry_order_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> "ManagedPosition":
        """
        Create ManagedPosition from broker Position.

        Useful for converting broker positions to managed positions.
        """
        return cls(
            position_id=position_id,
            ticker=broker_position.ticker,
            side=broker_position.side,
            quantity=broker_position.quantity,
            entry_price=broker_position.entry_price,
            current_price=broker_position.current_price,
            cost_basis=broker_position.cost_basis,
            market_value=broker_position.market_value,
            unrealized_pnl=broker_position.unrealized_pnl,
            unrealized_pnl_pct=broker_position.unrealized_pnl_pct,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            opened_at=broker_position.opened_at,
            updated_at=broker_position.updated_at,
            entry_order_id=entry_order_id,
            signal_id=signal_id,
            strategy=strategy,
            metadata=broker_position.metadata.copy(),
        )
```

#### Step 2: Fix Sync Version

**Option A: Import from canonical (recommended)**
```python
# position_manager_sync.py
from .types.positions import ManagedPosition, ClosedPosition, PositionSide

# Remove duplicate definitions (lines 32-100)
```

**Option B: Keep separate but fix bugs**
```python
# position_manager_sync.py (if must keep separate)

@dataclass
class ManagedPosition:
    # ... existing fields ...

    # FIX: Add side field
    side: PositionSide = PositionSide.LONG  # Default for backward compatibility

    # FIX: Add metadata field
    metadata: Dict = field(default_factory=dict)

    def should_stop_loss(self) -> bool:
        """Check if current price has hit stop loss."""
        if not self.stop_loss_price:
            return False

        # FIX: Side-aware logic
        if self.side == PositionSide.LONG:
            return self.current_price <= self.stop_loss_price
        else:  # SHORT
            return self.current_price >= self.stop_loss_price

    def should_take_profit(self) -> bool:
        """Check if current price has hit take profit."""
        if not self.take_profit_price:
            return False

        # FIX: Side-aware logic
        if self.side == PositionSide.LONG:
            return self.current_price >= self.take_profit_price
        else:  # SHORT
            return self.current_price <= self.take_profit_price

    # FIX: Add missing method
    def calculate_risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio"""
        if not self.stop_loss_price or not self.take_profit_price:
            return None

        if self.side == PositionSide.LONG:
            risk = abs(self.entry_price - self.stop_loss_price)
            reward = abs(self.take_profit_price - self.entry_price)
        else:  # SHORT
            risk = abs(self.stop_loss_price - self.entry_price)
            reward = abs(self.entry_price - self.take_profit_price)

        if risk == 0:
            return None

        return float(reward / risk)
```

### Migration Guide

#### Phase 1: Create Canonical Type (Day 1)

1. Add ManagedPosition to types/positions.py
2. Import from canonical in portfolio/position_manager.py
3. Test async position manager

#### Phase 2: Fix Sync Version (Day 2)

1. Add missing fields to sync version:
   - `side: PositionSide = PositionSide.LONG`
   - `metadata: Dict = field(default_factory=dict)`

2. Fix methods:
   - Update should_stop_loss() with side-aware logic
   - Update should_take_profit() with side-aware logic
   - Add calculate_risk_reward_ratio() method

3. Update database schema migration:
   ```sql
   -- Add side column to positions table
   ALTER TABLE positions ADD COLUMN side TEXT DEFAULT 'long';
   ```

#### Phase 3: Update Paper Trader (Day 3)

1. Update paper_trader.py to use canonical ManagedPosition
2. Test with live paper trading environment
3. Verify stop loss/take profit logic works for both sides

#### Phase 4: Database Migration (Day 4)

```python
# migrations/add_position_side.py

def upgrade_positions_table():
    """Add side column to existing positions table"""

    import sqlite3
    from pathlib import Path

    db_path = Path("data/trading.db")

    with sqlite3.connect(db_path) as conn:
        # Add side column (default to 'long' for existing positions)
        conn.execute("""
            ALTER TABLE positions
            ADD COLUMN side TEXT DEFAULT 'long'
        """)

        # Add side column to closed_positions too
        conn.execute("""
            ALTER TABLE closed_positions
            ADD COLUMN side TEXT DEFAULT 'long'
        """)

        conn.commit()
```

### Verification Plan

```bash
# Test async version
pytest tests/test_trading_engine.py::test_managed_position -v

# Test sync version
pytest tests/test_position_manager_sync.py -v

# Test paper trader
pytest tests/test_paper_trader.py -v

# Integration test
pytest tests/integration/test_position_lifecycle.py -v
```

---

## 3. CLOSEDPOSITION DUPLICATION

### Current State Analysis

#### Async ClosedPosition (/home/user/catalyst-bot/src/catalyst_bot/portfolio/position_manager.py:174-219)

```python
@dataclass
class ClosedPosition:
    """
    Represents a closed trading position.
    """

    # Identity
    position_id: str
    ticker: str
    side: PositionSide

    # Quantities
    quantity: int
    entry_price: Decimal
    exit_price: Decimal

    # P&L
    cost_basis: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal

    # Timestamps
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int

    # Exit details
    exit_reason: str  # 'stop_loss', 'take_profit', 'manual', 'timeout'
    exit_order_id: Optional[str] = None

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def was_profitable(self) -> bool:
        """Check if position was profitable"""
        return self.realized_pnl > 0

    def get_hold_duration_hours(self) -> float:
        """Get hold duration in hours"""
        return self.hold_duration_seconds / 3600.0
```

**Features:**
- 15 fields
- Has `side` field
- Has `metadata` field
- 2 utility methods

#### Sync ClosedPosition (/home/user/catalyst-bot/src/catalyst_bot/position_manager_sync.py:81-100)

```python
@dataclass
class ClosedPosition:
    """Represents a closed trading position with realized P&L."""

    position_id: str
    ticker: str
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int
    exit_reason: str  # 'stop_loss', 'take_profit', 'manual', 'max_hold_time'
    exit_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "catalyst_alert"
```

**Features:**
- 13 fields (missing side, metadata)
- No methods
- Different exit_reason values

### Field-by-Field Comparison

| Field | Async | Sync | Notes |
|-------|-------|------|-------|
| position_id | ✓ | ✓ | Same |
| ticker | ✓ | ✓ | Same |
| **side** | ✓ (PositionSide) | ✗ | **Missing in sync** |
| quantity | ✓ | ✓ | Same |
| entry_price | ✓ | ✓ | Same |
| exit_price | ✓ | ✓ | Same |
| cost_basis | ✓ | ✓ | Same |
| realized_pnl | ✓ | ✓ | Same |
| realized_pnl_pct | ✓ | ✓ | Same |
| opened_at | ✓ | ✓ | Same |
| closed_at | ✓ | ✓ | Same |
| hold_duration_seconds | ✓ | ✓ | Same |
| exit_reason | ✓ (timeout) | ✓ (max_hold_time) | Different values |
| exit_order_id | ✓ | ✓ | Same |
| entry_order_id | ✓ | ✓ | Same |
| signal_id | ✓ | ✓ | Same |
| strategy | ✓ (Optional[str]) | ✓ (str with default) | Different types |
| **metadata** | ✓ | ✗ | **Missing in sync** |

**Methods:**

| Method | Async | Sync |
|--------|-------|------|
| was_profitable() | ✓ | ✗ |
| get_hold_duration_hours() | ✓ | ✗ |

### Consolidation Strategy

**Recommendation:** Use async version as canonical, add methods to sync or import canonical

#### Canonical ClosedPosition

```python
# /home/user/catalyst-bot/src/catalyst_bot/types/positions.py

@dataclass
class ClosedPosition:
    """
    Closed trading position with realized P&L.

    Records complete trade lifecycle including entry/exit details,
    P&L, and trade metadata for analysis.
    """

    # Identity
    position_id: str
    ticker: str
    side: PositionSide = PositionSide.LONG  # Default for backward compatibility

    # Quantities
    quantity: int = 0
    entry_price: Decimal = Decimal("0")
    exit_price: Decimal = Decimal("0")

    # P&L
    cost_basis: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    realized_pnl_pct: Decimal = Decimal("0")

    # Timestamps
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: datetime = field(default_factory=datetime.now)
    hold_duration_seconds: int = 0

    # Exit details
    exit_reason: str = "manual"  # 'stop_loss', 'take_profit', 'manual', 'timeout'
    exit_order_id: Optional[str] = None

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def was_profitable(self) -> bool:
        """Check if position was profitable"""
        return self.realized_pnl > 0

    def get_hold_duration_hours(self) -> float:
        """Get hold duration in hours"""
        return self.hold_duration_seconds / 3600.0

    @classmethod
    def from_managed_position(
        cls,
        position: ManagedPosition,
        exit_price: Decimal,
        exit_reason: str,
        exit_order_id: Optional[str] = None,
    ) -> "ClosedPosition":
        """
        Create ClosedPosition from ManagedPosition.

        Calculates realized P&L and hold duration.
        """
        closed_at = datetime.now()
        hold_duration = int((closed_at - position.opened_at).total_seconds())

        # Calculate realized P&L
        if position.side == PositionSide.LONG:
            realized_pnl = (exit_price - position.entry_price) * position.quantity
        else:  # SHORT
            realized_pnl = (position.entry_price - exit_price) * position.quantity

        realized_pnl_pct = (
            realized_pnl / position.cost_basis
            if position.cost_basis > 0
            else Decimal("0")
        )

        return cls(
            position_id=position.position_id,
            ticker=position.ticker,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            cost_basis=position.cost_basis,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            opened_at=position.opened_at,
            closed_at=closed_at,
            hold_duration_seconds=hold_duration,
            exit_reason=exit_reason,
            exit_order_id=exit_order_id,
            entry_order_id=position.entry_order_id,
            signal_id=position.signal_id,
            strategy=position.strategy,
            metadata=position.metadata.copy(),
        )
```

### Migration Guide

Same approach as ManagedPosition:
1. Create canonical type
2. Import in both async and sync versions
3. Add database migration for `side` column
4. Update tests

---

## 4. LLM MONITOR CLASSES

### Current State Analysis

This is the most complex duplication - two completely separate LLM monitoring systems running in parallel.

#### LLMUsageMonitor (PRIMARY - /home/user/catalyst-bot/src/catalyst_bot/llm_usage_monitor.py)

**Architecture:**
- JSONL file-based persistent logging
- Real-time cost accumulator (in-memory)
- Multi-tier alerting (warn/crit/emergency)
- Model availability flags for cost control
- Automatic model disabling on threshold breach

**Dataclasses:**
```python
# Line 34
@dataclass
class LLMUsageEvent:
    timestamp: str
    provider: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    success: bool
    error: Optional[str] = None
    article_length: Optional[int] = None
    ticker: Optional[str] = None

# Line 60
@dataclass
class ProviderStats:
    provider: str
    model: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_input_cost: float = 0.0
    total_output_cost: float = 0.0
    total_cost: float = 0.0
    requests_last_hour: int = 0
    requests_last_day: int = 0

# Line 87
@dataclass
class UsageSummary:
    period_start: str
    period_end: str
    gemini: ProviderStats
    anthropic: ProviderStats
    local: ProviderStats
    total_requests: int
    total_tokens: int
    total_cost: float
    cost_by_provider: Dict[str, float]
    cost_by_operation: Dict[str, float]
```

**Key Features:**
```python
class LLMUsageMonitor:
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or settings.data_dir / "logs" / "llm_usage.jsonl"

        # Real-time cost tracking
        self.realtime_cost_today = 0.0
        self.last_reset_day: Optional[str] = None

        # Model availability flags
        self.model_availability = {
            "gemini-2.0-flash-lite": True,
            "gemini-2.5-flash": True,
            "gemini-2.5-pro": True,
            "anthropic": True,
        }

    def log_usage(self, provider, model, operation, input_tokens, output_tokens, ...):
        """Log to JSONL file and update real-time accumulators"""

    def check_cost_threshold(self, threshold_name: str = "warn") -> bool:
        """Instant threshold check without reading log file"""

    def disable_model(self, model_name: str):
        """Disable expensive model when threshold exceeded"""

    def get_stats(self, since, until) -> UsageSummary:
        """Read JSONL file and aggregate stats"""
```

**Usage:**
- Primary monitoring system
- Used by llm_hybrid.py for cost tracking
- scripts/llm_usage_report.py reads stats
- Heartbeat reads from JSONL file

#### LLMMonitor (UNUSED - /home/user/catalyst-bot/src/catalyst_bot/services/llm_monitor.py)

**Architecture:**
- In-memory stats only (no persistence)
- Thread-safe counters
- Single daily/monthly cost tracking
- No model availability control

**Key Features:**
```python
class LLMMonitor:
    def __init__(self, config: dict):
        self.lock = threading.Lock()

        # Statistics (in-memory only)
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "total_cost_usd": 0.0,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
            "total_latency_ms": 0.0,
        }

        # Breakdowns (in-memory)
        self.cost_by_provider = defaultdict(float)
        self.cost_by_feature = defaultdict(float)
        self.cost_by_model = defaultdict(float)

        # Daily/monthly tracking
        self.daily_cost = 0.0
        self.monthly_cost = 0.0

    def track_request(self, feature, provider, model, tokens_input, tokens_output, cost_usd, latency_ms, cached, error):
        """Track request (in-memory only)"""

    def get_stats(self) -> Dict:
        """Return in-memory stats"""
```

**Usage:**
- Created in services/llm_service.py (line 222)
- **NEVER ACTUALLY USED** - monitor created but track_request() never called
- Commented in heartbeat-audit/PATCH-01-critical-bugs.md as unused

### Key Differences

| Feature | LLMUsageMonitor | LLMMonitor | Winner |
|---------|----------------|------------|--------|
| **Persistence** | ✓ (JSONL file) | ✗ (in-memory) | LLMUsageMonitor |
| **Real-time cost** | ✓ (accumulator) | ✓ (in-memory) | Tie |
| **Model control** | ✓ (availability flags) | ✗ | LLMUsageMonitor |
| **Multi-tier alerts** | ✓ (warn/crit/emergency) | ✓ (daily/monthly) | LLMUsageMonitor |
| **Heartbeat integration** | ✓ (reads JSONL) | ✗ | LLMUsageMonitor |
| **Cache tracking** | ✗ | ✓ (cache hits/misses) | LLMMonitor |
| **Latency tracking** | ✗ | ✓ (avg latency) | LLMMonitor |
| **Thread safety** | ✗ | ✓ (lock) | LLMMonitor |
| **Actually used** | ✓ | ✗ | **LLMUsageMonitor** |

### Consolidation Strategy

**Recommendation:** Keep LLMUsageMonitor, remove LLMMonitor, add missing features

#### Enhanced LLMUsageMonitor

```python
# llm_usage_monitor.py

class LLMUsageMonitor:
    """
    Unified LLM usage tracker.

    Combines features from both monitors:
    - JSONL persistent logging (from LLMUsageMonitor)
    - Real-time cost tracking (from LLMUsageMonitor)
    - Model availability control (from LLMUsageMonitor)
    - Cache hit tracking (from LLMMonitor)
    - Latency tracking (from LLMMonitor)
    - Thread safety (from LLMMonitor)
    """

    def __init__(self, log_path: Optional[Path] = None):
        # Existing fields...

        # NEW: Thread safety (from LLMMonitor)
        import threading
        self.lock = threading.Lock()

        # NEW: Cache tracking (from LLMMonitor)
        self.cache_hits = 0
        self.cache_misses = 0

        # NEW: Latency tracking (from LLMMonitor)
        self.total_latency_ms = 0.0
        self.request_count = 0

    def log_usage(
        self,
        provider: str,
        model: str,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        success: bool = True,
        error: Optional[str] = None,
        article_length: Optional[int] = None,
        ticker: Optional[str] = None,
        # NEW parameters
        cached: bool = False,
        latency_ms: float = 0.0,
    ) -> LLMUsageEvent:
        """
        Log LLM API call with enhanced tracking.

        NEW: Thread-safe, tracks cache hits and latency.
        """
        with self.lock:  # NEW: Thread safety
            # Calculate costs (existing logic)
            pricing = PRICING.get(provider, {}).get(model, {"input": 0.0, "output": 0.0})
            input_cost = input_tokens * pricing["input"]
            output_cost = output_tokens * pricing["output"]
            total_cost = input_cost + output_cost

            # Create event (existing logic)
            event = LLMUsageEvent(...)

            # Write to log file (existing logic)
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(event)) + "\n")
            except Exception as e:
                _logger.warning("llm_usage_log_write_failed err=%s", str(e))

            # Update real-time cost (existing logic)
            self._update_realtime_cost(total_cost)

            # NEW: Cache tracking
            if cached:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

            # NEW: Latency tracking
            self.total_latency_ms += latency_ms
            self.request_count += 1

            # Check alerts (existing logic)
            self._check_alerts()

            return event

    def get_stats(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        include_realtime: bool = False,  # NEW parameter
    ) -> UsageSummary:
        """
        Get usage statistics.

        NEW: Optionally include real-time cache/latency stats.
        """
        with self.lock:  # NEW: Thread safety
            # Existing aggregation from JSONL...
            summary = UsageSummary(...)

            # NEW: Add real-time stats if requested
            if include_realtime:
                summary.metadata = {
                    "cache_hits": self.cache_hits,
                    "cache_misses": self.cache_misses,
                    "cache_hit_rate": (
                        self.cache_hits / (self.cache_hits + self.cache_misses)
                        if (self.cache_hits + self.cache_misses) > 0
                        else 0.0
                    ),
                    "avg_latency_ms": (
                        self.total_latency_ms / self.request_count
                        if self.request_count > 0
                        else 0.0
                    ),
                }

            return summary
```

### Migration Guide

#### Phase 1: Enhance LLMUsageMonitor (Week 1)

1. **Add thread safety:**
   ```python
   import threading

   class LLMUsageMonitor:
       def __init__(self, ...):
           self.lock = threading.Lock()
           # ... rest of init
   ```

2. **Add cache tracking:**
   ```python
   def log_usage(self, ..., cached: bool = False):
       with self.lock:
           if cached:
               self.cache_hits += 1
           else:
               self.cache_misses += 1
   ```

3. **Add latency tracking:**
   ```python
   def log_usage(self, ..., latency_ms: float = 0.0):
       with self.lock:
           self.total_latency_ms += latency_ms
           self.request_count += 1
   ```

#### Phase 2: Remove LLMMonitor (Week 1)

1. **Remove file:**
   ```bash
   git rm src/catalyst_bot/services/llm_monitor.py
   ```

2. **Update imports in llm_service.py:**
   ```python
   # OLD (line 222):
   from .llm_monitor import LLMMonitor

   # NEW:
   from ..llm_usage_monitor import LLMUsageMonitor as LLMMonitor
   # OR just remove - it's not used anyway
   ```

3. **Update tests:**
   ```bash
   # Remove or update tests that reference LLMMonitor
   git rm tests/test_llm_monitor.py  # if exists
   ```

#### Phase 3: Update Call Sites (Week 2)

Currently no call sites use LLMMonitor.track_request(), but if any are added in future:

```python
# OLD (unused):
monitor.track_request(
    feature="sec_analysis",
    provider="gemini",
    model="gemini-2.5-flash",
    tokens_input=1000,
    tokens_output=500,
    cost_usd=0.001,
    latency_ms=250.0,
    cached=False,
    error=None
)

# NEW:
from llm_usage_monitor import get_monitor

monitor = get_monitor()
monitor.log_usage(
    provider="gemini",
    model="gemini-2.5-flash",
    operation="sec_analysis",
    input_tokens=1000,
    output_tokens=500,
    cached=False,
    latency_ms=250.0,
)
```

### Verification Plan

```bash
# Test enhanced monitor
pytest tests/manual/test_llm_usage_monitor.py -v

# Test heartbeat integration
pytest tests/test_heartbeat.py::test_llm_usage_hourly -v

# Run cost report
python scripts/llm_usage_report.py

# Verify thread safety
python -c "
from catalyst_bot.llm_usage_monitor import get_monitor
import threading

monitor = get_monitor()

def log_many():
    for i in range(1000):
        monitor.log_usage('gemini', 'gemini-2.5-flash', 'test', 100, 50)

threads = [threading.Thread(target=log_many) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()

print(f'Total requests: {monitor.request_count}')
print('✓ Thread safety test passed')
"
```

---

## 5. ROUTER CLASSES

### Current State Analysis

Two separate routing systems with different philosophies.

#### HybridLLMRouter (PRIMARY - /home/user/catalyst-bot/src/catalyst_bot/llm_hybrid.py:536)

**Philosophy:** Three-tier fallback (Local → Gemini → Claude)

**Features:**
- Automatic routing based on article length
- Rate limit tracking with exponential backoff
- Model tiering (Flash-Lite, Flash, Pro)
- Complexity-based routing
- Health tracking
- Provider fallback chain

**Key Methods:**
```python
class HybridLLMRouter:
    def __init__(self, config: Optional[HybridConfig] = None):
        # Rate limit trackers
        self.gemini_rate_limiter = RateLimitTracker(requests_per_minute=15, ...)
        self.flash_lite_rate_limiter = RateLimitTracker(requests_per_minute=500, ...)
        self.claude_rate_limiter = RateLimitTracker(requests_per_minute=50, ...)

        # Health tracking
        self.local_healthy = True
        self.gemini_quota_remaining = 1500

    async def route_request(
        self,
        prompt: str,
        article_length: Optional[int] = None,
        priority: str = "normal",
        model_override: Optional[str] = None,
    ) -> Optional[str]:
        """Route through fallback chain: Local → Gemini → Claude"""
```

**Routing Logic:**
1. Try local Mistral if article < 1000 chars
2. Try Gemini (Flash-Lite/Flash/Pro based on complexity)
3. Try Claude as last resort

#### LLMRouter (SECONDARY - /home/user/catalyst-bot/src/catalyst_bot/services/llm_router.py:31)

**Philosophy:** Intelligent model selection based on task complexity

**Features:**
- Probability-based routing
- Cost-aware routing
- Provider health checks
- A/B testing support
- Fallback strategies

**Key Methods:**
```python
class LLMRouter:
    # Routing probabilities by complexity
    ROUTING_TABLE = {
        TaskComplexity.SIMPLE: [
            ("gemini_flash_lite", 0.70),  # 70% Flash Lite
            ("gemini_flash", 0.30),       # 30% Flash
        ],
        TaskComplexity.MEDIUM: [
            ("gemini_flash", 0.90),       # 90% Flash
            ("gemini_pro", 0.10),         # 10% Pro
        ],
        TaskComplexity.COMPLEX: [
            ("gemini_pro", 0.80),         # 80% Pro
            ("claude_sonnet", 0.20),      # 20% Sonnet
        ],
        TaskComplexity.CRITICAL: [
            ("claude_sonnet", 1.00),      # 100% Sonnet
        ],
    }

    def select_provider(self, complexity: Optional[TaskComplexity]) -> Tuple[str, str]:
        """Select provider based on complexity and probabilities"""
```

**Routing Logic:**
1. Classify task by complexity (SIMPLE/MEDIUM/COMPLEX/CRITICAL)
2. Weighted random selection from routing table
3. Filter out unhealthy providers
4. Return (provider_name, model_name)

### Key Differences

| Feature | HybridLLMRouter | LLMRouter | Winner |
|---------|-----------------|-----------|--------|
| **Fallback chain** | ✓ (Local→Gemini→Claude) | ✗ | HybridLLMRouter |
| **Rate limiting** | ✓ (per-provider trackers) | ✗ | HybridLLMRouter |
| **Complexity routing** | ✓ (auto-select model) | ✓ (probability-based) | Tie |
| **Probability routing** | ✗ | ✓ (weighted random) | LLMRouter |
| **Provider health** | ✓ (local_healthy flag) | ✓ (health dict) | Tie |
| **Cost awareness** | ✓ (via model selection) | ✓ (MODEL_COSTS) | Tie |
| **A/B testing** | ✗ | ✓ (probability distribution) | LLMRouter |
| **Actually used** | ✓ (primary router) | ✓ (in llm_service) | Both |

### Usage Comparison

**HybridLLMRouter:**
```python
# Global instance
_router: Optional[HybridLLMRouter] = None

async def query_hybrid_llm(prompt, article_length, priority, model_override):
    global _router
    if _router is None:
        _router = HybridLLMRouter()
    return await _router.route_request(prompt, article_length, priority, model_override)

# Called by:
# - llm_hybrid.py module functions
# - Various services that need LLM routing
```

**LLMRouter:**
```python
# Created in LLMService
class LLMService:
    def __init__(self, config: dict):
        self.router = LLMRouter(config)

    async def query(self, prompt: str, complexity: TaskComplexity):
        provider, model = self.router.select_provider(complexity)
        # ... call provider
```

### Consolidation Strategy

**Recommendation:** Merge capabilities - use HybridLLMRouter as base, add LLMRouter's probability routing

#### Enhanced HybridLLMRouter

```python
# llm_hybrid.py

class HybridLLMRouter:
    """
    Unified LLM router combining:
    - Three-tier fallback (from HybridLLMRouter)
    - Rate limit tracking (from HybridLLMRouter)
    - Probability-based routing (from LLMRouter)
    - A/B testing support (from LLMRouter)
    """

    # NEW: Probability routing tables (from LLMRouter)
    ROUTING_TABLE = {
        TaskComplexity.SIMPLE: [
            ("gemini_flash_lite", 0.70),
            ("gemini_flash", 0.30),
        ],
        TaskComplexity.MEDIUM: [
            ("gemini_flash", 0.90),
            ("gemini_pro", 0.10),
        ],
        TaskComplexity.COMPLEX: [
            ("gemini_pro", 0.80),
            ("claude_sonnet", 0.20),
        ],
        TaskComplexity.CRITICAL: [
            ("claude_sonnet", 1.00),
        ],
    }

    def __init__(self, config: Optional[HybridConfig] = None, use_probability_routing: bool = False):
        # Existing init...

        # NEW: Probability routing mode
        self.use_probability_routing = use_probability_routing

    async def route_request(
        self,
        prompt: str,
        article_length: Optional[int] = None,
        priority: str = "normal",
        model_override: Optional[str] = None,
        complexity: Optional[TaskComplexity] = None,  # NEW parameter
    ) -> Optional[str]:
        """
        Route request with unified logic.

        Two modes:
        1. Fallback mode (default): Try Local → Gemini → Claude
        2. Probability mode: Use routing table based on complexity
        """
        if self.use_probability_routing and complexity:
            # NEW: Probability-based routing (from LLMRouter)
            provider, model = self._select_by_probability(complexity)
            return await self._call_provider(provider, model, prompt)
        else:
            # Existing fallback logic
            # Try local → Gemini → Claude
            ...

    def _select_by_probability(self, complexity: TaskComplexity) -> Tuple[str, str]:
        """
        Select provider using probability distribution.

        From LLMRouter.
        """
        options = self.ROUTING_TABLE.get(complexity, self.ROUTING_TABLE[TaskComplexity.MEDIUM])

        # Filter healthy providers
        healthy_options = [
            (provider, prob)
            for provider, prob in options
            if self._is_provider_healthy(provider)
        ]

        if not healthy_options:
            healthy_options = options

        # Weighted random selection
        import random
        total_prob = sum(prob for _, prob in healthy_options)
        rand = random.random()
        cumulative = 0.0

        for provider, prob in healthy_options:
            cumulative += prob / total_prob
            if rand <= cumulative:
                model_name = self._get_model_name(provider)
                return provider, model_name

        # Fallback
        return healthy_options[-1][0], self._get_model_name(healthy_options[-1][0])
```

### Migration Guide

#### Option A: Merge into HybridLLMRouter (Recommended)

1. **Add probability routing to HybridLLMRouter:**
   - Copy ROUTING_TABLE from LLMRouter
   - Add use_probability_routing flag
   - Implement _select_by_probability() method

2. **Update LLMService:**
   ```python
   # services/llm_service.py

   # OLD:
   from .llm_router import LLMRouter
   self.router = LLMRouter(config)

   # NEW:
   from ..llm_hybrid import HybridLLMRouter
   self.router = HybridLLMRouter(use_probability_routing=True)
   ```

3. **Remove llm_router.py:**
   ```bash
   git rm src/catalyst_bot/services/llm_router.py
   ```

#### Option B: Keep Separate (If Different Use Cases)

If fallback routing and probability routing serve fundamentally different purposes:

1. **Rename for clarity:**
   - HybridLLMRouter → FallbackLLMRouter
   - LLMRouter → ProbabilityLLMRouter

2. **Create router factory:**
   ```python
   # routing/__init__.py

   from .fallback_router import FallbackLLMRouter
   from .probability_router import ProbabilityLLMRouter

   def create_router(strategy: str = "fallback", **kwargs):
       """
       Create LLM router based on strategy.

       Args:
           strategy: "fallback" or "probability"
       """
       if strategy == "fallback":
           return FallbackLLMRouter(**kwargs)
       elif strategy == "probability":
           return ProbabilityLLMRouter(**kwargs)
       else:
           raise ValueError(f"Unknown strategy: {strategy}")
   ```

### Verification Plan

```bash
# Test probability routing
pytest tests/test_llm_router_logic.py -v

# Test fallback routing
pytest tests/test_llm_hybrid.py -v

# Test rate limiting
pytest tests/test_rate_limiting.py -v

# Integration test
pytest tests/integration/test_llm_routing.py -v
```

---

## 6. TRADE RESULT TYPES

### Current State Analysis

#### TradeResult (/home/user/catalyst-bot/src/catalyst_bot/backtesting/trade_simulator.py:20)

```python
@dataclass
class TradeResult:
    """Result of a simulated trade execution."""

    executed: bool
    shares: int
    entry_price: float
    fill_price: float
    slippage_pct: float
    cost_basis: float
    commission: float
    reason: str
```

**Purpose:** Execution result with slippage and commission details

#### TradeSimResult (/home/user/catalyst-bot/src/catalyst_bot/models.py:179)

```python
@dataclass
class TradeSimResult:
    """Result of a single trade simulation.

    Stores the NewsItem, entry offset, hold duration and returns dict.
    """

    item: NewsItem
    entry_offset: int
    hold_duration: int
    returns: Dict[str, float]
```

**Purpose:** Simulation result with timing and returns

### Analysis

**These are NOT duplicates** - they serve different purposes:
- **TradeResult:** Low-level execution details (did trade execute? what was slippage?)
- **TradeSimResult:** High-level simulation results (what were returns over time?)

**Relationship:**
```
NewsItem → TradeSimulator → TradeResult (execution) → TradeSimResult (final results)
```

**Recommendation:** Keep both, but clarify naming and documentation

### Enhanced Documentation

```python
# backtesting/trade_simulator.py

@dataclass
class TradeExecutionResult:  # Rename from TradeResult for clarity
    """
    Result of a single trade execution attempt.

    Records low-level execution details including:
    - Whether trade was executed
    - Slippage and commission
    - Fill price vs. quote price
    - Execution rejection reason

    Used by:
    - PennyStockTradeSimulator.execute_trade()
    - Portfolio.open_position() / close_position()
    """
    executed: bool
    shares: int
    entry_price: float
    fill_price: float
    slippage_pct: float
    cost_basis: float
    commission: float
    reason: str
```

```python
# models.py

@dataclass
class TradeSimResult:
    """
    Result of a complete trade simulation.

    Records high-level simulation results including:
    - Original news item that triggered trade
    - Entry timing (offset from alert)
    - Hold duration
    - Returns across different timeframes

    Used by:
    - tradesim.py for backtesting
    - learning.py for ML training
    - backtest/simulator.py for analysis

    One TradeSimResult may involve multiple TradeExecutionResults
    (entry execution + exit execution).
    """
    item: NewsItem
    entry_offset: int
    hold_duration: int
    returns: Dict[str, float]  # e.g., {"1h": 0.05, "4h": 0.12}
```

### Migration Guide

**Optional Rename (for clarity):**

```python
# Step 1: Add TypeAlias for backward compatibility
# backtesting/trade_simulator.py

@dataclass
class TradeExecutionResult:
    """Result of a single trade execution attempt."""
    # ... existing fields

# Backward compatibility
TradeResult = TradeExecutionResult  # TypeAlias
```

```python
# Step 2: Update call sites over time
# No breaking changes - both names work
```

---

## IMPLEMENTATION ROADMAP

### Week 1: Foundation Types

**Day 1-2: Position Classes**
- [ ] Create `src/catalyst_bot/types/__init__.py`
- [ ] Create `src/catalyst_bot/types/positions.py`
- [ ] Implement canonical Position class
- [ ] Add backward compatibility properties
- [ ] Write comprehensive tests

**Day 3-4: Update Broker Interface**
- [ ] Update broker_interface.py imports
- [ ] Remove duplicate Position definition
- [ ] Update PositionSide import
- [ ] Run broker tests
- [ ] Update integration tests

**Day 5: Update Backtesting**
- [ ] Update backtesting/portfolio.py imports
- [ ] Remove duplicate Position definition
- [ ] Verify backward compatibility
- [ ] Run backtesting tests

### Week 2: Managed Positions

**Day 1-2: Canonical ManagedPosition**
- [ ] Add ManagedPosition to types/positions.py
- [ ] Add ClosedPosition to types/positions.py
- [ ] Include all methods and fields
- [ ] Test side-aware logic
- [ ] Add from_broker_position() factory

**Day 3: Fix Sync Version**
- [ ] Add `side` field to sync ManagedPosition
- [ ] Add `metadata` field
- [ ] Fix should_stop_loss() logic
- [ ] Fix should_take_profit() logic
- [ ] Add calculate_risk_reward_ratio() method

**Day 4-5: Database Migration**
- [ ] Create migration script for `side` column
- [ ] Run migration on test database
- [ ] Update position_manager_sync.py to use canonical types
- [ ] Test paper trader with enhanced types
- [ ] Verify production database compatibility

### Week 3: LLM Monitoring

**Day 1-2: Enhance LLMUsageMonitor**
- [ ] Add threading.Lock for thread safety
- [ ] Add cache_hits/cache_misses tracking
- [ ] Add latency tracking
- [ ] Add cached and latency_ms parameters to log_usage()
- [ ] Update get_stats() to include real-time metrics

**Day 3: Remove LLMMonitor**
- [ ] Remove services/llm_monitor.py
- [ ] Update services/llm_service.py imports
- [ ] Verify no other imports exist
- [ ] Update tests

**Day 4-5: Integration**
- [ ] Update llm_hybrid.py to pass cache/latency
- [ ] Test thread safety with concurrent requests
- [ ] Verify heartbeat still works
- [ ] Run llm_usage_report.py
- [ ] Document enhanced API

### Week 4: Router Consolidation

**Day 1-3: Merge Routers**
- [ ] Add ROUTING_TABLE to HybridLLMRouter
- [ ] Add use_probability_routing flag
- [ ] Implement _select_by_probability() method
- [ ] Add complexity parameter to route_request()
- [ ] Test both routing modes

**Day 4: Update LLMService**
- [ ] Update services/llm_service.py to use HybridLLMRouter
- [ ] Set use_probability_routing=True
- [ ] Remove services/llm_router.py
- [ ] Update tests

**Day 5: Verification**
- [ ] Test probability routing
- [ ] Test fallback routing
- [ ] Test rate limiting
- [ ] Integration tests
- [ ] Performance benchmarks

### Week 5: Documentation & Cleanup

**Day 1-2: Documentation**
- [ ] Update API documentation
- [ ] Add migration guides
- [ ] Document deprecations
- [ ] Update architecture diagrams
- [ ] Add code examples

**Day 3-4: Cleanup**
- [ ] Remove deprecated imports
- [ ] Clean up type annotations
- [ ] Run full test suite
- [ ] Fix any remaining type errors
- [ ] Update CI/CD

**Day 5: Release**
- [ ] Create release notes
- [ ] Tag version
- [ ] Deploy to staging
- [ ] Monitor for issues
- [ ] Deploy to production

---

## RISK MITIGATION

### High-Risk Changes

1. **Position class consolidation**
   - Risk: Breaking backtesting or broker integration
   - Mitigation: Extensive backward compatibility via properties
   - Rollback: TypeAlias allows instant rollback

2. **ManagedPosition side field**
   - Risk: Database schema changes in production
   - Mitigation: Default value ('long') for new column
   - Rollback: Column is nullable, can be dropped

3. **LLMMonitor removal**
   - Risk: Breaking services that depend on it
   - Mitigation: Currently unused, no actual call sites
   - Rollback: File can be restored if needed

### Testing Strategy

**Unit Tests:**
- Test each canonical type independently
- Test backward compatibility properties
- Test all methods with various inputs

**Integration Tests:**
- Test Position in backtesting engine
- Test Position in broker interface
- Test ManagedPosition in position manager
- Test LLMUsageMonitor in multi-threaded environment

**End-to-End Tests:**
- Full backtest with new Position types
- Paper trading with new ManagedPosition
- Live trading simulation
- LLM routing with enhanced monitoring

### Rollback Procedures

**Position Classes:**
```python
# Instant rollback via TypeAlias
# backtesting/portfolio.py
from dataclasses import dataclass

@dataclass
class Position:  # Restore original
    ticker: str
    shares: int
    # ... original fields
```

**ManagedPosition:**
```sql
-- Rollback database
ALTER TABLE positions DROP COLUMN side;
ALTER TABLE closed_positions DROP COLUMN side;
```

**LLMMonitor:**
```bash
# Restore file
git checkout HEAD~1 -- src/catalyst_bot/services/llm_monitor.py
```

---

## SUCCESS METRICS

### Code Quality
- [ ] 400+ lines of duplicate code removed
- [ ] Single source of truth for each type
- [ ] 100% test coverage on canonical types
- [ ] Zero mypy errors

### Functionality
- [ ] All existing tests pass
- [ ] Backtesting produces same results
- [ ] Paper trading works with enhanced types
- [ ] LLM monitoring tracks all metrics

### Performance
- [ ] No regression in backtest performance
- [ ] LLM monitoring overhead < 5ms per request
- [ ] Thread-safe monitoring with zero lock contention

### Documentation
- [ ] Complete API documentation
- [ ] Migration guide for each type
- [ ] Architecture diagrams updated
- [ ] Deprecation warnings in place

---

## CONCLUSION

WAVE 7 consolidates 6 major type definition duplications across the codebase, eliminating 400+ lines of duplicate code while enhancing functionality. The canonical types provide:

1. **Position:** Unified broker and backtesting position with Decimal precision
2. **ManagedPosition:** Side-aware position with risk/reward calculations
3. **ClosedPosition:** Complete trade lifecycle tracking
4. **LLMUsageMonitor:** Unified monitoring with persistence and real-time tracking
5. **HybridLLMRouter:** Combined fallback and probability routing

**Key Benefits:**
- Single source of truth for all types
- Enhanced type safety with Decimal and datetime
- Fixed critical bugs in sync position management
- Improved thread safety and performance
- Better cost control and monitoring

**Implementation Timeline:** 5 weeks
**Risk Level:** Medium (mitigated by extensive backward compatibility)
**Impact:** High (foundational improvement for entire codebase)
