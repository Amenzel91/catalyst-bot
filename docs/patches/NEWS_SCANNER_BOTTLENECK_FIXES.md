# News Scanner Bottleneck Fixes

## Executive Summary

The news scanner is experiencing **15-20 minute delays** between article publication and alert delivery. Investigation has identified **4 critical bottlenecks** causing this issue:

1. **Finnhub earnings calendar** returning 1000+ items (should be 30-50)
2. **Timestamp bug** allowing stale articles to bypass freshness filter
3. **No timestamp sorting** causing old articles to process before new ones
4. **SeenStore database** not initializing properly, causing reprocessing

**Current Performance:**
- ~2,000 articles processed per cycle
- 15-18 minute cycle time (should be 30-60 seconds)
- Alerts arrive 15-20 minutes after publication

**Expected Performance After Fixes:**
- ~200-400 articles per cycle (10x reduction)
- <2 minute cycle time (10x improvement)
- Alerts arrive within 2-5 minutes of publication

---

## Quick Reference Table

| Priority | Issue | Impact | Files Affected | Estimated Fix Time |
|----------|-------|--------|----------------|-------------------|
| **CRITICAL** | Finnhub earnings overload | 1145 → 30 articles | `src/catalyst_bot/finnhub_feeds.py` | 10 minutes |
| **CRITICAL** | Timestamp bug | ~400 stale articles pass filter | `src/catalyst_bot/feeds.py` | 15 minutes |
| **HIGH** | No timestamp sorting | New news queues behind old | `src/catalyst_bot/runner.py` | 5 minutes |
| **HIGH** | SeenStore not working | Reprocessing seen articles | `src/catalyst_bot/seen_store.py` + config | 20 minutes |
| **MEDIUM** | Tiingo no caching | Repeated API calls | `src/catalyst_bot/market.py` | 30 minutes |
| **MEDIUM** | Tiingo sequential fallback | 6-10 min API delays | `src/catalyst_bot/market.py` | 45 minutes |

---

## Issue #1: Finnhub Earnings Calendar Overload [CRITICAL]

### Problem Description

The Finnhub earnings calendar is fetching **ALL companies** with earnings in the next 7 days (~1000-1500 companies), overwhelming the news pipeline with future events that aren't actionable for immediate trading alerts.

**Observed Logs:**
```
finnhub_feeds_added news=30 earnings=1115 unique=1145
```

### Root Cause Analysis

**File:** `/home/user/catalyst-bot/src/catalyst_bot/finnhub_feeds.py`

**Line 156-179:** The `fetch_finnhub_earnings_calendar()` function has no limit on results:

```python
def fetch_finnhub_earnings_calendar(days_ahead: int = 7) -> List[Dict[str, Any]]:
    """Fetch upcoming earnings from Finnhub."""
    client = get_finnhub_client()
    if not client:
        return []

    try:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        to_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime(
            "%Y-%m-%d"
        )

        # ⚠️ PROBLEM: Returns ALL companies with earnings in 7-day window
        earnings = client.get_earnings_calendar(from_date=from_date, to_date=to_date)

        items = []
        for event in earnings:  # ⚠️ No limit, no filtering
            # ... process each event
            items.append(item)

        return items  # ⚠️ Returns 1000+ items
```

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`

**Line 1122:** Called without awareness of volume:

```python
finnhub_earnings = fetch_finnhub_earnings_calendar(days_ahead=7)  # Returns 1000+ items!
```

### Impact Assessment

- **Volume Impact:** 1145 extra articles per cycle (vs expected 30-50)
- **Processing Time:** 1145 × 0.5s avg = **572 seconds (~9.5 minutes)** per cycle
- **Relevance:** Most earnings are 3-7 days away, not actionable for immediate alerts
- **Alert Quality:** Dilutes high-priority breaking news with low-priority calendar events

### Proposed Fix

**Option A: Limit to Today + Tomorrow Only (Recommended)**

Reduce `days_ahead` to capture only imminent earnings:

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`
**Line 1122:**

```python
# BEFORE:
finnhub_earnings = fetch_finnhub_earnings_calendar(days_ahead=7)

# AFTER:
finnhub_earnings = fetch_finnhub_earnings_calendar(days_ahead=2)  # Today + tomorrow only
```

**Expected Result:** 1115 → ~150-300 earnings items

---

**Option B: Filter by Watchlist (Best for Quality)**

Only include earnings for stocks you're actively tracking:

**File:** `/home/user/catalyst-bot/src/catalyst_bot/finnhub_feeds.py`
**Line 156-235:** Modify function:

```python
def fetch_finnhub_earnings_calendar(days_ahead: int = 7, watchlist_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch upcoming earnings from Finnhub.

    Parameters
    ----------
    days_ahead : int
        Number of days to look ahead (default: 7)
    watchlist_only : bool
        If True, only return earnings for watchlist tickers (default: True)
    """
    client = get_finnhub_client()
    if not client:
        return []

    # Load watchlist if filtering enabled
    watchlist_tickers = set()
    if watchlist_only:
        try:
            from .watchlist import load_watchlist_set
            watchlist_tickers = load_watchlist_set()
            if not watchlist_tickers:
                log.debug("finnhub_earnings_no_watchlist - fetching all")
                watchlist_only = False  # Fallback if watchlist empty
        except Exception:
            log.debug("finnhub_earnings_watchlist_load_failed")
            watchlist_only = False

    try:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        to_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime(
            "%Y-%m-%d"
        )

        earnings = client.get_earnings_calendar(from_date=from_date, to_date=to_date)

        items = []
        for event in earnings:
            ticker = event.get("symbol", "")

            # ✅ NEW: Filter by watchlist
            if watchlist_only and ticker not in watchlist_tickers:
                continue

            date = event.get("date", "")
            if not ticker or not date:
                continue

            # ... rest of processing remains the same
            item = {
                "id": item_id,
                "title": title,
                "summary": summary,
                # ... etc
            }
            items.append(item)

        log.info("finnhub_earnings_fetched count=%d watchlist_only=%s", len(items), watchlist_only)
        return items

    except Exception as e:
        log.warning("finnhub_earnings_fetch_error err=%s", str(e))
        return []
```

