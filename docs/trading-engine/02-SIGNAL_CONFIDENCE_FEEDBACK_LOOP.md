# Implementation Plan: Signal Confidence Feedback Loop

## Overview

This document provides a complete implementation plan for adding a Signal Confidence Feedback Loop to the Catalyst Bot trading engine. The system will:

1. Track which catalyst keywords led to profitable vs unprofitable trades
2. Calculate rolling performance metrics per keyword (win rate, avg return, Sharpe-like score)
3. Automatically adjust keyword confidence multipliers based on actual trade outcomes
4. Store historical performance data for analysis and reporting

The feedback loop connects closed positions (with realized P&L) back to the signal generator's keyword weights, creating a self-improving system.

---

## Current State Analysis

### Fixed Keyword Weights (No Learning)

**File:** `src/catalyst_bot/trading/signal_generator.py`

The current system uses hardcoded `KeywordConfig` objects:

```python
BUY_KEYWORDS: Dict[str, KeywordConfig] = {
    "fda": KeywordConfig(
        action="buy",
        base_confidence=0.92,       # FIXED - never changes
        size_multiplier=1.6,
        stop_loss_pct=5.0,
        take_profit_pct=12.0,
        rationale="FDA approval = strong catalyst",
    ),
    "merger": KeywordConfig(
        action="buy",
        base_confidence=0.95,       # FIXED - never changes
        ...
    ),
}
```

### Gap: No Connection Between Trade Outcomes and Keyword Weights

The existing system has no feedback mechanism to improve signal quality based on actual trading results.

---

## Target State

### Dynamic Weights That Improve Over Time

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Trading Engine │────▶│ Position Manager │────▶│ Feedback        │
│  (executes)     │     │ (closes position)│     │ Tracker         │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                        ┌──────────────────┐              │
                        │ Signal Generator │◀─────────────┘
                        │ (uses adjusted   │   (updates confidence
                        │  confidences)    │    multipliers)
                        └──────────────────┘
```

---

## Dependencies & Libraries

**Standard library only - no new dependencies needed:**

```python
import sqlite3      # Already used in position_manager.py
import json         # Already used in position_manager.py
import statistics   # Standard library for mean, stdev calculations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
```

---

## Data Model

### New Table: `keyword_trade_outcomes`

```sql
CREATE TABLE IF NOT EXISTS keyword_trade_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    closed_at TIMESTAMP NOT NULL,
    keyword TEXT NOT NULL,
    keyword_weight REAL NOT NULL,
    ticker TEXT NOT NULL,
    realized_pnl REAL NOT NULL,
    realized_pnl_pct REAL NOT NULL,
    hold_duration_seconds INTEGER NOT NULL,
    exit_reason TEXT,
    entry_confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(position_id, keyword)
);
```

### New Table: `keyword_performance_stats`

```sql
CREATE TABLE IF NOT EXISTS keyword_performance_stats (
    keyword TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0.0,
    avg_pnl_pct REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    pnl_stddev REAL DEFAULT 0.0,
    sharpe_score REAL DEFAULT 0.0,
    base_confidence REAL NOT NULL,
    confidence_multiplier REAL DEFAULT 1.0,
    adjusted_confidence REAL NOT NULL,
    last_updated TIMESTAMP,
    last_trade_at TIMESTAMP,
    min_multiplier REAL DEFAULT 0.5,
    max_multiplier REAL DEFAULT 1.5
);
```

---

## Implementation Steps

### Step 1: Create Feedback Tracker Module

**File:** `src/catalyst_bot/trading/feedback_tracker.py` (NEW)

This module will contain:
- `FeedbackConfig` dataclass for configuration
- `KeywordOutcome` dataclass for outcome records
- `KeywordStats` dataclass for statistics
- `FeedbackTracker` class with:
  - `record_outcome()` - Called on position close
  - `get_confidence_multiplier()` - Called during signal generation
  - `apply_decay()` - Time-based decay toward neutral

### Step 2: Integrate with Position Manager

**File:** `src/catalyst_bot/portfolio/position_manager.py`
**Location:** Inside `close_position()` method

Add after `self._save_closed_position_to_db(closed)`:

```python
# Record outcome in feedback tracker
try:
    feedback_tracker = get_feedback_tracker()
    feedback_tracker.record_from_closed_position(closed)
except Exception as e:
    self.logger.debug("feedback_record_failed position_id=%s", closed.position_id)
