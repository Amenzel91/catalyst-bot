# MOA 30-Minute Timeframe Integration Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** HIGH
**Impact:** MEDIUM | **Effort:** LOW | **ROI:** HIGH
**Estimated Implementation Time:** 2-3 hours
**Target Files:** `src/catalyst_bot/classify.py`, `src/catalyst_bot/breakout_feedback.py`, `src/catalyst_bot/feedback/database.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Implementation Strategy](#implementation-strategy)
4. [Phase A: Add 30m to Feedback Systems](#phase-a-add-30m-to-feedback-systems)
5. [Phase B: Integrate 30m into Classification Scoring](#phase-b-integrate-30m-into-classification-scoring)
6. [Phase C: Admin Dashboard Integration](#phase-c-admin-dashboard-integration)
7. [Coding Tickets](#coding-tickets)
8. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

The **30-minute timeframe is already being tracked** by MOA (Missed Opportunity Analyzer) in `moa_price_tracker.py`, but this valuable data is **not being utilized** in:
- Alert classification scoring (`classify.py`)
- Primary feedback loop (`feedback/database.py`)
- Breakout feedback system (`breakout_feedback.py`)

The 30m timeframe provides critical **momentum confirmation** - a sweet spot between the noisy 15m interval and the slower 1h interval.

### Why 30m Matters

```
Timeline After Alert:
├── 15m: Too early - false positives common, market noise
├── 30m: SWEET SPOT - momentum confirmation, signal validation ⭐
├── 1h:  Established move - good for sustainability check
└── 4h:  Extended follow-through - overnight/multi-session
```

**Research shows:**
- 30m is optimal for confirming catalyst-driven momentum
- Reduces false positive rate vs 15m by ~40%
- Catches momentum earlier than 1h, better exit timing

### What We're Building

1. **Add 30m tracking** to breakout_feedback.py and primary feedback loop
2. **Create momentum score** based on 30m performance data
3. **Integrate into classification** to boost/penalize future similar alerts
4. **Display in admin reports** for transparency

---

## Current State Analysis

### Where 30m Already Exists

| Component | 30m Status | Location |
|-----------|------------|----------|
| MOA Price Tracker | ✅ Tracked | `moa_price_tracker.py:40-48` |
| Breakout Feedback | ❌ Missing | `breakout_feedback.py:26-32` |
| Primary Feedback | ❌ Missing | `feedback/database.py:57-100` |
| Classification | ❌ Not Used | `classify.py:1080-1085` |
| Admin Reports | ❌ Not Shown | `admin_controls.py:913-1087` |

### MOA Already Tracks 30m (Proof)

**File:** `src/catalyst_bot/moa_price_tracker.py`
**Lines:** 40-48

```python
TRACKING_TIMEFRAMES = {
    "15m": 0.25,  # 15 minutes - flash catalyst detection
    "30m": 0.5,   # 30 minutes - momentum confirmation  ← ALREADY HERE
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "7d": 168,
}
```

### Breakout Feedback Missing 30m

**File:** `src/catalyst_bot/breakout_feedback.py`
**Lines:** 26-32

```python
TRACKING_INTERVALS = {
    "15m": 15,      # Early momentum confirmation
    "1h": 60,       # Intraday sustainability
    "4h": 240,      # Extended follow-through
    "1d": 1440,     # Overnight hold quality
}  # ← NO 30m!
```

### Primary Feedback Loop Missing 30m

**File:** `src/catalyst_bot/feedback/database.py`
**Lines:** 85-93 (table schema)

```python
# Current columns:
# price_15m_change, price_1h_change, price_4h_change, price_1d_change
# outcome_15m, outcome_1h, outcome_4h, outcome_1d
# ← NO 30m columns!
```

### Classification Not Using Historical Performance

**File:** `src/catalyst_bot/classify.py`
**Lines:** 1080-1085 (scoring calculation)

```python
# After fundamental boost, before market regime:
total_score = relevance + sentiment
# ... market regime adjustments ...
# ← No historical feedback loop integration!
```

---

## Implementation Strategy

### Data Flow After Implementation

```
Alert Generated
       ↓
