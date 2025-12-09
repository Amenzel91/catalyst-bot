# Cross-Database Correlation Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** MEDIUM
**Impact:** MEDIUM | **Effort:** HIGH | **ROI:** MEDIUM
**Estimated Implementation Time:** 4-6 hours
**Target Files:** `src/catalyst_bot/correlation/`, `src/catalyst_bot/reports/correlation_reports.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Database Inventory](#database-inventory)
3. [Correlation Opportunities](#correlation-opportunities)
4. [Implementation Strategy](#implementation-strategy)
5. [Phase A: Cross-DB Query Layer](#phase-a-cross-db-query-layer)
6. [Phase B: High-Value Correlations](#phase-b-high-value-correlations)
7. [Phase C: Reporting Integration](#phase-c-reporting-integration)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

Catalyst-Bot has **multiple databases** that operate independently:

| Database | Purpose | Join Key Available |
|----------|---------|-------------------|
| `alert_feedback.db` | Alert performance tracking | ticker, alert_id, alert_time |
| `positions.db` | Trading positions | ticker, position_id, opened_at |
| `trading.db` | Orders, fills, portfolio | ticker, order_id, position_id |
| `sec_llm_cache.db` | SEC filing analysis | ticker, filing_id |
| `ml_training.db` | Model performance | run_id, algorithm |

**No cross-database queries exist** - each system operates in isolation.

### Why Cross-Database Correlation Matters

```
CURRENT STATE (Siloed):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Alert Feedback  │    │ Trading Positions│   │ SEC Analysis    │
│  - Win rate     │    │  - P&L           │    │  - Sentiment    │
│  - Categories   │    │  - Exit reasons  │    │  - Confidence   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                      │                      │
        └──────────── NO LINKS ────────────────────────┘

QUESTIONS WE CAN'T ANSWER:
  ❌ Did alerts that triggered trades end in wins?
  ❌ Which alert categories correlate with best trade outcomes?
  ❌ Does SEC sentiment predict trade profitability?
  ❌ Which tickers get too many alerts but poor trade results?


DESIRED STATE (Correlated):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Alert Feedback  │────│ Trading Positions│────│ SEC Analysis    │
│  - Win rate     │    │  - P&L           │    │  - Sentiment    │
│  - Categories   │    │  - Exit reasons  │    │  - Confidence   │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         └───────── UNIFIED CORRELATION ───────────────┘

QUESTIONS WE CAN ANSWER:
  ✅ Alert category X has 72% trade win rate
  ✅ SEC bullish sentiment → +12% avg trade P&L
  ✅ Ticker AAPL: 40 alerts, only 30% converted to winning trades
```

### Prerequisites

This implementation **depends on**:
- ✅ **#2 Unified Feedback System** - Provides single `alert_id` across tracking
- ✅ **#4 Exit Analytics** - Provides exit reason data
- ✅ **#5 SEC LLM Outcome Tracking** - Provides sentiment validation data

---

## Database Inventory

### 1. Unified Feedback Database (From #2)
**Path:** `data/feedback/alert_feedback.db`

```sql
-- Core table for all alert tracking
CREATE TABLE alert_feedback (
    alert_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,           -- earnings, sec_filing, breakout, etc.
    source TEXT NOT NULL,             -- alert, moa_rejected, breakout
    headline TEXT,
    alert_time TIMESTAMP NOT NULL,
    initial_price REAL NOT NULL,

    -- Outcomes at each timeframe
    change_15m, change_30m, change_1h, change_4h, change_1d, change_7d REAL,
    outcome_15m, outcome_30m, outcome_1h, outcome_4h, outcome_1d, outcome_7d TEXT,
    score_15m, score_30m, score_1h, score_4h, score_1d, score_7d REAL,

    -- Aggregates
    momentum_score REAL,
    final_outcome TEXT,
    final_score REAL
);

-- Indexes: ticker, category, alert_time, source
```

### 2. Trading Positions Database
**Path:** `data/positions.db`

```sql
-- Open positions
CREATE TABLE positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side TEXT,                        -- long, short
    entry_price REAL,
    current_price REAL,
    unrealized_pnl REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    opened_at INTEGER,
    signal_score REAL,
    strategy TEXT
);

