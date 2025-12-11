# Ticker Extraction Improvements - Implementation Plan

**Date**: 2025-12-11
**Goal**: Improve ticker extraction success rate from ~40% to ~85%+ overall
**Scope**: 3 priority fixes (CIK mapping, pattern enhancement, Finviz feed switch)

---

## Problem Summary

Current ticker extraction has significant gaps:
- **SEC filings**: ~8% success rate (6,274 filings/day, almost all fail)
- **GlobeNewswire/PR wires**: ~50% success rate (pattern matching incomplete)
- **Finviz CSV feed**: 0% success rate (no ticker column exists)

**Impact**: High-quality content (73 items scoring >1.0) being filtered as `ticker=N/A`

---

## Priority 1: SEC Filing CIK-to-Ticker Mapping

### Problem
SEC RSS feeds provide CIK numbers in URLs but no ticker symbols. Example:
- URL: `/edgar/data/0001018724/0001018724-24-001234.txt`
- Title: `8-K - Amazon.com Inc. (0001018724) (Filer)`
- Current extraction: Fails because "Amazon.com Inc." doesn't match ticker patterns
- Available data not used: CIK `0001018724`

### Solution Approach
Add CIK extraction and mapping layer in SEC filing processing pipeline.

### Files to Modify

**1. `src/catalyst_bot/ticker_map.py`** (Extend existing CIK functionality)
- Add function to fetch CIK-to-ticker mappings from SEC EDGAR API
- SEC endpoint: `https://www.sec.gov/files/company_tickers.json`
- Returns: `{cik: ticker}` mappings for all public companies
- Cache in SQLite database (existing `data/tickers.db` or new table)
- Add refresh mechanism (daily/weekly API fetch)

**2. `src/catalyst_bot/feeds.py`** (Update SEC processing)
- Modify `_enrich_sec_items_batch()` function (~line 1150-1200)
- Before LLM enrichment, attempt CIK extraction:
  - Extract CIK from item URL using existing `_CIK_RE` pattern
  - Look up ticker using new CIK mapping
  - If found, set `item['ticker']` and skip to next item
  - If not found, continue with existing LLM enrichment path
- Add logging for CIK extraction success/failure

**3. `src/catalyst_bot/sec_prefilter.py`** (Enhance extraction strategy)
- Update `extract_ticker_from_filing()` function
- Add Strategy 0 (before existing strategies): CIK lookup
- Extract CIK from `filing.item_id` URL
- Call new ticker_map function for CIK→ticker resolution
- Fall back to existing strategies if CIK lookup fails

### Implementation Notes
- Use existing `_CIK_RE` regex pattern from ticker_map.py
- SEC API has rate limits - implement exponential backoff
- Cache mappings in SQLite to minimize API calls
- CIK numbers may be zero-padded (handle both `1018724` and `0001018724`)
- Add User-Agent header for SEC API compliance
- Consider background refresh job to keep mappings current

### Expected Impact
- SEC filing ticker extraction: 8% → **95%+**
- LLM enrichment calls: Reduce by ~30% (CIK lookup is faster/cheaper)
- Processing speed: Faster (no LLM needed for most SEC items)

---

## Priority 2: Enhanced Pattern Matching for PR Wires

### Problem
Current regex patterns only catch standard formats like `(NASDAQ: AAPL)`. Many press releases use variations:
- "trades on NASDAQ under symbol AAPL"
- "listed on NYSE as BA"
- "ticker symbol: TSLA"

These valid tickers are missed, causing 40-50% of GlobeNewswire items to fail extraction.

### Solution Approach
Extend pattern matching in `title_ticker.py` to cover broader formats.

### Files to Modify

**1. `src/catalyst_bot/title_ticker.py`** (Add pattern variants)
- Add new regex patterns to existing pattern matching logic
- New patterns to support:
  - `listed on {EXCHANGE} (under |as )?{TICKER}`
  - `trades? (on|under) (ticker )?(symbol )?{TICKER}`
  - `ticker symbol:?\s+{TICKER}`
  - `symbol:?\s+{TICKER}`
