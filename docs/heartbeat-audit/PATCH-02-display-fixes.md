# PATCH-02: Display Fixes

> **Priority:** MEDIUM
> **Files Modified:** 1 (runner.py)
> **Estimated Time:** 1 vibecoding session

## Overview

This patch fixes two display issues in the heartbeat:

1. RSS feed source breakdown missing (shows aggregate only)
2. Average alerts/cycle rounding shows 0.0 for low values

---

## Issue 1: RSS Feed Source Breakdown

### Problem

The heartbeat shows `RSS Feeds: 1 items` without breaking down which sources contributed items. Compare to SEC filings which shows `SEC Filings: 44 filings (424B5: 1, 8-K: 42, FWP: 1)`.

### Root Cause Analysis

The `_track_feed_source()` function categorizes sources into buckets (`rss`, `sec`, `social`) but doesn't track individual source names. The data exists in `feeds.py` but is aggregated away.

### Solution

Add a new `RSS_SOURCE_BY_NAME` dict to track individual sources, similar to how `SEC_FILING_TYPES` tracks filing types.

### File: `src/catalyst_bot/runner.py`

### Step 1: Add Global Dict (After Line 159)

### Current Code (Lines 157-166)

```python
# Enhanced Admin Heartbeat: Feed source tracking
FEED_SOURCE_STATS: Dict[str, int] = {"rss": 0, "sec": 0, "social": 0}
SEC_FILING_TYPES: Dict[str, int] = {}  # "8k": count, "10q": count, etc.
TRADING_ACTIVITY_STATS: Dict[str, Any] = {
    "signals_generated": 0,
    "trades_executed": 0,
}
ERROR_TRACKER: List[Dict[str, Any]] = (
    []
)  # {"level": "error", "category": "API", "message": "..."}
```

### Modified Code

```python
# Enhanced Admin Heartbeat: Feed source tracking
FEED_SOURCE_STATS: Dict[str, int] = {"rss": 0, "sec": 0, "social": 0}
SEC_FILING_TYPES: Dict[str, int] = {}  # "8k": count, "10q": count, etc.
RSS_SOURCE_BY_NAME: Dict[str, int] = {}  # "globenewswire_public": count, "finnhub": count
TRADING_ACTIVITY_STATS: Dict[str, Any] = {
    "signals_generated": 0,
    "trades_executed": 0,
}
ERROR_TRACKER: List[Dict[str, Any]] = (
    []
)  # {"level": "error", "category": "API", "message": "..."}
```

### Step 2: Update `_track_feed_source()` (Lines 738-769)

### Current Code

```python
def _track_feed_source(source: str) -> None:
    """
    Track feed source type and SEC filing type.

    Args:
        source: Source string (e.g., "sec_8k", "globenewswire_public", "twitter")
    """
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES

        if not source:
            return

        source_lower = source.lower()

        # Classify source type
        if source_lower.startswith("sec_"):
            FEED_SOURCE_STATS["sec"] = FEED_SOURCE_STATS.get("sec", 0) + 1

            # Extract filing type (e.g., "sec_8k" -> "8k")
            filing_type = source_lower.replace("sec_", "")
            if filing_type:
                SEC_FILING_TYPES[filing_type] = SEC_FILING_TYPES.get(filing_type, 0) + 1

        elif any(social in source_lower for social in ["twitter", "reddit", "social"]):
            FEED_SOURCE_STATS["social"] = FEED_SOURCE_STATS.get("social", 0) + 1
        else:
            # Default to RSS/news
            FEED_SOURCE_STATS["rss"] = FEED_SOURCE_STATS.get("rss", 0) + 1

    except Exception:
        pass  # Silent fail - tracking is non-critical
```

### Modified Code

