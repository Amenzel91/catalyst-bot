# PATCH-04: Enhancements

> **Priority:** LOW
> **Files Modified:** 1-3
> **Estimated Time:** 1-2 vibecoding sessions

## Overview

This patch includes general improvements and new features to enhance admin visibility:

1. General code cleanup (duplicate tracking, hardcoded values)
2. Uptime counter display
3. Feed health matrix
4. API rate limit status
5. Memory/CPU usage
6. Last error detail
7. Alert win rate (24h preview)

---

## Part A: General Code Cleanup

### Issue 1: Duplicate Stat Tracking

Both `LAST_CYCLE_STATS` and `HeartbeatAccumulator` track similar data.

### File: `src/catalyst_bot/runner.py`

### Current Code (Lines 150-155)

```python
LAST_CYCLE_STATS: Dict[str, Any] = {}

# Accumulate totals across all cycles to provide new/total counters on
# heartbeats.  Keys mirror LAST_CYCLE_STATS; values start at zero and
# are incremented at the end of each cycle.  See update in _cycle().
TOTAL_STATS: Dict[str, int] = {"items": 0, "deduped": 0, "skipped": 0, "alerts": 0}
```

### Recommendation

Keep both for now as they serve different purposes:
- `LAST_CYCLE_STATS`: Per-cycle snapshot for logging
- `TOTAL_STATS`: Running totals across all cycles
- `HeartbeatAccumulator`: Totals between heartbeat sends (resets after each heartbeat)

Add a comment clarifying the distinction:

```python
# Per-cycle stats snapshot (reset each cycle, used for logging)
LAST_CYCLE_STATS: Dict[str, Any] = {}

# Running totals across ALL cycles since startup (never reset)
# Used for: total items processed, total alerts sent lifetime
TOTAL_STATS: Dict[str, int] = {"items": 0, "deduped": 0, "skipped": 0, "alerts": 0}

# Note: HeartbeatAccumulator tracks stats BETWEEN heartbeat sends,
# and resets after each heartbeat is posted. Use for period metrics.
```

### Issue 2: Hardcoded Cycle Time

The heartbeat shows `Scan Cycle: 30 sec` hardcoded instead of using actual config.

### Find and Fix

Search for hardcoded "30 sec" in heartbeat display and replace with dynamic value:

```python
# Before
"cycle_time": "30 sec"

# After
cycle_seconds = int(os.getenv("SCAN_INTERVAL", "30"))
"cycle_time": f"{cycle_seconds} sec"
```

### Issue 3: Missing Error Propagation in add_cycle()

The `add_cycle()` call always passes `errors=0`:

### Current Code (approximately line 3451-3456)

```python
_heartbeat_acc.add_cycle(
    scanned=len(items),
    alerts=alerted,
    errors=0,  # Always 0!
)
```

### Modified Code

Track errors in the cycle and pass the actual count:

```python
# At start of cycle:
cycle_errors = 0

# In exception handlers:
except Exception as e:
    cycle_errors += 1
    # ... existing error handling

# At end of cycle:
_heartbeat_acc.add_cycle(
    scanned=len(items),
    alerts=alerted,
    errors=cycle_errors,
)
```

---

## Part B: New Features

### Feature 1: Uptime Counter

Display how long the bot has been running since last restart.

### File: `src/catalyst_bot/runner.py`

### Add to `_send_heartbeat()` embed fields

```python
# Get uptime from health_monitor
def _get_uptime_display() -> str:
    """Get formatted uptime string."""
    try:
        from .health_monitor import get_uptime
        uptime_seconds = get_uptime()

        if uptime_seconds < 60:
            return f"{int(uptime_seconds)}s"
        elif uptime_seconds < 3600:
            minutes = int(uptime_seconds // 60)
            seconds = int(uptime_seconds % 60)
            return f"{minutes}m {seconds}s"
        elif uptime_seconds < 86400:
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            return f"{days}d {hours}h"
    except Exception:
        return "—"
```

### Add to heartbeat embed (in System Info or Market Status section)

```python
{
    "name": "⏱️ Uptime",
    "value": _get_uptime_display(),
    "inline": True,
}
```

---

### Feature 2: Feed Health Matrix

Show per-source status with indicators.

### Add Function