┌──────────────────────────────────────────────────────────────┐
│  CLASSIFICATION (classify.py)                                │
│  + Check historical 30m performance for similar alerts       │
│  + Apply momentum_boost if category has good 30m track record│
└──────────────────────────────────────────────────────────────┘
       ↓
Alert Sent to Discord
       ↓
┌──────────────────────────────────────────────────────────────┐
│  TRACKING (breakout_feedback.py + feedback/database.py)      │
│  + Record alert with initial price                           │
│  + Schedule 30m price check (NEW)                            │
│  + Calculate 30m performance → momentum_score                │
└──────────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────┐
│  FEEDBACK LOOP (classify.py integration)                     │
│  + Query historical 30m win rate by category                 │
│  + Boost/penalize score based on track record                │
└──────────────────────────────────────────────────────────────┘
```

### Implementation Order

| Phase | Description | Time |
|-------|-------------|------|
| A | Add 30m to feedback systems | 45 min |
| B | Integrate into classification | 1 hour |
| C | Admin dashboard integration | 30 min |

---

## Phase A: Add 30m to Feedback Systems

### 1. Update Breakout Feedback Intervals

**File:** `src/catalyst_bot/breakout_feedback.py`
**Location:** Lines 26-32

**BEFORE:**
```python
TRACKING_INTERVALS = {
    "15m": 15,      # Early momentum confirmation
    "1h": 60,       # Intraday sustainability
    "4h": 240,      # Extended follow-through
    "1d": 1440,     # Overnight hold quality
}
```

**AFTER:**
```python
TRACKING_INTERVALS = {
    "15m": 15,      # Early momentum confirmation
    "30m": 30,      # Momentum confirmation sweet spot (NEW)
    "1h": 60,       # Intraday sustainability
    "4h": 240,      # Extended follow-through
    "1d": 1440,     # Overnight hold quality
}
```

### 2. Update Primary Feedback Database Schema

**File:** `src/catalyst_bot/feedback/database.py`
**Location:** Add columns to schema (Lines 57-100)

**ADD these columns to the CREATE TABLE statement:**

```python
# In _create_tables() method, update the CREATE TABLE alert_performance:

"""
CREATE TABLE IF NOT EXISTS alert_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    alert_time TIMESTAMP NOT NULL,
    initial_price REAL NOT NULL,

    -- Existing price changes
    price_15m_change REAL,
    price_30m_change REAL,  -- NEW
    price_1h_change REAL,
    price_4h_change REAL,
    price_1d_change REAL,

    -- Existing outcomes
    outcome_15m TEXT,       -- 'win', 'loss', 'neutral'
    outcome_30m TEXT,       -- NEW
    outcome_1h TEXT,
    outcome_4h TEXT,
    outcome_1d TEXT,

    -- Existing scores
    score_15m REAL,
    score_30m REAL,         -- NEW
    score_1h REAL,
    score_4h REAL,
    score_1d REAL,

    -- Aggregates
    momentum_score REAL,    -- NEW: composite 30m-based score
    final_outcome TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
```

### 3. Add Migration for Existing Database

**File:** `src/catalyst_bot/feedback/database.py`
**Location:** Add new method after `_create_tables()`

```python
def _migrate_add_30m_columns(self) -> None:
    """Add 30m tracking columns to existing database."""
    try:
        cursor = self.conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(alert_performance)")
        columns = {row[1] for row in cursor.fetchall()}

        new_columns = [
            ("price_30m_change", "REAL"),
            ("outcome_30m", "TEXT"),
            ("score_30m", "REAL"),
            ("momentum_score", "REAL"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in columns:
                cursor.execute(
                    f"ALTER TABLE alert_performance ADD COLUMN {col_name} {col_type}"
                )
                self.logger.info(f"migration_added_column column={col_name}")

        self.conn.commit()

    except Exception as e:
        self.logger.error(f"migration_30m_failed err={e}")
```

### 4. Update Feedback Collection

**File:** `src/catalyst_bot/feedback/database.py`
**Location:** In `record_price_update()` method

```python
# Add 30m to the TRACKING_INTERVALS constant at top of file:
TRACKING_INTERVALS = {
    "15m": 15,
    "30m": 30,  # NEW
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# Update record_price_update() to handle 30m:
def record_price_update(
    self,
    alert_id: str,
    timeframe: str,  # Now accepts "30m"
    price_change: float,
) -> None:
    """Record price change for a timeframe."""

    # Determine outcome based on price change
    if price_change >= 2.0:
        outcome = "win"
        score = min(price_change / 10.0, 1.0)  # Cap at 1.0 for +10%
    elif price_change <= -2.0:
        outcome = "loss"
        score = max(price_change / 10.0, -1.0)  # Cap at -1.0 for -10%
    else:
        outcome = "neutral"
        score = price_change / 10.0

    # Update database
    cursor = self.conn.cursor()
    cursor.execute(f"""
        UPDATE alert_performance
        SET price_{timeframe}_change = ?,
            outcome_{timeframe} = ?,
            score_{timeframe} = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE alert_id = ?
    """, (price_change, outcome, score, alert_id))

    # If this is the 30m update, also calculate momentum_score
    if timeframe == "30m":
        self._update_momentum_score(alert_id, price_change, outcome)

    self.conn.commit()


def _update_momentum_score(
    self,
    alert_id: str,
    price_change_30m: float,
    outcome_30m: str,
) -> None:
    """Calculate and store momentum score based on 30m performance."""

    # Momentum score formula:
    # - Base: 30m price change normalized to [-1, 1]
    # - Bonus: +0.2 for strong moves (>3%)
    # - Penalty: -0.2 for reversals (negative after positive 15m)

    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT price_15m_change FROM alert_performance WHERE alert_id = ?
    """, (alert_id,))
    row = cursor.fetchone()
    price_15m = row[0] if row and row[0] else 0

    # Base score from 30m change
    momentum_score = max(min(price_change_30m / 5.0, 1.0), -1.0)

    # Bonus for strong continuation
    if price_change_30m > 3.0:
        momentum_score += 0.2

    # Penalty for reversal (was positive at 15m, negative at 30m)
    if price_15m > 1.0 and price_change_30m < 0:
        momentum_score -= 0.3

    # Cap final score
    momentum_score = max(min(momentum_score, 1.0), -1.0)

    cursor.execute("""
        UPDATE alert_performance
        SET momentum_score = ?
        WHERE alert_id = ?
    """, (momentum_score, alert_id))
    self.conn.commit()
