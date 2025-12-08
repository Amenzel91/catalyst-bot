# SEC LLM Outcome Tracking Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** MEDIUM
**Impact:** MEDIUM | **Effort:** LOW | **ROI:** MEDIUM
**Estimated Implementation Time:** 2-3 hours
**Target Files:** `src/catalyst_bot/feedback/sec_outcome_tracker.py`, `src/catalyst_bot/sec_llm_analyzer.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Implementation Strategy](#implementation-strategy)
4. [Phase A: SEC Outcome Tracker Module](#phase-a-sec-outcome-tracker-module)
5. [Phase B: Integration Points](#phase-b-integration-points)
6. [Phase C: Calibration Reports](#phase-c-calibration-reports)
7. [Coding Tickets](#coding-tickets)
8. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

SEC LLM summarization is **active and generating predictions**, but outcomes are **never tracked**:

| LLM Output | Status | Outcome Tracking | Status |
|------------|--------|------------------|--------|
| `llm_sentiment` | ✅ Generated | Sentiment vs price direction | ❌ Not tracked |
| `llm_confidence` | ✅ Generated | Confidence calibration | ❌ Not tracked |
| `catalysts[]` | ✅ Generated | Catalyst type accuracy | ❌ Not tracked |
| `risk_level` | ✅ Generated | Risk prediction vs outcome | ❌ Not tracked |

### What's Generated But Never Validated

**File:** `src/catalyst_bot/sec_llm_analyzer.py:160-170`

```python
result = {
    "llm_sentiment": float,        # -1 to +1, parsed from LLM JSON
    "llm_confidence": float,       # 0 to 1, parsed from LLM JSON
    "catalysts": list[str],        # ["dilution", "earnings", ...]
    "summary": str,                # LLM summary
    "risk_level": str,             # "low", "medium", "high"
}
# ALL GENERATED BUT NEVER COMPARED TO ACTUAL PRICE OUTCOMES!
```

### Why This Matters

```
LLM Predicts: BULLISH (+0.8 sentiment, 0.9 confidence)
              Catalysts: ["FDA approval"]

Actual Outcome: Stock drops -15% in 1 day

WITHOUT TRACKING:
  └─ We keep making the same wrong predictions
  └─ LLM prompt never improves
  └─ Confidence scores are meaningless

WITH TRACKING:
  └─ We see FDA predictions are only 45% accurate
  └─ We can tune prompts for FDA filings
  └─ Confidence calibration reveals overconfidence