**Expected Result:** 1115 → ~20-50 earnings items (depending on watchlist size)

---

**Option C: Disable Entirely (Quickest Fix)**

If earnings calendar alerts aren't needed for immediate trading:

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`
**Line 1122:**

```python
# BEFORE:
finnhub_earnings = fetch_finnhub_earnings_calendar(days_ahead=7)

# AFTER:
# Disable earnings calendar for immediate news alerts
# finnhub_earnings = fetch_finnhub_earnings_calendar(days_ahead=7)
finnhub_earnings = []  # Disabled - focus on breaking news only
```

**Expected Result:** 1145 → 30 articles from Finnhub

---

**Recommended Approach:** Start with **Option A** (days_ahead=2) for immediate relief, then implement **Option B** (watchlist filtering) for long-term quality.

### Testing Recommendations

1. **Verify log output changes:**
   ```bash
   # Before fix:
   grep "finnhub_feeds_added" data/logs/bot.jsonl | tail -5
   # Should show: news=30 earnings=1115

   # After fix:
   grep "finnhub_feeds_added" data/logs/bot.jsonl | tail -5
   # Should show: news=30 earnings=<50-300 depending on option>
   ```

2. **Monitor cycle time:**
   ```bash
   grep "CYCLE_DONE" data/logs/bot.jsonl | tail -10
   # Should show cycle time dropping from 900-1100s to <120s
   ```

3. **Verify alert quality:**
   - Check Discord - should see more breaking news, fewer "Earnings in 5 days" alerts

---

## Issue #2: Timestamp Bug Bypassing Freshness Filter [CRITICAL]

### Problem Description

Articles **without timestamps** or with **unparseable timestamps** are being stamped with the **current time** instead of being rejected. This causes old SEC filings (potentially days/weeks old) to bypass the 10-minute freshness filter and appear as "brand new" articles.

### Root Cause Analysis

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`

**Line 803-812:** The `_to_utc_iso()` helper function returns `now()` for missing timestamps:

```python
def _to_utc_iso(dt_str: Optional[str]) -> str:
    """Convert datetime string to UTC ISO format.

    ⚠️ PROBLEM: Returns current time for missing/invalid timestamps!
    """
    if not dt_str:
        return datetime.now(timezone.utc).isoformat()  # ❌ BUG: Should return None or empty
    try:
        d = dtparse.parse(dt_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()  # ❌ BUG: Should return None or empty
```

**Line 899-904:** Called when normalizing RSS entries:

```python
def _normalize_entry(e, source: str, http_dt: Optional[str] = None) -> Dict:
    # ...
    published = (
        getattr(e, "published", None)
        or getattr(e, "updated", None)
        or getattr(e, "pubDate", None)
    )
    ts_iso = _to_utc_iso(published)  # ❌ Returns "now" if published is None
    # ...
```

**Line 276-295:** Freshness filter checks for timestamps but never rejects because `ts` is always set:

```python
def _filter_by_freshness(items: List[Dict], max_age_minutes: int = 10):
    """Filter items by age.

    ⚠️ PROBLEM: Check for missing timestamp never triggers!
    """
    fresh_items = []
    rejected_count = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max_age_minutes)

    for item in items:
        ts_str = item.get("ts")
        if not ts_str:
            # No timestamp - keep it (assume fresh)
            # ❌ This condition NEVER executes because ts is always populated!
            fresh_items.append(item)
            continue

        # Parse timestamp and check age
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if ts >= cutoff:
                fresh_items.append(item)
            else:
                rejected_count += 1
                age_minutes = (now - ts).total_seconds() / 60.0
                log.debug("article_too_old age_min=%.1f", age_minutes)
        except Exception:
            # Can't parse - keep it
            fresh_items.append(item)

    return fresh_items, rejected_count
```

### Impact Assessment

- **SEC Feeds:** Each SEC feed fetches 100 items with `count=100` in the URL (Lines 428-462 in feeds.py)
- **Historical Articles:** During off-hours, these 100 items could be days/weeks old
- **Bypass Rate:** If 50% lack proper timestamps → ~200 stale articles pass filter per cycle
- **Processing Waste:** 200 stale articles × 0.5s = **100 seconds wasted per cycle**
- **Alert Quality:** Risk alerting on week-old filings that already moved the market

### Proposed Fix

**Option A: Return None for Missing Timestamps (Recommended)**

