# Unify Feedback Systems Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** HIGH
**Impact:** HIGH | **Effort:** MEDIUM | **ROI:** HIGH
**Estimated Implementation Time:** 4-6 hours
**Target Files:** `src/catalyst_bot/feedback/`, `src/catalyst_bot/breakout_feedback.py`, `src/catalyst_bot/moa_price_tracker.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Unified Architecture](#unified-architecture)
4. [Phase A: Create Unified Feedback Interface](#phase-a-create-unified-feedback-interface)
5. [Phase B: Migrate Breakout Feedback](#phase-b-migrate-breakout-feedback)
6. [Phase C: Migrate MOA Tracking](#phase-c-migrate-moa-tracking)
7. [Phase D: Deprecation & Cleanup](#phase-d-deprecation--cleanup)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

Catalyst-Bot has **three parallel feedback tracking systems** that evolved independently:

| System | Storage | Feature Flag | Active By Default |
|--------|---------|--------------|-------------------|
| Primary Feedback Loop | SQLite (`alert_performance.db`) | `FEATURE_FEEDBACK_LOOP` | No |
| Breakout Feedback | SQLite (`alert_outcomes` table) | None | **Yes** |
| MOA Price Tracker | JSONL (`outcomes.jsonl`) | None | **Yes** |

**Problems:**
1. **Duplicate tracking** - Same alerts tracked in multiple places
2. **Inconsistent schemas** - Different columns, different outcome definitions
3. **Split data** - Can't get unified view of alert performance
4. **Maintenance burden** - Three codepaths to update for any change

### What We're Building

A **unified feedback system** that:
1. Consolidates all tracking into one SQLite database
2. Uses consistent outcome definitions and scoring
3. Provides single API for recording and querying feedback
4. Maintains backward compatibility during migration

```
BEFORE (3 Systems)                    AFTER (1 System)
┌─────────────────┐                   ┌─────────────────────────────────┐
│ Primary Feedback│                   │                                 │
│ (SQLite)        │                   │  UNIFIED FEEDBACK SYSTEM        │
├─────────────────┤                   │  (SQLite: alert_feedback.db)    │
│ Breakout Feedbk │  ───────────►     │                                 │
│ (SQLite)        │                   │  - All alerts tracked           │
├─────────────────┤                   │  - Consistent schema            │
│ MOA Tracker     │                   │  - Single query interface       │
│ (JSONL)         │                   │  - Historical migration         │
└─────────────────┘                   └─────────────────────────────────┘
```

---

## Current State Analysis

### System 1: Primary Feedback Loop

**Location:** `src/catalyst_bot/feedback/database.py`
**Storage:** `data/feedback/alert_performance.db`
**Feature Flag:** `FEATURE_FEEDBACK_LOOP` (default: off)

**Schema (Lines 57-100):**
```python
# Table: alert_performance
# Columns:
#   id, alert_id, ticker, category, alert_time, initial_price,
#   price_15m_change, price_1h_change, price_4h_change, price_1d_change,
#   outcome_15m, outcome_1h, outcome_4h, outcome_1d,
#   score_15m, score_1h, score_4h, score_1d,
#   final_outcome, created_at, updated_at
```

**Strengths:**
- ✅ Comprehensive schema with scores
- ✅ SQLite for reliable storage
- ✅ Outcome classification (win/loss/neutral)

**Weaknesses:**
- ❌ Feature-flagged off by default
- ❌ Missing 30m timeframe
- ❌ Not integrated with classification

---

### System 2: Breakout Feedback

**Location:** `src/catalyst_bot/breakout_feedback.py`
**Storage:** Shared DB in `data/` (table: `alert_outcomes`)
**Feature Flag:** None (always active)

**Schema (Lines 55-75):**
```python
# Table: alert_outcomes
# Columns:
#   id, alert_id, ticker, category, headline,
#   alert_time, initial_price,
#   price_15m, price_1h, price_4h, price_1d,
#   change_15m, change_1h, change_4h, change_1d,
#   created_at
```

**Key Code (Lines 26-32):**
```python
TRACKING_INTERVALS = {
    "15m": 15,      # Early momentum confirmation
    "1h": 60,       # Intraday sustainability
    "4h": 240,      # Extended follow-through
    "1d": 1440,     # Overnight hold quality
}
```

**Strengths:**
- ✅ Always active
- ✅ Stores headline text

**Weaknesses:**
- ❌ No outcome classification
- ❌ No scoring
- ❌ Missing 30m timeframe
- ❌ Duplicate of primary feedback

---

### System 3: MOA Price Tracker

**Location:** `src/catalyst_bot/moa_price_tracker.py`
**Storage:** `data/moa/outcomes.jsonl`
**Feature Flag:** None (tracks rejected items)

**Schema (Lines 40-48 for timeframes, ~Line 200 for output):**
```python
TRACKING_TIMEFRAMES = {
    "15m": 0.25,
    "30m": 0.5,   # Has 30m!
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "7d": 168,
}

# Output format (JSONL):
# {"ticker": "AAPL", "headline": "...", "tracked_time": "...",
#  "price_changes": {"15m": 1.5, "30m": 2.3, ...}, "outcome": "missed_opportunity"}
```

**Strengths:**
- ✅ Has 30m timeframe
- ✅ Tracks rejected items (MOA analysis)
- ✅ 7d long-term tracking

**Weaknesses:**
- ❌ JSONL storage (harder to query)
- ❌ Only tracks rejected items
- ❌ Different outcome semantics

---

### Overlap Analysis

| Feature | Primary | Breakout | MOA |
|---------|---------|----------|-----|
| 15m tracking | ✅ | ✅ | ✅ |
| 30m tracking | ❌ | ❌ | ✅ |
| 1h tracking | ✅ | ✅ | ✅ |
| 4h tracking | ✅ | ✅ | ✅ |
| 1d tracking | ✅ | ✅ | ✅ |
| 7d tracking | ❌ | ❌ | ✅ |
| Win/loss classification | ✅ | ❌ | Partial |
| Score calculation | ✅ | ❌ | ❌ |
| SQLite storage | ✅ | ✅ | ❌ |
| Always active | ❌ | ✅ | ✅ |

---

## Unified Architecture

### New Schema Design

```python
# File: src/catalyst_bot/feedback/unified_database.py
# Table: alert_feedback (replaces all three systems)

