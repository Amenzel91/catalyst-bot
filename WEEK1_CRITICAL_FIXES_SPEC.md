# Week 1: Critical Stability Fixes - Implementation Specification
**Sprint Duration**: November 3-10, 2025
**Priority**: P0 - Data Corruption Prevention
**Agents**: 5 parallel specialist agents
**Estimated Effort**: 5-6 hours total

---

## Objectives

Fix 4 critical issues identified by code review that risk data corruption and silent failures:

1. **SeenStore SQLite race condition** → Database corruption under concurrent access
2. **SEC LLM Cache thread safety** → Cache corruption during batch processing
3. **asyncio.run() deadlock risk** → Silent failures in SEC analysis
4. **Price cache memory leak** → 10MB+ memory growth per day

---

## Agent Assignments

### Agent 1: SeenStore Thread Safety Specialist
- **Files**: `src/catalyst_bot/seen_store.py`
- **Time**: 2 hours
- **Complexity**: Medium

### Agent 2: SEC Cache Hardening Specialist
- **Files**: `src/catalyst_bot/sec_llm_cache.py`, `src/catalyst_bot/llm_usage_monitor.py`
- **Time**: 2 hours
- **Complexity**: Medium

### Agent 3: Runner Core Fixes Specialist
- **Files**: `src/catalyst_bot/runner.py`
- **Time**: 1 hour
- **Complexity**: Low

### Agent 4: Database Optimization Specialist
- **Files**: All SQLite modules (8 files)
- **Time**: 1 hour
- **Complexity**: Low (pattern replication)

### Agent 5: Testing & Integration Supervisor
- **Files**: Create 4 new test files
- **Time**: 2-3 hours (depends on agent completion)
- **Complexity**: Medium

---

## Detailed Agent Specifications

## AGENT 1: SeenStore Thread Safety Specialist

### Context
The `SeenStore` class manages deduplication state in SQLite. It's accessed from:
- Main runner loop (checking if items seen)
- Background threads (potentially)
- Multiple cycle iterations

**Current Problem**: Connection opened with `check_same_thread=False` but no locking mechanism, causing race conditions.

### Files to Modify
- `src/catalyst_bot/seen_store.py` (primary)

### Implementation Tasks

1. **Add Threading Lock**
```python
import threading

class SeenStore:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()  # NEW: Protect all database operations
        self._conn = None
        self._init_connection()
```

2. **Optimize Connection Initialization**
```python
def _init_connection(self):
    """Initialize connection with WAL mode and optimized pragmas."""
    self._conn = sqlite3.connect(str(self.cfg.path), timeout=30)

    # Enable WAL mode for better concurrency
    self._conn.execute("PRAGMA journal_mode=WAL")

    # Balance between safety and speed
    self._conn.execute("PRAGMA synchronous=NORMAL")

    # Increase cache size for better performance
    self._conn.execute("PRAGMA cache_size=10000")  # 10MB

    # Use memory for temp storage
    self._conn.execute("PRAGMA temp_store=MEMORY")

    log.info("seen_store_initialized path=%s wal_mode=enabled", self.cfg.path)
```

3. **Add Context Manager Support**
```python
def close(self):
    """Explicitly close connection."""
    if self._conn:
        try:
            self._conn.close()
            log.debug("seen_store_connection_closed")
        except Exception as e:
            log.warning("seen_store_close_error err=%s", str(e))
        finally:
            self._conn = None

def __enter__(self):
    """Context manager entry."""
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    """Context manager exit."""
    self.close()
    return False  # Don't suppress exceptions
```

4. **Protect All Database Operations with Lock**
```python
def is_seen(self, item_id: str) -> bool:
    """Check if item is seen (thread-safe)."""
    with self._lock:  # NEW: Thread-safe access
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1 FROM seen WHERE item_id = ? LIMIT 1", (item_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            log.error("is_seen_error item_id=%s err=%s", item_id, str(e), exc_info=True)
            return False  # Assume not seen on error (safer)

def mark_seen(self, item_id: str, timestamp: Optional[float] = None):
    """Mark item as seen (thread-safe)."""
    with self._lock:  # NEW: Thread-safe access
        try:
            if timestamp is None:
                timestamp = time.time()

            self._conn.execute(
                "INSERT OR IGNORE INTO seen (item_id, seen_at) VALUES (?, ?)",
                (item_id, timestamp)
            )
            self._conn.commit()
            log.debug("marked_seen item_id=%s", item_id)
        except Exception as e:
            log.error("mark_seen_error item_id=%s err=%s", item_id, str(e), exc_info=True)
            raise  # Re-raise for caller to handle
```

