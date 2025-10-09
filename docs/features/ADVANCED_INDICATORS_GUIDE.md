# Advanced Indicators Guide - WAVE 3.1

## Overview

WAVE 3.1 introduces professional-grade technical indicators to Catalyst-Bot's chart generation system. These indicators enhance chart analysis and provide actionable insights for trading decisions.

## Table of Contents

1. [Bollinger Bands](#bollinger-bands)
2. [Fibonacci Retracements](#fibonacci-retracements)
3. [Support & Resistance Detection](#support--resistance-detection)
4. [Volume Profile](#volume-profile)
5. [Multiple Timeframe Analysis](#multiple-timeframe-analysis)
6. [Chart Templates](#chart-templates)
7. [Configuration](#configuration)
8. [Usage Examples](#usage-examples)
9. [Performance & Caching](#performance--caching)

---

## Bollinger Bands

### What They Are

Bollinger Bands are volatility bands placed above and below a moving average. They automatically widen during volatile periods and narrow during quiet periods.

### Components

- **Middle Band**: 20-period Simple Moving Average (SMA)
- **Upper Band**: Middle Band + (2 × standard deviation)
- **Lower Band**: Middle Band - (2 × standard deviation)

### How to Interpret

- **Price touching Upper Band**: Potentially overbought
- **Price touching Lower Band**: Potentially oversold
- **Bands narrowing (squeeze)**: Low volatility, potential breakout coming
- **Bands widening**: High volatility, strong move in progress

### When to Use

- **Range Trading**: Buy near lower band, sell near upper band
- **Breakout Trading**: Watch for price breaking outside bands with volume
- **Trend Confirmation**: Strong trends often "walk the band"

### Configuration

```ini
CHART_SHOW_BOLLINGER=1        # Enable/disable Bollinger Bands
CHART_BOLLINGER_PERIOD=20     # Moving average period
CHART_BOLLINGER_STD=2.0       # Standard deviation multiplier
```

### Code Example

```python
from catalyst_bot.indicators import calculate_bollinger_bands

prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109]
upper, middle, lower = calculate_bollinger_bands(prices, period=20, std_dev=2.0)

# Check current position
from catalyst_bot.indicators import get_bollinger_position
current_price = 110
position = get_bollinger_position(current_price, upper[-1], middle[-1], lower[-1])
print(f"Price is: {position}")
```

---

## Fibonacci Retracements

### What They Are

Fibonacci retracements are horizontal lines indicating potential support and resistance levels based on the Fibonacci sequence.

### Key Levels

- **0%**: Swing low (starting point)
- **23.6%**: Shallow retracement
- **38.2%**: Moderate retracement
- **50%**: Half retracement (not a Fibonacci number, but widely used)
- **61.8%**: Golden ratio (most significant level)
- **78.6%**: Deep retracement
- **100%**: Swing high (ending point)

### How to Interpret

- Price often retraces to Fibonacci levels before continuing trend
- **61.8%** is the most reliable level (golden ratio)
- Levels act as potential support in uptrends, resistance in downtrends
- Multiple timeframe alignment strengthens the level

### When to Use

- **Pullback entries**: Enter on retracement to 38.2%, 50%, or 61.8%
- **Profit targets**: Use extensions (127.2%, 161.8%) for exits
- **Stop placement**: Below/above next Fibonacci level

### Configuration

```ini
CHART_SHOW_FIBONACCI=1         # Enable/disable Fibonacci levels
CHART_FIBONACCI_LOOKBACK=20    # Lookback period for swing detection
```

### Code Example

```python
from catalyst_bot.indicators import find_swing_points, calculate_fibonacci_levels

prices = [100, 105, 110, 108, 106, 104, 107, 112, 115, 113]

# Automatically find swing points
swing_high, swing_low, h_idx, l_idx = find_swing_points(prices, lookback=20)

# Calculate Fibonacci levels
fib_levels = calculate_fibonacci_levels(swing_high, swing_low)

print(f"Fibonacci 61.8%: ${fib_levels['61.8%']:.2f}")
print(f"Fibonacci 50%: ${fib_levels['50%']:.2f}")
```

---

## Support & Resistance Detection

### What They Are

Support and resistance are price levels where buying or selling pressure prevents further price movement.

- **Support**: Price level where demand prevents further decline
- **Resistance**: Price level where supply prevents further rise

### Detection Algorithm

1. Find local peaks (resistance) and troughs (support)
2. Cluster nearby levels within sensitivity threshold
3. Weight by volume at those price levels
4. Filter to levels with minimum touch count
5. Return strongest levels by combined score

### Strength Factors

- **Touch Count**: How many times price tested the level
- **Volume**: Trading activity at the level
- **Recency**: Recent touches are weighted more heavily

### How to Interpret

- **Strong levels** (3+ touches, high volume): Significant barriers
- **Breaking resistance**: Bullish (becomes new support)
- **Breaking support**: Bearish (becomes new resistance)
- **Price testing level**: Decision point, watch for breakout or bounce

### When to Use

- **Entry signals**: Buy at support, sell at resistance
- **Stop placement**: Below support (long) or above resistance (short)
- **Breakout trading**: Enter when level breaks with volume

### Configuration

```ini
CHART_SHOW_SUPPORT_RESISTANCE=1  # Enable/disable S/R detection
CHART_SR_SENSITIVITY=0.02        # Clustering threshold (2%)
CHART_SR_MAX_LEVELS=5            # Maximum levels to display
CHART_SR_MIN_TOUCHES=2           # Minimum touches required
```

### Code Example

```python
from catalyst_bot.indicators import detect_support_resistance

prices = [100, 102, 100, 103, 100, 105, 102, 107, 105, 110]
volumes = [1000, 1500, 1200, 1800, 1100, 2000, 1600, 2200, 1900, 2400]

support, resistance = detect_support_resistance(
    prices, volumes,
    sensitivity=0.02,
    max_levels=5
)

for i, level in enumerate(support):
    print(f"S{i+1}: ${level['price']:.2f} (strength: {level['strength']:.0f})")

for i, level in enumerate(resistance):
    print(f"R{i+1}: ${level['price']:.2f} (strength: {level['strength']:.0f})")
```

---

## Volume Profile

### What It Is

Volume Profile shows the distribution of volume across different price levels, unlike traditional volume which shows volume over time.

### Key Concepts

- **POC (Point of Control)**: Price level with highest volume (most significant S/R)
- **Value Area**: Price range containing 70% of volume (fair value zone)
- **High Volume Nodes (HVN)**: Prices with high volume (support/resistance)
- **Low Volume Nodes (LVN)**: Prices with low volume (potential breakout zones)

### How to Interpret

- **POC**: Acts as magnetic level, strong support/resistance
- **Value Area**: Price tends to return to this range
- **HVN**: Expect consolidation or bounces
- **LVN**: Price moves quickly through these levels

### When to Use

- **Institutional levels**: POC shows where big money traded
- **Range identification**: Value Area defines fair value
- **Breakout zones**: LVN indicates weak areas for fast moves

### Configuration

```ini
CHART_SHOW_VOLUME_PROFILE=0    # Enable/disable (0=off, resource intensive)
CHART_VOLUME_BINS=20           # Number of price bins
CHART_SHOW_POC=1               # Show Point of Control
CHART_SHOW_VALUE_AREA=1        # Show Value Area High/Low
```

### Code Example

```python
from catalyst_bot.indicators import (
    calculate_volume_profile,
    find_point_of_control,
    calculate_value_area
)

prices = [100, 101, 102, 101, 100, 99, 100, 101, 102, 103]
volumes = [1000, 1500, 2000, 1800, 1200, 900, 1100, 1600, 2100, 1700]

price_levels, vol_at_price = calculate_volume_profile(prices, volumes, bins=20)

poc = find_point_of_control(price_levels, vol_at_price)
vah, poc_va, val = calculate_value_area(price_levels, vol_at_price, value_area_pct=0.70)

print(f"POC: ${poc:.2f}")
print(f"Value Area: ${val:.2f} - ${vah:.2f}")
```

---

## Multiple Timeframe Analysis

### What It Is

Multiple Timeframe Analysis (MTF) examines the same security across different time periods to get a complete view of price action.

### Timeframe Hierarchy

- **Higher Timeframe**: Determines overall trend direction
- **Lower Timeframe**: Provides entry/exit timing
- **Alignment**: When all timeframes agree, probability increases

### Common Combinations

| Trading Style | Trend TF | Structure TF | Entry TF |
|--------------|----------|--------------|----------|
| Day Trading  | 1D       | 1H           | 5M       |
| Swing Trading| 1W       | 1D           | 4H       |
| Position     | 1M       | 1W           | 1D       |

### How to Interpret

- **All Bullish**: Strong uptrend, high confidence long setups
- **All Bearish**: Strong downtrend, high confidence short setups
- **Mixed**: Consolidation or reversal in progress
- **Divergence**: Lower TF counter-trend to higher TF (potential reversal)

### When to Use

- **Trend confirmation**: Align with higher timeframes
- **Entry timing**: Use lower timeframes for precise entries
- **Avoiding traps**: Check higher TF before taking lower TF signals

### Configuration

```ini
CHART_MTF_ANALYSIS=1    # Enable multiple timeframe analysis
```

### Code Example

```python
from catalyst_bot.indicators import analyze_multiple_timeframes, calculate_mtf_score

data = {
    "1D": [100, 102, 104, 106, 108, 110],
    "1W": [95, 100, 105, 110, 115, 120],
    "1M": [80, 90, 100, 110, 120, 130]
}

result = analyze_multiple_timeframes(data, timeframe_order=["1D", "1W", "1M"])

print(f"Alignment: {result['alignment']}")
print(f"Strength: {result['strength']:.0f}%")
print(f"Higher TF Bias: {result['higher_timeframe_bias']}")
print(f"Divergence: {result['divergence']}")

score = calculate_mtf_score(result)
print(f"MTF Confidence Score: {score}/100")
```

---

## Chart Templates

### What They Are

Pre-configured chart setups optimized for specific trading styles and strategies.

### Available Templates

1. **Breakout Chart**: Bollinger Bands + Volume Profile + S/R
   - Use for: Identifying volatility breakouts

2. **Swing Trading Chart**: Fibonacci + S/R + RSI
   - Use for: Multi-day position trading

3. **Scalping Chart**: VWAP + EMA + Volume
   - Use for: Quick intraday trades

4. **Earnings Chart**: Bollinger Bands + Volume + Highs/Lows
   - Use for: Trading earnings volatility

5. **Momentum Chart**: MACD + RSI + Volume
   - Use for: Riding strong trends

6. **Mean Reversion Chart**: Bollinger Bands + RSI + S/R
   - Use for: Range-bound trading

7. **Volume Analysis Chart**: Volume Profile + VWAP + Volume bars
   - Use for: Institutional activity detection

8. **Fibonacci Trader Chart**: Fibonacci + Extensions + S/R
   - Use for: Precision retracement trading

### Code Example

```python
from catalyst_bot.indicators.chart_templates import (
    get_template,
    list_templates,
    suggest_template
)

# List all templates
templates = list_templates()
for t in templates:
    print(f"{t['name']}: {t['description']}")

# Get specific template
breakout = get_template("breakout")
print(f"Indicators: {breakout['indicators']}")
print(f"Recommended TF: {breakout['timeframes']}")

# Get suggestions based on style
suggestions = suggest_template("swing", market_condition="trending")
print(f"Suggested templates: {suggestions}")
```

---

## Configuration

### Environment Variables (.env)

```ini
# --- WAVE 3.1: Advanced Chart Indicators ---

# Enable/disable specific indicators
CHART_SHOW_BOLLINGER=1
CHART_SHOW_FIBONACCI=1
CHART_SHOW_SUPPORT_RESISTANCE=1
CHART_SHOW_VOLUME_PROFILE=0
CHART_MTF_ANALYSIS=1

# Bollinger Bands settings
CHART_BOLLINGER_PERIOD=20
CHART_BOLLINGER_STD=2.0

# Fibonacci settings
CHART_FIBONACCI_LOOKBACK=20

# Support/Resistance settings
CHART_SR_SENSITIVITY=0.02       # 2% clustering threshold
CHART_SR_MAX_LEVELS=5           # Top 5 levels
CHART_SR_MIN_TOUCHES=2          # At least 2 touches

# Volume Profile settings
CHART_VOLUME_BINS=20
CHART_SHOW_POC=1
CHART_SHOW_VALUE_AREA=1

# Default indicators (comma-separated)
CHART_DEFAULT_INDICATORS=bollinger,sr

# Indicator cache settings
INDICATOR_CACHE_ENABLED=1
INDICATOR_CACHE_TTL_SEC=300     # 5 minutes
INDICATOR_CACHE_MAX_SIZE=1000   # Max cached items
```

---

## Usage Examples

### Example 1: Generate Chart with Multiple Indicators

```python
from catalyst_bot.chart_indicators_integration import generate_advanced_chart

ticker = "AAPL"
timeframe = "1D"
prices = [150, 152, 151, 153, 155, 154, 156, 158, 157, 159]
volumes = [1000, 1500, 1200, 1800, 2000, 1600, 2200, 2400, 1900, 2100]

# Generate chart with Bollinger Bands and S/R
config = generate_advanced_chart(
    ticker,
    timeframe,
    prices,
    volumes,
    indicators=['bollinger', 'sr']
)

# Convert to QuickChart URL
import json
import urllib.parse
config_json = json.dumps(config)
encoded = urllib.parse.quote(config_json)
url = f"http://localhost:3400/chart?c={encoded}"
```

### Example 2: Add Indicators to Existing Chart

```python
from catalyst_bot.chart_indicators_integration import (
    add_bollinger_bands_to_config,
    add_fibonacci_to_config
)

# Start with base config
config = {...}  # Your existing Chart.js config

# Add Bollinger Bands
config = add_bollinger_bands_to_config(config, prices, period=20, std_dev=2.0)

# Add Fibonacci levels
config = add_fibonacci_to_config(config, prices, lookback=20)

# Now config has both indicators
```

### Example 3: Use Chart Template

```python
from catalyst_bot.indicators.chart_templates import get_template, customize_template

# Get breakout template
template = get_template("breakout")

# Customize settings
custom = customize_template(
    "breakout",
    custom_settings={"bollinger_std": 3.0, "sr_max_levels": 3}
)

# Use template indicators
indicators = custom['indicators']  # ['bollinger', 'volume_profile', 'sr']
```

---

## Performance & Caching

### Indicator Caching

To avoid redundant calculations, indicators are cached with TTL:

```python
from catalyst_bot.indicators import get_cached_indicator, cache_indicator

# Try cache first
cached = get_cached_indicator("AAPL", "bollinger", {"period": 20})
if cached:
    upper, middle, lower = cached
else:
    # Calculate and cache
    upper, middle, lower = calculate_bollinger_bands(prices, period=20)
    cache_indicator("AAPL", "bollinger", {"period": 20}, (upper, middle, lower), ttl=300)
```

### Cache Statistics

```python
from catalyst_bot.indicators import get_cache

cache = get_cache()
stats = cache.get_stats()

print(f"Cache size: {stats['size']}/{stats['max_size']}")
print(f"Hit rate: {stats['hit_rate_pct']:.1f}%")
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

### Performance Tips

1. **Enable caching**: Set `INDICATOR_CACHE_ENABLED=1`
2. **Adjust TTL**: Balance freshness vs. performance with `INDICATOR_CACHE_TTL_SEC`
3. **Limit indicators**: Only enable needed indicators to reduce calculation time
4. **Use templates**: Templates have optimized indicator combinations
5. **Disable Volume Profile**: Most resource-intensive, only enable when needed

---

## Testing

Run the test suite to verify all indicators work correctly:

```bash
python test_indicators.py
```

Expected output:
```
============================================================
WAVE 3.1: Advanced Chart Indicators - Test Suite
============================================================

Testing Bollinger Bands...
  ✓ Bollinger Bands tests passed
Testing Fibonacci Levels...
  ✓ Fibonacci levels tests passed
Testing Swing Point Detection...
  ✓ Swing point detection tests passed
Testing Support/Resistance Detection...
  ✓ Support/Resistance detection tests passed
Testing Volume Profile...
  ✓ Volume Profile tests passed
Testing Multiple Timeframe Analysis...
  ✓ MTF Analysis tests passed
Testing Trend Detection...
  ✓ Trend detection tests passed

============================================================
SUCCESS: All 7 tests passed!
============================================================
```

---

## Troubleshooting

### Issue: Indicators not showing on charts

**Solution**: Check `.env` settings:
```ini
CHART_SHOW_BOLLINGER=1  # Make sure enabled
```

### Issue: Poor performance / slow chart generation

**Solution**: Enable caching and reduce indicators:
```ini
INDICATOR_CACHE_ENABLED=1
CHART_DEFAULT_INDICATORS=bollinger  # Use fewer indicators
CHART_SHOW_VOLUME_PROFILE=0  # Disable resource-intensive indicators
```

### Issue: No support/resistance levels detected

**Solution**: Adjust sensitivity and minimum touches:
```ini
CHART_SR_SENSITIVITY=0.03  # Increase (wider clustering)
CHART_SR_MIN_TOUCHES=1     # Lower threshold
```

### Issue: Fibonacci levels not at expected prices

**Solution**: Adjust lookback period for swing detection:
```ini
CHART_FIBONACCI_LOOKBACK=30  # Increase to find older swings
```

---

## References

- [Bollinger Bands - Investopedia](https://www.investopedia.com/terms/b/bollingerbands.asp)
- [Fibonacci Retracements - Investopedia](https://www.investopedia.com/terms/f/fibonacciretracement.asp)
- [Support and Resistance - Investopedia](https://www.investopedia.com/trading/support-and-resistance-basics/)
- [Volume Profile - TradingView](https://www.tradingview.com/support/solutions/43000502040-volume-profile/)

---

## Summary

WAVE 3.1 provides institutional-grade technical indicators that integrate seamlessly with QuickChart. Use these tools to:

- Identify high-probability trade setups
- Confirm trends across multiple timeframes
- Find precise entry and exit points
- Understand where institutional money is positioned

Combine indicators strategically using templates to match your trading style and current market conditions.
