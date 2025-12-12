# Implementation Plan: SignalGenerator Integration

## Overview

This document provides step-by-step instructions for integrating the `SignalGenerator` class into the `TradingEngine`. Currently, the TradingEngine uses a hardcoded stub method (`_generate_signal_stub()`) that applies naive signal generation with fixed risk parameters. The SignalGenerator provides sophisticated keyword-based signal generation with category-specific trading parameters:

- **FDA approval**: 92% confidence, 1.6x position size, 5% stop-loss, 12% take-profit
- **Merger/acquisition**: 95% confidence, 2.0x position size, 4% stop-loss, 15% take-profit
- **AVOID keywords**: Dilution, offerings, warrants - skip trade entirely
- **CLOSE keywords**: Bankruptcy, delisting, fraud - exit positions immediately

This integration enables the trading system to make smarter, keyword-driven decisions with appropriate risk management.

---

## Current State Analysis

### File: `src/catalyst_bot/trading/trading_engine.py`

**Issue 1: SignalGenerator Not Initialized** (Lines 154, 237-239)

```python
# Line 154 in __init__():
self.signal_generator = None  # Will be set after SignalGenerator is implemented

# Lines 237-239 in initialize():
# TODO: Initialize SignalGenerator (Agent 1 will implement)
# from .signal_generator import SignalGenerator
# self.signal_generator = SignalGenerator()
```

**Issue 2: Stub Method Used Instead of SignalGenerator** (Lines 295-296)

```python
# 2. Generate signal (stub for now - Agent 1 will implement)
signal = self._generate_signal_stub(scored_item, ticker, current_price)
```

**Issue 3: Stub Method is Hardcoded and Inflexible** (Lines 705-756)

The `_generate_signal_stub()` method uses:
- Fixed 2.0 score threshold
- Fixed 5% stop-loss for all keywords
- Fixed 10% take-profit for all keywords
- Fixed 3% position size
- No keyword-specific adjustments
- No AVOID/CLOSE signal handling

### File: `src/catalyst_bot/trading/signal_generator.py`

**Already Complete** - Contains fully implemented `SignalGenerator` class with:
- `BUY_KEYWORDS` mapping (fda, merger, partnership, trial, clinical, acquisition, uplisting)
- `AVOID_KEYWORDS` list (offering, dilution, warrant, rs, reverse_split)
- `CLOSE_KEYWORDS` list (bankruptcy, delisting, going_concern, fraud)
- `generate_signal()` method returning `Optional[TradingSignal]`
- Risk/reward verification (minimum 2:1 ratio)

---

## Target State

After implementation:

1. `SignalGenerator` is instantiated in `TradingEngine.__init__()`
2. `SignalGenerator` is used in `process_scored_item()` instead of the stub
3. The `_generate_signal_stub()` method is deprecated (kept for backward compatibility with tests)
4. Keyword-specific trading parameters are applied (FDA = 92% confidence, 1.6x size, etc.)
5. AVOID keywords result in `None` signal (skip trade)
6. CLOSE keywords result in position exit signals

---

## Dependencies & Libraries

### No New External Dependencies Required

All imports already exist in the codebase:

**Already imported in `trading_engine.py`:**
```python
from ..execution.order_executor import TradingSignal  # Line 44
from ..classify import ScoredItem  # Line 58
```

**New import needed:**
```python
from .signal_generator import SignalGenerator
```

---

## Implementation Steps

### Step 1: Add SignalGenerator Import

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Lines:** 59 (after existing imports)
**Action:** Add import statement

```python
from .signal_generator import SignalGenerator
```

**Insert after line 59:**
```python
from .market_data import MarketDataFeed  # Market data provider (Agent 3)
from .signal_generator import SignalGenerator  # Keyword-based signal generation
```

**Explanation:** This imports the SignalGenerator class from the same package, enabling instantiation in the TradingEngine.

---

### Step 2: Initialize SignalGenerator in Constructor

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Lines:** 154
**Action:** Replace `None` with SignalGenerator instantiation

**Current code (line 154):**
```python
self.signal_generator = None  # Will be set after SignalGenerator is implemented
```

**Replace with:**
```python
self.signal_generator: SignalGenerator = SignalGenerator()
```

**Explanation:** The SignalGenerator is instantiated in the constructor because:
1. It has no async dependencies (no broker/API connections)
2. It loads configuration from settings on initialization
3. It can be used immediately without waiting for `initialize()` to complete

---

### Step 3: Update initialize() Method - Remove TODO Comment

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Lines:** 237-239
**Action:** Replace TODO comment with logging confirmation