5. **Add Cleanup Method**
```python
def cleanup_old_entries(self, days_old: int = 30):
    """Remove entries older than N days (thread-safe)."""
    with self._lock:
        try:
            cutoff = time.time() - (days_old * 86400)
            cursor = self._conn.execute("DELETE FROM seen WHERE seen_at < ?", (cutoff,))
            deleted = cursor.rowcount
            self._conn.commit()
            log.info("seen_store_cleanup deleted=%d cutoff_days=%d", deleted, days_old)
            return deleted
        except Exception as e:
            log.error("cleanup_error err=%s", str(e), exc_info=True)
            return 0
```

### Configuration Changes
None required (internal optimization).

### Tests to Create
**File**: `tests/test_seen_store_concurrency.py`

```python
import pytest
import threading
import time
from pathlib import Path
from catalyst_bot.seen_store import SeenStore
from catalyst_bot.config import get_settings

def test_concurrent_is_seen_calls():
    """Test 100 concurrent is_seen() calls don't cause race conditions."""
    cfg = get_settings()
    store = SeenStore(cfg)

    # Pre-populate
    test_id = "concurrent_test_item"
    store.mark_seen(test_id)

    results = []
    errors = []

    def check_seen():
        try:
            results.append(store.is_seen(test_id))
        except Exception as e:
            errors.append(e)

    # Launch 100 concurrent threads
    threads = [threading.Thread(target=check_seen) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert all(results), "All threads should see the item"
    assert len(results) == 100, "All threads should complete"

    store.close()

def test_concurrent_mark_seen_calls():
    """Test 100 concurrent mark_seen() calls don't corrupt database."""
    cfg = get_settings()
    store = SeenStore(cfg)

    errors = []

    def mark_item(item_id):
        try:
            store.mark_seen(item_id)
        except Exception as e:
            errors.append(e)

    # Launch 100 concurrent threads with unique IDs
    threads = [threading.Thread(target=mark_item, args=(f"item_{i}",)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all items were marked
    for i in range(100):
        assert store.is_seen(f"item_{i}"), f"item_{i} should be marked"

    store.close()

def test_wal_mode_enabled():
    """Verify WAL mode is enabled on connection."""
    cfg = get_settings()
    store = SeenStore(cfg)

    cursor = store._conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]

    assert mode.upper() == "WAL", f"Expected WAL mode, got {mode}"

    store.close()

def test_context_manager():
    """Test context manager properly closes connection."""
    cfg = get_settings()

    with SeenStore(cfg) as store:
        store.mark_seen("context_test")
        assert store.is_seen("context_test")

    # Connection should be closed
    assert store._conn is None

def test_cleanup_old_entries():
    """Test cleanup removes old entries."""
    cfg = get_settings()
    store = SeenStore(cfg)

    # Add old entry (31 days ago)
    old_time = time.time() - (31 * 86400)
    store.mark_seen("old_item", timestamp=old_time)

    # Add recent entry
    store.mark_seen("recent_item")

    # Cleanup entries older than 30 days
    deleted = store.cleanup_old_entries(days_old=30)

    assert deleted >= 1, "Should delete at least old_item"
    assert not store.is_seen("old_item"), "Old item should be removed"
    assert store.is_seen("recent_item"), "Recent item should remain"

    store.close()
```

### Success Criteria
- ✅ All existing tests pass
- ✅ 5 new concurrency tests pass
- ✅ No database lock errors under load
- ✅ WAL mode enabled and verified
- ✅ Connection properly closed with context manager
- ✅ No breaking changes to API

---

## AGENT 2: SEC Cache Hardening Specialist

