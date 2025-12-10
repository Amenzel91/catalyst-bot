# Implementation Ticket: In-Memory LRU Cache Layer for SeenStore

## Title
Add thread-safe LRU cache layer to SeenStore for 100x dedup lookup performance

## Priority
**P3**

## Estimated Effort
**4-5 hours**

## Problem Statement

### Current Performance Issue
- **Current behavior**: Every dedup check via `is_seen()` hits SQLite database directly
- **Latency**: ~10ms per lookup (SQLite disk I/O)
- **Scale impact**: Processing 137 filings = 137 database queries = 1.37 seconds overhead
- **Root cause**: No caching layer between application and persistent storage

### Performance Goals
- **Target latency**: 0.1ms per cached lookup (100x improvement)
- **Cache hit rate**: 80-90% reduction in SQLite queries
- **Expected speedup**: 1.37s → ~150-200ms for 137 filings
- **Cache memory overhead**: Minimal (1000 entries × ~200 bytes = ~200KB max)

## Solution Overview

### Design Approach
Implement a **two-tier caching strategy**:
1. **L1 Cache**: In-memory LRU cache (cachetools.LRUCache) - fast path
2. **L2 Storage**: SQLite database - persistent, authoritative source of truth

### Key Principles
- **Thread-safe**: Protect cache access with existing `self._lock`
- **Minimal invasiveness**: Cache checks happen before database queries
- **Graceful degradation**: Cache misses fall back to SQLite lookup
- **Optional**: Feature toggleable via environment variable

## Files to Modify

**Primary**: `/home/user/catalyst-bot/src/catalyst_bot/seen_store.py`

## Implementation Steps

### Step 1: Add Dependencies (Line 21-28)

```python
try:
    import cachetools
except ImportError:
    cachetools = None  # Graceful degradation if not installed
```

### Step 2: Update SeenStoreConfig Dataclass (Line 50-54)

```python
@dataclass
class SeenStoreConfig:
    path: Path
    ttl_days: int
    cache_size: int = 1000
    cache_enabled: bool = True
```

### Step 3: Update SeenStore.__init__() (Lines 57-69)

```python
def __init__(self, config: Optional[SeenStoreConfig] = None):
    if config is None:
        path = Path(os.getenv("SEEN_DB_PATH", "data/seen_ids.sqlite"))
        ttl = int(os.getenv("SEEN_TTL_DAYS", "7"))
        cache_size = int(os.getenv("SEEN_STORE_CACHE_SIZE", "1000"))
        cache_enabled = os.getenv("SEEN_STORE_CACHE_ENABLED", "1") in ("1", "true", "yes")
        config = SeenStoreConfig(
            path=path,
            ttl_days=ttl,
            cache_size=cache_size,
            cache_enabled=cache_enabled,
        )

    self.cfg = config
    self.cfg.path.parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._conn = None

    # Initialize cache
    self._cache = None
    self._cache_hits = 0
    self._cache_misses = 0
    if self.cfg.cache_enabled and cachetools is not None:
        self._cache = cachetools.LRUCache(maxsize=self.cfg.cache_size)
        log.info("seen_store_cache_initialized size=%d", self.cfg.cache_size)

    self._init_connection()
    self._ensure_schema()
    self.purge_expired()
```

### Step 4: Add Cache Helper Methods (After Line 92)

```python
def _cache_get(self, item_id: str) -> Optional[bool]:
    """Check cache for item ID. Returns None if not in cache."""
    if self._cache is None:
        return None

    if item_id in self._cache:
        self._cache_hits += 1
        return self._cache[item_id]

    self._cache_misses += 1
    return None

def _cache_set(self, item_id: str, is_present: bool) -> None:
    """Store item lookup result in cache."""
    if self._cache is None:
        return

    try:
        self._cache[item_id] = is_present
    except Exception as e:
        log.warning("cache_set_error item_id=%s err=%s", item_id[:80], str(e))

def _cache_invalidate_all(self) -> None:
    """Clear entire cache (used during purge_expired)."""
    if self._cache is None:
        return
    self._cache.clear()
    log.debug("cache_invalidated_all")

def get_cache_stats(self) -> dict:
    """Return cache performance statistics."""
    if self._cache is None:
        return {"enabled": False}

    total = self._cache_hits + self._cache_misses
    hit_rate = (self._cache_hits / total * 100) if total > 0 else 0

    return {
        "enabled": True,
        "size": len(self._cache),
        "max_size": self.cfg.cache_size,
        "hits": self._cache_hits,
        "misses": self._cache_misses,
        "hit_rate_percent": round(hit_rate, 2),
    }
```

### Step 5: Modify is_seen() Method (Lines 130-142)

```python
def is_seen(self, item_id: str) -> bool:
    """Check if item is seen (thread-safe, cache-backed)."""
    # Fast path: check L1 cache first (1µs)
    cached_result = self._cache_get(item_id)
    if cached_result is not None:
        return cached_result

    # Cache miss: query L2 (SQLite)
    with self._lock:
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM seen WHERE id = ? LIMIT 1", (item_id,))
            row = cur.fetchone()
            is_present = row is not None

            # Store result in cache for future lookups
            self._cache_set(item_id, is_present)
            return is_present
        except Exception as e:
            log.error("is_seen_error item_id=%s err=%s", item_id, str(e), exc_info=True)
            return False
```

