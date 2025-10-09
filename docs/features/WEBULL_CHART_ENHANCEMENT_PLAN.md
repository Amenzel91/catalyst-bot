# WeBull-Style Chart Enhancement Plan

**Date:** October 6, 2025
**Document:** Analysis of "Creating WeBull-Style Stock Charts for Discord Bots.md"
**Goal:** Enhance chart quality to match WeBull aesthetics + add dropdown toggles for indicators

---

## 📊 Current State Analysis

### What We Have
- **Chart Engine:** QuickChart (Chart.js v3) via `charts_quickchart.py`
- **Fallback:** mplfinance via `charts.py` (basic implementation)
- **Indicators:** VWAP, RSI, MACD, Volume, Bollinger Bands, Fibonacci, Support/Resistance, Volume Profile
- **Templates:** 8 predefined chart templates (`chart_templates.py`)
- **Caching:** SQLite-based chart caching (`chart_cache.py`)
- **Parallel Generation:** ThreadPoolExecutor for multi-timeframe charts

### What's Missing for WeBull-Style Quality
1. **Professional Dark Theme** - Current charts don't match WeBull's signature aesthetic
2. **Advanced mplfinance Implementation** - Fallback is basic, not production-grade
3. **Interactive Discord Controls** - No dropdown menus to toggle indicators
4. **Mobile-Optimized Text Sizing** - May be too small for 320px mobile screens
5. **Multi-Panel Layouts** - No separate panels for volume/indicators
6. **Pattern Recognition** - Chart patterns (triangles, head & shoulders, etc.) not implemented
7. **Advanced Volume Visualization** - Volume profile not displayed as horizontal bars

---

## 🎨 Key Insights from WeBull Document

### 1. mplfinance is the Winner for WeBull Aesthetics

**Why mplfinance:**
- Purpose-built for financial charts
- **0.5-1.5 second** rendering times
- **100-500KB** file sizes (vs 2-5s for Plotly)
- Native PNG export (no Kaleido dependency)
- Built-in dark themes: `nightclouds`, `binance-dark`
- Simple 3-line implementation for candlestick + volume

**Recommendation:** Upgrade our `charts.py` implementation to production-grade mplfinance

---

### 2. Discord Dark Theme Optimization

**WeBull/Binance Dark Color Scheme:**
```python
WEBULL_STYLE = {
    # Background
    'base_mpl_style': 'dark_background',
    'facecolor': '#1b1f24',      # Chart background
    'edgecolor': '#2c2e31',      # Border
    'figcolor': '#1b1f24',       # Figure background

    # Candles
    'marketcolors': {
        'candle': {'up': '#3dc985', 'down': '#ef4f60'},
        'edge': {'up': '#3dc985', 'down': '#ef4f60'},
        'wick': {'up': '#3dc985', 'down': '#ef4f60'},
        'volume': {'up': '#3dc98570', 'down': '#ef4f6070'},
        'alpha': 1.0
    },

    # Grid
    'gridcolor': '#2c2e31',
    'gridstyle': '--',
    'gridaxis': 'both',

    # Text
    'y_on_right': True,
    'rc': {
        'axes.labelcolor': '#cccccc',
        'axes.edgecolor': '#2c2e31',
        'xtick.color': '#cccccc',
        'ytick.color': '#cccccc',
        'axes.titlecolor': '#ffffff',
        'axes.labelsize': 12,  # Mobile-readable
        'axes.titlesize': 16,  # Clear titles
        'font.size': 12
    }
}
```

**Discord Native Integration:**
```python
DISCORD_COLORS = {
    'positive': '#43B581',   # Discord green (for gains)
    'negative': '#F04747',   # Discord red (for losses)
    'blurple': '#5865F2',    # Discord brand color
    'background': '#36393F', # Discord dark background
    'text': '#DCDDDE',       # Discord text
    'subtle_grid': '#4E5058' # Subtle grid lines
}
```

---

### 3. Mobile-First Design Rules

**Text Sizing (Critical for 320px Screens):**
- **Axis Labels:** 12pt minimum (10pt becomes unreadable on mobile)
- **Titles:** 14-16pt (bold weight improves legibility)
- **Annotations:** 10-11pt bold (vs 9pt regular)

**Line Weights:**
- **Price Lines:** 2-3px
- **Grid Lines:** 0.5-1px (subtle, not competing)
- **Indicator Lines:** 1-2px