-- Closed positions (historical trades)
CREATE TABLE closed_positions (
    position_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    entry_price REAL,
    exit_price REAL,
    realized_pnl REAL,
    realized_pnl_pct REAL,
    exit_reason TEXT,                 -- stop_loss, take_profit, manual, etc.
    hold_duration_seconds INTEGER,
    opened_at INTEGER,
    closed_at INTEGER
);

-- Indexes: ticker, closed_at, exit_reason
```

### 3. Trading Execution Database
**Path:** `data/trading.db`

```sql
-- Orders
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    ticker TEXT,
    position_id TEXT,
    status TEXT,
    filled_avg_price REAL,
    signal_score REAL,
    submitted_at INTEGER
);

-- Portfolio snapshots
CREATE TABLE portfolio_snapshots (
    snapshot_date TEXT,
    daily_pnl REAL,
    daily_return_pct REAL,
    trades_today INTEGER,
    wins_today INTEGER,
    losses_today INTEGER
);

-- Performance metrics
CREATE TABLE performance_metrics (
    metric_date TEXT,
    sharpe_ratio REAL,
    max_drawdown_pct REAL,
    win_rate_30d REAL,
    profit_factor_30d REAL
);
```

### 4. SEC Outcomes Database (From #5)
**Path:** `data/feedback/sec_outcomes.db`

```sql
CREATE TABLE sec_predictions (
    filing_id TEXT PRIMARY KEY,
    ticker TEXT,
    filing_type TEXT,
    llm_sentiment REAL,
    llm_confidence REAL,
    change_1d REAL,
    direction_correct_1d BOOLEAN,
    prediction_score REAL
);
```

### Common Join Keys

| Key | Databases | Join Type |
|-----|-----------|-----------|
| `ticker` | All | Direct match |
| `alert_time ≈ opened_at` | feedback ↔ positions | Temporal (within 5-10 min) |
| `ticker + time window` | feedback ↔ sec_outcomes | Temporal correlation |
| `position_id` | positions ↔ orders | Direct FK |

---

## Correlation Opportunities

### High-Value Correlations

| # | Correlation | Query Complexity | Business Value |
|---|-------------|------------------|----------------|
| 1 | Alert → Trade Outcome | Medium | **HIGH** - Did alerts that triggered trades win? |
| 2 | SEC Sentiment → Price | Medium | HIGH - Does SEC analysis predict outcomes? |
| 3 | Category → Trade Performance | Low | HIGH - Which alert types trade best? |
| 4 | Ticker Bias Analysis | Low | MEDIUM - Are we over-alerting certain tickers? |
| 5 | Exit Reason → Alert Category | Medium | MEDIUM - Do earnings alerts exit differently? |
| 6 | Time-of-Day Patterns | Low | LOW - When are correlations strongest? |

---

## Implementation Strategy

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  CROSS-DATABASE CORRELATION                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                 CrossDatabaseAnalytics                       ││
│  │                 (correlation/__init__.py)                    ││
│  └──────────────────────────┬──────────────────────────────────┘│
│                             │                                    │
│          ┌──────────────────┼──────────────────┐                │
│          ▼                  ▼                  ▼                │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐      │
│  │alert_feedback  │ │  positions.db  │ │ sec_outcomes   │      │
│  │     .db        │ │                │ │     .db        │      │
│  └───────┬────────┘ └───────┬────────┘ └───────┬────────┘      │
│          │                  │                  │                │
│          └──────────────────┼──────────────────┘                │
│                             │                                    │
│                  ATTACH DATABASE (SQLite)                        │
│                             │                                    │
│                             ▼                                    │
│                    ┌─────────────────┐                          │
│                    │ Correlation     │                          │
│                    │ Query Results   │                          │
│                    └────────┬────────┘                          │
│                             │                                    │
│         ┌───────────────────┼───────────────────┐               │
│         ▼                   ▼                   ▼               │
│  ┌────────────┐      ┌────────────┐      ┌────────────┐        │
│  │ Admin      │      │ Weekly     │      │ JSON       │        │
│  │ Reports    │      │ Reports    │      │ Export     │        │
│  └────────────┘      └────────────┘      └────────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### SQLite ATTACH Strategy

```python
# Attach multiple databases in a single connection
conn = sqlite3.connect(":memory:")
conn.execute("ATTACH DATABASE 'data/feedback/alert_feedback.db' AS feedback")
conn.execute("ATTACH DATABASE 'data/positions.db' AS positions")
conn.execute("ATTACH DATABASE 'data/feedback/sec_outcomes.db' AS sec")