### Context
The SEC LLM cache stores analysis results in SQLite with 72-hour TTL. It's accessed from:
- Async batch processing (`batch_extract_keywords_from_documents`)
- Concurrent cache get/set operations during filing analysis
- Amendment invalidation logic

**Current Problem**: Creates new connection per operation inside lock, not thread-safe when multiple async tasks run concurrently.

### Files to Modify
1. `src/catalyst_bot/sec_llm_cache.py` (primary)
2. `src/catalyst_bot/llm_usage_monitor.py` (add Flash-Lite pricing)

### Implementation Tasks

1. **Add Proper Thread Locking**
```python
import threading

class SECLLMCache:
    def __init__(self, db_path: str = "data/cache/sec_llm_cache.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # NEW: Protect cache operations
        self._init_database()
        _logger.info("sec_llm_cache_initialized path=%s", self.db_path)
```

2. **Optimize Database Initialization**
```python
def _init_database(self):
    """Initialize database schema with WAL mode."""
    with sqlite3.connect(str(self.db_path), timeout=30) as conn:
        # Enable WAL mode for concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")

        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sec_llm_cache (
                cache_key TEXT PRIMARY KEY,
                filing_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                filing_type TEXT NOT NULL,
                analysis_result TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                hit_count INTEGER DEFAULT 0
            )
        """)

        # Optimize indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON sec_llm_cache(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_ticker_type ON sec_llm_cache(ticker, filing_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_filing ON sec_llm_cache(filing_id)")

        conn.commit()
        _logger.debug("sec_llm_cache_schema_initialized")
```

3. **Fix get_cached_sec_analysis with Thread Safety**
```python
def get_cached_sec_analysis(
    self, accession_number: str, filing_type: str
) -> Optional[dict]:
    """Retrieve cached SEC analysis result (thread-safe)."""
    with self._lock:  # NEW: Thread-safe access
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT analysis_result, created_at, hit_count
                    FROM sec_llm_cache
                    WHERE filing_id = ? AND filing_type = ? AND expires_at > ?
                """, (accession_number, filing_type, time.time()))

                row = cursor.fetchone()
                if row:
                    # Increment hit counter
                    cursor.execute("""
                        UPDATE sec_llm_cache
                        SET hit_count = hit_count + 1
                        WHERE filing_id = ? AND filing_type = ?
                    """, (accession_number, filing_type))
                    conn.commit()

                    _logger.info(
                        "sec_llm_cache_hit filing_id=%s type=%s age_hours=%.1f hit_count=%d",
                        accession_number, filing_type,
                        (time.time() - row["created_at"]) / 3600,
                        row["hit_count"] + 1
                    )

                    return json.loads(row["analysis_result"])
                else:
                    _logger.debug("sec_llm_cache_miss filing_id=%s type=%s", accession_number, filing_type)
                    return None

        except Exception as e:
            _logger.error("sec_llm_cache_get_error filing_id=%s err=%s", accession_number, str(e), exc_info=True)
            return None  # Treat errors as cache miss
```

4. **Fix cache_sec_analysis with Thread Safety**
```python
def cache_sec_analysis(
    self,
    accession_number: str,
    ticker: str,
    filing_type: str,
    analysis_result: dict,
    ttl_hours: int = 72
):
    """Store SEC analysis result in cache (thread-safe)."""
    with self._lock:  # NEW: Thread-safe access
        try:
            cache_key = f"{accession_number}_{filing_type}"
            now = time.time()
            expires_at = now + (ttl_hours * 3600)

            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO sec_llm_cache
                    (cache_key, filing_id, ticker, filing_type, analysis_result, created_at, expires_at, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    cache_key,
                    accession_number,
                    ticker,
                    filing_type,
                    json.dumps(analysis_result),
                    now,
                    expires_at
                ))
                conn.commit()

            _logger.info(
                "sec_llm_cache_stored filing_id=%s ticker=%s type=%s ttl_hours=%d",
                accession_number, ticker, filing_type, ttl_hours
            )

        except Exception as e:
            _logger.error(
                "sec_llm_cache_store_error filing_id=%s err=%s",
                accession_number, str(e), exc_info=True
            )
```

