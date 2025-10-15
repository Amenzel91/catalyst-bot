# MOA Nightly Scheduler - Quick Usage Guide

## What Is This?

The MOA Nightly Scheduler automatically runs two analysis jobs every night at 2 AM UTC:

1. **MOA Historical Analyzer** - Identifies rejected catalysts that became profitable
2. **False Positive Analyzer** - Identifies accepted alerts that failed

Both analyzers generate keyword weight recommendations that can be used to improve the bot's classification accuracy.

## Quick Start

### Default Behavior (Enabled)

The scheduler is **enabled by default** and runs at **2 AM UTC** every night.

No configuration needed - just run your bot normally:

```bash
python -m catalyst_bot.runner --loop
```

### Disable the Scheduler

To disable nightly MOA runs, add to your `.env` file:

```bash
MOA_NIGHTLY_ENABLED=0
```

### Change Run Time

To change the run time (e.g., to 3 AM UTC), add to your `.env` file:

```bash
MOA_NIGHTLY_HOUR=3
```

**Note:** Use 24-hour format in UTC. Examples:
- `MOA_NIGHTLY_HOUR=0` = Midnight UTC
- `MOA_NIGHTLY_HOUR=14` = 2 PM UTC
- `MOA_NIGHTLY_HOUR=22` = 10 PM UTC

## Monitoring

### Check if Scheduler Triggered

Look for these log entries in `data/logs/bot.jsonl`:

```bash
# Scheduler triggered
grep "moa_nightly_scheduled" data/logs/bot.jsonl

# Analysis started
grep "moa_nightly_start" data/logs/bot.jsonl

# MOA analysis completed
grep "moa_analysis_complete" data/logs/bot.jsonl

# False positive analysis completed
grep "false_positive_analysis_complete" data/logs/bot.jsonl

# Full run completed
grep "moa_nightly_complete" data/logs/bot.jsonl
```

### Check Analysis Reports

After a successful run, two JSON reports are generated:

**1. MOA Analysis Report:**
```
data/moa/analysis_report.json
```

**2. False Positive Analysis Report:**
```
data/false_positives/analysis_report.json
```

## Manual Testing

To test the scheduler without waiting for 2 AM UTC:

```bash
# Set hour to current hour (check your UTC time first)
MOA_NIGHTLY_HOUR=15  # If it's currently 3 PM UTC

# Run bot
python -m catalyst_bot.runner --loop
```

The scheduler will trigger on the first cycle when the hour matches.

## Understanding the Output

### Example Successful Run Logs

```
INFO  runner moa_nightly_scheduled hour=2 date=2025-10-13
INFO  runner moa_nightly_thread_started
INFO  runner moa_nightly_start
INFO  runner moa_analysis_complete outcomes=523 missed=147 recommendations=23
INFO  runner false_positive_analysis_complete accepts=89 failures=34 penalties=12
INFO  runner moa_nightly_complete
```

**Key Metrics:**
- `outcomes=523` - Total rejected items analyzed
- `missed=147` - Rejected items that became profitable (missed opportunities)
- `recommendations=23` - Keyword weight increase recommendations
- `accepts=89` - Total accepted alerts analyzed
- `failures=34` - Accepted alerts that failed
- `penalties=12` - Keyword weight decrease recommendations

### Common Warnings (Not Errors)

```
WARNING runner moa_analysis_failed status=no_data msg=No outcomes found
```
This is normal if you haven't accumulated outcome data yet. The scheduler will try again tomorrow.

## FAQ

### Q: Will this slow down my bot?
**A:** No. The analysis runs in a background thread and does not block feed processing. Your main alert loop continues immediately.

### Q: How long does the analysis take?
**A:** Typically 5-10 seconds depending on dataset size. This happens in the background while your bot continues processing feeds.

### Q: Can I run it more than once per day?
**A:** Currently no - the scheduler has built-in deduplication to run once per UTC day. To run multiple times, you would need to manually execute the analyzers:

```bash
# Manual MOA run
python -m catalyst_bot.moa_historical_analyzer

# Manual false positive run
python -m catalyst_bot.false_positive_analyzer
```

### Q: What if the analysis fails?
**A:** The scheduler has graceful error handling. If the analysis fails, it logs a warning but doesn't crash the bot. Your feed processing continues normally and the scheduler will retry tomorrow.

### Q: Where do the keyword recommendations go?
**A:** Recommendations are saved to JSON report files but not automatically applied. You can review the recommendations in:
- `data/moa/analysis_report.json` (boost recommendations)
- `data/false_positives/analysis_report.json` (penalty recommendations)

Future enhancement: Auto-apply recommendations with approval workflow.

### Q: Can I disable just one analyzer?
**A:** Currently no - the `MOA_NIGHTLY_ENABLED` flag controls both. To run only one, you would need to manually execute:

```bash
# Run only MOA
python -m catalyst_bot.moa_historical_analyzer

# Run only FP analyzer
python -m catalyst_bot.false_positive_analyzer
```

## Troubleshooting

### Scheduler Not Running

**Check 1: Is it enabled?**
```bash
# Look in .env or environment variables
echo $MOA_NIGHTLY_ENABLED
# Should be 1, true, yes, or on (or not set, defaults to enabled)
```

**Check 2: Is it the right hour?**
```bash
# Check current UTC time
python -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc))"
```

**Check 3: Did it already run today?**
The scheduler only runs once per UTC day. If you restart the bot on the same day, it won't run again until tomorrow.

### Analysis Failed

**Check 1: Do outcome files exist?**
```bash
# MOA needs this file
ls data/moa/outcomes.jsonl

# False positive analyzer needs this file
ls data/false_positives/outcomes.jsonl
```

**Check 2: Check error logs**
```bash
grep "moa_analysis_error\|false_positive_analysis_error" data/logs/bot.jsonl
```

## Configuration Reference

| Variable | Default | Valid Values | Description |
|----------|---------|--------------|-------------|
| `MOA_NIGHTLY_ENABLED` | `1` | `0`, `1`, `true`, `false`, `yes`, `no`, `on`, `off` | Enable/disable scheduler |
| `MOA_NIGHTLY_HOUR` | `2` | `0` - `23` | Hour (UTC) to run analysis |

## Related Files

- **Implementation:** `src/catalyst_bot/runner.py` (lines 1610-1732)
- **Config:** `src/catalyst_bot/config.py` (lines 840-851)
- **MOA Analyzer:** `src/catalyst_bot/moa_historical_analyzer.py`
- **FP Analyzer:** `src/catalyst_bot/false_positive_analyzer.py`
- **Full Details:** `MOA_NIGHTLY_SCHEDULER_IMPLEMENTATION.md`

## Support

For detailed technical information, see `MOA_NIGHTLY_SCHEDULER_IMPLEMENTATION.md`.

For MOA analysis methodology, see `MOA_COMPLETE_ROADMAP.md` or `MOA_README.md`.