**Aspect Ratios:**
- **Single Panel:** 16:9 (1200x675 or 1600x900)
- **Multi-Panel (with volume/indicators):** 14:8 or 12:8
- **Test on:** Actual mobile devices (not just desktop)

---

### 4. Performance Optimization Stack

**From the Document:**

1. **Aggressive Caching** (80-90% response time reduction)
   - In-memory: lru_cache for frequent symbols (<100ms)
   - Redis: 5-15 min TTL for intraday, 1-24 hr for daily
   - Already have: SQLite cache in `chart_cache.py` ✅

2. **Async Patterns**
   - aiohttp for data fetching (not blocking requests)
   - ThreadPoolExecutor for matplotlib rendering ✅ (already have)
   - BytesIO for in-memory chart generation ✅

3. **Memory Efficiency**
   - Agg backend for headless rendering ✅
   - plt.close() after each chart ✅
   - Downsampling for large datasets

**Target Response Times:**
- Cached charts: <1s
- Simple generation: 1-3s
- Complex technical analysis: 3-5s max

---

### 5. Multi-Panel Layouts (Critical for WeBull Look)

**Traditional WeBull Layout:**
```
┌─────────────────────────────┐
│  Title + Price Info         │
├─────────────────────────────┤
│                             │
│  Candlestick + Indicators   │ ← Main price panel (60% height)
│  (VWAP, Bollinger, etc.)    │
│                             │
├─────────────────────────────┤
│  Volume Bars                │ ← Volume panel (15% height)
├─────────────────────────────┤
│  RSI                        │ ← Oscillator panel (12.5% height)
├─────────────────────────────┤
│  MACD                       │ ← Momentum panel (12.5% height)
└─────────────────────────────┘
```

**mplfinance Implementation:**
```python
import mplfinance as mpf

# Define panels
apds = [
    mpf.make_addplot(vwap, panel=0, color='orange', width=2),
    mpf.make_addplot(bb_upper, panel=0, color='#2196F3', linestyle='--'),
    mpf.make_addplot(bb_lower, panel=0, color='#2196F3', linestyle='--'),
    mpf.make_addplot(rsi, panel=1, color='#00BCD4', ylabel='RSI'),
    mpf.make_addplot(macd_line, panel=2, color='#2196F3', ylabel='MACD'),
    mpf.make_addplot(macd_signal, panel=2, color='#FF5722'),
]

mpf.plot(
    df,
    type='candle',
    style=webull_style,
    addplot=apds,
    volume=True,  # Volume in separate panel
    panel_ratios=(6, 1.5, 1.25, 1.25),  # Ratio for each panel
    figsize=(16, 10)
)
```

---

### 6. Support/Resistance & Pattern Recognition

**Current Implementation:**
- ✅ S/R detection in `indicators/support_resistance.py`
- ✅ Integration in `chart_indicators_integration.py`
- ❌ Not prominently displayed on charts

**WeBull-Style Enhancement:**
```python
# Strong horizontal lines at key levels
for level in support_levels:
    plt.axhline(
        y=level['price'],
        color='#4CAF50',  # Green for support
        linestyle='-',
        linewidth=2 + (level['strength'] / 50),  # Thicker = stronger
        alpha=0.7,
        label=f"S: ${level['price']:.2f}"
    )

for level in resistance_levels:
    plt.axhline(
        y=level['price'],
        color='#F44336',  # Red for resistance
        linestyle='-',
        linewidth=2 + (level['strength'] / 50),
        alpha=0.7,
        label=f"R: ${level['price']:.2f}"
    )
```

**Pattern Recognition (Future Enhancement):**
- Triangles (ascending, descending, symmetrical)
- Head & Shoulders
- Double tops/bottoms
- Channels
- Flags and pennants

---

### 7. Volume Profile Visualization

**Current Implementation:**
- ✅ Calculation in `indicators/volume_profile.py`
- ❌ Only adds POC/VAH/VAL annotations (lines)
- ❌ No horizontal volume bars (true volume profile)

