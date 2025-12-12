# Implementation Plan: False Positive Penalties

## Overview

This implementation plan adds **automatic penalty application** to the trading engine, reducing confidence scores for signals containing historically poor-performing keywords, sources, and sectors. The system tracks catalysts that were accepted but didn't move price as expected, then automatically penalizes similar future signals.

**Core Concept:** When a position closes with poor outcomes (actual return < expected * 0.2), the keywords and sources associated with that signal accumulate "false positive points." Once a pattern's false positive rate exceeds a threshold with sufficient sample size, a penalty multiplier is applied to future signals.

---

## Current State Analysis

### Existing Infrastructure

| Component | File | Status |
|-----------|------|--------|
| Outcome Tracking | `false_positive_tracker.py` | Exists |
| Pattern Analysis | `false_positive_analyzer.py` | Exists |
| Signal Generator | `signal_generator.py` | No penalty integration |

### Critical Gap

The existing analysis generates recommendations but **penalties are never applied** to signal generation.

---

## Target State

### Automatic Penalty System Flow

```
Position Closes → Record Outcome → Update Stats → Apply Penalty to Future Signals
```

---

## Data Model

### False Positive Definition

```python
is_false_positive = actual_return_pct < (expected_return_pct * 0.2)
```

**Example:**
- Expected return: 10%
- Threshold: 10% * 0.2 = 2%
- If actual return < 2%, it's a false positive

### Penalty Multiplier Tiers

| False Positive Rate | Multiplier | Effective Confidence |
|---------------------|-----------|---------------------|
| < 30% | 1.0x | 100% of base |
| 30-50% | 0.8x | 80% of base |
| 50-70% | 0.6x | 60% of base |
| > 70% | 0.4x | 40% of base |

**Minimum Multiplier:** 0.5x

---

## Implementation Steps

### Step 1: Create Penalty Manager

**File:** `src/catalyst_bot/trading/false_positive_penalties.py` (NEW)

```python
@dataclass
class FalsePositiveRecord:
    signal_id: str
    ticker: str
    keywords: List[str]
    source: str
    sector: Optional[str]
    entry_price: Decimal
    exit_price: Decimal
    expected_return_pct: float
    actual_return_pct: float
    is_false_positive: bool
    timestamp: datetime

class FalsePositivePenaltyManager:
    def record_outcome(self, ...): ...
    def get_penalty_multiplier(self, keywords, source, sector): ...
    def _calculate_multiplier(self, fp_rate, sample_size): ...
```

### Step 2: Hook into Position Close

**File:** `src/catalyst_bot/portfolio/position_manager.py`

Add after `self._save_closed_position_to_db(closed)`:

```python
try:
    penalty_manager = get_penalty_manager()
    penalty_manager.record_outcome(
        signal_id=position.signal_id,
        ticker=closed.ticker,
        keywords=position.metadata.get("keywords", []),
        source=position.metadata.get("source"),
        sector=position.metadata.get("sector"),
        entry_price=closed.entry_price,
        exit_price=closed.exit_price,
        expected_return_pct=position.metadata.get("take_profit_pct", 10.0),
    )
except Exception as e:
    self.logger.debug("penalty_record_failed")
```

### Step 3: Apply Penalties in SignalGenerator

**File:** `src/catalyst_bot/trading/signal_generator.py`

Add to `_calculate_confidence()`:

```python
# Get penalty multiplier
penalty_manager = get_penalty_manager()
penalty_multiplier = penalty_manager.get_penalty_multiplier(
    keywords=keyword_list,
    source=source,
    sector=sector,
)

# Apply penalty
if penalty_multiplier < 1.0:
    confidence = confidence * penalty_multiplier
```

---

## Time Decay for Improvement

When FP rate improves by 10%+ over 7 days, reduce penalty by 20%:

```python
if improvement >= 0.10:
    decayed = multiplier + (1.0 - multiplier) * 0.20
```

---

## Configuration

### Constants

```python
FP_THRESHOLD = 0.2          # 20% of expected return
ROLLING_WINDOW_DAYS = 30    # Rolling window
MIN_SAMPLE_SIZE = 5         # Minimum occurrences
MIN_MULTIPLIER = 0.5        # Floor for penalty

PENALTY_TIERS = [
    (0.70, 0.4),  # >70% FP rate → 0.4x
    (0.50, 0.6),  # >50% FP rate → 0.6x
    (0.30, 0.8),  # >30% FP rate → 0.8x
]
```

---

## Testing Plan

### Unit Tests

```python
def test_false_positive_classification(self):
    """Test FP classification logic."""
    expected = 10.0
    actual = 1.0
    is_fp = actual < (expected * 0.2)  # 1% < 2%
    assert is_fp is True

def test_penalty_applied_at_min_samples(self, manager):
    """Test penalty IS applied at minimum sample size."""
    for i in range(5):
        manager.record_outcome(
            signal_id=f"test_{i}",
            keywords=["bad_keyword"],
            realized_pnl=-100.0,
            ...
        )

    multiplier = manager.get_penalty_multiplier(keywords=["bad_keyword"])
    assert multiplier < 1.0

def test_multiple_keywords_worst_penalty(self, manager):
    """Test multiple keywords use worst penalty."""
    # good_keyword: no penalties
    # bad_keyword: 100% FP rate

    multiplier = manager.get_penalty_multiplier(
        keywords=["good_keyword", "bad_keyword"]
    )
    assert multiplier < 1.0  # Uses bad_keyword's penalty
```

### Validation Criteria

1. **Penalty Application:** Reduces confidence correctly
2. **Minimum multiplier enforced:** Never below 0.5x
3. **Sample size respected:** No penalty with < 5 samples
4. **Time decay works:** Improving patterns reduce penalty

---

## Rollback Plan

### Immediate Disable

```bash
DISABLE_FP_PENALTIES=1
```

### Database Reset

```bash
rm data/false_positive_penalties.db
```

---

## Summary

| File | Action | Lines |
|------|--------|-------|
| `src/catalyst_bot/trading/false_positive_penalties.py` | NEW | ~500 |
| `src/catalyst_bot/portfolio/position_manager.py` | MODIFY | ~30 |
| `src/catalyst_bot/trading/signal_generator.py` | MODIFY | ~40 |

---

**Document Version:** 1.0
**Created:** 2025-12-12
**Priority:** P2 (Medium)
