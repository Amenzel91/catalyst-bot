# Admin Heartbeat Alert - Audit & Implementation Guide

> **Audit Date:** 2025-12-10
> **Branch:** `claude/audit-heartbeat-alert-01GKdg2FsTvnTxXZ45vTcc7s`
> **Status:** Implementation Ready

## Overview

This document serves as the master guide for fixing and enhancing the admin heartbeat alert feature in Catalyst-Bot. The audit identified 8 issues across 4 categories, organized into implementation patches for vibecoding sessions.

## Quick Reference

| Patch | Priority | Issues | Estimated Complexity |
|-------|----------|--------|---------------------|
| [PATCH-01: Critical Bugs](./PATCH-01-critical-bugs.md) | HIGH | MIN_SCORE bug, Trading counters, LLM bridge | Medium |
| [PATCH-02: Display Fixes](./PATCH-02-display-fixes.md) | MEDIUM | RSS source breakdown, Avg rounding | Easy |
| [PATCH-03: Error Monitoring](./PATCH-03-error-monitoring.md) | MEDIUM | Connect health_monitor to heartbeat | Medium |
| [PATCH-04: Enhancements](./PATCH-04-enhancements.md) | LOW | New features, general improvements | Variable |

## Issue Summary

### Critical Bugs (PATCH-01)

1. **MIN_SCORE Score Extraction Bug** - `runner.py:1683`
   - `_score_of()` function missing `source_weight` field check
   - Items pass MIN_SCORE via bypass but show 0 in stats
   - **Impact:** Misleading classification statistics

2. **Trading Activity Counters Not Wired** - `runner.py:160-163`, `alerts.py:1464-1474`
   - `TRADING_ACTIVITY_STATS` initialized but never incremented
   - Shows 0 for signals/trades even when trading occurs
   - **Impact:** No visibility into trading activity

3. **LLM Monitor Architecture Disconnect** - `runner.py:477-522`
   - Two separate monitors: `LLMUsageMonitor` (JSONL) and `LLMMonitor` (in-memory)
   - Heartbeat reads from wrong monitor
   - **Impact:** LLM usage always shows zeros

### Display Fixes (PATCH-02)

4. **RSS Feed Source Breakdown Missing** - `runner.py:738-769`
   - Shows aggregate "RSS Feeds: N items" without source breakdown
   - Data exists in `feeds.py` but not exposed
   - **Impact:** No visibility into individual feed health

5. **Average Alerts/Cycle Rounding Issue** - `runner.py:276-278`
   - `round(..., 1)` causes values < 0.05 to show as 0.0
   - 2 alerts / 60 cycles = 0.033 → displays as "0.0"
   - **Impact:** Misleading metric during low-alert periods

### Error Monitoring (PATCH-03)

6. **Error Tracking Not Connected** - `runner.py:772-799`
   - `_track_error()` function exists but rarely called
   - `health_monitor.py` tracks errors separately
   - **Impact:** "No errors or warnings" even when errors occur

### Enhancements (PATCH-04)

7. **General Code Cleanup**
   - Duplicate stat tracking (LAST_CYCLE_STATS vs HeartbeatAccumulator)
   - Hardcoded values that should use config
   - Missing error propagation in `add_cycle()`

8. **New Features to Add**
   - Feed health matrix with per-source status
   - API rate limit status display
   - Memory/CPU usage tracking
   - Uptime counter and last error detail

## File Map

### Primary Files

| File | Purpose | Lines Modified |
|------|---------|----------------|
| `src/catalyst_bot/runner.py` | Main heartbeat logic | ~15 locations |
| `src/catalyst_bot/alerts.py` | Trading execution trigger | 2 locations |
| `src/catalyst_bot/services/llm_service.py` | LLM request tracking | 1 location |
| `src/catalyst_bot/health_monitor.py` | Error tracking source | 0 (read only) |

### Supporting Files

| File | Purpose |
|------|---------|
| `src/catalyst_bot/llm_usage_monitor.py` | Legacy LLM monitor |
| `src/catalyst_bot/services/llm_monitor.py` | Modern LLM monitor |
| `src/catalyst_bot/classify.py` | Score calculation reference |
| `src/catalyst_bot/feeds.py` | Feed source data |

## Implementation Order

### Recommended Session Flow

```
Session 1: PATCH-01 (Critical Bugs)
├── Fix _score_of() in runner.py
├── Wire TRADING_ACTIVITY_STATS in alerts.py
└── Bridge LLM monitors in llm_service.py

Session 2: PATCH-02 (Display Fixes)
├── Add RSS_SOURCE_BY_NAME tracking
├── Update heartbeat display for RSS breakdown
└── Fix avg_alerts_per_cycle precision

Session 3: PATCH-03 (Error Monitoring)
├── Connect _track_error() to exception handlers
├── Integrate health_monitor metrics
└── Add error summary to heartbeat

Session 4: PATCH-04 (Enhancements)
├── Add uptime counter
├── Add feed health matrix
├── Add API rate limit display
└── Clean up duplicate tracking
```

## Testing Strategy

### Manual Testing

After each patch, verify by:
1. Starting the bot with `FEATURE_HEARTBEAT=1`
2. Waiting for interval heartbeat (or trigger manually)
3. Checking Discord admin channel for correct values
4. Comparing heartbeat values against log output

### Automated Testing

```bash
# Run existing heartbeat tests
pytest test_enhanced_heartbeat.py -v

# Run specific module tests
pytest tests/test_runner.py -v -k heartbeat
```

## Rollback Plan

Each patch is self-contained. If issues arise:

1. **Revert specific patch:**
   ```bash
   git revert <commit-hash>
   ```

2. **Return to baseline:**
   ```bash
   git checkout main -- src/catalyst_bot/runner.py
   git checkout main -- src/catalyst_bot/alerts.py
   ```

## Success Criteria

After all patches:

| Metric | Before | After |
|--------|--------|-------|
| RSS Feeds | "1 items" | "globenewswire: 1, finnhub: 28" |
| Above MIN_SCORE | 0 (0.0%) | 2 (4.4%) |
| Signals Generated | 0 | Actual count |
| LLM Requests | 0 | Actual count |
| Errors & Warnings | "No errors" | Actual errors |
| Avg Alerts/Cycle | 0.0 | 0.03 |

## Next Steps

1. Start with [PATCH-01: Critical Bugs](./PATCH-01-critical-bugs.md)
2. Test after each patch before proceeding
3. Commit with descriptive messages referencing this audit
4. Push to feature branch for review

---

*Generated by Claude Code audit session*
