# Parallel Ticker Enrichment Implementation Plan

## Executive Summary

**Goal**: Reduce cycle time from 448 seconds (7.5 minutes) to ~60-90 seconds by parallelizing ticker enrichment operations.

**Primary Bottleneck**: Float data scraping (Finviz) with 2-3 second delays per ticker.

**Current Architecture**: Sequential per-ticker enrichment in `classify.py` during classification loop.

**Proposed Solution**: Batch-fetch all enrichment data upfront using thread pool, then pass pre-computed data to classify().

**Expected Performance Gain**: 5-7x speedup (448s → 60-90s)

---

## Current Performance Analysis

### Bottleneck Breakdown (Per ~50 Tickers)

| Operation | Current Time | Bottleneck Severity |
|-----------|-------------|---------------------|
| **Float scraping** | 100-150s (2-3s × 50 tickers) | 🔴 **CRITICAL** |
| **VWAP calculation** | 25-35s (0.5-0.7s × 50 tickers) | 🟡 **MODERATE** |
| **RVol calculation** | 25-35s (0.5-0.7s × 50 tickers) | 🟡 **MODERATE** |
| **SEC LLM analysis** | ~35s (8-18s × 3 filings) | 🟢 **ACCEPTABLE** (already sequential by design) |
| **Price fetching** | ✅ **OPTIMIZED** (already batched in runner.py:1071-1085) |
| **Other operations** | <10s (classification, logging, etc.) | 🟢 **ACCEPTABLE** |

**Total**: ~448 seconds per cycle

### Target Performance (After Parallelization)

| Operation | Target Time | Speedup |
|-----------|-------------|---------|
| **Float scraping** | 10-15s (concurrent with max 10 workers) | **10x** |
| **VWAP calculation** | 5-8s (concurrent with max 15 workers) | **5x** |
| **RVol calculation** | 5-8s (concurrent with max 15 workers) | **5x** |
| **SEC LLM analysis** | ~35s (keep sequential) | 1x |
| **Other operations** | <10s | 1x |

**Target Total**: **60-90 seconds** per cycle

---

## Architecture Overview

### Phase 1: Current Sequential Flow
```
runner.py:_cycle()
  ├─> Fetch feeds                            [5-10s]
  ├─> Dedupe items                           [<1s]
  ├─> BATCH price fetch (OPTIMIZED) ✅       [2-5s]
  └─> FOR EACH item:
        ├─> classify(item)                   [Per-ticker operations below]
        │     ├─> calculate_rvol_intraday()  [0.5-0.7s per ticker] 🔴
        │     ├─> get_float_data()           [2-3s per ticker] 🔴
        │     └─> calculate_vwap()           [0.5-0.7s per ticker] 🔴
        ├─> send_alert_safe()                [<0.5s]
        └─> log metrics                      [<0.1s]
```

**Problem**: Each classify() call makes 3 sequential API calls/scrapes **per ticker**.

### Phase 2: Proposed Parallel Flow
```
runner.py:_cycle()
  ├─> Fetch feeds                            [5-10s]
  ├─> Dedupe items                           [<1s]
  ├─> Extract unique tickers                 [<0.1s]
  │
  ├─> PARALLEL BATCH ENRICHMENT ✨ (NEW)     [15-25s total]
  │     ├─> ThreadPoolExecutor (max_workers=10)
  │     ├─> batch_get_float_data(tickers)    [10-15s concurrent]
  │     ├─> batch_get_vwap_data(tickers)     [5-8s concurrent]
  │     └─> batch_get_rvol_data(tickers)     [5-8s concurrent]
  │
  ├─> BATCH price fetch (existing) ✅        [2-5s]
  └─> FOR EACH item:
        ├─> classify(item, precomputed_data) [<0.1s - no API calls!]
        ├─> send_alert_safe()                [<0.5s]
        └─> log metrics                      [<0.1s]
```

**Solution**: Batch-fetch ALL enrichment data upfront, then pass to classify() as cached/precomputed values.

---

## Implementation Phases

### Phase 1: Create Batch Enrichment Functions (Day 1)

#### File: `src/catalyst_bot/enrichment.py` (NEW)

Create a new centralized enrichment module with batch operations:

