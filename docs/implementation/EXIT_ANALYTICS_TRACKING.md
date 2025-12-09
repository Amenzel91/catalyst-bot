# Exit Analytics Tracking Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** MEDIUM
**Impact:** MEDIUM | **Effort:** LOW | **ROI:** HIGH
**Estimated Implementation Time:** 2-3 hours
**Target Files:** `src/catalyst_bot/trading/exit_analytics.py`, `src/catalyst_bot/portfolio/position_manager.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Implementation Strategy](#implementation-strategy)
4. [Phase A: Exit Analytics Module](#phase-a-exit-analytics-module)
5. [Phase B: Enhance Position Manager](#phase-b-enhance-position-manager)
6. [Phase C: Reporting Integration](#phase-c-reporting-integration)
7. [Coding Tickets](#coding-tickets)
8. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

The TradingEngine tracks position **entry** data comprehensively but lacks **exit** analytics:

| Entry Data | Status | Exit Data | Status |
|------------|--------|-----------|--------|
| Entry price | ✅ Tracked | Exit reason breakdown | ❌ Missing |
| Entry time | ✅ Tracked | Hold duration distribution | ❌ Missing |
| Signal score | ✅ Tracked | Slippage on exits | ❌ Missing |
| Stop-loss/Take-profit | ✅ Tracked | Time-of-day patterns | ❌ Missing |
| Strategy | ✅ Tracked | Exit reason analytics | ❌ Missing |

### What's Stored But Never Analyzed

**File:** `src/catalyst_bot/portfolio/position_manager.py:643`

```python
closed = await self.position_manager.close_position(
    position_id=position.position_id,
    exit_reason="close_signal",  # STORED but never analyzed!
)
```

The `exit_reason` field is captured in the database but **never queried or reported**.

### Defined Exit Reasons (8 types, only 2 implemented)

**File:** `src/catalyst_bot/migrations/001_create_positions_tables.py:124-134`

```sql
CONSTRAINT valid_exit_reason CHECK(
    exit_reason IN (
        'stop_loss',        -- ✅ Implemented
        'take_profit',      -- ✅ Implemented
        'trailing_stop',    -- ❌ NOT IMPLEMENTED
        'time_exit',        -- ❌ NOT IMPLEMENTED
        'manual',           -- Partial (via close_signal)
        'risk_limit',       -- ❌ NOT IMPLEMENTED
        'circuit_breaker',  -- ❌ NOT IMPLEMENTED
        'market_close'      -- ❌ NOT IMPLEMENTED
    )
)
```

---

## Current State Analysis

### Closed Positions Table Schema

**File:** `src/catalyst_bot/portfolio/position_manager.py:336-358`

```python
# Columns available but underutilized:
position_id, ticker, side, quantity
entry_price, exit_price, cost_basis
realized_pnl, realized_pnl_pct
exit_reason          # ← STORED, never analyzed
exit_order_id
opened_at, closed_at
hold_duration_seconds  # ← STORED, never distributed
max_favorable_excursion  # ← EMPTY (never populated)
max_adverse_excursion    # ← EMPTY (never populated)
slippage                 # ← EMPTY (never populated)
commission               # ← EMPTY (never populated)
```

### Current Analytics Method (Limited)

**File:** `src/catalyst_bot/portfolio/position_manager.py:981-1033`

`get_performance_stats()` returns:
```python
{
    'total_trades': int,
    'winning_trades': int,
    'losing_trades': int,
    'win_rate': float,
    'total_pnl': float,
    'avg_pnl': float,
    'avg_hold_time_hours': float,  # AGGREGATED ONLY - no distribution!
    # MISSING: exit_reason breakdown
    # MISSING: hold duration by exit reason
    # MISSING: time-of-day analysis
}
```

### Database Index Exists (Ready for Queries)

**File:** `src/catalyst_bot/migrations/001_create_positions_tables.py:189-191`

```sql
CREATE INDEX IF NOT EXISTS idx_closed_positions_exit_reason
ON closed_positions(exit_reason);
```

---

## Implementation Strategy

### Exit Analytics System

```
┌─────────────────────────────────────────────────────────────────┐
│                     EXIT ANALYTICS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │ Position Close  │                                            │
│  │ (trading_engine)│                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ closed_positions│───▶│ ExitAnalytics   │                     │
│  │ (SQLite table)  │    │ (new module)    │                     │
│  └─────────────────┘    └────────┬────────┘                     │
│                                  │                              │
│         ┌────────────────────────┼────────────────────┐         │
│         ▼                        ▼                    ▼         │
│  ┌────────────┐          ┌────────────┐       ┌────────────┐   │
│  │ Exit Reason│          │ Hold Time  │       │ Time-of-Day│   │
│  │ Breakdown  │          │ Distribution│      │ Patterns   │   │
│  └────────────┘          └────────────┘       └────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Analytics to Add