**Current code (lines 237-239):**
```python
# TODO: Initialize SignalGenerator (Agent 1 will implement)
# from .signal_generator import SignalGenerator
# self.signal_generator = SignalGenerator()
```

**Replace with:**
```python
# SignalGenerator is already initialized in __init__() since it has no async dependencies
self.logger.info(
    f"SignalGenerator ready: min_confidence={self.signal_generator.min_confidence:.2f}, "
    f"min_score={self.signal_generator.min_score:.2f}"
)
```

**Explanation:** Since SignalGenerator doesn't require async initialization (no broker connections), we only log its configuration here. The actual instantiation happens in `__init__()`.

---

### Step 4: Replace Stub with SignalGenerator in process_scored_item()

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Lines:** 295-296
**Action:** Replace stub call with SignalGenerator call

**Current code (lines 295-296):**
```python
# 2. Generate signal (stub for now - Agent 1 will implement)
signal = self._generate_signal_stub(scored_item, ticker, current_price)
```

**Replace with:**
```python
# 2. Generate signal using keyword-based SignalGenerator
signal = self.signal_generator.generate_signal(
    scored_item=scored_item,
    ticker=ticker,
    current_price=current_price,
)
```

**Explanation:** This is the core integration point. The SignalGenerator:
- Analyzes `scored_item.keyword_hits` for actionable keywords
- Returns `None` for AVOID keywords (offering, dilution, etc.)
- Returns CLOSE signal for distress keywords (bankruptcy, delisting)
- Returns BUY signal with keyword-specific parameters for bullish keywords
- Applies minimum score threshold (default 1.5)
- Applies minimum confidence threshold (default 0.6)
- Verifies 2:1 minimum risk/reward ratio

---

### Step 5: Deprecate the Stub Method

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Lines:** 701-756
**Action:** Add deprecation warning to stub method

**Current code (lines 701-704):**
```python
# ========================================================================
# Signal Generation (Stub for Agent 1)
# ========================================================================

def _generate_signal_stub(
```

**Replace with:**
```python
# ========================================================================
# Signal Generation (DEPRECATED - Use SignalGenerator Instead)
# ========================================================================

def _generate_signal_stub(
    self,
    scored_item: ScoredItem,
    ticker: str,
    current_price: Decimal,
) -> Optional[TradingSignal]:
    """
    DEPRECATED: Use SignalGenerator.generate_signal() instead.

    This stub method is kept for backward compatibility with existing tests.
    It will be removed in a future version.

    Args:
        scored_item: Scored item from classification
        ticker: Stock ticker
        current_price: Current price

    Returns:
        TradingSignal if actionable, None otherwise
    """
    import warnings
    warnings.warn(
        "_generate_signal_stub is deprecated. Use SignalGenerator.generate_signal() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # ... rest of existing stub code remains unchanged ...
```

**Explanation:** The stub is kept for backward compatibility with existing tests but marked as deprecated. This follows the deprecation pattern to give downstream users time to migrate.

---

### Step 6: Add Type Hint for signal_generator Attribute

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Lines:** 113-126 (class docstring area)
**Action:** Update type hints in class attributes section

Add to the `__init__` method's attribute definitions (around line 151-156):

**Current code:**
```python
# Initialize broker client
self.broker: Optional[AlpacaBrokerClient] = None
self.order_executor: Optional[OrderExecutor] = None
self.position_manager: Optional[PositionManager] = None
self.signal_generator = None  # Will be set after SignalGenerator is implemented
self.market_data_feed: Optional[MarketDataFeed] = None  # Market data provider (Agent 3)
```

**Replace with:**
```python
# Initialize broker client
self.broker: Optional[AlpacaBrokerClient] = None
self.order_executor: Optional[OrderExecutor] = None
self.position_manager: Optional[PositionManager] = None
self.signal_generator: SignalGenerator = SignalGenerator()
self.market_data_feed: Optional[MarketDataFeed] = None  # Market data provider (Agent 3)
```

**Explanation:** Proper type hints improve IDE support and static analysis.

---

## Wiring & Integration

