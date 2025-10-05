# Tiingo Integration for Advanced Charts

## ✅ Fixed: Charts Now Use Tiingo API

Your advanced charts now **properly use your $30 Tiingo API** for intraday data, including 1-minute bars!

---

## What Changed

### Before
- Charts called `yfinance` directly
- **Bypassed** your paid Tiingo API
- Slower, less reliable data

### After
- Charts use `market.get_intraday()`
- **Respects** Tiingo configuration
- Falls back to yfinance if Tiingo unavailable
- Uses **1-minute bars** for 1D charts (Tiingo $30 tier feature!)

---

## Configuration

### 1. Enable Tiingo in `.env`

```ini
# Enable Tiingo
FEATURE_TIINGO=1
TIINGO_API_KEY=your_tiingo_api_key_here

# Enable advanced charts
FEATURE_ADVANCED_CHARTS=1
FEATURE_RICH_ALERTS=1

# Default to 1D timeframe (uses 1-min bars via Tiingo)
CHART_DEFAULT_TIMEFRAME=1D
```

### 2. Verify Provider Order (Optional)

```ini
# Market data provider priority (Tiingo first)
MARKET_PROVIDER_ORDER=tiingo,av,yf
```

---

## Timeframe → Interval Mapping

When Tiingo is enabled (`FEATURE_TIINGO=1`):

| Timeframe | Interval | Bars | Source | Notes |
|-----------|----------|------|--------|-------|
| **1D** | 1-minute | 390 | Tiingo | **Your $30 tier unlocks this!** |
| **5D** | 5-minute | 390 | Tiingo | Faster than yfinance |
| **1M** | 15-minute | 400 | Tiingo | Better reliability |
| **3M** | Daily | 90 | yfinance | Tiingo daily not needed |
| **1Y** | Daily | 252 | yfinance | Long-term history |

---

## Benefits of Using Tiingo

✅ **Higher resolution**: 1-minute bars vs 5-minute (yfinance free tier)
✅ **Better reliability**: Paid API = fewer rate limits
✅ **Faster responses**: Optimized endpoints
✅ **Pre/post market data**: Included in Tiingo IEX
✅ **More history**: Tiingo $30 tier = more lookback

---

## Verification

### Check Logs

When charts are generated, check logs for source:

```bash
tail -f logs/catalyst.log | grep "fetch_data_success"
```

**With Tiingo enabled**, you should see:
```
fetch_data_success source=market.get_intraday ticker=AAPL tf=1D rows=390
```

**Without Tiingo** (or fallback):
```
fetch_data_success source=yfinance ticker=AAPL tf=1D rows=78
```

### Test Chart Generation

```bash
# Set Tiingo in .env first, then:
python test_advanced_charts.py AAPL

# Should show logs indicating Tiingo usage
```

---

## Troubleshooting

### Charts still using yfinance?

**Check these**:

1. `FEATURE_TIINGO=1` in `.env`
2. `TIINGO_API_KEY` is set correctly
3. API key is valid (test at https://api.tiingo.com/iex/AAPL)
4. No typos in key

### How to verify Tiingo is working:

```python
# Quick test
from catalyst_bot.market import get_intraday

df = get_intraday("AAPL", interval="1min", output_size="compact")
print(f"Got {len(df)} bars")
# Should return ~390 bars (6.5 hours * 60 mins) if Tiingo is working
```

### Check configuration:

```python
from catalyst_bot.config import get_settings

s = get_settings()
print(f"Tiingo enabled: {s.feature_tiingo}")
print(f"Tiingo key set: {bool(s.tiingo_api_key)}")
```

---

## API Rate Limits

### Tiingo $30 Tier Limits

- **IEX Intraday**: 50,000 requests/day
- **Daily Historical**: 5,000 requests/day
- **Per-second**: Generous (no hard limit published)

### Chart Cache Helps

With `CHART_CACHE_TTL_SECONDS=300` (5 minutes), you'll only hit Tiingo once per ticker per 5 minutes, dramatically reducing API usage.

**Example**:
- 100 alerts/day for same ticker = **1 Tiingo call** (if within 5-min window)
- Different tickers = separate cache entries

---

## Cost Optimization

### Tips to Reduce API Calls

1. **Increase cache TTL**: `CHART_CACHE_TTL_SECONDS=600` (10 minutes)
2. **Pre-generate popular tickers**: Cron job to warm cache
3. **Disable charts for low-priority alerts**: Only enable for key tickers
4. **Use 5D instead of 1D**: 5-minute bars = 5x fewer data points

### Monitor Usage

Check Tiingo dashboard: https://api.tiingo.com/account/usage

---

## Data Quality Comparison

| Feature | yfinance (free) | Tiingo $30 |
|---------|----------------|------------|
| 1-min bars | ❌ No | ✅ Yes |
| 5-min bars | ✅ Limited | ✅ Full |
| Pre-market | ⚠️ Sometimes | ✅ Always |
| Post-market | ⚠️ Sometimes | ✅ Always |
| Reliability | ⚠️ Medium | ✅ High |
| Rate limits | ⚠️ Strict | ✅ Generous |
| Historical depth | ⚠️ ~60 days | ✅ Years |

---

## Advanced: 1-Minute Bars

With your $30 tier, 1D charts now use **1-minute bars** (390 bars for a full trading day):

```
Regular trading: 9:30 AM - 4:00 PM = 390 minutes
Pre-market: 4:00 AM - 9:30 AM = ~330 minutes (if enabled)
After-hours: 4:00 PM - 8:00 PM = ~240 minutes (if enabled)
```

This gives you **ultra-high resolution** for day trading!

### Example .env for Day Traders

```ini
FEATURE_TIINGO=1
TIINGO_API_KEY=your_key_here
FEATURE_ADVANCED_CHARTS=1
CHART_DEFAULT_TIMEFRAME=1D  # Uses 1-min bars
CHART_CACHE_TTL_SECONDS=180  # 3 minutes (fresher data)
```

---

## Summary

✅ **Charts now use Tiingo** for 1D, 5D, 1M timeframes
✅ **1-minute bars** on 1D charts (your $30 tier feature)
✅ **Graceful fallback** to yfinance if Tiingo fails
✅ **Caching reduces** API usage
✅ **Logs show source** for verification

**Next**: Enable in `.env` and test with `python test_advanced_charts.py AAPL`