| Metric | Query Type | Value |
|--------|------------|-------|
| Exit reason breakdown | GROUP BY exit_reason | Which exits work best? |
| Hold duration by reason | GROUP BY exit_reason + AVG(hold) | Optimal hold per exit type |
| Time-of-day exits | EXTRACT hour FROM closed_at | Best exit timing |
| Win rate by exit reason | GROUP BY exit_reason + win/loss | Stop-loss vs take-profit performance |
| Slippage analysis | AVG(slippage) by exit | Execution quality |

---

## Phase A: Exit Analytics Module

### File Structure

```
src/catalyst_bot/trading/
├── __init__.py
├── trading_engine.py      # Existing
├── market_data.py         # Existing
└── exit_analytics.py      # NEW
```

### File: `src/catalyst_bot/trading/exit_analytics.py`

```python
"""
Exit analytics for Catalyst-Bot trading positions.

Provides analysis of:
- Exit reason effectiveness (stop-loss vs take-profit vs manual)
- Hold duration distributions by exit type
- Time-of-day exit patterns
- Slippage analysis

Reference: docs/implementation/EXIT_ANALYTICS_TRACKING.md
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("exit_analytics")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExitReasonStats:
    """Statistics for a single exit reason."""
    exit_reason: str
    count: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    avg_pnl_pct: float
    avg_hold_hours: float
    best_trade: float
    worst_trade: float


@dataclass
class HoldDurationBucket:
    """Hold duration distribution bucket."""
    min_hours: float
    max_hours: float
    count: int
    wins: int
    avg_pnl: float


@dataclass
class TimeOfDayStats:
    """Exit statistics by hour of day."""
    hour: int
    count: int
    wins: int
    win_rate: float
    avg_pnl: float


# =============================================================================
# Exit Analytics Class
# =============================================================================

class ExitAnalytics:
    """
    Analyzes exit patterns from closed positions.

    Usage:
        analytics = ExitAnalytics()
        breakdown = analytics.get_exit_reason_breakdown(days=30)
        distribution = analytics.get_hold_duration_distribution()
        patterns = analytics.get_time_of_day_patterns()
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize with database connection."""
        if db_path is None:
            try:
                from ..config import get_settings
                settings = get_settings()
                db_path = Path(settings.data_dir) / "positions.db"
            except Exception:
                db_path = Path("data") / "positions.db"

        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    # =========================================================================
    # Exit Reason Analysis
    # =========================================================================

    def get_exit_reason_breakdown(
        self,
        days: int = 30,
    ) -> List[ExitReasonStats]:
        """
        Get performance breakdown by exit reason.

        Args:
            days: Lookback period in days

        Returns:
            List of ExitReasonStats ordered by count

        SQL Reference:
            migrations/001_create_positions_tables.py:313-321
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    exit_reason,
                    COUNT(*) as count,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl) as avg_pnl,
                    AVG(realized_pnl_pct) as avg_pnl_pct,
                    AVG(hold_duration_seconds / 3600.0) as avg_hold_hours,
                    MAX(realized_pnl) as best_trade,
                    MIN(realized_pnl) as worst_trade
                FROM closed_positions
                WHERE closed_at > datetime('now', ?)
                GROUP BY exit_reason
                ORDER BY count DESC
            """, (f'-{days} days',))

            results = []
            for row in cursor.fetchall():
                count = row['count']
                wins = row['wins'] or 0
                win_rate = (wins / count * 100) if count > 0 else 0

                results.append(ExitReasonStats(
                    exit_reason=row['exit_reason'] or 'unknown',
                    count=count,
                    wins=wins,
                    losses=row['losses'] or 0,
                    win_rate=round(win_rate, 1),
                    total_pnl=round(row['total_pnl'] or 0, 2),
                    avg_pnl=round(row['avg_pnl'] or 0, 2),
                    avg_pnl_pct=round(row['avg_pnl_pct'] or 0, 2),
                    avg_hold_hours=round(row['avg_hold_hours'] or 0, 1),
                    best_trade=round(row['best_trade'] or 0, 2),
                    worst_trade=round(row['worst_trade'] or 0, 2),
                ))

            return results

        except Exception as e:
            log.error("exit_reason_breakdown_failed err=%s", e)
            return []

    def get_exit_reason_comparison(
        self,
        reason_a: str,
        reason_b: str,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Compare two exit reasons head-to-head.

        Args:
            reason_a: First exit reason (e.g., 'stop_loss')
            reason_b: Second exit reason (e.g., 'take_profit')
            days: Lookback period

        Returns:
            Dict with comparison metrics
        """
        breakdown = self.get_exit_reason_breakdown(days=days)
        stats_map = {s.exit_reason: s for s in breakdown}

        a = stats_map.get(reason_a)
        b = stats_map.get(reason_b)

        if not a or not b:
            return {'error': 'One or both exit reasons not found'}

        return {
            'comparison': f'{reason_a} vs {reason_b}',
            reason_a: {
                'count': a.count,
                'win_rate': a.win_rate,
                'avg_pnl': a.avg_pnl,
                'avg_hold_hours': a.avg_hold_hours,
            },
            reason_b: {
                'count': b.count,
                'win_rate': b.win_rate,
                'avg_pnl': b.avg_pnl,
                'avg_hold_hours': b.avg_hold_hours,
            },
            'winner': reason_a if a.avg_pnl > b.avg_pnl else reason_b,
            'pnl_difference': round(a.avg_pnl - b.avg_pnl, 2),
        }

    # =========================================================================
    # Hold Duration Analysis
    # =========================================================================

    def get_hold_duration_distribution(
        self,
        exit_reason: Optional[str] = None,
        days: int = 90,
    ) -> List[HoldDurationBucket]:
        """
        Get hold duration distribution.

        Args:
            exit_reason: Filter by exit reason (optional)
            days: Lookback period

        Returns:
            List of HoldDurationBucket
        """
        # Define buckets (in hours)
        bucket_bounds = [
            (0, 0.25),      # < 15 min
            (0.25, 0.5),    # 15-30 min
            (0.5, 1),       # 30 min - 1 hour
            (1, 4),         # 1-4 hours
            (4, 8),         # 4-8 hours
            (8, 24),        # 8-24 hours (1 day)
            (24, 72),       # 1-3 days
            (72, 168),      # 3-7 days
            (168, float('inf')),  # > 7 days
        ]

        try:
            cursor = self.conn.cursor()

            query = """
                SELECT
                    hold_duration_seconds / 3600.0 as hold_hours,
                    realized_pnl
                FROM closed_positions
                WHERE closed_at > datetime('now', ?)
            """
            params = [f'-{days} days']

            if exit_reason:
                query += " AND exit_reason = ?"
                params.append(exit_reason)

            cursor.execute(query, params)

            # Bucket the results
            buckets = {bounds: {'count': 0, 'wins': 0, 'total_pnl': 0}
                       for bounds in bucket_bounds}

            for row in cursor.fetchall():
                hold_hours = row['hold_hours'] or 0
                pnl = row['realized_pnl'] or 0

                for (min_h, max_h) in bucket_bounds:
                    if min_h <= hold_hours < max_h:
                        buckets[(min_h, max_h)]['count'] += 1
                        buckets[(min_h, max_h)]['total_pnl'] += pnl
                        if pnl > 0:
                            buckets[(min_h, max_h)]['wins'] += 1
                        break

            results = []
            for (min_h, max_h), data in buckets.items():
                if data['count'] > 0:
                    results.append(HoldDurationBucket(
                        min_hours=min_h,
                        max_hours=max_h if max_h != float('inf') else 999,
                        count=data['count'],
                        wins=data['wins'],
                        avg_pnl=round(data['total_pnl'] / data['count'], 2),
                    ))

            return results

        except Exception as e:
            log.error("hold_duration_distribution_failed err=%s", e)
            return []

    def get_optimal_hold_duration(
        self,
        exit_reason: Optional[str] = None,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Find optimal hold duration based on P&L.

        Returns:
            Dict with optimal duration range and stats
        """
        distribution = self.get_hold_duration_distribution(
            exit_reason=exit_reason,
            days=days,
        )

        if not distribution:
            return {'error': 'No data available'}

        # Find bucket with highest avg P&L
        best_bucket = max(distribution, key=lambda b: b.avg_pnl)

        # Find bucket with highest win rate
        best_winrate_bucket = max(
            distribution,
            key=lambda b: (b.wins / b.count) if b.count > 0 else 0
        )

        return {
            'optimal_by_pnl': {
                'range_hours': f"{best_bucket.min_hours}-{best_bucket.max_hours}",
                'avg_pnl': best_bucket.avg_pnl,
                'count': best_bucket.count,
            },
            'optimal_by_winrate': {
                'range_hours': f"{best_winrate_bucket.min_hours}-{best_winrate_bucket.max_hours}",
                'win_rate': round(best_winrate_bucket.wins / best_winrate_bucket.count * 100, 1)
                            if best_winrate_bucket.count > 0 else 0,
                'count': best_winrate_bucket.count,
            },
        }

    # =========================================================================
    # Time-of-Day Analysis
    # =========================================================================

    def get_time_of_day_patterns(
        self,
        days: int = 90,
    ) -> List[TimeOfDayStats]:
        """
        Analyze exit performance by hour of day.

        Args:
            days: Lookback period

        Returns:
            List of TimeOfDayStats for each hour (0-23)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    CAST(strftime('%H', closed_at) AS INTEGER) as exit_hour,
                    COUNT(*) as count,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(realized_pnl) as avg_pnl
                FROM closed_positions
                WHERE closed_at > datetime('now', ?)
                GROUP BY exit_hour
                ORDER BY exit_hour
            """, (f'-{days} days',))

            results = []
            for row in cursor.fetchall():
                count = row['count']
                wins = row['wins'] or 0
                results.append(TimeOfDayStats(
                    hour=row['exit_hour'],
                    count=count,
                    wins=wins,
                    win_rate=round((wins / count * 100) if count > 0 else 0, 1),
                    avg_pnl=round(row['avg_pnl'] or 0, 2),
                ))

            return results

        except Exception as e:
            log.error("time_of_day_patterns_failed err=%s", e)
            return []

    def get_best_exit_hours(
        self,
        days: int = 90,
        min_trades: int = 5,
    ) -> Dict[str, Any]:
        """
        Find best and worst hours for exits.

        Args:
            days: Lookback period
            min_trades: Minimum trades to consider

        Returns:
            Dict with best/worst hours
        """
        patterns = self.get_time_of_day_patterns(days=days)
        filtered = [p for p in patterns if p.count >= min_trades]

        if not filtered:
            return {'error': 'Not enough data'}

        best_by_pnl = max(filtered, key=lambda p: p.avg_pnl)
        worst_by_pnl = min(filtered, key=lambda p: p.avg_pnl)
        best_by_winrate = max(filtered, key=lambda p: p.win_rate)

        return {
            'best_hour_by_pnl': {
                'hour': best_by_pnl.hour,
                'avg_pnl': best_by_pnl.avg_pnl,
                'count': best_by_pnl.count,
            },
            'worst_hour_by_pnl': {
                'hour': worst_by_pnl.hour,
                'avg_pnl': worst_by_pnl.avg_pnl,
                'count': worst_by_pnl.count,
            },
            'best_hour_by_winrate': {
                'hour': best_by_winrate.hour,
                'win_rate': best_by_winrate.win_rate,
                'count': best_by_winrate.count,
            },
        }

    # =========================================================================
    # Summary Report
    # =========================================================================

    def get_exit_analytics_summary(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive exit analytics summary.

        Returns:
            Dict with all exit analytics
        """
        breakdown = self.get_exit_reason_breakdown(days=days)
        optimal_hold = self.get_optimal_hold_duration(days=days)
        best_hours = self.get_best_exit_hours(days=days)

        # Calculate totals
        total_trades = sum(s.count for s in breakdown)
        total_wins = sum(s.wins for s in breakdown)
        total_pnl = sum(s.total_pnl for s in breakdown)

        return {
            'period_days': days,
            'total_closed_positions': total_trades,
            'overall_win_rate': round((total_wins / total_trades * 100) if total_trades > 0 else 0, 1),
            'total_pnl': round(total_pnl, 2),
            'exit_reason_breakdown': [
                {
                    'reason': s.exit_reason,
                    'count': s.count,
                    'win_rate': s.win_rate,
                    'avg_pnl': s.avg_pnl,
                    'avg_hold_hours': s.avg_hold_hours,
                }
                for s in breakdown
            ],
            'optimal_hold_duration': optimal_hold,
            'best_exit_hours': best_hours,
        }

    def format_for_discord(self, days: int = 30) -> str:
        """
        Format exit analytics for Discord embed.

        Returns:
            Formatted string for Discord
        """
        breakdown = self.get_exit_reason_breakdown(days=days)

        if not breakdown:
            return "No exit data available"

        lines = [f"📊 **Exit Analytics ({days}d)**\n"]

        for stats in breakdown[:5]:  # Top 5 exit reasons
            emoji = "🟢" if stats.win_rate >= 50 else "🔴"
            lines.append(
                f"{emoji} **{stats.exit_reason}** ({stats.count} trades)\n"
                f"├─ Win Rate: {stats.win_rate}%\n"
                f"├─ Avg P&L: ${stats.avg_pnl:+.2f}\n"
                f"└─ Avg Hold: {stats.avg_hold_hours:.1f}h"
            )

        return "\n".join(lines)


# =============================================================================
# Module-Level Helper
# =============================================================================

def get_exit_analytics() -> ExitAnalytics:
    """Get exit analytics instance."""
    return ExitAnalytics()
```