```python
"""
Parallel Ticker Enrichment Module
Batch-fetches float, VWAP, and RVol data for multiple tickers concurrently.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any
import time
from .float_data import get_float_data
from .vwap_calculator import calculate_vwap
from .rvol import calculate_rvol_intraday
from .logging_utils import get_logger

log = get_logger("enrichment")

# Thread pool configuration
MAX_FLOAT_WORKERS = 10  # Finviz rate limiting (2-3s delays)
MAX_VWAP_WORKERS = 15   # yfinance can handle more concurrent requests
MAX_RVOL_WORKERS = 15   # yfinance can handle more concurrent requests
TIMEOUT_SECONDS = 30    # Per-ticker timeout


def batch_get_float_data(
    tickers: List[str],
    max_workers: int = MAX_FLOAT_WORKERS,
    timeout: int = TIMEOUT_SECONDS,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Batch-fetch float data for multiple tickers concurrently.

    Args:
        tickers: List of ticker symbols
        max_workers: Max concurrent threads (default: 10 for Finviz rate limiting)
        timeout: Timeout per ticker in seconds

    Returns:
        Dict mapping ticker -> float data (or None if failed)
    """
    if not tickers:
        return {}

    start_time = time.time()
    results = {}

    # Use ThreadPoolExecutor for I/O-bound operations
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(get_float_data, ticker): ticker
            for ticker in tickers
        }

        # Collect results as they complete
        for future in as_completed(future_to_ticker, timeout=timeout * len(tickers)):
            ticker = future_to_ticker[future]
            try:
                result = future.result(timeout=timeout)
                results[ticker] = result
            except Exception as e:
                log.warning(
                    "batch_float_failed ticker=%s err=%s",
                    ticker,
                    e.__class__.__name__,
                )
                results[ticker] = None

    elapsed = time.time() - start_time
    success_count = sum(1 for v in results.values() if v and v.get("success"))

    log.info(
        "batch_float_complete tickers=%d success=%d elapsed=%.2fs",
        len(tickers),
        success_count,
        elapsed,
    )

    return results


def batch_get_vwap_data(
    tickers: List[str],
    max_workers: int = MAX_VWAP_WORKERS,
    timeout: int = TIMEOUT_SECONDS,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Batch-fetch VWAP data for multiple tickers concurrently.

    Args:
        tickers: List of ticker symbols
        max_workers: Max concurrent threads (default: 15)
        timeout: Timeout per ticker in seconds

    Returns:
        Dict mapping ticker -> VWAP data (or None if failed)
    """
    if not tickers:
        return {}

    start_time = time.time()
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {
            executor.submit(calculate_vwap, ticker): ticker
            for ticker in tickers
        }

        for future in as_completed(future_to_ticker, timeout=timeout * len(tickers)):
            ticker = future_to_ticker[future]
            try:
                result = future.result(timeout=timeout)
                results[ticker] = result
            except Exception as e:
                log.warning(
                    "batch_vwap_failed ticker=%s err=%s",
                    ticker,
                    e.__class__.__name__,
                )
                results[ticker] = None

    elapsed = time.time() - start_time
    success_count = sum(1 for v in results.values() if v is not None)

    log.info(
        "batch_vwap_complete tickers=%d success=%d elapsed=%.2fs",
        len(tickers),
        success_count,
        elapsed,
    )

    return results


def batch_get_rvol_data(
    tickers: List[str],
    max_workers: int = MAX_RVOL_WORKERS,
    timeout: int = TIMEOUT_SECONDS,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Batch-fetch RVol data for multiple tickers concurrently.

    Args:
        tickers: List of ticker symbols
        max_workers: Max concurrent threads (default: 15)
        timeout: Timeout per ticker in seconds

    Returns:
        Dict mapping ticker -> RVol data (or None if failed)
    """
    if not tickers:
        return {}

    start_time = time.time()
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {
            executor.submit(calculate_rvol_intraday, ticker): ticker
            for ticker in tickers
        }

        for future in as_completed(future_to_ticker, timeout=timeout * len(tickers)):
            ticker = future_to_ticker[future]
            try:
                result = future.result(timeout=timeout)
                results[ticker] = result
            except Exception as e:
                log.warning(
                    "batch_rvol_failed ticker=%s err=%s",
                    ticker,
                    e.__class__.__name__,
                )
                results[ticker] = None

    elapsed = time.time() - start_time
    success_count = sum(1 for v in results.values() if v is not None)

    log.info(
        "batch_rvol_complete tickers=%d success=%d elapsed=%.2fs",
        len(tickers),
        success_count,
        elapsed,
    )

    return results


def batch_enrich_all(
    tickers: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Batch-fetch ALL enrichment data (float, VWAP, RVol) for multiple tickers.

    Runs all three batch operations in PARALLEL for maximum performance.

    Args:
        tickers: List of ticker symbols

    Returns:
        Dict mapping ticker -> enrichment data dict with keys:
            - float_data: Dict or None
            - vwap_data: Dict or None
            - rvol_data: Dict or None
    """
    if not tickers:
        return {}

    start_time = time.time()

    # Run all three batch operations in parallel using separate thread pools
    with ThreadPoolExecutor(max_workers=3) as meta_executor:
        float_future = meta_executor.submit(batch_get_float_data, tickers)
        vwap_future = meta_executor.submit(batch_get_vwap_data, tickers)
        rvol_future = meta_executor.submit(batch_get_rvol_data, tickers)

        # Wait for all to complete
        float_results = float_future.result()
        vwap_results = vwap_future.result()
        rvol_results = rvol_future.result()

    # Combine results
    combined = {}
    for ticker in tickers:
        combined[ticker] = {
            "float_data": float_results.get(ticker),
            "vwap_data": vwap_results.get(ticker),
            "rvol_data": rvol_results.get(ticker),
        }

    elapsed = time.time() - start_time

    log.info(
        "batch_enrich_all_complete tickers=%d elapsed=%.2fs",
        len(tickers),
        elapsed,
    )

    return combined
```