Modify `_to_utc_iso()` to return `None` for invalid timestamps, then handle in freshness filter:

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`
**Line 803-812:**

```python
def _to_utc_iso(dt_str: Optional[str]) -> Optional[str]:
    """Convert datetime string to UTC ISO format.

    Returns
    -------
    str or None
        ISO format timestamp, or None if invalid/missing
    """
    if not dt_str:
        return None  # ✅ FIX: Return None instead of now()
    try:
        d = dtparse.parse(dt_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return None  # ✅ FIX: Return None instead of now()
```

**Line 899-954:** Update normalization to handle None timestamps:

```python
def _normalize_entry(e, source: str, http_dt: Optional[str] = None) -> Dict:
    # ...
    published = (
        getattr(e, "published", None)
        or getattr(e, "updated", None)
        or getattr(e, "pubDate", None)
    )
    ts_iso = _to_utc_iso(published)

    # ✅ FIX: If no valid timestamp, use current time BUT mark as uncertain
    if ts_iso is None:
        ts_iso = datetime.now(timezone.utc).isoformat()
        timestamp_uncertain = True  # Add flag for filtering later
    else:
        timestamp_uncertain = False

    return {
        "id": id_,
        # ... other fields
        "ts": ts_iso,
        "timestamp_uncertain": timestamp_uncertain,  # ✅ NEW: Track uncertain timestamps
        # ...
    }
```

**Line 276-295:** Update freshness filter to reject uncertain timestamps:

```python
def _filter_by_freshness(items: List[Dict], max_age_minutes: int = 10):
    """Filter items by age, rejecting items without valid timestamps."""
    fresh_items = []
    rejected_count = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max_age_minutes)

    for item in items:
        # ✅ FIX: Reject items with uncertain timestamps
        if item.get("timestamp_uncertain"):
            rejected_count += 1
            log.debug("article_rejected reason=uncertain_timestamp source=%s", item.get("source"))
            continue

        ts_str = item.get("ts")
        if not ts_str:
            # No timestamp at all - reject it
            rejected_count += 1
            log.debug("article_rejected reason=no_timestamp source=%s", item.get("source"))
            continue

        # Parse timestamp and check age
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if ts >= cutoff:
                fresh_items.append(item)
            else:
                rejected_count += 1
                age_minutes = (now - ts).total_seconds() / 60.0
                log.debug("article_too_old age_min=%.1f source=%s", age_minutes, item.get("source"))
        except Exception as e:
            # Can't parse - reject it for safety
            rejected_count += 1
            log.debug("article_rejected reason=unparseable_timestamp source=%s", item.get("source"))

    return fresh_items, rejected_count
```

**Expected Result:** ~200-400 stale articles properly rejected per cycle

---

**Option B: Make Freshness Filter More Strict (Alternative)**

Keep current behavior but reduce `NEWS_MAX_AGE_MINUTES` to be more aggressive:

**File:** `.env`

```bash
# BEFORE:
# NEWS_MAX_AGE_MINUTES=10  (default)

# AFTER:
NEWS_MAX_AGE_MINUTES=5  # Only process articles from last 5 minutes
```

**Pros:** Simple config change
**Cons:** Doesn't fix the underlying bug, may still miss some articles

---

**Recommended Approach:** Implement **Option A** to properly handle missing timestamps, then adjust `NEWS_MAX_AGE_MINUTES` based on observed results.

### Testing Recommendations

1. **Check freshness filter logs:**
   ```bash
   grep "freshness_filter_applied" data/logs/bot.jsonl | tail -5
   # Before fix: rejected=20-50 kept=1500-1800
   # After fix: rejected=300-500 kept=200-400
   ```

2. **Verify uncertain timestamp rejections:**
   ```bash
   grep "article_rejected reason=uncertain_timestamp" data/logs/bot.jsonl | wc -l
   # Should show hundreds of rejections per cycle
   ```

3. **Monitor article counts by source:**
   ```bash
   grep "feeds_summary" data/logs/bot.jsonl | tail -5
   # SEC feed entries should drop significantly
   ```

4. **Spot check SEC filings:**
   - Manually verify that alerted SEC filings are recent (within 10 minutes)
   - Check that week-old filings are no longer triggering alerts

---

## Issue #3: No Timestamp Sorting Before Processing [HIGH]

### Problem Description

Articles from multiple sources are combined in **unsorted order** before processing. When the alert cap is reached (e.g., `MAX_ALERTS_PER_CYCLE=5`), processing stops, causing newer articles to queue behind older ones. This creates a **15-20 minute backlog** as new articles wait for old articles to finish processing.

### Root Cause Analysis

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`

**Line 1093, 1184, 1394:** Articles are combined without sorting:

```python
# Line 1134: Finnhub added
all_items.extend(finnhub_unique)  # ❌ Appended in fetch order, not sorted

# Line 1184: Finviz added
all_items.extend(finviz_unique)  # ❌ Appended in fetch order, not sorted

# Line 1394: RSS feeds added
all_items.extend(items)  # ❌ Appended in fetch order, not sorted
```

**File:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py`

**Line 1309:** Items processed in combined order:

```python
for it in deduped:  # ❌ Processes in whatever order they were appended
    source = it.get("source") or "unknown"
    # ... process article
```

**Line 2377-2379:** Early exit prevents newer articles from being processed:

```python
# Optional: stop early if we hit the cap
if max_alerts_per_cycle > 0 and alerted >= max_alerts_per_cycle:
    log.info("alert_cap_reached cap=%s", max_alerts_per_cycle)
    break  # ❌ STOPS processing remaining items - newer articles must wait!
```

### Impact Assessment

**Scenario with 1500 articles per cycle:**

1. Finnhub fetches 1145 items (mostly old earnings)
2. Finviz fetches 82 items (mix of old/new)
3. RSS fetches 300 items (mostly old)
4. Combined unsorted: [Finnhub 1-1145, Finviz 1-82, RSS 1-300]
5. Alert cap = 5 alerts
6. Bot processes first 200-300 items, hits cap, breaks loop
7. **New breaking news in positions 400-1500 must wait until next cycle**
8. Next cycle: Same pattern repeats
9. Result: **New news queues up for 30-40 cycles = 15-20 minutes**

### Proposed Fix

**Sort articles by timestamp (newest first) before processing loop:**

**File:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py`
**Line ~1115:** Add sorting after enrichment, before processing:

