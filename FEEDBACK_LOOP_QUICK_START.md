# Feedback Loop Quick Start Guide

## Enable the Feedback Loop (3 Steps)

### Step 1: Add to `.env`

```ini
# Enable feedback loop
FEATURE_FEEDBACK_LOOP=1

# Price tracking every 15 minutes
FEEDBACK_TRACKING_INTERVAL=900

# Send recommendations to admin (not auto-apply)
FEEDBACK_AUTO_ADJUST=0

# Minimum 20 alerts before adjusting weights
FEEDBACK_MIN_SAMPLES=20

# Enable weekly reports on Sunday at 23:00 UTC
FEEDBACK_WEEKLY_REPORT=1
FEEDBACK_WEEKLY_REPORT_DAY=6
FEEDBACK_WEEKLY_REPORT_HOUR=23
```

### Step 2: Restart the Bot

The feedback loop will:
1. Create database at `data/feedback/alert_performance.db`
2. Start background price tracker (every 15 minutes)
3. Begin recording all alerts automatically

Check logs for:
```
feedback_loop_database_initialized
feedback_tracker_started interval=900s
```

### Step 3: Monitor First Week

Watch for these log messages:

**Alerts being recorded:**
```
alert_recorded alert_id=abc123 ticker=TSLA catalyst_type=partnership
```

**Price tracking (every 15 min):**
```
performance_tracked alert_id=abc123 ticker=TSLA timeframe=15m price=252.50 change=+1.00%
```

**Outcome scoring (after 24h):**
```
alert_scored alert_id=abc123 ticker=TSLA outcome=win score=0.65
```

**Keyword analysis (daily at 21:30 UTC):**
```
keyword_weights_adjusted auto=False count=8
```

## What You'll See

### Daily Admin Reports

After enabling, your nightly admin reports will include a new "Feedback Loop (7d)" section:

```
🔄 Feedback Loop (7d)
Total Alerts: 142
Win Rate: 58.4%
Avg Return: +2.3%
Wins: 83 | Losses: 45 | Neutral: 14
```

### Weekly Performance Reports

Every Sunday at 23:00 UTC, you'll receive a comprehensive report:

```
📊 Weekly Performance Report (Oct 28 - Nov 3)

Overview
• Alerts Posted: 142
• Win Rate: 58.4%
• Avg Return: +2.3%

🏆 Best Catalyst Types
1. Partnerships: 72% win rate, +3.8% avg
2. FDA Approval: 68% win rate, +5.2% avg

⚠️ Worst Catalyst Types
1. Offerings: 23% win rate, -2.8% avg

📈 Top Gaining Tickers
NVDA: +12.3% (3 alerts)
AMD: +8.7% (2 alerts)

💡 Keyword Recommendations
• Increase weight: 8 keywords
• Decrease weight: 5 keywords
```

### Keyword Recommendations

Sent to admin webhook when keywords show significant performance:

```
Keyword Weight Recommendations

📈 partnership
Current: 1.20 → Recommended: 1.35 (+0.15)
Win Rate: 72.0% | Score: +0.42
Reason: High win rate and positive score

📉 offering
Current: 1.00 → Recommended: 0.70 (-0.30)
Win Rate: 28.0% | Score: -0.35
Reason: Low win rate and negative score
```

## Manual Testing Commands

### Check Database Stats

```python
from catalyst_bot.feedback.database import get_performance_stats

stats = get_performance_stats(lookback_days=7)
print(f"Total alerts: {stats['total_alerts']}")
print(f"Win rate: {stats['win_rate']:.1%}")
print(f"Avg return: {stats['avg_return_1d']:+.2%}")
```

### Manually Trigger Price Tracking

```python
from catalyst_bot.feedback import track_alert_performance

updated = track_alert_performance()
print(f"Updated {updated} alerts")
```

### Score Pending Alerts

```python
from catalyst_bot.feedback import score_pending_alerts

scored = score_pending_alerts()
print(f"Scored {scored} alerts")
```

### Generate Weekly Report

```python
from catalyst_bot.feedback.weekly_report import generate_weekly_report

report = generate_weekly_report()
print(f"Total alerts: {report['overview']['total_alerts']}")
print(f"Win rate: {report['overview']['win_rate']:.1%}")
```

### Analyze Keywords

```python
from catalyst_bot.feedback.weight_adjuster import analyze_keyword_performance

recs = analyze_keyword_performance(lookback_days=7)

for keyword, data in recs.items():
    print(f"{keyword}: {data['win_rate']:.1%} win rate")
    print(f"  Current: {data['current_weight']} → Recommended: {data['recommended_weight']}")
```

## Enable Auto-Adjustment (After 1 Week)

Once you've collected enough data and verified the recommendations look good:

```ini
# Auto-apply weight adjustments
FEEDBACK_AUTO_ADJUST=1
```

Now the system will automatically update `out/dynamic_keyword_weights.json` instead of sending recommendations to admin.

All changes are logged to `data/admin_changes.jsonl` for auditing.

## Database Location

```
data/feedback/alert_performance.db
```

You can query this database directly with SQLite:

```bash
sqlite3 data/feedback/alert_performance.db

.schema alert_performance
SELECT * FROM alert_performance ORDER BY posted_at DESC LIMIT 10;
```

## Disable Feedback Loop

To disable:

```ini
FEATURE_FEEDBACK_LOOP=0
```

The database and historical data will be preserved.

## Questions?

See `WAVE_1.2_IMPLEMENTATION.md` for complete documentation.