5. **Add Flash-Lite Pricing to llm_usage_monitor.py**
```python
# In llm_usage_monitor.py around line 108-134
PRICING = {
    "gemini": {
        "gemini-2.5-flash": {
            "input_per_million": 0.075,
            "output_per_million": 0.30,
        },
        "gemini-2.0-flash-lite": {  # NEW: Add Flash-Lite pricing
            "input_per_million": 0.02,
            "output_per_million": 0.10,
        },
        "gemini-1.5-flash": {
            "input_per_million": 0.075,
            "output_per_million": 0.30,
        },
        "gemini-2.5-pro": {
            "input_per_million": 1.25,
            "output_per_million": 5.00,
        },
    },
    # ... rest unchanged
}
```

### Configuration Changes
None required (internal optimization).

### Tests to Create
**File**: `tests/test_sec_cache_threading.py`

```python
import pytest
import threading
import json
from catalyst_bot.sec_llm_cache import SECLLMCache

def test_concurrent_cache_reads():
    """Test concurrent cache reads don't cause corruption."""
    cache = SECLLMCache(db_path="data/cache/test_sec_cache.db")

    # Pre-populate cache
    test_result = {"keywords": ["test"], "sentiment": 0.5}
    cache.cache_sec_analysis("test_filing", "TEST", "8-K", test_result)

    results = []
    errors = []

    def read_cache():
        try:
            result = cache.get_cached_sec_analysis("test_filing", "8-K")
            results.append(result)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=read_cache) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 50
    assert all(r == test_result for r in results)

def test_concurrent_cache_writes():
    """Test concurrent cache writes don't corrupt database."""
    cache = SECLLMCache(db_path="data/cache/test_sec_cache.db")

    errors = []

    def write_cache(filing_id, ticker):
        try:
            result = {"keywords": [ticker], "sentiment": 0.5}
            cache.cache_sec_analysis(filing_id, ticker, "8-K", result)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=write_cache, args=(f"filing_{i}", f"TICK{i}"))
        for i in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Errors: {errors}"

    # Verify all filings cached
    for i in range(50):
        result = cache.get_cached_sec_analysis(f"filing_{i}", "8-K")
        assert result is not None
        assert result["keywords"] == [f"TICK{i}"]

def test_wal_mode_enabled():
    """Verify WAL mode enabled."""
    cache = SECLLMCache(db_path="data/cache/test_sec_cache.db")

    import sqlite3
    conn = sqlite3.connect(str(cache.db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    conn.close()

    assert mode.upper() == "WAL"

def test_flash_lite_pricing_exists():
    """Verify Flash-Lite pricing added to monitor."""
    from catalyst_bot.llm_usage_monitor import PRICING

    assert "gemini-2.0-flash-lite" in PRICING["gemini"]
    assert PRICING["gemini"]["gemini-2.0-flash-lite"]["input_per_million"] == 0.02
```

### Success Criteria
- ✅ No database lock errors during batch processing
- ✅ All concurrent tests pass
- ✅ Flash-Lite costs tracked correctly
- ✅ Cache hit rate increases measurably
- ✅ No breaking changes

---

## AGENT 3: Runner Core Fixes Specialist

### Context
The main runner loop (`runner.py`) orchestrates all bot functionality. Issues:
1. `asyncio.run()` called without checking for existing event loop
2. Price cache (`_PX_CACHE`) never cleared, grows unbounded
3. No detection of feed outages (consecutive empty cycles)

### Files to Modify
- `src/catalyst_bot/runner.py`

### Implementation Tasks

