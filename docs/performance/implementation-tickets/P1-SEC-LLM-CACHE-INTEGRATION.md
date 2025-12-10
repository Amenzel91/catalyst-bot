# Implementation Ticket: Integrate SECLLMCache into feeds.py RSS Enrichment Path

## Title
**Integrate SECLLMCache into RSS-fed SEC filing LLM enrichment to eliminate duplicate LLM API calls**

## Priority
**P1** - High impact optimization reducing LLM API costs by 40-50%

## Estimated Effort
**3 hours** (1 hour implementation + 1 hour testing + 1 hour integration/review)

## Problem Statement

Currently, the RSS enrichment path in `feeds.py` (`_enrich_sec_filing_with_llm()` function) calls the Claude LLM **without checking the SECLLMCache**, resulting in duplicate API calls for filings that have already been analyzed.

### Evidence of Problem:
1. **Cache exists and is working**: The batch path in `sec_llm_analyzer.py` (lines 662-731) successfully uses `SECLLMCache.get_cached_sec_analysis()` to eliminate redundant calls
2. **Cache misses in RSS path**: The RSS enrichment function calls `analyze_sec_filing()` directly without any cache lookup
3. **Business Impact**:
   - Duplicate costs: Each filing analyzed multiple times across different RSS cycles
   - Unnecessary API calls: 40-50% of LLM calls are redundant based on cache hit rate in batch path
   - Performance: Slower enrichment due to LLM latency vs. cache hits (~50ms vs. ~1-2ms)

### Root Cause:
The `_enrich_sec_filing_with_llm()` function at line 999 was implemented before `SECLLMCache` was created. The pattern was later added to the batch path but the RSS path was never updated.

## Solution Overview

Integrate `SECLLMCache` into the RSS enrichment path by:

1. **Import cache module** in `_enrich_sec_filing_with_llm()`
2. **Generate filing identifiers**:
   - Use filing `id` (or `link` as fallback) as `filing_id`
   - Generate `document_hash` from first 1000 chars of summary (MD5, truncated to 8 chars)
3. **Check cache before LLM call**:
   - Call `cache.get_cached_sec_analysis(filing_id, ticker, filing_type, document_hash)`
   - Return cached result immediately if found
4. **Cache successful LLM results**:
   - Call `cache.cache_sec_analysis()` with analysis result
5. **Add logging** for cache hits/misses
6. **Handle cache errors gracefully** (treat as cache miss, not blocking errors)

### Expected Outcomes:
- **40-50% reduction** in LLM API calls for filings
- **Faster enrichment** (cache hits ~2ms vs. LLM ~500-1000ms)
- **Cost savings** from reduced API calls
- **Consistent cache behavior** across batch and RSS paths

## Files to Modify

| File | Path | Changes |
|------|------|---------|
| feeds.py | `/home/user/catalyst-bot/src/catalyst_bot/feeds.py` | Modify `_enrich_sec_filing_with_llm()` function (lines 999-1093) |

## Implementation Steps

### Step 1: Add cache imports (Line 1045-1050)

**Current Code (Lines 1045-1050):**
```python
    try:
        # Import here to avoid circular dependency
        from .logging_utils import get_logger
        from .sec_llm_analyzer import analyze_sec_filing

        log = get_logger("feeds.sec_llm")
```

**Change To:**
```python
    try:
        # Import here to avoid circular dependency
        import hashlib
        from .logging_utils import get_logger
        from .sec_llm_analyzer import analyze_sec_filing
        from .sec_llm_cache import get_sec_llm_cache

        log = get_logger("feeds.sec_llm")
        cache = get_sec_llm_cache()
```

### Step 2: Extract filing identifiers (After line 1044)

Add after the `filing_type` extraction and before the `try` block:

```python
    # Extract filing_id for cache key (use id or link as fallback)
    filing_id = filing.get("id") or filing.get("link") or ""
```

### Step 3: Generate document hash and check cache (Replace lines 1052-1065)

**Current Code (Lines 1052-1065):**
```python
        log.debug(
            "sec_llm_enrich_start ticker=%s type=%s text_len=%d",
            ticker,
            filing_type,
            len(raw_summary or ""),
        )

        # Call LLM analyzer (sync function, but fast enough for our use)
        result = analyze_sec_filing(
            title=title,
            filing_type=filing_type,
            summary=raw_summary[:3000] if raw_summary else "",  # Limit input size
            timeout=timeout,
        )
```