---

### Phase 2: Modify classify.py to Use Precomputed Data (Day 1)

Update `classify()` function signature to accept optional precomputed enrichment data:

```python
# In classify.py

def classify(
    item: NewsItem,
    keyword_weights: Optional[Dict[str, float]] = None,
    precomputed_enrichment: Optional[Dict[str, Any]] = None,  # NEW PARAMETER
) -> ClassificationResult:
    """
    Classify a news item with optional precomputed enrichment data.

    Args:
        item: News item to classify
        keyword_weights: Optional keyword weights
        precomputed_enrichment: Optional dict with keys:
            - float_data: Float enrichment data
            - vwap_data: VWAP enrichment data
            - rvol_data: RVol enrichment data

    Returns:
        Classification result
    """
    # ... existing classification logic ...

    # RVOL Integration (MODIFIED)
    rvol_multiplier = 1.0
    rvol_data = None

    if ticker and ticker.strip():
        # Check if precomputed data is available
        if precomputed_enrichment and "rvol_data" in precomputed_enrichment:
            rvol_data = precomputed_enrichment["rvol_data"]
            log.debug("using_precomputed_rvol ticker=%s", ticker)
        else:
            # Fallback to on-demand calculation (backward compatibility)
            try:
                from .rvol import calculate_rvol_intraday
                rvol_data = calculate_rvol_intraday(ticker)
            except Exception as e:
                log.debug("rvol_calculation_failed ticker=%s err=%s", ticker, str(e))

        if rvol_data:
            rvol_multiplier = rvol_data.get("multiplier", 1.0)
            # ... rest of RVol logic ...

    # Float Integration (MODIFIED - similar pattern)
    float_multiplier = 1.0
    float_data = None

    if ticker:
        if precomputed_enrichment and "float_data" in precomputed_enrichment:
            float_data = precomputed_enrichment["float_data"]
            log.debug("using_precomputed_float ticker=%s", ticker)
        else:
            try:
                from .float_data import get_float_data
                float_data = get_float_data(ticker)
            except Exception as e:
                log.debug("float_fetch_failed ticker=%s err=%s", ticker, str(e))

        if float_data:
            float_multiplier = float_data.get("multiplier", 1.0)
            # ... rest of float logic ...

    # VWAP Integration (MODIFIED - similar pattern)
    vwap_multiplier = 1.0
    vwap_data = None

    if ticker and ticker.strip():
        if precomputed_enrichment and "vwap_data" in precomputed_enrichment:
            vwap_data = precomputed_enrichment["vwap_data"]
            log.debug("using_precomputed_vwap ticker=%s", ticker)
        else:
            try:
                from .vwap_calculator import calculate_vwap, get_vwap_multiplier
                vwap_data = calculate_vwap(ticker)
            except Exception as e:
                log.debug("vwap_calculation_failed ticker=%s err=%s", ticker, str(e))

        if vwap_data:
            vwap_multiplier = get_vwap_multiplier(vwap_data)
            # ... rest of VWAP logic ...

    # ... continue with rest of classification ...
```

