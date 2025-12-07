# Chart Indicator Integration Patterns - Quick Reference

---

## Pattern Comparison Table

| Pattern Type | Examples | Panel | Color | Line Style | Alpha | Error Handling | Complexity |
|-------------|----------|-------|-------|------------|-------|----------------|------------|
| **Simple Overlay** | VWAP | 0 | `#FF9800` | `-` | 1.0 | Try-except with log | ⭐ Easy |
| **Multi-Line Overlay** | Bollinger Bands | 0 | `#9C27B0` | `--` | 0.7 | Try-except per line | ⭐⭐ Medium |
| **Oscillator Panel** | RSI, MACD | 2+ | Various | `-` | 1.0 | Try-except with log | ⭐⭐ Medium |
| **Horizontal Lines** | Support/Resistance | 0 | `#4CAF50`/`#F44336` | `-` | 0.7 | Try-except with log | ⭐⭐⭐ Complex |

---

## Code Pattern Templates

### 1. Simple Overlay (VWAP Style)

```python
# Use this for: Moving averages, VWAP, single-line indicators
if "indicator" in indicators and "indicator_col" in df.columns:
    try:
        apds.append(
            mpf.make_addplot(
                df["indicator_col"],
                panel=0,
                color=INDICATOR_COLORS["indicator"],
                width=2,
                label="Indicator Name",
            )
        )
    except Exception as err:
        log.warning("indicator_addplot_failed err=%s", str(err))
```

**When to use:** Single line overlaying price action

**Pros:** Simple, fast, clear
**Cons:** Can clutter chart with too many overlays

---

### 2. Multi-Line Overlay (Bollinger Bands Style)

```python
# Use this for: Bollinger Bands, Keltner Channels, Fibonacci
if "indicator" in indicators:
    # Upper band
    if "indicator_upper" in df.columns:
        try:
            apds.append(mpf.make_addplot(
                df["indicator_upper"],
                panel=0,
                color=INDICATOR_COLORS["indicator"],
                linestyle="--",
                width=1,
                alpha=0.7,
            ))
        except Exception:
            pass

    # Middle band
    if "indicator_middle" in df.columns:
        try:
            apds.append(mpf.make_addplot(
                df["indicator_middle"],
                panel=0,
                color=INDICATOR_COLORS["indicator"],
                width=1,
                alpha=0.5,
            ))
        except Exception:
            pass

    # Lower band
    if "indicator_lower" in df.columns:
        try:
            apds.append(mpf.make_addplot(
                df["indicator_lower"],
                panel=0,
                color=INDICATOR_COLORS["indicator"],
                linestyle="--",
                width=1,
                alpha=0.7,
            ))
        except Exception:
            pass
```

**When to use:** Multiple related lines (bands, channels)

**Pros:** Groups related indicators, uses transparency
**Cons:** More complex, multiple try-except blocks

---

### 3. Oscillator Panel (RSI Style)

```python
# Use this for: RSI, Stochastic, CCI, Williams %R
if "indicator" in indicators and "indicator_col" in df.columns:
    # Determine panel number
    panel_num = 2
    if "rsi" in indicators and "rsi" in df.columns:
        panel_num = 3  # Push to next panel if RSI already present

    try:
        apds.append(
            mpf.make_addplot(
                df["indicator_col"],
                panel=panel_num,
                color=INDICATOR_COLORS["indicator"],
                ylabel="Indicator Name",
                ylim=(min_val, max_val),  # e.g., (0, 100) for RSI
                width=2,
            )
        )
    except Exception as err:
        log.warning("indicator_addplot_failed err=%s", str(err))
```

**When to use:** Bounded oscillators that need separate panel

**Pros:** Doesn't clutter price panel, uses fixed scale
**Cons:** Reduces price panel size, requires panel coordination

**Important:** Update panel_ratios in `chart_panels.calculate_panel_ratios()`

---

### 4. Horizontal Lines (Support/Resistance Style)

```python
# Use this for: S/R levels, Pivot Points, Fibonacci, Price Targets

# Step 1: Build hlines dict (before chart creation)
hlines = {}
for i, level in enumerate(levels):
    hlines[f"level_{i}"] = dict(
        y=level['price'],
        color=INDICATOR_COLORS["indicator"],
        linestyle="--",
        linewidth=1.5,
        alpha=0.7,
    )

# Step 2: Create chart
fig, axes = mpf.plot(df, **plot_kwargs)

# Step 3: Add lines manually (after chart creation)
if hlines:
    try:
        price_ax = axes[0] if hasattr(axes, "__iter__") else axes

        for key, val in hlines.items():
            price_ax.axhline(
                y=val["y"],
                color=val["color"],
                linestyle=val["linestyle"],
                linewidth=val["linewidth"],
                alpha=val["alpha"],
            )
        log.debug("added_lines count=%d", len(hlines))
    except Exception as err:
        log.warning("lines_failed err=%s", str(err))
```