---

## Phase B: Enhance Position Manager

### 1. Add Exit Analytics Query Method

**File:** `src/catalyst_bot/portfolio/position_manager.py`
**Location:** After `get_performance_stats()` (around Line 1033)

```python
def get_exit_analytics(self, days: int = 30) -> Dict[str, Any]:
    """
    Get detailed exit analytics.

    Delegates to ExitAnalytics module for comprehensive analysis.

    Args:
        days: Lookback period

    Returns:
        Dict with exit reason breakdown, hold distribution, time patterns
    """
    try:
        from ..trading.exit_analytics import ExitAnalytics
        analytics = ExitAnalytics(db_path=self.db_path)
        return analytics.get_exit_analytics_summary(days=days)
    except Exception as e:
        self.logger.error(f"exit_analytics_failed: {e}")
        return {'error': str(e)}
```

### 2. Populate Missing Fields on Close

**File:** `src/catalyst_bot/portfolio/position_manager.py`
**Location:** In `close_position()` method (around Line 630)

```python
# ADD to close_position() before saving to database:

# Calculate slippage if we have expected exit price
slippage = 0.0
if position.take_profit_price and exit_reason == 'take_profit':
    expected_price = float(position.take_profit_price)
    slippage = ((exit_price - expected_price) / expected_price) * 100
elif position.stop_loss_price and exit_reason == 'stop_loss':
    expected_price = float(position.stop_loss_price)
    slippage = ((exit_price - expected_price) / expected_price) * 100

# Calculate max favorable/adverse excursion if tracked
# (Requires price tracking during position lifecycle - future enhancement)
max_favorable = position.metadata.get('max_favorable_price', exit_price)
max_adverse = position.metadata.get('max_adverse_price', exit_price)

mfe = ((max_favorable - entry_price) / entry_price) * 100 if entry_price > 0 else 0
mae = ((max_adverse - entry_price) / entry_price) * 100 if entry_price > 0 else 0
```

