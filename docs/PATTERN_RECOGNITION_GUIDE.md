# Pattern Recognition System

## Overview
Automated chart pattern detection using proven technical analysis algorithms. The pattern recognition system identifies common chart patterns and overlays them on price charts with confidence scores, key levels, and projected price targets.

## Supported Patterns

### 1. Triangles
Triangles form when price consolidates between converging trendlines, often preceding significant breakouts.

#### Ascending Triangle (Bullish)
- **Structure**: Flat resistance line, rising support line
- **Signal**: Bullish continuation or reversal
- **Breakout**: Typically upward through resistance
- **Target**: Resistance + pattern height
- **Confidence**: Based on number of touches (3+ required)

#### Descending Triangle (Bearish)
- **Structure**: Falling resistance line, flat support line
- **Signal**: Bearish continuation or reversal
- **Breakout**: Typically downward through support
- **Target**: Support - pattern height
- **Confidence**: Based on number of touches (3+ required)

#### Symmetrical Triangle (Neutral)
- **Structure**: Both trendlines converging toward apex
- **Signal**: Continuation pattern (direction depends on prior trend)
- **Breakout**: Can be upward or downward
- **Target**: Current price + pattern height (upside assumption)
- **Confidence**: Based on symmetry and touches

### 2. Head & Shoulders
Classic reversal pattern with three peaks, indicating trend exhaustion.

#### Classic Head & Shoulders (Bearish Reversal)
- **Structure**: Left shoulder → Head (higher) → Right shoulder (similar to left)
- **Signal**: Bearish reversal after uptrend
- **Breakout**: Downward through neckline
- **Target**: Neckline - (Head - Neckline)
- **Key Level**: Neckline (support line connecting troughs)
- **Confidence**: Based on shoulder symmetry (within 5%)

#### Inverse Head & Shoulders (Bullish Reversal)
- **Structure**: Inverted pattern with head as lowest point
- **Signal**: Bullish reversal after downtrend
- **Breakout**: Upward through neckline
- **Target**: Neckline + (Neckline - Head)
- **Key Level**: Neckline (resistance line connecting peaks)
- **Confidence**: Based on shoulder symmetry

### 3. Double Tops/Bottoms
Reversal patterns where price tests the same level twice and fails to break through.

#### Double Top (Bearish)
- **Structure**: Two equal peaks separated by a trough
- **Signal**: Bearish reversal
- **Breakout**: Downward through trough support
- **Target**: Trough - (Peak - Trough)
- **Tolerance**: Peaks within 2% of each other
- **Confidence**: Based on price match quality

#### Double Bottom (Bullish)
- **Structure**: Two equal troughs separated by a peak
- **Signal**: Bullish reversal
- **Breakout**: Upward through peak resistance
- **Target**: Peak + (Peak - Trough)
- **Tolerance**: Troughs within 2% of each other
- **Confidence**: Based on price match quality

### 4. Channels
Parallel trendlines where price bounces between support and resistance.

#### Ascending Channel (Bullish)
- **Structure**: Parallel rising trendlines
- **Signal**: Bullish continuation
- **Trading**: Buy near support, sell near resistance
- **Breakout**: Watch for breakdown or breakout

#### Descending Channel (Bearish)
- **Structure**: Parallel falling trendlines
- **Signal**: Bearish continuation
- **Trading**: Sell near resistance, cover near support
- **Breakout**: Watch for breakdown or breakout

#### Horizontal Channel (Range-bound)
- **Structure**: Flat parallel lines
- **Signal**: Consolidation/accumulation
- **Trading**: Range-bound strategy
- **Breakout**: Direction indicates next trend

### 5. Flags & Pennants
Short-term continuation patterns following sharp price moves.

#### Bull Flag
- **Structure**: Sharp upward move (flagpole) → rectangular consolidation (flag)
- **Signal**: Bullish continuation
- **Target**: Prior move length added to breakout
- **Volume**: Should decrease during consolidation
- **Confidence**: Higher with volume confirmation

#### Bear Flag
- **Structure**: Sharp downward move → rectangular consolidation
- **Signal**: Bearish continuation
- **Target**: Prior move length subtracted from breakdown
- **Volume**: Should decrease during consolidation

#### Pennants (Bull/Bear)
- **Structure**: Similar to flags but consolidation has converging trendlines
- **Signal**: Continuation pattern
- **Target**: Similar to flags
- **Duration**: Typically shorter than flags

## Configuration

### Master Toggle
Enable/disable all pattern recognition:
```ini
CHART_PATTERN_RECOGNITION=1
```