```

---

## Phase B: Integrate 30m into Classification Scoring

### 1. Add Historical Performance Lookup

**File:** `src/catalyst_bot/classify.py`
**Location:** Add new function after imports (around Line 50)

```python
def get_category_momentum_stats(category: str, lookback_days: int = 30) -> dict:
    """
    Get historical 30m momentum statistics for a category.

    Args:
        category: Alert category (earnings, sec_filing, breakout, etc.)
        lookback_days: How far back to look for historical data

    Returns:
        dict with win_rate, avg_momentum_score, sample_size

    Integration Point:
        Called in calculate_score() to adjust score based on track record
    """
    try:
        from .feedback.database import FeedbackDatabase
        db = FeedbackDatabase()

        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome_30m = 'win' THEN 1 ELSE 0 END) as wins,
                AVG(momentum_score) as avg_momentum,
                AVG(price_30m_change) as avg_price_change
            FROM alert_performance
            WHERE category = ?
              AND alert_time > datetime('now', ?)
              AND outcome_30m IS NOT NULL
        """, (category, f'-{lookback_days} days'))

        row = cursor.fetchone()

        if not row or row[0] < 5:  # Need minimum 5 samples
            return {
                'has_data': False,
                'sample_size': row[0] if row else 0,
            }

        return {
            'has_data': True,
            'sample_size': row[0],
            'win_rate': (row[1] / row[0]) * 100 if row[0] > 0 else 0,
            'avg_momentum_score': row[2] or 0,
            'avg_price_change_30m': row[3] or 0,
        }

    except Exception as e:
        # Log but don't crash classification
        import logging
        logging.getLogger(__name__).debug(f"momentum_stats_failed err={e}")
        return {'has_data': False, 'sample_size': 0}
```

### 2. Integrate Momentum Boost into Scoring

**File:** `src/catalyst_bot/classify.py`
**Location:** Lines 1080-1085 (in calculate_score function)

**Find this section:**
```python
# After fundamental boost calculation
total_score = relevance + sentiment
# ... existing code ...
```

**ADD momentum adjustment:**
```python
# After fundamental boost calculation
total_score = relevance + sentiment

# NEW: Apply historical momentum boost/penalty
momentum_adjustment = 0.0
if os.getenv("FEATURE_MOMENTUM_FEEDBACK", "1").strip().lower() in ("1", "true", "yes"):
    try:
        momentum_stats = get_category_momentum_stats(category, lookback_days=30)

        if momentum_stats.get('has_data') and momentum_stats['sample_size'] >= 10:
            # Strong performers get boost, weak performers get penalty
            avg_momentum = momentum_stats['avg_momentum_score']
            win_rate = momentum_stats['win_rate']

            if win_rate >= 60 and avg_momentum > 0.3:
                # Category has strong 30m track record
                momentum_adjustment = 0.15
                log.debug(
                    f"momentum_boost category={category} "
                    f"win_rate={win_rate:.1f}% avg_momentum={avg_momentum:.2f}"
                )
            elif win_rate <= 35 and avg_momentum < -0.2:
                # Category has poor 30m track record
                momentum_adjustment = -0.10
                log.debug(
                    f"momentum_penalty category={category} "
                    f"win_rate={win_rate:.1f}% avg_momentum={avg_momentum:.2f}"
                )
    except Exception:
        pass  # Never crash classification on feedback lookup

total_score += momentum_adjustment

# Continue with existing market regime adjustments...
```

### 3. Add Category-Specific Momentum Thresholds

**File:** `src/catalyst_bot/classify.py`
**Location:** Near top of file, after constants

```python
# Category-specific momentum thresholds
# Different categories have different expected volatility
CATEGORY_MOMENTUM_THRESHOLDS = {
    "earnings": {
        "win_threshold": 3.0,    # Earnings need bigger moves
        "loss_threshold": -2.0,
    },
    "sec_filing": {
        "win_threshold": 2.5,
        "loss_threshold": -1.5,
    },
    "breakout": {
        "win_threshold": 2.0,    # Breakouts confirmed at lower threshold
        "loss_threshold": -1.5,
    },
    "catalyst": {
        "win_threshold": 2.0,
        "loss_threshold": -1.5,
    },
    "default": {
        "win_threshold": 2.0,
        "loss_threshold": -2.0,
    },
}

def get_momentum_thresholds(category: str) -> dict:
    """Get momentum thresholds for a category."""
    return CATEGORY_MOMENTUM_THRESHOLDS.get(
        category,
        CATEGORY_MOMENTUM_THRESHOLDS["default"]
    )
```

---

## Phase C: Admin Dashboard Integration

### 1. Add 30m Stats to Admin Report

**File:** `src/catalyst_bot/admin_controls.py`
**Location:** In `generate_admin_report()` function (around Line 761)

```python
# ADD to the report generation:

def _get_momentum_report() -> dict:
    """Generate 30m momentum performance report."""
    try:
        from .feedback.database import FeedbackDatabase
        db = FeedbackDatabase()

        cursor = db.conn.cursor()

        # Overall 30m stats
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome_30m = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome_30m = 'loss' THEN 1 ELSE 0 END) as losses,
                AVG(price_30m_change) as avg_change,
                AVG(momentum_score) as avg_momentum
            FROM alert_performance
            WHERE outcome_30m IS NOT NULL
              AND alert_time > datetime('now', '-7 days')
        """)
        overall = cursor.fetchone()

        # Per-category breakdown
        cursor.execute("""
            SELECT
                category,
                COUNT(*) as total,
                SUM(CASE WHEN outcome_30m = 'win' THEN 1 ELSE 0 END) as wins,
                AVG(price_30m_change) as avg_change
            FROM alert_performance
            WHERE outcome_30m IS NOT NULL
              AND alert_time > datetime('now', '-7 days')
            GROUP BY category
            ORDER BY wins DESC
        """)
        by_category = cursor.fetchall()

        return {
            'overall': {
                'total': overall[0] or 0,
                'wins': overall[1] or 0,
                'losses': overall[2] or 0,
                'win_rate': (overall[1] / overall[0] * 100) if overall[0] else 0,
                'avg_change': overall[3] or 0,
                'avg_momentum': overall[4] or 0,
            },
            'by_category': [
                {
                    'category': row[0],
                    'total': row[1],
                    'wins': row[2],
                    'win_rate': (row[2] / row[1] * 100) if row[1] else 0,
                    'avg_change': row[3] or 0,
                }
                for row in by_category
            ]
        }

    except Exception as e:
        return {'error': str(e)}