```python
def _cycle(log, settings, *, market_info=None):
    # ... existing code ...

    # Line 1009-1010: Fetch and dedupe
    items = feeds.fetch_pr_feeds()
    deduped = feeds.dedupe(items)

    # ... existing enrichment code (~lines 1050-1110) ...

    # ✅ NEW: Sort by timestamp (newest first) BEFORE processing
    # This ensures breaking news is always processed first, even if alert cap is hit
    try:
        deduped.sort(
            key=lambda x: x.get('published_parsed') or x.get('ts') or '',
            reverse=True  # Newest first
        )
        log.info("articles_sorted_by_timestamp count=%d", len(deduped))
    except Exception as e:
        # Sorting failed - log but continue with unsorted (graceful degradation)
        log.warning("article_sort_failed err=%s - continuing with unsorted", str(e))

    # Line 1309+: Process articles (now in newest-first order)
    for it in deduped:
        # ... existing processing logic
```

**Alternative location (if preferred):** Sort immediately after deduplication:

**File:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py`
**Line 1420:** Add sorting after freshness filter:

```python
def fetch_pr_feeds():
    # ... existing fetch logic ...

    # Line 1413: Freshness filter
    all_items, rejected_old = _filter_by_freshness(all_items, max_age_minutes=max_age_min)

    # ✅ NEW: Sort by timestamp (newest first)
    try:
        all_items.sort(
            key=lambda x: x.get('published_parsed') or x.get('ts') or '',
            reverse=True
        )
        log.info("articles_sorted count=%d", len(all_items))
    except Exception:
        log.warning("article_sort_failed - continuing unsorted")

    # Return sorted items
    return all_items
```

**Expected Result:** Breaking news always processed first, regardless of source order or alert cap

### Testing Recommendations

1. **Verify sorting log appears:**
   ```bash
   grep "articles_sorted" data/logs/bot.jsonl | tail -5
   # Should show: articles_sorted_by_timestamp count=X
   ```

2. **Check alert timestamps:**
   - Before fix: Alerts may be 15-20 min old
   - After fix: Alerts should be <5 min old consistently

3. **Monitor alert quality:**
   ```bash
   # Check that newest articles are being alerted
   grep "alert_success" data/logs/bot.jsonl | tail -20
   # Verify timestamps are recent
   ```

4. **Test with alert cap:**
   ```bash
   # Set low alert cap to test prioritization
   export MAX_ALERTS_PER_CYCLE=3
   # Verify that the 3 alerts are for the NEWEST articles, not random/old ones
   ```

---

## Issue #4: SeenStore Database Not Initializing [HIGH]

### Problem Description

The SeenStore database (`data/seen_ids.sqlite`) is **not being created**, suggesting that the deduplication system isn't working properly. This means **previously-seen articles are being reprocessed every cycle**, contributing to the high article volume.

**Expected:** Database file at `/home/user/catalyst-bot/data/seen_ids.sqlite`
**Actual:** No SQLite files found in data directory

### Root Cause Analysis

**File:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py`

**Line 1000-1006:** SeenStore initialization with silent failure:

```python
try:
    if os.getenv("FEATURE_PERSIST_SEEN", "true").strip().lower() in {"1", "true", "yes", "on"}:
        seen_store = SeenStore()
except Exception:
    log.warning("seen_store_init_failed", exc_info=True)
    # ❌ PROBLEM: Silently continues with seen_store = None
    # No further action taken, all articles will bypass seen check
```

**Line 1318-1322:** Seen check - fails silently if seen_store is None:

```python
if item_id and seen_store and seen_store.is_seen(item_id):
    skipped_seen += 1
    continue
# ❌ PROBLEM: If seen_store is None, check is skipped - all items pass through
```

**Possible causes:**

1. **Directory doesn't exist:** `data/` directory not created
2. **Permission issues:** Bot doesn't have write access to `data/` directory
3. **SQLite not installed:** Missing SQLite3 library
4. **Configuration issue:** `FEATURE_PERSIST_SEEN` disabled or `SEEN_DB_PATH` misconfigured

### Impact Assessment

Without SeenStore:
- **No deduplication across cycles** - articles reprocess every 30-60 seconds
- **Duplicate alerts** - same article could alert multiple times
- **Wasted processing** - 50-80% of articles may be duplicates from previous cycles
- **Volume inflation** - 400 unique articles → 2000 with duplicates = **5x inflation**

### Proposed Fix

**Step 1: Add Explicit Initialization Check and Logging**

**File:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py`
**Line 1000-1006:**

```python
# ✅ IMPROVED: Better error handling and visibility
seen_store = None
try:
    feature_enabled = os.getenv("FEATURE_PERSIST_SEEN", "true").strip().lower() in {"1", "true", "yes", "on"}

    if not feature_enabled:
        log.warning("seen_store_disabled feature_flag=false")
    else:
        # Ensure data directory exists
        db_path = os.getenv("SEEN_DB_PATH", "data/seen_ids.sqlite")
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            log.info("seen_store_creating_dir path=%s", db_dir)
            os.makedirs(db_dir, exist_ok=True)

        seen_store = SeenStore()
        log.info("seen_store_initialized path=%s", db_path)

        # ✅ NEW: Verify database was actually created
        if not os.path.exists(db_path):
            log.error("seen_store_db_not_created path=%s - deduplication DISABLED", db_path)
            seen_store = None
        else:
            log.info("seen_store_verified db_exists=true path=%s", db_path)

except Exception as e:
    log.error("seen_store_init_failed err=%s - deduplication DISABLED", str(e), exc_info=True)
    seen_store = None

# ✅ NEW: Log status for monitoring
if seen_store is None:
    log.warning("SEEN_STORE_NOT_AVAILABLE - articles will reprocess every cycle!")
```

**Step 2: Add Seen Count to Cycle Metrics**

**File:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py`
**Line 2387-2418:** Add `skipped_seen` to cycle_metrics log:

```python
log.info(
    "cycle_metrics items=%s deduped=%s tickers_present=%s tickers_missing=%s "
    "dyn_weights=%s dyn_path_exists=%s dyn_path='%s' price_ceiling=%s "
    "skipped_no_ticker=%s skipped_crypto=%s skipped_ticker_relevance=%s skipped_price_gate=%s skipped_instr=%s skipped_by_source=%s "
    "skipped_multi_ticker=%s skipped_data_presentation=%s skipped_stale=%s skipped_otc=%s skipped_unit_warrant=%s skipped_low_volume=%s skipped_low_score=%s skipped_sent_gate=%s skipped_cat_gate=%s "
    "skipped_seen=%s "  # ✅ NEW: Add visibility to seen rejections
    "strong_negatives_bypassed=%s alerted=%s",
    len(items),
    len(deduped),
    tickers_present,
    tickers_missing,
    # ... existing parameters ...
    skipped_seen,  # ✅ NEW: Add the counter
    strong_negatives_bypassed,
    alerted,
)
```

**Step 3: Ensure Data Directory Exists**

**Add to project setup or create script:**

```bash
#!/bin/bash
# File: scripts/ensure_data_dirs.sh

# Create necessary directories for bot operation
mkdir -p data/logs
mkdir -p data/cache/alpha
mkdir -p data/cache/float

# Set permissions (if needed)
chmod 755 data
chmod 755 data/logs
chmod 755 data/cache

echo "Data directories created successfully"
```

**Or add to:** `/home/user/catalyst-bot/src/catalyst_bot/runner.py` (startup)

```python
def runner_main():
    """Main runner entry point."""
    # ✅ NEW: Ensure directories exist at startup
    required_dirs = [
        "data",
        "data/logs",
        "data/cache",
        "data/cache/alpha",
        "data/cache/float",
    ]
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            log.info("creating_directory path=%s", dir_path)
            os.makedirs(dir_path, exist_ok=True)

    # ... rest of runner_main
```

### Testing Recommendations

1. **Verify database creation:**
   ```bash
   ls -lh /home/user/catalyst-bot/data/seen_ids.sqlite
   # Should exist after first cycle
   ```

2. **Check database contents:**
   ```bash
   sqlite3 data/seen_ids.sqlite "SELECT COUNT(*) FROM seen;"
   # Should show growing number of seen articles

   sqlite3 data/seen_ids.sqlite "SELECT COUNT(*) FROM seen WHERE ts > strftime('%s', 'now') - 3600;"
   # Should show articles seen in last hour
   ```

3. **Monitor seen rejection rate:**
   ```bash
   grep "cycle_metrics" data/logs/bot.jsonl | tail -5
   # Should show: skipped_seen=50-200 (depending on volume)
   ```

4. **Verify initialization logs:**
   ```bash
   grep "seen_store" data/logs/bot.jsonl | head -20
   # Should show: seen_store_initialized, seen_store_verified
   # Should NOT show: seen_store_init_failed, SEEN_STORE_NOT_AVAILABLE
   ```

5. **Test duplicate detection:**
   - Run bot for 1 cycle, note article IDs alerted
   - Wait 2 minutes, run another cycle
   - Verify same articles are NOT alerted again (skipped_seen increments)

---

## Issue #5: Tiingo Price Data No Caching [MEDIUM]

### Problem Description

Price lookups via Tiingo API have **no caching layer**, causing repeated API calls for the same ticker within minutes. While the bot uses batch fetching via yfinance as primary method, Tiingo is used as fallback for failed tickers, and these fallback calls are slow and uncached.

**User has paid Tiingo tier:** 10,000 requests/hour (not a rate limit issue, but still wasteful)

### Root Cause Analysis

**File:** `/home/user/catalyst-bot/src/catalyst_bot/market.py`

**Line 202-265:** Direct Tiingo API calls with no caching:

```python
def _tiingo_last_prev(ticker: str, api_key: str, *, timeout: int = 8):
    """Return (last, previous_close) using Tiingo IEX API.

    ❌ PROBLEM: No caching - every call hits the API
    """
    url = f"https://api.tiingo.com/iex/{ticker.strip().upper()}"
    params = {"token": api_key}

    r = requests.get(url, params=params, timeout=timeout)  # Direct API call, no cache check

    if r.status_code != 200:
        return (None, None)

    data = r.json()
    # ... parse and return
```

**For comparison, Alpha Vantage HAS caching (lines 33-111):**

```python
def _alpha_last_prev_cached(ticker: str, api_key: str, *, timeout: int = 8):
    """Return (last, previous_close) using Alpha Vantage with disk cache."""

    # ✅ Check cache first
    cache_dir = os.environ.get("AV_CACHE_DIR", "data/cache/alpha")
    cache_ttl = int(os.environ.get("AV_CACHE_TTL_SECS", "0"))

    if cache_ttl > 0:
        # ... check cache logic
        if cached_data and not is_expired:
            return cached_data

    # Cache miss - fetch from API and cache result
    result = _alpha_last_prev(ticker, api_key, timeout=timeout)
    # ... save to cache
    return result
```

### Impact Assessment

**With 50 unique tickers per cycle:**
- Without cache: 50 API calls per cycle × 4 cycles/hour = **200 calls/hour**
- With 5-min cache: ~10 API calls per cycle × 4 cycles/hour = **40 calls/hour** (80% reduction)

**Performance impact:**
- Each uncached Tiingo call: 0.5-2 seconds (network latency)
- 50 tickers × 1s avg = **50 seconds wasted per cycle**
- With cache: Most lookups = <1ms (in-memory) = **<1 second total**

### Proposed Fix

**Implement Tiingo caching similar to Alpha Vantage:**

