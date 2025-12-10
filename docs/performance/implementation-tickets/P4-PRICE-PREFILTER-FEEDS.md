# Implementation Ticket: Add Price Pre-Filter in feeds.py Before LLM Enrichment

## Title
Add Price Pre-Filter in feeds.py Before LLM Enrichment

## Priority
**P4** - Optimization (Cost Reduction)

## Estimated Effort
**3-4 hours** (including testing and verification)

## Problem Statement

**Cost Inefficiency in SEC Filing Processing:**

Currently, price filtering happens in TWO places:
1. **`sec_prefilter.py::check_price_filters()`** - Checks price ceiling/floor BEFORE LLM (good, but optional)
2. **`runner.py:2728-2825`** - Enforces price ceiling/floor AFTER LLM enrichment (wasteful)

**Impact:**
- Some SEC filings pass prefilter checks but fail price validation AFTER expensive LLM enrichment
- This wastes LLM API calls ($0.05+ per call) and processing time
- Estimated waste: 10-20% of LLM calls on items that will be filtered anyway

## Solution Overview

**Add price pre-filtering directly in `feeds.py::_enrich_sec_items_batch()`**

Before calling LLM enrichment, filter SEC items by price ceiling/floor constraints. This prevents wasting LLM API calls on items that won't survive post-enrichment filtering.

## Files to Modify

```
/home/user/catalyst-bot/src/catalyst_bot/feeds.py
  - Function: _enrich_sec_items_batch() (lines 1096-1213)
```

## Implementation Steps

### Step 1: Add Configuration Check (after line 1131)

```python
# Check if price pre-filtering is enabled (default: enabled)
price_filter_enabled = os.getenv("SEC_PRICE_FILTER_ENABLED", "1").strip() in (
    "1", "true", "yes", "on",
)
```

### Step 2: Add Price Pre-Filtering Logic (after line 1133)

```python
try:
    from .logging_utils import get_logger
    log = get_logger("feeds.sec_llm")

    # Price pre-filtering before LLM enrichment
    items_to_enrich = []
    items_skipped_price = []

    if price_filter_enabled:
        from .sec_prefilter import check_price_filters

        for filing in sec_items:
            ticker = filing.get("ticker")

            # If no ticker, cannot filter - include in enrichment
            if not ticker:
                items_to_enrich.append(filing)
                continue

            # Check price filters (ceiling/floor)
            try:
                passes_price, reject_reason = check_price_filters(ticker)

                if passes_price:
                    items_to_enrich.append(filing)
                else:
                    items_skipped_price.append(filing)
                    filing_id = filing.get("id", filing.get("link", "unknown"))
                    log.debug(
                        "sec_price_prefilter_rejected ticker=%s reason=%s filing_id=%s",
                        ticker, reject_reason, filing_id[:50] if filing_id else "unknown"
                    )

            except Exception as e:
                # If price check errors, be conservative and include
                items_to_enrich.append(filing)
                log.debug("sec_price_prefilter_error ticker=%s error=%s", ticker, str(e))
    else:
        items_to_enrich = sec_items
        items_skipped_price = []

    log.info(
        "sec_price_prefilter_complete total=%d to_enrich=%d skipped_price=%d filter_enabled=%s",
        len(sec_items), len(items_to_enrich), len(items_skipped_price), price_filter_enabled
    )
```

### Step 3: Update LLM Processing to Use Filtered List

```python
    log.info(
        "sec_llm_batch_start total_filings=%d skipped_price=%d to_enrich=%d max_concurrent=%d",
        len(sec_items), len(items_skipped_price), len(items_to_enrich), max_concurrent,
    )

    # If all filings were filtered out, skip LLM processing entirely
    if not items_to_enrich:
        log.info(
            "sec_llm_batch_complete total=%d skipped_price=%d all_filtered=true",
            len(sec_items), len(items_skipped_price),
        )
        return items_to_enrich + items_skipped_price
```