**Key Design Decisions**:
1. **Backward compatibility**: Falls back to on-demand calculation if precomputed data not provided
2. **Optional parameter**: Doesn't break existing code that calls `classify()` without enrichment
3. **Clear logging**: Logs when using precomputed vs on-demand data

---

### Phase 3: Integrate Batch Enrichment into runner.py (Day 2)

Modify `_cycle()` function in `runner.py` to batch-enrich all tickers upfront:

```python
# In runner.py:_cycle() function, around line 1065

def _cycle(log, settings, market_info: dict | None = None) -> None:
    """One ingest→dedupe→enrich→classify→alert pass with parallel enrichment."""

    # ... existing code (fetch feeds, dedupe, etc.) ...

    # Quick metrics
    tickers_present = sum(1 for it in deduped if (it.get("ticker") or "").strip())
    tickers_missing = len(deduped) - tickers_present

    # ============================================================================
    # PARALLEL BATCH ENRICHMENT (NEW)
    # ============================================================================
    # Extract all unique tickers that need enrichment
    all_tickers = list(
        set(it.get("ticker") for it in deduped if (it.get("ticker") or "").strip())
    )

    # Batch-fetch enrichment data for ALL tickers in parallel
    enrichment_data = {}
    if all_tickers:
        try:
            from .enrichment import batch_enrich_all

            log.info("batch_enrichment_start tickers=%d", len(all_tickers))
            enrichment_start = time.time()

            enrichment_data = batch_enrich_all(all_tickers)

            enrichment_elapsed = time.time() - enrichment_start
            log.info(
                "batch_enrichment_complete tickers=%d elapsed=%.2fs",
                len(all_tickers),
                enrichment_elapsed,
            )
        except Exception as e:
            log.warning(
                "batch_enrichment_failed err=%s falling_back_to_sequential",
                e.__class__.__name__,
            )
            enrichment_data = {}

    # ============================================================================
    # PERFORMANCE OPTIMIZATION: Batch-fetch all prices at once (EXISTING CODE)
    # ============================================================================
    price_cache = {}
    if all_tickers and price_ceiling is not None:
        try:
            price_cache = market.batch_get_prices(all_tickers)
            log.info(
                "batch_price_fetch tickers=%d cached=%d",
                len(all_tickers),
                len(price_cache),
            )
        except Exception as e:
            log.warning(
                "batch_price_fetch_failed err=%s falling_back_to_sequential",
                e.__class__.__name__,
            )
            price_cache = {}

    # ... existing skip counters and loop setup ...

    for it in deduped:
        ticker = (it.get("ticker") or "").strip()
        source = it.get("source") or "unknown"

        # ... existing skip logic (seen, source, ticker, instrument, etc.) ...

        # ========================================================================
        # CLASSIFY WITH PRECOMPUTED ENRICHMENT (MODIFIED)
        # ========================================================================
        try:
            # Get precomputed enrichment data for this ticker
            precomputed = enrichment_data.get(ticker) if ticker else None

            scored = classify(
                item=market.NewsItem.from_feed_dict(it),
                keyword_weights=dyn_weights,
                precomputed_enrichment=precomputed,  # NEW: Pass precomputed data
            )
        except Exception as err:
            # ... existing error handling ...

        # ... rest of alert logic (price gating, scoring, sending alerts) ...
```

**Key Changes**:
1. **Lines ~1065-1090**: Extract unique tickers and batch-enrich BEFORE classification loop
2. **Lines ~1170-1175**: Pass `precomputed_enrichment` parameter to `classify()`
3. **Backward compatible**: If `batch_enrich_all()` fails, falls back to sequential (existing behavior)

---

### Phase 4: Configuration and Feature Flags (Day 2)