**When to use:** Static price levels, support/resistance, targets

**Pros:** Clear, non-intrusive, strength-weighted styling
**Cons:** More complex (two-step process), requires post-render addition

**Why not use mplfinance hlines param?** Validator issues cause crashes - manual axhline is more reliable

---

## Decision Tree: Which Pattern to Use?

```
Does indicator overlay on price?
├─ YES
│  ├─ Single line? → Use Pattern 1 (Simple Overlay)
│  ├─ Multiple lines (bands)? → Use Pattern 2 (Multi-Line Overlay)
│  └─ Horizontal levels? → Use Pattern 4 (Horizontal Lines)
└─ NO (separate panel)
   └─ Oscillator (bounded range)? → Use Pattern 3 (Oscillator Panel)
```

---

## Color Selection Guide

### For Overlays (Panel 0)
- **High contrast required** - must stand out against candles
- **Use bold colors:** Orange, Cyan, Purple, Yellow
- **Avoid:** Red, Green (used for candles)

### For Oscillators (Panel 2+)
- **Medium contrast acceptable** - dedicated panel
- **Use distinct colors:** Cyan, Blue, Orange-Red
- **Consistent across indicators:** MACD always blue/orange-red

### For Horizontal Lines
- **Semantic colors preferred:**
  - Support = Green (`#4CAF50`)
  - Resistance = Red (`#F44336`)
  - Neutral/Fibonacci = Purple (`#9C27B0`)
- **Use transparency:** `alpha=0.6-0.7` to avoid obscuring candles

### Color Palette Reference

```python
INDICATOR_COLORS = {
    # Overlays (Panel 0)
    "vwap": "#FF9800",           # Orange - high visibility
    "bb_upper": "#9C27B0",       # Purple - bands
    "bb_middle": "#9C27B0",      # Purple - bands
    "bb_lower": "#9C27B0",       # Purple - bands

    # Oscillators (Panel 2+)
    "rsi": "#00BCD4",            # Cyan - bounded indicator
    "macd_line": "#2196F3",      # Blue - trend line
    "macd_signal": "#FF5722",    # Orange-Red - signal line

    # Horizontal Lines (Panel 0)
    "support": "#4CAF50",        # Green - semantic
    "resistance": "#F44336",     # Red - semantic

    # Proposed New Indicators
    "fibonacci": "#9C27B0",      # Purple - harmonic analysis
    "volume_profile": "#26C6DA", # Cyan - volume-related
    "pattern_bullish": "#4CAF50",# Green - bullish signals
    "pattern_bearish": "#F44336",# Red - bearish signals
}
```

---

## Error Handling Standards

### Logging Levels

```python
# WARNING - For failures that skip the indicator
log.warning("indicator_addplot_failed err=%s", str(err))

# DEBUG - For successful operations
log.debug("added_sr_lines count=%d", len(hlines))

# INFO - For major milestones
log.info("chart_panels_saved ticker=%s path=%s", sym, img_path)
```

### Exception Handling

```python
# ✅ GOOD - Specific exception, logged, graceful
try:
    apds.append(mpf.make_addplot(...))
except Exception as err:
    log.warning("indicator_failed err=%s", str(err))
    # Chart continues without this indicator

# ❌ BAD - No exception handling
apds.append(mpf.make_addplot(...))  # May crash entire chart!

# ❌ BAD - Silent failure without logging
try:
    apds.append(mpf.make_addplot(...))
except Exception:
    pass  # No one knows what failed!
```

---

## Testing Checklist

For each new indicator:

- [ ] **Calculation Test:** Indicator calculates without errors
- [ ] **Rendering Test:** Indicator renders on chart
- [ ] **Error Handling Test:** Graceful failure on bad data
- [ ] **Color Test:** Color is defined and mobile-readable
- [ ] **Integration Test:** Works with other indicators (no conflicts)
- [ ] **Performance Test:** Renders within 2 seconds

---

## Common Pitfalls

### ❌ Pitfall 1: Not Checking Column Existence

```python
# BAD - May raise KeyError!
if "indicator" in indicators:
    apds.append(mpf.make_addplot(df["indicator_col"], ...))

# GOOD - Safe check
if "indicator" in indicators and "indicator_col" in df.columns:
    apds.append(mpf.make_addplot(df["indicator_col"], ...))
```

### ❌ Pitfall 2: Hardcoded Panel Numbers

```python
# BAD - Breaks if other indicators change
apds.append(mpf.make_addplot(df["rsi"], panel=2, ...))

# GOOD - Calculate panel number dynamically
panel_num = 2
if "rsi" in indicators:
    panel_num = 3
apds.append(mpf.make_addplot(df["macd"], panel=panel_num, ...))
```