**WeBull-Style Volume Profile:**
```python
# Horizontal volume bars on right side of chart
# This requires custom overlay - complex in Chart.js
# But straightforward in mplfinance:

from mplfinance.original_flavor import candlestick_ohlc
import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(1, 2, gridspec_kw={'width_ratios': [4, 1]})

# Left panel: Candlesticks
candlestick_ohlc(ax1, ohlc_data)

# Right panel: Volume profile (horizontal bars)
ax2.barh(price_levels, volume_at_price, color='#546E7A', alpha=0.6)
ax2.axhline(poc, color='#FF9800', linewidth=3, label='POC')
```

---

## 🔧 Discord Dropdown Menu Integration

### The User's Request: Toggle R/S and Patterns On/Off

**Discord Select Menu Structure:**
```python
# In Discord embed, add select menu components
components = [
    {
        "type": 1,  # Action Row
        "components": [
            {
                "type": 3,  # Select Menu
                "custom_id": f"chart_indicators_{ticker}",
                "placeholder": "Toggle Indicators",
                "min_values": 0,  # Can deselect all
                "max_values": 5,  # Can select up to 5
                "options": [
                    {
                        "label": "Support/Resistance Levels",
                        "value": "sr",
                        "description": "Show S/R lines",
                        "emoji": {"name": "📊"},
                        "default": True  # Enabled by default
                    },
                    {
                        "label": "Bollinger Bands",
                        "value": "bollinger",
                        "description": "20-period BB with 2σ",
                        "emoji": {"name": "📈"},
                        "default": True
                    },
                    {
                        "label": "Fibonacci Levels",
                        "value": "fibonacci",
                        "description": "Auto Fib retracements",
                        "emoji": {"name": "🔢"},
                        "default": False
                    },
                    {
                        "label": "Volume Profile",
                        "value": "volume_profile",
                        "description": "POC + Value Area",
                        "emoji": {"name": "📊"},
                        "default": False
                    },
                    {
                        "label": "Chart Patterns",
                        "value": "patterns",
                        "description": "Triangles, H&S, etc.",
                        "emoji": {"name": "🔺"},
                        "default": False
                    }
                ]
            }
        ]
    }
]
```

**Interaction Handler:**
```python
async def handle_chart_indicator_toggle(interaction):
    """Handle indicator toggle from select menu."""
    # Extract selected indicators
    selected = interaction.data['values']  # ['sr', 'bollinger', 'fibonacci']

    # Extract ticker from custom_id
    ticker = interaction.data['custom_id'].replace('chart_indicators_', '')

    # Regenerate chart with only selected indicators
    chart_url = generate_chart_with_indicators(ticker, indicators=selected)

    # Update the embed with new chart
    await interaction.response.edit_message(
        embed={
            "title": f"{ticker} Chart (Custom Indicators)",
            "image": {"url": chart_url},
            "description": f"Showing: {', '.join(selected)}"
        },
        components=components  # Keep the select menu
    )
```

---

## 🚀 Implementation Plan

### Phase 1: WeBull Dark Theme (Immediate - 2 hours)

**Files to Modify:**
1. `src/catalyst_bot/charts.py` - Upgrade mplfinance implementation
2. `src/catalyst_bot/charts_quickchart.py` - Add WeBull color scheme

**Tasks:**
- [ ] Define `WEBULL_STYLE` dict in `charts.py`
- [ ] Update `render_intraday_chart()` to use WeBull style
- [ ] Add multi-panel support (price + volume + 2 oscillators)
- [ ] Update text sizing (12pt labels, 16pt titles)
- [ ] Test on mobile (320px screenshots)

**Expected Outcome:**
Charts that look like WeBull with dark background, green/red candles, subtle grids

---

### Phase 2: Dropdown Indicator Toggles (Immediate - 3 hours)

**Files to Create/Modify:**
1. `src/catalyst_bot/commands/chart_interactions.py` - New file for select menu handlers
2. `src/catalyst_bot/commands/handlers.py` - Update `handle_chart_command()`
3. `src/catalyst_bot/health_endpoint.py` - Add interaction routing

**Tasks:**
- [ ] Create select menu component builder
- [ ] Implement interaction handler for indicator toggles
- [ ] Add session state to track user's indicator preferences
- [ ] Regenerate charts dynamically based on selection
- [ ] Add caching for common indicator combinations

**Expected Outcome:**
Users can click dropdown below chart to toggle indicators on/off, chart updates instantly

---

### Phase 3: Enhanced Multi-Panel Layouts (Tonight - 2 hours)