"""
CREATE TABLE IF NOT EXISTS alert_feedback (
    -- Identifiers
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,           -- 'alert', 'moa_rejected', 'breakout'

    -- Context
    headline TEXT,
    alert_time TIMESTAMP NOT NULL,
    initial_price REAL NOT NULL,

    -- Price tracking (all timeframes)
    price_15m REAL,
    price_30m REAL,
    price_1h REAL,
    price_4h REAL,
    price_1d REAL,
    price_7d REAL,

    -- Change percentages
    change_15m REAL,
    change_30m REAL,
    change_1h REAL,
    change_4h REAL,
    change_1d REAL,
    change_7d REAL,

    -- Outcomes (win/loss/neutral per timeframe)
    outcome_15m TEXT,
    outcome_30m TEXT,
    outcome_1h TEXT,
    outcome_4h TEXT,
    outcome_1d TEXT,
    outcome_7d TEXT,

    -- Scores (-1.0 to +1.0 per timeframe)
    score_15m REAL,
    score_30m REAL,
    score_1h REAL,
    score_4h REAL,
    score_1d REAL,
    score_7d REAL,

    -- Aggregates
    momentum_score REAL,            -- 30m-based composite
    final_outcome TEXT,             -- Overall assessment
    final_score REAL,               -- Weighted average

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for common queries
    UNIQUE(ticker, alert_time)
)

CREATE INDEX idx_alert_feedback_ticker ON alert_feedback(ticker);
CREATE INDEX idx_alert_feedback_category ON alert_feedback(category);
CREATE INDEX idx_alert_feedback_alert_time ON alert_feedback(alert_time);
CREATE INDEX idx_alert_feedback_source ON alert_feedback(source);
"""
```

### Unified API

```python
# File: src/catalyst_bot/feedback/unified_feedback.py

class UnifiedFeedback:
    """
    Single interface for all feedback tracking.

    Replaces:
    - feedback/database.py FeedbackDatabase
    - breakout_feedback.py BreakoutFeedback
    - moa_price_tracker.py price tracking

    Usage:
        from catalyst_bot.feedback import UnifiedFeedback

        fb = UnifiedFeedback()
        fb.record_alert(alert_id, ticker, category, price, headline)
        fb.update_price(alert_id, "30m", new_price)
        stats = fb.get_category_stats("earnings", days=30)
    """

    def record_alert(self, alert_id, ticker, category, initial_price, headline=None, source='alert'):
        """Record a new alert for tracking."""
        pass

    def update_price(self, alert_id, timeframe, current_price):
        """Update price for a timeframe, calculate change and outcome."""
        pass

    def get_category_stats(self, category, days=30):
        """Get performance statistics for a category."""
        pass

    def get_ticker_stats(self, ticker, days=90):
        """Get performance statistics for a ticker."""
        pass

    def get_pending_updates(self, timeframe):
        """Get alerts needing price updates for a timeframe."""
        pass
```

---

## Phase A: Create Unified Feedback Interface

### 1. Create New Module Structure

**Create directory and files:**
```
src/catalyst_bot/feedback/
├── __init__.py              # Package exports
├── unified_database.py      # New unified schema
├── unified_feedback.py      # New unified API
├── database.py              # Existing (keep for migration)
└── migration.py             # Data migration utilities
```

### 2. Implement Unified Database

**File:** `src/catalyst_bot/feedback/unified_database.py`

```python
"""
Unified feedback database schema.

Consolidates:
- Primary feedback loop (alert_performance table)
- Breakout feedback (alert_outcomes table)
- MOA price tracker (outcomes.jsonl)

Into single alert_feedback table with consistent schema.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("unified_feedback")


# Tracking timeframes with minutes
TIMEFRAMES = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "7d": 10080,
}

# Outcome thresholds (percentage change)
WIN_THRESHOLD = 2.0       # +2% = win
LOSS_THRESHOLD = -2.0     # -2% = loss


def get_db_path() -> Path:
    """Get path to unified feedback database."""
    try:
        from ..config import get_settings
        settings = get_settings()
        data_dir = Path(settings.data_dir)
    except Exception:
        data_dir = Path("data")

    feedback_dir = data_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    return feedback_dir / "alert_feedback.db"


def init_database(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Initialize unified feedback database.

    Args:
        db_path: Optional path override for testing

    Returns:
        sqlite3.Connection to the database
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Create main table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id TEXT NOT NULL UNIQUE,
            ticker TEXT NOT NULL,
            category TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'alert',

            headline TEXT,
            alert_time TIMESTAMP NOT NULL,
            initial_price REAL NOT NULL,

            price_15m REAL,
            price_30m REAL,
            price_1h REAL,
            price_4h REAL,
            price_1d REAL,
            price_7d REAL,

            change_15m REAL,
            change_30m REAL,
            change_1h REAL,
            change_4h REAL,
            change_1d REAL,
            change_7d REAL,

            outcome_15m TEXT,
            outcome_30m TEXT,
            outcome_1h TEXT,
            outcome_4h TEXT,
            outcome_1d TEXT,
            outcome_7d TEXT,

            score_15m REAL,
            score_30m REAL,
            score_1h REAL,
            score_4h REAL,
            score_1d REAL,
            score_7d REAL,

            momentum_score REAL,
            final_outcome TEXT,
            final_score REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_ticker
        ON alert_feedback(ticker)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_category
        ON alert_feedback(category)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_alert_time
        ON alert_feedback(alert_time)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_source
        ON alert_feedback(source)
    """)

    conn.commit()
    log.info("unified_database_initialized path=%s", db_path)

    return conn