### Individual Pattern Controls
Toggle specific pattern types:
```ini
CHART_PATTERNS_TRIANGLES=1           # Ascending, descending, symmetrical
CHART_PATTERNS_HEAD_SHOULDERS=1      # Classic and inverse H&S
CHART_PATTERNS_DOUBLE_TOPS=1         # Double tops and bottoms
CHART_PATTERNS_CHANNELS=1            # Ascending, descending, horizontal
CHART_PATTERNS_FLAGS=1               # Flags and pennants
```

### Detection Sensitivity
Control pattern detection strictness (0.0-1.0):
```ini
CHART_PATTERN_SENSITIVITY=0.6
```

**Sensitivity Levels**:
- **Low (0.3-0.5)**: More patterns detected, may include false positives
- **Medium (0.5-0.7)**: Balanced detection (recommended for most users)
- **High (0.7-0.9)**: Only high-confidence patterns, fewer detections

### Lookback Period
Define how far back to search for patterns:
```ini
CHART_PATTERN_LOOKBACK_MIN=20        # Minimum bars (smaller patterns)
CHART_PATTERN_LOOKBACK_MAX=100       # Maximum bars (larger patterns)
```

**Lookback Guidelines**:
- **1D/5D charts**: 20-50 bars (intraday patterns)
- **1M charts**: 30-100 bars (swing patterns)
- **3M/1Y charts**: 50-200 bars (position patterns)

### Visualization Options
Control how patterns are displayed:
```ini
CHART_PATTERN_SHOW_LABELS=1          # Show pattern names
CHART_PATTERN_SHOW_PROJECTIONS=1     # Show price targets
CHART_PATTERN_LABEL_FONT_SIZE=10     # Label text size
```

### Color Customization
Override default pattern colors (hex codes):
```ini
# Triangles
CHART_PATTERN_TRIANGLE_ASCENDING_COLOR=#00FF00      # Green
CHART_PATTERN_TRIANGLE_DESCENDING_COLOR=#FF0000     # Red
CHART_PATTERN_TRIANGLE_SYMMETRICAL_COLOR=#FFA500    # Orange

# Head & Shoulders
CHART_PATTERN_HS_COLOR=#FF1493                      # Deep Pink
CHART_PATTERN_INVERSE_HS_COLOR=#32CD32              # Lime Green

# Double Tops/Bottoms
CHART_PATTERN_DOUBLE_TOP_COLOR=#DC143C              # Crimson
CHART_PATTERN_DOUBLE_BOTTOM_COLOR=#32CD32           # Lime Green

# Channels
CHART_PATTERN_CHANNEL_COLOR=#00BCD4                 # Cyan

# Flags & Pennants
CHART_PATTERN_FLAG_COLOR=#4CAF50                    # Green
```

## Usage in Charts

### Enable Pattern Detection
Include "patterns" in your indicator list:

```python
from catalyst_bot.charts_advanced import generate_multi_panel_chart

chart_path = generate_multi_panel_chart(
    ticker="AAPL",
    timeframe="1D",
    indicators=["vwap", "patterns", "rsi"],
    out_dir="out/charts"
)
```

### Pattern Detection Process
1. **Data Collection**: Fetches OHLCV data for specified timeframe
2. **Pattern Scanning**: Runs detection algorithms on price data
3. **Confidence Filtering**: Applies minimum confidence threshold
4. **Caching**: Stores results for 5 minutes to reduce computation
5. **Visualization**: Overlays detected patterns on chart

### Pattern Output Structure
Each detected pattern includes:
```python
{
    "type": "ascending_triangle",        # Pattern type
    "confidence": 0.85,                   # 0.0 to 1.0
    "start_idx": 0,                       # Starting candle index
    "end_idx": 25,                        # Ending candle index
    "key_levels": {                       # Pattern-specific levels
        "resistance": 150.50,
        "support_slope": 0.25,
        "current_price": 148.75
    },
    "target": 155.00,                     # Projected price target
    "description": "Ascending triangle with resistance at $150.50, target $155.00"
}
```

## Visual Guide

### Pattern Visualization Elements
1. **Trendlines**: Connect key points defining the pattern
2. **Markers**: Highlight critical points (shoulders, peaks, troughs)
3. **Labels**: Pattern name and confidence score
4. **Projection Lines**: Dashed lines showing price targets
5. **Color Coding**:
   - Green: Bullish patterns
   - Red: Bearish patterns
   - Orange/Yellow: Neutral patterns

### Reading Pattern Overlays
- **Solid Lines**: Confirmed pattern boundaries
- **Dashed Lines**: Projected breakout levels
- **Markers**: Key reversal or continuation points
- **Text Boxes**: Pattern identification and targets

## Performance Notes

### Processing Time
- Pattern detection adds approximately 0.5-1.0 seconds per chart
- Caching reduces subsequent requests to ~0.1 seconds
- Cache validity: 5 minutes

### Accuracy Considerations
- **Confidence scores** indicate pattern quality, not success probability
- **Historical patterns** are most reliable when fully formed
- **In-progress patterns** may change as new data arrives
- **Volume confirmation** increases pattern reliability

