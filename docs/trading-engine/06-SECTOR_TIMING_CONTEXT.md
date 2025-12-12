# Implementation Plan: Sector/Timing Context

## Overview

This document provides a detailed implementation plan to add sector-aware and timing-aware signal adjustments to the trading engine. The core insight: **biotech FDA approvals work differently than tech partnerships** - sector-specific and time-of-day adjustments will improve signal quality and reduce false positives.

**Key Goals:**
- Apply sector-specific keyword multipliers (FDA matters more for biotech than for retail)
- Track sector momentum (is biotech hot or cold today?)
- Incorporate time-of-day patterns (pre-market news behaves differently than midday news)
- Apply day-of-week adjustments (Monday gaps, Friday profit-taking)

---

## Current State Analysis

### Existing Sector Infrastructure (Not Integrated)

| Module | File | Status |
|--------|------|--------|
| SectorContextManager | `sector_context.py` | Exists, NOT used in signals |
| get_session() | `sector_info.py` | Exists, NOT integrated |
| MarketStatus | `market_hours.py` | Exists, NOT used in signals |

### Gap

SignalGenerator uses **fixed keyword multipliers** regardless of sector or timing.

---

## Target State

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SignalGenerator                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ SectorContext   │  │ TimingContext   │  │ KeywordConfig   │      │
│  │ Provider        │  │ Provider        │  │ (existing)      │      │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘      │
│           │                    │                    │               │
│           ▼                    ▼                    ▼               │
│  final_confidence = base * sector_mult * timing_mult                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Sector-Keyword Multiplier Matrix

| Sector | FDA | Trial | Merger | Partnership | Uplisting |
|--------|-----|-------|--------|-------------|-----------|
| Health Care | **1.4** | **1.3** | 1.1 | 1.0 | 0.9 |
| Technology | 0.5 | 0.4 | 1.2 | **1.3** | 1.1 |
| Financials | 0.3 | 0.3 | **1.4** | 1.0 | 0.8 |
| Energy | 0.2 | 0.2 | 1.3 | 1.2 | 0.9 |
| Consumer Discretionary | 0.4 | 0.3 | 1.2 | 1.2 | 1.0 |
| Communication Services | 0.3 | 0.3 | 1.3 | **1.4** | 1.0 |

**Key Insights:**
- FDA/Clinical keywords boosted 40% for Healthcare
- Partnership keywords boosted 30% for Tech
- M&A keywords boosted 40% for Financials

---

## Timing Patterns

### Time-of-Day Multipliers

| Session | Time (ET) | Confidence | Size | Stop Buffer |
|---------|-----------|------------|------|-------------|
| Pre-market Early | 4:00-6:00 AM | **1.15** | 0.7 | +1.0% |
| Pre-market Late | 6:00-9:30 AM | **1.20** | 0.8 | +0.5% |
| First Hour | 9:30-10:30 AM | **1.15** | 1.0 | +0.5% |
| Morning | 10:30 AM-12:00 PM | 1.05 | 1.0 | 0% |
| Midday | 12:00-2:00 PM | **0.90** | 0.9 | 0% |
| Afternoon | 2:00-3:00 PM | 1.00 | 1.0 | 0% |
| Power Hour | 3:00-4:00 PM | 1.10 | 1.0 | +0.3% |
| After-hours Early | 4:00-6:00 PM | 1.05 | 0.6 | +1.5% |
| After-hours Late | 6:00-8:00 PM | **0.85** | 0.4 | +2.0% |

### Day-of-Week Multipliers

| Day | Multiplier | Rationale |
|-----|------------|-----------|
| Monday | **0.90** | Gap risk from weekend news |
| Tuesday | 1.00 | Normal |
| Wednesday | **1.05** | Typically highest volume |
| Thursday | 1.00 | Normal |
| Friday | **0.85** | Profit-taking, weekend risk |

### Optimal Windows
- **Best:** Tuesday-Thursday, 6:00-10:30 AM ET
- **Good:** Tuesday-Thursday, morning session
- **Avoid:** Friday afternoons, Monday mornings

---

## Implementation Steps

### Step 1: Create Sector-Keyword Multiplier Provider

**File:** `src/catalyst_bot/trading/sector_keyword_multiplier.py` (NEW)

```python
SECTOR_KEYWORD_MATRIX: Dict[str, Dict[str, float]] = {
    "Health Care": {
        "fda": 1.4,
        "trial": 1.3,
        "merger": 1.1,
        "partnership": 1.0,
    },
    "Technology": {
        "fda": 0.5,
        "merger": 1.2,
        "partnership": 1.3,
    },
    # ... more sectors
}

class SectorKeywordMultiplierProvider:
    def get_multiplier(self, ticker: str, keyword: str) -> SectorKeywordContext:
        sector, _ = get_ticker_sector(ticker)
        base_mult = SECTOR_KEYWORD_MATRIX.get(sector, {}).get(keyword, 1.0)

        # Get sector momentum
        sector_perf = manager.get_sector_performance(sector)
        momentum_mult = self._calculate_momentum_multiplier(sector_perf)

        return SectorKeywordContext(
            sector=sector,
            base_multiplier=base_mult,
            sector_momentum_multiplier=momentum_mult,
            combined_multiplier=base_mult * momentum_mult,
        )
```