```python
def _get_feed_health_matrix() -> str:
    """
    Get feed health status for each source.

    Returns:
        Formatted string with status indicators per feed source
    """
    try:
        # Get last fetch summary from feeds module if available
        # This would require feeds.py to expose last_fetch_summary
        from .feeds import get_last_fetch_summary

        summary = get_last_fetch_summary()
        if not summary or "by_source" not in summary:
            return "—"

        lines = []
        for source, stats in sorted(summary["by_source"].items()):
            if stats.get("ok", 0) > 0:
                emoji = "✅"
                status = f"{stats.get('entries', 0)} items"
            elif stats.get("not_modified", 0) > 0:
                emoji = "📋"  # 304 Not Modified (cached)
                status = "cached"
            elif stats.get("http4", 0) > 0:
                emoji = "⚠️"
                status = "4xx error"
            elif stats.get("http5", 0) > 0:
                emoji = "🔴"
                status = "5xx error"
            elif stats.get("errors", 0) > 0:
                emoji = "❌"
                status = "error"
            else:
                emoji = "⏸️"
                status = "no data"

            # Shorten source name
            short_name = source.replace("_public", "").replace("_", " ").title()[:15]
            lines.append(f"{emoji} {short_name}: {status}")

        return "\n".join(lines[:8]) if lines else "—"  # Limit to 8 sources
    except Exception:
        return "—"
```

### Requires: Add to feeds.py

```python
# Global to store last fetch summary
_LAST_FETCH_SUMMARY: Dict[str, Any] = {}

def get_last_fetch_summary() -> Dict[str, Any]:
    """Get the summary from the last feed fetch."""
    return _LAST_FETCH_SUMMARY

# Update in fetch_pr_feeds():
def fetch_pr_feeds(...):
    global _LAST_FETCH_SUMMARY
    # ... existing code ...
    _LAST_FETCH_SUMMARY = summary
    return all_items, summary
```

### Add to Heartbeat

```python
{
    "name": "🔌 Feed Health",
    "value": _get_feed_health_matrix(),
    "inline": False,
}
```

### Expected Output

```
🔌 Feed Health
✅ Globenewswire: 1 items
✅ Sec 8K: 42 items
✅ Sec 424B5: 1 items
✅ Finnhub: 28 items
📋 Sec 13D: cached
⚠️ Twitter: 4xx error
```

---

### Feature 3: API Rate Limit Status

Show remaining API quota for key services.

### Add Function

```python
def _get_api_rate_status() -> str:
    """
    Get rate limit status for external APIs.

    Returns:
        Formatted string with remaining quota indicators
    """
    try:
        lines = []

        # Discord rate limit (from alerts module if tracked)
        try:
            from .alerts import get_discord_rate_status
            discord_status = get_discord_rate_status()
            if discord_status:
                remaining = discord_status.get("remaining", "?")
                emoji = "🟢" if remaining == "?" or int(remaining) > 5 else "🟡"
                lines.append(f"{emoji} Discord: {remaining} remaining")
        except Exception:
            pass

        # Tiingo rate limit
        try:
            from .providers.tiingo import get_rate_limit_status
            tiingo = get_rate_limit_status()
            if tiingo:
                used = tiingo.get("used", 0)
                limit = tiingo.get("limit", 1000)
                pct = (used / limit * 100) if limit > 0 else 0
                emoji = "🟢" if pct < 50 else "🟡" if pct < 80 else "🔴"
                lines.append(f"{emoji} Tiingo: {used}/{limit} ({pct:.0f}%)")
        except Exception:
            pass

        # Finnhub rate limit
        try:
            from .finnhub_feeds import get_rate_limit_status
            finnhub = get_rate_limit_status()
            if finnhub:
                remaining = finnhub.get("remaining", "?")
                emoji = "🟢" if remaining == "?" or int(remaining) > 10 else "🟡"
                lines.append(f"{emoji} Finnhub: {remaining} remaining")
        except Exception:
            pass

        return "\n".join(lines) if lines else "—"
    except Exception:
        return "—"
```

### Note

This feature requires the API modules to expose rate limit tracking. If not already implemented, this could be a larger effort.

---

### Feature 4: Memory/CPU Usage

Show system resource consumption.

### Add Function

```python
def _get_system_resources() -> str:
    """
    Get system resource usage.

    Returns:
        Formatted string with memory and CPU usage
    """
    try:
        import os

        lines = []

        # Memory usage via /proc/self/status (Linux)
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # Resident memory in KB
                        kb = int(line.split()[1])
                        mb = kb / 1024
                        emoji = "🟢" if mb < 500 else "🟡" if mb < 1000 else "🔴"
                        lines.append(f"{emoji} Memory: {mb:.0f} MB")
                        break
        except Exception:
            # Fallback: try psutil if available
            try:
                import psutil
                process = psutil.Process(os.getpid())
                mb = process.memory_info().rss / (1024 * 1024)
                emoji = "🟢" if mb < 500 else "🟡" if mb < 1000 else "🔴"
                lines.append(f"{emoji} Memory: {mb:.0f} MB")
            except Exception:
                pass

        # CPU usage (requires psutil or /proc sampling)
        try:
            import psutil
            cpu_pct = psutil.Process(os.getpid()).cpu_percent(interval=0.1)
            emoji = "🟢" if cpu_pct < 50 else "🟡" if cpu_pct < 80 else "🔴"
            lines.append(f"{emoji} CPU: {cpu_pct:.0f}%")
        except Exception:
            pass

        return "\n".join(lines) if lines else "—"
    except Exception:
        return "—"
```

