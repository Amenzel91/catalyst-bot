# Implementation Ticket: Make SeenStore Async-Safe for Pre-Filtering

## Title
Make SeenStore async-safe using thread-local connections to enable pre-filtering in feeds.py

## Priority
**P2 (High)**

## Estimated Effort
**4 hours**

## Problem Statement

The `SeenStore` class currently uses a single SQLite connection (`self._conn`) that is created in the main thread during `__init__`. This causes failures when the store is accessed from async contexts or different threads.

**Current Error:**
```
sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread
```

**Current Situation:**
- The pre-filter code in `/home/user/catalyst-bot/src/catalyst_bot/feeds.py` (lines 1146-1158) is **commented out** due to this issue
- The commented code would skip enrichment for 70-80% of duplicate SEC filings before LLM processing
- This represents a **7-8 minute time savings per cycle** that is currently lost

**Impact:**
- Wasted API calls on duplicate SEC filings (100+ per cycle)
- Extended processing time due to unnecessary LLM enrichment calls
- Inability to detect and skip already-processed filings in async contexts

## Solution Overview

Implement **thread-local storage** using Python's `threading.local()` to maintain one SQLite connection per thread. This approach:

1. Creates a unique connection for each thread that accesses the store
2. Ensures SQLite's "same-thread" requirement is always satisfied
3. Maintains backward compatibility with existing lock-based synchronization
4. Supports both synchronous and asynchronous call contexts

## Files to Modify

1. **`/home/user/catalyst-bot/src/catalyst_bot/seen_store.py`** - Primary implementation
2. **`/home/user/catalyst-bot/src/catalyst_bot/feeds.py`** - Re-enable pre-filter (lines 1146-1158)

## Implementation Steps

### Step 1: Update SeenStore.__init__() (seen_store.py, lines 56-68)

**Current code:**
```python
def __init__(self, config: Optional[SeenStoreConfig] = None):
    if config is None:
        path = Path(os.getenv("SEEN_DB_PATH", "data/seen_ids.sqlite"))
        ttl = int(os.getenv("SEEN_TTL_DAYS", "7"))
        config = SeenStoreConfig(path=path, ttl_days=ttl)

    self.cfg = config
    self.cfg.path.parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._conn = None
    self._init_connection()
    self._ensure_schema()
    self.purge_expired()
```

**Replace with:**
```python
def __init__(self, config: Optional[SeenStoreConfig] = None):
    if config is None:
        path = Path(os.getenv("SEEN_DB_PATH", "data/seen_ids.sqlite"))
        ttl = int(os.getenv("SEEN_TTL_DAYS", "7"))
        config = SeenStoreConfig(path=path, ttl_days=ttl)

    self.cfg = config
    self.cfg.path.parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._thread_local = threading.local()  # Thread-local storage for connections
    self._init_schema()
    self.purge_expired()
```

### Step 2: Add _get_connection() method (seen_store.py, after line 68)

**New method to add:**
```python
def _get_connection(self) -> sqlite3.Connection:
    """
    Get a thread-local SQLite connection.

    Creates a new connection for each thread on first access, ensuring
    SQLite's "same-thread" requirement is always satisfied.
    """
    if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None:
        from catalyst_bot.storage import init_optimized_connection

        self._thread_local.conn = init_optimized_connection(
            str(self.cfg.path), timeout=30
        )
        log.debug(
            "seen_store_thread_connection_created thread_id=%s",
            threading.current_thread().ident
        )

    return self._thread_local.conn
```

### Step 3: Add _init_schema() method (seen_store.py)

**Replace _init_connection() with:**
```python
def _init_schema(self) -> None:
    """Initialize database schema in the main thread."""
    conn = self._get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                id TEXT PRIMARY KEY,
                ts INTEGER NOT NULL
            )
            """
        )
        conn.commit()
        log.info("seen_store_initialized path=%s wal_mode=enabled", self.cfg.path)
    except Exception as e:
        log.error("seen_store_schema_init_failed err=%s", str(e), exc_info=True)
        raise
```

### Step 4: Update is_seen() method (seen_store.py, lines 130-142)

**Replace with:**
```python
def is_seen(self, item_id: str) -> bool:
    """Check if item is seen (thread-safe across async and sync contexts)."""
    with self._lock:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM seen WHERE id = ? LIMIT 1", (item_id,))
            row = cur.fetchone()
            return row is not None
        except Exception as e:
            log.error(
                "is_seen_error item_id=%s err=%s thread_id=%s",
                item_id, str(e), threading.current_thread().ident,
                exc_info=True
            )
            return False
```

### Step 5: Update mark_seen() method (seen_store.py, lines 144-161)