---

## Phase C: Reporting Integration

### 1. Admin Report Integration

**File:** `src/catalyst_bot/admin_controls.py`
**Location:** In `build_admin_embed()` (add new field)

```python
# ADD exit analytics section to admin embed:

def _get_exit_analytics_summary() -> str:
    """Get exit analytics for admin embed."""
    try:
        from .trading.exit_analytics import ExitAnalytics
        analytics = ExitAnalytics()
        return analytics.format_for_discord(days=7)
    except Exception as e:
        return f"Exit analytics error: {e}"


# In build_admin_embed():
embed["fields"].append({
    "name": "🚪 Exit Performance",
    "value": _get_exit_analytics_summary(),
    "inline": False,
})
```

### 2. Backtesting Report Enhancement

**File:** `src/catalyst_bot/backtesting/reports.py`
**Location:** After Line 149 (after trade table)

```python
# ADD exit reason summary to backtest reports:

def _format_exit_reason_summary(trades: List[Dict]) -> str:
    """Format exit reason breakdown for backtest report."""
    from collections import defaultdict

    by_reason = defaultdict(lambda: {'count': 0, 'wins': 0, 'total_pnl': 0})

    for trade in trades:
        reason = trade.get('exit_reason', 'unknown')
        by_reason[reason]['count'] += 1
        by_reason[reason]['total_pnl'] += trade.get('profit', 0)
        if trade.get('profit', 0) > 0:
            by_reason[reason]['wins'] += 1

    lines = ["\n## Exit Reason Breakdown\n"]
    lines.append("| Exit Reason | Count | Win Rate | Avg P&L |")
    lines.append("|-------------|-------|----------|---------|")

    for reason, stats in sorted(by_reason.items(), key=lambda x: -x[1]['count']):
        win_rate = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
        avg_pnl = stats['total_pnl'] / stats['count'] if stats['count'] > 0 else 0
        lines.append(f"| {reason} | {stats['count']} | {win_rate:.1f}% | ${avg_pnl:.2f} |")

    return "\n".join(lines)
```