# Now can join across databases
cursor = conn.execute("""
    SELECT
        f.category,
        f.ticker,
        p.realized_pnl
    FROM feedback.alert_feedback f
    JOIN positions.closed_positions p
        ON f.ticker = p.ticker
        AND f.alert_time BETWEEN datetime(p.opened_at, '-10 minutes')
                             AND datetime(p.opened_at, '+10 minutes')
""")
```

---

## Phase A: Cross-DB Query Layer

### File Structure

```
src/catalyst_bot/correlation/
├── __init__.py              # Package exports
├── cross_db.py              # Cross-database connection manager
└── queries.py               # Correlation queries
```

### File: `src/catalyst_bot/correlation/__init__.py`

```python
"""
Cross-Database Correlation Package for Catalyst-Bot.

Provides unified queries across multiple SQLite databases:
- Alert feedback → Trade outcomes
- SEC predictions → Price movements
- Category performance trends
- Ticker pattern analysis
"""

from .cross_db import CrossDatabaseConnection
from .queries import (
    alert_to_trade_correlation,
    sec_sentiment_impact,
    category_trade_performance,
    ticker_concentration_analysis,
    get_correlation_report,
)

__all__ = [
    'CrossDatabaseConnection',
    'alert_to_trade_correlation',
    'sec_sentiment_impact',
    'category_trade_performance',
    'ticker_concentration_analysis',
    'get_correlation_report',
]
```

### File: `src/catalyst_bot/correlation/cross_db.py`

```python
"""
Cross-database connection manager for SQLite.

Uses ATTACH DATABASE to enable joins across multiple database files.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("cross_db")


class CrossDatabaseConnection:
    """
    Manages connections across multiple SQLite databases.

    Uses SQLite ATTACH DATABASE feature to enable cross-database joins.

    Usage:
        with CrossDatabaseConnection() as conn:
            cursor = conn.execute('''
                SELECT f.category, p.realized_pnl
                FROM feedback.alert_feedback f
                JOIN positions.closed_positions p ON f.ticker = p.ticker
            ''')
            results = cursor.fetchall()
    """

    # Database paths relative to data directory
    DATABASES = {
        'feedback': 'feedback/alert_feedback.db',
        'positions': 'positions.db',
        'trading': 'trading.db',
        'sec': 'feedback/sec_outcomes.db',
        'ml': 'ml_training.db',
    }

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize cross-database connection.

        Args:
            data_dir: Base data directory (default: data/)
        """
        if data_dir is None:
            try:
                from ..config import get_settings
                settings = get_settings()
                data_dir = Path(settings.data_dir)
            except Exception:
                data_dir = Path("data")

        self.data_dir = data_dir
        self._conn: Optional[sqlite3.Connection] = None
        self._attached: List[str] = []

    def connect(self) -> sqlite3.Connection:
        """
        Create connection and attach all available databases.

        Returns:
            sqlite3.Connection with attached databases
        """
        # Use in-memory database as the main connection
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Attach each database that exists
        for alias, rel_path in self.DATABASES.items():
            db_path = self.data_dir / rel_path
            if db_path.exists():
                try:
                    self._conn.execute(
                        f"ATTACH DATABASE '{db_path}' AS {alias}"
                    )
                    self._attached.append(alias)
                    log.debug("attached_database alias=%s path=%s", alias, db_path)
                except Exception as e:
                    log.warning("attach_failed alias=%s err=%s", alias, e)

        log.info("cross_db_connected attached=%s", self._attached)
        return self._conn

    def close(self) -> None:
        """Close connection and detach databases."""
        if self._conn:
            for alias in self._attached:
                try:
                    self._conn.execute(f"DETACH DATABASE {alias}")
                except Exception:
                    pass
            self._conn.close()
            self._conn = None
            self._attached = []

    def __enter__(self) -> sqlite3.Connection:
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @property
    def available_databases(self) -> List[str]:
        """Get list of attached database aliases."""
        return self._attached.copy()


@contextmanager
def get_cross_db_connection() -> Iterator[sqlite3.Connection]:
    """
    Context manager for cross-database queries.

    Usage:
        with get_cross_db_connection() as conn:
            cursor = conn.execute("SELECT ...")
    """
    cross_db = CrossDatabaseConnection()
    try:
        yield cross_db.connect()
    finally:
        cross_db.close()