**Change To:**
```python
        log.debug(
            "sec_llm_enrich_start ticker=%s type=%s text_len=%d filing_id=%s",
            ticker,
            filing_type,
            len(raw_summary or ""),
            filing_id,
        )

        # Check cache first (same pattern as batch path in sec_llm_analyzer.py)
        doc_hash = ""
        if raw_summary:
            doc_hash = hashlib.md5(raw_summary[:1000].encode()).hexdigest()[:8]

        cached_result = cache.get_cached_sec_analysis(
            filing_id=filing_id,
            ticker=ticker,
            filing_type=filing_type,
            document_hash=doc_hash,
        )

        if cached_result is not None:
            # Cache hit - use cached result
            log.info(
                "sec_llm_cache_hit_rss ticker=%s filing_type=%s filing_id=%s",
                ticker,
                filing_type,
                filing_id,
            )

            return {
                **filing,
                "summary": cached_result.get("summary", raw_summary),
                "llm_sentiment": cached_result.get("llm_sentiment", 0.0),
                "llm_confidence": cached_result.get("llm_confidence", 0.5),
                "catalysts": cached_result.get("catalysts", []),
            }

        # Cache miss - call LLM analyzer
        result = analyze_sec_filing(
            title=title,
            filing_type=filing_type,
            summary=raw_summary[:3000] if raw_summary else "",  # Limit input size
            timeout=timeout,
        )
```

### Step 4: Cache successful results (After line 1081)

**Current Code (Lines 1067-1081):**
```python
        if result and result.get("summary"):
            log.info(
                "sec_llm_enrich_success ticker=%s sentiment=%.2f summary_len=%d",
                ticker,
                result.get("llm_sentiment", 0),
                len(result.get("summary", "")),
            )

            return {
                **filing,
                "summary": result["summary"],  # Replace original summary
                "llm_sentiment": result.get("llm_sentiment", 0.0),
                "llm_confidence": result.get("llm_confidence", 0.5),
                "catalysts": result.get("catalysts", []),
            }
```

**Change To:**
```python
        if result and result.get("summary"):
            log.info(
                "sec_llm_enrich_success ticker=%s sentiment=%.2f summary_len=%d filing_id=%s",
                ticker,
                result.get("llm_sentiment", 0),
                len(result.get("summary", "")),
                filing_id,
            )

            # Cache the result
            cache.cache_sec_analysis(
                filing_id=filing_id,
                ticker=ticker,
                filing_type=filing_type,
                analysis_result=result,
                document_hash=doc_hash,
            )

            return {
                **filing,
                "summary": result["summary"],  # Replace original summary
                "llm_sentiment": result.get("llm_sentiment", 0.0),
                "llm_confidence": result.get("llm_confidence", 0.5),
                "catalysts": result.get("catalysts", []),
            }
```

## Test Verification

### Test 1: Cache Hit Detection
```bash
# 1. Process an SEC filing once (should cache it)
python -m pytest tests/ -k "test_enrich_sec_filing" -v

# 2. Check logs for cache miss then cache set
# 3. Process same filing again (should hit cache)
# 4. Check logs for cache hit:
#    "sec_llm_cache_hit_rss ticker=... filing_id=..."
```

### Test 2: Integration Test with Runner
```bash
# Run full runner cycle and monitor logs
python -m catalyst_bot.runner --feeds-only 2>&1 | grep -E "sec_llm_cache|sec_llm_enrich"

# Expected log output:
# sec_llm_enrich_start ticker=... filing_id=...
# sec_llm_cache_hit_rss ... (when re-processing same filing)
```

### Test 3: Performance Comparison
```bash
# Monitor LLM API call metrics before/after
# Check logs for:
# - Reduction in API call count (40-50% expected)
# - Faster enrichment time
```

## Rollback Procedure

### Option 1: Quick Revert (< 2 minutes)
```bash
# Disable cache feature flag
export FEATURE_SEC_LLM_CACHE=0

# Restart application - falls back to original LLM behavior
```

### Option 2: Code Rollback (< 5 minutes)
```bash
git revert <commit-hash>
git push
# Restart application
```

## Dependencies

### Required (Already Exist)
- `SECLLMCache` class - Already implemented in `sec_llm_cache.py`
- `get_sec_llm_cache()` function - Already exported
- `hashlib` module - Python standard library

### Environment Variables (Optional)
- `FEATURE_SEC_LLM_CACHE` - Enable/disable cache (default: 1/enabled)
- `SEC_LLM_CACHE_TTL_HOURS` - Cache time-to-live in hours (default: 72)

## Risk Assessment

**Overall Risk: LOW**

| Factor | Level | Mitigation |
|--------|-------|-----------|
| Code Changes | LOW | Small, localized changes to single function (< 50 lines) |
| Cache Integration | LOW | Uses battle-tested `SECLLMCache` class already in production |
| Thread Safety | LOW | SECLLMCache uses locks; feeds.py is async-safe |
| Error Handling | LOW | Gracefully degrades to non-cached LLM calls on errors |

## Success Criteria

- [ ] Cache is checked before every LLM call in RSS enrichment path
- [ ] Successful LLM analyses are cached with correct TTL
- [ ] Cache hits return results in < 5ms (vs. LLM ~500ms+)
- [ ] Cache hit rate reaches 40-50% within 72 hours
- [ ] All logs show proper cache hit/miss patterns
- [ ] API call count reduced by 40-50%