1. **Fix asyncio.run() Deadlock Risk** (around line 1234)
```python
# Current code:
# sec_llm_cache = asyncio.run(batch_extract_keywords_from_documents(sec_filings_to_process))

# NEW: Safe async execution with loop detection
try:
    # Check if event loop already exists
    try:
        loop = asyncio.get_running_loop()
        # Already in async context, use await
        log.warning("async_loop_detected using_existing_loop=True")
        # This path shouldn't be hit in current codebase, but defensive
        sec_llm_results = await batch_extract_keywords_from_documents(sec_filings_to_process)
    except RuntimeError:
        # No loop exists, safe to use asyncio.run()
        log.debug("sec_batch_processing_start filings=%d", len(sec_filings_to_process))
        sec_llm_results = asyncio.run(
            batch_extract_keywords_from_documents(sec_filings_to_process)
        )
        log.info("sec_batch_processing_complete analyzed=%d cached=%d",
                 len(sec_llm_results), len(sec_filings_to_process) - len(sec_llm_results))
except Exception as e:
    log.error("sec_batch_processing_failed err=%s", str(e), exc_info=True)
    sec_llm_results = {}  # Fallback to empty results, don't crash cycle
```

2. **Clear Price Cache at Cycle End** (around line 2480)
```python
# At the end of _cycle() function, before returning

# Clear price cache to prevent memory leak
cache_size = len(_PX_CACHE)
if cache_size > 0:
    _PX_CACHE.clear()
    log.debug("price_cache_cleared entries=%d", cache_size)
```

3. **Add Network Failure Detection** (around line 1005)
```python
# Add at module level (near other globals like _PX_CACHE)
_CONSECUTIVE_EMPTY_CYCLES = 0
_MAX_EMPTY_CYCLES = int(os.getenv("ALERT_CONSECUTIVE_EMPTY_CYCLES", "5"))

# In _cycle() function after fetching feeds:
if not items or len(items) == 0:
    global _CONSECUTIVE_EMPTY_CYCLES
    _CONSECUTIVE_EMPTY_CYCLES += 1

    if _CONSECUTIVE_EMPTY_CYCLES >= _MAX_EMPTY_CYCLES:
        log.error(
            "feed_outage_detected consecutive_empty=%d max=%d",
            _CONSECUTIVE_EMPTY_CYCLES,
            _MAX_EMPTY_CYCLES
        )
        # Send admin alert
        try:
            from .alerts import send_admin_alert
            send_admin_alert(
                f"⚠️ Feed Outage Detected\n\n"
                f"No items fetched for {_CONSECUTIVE_EMPTY_CYCLES} consecutive cycles.\n"
                f"Check feed sources and network connectivity."
            )
        except Exception as e:
            log.warning("failed_to_send_outage_alert err=%s", str(e))
else:
    # Reset counter on successful fetch
    if _CONSECUTIVE_EMPTY_CYCLES > 0:
        log.info("feed_recovery detected after=%d empty_cycles", _CONSECUTIVE_EMPTY_CYCLES)
    _CONSECUTIVE_EMPTY_CYCLES = 0
```

4. **Add Basic Cycle Timing** (optional but recommended)
```python
# At start of _cycle():
cycle_start = time.perf_counter()

# After each major stage:
fetch_duration = time.perf_counter() - cycle_start
# ... classify ...
classify_duration = time.perf_counter() - cycle_start - fetch_duration
# ... enrich ...
enrich_duration = time.perf_counter() - cycle_start - fetch_duration - classify_duration

# At end of _cycle():
cycle_duration = time.perf_counter() - cycle_start
log.info(
    "cycle_timing total=%.2fs fetch=%.2fs classify=%.2fs enrich=%.2fs alert=%.2fs",
    cycle_duration,
    fetch_duration,
    classify_duration,
    enrich_duration,
    alert_duration
)
```

### Configuration Changes
Add to `.env.example`:
```bash
# Network Failure Detection (Week 1)
ALERT_CONSECUTIVE_EMPTY_CYCLES=5    # Alert after N consecutive empty cycles
```

### Tests to Create
**File**: `tests/test_runner_stability.py`