```

---

## Current State Analysis

### 1. SEC Enrichment Pipeline

**File:** `src/catalyst_bot/sec_llm_analyzer.py`

| Function | Lines | Output | Tracked? |
|----------|-------|--------|----------|
| `analyze_sec_filing()` | 55-198 | sentiment, confidence, catalysts | ❌ No |
| `extract_keywords_from_document()` | 354-577 | keywords, sentiment, confidence | ❌ No |
| `batch_extract_keywords_from_documents()` | 585-752 | Batch results | ❌ No |

### 2. SEC Alert Sending

**File:** `src/catalyst_bot/sec_filing_alerts.py:563-710`

Data sent to Discord:
- ✅ Priority tier
- ✅ Filing metrics (revenue, EPS)
- ✅ SEC sentiment score
- ✅ LLM summary
- ❌ `llm_confidence` NOT sent
- ❌ No tracking ID for outcome correlation

### 3. Current Feedback Loop (Incomplete)

**File:** `src/catalyst_bot/breakout_feedback.py:95-164`

Current `register_alert_for_tracking()` signature:
```python
def register_alert_for_tracking(
    ticker: str,
    entry_price: float,
    entry_volume: Optional[float],
    timestamp: datetime,
    keywords: List[str],
    confidence: float,  # Generic confidence, NOT llm_confidence
    alert_id: Optional[str] = None,
) -> str
```

**Missing Fields:**
- `source` (was it SEC or news?)
- `llm_sentiment` (SEC sentiment prediction)
- `llm_confidence` (prediction confidence)
- `filing_type` (8-K, 424B5, etc.)
- `catalyst_types` (from LLM analysis)

---

## Implementation Strategy

### SEC Outcome Tracking Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   SEC LLM OUTCOME TRACKING                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │ SEC Filing      │                                            │
│  │ Arrives         │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ sec_llm_analyzer│───▶│ LLM Predictions │                     │
│  │ (existing)      │    │ sentiment, conf │                     │
│  └─────────────────┘    └────────┬────────┘                     │
│                                  │                              │
│                                  ▼                              │
│                         ┌─────────────────┐                     │
│                         │ sec_outcomes    │◀── NEW TABLE        │
│                         │ (tracking DB)   │                     │
│                         └────────┬────────┘                     │
│                                  │                              │
│              ┌───────────────────┼───────────────────┐          │
│              ▼                   ▼                   ▼          │
│       ┌────────────┐     ┌────────────┐     ┌────────────┐     │
│       │ Price at   │     │ Price at   │     │ Calibration│     │
│       │ 15m/30m/1h │     │ 1d/7d      │     │ Report     │     │
│       └────────────┘     └────────────┘     └────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### What We're Tracking

| Prediction | Outcome Comparison |
|------------|-------------------|
| `llm_sentiment > 0` (bullish) | Did price go up at 1d/7d? |
| `llm_confidence = 0.9` | When conf=0.9, are we 90% accurate? |
| `catalysts = ["dilution"]` | Do dilution predictions match outcomes? |
| `risk_level = "high"` | Do high-risk filings have higher volatility? |

---

## Phase A: SEC Outcome Tracker Module

### File Structure

```
src/catalyst_bot/feedback/
├── __init__.py
├── database.py              # Existing
├── unified_feedback.py      # From Proposal #2
└── sec_outcome_tracker.py   # NEW
```

### File: `src/catalyst_bot/feedback/sec_outcome_tracker.py`

```python
"""
SEC LLM Outcome Tracking for Catalyst-Bot.

Tracks SEC filing LLM predictions against actual price outcomes:
- Sentiment prediction accuracy
- Confidence calibration
- Catalyst type effectiveness
- Filing type performance

Reference: docs/implementation/SEC_LLM_OUTCOME_TRACKING.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("sec_outcome_tracker")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SECPrediction:
    """LLM prediction for an SEC filing."""
    filing_id: str
    ticker: str
    filing_type: str  # 8-K, 424B5, SC13D, etc.
    llm_sentiment: float  # -1 to +1
    llm_confidence: float  # 0 to 1
    catalysts: List[str]  # ["dilution", "earnings", ...]
    risk_level: str  # low, medium, high
    summary: str
    filing_time: datetime
    initial_price: float


@dataclass
class CalibrationStats:
    """Confidence calibration statistics."""
    confidence_bucket: str  # "0.7-0.8", "0.8-0.9", "0.9-1.0"
    total_predictions: int
    correct_predictions: int
    actual_accuracy: float
    expected_accuracy: float  # Bucket midpoint
    calibration_error: float  # |actual - expected|


# =============================================================================
# SEC Outcome Tracker
# =============================================================================

class SECOutcomeTracker:
    """
    Tracks SEC LLM predictions vs actual outcomes.

    Usage:
        tracker = SECOutcomeTracker()

        # When SEC alert sent:
        tracker.record_prediction(
            filing_id="8K-AAPL-2025-001",
            ticker="AAPL",
            filing_type="8-K",
            llm_sentiment=0.7,
            llm_confidence=0.85,
            catalysts=["earnings_beat"],
            risk_level="medium",
            summary="Strong Q4 results...",
            initial_price=150.50,
        )

        # Later, update with outcomes:
        tracker.update_outcome("8K-AAPL-2025-001", "1d", current_price=158.00)

        # Generate calibration report:
        report = tracker.get_calibration_report()
    """

    _instance: Optional['SECOutcomeTracker'] = None
    _conn: Optional[sqlite3.Connection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._conn = cls._init_database()
        return cls._instance

    @classmethod
    def _init_database(cls) -> sqlite3.Connection:
        """Initialize SEC outcome tracking database."""
        try:
            from ..config import get_settings
            settings = get_settings()
            data_dir = Path(settings.data_dir)
        except Exception:
            data_dir = Path("data")

        db_path = data_dir / "feedback" / "sec_outcomes.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # SEC predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sec_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id TEXT UNIQUE NOT NULL,
                ticker TEXT NOT NULL,
                filing_type TEXT NOT NULL,
                llm_sentiment REAL NOT NULL,
                llm_confidence REAL NOT NULL,
                catalysts TEXT,
                risk_level TEXT,
                summary TEXT,
                filing_time TIMESTAMP NOT NULL,
                initial_price REAL NOT NULL,

                -- Prices at various intervals
                price_15m REAL,
                price_30m REAL,
                price_1h REAL,
                price_4h REAL,
                price_1d REAL,
                price_7d REAL,

                -- Price changes
                change_15m REAL,
                change_30m REAL,
                change_1h REAL,
                change_4h REAL,
                change_1d REAL,
                change_7d REAL,

                -- Prediction accuracy
                direction_correct_1d BOOLEAN,
                direction_correct_7d BOOLEAN,
                prediction_score REAL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sec_ticker
            ON sec_predictions(ticker)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sec_filing_type
            ON sec_predictions(filing_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sec_confidence
            ON sec_predictions(llm_confidence)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sec_filing_time
            ON sec_predictions(filing_time)
        """)

        conn.commit()
        log.info("sec_outcome_database_initialized path=%s", db_path)

        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = self._init_database()
        return self._conn

    # =========================================================================
    # Recording
    # =========================================================================

    def record_prediction(
        self,
        filing_id: str,
        ticker: str,
        filing_type: str,
        llm_sentiment: float,
        llm_confidence: float,
        initial_price: float,
        catalysts: Optional[List[str]] = None,
        risk_level: Optional[str] = None,
        summary: Optional[str] = None,
        filing_time: Optional[datetime] = None,
    ) -> str:
        """
        Record an SEC LLM prediction for tracking.

        Args:
            filing_id: Unique filing identifier
            ticker: Stock symbol
            filing_type: SEC form type (8-K, 424B5, etc.)
            llm_sentiment: LLM sentiment prediction (-1 to +1)
            llm_confidence: LLM confidence (0 to 1)
            initial_price: Price at time of filing
            catalysts: List of predicted catalyst types
            risk_level: Predicted risk level
            summary: LLM summary text
            filing_time: Time of filing (default: now)

        Returns:
            filing_id for tracking

        Integration Points:
            - sec_filing_alerts.py: After sending SEC alert
            - runner.py: After SEC enrichment
        """
        import json

        if filing_time is None:
            filing_time = datetime.now(timezone.utc)

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sec_predictions
                (filing_id, ticker, filing_type, llm_sentiment, llm_confidence,
                 catalysts, risk_level, summary, filing_time, initial_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filing_id, ticker.upper(), filing_type,
                llm_sentiment, llm_confidence,
                json.dumps(catalysts) if catalysts else None,
                risk_level, summary,
                filing_time.isoformat(), initial_price,
            ))
            self.conn.commit()

            log.debug(
                "sec_prediction_recorded id=%s ticker=%s sentiment=%.2f confidence=%.2f",
                filing_id, ticker, llm_sentiment, llm_confidence
            )
            return filing_id

        except Exception as e:
            log.error("record_prediction_failed id=%s err=%s", filing_id, e)
            raise

    def update_outcome(
        self,
        filing_id: str,
        timeframe: str,
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Update price outcome for a timeframe.

        Args:
            filing_id: Filing identifier
            timeframe: Timeframe (15m, 30m, 1h, 4h, 1d, 7d)
            current_price: Current price

        Returns:
            Dict with change_pct, direction_correct

        Integration Points:
            - feedback/collector.py: Scheduled price checks
        """
        valid_timeframes = ['15m', '30m', '1h', '4h', '1d', '7d']
        if timeframe not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        try:
            cursor = self.conn.cursor()

            # Get initial data
            cursor.execute("""
                SELECT initial_price, llm_sentiment
                FROM sec_predictions WHERE filing_id = ?
            """, (filing_id,))
            row = cursor.fetchone()

            if not row:
                return {'error': 'Filing not found'}

            initial_price = row['initial_price']
            llm_sentiment = row['llm_sentiment']

            if initial_price <= 0:
                return {'error': 'Invalid initial price'}

            # Calculate change
            change_pct = ((current_price - initial_price) / initial_price) * 100

            # Check if direction matches prediction
            direction_correct = None
            if timeframe in ['1d', '7d']:
                # Bullish prediction (sentiment > 0) should see price up
                # Bearish prediction (sentiment < 0) should see price down
                if abs(llm_sentiment) > 0.1:  # Only for non-neutral predictions
                    predicted_up = llm_sentiment > 0
                    actual_up = change_pct > 0
                    direction_correct = predicted_up == actual_up

            # Update database
            update_fields = [
                f"price_{timeframe} = ?",
                f"change_{timeframe} = ?",
                "updated_at = CURRENT_TIMESTAMP",
            ]

            params = [current_price, change_pct]

            if timeframe == '1d':
                update_fields.append("direction_correct_1d = ?")
                params.append(direction_correct)
            elif timeframe == '7d':
                update_fields.append("direction_correct_7d = ?")
                params.append(direction_correct)

            params.append(filing_id)

            cursor.execute(f"""
                UPDATE sec_predictions
                SET {', '.join(update_fields)}
                WHERE filing_id = ?
            """, params)

            # Update prediction score if we have 1d outcome
            if timeframe == '1d':
                self._update_prediction_score(filing_id)

            self.conn.commit()

            log.debug(
                "sec_outcome_updated id=%s tf=%s change=%.2f%% correct=%s",
                filing_id, timeframe, change_pct, direction_correct
            )

            return {
                'change_pct': round(change_pct, 2),
                'direction_correct': direction_correct,
            }

        except Exception as e:
            log.error("update_outcome_failed id=%s err=%s", filing_id, e)
            raise

    def _update_prediction_score(self, filing_id: str) -> None:
        """Calculate prediction score based on outcomes."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT llm_sentiment, llm_confidence, change_1d, direction_correct_1d
            FROM sec_predictions WHERE filing_id = ?
        """, (filing_id,))
        row = cursor.fetchone()

        if not row or row['change_1d'] is None:
            return

        # Score formula:
        # - Base: direction_correct gives +1, incorrect gives -1
        # - Weighted by confidence (more confident = bigger penalty/reward)
        # - Magnitude bonus if direction correct and large move

        direction_correct = row['direction_correct_1d']
        confidence = row['llm_confidence'] or 0.5
        change_1d = row['change_1d']

        if direction_correct is None:
            score = 0  # Neutral prediction
        elif direction_correct:
            # Correct direction: reward scaled by confidence
            base_score = 0.5 + (confidence * 0.5)
            # Bonus for large moves (>5%)
            magnitude_bonus = min(abs(change_1d) / 20, 0.3)
            score = base_score + magnitude_bonus
        else:
            # Wrong direction: penalty scaled by confidence
            score = -0.5 - (confidence * 0.5)

        score = max(min(score, 1.0), -1.0)

        cursor.execute("""
            UPDATE sec_predictions SET prediction_score = ? WHERE filing_id = ?
        """, (round(score, 3), filing_id))

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_sentiment_accuracy(
        self,
        days: int = 30,
        filing_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get accuracy of sentiment predictions.

        Args:
            days: Lookback period
            filing_type: Filter by filing type (optional)

        Returns:
            Dict with accuracy stats by sentiment range
        """
        try:
            cursor = self.conn.cursor()

            query = """
                SELECT
                    CASE
                        WHEN llm_sentiment >= 0.5 THEN 'strong_bullish'
                        WHEN llm_sentiment >= 0.1 THEN 'mild_bullish'
                        WHEN llm_sentiment <= -0.5 THEN 'strong_bearish'
                        WHEN llm_sentiment <= -0.1 THEN 'mild_bearish'
                        ELSE 'neutral'
                    END as sentiment_bucket,
                    COUNT(*) as total,
                    SUM(CASE WHEN direction_correct_1d = 1 THEN 1 ELSE 0 END) as correct,
                    AVG(change_1d) as avg_change
                FROM sec_predictions
                WHERE filing_time > datetime('now', ?)
                  AND direction_correct_1d IS NOT NULL
            """
            params = [f'-{days} days']

            if filing_type:
                query += " AND filing_type = ?"
                params.append(filing_type)

            query += " GROUP BY sentiment_bucket ORDER BY sentiment_bucket"

            cursor.execute(query, params)

            results = {}
            for row in cursor.fetchall():
                bucket = row['sentiment_bucket']
                total = row['total']
                correct = row['correct'] or 0
                results[bucket] = {
                    'total': total,
                    'correct': correct,
                    'accuracy': round((correct / total * 100) if total > 0 else 0, 1),
                    'avg_change': round(row['avg_change'] or 0, 2),
                }

            return results

        except Exception as e:
            log.error("sentiment_accuracy_failed err=%s", e)
            return {}

    def get_confidence_calibration(
        self,
        days: int = 90,
    ) -> List[CalibrationStats]:
        """
        Get confidence calibration statistics.

        Compares predicted confidence to actual accuracy.

        Args:
            days: Lookback period

        Returns:
            List of CalibrationStats by confidence bucket
        """
        # Define confidence buckets
        buckets = [
            (0.5, 0.6, "0.5-0.6"),
            (0.6, 0.7, "0.6-0.7"),
            (0.7, 0.8, "0.7-0.8"),
            (0.8, 0.9, "0.8-0.9"),
            (0.9, 1.0, "0.9-1.0"),
        ]

        try:
            cursor = self.conn.cursor()

            results = []
            for min_conf, max_conf, label in buckets:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN direction_correct_1d = 1 THEN 1 ELSE 0 END) as correct
                    FROM sec_predictions
                    WHERE filing_time > datetime('now', ?)
                      AND llm_confidence >= ? AND llm_confidence < ?
                      AND direction_correct_1d IS NOT NULL
                """, (f'-{days} days', min_conf, max_conf))

                row = cursor.fetchone()
                total = row['total'] or 0
                correct = row['correct'] or 0

                if total > 0:
                    actual_accuracy = correct / total
                    expected_accuracy = (min_conf + max_conf) / 2
                    calibration_error = abs(actual_accuracy - expected_accuracy)

                    results.append(CalibrationStats(
                        confidence_bucket=label,
                        total_predictions=total,
                        correct_predictions=correct,
                        actual_accuracy=round(actual_accuracy * 100, 1),
                        expected_accuracy=round(expected_accuracy * 100, 1),
                        calibration_error=round(calibration_error * 100, 1),
                    ))

            return results

        except Exception as e:
            log.error("confidence_calibration_failed err=%s", e)
            return []

    def get_filing_type_accuracy(
        self,
        days: int = 90,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get accuracy breakdown by SEC filing type.

        Returns:
            Dict mapping filing_type to accuracy stats
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    filing_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN direction_correct_1d = 1 THEN 1 ELSE 0 END) as correct,
                    AVG(change_1d) as avg_change,
                    AVG(prediction_score) as avg_score
                FROM sec_predictions
                WHERE filing_time > datetime('now', ?)
                  AND direction_correct_1d IS NOT NULL
                GROUP BY filing_type
                ORDER BY total DESC
            """, (f'-{days} days',))

            results = {}
            for row in cursor.fetchall():
                filing_type = row['filing_type']
                total = row['total']
                correct = row['correct'] or 0

                results[filing_type] = {
                    'total': total,
                    'correct': correct,
                    'accuracy': round((correct / total * 100) if total > 0 else 0, 1),
                    'avg_change': round(row['avg_change'] or 0, 2),
                    'avg_score': round(row['avg_score'] or 0, 2),
                }

            return results

        except Exception as e:
            log.error("filing_type_accuracy_failed err=%s", e)
            return {}

    def get_catalyst_effectiveness(
        self,
        days: int = 90,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get effectiveness by predicted catalyst type.

        Returns:
            Dict mapping catalyst type to accuracy stats
        """
        import json

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT catalysts, direction_correct_1d, change_1d
                FROM sec_predictions
                WHERE filing_time > datetime('now', ?)
                  AND catalysts IS NOT NULL
                  AND direction_correct_1d IS NOT NULL
            """, (f'-{days} days',))

            # Aggregate by catalyst type
            catalyst_stats = {}
            for row in cursor.fetchall():
                try:
                    catalysts = json.loads(row['catalysts'])
                except:
                    continue

                for catalyst in catalysts:
                    if catalyst not in catalyst_stats:
                        catalyst_stats[catalyst] = {
                            'total': 0, 'correct': 0, 'total_change': 0
                        }

                    catalyst_stats[catalyst]['total'] += 1
                    catalyst_stats[catalyst]['total_change'] += row['change_1d'] or 0
                    if row['direction_correct_1d']:
                        catalyst_stats[catalyst]['correct'] += 1

            # Calculate final stats
            results = {}
            for catalyst, stats in catalyst_stats.items():
                if stats['total'] > 0:
                    results[catalyst] = {
                        'total': stats['total'],
                        'correct': stats['correct'],
                        'accuracy': round(stats['correct'] / stats['total'] * 100, 1),
                        'avg_change': round(stats['total_change'] / stats['total'], 2),
                    }

            return dict(sorted(results.items(), key=lambda x: -x[1]['total']))

        except Exception as e:
            log.error("catalyst_effectiveness_failed err=%s", e)
            return {}

    # =========================================================================
    # Reporting
    # =========================================================================

    def get_calibration_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive calibration report.

        Returns:
            Dict with all calibration metrics
        """
        return {
            'period_days': days,
            'sentiment_accuracy': self.get_sentiment_accuracy(days=days),
            'confidence_calibration': [
                {
                    'bucket': s.confidence_bucket,
                    'predictions': s.total_predictions,
                    'actual_accuracy': s.actual_accuracy,
                    'expected_accuracy': s.expected_accuracy,
                    'calibration_error': s.calibration_error,
                }
                for s in self.get_confidence_calibration(days=days)
            ],
            'filing_type_accuracy': self.get_filing_type_accuracy(days=days),
            'catalyst_effectiveness': self.get_catalyst_effectiveness(days=days),
        }

    def format_for_discord(self, days: int = 30) -> str:
        """
        Format calibration report for Discord embed.

        Returns:
            Formatted string for Discord
        """
        sentiment = self.get_sentiment_accuracy(days=days)
        filing_types = self.get_filing_type_accuracy(days=days)

        lines = [f"🔬 **SEC LLM Calibration ({days}d)**\n"]

        # Sentiment accuracy
        if sentiment:
            lines.append("**By Sentiment:**")
            for bucket, stats in sentiment.items():
                emoji = "🟢" if stats['accuracy'] >= 60 else "🔴" if stats['accuracy'] < 40 else "🟡"
                lines.append(f"{emoji} {bucket}: {stats['accuracy']}% ({stats['total']} filings)")

        # Filing type accuracy
        if filing_types:
            lines.append("\n**By Filing Type:**")
            for ftype, stats in list(filing_types.items())[:5]:  # Top 5
                emoji = "🟢" if stats['accuracy'] >= 60 else "🔴" if stats['accuracy'] < 40 else "🟡"
                lines.append(f"{emoji} {ftype}: {stats['accuracy']}% ({stats['total']})")

        return "\n".join(lines)


# =============================================================================
# Module-Level Helper
# =============================================================================

def get_sec_outcome_tracker() -> SECOutcomeTracker:
    """Get SEC outcome tracker instance."""
    return SECOutcomeTracker()
```

---

## Phase B: Integration Points

### 1. Record Prediction on SEC Alert

**File:** `src/catalyst_bot/sec_filing_alerts.py`
**Location:** In `send_sec_filing_alert()` after successful send (around Line 700)

```python
# ADD after sending SEC alert to Discord:

# Record prediction for outcome tracking
if os.getenv("FEATURE_SEC_OUTCOME_TRACKING", "1").strip().lower() in ("1", "true", "yes"):
    try:
        from .feedback.sec_outcome_tracker import get_sec_outcome_tracker
        tracker = get_sec_outcome_tracker()

        tracker.record_prediction(
            filing_id=f"{filing_type}-{ticker}-{filing_id}",
            ticker=ticker,
            filing_type=filing_type,
            llm_sentiment=enrichment.get('llm_sentiment', 0),
            llm_confidence=enrichment.get('llm_confidence', 0.5),
            initial_price=current_price,
            catalysts=enrichment.get('catalysts', []),
            risk_level=enrichment.get('risk_level'),
            summary=enrichment.get('summary'),
        )
    except Exception as e:
        log.debug("sec_outcome_tracking_failed err=%s", e)
```

### 2. Pass LLM Fields Through Pipeline

**File:** `src/catalyst_bot/sec_filing_adapter.py`
**Location:** In `filing_to_newsitem()` (around Line 49-180)

```python
# MODIFY filing_to_newsitem() to pass through LLM fields:

def filing_to_newsitem(
    filing_section: dict,
    llm_summary: Optional[str] = None,
    llm_sentiment: Optional[float] = None,      # NEW
    llm_confidence: Optional[float] = None,     # NEW
    catalysts: Optional[List[str]] = None,      # NEW
    risk_level: Optional[str] = None,           # NEW
    **kwargs,
) -> dict:
    """Convert SEC filing to NewsItem format with LLM enrichment."""

    # ... existing conversion code ...

    # Add LLM fields to result
    result['llm_sentiment'] = llm_sentiment
    result['llm_confidence'] = llm_confidence
    result['catalysts'] = catalysts
    result['risk_level'] = risk_level

    return result
```

### 3. Schedule Outcome Updates

**File:** `src/catalyst_bot/feedback/collector.py` (or create new)
**Location:** Add SEC outcome polling

```python
# ADD to feedback collector or create new function:

async def update_sec_outcomes():
    """Update price outcomes for tracked SEC filings."""
    from .sec_outcome_tracker import get_sec_outcome_tracker
    from ..market import get_current_price

    tracker = get_sec_outcome_tracker()

    # Get pending SEC filings needing updates
    for timeframe in ['15m', '30m', '1h', '4h', '1d', '7d']:
        pending = tracker.get_pending_updates(timeframe)

        for filing in pending:
            try:
                price = await get_current_price(filing['ticker'])
                if price:
                    tracker.update_outcome(
                        filing_id=filing['filing_id'],
                        timeframe=timeframe,
                        current_price=price,
                    )
            except Exception as e:
                log.debug("sec_outcome_update_failed filing=%s err=%s",
                         filing['filing_id'], e)
```

---

## Phase C: Calibration Reports

### 1. Admin Report Integration

**File:** `src/catalyst_bot/admin_controls.py`
**Location:** In `build_admin_embed()`

```python
# ADD SEC calibration section:

def _get_sec_calibration_summary() -> str:
    """Get SEC LLM calibration for admin embed."""
    try:
        from .feedback.sec_outcome_tracker import get_sec_outcome_tracker
        tracker = get_sec_outcome_tracker()
        return tracker.format_for_discord(days=7)
    except Exception as e:
        return f"SEC calibration error: {e}"


# In build_admin_embed():
embed["fields"].append({
    "name": "🔬 SEC LLM Calibration",
    "value": _get_sec_calibration_summary(),
    "inline": False,
})
```

### 2. Weekly Calibration Report

```python
# Could add to weekly_performance.py or create separate report:

def generate_sec_calibration_report(days: int = 30) -> str:
    """Generate weekly SEC LLM calibration report."""
    from .feedback.sec_outcome_tracker import get_sec_outcome_tracker

    tracker = get_sec_outcome_tracker()
    report = tracker.get_calibration_report(days=days)

    lines = [
        f"# SEC LLM Calibration Report ({days} days)",
        "",
        "## Confidence Calibration",
        "| Confidence | Expected | Actual | Error |",
        "|------------|----------|--------|-------|",
    ]

    for cal in report['confidence_calibration']:
        lines.append(
            f"| {cal['bucket']} | {cal['expected_accuracy']}% | "
            f"{cal['actual_accuracy']}% | {cal['calibration_error']}% |"
        )

    lines.extend([
        "",
        "## Filing Type Performance",
        "| Type | Total | Accuracy | Avg Change |",
        "|------|-------|----------|------------|",
    ])

    for ftype, stats in report['filing_type_accuracy'].items():
        lines.append(
            f"| {ftype} | {stats['total']} | {stats['accuracy']}% | "
            f"{stats['avg_change']:+.2f}% |"
        )

    return "\n".join(lines)
```

---

## Coding Tickets

### Phase A: SEC Outcome Tracker

#### Ticket A.1: Create SEC Outcome Tracker Module
```
Title: Create sec_outcome_tracker.py with tracking and analytics
Priority: High
Estimate: 2 hours

Files to Create:
- src/catalyst_bot/feedback/sec_outcome_tracker.py

Tasks:
1. Implement SECPrediction and CalibrationStats dataclasses
2. Implement SECOutcomeTracker singleton with database
3. Implement record_prediction()
4. Implement update_outcome() with direction checking
5. Implement get_sentiment_accuracy()
6. Implement get_confidence_calibration()
7. Implement get_filing_type_accuracy()
8. Implement get_catalyst_effectiveness()
9. Implement format_for_discord()

Acceptance Criteria:
- [ ] Database initializes correctly
- [ ] Predictions recorded with all fields
- [ ] Outcomes update direction_correct flags
- [ ] Calibration queries return accurate stats
```

### Phase B: Integration

#### Ticket B.1: Record Predictions on SEC Alert
```
Title: Add prediction recording to sec_filing_alerts.py
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/sec_filing_alerts.py
Location: After Line 700

Tasks:
1. Import SEC outcome tracker
2. Record prediction after successful alert send
3. Make feature-flagged (FEATURE_SEC_OUTCOME_TRACKING)

Acceptance Criteria:
- [ ] Predictions recorded for all SEC alerts
- [ ] LLM fields passed correctly
- [ ] Graceful handling if tracker unavailable
```

#### Ticket B.2: Pass LLM Fields Through Pipeline
```
Title: Add LLM fields to SEC filing adapter
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/sec_filing_adapter.py
Location: filing_to_newsitem()

Tasks:
1. Add llm_sentiment, llm_confidence, catalysts, risk_level parameters
2. Include in returned dict

Acceptance Criteria:
- [ ] All LLM fields available in downstream processing
```

#### Ticket B.3: Schedule Outcome Updates
```
Title: Add SEC outcome polling to feedback collector
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/feedback/collector.py (or new)

Tasks:
1. Create update_sec_outcomes() function
2. Get pending filings needing price updates
3. Update each timeframe

Acceptance Criteria:
- [ ] Prices updated at 15m, 30m, 1h, 4h, 1d, 7d
- [ ] direction_correct calculated at 1d/7d
```

### Phase C: Reporting

#### Ticket C.1: Add to Admin Report
```
Title: Display SEC calibration in admin embed
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/admin_controls.py

Tasks:
1. Create _get_sec_calibration_summary() helper
2. Add "SEC LLM Calibration" field to embed

Acceptance Criteria:
- [ ] Admin shows sentiment accuracy by bucket
- [ ] Shows filing type performance
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_sec_outcome_tracker.py
import pytest

def test_record_prediction():
    """Test recording SEC prediction."""
    from catalyst_bot.feedback.sec_outcome_tracker import SECOutcomeTracker

    tracker = SECOutcomeTracker()
    filing_id = tracker.record_prediction(
        filing_id="TEST-8K-001",
        ticker="AAPL",
        filing_type="8-K",
        llm_sentiment=0.7,
        llm_confidence=0.85,
        initial_price=150.00,
        catalysts=["earnings"],
    )

    assert filing_id == "TEST-8K-001"

def test_update_outcome():
    """Test outcome update with direction check."""
    from catalyst_bot.feedback.sec_outcome_tracker import SECOutcomeTracker

    tracker = SECOutcomeTracker()

    # Record bullish prediction
    tracker.record_prediction(
        filing_id="TEST-8K-002",
        ticker="TSLA",
        filing_type="8-K",
        llm_sentiment=0.7,  # Bullish
        llm_confidence=0.85,
        initial_price=200.00,
    )

    # Price went up - direction correct
    result = tracker.update_outcome("TEST-8K-002", "1d", 210.00)

    assert result['change_pct'] == 5.0
    assert result['direction_correct'] == True

def test_confidence_calibration():
    """Test confidence calibration query."""
    from catalyst_bot.feedback.sec_outcome_tracker import SECOutcomeTracker

    tracker = SECOutcomeTracker()
    calibration = tracker.get_confidence_calibration(days=90)

    assert isinstance(calibration, list)
```

### 2. Integration Test

```bash
# Test SEC outcome tracking end-to-end
python -c "
from catalyst_bot.feedback.sec_outcome_tracker import get_sec_outcome_tracker

tracker = get_sec_outcome_tracker()

# Record test prediction
tracker.record_prediction(
    filing_id='TEST-8K-INTEG',
    ticker='NVDA',
    filing_type='8-K',
    llm_sentiment=0.8,
    llm_confidence=0.9,
    initial_price=500.00,
    catalysts=['earnings_beat', 'guidance_raised'],
)

# Simulate 1d outcome (price up 10%)
result = tracker.update_outcome('TEST-8K-INTEG', '1d', 550.00)
print(f'Outcome: {result}')

# Get calibration report
report = tracker.get_calibration_report(days=30)
print(f'Report: {report}')

# Discord format
print(tracker.format_for_discord(days=30))
"
```

### 3. Verify Database

```bash
sqlite3 data/feedback/sec_outcomes.db "
SELECT
    filing_type,
    COUNT(*) as total,
    SUM(CASE WHEN direction_correct_1d = 1 THEN 1 ELSE 0 END) as correct,
    ROUND(AVG(llm_confidence), 2) as avg_confidence
FROM sec_predictions
WHERE direction_correct_1d IS NOT NULL
GROUP BY filing_type
"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_SEC_OUTCOME_TRACKING` | `1` | Enable SEC outcome tracking |

---

## Summary

This implementation provides:

1. **Sentiment Validation** - Compare bullish/bearish predictions to price direction
2. **Confidence Calibration** - Is 90% confidence actually 90% accurate?
3. **Filing Type Analysis** - Which SEC forms predict best?
4. **Catalyst Effectiveness** - Which predicted catalysts are accurate?
5. **Admin Visibility** - Calibration stats in Discord reports

**Implementation Order:**
1. Phase A: Create sec_outcome_tracker.py (2 hours)
2. Phase B: Integration points (1 hour)
3. Phase C: Admin report integration (30 min)

**Expected Impact:**
- Validate LLM effectiveness on SEC filings
- Identify overconfident predictions
- Tune prompts based on accuracy data
- Potentially reduce API costs by filtering ineffective enrichment

---

**End of Implementation Guide**