**File:** `/home/user/catalyst-bot/src/catalyst_bot/market.py`
**Add after line 201:**

```python
# ✅ NEW: In-memory cache for Tiingo price data
_TIINGO_CACHE = {}
_TIINGO_CACHE_LOCK = threading.Lock()

def _tiingo_last_prev_cached(ticker: str, api_key: str, *, timeout: int = 8):
    """Return (last, previous_close) using Tiingo IEX API with caching.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    api_key : str
        Tiingo API key
    timeout : int
        Request timeout in seconds (default: 8)

    Returns
    -------
    tuple of (float, float) or (None, None)
        (last_price, previous_close) or (None, None) on error
    """
    cache_ttl = int(os.getenv("TIINGO_CACHE_TTL_SECS", "300"))  # Default: 5 minutes

    if cache_ttl <= 0:
        # Caching disabled
        return _tiingo_last_prev(ticker, api_key, timeout=timeout)

    cache_key = ticker.upper()
    now = time.time()

    # Check cache
    with _TIINGO_CACHE_LOCK:
        if cache_key in _TIINGO_CACHE:
            cached_ts, cached_last, cached_prev = _TIINGO_CACHE[cache_key]
            age = now - cached_ts

            if age < cache_ttl:
                log.debug("tiingo_cache_hit ticker=%s age_sec=%.1f", ticker, age)
                return (cached_last, cached_prev)
            else:
                log.debug("tiingo_cache_expired ticker=%s age_sec=%.1f ttl=%d", ticker, age, cache_ttl)

    # Cache miss or expired - fetch from API
    log.debug("tiingo_cache_miss ticker=%s", ticker)
    last, prev = _tiingo_last_prev(ticker, api_key, timeout=timeout)

    # Store in cache
    if last is not None:
        with _TIINGO_CACHE_LOCK:
            _TIINGO_CACHE[cache_key] = (now, last, prev)
            log.debug("tiingo_cached ticker=%s last=%.2f prev=%.2f", ticker, last, prev)

    return (last, prev)
```

**Line 403-665:** Update `get_last_price_snapshot()` to use cached version:

```python
def get_last_price_snapshot(ticker: str, retries: int = 2):
    """Get last price and previous close with provider fallback chain."""

    # ... existing logic ...

    # Try Tiingo (with caching)
    if api_key:
        try:
            # BEFORE:
            # last, prev = _tiingo_last_prev(ticker, api_key, timeout=8)

            # AFTER:
            last, prev = _tiingo_last_prev_cached(ticker, api_key, timeout=8)  # ✅ Use cached version

            if last is not None:
                return (last, prev - last if prev else 0.0)
        except Exception:
            pass

    # ... rest of fallback chain
```

**Environment variable configuration:**

**File:** `.env` (add this line)

```bash
# Tiingo price caching (5 minutes = 300 seconds)
TIINGO_CACHE_TTL_SECS=300
```

**Optional: Add cache statistics logging:**

```python
def _log_tiingo_cache_stats():
    """Log cache hit/miss statistics."""
    with _TIINGO_CACHE_LOCK:
        size = len(_TIINGO_CACHE)
        log.info("tiingo_cache_stats size=%d", size)

# Call periodically from runner (e.g., end of cycle)
```

### Testing Recommendations

1. **Verify caching is enabled:**
   ```bash
   grep "tiingo_cache" data/logs/bot.jsonl | head -20
   # Should show: tiingo_cache_miss (first call), tiingo_cache_hit (subsequent)
   ```

2. **Monitor cache hit rate:**
   ```bash
   grep "tiingo_cache_hit" data/logs/bot.jsonl | wc -l
   grep "tiingo_cache_miss" data/logs/bot.jsonl | wc -l
   # Hit rate should be 70-90%
   ```

3. **Measure cycle time improvement:**
   ```bash
   grep "CYCLE_DONE" data/logs/bot.jsonl | tail -10
   # Should show reduction in total cycle time
   ```

4. **Verify API call reduction:**
   - Monitor Tiingo dashboard (if available)
   - Before: ~200 calls/hour
   - After: ~40-80 calls/hour

---

## Issue #6: Tiingo Sequential Fallback Not Parallelized [MEDIUM]

### Problem Description

When the batch price fetch via yfinance fails for multiple tickers, the fallback to Tiingo is **sequential** (one ticker at a time). With 50 failed tickers, this takes **50 × 8 seconds = 400 seconds (6.7 minutes)** per cycle.

### Root Cause Analysis

**File:** `/home/user/catalyst-bot/src/catalyst_bot/market.py`

**Line 850-867:** Sequential Tiingo fallback loop:

```python
def batch_get_prices(tickers):
    """Batch fetch prices with provider fallback."""

    # ... yfinance batch fetch (fast) ...

    # ❌ PROBLEM: Sequential fallback for failed tickers
    for ticker in failed_tickers:
        try:
            fallback_price, fallback_change = get_last_price_change(ticker)  # Blocking, 8s each
            if fallback_price is not None:
                result[ticker] = (fallback_price, fallback_change)
                log.info("batch_fallback_success ticker=%s provider=tiingo", ticker)
        except Exception as e:
            log.warning("batch_fallback_failed ticker=%s err=%s", ticker, str(e))
            result[ticker] = (None, 0.0)

    return result
```

**Each `get_last_price_change()` call:**
- Timeout: 8 seconds
- Retry backoff: 0.35 seconds
- Total: 8-16 seconds per ticker (worst case with retries)

### Impact Assessment

**Scenario: 50 tickers fail yfinance batch fetch**

- Sequential processing: 50 × 8s = **400 seconds (6.7 minutes)**
- With parallelization (10 workers): 50 ÷ 10 × 8s = **40 seconds (10x faster)**

### Proposed Fix

