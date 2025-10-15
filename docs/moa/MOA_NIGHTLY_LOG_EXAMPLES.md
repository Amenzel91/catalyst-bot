# MOA Nightly Scheduler - Example Log Output

This document shows real-world example log output for different scenarios.

## Successful Execution

### Full Run Example

```json
{"timestamp": "2025-10-13T02:00:15.234Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_scheduled", "hour": 2, "date": "2025-10-13"}
{"timestamp": "2025-10-13T02:00:15.245Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_thread_started"}
{"timestamp": "2025-10-13T02:00:15.246Z", "level": "INFO", "logger": "runner", "message": "CYCLE_DONE", "took": 1.23}
{"timestamp": "2025-10-13T02:00:16.001Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_start"}
{"timestamp": "2025-10-13T02:00:16.123Z", "level": "INFO", "logger": "moa_historical", "message": "moa_historical_analysis_start"}
{"timestamp": "2025-10-13T02:00:16.456Z", "level": "INFO", "logger": "moa_historical", "message": "loaded_outcomes", "count": 523}
{"timestamp": "2025-10-13T02:00:16.678Z", "level": "INFO", "logger": "moa_historical", "message": "loaded_rejected_items", "count": 523}
{"timestamp": "2025-10-13T02:00:16.891Z", "level": "INFO", "logger": "moa_historical", "message": "merged_data", "total": 523, "with_keywords": 487}
{"timestamp": "2025-10-13T02:00:17.234Z", "level": "INFO", "logger": "moa_historical", "message": "identified_missed_opportunities", "total": 523, "missed": 147, "rate": 28.1}
{"timestamp": "2025-10-13T02:00:17.567Z", "level": "INFO", "logger": "moa_historical", "message": "extracted_keywords", "total_unique": 78, "significant": 34, "min_occurrences": 3}
{"timestamp": "2025-10-13T02:00:17.890Z", "level": "INFO", "logger": "moa_historical", "message": "analyzed_rejection_reasons", "count": 5}
{"timestamp": "2025-10-13T02:00:18.123Z", "level": "INFO", "logger": "moa_historical", "message": "generated_recommendations", "count": 23}
{"timestamp": "2025-10-13T02:00:18.456Z", "level": "INFO", "logger": "moa_historical", "message": "saved_analysis_report", "path": "C:\\Users\\...\\data\\moa\\analysis_report.json"}
{"timestamp": "2025-10-13T02:00:18.789Z", "level": "INFO", "logger": "moa_historical", "message": "moa_historical_analysis_complete", "elapsed": 2.67, "outcomes": 523, "missed": 147, "keywords": 34, "recommendations": 23, "flash_catalysts": 42, "sectors_analyzed": 11}
{"timestamp": "2025-10-13T02:00:18.890Z", "level": "INFO", "logger": "runner", "message": "moa_analysis_complete", "outcomes": 523, "missed": 147, "recommendations": 23}
{"timestamp": "2025-10-13T02:00:19.012Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "false_positive_analysis_start"}
{"timestamp": "2025-10-13T02:00:19.234Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "loaded_outcomes", "count": 89}
{"timestamp": "2025-10-13T02:00:19.456Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "analyzed_keywords", "total_unique": 45, "significant": 23, "min_occurrences": 3}
{"timestamp": "2025-10-13T02:00:19.567Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "analyzed_sources", "count": 8}
{"timestamp": "2025-10-13T02:00:19.678Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "analyzed_score_correlation", "buckets": 4}
{"timestamp": "2025-10-13T02:00:19.789Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "analyzed_time_patterns", "buckets": 5}
{"timestamp": "2025-10-13T02:00:19.890Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "generated_penalties", "count": 12}
{"timestamp": "2025-10-13T02:00:20.123Z", "level": "INFO", "logger": "false_positive_analyzer", "message": "false_positive_analysis_complete", "outcomes": 89, "precision": 0.618, "false_positive_rate": 0.382, "penalties": 12, "elapsed": 1.1}
{"timestamp": "2025-10-13T02:00:20.234Z", "level": "INFO", "logger": "runner", "message": "false_positive_analysis_complete", "accepts": 89, "failures": 34, "penalties": 12}
{"timestamp": "2025-10-13T02:00:20.345Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_complete"}
{"timestamp": "2025-10-13T02:01:20.456Z", "level": "INFO", "logger": "runner", "message": "CYCLE_DONE", "took": 1.45}
```

**Timeline:**
- 02:00:15 - Scheduler triggers, spawns thread
- 02:00:15 - Main loop continues immediately (CYCLE_DONE)
- 02:00:16 - Background thread starts MOA analysis
- 02:00:18 - MOA analysis completes (2.67 seconds)
- 02:00:19 - False positive analysis starts
- 02:00:20 - False positive analysis completes (1.1 seconds)
- 02:00:20 - Full nightly run complete (total ~5 seconds)
- 02:01:20 - Main loop continues normally

