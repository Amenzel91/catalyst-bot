# MOA Nightly Scheduler Implementation Summary

## Overview
Implemented automatic nightly execution of MOA (Missed Opportunities Analyzer) and False Positive Analyzer at 2 AM UTC to analyze the previous day's catalyst outcomes.

## Changes Made

### 1. Runner.py Modifications

**File:** `src/catalyst_bot/runner.py`

#### Import Updates (Line 61)
- Added `date` to datetime imports for tracking last run date

```python
from datetime import datetime, timezone, date
```

#### Global State Variable (Line 129)
- Added `_MOA_LAST_RUN_DATE` to prevent duplicate runs within same day

```python
# MOA Nightly Scheduler: Track last run date to prevent duplicate runs
_MOA_LAST_RUN_DATE: date | None = None
```

#### New Function: `_run_moa_nightly_if_scheduled()` (Lines 1610-1732)

**Purpose:** Orchestrates nightly MOA and False Positive analysis runs

**Key Features:**
- Checks feature flag `MOA_NIGHTLY_ENABLED` (default: enabled)
- Configurable run hour via `MOA_NIGHTLY_HOUR` (default: 2 AM UTC)
- Prevents duplicate runs by tracking last run date
- Runs asynchronously in background daemon thread
- Does NOT block main feed processing loop
- Comprehensive error handling with graceful degradation

**Execution Flow:**
1. Check if MOA_NIGHTLY_ENABLED is true
2. Check if current hour matches MOA_NIGHTLY_HOUR
3. Check if already run today (dedupe protection)
4. Mark today as run
5. Spawn background thread to run:
   - MOA Historical Analyzer (`run_historical_moa_analysis()`)
   - False Positive Analyzer (`run_false_positive_analysis()`)
6. Log all steps with structured logging

#### Integration Point (Line 1507)
- Added scheduler check in main event loop after weekly reports
- Positioned alongside other nightly tasks (admin reports, weekly reports)
- Wrapped in try/except for fault tolerance

```python
# Check if it's time to run MOA nightly analysis
try:
    _run_moa_nightly_if_scheduled(log, get_settings())
except Exception as e:
    log.warning("moa_nightly_check_failed err=%s", str(e))
```

### 2. Config.py Additions

**File:** `src/catalyst_bot/config.py`

#### New Configuration Variables (Lines 840-851)

```python
# --- MOA (Missed Opportunities Analyzer) Nightly Scheduler ---
# Enable nightly MOA analysis. When enabled, the bot will automatically run
# the MOA historical analyzer and false positive analyzer at the configured
# hour (default 2 AM UTC). This analyzes rejected catalysts that became
# profitable and generates keyword weight recommendations. Runs in a
# background thread to avoid blocking the main feed processing loop.
# Set MOA_NIGHTLY_ENABLED=0 to disable. Defaults to enabled.
moa_nightly_enabled: bool = _b("MOA_NIGHTLY_ENABLED", True)

# Hour (UTC) to run nightly MOA analysis. Defaults to 2 AM UTC.
# Use MOA_NIGHTLY_HOUR=3 to run at 3 AM UTC instead.
moa_nightly_hour: int = int(os.getenv("MOA_NIGHTLY_HOUR", "2") or "2")
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOA_NIGHTLY_ENABLED` | `1` (enabled) | Master switch for nightly MOA analysis |
| `MOA_NIGHTLY_HOUR` | `2` | Hour (UTC) to run analysis (0-23) |

### Enable/Disable Examples

**Disable MOA nightly scheduler:**
```bash
MOA_NIGHTLY_ENABLED=0
```

**Change run time to 3 AM UTC:**
```bash
MOA_NIGHTLY_HOUR=3
```

**Change run time to 10 PM UTC:**
```bash
MOA_NIGHTLY_HOUR=22
```

## Logging Output

### Successful Run Example

```
INFO  runner moa_nightly_scheduled hour=2 date=2025-10-13
INFO  runner moa_nightly_thread_started
INFO  runner moa_nightly_start
INFO  runner moa_analysis_complete outcomes=523 missed=147 recommendations=23
INFO  runner false_positive_analysis_complete accepts=89 failures=34 penalties=12
INFO  runner moa_nightly_complete
```

### Error Handling Example

```
WARNING runner moa_nightly_check_failed err=ImportError
ERROR   runner moa_analysis_error err=FileNotFoundError
WARNING runner moa_analysis_failed status=no_data msg=No outcomes found
```

## Technical Details

### Deduplication Strategy
- Uses global `_MOA_LAST_RUN_DATE` variable to track last execution date
- Prevents multiple runs within same UTC day even if loop cycles multiple times at 2 AM
- State persists throughout bot session but resets on restart (intentional)

### Async Execution
- Runs in background daemon thread named "MOA-Nightly"
- Main feed processing loop continues immediately after spawning thread
- Thread completes independently without blocking alerts
- Daemon flag ensures thread doesn't prevent shutdown