### Step 2: Create Timing Context Provider

**File:** `src/catalyst_bot/trading/timing_context.py` (NEW)

```python
class TimingContextProvider:
    def get_timing_context(self, dt: datetime = None) -> TimingContext:
        session_type = self.get_session_type(dt_et)
        session_config = SESSION_MULTIPLIERS[session_type]
        day_multiplier = DAY_OF_WEEK_MULTIPLIERS[dt_et.weekday()]

        combined = session_config.confidence_multiplier * day_multiplier

        return TimingContext(
            session_type=session_type,
            day_of_week=dt_et.weekday(),
            combined_confidence_multiplier=combined,
            is_optimal_window=self._is_optimal(session_type, dt_et.weekday()),
        )
```

### Step 3: Integrate into SignalGenerator

**File:** `src/catalyst_bot/trading/signal_generator.py`

Modify `_calculate_confidence()`:

```python
# Sector-Keyword Multiplier
sector_multiplier = 1.0
if self.sector_keyword_provider and ticker and keyword_hits:
    best_keyword, sector_context = (
        self.sector_keyword_provider.get_best_keyword_multiplier(ticker, keywords)
    )
    sector_multiplier = sector_context.combined_multiplier

# Timing Multiplier
timing_multiplier = 1.0
if self.timing_provider:
    timing_context = self.timing_provider.get_timing_context()
    timing_multiplier = timing_context.combined_confidence_multiplier

# Combine
final_confidence = confidence * sector_multiplier * timing_multiplier
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_SECTOR_SIGNAL_ADJUSTMENT` | `1` | Enable sector multipliers |
| `FEATURE_TIMING_SIGNAL_ADJUSTMENT` | `1` | Enable timing multipliers |
| `SECTOR_HOT_THRESHOLD_PCT` | `2.0` | Sector +2% = "hot" |
| `SECTOR_COLD_THRESHOLD_PCT` | `-2.0` | Sector -2% = "cold" |
| `MAX_SECTOR_MULTIPLIER` | `1.5` | Cap sector adjustment |
| `MAX_TIMING_MULTIPLIER` | `1.3` | Cap timing adjustment |

---

## Combined Effect Examples

| Scenario | Sector Mult | Timing Mult | Combined |
|----------|------------|-------------|----------|
| Biotech + FDA + Tuesday 8am | 1.4 | 1.2 | **1.68x** |
| Tech + FDA + Friday 1pm | 0.5 | 0.77 | **0.38x** |
| Finance + Merger + Wed 10am | 1.4 | 1.05 | **1.47x** |

---

## Testing Plan

### Unit Tests

```python
def test_healthcare_fda_boosted(self):
    """FDA should be boosted for healthcare."""
    assert SECTOR_KEYWORD_MATRIX["Health Care"]["fda"] == 1.4

def test_tech_fda_reduced(self):
    """FDA should be reduced for technology."""
    assert SECTOR_KEYWORD_MATRIX["Technology"]["fda"] == 0.5

def test_tuesday_morning_optimal(self):
    """Tuesday morning should be optimal."""
    provider = TimingContextProvider()
    dt = datetime(2025, 12, 16, 13, 0, tzinfo=timezone.utc)  # 8 AM ET Tuesday
    assert provider.is_optimal_trading_window(dt) is True

def test_friday_afternoon_not_optimal(self):
    """Friday afternoon should not be optimal."""
    provider = TimingContextProvider()
    dt = datetime(2025, 12, 19, 20, 0, tzinfo=timezone.utc)  # 3 PM ET Friday
    assert provider.is_optimal_trading_window(dt) is False
```

### Validation Criteria

1. **Sector Multipliers Applied:** Healthcare + FDA = 1.4x
2. **Timing Multipliers Applied:** Pre-market = 1.2x, Midday = 0.9x
3. **Day-of-Week Applied:** Friday = 0.85x
4. **Feature Flags Work:** Disabling returns 1.0 multipliers

---

## Rollback Plan

### Feature Flag Disable

```bash
FEATURE_SECTOR_SIGNAL_ADJUSTMENT=0
FEATURE_TIMING_SIGNAL_ADJUSTMENT=0
```

When disabled, multipliers return 1.0 (no effect).

---

## Summary

| File | Action | Lines |
|------|--------|-------|
| `src/catalyst_bot/trading/sector_keyword_multiplier.py` | NEW | ~400 |
| `src/catalyst_bot/trading/timing_context.py` | NEW | ~350 |
| `src/catalyst_bot/trading/signal_generator.py` | MODIFY | ~100 |
| `src/catalyst_bot/config.py` | MODIFY | ~40 |

---

**Document Version:** 1.0
**Created:** 2025-12-12
**Priority:** P2 (Medium)
