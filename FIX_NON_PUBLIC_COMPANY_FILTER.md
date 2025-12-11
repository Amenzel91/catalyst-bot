# Fix: Filter Non-Public Company News Items

## Problem
Bot processes news items for non-public companies (future IPOs, private companies), leading to:
- **73 high-scoring items with ticker=N/A** that can't generate alerts
- Wasted classification compute on untradeable items
- Repeated processing of same non-public company announcements

**Examples:**
- "Camposol Holding PLC" (future IPO, not yet public)
- "LVT" (private company)
- "Crusoe" (private company)
- Generic corporate announcements ("Changes to Executive Management")

## Root Cause
GlobeNewswire RSS feeds include corporate announcements for companies that:
1. Don't have ticker symbols
2. Are pre-IPO / not yet trading
3. Are private companies

**Current Stats:**
- Finviz: 100% ticker extraction (all public companies) ✅
- GlobeNewswire: 10% ticker extraction (90% non-public/invalid) ❌
- SEC filings: ~92% after CIK lookup ✅

## Solution
Filter out items without valid tickers BEFORE classification to save compute and reduce noise.

---

## Implementation Plan

### File: `src/catalyst_bot/feeds.py`

### Step 1: Add Filter Function (Insert after line 290)

```python
def _filter_non_public_companies(
    items: List[Dict],
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Filter out items without valid tickers (likely non-public companies).

    This removes news items for:
    - Pre-IPO companies
    - Private companies
    - Generic corporate announcements without ticker context

    Parameters
    ----------
    items : List[Dict]
        Items after ticker extraction

    Returns
    -------
    Tuple[List[Dict], Dict[str, int]]
        (filtered_items, filter_stats)

    Notes
    -----
    Items with valid tickers are kept regardless of source.
    This primarily filters GlobeNewswire items (~90% lack tickers).
    """
    if not items:
        return [], {}

    kept = []
    stats = {
        "total": len(items),
        "filtered_no_ticker": 0,
        "filtered_na_ticker": 0,
        "kept": 0,
        "kept_with_ticker": 0,
    }

    for item in items:
        ticker = item.get("ticker", "").strip().upper()
        source = item.get("source", "unknown")

        # Keep items with valid tickers
        if ticker and ticker not in {"N/A", "NA", "NONE", ""}:
            kept.append(item)
            stats["kept"] += 1
            stats["kept_with_ticker"] += 1
            continue

        # Filter out items without tickers
        if not ticker or ticker == "":
            stats["filtered_no_ticker"] += 1
        else:  # ticker == "N/A" or similar
            stats["filtered_na_ticker"] += 1

        # Log for analysis (debug level to avoid spam)
        log.debug(
            "filtered_non_public source=%s ticker=%s title=%s",
            source,
            ticker or "none",
            item.get("title", "")[:80]
        )

    stats["kept"] = len(kept)

    log.info(
        "non_public_filter total=%d filtered=%d kept=%d kept_with_ticker=%d",
        stats["total"],
        stats["filtered_no_ticker"] + stats["filtered_na_ticker"],
        stats["kept"],
        stats["kept_with_ticker"]
    )

    return kept, stats
```

### Step 2: Integrate into Feed Pipeline

**Location:** `fetch_pr_feeds()` function around line 2800

**BEFORE:**
```python
def fetch_pr_feeds(...) -> List[Dict]:
    # ... existing code ...

    # Ticker extraction happens here
    all_items = _extract_tickers_from_items(all_items)

    # CURRENTLY: Items go straight to classification
    return all_items
```

**AFTER:**
```python
def fetch_pr_feeds(...) -> List[Dict]:
    # ... existing code ...

    # Ticker extraction happens here
    all_items = _extract_tickers_from_items(all_items)

    # FILTER: Remove items without valid tickers (non-public companies)
    all_items, filter_stats = _filter_non_public_companies(all_items)

    # Log impact
    log.info(
        "feed_pipeline_summary total_fetched=%d after_dedup=%d after_filter=%d",
        initial_item_count,
        len(all_items) + filter_stats.get("filtered_no_ticker", 0) + filter_stats.get("filtered_na_ticker", 0),
        len(all_items)
    )

    return all_items
```

### Step 3: Add Feature Flag (Optional Safety)

**File:** `src/catalyst_bot/config.py`

Add configuration option:
```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Feature flag to enable/disable non-public company filtering
    feature_filter_non_public: bool = Field(
        default=True,
        description="Filter out news items without valid tickers (non-public companies)"
    )
```

**Usage in feeds.py:**
```python
def fetch_pr_feeds(...) -> List[Dict]:
    # ... after ticker extraction ...

    # Apply filter if feature enabled
    settings = get_settings()
    if settings and getattr(settings, "feature_filter_non_public", True):
        all_items, filter_stats = _filter_non_public_companies(all_items)
    else:
        log.info("non_public_filter_disabled keeping_all_items")

    return all_items
```

---

## Expected Impact

**Before:**
- 198 high-scoring items with ticker=N/A processed per 9 hours
- ~73 items scoring >=0.6 (alert threshold) wasted
- Classification runs on all items regardless of tradability

**After:**
- ~5-10 items with ticker=N/A (legitimate edge cases only)
- 90% reduction in non-tradeable item processing
- Classification compute saved on ~18 GlobeNewswire items per cycle