Add configuration options in `config.py`:

```python
# In config.py

class Settings:
    # ... existing settings ...

    # Parallel Enrichment Configuration
    feature_parallel_enrichment: bool = True  # Master enable/disable
    parallel_enrichment_max_float_workers: int = 10  # Finviz rate limiting
    parallel_enrichment_max_vwap_workers: int = 15  # yfinance concurrency
    parallel_enrichment_max_rvol_workers: int = 15  # yfinance concurrency
    parallel_enrichment_timeout_sec: int = 30  # Per-ticker timeout
```

Add environment variable overrides:

```bash
# .env.example

# Parallel Enrichment Settings (Performance Optimization)
FEATURE_PARALLEL_ENRICHMENT=1  # Enable/disable parallel ticker enrichment
PARALLEL_MAX_FLOAT_WORKERS=10  # Max concurrent Finviz scrapes (rate limited)
PARALLEL_MAX_VWAP_WORKERS=15   # Max concurrent VWAP calculations
PARALLEL_MAX_RVOL_WORKERS=15   # Max concurrent RVol calculations
PARALLEL_TIMEOUT_SEC=30        # Timeout per ticker (seconds)
```

---

### Phase 5: Error Handling and Graceful Degradation (Day 3)

Implement robust error handling with fallback to sequential processing:

```python
# In enrichment.py

def batch_enrich_all_safe(
    tickers: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Safe version of batch_enrich_all with fallback to sequential.

    If batch enrichment fails, gracefully falls back to sequential
    on-demand enrichment during classification (existing behavior).

    Returns:
        Enrichment data dict, or empty dict if batch fails
    """
    try:
        return batch_enrich_all(tickers)
    except Exception as e:
        log.error(
            "batch_enrich_all_failed err=%s falling_back_to_sequential",
            e.__class__.__name__,
            exc_info=True,
        )
        return {}  # Empty dict triggers fallback in classify()
```

**Fallback Strategy**:
1. If `batch_enrich_all()` fails → empty dict → `classify()` uses on-demand enrichment
2. If individual ticker fails → None value → `classify()` handles gracefully
3. If thread pool hangs → timeout → log warning and continue
4. **No cycle crashes**: All failures are logged but don't stop the main loop

---

## Testing Strategy

### Phase 1: Unit Tests

```python
# tests/test_enrichment.py

def test_batch_get_float_data():
    """Test batch float data fetching."""
    tickers = ["AAPL", "MSFT", "GOOGL"]
    results = batch_get_float_data(tickers, max_workers=3)

    assert len(results) == 3
    for ticker in tickers:
        assert ticker in results
        # Results can be None (ticker not found) or dict (success)
        assert results[ticker] is None or isinstance(results[ticker], dict)


def test_batch_get_vwap_data():
    """Test batch VWAP data fetching."""
    tickers = ["AAPL", "MSFT"]
    results = batch_get_vwap_data(tickers, max_workers=2)

    assert len(results) == 2
    assert all(ticker in results for ticker in tickers)


def test_batch_get_rvol_data():
    """Test batch RVol data fetching."""
    tickers = ["AAPL", "MSFT"]
    results = batch_get_rvol_data(tickers, max_workers=2)

    assert len(results) == 2
    assert all(ticker in results for ticker in tickers)


def test_batch_enrich_all():
    """Test combined batch enrichment."""
    tickers = ["AAPL", "MSFT"]
    results = batch_enrich_all(tickers)

    assert len(results) == 2
    for ticker in tickers:
        assert ticker in results
        enrichment = results[ticker]
        assert "float_data" in enrichment
        assert "vwap_data" in enrichment
        assert "rvol_data" in enrichment


def test_batch_enrich_empty_list():
    """Test batch enrichment with empty list."""
    results = batch_enrich_all([])
    assert results == {}


def test_batch_enrich_invalid_ticker():
    """Test batch enrichment with invalid ticker."""
    results = batch_enrich_all(["INVALID_TICKER_12345"])
    assert len(results) == 1
    assert results["INVALID_TICKER_12345"]["float_data"] is None
```

### Phase 2: Integration Tests