def calculate_outcome(change_pct: float) -> tuple[str, float]:
    """
    Calculate outcome and score from price change.

    Args:
        change_pct: Percentage change (e.g., 2.5 for +2.5%)

    Returns:
        Tuple of (outcome, score) where:
        - outcome: 'win', 'loss', or 'neutral'
        - score: -1.0 to +1.0
    """
    if change_pct >= WIN_THRESHOLD:
        outcome = "win"
        # Score scales from 0.5 at threshold to 1.0 at +10%
        score = min(0.5 + (change_pct - WIN_THRESHOLD) / 16.0, 1.0)
    elif change_pct <= LOSS_THRESHOLD:
        outcome = "loss"
        # Score scales from -0.5 at threshold to -1.0 at -10%
        score = max(-0.5 + (change_pct - LOSS_THRESHOLD) / 16.0, -1.0)
    else:
        outcome = "neutral"
        # Small score based on direction
        score = change_pct / 10.0

    return outcome, round(score, 3)
```

### 3. Implement Unified API

**File:** `src/catalyst_bot/feedback/unified_feedback.py`

```python
"""
Unified feedback API for Catalyst-Bot.

Provides single interface for:
- Recording alerts for tracking
- Updating prices at each timeframe
- Querying performance statistics
- Getting pending price updates

Replaces breakout_feedback.py and primary feedback loop.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .unified_database import (
    TIMEFRAMES,
    calculate_outcome,
    get_db_path,
    init_database,
)

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("unified_feedback")


class UnifiedFeedback:
    """
    Unified feedback tracking system.

    Thread-safe singleton pattern - all instances share same connection.
    """

    _instance: Optional['UnifiedFeedback'] = None
    _conn: Optional[sqlite3.Connection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._conn = init_database()
        return cls._instance

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection, reinitializing if needed."""
        if self._conn is None:
            self._conn = init_database()
        return self._conn

    def record_alert(
        self,
        ticker: str,
        category: str,
        initial_price: float,
        headline: Optional[str] = None,
        source: str = "alert",
        alert_id: Optional[str] = None,
        alert_time: Optional[datetime] = None,
    ) -> str:
        """
        Record a new alert for feedback tracking.

        Args:
            ticker: Stock ticker symbol
            category: Alert category (earnings, sec_filing, breakout, etc.)
            initial_price: Price at time of alert
            headline: Optional alert headline
            source: Source system ('alert', 'moa_rejected', 'breakout')
            alert_id: Optional custom ID (auto-generated if not provided)
            alert_time: Optional timestamp (defaults to now)

        Returns:
            alert_id for the recorded alert

        Integration Points:
            - runner.py: After sending Discord alert
            - moa_price_tracker.py: When recording rejected item
            - breakout_feedback.py: Replace record_alert()
        """
        if alert_id is None:
            alert_id = f"{ticker}_{uuid.uuid4().hex[:8]}"

        if alert_time is None:
            alert_time = datetime.now(timezone.utc)

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO alert_feedback
                (alert_id, ticker, category, source, headline, alert_time, initial_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (alert_id, ticker.upper(), category, source, headline,
                  alert_time.isoformat(), initial_price))
            self.conn.commit()

            log.debug(
                "alert_recorded id=%s ticker=%s category=%s price=%.2f",
                alert_id, ticker, category, initial_price
            )
            return alert_id

        except Exception as e:
            log.error("record_alert_failed ticker=%s err=%s", ticker, e)
            raise

    def update_price(
        self,
        alert_id: str,
        timeframe: str,
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Update price for a timeframe, calculating change and outcome.

        Args:
            alert_id: Alert identifier
            timeframe: Timeframe key ('15m', '30m', '1h', '4h', '1d', '7d')
            current_price: Current price to record

        Returns:
            Dict with change_pct, outcome, score

        Integration Points:
            - feedback/collector.py: On scheduled price checks
            - breakout_feedback.py: Replace update_price()
        """
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Invalid timeframe: {timeframe}. Valid: {list(TIMEFRAMES.keys())}")

        try:
            cursor = self.conn.cursor()

            # Get initial price
            cursor.execute("""
                SELECT initial_price FROM alert_feedback WHERE alert_id = ?
            """, (alert_id,))
            row = cursor.fetchone()

            if not row:
                log.warning("update_price_alert_not_found id=%s", alert_id)
                return {"error": "Alert not found"}

            initial_price = row[0]
            if initial_price <= 0:
                return {"error": "Invalid initial price"}

            # Calculate change
            change_pct = ((current_price - initial_price) / initial_price) * 100
            outcome, score = calculate_outcome(change_pct)

            # Update database
            cursor.execute(f"""
                UPDATE alert_feedback
                SET price_{timeframe} = ?,
                    change_{timeframe} = ?,
                    outcome_{timeframe} = ?,
                    score_{timeframe} = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE alert_id = ?
            """, (current_price, change_pct, outcome, score, alert_id))

            # Update momentum score if 30m
            if timeframe == "30m":
                self._update_momentum_score(alert_id, change_pct, outcome)

            # Update final outcome if 1d
            if timeframe == "1d":
                self._update_final_outcome(alert_id)

            self.conn.commit()

            log.debug(
                "price_updated id=%s tf=%s change=%.2f%% outcome=%s",
                alert_id, timeframe, change_pct, outcome
            )

            return {
                "change_pct": round(change_pct, 2),
                "outcome": outcome,
                "score": score,
            }

        except Exception as e:
            log.error("update_price_failed id=%s tf=%s err=%s", alert_id, timeframe, e)
            raise

    def _update_momentum_score(
        self,
        alert_id: str,
        change_30m: float,
        outcome_30m: str,
    ) -> None:
        """Calculate and store momentum score from 30m data."""
        cursor = self.conn.cursor()

        # Get 15m data for reversal detection
        cursor.execute("""
            SELECT change_15m FROM alert_feedback WHERE alert_id = ?
        """, (alert_id,))
        row = cursor.fetchone()
        change_15m = row[0] if row and row[0] else 0

        # Base score from 30m change
        momentum_score = max(min(change_30m / 5.0, 1.0), -1.0)

        # Bonus for strong continuation
        if change_30m > 3.0:
            momentum_score += 0.2

        # Penalty for reversal (positive 15m, negative 30m)
        if change_15m > 1.0 and change_30m < 0:
            momentum_score -= 0.3

        momentum_score = max(min(momentum_score, 1.0), -1.0)

        cursor.execute("""
            UPDATE alert_feedback SET momentum_score = ? WHERE alert_id = ?
        """, (round(momentum_score, 3), alert_id))

    def _update_final_outcome(self, alert_id: str) -> None:
        """Calculate final outcome from all timeframes."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT outcome_15m, outcome_30m, outcome_1h, outcome_4h, outcome_1d,
                   score_15m, score_30m, score_1h, score_4h, score_1d
            FROM alert_feedback WHERE alert_id = ?
        """, (alert_id,))
        row = cursor.fetchone()

        if not row:
            return

        # Weight later timeframes more heavily
        weights = {'15m': 0.1, '30m': 0.15, '1h': 0.2, '4h': 0.25, '1d': 0.3}
        outcomes = [row[0], row[1], row[2], row[3], row[4]]
        scores = [row[5], row[6], row[7], row[8], row[9]]

        # Calculate weighted score
        total_weight = 0
        weighted_score = 0
        for i, (tf, weight) in enumerate(weights.items()):
            if scores[i] is not None:
                weighted_score += scores[i] * weight
                total_weight += weight

        final_score = weighted_score / total_weight if total_weight > 0 else 0

        # Determine final outcome
        wins = sum(1 for o in outcomes if o == 'win')
        losses = sum(1 for o in outcomes if o == 'loss')

        if wins >= 3:
            final_outcome = 'win'
        elif losses >= 3:
            final_outcome = 'loss'
        elif final_score > 0.2:
            final_outcome = 'win'
        elif final_score < -0.2:
            final_outcome = 'loss'
        else:
            final_outcome = 'neutral'

        cursor.execute("""
            UPDATE alert_feedback
            SET final_outcome = ?, final_score = ?
            WHERE alert_id = ?
        """, (final_outcome, round(final_score, 3), alert_id))

    def get_category_stats(
        self,
        category: str,
        days: int = 30,
        timeframe: str = "30m",
    ) -> Dict[str, Any]:
        """
        Get performance statistics for a category.

        Args:
            category: Alert category
            days: Lookback period
            timeframe: Timeframe to analyze

        Returns:
            Dict with total, wins, losses, win_rate, avg_change, avg_score

        Integration Points:
            - classify.py: get_category_momentum_stats()
            - admin_controls.py: Admin reports
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome_{timeframe} = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome_{timeframe} = 'loss' THEN 1 ELSE 0 END) as losses,
                    AVG(change_{timeframe}) as avg_change,
                    AVG(score_{timeframe}) as avg_score,
                    AVG(momentum_score) as avg_momentum
                FROM alert_feedback
                WHERE category = ?
                  AND alert_time > datetime('now', ?)
                  AND outcome_{timeframe} IS NOT NULL
            """, (category, f'-{days} days'))

            row = cursor.fetchone()

            if not row or row[0] == 0:
                return {
                    'has_data': False,
                    'sample_size': 0,
                }

            return {
                'has_data': True,
                'sample_size': row[0],
                'wins': row[1],
                'losses': row[2],
                'win_rate': (row[1] / row[0]) * 100 if row[0] > 0 else 0,
                'avg_change': row[3] or 0,
                'avg_score': row[4] or 0,
                'avg_momentum': row[5] or 0,
            }

        except Exception as e:
            log.error("get_category_stats_failed category=%s err=%s", category, e)
            return {'has_data': False, 'error': str(e)}

    def get_ticker_stats(
        self,
        ticker: str,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Get performance statistics for a ticker.

        Args:
            ticker: Stock ticker symbol
            days: Lookback period

        Returns:
            Dict with stats per timeframe
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN final_outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    AVG(momentum_score) as avg_momentum,
                    AVG(final_score) as avg_score
                FROM alert_feedback
                WHERE ticker = ?
                  AND alert_time > datetime('now', ?)
            """, (ticker.upper(), f'-{days} days'))

            row = cursor.fetchone()

            if not row or row[0] == 0:
                return {'has_data': False, 'sample_size': 0}

            return {
                'has_data': True,
                'sample_size': row[0],
                'wins': row[1],
                'win_rate': (row[1] / row[0]) * 100 if row[0] > 0 else 0,
                'avg_momentum': row[2] or 0,
                'avg_score': row[3] or 0,
            }

        except Exception as e:
            log.error("get_ticker_stats_failed ticker=%s err=%s", ticker, e)
            return {'has_data': False, 'error': str(e)}

    def get_pending_updates(
        self,
        timeframe: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get alerts needing price updates for a timeframe.

        Args:
            timeframe: Timeframe to check
            limit: Maximum results

        Returns:
            List of dicts with alert_id, ticker, alert_time

        Integration Points:
            - feedback/collector.py: Scheduled price collection
        """
        if timeframe not in TIMEFRAMES:
            return []

        minutes = TIMEFRAMES[timeframe]

        try:
            cursor = self.conn.cursor()
            cursor.execute(f"""
                SELECT alert_id, ticker, alert_time, initial_price
                FROM alert_feedback
                WHERE price_{timeframe} IS NULL
                  AND alert_time <= datetime('now', '-{minutes} minutes')
                  AND alert_time > datetime('now', '-7 days')
                ORDER BY alert_time ASC
                LIMIT ?
            """, (limit,))

            return [
                {
                    'alert_id': row[0],
                    'ticker': row[1],
                    'alert_time': row[2],
                    'initial_price': row[3],
                }
                for row in cursor.fetchall()
            ]

        except Exception as e:
            log.error("get_pending_updates_failed tf=%s err=%s", timeframe, e)
            return []

    def get_recent_outcomes(
        self,
        hours: int = 24,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent alerts with their outcomes."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    alert_id, ticker, category, headline,
                    change_30m, outcome_30m,
                    change_1d, final_outcome, final_score
                FROM alert_feedback
                WHERE alert_time > datetime('now', ?)
                ORDER BY alert_time DESC
                LIMIT ?
            """, (f'-{hours} hours', limit))

            return [
                {
                    'alert_id': row[0],
                    'ticker': row[1],
                    'category': row[2],
                    'headline': row[3],
                    'change_30m': row[4],
                    'outcome_30m': row[5],
                    'change_1d': row[6],
                    'final_outcome': row[7],
                    'final_score': row[8],
                }
                for row in cursor.fetchall()
            ]

        except Exception as e:
            log.error("get_recent_outcomes_failed err=%s", e)
            return []