```python
def _track_feed_source(source: str) -> None:
    """
    Track feed source type, SEC filing type, and individual RSS source names.

    Args:
        source: Source string (e.g., "sec_8k", "globenewswire_public", "twitter")
    """
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES, RSS_SOURCE_BY_NAME

        if not source:
            return

        source_lower = source.lower()

        # Classify source type
        if source_lower.startswith("sec_"):
            FEED_SOURCE_STATS["sec"] = FEED_SOURCE_STATS.get("sec", 0) + 1

            # Extract filing type (e.g., "sec_8k" -> "8k")
            filing_type = source_lower.replace("sec_", "").upper()
            if filing_type:
                SEC_FILING_TYPES[filing_type] = SEC_FILING_TYPES.get(filing_type, 0) + 1

        elif any(social in source_lower for social in ["twitter", "reddit", "social"]):
            FEED_SOURCE_STATS["social"] = FEED_SOURCE_STATS.get("social", 0) + 1
            # Also track individual social sources
            RSS_SOURCE_BY_NAME[source_lower] = RSS_SOURCE_BY_NAME.get(source_lower, 0) + 1
        else:
            # Default to RSS/news
            FEED_SOURCE_STATS["rss"] = FEED_SOURCE_STATS.get("rss", 0) + 1
            # Track individual RSS source names
            RSS_SOURCE_BY_NAME[source_lower] = RSS_SOURCE_BY_NAME.get(source_lower, 0) + 1

    except Exception:
        pass  # Silent fail - tracking is non-critical
```

### Step 3: Update `_reset_cycle_tracking()` (Lines 802-812)

### Current Code

```python
def _reset_cycle_tracking() -> None:
    """Reset feed source tracking at start of each cycle."""
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES

        FEED_SOURCE_STATS = {"rss": 0, "sec": 0, "social": 0}
        SEC_FILING_TYPES = {}
        # Note: ERROR_TRACKER persists across cycles

    except Exception:
        pass
```

### Modified Code

```python
def _reset_cycle_tracking() -> None:
    """Reset feed source tracking at start of each cycle."""
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES, RSS_SOURCE_BY_NAME

        FEED_SOURCE_STATS = {"rss": 0, "sec": 0, "social": 0}
        SEC_FILING_TYPES = {}
        RSS_SOURCE_BY_NAME = {}
        # Note: ERROR_TRACKER persists across cycles

    except Exception:
        pass
```

### Step 4: Update `_get_feed_activity_summary()` (Lines ~629-672)

Find the function and update it to include RSS breakdown:

### Current Code (approximate)

```python
def _get_feed_activity_summary() -> Dict[str, Any]:
    """Get feed activity summary for heartbeat."""
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES

        rss_count = FEED_SOURCE_STATS.get("rss", 0)
        sec_count = FEED_SOURCE_STATS.get("sec", 0)
        social_count = FEED_SOURCE_STATS.get("social", 0)

        # Format SEC breakdown
        if SEC_FILING_TYPES:
            sec_parts = [f"{k.upper()}: {v}" for k, v in sorted(SEC_FILING_TYPES.items())]
            sec_breakdown = ", ".join(sec_parts)
        else:
            sec_breakdown = "—"

        return {
            "rss_count": rss_count,
            "sec_count": sec_count,
            "social_count": social_count,
            "sec_breakdown": sec_breakdown,
        }
    except Exception:
        return {
            "rss_count": 0,
            "sec_count": 0,
            "social_count": 0,
            "sec_breakdown": "—",
        }
```

### Modified Code

```python
def _get_feed_activity_summary() -> Dict[str, Any]:
    """Get feed activity summary for heartbeat."""
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES, RSS_SOURCE_BY_NAME

        rss_count = FEED_SOURCE_STATS.get("rss", 0)
        sec_count = FEED_SOURCE_STATS.get("sec", 0)
        social_count = FEED_SOURCE_STATS.get("social", 0)

        # Format SEC breakdown
        if SEC_FILING_TYPES:
            sec_parts = [f"{k}: {v}" for k, v in sorted(SEC_FILING_TYPES.items())]
            sec_breakdown = ", ".join(sec_parts)
        else:
            sec_breakdown = "—"

        # Format RSS source breakdown (top 5 by count)
        if RSS_SOURCE_BY_NAME:
            # Sort by count descending, take top 5
            sorted_sources = sorted(
                RSS_SOURCE_BY_NAME.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            # Format source names nicely (remove underscores, title case)
            rss_parts = []
            for src, count in sorted_sources:
                # Clean up source name for display
                display_name = src.replace("_", " ").replace("public", "").strip()
                display_name = display_name.title() if display_name else src
                rss_parts.append(f"{display_name}: {count}")
            rss_breakdown = ", ".join(rss_parts)
        else:
            rss_breakdown = "—"

        return {
            "rss_count": rss_count,
            "sec_count": sec_count,
            "social_count": social_count,
            "sec_breakdown": sec_breakdown,
            "rss_breakdown": rss_breakdown,
        }
    except Exception:
        return {
            "rss_count": 0,
            "sec_count": 0,
            "social_count": 0,
            "sec_breakdown": "—",
            "rss_breakdown": "—",
        }
```