### Add to Heartbeat

```python
{
    "name": "💻 Resources",
    "value": _get_system_resources(),
    "inline": True,
}
```

---

### Feature 5: Last Error Detail

Show the most recent error with timestamp.

### Add Function

```python
def _get_last_error_detail() -> str:
    """
    Get details of the most recent error.

    Returns:
        Formatted string with last error info
    """
    try:
        global ERROR_TRACKER

        if not ERROR_TRACKER:
            return "No recent errors"

        # Get last error
        last = ERROR_TRACKER[-1]
        timestamp = last.get("timestamp", "")
        level = last.get("level", "error")
        category = last.get("category", "Unknown")
        message = last.get("message", "")[:80]

        # Format timestamp
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            time_str = "?"

        emoji = "🔴" if level == "error" else "🟡" if level == "warning" else "🟢"
        return f"{emoji} [{time_str}] {category}: {message}"
    except Exception:
        return "—"
```

### Add to Heartbeat (in Errors & Warnings section)

```python
# Update the error summary to include last error detail
error_summary = _get_error_summary()
last_error = _get_last_error_detail()

{
    "name": "⚠️ Errors & Warnings",
    "value": f"{error_summary}\n\n**Last:** {last_error}" if last_error != "No recent errors" else error_summary,
    "inline": False,
}
```

---

### Feature 6: Alert Win Rate (24h Preview)

Show quick feedback on alert quality.

### Add Function

```python
def _get_alert_win_rate_24h() -> str:
    """
    Get alert win rate for last 24 hours from feedback database.

    Returns:
        Formatted string with win rate and counts
    """
    try:
        from .feedback.outcome_tracker import get_24h_summary

        summary = get_24h_summary()
        if not summary:
            return "—"

        total = summary.get("total", 0)
        wins = summary.get("wins", 0)
        losses = summary.get("losses", 0)

        if total == 0:
            return "No alerts tracked"

        win_rate = (wins / total * 100) if total > 0 else 0
        emoji = "🟢" if win_rate >= 60 else "🟡" if win_rate >= 40 else "🔴"

        return f"{emoji} {win_rate:.0f}% ({wins}W/{losses}L of {total})"
    except Exception:
        return "—"
```

### Note

This requires the feedback module to expose a `get_24h_summary()` function. If not available, skip this feature or implement the query:

```python
# In feedback/outcome_tracker.py or similar:
def get_24h_summary() -> Dict[str, int]:
    """Get alert outcomes from last 24 hours."""
    try:
        from datetime import datetime, timedelta, timezone
        import sqlite3

        db_path = "data/feedback.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses
            FROM alert_performance
            WHERE posted_at > ?
        """, (cutoff,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {"total": row[0] or 0, "wins": row[1] or 0, "losses": row[2] or 0}
        return None
    except Exception:
        return None
```

---

### Feature 7: Dedup Efficiency Metric

Show what percentage of items are being deduplicated.

### Add to `_get_feed_activity_summary()`

```python
def _get_feed_activity_summary() -> Dict[str, Any]:
    """Get feed activity summary for heartbeat."""
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES, RSS_SOURCE_BY_NAME

        # ... existing code ...

        # Calculate dedup efficiency from TOTAL_STATS
        total_items = TOTAL_STATS.get("items", 0)
        total_deduped = TOTAL_STATS.get("deduped", 0)

        if total_items > 0:
            dedup_pct = ((total_items - total_deduped) / total_items * 100)
            dedup_display = f"{dedup_pct:.0f}% deduped"
        else:
            dedup_display = "—"

        return {
            # ... existing fields ...
            "dedup_efficiency": dedup_display,
        }
    except Exception:
        # ... existing fallback ...
```

---

## Complete New Heartbeat Layout

After all enhancements, the interval heartbeat would include:

```
🤖 Catalyst-Bot heartbeat (interval)

📊 Configuration Summary
├── Target: admin
├── Record Only: False
├── Min Score: 0.20
└── Providers: tiingo, av, yf

⏱️ Status
├── Uptime: 2d 5h
├── Memory: 450 MB 🟢
└── CPU: 12% 🟢

📰 Feed Activity (Last Hour)
├── RSS Feeds: 29 items (Finnhub: 28, Globenewswire: 1)
├── SEC Filings: 44 filings (8-K: 42, 424B5: 1, FWP: 1)
└── Twitter/Social: 0 posts

🔌 Feed Health
├── ✅ Globenewswire: 1 items
├── ✅ Sec 8K: 42 items
├── ✅ Finnhub: 28 items
└── 📋 Sec 13D: cached

🎯 Classification Summary
├── Total Classified: 45
├── Above MIN_SCORE: 2 (4.4%)
├── Below Threshold: 43 (95.6%)
├── Deduped: 45 (0% deduped)
└── Skipped: 45

💹 Trading Activity
├── Signals Generated: 2
├── Trades Executed: 1
├── Open Positions: 1
└── P&L (Today): +$12.50

🤖 LLM Usage (Last Hour)
├── Requests: 15 (Gemini: 12, Claude: 3)
├── Tokens In/Out: 8,500 / 2,100
├── Est. Cost (1hr): $0.08
└── Est. Cost (Today): $1.25

⚠️ Errors & Warnings
├── 📊 2 errors in last hour
├── 🟡 API: 2 warnings
│   └─ Price fetch failed for XYZ
└── Last: 🟡 [14:32:15] API: Rate limit warning

🕐 Market Status
├── Current: 🟢 Open
├── Next Event: Close in 2h 15m
└── Scan Cycle: 30 sec

📈 Alert Quality (24h)
└── 🟢 65% (13W/7L of 20)

📊 Period Summary
├── Last 60.8 minutes • 60 cycles
├── Feeds Scanned: 2,337
├── Alerts Posted: 2
└── Avg Alerts/Cycle: 0.03
```

---

## Implementation Priority

| Feature | Effort | Value | Priority |
|---------|--------|-------|----------|
| Uptime Counter | Low | High | 1 |
| Last Error Detail | Low | High | 2 |
| Memory/CPU Usage | Low | Medium | 3 |
| Hardcoded Cycle Fix | Low | Medium | 4 |
| Error Propagation Fix | Low | Medium | 5 |
| Dedup Efficiency | Low | Medium | 6 |
| Feed Health Matrix | Medium | High | 7 |
| Alert Win Rate | Medium | High | 8 |
| API Rate Limits | High | Medium | 9 |

---

## Complete Change List

| File | Lines | Change |
|------|-------|--------|
| `runner.py` | ~150-155 | Add clarifying comments |
| `runner.py` | ~625 | Fix hardcoded cycle time |
| `runner.py` | ~3451-3456 | Add actual error count to add_cycle() |
| `runner.py` | New | Add `_get_uptime_display()` |
| `runner.py` | New | Add `_get_system_resources()` |
| `runner.py` | New | Add `_get_last_error_detail()` |
| `runner.py` | New | Add `_get_feed_health_matrix()` |
| `runner.py` | ~640-665 | Add dedup efficiency to feed summary |
| `feeds.py` | New | Add `_LAST_FETCH_SUMMARY` and getter |
| `feedback/` | New | Add `get_24h_summary()` if not exists |

## Testing Checklist

- [ ] Uptime displays correctly (format: Xd Xh or Xh Xm)
- [ ] Memory usage displays (requires /proc or psutil)
- [ ] CPU usage displays (requires psutil)
- [ ] Last error detail shows timestamp and message
- [ ] Feed health matrix shows per-source status
- [ ] Dedup efficiency shows percentage
- [ ] Cycle time uses actual SCAN_INTERVAL
- [ ] No performance regression from new calculations

## Commit Message Template

```
feat(heartbeat): add admin visibility enhancements

- Add uptime counter display
- Add memory/CPU resource monitoring
- Add last error detail with timestamp
- Add dedup efficiency metric
- Fix hardcoded cycle time to use SCAN_INTERVAL
- Fix error count propagation in add_cycle()

Improves admin ability to monitor bot health at a glance

Audit: docs/heartbeat-audit/PATCH-04-enhancements.md
```

---

## Future Enhancements (Not in Scope)

These could be added in future iterations:

1. **Alert Latency Tracking**: Time from news publish to alert post
2. **Ticker Performance Heatmap**: Which tickers generate best alerts
3. **Model Performance Comparison**: Gemini vs Claude accuracy
4. **Webhook Health**: Discord webhook response times
5. **Database Size**: SQLite file sizes and row counts
6. **Cache Hit Rates**: ETag/304 response percentages
7. **Sentiment Distribution**: Histogram of sentiment scores
8. **Peak Hours Analysis**: When most alerts are generated

---

*This completes the heartbeat audit documentation. Return to [README](./README.md) for the full implementation guide.*
