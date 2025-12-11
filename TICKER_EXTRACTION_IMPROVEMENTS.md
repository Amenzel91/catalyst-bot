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

# IMPLEMENTATION TICKETS (Code Examples)

The following tickets provide detailed, copy-paste ready code for implementation.

---

## TICKET-001: P1 - Integrate CIK Pre-extraction in feeds.py

**Priority**: P1 (Highest Impact)
**Estimated Effort**: 30 minutes
**Risk Level**: Low (fallback to existing LLM path)

### Context

The existing `extract_ticker_from_filing()` function in `sec_prefilter.py` already has CIK lookup implemented (lines 79-87). However, it's not being called early enough in the `feeds.py` processing pipeline. We need to call it BEFORE the expensive LLM enrichment to skip ~70% of LLM calls.

### Current Code Location

**File**: `src/catalyst_bot/feeds.py`
**Location**: Lines 1186-1207 (inside `_enrich_sec_items_batch()`)

```python
# Current code starts at line 1186
# CRITICAL OPTIMIZATION: Pre-filter already-seen filings BEFORE expensive LLM calls
# This prevents reprocessing the same 100+ filings every cycle (saves 7-8 min/cycle)
items_to_enrich = []
skipped_seen = 0

# Pre-filter already-seen filings using async-safe seen_store
if seen_store:
    for filing in sec_items:
        filing_id = filing.get("id") or filing.get("link") or ""
        # ... etc
```

### Code Change

**INSERT AFTER line 1207** (after the seen_store loop ends):

```python
        # -----------------------------------------------------------------
        # P1 OPTIMIZATION: Extract ticker from CIK BEFORE expensive LLM calls
        # CIK lookup is ~1000x faster than LLM and works for 95%+ of SEC filings
        # Expected impact: Skip LLM enrichment for ~70% of items
        # -----------------------------------------------------------------
        cik_extracted_count = 0
        try:
            from .sec_prefilter import init_prefilter, extract_ticker_from_filing

            # Ensure CIK map is loaded (idempotent)
            init_prefilter()

            for filing in items_to_enrich:
                # Skip if ticker already extracted from title
                if filing.get("ticker"):
                    continue

                # Try CIK extraction
                ticker = extract_ticker_from_filing(filing)
                if ticker:
                    filing["ticker"] = ticker
                    filing["ticker_source"] = "cik_lookup"
                    cik_extracted_count += 1
                    log.debug(
                        "ticker_from_cik_prefilter ticker=%s filing_id=%s",
                        ticker,
                        (filing.get("id") or "")[:50]
                    )
        except Exception as e:
            log.warning("cik_prefilter_failed error=%s", str(e))

        if cik_extracted_count > 0:
            log.info(
                "cik_prefilter_complete extracted=%d total=%d",
                cik_extracted_count,
                len(items_to_enrich)
            )
```

### Validation Steps

1. Run existing tests: `pytest tests/test_sec_feed_integration.py -v`
2. Test with sample SEC filing:
   ```python
   filing = {
       "item_id": "/edgar/data/0001018724/0001018724-24-001234.txt",
       "title": "8-K - Amazon.com Inc. (0001018724) (Filer)",
       "ticker": None
   }
   # Expected: filing["ticker"] == "AMZN" after extraction
   ```
3. Monitor logs for `ticker_from_cik_prefilter` events

### Rollback Plan

If issues occur, simply comment out the new block. The existing LLM enrichment path remains unchanged and will handle all items.

---

## TICKET-002: P1 - Verify CIK Extraction in sec_prefilter.py

**Priority**: P1
**Estimated Effort**: 15 minutes (verification only)
**Risk Level**: None (code already exists)

### Context

The CIK extraction functionality already exists in `sec_prefilter.py` lines 60-106. This ticket is for verification and potential enhancement.

### Existing Code (Lines 79-87)