### Step 5: Update Heartbeat Display

Find where feed activity is displayed in `_send_heartbeat()` and update:

### Current Display Code (approximate, in embed fields)

```python
{
    "name": "📰 Feed Activity (Last Hour)",
    "value": (
        f"RSS Feeds: {feed_summary['rss_count']} items\n"
        f"SEC Filings: {feed_summary['sec_count']} filings ({feed_summary['sec_breakdown']})\n"
        f"Twitter/Social: {feed_summary['social_count']} posts"
    ),
    "inline": False,
}
```

### Modified Display Code

```python
{
    "name": "📰 Feed Activity (Last Hour)",
    "value": (
        f"RSS Feeds: {feed_summary['rss_count']} items ({feed_summary['rss_breakdown']})\n"
        f"SEC Filings: {feed_summary['sec_count']} filings ({feed_summary['sec_breakdown']})\n"
        f"Twitter/Social: {feed_summary['social_count']} posts"
    ),
    "inline": False,
}
```

### Expected Output

**Before:**
```
📰 Feed Activity (Last Hour)
RSS Feeds: 1 items
SEC Filings: 44 filings (424B5: 1, 8-K: 42, FWP: 1)
Twitter/Social: 0 posts
```

**After:**
```
📰 Feed Activity (Last Hour)
RSS Feeds: 29 items (Finnhub: 28, Globenewswire: 1)
SEC Filings: 44 filings (424B5: 1, 8-K: 42, FWP: 1)
Twitter/Social: 0 posts
```

---

## Issue 2: Average Alerts/Cycle Rounding

### Problem

The heartbeat shows `Avg Alerts/Cycle: 0.0` even when 2 alerts were posted over 60 cycles.

### Root Cause Analysis

The calculation at `runner.py:276-278`:
```python
"avg_alerts_per_cycle": round(
    self.total_alerts / max(self.cycles_completed, 1), 1
),
```

Math: `2 / 60 = 0.0333...` → `round(0.0333, 1) = 0.0`

### Solution Options

| Option | Display | Pros | Cons |
|--------|---------|------|------|
| 2 decimal places | 0.03 | Accurate | Looks odd |
| Fraction format | "2 in 60 cycles" | Clear | Different format |
| Percentage | "3.3%" | Intuitive | Different meaning |
| Conditional | 0.03 or "2/60" | Best of both | Complex |

### Recommended: 2 Decimal Places + Conditional

### File: `src/catalyst_bot/runner.py`

### Current Code (Lines 276-278)

```python
            "avg_alerts_per_cycle": round(
                self.total_alerts / max(self.cycles_completed, 1), 1
            ),
```

### Modified Code

```python
            "avg_alerts_per_cycle": self._format_avg_alerts(),
```

### Add Helper Method (After Line 278, inside HeartbeatAccumulator class)

```python
    def _format_avg_alerts(self) -> str:
        """Format average alerts per cycle with appropriate precision.

        Uses 2 decimal places for low values to avoid showing 0.0 when
        there are actual alerts. Falls back to 1 decimal for larger values.
        """
        if self.cycles_completed == 0:
            return "0.0"

        avg = self.total_alerts / self.cycles_completed

        if avg == 0:
            return "0.0"
        elif avg < 0.1:
            # Low value - use 2 decimal places to show actual value
            return f"{avg:.2f}"
        elif avg < 1:
            # Medium value - use 1 decimal place
            return f"{avg:.1f}"
        else:
            # High value - use 1 decimal place
            return f"{avg:.1f}"
```

### Complete Modified HeartbeatAccumulator Class