---

## Coding Tickets

### Phase A: Exit Analytics Module

#### Ticket A.1: Create Exit Analytics Module
```
Title: Create exit_analytics.py with analysis functions
Priority: High
Estimate: 1.5 hours

Files to Create:
- src/catalyst_bot/trading/exit_analytics.py

Tasks:
1. Implement ExitReasonStats, HoldDurationBucket, TimeOfDayStats dataclasses
2. Implement ExitAnalytics class with database connection
3. Implement get_exit_reason_breakdown()
4. Implement get_hold_duration_distribution()
5. Implement get_time_of_day_patterns()
6. Implement get_exit_analytics_summary()
7. Implement format_for_discord()

Acceptance Criteria:
- [ ] All queries return correct results
- [ ] Graceful handling of empty database
- [ ] Discord formatting is readable
```

### Phase B: Position Manager

#### Ticket B.1: Add Exit Analytics Method
```
Title: Add get_exit_analytics() to PositionManager
Priority: High
Estimate: 20 minutes

File: src/catalyst_bot/portfolio/position_manager.py
Location: After Line 1033

Tasks:
1. Add get_exit_analytics() method
2. Delegate to ExitAnalytics module

Acceptance Criteria:
- [ ] Method returns comprehensive analytics
- [ ] Graceful error handling
```