**Files to Modify:**
1. `src/catalyst_bot/charts.py` - Add panel layout functions

**Tasks:**
- [ ] Implement 4-panel layout (price, volume, RSI, MACD)
- [ ] Add panel ratio configuration (6:1.5:1.25:1.25)
- [ ] Ensure all indicators render in correct panels
- [ ] Add panel-specific styling

**Expected Outcome:**
Professional multi-panel charts matching WeBull layout

---

### Phase 4: Advanced Features (Weekend)

**Pattern Recognition:**
- [ ] Implement triangle detection
- [ ] Add head & shoulders detection
- [ ] Channel identification
- [ ] Flag/pennant detection

**Volume Profile Enhancement:**
- [ ] True horizontal volume bars (not just POC lines)
- [ ] High Volume Nodes (HVN) highlighting
- [ ] Low Volume Nodes (LVN) highlighting

**Mobile Optimization:**
- [ ] Test all charts on mobile devices
- [ ] Adjust text sizes if needed
- [ ] Verify grid visibility at 320px

---

## 📝 Configuration (.env Variables)

**New Environment Variables:**
```ini
# Chart Style
CHART_STYLE=webull  # Options: webull, binance, traditional
CHART_THEME=dark    # Options: dark, light

# Text Sizing
CHART_AXIS_LABEL_SIZE=12
CHART_TITLE_SIZE=16
CHART_ANNOTATION_SIZE=10

# Multi-Panel Layout
CHART_USE_PANELS=1
CHART_PANEL_RATIOS=6,1.5,1.25,1.25  # price,volume,rsi,macd

# Default Indicators (for non-interactive charts)
CHART_DEFAULT_INDICATORS=sr,bollinger,vwap

# Indicator Toggles (1=show by default in dropdown)
CHART_SHOW_SUPPORT_RESISTANCE=1
CHART_SHOW_BOLLINGER=1
CHART_SHOW_FIBONACCI=0
CHART_SHOW_VOLUME_PROFILE=0
CHART_SHOW_PATTERNS=0

# Discord Integration
CHART_ENABLE_DROPDOWNS=1  # Enable select menus
CHART_DROPDOWN_MAX_OPTIONS=5
```

---

## 🎯 Success Criteria