```python
class HeartbeatAccumulator:
    """Track cumulative stats between heartbeat messages."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all counters (called after sending heartbeat)."""
        self.total_scanned = 0
        self.total_alerts = 0
        self.total_errors = 0
        self.cycles_completed = 0
        self.last_heartbeat_time = datetime.now(timezone.utc)

    def add_cycle(self, scanned: int, alerts: int, errors: int):
        """Record stats from a completed cycle."""
        self.total_scanned += scanned
        self.total_alerts += alerts
        self.total_errors += errors
        self.cycles_completed += 1

    def should_send_heartbeat(self, interval_minutes: int = 60) -> bool:
        """Check if it's time to send heartbeat."""
        elapsed = (
            datetime.now(timezone.utc) - self.last_heartbeat_time
        ).total_seconds()
        return elapsed >= (interval_minutes * 60)

    def _format_avg_alerts(self) -> str:
        """Format average alerts per cycle with appropriate precision.

        Uses 2 decimal places for low values to avoid showing 0.0 when
        there are actual alerts. Falls back to 1 decimal for larger values.
        """
        if self.cycles_completed == 0:
            return "0.0"

        avg = self.total_alerts / self.cycles_completed

        if avg == 0:
            return "0.0"
        elif avg < 0.1:
            # Low value - use 2 decimal places to show actual value
            return f"{avg:.2f}"
        elif avg < 1:
            # Medium value - use 1 decimal place
            return f"{avg:.1f}"
        else:
            # High value - use 1 decimal place
            return f"{avg:.1f}"

    def get_stats(self) -> dict:
        """Get cumulative stats for heartbeat message."""
        elapsed_min = (
            datetime.now(timezone.utc) - self.last_heartbeat_time
        ).total_seconds() / 60
        return {
            "total_scanned": self.total_scanned,
            "total_alerts": self.total_alerts,
            "total_errors": self.total_errors,
            "cycles_completed": self.cycles_completed,
            "elapsed_minutes": round(elapsed_min, 1),
            "avg_alerts_per_cycle": self._format_avg_alerts(),
        }
```

### Expected Output

**Before:**
```
Avg Alerts/Cycle: 0.0
```

**After:**
```
Avg Alerts/Cycle: 0.03
```

### Alternative: Show Raw Fraction

If you prefer showing the raw numbers:

```python
    def _format_avg_alerts(self) -> str:
        """Format average alerts per cycle."""
        if self.cycles_completed == 0:
            return "—"

        avg = self.total_alerts / self.cycles_completed

        if avg == 0:
            return "0"
        elif avg < 0.1 and self.total_alerts > 0:
            # Show as fraction for clarity
            return f"{self.total_alerts}/{self.cycles_completed}"
        else:
            return f"{avg:.1f}"
```

This would display: `Avg Alerts/Cycle: 2/60`

---

## Complete Change List

| File | Lines | Change |
|------|-------|--------|
| `runner.py` | 159 | Add `RSS_SOURCE_BY_NAME` global dict |
| `runner.py` | 746 | Add `RSS_SOURCE_BY_NAME` to global declaration |
| `runner.py` | 764-766 | Track individual RSS source names |
| `runner.py` | 805 | Add `RSS_SOURCE_BY_NAME` to global declaration |
| `runner.py` | 810 | Reset `RSS_SOURCE_BY_NAME = {}` |
| `runner.py` | ~640-665 | Add `rss_breakdown` to feed summary |
| `runner.py` | ~1115 | Update feed activity display to show breakdown |
| `runner.py` | 265-279 | Add `_format_avg_alerts()` method |
| `runner.py` | 276-278 | Use `_format_avg_alerts()` in `get_stats()` |

## Testing Checklist

- [ ] RSS Feeds shows source breakdown (e.g., "Finnhub: 28, Globenewswire: 1")
- [ ] SEC Filings breakdown unchanged
- [ ] Avg Alerts/Cycle shows 0.03 for 2 alerts / 60 cycles
- [ ] Avg Alerts/Cycle shows 0.0 for 0 alerts
- [ ] Avg Alerts/Cycle shows 1.5 for high values
- [ ] No errors when RSS_SOURCE_BY_NAME is empty
- [ ] No truncation issues with long source lists (top 5 limit)

## Commit Message Template

```
fix(heartbeat): improve RSS source visibility and avg precision

- Add RSS_SOURCE_BY_NAME tracking for individual feed sources
- Display top 5 RSS sources by count in heartbeat
- Fix avg_alerts_per_cycle to use 2 decimal places for low values
- Prevent misleading 0.0 display when alerts exist

Closes: RSS breakdown missing, Avg showing 0.0 incorrectly

Audit: docs/heartbeat-audit/PATCH-02-display-fixes.md
```

---

*Proceed to [PATCH-03: Error Monitoring](./PATCH-03-error-monitoring.md) after completing this patch.*