- Maintain priority order: Try existing patterns first, fall back to new patterns
- Keep existing exclusion lists (don't break FDA, SEC, etc. filtering)

**2. Pattern ordering considerations**
- Most specific patterns first (exchange-qualified)
- Broader patterns last (to avoid false positives)
- Test against existing exclusion lists to ensure no regressions

### Implementation Notes
- Patterns should remain case-insensitive for exchange names
- Ticker extraction must still be uppercase `[A-Z]{2,5}`
- Add boundary checks to avoid partial word matches
- Consider summary fallback for items where title patterns fail
- Test with historical GlobeNewswire data to validate improvements

### Expected Impact
- GlobeNewswire ticker extraction: 50% → **70%+**
- Overall PR wire coverage: +10-15% improvement
- No change to existing successful extractions (additive only)

---

## Priority 4: Switch Finviz Feed from CSV to API Endpoint

### Problem
Current Finviz News Export CSV format provides **no ticker column**. Documentation in code states: "Events lack ticker information, so downstream logic should handle missing tickers gracefully."

Result: 100% ticker extraction failure for this feed.

### Solution Approach
Replace problematic CSV endpoint with `news_export.ashx` which includes ticker field.

### Files to Modify

**1. `src/catalyst_bot/feeds.py`** (Replace feed implementation)
- Locate Finviz CSV handler (~lines 3100-3187)
- Replace `_fetch_finviz_news_csv()` logic with `news_export.ashx` endpoint call
- New endpoint returns ticker data in structured format
- Reference existing `_fetch_finviz_news_from_env()` implementation (~lines 2947-3014) for pattern
- That function already handles `news_export.ashx` correctly with ticker field extraction
- Remove or deprecate CSV-specific code

**2. Configuration considerations**
- Check if `news_export.ashx` requires different authentication/subscription level
- Verify API rate limits differ from CSV endpoint
- Update any environment variables or config references to CSV endpoint
- May need to adjust polling frequency if rate limits differ

### Implementation Notes
- The `news_export.ashx` endpoint is already implemented in the codebase
- It successfully extracts tickers from the `ticker` CSV column
- Supports multi-ticker items (comma/semicolon separated)
- Existing code at lines 2962-2968 handles primary ticker extraction
- Main change: switch which endpoint is actively used, remove CSV logic

### Expected Impact
- Finviz ticker extraction: 0% → **92%+**
- Eliminates entire category of ticker=N/A items
- Cleaner codebase (remove CSV workaround logic)

---

## Testing & Validation

### For Each Priority:

1. **Unit tests**
   - CIK extraction from various URL formats
   - Pattern matching against diverse PR wire titles
   - Finviz feed parsing with ticker field

2. **Integration tests**
   - Run against recent 100 SEC filings (test CIK mapping)
   - Run against recent 100 GlobeNewswire items (test patterns)
   - Run against recent Finviz data (test new endpoint)

3. **Production validation**
   - Monitor `skipped_no_ticker` metric (should decrease)
   - Track ticker extraction success rate by feed source
   - Verify high-scoring items (>1.0) have valid tickers
   - Check for any new false positives from broader patterns

### Success Metrics

- Overall ticker extraction rate: **40% → 85%+**
- SEC filing extraction: **8% → 95%+**
- PR wire extraction: **50% → 70%+**
- Finviz extraction: **0% → 92%+**
- High-scoring ticker=N/A items: **73 → <5**

---

## Rollout Plan

### Phase 1: CIK Mapping (Highest Impact)
1. Implement CIK-to-ticker mapping in ticker_map.py
2. Integrate into SEC prefilter and feeds.py
3. Test with last 24 hours of SEC filings
4. Deploy and monitor for 1-2 days

### Phase 2: Pattern Enhancement (Quick Win)
1. Add new regex patterns to title_ticker.py
2. Test against historical GlobeNewswire data
3. Verify no false positives from exclusion lists
4. Deploy and monitor

### Phase 3: Finviz Feed Switch (Cleanup)
1. Verify subscription includes news_export.ashx access
2. Switch feed endpoint in feeds.py
3. Remove CSV-specific logic
4. Monitor for any API rate limit issues

---

## Notes for Implementation

- All changes should maintain backward compatibility where possible
- Add comprehensive logging for debugging (ticker extraction attempts, CIK lookups, etc.)
- Consider feature flags for gradual rollout (can disable CIK mapping if API issues occur)
- Update keyword weights may benefit from additional tickers being extracted (already done: 58 keywords active)
- Monitor LLM API costs - should decrease as fewer items need enrichment fallback

---

## Risk Mitigation

**CIK Mapping Risks**:
- SEC API downtime → Fall back to existing LLM enrichment
- Rate limits → Cache aggressively, implement retry logic
- Stale mappings → Refresh daily/weekly

**Pattern Matching Risks**:
- False positives → Keep exclusion lists, test thoroughly
- Breaking existing extractions → Add new patterns as fallback only

**Finviz Feed Risks**:
- Different subscription tier required → Validate access before deploying
- Rate limit changes → Monitor and adjust polling frequency

---

## Future Enhancements (Out of Scope)

- Multi-ticker article handling improvements
- Machine learning-based ticker extraction
- Company name → ticker resolution via external APIs
- Real-time ticker validation against exchange APIs

---

**Document Version**: 1.0
**Last Updated**: 2025-12-11
**Status**: Ready for Implementation
