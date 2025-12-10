# Phase 2 Performance Optimization - Implementation Tickets

**Created:** December 10, 2025
**Status:** Ready for Implementation
**Total Estimated Effort:** 12-15 hours

## Overview

This directory contains detailed implementation tickets for Phase 2 SEC performance optimizations. These tickets were created after cross-referencing the original optimization plan against the existing codebase to identify gaps and avoid duplication.

## Key Findings from Assessment

| Original Proposal | Codebase Status | Recommendation |
|-------------------|-----------------|----------------|
| 2.1 Price Pre-Filter | Partial (split between runner.py/feeds.py) | P4: Add unified pre-filter |
| 2.2 LRU Cache | Does NOT exist | P3: Implement |
| 2.3 Async-Safe seen_store | Partial (thread-safe only, deactivated in async) | P2: Critical fix |
| 2.4 Dynamic Concurrency | Exists (static value) | Skip - low ROI |
| 2.5 LLM Response Caching | 3 caches exist but RSS path MISSING integration | P1: Integrate existing cache |

### Critical Discovery: Two Separate SEC Pipelines

```
PATH 1: RSS Feed Enrichment (feeds.py) ❌ NO CACHE
─────────────────────────────────────────────────
feeds.py → _enrich_sec_items_batch() → _enrich_sec_filing_with_llm()
         → analyze_sec_filing() → query_llm() [NO CACHE CHECK!]

PATH 2: Batch Processing (runner.py) ✅ USES CACHE
─────────────────────────────────────────────────
runner.py → batch_extract_keywords_from_documents()
          → cache.get_cached_sec_analysis() → LLM if miss → cache result
```

## Implementation Tickets

| Priority | Ticket | Impact | Effort | File |
|----------|--------|--------|--------|------|
| **P1** | [SECLLMCache Integration](./P1-SEC-LLM-CACHE-INTEGRATION.md) | High - 40-50% LLM cost reduction | 3 hrs | feeds.py |
| **P2** | [Async-Safe seen_store](./P2-ASYNC-SAFE-SEEN-STORE.md) | High - 70-80% dedup savings | 4 hrs | seen_store.py, feeds.py |
| **P3** | [LRU Cache Layer](./P3-LRU-CACHE-SEEN-STORE.md) | Medium - 100x faster lookups | 4-5 hrs | seen_store.py |
| **P4** | [Price Pre-Filter](./P4-PRICE-PREFILTER-FEEDS.md) | Medium - 15-20% LLM savings | 3-4 hrs | feeds.py |
| **P5** | [Remove Dead Code](./P5-REMOVE-DEAD-SEMANTIC-CACHE.md) | Low - cleanup | 0.5 hrs | llm_cache.py |

## Recommended Implementation Order

### Week 1: High-Impact Fixes
1. **P1: SECLLMCache Integration** (3 hrs)
   - Integrate existing cache into RSS path
   - Expected: 40-50% reduction in LLM API calls

2. **P2: Async-Safe seen_store** (4 hrs)
   - Enable pre-filtering of duplicate SEC filings
   - Expected: 70-80% reduction in unnecessary enrichment

### Week 2: Performance Optimization
3. **P3: LRU Cache Layer** (4-5 hrs)
   - Add in-memory caching for dedup lookups
   - Expected: 100x faster lookup performance

4. **P4: Price Pre-Filter** (3-4 hrs)
   - Filter expensive stocks before LLM
   - Expected: 15-20% additional LLM savings

### Cleanup
5. **P5: Remove Dead Code** (0.5 hrs)
   - Delete unused SemanticLLMCache
   - Reduces maintenance burden

## Expected Combined Impact

| Metric | Current | After Phase 2 | Improvement |
|--------|---------|---------------|-------------|
| Cycle time | ~320s | 120-150s | 2-2.5x faster |
| LLM calls/cycle | 137 | 20-40 | 70-85% reduction |
| Dedup lookup time | 10ms | 0.1ms | 100x faster |
| Daily API cost | ~$1.80 | ~$0.40 | $1.40 saved |

## Usage with Claude Code CLI

Each ticket is designed to be self-contained for vibecoding with Claude Code:

```bash
# Example: Implement P1
claude "Read docs/performance/implementation-tickets/P1-SEC-LLM-CACHE-INTEGRATION.md and implement the changes described"

# Example: Implement P2
claude "Read docs/performance/implementation-tickets/P2-ASYNC-SAFE-SEEN-STORE.md and implement the thread-local connection changes"
```

## Related Documentation

- [SEC Performance Optimization Plan](../SEC_PERFORMANCE_OPTIMIZATION_PLAN.md) - Original Phase 1/2 plan
- [SEC Implementation Summary](../../sec/SEC_IMPLEMENTATION_SUMMARY.md) - Overall SEC architecture

## Risk Summary

| Ticket | Risk Level | Rollback Method |
|--------|------------|-----------------|
| P1 | LOW | Env var: `FEATURE_SEC_LLM_CACHE=0` |
| P2 | MEDIUM | Re-comment pre-filter code |
| P3 | LOW | Env var: `SEEN_STORE_CACHE_ENABLED=0` |
| P4 | LOW | Env var: `SEC_PRICE_FILTER_ENABLED=0` |
| P5 | MINIMAL | Git revert |