```

### 4. Update Package Exports

**File:** `src/catalyst_bot/feedback/__init__.py`

```python
"""
Catalyst-Bot Feedback System Package.

Provides unified feedback tracking for alert performance analysis.
"""

from .unified_feedback import UnifiedFeedback
from .unified_database import (
    TIMEFRAMES,
    WIN_THRESHOLD,
    LOSS_THRESHOLD,
    calculate_outcome,
    init_database,
)

# Legacy imports for backward compatibility during migration
try:
    from .database import FeedbackDatabase
except ImportError:
    FeedbackDatabase = None

__all__ = [
    'UnifiedFeedback',
    'TIMEFRAMES',
    'WIN_THRESHOLD',
    'LOSS_THRESHOLD',
    'calculate_outcome',
    'init_database',
    'FeedbackDatabase',  # Legacy
]
```

---

## Phase B: Migrate Breakout Feedback

### 1. Add Compatibility Layer to breakout_feedback.py

**File:** `src/catalyst_bot/breakout_feedback.py`
**Location:** Replace internal implementation with unified calls

```python
"""
Breakout feedback tracking.

NOTE: This module now delegates to UnifiedFeedback for all storage.
The external API remains unchanged for backward compatibility.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from .feedback import UnifiedFeedback
    from .logging_utils import get_logger
except ImportError:
    # Fallback for direct execution
    from feedback import UnifiedFeedback
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("breakout_feedback")

# Tracking intervals (kept for reference, actual tracking uses UnifiedFeedback)
TRACKING_INTERVALS = {
    "15m": 15,
    "30m": 30,  # Added 30m
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class BreakoutFeedback:
    """
    Breakout feedback tracker.

    Now delegates to UnifiedFeedback for all storage operations.
    This class is kept for backward compatibility.
    """

    def __init__(self):
        self._unified = UnifiedFeedback()
        self.logger = log

    def record_alert(
        self,
        ticker: str,
        category: str,
        headline: str,
        initial_price: float,
        alert_id: Optional[str] = None,
    ) -> str:
        """
        Record an alert for tracking.

        Delegates to UnifiedFeedback.record_alert()
        """
        return self._unified.record_alert(
            ticker=ticker,
            category=category,
            initial_price=initial_price,
            headline=headline,
            source="breakout",
            alert_id=alert_id,
        )

    def update_price(
        self,
        alert_id: str,
        timeframe: str,
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Update price for a timeframe.

        Delegates to UnifiedFeedback.update_price()
        """
        return self._unified.update_price(
            alert_id=alert_id,
            timeframe=timeframe,
            current_price=current_price,
        )

    def get_pending_updates(self, timeframe: str) -> list:
        """Get alerts needing price updates."""
        return self._unified.get_pending_updates(timeframe)

    def get_stats(self, category: str = None, days: int = 30) -> Dict[str, Any]:
        """Get performance statistics."""
        if category:
            return self._unified.get_category_stats(category, days)
        # Overall stats
        return self._unified.get_category_stats("breakout", days)


