# Feedback Loop to SignalGenerator Integration - Implementation Plan

**Date:** 2025-12-18
**Status:** PLANNING COMPLETE
**Priority:** High

---

## Executive Summary

**Goal:** Enable adaptive learning from trade outcomes by integrating the feedback loop system with SignalGenerator, allowing keyword performance multipliers to dynamically adjust confidence scores.

**What We're Building:**
- A bridge between the existing feedback system (`src/catalyst_bot/feedback/`) and SignalGenerator (`src/catalyst_bot/trading/signal_generator.py`)
- Dynamic keyword performance multipliers that adjust confidence scores based on historical performance
- A feature-flagged, gradual rollout with full rollback capability

**Why This Matters:**
- FDA keywords might consistently outperform expectations (boost confidence)
- Partnership keywords might underperform (reduce confidence)
- System learns from actual trade outcomes, not just theoretical models

**Current State:**
- Feedback system tracks alert performance with `win/loss/neutral` outcomes
- `weight_adjuster.py` already calculates keyword-specific multipliers
- SignalGenerator uses static keyword configurations (base confidence, stop %, take profit %)
- **Gap:** These two systems are not connected

---

## Current State Analysis

### Feedback System (`src/catalyst_bot/feedback/`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `database.py` | SQLite persistence for alert_performance | `log_alert()`, `log_trade_outcome()`, `_get_connection()` |
| `outcome_scorer.py` | Scores outcomes (1d, 5d, 10d price changes) | `calculate_outcome_score()` |
| `price_tracker.py` | Tracks prices post-alert | `check_price_outcomes()` |
| `weight_adjuster.py` | **Key file** - Calculates keyword multipliers | `analyze_keyword_performance()`, `get_keyword_multipliers()` |
| `weekly_report.py` | Weekly performance summaries | `generate_weekly_report()` |

**Database Schema (alert_performance table):**
```sql
- ticker, posted_at, catalyst_type (keyword)
- price_at_alert, price_1d, price_5d, price_10d
- price_change_1d, price_change_5d, price_change_10d
- outcome ('win', 'loss', 'neutral'), outcome_score
- keywords (JSON)
```

**WeightAdjuster Multiplier Calculation:**
- Looks at last N days of performance per keyword
- Calculates win rate and average return
- Applies smoothing (blend with baseline)
- Returns multiplier in range [0.5, 1.5]

### SignalGenerator (`src/catalyst_bot/trading/signal_generator.py`)

**Current Keyword Configuration:**
```python
BUY_KEYWORDS = {
    "fda": KeywordConfig(base_confidence=0.92, stop_loss_pct=5.0, take_profit_pct=12.0, ...),
    "merger": KeywordConfig(base_confidence=0.95, stop_loss_pct=4.0, take_profit_pct=15.0, ...),
    "partnership": KeywordConfig(base_confidence=0.85, ...),
    # etc.
}
```

**Confidence Calculation Flow:**
1. Match keyword from scored_item
2. Get base_confidence from keyword config
3. Apply sentiment alignment bonus (if sentiment > 0.5, +20%)
4. Clamp to [0, 1.0]
5. **Missing:** Performance multiplier adjustment

---

## Architecture Design

### Data Flow Diagram

```
Feedback Database                SignalGenerator
     |                                 |
     v                                 |
+-----------+                          |
| alert_    |                          |
| perf. DB  |----+                     |
+-----------+    |                     |
                 v                     v
        +------------------+    +----------------+
        | WeightAdjuster   |    | Keyword        |
        | get_keyword_     |--->| Performance    |
        | multipliers()    |    | Provider       |
        +------------------+    +----------------+
                                       |
                                       v
                               +----------------+
                               | generate_      |
                               | signal()       |
                               +----------------+
                                       |
                                       v
                               +----------------+
                               | Adjusted       |
                               | confidence,    |
                               | position_size  |
                               +----------------+
```

### New Component: KeywordPerformanceProvider

**Location:** `src/catalyst_bot/trading/keyword_performance.py` (new file)

**Responsibilities:**
1. Fetch multipliers from feedback system
2. Cache multipliers (TTL-based, avoid DB hits per signal)
3. Provide fallback multipliers when feedback unavailable
4. Log when multipliers deviate significantly from baseline

**Interface:**
```python
class KeywordPerformanceProvider:
    def __init__(self, cache_ttl_minutes: int = 60):
        ...

    def get_multiplier(self, keyword: str) -> float:
        """Get performance multiplier for keyword (1.0 = baseline)"""
        ...

    def refresh_cache(self) -> None:
        """Force refresh of multiplier cache"""
        ...

    def get_all_multipliers(self) -> Dict[str, float]:
        """Get all keyword multipliers for debugging"""
        ...
```

---

## Implementation Steps

### Phase 1: Foundation (Day 1-2)

| Step | File | Change |
|------|------|--------|
| 1.1 | `src/catalyst_bot/config.py` | Add feedback integration settings |
| 1.2 | `src/catalyst_bot/trading/keyword_performance.py` | Create KeywordPerformanceProvider class |
| 1.3 | `src/catalyst_bot/feedback/weight_adjuster.py` | Add `get_keyword_multipliers()` function if not exists |
| 1.4 | `tests/test_keyword_performance.py` | Unit tests for provider |

### Phase 2: SignalGenerator Integration (Day 2-3)