```python
# Strategy 1: Extract CIK from filing URL/ID
item_id = filing.get("item_id", "")
if item_id:
    cik = cik_from_text(item_id)
    if cik:
        ticker = _CIK_MAP.get(cik) or _CIK_MAP.get(str(cik).zfill(10))
        if ticker:
            log.debug("ticker_from_cik cik=%s ticker=%s", cik, ticker)
            return ticker.upper()
```

### Verification Steps

1. **Verify CIK map loading**:
   ```python
   from src.catalyst_bot.sec_prefilter import init_prefilter, _CIK_MAP
   init_prefilter()
   print(f"CIK map loaded: {len(_CIK_MAP)} entries")
   # Expected: ~6000+ entries
   ```

2. **Test CIK extraction**:
   ```python
   from src.catalyst_bot.ticker_map import cik_from_text

   # Test URLs
   test_urls = [
       "/edgar/data/0001018724/0001018724-24-001234.txt",  # Amazon
       "/edgar/data/320193/000032019324000001.txt",        # Apple (unpadded)
       "/edgar/data/0000320193/000032019324000001.txt",    # Apple (padded)
   ]

   for url in test_urls:
       cik = cik_from_text(url)
       print(f"URL: {url} -> CIK: {cik}")
   ```

3. **Test end-to-end extraction**:
   ```python
   from src.catalyst_bot.sec_prefilter import extract_ticker_from_filing

   filing = {
       "item_id": "/edgar/data/0001018724/0001018724-24-001234.txt",
       "title": "8-K - Amazon.com Inc. (0001018724) (Filer)"
   }
   ticker = extract_ticker_from_filing(filing)
   assert ticker == "AMZN", f"Expected AMZN, got {ticker}"
   ```

### Optional Enhancement

Add `item_id` extraction from `link` field as fallback (lines 79-87):

```python
# Strategy 1: Extract CIK from filing URL/ID
item_id = filing.get("item_id", "") or filing.get("link", "")  # Added link fallback
if item_id:
    cik = cik_from_text(item_id)
    # ... rest unchanged
```

---

## TICKET-003: P1 - Add SEC API Refresh for CIK Mappings (Optional)

**Priority**: P1 (Optional - current NDJSON bootstrap works)
**Estimated Effort**: 45 minutes
**Risk Level**: Low

### Context

The current implementation bootstraps from `company_tickers.ndjson`. This ticket adds optional refresh from SEC API for newer IPOs.

### New Function for ticker_map.py

**INSERT AFTER line 137** (after `load_cik_to_ticker` function):

```python
def refresh_cik_mappings_from_sec() -> int:
    """
    Refresh CIK-to-ticker mappings from SEC EDGAR API.

    Fetches the latest company_tickers.json from SEC and updates
    the local SQLite database. Safe to call periodically (daily/weekly).

    Returns:
        Number of new/updated mappings, or -1 on error

    SEC API Details:
        - Endpoint: https://www.sec.gov/files/company_tickers.json
        - Rate limit: 10 requests/second (we make 1 request)
        - User-Agent: Required per SEC guidelines
    """
    import time
    from urllib.request import Request, urlopen
    from .storage import init_optimized_connection

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {
        "User-Agent": "CatalystBot/1.0 (+https://github.com/catalyst-bot)",
        "Accept": "application/json",
    }

    # Rate limit safety (SEC allows 10/sec, we use 1)
    log.info("sec_api_fetch_start url=%s", url)

    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        log.error("sec_api_fetch_failed error=%s", str(e))
        return -1

    # Parse response (dict format: {"0": {"cik_str": 320193, "ticker": "AAPL"}, ...})
    updates = 0
    conn = init_optimized_connection(str(_db_path()))

    try:
        for key, record in (data or {}).items():
            cik = str(record.get("cik_str", "")).strip()
            ticker = str(record.get("ticker", "")).strip().upper()
            if cik and ticker:
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO tickers(cik, ticker) VALUES(?, ?)",
                        (cik, ticker),
                    )
                    # Also add zero-padded version
                    if len(cik) < 10:
                        conn.execute(
                            "INSERT OR REPLACE INTO tickers(cik, ticker) VALUES(?, ?)",
                            (cik.zfill(10), ticker),
                        )
                    updates += 1
                except Exception:
                    continue
        conn.commit()
        log.info("sec_api_refresh_complete updates=%d", updates)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return updates
```

