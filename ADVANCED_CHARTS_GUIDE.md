# Advanced Multi-Panel Charts Guide

## Overview

The Catalyst Bot now supports **professional-grade multi-panel financial charts** with interactive timeframe switching. This feature provides:

- **Multi-panel layout**: Price candlesticks, Volume, RSI, and MACD in one cohesive image
- **Dark theme styling**: Green/red candles with professional color scheme
- **Multiple timeframes**: 1D, 5D, 1M, 3M, 1Y
- **Interactive buttons**: Discord message components to switch timeframes
- **Smart caching**: Avoids regenerating identical charts (5-minute TTL)
- **Technical indicators**:
  - VWAP (Volume Weighted Average Price) overlay
  - Moving averages (20-day, 50-day on longer timeframes)
  - RSI (Relative Strength Index) with 30/70 reference lines
  - MACD with signal line and histogram

---

## Quick Start

### 1. Install Dependencies

```bash
pip install matplotlib mplfinance pandas yfinance
```

### 2. Enable in `.env`

```ini
# Enable advanced charts
FEATURE_ADVANCED_CHARTS=1
FEATURE_RICH_ALERTS=1

# Optional: Configure defaults
CHART_DEFAULT_TIMEFRAME=1D
CHART_CACHE_TTL_SECONDS=300
FEATURE_CHART_BUTTONS=1
```

### 3. Run the Bot

```bash
python -m catalyst_bot.runner --once
```

Charts will now appear in Discord alerts with timeframe switching buttons!

---

## Configuration Options

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_ADVANCED_CHARTS` | `0` | Enable/disable advanced multi-panel charts |
| `FEATURE_RICH_ALERTS` | `0` | Required to enable chart embeds |
| `CHART_DEFAULT_TIMEFRAME` | `1D` | Default timeframe (1D, 5D, 1M, 3M, 1Y) |

### Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `CHART_CACHE_TTL_SECONDS` | `300` | How long to cache charts (5 minutes) |
| `CHART_CACHE_DIR` | `out/charts/cache` | Where to store cached charts |

### Interactive Buttons

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_CHART_BUTTONS` | `1` | Show timeframe switching buttons |
| `DISCORD_PUBLIC_KEY` | `` | Discord app public key (for interactions) |

---

## Timeframe Details

### Available Timeframes

| Timeframe | Period | Interval | Bars | Best For |
|-----------|--------|----------|------|----------|
| **1D** | 1 day | 5-minute | 78 | Intraday trading, day trades |
| **5D** | 5 days | 15-minute | 130 | Short-term swing trades |
| **1M** | 30 days | 1-hour | 150 | Medium-term positions |
| **3M** | 90 days | Daily | 90 | Longer-term trends |
| **1Y** | 365 days | Daily | 252 | Long-term analysis |

### Indicators by Timeframe

- **1D, 5D, 1M**: VWAP overlay
- **3M, 1Y**: VWAP + 20-day MA + 50-day MA
- **All**: RSI-14, MACD (12,26,9), Volume

---

## Interactive Buttons (Optional)

### How It Works

Discord message components allow users to click buttons to switch chart timeframes **without buttons actually working yet** unless you set up an interaction endpoint.

### Current Limitation

**Buttons are displayed but not yet functional** because Discord interactions require:
1. A Discord Application (not just a webhook)
2. An interaction endpoint URL (HTTP server)
3. Proper signature verification

### Two Options

#### Option A: Display-Only Buttons (Current State)

- Buttons appear on messages
- Users see available timeframes
- Clicking does nothing (no backend set up)
- Still useful for visual indication

```ini
FEATURE_CHART_BUTTONS=1  # Show buttons (cosmetic)
```

#### Option B: Fully Interactive Buttons (Advanced Setup)

Requires additional setup:

1. **Create Discord Application**
   - Go to https://discord.com/developers/applications
   - Create new application
   - Copy "Public Key" → `DISCORD_PUBLIC_KEY` in `.env`

2. **Set Up Interaction Endpoint**

   The bot includes a Flask endpoint example:

   ```python
   # Run this in a separate process
   from catalyst_bot.discord_interactions import create_interaction_endpoint_flask

   app = create_interaction_endpoint_flask()
   app.run(host='0.0.0.0', port=3000)
   ```

3. **Configure Discord App**
   - Set "Interactions Endpoint URL" to your public URL (e.g., `https://your-domain.com/interactions`)
   - Use ngrok for testing: `ngrok http 3000`

4. **Enable in `.env`**

   ```ini
   DISCORD_PUBLIC_KEY=your_app_public_key_here
   FEATURE_CHART_BUTTONS=1
   ```

---

## Chart Caching

### How It Works

Charts are cached by `(ticker, timeframe)` to avoid regenerating identical images:

- Cache key: `AAPL_1D`, `TSLA_5D`, etc.
- TTL: 5 minutes (configurable)
- Storage: `out/charts/cache/`

### Cache Statistics

```python
from catalyst_bot.chart_cache import get_cache

cache = get_cache()
stats = cache.stats()
print(stats)
# {
#   "size": 42,
#   "oldest": "2025-10-01T14:23:00",
#   "newest": "2025-10-01T14:28:00",
#   "expired": 5,
#   "ttl_seconds": 300
# }
```

### Manual Cache Management

```python
# Clear expired entries
cache.clear_expired()

# Clear all entries
cache.clear_all()

# Get specific chart
path = cache.get("AAPL", "1D")
```

---

## Programmatic Usage

### Generate Chart Manually

```python
from catalyst_bot.charts_advanced import generate_multi_panel_chart

# Generate 1D chart for AAPL
chart_path = generate_multi_panel_chart(
    ticker="AAPL",
    timeframe="1D",
    style="dark"
)

print(f"Chart saved to: {chart_path}")
# Chart saved to: out/charts/AAPL_1D_20251001-142530.png
```