| Step | File | Change |
|------|------|--------|
| 2.1 | `src/catalyst_bot/trading/signal_generator.py` | Import KeywordPerformanceProvider |
| 2.2 | `src/catalyst_bot/trading/signal_generator.py` | Initialize provider in `__init__` |
| 2.3 | `src/catalyst_bot/trading/signal_generator.py` | Modify `generate_signal()` to apply multiplier |
| 2.4 | `tests/test_signal_generator.py` | Add integration tests |

### Phase 3: Position Sizing Enhancement (Day 3-4)

| Step | File | Change |
|------|------|--------|
| 3.1 | `src/catalyst_bot/trading/signal_generator.py` | Apply multiplier to position sizing |
| 3.2 | `src/catalyst_bot/trading/signal_generator.py` | Add metadata about adjustment |
| 3.3 | `tests/test_signal_generator.py` | Test position sizing adjustments |

### Phase 4: Feedback Loop Completion (Day 4-5)

| Step | File | Change |
|------|------|--------|
| 4.1 | `src/catalyst_bot/trading/trading_engine.py` | Log trade outcomes to feedback DB |
| 4.2 | `src/catalyst_bot/feedback/database.py` | Add trade signal reference |
| 4.3 | `src/catalyst_bot/portfolio/position_manager.py` | Capture keyword in closed position |

### Phase 5: Observability & Testing (Day 5-6)

| Step | File | Change |
|------|------|--------|
| 5.1 | `src/catalyst_bot/trading/signal_generator.py` | Add metrics/logging |
| 5.2 | `src/catalyst_bot/health_endpoint.py` | Expose multiplier stats |
| 5.3 | `tests/integration/test_feedback_signal_integration.py` | End-to-end tests |

---

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_FEEDBACK_SIGNAL_INTEGRATION` | `0` | Enable/disable feature |
| `FEEDBACK_MULTIPLIER_MIN` | `0.7` | Minimum multiplier bound |
| `FEEDBACK_MULTIPLIER_MAX` | `1.3` | Maximum multiplier bound |
| `FEEDBACK_CACHE_TTL_MINUTES` | `60` | Cache refresh interval |
| `FEEDBACK_MIN_SAMPLE_SIZE` | `10` | Minimum trades before adjusting |
| `FEEDBACK_SMOOTHING_FACTOR` | `0.3` | Blend factor (0=baseline, 1=raw) |

---

## Testing Strategy

### Unit Tests

**`tests/test_keyword_performance.py`:**
- `test_returns_baseline_when_disabled` - Returns 1.0 when feature disabled
- `test_applies_multiplier_bounds` - Multiplier clamped to [0.7, 1.3]
- `test_requires_minimum_samples` - Returns 1.0 if sample_size < min
- `test_applies_smoothing` - Blends with baseline per smoothing factor
- `test_cache_ttl_respected` - Cache refreshes after TTL expiry
- `test_thread_safety` - Concurrent access doesn't corrupt cache

### Integration Tests

- End-to-end adjustment flow: DB -> WeightAdjuster -> Provider -> SignalGenerator
- Weak keyword confidence reduced
- Strong keyword confidence boosted

### Manual Testing Checklist

- [ ] Run with `FEATURE_FEEDBACK_SIGNAL_INTEGRATION=0` - signals unchanged
- [ ] Run with `FEATURE_FEEDBACK_SIGNAL_INTEGRATION=1` - multipliers applied
- [ ] Verify multipliers visible at `/health/feedback-multipliers`
- [ ] Simulate poor-performing keyword - confirm reduced confidence
- [ ] Verify cache refresh happens after TTL
- [ ] Check logs for `performance_multiplier` entries

---

## Rollback Plan

### Immediate Disable (< 1 minute)

Set environment variable:
```bash
FEATURE_FEEDBACK_SIGNAL_INTEGRATION=0
```

Restart the bot. All signals revert to static keyword configurations.

### Monitoring Alerts

Set up alerts for:
- Confidence values falling below 0.6 (min_confidence)
- Position sizes consistently hitting max_position_pct
- Win rate dropping more than 10% week-over-week

---

## Future Enhancements

### Path to True ML (Phase 2)

| Enhancement | Description | Complexity |
|-------------|-------------|------------|
| **Time-weighted decay** | Recent trades matter more | Medium |
| **Sector context** | Adjust multipliers by market sector | Medium |
| **Market regime** | Different multipliers in bull/bear markets | High |
| **Multi-keyword combinations** | "FDA + partnership" different from each alone | High |
| **Online learning** | Real-time model updates (scikit-learn) | Very High |
| **RL-based sizing** | Reinforcement learning for position sizing | Expert |

### Recommended Next Steps After This Integration

1. **Add time decay** - Exponential decay so recent trades matter more
2. **Sector-specific multipliers** - Biotech FDA != Industrial FDA
3. **Weekly auto-reports** - Discord summary of multiplier changes
4. **Confidence intervals** - Add uncertainty bounds to multipliers

---

## Critical Files for Implementation

| File | Purpose |
|------|---------|
| `src/catalyst_bot/trading/signal_generator.py` | Core file - modify generate_signal() |
| `src/catalyst_bot/feedback/weight_adjuster.py` | Source of multiplier calculations |
| `src/catalyst_bot/config.py` | Add new settings |
| `src/catalyst_bot/feedback/database.py` | Schema reference |
| `tests/test_signal_generator.py` | Test patterns |

---

*Generated: 2025-12-18*
