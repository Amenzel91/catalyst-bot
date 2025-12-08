# Histogram Distributions Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** MEDIUM
**Impact:** MEDIUM | **Effort:** LOW | **ROI:** MEDIUM
**Estimated Implementation Time:** 2-3 hours
**Target Files:** `src/catalyst_bot/analytics/distributions.py`, `src/catalyst_bot/feedback/database.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Implementation Strategy](#implementation-strategy)
4. [Phase A: Core Distribution Module](#phase-a-core-distribution-module)
5. [Phase B: Integration Points](#phase-b-integration-points)
6. [Phase C: Reporting & Visualization](#phase-c-reporting--visualization)
7. [Coding Tickets](#coding-tickets)
8. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

The Catalyst-Bot tracks numerous metrics but **stores only averages and totals**, losing critical distribution information:

| Metric | What's Stored | What's Lost |
|--------|---------------|-------------|
| Price returns | `avg_return_15m`, `avg_return_1h`, etc. | Full distribution, outliers, skewness |
| Sentiment scores | Single combined score | Per-source breakdown, consensus |
| Hold durations | Raw `hold_duration_seconds` | Distribution by exit type |
| Volume changes | Raw volumes | Volume surprise distribution |
| Outcome scores | Single score per alert | Score distribution by category |

### Why Distributions Matter

```
Average Return: +5%

But which scenario is it?

Scenario A (Consistent):     Scenario B (Risky):
├── +4% ████████            ├── -20% ████
├── +5% █████████           ├── +0%  ██
├── +6% ████████            ├── +35% █████████████
└── Mean: 5%                └── Mean: 5%

Same average, VERY different risk profiles!
```

**Key Benefits:**
- **Risk Management** - Understand tail risks, not just averages
- **Signal Quality** - Which catalyst types are most consistent?
- **Parameter Tuning** - What hold duration actually works?
- **Anomaly Detection** - When metrics deviate from typical distribution

---

## Current State Analysis

### 1. MOA Price Tracker - Only Averages

**File:** `src/catalyst_bot/moa_price_tracker.py`
**Lines:** 728-733

```python
# Current: Only averages calculated
avg_returns = {}
for tf, returns in returns_by_timeframe.items():
    if returns:
        avg_returns[f"avg_return_{tf}"] = round(sum(returns) / len(returns), 2)
# LOST: Full distribution, median, percentiles, outliers
```

### 2. Classification Scoring - Single Combined Score

**File:** `src/catalyst_bot/classify.py`
**Lines:** 356-357

```python
# 10 sentiment sources aggregated to single value
temp_sentiment = 0.0
if sentiment_sources:
    temp_sum = sum(sentiment_sources.values())
    temp_sentiment = temp_sum / len(sentiment_sources) if temp_sum else 0.0
# LOST: Per-source distribution, consensus vs divergence
```

### 3. Outcome Scoring - No Bucketing

**File:** `src/catalyst_bot/feedback/outcome_scorer.py`
**Lines:** 49-81

```python
score = 0.0
if price_change > 5.0:  # >5%
    score += 0.7
elif price_change > 3.0:  # >3%
    score += 0.4
# LOST: Distribution of scores, calibration data
```

### 4. Backtesting Reports - Only Averages Per Catalyst

**File:** `src/catalyst_bot/backtesting/reports.py`
**Lines:** 106-123

```python
# Only average per catalyst
for catalyst, perf in metrics["catalyst_performance"].items():
    lines.append(
        f"| {catalyst} | {perf['total_trades']} | {perf['win_rate']*100:.1f}% | "
        f"{perf['avg_return']:.2f}% | ..."
    )
