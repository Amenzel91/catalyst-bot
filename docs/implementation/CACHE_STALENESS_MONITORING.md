# Cache Staleness Monitoring Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** MEDIUM
**Impact:** MEDIUM | **Effort:** LOW | **ROI:** LOW-MEDIUM
**Estimated Implementation Time:** 2-3 hours
**Target Files:** `src/catalyst_bot/monitoring/cache_monitor.py`, various cache modules

---

## Table of Contents

1. [Overview](#overview)
2. [Current Cache Inventory](#current-cache-inventory)
3. [Risk Assessment](#risk-assessment)
4. [Implementation Strategy](#implementation-strategy)
5. [Phase A: Core Cache Monitor](#phase-a-core-cache-monitor)
6. [Phase B: Instrument Caches](#phase-b-instrument-caches)
7. [Phase C: Alerting & Reporting](#phase-c-alerting--reporting)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

Catalyst-Bot has **17 distinct caching mechanisms** across the codebase, each with different TTL strategies:

| Cache Type | Count | Risk if Stale |
|------------|-------|---------------|
| LLM/Semantic Cache | 2 | CRITICAL - Wrong analysis cached |
| Price Data Cache | 3 | HIGH - Position valuation errors |
| Fundamental Data | 1 | HIGH - Missed float/SI changes |
| Deduplication | 3 | MEDIUM - Missed alerts or duplicates |
| Chart Cache | 1 | LOW - Visual only |
| Other | 7 | MEDIUM - Various operational issues |

**No unified monitoring exists** to detect:
- Cache entries that exceed intended TTL
- Cache hit/miss rates
- Stale data serving during volatile periods
- Cache size growth

### What We're Building

A lightweight cache monitoring system that:
1. **Tracks cache health metrics** (hit rate, staleness, size)
2. **Detects stale entries** that exceed TTL
3. **Reports via admin heartbeat** - no new services needed
4. **Integrates with Prometheus** (if enabled) for observability

```
┌─────────────────────────────────────────────────────────────────┐
│                     CACHE MONITORING                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ LLM Cache   │  │ Price Cache │  │ Dedup Cache │  ... 14 more │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│         └────────────────┼────────────────┘                      │
│                          ▼                                       │
│              ┌─────────────────────────┐                        │
│              │    CacheMonitor         │                        │
│              │    (Singleton)          │                        │
│              └─────────────┬───────────┘                        │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐            │
│  │ Prometheus │    │ Admin      │    │ Health     │            │
│  │ Metrics    │    │ Heartbeat  │    │ Endpoint   │            │
│  └────────────┘    └────────────┘    └────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Current Cache Inventory

### CRITICAL Risk Caches

#### 1. LLM Semantic Cache
**File:** `src/catalyst_bot/llm_cache.py`
**Storage:** SQLite
**TTL:** 7 days (SEC filings), 24h-3d (others)

```python
# Current TTL settings (various locations)
SEC_FILING_CACHE_TTL = 7 * 24 * 3600  # 7 days
DEFAULT_CACHE_TTL = 24 * 3600          # 24 hours
```

**Risk:** Market-moving analysis cached too long. SEC filing amendments may not trigger cache invalidation.

#### 2. SEC LLM Cache
**File:** `src/catalyst_bot/sec_llm_cache.py`
**Storage:** SQLite (`data/sec_llm_cache.db`)
**TTL:** 72 hours

```python
CACHE_TTL_HOURS = 72  # 3 days
```

**Risk:** 8-K amendments not reliably detected. No cross-feed validation.

---

### HIGH Risk Caches

#### 3. Fundamental Data Cache
**File:** `src/catalyst_bot/fundamental_data.py`
**Storage:** SQLite (`data/cache/fundamentals.db`)
**TTL:** Float: 30 days, Short Interest: 14 days

```python
FLOAT_CACHE_TTL_DAYS = 30
SHORT_INTEREST_CACHE_TTL_DAYS = 14
```

**Risk:** Missing sudden float changes, short squeeze setups. Rate-limited API (1 req/sec).

#### 4. Price Cache (In-Memory)
**File:** `src/catalyst_bot/trading/market_data.py`
**Storage:** In-memory dict
**TTL:** 30 seconds

```python
PRICE_CACHE_TTL = 30  # seconds
```

**Risk:** Position valuation errors during volatile periods.

#### 5. Price Cache (File-Based)
**File:** `src/catalyst_bot/market.py`
**Storage:** File-based
**TTL:** 60 seconds

**Risk:** Stale during market gaps, earnings releases.

#### 6. Indicator Cache
**File:** `src/catalyst_bot/indicators/cache.py`
**Storage:** In-memory
**TTL:** 300 seconds (5 minutes)

**Risk:** Technical indicators stale during fast-moving markets.

#### 7. Chart Cache
**File:** `src/catalyst_bot/chart_cache.py`
**Storage:** SQLite (`data/chart_cache.db`)
**TTL:** 60s (1D), 5min (5D), longer for weekly/monthly

**Risk:** Stale charts during volatile periods (visual only).

---

### MEDIUM Risk Caches

#### 8. Seen Store (Deduplication)
**File:** `src/catalyst_bot/seen_store.py`
**Storage:** SQLite (`data/seen_ids.sqlite`)
**TTL:** 7 days

**Risk:** False duplicates if cache corrupted. Missed alerts if TTL too short.

#### 9. First Seen Index (Cross-Feed Dedup)
**File:** `src/catalyst_bot/dedup/first_seen_index.py`
**Storage:** SQLite (`data/dedup/first_seen.db`)
**TTL:** 48 hours

**Risk:** Cross-feed duplicate detection fails if stale.

#### 10. Sector Context
**File:** `src/catalyst_bot/sector_context.py`
**Storage:** In-memory
**TTL:** 30 days

**Risk:** Sector rotation not reflected in context.

#### 11. Sentiment Tracking
**File:** `src/catalyst_bot/sentiment_tracking.py`
**Storage:** SQLite (`data/sentiment_history.db`)
**TTL:** No auto-cleanup

**Risk:** Database growth, stale sentiment baselines.

#### 12. Rate Limiter State
**File:** `src/catalyst_bot/alerts_rate_limit.py`
**Storage:** In-memory
**TTL:** N/A (resets on restart)

**Risk:** Rate limits reset on restart, allowing burst alerts.

---

### LOWER Risk Caches

| Cache | File | Storage | TTL | Risk |
|-------|------|---------|-----|------|
| Chart Queue | `chart_queue.py` | In-memory | Session | Low |
| Position Manager | `position_manager.py` | SQLite | Persistent | Low |
| Backtesting Cache | `backtesting/` | File | Analysis session | Low |
| Google Trends | `google_trends.py` | In-memory | Varies | Low |
| News Velocity | `news_velocity.py` | SQLite | 24h | Low |

---

## Risk Assessment

### Staleness Risk Matrix

| Cache | Impact if Stale | Likelihood | Detection Difficulty | Priority |
|-------|-----------------|------------|---------------------|----------|
| LLM Semantic | HIGH | Medium | Hard | **P1** |
| SEC LLM | HIGH | Medium | Hard | **P1** |
| Fundamental | HIGH | Low | Medium | **P2** |
| Price (Memory) | HIGH | High | Easy | **P2** |
| Price (File) | MEDIUM | Medium | Easy | **P2** |
| Indicator | MEDIUM | Medium | Medium | **P3** |
| Dedup Caches | MEDIUM | Low | Hard | **P3** |
| Chart | LOW | High | Easy | **P4** |

---

## Implementation Strategy

### Metrics to Track

For each cache:
1. **Hit Rate** - % of requests served from cache
2. **Miss Rate** - % of requests that required fresh fetch
3. **Staleness Rate** - % of served entries exceeding soft TTL
4. **Size** - Number of entries / storage bytes
5. **Age Distribution** - Histogram of entry ages
6. **Eviction Rate** - Entries removed per hour

### Cache Monitor Interface

```python
class CacheMonitor:
    """
    Unified cache monitoring interface.

    Each cache registers with the monitor and reports:
    - hits/misses
    - entry ages
    - evictions
    """

    def register_cache(self, name: str, ttl_seconds: int, risk_level: str)
    def record_hit(self, cache_name: str, entry_age_seconds: float)
    def record_miss(self, cache_name: str)
    def record_eviction(self, cache_name: str, reason: str)
    def get_health_report(self) -> Dict[str, Any]
```

---

## Phase A: Core Cache Monitor

### File Structure

```
src/catalyst_bot/
├── monitoring/
│   ├── __init__.py           # Updated exports
│   ├── metrics.py            # Existing Prometheus metrics
│   ├── metrics_server.py     # Existing metrics server
│   └── cache_monitor.py      # NEW: Cache monitoring
```

### File: `src/catalyst_bot/monitoring/cache_monitor.py`

```python
"""
Cache staleness monitoring for Catalyst-Bot.

Provides unified monitoring for all cache implementations:
- Hit/miss tracking
- Staleness detection
- Size monitoring
- Health reporting

Reference: docs/implementation/CACHE_STALENESS_MONITORING.md
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from ..logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

log = get_logger("cache_monitor")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CacheConfig:
    """Configuration for a monitored cache."""
    name: str
    ttl_seconds: int
    risk_level: str  # 'critical', 'high', 'medium', 'low'
    soft_ttl_ratio: float = 0.8  # Warn at 80% of TTL
    description: str = ""


@dataclass
class CacheStats:
    """Statistics for a single cache."""
    hits: int = 0
    misses: int = 0
    stale_hits: int = 0  # Hits where entry age > soft_ttl
    evictions: int = 0
    total_age_seconds: float = 0  # For average age calculation
    max_age_seconds: float = 0
    size: int = 0
    last_hit_time: Optional[float] = None
    last_miss_time: Optional[float] = None

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100

    @property
    def staleness_rate(self) -> float:
        if self.hits == 0:
            return 0.0
        return (self.stale_hits / self.hits) * 100

    @property
    def avg_age_seconds(self) -> float:
        if self.hits == 0:
            return 0.0
        return self.total_age_seconds / self.hits


# =============================================================================
# Cache Monitor
# =============================================================================

class CacheMonitor:
    """
    Unified cache monitoring system.

    Thread-safe singleton that aggregates metrics from all caches.

    Usage:
        monitor = CacheMonitor()
        monitor.register_cache("llm_cache", ttl_seconds=86400, risk_level="critical")

        # In cache implementation:
        monitor.record_hit("llm_cache", entry_age_seconds=3600)
        monitor.record_miss("llm_cache")

        # In health check:
        report = monitor.get_health_report()
    """

    _instance: Optional['CacheMonitor'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize monitor state."""
        self._caches: Dict[str, CacheConfig] = {}
        self._stats: Dict[str, CacheStats] = defaultdict(CacheStats)
        self._start_time = time.time()
        log.info("cache_monitor_initialized")

    # =========================================================================
    # Registration
    # =========================================================================

    def register_cache(
        self,
        name: str,
        ttl_seconds: int,
        risk_level: str = "medium",
        soft_ttl_ratio: float = 0.8,
        description: str = "",
    ) -> None:
        """
        Register a cache for monitoring.

        Args:
            name: Unique cache identifier
            ttl_seconds: Cache TTL in seconds
            risk_level: 'critical', 'high', 'medium', or 'low'
            soft_ttl_ratio: Ratio of TTL at which to warn (default 0.8)
            description: Human-readable description
        """
        self._caches[name] = CacheConfig(
            name=name,
            ttl_seconds=ttl_seconds,
            risk_level=risk_level,
            soft_ttl_ratio=soft_ttl_ratio,
            description=description,
        )
        log.debug("cache_registered name=%s ttl=%d risk=%s", name, ttl_seconds, risk_level)

    # =========================================================================
    # Recording
    # =========================================================================

    def record_hit(
        self,
        cache_name: str,
        entry_age_seconds: float,
    ) -> None:
        """
        Record a cache hit.

        Args:
            cache_name: Name of the cache
            entry_age_seconds: Age of the cached entry
        """
        stats = self._stats[cache_name]
        config = self._caches.get(cache_name)

        stats.hits += 1
        stats.total_age_seconds += entry_age_seconds
        stats.max_age_seconds = max(stats.max_age_seconds, entry_age_seconds)
        stats.last_hit_time = time.time()

        # Check staleness
        if config:
            soft_ttl = config.ttl_seconds * config.soft_ttl_ratio
            if entry_age_seconds > soft_ttl:
                stats.stale_hits += 1
                log.debug(
                    "stale_cache_hit cache=%s age=%.1fs soft_ttl=%.1fs",
                    cache_name, entry_age_seconds, soft_ttl
                )

        # Update Prometheus metrics if available
        self._update_prometheus_hit(cache_name, entry_age_seconds)

    def record_miss(self, cache_name: str) -> None:
        """
        Record a cache miss.

        Args:
            cache_name: Name of the cache
        """
        stats = self._stats[cache_name]
        stats.misses += 1
        stats.last_miss_time = time.time()

        self._update_prometheus_miss(cache_name)

    def record_eviction(
        self,
        cache_name: str,
        reason: str = "ttl_expired",
    ) -> None:
        """
        Record a cache eviction.

        Args:
            cache_name: Name of the cache
            reason: Why entry was evicted (ttl_expired, manual, size_limit)
        """
        stats = self._stats[cache_name]
        stats.evictions += 1

        log.debug("cache_eviction cache=%s reason=%s", cache_name, reason)

    def update_size(self, cache_name: str, size: int) -> None:
        """
        Update the reported size of a cache.

        Args:
            cache_name: Name of the cache
            size: Number of entries (or bytes)
        """
        self._stats[cache_name].size = size

    # =========================================================================
    # Reporting
    # =========================================================================

    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate health report for all monitored caches.

        Returns:
            Dict with per-cache stats and overall health
        """
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': time.time() - self._start_time,
            'caches': {},
            'alerts': [],
            'summary': {
                'total_caches': len(self._caches),
                'healthy': 0,
                'warning': 0,
                'critical': 0,
            },
        }

        for name, config in self._caches.items():
            stats = self._stats[name]
            cache_report = self._build_cache_report(name, config, stats)
            report['caches'][name] = cache_report

            # Update summary
            health = cache_report['health']
            if health == 'healthy':
                report['summary']['healthy'] += 1
            elif health == 'warning':
                report['summary']['warning'] += 1
            else:
                report['summary']['critical'] += 1

            # Generate alerts
            alerts = self._check_alerts(name, config, stats)
            report['alerts'].extend(alerts)

        return report

    def _build_cache_report(
        self,
        name: str,
        config: CacheConfig,
        stats: CacheStats,
    ) -> Dict[str, Any]:
        """Build report for a single cache."""
        # Determine health status
        health = 'healthy'

        if stats.staleness_rate > 20:
            health = 'critical' if config.risk_level in ('critical', 'high') else 'warning'
        elif stats.staleness_rate > 10:
            health = 'warning'
        elif stats.hit_rate < 50 and stats.total_requests > 100:
            health = 'warning'  # Low hit rate might indicate issue

        return {
            'config': {
                'ttl_seconds': config.ttl_seconds,
                'risk_level': config.risk_level,
                'description': config.description,
            },
            'stats': {
                'hit_rate': round(stats.hit_rate, 1),
                'staleness_rate': round(stats.staleness_rate, 1),
                'total_requests': stats.total_requests,
                'hits': stats.hits,
                'misses': stats.misses,
                'stale_hits': stats.stale_hits,
                'evictions': stats.evictions,
                'avg_age_seconds': round(stats.avg_age_seconds, 1),
                'max_age_seconds': round(stats.max_age_seconds, 1),
                'size': stats.size,
            },
            'health': health,
        }

    def _check_alerts(
        self,
        name: str,
        config: CacheConfig,
        stats: CacheStats,
    ) -> List[Dict[str, Any]]:
        """Check for alert conditions."""
        alerts = []

        # High staleness rate
        if stats.staleness_rate > 20:
            alerts.append({
                'cache': name,
                'type': 'high_staleness',
                'severity': 'critical' if config.risk_level == 'critical' else 'warning',
                'message': f"{name}: {stats.staleness_rate:.1f}% stale hits (>{config.ttl_seconds * config.soft_ttl_ratio}s)",
            })

        # Max age exceeds TTL
        if stats.max_age_seconds > config.ttl_seconds:
            alerts.append({
                'cache': name,
                'type': 'ttl_exceeded',
                'severity': 'warning',
                'message': f"{name}: Max entry age {stats.max_age_seconds:.0f}s exceeds TTL {config.ttl_seconds}s",
            })

        # Low hit rate (potential misconfiguration)
        if stats.total_requests > 100 and stats.hit_rate < 30:
            alerts.append({
                'cache': name,
                'type': 'low_hit_rate',
                'severity': 'info',
                'message': f"{name}: Low hit rate {stats.hit_rate:.1f}% - cache may be ineffective",
            })

        return alerts

    def get_summary_for_heartbeat(self) -> str:
        """
        Get compact summary for Discord heartbeat.

        Returns:
            Formatted string for embed
        """
        report = self.get_health_report()
        summary = report['summary']

        lines = [f"📦 **Cache Health**"]

        # Overall status
        if summary['critical'] > 0:
            lines.append(f"├─ Status: 🔴 {summary['critical']} critical")
        elif summary['warning'] > 0:
            lines.append(f"├─ Status: 🟡 {summary['warning']} warnings")
        else:
            lines.append(f"├─ Status: 🟢 All healthy")

        lines.append(f"├─ Monitored: {summary['total_caches']} caches")

        # Top issues
        critical_caches = [
            name for name, data in report['caches'].items()
            if data['health'] == 'critical'
        ]
        if critical_caches:
            lines.append(f"└─ Issues: {', '.join(critical_caches[:3])}")
        else:
            # Show hit rates for critical caches
            for name in ['llm_cache', 'sec_llm_cache', 'price_cache']:
                if name in report['caches']:
                    data = report['caches'][name]
                    lines.append(f"└─ {name}: {data['stats']['hit_rate']:.0f}% hits")
                    break

        return "\n".join(lines)

    # =========================================================================
    # Prometheus Integration
    # =========================================================================

    def _update_prometheus_hit(self, cache_name: str, age: float) -> None:
        """Update Prometheus metrics for cache hit."""
        try:
            from .metrics import cache_hits_total, cache_entry_age
            cache_hits_total.labels(cache=cache_name).inc()
            cache_entry_age.labels(cache=cache_name).observe(age)
        except Exception:
            pass  # Prometheus not available

    def _update_prometheus_miss(self, cache_name: str) -> None:
        """Update Prometheus metrics for cache miss."""
        try:
            from .metrics import cache_misses_total
            cache_misses_total.labels(cache=cache_name).inc()
        except Exception:
            pass  # Prometheus not available


# =============================================================================
# Module-Level Helpers
# =============================================================================

def get_cache_monitor() -> CacheMonitor:
    """Get the singleton cache monitor instance."""
    return CacheMonitor()


def register_default_caches() -> None:
    """
    Register all known caches with default configurations.

    Call this during bot initialization.
    """
    monitor = get_cache_monitor()

    # Critical risk caches
    monitor.register_cache(
        name="llm_cache",
        ttl_seconds=86400,  # 24 hours default
        risk_level="critical",
        description="LLM semantic cache for analysis"
    )
    monitor.register_cache(
        name="sec_llm_cache",
        ttl_seconds=72 * 3600,  # 72 hours
        risk_level="critical",
        description="SEC filing LLM analysis cache"
    )

    # High risk caches
    monitor.register_cache(
        name="fundamental_cache",
        ttl_seconds=30 * 86400,  # 30 days for float
        risk_level="high",
        description="Float shares and short interest"
    )
    monitor.register_cache(
        name="price_cache_memory",
        ttl_seconds=30,
        risk_level="high",
        description="In-memory price quotes"
    )
    monitor.register_cache(
        name="price_cache_file",
        ttl_seconds=60,
        risk_level="high",
        description="File-based price quotes"
    )
    monitor.register_cache(
        name="indicator_cache",
        ttl_seconds=300,
        risk_level="high",
        description="Technical indicator values"
    )

    # Medium risk caches
    monitor.register_cache(
        name="chart_cache",
        ttl_seconds=60,
        risk_level="medium",
        description="Chart image URLs"
    )
    monitor.register_cache(
        name="seen_store",
        ttl_seconds=7 * 86400,
        risk_level="medium",
        description="Deduplication seen IDs"
    )
    monitor.register_cache(
        name="first_seen_index",
        ttl_seconds=48 * 3600,
        risk_level="medium",
        description="Cross-feed deduplication"
    )

    log.info("default_caches_registered count=%d", len(monitor._caches))
```

### Update: `src/catalyst_bot/monitoring/__init__.py`

Add to existing exports:

```python
# Add to existing __init__.py

from .cache_monitor import (
    CacheMonitor,
    CacheConfig,
    CacheStats,
    get_cache_monitor,
    register_default_caches,
)

# Update __all__
__all__ = [
    # ... existing exports ...
    'CacheMonitor',
    'CacheConfig',
    'CacheStats',
    'get_cache_monitor',
    'register_default_caches',
]
```

### Add Prometheus Metrics (Optional)

**File:** `src/catalyst_bot/monitoring/metrics.py`
**Location:** Add after existing metrics

```python
# Cache metrics (add to existing metrics.py)

cache_hits_total = Counter(
    f'{METRIC_PREFIX}_cache_hits_total',
    'Cache hits by cache name',
    ['cache']
)

cache_misses_total = Counter(
    f'{METRIC_PREFIX}_cache_misses_total',
    'Cache misses by cache name',
    ['cache']
)

cache_entry_age = Histogram(
    f'{METRIC_PREFIX}_cache_entry_age_seconds',
    'Age of cache entries when served',
    ['cache'],
    buckets=[1, 5, 30, 60, 300, 900, 3600, 86400]
)

cache_staleness_ratio = Gauge(
    f'{METRIC_PREFIX}_cache_staleness_ratio',
    'Ratio of stale cache hits',
    ['cache']
)
```

---

## Phase B: Instrument Caches

### 1. LLM Cache Instrumentation

**File:** `src/catalyst_bot/llm_cache.py`
**Location:** In cache lookup and store methods

```python
# ADD at top of file:
try:
    from .monitoring import get_cache_monitor
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False


# In get_cached() or similar method:
def get_cached(self, key: str) -> Optional[Any]:
    """Get cached LLM response."""
    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT response, created_at FROM llm_cache WHERE key = ?
    """, (key,))
    row = cursor.fetchone()

    if row:
        # Calculate entry age
        created_at = datetime.fromisoformat(row['created_at'])
        age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()

        # Record cache hit
        if _MONITOR_AVAILABLE:
            monitor = get_cache_monitor()
            monitor.record_hit("llm_cache", age_seconds)

        return row['response']

    # Record cache miss
    if _MONITOR_AVAILABLE:
        monitor = get_cache_monitor()
        monitor.record_miss("llm_cache")

    return None
```

### 2. Price Cache Instrumentation

**File:** `src/catalyst_bot/trading/market_data.py`
**Location:** In get_price() method

```python
# ADD at top of file:
try:
    from ..monitoring import get_cache_monitor
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False


# In get_price() or similar:
def get_price(self, ticker: str) -> Optional[float]:
    """Get current price, from cache if fresh."""
    now = time.time()

    if ticker in self._price_cache:
        cached_price, cached_time = self._price_cache[ticker]
        age = now - cached_time

        if age < PRICE_CACHE_TTL:
            # Record cache hit
            if _MONITOR_AVAILABLE:
                get_cache_monitor().record_hit("price_cache_memory", age)
            return cached_price

    # Cache miss or expired
    if _MONITOR_AVAILABLE:
        get_cache_monitor().record_miss("price_cache_memory")

    # Fetch fresh price...
    fresh_price = self._fetch_price(ticker)
    self._price_cache[ticker] = (fresh_price, now)
    return fresh_price
```

### 3. SEC LLM Cache Instrumentation

**File:** `src/catalyst_bot/sec_llm_cache.py`
**Location:** In lookup method

```python
# ADD at top:
try:
    from .monitoring import get_cache_monitor
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False


# In get_analysis() or similar:
def get_analysis(self, filing_id: str) -> Optional[Dict]:
    """Get cached SEC filing analysis."""
    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT analysis, cached_at FROM sec_llm_cache WHERE filing_id = ?
    """, (filing_id,))
    row = cursor.fetchone()

    if row:
        cached_at = datetime.fromisoformat(row['cached_at'])
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()

        # Check TTL
        if age_seconds < CACHE_TTL_HOURS * 3600:
            if _MONITOR_AVAILABLE:
                get_cache_monitor().record_hit("sec_llm_cache", age_seconds)
            return json.loads(row['analysis'])

        # Expired - evict
        if _MONITOR_AVAILABLE:
            get_cache_monitor().record_eviction("sec_llm_cache", "ttl_expired")

    if _MONITOR_AVAILABLE:
        get_cache_monitor().record_miss("sec_llm_cache")

    return None
```

### 4. Fundamental Data Instrumentation

**File:** `src/catalyst_bot/fundamental_data.py`
**Location:** In get_float() and get_short_interest() methods

```python
# Similar pattern - record hits/misses with age calculation
```

---

## Phase C: Alerting & Reporting

### 1. Admin Heartbeat Integration

**File:** `src/catalyst_bot/runner.py`
**Location:** In heartbeat building function

```python
# ADD to heartbeat embed builder:

def _build_heartbeat_embed(...) -> dict:
    # ... existing code ...

    # Add cache health section
    try:
        from .monitoring import get_cache_monitor
        monitor = get_cache_monitor()
        cache_summary = monitor.get_summary_for_heartbeat()

        # Add to description or as field
        embed["fields"].append({
            "name": "📦 Caches",
            "value": cache_summary,
            "inline": True,
        })
    except Exception:
        pass  # Cache monitoring not available

    return embed
```

### 2. Health Endpoint Integration

**File:** `src/catalyst_bot/health_endpoint.py`
**Location:** In `_handle_detailed()` method

```python
# ADD to detailed health response:

def _handle_detailed(self):
    """Detailed health endpoint with cache status."""
    try:
        health = get_health_status()

        # Add cache health
        try:
            from .monitoring import get_cache_monitor
            monitor = get_cache_monitor()
            health['caches'] = monitor.get_health_report()
        except Exception:
            health['caches'] = {'error': 'Cache monitoring unavailable'}

        # ... rest of handler
```

### 3. Bot Initialization

**File:** `src/catalyst_bot/runner.py`
**Location:** In `runner_main()` after health server start

```python
# ADD after health server initialization:

# Initialize cache monitoring
if os.getenv("FEATURE_CACHE_MONITORING", "1").strip().lower() in ("1", "true", "yes"):
    try:
        from .monitoring import register_default_caches
        register_default_caches()
        log.info("cache_monitoring_enabled")
    except Exception as e:
        log.warning("cache_monitoring_init_failed err=%s", e)
```

---

## Coding Tickets

### Phase A: Core Module

#### Ticket A.1: Create Cache Monitor
```
Title: Create cache monitoring module
Priority: High
Estimate: 1.5 hours

Files to Create:
- src/catalyst_bot/monitoring/cache_monitor.py

Tasks:
1. Implement CacheConfig and CacheStats dataclasses
2. Implement CacheMonitor singleton
3. Implement registration, recording, and reporting methods
4. Implement get_summary_for_heartbeat()
5. Add register_default_caches() helper

Acceptance Criteria:
- [ ] Singleton pattern works correctly
- [ ] Can register and track multiple caches
- [ ] Health report generates correctly
- [ ] Heartbeat summary is compact and readable
```

#### Ticket A.2: Update Monitoring Package
```
Title: Export cache monitor from monitoring package
Priority: High
Estimate: 10 minutes

File: src/catalyst_bot/monitoring/__init__.py

Tasks:
1. Import cache monitor classes
2. Add to __all__

Acceptance Criteria:
- [ ] from catalyst_bot.monitoring import CacheMonitor works
```

#### Ticket A.3: Add Prometheus Cache Metrics (Optional)
```
Title: Add cache metrics to Prometheus
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/monitoring/metrics.py

Tasks:
1. Add cache_hits_total Counter
2. Add cache_misses_total Counter
3. Add cache_entry_age Histogram
4. Update __init__.py exports

Acceptance Criteria:
- [ ] Cache metrics visible in /metrics endpoint
```

### Phase B: Instrumentation

#### Ticket B.1: Instrument LLM Cache
```
Title: Add monitoring to llm_cache.py
Priority: High
Estimate: 20 minutes

File: src/catalyst_bot/llm_cache.py

Tasks:
1. Import cache monitor with fallback
2. Record hits with entry age
3. Record misses
4. Record evictions on TTL expiry

Acceptance Criteria:
- [ ] LLM cache hits/misses tracked
- [ ] Entry ages recorded correctly
```

#### Ticket B.2: Instrument Price Caches
```
Title: Add monitoring to price cache implementations
Priority: High
Estimate: 30 minutes

Files:
- src/catalyst_bot/trading/market_data.py
- src/catalyst_bot/market.py

Tasks:
1. Import cache monitor with fallback
2. Record hits/misses in both implementations
3. Calculate and report entry ages

Acceptance Criteria:
- [ ] Both price caches tracked
- [ ] Staleness detection working
```

#### Ticket B.3: Instrument SEC LLM Cache
```
Title: Add monitoring to sec_llm_cache.py
Priority: High
Estimate: 20 minutes

File: src/catalyst_bot/sec_llm_cache.py

Tasks:
1. Import cache monitor
2. Record hits/misses with ages
3. Record evictions

Acceptance Criteria:
- [ ] SEC cache tracked
```

#### Ticket B.4: Instrument Remaining Caches
```
Title: Add monitoring to fundamental, indicator, dedup caches
Priority: Medium
Estimate: 45 minutes

Files:
- src/catalyst_bot/fundamental_data.py
- src/catalyst_bot/indicators/cache.py
- src/catalyst_bot/seen_store.py
- src/catalyst_bot/dedup/first_seen_index.py

Tasks:
1. Add monitoring to each cache

Acceptance Criteria:
- [ ] All registered caches instrumented
```

### Phase C: Integration

#### Ticket C.1: Initialize on Bot Start
```
Title: Register caches on bot initialization
Priority: High
Estimate: 15 minutes

File: src/catalyst_bot/runner.py

Tasks:
1. Call register_default_caches() after health server
2. Make feature-flagged (FEATURE_CACHE_MONITORING)

Acceptance Criteria:
- [ ] Caches registered on startup
- [ ] Can be disabled via env var
```

#### Ticket C.2: Add to Heartbeat
```
Title: Display cache health in Discord heartbeat
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/runner.py

Tasks:
1. Call get_summary_for_heartbeat() in embed builder
2. Add as field to heartbeat embed

Acceptance Criteria:
- [ ] Cache health visible in heartbeat
- [ ] Shows critical issues prominently
```

#### Ticket C.3: Add to Health Endpoint
```
Title: Include cache report in /health/detailed
Priority: Medium
Estimate: 15 minutes

File: src/catalyst_bot/health_endpoint.py

Tasks:
1. Add get_health_report() to detailed response

Acceptance Criteria:
- [ ] /health/detailed includes cache stats
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_cache_monitor.py
import pytest

def test_cache_monitor_singleton():
    """Test singleton pattern."""
    from catalyst_bot.monitoring import CacheMonitor

    m1 = CacheMonitor()
    m2 = CacheMonitor()
    assert m1 is m2

def test_cache_registration():
    """Test cache registration."""
    from catalyst_bot.monitoring import get_cache_monitor

    monitor = get_cache_monitor()
    monitor.register_cache("test_cache", ttl_seconds=60, risk_level="low")

    assert "test_cache" in monitor._caches

def test_hit_miss_recording():
    """Test hit/miss tracking."""
    from catalyst_bot.monitoring import get_cache_monitor

    monitor = get_cache_monitor()
    monitor.register_cache("test_cache", ttl_seconds=60, risk_level="low")

    # Record some activity
    monitor.record_hit("test_cache", entry_age_seconds=10)
    monitor.record_hit("test_cache", entry_age_seconds=20)
    monitor.record_miss("test_cache")

    stats = monitor._stats["test_cache"]
    assert stats.hits == 2
    assert stats.misses == 1
    assert stats.hit_rate == pytest.approx(66.67, rel=0.1)

def test_staleness_detection():
    """Test stale hit detection."""
    from catalyst_bot.monitoring import get_cache_monitor

    monitor = get_cache_monitor()
    monitor.register_cache("test_cache", ttl_seconds=100, risk_level="high", soft_ttl_ratio=0.8)

    # Hit within soft TTL (80s)
    monitor.record_hit("test_cache", entry_age_seconds=70)

    # Hit exceeding soft TTL
    monitor.record_hit("test_cache", entry_age_seconds=90)

    stats = monitor._stats["test_cache"]
    assert stats.stale_hits == 1  # Only the 90s hit is stale

def test_health_report():
    """Test health report generation."""
    from catalyst_bot.monitoring import get_cache_monitor

    monitor = get_cache_monitor()
    report = monitor.get_health_report()

    assert 'timestamp' in report
    assert 'caches' in report
    assert 'summary' in report
    assert 'alerts' in report
```

### 2. Integration Test

```bash
# Test cache monitoring end-to-end
python -c "
from catalyst_bot.monitoring import get_cache_monitor, register_default_caches

# Register caches
register_default_caches()

monitor = get_cache_monitor()

# Simulate some activity
monitor.record_hit('llm_cache', 3600)
monitor.record_hit('llm_cache', 7200)
monitor.record_miss('llm_cache')
monitor.record_hit('price_cache_memory', 15)
monitor.record_hit('price_cache_memory', 25)

# Get report
report = monitor.get_health_report()
print('Health Report:')
print(f'  Total caches: {report[\"summary\"][\"total_caches\"]}')
print(f'  Healthy: {report[\"summary\"][\"healthy\"]}')
print(f'  Alerts: {len(report[\"alerts\"])}')

# Heartbeat summary
print()
print('Heartbeat Summary:')
print(monitor.get_summary_for_heartbeat())
"
```

### 3. Verify Prometheus Metrics

```bash
# After running bot with cache activity
curl -s http://localhost:9090/metrics | grep catalyst_bot_cache
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_CACHE_MONITORING` | `1` | Enable cache monitoring |

---

## Summary

This implementation provides:

1. **Unified Visibility** - All 17 caches monitored in one place
2. **Staleness Detection** - Automatic alerting when entries exceed soft TTL
3. **Health Reporting** - Summary in heartbeat, details in /health endpoint
4. **Prometheus Ready** - Metrics exposed if Prometheus enabled
5. **Low Overhead** - Minimal instrumentation, no new services

**Implementation Order:**
1. Phase A: Create cache monitor module (1.5 hours)
2. Phase B: Instrument critical caches (1 hour)
3. Phase C: Add to heartbeat and health endpoint (30 min)

**Expected Impact:**
- Early warning when caches serve stale data
- Visibility into cache effectiveness (hit rates)
- Proactive detection of cache configuration issues

---

**End of Implementation Guide**
