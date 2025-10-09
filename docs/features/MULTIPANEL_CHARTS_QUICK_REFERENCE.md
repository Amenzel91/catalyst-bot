# Multi-Panel Charts - Quick Reference Guide

**Phase 3: WeBull Enhancement - Panel Layouts**

---

## 🚀 Quick Start

### Basic Usage
```python
from catalyst_bot.charts import render_multipanel_chart

# Generate 4-panel WeBull-style chart
chart = render_multipanel_chart("AAPL", indicators=["vwap", "rsi", "macd"])
```

---

## 📊 Panel Layouts

### 4-Panel Layout (Full)
**Indicators:** `["vwap", "rsi", "macd"]` or `["bollinger", "rsi", "macd"]`

```
┌─────────────────┐
│ Price (60%)     │  ← Candlesticks + VWAP/BB + S/R
├─────────────────┤
│ Volume (15%)    │  ← Volume bars
├─────────────────┤
│ RSI (12.5%)     │  ← RSI with 30/70 lines
├─────────────────┤
│ MACD (12.5%)    │  ← MACD with zero line
└─────────────────┘
```

### 3-Panel Layout (RSI Only)
**Indicators:** `["vwap", "rsi"]`

```
┌─────────────────┐
│ Price (60%)     │
├─────────────────┤
│ Volume (15%)    │
├─────────────────┤
│ RSI (25%)       │  ← Gets extra space
└─────────────────┘
```

### 3-Panel Layout (MACD Only)
**Indicators:** `["vwap", "macd"]`

```
┌─────────────────┐
│ Price (60%)     │
├─────────────────┤
│ Volume (15%)    │
├─────────────────┤
│ MACD (25%)      │  ← Gets extra space
└─────────────────┘
```

### 2-Panel Layout (Price + Volume)
**Indicators:** `["vwap", "bollinger"]` (no oscillators)

```
┌─────────────────┐
│ Price (60%)     │
├─────────────────┤
│ Volume (40%)    │  ← Gets extra space
└─────────────────┘
```

---

## ⚙️ Configuration (.env)

### Panel Ratios
```ini
# Default WeBull ratios (price:volume:rsi:macd = 6:1.5:1.25:1.25)
CHART_PANEL_RATIOS=6,1.5,1.25,1.25

# Custom ratios (example: larger RSI panel)
CHART_PANEL_RATIOS=6,1.5,2,1
```

### Panel Enable/Disable
```ini
CHART_RSI_PANEL=1      # 1=enabled, 0=disabled
CHART_MACD_PANEL=1
CHART_VOLUME_PANEL=1
```

### Panel Colors
```ini
CHART_RSI_COLOR=#00BCD4               # Cyan
CHART_MACD_LINE_COLOR=#2196F3         # Blue
CHART_MACD_SIGNAL_COLOR=#FF5722       # Orange-red
CHART_VOLUME_UP_COLOR=#3dc98570       # Green with 70% opacity
CHART_VOLUME_DOWN_COLOR=#ef4f6070     # Red with 70% opacity
```

### Panel Styling
```ini
CHART_PANEL_SPACING=0.05    # Spacing between panels (0.0-0.2)
CHART_PANEL_BORDERS=1       # 1=show borders, 0=hide
```

---

## 🎨 Reference Lines

### RSI Panel (Automatic)
- **70:** Red dashed line (overbought)
- **30:** Green dashed line (oversold)

### MACD Panel (Automatic)
- **0:** Gray solid line (zero crossover)

These lines are added automatically when the respective panels are enabled.

---

## 🔧 API Reference

### render_multipanel_chart()
```python
def render_multipanel_chart(
    ticker: str,
    timeframe: str = "1D",
    indicators: Optional[List[str]] = None,
    out_dir: Path | str = "out/charts",
) -> Optional[Path]:
    """
    Render WeBull-style multi-panel chart.

    Args:
        ticker: Stock symbol
        timeframe: Chart timeframe (default "1D")
        indicators: List of indicators (default ["vwap", "rsi", "macd"])
        out_dir: Output directory

    Returns:
        Path to generated PNG or None on error
    """
```

### render_chart_with_panels()
```python
def render_chart_with_panels(
    ticker: str,
    df: pd.DataFrame,
    indicators: Optional[List[str]] = None,
    support_levels: Optional[List[Dict]] = None,
    resistance_levels: Optional[List[Dict]] = None,
    out_dir: Path | str = "out/charts",
) -> Optional[Path]:
    """
    Lower-level panel rendering with custom DataFrame.

    Args:
        ticker: Stock symbol
        df: DataFrame with OHLCV data
        indicators: Indicator list
        support_levels: S/R support levels
        resistance_levels: S/R resistance levels
        out_dir: Output directory

    Returns:
        Path to generated PNG or None on error
    """
```

