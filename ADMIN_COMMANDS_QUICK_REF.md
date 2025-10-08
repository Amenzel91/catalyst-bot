# Admin Commands Quick Reference

## Discord Slash Commands

### View Current Configuration
```
/admin stats
```
Shows all current parameters and recent changes.

### Update a Parameter
```
/admin set MIN_SCORE 0.3
/admin set PRICE_CEILING 5.0
/admin set MAX_ALERTS_PER_CYCLE 50
```

### Revert to Previous Configuration
```
/admin revert
```
Rolls back to the most recent backup.

### Generate Admin Report On-Demand
```
/admin report
/admin report 2025-10-03
```

## Interactive Buttons (Nightly Reports)

When you receive the nightly admin report, use these buttons:

- **📊 View Details** - See full backtest breakdown and top keywords
- **✅ Approve Changes** - Apply all recommended parameter changes
- **❌ Reject Changes** - Keep current settings
- **⚙️ Custom Adjust** - Open modal to manually set specific parameters

## Common Parameters

### Sentiment Thresholds
- `MIN_SCORE` - Minimum classification score (0-1)
- `MIN_SENT_ABS` - Minimum absolute sentiment (0-1)

### Price Filters
- `PRICE_CEILING` - Maximum stock price ($)
- `PRICE_FLOOR` - Minimum stock price ($)

### Alert Limits
- `MAX_ALERTS_PER_CYCLE` - Max alerts per cycle
- `ALERTS_MIN_INTERVAL_MS` - Min ms between alerts

### Confidence Levels
- `CONFIDENCE_HIGH` - High confidence threshold (0-1)
- `CONFIDENCE_MODERATE` - Moderate confidence threshold (0-1)

### Analyzer Thresholds
- `ANALYZER_HIT_UP_THRESHOLD_PCT` - Win threshold (%)
- `ANALYZER_HIT_DOWN_THRESHOLD_PCT` - Loss threshold (%)

### Breakout Scanner
- `BREAKOUT_MIN_AVG_VOL` - Minimum average volume
- `BREAKOUT_MIN_RELVOL` - Minimum relative volume

## Safety Features

✅ **Automatic Backups** - Created before every change
✅ **Rate Limiting** - 60 seconds between changes
✅ **Validation** - All values checked before applying
✅ **Change History** - All changes logged to `data/admin_changes.jsonl`
✅ **Rollback** - Can revert to any previous backup

## Files & Locations

- **Change History:** `data/admin_changes.jsonl`
- **Backups:** `data/config_backups/env_*.backup`
- **Reports:** `out/admin_reports/report_*.json`
- **Configuration:** `.env`

## Monitoring

### View Change History
```python
from catalyst_bot.config_updater import get_change_history
history = get_change_history(limit=10)
```

### List Backups
```bash
ls data/config_backups/
```

## Error Messages

**"Rate limit: Please wait 45s"**
- You made a change too recently
- Wait for the cooldown period

**"Validation failed for MIN_SCORE"**
- Value is out of valid range
- Check parameter requirements

**"No configuration backups found"**
- No changes have been made yet
- Make a change to create first backup

## Tips

1. **Always check /admin stats before making changes** - See current values
2. **Use /admin revert if something goes wrong** - Quick rollback
3. **Review nightly reports** - Automated recommendations based on performance
4. **Test changes with one parameter at a time** - Easier to track impact
5. **Use "Custom Adjust" for multiple parameters** - Batch changes in one go

## Support

For issues or questions:
1. Check `WAVE_1_1_IMPLEMENTATION_REPORT.md` for detailed documentation
2. Review `data/admin_changes.jsonl` for change history
3. Check `data/logs/bot.jsonl` for detailed logs