### Step 4: Update Return Logic

```python
    # Combine enriched items with skipped items
    result = enriched + items_skipped_price

    log.info(
        "sec_llm_batch_complete total=%d enriched=%d skipped_price=%d success_rate=%.1f%%",
        len(sec_items), success_count, len(items_skipped_price),
        (success_count / len(items_to_enrich)) * 100 if items_to_enrich else 0,
    )

    return result
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEC_PRICE_FILTER_ENABLED` | `1` | Enable/disable price pre-filtering |
| `PRICE_CEILING` | (from settings) | Maximum stock price to process |

### Example:
```bash
export SEC_PRICE_FILTER_ENABLED=1  # Enable price pre-filtering (default)
export SEC_PRICE_FILTER_ENABLED=0  # Disable price pre-filtering
```

## Test Verification

### Check Log Messages

Enable debug logging to see price filtering in action:

```bash
LOG_LEVEL=DEBUG python -m catalyst_bot.runner
```

Look for these log messages:
```
sec_price_prefilter_complete total=47 to_enrich=38 skipped_price=9 filter_enabled=1
sec_price_prefilter_rejected ticker=XYZW reason=above_price_ceiling price=18.50 ceiling=15.00
sec_llm_batch_start total_filings=47 skipped_price=9 to_enrich=38 max_concurrent=3
sec_llm_batch_complete total=47 enriched=35 skipped_price=9 success_rate=92.1%
```

### Manual Test Script

```python
import os
os.environ['SEC_PRICE_FILTER_ENABLED'] = '1'
os.environ['PRICE_CEILING'] = '10.00'

from catalyst_bot.feeds import _enrich_sec_items_batch
import asyncio

test_items = [
    {"ticker": "AAPL", "title": "Apple 8-K", "link": "http://sec.gov/1"},   # ~$250, skip
    {"ticker": "SIRI", "title": "Sirius 8-K", "link": "http://sec.gov/2"},  # ~$5, process
]

result = asyncio.run(_enrich_sec_items_batch(test_items))

print(f"Enriched: {sum(1 for i in result if i.get('llm_confidence'))}")
print(f"Skipped: {sum(1 for i in result if not i.get('llm_confidence'))}")
```

## Rollback Procedure

### To Disable Price Pre-Filtering

```bash
export SEC_PRICE_FILTER_ENABLED=0
# Restart application - all SEC items bypass price filtering
```

### Verify Rollback

Check logs for:
```
sec_price_prefilter_complete ... filter_enabled=0
```

## Dependencies

**No external dependencies added**

- Uses existing `check_price_filters()` from `sec_prefilter.py`
- Uses existing `get_last_price_snapshot()` from `market.py`

## Risk Assessment

### Risk Level: **LOW**

| Factor | Risk | Mitigation |
|--------|------|-----------|
| Conservative filtering | LOW | Items that fail are returned as-is (not deleted) |
| Fail-safe logic | LOW | If price check fails, item is included (not skipped) |
| Feature flag | LOW | Can be disabled with single environment variable |
| No API changes | LOW | Input/output contract unchanged |

**Potential Issues & Mitigations:**

| Issue | Probability | Mitigation |
|-------|-------------|-----------|
| Price fetch timeout | Low | Timeout is 8s; fail-open (include in enrichment) |
| Over-aggressive filtering | Low | Logging shows what was filtered; adjust PRICE_CEILING |
| Performance regression | Very Low | Only ~100-200ms for 50 items |

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| LLM calls per batch | 100% | 80-85% |
| Estimated savings | - | 15-20% LLM cost reduction |
| Daily savings (100 filings/hr) | - | ~$12-24/day |

## Success Criteria

- [ ] Price filtering logs show expected rejection counts
- [ ] LLM API call count reduced by 15-20%
- [ ] No data loss (rejected items still returned)
- [ ] Feature can be disabled via env var
- [ ] All existing tests pass