### Error Isolation
- Three levels of error handling:
  1. Outer wrapper catches scheduler check failures
  2. Inner thread catches overall execution failures
  3. Individual analyzers have their own try/except blocks
- Any failure logs warning but doesn't crash main loop
- Graceful degradation ensures feed processing continues

### Performance Impact
- **Main loop impact:** Near zero (only checks hour + date once per cycle)
- **Background thread:** Runs for ~5-10 seconds depending on dataset size
- **Memory overhead:** Minimal (thread stack + analyzer temporary data)
- **No blocking:** Feed processing continues immediately

## Integration with Existing Components

### MOA Historical Analyzer Integration
- Calls `run_historical_moa_analysis()` from `moa_historical_analyzer.py`
- Reads outcomes from `data/moa/outcomes.jsonl`
- Generates keyword weight recommendations
- Saves report to `data/moa/analysis_report.json`

### False Positive Analyzer Integration
- Calls `run_false_positive_analysis()` from `false_positive_analyzer.py`
- Reads accepted outcomes from `data/false_positives/outcomes.jsonl`
- Generates keyword penalty recommendations
- Saves report to `data/false_positives/analysis_report.json`

## Verification

### Check if Scheduler is Active

1. **Look for initialization log:**
   ```bash
   grep "moa_nightly_scheduled" data/logs/bot.jsonl
   ```

2. **Verify thread started:**
   ```bash
   grep "moa_nightly_thread_started" data/logs/bot.jsonl
   ```

3. **Check for completion:**
   ```bash
   grep "moa_nightly_complete" data/logs/bot.jsonl
   ```

### Manual Test

To trigger manually for testing:
```bash
# Set hour to current hour (e.g., if it's 15:00 UTC, set MOA_NIGHTLY_HOUR=15)
MOA_NIGHTLY_HOUR=15 python -m catalyst_bot.runner --loop
```

## Files Modified

1. **src/catalyst_bot/runner.py**
   - Line 61: Import additions
   - Line 129: Global state variable
   - Lines 1507-1510: Integration point in main loop
   - Lines 1610-1732: New scheduler function

2. **src/catalyst_bot/config.py**
   - Lines 840-851: Configuration variables

## Confirmation Checklist

✅ **Scheduler won't block main feed processing**
- Runs in background daemon thread
- Main loop continues immediately after thread spawn
- No synchronous waits or blocking calls

✅ **Configuration variables added to config.py**
- `moa_nightly_enabled` (default: True)
- `moa_nightly_hour` (default: 2)
- Both accessible via environment variables

✅ **Deduplication prevents multiple runs**
- Tracks last run date globally
- Only runs once per UTC day
- Safe even if loop cycles multiple times at trigger hour

✅ **Error handling with graceful degradation**
- Three-layer error isolation
- Logs warnings but doesn't crash
- Main feed processing continues on any failure

✅ **Comprehensive logging**
- Structured logs for all events
- Includes scheduler trigger, thread start, analysis results, completion
- Easy to grep/filter for monitoring

## Example Log Flow

```
# At 2:00 AM UTC
[2025-10-13T02:00:15Z] INFO  runner moa_nightly_scheduled hour=2 date=2025-10-13
[2025-10-13T02:00:15Z] INFO  runner moa_nightly_thread_started
[2025-10-13T02:00:15Z] INFO  runner CYCLE_DONE took=1.23s    # Main loop continues immediately

# Background thread runs
[2025-10-13T02:00:16Z] INFO  runner moa_nightly_start
[2025-10-13T02:00:18Z] INFO  moa_historical loaded_outcomes count=523
[2025-10-13T02:00:19Z] INFO  moa_historical identified_missed_opportunities total=523 missed=147 rate=28.1%
[2025-10-13T02:00:20Z] INFO  runner moa_analysis_complete outcomes=523 missed=147 recommendations=23
[2025-10-13T02:00:21Z] INFO  false_positive_analyzer loaded_outcomes count=89
[2025-10-13T02:00:21Z] INFO  runner false_positive_analysis_complete accepts=89 failures=34 penalties=12
[2025-10-13T02:00:21Z] INFO  runner moa_nightly_complete

# Main loop continues processing feeds
[2025-10-13T02:01:20Z] INFO  runner CYCLE_DONE took=1.45s
[2025-10-13T02:02:25Z] INFO  runner CYCLE_DONE took=1.31s
```

## Future Enhancements (Not Implemented)

Potential future improvements:
1. Add Discord notification with summary embed when analysis completes
2. Persist last run date to file for cross-session deduplication
3. Add configurable minute offset (e.g., run at 2:30 AM instead of 2:00 AM)
4. Add retry logic if analysis fails
5. Add health check endpoint to report last MOA run status

---

**Implementation Date:** 2025-10-13
**Implementation Type:** Full implementation (not design/planning)
**Testing Status:** Ready for testing
**Breaking Changes:** None