### Data Flow After Integration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TRADING FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────┘

  runner.py
      │
      ▼
  ┌───────────────────┐
  │ ScoredItem        │  (from classify.py)
  │ - keyword_hits    │  e.g., ["fda", "approval"]
  │ - sentiment       │  e.g., 0.85
  │ - total score     │  e.g., 3.7
  └─────────┬─────────┘
            │
            ▼
  ┌───────────────────────────────────────────────────────────────────────────┐
  │ TradingEngine.process_scored_item(scored_item, ticker, current_price)     │
  │                                                                           │
  │   1. Check trading enabled                                                │
  │   2. self.signal_generator.generate_signal(scored_item, ticker, price) ◄──┼── NEW
  │   3. Handle CLOSE signals                                                 │
  │   4. Check risk limits                                                    │
  │   5. Execute signal via OrderExecutor                                     │
  └───────────────────────────────────────────────────────────────────────────┘
            │
            ▼
  ┌───────────────────────────────────────────────────────────────────────────┐
  │ SignalGenerator.generate_signal(scored_item, ticker, current_price)       │
  │                                                                           │
  │   1. Extract keyword_hits from scored_item                                │
  │   2. Determine action (buy/avoid/close) from keywords                     │
  │      - "fda" → BUY with KeywordConfig(confidence=0.92, size=1.6x, ...)   │
  │      - "offering" → AVOID (return None)                                   │
  │      - "bankruptcy" → CLOSE (return close signal)                         │
  │   3. Calculate confidence (base + sentiment alignment bonus)              │
  │   4. Calculate position_size_pct = base_pct * confidence * multiplier     │
  │   5. Calculate stop_loss_price and take_profit_price                      │
  │   6. Verify 2:1 risk/reward ratio                                         │
  │   7. Return TradingSignal                                                 │
  └───────────────────────────────────────────────────────────────────────────┘
            │
            ▼
  ┌───────────────────┐
  │ TradingSignal     │
  │ - action: "buy"   │
  │ - confidence: 0.92│
  │ - position_size_pct: 2.94% (2% * 0.92 * 1.6)
  │ - stop_loss: $24.22 (entry $25.50 - 5%)
  │ - take_profit: $28.56 (entry $25.50 + 12%)
  └───────────────────┘
```

### Keyword Configuration Reference

| Keyword     | Action | Confidence | Size Multiplier | Stop-Loss | Take-Profit |
|-------------|--------|------------|-----------------|-----------|-------------|
| fda         | BUY    | 92%        | 1.6x            | 5%        | 12%         |
| merger      | BUY    | 95%        | 2.0x            | 4%        | 15%         |
| partnership | BUY    | 85%        | 1.4x            | 5%        | 10%         |
| trial       | BUY    | 88%        | 1.5x            | 6%        | 12%         |
| clinical    | BUY    | 88%        | 1.5x            | 6%        | 12%         |
| acquisition | BUY    | 90%        | 1.7x            | 4.5%      | 14%         |
| uplisting   | BUY    | 87%        | 1.3x            | 5.5%      | 11%         |
| offering    | AVOID  | -          | -               | -         | -           |
| dilution    | AVOID  | -          | -               | -         | -           |
| warrant     | AVOID  | -          | -               | -         | -           |
| bankruptcy  | CLOSE  | 100%       | -               | -         | -           |
| delisting   | CLOSE  | 100%       | -               | -         | -           |
| fraud       | CLOSE  | 100%       | -               | -         | -           |

---

## Configuration

### Environment Variables (Optional)

The SignalGenerator reads these from settings if available:

| Variable                  | Default | Description                           |
|---------------------------|---------|---------------------------------------|
| `SIGNAL_MIN_CONFIDENCE`   | 0.6     | Minimum confidence to generate signal |
| `SIGNAL_MIN_SCORE`        | 1.5     | Minimum total score threshold         |
| `POSITION_SIZE_BASE_PCT`  | 2.0     | Base position size (%)                |
| `POSITION_SIZE_MAX_PCT`   | 5.0     | Maximum position size (%)             |
| `DEFAULT_STOP_LOSS_PCT`   | 5.0     | Default stop-loss (%)                 |
| `DEFAULT_TAKE_PROFIT_PCT` | 10.0    | Default take-profit (%)               |

### Programmatic Configuration

The SignalGenerator can also be configured via constructor:

```python
self.signal_generator = SignalGenerator(config={
    "min_confidence": 0.7,
    "min_score": 2.0,
    "base_position_pct": 2.5,
    "max_position_pct": 6.0,
    "default_stop_pct": 4.0,
    "default_tp_pct": 12.0,
})
```

---

## Testing Plan

### Unit Tests

#### Test File: `tests/test_signal_generator_integration.py`

```python
"""Unit tests for SignalGenerator integration with TradingEngine."""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from catalyst_bot.trading.trading_engine import TradingEngine
from catalyst_bot.trading.signal_generator import SignalGenerator
from catalyst_bot.models import ScoredItem