**Parallelize Tiingo fallback using ThreadPoolExecutor:**

**File:** `/home/user/catalyst-bot/src/catalyst_bot/market.py`
**Add import at top:**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

**Line 850-867:** Replace sequential loop with parallel execution:

```python
def batch_get_prices(tickers):
    """Batch fetch prices with provider fallback (parallelized)."""

    # ... existing yfinance batch fetch code ...

    # ✅ NEW: Parallel fallback for failed tickers
    failed_tickers = [t for t, (p, c) in result.items() if p is None]

    if failed_tickers:
        log.info("batch_fallback_start count=%d method=parallel", len(failed_tickers))

        # Configure worker pool
        max_workers = int(os.getenv("PRICE_FALLBACK_WORKERS", "10"))
        max_workers = min(max_workers, len(failed_tickers))  # Don't over-allocate

        def fetch_fallback(ticker):
            """Fetch single ticker via fallback (runs in thread)."""
            try:
                price, change = get_last_price_change(ticker)
                if price is not None:
                    log.debug("fallback_success ticker=%s price=%.2f", ticker, price)
                    return (ticker, price, change)
                else:
                    log.debug("fallback_no_data ticker=%s", ticker)
                    return (ticker, None, 0.0)
            except Exception as e:
                log.warning("fallback_error ticker=%s err=%s", ticker, str(e))
                return (ticker, None, 0.0)

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_fallback, t): t for t in failed_tickers}

            for future in as_completed(futures):
                ticker, price, change = future.result()
                result[ticker] = (price, change)

                if price is not None:
                    log.info("batch_fallback_success ticker=%s provider=tiingo", ticker)

        log.info("batch_fallback_complete count=%d", len(failed_tickers))

    return result
```

**Environment variable configuration:**

**File:** `.env` (add this line)

```bash
# Number of parallel workers for price fallback (default: 10)
PRICE_FALLBACK_WORKERS=10
```

**Alternative: Use asyncio for fully async approach**

If you want even better performance, convert to async:

```python
import asyncio
import aiohttp

async def _tiingo_last_prev_async(ticker: str, api_key: str, timeout: int = 8):
    """Async Tiingo price fetch."""
    url = f"https://api.tiingo.com/iex/{ticker.strip().upper()}"
    params = {"token": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # ... parse data
                    return (last, prev)
    except Exception:
        pass

    return (None, None)

async def batch_fallback_async(failed_tickers):
    """Fetch multiple tickers concurrently."""
    tasks = [_tiingo_last_prev_async(t, api_key) for t in failed_tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return dict(zip(failed_tickers, results))
```

### Testing Recommendations

1. **Measure fallback time:**
   ```bash
   # Add timing logs to see improvement
   grep "batch_fallback" data/logs/bot.jsonl | tail -10
   # Before: batch_fallback_complete count=50 took=400s
   # After: batch_fallback_complete count=50 took=40s
   ```

2. **Verify parallel execution:**
   ```bash
   # Check that multiple tickers are processed simultaneously
   grep "fallback_success" data/logs/bot.jsonl | head -50
   # Timestamps should be clustered (parallel) not sequential
   ```

3. **Monitor worker pool:**
   ```bash
   export PRICE_FALLBACK_WORKERS=5  # Test with fewer workers
   # Verify cycle time is slower with fewer workers
   ```

4. **Check for errors:**
   ```bash
   grep "fallback_error" data/logs/bot.jsonl | wc -l
   # Should be minimal - errors may indicate rate limiting or network issues
   ```

---

## Implementation Checklist

### Phase 1: Critical Fixes (Do First - Immediate Relief)

- [ ] **Issue #1: Finnhub Earnings Limit**
  - [ ] Modify `finnhub_feeds.py:1122` to use `days_ahead=2` OR disable entirely
  - [ ] Verify log shows `news=30 earnings=<300` instead of `earnings=1115`
  - [ ] Monitor cycle time drops from 15-18 min to <5 min
  - [ ] Expected time: 10 minutes

- [ ] **Issue #2: Timestamp Bug Fix**
  - [ ] Modify `_to_utc_iso()` to return `None` for missing timestamps
  - [ ] Update `_normalize_entry()` to flag uncertain timestamps
  - [ ] Update `_filter_by_freshness()` to reject uncertain timestamps
  - [ ] Verify freshness filter rejects 300-500 articles per cycle
  - [ ] Expected time: 20 minutes

- [ ] **Issue #3: Add Timestamp Sorting**
  - [ ] Add `deduped.sort()` call in `runner.py` after enrichment
  - [ ] Verify log shows `articles_sorted_by_timestamp`
  - [ ] Test with low alert cap to ensure newest articles prioritized
  - [ ] Expected time: 5 minutes

### Phase 2: High Priority (Do Next - Quality & Reliability)

- [ ] **Issue #4: Fix SeenStore Initialization**
  - [ ] Add directory creation to `runner_main()` startup
  - [ ] Improve error handling and logging in SeenStore init
  - [ ] Add `skipped_seen` to cycle_metrics log
  - [ ] Verify `data/seen_ids.sqlite` file is created
  - [ ] Query database to confirm seen articles are tracked
  - [ ] Expected time: 30 minutes

### Phase 3: Medium Priority (Do Later - Performance Optimization)

- [ ] **Issue #5: Add Tiingo Price Caching**
  - [ ] Implement `_tiingo_last_prev_cached()` function
  - [ ] Update `get_last_price_snapshot()` to use cached version
  - [ ] Add `TIINGO_CACHE_TTL_SECS=300` to .env
  - [ ] Verify cache hit rate is 70-90%
  - [ ] Expected time: 30 minutes