**Replace with:**
```python
def mark_seen(self, item_id: str, ts: Optional[int] = None) -> None:
    """Mark item as seen (thread-safe across async and sync contexts)."""
    ts = int(time.time()) if ts is None else int(ts)

    with self._lock:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO seen(id, ts) VALUES(?, ?)",
                (item_id, ts),
            )
            conn.commit()
            log.debug("marked_seen item_id=%s", item_id[:80])
        except Exception as e:
            log.error(
                "mark_seen_error item_id=%s err=%s thread_id=%s",
                item_id, str(e), threading.current_thread().ident,
                exc_info=True
            )
            raise
```

### Step 6: Update close() method (seen_store.py, lines 94-106)

**Replace with:**
```python
def close(self) -> None:
    """Close all thread-local connections and truncate WAL files."""
    try:
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn:
            conn = self._thread_local.conn
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
                log.debug("seen_store_connection_closed wal_truncated=true")
            except Exception as e:
                log.warning("seen_store_close_error err=%s", str(e))
            finally:
                self._thread_local.conn = None
    except Exception as e:
        log.warning("seen_store_close_cleanup_error err=%s", str(e))
```

### Step 7: Un-comment pre-filter code in feeds.py (lines 1146-1158)

**Replace commented code with:**
```python
# Pre-filter already-seen filings using async-safe seen_store
if seen_store:
    for filing in sec_items:
        filing_id = filing.get("id") or filing.get("link") or ""
        try:
            if filing_id and seen_store.is_seen(filing_id):
                skipped_seen += 1
                continue
        except Exception as e:
            log.warning(
                "seen_store_check_failed filing_id=%s err=%s",
                filing_id[:60] if filing_id else "",
                str(e)
            )
            pass
        items_to_enrich.append(filing)
else:
    items_to_enrich = sec_items
```

## Test Verification

### Manual Testing

**1. Basic Functionality Test:**
```python
from src.catalyst_bot.seen_store import SeenStore
store = SeenStore()
store.mark_seen('test_id_1')
assert store.is_seen('test_id_1'), 'Same thread check failed'
print('✓ Test passed: Same-thread operations work')
store.close()
```

**2. Multi-threaded Test:**
```python
import threading
from src.catalyst_bot.seen_store import SeenStore

store = SeenStore()
results = []

def thread_func(thread_id):
    item_id = f'test_id_{thread_id}'
    store.mark_seen(item_id)
    is_seen = store.is_seen(item_id)
    results.append((thread_id, is_seen))

threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()

for tid, seen in results:
    assert seen, f'Thread {tid} check failed'
print(f'✓ Test passed: All {len(results)} threads work correctly')
store.close()
```

**3. Async Context Test:**
```python
import asyncio
from src.catalyst_bot.seen_store import SeenStore

store = SeenStore()

async def async_func(item_id):
    store.mark_seen(item_id)
    return store.is_seen(item_id)

async def main():
    results = await asyncio.gather(
        async_func('async_1'),
        async_func('async_2'),
        async_func('async_3')
    )
    assert all(results), 'Async tests failed'
    print(f'✓ Test passed: Async contexts work ({len(results)} items)')

asyncio.run(main())
store.close()
```

### Expected Behavior After Fix

1. **No "SQLite objects created in a thread" errors** when `is_seen()` is called from async contexts
2. **Pre-filter logs show skipped filings:**
   ```
   sec_llm_batch_start total_filings=150 skipped_seen=120 to_enrich=30 max_concurrent=3
   ```
3. **7-8 minute time savings per cycle** due to skipped LLM enrichment calls

## Rollback Procedure

**1. Revert the code changes:**
```bash
git checkout HEAD -- src/catalyst_bot/seen_store.py src/catalyst_bot/feeds.py
```

**2. Re-comment the pre-filter code** in feeds.py (lines 1146-1158)

**3. Restart the service**

## Dependencies

- **Python stdlib:** `threading`, `sqlite3` (already available)
- **Internal:** `catalyst_bot.storage.init_optimized_connection()` (already exists)
- **No external package changes required**

## Risk Assessment

**Risk Level: MEDIUM**

### Positive Factors:
- Thread-local storage is a standard Python pattern
- `threading.local()` is well-tested and widely used
- Existing lock-based synchronization is retained
- No changes to database schema or file format

### Potential Risks:
1. Memory usage: Each thread gets its own connection (mitigated: typically 1-2 threads)
2. Connection cleanup in long-running threads (mitigated by `close()` method)

### Mitigation:
- Use included test suite to verify functionality
- Monitor for "seen_store_thread_connection_created" logs
- Gradual rollout to staging environment first

## Success Criteria

- [ ] No "SQLite objects created in a thread" errors in logs
- [ ] Pre-filter correctly skips 70-80% of duplicate SEC filings
- [ ] `sec_llm_batch_start` logs show `skipped_seen >= 100` on typical runs
- [ ] Processing time per cycle reduced by 7-8 minutes
- [ ] All automated tests pass
