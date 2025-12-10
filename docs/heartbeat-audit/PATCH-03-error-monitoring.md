# PATCH-03: Error Monitoring

> **Priority:** MEDIUM
> **Files Modified:** 1-2
> **Estimated Time:** 1 vibecoding session

## Overview

This patch connects the existing error tracking infrastructure to the heartbeat display. The infrastructure exists but isn't being populated.

**What Exists:**
- `ERROR_TRACKER` circular buffer in `runner.py`
- `_track_error()` function in `runner.py`
- `_get_error_summary()` function in `runner.py`
- `health_monitor.py` with `record_error()` function

**What's Missing:**
- Calls to `_track_error()` from exception handlers
- Integration between `health_monitor` and heartbeat

---

## Current Architecture

### ERROR_TRACKER (runner.py:164-166)

```python
ERROR_TRACKER: List[Dict[str, Any]] = (
    []
)  # {"level": "error", "category": "API", "message": "..."}
```

### _track_error() (runner.py:772-799)

```python
def _track_error(level: str, category: str, message: str) -> None:
    """
    Track error in global ERROR_TRACKER.

    Args:
        level: "error", "warning", or "info"
        category: Error category (e.g., "API", "LLM", "Database")
        message: Error message
    """
    try:
        global ERROR_TRACKER
        from datetime import datetime, timezone

        ERROR_TRACKER.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "category": category,
                "message": message,
            }
        )

        # Keep only last 100 errors (circular buffer)
        if len(ERROR_TRACKER) > 100:
            ERROR_TRACKER = ERROR_TRACKER[-100:]

    except Exception:
        pass  # Silent fail - error tracking shouldn't cause errors
```

### health_monitor.py (Lines 80-90)

```python
def record_error() -> None:
    """Record an error occurrence."""
    global _ERROR_COUNT_HOUR, _LAST_ERROR_RESET

    now = time.time()
    # Reset hourly error counter
    if now - _LAST_ERROR_RESET > 3600:
        _ERROR_COUNT_HOUR = 0
        _LAST_ERROR_RESET = now

    _ERROR_COUNT_HOUR += 1
```

---

## Solution: Connect Error Tracking to Key Locations

### Strategy

1. Add `_track_error()` calls to main exception handlers in `runner.py`
2. Categorize errors appropriately (API, LLM, Feed, Database, etc.)
3. Also call `health_monitor.record_error()` for hourly counts

### File: `src/catalyst_bot/runner.py`

### Location 1: Feed Fetching Errors

Find the main cycle loop where feeds are fetched. Add error tracking around feed failures.

### Example Pattern

```python
# Before
try:
    items, summary = fetch_pr_feeds(seen_store)
except Exception as e:
    log.error("feed_fetch_failed error=%s", str(e))
    items, summary = [], {}

# After
try:
    items, summary = fetch_pr_feeds(seen_store)
except Exception as e:
    log.error("feed_fetch_failed error=%s", str(e))
    _track_error("error", "Feed", f"Feed fetch failed: {str(e)[:100]}")
    try:
        from .health_monitor import record_error
        record_error()
    except Exception:
        pass
    items, summary = [], {}
```

### Location 2: Classification Errors

```python
# Before
try:
    scored = fast_classify(item, keyword_weights)
except Exception as e:
    log.error("classify_failed error=%s", str(e))
    continue

# After
try:
    scored = fast_classify(item, keyword_weights)
except Exception as e:
    log.error("classify_failed error=%s", str(e))
    _track_error("error", "Classification", f"Classify failed: {str(e)[:100]}")
    try:
        from .health_monitor import record_error
        record_error()
    except Exception:
        pass
    continue
```

### Location 3: Alert Posting Errors

```python
# Before
try:
    ok = send_alert_safe(...)
except Exception as e:
    log.error("alert_post_failed error=%s", str(e))
    ok = False

# After
try:
    ok = send_alert_safe(...)
except Exception as e:
    log.error("alert_post_failed error=%s", str(e))
    _track_error("error", "Discord", f"Alert post failed: {str(e)[:100]}")
    try:
        from .health_monitor import record_error
        record_error()
    except Exception:
        pass
    ok = False
```

### Location 4: API Errors (Tiingo, Finnhub, etc.)

```python
# Before
try:
    price = get_current_price(ticker)
except Exception as e:
    log.warning("price_fetch_failed ticker=%s error=%s", ticker, str(e))
    price = None

# After
try:
    price = get_current_price(ticker)
except Exception as e:
    log.warning("price_fetch_failed ticker=%s error=%s", ticker, str(e))
    _track_error("warning", "API", f"Price fetch failed for {ticker}: {str(e)[:80]}")
    price = None
```

### Location 5: LLM Errors

