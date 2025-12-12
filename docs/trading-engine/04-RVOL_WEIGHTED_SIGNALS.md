# Implementation Plan: RVOL-Weighted Signals

## Overview

Integrate Relative Volume (RVOL) into the SignalGenerator's confidence calculation to boost signal quality when volume confirms the catalyst. RVOL measures current volume versus the 20-day average volume - a strong predictor of post-catalyst momentum.

**Key Principle:** High volume confirms institutional interest and increases signal reliability. Low volume suggests weak conviction and should reduce or filter out signals.

---

## Current State Analysis

### Existing RVOL Infrastructure (ALREADY IMPLEMENTED)

The codebase already has a comprehensive RVOL module at `src/catalyst_bot/rvol.py`:

**Key Functions Available:**
```python
calculate_rvol_intraday(ticker: str) -> Optional[Dict[str, Any]]
get_rvol_multiplier(rvol: float) -> float
classify_rvol(rvol: float) -> str
```

**Current RVOL Multiplier Logic:**

| RVOL Range | Category | Multiplier |
|------------|----------|------------|
| >= 5.0x | EXTREME_RVOL | 1.4x (40% boost) |
| 3.0-5.0x | HIGH_RVOL | 1.3x (30% boost) |
| 2.0-3.0x | ELEVATED_RVOL | 1.2x (20% boost) |
| 1.0-2.0x | NORMAL_RVOL | 1.0x (baseline) |
| < 1.0x | LOW_RVOL | 0.8x (20% reduction) |

### Gap: SignalGenerator Does NOT Use RVOL

The `_calculate_confidence()` method only considers:
- `keyword_config.base_confidence`
- Sentiment alignment bonus (+20% if aligned)

**No RVOL integration exists in SignalGenerator.**

---

## Target State

1. **SignalGenerator** applies RVOL multiplier to confidence score
2. **TradingSignal** includes explicit RVOL fields
3. **Low RVOL filter** rejects signals with RVOL < 0.5
4. **Configuration** adds new settings for RVOL integration

---

## Implementation Steps

### Step 1: Add Configuration Settings

**File:** `src/catalyst_bot/config.py`

```python
# RVOL Signal Integration Settings
rvol_confidence_integration: bool = _b("RVOL_CONFIDENCE_INTEGRATION", True)
rvol_min_threshold: float = 0.5  # Filter signals below this RVOL
rvol_max_confidence: float = 0.98  # Cap confidence after RVOL boost
```

### Step 2: Add RVOL Fields to TradingSignal

**File:** `src/catalyst_bot/execution/order_executor.py`

```python
@dataclass
class TradingSignal:
    # ... existing fields ...

    # RVOL fields (NEW)
    rvol: Optional[float] = None
    rvol_class: Optional[str] = None
    rvol_multiplier: Optional[float] = None
    current_volume: Optional[int] = None
    avg_volume_20d: Optional[float] = None
```

### Step 3: Integrate RVOL into SignalGenerator

**File:** `src/catalyst_bot/trading/signal_generator.py`

Add import:
```python
from ..rvol import calculate_rvol_intraday, get_rvol_multiplier
```

Add RVOL lookup method:
```python
def _get_rvol_data(self, ticker: str, scored_item: ScoredItem):
    # Check if RVOL data already on scored_item (from classify.py)
    rvol = getattr(scored_item, "rvol", None)
    if rvol is not None:
        return {...}

    # Fetch fresh RVOL data
    return calculate_rvol_intraday(ticker)
```

Modify `generate_signal()`:
```python
# RVOL lookup and filtering
rvol_data = self._get_rvol_data(ticker, scored_item)
if rvol_data and rvol_data.get("rvol", 1.0) < self.rvol_min_threshold:
    return None  # Filter low volume signals

# Apply RVOL multiplier to confidence
rvol_multiplier = rvol_data.get("multiplier", 1.0)
confidence = confidence * rvol_multiplier
confidence = min(confidence, self.rvol_max_confidence)
```

---

## RVOL Confidence Multiplier Logic

| RVOL Range | Category | Confidence Multiplier | Example |
|------------|----------|----------------------|---------|
| >= 5.0x | EXTREME_RVOL | 1.4x | 0.85 → 0.98 (capped) |
| 3.0-5.0x | HIGH_RVOL | 1.3x | 0.85 → 0.98 (capped) |
| 2.0-3.0x | ELEVATED_RVOL | 1.2x | 0.85 → 0.98 (capped) |
| 1.0-2.0x | NORMAL_RVOL | 1.0x | 0.85 → 0.85 |
| 0.5-1.0x | LOW_RVOL | 0.8x | 0.85 → 0.68 |
| < 0.5x | (filtered) | N/A | Signal rejected |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_RVOL` | `0` | Master RVOL feature flag |
| `RVOL_CONFIDENCE_INTEGRATION` | `1` | Apply RVOL to SignalGenerator |
| `RVOL_MIN_THRESHOLD` | `0.5` | Filter signals below this RVOL |
| `RVOL_MAX_CONFIDENCE` | `0.98` | Maximum confidence after boost |
| `RVOL_BASELINE_DAYS` | `20` | Days for average volume |
| `RVOL_CACHE_TTL_MINUTES` | `5` | Intraday cache TTL |

---

## Testing Plan

### Unit Tests

```python
def test_rvol_boosts_confidence(self, signal_generator, scored_item_with_rvol):
    """Test that high RVOL boosts confidence."""
    signal = signal_generator.generate_signal(
        scored_item_with_rvol,
        ticker="AAPL",
        current_price=Decimal("150.00"),
    )

    assert signal is not None
    assert signal.rvol == 3.5
    assert signal.rvol_class == "HIGH_RVOL"
    assert signal.confidence > signal.metadata["pre_rvol_confidence"]

def test_rvol_below_threshold_filtered(self, signal_generator):
    """Test that RVOL below threshold filters out signal."""
    item = ScoredItem(...)
    item.rvol = 0.3  # Below 0.5 threshold

    signal = signal_generator.generate_signal(item, ticker="AAPL", ...)
    assert signal is None  # Filtered out
```

### Validation Criteria

1. **RVOL Boost Applied:** Signals with RVOL >= 2.0 have higher confidence
2. **RVOL Reduction Applied:** Signals with RVOL < 1.0 have lower confidence
3. **Filtering Works:** Signals with RVOL < 0.5 rejected
4. **Max Confidence Respected:** No confidence exceeds 0.98
5. **RVOL Fields Populated:** TradingSignal includes all RVOL fields

---

## Rollback Plan

### Immediate Disable

```bash
RVOL_CONFIDENCE_INTEGRATION=0
```

### Full Rollback

1. Revert `signal_generator.py` changes
2. Revert `order_executor.py` TradingSignal changes
3. Remove config settings

---

## Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/catalyst_bot/config.py` | ADD | 3 new RVOL settings |
| `src/catalyst_bot/execution/order_executor.py` | MODIFY | Add 5 RVOL fields |
| `src/catalyst_bot/trading/signal_generator.py` | MODIFY | RVOL integration |

---

**Document Version:** 1.0
**Created:** 2025-12-12
**Priority:** P1 (High)