```python
import pytest
import asyncio
from unittest.mock import Mock, patch
from catalyst_bot.runner import _cycle, _PX_CACHE

def test_asyncio_loop_detection():
    """Test asyncio.run() doesn't deadlock with existing loop."""
    # This test would mock the SEC batch processing
    # and verify it doesn't raise RuntimeError
    pass  # Implementation would depend on refactoring for testability

def test_price_cache_cleared():
    """Test price cache is cleared at end of cycle."""
    # Pre-populate cache
    _PX_CACHE["TEST"] = (100.0, time.time())
    assert len(_PX_CACHE) > 0

    # Run cycle (mock dependencies)
    # ... cycle execution ...

    # Verify cache cleared
    assert len(_PX_CACHE) == 0

def test_consecutive_empty_cycle_detection():
    """Test alert fires after N empty cycles."""
    # Mock feed fetching to return empty
    with patch('catalyst_bot.feeds.fetch_pr_feeds', return_value=[]):
        # Run N+1 cycles
        for i in range(6):
            # ... run cycle ...
            pass

        # Verify alert was sent after 5th empty cycle
        # ... assertion ...
```

### Success Criteria
- ✅ No asyncio deadlocks in SEC processing
- ✅ Price cache memory stable over 100 cycles
- ✅ Empty cycle alerts fire correctly
- ✅ Cycle timing logged for performance analysis
- ✅ No breaking changes

---

## AGENT 4: Database Optimization Specialist

### Context
Multiple modules use SQLite without optimal configuration. Need to:
1. Enable WAL mode for concurrency
2. Add optimized pragmas for performance
3. Standardize connection initialization

### Files to Modify (8 files)
1. `src/catalyst_bot/dedupe.py`
2. `src/catalyst_bot/chart_cache.py`
3. `src/catalyst_bot/breakout_feedback.py`
4. `src/catalyst_bot/backtesting/database.py`
5. `src/catalyst_bot/feedback/database.py`
6. `src/catalyst_bot/storage.py`
7. `src/catalyst_bot/ticker_map.py`
8. Any other files with `sqlite3.connect()`

### Implementation Pattern

**Apply this pattern to ALL SQLite connections**:

```python
def _init_optimized_connection(db_path: str, timeout: int = 30) -> sqlite3.Connection:
    """
    Initialize SQLite connection with performance optimizations.

    Week 1 Optimization: Enable WAL mode and optimal pragmas.
    """
    conn = sqlite3.connect(db_path, timeout=timeout)

    # Enable WAL mode for better concurrency (configurable)
    if os.getenv("SQLITE_WAL_MODE", "1") == "1":
        conn.execute("PRAGMA journal_mode=WAL")

    # Balance between safety and speed
    synchronous_mode = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL")
    conn.execute(f"PRAGMA synchronous={synchronous_mode}")

    # Increase cache size (negative = KB, positive = pages)
    cache_size = int(os.getenv("SQLITE_CACHE_SIZE", "10000"))
    conn.execute(f"PRAGMA cache_size={cache_size}")

    # Enable memory-mapped I/O (30GB default)
    mmap_size = int(os.getenv("SQLITE_MMAP_SIZE", "30000000000"))
    conn.execute(f"PRAGMA mmap_size={mmap_size}")

    # Use memory for temporary tables
    conn.execute("PRAGMA temp_store=MEMORY")

    return conn
```

### Specific File Changes

**dedupe.py** (around line 129):
```python
# OLD:
self._conn = sqlite3.connect(db_path, timeout=10)

# NEW:
self._conn = _init_optimized_connection(db_path, timeout=30)
log.info("dedupe_db_initialized path=%s wal_mode=enabled", db_path)
```

**chart_cache.py** (around line 137):
```python
# OLD:
conn = sqlite3.connect(str(self.db_path), timeout=10)

# NEW:
conn = _init_optimized_connection(str(self.db_path), timeout=30)
log.info("chart_cache_initialized path=%s wal_mode=enabled", self.db_path)
```

**breakout_feedback.py** (around line 68):
```python
# OLD:
conn = sqlite3.connect(db_path, timeout=30)

# NEW:
conn = _init_optimized_connection(db_path, timeout=30)
```

**Repeat for all other files with SQLite connections.**

### Configuration Changes
Add to `.env.example`:
```bash
# SQLite Performance Optimization (Week 1)
SQLITE_WAL_MODE=1                    # Enable Write-Ahead Logging (1=on, 0=off)
SQLITE_SYNCHRONOUS=NORMAL            # FULL=safest, NORMAL=balanced, OFF=fastest
SQLITE_CACHE_SIZE=10000              # Cache size in pages (10000 pages ~40MB)
SQLITE_MMAP_SIZE=30000000000         # Memory-mapped I/O size in bytes (30GB)
```