```python
# Before
try:
    llm_result = process_with_llm(item)
except Exception as e:
    log.error("llm_processing_failed error=%s", str(e))
    llm_result = None

# After
try:
    llm_result = process_with_llm(item)
except Exception as e:
    log.error("llm_processing_failed error=%s", str(e))
    _track_error("error", "LLM", f"LLM processing failed: {str(e)[:100]}")
    try:
        from .health_monitor import record_error
        record_error()
    except Exception:
        pass
    llm_result = None
```

---

## Helper Function: Unified Error Tracking

To reduce code duplication, add a helper function:

### File: `src/catalyst_bot/runner.py`

### Add After Line 799 (after `_track_error()`)

```python
def _record_and_track_error(
    level: str,
    category: str,
    message: str,
    log_func=None,
    log_message: str = None
) -> None:
    """
    Track error in both ERROR_TRACKER and health_monitor.

    This is a convenience wrapper that:
    1. Calls _track_error() for heartbeat display
    2. Calls health_monitor.record_error() for hourly counts
    3. Optionally logs the error

    Args:
        level: "error", "warning", or "info"
        category: Error category (e.g., "API", "LLM", "Database", "Feed", "Discord")
        message: Error message (will be truncated to 100 chars)
        log_func: Optional logging function (e.g., log.error, log.warning)
        log_message: Optional message to log (if different from message)

    Example:
        _record_and_track_error(
            "error", "Feed", f"Feed fetch failed: {e}",
            log_func=log.error, log_message=f"feed_fetch_failed error={e}"
        )
    """
    # Track in ERROR_TRACKER for heartbeat display
    _track_error(level, category, message[:100] if message else "Unknown error")

    # Track in health_monitor for hourly counts
    if level == "error":
        try:
            from .health_monitor import record_error
            record_error()
        except Exception:
            pass

    # Optionally log
    if log_func and log_message:
        try:
            log_func(log_message)
        except Exception:
            pass
```

### Usage Examples

```python
# Feed error
_record_and_track_error(
    "error", "Feed", f"Feed fetch failed: {e}",
    log_func=log.error, log_message=f"feed_fetch_failed error={e}"
)

# API warning
_record_and_track_error(
    "warning", "API", f"Price fetch failed for {ticker}: {e}"
)

# Discord error
_record_and_track_error(
    "error", "Discord", f"Webhook post failed: {e}",
    log_func=log.error, log_message=f"discord_post_failed error={e}"
)
```

---

## Specific Locations to Modify

Based on the codebase structure, here are the specific locations to add error tracking:

### 1. Main Cycle Exception Handler

Find the main `while not STOP:` loop and its outer try/except:

```python
# Look for pattern like:
while not STOP:
    try:
        # ... cycle code ...
    except Exception as e:
        log.error("cycle_error error=%s", str(e))
        # ADD HERE:
        _record_and_track_error(
            "error", "Cycle", f"Main cycle error: {e}",
            log_func=log.error, log_message=f"cycle_error error={e}"
        )
```

### 2. Feed Fetch in _cycle() Function

```python
# In _cycle() function, around feed fetching:
try:
    items, summary = fetch_pr_feeds(seen_store)
except Exception as e:
    _record_and_track_error("error", "Feed", f"Feed fetch: {e}")
    items, summary = [], {}
```

### 3. Price Enrichment

```python
# In price enrichment section:
try:
    price_data = enrich_with_prices(items)
except Exception as e:
    _record_and_track_error("warning", "API", f"Price enrichment: {e}")
```

### 4. Classification Loop

```python
# In classification loop:
for item in items:
    try:
        scored = fast_classify(item)
    except Exception as e:
        _record_and_track_error("error", "Classification", f"Classify: {e}")
        continue
```

### 5. Alert Posting

```python
# In alert posting:
try:
    ok = send_alert_safe(payload, ...)
    if not ok:
        _record_and_track_error("warning", "Discord", "Alert post returned False")
except Exception as e:
    _record_and_track_error("error", "Discord", f"Alert post: {e}")
```

### 6. Trading Execution

```python
# In trading execution (alerts.py):
try:
    success = execute_with_trading_engine(...)
except Exception as trade_err:
    # Add tracking here
    try:
        from .runner import _record_and_track_error
        _record_and_track_error("error", "Trading", f"Trade execution: {trade_err}")
    except Exception:
        pass
```

---

## Enhanced Error Summary Display

### Update `_get_error_summary()` to Include Counts

### Current Code (runner.py:675-735)

The function already handles grouping and formatting. Enhance it to also show hourly count from health_monitor:

### Modified Code