```python
# tests/test_parallel_runner.py

def test_cycle_with_parallel_enrichment(mocker):
    """Test runner cycle with parallel enrichment enabled."""
    from catalyst_bot.runner import _cycle

    # Mock settings with parallel enrichment enabled
    settings = get_settings()
    settings.feature_parallel_enrichment = True

    # Mock feeds to return test data with known tickers
    mocker.patch("catalyst_bot.feeds.fetch_pr_feeds", return_value=[
        {
            "id": "test1",
            "ticker": "AAPL",
            "title": "Apple announces new product",
            "source": "prnewswire",
        },
        {
            "id": "test2",
            "ticker": "MSFT",
            "title": "Microsoft reports earnings",
            "source": "prnewswire",
        },
    ])

    # Run cycle
    _cycle(get_logger("test"), settings)

    # Verify batch enrichment was called
    # (Check logs or mock calls)


def test_cycle_fallback_to_sequential(mocker):
    """Test runner falls back to sequential when batch fails."""
    from catalyst_bot.runner import _cycle

    # Mock batch_enrich_all to fail
    mocker.patch(
        "catalyst_bot.enrichment.batch_enrich_all",
        side_effect=Exception("Batch failed"),
    )

    settings = get_settings()

    # Cycle should still complete without crashing
    _cycle(get_logger("test"), settings)
```

### Phase 3: Performance Benchmarks

```python
# tests/test_enrichment_performance.py

import time
from catalyst_bot.enrichment import batch_enrich_all
from catalyst_bot.float_data import get_float_data
from catalyst_bot.vwap_calculator import calculate_vwap
from catalyst_bot.rvol import calculate_rvol_intraday


def test_performance_sequential_vs_parallel():
    """Benchmark sequential vs parallel enrichment."""
    tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA",
               "AMD", "INTC", "QCOM", "AVGO", "TXN"]

    # Sequential baseline
    start = time.time()
    for ticker in tickers:
        get_float_data(ticker)
        calculate_vwap(ticker)
        calculate_rvol_intraday(ticker)
    sequential_time = time.time() - start

    # Parallel version
    start = time.time()
    batch_enrich_all(tickers)
    parallel_time = time.time() - start

    speedup = sequential_time / parallel_time

    print(f"Sequential: {sequential_time:.2f}s")
    print(f"Parallel: {parallel_time:.2f}s")
    print(f"Speedup: {speedup:.2f}x")

    # Assert at least 3x speedup
    assert speedup >= 3.0, f"Expected 3x speedup, got {speedup:.2f}x"
```

---

## Rollout Plan

### Week 1: Development and Testing

**Day 1 (4 hours)**:
- Create `enrichment.py` with batch functions
- Add unit tests for batch functions
- Test with 5-10 tickers to verify functionality

**Day 2 (4 hours)**:
- Modify `classify.py` to accept precomputed data
- Update `runner.py` to call batch enrichment
- Add configuration options and feature flags

**Day 3 (4 hours)**:
- Add error handling and fallback logic
- Create integration tests
- Performance benchmarks with 50+ tickers

### Week 2: Production Rollout

**Day 1 (Monitoring)**:
- Deploy with `FEATURE_PARALLEL_ENRICHMENT=1`
- Monitor cycle times in `data/logs/bot.jsonl`
- Expected log pattern:
  ```
  batch_enrichment_start tickers=47
  batch_float_complete tickers=47 success=45 elapsed=12.34s
  batch_vwap_complete tickers=47 success=44 elapsed=7.89s
  batch_rvol_complete tickers=47 success=46 elapsed=8.12s
  batch_enrichment_complete tickers=47 elapsed=15.23s
  CYCLE_DONE took=68.45s
  ```

**Day 2-7 (Optimization)**:
- Fine-tune `max_workers` values based on actual performance
- Adjust timeouts if needed
- Monitor error rates and fallback frequency

---

## Monitoring and Metrics

### Log Patterns to Monitor

**Success Pattern**:
```
batch_enrichment_start tickers=50
batch_float_complete tickers=50 success=48 elapsed=12.5s
batch_vwap_complete tickers=50 success=49 elapsed=8.2s
batch_rvol_complete tickers=50 success=47 elapsed=7.8s
batch_enrichment_complete tickers=50 elapsed=16.3s
CYCLE_DONE took=72.1s
```

