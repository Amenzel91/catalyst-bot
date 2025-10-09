# Chart Enhancement Environment Variables

**Last Updated:** 2025-10-06
**Feature Set:** WeBull Chart Enhancement (Phases 1-4)

This document lists all environment variables for the enhanced WeBull-style chart system with interactive dropdowns, multi-panel layouts, pattern recognition, and volume profile features.

---

## Phase 1: WeBull Dark Theme

### Visual Styling

```bash
# Chart style (webull, yahoo, classic)
CHART_STYLE=webull

# Theme (dark, light)
CHART_THEME=dark

# Text sizing for mobile readability
CHART_AXIS_LABEL_SIZE=12
CHART_TITLE_SIZE=16
CHART_TICK_LABEL_SIZE=10

# Color overrides (optional - defaults to WeBull palette)
CHART_BG_COLOR=#1b1f24
CHART_GRID_COLOR=#2c2e31
CHART_CANDLE_UP_COLOR=#3dc985
CHART_CANDLE_DOWN_COLOR=#ef4f60
```

**Defaults:**
- WeBull background: `#1b1f24`
- WeBull grid: `#2c2e31`
- Up candles: `#3dc985` (green)
- Down candles: `#ef4f60` (red)

---

## Phase 2: Dropdown Menu Integration

### Interactive Controls

```bash
# Enable dropdown menus for indicator toggles
CHART_ENABLE_DROPDOWNS=1

# Default indicators to show (comma-separated)
# Options: sr, bollinger, fibonacci, volume_profile, patterns
CHART_DEFAULT_INDICATORS=sr,bollinger

# Maximum dropdown options displayed
CHART_DROPDOWN_MAX_OPTIONS=5
```

### Session Management

```bash
# Session TTL in seconds (default: 1 hour)
CHART_SESSION_TTL=3600

# Enable automatic cleanup of expired sessions
CHART_SESSION_AUTO_CLEANUP=1
```

---

## Phase 3: Multi-Panel Layout Enhancement

### Panel Configuration

```bash
# Enable multi-panel layouts
CHART_USE_PANELS=1

# Panel height ratios (comma-separated)
# Format: price,volume,rsi,macd
CHART_PANEL_RATIOS=6,1.5,1.25,1.25

# Panel spacing
CHART_PANEL_SPACING=0.05

# Individual panel toggles
CHART_SHOW_VOLUME_PANEL=1
CHART_SHOW_RSI_PANEL=1
CHART_SHOW_MACD_PANEL=1
```

### RSI/MACD Reference Lines

```bash
# RSI oversold/overbought levels
CHART_RSI_OVERSOLD=30
CHART_RSI_OVERBOUGHT=70

# MACD zero line visibility
CHART_MACD_SHOW_ZERO_LINE=1
```

---

## Phase 4: Advanced Features

### Pattern Recognition

```bash
# Enable pattern detection
CHART_SHOW_PATTERNS=1

# Minimum confidence threshold (0.0 - 1.0)
CHART_PATTERN_CONFIDENCE_MIN=0.6

# Pattern cache TTL in seconds (default: 1 hour)
CHART_PATTERN_CACHE_TTL=3600

# Pattern types to detect (comma-separated)
# Options: triangles, head_shoulders, double_tops, channels, flags
CHART_PATTERN_TYPES=triangles,head_shoulders,double_tops,channels,flags
```

### Volume Profile

```bash
# Enable enhanced volume profile
CHART_VOLUME_PROFILE_ENHANCED=1

# Show horizontal volume bars
CHART_VOLUME_PROFILE_BARS=1

# Number of volume bins (default: 20)
CHART_VOLUME_PROFILE_BINS=20

# Show POC/VAH/VAL lines
CHART_VOLUME_PROFILE_SHOW_POC=1
CHART_VOLUME_PROFILE_SHOW_VALUE_AREA=1

# Identify High/Low Volume Nodes
CHART_VOLUME_PROFILE_SHOW_HVN_LVN=1
```

---

## QuickChart Integration

### QuickChart Configuration

```bash
# QuickChart base URL
QUICKCHART_URL=http://localhost:3400
# Alternative:
QUICKCHART_BASE_URL=http://localhost:3400

# QuickChart API key (optional)
QUICKCHART_API_KEY=

# URL shortening threshold in characters
QUICKCHART_SHORTEN_THRESHOLD=3500
```

---

## Performance & Optimization

### Caching

```bash
# Chart cache enabled
CHART_CACHE_ENABLED=1

# Chart cache TTL in seconds (default: 5 minutes)
CHART_CACHE_TTL=300

# Pattern cache enabled
CHART_PATTERN_CACHE_ENABLED=1
```

### Rendering

```bash
# Chart width in pixels
CHART_WIDTH=1200

# Chart height in pixels
CHART_HEIGHT=800

# DPI for chart rendering
CHART_DPI=100

# Mobile optimization
CHART_MOBILE_OPTIMIZED=1
```

---

## Complete Example Configuration