```

### Step 3: Integrate with Signal Generator

**File:** `src/catalyst_bot/trading/signal_generator.py`

Add to `_calculate_confidence()` method:

```python
# Apply feedback multiplier if available
if self.feedback_tracker:
    multiplier = self.feedback_tracker.get_confidence_multiplier(primary_keyword)
    adjusted = base * multiplier
    return max(0.0, min(1.0, adjusted))
```

### Step 4: Add Decay to Trading Engine

**File:** `src/catalyst_bot/trading/trading_engine.py`

Add periodic decay call in `update_positions()`:

```python
# Apply feedback decay (runs daily check)
await self._apply_feedback_decay()
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEEDBACK_LOOP_ENABLED` | `true` | Enable/disable the feedback loop |
| `FEEDBACK_LEARNING_RATE` | `0.1` | How fast multipliers adjust (0.0-1.0) |
| `FEEDBACK_DECAY_RATE` | `0.01` | Daily decay toward neutral (0.0-0.1) |
| `FEEDBACK_MIN_TRADES` | `5` | Minimum trades before adjustment |
| `FEEDBACK_WINDOW_DAYS` | `30` | Rolling window for statistics |
| `FEEDBACK_MIN_MULTIPLIER` | `0.5` | Minimum confidence multiplier |
| `FEEDBACK_MAX_MULTIPLIER` | `1.5` | Maximum confidence multiplier |

---

## Multiplier Calculation Logic

### Formula

```python
def _calculate_multiplier(
    self,
    win_rate: float,
    avg_pnl_pct: float,
    sharpe_score: float,
    total_trades: int,
) -> float:
    # Start at neutral
    multiplier = 1.0

    # Skip if insufficient sample
    if total_trades < self.config.min_trades_for_adjustment:
        return multiplier

    # Sample size confidence
    sample_confidence = min(1.0, total_trades / 20.0)

    # Win rate component
    win_rate_adjustment = (win_rate - 0.5) * 0.5 * sample_confidence

    # P&L component
    pnl_adjustment = avg_pnl_pct * 2.0 * sample_confidence

    # Apply with learning rate
    total_adjustment = (win_rate_adjustment + pnl_adjustment) * learning_rate

    return multiplier + total_adjustment
```

---

## Testing Plan

### Unit Tests

```python
def test_multiplier_increases_for_winners(self, tracker):
    """Test that multiplier increases for winning keywords."""
    for i in range(5):
        tracker.record_outcome(
            position_id=f"win-{i}",
            ticker="AAPL",
            keywords={"fda": 0.92},
            realized_pnl=100.0,
            realized_pnl_pct=0.05,
            hold_duration_seconds=3600,
            exit_reason="take_profit",
            entry_confidence=0.85,
        )

    multiplier = tracker.get_confidence_multiplier("fda")
    assert multiplier > 1.0

def test_multiplier_decreases_for_losers(self, tracker):
    """Test that multiplier decreases for losing keywords."""
    for i in range(5):
        tracker.record_outcome(
            position_id=f"loss-{i}",
            ticker="AAPL",
            keywords={"merger": 0.95},
            realized_pnl=-100.0,
            realized_pnl_pct=-0.05,
            hold_duration_seconds=3600,
            exit_reason="stop_loss",
            entry_confidence=0.85,
        )

    multiplier = tracker.get_confidence_multiplier("merger")
    assert multiplier < 1.0
```

### Validation Criteria

1. **Correctness**: Multipliers bounded between min/max
2. **Performance**: Database queries < 10ms average
3. **Stability**: Decay prevents runaway adjustments
4. **Accuracy**: Win rate calculations match manual verification

---

## Rollback Plan

### Disable Feedback Loop

```bash
FEEDBACK_LOOP_ENABLED=false
```

### Database Cleanup

```sql
UPDATE keyword_performance_stats
SET confidence_multiplier = 1.0,
    adjusted_confidence = base_confidence;
```

---

## Summary

| File | Action | Lines |
|------|--------|-------|
| `src/catalyst_bot/trading/feedback_tracker.py` | NEW | ~500 |
| `src/catalyst_bot/trading/signal_generator.py` | MODIFY | ~50 |
| `src/catalyst_bot/portfolio/position_manager.py` | MODIFY | ~30 |
| `src/catalyst_bot/trading/trading_engine.py` | MODIFY | ~20 |
| `src/catalyst_bot/config.py` | MODIFY | ~30 |

---

**Document Version:** 1.0
**Created:** 2025-12-12
**Priority:** P0 (Critical)