### Generate All Timeframes

```python
from catalyst_bot.charts_advanced import generate_all_timeframes

results = generate_all_timeframes("AAPL")

for tf, path in results.items():
    print(f"{tf}: {path}")
# 1D: out/charts/AAPL_1D_20251001-142530.png
# 5D: out/charts/AAPL_5D_20251001-142531.png
# ...
```

---

## Troubleshooting

### Charts Not Appearing

**Issue**: Alerts don't show charts

**Solutions**:
1. Check `FEATURE_ADVANCED_CHARTS=1` and `FEATURE_RICH_ALERTS=1`
2. Verify matplotlib/mplfinance installed: `pip list | grep mpl`
3. Check logs for errors: `grep "advanced_chart" logs/catalyst.log`

### Import Errors

**Issue**: `ModuleNotFoundError: No module named 'mplfinance'`

**Solution**:
```bash
pip install matplotlib mplfinance pandas yfinance
```

### Buttons Not Working

**Issue**: Clicking buttons does nothing

**Expected**: This is normal without interaction endpoint setup (see "Interactive Buttons" section above)

**Solution**: Either:
- Leave buttons as visual indicators (`FEATURE_CHART_BUTTONS=1`)
- Or set up full interaction endpoint (advanced)

### Chart Generation Slow

**Issue**: First chart takes 5-10 seconds

**Solutions**:
1. **Normal behavior** - first chart fetch + render is slow
2. Subsequent charts use cache (< 1 second)
3. Increase cache TTL: `CHART_CACHE_TTL_SECONDS=600` (10 minutes)
4. Pre-generate charts for common tickers (cron job)

### Cache Not Working

**Issue**: Charts regenerated every time

**Solutions**:
1. Check cache directory exists: `mkdir -p out/charts/cache`
2. Verify TTL not too short: `CHART_CACHE_TTL_SECONDS=300`
3. Check disk space: `df -h`
4. Review cache stats: `cache.stats()`

---

## Advanced Customization

### Custom Dark Theme Colors

Edit `src/catalyst_bot/charts_advanced.py`:

```python
mc = mpf.make_marketcolors(
    up="#26A69A",      # Change green color
    down="#EF5350",    # Change red color
    edge="inherit",
    wick="inherit",
    volume="#546E7A",  # Change volume bar color
    alpha=0.9,
)
```

### Add More Indicators

```python
# In generate_multi_panel_chart(), add to addplot_main:

# Example: Add Bollinger Bands
bb_upper = df["Close"].rolling(window=20).mean() + 2 * df["Close"].rolling(window=20).std()
bb_lower = df["Close"].rolling(window=20).mean() - 2 * df["Close"].rolling(window=20).std()

addplot_main.append(
    mpf.make_addplot(bb_upper, color="#FFA500", width=0.5, panel=0, linestyle="--")
)
addplot_main.append(
    mpf.make_addplot(bb_lower, color="#FFA500", width=0.5, panel=0, linestyle="--")
)
```

### Custom Timeframes

Add to `TIMEFRAME_CONFIG` in `charts_advanced.py`:

```python
TIMEFRAME_CONFIG = {
    "1D": {"days": 1, "interval": "5min", "bars": 78},
    "2W": {"days": 14, "interval": "1h", "bars": 168},  # Custom: 2 weeks
    # ... existing timeframes
}
```

---

## Performance Tips

1. **Enable caching**: Set reasonable TTL (300-600 seconds)
2. **Limit timeframes**: Remove unused timeframes from buttons
3. **Pre-generate popular tickers**: Cron job to warm cache
4. **Optimize bar counts**: Reduce `bars` in `TIMEFRAME_CONFIG` for faster rendering
5. **Use SSD**: Store cache on fast disk

---

## Example Workflow

### Daily Trading Setup

```ini
# .env configuration
FEATURE_ADVANCED_CHARTS=1
FEATURE_RICH_ALERTS=1
CHART_DEFAULT_TIMEFRAME=1D
CHART_CACHE_TTL_SECONDS=600  # 10 minutes
FEATURE_CHART_BUTTONS=1
```

**Result**: Real-time alerts with 1D intraday charts, cached for 10 minutes

### Swing Trading Setup

```ini
CHART_DEFAULT_TIMEFRAME=5D
CHART_CACHE_TTL_SECONDS=1800  # 30 minutes
```

**Result**: Alerts show 5-day charts with 15-minute bars

---

## Migration from QuickChart

If currently using `FEATURE_QUICKCHART_POST=1`:

```ini
# Old setup
FEATURE_QUICKCHART_POST=1
QUICKCHART_BASE_URL=https://quickchart.io

# New setup (replaces QuickChart)
FEATURE_ADVANCED_CHARTS=1
FEATURE_QUICKCHART_POST=0  # Disable to avoid conflicts
```

**Advantages over QuickChart**:
- ✅ Multi-panel layout (volume + RSI + MACD)
- ✅ More technical indicators
- ✅ Better dark theme
- ✅ No external API dependency
- ✅ Local caching

**Disadvantages**:
- ❌ Slower first render (5-10s vs 1-2s)
- ❌ Requires matplotlib/mplfinance
- ❌ More disk space (300KB vs 50KB per chart)

---

## Credits

Built with:
- **mplfinance**: Financial charting library
- **matplotlib**: Plotting backend
- **yfinance**: Market data source
- **Discord.py concepts**: Message components

---

## Support

**Questions?** Check logs for errors:
```bash
tail -f logs/catalyst.log | grep -i chart
```

**Still stuck?** Open an issue with:
- `.env` configuration
- Error logs
- Chart generation attempt output