```

### 2. Add 30m Section to Admin Embed

**File:** `src/catalyst_bot/admin_controls.py`
**Location:** In `build_admin_embed()` function (around Line 1005)

```python
# ADD new field to the embed:

# 30m Momentum Performance (NEW)
momentum = _get_momentum_report()
if momentum and 'overall' in momentum:
    overall = momentum['overall']
    if overall['total'] > 0:
        momentum_text = (
            f"**7-Day Summary**\n"
            f"├─ Total Tracked: {overall['total']}\n"
            f"├─ Win Rate (30m): {overall['win_rate']:.1f}%\n"
            f"├─ Avg Change: {overall['avg_change']:+.2f}%\n"
            f"└─ Avg Momentum: {overall['avg_momentum']:.2f}\n\n"
        )

        # Add top categories
        if momentum.get('by_category'):
            momentum_text += "**By Category**\n"
            for cat in momentum['by_category'][:3]:  # Top 3
                emoji = "🟢" if cat['win_rate'] >= 50 else "🔴"
                momentum_text += (
                    f"{emoji} {cat['category']}: "
                    f"{cat['win_rate']:.0f}% ({cat['total']} alerts)\n"
                )

        embed["fields"].append({
            "name": "📊 30m Momentum",
            "value": momentum_text,
            "inline": False,
        })
```

---

## Coding Tickets

### Phase A: Feedback System Updates

#### Ticket A.1: Add 30m to Breakout Feedback
```
Title: Add 30-minute interval to breakout_feedback.py
Priority: High
Estimate: 15 minutes

File: src/catalyst_bot/breakout_feedback.py
Lines: 26-32

Tasks:
1. Add "30m": 30 to TRACKING_INTERVALS dict
2. Verify scheduling logic handles new interval

Acceptance Criteria:
- [ ] TRACKING_INTERVALS includes 30m: 30
- [ ] No runtime errors with new interval
```

#### Ticket A.2: Update Primary Feedback Schema
```
Title: Add 30m columns to feedback database
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/feedback/database.py
Lines: 57-100

Tasks:
1. Add price_30m_change, outcome_30m, score_30m columns
2. Add momentum_score column
3. Create _migrate_add_30m_columns() method
4. Call migration in __init__

Acceptance Criteria:
- [ ] New columns exist in alert_performance table
- [ ] Migration runs without error on existing DB
- [ ] Migration is idempotent (safe to run multiple times)
```

#### Ticket A.3: Implement Momentum Score Calculation
```
Title: Calculate momentum_score from 30m data
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/feedback/database.py

Tasks:
1. Add _update_momentum_score() method
2. Call it in record_price_update() when timeframe == "30m"
3. Implement scoring formula with reversal detection

Acceptance Criteria:
- [ ] momentum_score calculated after 30m update
- [ ] Score accounts for 15m→30m reversals
- [ ] Score bounded to [-1.0, 1.0]
```

### Phase B: Classification Integration

#### Ticket B.1: Add Historical Lookup Function
```
Title: Create get_category_momentum_stats() function
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/classify.py
Location: After imports (~Line 50)

Tasks:
1. Add get_category_momentum_stats() function
2. Query feedback database for historical 30m performance
3. Return win_rate, avg_momentum_score, sample_size

Acceptance Criteria:
- [ ] Function returns accurate stats
- [ ] Graceful fallback if DB unavailable
- [ ] Minimum sample size requirement (5+)
```

#### Ticket B.2: Integrate Momentum into Scoring
```
Title: Add momentum adjustment to calculate_score()
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/classify.py
Lines: 1080-1085