### Usage

Call periodically (e.g., daily via cron or at startup):

```python
from src.catalyst_bot.ticker_map import refresh_cik_mappings_from_sec

# Refresh mappings (optional, current bootstrap is sufficient)
updated = refresh_cik_mappings_from_sec()
if updated > 0:
    log.info("Refreshed %d CIK mappings from SEC", updated)
```

---

## TICKET-004: P2 - Add PR Wire Pattern Variants (Analysis Complete)

**Priority**: P2
**Estimated Effort**: 20 minutes
**Risk Level**: Low (patterns already well-designed in existing code)

### Context

After code analysis, the existing patterns in `title_ticker.py` already cover the main cases:
- Exchange-qualified: `(NASDAQ: AAPL)` ✓
- Company + Ticker: `Apple (AAPL)` ✓
- Headline start: `TSLA: Deliveries` ✓
- Dollar ticker: `$AAPL` ✓

**Finding**: The current patterns are comprehensive. Additional patterns may increase false positives without significant gain.

### Recommended: Verify Existing Coverage

Run the existing test suite:
```bash
pytest tests/test_title_ticker.py -v
```

### Optional: Add "Ticker Symbol:" Pattern

If analysis shows this format is common in your PR wire data, add to `title_ticker.py`:

**INSERT AFTER line 96** (after `_HEADLINE_START_TICKER`):

```python
# "Ticker symbol: AAPL" or "ticker symbol TSLA"
_TICKER_SYMBOL_PATTERN = r"(?:ticker\s+symbol\s*:?\s*)([A-Z]{2,5}(?:\.[A-Z])?)"
```

**MODIFY line 60-62** to include the new pattern:

```python
        combined = (
            rf"{exch_pattern}|{_COMPANY_TICKER_PATTERN}|"
            rf"{_HEADLINE_START_TICKER}|{_TICKER_SYMBOL_PATTERN}|{_DOLLAR_PATTERN}"
        )
```

### Test Cases for New Pattern

```python
def test_ticker_symbol_pattern():
    from src.catalyst_bot.title_ticker import ticker_from_title

    assert ticker_from_title("Ticker symbol: AAPL") == "AAPL"
    assert ticker_from_title("ticker symbol TSLA today") == "TSLA"
    assert ticker_from_title("Stock ticker symbol: BA announced") == "BA"
```

---

## TICKET-005: P4 - Disable Finviz CSV Export (Simple Fix)

**Priority**: P4 (Cleanup)
**Estimated Effort**: 10 minutes
**Risk Level**: Very Low (CSV already disabled by default)

### Context

The Finviz CSV export at `_fetch_finviz_news_export()` (lines 3113-3187) returns NO ticker data. The working endpoint `_fetch_finviz_news_from_env()` (lines 2790-3014) is already the default.

### Current State

**File**: `src/catalyst_bot/feeds.py`
**Line 1609**: CSV export is called when feature flag is enabled

```python
if settings.feature_finviz_news_export and settings.finviz_news_export_url:
    try:
        export_items = _fetch_finviz_news_export(
            settings.finviz_news_export_url
        )
```

### Verification

The feature flag `FEATURE_FINVIZ_NEWS_EXPORT` defaults to `False` in config.py.

**Verify it's disabled**:
```bash
grep -n "FEATURE_FINVIZ_NEWS_EXPORT" src/catalyst_bot/config.py
# Should show: feature_finviz_news_export: bool = _b("FEATURE_FINVIZ_NEWS_EXPORT", False)
```

### Option A: Leave As-Is (Recommended)

The CSV export is already disabled by default. No code changes needed.

### Option B: Remove CSV Code (Optional Cleanup)

If you want to remove the unused code:

1. **DELETE lines 3113-3187** (entire `_fetch_finviz_news_export` function)
2. **DELETE lines 1605-1644** (the CSV export block in `fetch_pr_feeds`)
3. **DELETE config entries** for `FINVIZ_NEWS_EXPORT_URL` and `FEATURE_FINVIZ_NEWS_EXPORT`

### Validation

After any changes:
```bash
# Verify Finviz news still works
python -c "from src.catalyst_bot.feeds import _fetch_finviz_news_from_env; print(len(_fetch_finviz_news_from_env()))"
# Expected: Some number of items with tickers
```

---

## TICKET-006: Add Extraction Method Logging

**Priority**: P2 (Observability)
**Estimated Effort**: 15 minutes
**Risk Level**: None

### Context

Add tracking for how tickers are extracted (CIK vs title vs summary) for monitoring and optimization.

### Code Change in feeds.py

**MODIFY the normalization section** (~line 780-850) to track extraction method:

```python
# After ticker extraction, before item is added to results
if item.get("ticker"):
    # Track extraction source for metrics
    if not item.get("ticker_source"):
        item["ticker_source"] = "title_pattern"
```

### Add Summary Log in fetch_pr_feeds()

**INSERT** at end of `fetch_pr_feeds()` function (~line 1900):

```python
    # Log ticker extraction summary for monitoring
    extraction_summary = {}
    for item in all_items:
        source = item.get("ticker_source", "unknown")
        extraction_summary[source] = extraction_summary.get(source, 0) + 1

    log.info(
        "ticker_extraction_summary total=%d by_source=%s",
        len(all_items),
        extraction_summary
    )
```

### Expected Log Output

```
INFO ticker_extraction_summary total=450 by_source={'cik_lookup': 285, 'title_pattern': 120, 'unknown': 45}
```

---

## TICKET-007: Integration Test for Full Pipeline

**Priority**: P1
**Estimated Effort**: 30 minutes
**Risk Level**: None (test only)

### Test File: `tests/test_ticker_extraction_integration.py`

```python
"""Integration tests for ticker extraction improvements."""
import pytest


class TestCIKExtraction:
    """Tests for CIK-to-ticker extraction (P1)."""

    def test_cik_from_edgar_url(self):
        """Verify CIK extraction from EDGAR URLs."""
        from src.catalyst_bot.ticker_map import cik_from_text

        # Standard padded CIK
        assert cik_from_text("/edgar/data/0001018724/file.txt") == "0001018724"
        # Unpadded CIK
        assert cik_from_text("/edgar/data/320193/file.txt") == "320193"
        # No CIK present
        assert cik_from_text("https://example.com/news") is None

    def test_cik_to_ticker_mapping(self):
        """Verify CIK maps to correct ticker."""
        from src.catalyst_bot.ticker_map import load_cik_to_ticker

        cik_map = load_cik_to_ticker()
        assert len(cik_map) > 5000, "CIK map should have 5000+ entries"

        # Test known mappings (both padded and unpadded)
        assert cik_map.get("1018724") == "AMZN" or cik_map.get("0001018724") == "AMZN"

    def test_extract_ticker_from_filing(self):
        """Verify full extraction from SEC filing dict."""
        from src.catalyst_bot.sec_prefilter import init_prefilter, extract_ticker_from_filing

        init_prefilter()

        filing = {
            "item_id": "/edgar/data/0001018724/0001018724-24-001234.txt",
            "title": "8-K - Amazon.com Inc. (0001018724) (Filer)",
        }

        ticker = extract_ticker_from_filing(filing)
        assert ticker == "AMZN", f"Expected AMZN, got {ticker}"


class TestPatternMatching:
    """Tests for PR wire pattern matching (P2)."""

    def test_exchange_qualified_patterns(self):
        """Verify exchange-qualified patterns work."""
        from src.catalyst_bot.title_ticker import ticker_from_title

        assert ticker_from_title("(Nasdaq: AAPL) reports strong Q3") == "AAPL"
        assert ticker_from_title("Boeing (NYSE: BA) announces layoffs") == "BA"

    def test_company_ticker_patterns(self):
        """Verify company + ticker patterns work."""
        from src.catalyst_bot.title_ticker import ticker_from_title

        assert ticker_from_title("Apple (AAPL) Reports Strong Quarter") == "AAPL"
        assert ticker_from_title("Tesla Inc. (TSLA) Q3 earnings beat") == "TSLA"

    def test_exclusion_lists(self):
        """Verify false positives are filtered."""
        from src.catalyst_bot.title_ticker import ticker_from_title

        # These should NOT return tickers
        assert ticker_from_title("FDA approves new drug") is None
        assert ticker_from_title("PRICE: Stock rises 5%") is None
        assert ticker_from_title("CEO announces strategy") is None


class TestFinvizExtraction:
    """Tests for Finviz feed ticker extraction (P4)."""

    def test_finviz_env_has_ticker(self):
        """Verify news_export.ashx returns ticker data."""
        # This test requires FINVIZ_AUTH_TOKEN to be set
        import os
        if not os.getenv("FINVIZ_AUTH_TOKEN"):
            pytest.skip("FINVIZ_AUTH_TOKEN not set")

        from src.catalyst_bot.feeds import _fetch_finviz_news_from_env

        items = _fetch_finviz_news_from_env()
        if items:
            # At least some items should have tickers
            with_ticker = [i for i in items if i.get("ticker")]
            assert len(with_ticker) > 0, "Expected some items with tickers"
```