### Tests to Create
**File**: `tests/test_database_performance.py`

```python
import pytest
import sqlite3
import time
from pathlib import Path

def test_wal_mode_enabled_dedupe():
    """Verify WAL mode enabled in dedupe.py."""
    from catalyst_bot.dedupe import FirstSeenIndex

    idx = FirstSeenIndex(db_path="data/test_dedupe.db")
    cursor = idx._conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    idx.close()

    assert mode.upper() == "WAL"

def test_wal_mode_enabled_chart_cache():
    """Verify WAL mode enabled in chart_cache.py."""
    from catalyst_bot.chart_cache import ChartCache

    cache = ChartCache()
    conn = sqlite3.connect(str(cache.db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    conn.close()

    assert mode.upper() == "WAL"

def test_read_performance_improvement():
    """Benchmark read performance with optimizations."""
    # Create test database
    db_path = "data/test_perf.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")
    conn.executemany("INSERT INTO test (data) VALUES (?)",
                     [(f"data_{i}",) for i in range(1000)])
    conn.commit()
    conn.close()

    # Benchmark without optimizations
    conn = sqlite3.connect(db_path)
    start = time.perf_counter()
    for _ in range(100):
        conn.execute("SELECT * FROM test WHERE id = ?", (500,)).fetchone()
    baseline_duration = time.perf_counter() - start
    conn.close()

    # Benchmark with optimizations
    from catalyst_bot.runner import _init_optimized_connection
    conn = _init_optimized_connection(db_path)
    start = time.perf_counter()
    for _ in range(100):
        conn.execute("SELECT * FROM test WHERE id = ?", (500,)).fetchone()
    optimized_duration = time.perf_counter() - start
    conn.close()

    # Should be at least marginally faster
    assert optimized_duration < baseline_duration * 1.2  # Allow 20% variance
```

### Success Criteria
- ✅ All 8+ database modules using optimized connections
- ✅ WAL mode enabled by default (configurable via env)
- ✅ Pragmas applied correctly
- ✅ Performance tests show improvement
- ✅ All existing tests still pass

---

## AGENT 5: Testing & Integration Supervisor

### Context
Supervise implementation of Agents 1-4, ensure all changes integrate properly, and create comprehensive test suite.

### Responsibilities

1. **Monitor Agent Progress**
   - Wait for Agents 1-4 to complete
   - Review code changes for correctness
   - Identify integration issues

2. **Create Test Files**
   - `tests/test_seen_store_concurrency.py` (Agent 1 tests)
   - `tests/test_sec_cache_threading.py` (Agent 2 tests)
   - `tests/test_runner_stability.py` (Agent 3 tests)
   - `tests/test_database_performance.py` (Agent 4 tests)

3. **Run Test Suite**
```bash
# Run all tests
pytest tests/ -v --tb=short --durations=10

# Run only Week 1 tests
pytest tests/test_seen_store_concurrency.py tests/test_sec_cache_threading.py tests/test_runner_stability.py tests/test_database_performance.py -v

# Run with coverage
pytest tests/ --cov=src/catalyst_bot --cov-report=html
```

4. **Run Pre-Commit Checks**
```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Expected to pass:
# - trailing-whitespace
# - end-of-file-fixer
# - check-yaml
# - check-added-large-files
# - python syntax checks
```

5. **Verify Integration**
   - SeenStore changes don't break runner
   - SEC cache changes don't break LLM integration
   - Database optimizations don't break existing queries
   - No circular import issues