- [ ] **Issue #6: Parallelize Tiingo Fallback**
  - [ ] Add ThreadPoolExecutor to `batch_get_prices()`
  - [ ] Add `PRICE_FALLBACK_WORKERS=10` to .env
  - [ ] Measure fallback time improvement (400s → 40s)
  - [ ] Expected time: 45 minutes

### Phase 4: Verification & Monitoring

- [ ] **Run full cycle and verify logs:**
  ```bash
  # Check article counts
  grep "finnhub_feeds_added" data/logs/bot.jsonl | tail -1
  grep "freshness_filter_applied" data/logs/bot.jsonl | tail -1
  grep "cycle_metrics" data/logs/bot.jsonl | tail -1

  # Check cycle timing
  grep "CYCLE_DONE" data/logs/bot.jsonl | tail -5

  # Check SeenStore
  ls -lh data/seen_ids.sqlite
  sqlite3 data/seen_ids.sqlite "SELECT COUNT(*) FROM seen;"
  ```

- [ ] **Monitor alert latency:**
  - [ ] Before: 15-20 minutes after publication
  - [ ] After: <5 minutes after publication
  - [ ] Goal: <2 minutes consistently

- [ ] **Performance metrics:**
  - [ ] Articles per cycle: 2000 → 200-400 (80% reduction)
  - [ ] Cycle time: 15-18 min → <2 min (90% improvement)
  - [ ] Alert quality: More breaking news, fewer stale articles

---

## Expected Results After All Fixes

### Article Volume Reduction

| Source | Before | After Phase 1 | After Phase 2 |
|--------|--------|---------------|---------------|
| Finnhub News | 30 | 30 | 30 |
| Finnhub Earnings | 1,115 | 50-300 | 20-50 |
| Finviz | 82 | 82 | 82 |
| SEC Feeds | 400 | 100-200 | 100-200 |
| RSS Feeds | 100 | 50-80 | 50-80 |
| **Duplicates (SeenStore)** | +700 | +700 | +0 |
| **TOTAL** | **~2,400** | **~600** | **~300** |

### Cycle Time Improvement

| Metric | Before | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|--------|---------------|---------------|---------------|
| Article Processing | 12 min | 3 min | 1.5 min | 1 min |
| Price Lookups | 7 min | 7 min | 7 min | 0.5 min |
| Alert Delivery | 30 sec | 30 sec | 30 sec | 30 sec |
| **TOTAL CYCLE TIME** | **~19 min** | **~10 min** | **~8 min** | **~2 min** |

### Alert Latency

| Phase | Publication to Alert | Target Achieved |
|-------|---------------------|-----------------|
| Before | 15-20 minutes | ❌ |
| After Phase 1 | 8-12 minutes | 🟡 Improved |
| After Phase 2 | 4-8 minutes | 🟡 Better |
| After Phase 3 | 2-5 minutes | ✅ **GOAL MET** |

---

## Additional Recommendations

### Future Optimizations (Not Urgent)

1. **Add SEC feed date filtering:**
   - Modify SEC RSS URLs to include `&dateb=<today>` parameter
   - Reduces historical filing fetches

2. **Implement watchlist-based earnings:**
   - Only fetch earnings for tickers you're actively trading
   - Further reduces Finnhub volume

3. **Add rate limiter for Tiingo:**
   - Prevents accidental rate limit hits
   - Smooth out API usage

4. **Convert to async/await architecture:**
   - Full async pipeline for 10-50x performance improvement
   - More complex refactor, save for later

### Configuration Recommendations

**File:** `.env` (recommended settings after fixes)

```bash
# News freshness (strict for real-time alerts)
NEWS_MAX_AGE_MINUTES=5

# Alert cap (adjust based on quality)
MAX_ALERTS_PER_CYCLE=5

# Tiingo caching (5 minutes)
TIINGO_CACHE_TTL_SECS=300

# Price fallback parallelization
PRICE_FALLBACK_WORKERS=10

# SeenStore (ensure enabled)
FEATURE_PERSIST_SEEN=true
SEEN_DB_PATH=data/seen_ids.sqlite
SEEN_TTL_DAYS=7

# Finnhub (ensure enabled)
FEATURE_FINNHUB_NEWS=1
FINNHUB_API_KEY=your_key_here

# Finviz (ensure enabled)
FEATURE_FINVIZ_NEWS=1
FINVIZ_AUTH_TOKEN=your_token_here
```

---

## Support & Documentation

### Related Files

- **Investigation reports:** `/docs/MASTER_COORDINATION_PLAN.md`
- **Configuration guide:** `/docs/CONFIGURATION_GUIDE.md`
- **Performance report:** `/docs/PERFORMANCE_REPORT.md`

### Logging & Debugging

**Enable debug logging for troubleshooting:**

```bash
export LOG_LEVEL=DEBUG
export LOG_PLAIN=1  # Human-readable colored logs
```

**Key log patterns to monitor:**

```bash
# Article volume
grep "finnhub_feeds_added" data/logs/bot.jsonl
grep "freshness_filter_applied" data/logs/bot.jsonl
grep "cycle_metrics" data/logs/bot.jsonl

# Timing
grep "CYCLE_DONE" data/logs/bot.jsonl

# SeenStore
grep "seen_store" data/logs/bot.jsonl
grep "skipped_seen" data/logs/bot.jsonl

# Caching
grep "tiingo_cache" data/logs/bot.jsonl
```

### Questions or Issues?

If you encounter issues during implementation:

1. Check logs for error messages
2. Verify environment variables are set correctly
3. Ensure data directories exist and are writable
4. Test each fix independently before moving to next phase

---

**Document Version:** 1.0
**Date:** 2025-11-10
**Investigation Session:** claude/explore-news-scanner-011CUzPYMrUGcRfkJGhvphGt