#### Ticket B.2: Populate Slippage on Close
```
Title: Calculate and store slippage on position close
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/portfolio/position_manager.py
Location: In close_position() around Line 630

Tasks:
1. Calculate slippage vs expected price
2. Store in closed_positions record

Acceptance Criteria:
- [ ] Slippage calculated for stop_loss and take_profit exits
- [ ] Value stored in database
```

### Phase C: Reporting

#### Ticket C.1: Add to Admin Report
```
Title: Display exit analytics in admin embed
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/admin_controls.py

Tasks:
1. Create _get_exit_analytics_summary() helper
2. Add "Exit Performance" field to embed

Acceptance Criteria:
- [ ] Admin embed shows exit breakdown
- [ ] Shows win rate per exit reason
```

#### Ticket C.2: Add to Backtest Reports
```
Title: Add exit reason summary to backtest reports
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/backtesting/reports.py

Tasks:
1. Add _format_exit_reason_summary() function
2. Include in report generation

Acceptance Criteria:
- [ ] Backtest reports show exit breakdown table
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_exit_analytics.py
import pytest

def test_exit_reason_breakdown():
    """Test exit reason breakdown query."""
    from catalyst_bot.trading.exit_analytics import ExitAnalytics

    analytics = ExitAnalytics()
    breakdown = analytics.get_exit_reason_breakdown(days=90)

    assert isinstance(breakdown, list)
    for stats in breakdown:
        assert stats.exit_reason is not None
        assert stats.count >= 0
        assert 0 <= stats.win_rate <= 100

def test_hold_duration_distribution():
    """Test hold duration bucketing."""
    from catalyst_bot.trading.exit_analytics import ExitAnalytics

    analytics = ExitAnalytics()
    distribution = analytics.get_hold_duration_distribution(days=90)

    assert isinstance(distribution, list)
    for bucket in distribution:
        assert bucket.min_hours >= 0
        assert bucket.count >= 0

def test_time_of_day_patterns():
    """Test time-of-day analysis."""
    from catalyst_bot.trading.exit_analytics import ExitAnalytics

    analytics = ExitAnalytics()
    patterns = analytics.get_time_of_day_patterns(days=90)

    assert isinstance(patterns, list)
    for p in patterns:
        assert 0 <= p.hour <= 23
```