```

### File: `src/catalyst_bot/correlation/queries.py`

```python
"""
Cross-database correlation queries.

Provides pre-built queries for common correlation analyses:
- Alert → Trade outcome correlation
- SEC sentiment → Price impact
- Category → Trade performance
- Ticker concentration analysis
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .cross_db import get_cross_db_connection

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("correlation_queries")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AlertTradeCorrelation:
    """Correlation between alert and resulting trade."""
    category: str
    alerts_count: int
    trades_triggered: int
    conversion_rate: float
    winning_trades: int
    trade_win_rate: float
    avg_trade_pnl: float
    avg_alert_score: float


@dataclass
class SECSentimentImpact:
    """Impact of SEC sentiment on price outcomes."""
    sentiment_bucket: str
    filings_count: int
    correct_predictions: int
    accuracy: float
    avg_price_change: float
    avg_trade_pnl: float


@dataclass
class CategoryPerformance:
    """Performance metrics by alert category."""
    category: str
    total_alerts: int
    alert_win_rate: float
    trades_triggered: int
    trade_win_rate: float
    avg_momentum_score: float
    avg_trade_pnl: float


# =============================================================================
# Correlation Queries
# =============================================================================

def alert_to_trade_correlation(
    days: int = 30,
    min_alerts: int = 5,
) -> List[AlertTradeCorrelation]:
    """
    Correlate alerts with trade outcomes.

    Joins alert_feedback with closed_positions to measure:
    - How many alerts converted to trades
    - Win rate of trades triggered by each alert category

    Args:
        days: Lookback period
        min_alerts: Minimum alerts per category to include

    Returns:
        List of AlertTradeCorrelation by category
    """
    try:
        with get_cross_db_connection() as conn:
            # Check if required databases are attached
            cursor = conn.execute("PRAGMA database_list")
            dbs = {row[1] for row in cursor.fetchall()}

            if 'feedback' not in dbs or 'positions' not in dbs:
                log.warning("required_databases_not_attached available=%s", dbs)
                return []

            cursor = conn.execute("""
                SELECT
                    f.category,
                    COUNT(DISTINCT f.alert_id) as alerts_count,
                    COUNT(DISTINCT p.position_id) as trades_triggered,
                    COUNT(DISTINCT CASE WHEN p.realized_pnl > 0 THEN p.position_id END) as winning_trades,
                    AVG(p.realized_pnl) as avg_trade_pnl,
                    AVG(f.final_score) as avg_alert_score
                FROM feedback.alert_feedback f
                LEFT JOIN positions.closed_positions p
                    ON f.ticker = p.ticker
                    AND f.alert_time BETWEEN datetime(p.opened_at, 'unixepoch', '-10 minutes')
                                         AND datetime(p.opened_at, 'unixepoch', '+10 minutes')
                WHERE f.alert_time > datetime('now', ?)
                GROUP BY f.category
                HAVING COUNT(DISTINCT f.alert_id) >= ?
                ORDER BY alerts_count DESC
            """, (f'-{days} days', min_alerts))

            results = []
            for row in cursor.fetchall():
                alerts = row['alerts_count'] or 0
                trades = row['trades_triggered'] or 0
                wins = row['winning_trades'] or 0

                results.append(AlertTradeCorrelation(
                    category=row['category'],
                    alerts_count=alerts,
                    trades_triggered=trades,
                    conversion_rate=round((trades / alerts * 100) if alerts > 0 else 0, 1),
                    winning_trades=wins,
                    trade_win_rate=round((wins / trades * 100) if trades > 0 else 0, 1),
                    avg_trade_pnl=round(row['avg_trade_pnl'] or 0, 2),
                    avg_alert_score=round(row['avg_alert_score'] or 0, 3),
                ))

            return results

    except Exception as e:
        log.error("alert_to_trade_correlation_failed err=%s", e)
        return []


def sec_sentiment_impact(
    days: int = 90,
) -> List[SECSentimentImpact]:
    """
    Analyze SEC sentiment prediction impact on prices and trades.

    Joins sec_predictions with closed_positions to measure:
    - Does bullish SEC sentiment correlate with profitable trades?
    - How accurate are SEC sentiment predictions?

    Args:
        days: Lookback period

    Returns:
        List of SECSentimentImpact by sentiment bucket
    """
    try:
        with get_cross_db_connection() as conn:
            cursor = conn.execute("PRAGMA database_list")
            dbs = {row[1] for row in cursor.fetchall()}

            if 'sec' not in dbs:
                log.warning("sec_database_not_attached")
                return []

            # Define sentiment buckets
            cursor = conn.execute("""
                SELECT
                    CASE
                        WHEN s.llm_sentiment >= 0.5 THEN 'strong_bullish'
                        WHEN s.llm_sentiment >= 0.1 THEN 'mild_bullish'
                        WHEN s.llm_sentiment <= -0.5 THEN 'strong_bearish'
                        WHEN s.llm_sentiment <= -0.1 THEN 'mild_bearish'
                        ELSE 'neutral'
                    END as sentiment_bucket,
                    COUNT(*) as filings_count,
                    SUM(CASE WHEN s.direction_correct_1d = 1 THEN 1 ELSE 0 END) as correct,
                    AVG(s.change_1d) as avg_price_change,
                    AVG(p.realized_pnl) as avg_trade_pnl
                FROM sec.sec_predictions s
                LEFT JOIN positions.closed_positions p
                    ON s.ticker = p.ticker
                    AND s.filing_time BETWEEN datetime(p.opened_at, 'unixepoch', '-30 minutes')
                                          AND datetime(p.opened_at, 'unixepoch', '+30 minutes')
                WHERE s.filing_time > datetime('now', ?)
                  AND s.direction_correct_1d IS NOT NULL
                GROUP BY sentiment_bucket
                ORDER BY sentiment_bucket
            """, (f'-{days} days',))

            results = []
            for row in cursor.fetchall():
                count = row['filings_count'] or 0
                correct = row['correct'] or 0

                results.append(SECSentimentImpact(
                    sentiment_bucket=row['sentiment_bucket'],
                    filings_count=count,
                    correct_predictions=correct,
                    accuracy=round((correct / count * 100) if count > 0 else 0, 1),
                    avg_price_change=round(row['avg_price_change'] or 0, 2),
                    avg_trade_pnl=round(row['avg_trade_pnl'] or 0, 2),
                ))

            return results

    except Exception as e:
        log.error("sec_sentiment_impact_failed err=%s", e)
        return []


def category_trade_performance(
    days: int = 30,
) -> List[CategoryPerformance]:
    """
    Get comprehensive performance by alert category.

    Combines alert feedback metrics with trade outcomes.

    Args:
        days: Lookback period

    Returns:
        List of CategoryPerformance
    """
    try:
        with get_cross_db_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    f.category,
                    COUNT(DISTINCT f.alert_id) as total_alerts,
                    SUM(CASE WHEN f.final_outcome = 'win' THEN 1 ELSE 0 END) as alert_wins,
                    COUNT(DISTINCT p.position_id) as trades_triggered,
                    COUNT(DISTINCT CASE WHEN p.realized_pnl > 0 THEN p.position_id END) as trade_wins,
                    AVG(f.momentum_score) as avg_momentum,
                    AVG(p.realized_pnl) as avg_trade_pnl
                FROM feedback.alert_feedback f
                LEFT JOIN positions.closed_positions p
                    ON f.ticker = p.ticker
                    AND f.alert_time BETWEEN datetime(p.opened_at, 'unixepoch', '-10 minutes')
                                         AND datetime(p.opened_at, 'unixepoch', '+10 minutes')
                WHERE f.alert_time > datetime('now', ?)
                GROUP BY f.category
                ORDER BY total_alerts DESC
            """, (f'-{days} days',))

            results = []
            for row in cursor.fetchall():
                alerts = row['total_alerts'] or 0
                alert_wins = row['alert_wins'] or 0
                trades = row['trades_triggered'] or 0
                trade_wins = row['trade_wins'] or 0

                results.append(CategoryPerformance(
                    category=row['category'],
                    total_alerts=alerts,
                    alert_win_rate=round((alert_wins / alerts * 100) if alerts > 0 else 0, 1),
                    trades_triggered=trades,
                    trade_win_rate=round((trade_wins / trades * 100) if trades > 0 else 0, 1),
                    avg_momentum_score=round(row['avg_momentum'] or 0, 3),
                    avg_trade_pnl=round(row['avg_trade_pnl'] or 0, 2),
                ))

            return results

    except Exception as e:
        log.error("category_trade_performance_failed err=%s", e)
        return []