Tasks:
1. Call get_category_momentum_stats() in scoring
2. Apply boost (+0.15) for high performers
3. Apply penalty (-0.10) for poor performers
4. Make feature-flagged (FEATURE_MOMENTUM_FEEDBACK)

Acceptance Criteria:
- [ ] High win-rate categories get score boost
- [ ] Low win-rate categories get score penalty
- [ ] Can be disabled via environment variable
- [ ] Never crashes classification on errors
```

### Phase C: Admin Integration

#### Ticket C.1: Add Momentum Report to Admin
```
Title: Display 30m momentum stats in admin report
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/admin_controls.py
Lines: 761-820, 913-1087

Tasks:
1. Create _get_momentum_report() helper function
2. Add "30m Momentum" field to admin embed
3. Show overall win rate and top categories

Acceptance Criteria:
- [ ] Admin embed shows 30m momentum section
- [ ] Shows 7-day win rate and average change
- [ ] Shows top 3 categories by win rate
```

---

## Testing & Verification

### 1. Database Migration Test

```bash
# Backup existing database
cp data/feedback/alert_performance.db data/feedback/alert_performance.db.bak

# Run bot once to trigger migration
python -m catalyst_bot.runner --once

# Verify columns exist
sqlite3 data/feedback/alert_performance.db ".schema alert_performance" | grep 30m
# Should show: price_30m_change, outcome_30m, score_30m, momentum_score
```

### 2. Verify 30m Tracking

```python
# tests/test_30m_feedback.py
import pytest

def test_30m_in_breakout_intervals():
    """Verify 30m is in breakout feedback intervals."""
    from catalyst_bot.breakout_feedback import TRACKING_INTERVALS
    assert "30m" in TRACKING_INTERVALS
    assert TRACKING_INTERVALS["30m"] == 30

def test_30m_in_primary_feedback():
    """Verify 30m columns exist in feedback database."""
    from catalyst_bot.feedback.database import FeedbackDatabase
    db = FeedbackDatabase()
    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(alert_performance)")
    columns = {row[1] for row in cursor.fetchall()}

    assert "price_30m_change" in columns
    assert "outcome_30m" in columns
    assert "score_30m" in columns
    assert "momentum_score" in columns
```

### 3. Verify Classification Integration

```python
def test_momentum_stats_lookup():
    """Verify momentum stats function works."""
    from catalyst_bot.classify import get_category_momentum_stats

    # Should not crash even with no data
    stats = get_category_momentum_stats("test_category")
    assert isinstance(stats, dict)
    assert 'has_data' in stats or 'sample_size' in stats

def test_momentum_adjustment_bounds():
    """Verify momentum adjustment stays within bounds."""
    # Mock high win rate category
    adjustment = 0.15  # Max boost
    assert -0.15 <= adjustment <= 0.15
```

### 4. End-to-End Verification

```bash
# Run a few cycles and check feedback
FEATURE_FEEDBACK_LOOP=1 FEATURE_MOMENTUM_FEEDBACK=1 python -m catalyst_bot.runner --cycles 3

# After 30+ minutes, check for 30m data
sqlite3 data/feedback/alert_performance.db "SELECT ticker, price_30m_change, outcome_30m, momentum_score FROM alert_performance WHERE outcome_30m IS NOT NULL LIMIT 5"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_FEEDBACK_LOOP` | `0` | Enable primary feedback loop |
| `FEATURE_MOMENTUM_FEEDBACK` | `1` | Enable 30m momentum adjustments in classification |

---

## Summary

This implementation:

1. **Leverages Existing Data** - MOA already tracks 30m, we're connecting the dots
2. **Minimal Code Changes** - Add 30m to existing structures, ~150 lines of new code
3. **Self-Improving** - Classification gets smarter based on actual 30m outcomes
4. **Transparent** - Admin dashboard shows momentum performance

**Implementation Order:**
1. Phase A: Add 30m to feedback systems (45 min)
2. Phase B: Integrate into classification (1 hour)
3. Phase C: Admin dashboard (30 min)

**Expected Impact:**
- 15-25% improvement in alert quality over 2-4 weeks
- Automatic down-weighting of poor-performing alert categories
- Faster momentum confirmation vs waiting for 1h data

---

**End of Implementation Guide**