class TestSignalGeneratorIntegration:
    """Test SignalGenerator is properly wired into TradingEngine."""

    def test_signal_generator_initialized(self):
        """SignalGenerator should be initialized in TradingEngine constructor."""
        engine = TradingEngine({"trading_enabled": False})

        assert engine.signal_generator is not None
        assert isinstance(engine.signal_generator, SignalGenerator)

    def test_signal_generator_has_correct_defaults(self):
        """SignalGenerator should have expected default configuration."""
        engine = TradingEngine({"trading_enabled": False})

        assert engine.signal_generator.min_confidence == 0.6
        assert engine.signal_generator.min_score == 1.5

    def test_fda_keyword_generates_buy_signal(self):
        """FDA keyword should generate BUY signal with correct parameters."""
        engine = TradingEngine({"trading_enabled": False})

        scored_item = ScoredItem(
            relevance=3.7,
            sentiment=0.85,
            tags=["fda"],
            keyword_hits=["fda", "approval"],
        )

        signal = engine.signal_generator.generate_signal(
            scored_item=scored_item,
            ticker="XYPH",
            current_price=Decimal("25.50"),
        )

        assert signal is not None
        assert signal.action == "buy"
        assert signal.confidence >= 0.92  # FDA base confidence
        assert signal.stop_loss_price == Decimal("24.22")  # 5% stop
        assert signal.take_profit_price == Decimal("28.56")  # 12% target

    def test_offering_keyword_avoids_trade(self):
        """Offering keyword should result in None signal (AVOID)."""
        engine = TradingEngine({"trading_enabled": False})

        scored_item = ScoredItem(
            relevance=3.5,
            sentiment=0.5,
            tags=["offering"],
            keyword_hits=["offering", "dilution"],
        )

        signal = engine.signal_generator.generate_signal(
            scored_item=scored_item,
            ticker="DILUTE",
            current_price=Decimal("10.00"),
        )

        assert signal is None  # AVOID keywords should return None

    def test_bankruptcy_keyword_generates_close_signal(self):
        """Bankruptcy keyword should generate CLOSE signal."""
        engine = TradingEngine({"trading_enabled": False})

        scored_item = ScoredItem(
            relevance=4.0,
            sentiment=-0.9,
            tags=["bankruptcy"],
            keyword_hits=["bankruptcy", "chapter11"],
        )

        signal = engine.signal_generator.generate_signal(
            scored_item=scored_item,
            ticker="FAIL",
            current_price=Decimal("1.00"),
        )

        assert signal is not None
        assert signal.action == "close"
        assert signal.confidence == 1.0  # CLOSE signals are always high confidence
```

### Validation Criteria

1. **Unit Test Passing**: All tests in `test_signal_generator_integration.py` pass
2. **Integration Test Passing**: All tests in `test_trading_flow.py` pass
3. **Manual Verification**:
   - Start the bot with a test FDA news item
   - Verify log shows: `signal_generated ticker=... action=buy confidence=0.92`
   - Verify stop-loss is 5% below entry price
   - Verify take-profit is 12% above entry price
4. **Regression Check**: Existing trading tests still pass

---

## Rollback Plan

If issues occur after deployment:

### Option 1: Quick Revert (Recommended)

Revert the single line change in `process_scored_item()` to use the stub:

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Line:** 296

Change back to:
```python
signal = self._generate_signal_stub(scored_item, ticker, current_price)
```

### Option 2: Disable via Configuration

Add a feature flag check before using SignalGenerator:

```python
# In process_scored_item(), around line 295:
if self.config.use_signal_generator:
    signal = self.signal_generator.generate_signal(
        scored_item=scored_item,
        ticker=ticker,
        current_price=current_price,
    )
else:
    signal = self._generate_signal_stub(scored_item, ticker, current_price)
```

### Option 3: Git Revert

```bash
git revert <commit-hash>
```

---

## Summary of Changes

| File | Line(s) | Change |
|------|---------|--------|
| `trading_engine.py` | 59-60 | Add `from .signal_generator import SignalGenerator` import |
| `trading_engine.py` | 154 | Replace `self.signal_generator = None` with `SignalGenerator()` |
| `trading_engine.py` | 237-239 | Replace TODO with logging confirmation |
| `trading_engine.py` | 295-296 | Replace stub call with `self.signal_generator.generate_signal()` |
| `trading_engine.py` | 701-756 | Add deprecation warning to `_generate_signal_stub()` |

---

**Document Version:** 1.0
**Created:** 2025-12-12
**Priority:** P0 (Critical)
**Target Files:** `src/catalyst_bot/trading/trading_engine.py`