6. **Update .env.example**
```bash
# Add at end of file:

##############################################################################
# Week 1: Critical Stability Fixes (2025-11-03)
##############################################################################

# SQLite Performance Optimization
SQLITE_WAL_MODE=1                    # Enable Write-Ahead Logging (1=on, 0=off)
SQLITE_SYNCHRONOUS=NORMAL            # FULL=safest, NORMAL=balanced, OFF=fastest
SQLITE_CACHE_SIZE=10000              # Cache size in pages (~40MB with default page size)
SQLITE_MMAP_SIZE=30000000000         # Memory-mapped I/O size in bytes (30GB default)

# Network Failure Detection
ALERT_CONSECUTIVE_EMPTY_CYCLES=5    # Alert admin after N consecutive empty feed cycles

# Note: All Week 1 changes are backward compatible and enabled by default
# To disable SQLite WAL mode: SQLITE_WAL_MODE=0
```

7. **Create Completion Report**

**File**: `WEEK1_COMPLETION_REPORT.md`

```markdown
# Week 1 Completion Report
**Date**: 2025-11-03
**Sprint**: Critical Stability Fixes
**Status**: [COMPLETE | IN_PROGRESS | BLOCKED]

## Agents Deployed

### Agent 1: SeenStore Thread Safety
- Status: [COMPLETE | IN_PROGRESS | BLOCKED]
- Files Modified: [list]
- Tests Added: [count]
- Tests Passing: [X/Y]
- Issues Found: [list]

### Agent 2: SEC Cache Hardening
- Status: [...]
- ...

### Agent 3: Runner Core Fixes
- Status: [...]
- ...

### Agent 4: Database Optimization
- Status: [...]
- ...

## Test Results

### Existing Tests
- Total: [count]
- Passing: [count]
- Failing: [count]
- Details: [any failures]

### New Tests (Week 1)
- Total: 12+
- Passing: [count]
- Failing: [count]
- Coverage: [percentage]

### Pre-Commit Checks
- Status: [PASS | FAIL]
- Issues: [list if any]

## Performance Baselines

### Feed Fetch Time
- Before: [measure]
- After: [measure]
- Improvement: [percentage]

### Cycle Duration
- Before: [measure]
- After: [measure]
- Improvement: [percentage]

### Memory Usage
- Before: [measure]
- After: [measure]
- Improvement: [percentage]

### Database Query Time (P95)
- Before: [measure]
- After: [measure]
- Improvement: [percentage]

## Issues Found

[List any issues discovered during implementation]

## Breaking Changes

[None expected, but document if any]

## Recommendations for Week 2

[Based on Week 1 findings]

## Sign-Off

- [ ] All critical fixes implemented
- [ ] All tests passing
- [ ] Pre-commit checks passing
- [ ] .env.example updated
- [ ] No breaking changes
- [ ] Ready for production deployment

**Supervisor**: Claude Testing Agent
**Date**: 2025-11-03
```

### Success Criteria
- ✅ All 4 agent implementations reviewed
- ✅ 12+ new tests created and passing
- ✅ All existing tests still passing (30+)
- ✅ Pre-commit checks passing
- ✅ .env.example properly documented
- ✅ Completion report generated
- ✅ No integration issues found

---

## Deployment Instructions

### Step 1: Deploy Agents in Parallel
```
Launch all 5 agents simultaneously via Task tool
```

### Step 2: Monitor Progress
```
Check agent outputs as they complete
Verify each agent's success criteria
```

### Step 3: Integration Testing
```
Agent 5 runs full test suite
Verifies integration
Generates report
```

### Step 4: Final Validation
```
Run bot for 1 hour
Monitor for crashes or errors
Check memory stability
```

### Step 5: Documentation
```
Update .env.example
Generate completion report
Commit all changes
```

---

## Success Metrics

### Must Pass
- 0 database corruption errors
- 0 asyncio deadlocks
- Memory stable over 100 cycles
- All 30+ existing tests passing
- All 12+ new tests passing
- Pre-commit checks passing

### Performance Targets
- Price cache memory: <1MB growth per hour
- No database lock errors under concurrent access
- Feed outages detected within 5 cycles

---

## Rollback Plan

If any critical issues found:
1. Identify problematic agent's changes
2. Revert specific files via git
3. Disable optimizations via env vars if needed
4. All changes are backward compatible
5. No database migrations required

---

**Document Version**: 1.0
**Last Updated**: 2025-11-03
**Owner**: Supervisor Agent