### 2. Integration Test

```bash
# Test exit analytics end-to-end
python -c "
from catalyst_bot.trading.exit_analytics import ExitAnalytics

analytics = ExitAnalytics()

# Get breakdown
breakdown = analytics.get_exit_reason_breakdown(days=90)
print('Exit Reason Breakdown:')
for stats in breakdown:
    print(f'  {stats.exit_reason}: {stats.count} trades, {stats.win_rate}% win rate')

# Get summary
summary = analytics.get_exit_analytics_summary(days=30)
print(f'\\nTotal trades: {summary[\"total_closed_positions\"]}')
print(f'Overall win rate: {summary[\"overall_win_rate\"]}%')

# Discord format
print('\\nDiscord Format:')
print(analytics.format_for_discord(days=30))
"
```

### 3. Verify Database Queries

```bash
# Direct SQL verification
sqlite3 data/positions.db "
SELECT
    exit_reason,
    COUNT(*) as count,
    ROUND(AVG(realized_pnl), 2) as avg_pnl,
    ROUND(AVG(hold_duration_seconds / 3600.0), 1) as avg_hours
FROM closed_positions
GROUP BY exit_reason
ORDER BY count DESC
"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_EXIT_ANALYTICS` | `1` | Enable exit analytics |

---

## Summary

This implementation provides:

1. **Exit Reason Breakdown** - Which exit types (stop-loss, take-profit, manual) perform best
2. **Hold Duration Analysis** - Optimal holding periods by exit type
3. **Time-of-Day Patterns** - Best/worst hours for exits
4. **Slippage Tracking** - Execution quality measurement
5. **Admin Integration** - Visible in Discord admin reports

**Implementation Order:**
1. Phase A: Create exit_analytics.py module (1.5 hours)
2. Phase B: Enhance position manager (30 min)
3. Phase C: Add to admin and backtest reports (30 min)

**Expected Impact:**
- Identify which exit strategies work best
- Optimize hold durations based on data
- Improve exit timing with time-of-day insights

---

**End of Implementation Guide**
