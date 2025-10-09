# 🛠️ Admin Channel Commands

**Channel Purpose:** Bot configuration, reports, and parameter management

---

## Slash Commands

### `/admin report [date]`
Generate and view performance report for a specific date
- **date** (optional): YYYY-MM-DD format (default: yesterday)
- **Example:** `/admin report 2025-10-04`
- **Returns:** Interactive report with backtest results, parameter recommendations, and action buttons

### `/admin set <parameter> <value>`
Update a bot parameter in real-time
- **parameter** (required): Parameter name (e.g., MIN_SCORE, PRICE_CEILING)
- **value** (required): New value
- **Example:** `/admin set MIN_SCORE 0.30`
- **Note:** Changes take effect immediately

### `/admin rollback`
Revert to previous configuration
- **No parameters**
- **Returns:** Confirmation of rollback with restored parameter values

### `/admin stats`
Show current bot parameter values
- **No parameters**
- **Returns:** Current configuration snapshot

---

## Button Interactions

When admin reports are posted, they include interactive buttons:

### 📊 **Apply Recommendation**
- Automatically applies suggested parameter changes
- Creates a backup before applying
- Shows confirmation with new values

### 🔄 **Refresh Report**
- Regenerates the report with latest data
- Useful if new alerts came in after initial report

### 📈 **View Details**
- Shows detailed breakdown of recommendations
- Includes reasoning and impact assessment

### ⚙️ **Manual Override**
- Opens dialog to manually set parameters
- Bypasses recommendations for custom tuning

---

## Automated Posts

### **Nightly Admin Report** (8:00 PM ET / 00:00 UTC)
- Daily performance summary
- Backtest results (win rate, avg return)
- Parameter recommendations based on:
  - Real-time breakout feedback
  - Historical trending keywords
  - Volume and sentiment patterns

### **Weekly Performance Report** (Sunday 8:00 PM ET)
- 7-day lookback analysis
- Top catalysts (best performing keywords)
- Underperforming categories
- Confidence tier breakdown
- Price range performance

---

## Parameter Reference

**Common parameters you can adjust:**
- `MIN_SCORE` - Minimum classification score (0.0-1.0)
- `MIN_SENT_ABS` - Minimum absolute sentiment (-1.0 to 1.0)
- `PRICE_CEILING` - Maximum stock price ($)
- `PRICE_FLOOR` - Minimum stock price ($)
- `MAX_ALERTS_PER_CYCLE` - Alert rate limit (1-50)
- `KEYWORD_WEIGHT_*` - Keyword category weights

**See current values:** `/admin stats`

---

## Best Practices

1. **Review reports daily** - Check nightly admin report for parameter recommendations
2. **Test before applying** - Review recommendation reasoning before clicking "Apply"
3. **Monitor impact** - Check next report to see if changes improved win rate
4. **Use rollback** - If performance degrades, use `/admin rollback` immediately
5. **Weekly review** - Use Sunday report to identify trending patterns

---

**Need help?** Contact bot maintainer or check `/admin stats` for current config.