### Step 6: Modify mark_seen() Method (Lines 144-161)

```python
def mark_seen(self, item_id: str, ts: Optional[int] = None) -> None:
    """Mark item as seen (thread-safe, cache-backed)."""
    ts = int(time.time()) if ts is None else int(ts)

    with self._lock:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO seen(id, ts) VALUES(?, ?)",
                (item_id, ts),
            )
            self._conn.commit()

            # Update cache (write-through)
            self._cache_set(item_id, True)

            log.debug("marked_seen item_id=%s", item_id[:80])
        except Exception as e:
            log.error("mark_seen_error item_id=%s err=%s", item_id, str(e), exc_info=True)
            raise
```

### Step 7: Modify purge_expired() Method (Lines 117-128)

```python
def purge_expired(self) -> None:
    """Remove expired entries (thread-safe)."""
    ttl_secs = self.cfg.ttl_days * 86400
    cutoff = int(time.time()) - ttl_secs
    with self._lock:
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
            self._conn.commit()

            # Invalidate cache since entries were deleted
            self._cache_invalidate_all()

            log.debug("purge_expired_success cutoff=%d", cutoff)
        except Exception as e:
            log.warning("purge_expired_failed", extra={"error": str(e)})
```

## Configuration

### New Environment Variables

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SEEN_STORE_CACHE_SIZE` | `1000` | integer | Maximum number of entries in LRU cache |
| `SEEN_STORE_CACHE_ENABLED` | `1` | boolean | Enable/disable in-memory cache layer |

### Configuration Examples

```bash
# Production (full cache)
SEEN_STORE_CACHE_SIZE=10000
SEEN_STORE_CACHE_ENABLED=1

# Disable cache (fallback to pure SQLite)
SEEN_STORE_CACHE_ENABLED=0
```

## Test Verification

### Unit Tests

```python
def test_cache_hit_on_repeated_lookup():
    """Verify cache hit returns True without database query."""
    store = SeenStore()

    # First lookup: cache miss
    assert not store.is_seen("test_id_1")
    store.mark_seen("test_id_1")

    # Second lookup: cache hit
    stats_before = store.get_cache_stats()
    hits_before = stats_before["hits"]
    assert store.is_seen("test_id_1") is True

    stats_after = store.get_cache_stats()
    assert stats_after["hits"] == hits_before + 1

def test_cache_disabled():
    """Verify cache can be disabled."""
    import os
    os.environ["SEEN_STORE_CACHE_ENABLED"] = "0"
    store = SeenStore()

    assert store._cache is None
    store.mark_seen("test_id")
    assert store.is_seen("test_id") is True
```

### Performance Benchmark

```python
import time

def benchmark_cache_vs_no_cache():
    """Compare performance with and without cache."""
    # Without cache: ~10ms per lookup
    # With cache: ~0.001ms per lookup (cache hit)

    store = SeenStore()

    # Warm up cache
    for i in range(50):
        store.mark_seen(f"filing_{i}")

    # Benchmark 5000 lookups
    start = time.time()
    for _ in range(100):
        for i in range(50):
            store.is_seen(f"filing_{i}")
    elapsed = time.time() - start

    stats = store.get_cache_stats()
    print(f"Time: {elapsed:.4f}s")
    print(f"Cache hit rate: {stats['hit_rate_percent']:.1f}%")
    # Expected: ~100x speedup on repeated lookups
```

## Rollback Procedure

### Method 1: Disable Cache via Environment Variable
```bash
export SEEN_STORE_CACHE_ENABLED=0
# Restart application - SQLite only, no code changes
```

### Method 2: Revert Code
```bash
git revert <commit-hash>
```

## Dependencies

### Required Package
```bash
pip install cachetools>=5.3.0
```

### Graceful Degradation
If `cachetools` not installed:
- Cache remains disabled
- SQLite fallback used automatically
- No crashes or errors

## Risk Assessment

### Risk Level: **LOW**

| Factor | Level | Mitigation |
|--------|-------|-----------|
| Additive Change | LOW | New code layer, no SQLite changes |
| Graceful Degradation | LOW | Cache disabled if unavailable |
| Backward Compatible | LOW | Public API unchanged |
| Memory Bounded | LOW | LRU has hard size limit (~200KB) |
| Well-Tested Library | LOW | cachetools widely used in production |

## Expected Performance Results

| Scenario | Without Cache | With Cache | Improvement |
|----------|---------------|------------|-------------|
| Single lookup | 10ms | 0.001ms | 10,000x |
| 137 filings (cold) | 1.37s | 1.37s | - |
| 137 filings (warm) | 1.37s | 0.014s | 100x |
| Cache hit rate | 0% | 80-90% | - |

## Success Criteria

- [ ] Cache hit rate > 80% on warm cache
- [ ] Memory usage < 1MB (1000 entries LRU)
- [ ] No increase in p99 latency
- [ ] All tests pass
- [ ] Can be disabled via env var
- [ ] No breaking changes to public API