# LOST: Return distribution per catalyst type
```

### 5. Position Manager - Duration Not Analyzed

**File:** `src/catalyst_bot/portfolio/position_manager.py`
**Line:** 49

```python
hold_duration_seconds INTEGER NOT NULL,
# STORED but never analyzed by distribution
```

---

## Implementation Strategy

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTION TRACKING                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ Price Returns   │    │ Sentiment Scores│    │ Hold Times  │ │
│  │ by Timeframe    │    │ by Source       │    │ by Exit     │ │
│  └────────┬────────┘    └────────┬────────┘    └──────┬──────┘ │
│           │                      │                     │        │
│           └──────────────────────┼─────────────────────┘        │
│                                  ▼                              │
│                    ┌─────────────────────────┐                  │
│                    │   DistributionTracker   │                  │
│                    │   (analytics/distrib.)  │                  │
│                    └─────────────┬───────────┘                  │
│                                  │                              │
│              ┌───────────────────┼───────────────────┐          │
│              ▼                   ▼                   ▼          │
│     ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│     │ SQLite Storage │  │ Admin Reports  │  │ Prometheus     │ │
│     │ (distributions)│  │ (histograms)   │  │ (if enabled)   │ │
│     └────────────────┘  └────────────────┘  └────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Bucket Schemes

| Metric Type | Buckets |
|-------------|---------|
| Price Returns (%) | `[-20, -10, -5, -2, 0, 2, 5, 10, 25, 50, 100, ∞]` |
| Sentiment Scores | `[-1.0, -0.6, -0.3, 0, 0.3, 0.6, 1.0]` |
| Hold Duration (min) | `[1, 5, 15, 30, 60, 240, 480, 1440, ∞]` |
| Volume Multiplier | `[0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, ∞]` |
| Outcome Scores | `[-1.0, -0.5, -0.2, 0, 0.2, 0.5, 0.7, 1.0]` |

---

## Phase A: Core Distribution Module

### File Structure

```
src/catalyst_bot/
├── analytics/
│   ├── __init__.py
│   └── distributions.py      # NEW: Core distribution tracking
```

### File: `src/catalyst_bot/analytics/__init__.py`

```python
"""
Catalyst-Bot Analytics Package.

Provides statistical analysis and distribution tracking.
"""

from .distributions import (
    DistributionTracker,
    Histogram,
    PRICE_RETURN_BUCKETS,
    SENTIMENT_BUCKETS,
    HOLD_DURATION_BUCKETS,
    VOLUME_BUCKETS,
    OUTCOME_SCORE_BUCKETS,
)