---

## 📋 Supported Indicators

### Price Panel (Panel 0)
- `"vwap"` - Volume-Weighted Average Price
- `"bollinger"` or `"bb"` - Bollinger Bands
- `"support_resistance"` or `"sr"` - S/R levels
- `"fibonacci"` or `"fib"` - Fibonacci retracements

### Oscillator Panels
- `"rsi"` - Relative Strength Index (Panel 2)
- `"macd"` - MACD with signal line (Panel 3)

Volume panel is always included automatically.

---

## 🧪 Testing

### Run Test Suite
```bash
python test_multipanel_charts.py
```

### Expected Output
```
======================================================================
MULTI-PANEL CHART TEST SUITE (Phase 3: WeBull Enhancement)
======================================================================

Results: 11/11 tests passed (100%)
ALL TESTS PASSED!
```

---

## 📝 Code Examples

### Example 1: Standard 4-Panel Chart
```python
from catalyst_bot.charts import render_multipanel_chart

chart = render_multipanel_chart(
    ticker="AAPL",
    indicators=["vwap", "rsi", "macd"]
)

if chart:
    print(f"Chart saved to: {chart}")
```

### Example 2: Custom Indicators
```python
# Include Bollinger Bands and Fibonacci
chart = render_multipanel_chart(
    ticker="TSLA",
    indicators=["bollinger", "fibonacci", "rsi", "macd"]
)
```

### Example 3: RSI Only (3-Panel)
```python
# Price + Volume + RSI (no MACD)
chart = render_multipanel_chart(
    ticker="SPY",
    indicators=["vwap", "rsi"]
)
```

### Example 4: Price Analysis Only (2-Panel)
```python
# No oscillators, just price indicators
chart = render_multipanel_chart(
    ticker="QQQ",
    indicators=["vwap", "bollinger", "sr"]
)
```

### Example 5: Custom DataFrame
```python
from catalyst_bot.charts import render_chart_with_panels
from catalyst_bot import market

# Fetch custom data
df = market.get_intraday("NVDA", interval="15min")

# Add your custom indicators to df
df["custom_ma"] = df["Close"].rolling(20).mean()

# Render with panels
chart = render_chart_with_panels(
    ticker="NVDA",
    df=df,
    indicators=["vwap", "rsi", "macd"]
)
```

---

## 🐛 Troubleshooting

### Issue: Panel ratios not applied
**Solution:** Check `CHART_PANEL_RATIOS` format
```ini
# Correct (comma-separated, no spaces)
CHART_PANEL_RATIOS=6,1.5,1.25,1.25

# Incorrect (spaces cause parsing errors)
CHART_PANEL_RATIOS=6, 1.5, 1.25, 1.25
```

### Issue: Reference lines not showing
**Solution:** Ensure panels are enabled
```ini
CHART_RSI_PANEL=1
CHART_MACD_PANEL=1
```

### Issue: Chart generation returns None
**Solutions:**
1. Check if market data is available (market hours)
2. Verify matplotlib/mplfinance installed
3. Check logs for specific error messages
4. Ensure ticker symbol is valid

---

## 📚 Additional Resources

- **Full Implementation Report:** `PHASE_3_MULTIPANEL_IMPLEMENTATION_REPORT.md`
- **Enhancement Plan:** `WEBULL_CHART_ENHANCEMENT_PLAN.md`
- **Test Suite:** `test_multipanel_charts.py`
- **Source Code:**
  - `src/catalyst_bot/charts.py`
  - `src/catalyst_bot/chart_panels.py`

---

## 🎯 Pro Tips

1. **Adaptive Layouts:** Don't specify indicators you don't need. The system adapts panel count automatically.

2. **Custom Colors:** Override default colors via environment variables for brand consistency.

3. **Performance:** Use cached charts when possible. Multi-panel rendering takes ~1-3 seconds.

4. **Testing:** Always run `test_multipanel_charts.py` after configuration changes.

5. **Mobile:** Panel layouts are mobile-optimized with 12pt minimum font size.

---

## 🔗 Quick Links

| Task | Command |
|------|---------|
| Generate chart | `render_multipanel_chart("AAPL", indicators=["vwap","rsi","macd"])` |
| Run tests | `python test_multipanel_charts.py` |
| Check config | `from catalyst_bot.chart_panels import validate_panel_configuration; validate_panel_configuration()` |
| Get colors | `from catalyst_bot.chart_panels import get_panel_color_scheme; get_panel_color_scheme()` |

---

**Quick Reference v1.0 - Phase 3 Complete** ✅
