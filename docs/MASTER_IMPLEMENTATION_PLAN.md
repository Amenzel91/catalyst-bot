# Catalyst-Bot Master Implementation Plan

**Document Version:** 1.0
**Created:** 2025-12-06
**Purpose:** Comprehensive guide for CLI-based implementation of all pending patches and fixes
**Target Audience:** Claude Code, Codex, and other AI coding assistants

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Dependency Graph](#dependency-graph)
3. [Critical Path Fixes (BLOCKING)](#critical-path-fixes-blocking)
4. [High Priority Fixes](#high-priority-fixes)
5. [Medium Priority Enhancements](#medium-priority-enhancements)
6. [Future Enhancements](#future-enhancements)
7. [Testing Strategy](#testing-strategy)
8. [Rollback Procedures](#rollback-procedures)
9. [Sources & References](#sources--references)

---

## Executive Summary

This document provides a step-by-step implementation guide for all pending patches identified in the Catalyst-Bot codebase. Each section includes:

- **Prerequisites**: What must be completed first
- **Files to Modify**: Exact paths and line numbers
- **Code Changes**: Annotated snippets with integration points
- **Testing**: Unit tests and verification commands
- **Rollback**: How to revert if issues arise

### Priority Levels

| Priority | Description | Estimated Items |
|----------|-------------|-----------------|
| **CRITICAL** | Blocking deployment, syntax errors, deprecations | 4 fixes |
| **HIGH** | Stability, performance, core functionality | 8 fixes |
| **MEDIUM** | Code quality, optimizations | 6 fixes |
| **LOW** | Future enhancements, nice-to-haves | 10+ features |

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CRITICAL PATH                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [1] UTF-8 BOM Fix ──────┐                                          │
│      (feeds.py)          │                                          │
│                          ▼                                          │
│  [2] datetime.utcnow() ──┼──► [4] Dedup Hash Fix                    │
│      (12 files)          │        (dedupe.py)                       │
│                          │            │                              │
│  [3] Thread Safety ──────┘            │                              │
│      (vwap_calculator.py)             ▼                              │
│                               [5] Test Suite Pass                    │
│                                       │                              │
├───────────────────────────────────────┼─────────────────────────────┤
│                        HIGH PRIORITY  │                              │
│                                       ▼                              │
│  [6] LLM Batching ◄────────── [7] Heartbeat Cumulative              │
│      (llm_client.py)              (runner.py)                       │
│          │                            │                              │
│          ▼                            ▼                              │
│  [8] SEC LLM Summarization    [9] Pre-Market Coverage               │
│      (feeds.py, llm_chain.py)     (runner.py)                       │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                        MEDIUM PRIORITY                               │
│                                                                      │
│  [10] Print → Logging         [11] CSV Encoding Safety              │
│       (45 files)                   (train_ml.py)                    │
│                                                                      │
│  [12] Hash Algorithm Upgrade  [13] Global Variable Audit            │
│       (dedupe.py)                  (multiple files)                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Critical Path Fixes (BLOCKING)

### CRITICAL-1: UTF-8 BOM Removal

**Priority:** CRITICAL
**Estimated Time:** 5 minutes
**Prerequisites:** None
**Blocks:** All other fixes (file must parse correctly)

#### Problem Description

Three files contain UTF-8 BOM (Byte Order Mark) characters that can cause:
- JSON parsing failures
- Import errors in Python
- YAML configuration loading issues

#### Files Affected

| File | Status |
|------|--------|
| `src/catalyst_bot/feeds.py` | BOM detected |
| `test_closed_loop.py` | BOM detected |
| `tests/test_market_fallback.py` | BOM detected |

#### Implementation

**Option A: Python Script (Recommended)**

Create and run this one-time fix script:

```python
#!/usr/bin/env python3
"""
Remove UTF-8 BOM from affected files.
Run from project root: python fix_bom.py
"""
from pathlib import Path

FILES_WITH_BOM = [
    "src/catalyst_bot/feeds.py",
    "test_closed_loop.py",
    "tests/test_market_fallback.py",
]

def remove_bom(file_path: str) -> bool:
    """Remove BOM if present. Returns True if BOM was removed."""
    path = Path(file_path)
    if not path.exists():
        print(f"  SKIP: {file_path} (not found)")
        return False

    content = path.read_bytes()

    # UTF-8 BOM is: 0xEF 0xBB 0xBF
    if content.startswith(b'\xef\xbb\xbf'):
        # Remove BOM and write back
        path.write_bytes(content[3:])
        print(f"  FIXED: {file_path}")
        return True
    else:
        print(f"  OK: {file_path} (no BOM)")
        return False

if __name__ == "__main__":
    print("Removing UTF-8 BOM from files...")
    fixed = sum(remove_bom(f) for f in FILES_WITH_BOM)
    print(f"\nDone. Fixed {fixed} file(s).")
```

**Option B: Manual Command**

```bash
# For each file, run:
python -c "
import sys
with open(sys.argv[1], 'rb') as f:
    content = f.read()
if content.startswith(b'\xef\xbb\xbf'):
    with open(sys.argv[1], 'wb') as f:
        f.write(content[3:])
    print('BOM removed')
else:
    print('No BOM found')
" src/catalyst_bot/feeds.py
```

#### Verification

```bash
# Verify files compile without errors
python -m py_compile src/catalyst_bot/feeds.py
python -m py_compile test_closed_loop.py
python -m py_compile tests/test_market_fallback.py

# Check for BOM (should return nothing)
head -c 3 src/catalyst_bot/feeds.py | xxd | grep -i "efbbbf"
```

#### Rollback

```bash
# If issues arise, restore from git
git checkout HEAD -- src/catalyst_bot/feeds.py
git checkout HEAD -- test_closed_loop.py
git checkout HEAD -- tests/test_market_fallback.py
```

---

### CRITICAL-2: datetime.utcnow() Deprecation Fix

**Priority:** CRITICAL
**Estimated Time:** 30 minutes
**Prerequisites:** CRITICAL-1 (BOM fix)
**Blocks:** Python 3.12+ compatibility

#### Problem Description

`datetime.utcnow()` is deprecated in Python 3.12 and will be removed in a future version. It returns "naive" datetime objects without timezone info, which can cause subtle bugs when comparing datetimes.

**Industry Best Practice:** Use `datetime.now(timezone.utc)` which returns timezone-aware objects.

> **Source:** [Miguel Grinberg - datetime.utcnow() Is Now Deprecated](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated)

#### Files Affected (12 files, 15+ instances)

| File | Line(s) | Context |
|------|---------|---------|
| `apply_safe_recommendations.py` | 90, 100, 116 | Timestamp for reports |
| `jobs/finviz_filings.py` | 77 | Filing cutoff date |
| `src/catalyst_bot/store.py` | 73 | Rolling 24h window |
| `src/catalyst_bot/sec_stream.py` | 117 | Fallback timestamp |
| `src/catalyst_bot/quickchart_post.py` | 123 | Chart filename |
| `src/catalyst_bot/sentiment_sources.py` | 747 | Analyst tracking |
| `src/catalyst_bot/watchlist_cascade.py` | 27 | Decay calculation |
| `src/catalyst_bot/trading/signal_generator.py` | 271, 350 | Signal timestamp |
| `src/catalyst_bot/rag_system.py` | 336 | Filing chunk |
| `src/catalyst_bot/learning.py` | 54 | Weight initialization |
| `src/catalyst_bot/charts_advanced.py` | 673 | Chart output filename |

#### Implementation Pattern

**Before (Deprecated):**
```python
from datetime import datetime

# This is deprecated and returns naive datetime
now = datetime.utcnow()
timestamp = datetime.utcnow().isoformat()
```

**After (Correct):**
```python
from datetime import datetime, timezone

# Returns timezone-aware datetime (recommended)
now = datetime.now(timezone.utc)
timestamp = datetime.now(timezone.utc).isoformat()

# For Python 3.11+, you can also use:
# now = datetime.now(datetime.UTC)
```

#### Detailed Changes

**File: `src/catalyst_bot/store.py` (Line 73)**

```python
# BEFORE:
def rolling_last24(self) -> List[Dict]:
    """Get items from the last 24 hours."""
    now = datetime.utcnow()  # ❌ Deprecated
    cutoff = now - timedelta(hours=24)
    # ...

# AFTER:
from datetime import datetime, timezone, timedelta

def rolling_last24(self) -> List[Dict]:
    """Get items from the last 24 hours."""
    now = datetime.now(timezone.utc)  # ✅ Timezone-aware
    cutoff = now - timedelta(hours=24)
    # ...
```

**File: `src/catalyst_bot/watchlist_cascade.py` (Line 27)**

```python
# BEFORE:
def calculate_decay(self, ticker: str) -> float:
    now = datetime.utcnow()  # ❌ Deprecated
    # ...

# AFTER:
from datetime import datetime, timezone

def calculate_decay(self, ticker: str) -> float:
    now = datetime.now(timezone.utc)  # ✅ Timezone-aware
    # ...
```

**File: `src/catalyst_bot/trading/signal_generator.py` (Lines 271, 350)**

```python
# BEFORE:
signal = TradingSignal(
    ticker=ticker,
    timestamp=datetime.utcnow(),  # ❌ Deprecated
    # ...
)

# AFTER:
from datetime import datetime, timezone

signal = TradingSignal(
    ticker=ticker,
    timestamp=datetime.now(timezone.utc),  # ✅ Timezone-aware
    # ...
)
```

**File: `src/catalyst_bot/charts_advanced.py` (Line 673)**

```python
# BEFORE:
timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")  # ❌

# AFTER:
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")  # ✅
```

#### Automated Fix Script

```python
#!/usr/bin/env python3
"""
Automated datetime.utcnow() replacement.
Run from project root: python fix_datetime.py
"""
import re
from pathlib import Path

FILES_TO_FIX = [
    "apply_safe_recommendations.py",
    "jobs/finviz_filings.py",
    "src/catalyst_bot/store.py",
    "src/catalyst_bot/sec_stream.py",
    "src/catalyst_bot/quickchart_post.py",
    "src/catalyst_bot/sentiment_sources.py",
    "src/catalyst_bot/watchlist_cascade.py",
    "src/catalyst_bot/trading/signal_generator.py",
    "src/catalyst_bot/rag_system.py",
    "src/catalyst_bot/learning.py",
    "src/catalyst_bot/charts_advanced.py",
]

def fix_file(file_path: str) -> int:
    """Fix datetime.utcnow() in a file. Returns count of replacements."""
    path = Path(file_path)
    if not path.exists():
        print(f"  SKIP: {file_path} (not found)")
        return 0

    content = path.read_text(encoding='utf-8')
    original = content

    # Pattern 1: datetime.utcnow()
    content = re.sub(
        r'datetime\.utcnow\(\)',
        'datetime.now(timezone.utc)',
        content
    )

    # Pattern 2: datetime.datetime.utcnow()
    content = re.sub(
        r'datetime\.datetime\.utcnow\(\)',
        'datetime.datetime.now(datetime.timezone.utc)',
        content
    )

    # Add timezone import if needed
    if content != original:
        # Check if timezone import exists
        if 'from datetime import' in content:
            if 'timezone' not in content:
                # Add timezone to existing import
                content = re.sub(
                    r'from datetime import ([^;\n]+)',
                    r'from datetime import \1, timezone',
                    content,
                    count=1
                )
        elif 'import datetime' in content:
            # Already uses datetime.datetime pattern
            pass
        else:
            # Add new import at top
            content = "from datetime import datetime, timezone\n" + content

        path.write_text(content, encoding='utf-8')
        count = original.count('utcnow()') - content.count('utcnow()')
        print(f"  FIXED: {file_path} ({count} replacement(s))")
        return count
    else:
        print(f"  OK: {file_path} (no changes needed)")
        return 0

if __name__ == "__main__":
    print("Fixing datetime.utcnow() deprecations...")
    total = sum(fix_file(f) for f in FILES_TO_FIX)
    print(f"\nDone. Fixed {total} instance(s).")
```

#### Verification

```bash
# Check no utcnow() remains in source files
grep -r "utcnow()" src/catalyst_bot/ --include="*.py" | grep -v "__pycache__"

# Run tests to verify no regressions
pytest tests/test_classify.py tests/test_trading_engine.py -v

# Check for deprecation warnings
python -W error::DeprecationWarning -c "from catalyst_bot import runner"
```

#### Testing

Add this test to verify timezone awareness:

```python
# tests/test_datetime_awareness.py
"""Verify all datetimes are timezone-aware."""
import pytest
from datetime import datetime, timezone

def test_store_rolling_returns_aware_datetime():
    """Verify store.rolling_last24() uses timezone-aware datetimes."""
    from catalyst_bot.store import SeenStore
    store = SeenStore()
    # Internal 'now' should be timezone-aware
    # Implementation detail: verify no DeprecationWarning

def test_signal_generator_timestamps_aware():
    """Verify trading signals have timezone-aware timestamps."""
    from catalyst_bot.trading.signal_generator import TradingSignal
    # Create signal and verify timestamp.tzinfo is not None
```

#### Rollback

```bash
# Revert all datetime changes
git checkout HEAD -- src/catalyst_bot/store.py
git checkout HEAD -- src/catalyst_bot/watchlist_cascade.py
# ... (repeat for all files)
```

---

### CRITICAL-3: Thread Safety - VWAP Calculator

**Priority:** CRITICAL
**Estimated Time:** 15 minutes
**Prerequisites:** None
**Blocks:** Production stability under concurrent load

#### Problem Description

The VWAP calculator uses a global dictionary `_VWAP_CACHE` without thread synchronization. In a multi-threaded environment (which the bot uses for concurrent feed fetching), this can cause:
- Race conditions
- Data corruption
- Intermittent crashes

#### File Affected

`src/catalyst_bot/vwap_calculator.py` (Lines 26-28)

#### Implementation

**Before (Unsafe):**
```python
# Line 26-28 in vwap_calculator.py
# In-memory cache with TTL
_VWAP_CACHE: Dict[str, Dict[str, Any]] = {}
_VWAP_CACHE_TTL_SEC = 300  # 5 minutes
```

**After (Thread-Safe):**
```python
# Line 26-35 in vwap_calculator.py
from threading import Lock
from typing import Dict, Any, Optional

# In-memory cache with TTL (thread-safe)
_VWAP_CACHE: Dict[str, Dict[str, Any]] = {}
_VWAP_CACHE_LOCK = Lock()
_VWAP_CACHE_TTL_SEC = 300  # 5 minutes

def _cache_get(ticker: str) -> Optional[Dict[str, Any]]:
    """Thread-safe cache retrieval."""
    with _VWAP_CACHE_LOCK:
        entry = _VWAP_CACHE.get(ticker)
        if entry is None:
            return None
        # Check TTL
        if time.time() - entry.get("_cached_at", 0) > _VWAP_CACHE_TTL_SEC:
            del _VWAP_CACHE[ticker]
            return None
        return entry.copy()  # Return copy to prevent external mutation

def _cache_set(ticker: str, data: Dict[str, Any]) -> None:
    """Thread-safe cache storage."""
    with _VWAP_CACHE_LOCK:
        _VWAP_CACHE[ticker] = {
            **data,
            "_cached_at": time.time()
        }

def _cache_clear_expired() -> int:
    """Remove expired entries. Returns count removed."""
    with _VWAP_CACHE_LOCK:
        now = time.time()
        expired = [
            k for k, v in _VWAP_CACHE.items()
            if now - v.get("_cached_at", 0) > _VWAP_CACHE_TTL_SEC
        ]
        for k in expired:
            del _VWAP_CACHE[k]
        return len(expired)
```

**Update all cache access points:**

```python
# BEFORE (throughout the file):
def get_vwap(ticker: str) -> Optional[float]:
    if ticker in _VWAP_CACHE:  # ❌ Race condition
        cached = _VWAP_CACHE[ticker]
        if time.time() - cached["_cached_at"] < _VWAP_CACHE_TTL_SEC:
            return cached["vwap"]

    # Calculate VWAP...
    _VWAP_CACHE[ticker] = {"vwap": vwap, "_cached_at": time.time()}  # ❌
    return vwap

# AFTER:
def get_vwap(ticker: str) -> Optional[float]:
    # Check cache first (thread-safe)
    cached = _cache_get(ticker)
    if cached is not None:
        return cached.get("vwap")

    # Calculate VWAP...
    _cache_set(ticker, {"vwap": vwap})  # Thread-safe
    return vwap
```

#### Verification

```bash
# Run thread safety test
python -c "
from concurrent.futures import ThreadPoolExecutor
from catalyst_bot.vwap_calculator import get_vwap

def test_concurrent_access():
    tickers = ['AAPL', 'TSLA', 'NVDA', 'AMD'] * 25
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_vwap, tickers))
    print(f'Completed {len(results)} concurrent calls without error')

test_concurrent_access()
"
```

#### Testing

```python
# tests/test_vwap_thread_safety.py
"""Test VWAP calculator thread safety."""
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from catalyst_bot.vwap_calculator import get_vwap, _cache_clear_expired

class TestVWAPThreadSafety:
    def test_concurrent_reads(self):
        """Verify concurrent cache reads don't corrupt data."""
        tickers = ['AAPL'] * 100
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(get_vwap, t) for t in tickers]
            results = [f.result() for f in as_completed(futures)]

        # All results should be identical (same ticker)
        assert len(set(r for r in results if r is not None)) <= 1

    def test_concurrent_writes(self):
        """Verify concurrent cache writes don't cause errors."""
        tickers = [f'TEST{i}' for i in range(100)]
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(get_vwap, t) for t in tickers]
            for f in as_completed(futures):
                f.result()  # Should not raise

    def test_cache_clear_during_access(self):
        """Verify cache clearing during access is safe."""
        def access_and_clear():
            get_vwap('AAPL')
            _cache_clear_expired()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(access_and_clear) for _ in range(50)]
            for f in as_completed(futures):
                f.result()  # Should not raise
```

---

### CRITICAL-4: Deduplication Hash Determinism

**Priority:** CRITICAL
**Estimated Time:** 45 minutes
**Prerequisites:** CRITICAL-2 (datetime fix)
**Blocks:** Reliable deduplication across restarts

#### Problem Description

The deduplication system uses MD5 and SHA1 hashes which have known weaknesses. More critically, if hash inputs aren't deterministic (e.g., dict ordering varies), the same content can produce different hashes.

#### Files Affected

`src/catalyst_bot/dedupe.py` (Lines 56, 307, 336)

#### Implementation

**1. Upgrade hash algorithm (MD5 → SHA256):**

```python
# BEFORE (Line 56):
import hashlib

def hash_title(title: str) -> str:
    """Compute a deterministic hash for a news headline."""
    normalized = normalize_title(title)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()  # ❌ Weak

# AFTER:
import hashlib

def hash_title(title: str) -> str:
    """Compute a deterministic hash for a news headline.

    Uses SHA-256 for better collision resistance.
    Truncated to 16 chars for storage efficiency (still 64 bits).
    """
    normalized = normalize_title(title)
    full_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return full_hash[:16]  # First 16 chars = 64 bits (sufficient for dedup)
```

**2. Ensure deterministic signature generation:**

```python
# BEFORE (Line 307):
def signature_from(title: str, url: str, ticker: str = "") -> str:
    ticker_component = ticker.upper() if ticker else ""
    normalized_title = normalize_title(title)
    accession = _extract_sec_accession_number(url) or ""

    core = ticker_component + "|" + normalized_title + "|" + accession
    return hashlib.sha1(core.encode("utf-8")).hexdigest()  # ❌ SHA1 weak

# AFTER:
def signature_from(
    title: str,
    url: str,
    ticker: str = "",
    extra_fields: Optional[Dict[str, str]] = None
) -> str:
    """Generate deterministic signature for deduplication.

    Args:
        title: News headline
        url: Article URL
        ticker: Stock symbol (optional)
        extra_fields: Additional fields to include in signature (optional)

    Returns:
        SHA-256 hash truncated to 20 chars (80 bits)

    Note:
        - All inputs are normalized for consistency
        - Dict fields are sorted for determinism
        - Empty values are represented as empty strings
    """
    # Normalize all inputs
    ticker_component = ticker.upper().strip() if ticker else ""
    normalized_title = normalize_title(title)
    accession = _extract_sec_accession_number(url) or ""

    # Build deterministic core string
    parts = [
        f"ticker={ticker_component}",
        f"title={normalized_title}",
        f"accession={accession}",
    ]

    # Add extra fields in sorted order (deterministic)
    if extra_fields:
        for key in sorted(extra_fields.keys()):
            value = str(extra_fields.get(key, "")).strip()
            parts.append(f"{key}={value}")

    core = "|".join(parts)

    # Use SHA-256 (truncated for efficiency)
    full_hash = hashlib.sha256(core.encode("utf-8")).hexdigest()
    return full_hash[:20]  # 20 chars = 80 bits
```

**3. Fix temporal dedup key:**

```python
# BEFORE (Line 336):
def temporal_dedup_key(ticker: str, title: str, timestamp: int) -> str:
    bucket_size = 30 * 60  # 30 minutes
    time_bucket = (timestamp // bucket_size) * bucket_size
    normalized_title = normalize_title(title)
    key = f"{ticker.upper()}|{normalized_title}|{time_bucket}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

# AFTER:
def temporal_dedup_key(
    ticker: str,
    title: str,
    timestamp: int,
    bucket_minutes: int = 30
) -> str:
    """Generate time-bucketed dedup key.

    Args:
        ticker: Stock symbol
        title: News headline
        timestamp: Unix timestamp (seconds)
        bucket_minutes: Time bucket size (default: 30 min)

    Returns:
        SHA-256 hash for the ticker+title within time bucket

    Example:
        Two articles about AAPL with same title within 30 minutes
        will generate the same key, enabling deduplication.
    """
    bucket_size = bucket_minutes * 60
    time_bucket = (timestamp // bucket_size) * bucket_size

    # Normalize inputs
    ticker_normalized = ticker.upper().strip() if ticker else "UNKNOWN"
    title_normalized = normalize_title(title)

    # Deterministic key format
    key = f"temporal|{ticker_normalized}|{title_normalized}|{time_bucket}"

    # SHA-256 truncated
    full_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return full_hash[:20]
```

#### Verification

```bash
# Test hash determinism
python -c "
from catalyst_bot.dedupe import signature_from, temporal_dedup_key

# Same inputs should always produce same output
sig1 = signature_from('FDA approves drug', 'https://example.com/1', 'AAPL')
sig2 = signature_from('FDA approves drug', 'https://example.com/1', 'AAPL')
assert sig1 == sig2, 'Signature not deterministic!'

# Different tickers should produce different signatures
sig3 = signature_from('FDA approves drug', 'https://example.com/1', 'TSLA')
assert sig1 != sig3, 'Different tickers produced same signature!'

print('Hash determinism: PASSED')
"
```

#### Testing

```python
# tests/test_dedupe_determinism.py
"""Test deduplication hash determinism."""
import pytest
import time
from catalyst_bot.dedupe import (
    hash_title,
    signature_from,
    temporal_dedup_key,
    normalize_title
)

class TestHashDeterminism:
    def test_hash_title_deterministic(self):
        """Same title always produces same hash."""
        title = "AAPL announces new iPhone"
        hashes = [hash_title(title) for _ in range(100)]
        assert len(set(hashes)) == 1

    def test_signature_deterministic_with_dict(self):
        """Signature with extra_fields is deterministic."""
        sig1 = signature_from(
            "FDA approval",
            "https://sec.gov/123",
            "AAPL",
            extra_fields={"source": "sec", "type": "8-K"}
        )
        sig2 = signature_from(
            "FDA approval",
            "https://sec.gov/123",
            "AAPL",
            extra_fields={"type": "8-K", "source": "sec"}  # Different order
        )
        assert sig1 == sig2, "Dict order affected signature"

    def test_temporal_key_same_bucket(self):
        """Items in same time bucket get same key."""
        base_time = 1700000000
        key1 = temporal_dedup_key("AAPL", "News", base_time)
        key2 = temporal_dedup_key("AAPL", "News", base_time + 60)  # +1 min
        assert key1 == key2, "Same bucket should have same key"

    def test_temporal_key_different_bucket(self):
        """Items in different time buckets get different keys."""
        base_time = 1700000000
        key1 = temporal_dedup_key("AAPL", "News", base_time)
        key2 = temporal_dedup_key("AAPL", "News", base_time + 1800 + 1)  # +30 min
        assert key1 != key2, "Different buckets should have different keys"

    def test_hash_length_appropriate(self):
        """Hash lengths are appropriate for storage."""
        title_hash = hash_title("Test title")
        sig = signature_from("Test", "https://example.com", "AAPL")
        temp_key = temporal_dedup_key("AAPL", "Test", int(time.time()))

        assert len(title_hash) == 16, f"Title hash should be 16 chars, got {len(title_hash)}"
        assert len(sig) == 20, f"Signature should be 20 chars, got {len(sig)}"
        assert len(temp_key) == 20, f"Temporal key should be 20 chars, got {len(temp_key)}"
```

#### Migration Considerations

Changing hash algorithms will invalidate the existing dedup database. Options:

1. **Full reset** (recommended for most cases):
   ```bash
   # Backup and reset dedup index
   mv data/first_seen_index.db data/first_seen_index.db.bak
   # Bot will create fresh index on next run
   ```

2. **Gradual migration** (for production systems):
   ```python
   def signature_from_with_migration(...):
       """Generate new-style signature, but check both old and new."""
       new_sig = _new_signature(...)
       old_sig = _old_signature(...)  # Legacy MD5/SHA1

       # Check old signature in DB for backwards compatibility
       if _check_legacy_seen(old_sig):
           return old_sig  # Use old for existing items
       return new_sig
   ```

---

## High Priority Fixes

### HIGH-1: LLM Batching and GPU Overload Fix

**Priority:** HIGH
**Estimated Time:** 1-2 hours
**Prerequisites:** CRITICAL fixes complete
**Reference Doc:** `docs/patches/TONIGHT_PATCHES.md`

#### Problem Description

The Mistral LLM returns HTTP 500 errors due to GPU overload when processing 100+ items without batching. This causes:
- 25% loss in sentiment analysis accuracy
- Bot cycle delays
- Potential crashes

#### Files to Modify

| File | Changes |
|------|---------|
| `src/catalyst_bot/llm_client.py` | Add retry logic, batching |
| `src/catalyst_bot/classify.py` | Add pre-filtering, batch delays |
| `.env` | Add batch configuration |

#### Implementation

**Step 1: Add configuration to `.env`:**

```bash
# LLM Batching Configuration
MISTRAL_BATCH_SIZE=5              # Process 5 items at a time
MISTRAL_BATCH_DELAY=2.0           # 2 second delay between batches
MISTRAL_MIN_PRESCALE=0.20         # Only use Mistral on items scoring >0.20
MISTRAL_MAX_RETRIES=3             # Retry attempts on failure
MISTRAL_RETRY_BACKOFF=2.0         # Base backoff multiplier (2s, 4s, 6s)
```

**Step 2: Update `llm_client.py`:**

```python
# Add after line ~200 in llm_client.py

def query_llm_with_retry(
    prompt: str,
    system: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: int = 3,
    priority: str = "normal"
) -> Optional[str]:
    """
    Query LLM with retry logic and exponential backoff.

    Args:
        prompt: The prompt to send
        system: System prompt (optional)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        priority: "high" (more retries), "normal", "low" (fewer retries)

    Returns:
        LLM response text or None on failure

    Integration Points:
        - Called by classify.py during sentiment analysis
        - Called by sec_llm_analyzer.py for filing analysis
        - Called by llm_chain.py for multi-stage processing
    """
    retry_multiplier = {"high": 1.5, "normal": 1.0, "low": 0.5}.get(priority, 1.0)
    effective_retries = max(1, int(max_retries * retry_multiplier))

    base_backoff = float(os.getenv("MISTRAL_RETRY_BACKOFF", "2.0"))

    for attempt in range(effective_retries):
        try:
            # Get timeout from env or use default
            effective_timeout = timeout or float(os.getenv("LLM_TIMEOUT_SECS", "15"))

            response = _send_llm_request(prompt, system, effective_timeout)

            if response is not None and len(response.strip()) > 0:
                return response

            # Empty response - retry
            log.warning(
                "llm_empty_response attempt=%d/%d",
                attempt + 1, effective_retries
            )

        except requests.exceptions.Timeout:
            log.warning(
                "llm_timeout attempt=%d/%d timeout=%.1fs",
                attempt + 1, effective_retries, effective_timeout
            )

        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None

            if status_code == 500:
                # Ollama overloaded - definitely retry with backoff
                log.warning(
                    "ollama_overloaded_500 attempt=%d/%d",
                    attempt + 1, effective_retries
                )
            else:
                log.error(
                    "llm_request_failed attempt=%d/%d error=%s",
                    attempt + 1, effective_retries, str(e)
                )

        # Exponential backoff before retry
        if attempt < effective_retries - 1:
            backoff_time = base_backoff * (attempt + 1)
            log.debug("llm_retry_backoff seconds=%.1f", backoff_time)
            time.sleep(backoff_time)

    # All retries exhausted
    log.error("llm_failed_all_retries retries=%d", effective_retries)

    # Force GPU cleanup on repeated failures
    cleanup_gpu_memory(force=True)

    return None
```

**Step 3: Update `classify.py` with batching:**

```python
# Add to classify.py after existing imports

from typing import List, Dict, Optional
import time
import os

def classify_batch_with_llm(
    items: List["NewsItem"],
    min_prescale_score: float = None,
    batch_size: int = None,
    batch_delay: float = None,
) -> List["ScoredItem"]:
    """
    Classify items with LLM sentiment in optimized batches.

    This function implements the GPU-friendly batching strategy:
    1. Pre-filter items using fast VADER scoring (reduces 136 → ~40 items)
    2. Process remaining items in small batches with delays
    3. Gracefully handle LLM failures with fallback scoring

    Args:
        items: List of NewsItem objects to classify
        min_prescale_score: Minimum VADER score to qualify for LLM (default: 0.20)
        batch_size: Items per batch (default: 5)
        batch_delay: Seconds between batches (default: 2.0)

    Returns:
        List of ScoredItem objects with sentiment scores

    Integration Points:
        - Called from runner.py _cycle() function
        - Results feed into alerts.py send_alert_safe()

    Example:
        items = fetch_pr_feeds()
        scored = classify_batch_with_llm(items)
        for item in scored:
            if item.total >= MIN_SCORE:
                send_alert_safe(item)
    """
    # Load config with defaults
    min_prescale = min_prescale_score or float(os.getenv("MISTRAL_MIN_PRESCALE", "0.20"))
    batch_sz = batch_size or int(os.getenv("MISTRAL_BATCH_SIZE", "5"))
    delay = batch_delay or float(os.getenv("MISTRAL_BATCH_DELAY", "2.0"))

    log.info(
        "classify_batch_start items=%d min_prescale=%.2f batch_size=%d",
        len(items), min_prescale, batch_sz
    )

    results = []

    # Step 1: Fast pre-scoring with VADER (no GPU)
    prescored = []
    for item in items:
        vader_score = _quick_vader_score(item.title)
        prescored.append((item, vader_score))

    # Step 2: Separate items by prescale threshold
    items_for_llm = [(item, score) for item, score in prescored if score >= min_prescale]
    items_skip_llm = [(item, score) for item, score in prescored if score < min_prescale]

    log.info(
        "prescale_filter llm_qualified=%d skipped=%d reduction=%.1f%%",
        len(items_for_llm),
        len(items_skip_llm),
        (1 - len(items_for_llm) / max(len(items), 1)) * 100
    )

    # Step 3: Process skipped items with VADER-only scoring
    for item, vader_score in items_skip_llm:
        scored = _classify_vader_only(item, vader_score)
        results.append(scored)

    # Step 4: GPU warmup before batch processing
    if items_for_llm:
        prime_ollama_gpu()

    # Step 5: Process LLM items in batches
    num_batches = (len(items_for_llm) + batch_sz - 1) // batch_sz

    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_sz
        end_idx = min(start_idx + batch_sz, len(items_for_llm))
        batch = items_for_llm[start_idx:end_idx]

        log.info(
            "processing_batch batch=%d/%d items=%d",
            batch_idx + 1, num_batches, len(batch)
        )

        for item, vader_score in batch:
            try:
                scored = _classify_with_llm(item, vader_score)
                results.append(scored)
            except Exception as e:
                log.warning(
                    "llm_classify_failed ticker=%s error=%s falling_back=vader",
                    item.ticker, str(e)
                )
                # Fallback to VADER-only
                scored = _classify_vader_only(item, vader_score)
                results.append(scored)

        # Delay between batches (except last batch)
        if batch_idx < num_batches - 1:
            log.debug("batch_delay seconds=%.1f", delay)
            time.sleep(delay)

    log.info(
        "classify_batch_complete items=%d llm_processed=%d vader_only=%d",
        len(results), len(items_for_llm), len(items_skip_llm)
    )

    return results


def _quick_vader_score(text: str) -> float:
    """Fast VADER scoring for pre-filtering."""
    try:
        scores = _vader.polarity_scores(text)
        return abs(scores.get("compound", 0.0))
    except Exception:
        return 0.0


def _classify_vader_only(item: "NewsItem", vader_score: float) -> "ScoredItem":
    """Create ScoredItem using only VADER sentiment."""
    # Existing VADER-based classification logic
    # (reuse from existing classify() function)
    pass  # Implementation depends on existing code structure


def _classify_with_llm(item: "NewsItem", vader_score: float) -> "ScoredItem":
    """Create ScoredItem using full LLM pipeline."""
    # Existing LLM classification logic
    # (reuse from existing classify() function)
    pass  # Implementation depends on existing code structure
```

#### Verification

```bash
# Monitor Ollama during batch processing
tail -f data/logs/bot.jsonl | grep -E "classify_batch|processing_batch|ollama"

# Expected output:
# classify_batch_start items=136 min_prescale=0.20 batch_size=5
# prescale_filter llm_qualified=42 skipped=94 reduction=69.1%
# processing_batch batch=1/9 items=5
# processing_batch batch=2/9 items=5
# ...
```

#### Testing

```python
# tests/test_llm_batching.py
"""Test LLM batching functionality."""
import pytest
from unittest.mock import patch, MagicMock
from catalyst_bot.classify import classify_batch_with_llm
from catalyst_bot.models import NewsItem

class TestLLMBatching:
    @pytest.fixture
    def mock_items(self):
        """Create test NewsItem objects."""
        return [
            NewsItem(title=f"Test news {i}", ticker="AAPL")
            for i in range(20)
        ]

    def test_prescale_filtering(self, mock_items):
        """Verify low-scoring items skip LLM."""
        with patch('catalyst_bot.classify._quick_vader_score') as mock_vader:
            # Half items score high, half score low
            mock_vader.side_effect = lambda t: 0.5 if 'news 0' in t else 0.1

            with patch('catalyst_bot.classify._classify_with_llm') as mock_llm:
                with patch('catalyst_bot.classify._classify_vader_only') as mock_vader_only:
                    mock_llm.return_value = MagicMock()
                    mock_vader_only.return_value = MagicMock()

                    classify_batch_with_llm(mock_items)

                    # Most items should use VADER-only (score < 0.20)
                    assert mock_vader_only.call_count > mock_llm.call_count

    def test_batch_delay_applied(self, mock_items):
        """Verify delays between batches."""
        with patch('catalyst_bot.classify.time.sleep') as mock_sleep:
            with patch('catalyst_bot.classify._quick_vader_score', return_value=0.5):
                with patch('catalyst_bot.classify._classify_with_llm'):
                    classify_batch_with_llm(
                        mock_items[:10],
                        min_prescale_score=0.1,
                        batch_size=3,
                        batch_delay=1.0
                    )

                    # 10 items / 3 per batch = 4 batches = 3 delays
                    assert mock_sleep.call_count == 3
```

---

### HIGH-2: Heartbeat Cumulative Tracking

**Priority:** HIGH
**Estimated Time:** 30 minutes
**Prerequisites:** None
**Reference Doc:** `docs/patches/TONIGHT_PATCHES.md`

#### Problem Description

The heartbeat only shows counts from the most recent scan cycle, not cumulative totals since the last heartbeat. This makes it difficult to track bot performance over time.

#### Files to Modify

| File | Changes |
|------|---------|
| `src/catalyst_bot/runner.py` | Add HeartbeatAccumulator class |
| `src/catalyst_bot/discord_utils.py` | Update heartbeat embed format |
| `.env` | Add heartbeat interval config |

#### Implementation

**The `HeartbeatAccumulator` class already exists** at line 223 of `runner.py`. Verify it's being used correctly:

```python
# runner.py - Verify this class exists and is used
class HeartbeatAccumulator:
    """Tracks cumulative statistics between heartbeat reports."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all counters for new heartbeat period."""
        self.total_scanned = 0
        self.total_alerts = 0
        self.total_errors = 0
        self.cycles_completed = 0
        self.last_heartbeat_time = datetime.now(timezone.utc)

    def add_cycle(self, scanned: int, alerts: int, errors: int = 0):
        """Record stats from a completed cycle."""
        self.total_scanned += scanned
        self.total_alerts += alerts
        self.total_errors += errors
        self.cycles_completed += 1

    def should_send_heartbeat(self, interval_minutes: int = 60) -> bool:
        """Check if heartbeat interval has elapsed."""
        elapsed = (datetime.now(timezone.utc) - self.last_heartbeat_time).total_seconds()
        return elapsed >= (interval_minutes * 60)

    def get_stats(self) -> dict:
        """Get accumulated statistics for heartbeat."""
        elapsed_min = (datetime.now(timezone.utc) - self.last_heartbeat_time).total_seconds() / 60
        return {
            "total_scanned": self.total_scanned,
            "total_alerts": self.total_alerts,
            "total_errors": self.total_errors,
            "cycles_completed": self.cycles_completed,
            "elapsed_minutes": round(elapsed_min, 1),
            "avg_alerts_per_cycle": round(
                self.total_alerts / max(self.cycles_completed, 1), 2
            ),
            "avg_scanned_per_cycle": round(
                self.total_scanned / max(self.cycles_completed, 1), 1
            ),
        }


# Global instance (create near top of file after imports)
_heartbeat_accumulator = HeartbeatAccumulator()
```

**Update the `_cycle()` function to use accumulator:**

```python
def _cycle(log, settings, market_info: dict | None = None) -> None:
    """Main processing cycle."""
    global _heartbeat_accumulator

    # ... existing cycle logic ...

    # At end of cycle, after all processing:
    _heartbeat_accumulator.add_cycle(
        scanned=len(items_processed),
        alerts=len(alerts_posted),
        errors=error_count
    )

    # Check if heartbeat should be sent
    heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "60"))

    if _heartbeat_accumulator.should_send_heartbeat(heartbeat_interval):
        stats = _heartbeat_accumulator.get_stats()
        _send_heartbeat(stats)
        _heartbeat_accumulator.reset()
```

**Update heartbeat embed in `discord_utils.py`:**

```python
def build_heartbeat_embed(stats: dict) -> dict:
    """Build Discord embed for heartbeat with cumulative stats."""

    # Determine health color based on metrics
    if stats["total_errors"] > 10:
        color = 0xFF0000  # Red - errors
    elif stats["avg_alerts_per_cycle"] < 0.5:
        color = 0xFFFF00  # Yellow - low activity
    else:
        color = 0x00FF00  # Green - healthy

    return {
        "title": ":robot: Bot Heartbeat",
        "color": color,
        "fields": [
            {
                "name": ":clock1: Period",
                "value": f"Last {stats['elapsed_minutes']:.0f} minutes",
                "inline": False
            },
            {
                "name": ":bar_chart: Feeds Scanned",
                "value": f"{stats['total_scanned']:,}",
                "inline": True
            },
            {
                "name": ":bell: Alerts Posted",
                "value": f"{stats['total_alerts']}",
                "inline": True
            },
            {
                "name": ":repeat: Cycles",
                "value": f"{stats['cycles_completed']}",
                "inline": True
            },
            {
                "name": ":chart_with_upwards_trend: Avg Alerts/Cycle",
                "value": f"{stats['avg_alerts_per_cycle']:.2f}",
                "inline": True
            },
            {
                "name": ":page_facing_up: Avg Scanned/Cycle",
                "value": f"{stats['avg_scanned_per_cycle']:.0f}",
                "inline": True
            },
            {
                "name": ":x: Errors",
                "value": f"{stats['total_errors']}",
                "inline": True
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "Catalyst-Bot Health Monitor"
        }
    }
```

**Add to `.env`:**

```bash
# Heartbeat Configuration
HEARTBEAT_INTERVAL_MINUTES=60     # Send heartbeat every 60 minutes
HEARTBEAT_WEBHOOK_URL=            # Optional: separate webhook for heartbeats
```

#### Verification

```bash
# Watch for heartbeat in logs
tail -f data/logs/bot.jsonl | grep heartbeat

# Expected after 2 cycles (if interval is short for testing):
# heartbeat_sent total_scanned=272 total_alerts=4 cycles=2 elapsed_min=2.0
```

---

### HIGH-3: SEC LLM Summarization Integration

**Priority:** HIGH
**Estimated Time:** 1-2 hours
**Prerequisites:** HIGH-1 (LLM batching)
**Reference Doc:** `docs/sec/SEC_INTEGRATION_KNOWN_ISSUES_AND_NEXT_STEPS.md`

#### Problem Description

SEC filings currently use placeholder summaries instead of real LLM-generated analysis. This reduces the quality of keyword scoring and alert actionability.

**Current behavior:**
```python
llm_summary = f"SEC {filing_type} filing for {ticker}"  # Placeholder
```

**Desired behavior:**
```python
llm_summary = "BULLISH: $50M institutional investment at 15% premium to market..."
```

#### Files to Modify

| File | Changes |
|------|---------|
| `src/catalyst_bot/feeds.py` | Add LLM summarization call before NewsItem conversion |
| `src/catalyst_bot/sec_llm_analyzer.py` | Ensure analyze_sec_filing() is callable |
| `src/catalyst_bot/llm_chain.py` | Multi-stage pipeline (already exists) |

#### Implementation

**Update `feeds.py` to call LLM summarization:**

```python
# In feeds.py, find the SEC filing processing section (around line 1000-1050)
# Add this function and integrate it into the pipeline:

async def _enrich_sec_filing_with_llm(
    filing: Dict[str, Any],
    timeout: float = 20.0
) -> Dict[str, Any]:
    """
    Enrich SEC filing with LLM-generated summary.

    Args:
        filing: Raw SEC filing dict with keys:
            - ticker: Stock symbol
            - filing_type: e.g., "8-K", "424B5"
            - title: Filing title
            - summary: Raw text excerpt (first ~2000 chars)
            - url: SEC EDGAR URL
        timeout: LLM request timeout

    Returns:
        Filing dict with added keys:
            - llm_summary: AI-generated trading-focused summary
            - llm_sentiment: Sentiment score (-1 to +1)
            - llm_confidence: Confidence score (0 to 1)
            - catalysts: List of detected catalyst types

    Integration Points:
        - Called from fetch_sec_filings() before NewsItem conversion
        - Uses sec_llm_analyzer.analyze_sec_filing() for analysis
        - Falls back to placeholder on LLM failure

    Example Output:
        {
            ...original filing...,
            "llm_summary": "BEARISH: $25M ATM offering announced, 8% dilution...",
            "llm_sentiment": -0.65,
            "llm_confidence": 0.85,
            "catalysts": ["offering", "dilution"]
        }
    """
    ticker = filing.get("ticker", "UNKNOWN")
    filing_type = filing.get("filing_type", "8-K")
    raw_text = filing.get("summary", filing.get("title", ""))

    try:
        # Import here to avoid circular dependency
        from catalyst_bot.sec_llm_analyzer import analyze_sec_filing

        log.debug(
            "sec_llm_enrich_start ticker=%s type=%s text_len=%d",
            ticker, filing_type, len(raw_text)
        )

        result = await analyze_sec_filing(
            title=filing.get("title", ""),
            filing_type=filing_type,
            summary=raw_text[:3000],  # Limit input size
            timeout=timeout
        )

        if result and result.get("llm_summary"):
            log.info(
                "sec_llm_enrich_success ticker=%s sentiment=%.2f summary_len=%d",
                ticker,
                result.get("llm_sentiment", 0),
                len(result.get("llm_summary", ""))
            )

            return {
                **filing,
                "llm_summary": result["llm_summary"],
                "llm_sentiment": result.get("llm_sentiment", 0.0),
                "llm_confidence": result.get("llm_confidence", 0.5),
                "catalysts": result.get("catalysts", []),
            }

    except asyncio.TimeoutError:
        log.warning("sec_llm_enrich_timeout ticker=%s", ticker)
    except Exception as e:
        log.warning("sec_llm_enrich_failed ticker=%s error=%s", ticker, str(e))

    # Fallback: return original filing with placeholder
    return {
        **filing,
        "llm_summary": f"SEC {filing_type} filing for {ticker}",
        "llm_sentiment": 0.0,
        "llm_confidence": 0.3,
        "catalysts": [],
    }


# Update fetch_sec_filings() to use enrichment:
async def fetch_sec_filings(...) -> List[NewsItem]:
    """Fetch and process SEC filings."""
    raw_filings = await _fetch_raw_sec_filings(...)

    # Enrich with LLM summaries (with concurrency limit)
    enriched = []
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent LLM calls

    async def enrich_one(filing):
        async with semaphore:
            return await _enrich_sec_filing_with_llm(filing)

    enriched = await asyncio.gather(*[enrich_one(f) for f in raw_filings])

    # Convert to NewsItem objects
    news_items = []
    for filing in enriched:
        item = NewsItem(
            ts_utc=filing["filed_at"],
            title=filing["title"],
            canonical_url=filing["url"],
            source_host="sec.gov",
            ticker=filing["ticker"],
            summary=filing["llm_summary"],  # Use LLM summary
            raw={
                **filing,
                "source": f"sec_{filing['filing_type'].lower()}",
            }
        )
        news_items.append(item)

    log.info(
        "sec_filings_fetched total=%d with_llm_summary=%d",
        len(news_items),
        sum(1 for f in enriched if f.get("llm_confidence", 0) > 0.3)
    )

    return news_items
```

#### Verification

```bash
# Watch for LLM enrichment in logs
tail -f data/logs/bot.jsonl | grep "sec_llm_enrich"

# Expected:
# sec_llm_enrich_start ticker=AAPL type=8-K text_len=2500
# sec_llm_enrich_success ticker=AAPL sentiment=-0.45 summary_len=150
```

#### Testing

```python
# tests/test_sec_llm_enrichment.py
"""Test SEC filing LLM enrichment."""
import pytest
from unittest.mock import patch, AsyncMock
import asyncio
from catalyst_bot.feeds import _enrich_sec_filing_with_llm

class TestSECLLMEnrichment:
    @pytest.fixture
    def sample_filing(self):
        return {
            "ticker": "AAPL",
            "filing_type": "8-K",
            "title": "Form 8-K - Current Report",
            "summary": "Apple Inc. announced quarterly earnings...",
            "url": "https://sec.gov/...",
            "filed_at": "2025-01-15T09:00:00Z"
        }

    @pytest.mark.asyncio
    async def test_successful_enrichment(self, sample_filing):
        """Test successful LLM enrichment."""
        with patch('catalyst_bot.feeds.analyze_sec_filing') as mock_analyze:
            mock_analyze.return_value = {
                "llm_summary": "BULLISH: Strong Q1 earnings beat...",
                "llm_sentiment": 0.75,
                "llm_confidence": 0.90,
                "catalysts": ["earnings", "guidance_raise"]
            }

            result = await _enrich_sec_filing_with_llm(sample_filing)

            assert result["llm_summary"].startswith("BULLISH")
            assert result["llm_sentiment"] == 0.75
            assert "earnings" in result["catalysts"]

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self, sample_filing):
        """Test fallback to placeholder on LLM failure."""
        with patch('catalyst_bot.feeds.analyze_sec_filing') as mock_analyze:
            mock_analyze.side_effect = Exception("LLM unavailable")

            result = await _enrich_sec_filing_with_llm(sample_filing)

            # Should return placeholder, not crash
            assert "SEC 8-K filing for AAPL" in result["llm_summary"]
            assert result["llm_confidence"] == 0.3
```

---

## Medium Priority Enhancements

### MEDIUM-1: Convert Print Statements to Logging

**Priority:** MEDIUM
**Estimated Time:** 2-4 hours
**Prerequisites:** None

#### Problem Description

45+ files contain `print()` statements instead of proper logging. This reduces observability and makes debugging difficult.

#### Implementation Pattern

```python
# BEFORE:
print(f"Processing ticker: {ticker}")
print(f"Error: {e}")

# AFTER:
import logging
log = logging.getLogger(__name__)

log.info("processing_ticker ticker=%s", ticker)
log.error("processing_failed ticker=%s error=%s", ticker, str(e))
```

#### Priority Files

Focus on these core files first:

1. `src/catalyst_bot/runner.py`
2. `src/catalyst_bot/classify.py`
3. `src/catalyst_bot/alerts.py`
4. `src/catalyst_bot/feeds.py`

#### Automated Fix Script

```python
#!/usr/bin/env python3
"""
Convert print statements to logging calls.
Run: python fix_print_to_logging.py <file_path>
"""
import re
import sys
from pathlib import Path

def convert_print_to_log(content: str) -> str:
    """Convert print() calls to log.info() calls."""

    # Pattern: print(f"..." or print("...")
    # This is a simplified converter - manual review recommended

    # Add logging import if not present
    if 'import logging' not in content and 'from catalyst_bot.logger' not in content:
        content = "import logging\nlog = logging.getLogger(__name__)\n\n" + content

    # Convert print(f"...") to log.info("...")
    # Note: This is basic - complex prints need manual review
    content = re.sub(
        r'print\(f"([^"]+)"\)',
        r'log.info("\1")',
        content
    )

    content = re.sub(
        r"print\(f'([^']+)'\)",
        r"log.info('\1')",
        content
    )

    return content

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_print_to_logging.py <file_path>")
        sys.exit(1)

    path = Path(sys.argv[1])
    content = path.read_text()
    converted = convert_print_to_log(content)

    # Write to .new file for review
    new_path = path.with_suffix('.py.new')
    new_path.write_text(converted)
    print(f"Converted file written to: {new_path}")
    print("Review changes and rename to original filename.")
```

---

### MEDIUM-2: CSV Encoding Safety

**Priority:** MEDIUM
**Estimated Time:** 15 minutes
**Prerequisites:** None

#### File to Modify

`src/catalyst_bot/jobs/train_ml.py` (Line 48)

#### Implementation

```python
# BEFORE (Line 48):
if input_path.suffix.lower() == ".csv":
    df = pd.read_csv(input_path)

# AFTER:
if input_path.suffix.lower() == ".csv":
    df = pd.read_csv(
        input_path,
        encoding='utf-8',
        on_bad_lines='warn',  # Don't fail on malformed lines
        dtype_backend='pyarrow'  # Optional: better performance
    )
```

---

## Testing Strategy

### Pre-Implementation Testing

Before making any changes:

```bash
# Run full test suite to establish baseline
pytest tests/ -v --tb=short > test_baseline.txt 2>&1

# Note current pass rate
grep -E "passed|failed|error" test_baseline.txt | tail -5
```

### Post-Fix Testing

After each critical fix:

```bash
# Run targeted tests for the fix
pytest tests/test_<relevant>.py -v

# Run integration tests
pytest tests/ -v -k "integration" --tb=short

# Run full suite
pytest tests/ -v --tb=short
```

### Verification Commands Summary

| Fix | Verification Command |
|-----|---------------------|
| BOM removal | `python -m py_compile src/catalyst_bot/feeds.py` |
| datetime fix | `grep -r "utcnow()" src/ --include="*.py"` |
| Thread safety | `python -c "from concurrent.futures import ThreadPoolExecutor; ..."` |
| Hash determinism | `pytest tests/test_dedupe_determinism.py -v` |
| LLM batching | `tail -f logs/bot.jsonl \| grep batch` |
| Heartbeat | `tail -f logs/bot.jsonl \| grep heartbeat` |

---

## Rollback Procedures

### Quick Rollback (Git)

```bash
# Rollback single file
git checkout HEAD -- <file_path>

# Rollback to specific commit
git revert <commit_hash>

# Full rollback to last known good
git reset --hard <last_good_commit>
```

### Feature Flag Rollback

For LLM batching, add feature flags:

```bash
# In .env - disable batching if issues arise
FEATURE_LLM_BATCHING=0
MISTRAL_BATCH_SIZE=999  # Effectively disables batching
```

### Database Rollback

For dedup hash changes:

```bash
# Restore from backup
cp data/first_seen_index.db.bak data/first_seen_index.db
```

---

## Sources & References

### Internal Documentation

| Document | Location | Purpose |
|----------|----------|---------|
| ACTION_CHECKLIST | `docs/planning/ACTION_CHECKLIST.md` | Critical fixes checklist |
| TONIGHT_PATCHES | `docs/patches/TONIGHT_PATCHES.md` | LLM batching, heartbeat fixes |
| SEC_INTEGRATION_KNOWN_ISSUES | `docs/sec/SEC_INTEGRATION_KNOWN_ISSUES_AND_NEXT_STEPS.md` | SEC LLM summarization |
| PATCH_ROADMAP | `docs/patches/PATCH_ROADMAP.md` | Complete roadmap with waves |
| ALL_FIXES_STATUS_SUMMARY | `docs/patches/ALL_FIXES_STATUS_SUMMARY.md` | Fix verification status |

### External Sources

- [Miguel Grinberg - datetime.utcnow() Is Now Deprecated](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated) - Datetime migration guide
- [Simon Willison - Fixes for datetime UTC warnings](https://til.simonwillison.net/python/utc-warning-fix) - Practical fix examples
- [Discord Webhooks Guide - File Attachments](https://birdie0.github.io/discord-webhooks-guide/structure/file.html) - Discord API v10 requirements
- [Python hashlib Documentation](https://docs.python.org/3/library/hashlib.html) - Hash algorithm reference
- [Stack Overflow - Hash Algorithms for Deduplication](https://stackoverflow.com/questions/11696403/what-are-some-of-the-best-hashing-algorithms-to-use-for-data-integrity-and-dedup) - SHA256 vs MD5 comparison
- [Medium - Avoiding Race Conditions in Python 2025](https://medium.com/pythoneers/avoiding-race-conditions-in-python-in-2025-best-practices-for-async-and-threads-4e006579a622) - Thread safety patterns

---

## Implementation Order Checklist

Use this checklist to track progress:

### Phase 1: Critical Path (Day 1)
- [ ] CRITICAL-1: UTF-8 BOM removal
- [ ] CRITICAL-2: datetime.utcnow() deprecation
- [ ] CRITICAL-3: Thread safety (VWAP cache)
- [ ] CRITICAL-4: Dedup hash determinism
- [ ] Run test suite - verify no regressions

### Phase 2: High Priority (Day 2-3)
- [ ] HIGH-1: LLM batching and GPU overload
- [ ] HIGH-2: Heartbeat cumulative tracking
- [ ] HIGH-3: SEC LLM summarization
- [ ] Run integration tests

### Phase 3: Medium Priority (Week 2)
- [ ] MEDIUM-1: Convert print to logging (priority files)
- [ ] MEDIUM-2: CSV encoding safety
- [ ] MEDIUM-3: Hash algorithm upgrade (SHA256)
- [ ] Full test suite pass

### Phase 4: Validation
- [ ] 24-hour production monitoring
- [ ] Alert quality verification
- [ ] Performance metrics review

---

**Document Maintained By:** Claude Code / Codex
**Last Updated:** 2025-12-06
**Next Review:** After Phase 2 completion