### Run Tests

```bash
pytest tests/test_ticker_extraction_integration.py -v
```

---

## Architecture Reference

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     FEED SOURCES                                 │
├─────────────────────────────────────────────────────────────────┤
│  PR Wires              SEC Filings            Finviz            │
│  (GlobeNewswire,       (8-K, 424B5,           (news_export.ashx)│
│   BusinessWire)         13D, 13G)                               │
└────────┬───────────────────┬────────────────────┬───────────────┘
         │                   │                    │
         ▼                   ▼                    ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ title_ticker.py │  │ sec_prefilter.py │  │ ticker field     │
│ Pattern Match   │  │ CIK → Ticker     │  │ (direct extract) │
│ (50% success)   │  │ (95% success)    │  │ (92% success)    │
└────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                    │                     │
         └────────────────────┼─────────────────────┘
                              ▼
                    ┌──────────────────┐
                    │  Validated Item  │
                    │  ticker = "AAPL" │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │  Downstream      │
                    │  Processing      │
                    │  (classify,      │
                    │   alert, track)  │
                    └──────────────────┘
```

### Key File Locations

| File | Purpose | Key Lines |
|------|---------|-----------|
| `ticker_map.py` | CIK extraction & mapping | `cik_from_text()` L140, `load_cik_to_ticker()` L98 |
| `sec_prefilter.py` | SEC filing pre-filter | `extract_ticker_from_filing()` L60 |
| `title_ticker.py` | Regex pattern matching | `ticker_from_title()` L185 |
| `feeds.py` | Feed orchestration | `_enrich_sec_items_batch()` L1143 |

### Existing Patterns Inventory

| Pattern | Regex | Example Match |
|---------|-------|---------------|
| Exchange-qualified | `(?i:\b(?:NASDAQ\|NYSE...)\s*[:\-]\s*)\$?([A-Z][A-Z0-9.\-]{0,5})\b` | `(NASDAQ: AAPL)` |
| Company + Ticker | `[A-Z][A-Za-z0-9&\.\-]*(?:\s+(?:Inc\.?\|Corp\.?...))?\s*\(([A-Z]{2,5}(?:\.[A-Z])?)\)` | `Apple (AAPL)` |
| Headline Start | `^([A-Z]{2,5}):\s+` | `TSLA: Reports` |
| Dollar Ticker | `(?<!\w)\$([A-Z][A-Z0-9.\-]{0,5})\b` | `$NVDA` |
| CIK from URL | `/edgar/data/(\d+)/` | `/edgar/data/0001018724/` |

---

**Document Version**: 2.0
**Last Updated**: 2025-12-11
**Status**: Ready for Implementation with Code Tickets
