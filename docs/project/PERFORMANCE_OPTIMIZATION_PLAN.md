# Final Optimization Plan - Catalyst Bot

## Current Performance
- **Baseline**: 86.92s per cycle (from profiling)
- **After Wave 1 Improvements**: 52-57s per cycle
  - Batch price lookups: 43s → 1.7s (25x speedup)
  - Async feed fetching: 40s → 2-4s (10-20x speedup)

## Remaining Bottleneck (CRITICAL DISCOVERY)
**Sequential price calls in feeds.py lines 1723-1760** are happening BEFORE runner.py's batch fetch, causing 20-30s of wasted sequential lookups.

---

## **PHASE 0 - FIX FEEDS.PY PRICE FILTERING** ⚡ **HIGHEST PRIORITY**

**Impact**: Save 20-30 seconds per cycle (40-50% speedup)

**Changes**:
1. Disable price filtering in `src/catalyst_bot/feeds.py`:
   - Comment out/remove lines 1723-1737 (price floor filtering)
   - Comment out/remove lines 1740-1760 (price ceiling filtering)

2. Keep ALL price filtering in `src/catalyst_bot/runner.py`:
   - Lines 1074-1091 already handle price ceiling check using batch cache
   - Add price floor check in same location using batch cache

**Why This Works**:
- Runner.py already has `batch_get_prices()` cache with all prices fetched in 1.7s
- Feeds.py makes 100+ sequential `get_last_price_snapshot()` calls taking 20-30s
- Moving filtering to runner.py = zero additional cost (prices already cached)

**Verification**:
- Price filtering functionality preserved (just moved to better location)
- No behavior change, only performance improvement

---

## **PHASE 1 - REDIS SENTIMENT CACHING**

**Impact**: Save 5-10 seconds per cycle (10-15% speedup)

**Implementation**:
1. Enable Redis caching for LLM sentiment analysis
2. Use semantic similarity matching (95% threshold)
3. Expected cache hit rate: 15-30% for PR blasts

**Files**:
- `src/catalyst_bot/llm_cache.py` (already exists)
- `src/catalyst_bot/classify.py` - integrate cache checks

**Requirements**:
```bash
pip install redis sentence-transformers
```

**Environment Variables**:
```env
REDIS_URL=redis://localhost:6379
LLM_CACHE_SIMILARITY=0.95
LLM_CACHE_TTL=86400
```

---

## **PHASE 2 - PARALLEL CLASSIFICATION**

**Impact**: Save 10-15 seconds per cycle (20-25% speedup)

**Implementation**:
1. Use `ThreadPoolExecutor` for CPU-bound classification
2. Process 3-5 items concurrently (limited by CPU cores)
3. Combine with Redis caching for maximum benefit

**Changes**:
```python
# src/catalyst_bot/runner.py
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(classify, item) for item in deduped]
    scored = [f.result() for f in futures]
```

---

## **PHASE 3 - GPU OPTIMIZATION (IF AVAILABLE)**

**Impact**: Save 3-5 seconds per cycle (5-10% speedup) if GPU present

**Implementation**:
1. Enable CUDA streams for parallel sentiment analysis
2. Batch inference instead of sequential calls
3. GPU memory pooling to reduce allocation overhead

**Files**:
- `src/catalyst_bot/ml/cuda_streams.py` (already exists)
- `src/catalyst_bot/ml/batch_sentiment.py` (already exists)

**Check GPU Availability**:
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

**Skip if**: No CUDA-capable GPU detected

---

## **PHASE 4 - SMART DEDUPLICATION**

**Impact**: Save 2-3 seconds per cycle (3-5% speedup)

**Implementation**:
1. Pre-filter duplicate headlines before expensive processing
2. Use fuzzy matching to catch PR blast variations
3. Reduce items entering classification pipeline by 20-30%

**Changes**:
```python
# Early deduplication with fuzzy matching
from difflib import SequenceMatcher

def fuzzy_dedupe(items, threshold=0.85):
    seen = []
    unique = []
    for item in items:
        if not any(SequenceMatcher(None, item['title'], s).ratio() > threshold for s in seen):
            unique.append(item)
            seen.append(item['title'])
    return unique
```

---

## **PHASE 5 - ASYNC LLM CALLS**

**Impact**: Save 3-5 seconds per cycle (5-8% speedup)

**Implementation**:
1. Switch from sync to async LLM client for concurrent queries
2. Connection pooling with aiohttp (already implemented in `llm_async.py`)
3. Circuit breaker pattern for failure handling

**Files**:
- `src/catalyst_bot/llm_async.py` (already exists)
- Update `src/catalyst_bot/classify.py` to use `query_llm_async()`

---

## **PROJECTED TOTAL IMPROVEMENTS**

| Phase | Time Saved | Cumulative Time | % Improvement |
|-------|-----------|-----------------|---------------|
| Current (Wave 1) | - | 52-57s | 35-40% vs baseline |
| **Phase 0** (feeds.py fix) | **20-30s** | **22-37s** | **60-75% total** |
| Phase 1 (Redis cache) | 5-10s | 12-32s | 75-85% total |
| Phase 2 (parallel classify) | 10-15s | 2-22s | 85-97% total |
| Phase 3 (GPU - optional) | 3-5s | 0-19s | 90-100% total |
| Phase 4 (smart dedupe) | 2-3s | 0-17s | 95-100% total |
| Phase 5 (async LLM) | 3-5s | 0-14s | 97-100% total |

**Target Performance**: **10-15 seconds per cycle** (83-85% improvement from baseline)

---

## **IMPLEMENTATION ORDER**

**Recommended sequence**:
1. ✅ **Phase 0 FIRST** - Biggest single impact, simplest change
2. Phase 1 - Redis caching (requires Redis server)
3. Phase 2 - Parallel classification (works with Phase 1)
4. Phase 4 - Smart deduplication (low risk, good ROI)
5. Phase 5 - Async LLM (marginal gains after Phases 1-2)
6. Phase 3 - GPU optimization (only if hardware available)

---

## **NEXT STEPS**

1. **Confirm plan approval**
2. **Implement Phase 0** (feeds.py fix) - ~5 minutes
3. **Test and measure** - verify 20-30s improvement
4. **Proceed to Phase 1** (Redis) if Phase 0 successful
5. **Iterate through remaining phases** based on results