__all__ = [
    'DistributionTracker',
    'Histogram',
    'PRICE_RETURN_BUCKETS',
    'SENTIMENT_BUCKETS',
    'HOLD_DURATION_BUCKETS',
    'VOLUME_BUCKETS',
    'OUTCOME_SCORE_BUCKETS',
]
```

### File: `src/catalyst_bot/analytics/distributions.py`

```python
"""
Distribution tracking and histogram analysis for Catalyst-Bot.

Provides statistical distribution tracking for:
- Price returns by timeframe
- Sentiment scores by source
- Hold durations by exit reason
- Volume changes
- Outcome scores by category

Reference: docs/implementation/HISTOGRAM_DISTRIBUTIONS.md
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("distributions")


# =============================================================================
# Bucket Definitions
# =============================================================================

# Price return buckets (percentage)
PRICE_RETURN_BUCKETS = [-20, -10, -5, -2, 0, 2, 5, 10, 25, 50, 100]

# Sentiment score buckets (-1 to +1)
SENTIMENT_BUCKETS = [-1.0, -0.6, -0.3, 0, 0.3, 0.6, 1.0]

# Hold duration buckets (minutes)
HOLD_DURATION_BUCKETS = [1, 5, 15, 30, 60, 240, 480, 1440]  # up to 1 day

# Volume multiplier buckets (vs average)
VOLUME_BUCKETS = [0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0]

# Outcome score buckets
OUTCOME_SCORE_BUCKETS = [-1.0, -0.5, -0.2, 0, 0.2, 0.5, 0.7, 1.0]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Histogram:
    """
    Represents a histogram distribution.

    Attributes:
        buckets: List of bucket boundaries
        counts: Dict mapping bucket labels to counts
        total: Total number of observations
        stats: Computed statistics (mean, median, std, percentiles)
    """
    buckets: List[float]
    counts: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    stats: Dict[str, float] = field(default_factory=dict)

    def add_value(self, value: float) -> str:
        """
        Add a value to the histogram.

        Returns:
            The bucket label the value was placed in
        """
        bucket_label = self._get_bucket_label(value)
        self.counts[bucket_label] = self.counts.get(bucket_label, 0) + 1
        self.total += 1
        return bucket_label

    def _get_bucket_label(self, value: float) -> str:
        """Get the bucket label for a value."""
        for i, threshold in enumerate(self.buckets):
            if value < threshold:
                if i == 0:
                    return f"<{threshold}"
                return f"{self.buckets[i-1]}_{threshold}"
        return f">{self.buckets[-1]}"

    def compute_stats(self, values: List[float]) -> None:
        """Compute statistics from raw values."""
        if not values:
            return

        self.stats = {
            'mean': round(statistics.mean(values), 3),
            'median': round(statistics.median(values), 3),
            'std': round(statistics.stdev(values), 3) if len(values) > 1 else 0,
            'min': round(min(values), 3),
            'max': round(max(values), 3),
            'p25': round(statistics.quantiles(values, n=4)[0], 3) if len(values) >= 4 else None,
            'p75': round(statistics.quantiles(values, n=4)[2], 3) if len(values) >= 4 else None,
            'p90': round(statistics.quantiles(values, n=10)[8], 3) if len(values) >= 10 else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            'buckets': self.buckets,
            'counts': self.counts,
            'total': self.total,
            'stats': self.stats,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Histogram':
        """Create Histogram from dictionary."""
        hist = cls(buckets=data['buckets'])
        hist.counts = data.get('counts', {})
        hist.total = data.get('total', 0)
        hist.stats = data.get('stats', {})
        return hist

    def get_percentile_bucket(self, percentile: int) -> Optional[str]:
        """Get the bucket containing a given percentile."""
        if self.total == 0:
            return None

        target_count = (percentile / 100) * self.total
        cumulative = 0

        for bucket_label in self._sorted_bucket_labels():
            cumulative += self.counts.get(bucket_label, 0)
            if cumulative >= target_count:
                return bucket_label

        return None

    def _sorted_bucket_labels(self) -> List[str]:
        """Get bucket labels in sorted order."""
        labels = []
        labels.append(f"<{self.buckets[0]}")
        for i in range(len(self.buckets) - 1):
            labels.append(f"{self.buckets[i]}_{self.buckets[i+1]}")
        labels.append(f">{self.buckets[-1]}")
        return labels


# =============================================================================
# Distribution Tracker
# =============================================================================

class DistributionTracker:
    """
    Tracks distributions for various metrics.

    Thread-safe singleton with SQLite persistence.

    Usage:
        tracker = DistributionTracker()
        tracker.record_price_return("AAPL", "earnings", "30m", 5.2)
        tracker.record_sentiment_score("vader", 0.65)
        tracker.record_hold_duration("take_profit", 45.5)

        stats = tracker.get_distribution("price_return", category="earnings", timeframe="30m")
    """

    _instance: Optional['DistributionTracker'] = None
    _conn: Optional[sqlite3.Connection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._conn = cls._init_database()
        return cls._instance

    @classmethod
    def _init_database(cls) -> sqlite3.Connection:
        """Initialize SQLite database for distribution storage."""
        try:
            from ..config import get_settings
            settings = get_settings()
            data_dir = Path(settings.data_dir)
        except Exception:
            data_dir = Path("data")

        db_path = data_dir / "analytics" / "distributions.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # Main distribution tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS distributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_type TEXT NOT NULL,
                category TEXT,
                timeframe TEXT,
                date TEXT NOT NULL,
                histogram_json TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(metric_type, category, timeframe, date)
            )
        """)

        # Raw values table for detailed analysis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS distribution_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_type TEXT NOT NULL,
                category TEXT,
                timeframe TEXT,
                value REAL NOT NULL,
                ticker TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dist_lookup
            ON distributions(metric_type, category, timeframe, date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_values_lookup
            ON distribution_values(metric_type, category, timeframe, recorded_at)
        """)

        conn.commit()
        log.info("distribution_database_initialized path=%s", db_path)

        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = self._init_database()
        return self._conn

    # =========================================================================
    # Recording Methods
    # =========================================================================

    def record_price_return(
        self,
        ticker: str,
        category: str,
        timeframe: str,
        return_pct: float,
    ) -> None:
        """
        Record a price return observation.

        Args:
            ticker: Stock symbol
            category: Alert category (earnings, sec_filing, breakout, etc.)
            timeframe: Time interval (15m, 30m, 1h, 4h, 1d, 7d)
            return_pct: Return percentage (e.g., 5.2 for +5.2%)

        Integration Points:
            - moa_price_tracker.py: After calculating returns
            - feedback/collector.py: After price updates
        """
        self._record_value(
            metric_type="price_return",
            category=category,
            timeframe=timeframe,
            value=return_pct,
            ticker=ticker,
            buckets=PRICE_RETURN_BUCKETS,
        )

    def record_sentiment_score(
        self,
        source: str,
        score: float,
        ticker: Optional[str] = None,
    ) -> None:
        """
        Record a sentiment score observation.

        Args:
            source: Sentiment source (vader, ml, llm, trends, etc.)
            score: Sentiment score (-1 to +1)
            ticker: Optional stock symbol

        Integration Points:
            - classify.py: When aggregating sentiment sources
        """
        self._record_value(
            metric_type="sentiment",
            category=source,
            timeframe=None,
            value=score,
            ticker=ticker,
            buckets=SENTIMENT_BUCKETS,
        )

    def record_hold_duration(
        self,
        exit_reason: str,
        duration_minutes: float,
        ticker: Optional[str] = None,
    ) -> None:
        """
        Record a position hold duration.

        Args:
            exit_reason: Why position closed (stop_loss, take_profit, manual, timeout)
            duration_minutes: How long position was held
            ticker: Optional stock symbol

        Integration Points:
            - trading_engine.py: When closing positions
            - position_manager.py: On position close
        """
        self._record_value(
            metric_type="hold_duration",
            category=exit_reason,
            timeframe=None,
            value=duration_minutes,
            ticker=ticker,
            buckets=HOLD_DURATION_BUCKETS,
        )

    def record_volume_change(
        self,
        category: str,
        volume_multiplier: float,
        ticker: Optional[str] = None,
    ) -> None:
        """
        Record a volume change observation.

        Args:
            category: Alert category
            volume_multiplier: Volume vs average (e.g., 2.5 for 2.5x average)
            ticker: Optional stock symbol

        Integration Points:
            - classify.py: When checking volume
            - breakout detection
        """
        self._record_value(
            metric_type="volume_change",
            category=category,
            timeframe=None,
            value=volume_multiplier,
            ticker=ticker,
            buckets=VOLUME_BUCKETS,
        )

    def record_outcome_score(
        self,
        category: str,
        score: float,
        ticker: Optional[str] = None,
    ) -> None:
        """
        Record an outcome score observation.

        Args:
            category: Alert category
            score: Outcome score (-1 to +1)
            ticker: Optional stock symbol

        Integration Points:
            - feedback/outcome_scorer.py: After scoring
        """
        self._record_value(
            metric_type="outcome_score",
            category=category,
            timeframe=None,
            value=score,
            ticker=ticker,
            buckets=OUTCOME_SCORE_BUCKETS,
        )

    def _record_value(
        self,
        metric_type: str,
        category: Optional[str],
        timeframe: Optional[str],
        value: float,
        ticker: Optional[str],
        buckets: List[float],
    ) -> None:
        """Internal method to record a value."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            cursor = self.conn.cursor()

            # Store raw value
            cursor.execute("""
                INSERT INTO distribution_values
                (metric_type, category, timeframe, value, ticker)
                VALUES (?, ?, ?, ?, ?)
            """, (metric_type, category, timeframe, value, ticker))

            # Update daily histogram
            cursor.execute("""
                SELECT histogram_json, sample_count
                FROM distributions
                WHERE metric_type = ? AND category = ? AND timeframe = ? AND date = ?
            """, (metric_type, category or '', timeframe or '', today))

            row = cursor.fetchone()

            if row:
                hist = Histogram.from_dict(json.loads(row['histogram_json']))
            else:
                hist = Histogram(buckets=buckets)

            hist.add_value(value)

            cursor.execute("""
                INSERT OR REPLACE INTO distributions
                (metric_type, category, timeframe, date, histogram_json, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (metric_type, category or '', timeframe or '', today,
                  json.dumps(hist.to_dict()), hist.total))

            self.conn.commit()

        except Exception as e:
            log.error("record_value_failed type=%s err=%s", metric_type, e)

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_distribution(
        self,
        metric_type: str,
        category: Optional[str] = None,
        timeframe: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get distribution statistics for a metric.

        Args:
            metric_type: price_return, sentiment, hold_duration, etc.
            category: Optional filter by category
            timeframe: Optional filter by timeframe
            days: Lookback period

        Returns:
            Dict with histogram, stats, and sample info
        """
        try:
            cursor = self.conn.cursor()

            # Get raw values for stats calculation
            query = """
                SELECT value
                FROM distribution_values
                WHERE metric_type = ?
                  AND recorded_at > datetime('now', ?)
            """
            params = [metric_type, f'-{days} days']

            if category:
                query += " AND category = ?"
                params.append(category)
            if timeframe:
                query += " AND timeframe = ?"
                params.append(timeframe)

            cursor.execute(query, params)
            values = [row[0] for row in cursor.fetchall()]

            if not values:
                return {
                    'has_data': False,
                    'sample_size': 0,
                }

            # Build histogram from values
            buckets = self._get_buckets_for_type(metric_type)
            hist = Histogram(buckets=buckets)
            for v in values:
                hist.add_value(v)
            hist.compute_stats(values)

            return {
                'has_data': True,
                'sample_size': len(values),
                'histogram': hist.counts,
                'stats': hist.stats,
                'buckets': buckets,
            }

        except Exception as e:
            log.error("get_distribution_failed type=%s err=%s", metric_type, e)
            return {'has_data': False, 'error': str(e)}

    def get_comparison(
        self,
        metric_type: str,
        categories: List[str],
        timeframe: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare distributions across categories.

        Args:
            metric_type: Metric to compare
            categories: List of categories to compare
            timeframe: Optional timeframe filter
            days: Lookback period

        Returns:
            Dict mapping category to distribution stats
        """
        result = {}
        for category in categories:
            result[category] = self.get_distribution(
                metric_type=metric_type,
                category=category,
                timeframe=timeframe,
                days=days,
            )
        return result

    def _get_buckets_for_type(self, metric_type: str) -> List[float]:
        """Get appropriate bucket list for a metric type."""
        bucket_map = {
            'price_return': PRICE_RETURN_BUCKETS,
            'sentiment': SENTIMENT_BUCKETS,
            'hold_duration': HOLD_DURATION_BUCKETS,
            'volume_change': VOLUME_BUCKETS,
            'outcome_score': OUTCOME_SCORE_BUCKETS,
        }
        return bucket_map.get(metric_type, PRICE_RETURN_BUCKETS)

    # =========================================================================
    # Reporting Methods
    # =========================================================================

    def get_summary_report(self, days: int = 7) -> Dict[str, Any]:
        """
        Generate summary report of all distributions.

        Returns:
            Dict with summary stats for all tracked metrics
        """
        report = {}

        for metric_type in ['price_return', 'sentiment', 'hold_duration',
                            'volume_change', 'outcome_score']:
            report[metric_type] = self.get_distribution(metric_type, days=days)

        return report

    def format_histogram_ascii(
        self,
        histogram: Dict[str, int],
        width: int = 30,
    ) -> str:
        """
        Format histogram as ASCII bar chart for Discord/terminal.

        Args:
            histogram: Dict of bucket -> count
            width: Max bar width in characters

        Returns:
            ASCII histogram string
        """
        if not histogram:
            return "No data"

        max_count = max(histogram.values()) if histogram else 1
        lines = []

        for bucket, count in sorted(histogram.items()):
            bar_len = int((count / max_count) * width) if max_count > 0 else 0
            bar = "█" * bar_len
            lines.append(f"{bucket:>12} | {bar} ({count})")

        return "\n".join(lines)
```

---

## Phase B: Integration Points

### 1. MOA Price Tracker Integration

**File:** `src/catalyst_bot/moa_price_tracker.py`
**Location:** After Line 733 (after avg_returns calculation)

```python
# ADD after calculating avg_returns:

# Record to distribution tracker
try:
    from .analytics import DistributionTracker
    tracker = DistributionTracker()

    for tf, returns in returns_by_timeframe.items():
        for ret in returns:
            tracker.record_price_return(
                ticker=ticker,
                category=category,
                timeframe=tf,
                return_pct=ret,
            )
except Exception:
    pass  # Never crash on distribution tracking
```

### 2. Classification Scoring Integration

**File:** `src/catalyst_bot/classify.py`
**Location:** After Line 357 (after sentiment aggregation)

```python
# ADD after sentiment source aggregation:

# Record sentiment scores to distribution tracker
if os.getenv("FEATURE_DISTRIBUTIONS", "1").strip().lower() in ("1", "true", "yes"):
    try:
        from .analytics import DistributionTracker
        tracker = DistributionTracker()

        for source, score in sentiment_sources.items():
            tracker.record_sentiment_score(
                source=source,
                score=score,
                ticker=ticker,
            )
    except Exception:
        pass
```

### 3. Outcome Scorer Integration

**File:** `src/catalyst_bot/feedback/outcome_scorer.py`
**Location:** After Line 81 (after score calculation)

```python
# ADD after calculating final score:

# Record outcome score to distribution tracker
try:
    from ..analytics import DistributionTracker
    tracker = DistributionTracker()
    tracker.record_outcome_score(
        category=category,
        score=score,
        ticker=ticker,
    )
except Exception:
    pass
```

### 4. Trading Engine - Hold Duration

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Location:** In `_handle_close_signal()` after position close (around Line 636)

```python
# ADD after closing position:

# Record hold duration to distribution tracker
try:
    from ..analytics import DistributionTracker
    tracker = DistributionTracker()

    duration_minutes = (datetime.now(timezone.utc) - position.entry_time).total_seconds() / 60
    tracker.record_hold_duration(
        exit_reason=exit_reason,
        duration_minutes=duration_minutes,
        ticker=position.ticker,
    )
except Exception:
    pass
```

---

## Phase C: Reporting & Visualization

### 1. Admin Report Integration

**File:** `src/catalyst_bot/admin_controls.py`
**Location:** In `build_admin_embed()` (around Line 1005)

```python
# ADD new field for distribution summary:

def _get_distribution_summary() -> str:
    """Generate distribution summary for admin embed."""
    try:
        from .analytics import DistributionTracker
        tracker = DistributionTracker()

        report = tracker.get_summary_report(days=7)
        lines = []

        # Price return summary
        if report.get('price_return', {}).get('has_data'):
            stats = report['price_return']['stats']
            lines.append(f"📈 **Returns (7d)**")
            lines.append(f"├─ Mean: {stats.get('mean', 0):+.2f}%")
            lines.append(f"├─ Median: {stats.get('median', 0):+.2f}%")
            lines.append(f"└─ Std Dev: {stats.get('std', 0):.2f}%")

        # Sentiment summary
        if report.get('sentiment', {}).get('has_data'):
            stats = report['sentiment']['stats']
            lines.append(f"\n💭 **Sentiment (7d)**")
            lines.append(f"├─ Mean: {stats.get('mean', 0):+.2f}")
            lines.append(f"└─ Range: [{stats.get('min', 0):.2f}, {stats.get('max', 0):.2f}]")

        # Hold duration summary
        if report.get('hold_duration', {}).get('has_data'):
            stats = report['hold_duration']['stats']
            lines.append(f"\n⏱️ **Hold Time (7d)**")
            lines.append(f"├─ Median: {stats.get('median', 0):.0f} min")
            lines.append(f"└─ P90: {stats.get('p90', 0):.0f} min")

        return "\n".join(lines) if lines else "No distribution data"

    except Exception as e:
        return f"Distribution error: {e}"


# In build_admin_embed(), add field:
embed["fields"].append({
    "name": "📊 Distributions",
    "value": _get_distribution_summary(),
    "inline": False,
})
```

### 2. Discord Histogram Command (Optional)

```python
# Could add to admin_controls.py for /histogram command

def format_histogram_for_discord(
    metric_type: str,
    category: Optional[str] = None,
    days: int = 7,
) -> str:
    """Format histogram for Discord embed."""
    from .analytics import DistributionTracker
    tracker = DistributionTracker()

    dist = tracker.get_distribution(metric_type, category=category, days=days)

    if not dist.get('has_data'):
        return "No data available"

    return tracker.format_histogram_ascii(dist['histogram'], width=20)
```

---

## Coding Tickets

### Phase A: Core Module

#### Ticket A.1: Create Analytics Package
```
Title: Create analytics package with distribution tracking
Priority: High
Estimate: 1.5 hours

Files to Create:
- src/catalyst_bot/analytics/__init__.py
- src/catalyst_bot/analytics/distributions.py

Tasks:
1. Define bucket constants for all metric types
2. Implement Histogram dataclass
3. Implement DistributionTracker singleton
4. Create SQLite schema for persistence
5. Implement all record_* methods
6. Implement get_distribution() and get_comparison()

Acceptance Criteria:
- [ ] Database initializes correctly
- [ ] Values can be recorded and retrieved
- [ ] Histogram computation is accurate
- [ ] Statistics (mean, median, percentiles) are correct
```

### Phase B: Integration

#### Ticket B.1: Integrate with MOA Price Tracker
```
Title: Add distribution tracking to MOA returns
Priority: High
Estimate: 20 minutes

File: src/catalyst_bot/moa_price_tracker.py
Location: After Line 733

Tasks:
1. Import DistributionTracker with fallback
2. Record each return to distribution tracker
3. Wrap in try/except for safety

Acceptance Criteria:
- [ ] Returns recorded to distribution database
- [ ] No crashes if analytics module unavailable
```

#### Ticket B.2: Integrate with Classification
```
Title: Add sentiment score distribution tracking
Priority: High
Estimate: 20 minutes

File: src/catalyst_bot/classify.py
Location: After Line 357

Tasks:
1. Import DistributionTracker with fallback
2. Record each sentiment source score
3. Make feature-flagged (FEATURE_DISTRIBUTIONS)

Acceptance Criteria:
- [ ] Sentiment scores tracked by source
- [ ] Can be disabled via environment variable
```

#### Ticket B.3: Integrate with Outcome Scorer
```
Title: Add outcome score distribution tracking
Priority: Medium
Estimate: 15 minutes

File: src/catalyst_bot/feedback/outcome_scorer.py
Location: After Line 81

Tasks:
1. Import DistributionTracker
2. Record outcome scores by category

Acceptance Criteria:
- [ ] Outcome scores tracked by category
```

#### Ticket B.4: Integrate with Trading Engine
```
Title: Add hold duration distribution tracking
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/trading/trading_engine.py
Location: In _handle_close_signal()

Tasks:
1. Import DistributionTracker
2. Calculate hold duration in minutes
3. Record by exit reason

Acceptance Criteria:
- [ ] Hold durations tracked by exit reason
```

### Phase C: Reporting

#### Ticket C.1: Add to Admin Report
```
Title: Display distribution summary in admin embed
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/admin_controls.py

Tasks:
1. Create _get_distribution_summary() helper
2. Add "Distributions" field to admin embed
3. Format key stats (mean, median, percentiles)

Acceptance Criteria:
- [ ] Admin embed shows distribution summary
- [ ] Graceful fallback if no data
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_distributions.py
import pytest

def test_histogram_bucketing():
    """Test histogram bucket assignment."""
    from catalyst_bot.analytics.distributions import Histogram, PRICE_RETURN_BUCKETS

    hist = Histogram(buckets=PRICE_RETURN_BUCKETS)

    # Test various values
    assert hist.add_value(-25) == "<-20"
    assert hist.add_value(-5) == "-10_-5"
    assert hist.add_value(0) == "-2_0"
    assert hist.add_value(7) == "5_10"
    assert hist.add_value(150) == ">100"

def test_histogram_stats():
    """Test statistics computation."""
    from catalyst_bot.analytics.distributions import Histogram, PRICE_RETURN_BUCKETS

    hist = Histogram(buckets=PRICE_RETURN_BUCKETS)
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    for v in values:
        hist.add_value(v)
    hist.compute_stats(values)

    assert hist.stats['mean'] == 5.5
    assert hist.stats['median'] == 5.5
    assert hist.total == 10

def test_distribution_tracker():
    """Test distribution tracker singleton."""
    from catalyst_bot.analytics import DistributionTracker

    tracker = DistributionTracker()

    # Record some values
    tracker.record_price_return("AAPL", "earnings", "30m", 5.2)
    tracker.record_price_return("AAPL", "earnings", "30m", -2.1)
    tracker.record_price_return("AAPL", "earnings", "30m", 8.5)

    # Query distribution
    dist = tracker.get_distribution("price_return", category="earnings", timeframe="30m", days=1)

    assert dist['has_data'] == True
    assert dist['sample_size'] == 3
```

### 2. Integration Test

```bash
# Record some test values
python -c "
from catalyst_bot.analytics import DistributionTracker

tracker = DistributionTracker()

# Simulate price returns
for ret in [2.5, -1.2, 5.8, 0.3, -3.2, 12.1, 1.5, -0.5]:
    tracker.record_price_return('TEST', 'test', '30m', ret)

# Query distribution
dist = tracker.get_distribution('price_return', category='test', timeframe='30m', days=1)
print('Distribution:', dist)

# ASCII histogram
print(tracker.format_histogram_ascii(dist['histogram']))
"
```

### 3. Verify Database

```bash
# Check database structure
sqlite3 data/analytics/distributions.db ".schema"

# Check recorded values
sqlite3 data/analytics/distributions.db "SELECT metric_type, category, COUNT(*) FROM distribution_values GROUP BY metric_type, category"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_DISTRIBUTIONS` | `1` | Enable distribution tracking |

---

## Summary

This implementation provides:

1. **Statistical Insight** - Full distributions instead of just averages
2. **Risk Understanding** - Identify outliers, skewness, tail risks
3. **Per-Category Analysis** - Compare distributions across catalyst types
4. **Lightweight** - SQLite storage, no external dependencies
5. **Feature-Flagged** - Can be disabled if needed

**Implementation Order:**
1. Phase A: Create analytics package (1.5 hours)
2. Phase B: Wire into existing modules (1 hour)
3. Phase C: Add to admin reports (30 min)

**Expected Impact:**
- Better risk-adjusted decision making
- Identify which categories have consistent vs volatile returns
- Optimize hold times based on actual distribution

---

**End of Implementation Guide**