### Best Practices
1. **Combine with other indicators**: Use RSI, MACD, volume for confirmation
2. **Consider market context**: Patterns more reliable in trending markets
3. **Wait for breakout confirmation**: Don't trade on pattern formation alone
4. **Adjust sensitivity**: Lower for swing trading, higher for day trading
5. **Review historical accuracy**: Backtest patterns on specific tickers

## Troubleshooting

### No Patterns Detected
- **Lower sensitivity**: Reduce CHART_PATTERN_SENSITIVITY to 0.4-0.5
- **Increase lookback**: Raise CHART_PATTERN_LOOKBACK_MAX to 150-200
- **Check data quality**: Ensure sufficient price history available
- **Verify toggles**: Confirm pattern types are enabled (=1)

### Too Many False Positives
- **Raise sensitivity**: Increase CHART_PATTERN_SENSITIVITY to 0.7-0.8
- **Reduce lookback**: Lower CHART_PATTERN_LOOKBACK_MAX to 50-75
- **Enable specific patterns**: Disable unreliable pattern types
- **Add confirmations**: Require volume or momentum confirmation

### Pattern Not Visible on Chart
- **Check master toggle**: Ensure CHART_PATTERN_RECOGNITION=1
- **Verify indicators**: Include "patterns" in indicator list
- **Check labels toggle**: Confirm CHART_PATTERN_SHOW_LABELS=1
- **Review logs**: Check for pattern detection errors

## Examples

### Conservative Configuration (High Confidence)
```ini
CHART_PATTERN_RECOGNITION=1
CHART_PATTERN_SENSITIVITY=0.75
CHART_PATTERN_LOOKBACK_MIN=30
CHART_PATTERN_LOOKBACK_MAX=80
CHART_PATTERNS_TRIANGLES=1
CHART_PATTERNS_HEAD_SHOULDERS=1
CHART_PATTERNS_DOUBLE_TOPS=0        # Disable double tops
CHART_PATTERNS_CHANNELS=0           # Disable channels
CHART_PATTERNS_FLAGS=0              # Disable flags
```

### Aggressive Configuration (More Patterns)
```ini
CHART_PATTERN_RECOGNITION=1
CHART_PATTERN_SENSITIVITY=0.4
CHART_PATTERN_LOOKBACK_MIN=15
CHART_PATTERN_LOOKBACK_MAX=150
CHART_PATTERNS_TRIANGLES=1
CHART_PATTERNS_HEAD_SHOULDERS=1
CHART_PATTERNS_DOUBLE_TOPS=1
CHART_PATTERNS_CHANNELS=1
CHART_PATTERNS_FLAGS=1
```

### Day Trading Configuration (Intraday)
```ini
CHART_PATTERN_RECOGNITION=1
CHART_PATTERN_SENSITIVITY=0.6
CHART_PATTERN_LOOKBACK_MIN=10
CHART_PATTERN_LOOKBACK_MAX=50
CHART_PATTERNS_TRIANGLES=1
CHART_PATTERNS_FLAGS=1              # Flags good for intraday
CHART_PATTERNS_HEAD_SHOULDERS=0     # Less reliable intraday
CHART_PATTERNS_CHANNELS=1
```

## API Reference

### Pattern Detection Functions

```python
from catalyst_bot.indicators.patterns import (
    detect_triangles,
    detect_head_shoulders,
    detect_double_tops_bottoms,
    detect_channels,
    detect_flags_pennants,
    detect_all_patterns
)

# Detect all patterns at once
patterns = detect_all_patterns(
    prices=[100, 105, 102, ...],
    highs=[101, 106, 103, ...],
    lows=[99, 104, 101, ...],
    volumes=[1000000, 1200000, ...],
    min_confidence=0.6
)

# Detect specific pattern type
triangles = detect_triangles(
    prices=[...],
    highs=[...],
    lows=[...],
    min_touches=3,
    lookback=20
)
```

## Resources

### Further Reading
- Technical Analysis of Financial Markets by John Murphy
- Encyclopedia of Chart Patterns by Thomas Bulkowski
- Trading Classic Chart Patterns by Thomas Bulkowski

### Pattern Statistics
Based on historical data:
- **Triangles**: ~65-70% breakout success rate
- **Head & Shoulders**: ~80% reversal success rate
- **Double Tops/Bottoms**: ~60-65% reversal success rate
- **Channels**: Best for range trading, variable breakout success
- **Flags/Pennants**: ~70% continuation success rate

### Community
- Report pattern detection issues on GitHub
- Share configuration optimizations in Discord
- Contribute pattern improvements via pull requests

---

**Last Updated**: 2025-10-24
**Version**: 1.0
**Compatibility**: Catalyst-Bot v3.0+