```python
def _get_error_summary() -> str:
    """
    Get formatted error summary from global ERROR_TRACKER.

    Returns:
        Multi-line string with color-coded errors (🔴/🟡/🟢)
    """
    try:
        global ERROR_TRACKER

        # Get hourly error count from health_monitor
        hourly_count = 0
        try:
            from .health_monitor import get_error_count
            hourly_count = get_error_count()
        except Exception:
            pass

        if not ERROR_TRACKER and hourly_count == 0:
            return "No errors or warnings"

        # Group errors by category
        error_groups: Dict[str, Dict[str, int]] = {}
        for error in ERROR_TRACKER[-50:]:  # Last 50 errors
            level = error.get("level", "info")
            category = error.get("category", "Unknown")
            message = error.get("message", "")

            if category not in error_groups:
                error_groups[category] = {
                    "error": 0,
                    "warning": 0,
                    "info": 0,
                    "sample": "",
                }

            error_groups[category][level] += 1
            if not error_groups[category]["sample"]:
                error_groups[category]["sample"] = message[:50]

        # Format output with emojis
        lines = []

        # Add hourly summary if we have errors
        if hourly_count > 0:
            lines.append(f"📊 {hourly_count} errors in last hour")

        for category, counts in sorted(error_groups.items()):
            total_errors = counts["error"]
            total_warnings = counts["warning"]
            total_info = counts["info"]

            if total_errors > 0:
                emoji = "🔴"
                display_count = total_errors
                level_text = "errors"
            elif total_warnings > 0:
                emoji = "🟡"
                display_count = total_warnings
                level_text = "warnings"
            else:
                emoji = "🟢"
                display_count = total_info
                level_text = "info"

            sample = counts["sample"]
            line = f"{emoji} {category}: {display_count} {level_text}"
            if sample:
                line += f"\n   └─ {sample}"
            lines.append(line)

        return "\n".join(lines) if lines else "No errors or warnings"
    except Exception:
        return "Error retrieving stats"
```

### Expected Output

**Before:**
```
⚠️ Errors & Warnings
No errors or warnings
```

**After (with errors):**
```
⚠️ Errors & Warnings
📊 3 errors in last hour
🔴 Feed: 1 errors
   └─ Feed fetch failed: Connection timeout
🟡 API: 2 warnings
   └─ Price fetch failed for AAPL: Rate limited
```

---

## Error Categories Reference

Use consistent categories for tracking:

| Category | When to Use | Level |
|----------|-------------|-------|
| `Feed` | RSS/Atom feed fetch failures | error |
| `API` | External API errors (Tiingo, Finnhub, etc.) | warning/error |
| `Discord` | Webhook post failures | error |
| `LLM` | LLM API or processing errors | error |
| `Classification` | Score calculation errors | error |
| `Trading` | Trade execution failures | error |
| `Database` | SQLite/storage errors | error |
| `Config` | Configuration/env var issues | warning |
| `Cycle` | Main loop errors | error |

---

## Complete Change List

| File | Lines | Change |
|------|-------|--------|
| `runner.py` | 800-835 | Add `_record_and_track_error()` helper |
| `runner.py` | ~675-735 | Enhance `_get_error_summary()` with hourly count |
| `runner.py` | Various | Add error tracking calls to exception handlers |
| `alerts.py` | ~1485-1491 | Add trading error tracking |

## Testing Checklist

- [ ] "Errors & Warnings" shows hourly count when errors exist
- [ ] Error categories display correctly (Feed, API, Discord, etc.)
- [ ] Error levels show correct emoji (🔴 error, 🟡 warning, 🟢 info)
- [ ] Sample error messages truncate properly
- [ ] "No errors or warnings" displays when tracker is empty
- [ ] Errors don't persist across heartbeat intervals (or do, depending on design)

## Testing Tips

To verify error tracking works:

1. **Simulate feed error:**
   ```bash
   # Temporarily set invalid RSS URL
   export GLOBENEWSWIRE_RSS_URL="http://invalid.example.com"
   ```

2. **Simulate API error:**
   ```bash
   # Temporarily set invalid API key
   export TIINGO_API_KEY="invalid"
   ```

3. **Check heartbeat:**
   - Wait for interval heartbeat
   - Verify errors appear in "Errors & Warnings" section

## Commit Message Template

```
feat(heartbeat): connect error monitoring to heartbeat display

- Add _record_and_track_error() unified error tracking helper
- Connect error tracking to feed, API, LLM, and Discord handlers
- Enhance _get_error_summary() with hourly error count
- Integrate health_monitor.record_error() for metrics

Enables admin visibility into bot errors via heartbeat alerts

Audit: docs/heartbeat-audit/PATCH-03-error-monitoring.md
```

---

*Proceed to [PATCH-04: Enhancements](./PATCH-04-enhancements.md) after completing this patch.*