### Visual Quality
- [ ] Charts match WeBull dark aesthetic
- [ ] Green/red candles with proper #3dc985/#ef4f60 colors
- [ ] Subtle grid lines (#2c2e31) that don't compete with data
- [ ] Clean, professional appearance

### Mobile Readability
- [ ] All text readable at 320px width
- [ ] Labels at 12pt or larger
- [ ] Titles at 16pt bold
- [ ] Test on actual mobile devices

### Interactive Controls
- [ ] Dropdown menu appears below every chart
- [ ] 5 toggle options: S/R, Bollinger, Fibonacci, Volume Profile, Patterns
- [ ] Chart regenerates within 2 seconds of selection
- [ ] User preferences cached per session

### Performance
- [ ] Cached charts: <1s response
- [ ] New charts: <3s response
- [ ] No memory leaks (plt.close() after every chart)
- [ ] Caching reduces API load by 70%+

---

## 📚 Code Examples

### Example 1: WeBull-Style mplfinance Chart

```python
import mplfinance as mpf
import pandas as pd

# Define WeBull style
webull_style = mpf.make_mpf_style(
    base_mpf_style='nightclouds',
    marketcolors=mpf.make_marketcolors(
        up='#3dc985',
        down='#ef4f60',
        edge={'up':'#3dc985', 'down':'#ef4f60'},
        wick={'up':'#3dc985', 'down':'#ef4f60'},
        volume={'up':'#3dc98570', 'down':'#ef4f6070'},
    ),
    facecolor='#1b1f24',
    edgecolor='#2c2e31',
    gridcolor='#2c2e31',
    gridstyle='--',
    y_on_right=True,
    rc={
        'axes.labelcolor': '#cccccc',
        'xtick.color': '#cccccc',
        'ytick.color': '#cccccc',
        'axes.titlecolor': '#ffffff',
        'font.size': 12
    }
)

# Generate chart with indicators
apds = []

if 'vwap' in indicators:
    apds.append(mpf.make_addplot(df['vwap'], panel=0, color='#FF9800', width=2))

if 'bollinger' in indicators:
    apds.append(mpf.make_addplot(df['bb_upper'], panel=0, color='#2196F3', linestyle='--'))
    apds.append(mpf.make_addplot(df['bb_lower'], panel=0, color='#2196F3', linestyle='--'))

if 'rsi' in indicators:
    apds.append(mpf.make_addplot(df['rsi'], panel=1, color='#00BCD4', ylabel='RSI', ylim=(0,100)))

if 'macd' in indicators:
    apds.append(mpf.make_addplot(df['macd'], panel=2, color='#2196F3', ylabel='MACD'))
    apds.append(mpf.make_addplot(df['macd_signal'], panel=2, color='#FF5722'))

# Add S/R levels
hlines = {}
if 'sr' in indicators:
    for i, level in enumerate(support_levels):
        hlines[f's{i}'] = dict(y=level['price'], color='#4CAF50', linestyle='-', linewidth=2)
    for i, level in enumerate(resistance_levels):
        hlines[f'r{i}'] = dict(y=level['price'], color='#F44336', linestyle='-', linewidth=2)

# Render
fig, axes = mpf.plot(
    df,
    type='candle',
    style=webull_style,
    addplot=apds if apds else None,
    hlines=hlines if hlines else None,
    volume=True,
    panel_ratios=(6, 1.5, 1.25, 1.25) if len(apds) > 0 else (6, 1.5),
    figsize=(16, 10),
    returnfig=True,
    savefig='chart.png'
)
plt.close(fig)
```

### Example 2: Discord Select Menu for Chart

```python
def build_chart_select_menu(ticker: str, default_indicators: List[str]) -> Dict:
    """Build Discord select menu for indicator toggles."""
    return {
        "type": 1,
        "components": [
            {
                "type": 3,
                "custom_id": f"chart_toggle_{ticker}",
                "placeholder": "📊 Toggle Indicators",
                "min_values": 0,
                "max_values": 5,
                "options": [
                    {
                        "label": "Support/Resistance",
                        "value": "sr",
                        "description": "Key price levels",
                        "emoji": {"name": "📏"},
                        "default": "sr" in default_indicators
                    },
                    {
                        "label": "Bollinger Bands",
                        "value": "bollinger",
                        "description": "Volatility bands",
                        "emoji": {"name": "📈"},
                        "default": "bollinger" in default_indicators
                    },
                    {
                        "label": "Fibonacci",
                        "value": "fibonacci",
                        "description": "Retracement levels",
                        "emoji": {"name": "🔢"},
                        "default": "fibonacci" in default_indicators
                    },
                    {
                        "label": "Volume Profile",
                        "value": "volume_profile",
                        "description": "POC + Value Area",
                        "emoji": {"name": "📊"},
                        "default": "volume_profile" in default_indicators
                    },
                    {
                        "label": "Patterns",
                        "value": "patterns",
                        "description": "Auto-detected patterns",
                        "emoji": {"name": "🔺"},
                        "default": "patterns" in default_indicators
                    }
                ]
            }
        ]
    }
```

---

## 🔄 Testing Checklist

- [ ] Generate chart on desktop - verify WeBull colors
- [ ] View chart on mobile (320px) - verify text readable
- [ ] Test dropdown menu - verify all 5 indicators toggle correctly
- [ ] Test with all indicators enabled - verify no overlap
- [ ] Test with all indicators disabled - verify clean candlestick chart
- [ ] Benchmark response times - verify <3s for new charts
- [ ] Check memory usage - verify plt.close() prevents leaks
- [ ] Test caching - verify repeated requests use cache
- [ ] Verify grid lines subtle (#2c2e31) not competing with data
- [ ] Verify Discord dark mode integration (background matches)

---

## 📈 Expected Results

**Before (Current):**
- Basic Chart.js candlesticks with simple colors
- Limited indicator visibility
- No interactive controls
- Generic appearance

**After (WeBull-Enhanced):**
- Professional dark theme matching WeBull/Binance
- Multi-panel layout with proper spacing
- Interactive dropdown to toggle indicators
- Mobile-optimized text and layout
- Prominent S/R levels and patterns
- True volume profile visualization
- Sub-3-second chart generation
- 70%+ cache hit rate

---

*This plan provides a clear roadmap to transform the bot's charts from basic to professional WeBull-quality with interactive Discord controls.*