## Edge Cases

### No Data Available (First Run)

```json
{"timestamp": "2025-10-13T02:00:15.234Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_scheduled", "hour": 2, "date": "2025-10-13"}
{"timestamp": "2025-10-13T02:00:15.245Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_thread_started"}
{"timestamp": "2025-10-13T02:00:16.001Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_start"}
{"timestamp": "2025-10-13T02:00:16.123Z", "level": "WARNING", "logger": "moa_historical", "message": "outcomes_not_found", "path": "C:\\Users\\...\\data\\moa\\outcomes.jsonl"}
{"timestamp": "2025-10-13T02:00:16.234Z", "level": "INFO", "logger": "moa_historical", "message": "loaded_outcomes", "count": 0}
{"timestamp": "2025-10-13T02:00:16.345Z", "level": "WARNING", "logger": "runner", "message": "moa_analysis_failed", "status": "no_data", "msg": "No outcomes found in data/moa/outcomes.jsonl"}
{"timestamp": "2025-10-13T02:00:16.456Z", "level": "WARNING", "logger": "false_positive_analyzer", "message": "outcomes_not_found", "path": "C:\\Users\\...\\data\\false_positives\\outcomes.jsonl"}
{"timestamp": "2025-10-13T02:00:16.567Z", "level": "WARNING", "logger": "runner", "message": "false_positive_analysis_failed", "status": "no_data", "msg": "No outcomes found in data/false_positives/outcomes.jsonl"}
{"timestamp": "2025-10-13T02:00:16.678Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_complete"}
```

**Note:** This is normal for first-time runs. The bot needs to accumulate outcome data over time.

### No Missed Opportunities Found

```json
{"timestamp": "2025-10-13T02:00:16.123Z", "level": "INFO", "logger": "moa_historical", "message": "loaded_outcomes", "count": 152}
{"timestamp": "2025-10-13T02:00:16.234Z", "level": "INFO", "logger": "moa_historical", "message": "identified_missed_opportunities", "total": 152, "missed": 0, "rate": 0.0}
{"timestamp": "2025-10-13T02:00:16.345Z", "level": "WARNING", "logger": "moa_historical", "message": "no_missed_opportunities"}
{"timestamp": "2025-10-13T02:00:16.456Z", "level": "WARNING", "logger": "runner", "message": "moa_analysis_failed", "status": "no_opportunities", "msg": "No missed opportunities identified (none with >10% return)"}
```

**Note:** This means your filters are working well - all rejected items stayed low. No keyword weight changes needed.

### Duplicate Run Prevention

```json
{"timestamp": "2025-10-13T02:00:15.234Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_scheduled", "hour": 2, "date": "2025-10-13"}
{"timestamp": "2025-10-13T02:00:15.245Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_thread_started"}
...
{"timestamp": "2025-10-13T02:00:20.345Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_complete"}

// Later in the same hour (bot still running)
{"timestamp": "2025-10-13T02:05:00.123Z", "level": "INFO", "logger": "runner", "message": "CYCLE_DONE", "took": 1.23}
// No moa_nightly_scheduled log - already ran today
```

**Note:** Deduplication working correctly. Won't run again until tomorrow.

## Error Scenarios

### Analysis Import Error

```json
{"timestamp": "2025-10-13T02:00:15.234Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_scheduled", "hour": 2, "date": "2025-10-13"}
{"timestamp": "2025-10-13T02:00:15.245Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_thread_started"}
{"timestamp": "2025-10-13T02:00:16.001Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_start"}
{"timestamp": "2025-10-13T02:00:16.123Z", "level": "ERROR", "logger": "runner", "message": "moa_analysis_error", "err": "ImportError", "traceback": "..."}
{"timestamp": "2025-10-13T02:00:16.234Z", "level": "ERROR", "logger": "runner", "message": "false_positive_analysis_error", "err": "ImportError", "traceback": "..."}
{"timestamp": "2025-10-13T02:00:16.345Z", "level": "INFO", "logger": "runner", "message": "moa_nightly_complete"}
```

**Action:** Check that analyzer modules are installed and accessible.

### File Permission Error

```json
{"timestamp": "2025-10-13T02:00:18.456Z", "level": "ERROR", "logger": "moa_historical", "message": "save_analysis_report_failed", "err": "PermissionError"}
{"timestamp": "2025-10-13T02:00:18.567Z", "level": "ERROR", "logger": "runner", "message": "moa_analysis_error", "err": "PermissionError", "traceback": "..."}
```