def ticker_concentration_analysis(
    days: int = 30,
    top_n: int = 20,
) -> List[Dict[str, Any]]:
    """
    Analyze ticker concentration and performance.

    Identifies:
    - Tickers with most alerts
    - Whether high-alert tickers perform well
    - Potential over-concentration

    Args:
        days: Lookback period
        top_n: Number of top tickers to return

    Returns:
        List of ticker concentration stats
    """
    try:
        with get_cross_db_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    f.ticker,
                    COUNT(DISTINCT f.alert_id) as total_alerts,
                    AVG(f.final_score) as avg_alert_score,
                    COUNT(DISTINCT p.position_id) as trades,
                    SUM(CASE WHEN p.realized_pnl > 0 THEN 1 ELSE 0 END) as trade_wins,
                    SUM(p.realized_pnl) as total_pnl,
                    AVG(p.realized_pnl) as avg_pnl
                FROM feedback.alert_feedback f
                LEFT JOIN positions.closed_positions p
                    ON f.ticker = p.ticker
                    AND f.alert_time BETWEEN datetime(p.opened_at, 'unixepoch', '-10 minutes')
                                         AND datetime(p.opened_at, 'unixepoch', '+10 minutes')
                WHERE f.alert_time > datetime('now', ?)
                GROUP BY f.ticker
                ORDER BY total_alerts DESC
                LIMIT ?
            """, (f'-{days} days', top_n))

            results = []
            for row in cursor.fetchall():
                alerts = row['total_alerts'] or 0
                trades = row['trades'] or 0
                wins = row['trade_wins'] or 0

                results.append({
                    'ticker': row['ticker'],
                    'total_alerts': alerts,
                    'avg_alert_score': round(row['avg_alert_score'] or 0, 3),
                    'trades': trades,
                    'conversion_rate': round((trades / alerts * 100) if alerts > 0 else 0, 1),
                    'trade_win_rate': round((wins / trades * 100) if trades > 0 else 0, 1),
                    'total_pnl': round(row['total_pnl'] or 0, 2),
                    'avg_pnl': round(row['avg_pnl'] or 0, 2),
                })

            return results

    except Exception as e:
        log.error("ticker_concentration_analysis_failed err=%s", e)
        return []


def get_correlation_report(days: int = 30) -> Dict[str, Any]:
    """
    Generate comprehensive correlation report.

    Returns:
        Dict with all correlation analyses
    """
    return {
        'period_days': days,
        'alert_to_trade': [
            {
                'category': c.category,
                'alerts': c.alerts_count,
                'trades': c.trades_triggered,
                'conversion_rate': c.conversion_rate,
                'trade_win_rate': c.trade_win_rate,
                'avg_pnl': c.avg_trade_pnl,
            }
            for c in alert_to_trade_correlation(days=days)
        ],
        'sec_sentiment_impact': [
            {
                'sentiment': s.sentiment_bucket,
                'filings': s.filings_count,
                'accuracy': s.accuracy,
                'avg_change': s.avg_price_change,
            }
            for s in sec_sentiment_impact(days=days)
        ],
        'category_performance': [
            {
                'category': cp.category,
                'alerts': cp.total_alerts,
                'alert_win_rate': cp.alert_win_rate,
                'trade_win_rate': cp.trade_win_rate,
            }
            for cp in category_trade_performance(days=days)
        ],
        'ticker_concentration': ticker_concentration_analysis(days=days, top_n=10),
    }
```

---

## Phase B: High-Value Correlations

### Correlation #1: Alert → Trade (Detailed)

Add to `queries.py`:

```python
def alert_trade_detailed(
    alert_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get detailed correlation for a specific alert.

    Returns:
        Dict with alert details and linked trade outcome
    """
    try:
        with get_cross_db_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    f.alert_id,
                    f.ticker,
                    f.category,
                    f.alert_time,
                    f.initial_price,
                    f.final_outcome as alert_outcome,
                    f.final_score as alert_score,
                    p.position_id,
                    p.entry_price,
                    p.exit_price,
                    p.realized_pnl,
                    p.exit_reason,
                    p.hold_duration_seconds
                FROM feedback.alert_feedback f
                LEFT JOIN positions.closed_positions p
                    ON f.ticker = p.ticker
                    AND f.alert_time BETWEEN datetime(p.opened_at, 'unixepoch', '-10 minutes')
                                         AND datetime(p.opened_at, 'unixepoch', '+10 minutes')
                WHERE f.alert_id = ?
            """, (alert_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return dict(row)

    except Exception as e:
        log.error("alert_trade_detailed_failed err=%s", e)
        return None
```

---

## Phase C: Reporting Integration

### 1. Admin Report Integration

**File:** `src/catalyst_bot/admin_controls.py`

```python
# ADD correlation section to admin embed:

def _get_correlation_summary() -> str:
    """Get correlation summary for admin embed."""
    try:
        from .correlation import category_trade_performance

        perf = category_trade_performance(days=7)

        if not perf:
            return "No correlation data"

        lines = ["📊 **Alert→Trade Correlation (7d)**"]

        for cp in perf[:5]:  # Top 5 categories
            emoji = "🟢" if cp.trade_win_rate >= 50 else "🔴"
            lines.append(
                f"{emoji} **{cp.category}**\n"
                f"├─ Alerts: {cp.total_alerts} → Trades: {cp.trades_triggered}\n"
                f"└─ Trade Win Rate: {cp.trade_win_rate}%"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"Correlation error: {e}"


# In build_admin_embed():
embed["fields"].append({
    "name": "🔗 Correlations",
    "value": _get_correlation_summary(),
    "inline": False,
})
```

### 2. Weekly Report Integration

```python
# Add to weekly report generation:

def generate_correlation_section(days: int = 7) -> str:
    """Generate correlation section for weekly report."""
    from .correlation import get_correlation_report

    report = get_correlation_report(days=days)

    lines = [
        "## Cross-Database Correlations",
        "",
        "### Alert → Trade Conversion",
        "| Category | Alerts | Trades | Conversion | Trade Win Rate |",
        "|----------|--------|--------|------------|----------------|",
    ]

    for item in report['alert_to_trade'][:10]:
        lines.append(
            f"| {item['category']} | {item['alerts']} | {item['trades']} | "
            f"{item['conversion_rate']}% | {item['trade_win_rate']}% |"
        )

    lines.extend([
        "",
        "### SEC Sentiment Impact",
        "| Sentiment | Filings | Accuracy | Avg Change |",
        "|-----------|---------|----------|------------|",
    ])

    for item in report['sec_sentiment_impact']:
        lines.append(
            f"| {item['sentiment']} | {item['filings']} | "
            f"{item['accuracy']}% | {item['avg_change']:+.2f}% |"
        )

    return "\n".join(lines)
```

---

## Coding Tickets

### Phase A: Cross-DB Query Layer

#### Ticket A.1: Create Correlation Package
```
Title: Create correlation package with cross-DB connection
Priority: High
Estimate: 2 hours

Files to Create:
- src/catalyst_bot/correlation/__init__.py
- src/catalyst_bot/correlation/cross_db.py
- src/catalyst_bot/correlation/queries.py

Tasks:
1. Implement CrossDatabaseConnection with ATTACH DATABASE
2. Implement alert_to_trade_correlation()
3. Implement sec_sentiment_impact()
4. Implement category_trade_performance()
5. Implement ticker_concentration_analysis()
6. Implement get_correlation_report()

Acceptance Criteria:
- [ ] Can attach multiple databases
- [ ] Cross-database joins work correctly
- [ ] All query functions return valid data
- [ ] Graceful handling when databases missing
```

### Phase B: High-Value Correlations

#### Ticket B.1: Alert-Trade Detailed Query
```
Title: Add detailed alert-trade correlation query
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/correlation/queries.py

Tasks:
1. Implement alert_trade_detailed()
2. Return both alert and linked trade data

Acceptance Criteria:
- [ ] Can query specific alert's trade outcome
- [ ] Returns None if alert not found
```

### Phase C: Reporting

#### Ticket C.1: Add to Admin Report
```
Title: Display correlations in admin embed
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/admin_controls.py

Tasks:
1. Create _get_correlation_summary() helper
2. Add "Correlations" field to embed

Acceptance Criteria:
- [ ] Admin shows top correlations
- [ ] Shows alert→trade conversion rates
```

#### Ticket C.2: Add to Weekly Report
```
Title: Add correlation section to weekly report
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/reports/ or weekly_performance.py

Tasks:
1. Create generate_correlation_section()
2. Include in weekly report

Acceptance Criteria:
- [ ] Weekly report shows correlation tables
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_cross_db_correlation.py
import pytest

def test_cross_db_connection():
    """Test cross-database connection."""
    from catalyst_bot.correlation import CrossDatabaseConnection

    with CrossDatabaseConnection() as conn:
        # Should have at least one database attached
        cursor = conn.execute("PRAGMA database_list")
        dbs = cursor.fetchall()
        assert len(dbs) >= 1

def test_alert_to_trade_correlation():
    """Test alert-trade correlation query."""
    from catalyst_bot.correlation import alert_to_trade_correlation

    results = alert_to_trade_correlation(days=90)

    assert isinstance(results, list)
    for r in results:
        assert hasattr(r, 'category')
        assert hasattr(r, 'conversion_rate')
        assert 0 <= r.conversion_rate <= 100

def test_correlation_report():
    """Test full correlation report."""
    from catalyst_bot.correlation import get_correlation_report

    report = get_correlation_report(days=30)

    assert 'alert_to_trade' in report
    assert 'sec_sentiment_impact' in report
    assert 'category_performance' in report
    assert 'ticker_concentration' in report
```

### 2. Integration Test

```bash
# Test cross-database queries
python -c "
from catalyst_bot.correlation import (
    get_correlation_report,
    alert_to_trade_correlation,
    ticker_concentration_analysis,
)

# Full report
report = get_correlation_report(days=30)
print('Correlation Report:')
print(f'  Alert-Trade correlations: {len(report[\"alert_to_trade\"])}')
print(f'  SEC sentiment buckets: {len(report[\"sec_sentiment_impact\"])}')

# Alert-trade details
correlations = alert_to_trade_correlation(days=30)
for c in correlations[:5]:
    print(f'  {c.category}: {c.alerts_count} alerts → {c.trades_triggered} trades ({c.conversion_rate}%)')

# Ticker concentration
tickers = ticker_concentration_analysis(days=30, top_n=5)
for t in tickers:
    print(f'  {t[\"ticker\"]}: {t[\"total_alerts\"]} alerts, {t[\"trade_win_rate\"]}% win rate')
"
```

### 3. Verify Database Attachments

```bash
# Test ATTACH DATABASE manually
python -c "
import sqlite3

conn = sqlite3.connect(':memory:')

# Try attaching databases
for alias, path in [
    ('feedback', 'data/feedback/alert_feedback.db'),
    ('positions', 'data/positions.db'),
]:
    try:
        conn.execute(f\"ATTACH DATABASE '{path}' AS {alias}\")
        print(f'✅ Attached {alias}')
    except Exception as e:
        print(f'❌ Failed {alias}: {e}')

# List attached
cursor = conn.execute('PRAGMA database_list')
for row in cursor:
    print(f'  {row[1]}: {row[2]}')
"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_CROSS_DB_CORRELATION` | `1` | Enable cross-database queries |

---

## Prerequisites Checklist

Before implementing this proposal, ensure:

- [ ] **#2 Unified Feedback System** implemented and populated
- [ ] **#4 Exit Analytics** implemented (for exit_reason data)
- [ ] **#5 SEC LLM Outcome Tracking** implemented (for sec_predictions data)
- [ ] Databases have at least 1-2 weeks of data for meaningful correlations

---

## Summary

This implementation provides:

1. **Unified Query Layer** - ATTACH DATABASE for cross-db joins
2. **Alert→Trade Correlation** - Did alerts that triggered trades win?
3. **SEC Sentiment Impact** - Does sentiment predict trade outcomes?
4. **Category Performance** - Which alert types trade best?
5. **Ticker Concentration** - Identify over-alerting issues

**Implementation Order:**
1. Phase A: Cross-DB query layer (2 hours)
2. Phase B: High-value correlations (1 hour)
3. Phase C: Reporting integration (1 hour)

**Note:** Wait 1-2 weeks after implementing #2, #4, #5 for data to populate before deploying this proposal.

**Expected Impact:**
- Answer "Did our alerts make money?" definitively
- Identify best-performing alert categories for trading
- Detect ticker concentration issues
- Data-driven optimization of alert generation

---

**End of Implementation Guide**