**Fallback Pattern** (batch failed, using sequential):
```
batch_enrichment_failed err=TimeoutError falling_back_to_sequential
using_sequential_rvol ticker=AAPL
using_sequential_float ticker=AAPL
using_sequential_vwap ticker=AAPL
CYCLE_DONE took=442.8s
```

### Performance Metrics to Track

```python
# Add to runner.py after cycle completion
metrics = {
    "cycle_time_sec": cycle_time,
    "batch_enrichment_time_sec": enrichment_elapsed if enrichment_data else None,
    "batch_enrichment_ticker_count": len(all_tickers),
    "batch_enrichment_success_rate": (
        sum(1 for e in enrichment_data.values()
            if e.get("float_data") or e.get("vwap_data") or e.get("rvol_data"))
        / len(enrichment_data)
        if enrichment_data else 0
    ),
    "sequential_fallback_used": len(enrichment_data) == 0,
}

log.info("cycle_performance %s", json.dumps(metrics))
```

---

## Risk Mitigation

### Risk 1: Thread Pool Hangs
**Mitigation**: Use `timeout` parameter on `as_completed()` and individual `future.result()`
**Fallback**: Kill hung threads after timeout, log warning, continue with partial results

### Risk 2: Rate Limiting (Finviz/yfinance)
**Mitigation**:
- Finviz: Use `max_workers=10` with existing 2-3s delays built into `get_float_data()`
- yfinance: Use `max_workers=15` (tested to handle this concurrency)
**Fallback**: If rate-limited, individual ticker enrichment returns None (classify() handles gracefully)

### Risk 3: Memory Usage Spike
**Mitigation**: Limit `max_workers` to prevent spawning 100+ threads
**Monitoring**: Track memory usage before/after batch enrichment
**Fallback**: Reduce `max_workers` in config if memory issues occur

### Risk 4: Partial Enrichment Data
**Mitigation**: Each ticker's enrichment is independent - partial results are OK
**Handling**: `classify()` checks each data field individually, applies multipliers only when data exists
**No crashes**: Missing data → multiplier defaults to 1.0 (no change to score)

---

## Expected Results

### Performance Improvement
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Cycle time** | 448s | 60-90s | **5-7x faster** |
| Float scraping | 150s | 12-15s | 10x faster |
| VWAP calculation | 35s | 7-10s | 4x faster |
| RVol calculation | 35s | 7-10s | 4x faster |
| Items/hour | ~500 | ~2500 | 5x throughput |

### System Impact
- ✅ **CPU usage**: Temporary spike during batch enrichment, then idle during classification
- ✅ **Memory usage**: +50-100MB for thread pool overhead (acceptable)
- ✅ **Network**: Same total API calls, just parallelized
- ✅ **Error rate**: No increase (fallback to sequential on failure)
- ✅ **Code complexity**: Minimal - 1 new file, 2 modified functions

---

## Success Criteria

**Must Have** (Week 1):
- [ ] `enrichment.py` created with batch functions
- [ ] `classify.py` accepts precomputed data
- [ ] `runner.py` calls batch enrichment before classification loop
- [ ] Unit tests pass for batch functions
- [ ] Integration test shows cycle time reduction

**Should Have** (Week 2):
- [ ] Performance benchmarks show 3x+ speedup
- [ ] Error handling tested with mock failures
- [ ] Fallback to sequential works correctly
- [ ] Production deployment successful with monitoring

**Nice to Have** (Future):
- [ ] Dynamic worker pool sizing based on ticker count
- [ ] Prometheus metrics export for cycle performance
- [ ] Web UI dashboard showing enrichment stats

---

## Conclusion

This implementation provides a **significant performance boost (5-7x)** with **minimal risk** due to robust fallback mechanisms. The parallel enrichment architecture is:

✅ **Backward compatible**: Falls back to existing sequential behavior on failure
✅ **Modular**: New `enrichment.py` module, minimal changes to existing code
✅ **Configurable**: Feature flags and worker pool sizing via environment variables
✅ **Observable**: Detailed logging of batch operations and performance metrics
✅ **Production-ready**: Comprehensive error handling, timeouts, and graceful degradation

**Next Steps**: Create `enrichment.py` and run initial performance benchmarks with 10-20 tickers to validate the approach before full integration.