# Module-level singleton for backward compatibility
_feedback_instance: Optional[BreakoutFeedback] = None


def get_feedback() -> BreakoutFeedback:
    """Get singleton feedback instance."""
    global _feedback_instance
    if _feedback_instance is None:
        _feedback_instance = BreakoutFeedback()
    return _feedback_instance


def record_breakout_alert(
    ticker: str,
    category: str,
    headline: str,
    initial_price: float,
) -> str:
    """Convenience function for recording alerts."""
    return get_feedback().record_alert(ticker, category, headline, initial_price)
```

---

## Phase C: Migrate MOA Tracking

### 1. Update MOA Price Tracker

**File:** `src/catalyst_bot/moa_price_tracker.py`
**Location:** Add unified feedback integration

```python
# ADD after existing imports (~Line 30):

try:
    from .feedback import UnifiedFeedback
    UNIFIED_FEEDBACK_AVAILABLE = True
except ImportError:
    UNIFIED_FEEDBACK_AVAILABLE = False


# MODIFY track_rejected_item() to also record to unified system:

def track_rejected_item(
    ticker: str,
    headline: str,
    rejection_reason: str,
    initial_price: float,
) -> str:
    """
    Track a rejected item for MOA analysis.

    Now also records to UnifiedFeedback for consolidated tracking.
    """
    alert_id = f"moa_{ticker}_{int(time.time())}"

    # Record to unified feedback system (NEW)
    if UNIFIED_FEEDBACK_AVAILABLE:
        try:
            fb = UnifiedFeedback()
            fb.record_alert(
                ticker=ticker,
                category="moa_rejected",
                initial_price=initial_price,
                headline=headline,
                source="moa_rejected",
                alert_id=alert_id,
            )
        except Exception as e:
            log.debug("unified_feedback_record_failed err=%s", e)

    # Continue with existing JSONL tracking...
    # (keep existing implementation for backward compatibility)

    return alert_id