### ❌ Pitfall 3: Using mplfinance hlines Parameter

```python
# BAD - Has validator issues
fig, axes = mpf.plot(df, hlines=hlines_dict, ...)

# GOOD - Manual axhline
fig, axes = mpf.plot(df, ...)
for key, val in hlines.items():
    axes[0].axhline(y=val["y"], ...)
```

### ❌ Pitfall 4: No Transparency on Overlays

```python
# BAD - Obscures candles
apds.append(mpf.make_addplot(df["fib"], panel=0, alpha=1.0, ...))

# GOOD - Semi-transparent
apds.append(mpf.make_addplot(df["fib"], panel=0, alpha=0.6, ...))
```

---

## Performance Tips

### Tip 1: Limit Addplot Objects
**Issue:** Too many addplot objects slow rendering

**Solution:** Combine similar lines when possible
```python
# GOOD - One addplot for all Fibonacci levels
fib_data = pd.DataFrame({
    '0.236': [level_236] * len(df),
    '0.382': [level_382] * len(df),
    # ...
})
# Use single addplot with multiple columns
```

### Tip 2: Use .tail() for Calculations
**Issue:** Calculating indicators on full history is slow

**Solution:** Limit lookback window
```python
# Calculate on recent data only
recent_df = df.tail(200)
indicator_values = calculate_indicator(recent_df)
```

### Tip 3: Cache Heavy Calculations
**Issue:** Pattern recognition can be O(n²)

**Solution:** Cache results
```python
@lru_cache(maxsize=128)
def detect_patterns(df_hash):
    # Expensive calculation
    return patterns
```

---

## File Location Reference

**Add Color Constants:**
- `src/catalyst_bot/charts.py` lines 62-73

**Add Indicator Integration:**
- `src/catalyst_bot/charts.py` function `add_indicator_panels()` (lines 218-362)

**Add Horizontal Lines:**
- `src/catalyst_bot/charts.py` function `render_chart_with_panels()` (lines 524-550)

**Panel Configuration:**
- `src/catalyst_bot/chart_panels.py` function `calculate_panel_ratios()` (lines 182-258)

**Create Indicator Calculation:**
- `src/catalyst_bot/indicators/your_indicator.py` (new file)

**Add Tests:**
- `tests/test_chart_indicators.py` (add test class)

---

## Quick Start: Adding Fibonacci

**Estimated Time:** 2-4 hours

### Step 1: Create Calculation Module (30 min)

```bash
# Create file: src/catalyst_bot/indicators/fibonacci.py

def calculate_fibonacci_levels(high: float, low: float) -> Dict[str, float]:
    """Calculate Fibonacci retracement levels."""
    diff = high - low
    return {
        '0.0': high,
        '0.236': high - (diff * 0.236),
        '0.382': high - (diff * 0.382),
        '0.5': high - (diff * 0.5),
        '0.618': high - (diff * 0.618),
        '0.786': high - (diff * 0.786),
        '1.0': low,
    }
```

### Step 2: Add Color (5 min)

```python
# In src/catalyst_bot/charts.py
INDICATOR_COLORS = {
    # ... existing colors
    "fibonacci": "#9C27B0",  # Purple
}
```

### Step 3: Add Integration (60 min)

```python
# In src/catalyst_bot/charts.py, in add_indicator_panels()
if "fibonacci" in indicators:
    try:
        from .indicators.fibonacci import calculate_fibonacci_levels

        high = df['High'].tail(50).max()
        low = df['Low'].tail(50).min()
        fib_levels = calculate_fibonacci_levels(high, low)

        for ratio, price in fib_levels.items():
            apds.append(
                mpf.make_addplot(
                    [price] * len(df),
                    panel=0,
                    color=INDICATOR_COLORS["fibonacci"],
                    linestyle="--",
                    width=1,
                    alpha=0.6,
                )
            )
    except Exception as err:
        log.warning("fibonacci_failed err=%s", str(err))
```

### Step 4: Test (30 min)

```bash
pytest tests/test_chart_indicators.py::TestFibonacciIntegration -v
```

### Step 5: Manual Verification (30 min)

```python
# Create test script: test_fibonacci_manual.py
from catalyst_bot.charts import render_chart_with_panels
from catalyst_bot import market

df = market.get_intraday("AAPL", interval="5min")
chart_path = render_chart_with_panels(
    ticker="AAPL",
    df=df,
    indicators=["vwap", "fibonacci"],
    out_dir="out/charts/test"
)
print(f"Chart saved to: {chart_path}")
```

---

**Quick Reference Complete**
**Use this as a reference when implementing Wave 2 indicators**