**Breakdown by Source:**
| Source | Before | After | Change |
|--------|--------|-------|--------|
| Finviz | 89 kept | 89 kept | No change ✅ |
| GlobeNewswire | 20 processed | 2 kept | -90% ❌ |
| SEC Filings | ~65 kept | ~60 kept | -8% (CIK misses) |

**Compute Savings:**
- ~20 fewer LLM classification calls per cycle
- 46 cycles/hour × 20 items = ~920 fewer classifications per hour
- Estimated cost savings: ~$2-3/day in LLM API costs

---

## Edge Cases & Considerations

### What Gets Filtered?
- ❌ "Company X Appoints New CEO" (no ticker)
- ❌ "Camposol Holding PLC announces..." (pre-IPO)
- ❌ "LVT expands operations" (private company)

### What's Preserved?
- ✅ Any item with a valid ticker symbol
- ✅ SEC filings with CIK→ticker mapping
- ✅ All Finviz items (100% have tickers)
- ✅ Valid public companies from all sources

### Potential Misses
**Scenario:** Company announces ticker before full extraction runs

**Example:** "Acme Corp announces IPO under ticker ACME"
- Title has ticker "ACME" mentioned
- Title pattern extraction would catch it ✅
- Item kept for classification ✅

**Mitigation:** Title pattern extraction (existing) runs BEFORE this filter, so ticker mentions in titles are caught.

---

## Testing Plan

### Unit Tests
```python
# tests/test_non_public_filter.py

def test_filter_keeps_items_with_tickers():
    """Items with valid tickers should be kept."""
    items = [
        {"ticker": "AAPL", "title": "Apple announces iPhone"},
        {"ticker": "MSFT", "title": "Microsoft launches AI"},
    ]
    filtered, stats = _filter_non_public_companies(items)
    assert len(filtered) == 2
    assert stats["kept_with_ticker"] == 2

def test_filter_removes_items_without_tickers():
    """Items without tickers should be filtered."""
    items = [
        {"ticker": "", "title": "Company X hires CEO"},
        {"ticker": None, "title": "Private company news"},
        {"ticker": "N/A", "title": "Non-public announcement"},
    ]
    filtered, stats = _filter_non_public_companies(items)
    assert len(filtered) == 0
    assert stats["filtered_no_ticker"] == 2
    assert stats["filtered_na_ticker"] == 1

def test_filter_mixed_items():
    """Filter should separate valid from invalid."""
    items = [
        {"ticker": "TSLA", "source": "finviz", "title": "Tesla stock rises"},
        {"ticker": "", "source": "globenewswire", "title": "Private Co news"},
        {"ticker": "NVDA", "source": "sec_8k", "title": "Nvidia files 8-K"},
        {"ticker": "N/A", "source": "globenewswire", "title": "Generic announcement"},
    ]
    filtered, stats = _filter_non_public_companies(items)
    assert len(filtered) == 2  # Only TSLA and NVDA
    assert all(item["ticker"] in {"TSLA", "NVDA"} for item in filtered)
```

### Integration Test
```bash
# Run cycle and check logs for filter stats
python -m catalyst_bot.runner --loop --sleep-secs 60

# Expected log output:
# non_public_filter total=109 filtered=18 kept=91 kept_with_ticker=91
# feed_pipeline_summary total_fetched=120 after_dedup=109 after_filter=91
```

### Manual Validation
```bash
# Check high-scoring N/A items after deployment
python lookup_high_score_items.py

# Expected: <10 items with ticker=N/A (down from 73)
```

---

## Rollback Plan

If issues arise:

**Option 1:** Disable feature flag
```bash
# In .env
FEATURE_FILTER_NON_PUBLIC=0
```

**Option 2:** Revert commit
```bash
git revert <commit-hash>
```

**Risk: Very Low**
- Only removes items without tickers
- Items with tickers completely unaffected
- All existing sources (Finviz, SEC) unaffected

---

## Monitoring

After deployment, track:

```python
# Add to cycle logs
log.info(
    "ticker_quality_metrics",
    items_processed=total_items,
    items_with_tickers=items_with_valid_tickers,
    ticker_extraction_rate=items_with_valid_tickers / total_items,
    high_score_na_items=count_high_score_na,  # Should be <10
)
```

**Success Criteria:**
- High-scoring ticker=N/A items: <10 per 9-hour period (down from 73)
- Classification compute: Reduced by ~15-20%
- No impact on items with valid tickers

---

## Alternative Approaches Considered

### Alternative 1: Company Name Validation
Query external API to validate if company is publicly traded.

**Pros:** More precise
**Cons:** Additional API dependency, latency, cost

**Decision:** Not needed - ticker absence is sufficient signal

### Alternative 2: Source-Specific Filtering
Block entire GlobeNewswire feed.

**Pros:** Simple
**Cons:** Loses 10% of GlobeNewswire items that DO have valid tickers

**Decision:** Too aggressive - ticker-based filtering is more precise

### Alternative 3: Pattern-Based Title Filtering
Filter generic titles like "Appoints Executive" regardless of ticker.

**Pros:** Could catch more noise
**Cons:** Complex pattern maintenance, potential false positives

**Decision:** Ticker-based filtering is cleaner and more maintainable

---

**Created:** 2025-12-11
**Priority:** P1 - High (reduces noise, saves compute)
**Estimated Impact:** 90% reduction in non-public company processing
**Risk:** Very Low (only affects items without tickers)