**Action:** Check file permissions on `data/moa/` and `data/false_positives/` directories.

### JSON Decode Error (Corrupted Data)

```json
{"timestamp": "2025-10-13T02:00:16.456Z", "level": "DEBUG", "logger": "moa_historical", "message": "invalid_json", "line": 45, "err": "JSONDecodeError"}
{"timestamp": "2025-10-13T02:00:16.567Z", "level": "INFO", "logger": "moa_historical", "message": "loaded_outcomes", "count": 522}
```

**Note:** Individual corrupted lines are skipped. Analysis continues with valid data.

## Disabled Scheduler

```json
// No moa_nightly_scheduled logs appear at 2 AM
{"timestamp": "2025-10-13T02:00:15.234Z", "level": "INFO", "logger": "runner", "message": "CYCLE_DONE", "took": 1.23}
{"timestamp": "2025-10-13T02:01:20.456Z", "level": "INFO", "logger": "runner", "message": "CYCLE_DONE", "took": 1.34}
```

**Note:** If `MOA_NIGHTLY_ENABLED=0`, no logs will appear. This is normal.

## Log Analysis Commands

### Check if Scheduler Ran Today

```bash
# Linux/Mac
grep -E "moa_nightly_scheduled|moa_nightly_complete" data/logs/bot.jsonl | grep "2025-10-13"

# Windows PowerShell
Select-String -Pattern "moa_nightly_scheduled|moa_nightly_complete" -Path data\logs\bot.jsonl | Select-String -Pattern "2025-10-13"
```

### Count Total Missed Opportunities Over Time

```bash
# Linux/Mac
grep "identified_missed_opportunities" data/logs/bot.jsonl | grep -oP '"missed":\s*\K\d+' | awk '{sum+=$1} END {print sum}'

# Windows PowerShell
(Select-String -Pattern "identified_missed_opportunities" -Path data\logs\bot.jsonl | ForEach-Object { if ($_ -match '"missed":\s*(\d+)') { [int]$matches[1] } } | Measure-Object -Sum).Sum
```

### Extract Last Run Summary

```bash
# Linux/Mac
grep "moa_analysis_complete" data/logs/bot.jsonl | tail -1 | jq '{outcomes, missed, recommendations}'

# Windows PowerShell
(Select-String -Pattern "moa_analysis_complete" -Path data\logs\bot.jsonl)[-1].Line | ConvertFrom-Json | Select-Object outcomes, missed, recommendations
```

### Check for Errors

```bash
# Linux/Mac
grep -E "moa_.*_error|false_positive.*_error" data/logs/bot.jsonl

# Windows PowerShell
Select-String -Pattern "moa_.*_error|false_positive.*_error" -Path data\logs\bot.jsonl
```

## Performance Metrics

### Typical Execution Times

| Component | Duration | Notes |
|-----------|----------|-------|
| Scheduler check | <1ms | Negligible impact on main loop |
| Thread spawn | <10ms | Main loop continues immediately |
| MOA analysis | 2-5s | Depends on outcome dataset size |
| FP analysis | 1-2s | Depends on accepted alert dataset size |
| Total background time | 3-7s | Does not block feed processing |

### Resource Usage

| Resource | Usage | Notes |
|----------|-------|-------|
| CPU | <5% during analysis | Spikes briefly, returns to baseline |
| Memory | +10-20MB during analysis | Released after completion |
| Disk I/O | Minimal | Only reads outcomes, writes JSON reports |
| Network | None | All local file operations |

## Monitoring Dashboard Queries

If you have log aggregation (Elasticsearch, Splunk, etc.), use these queries:

### MOA Run Success Rate (Last 7 Days)

```
logger:"runner" AND message:"moa_nightly_complete" AND timestamp:[now-7d TO now]
```

### Average Missed Opportunity Rate

```
logger:"moa_historical" AND message:"identified_missed_opportunities"
| stats avg(rate) as avg_miss_rate
```

### False Positive Precision Trend

```
logger:"false_positive_analyzer" AND message:"false_positive_analysis_complete"
| timechart avg(precision) span=1d
```

### Analysis Errors (Last 24 Hours)

```
logger:("runner" OR "moa_historical" OR "false_positive_analyzer")
AND (level:"ERROR" OR level:"WARNING")
AND timestamp:[now-24h TO now]
```

---

**Document Version:** 1.0
**Last Updated:** 2025-10-13
**Related Files:**
- `MOA_NIGHTLY_SCHEDULER_IMPLEMENTATION.md` (technical details)
- `MOA_NIGHTLY_USAGE_GUIDE.md` (user guide)