# MODIFY update_moa_price() to also update unified system:

def update_moa_price(
    alert_id: str,
    timeframe: str,
    current_price: float,
) -> Dict[str, Any]:
    """
    Update price for MOA tracked item.

    Now also updates UnifiedFeedback for consolidated tracking.
    """
    result = {}

    # Update unified feedback system (NEW)
    if UNIFIED_FEEDBACK_AVAILABLE:
        try:
            fb = UnifiedFeedback()
            result = fb.update_price(alert_id, timeframe, current_price)
        except Exception as e:
            log.debug("unified_feedback_update_failed err=%s", e)

    # Continue with existing JSONL update...
    # (keep existing implementation for backward compatibility)

    return result
```

---

## Phase D: Deprecation & Cleanup

### 1. Add Deprecation Warnings

**File:** `src/catalyst_bot/feedback/database.py`
**Location:** Top of file

```python
"""
DEPRECATED: This module is deprecated in favor of unified_feedback.py

Migration path:
    OLD: from catalyst_bot.feedback.database import FeedbackDatabase
    NEW: from catalyst_bot.feedback import UnifiedFeedback

This module will be removed in a future version.
"""

import warnings

def __getattr__(name):
    if name == "FeedbackDatabase":
        warnings.warn(
            "FeedbackDatabase is deprecated. Use UnifiedFeedback instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from .database_impl import FeedbackDatabase
        return FeedbackDatabase
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### 2. Create Data Migration Script

**File:** `src/catalyst_bot/feedback/migration.py`

```python
"""
Migration utilities for unified feedback system.

Migrates data from:
- alert_performance table (primary feedback)
- alert_outcomes table (breakout feedback)
- outcomes.jsonl (MOA tracker)

Into unified alert_feedback table.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

from .unified_database import get_db_path, init_database

log = get_logger("feedback_migration")


def migrate_alert_performance(
    source_db: Path,
    target_conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Migrate data from alert_performance table.

    Returns:
        Number of records migrated
    """
    if target_conn is None:
        target_conn = init_database()

    if not source_db.exists():
        log.info("source_db_not_found path=%s", source_db)
        return 0

    try:
        source_conn = sqlite3.connect(str(source_db))
        source_conn.row_factory = sqlite3.Row
        cursor = source_conn.cursor()

        cursor.execute("""
            SELECT * FROM alert_performance
        """)

        migrated = 0
        target_cursor = target_conn.cursor()

        for row in cursor.fetchall():
            try:
                target_cursor.execute("""
                    INSERT OR IGNORE INTO alert_feedback
                    (alert_id, ticker, category, source, alert_time, initial_price,
                     change_15m, change_1h, change_4h, change_1d,
                     outcome_15m, outcome_1h, outcome_4h, outcome_1d,
                     score_15m, score_1h, score_4h, score_1d,
                     final_outcome, created_at)
                    VALUES (?, ?, ?, 'primary_feedback', ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?)
                """, (
                    row['alert_id'], row['ticker'], row['category'],
                    row['alert_time'], row['initial_price'],
                    row.get('price_15m_change'), row.get('price_1h_change'),
                    row.get('price_4h_change'), row.get('price_1d_change'),
                    row.get('outcome_15m'), row.get('outcome_1h'),
                    row.get('outcome_4h'), row.get('outcome_1d'),
                    row.get('score_15m'), row.get('score_1h'),
                    row.get('score_4h'), row.get('score_1d'),
                    row.get('final_outcome'), row.get('created_at'),
                ))
                migrated += 1
            except Exception as e:
                log.debug("row_migration_failed id=%s err=%s", row.get('alert_id'), e)

        target_conn.commit()
        source_conn.close()

        log.info("migration_complete source=alert_performance count=%d", migrated)
        return migrated

    except Exception as e:
        log.error("migration_failed source=alert_performance err=%s", e)
        return 0


def migrate_alert_outcomes(
    source_db: Path,
    target_conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Migrate data from alert_outcomes table (breakout feedback).

    Returns:
        Number of records migrated
    """
    if target_conn is None:
        target_conn = init_database()

    if not source_db.exists():
        return 0

    try:
        source_conn = sqlite3.connect(str(source_db))
        source_conn.row_factory = sqlite3.Row
        cursor = source_conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='alert_outcomes'
        """)
        if not cursor.fetchone():
            return 0

        cursor.execute("""
            SELECT * FROM alert_outcomes
        """)

        migrated = 0
        target_cursor = target_conn.cursor()

        for row in cursor.fetchall():
            try:
                target_cursor.execute("""
                    INSERT OR IGNORE INTO alert_feedback
                    (alert_id, ticker, category, source, headline,
                     alert_time, initial_price,
                     price_15m, price_1h, price_4h, price_1d,
                     change_15m, change_1h, change_4h, change_1d,
                     created_at)
                    VALUES (?, ?, ?, 'breakout', ?,
                            ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?)
                """, (
                    row['alert_id'], row['ticker'], row['category'],
                    row.get('headline'),
                    row['alert_time'], row['initial_price'],
                    row.get('price_15m'), row.get('price_1h'),
                    row.get('price_4h'), row.get('price_1d'),
                    row.get('change_15m'), row.get('change_1h'),
                    row.get('change_4h'), row.get('change_1d'),
                    row.get('created_at'),
                ))
                migrated += 1
            except Exception as e:
                log.debug("row_migration_failed id=%s err=%s", row.get('alert_id'), e)

        target_conn.commit()
        source_conn.close()

        log.info("migration_complete source=alert_outcomes count=%d", migrated)
        return migrated

    except Exception as e:
        log.error("migration_failed source=alert_outcomes err=%s", e)
        return 0


def migrate_moa_jsonl(
    source_file: Path,
    target_conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Migrate data from MOA outcomes.jsonl file.

    Returns:
        Number of records migrated
    """
    if target_conn is None:
        target_conn = init_database()

    if not source_file.exists():
        return 0

    try:
        migrated = 0
        target_cursor = target_conn.cursor()

        with open(source_file, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())

                    # Generate alert_id from data
                    alert_id = f"moa_{data.get('ticker', 'UNK')}_{data.get('tracked_time', '')[:10]}"

                    price_changes = data.get('price_changes', {})

                    target_cursor.execute("""
                        INSERT OR IGNORE INTO alert_feedback
                        (alert_id, ticker, category, source, headline,
                         alert_time, initial_price,
                         change_15m, change_30m, change_1h, change_4h, change_1d, change_7d)
                        VALUES (?, ?, 'moa_rejected', 'moa', ?,
                                ?, ?,
                                ?, ?, ?, ?, ?, ?)
                    """, (
                        alert_id, data.get('ticker', '').upper(),
                        data.get('headline'),
                        data.get('tracked_time'), data.get('initial_price', 0),
                        price_changes.get('15m'), price_changes.get('30m'),
                        price_changes.get('1h'), price_changes.get('4h'),
                        price_changes.get('1d'), price_changes.get('7d'),
                    ))
                    migrated += 1
                except Exception as e:
                    log.debug("jsonl_line_migration_failed err=%s", e)

        target_conn.commit()

        log.info("migration_complete source=moa_jsonl count=%d", migrated)
        return migrated

    except Exception as e:
        log.error("migration_failed source=moa_jsonl err=%s", e)
        return 0


def run_full_migration() -> dict:
    """
    Run full migration from all legacy systems.

    Returns:
        Dict with migration counts per source
    """
    try:
        from ..config import get_settings
        settings = get_settings()
        data_dir = Path(settings.data_dir)
    except Exception:
        data_dir = Path("data")

    log.info("starting_full_migration data_dir=%s", data_dir)

    conn = init_database()
    results = {}

    # Migrate primary feedback
    primary_db = data_dir / "feedback" / "alert_performance.db"
    results['alert_performance'] = migrate_alert_performance(primary_db, conn)

    # Migrate breakout feedback (may be in various locations)
    for db_name in ["catalyst_bot.db", "breakout_feedback.db", "alerts.db"]:
        breakout_db = data_dir / db_name
        count = migrate_alert_outcomes(breakout_db, conn)
        if count > 0:
            results[f'alert_outcomes_{db_name}'] = count

    # Migrate MOA JSONL
    moa_file = data_dir / "moa" / "outcomes.jsonl"
    results['moa_jsonl'] = migrate_moa_jsonl(moa_file, conn)

    total = sum(results.values())
    log.info("full_migration_complete total=%d details=%s", total, results)

    return results
```

### 3. CLI Migration Command

**File:** `src/catalyst_bot/feedback/migrate_cli.py`

```python
#!/usr/bin/env python3
"""
CLI tool for running feedback data migration.

Usage:
    python -m catalyst_bot.feedback.migrate_cli
    python -m catalyst_bot.feedback.migrate_cli --dry-run
"""

import argparse
import sys

from .migration import run_full_migration


def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy feedback data to unified system"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes"
    )

    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN - No changes will be made")
        print("Would migrate from:")
        print("  - data/feedback/alert_performance.db")
        print("  - data/catalyst_bot.db (alert_outcomes table)")
        print("  - data/moa/outcomes.jsonl")
        return 0

    print("Starting migration...")
    results = run_full_migration()

    print("\nMigration Results:")
    for source, count in results.items():
        print(f"  {source}: {count} records")

    total = sum(results.values())
    print(f"\nTotal: {total} records migrated")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## Coding Tickets

### Phase A: Create Unified System

#### Ticket A.1: Create Unified Database Module
```
Title: Create unified_database.py with new schema
Priority: Critical
Estimate: 1 hour

Files to Create:
- src/catalyst_bot/feedback/unified_database.py

Tasks:
1. Define TIMEFRAMES constant
2. Define WIN_THRESHOLD, LOSS_THRESHOLD constants
3. Implement get_db_path() function
4. Implement init_database() with full schema
5. Implement calculate_outcome() function

Acceptance Criteria:
- [ ] Database creates successfully
- [ ] All timeframe columns exist
- [ ] Indexes created for common queries
- [ ] calculate_outcome() returns correct results
```

#### Ticket A.2: Create Unified Feedback API
```
Title: Create unified_feedback.py with UnifiedFeedback class
Priority: Critical
Estimate: 2 hours

Files to Create:
- src/catalyst_bot/feedback/unified_feedback.py

Tasks:
1. Implement singleton pattern
2. Implement record_alert()
3. Implement update_price() with outcome calculation
4. Implement _update_momentum_score()
5. Implement _update_final_outcome()
6. Implement get_category_stats()
7. Implement get_ticker_stats()
8. Implement get_pending_updates()

Acceptance Criteria:
- [ ] All methods work correctly
- [ ] Thread-safe singleton
- [ ] Graceful error handling
- [ ] Debug logging for all operations
```

#### Ticket A.3: Update Package __init__.py
```
Title: Update feedback package exports
Priority: High
Estimate: 15 minutes

File: src/catalyst_bot/feedback/__init__.py

Tasks:
1. Export UnifiedFeedback
2. Export helper functions
3. Keep legacy imports for compatibility

Acceptance Criteria:
- [ ] from catalyst_bot.feedback import UnifiedFeedback works
- [ ] Legacy imports still work
```

### Phase B: Migrate Breakout Feedback

#### Ticket B.1: Update breakout_feedback.py
```
Title: Delegate breakout_feedback.py to UnifiedFeedback
Priority: High
Estimate: 45 minutes

File: src/catalyst_bot/breakout_feedback.py

Tasks:
1. Import UnifiedFeedback
2. Update BreakoutFeedback class to delegate
3. Keep external API unchanged
4. Add 30m to TRACKING_INTERVALS

Acceptance Criteria:
- [ ] Existing callers work without changes
- [ ] Data stored in unified database
- [ ] No duplicate storage
```

### Phase C: Migrate MOA Tracking

#### Ticket C.1: Update moa_price_tracker.py
```
Title: Add UnifiedFeedback integration to MOA
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/moa_price_tracker.py

Tasks:
1. Import UnifiedFeedback with fallback
2. Update track_rejected_item() to record to unified
3. Update update_moa_price() to update unified
4. Keep JSONL backup for backward compatibility

Acceptance Criteria:
- [ ] MOA data recorded in unified database
- [ ] JSONL still written for compatibility
- [ ] No crashes if unified unavailable
```

### Phase D: Migration and Cleanup

#### Ticket D.1: Create Migration Script
```
Title: Create data migration utilities
Priority: High
Estimate: 1 hour

Files to Create:
- src/catalyst_bot/feedback/migration.py
- src/catalyst_bot/feedback/migrate_cli.py

Tasks:
1. Implement migrate_alert_performance()
2. Implement migrate_alert_outcomes()
3. Implement migrate_moa_jsonl()
4. Implement run_full_migration()
5. Create CLI tool

Acceptance Criteria:
- [ ] All legacy data can be migrated
- [ ] Migration is idempotent
- [ ] CLI provides clear output
- [ ] Dry-run mode works
```

#### Ticket D.2: Add Deprecation Warnings
```
Title: Add deprecation notices to legacy modules
Priority: Medium
Estimate: 15 minutes

Files to Modify:
- src/catalyst_bot/feedback/database.py (add warning)

Tasks:
1. Add module-level deprecation notice
2. Add __getattr__ for FeedbackDatabase warning

Acceptance Criteria:
- [ ] Warning shown when importing legacy class
- [ ] Legacy code still works
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_unified_feedback.py
import pytest
import tempfile
from pathlib import Path

def test_unified_feedback_creation():
    """Test database initialization."""
    from catalyst_bot.feedback import UnifiedFeedback
    fb = UnifiedFeedback()
    assert fb.conn is not None

def test_record_and_update_alert():
    """Test full alert lifecycle."""
    from catalyst_bot.feedback import UnifiedFeedback
    fb = UnifiedFeedback()

    # Record
    alert_id = fb.record_alert(
        ticker="AAPL",
        category="earnings",
        initial_price=150.00,
        headline="Apple beats earnings",
    )
    assert alert_id is not None

    # Update 30m price
    result = fb.update_price(alert_id, "30m", 153.50)
    assert result['change_pct'] == pytest.approx(2.33, rel=0.01)
    assert result['outcome'] == 'win'

def test_category_stats():
    """Test category statistics query."""
    from catalyst_bot.feedback import UnifiedFeedback
    fb = UnifiedFeedback()

    # Record some test alerts
    for i in range(5):
        alert_id = fb.record_alert(
            ticker=f"TEST{i}",
            category="test_category",
            initial_price=100.00,
        )
        fb.update_price(alert_id, "30m", 103.00)  # All wins

    stats = fb.get_category_stats("test_category", days=1)
    assert stats['has_data'] == True
    assert stats['win_rate'] == 100.0

def test_calculate_outcome():
    """Test outcome calculation."""
    from catalyst_bot.feedback.unified_database import calculate_outcome

    # Win case
    outcome, score = calculate_outcome(5.0)
    assert outcome == "win"
    assert score > 0.5

    # Loss case
    outcome, score = calculate_outcome(-5.0)
    assert outcome == "loss"
    assert score < -0.5

    # Neutral case
    outcome, score = calculate_outcome(0.5)
    assert outcome == "neutral"
```

### 2. Integration Test

```bash
# Test unified feedback in isolation
python -c "
from catalyst_bot.feedback import UnifiedFeedback
fb = UnifiedFeedback()

# Record test alert
alert_id = fb.record_alert('TEST', 'earnings', 100.0, 'Test headline')
print(f'Recorded: {alert_id}')

# Update prices
for tf in ['15m', '30m', '1h']:
    result = fb.update_price(alert_id, tf, 102.5)
    print(f'{tf}: {result}')

# Get stats
stats = fb.get_category_stats('earnings')
print(f'Stats: {stats}')
"
```

### 3. Migration Test

```bash
# Dry run
python -m catalyst_bot.feedback.migrate_cli --dry-run

# Full migration
python -m catalyst_bot.feedback.migrate_cli

# Verify data
sqlite3 data/feedback/alert_feedback.db "SELECT COUNT(*) as total, source FROM alert_feedback GROUP BY source"
```

### 4. Backward Compatibility Test

```bash
# Test that existing code still works
python -c "
from catalyst_bot.breakout_feedback import BreakoutFeedback, record_breakout_alert

# Old API should still work
fb = BreakoutFeedback()
alert_id = fb.record_alert('COMPAT', 'test', 'Test', 100.0)
print(f'Legacy API works: {alert_id}')
"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_UNIFIED_FEEDBACK` | `1` | Enable unified feedback system |
| `FEEDBACK_DB_PATH` | `data/feedback/alert_feedback.db` | Path to unified database |

---

## Summary

This implementation:

1. **Consolidates Three Systems** into one unified database
2. **Adds Missing Features** - 30m tracking, 7d tracking, consistent scoring
3. **Maintains Compatibility** - Existing code works during migration
4. **Provides Migration Tools** - CLI for migrating historical data
5. **Reduces Maintenance** - One codebase instead of three

**Implementation Order:**
1. Phase A: Create unified system (2-3 hours)
2. Phase B: Migrate breakout feedback (45 min)
3. Phase C: Migrate MOA tracking (30 min)
4. Phase D: Run migration, add deprecation (1 hour)

**Expected Impact:**
- Single source of truth for all alert feedback
- Consistent outcome definitions across all alerts
- Easier querying and analysis
- Foundation for ML model training on feedback data

---

**End of Implementation Guide**