```bash
# ============================================================================
# WeBull Chart Enhancement - Complete Configuration
# ============================================================================

# Phase 1: WeBull Dark Theme
CHART_STYLE=webull
CHART_THEME=dark
CHART_AXIS_LABEL_SIZE=12
CHART_TITLE_SIZE=16

# Phase 2: Dropdown Menus
CHART_ENABLE_DROPDOWNS=1
CHART_DEFAULT_INDICATORS=sr,bollinger
CHART_SESSION_TTL=3600
CHART_SESSION_AUTO_CLEANUP=1

# Phase 3: Multi-Panel Layouts
CHART_USE_PANELS=1
CHART_PANEL_RATIOS=6,1.5,1.25,1.25
CHART_SHOW_VOLUME_PANEL=1
CHART_SHOW_RSI_PANEL=1
CHART_SHOW_MACD_PANEL=1
CHART_RSI_OVERSOLD=30
CHART_RSI_OVERBOUGHT=70

# Phase 4: Pattern Recognition & Volume Profile
CHART_SHOW_PATTERNS=1
CHART_PATTERN_CONFIDENCE_MIN=0.6
CHART_PATTERN_CACHE_TTL=3600
CHART_VOLUME_PROFILE_ENHANCED=1
CHART_VOLUME_PROFILE_BARS=1
CHART_VOLUME_PROFILE_BINS=20
CHART_VOLUME_PROFILE_SHOW_POC=1
CHART_VOLUME_PROFILE_SHOW_VALUE_AREA=1

# QuickChart
QUICKCHART_URL=http://localhost:3400
QUICKCHART_SHORTEN_THRESHOLD=3500

# Performance
CHART_CACHE_ENABLED=1
CHART_CACHE_TTL=300
CHART_WIDTH=1200
CHART_HEIGHT=800
CHART_DPI=100
CHART_MOBILE_OPTIMIZED=1
```

---

## Testing Configuration

For testing purposes, use these minimal settings:

```bash
CHART_STYLE=webull
CHART_THEME=dark
CHART_ENABLE_DROPDOWNS=1
CHART_DEFAULT_INDICATORS=sr,bollinger
CHART_USE_PANELS=1
CHART_SHOW_PATTERNS=1
CHART_PATTERN_CONFIDENCE_MIN=0.6
CHART_VOLUME_PROFILE_ENHANCED=1
CHART_SESSION_AUTO_CLEANUP=0  # Disable in tests
```

---

## Setting Environment Variables

### Windows (PowerShell)

```powershell
$env:CHART_STYLE = "webull"
$env:CHART_ENABLE_DROPDOWNS = "1"
$env:CHART_SHOW_PATTERNS = "1"
```

### Windows (CMD)

```cmd
set CHART_STYLE=webull
set CHART_ENABLE_DROPDOWNS=1
set CHART_SHOW_PATTERNS=1
```

### Linux/Mac (Bash)

```bash
export CHART_STYLE=webull
export CHART_ENABLE_DROPDOWNS=1
export CHART_SHOW_PATTERNS=1
```

### Docker

Add to `docker-compose.yml`:

```yaml
environment:
  - CHART_STYLE=webull
  - CHART_ENABLE_DROPDOWNS=1
  - CHART_SHOW_PATTERNS=1
  - CHART_VOLUME_PROFILE_ENHANCED=1
```

---

## Feature Flags Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CHART_ENABLE_DROPDOWNS` | `1` | Enable Discord dropdown menus |
| `CHART_USE_PANELS` | `1` | Enable multi-panel layouts |
| `CHART_SHOW_PATTERNS` | `1` | Enable pattern detection |
| `CHART_VOLUME_PROFILE_ENHANCED` | `1` | Enable enhanced volume profile |
| `CHART_MOBILE_OPTIMIZED` | `1` | Optimize for mobile screens |
| `CHART_SESSION_AUTO_CLEANUP` | `1` | Auto-cleanup expired sessions |

---

## Troubleshooting

### Charts Not Showing Patterns

1. Ensure `CHART_SHOW_PATTERNS=1`
2. Check `CHART_PATTERN_CONFIDENCE_MIN` (lower = more patterns)
3. Verify scipy is installed: `pip install scipy`

### Dropdown Menus Not Appearing

1. Ensure `CHART_ENABLE_DROPDOWNS=1`
2. Check Discord API version supports select menus
3. Verify chart_sessions module is imported correctly

### QuickChart Not Rendering

1. Verify QuickChart is running: `curl http://localhost:3400/healthcheck`
2. Check `QUICKCHART_URL` matches your deployment
3. Ensure Chart.js v3 candlestick plugin is loaded

---

## Related Documentation

- [WEBULL_CHART_ENHANCEMENT_PLAN.md](WEBULL_CHART_ENHANCEMENT_PLAN.md) - Implementation roadmap
- [MULTIPANEL_CHARTS_QUICK_REFERENCE.md](MULTIPANEL_CHARTS_QUICK_REFERENCE.md) - Panel configuration guide
- [Creating WeBull-Style Stock Charts for Discord Bots.md](Creating%20WeBull-Style%20Stock%20Charts%20for%20Discord%20Bots.md) - Design philosophy

---

**Generated with Claude Code** 🤖
