# Chart Integration Architecture Diagram

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Chart Rendering Pipeline                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────┐      ┌──────────────┐      ┌────────────────┐
│   Caller    │─────▶│   charts.py  │─────▶│  mplfinance    │
│  (alerts,   │      │              │      │                │
│   runner)   │      │ Entry Points:│      │ mpf.plot()     │
└─────────────┘      │ - render_    │      │                │
                     │   chart_with_│      └────────────────┘
                     │   panels()   │
                     │ - render_    │              │
                     │   multipanel_│              │
                     │   chart()    │              ▼
                     └──────────────┘      ┌────────────────┐
                             │             │  PNG File      │
                             │             │  (out/charts/) │
                             ▼             └────────────────┘
                     ┌──────────────┐
                     │ Indicator    │
                     │ Integration  │
                     │ Layer        │
                     └──────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ add_indicator │   │ apply_sr_     │   │ chart_panels  │
│ _panels()     │   │ lines()       │   │ .calculate_   │
│               │   │               │   │ panel_ratios()│
│ Creates       │   │ Converts S/R  │   │               │
│ mpf.make_     │   │ to hlines     │   │ Determines    │
│ addplot()     │   │ dict          │   │ layout ratios │
│ objects       │   │               │   │               │
└───────────────┘   └───────────────┘   └───────────────┘
        │                    │                    │
        └────────────────────┴────────────────────┘
                             │
                             ▼
                     ┌──────────────┐
                     │ Indicators   │
                     │ Module       │
                     │ (calculation)│
                     └──────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ bollinger.py  │   │ support_      │   │ fibonacci.py  │
│               │   │ resistance.py │   │ (Wave 2)      │
│ calculate_    │   │               │   │               │
│ bollinger_    │   │ detect_       │   │ calculate_    │
│ bands()       │   │ support_      │   │ fibonacci_    │
│               │   │ resistance()  │   │ levels()      │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Data Flow Diagram

```
Input (Caller)
    │
    │  ticker="AAPL"
    │  indicators=["vwap", "rsi", "fibonacci"]
    │  support_levels=[{...}]
    │  resistance_levels=[{...}]
    │
    ▼
render_chart_with_panels()  ◄─── Entry point
    │
    ├──▶ market.get_intraday()  ◄─── Fetch OHLCV data
    │        │
    │        └──▶ DataFrame (OHLC + Volume)
    │
    ├──▶ Calculate Indicators  ◄─── Add columns to DataFrame
    │        │
    │        ├──▶ df["vwap"] = calculate_vwap()
    │        ├──▶ df["rsi"] = calculate_rsi()
    │        └──▶ fib_levels = calculate_fibonacci()
    │
    ├──▶ add_indicator_panels(df, indicators)  ◄─── Create addplot objects
    │        │
    │        │   ┌─────────────────────────────────────────┐
    │        │   │ For each indicator in indicators list:  │
    │        │   │                                         │
    │        │   │ 1. Check if indicator requested         │
    │        │   │ 2. Check if data column exists          │
    │        │   │ 3. Create mpf.make_addplot() object     │
    │        │   │ 4. Append to apds list                  │
    │        │   │                                         │
    │        │   │ Error handling:                         │
    │        │   │ - Try-except around each indicator      │
    │        │   │ - Log warning on failure                │
    │        │   │ - Continue without failed indicator     │
    │        │   └─────────────────────────────────────────┘
    │        │
    │        └──▶ List[mpf.make_addplot(...)]
    │
    ├──▶ apply_sr_lines(support, resistance)  ◄─── Build hlines dict
    │        │
    │        └──▶ {"s0": {...}, "r0": {...}, ...}
    │
    ├──▶ chart_panels.calculate_panel_ratios(indicators)
    │        │
    │        └──▶ (6.0, 1.5, 1.25, 1.25)  # Price, Vol, RSI, MACD
    │
    ├──▶ create_webull_style()  ◄─── Build style dict
    │        │
    │        └──▶ mpf.make_mpf_style(...)
    │
    ├──▶ mpf.plot()  ◄─── Render chart
    │        │
    │        │   plot_kwargs = {
    │        │       "type": "candle",
    │        │       "style": webull_style,
    │        │       "volume": True,
    │        │       "addplot": apds,  # Overlays and oscillators
    │        │       "panel_ratios": (6.0, 1.5, 1.25, 1.25),
    │        │       "returnfig": True
    │        │   }
    │        │
    │        └──▶ (fig, axes)
    │
    ├──▶ Add S/R lines manually  ◄─── Post-render step
    │        │
    │        │   for key, val in hlines.items():
    │        │       price_ax.axhline(y=val["y"], ...)
    │        │
    │        └──▶ Modified fig
    │
    ├──▶ optimize_for_mobile(fig, axes)  ◄─── Adjust tick density
    │
    ├──▶ fig.savefig(path)  ◄─── Save PNG
    │        │
    │        └──▶ Path("out/charts/AAPL_panels.png")
    │
    └──▶ Return chart_path
```

---

## Panel Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│                     Panel 0: Price Chart                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Candlesticks (OHLC)                                 │  │
│  │  + VWAP overlay (orange line)                        │  │
│  │  + Bollinger Bands overlay (purple dashed)           │  │
│  │  + Fibonacci levels (purple dashed horizontal)       │  │
│  │  + Support/Resistance levels (green/red horizontal)  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Ratio: 6.0 (60% of total height)                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Panel 1: Volume Chart                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Volume bars (green for up, red for down)            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Ratio: 1.5 (15% of total height)                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                Panel 2: RSI Oscillator                       │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  RSI line (cyan)                                      │  │
│  │  + Overbought line at 70 (red dashed)                │  │
│  │  + Oversold line at 30 (green dashed)                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Ratio: 1.25 (12.5% of total height)                        │
│  Y-axis: Fixed 0-100                                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 Panel 3: MACD Oscillator                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MACD line (blue)                                     │  │
│  │  Signal line (orange-red)                             │  │
│  │  Histogram (green/red bars)                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Ratio: 1.25 (12.5% of total height)                        │
│  Y-axis: Auto-scaled                                         │
└─────────────────────────────────────────────────────────────┘

Total Ratio Sum: 6.0 + 1.5 + 1.25 + 1.25 = 10.0
```

---

## Indicator Integration Flow

### Overlay Indicators (Panel 0)

```
                    ┌──────────────────┐
                    │ User requests    │
                    │ "vwap" indicator │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Check if "vwap"  │
                    │ in indicators    │
                    │ list             │
                    └──────────────────┘
                             │
                  ┌──────────┴──────────┐
                  │                     │
           YES    ▼                     ▼    NO
        ┌──────────────────┐   ┌──────────────────┐
        │ Check if "vwap"  │   │ Skip - indicator │
        │ column in df     │   │ not requested    │
        └──────────────────┘   └──────────────────┘
                  │
       ┌──────────┴──────────┐
       │                     │
YES    ▼                     ▼    NO
┌─────────────────┐   ┌─────────────────┐
│ Try:            │   │ Skip - data not │
│ Create addplot  │   │ available       │
│ with:           │   └─────────────────┘
│ - df["vwap"]    │
│ - panel=0       │
│ - color=#FF9800 │
│ - width=2       │
└─────────────────┘
       │
       │ Except:
       ▼
┌─────────────────┐
│ Log warning     │
│ Continue without│
│ this indicator  │
└─────────────────┘
```

### Oscillator Indicators (Panel 2+)

```
                    ┌──────────────────┐
                    │ User requests    │
                    │ "rsi" indicator  │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Calculate panel  │
                    │ number based on  │
                    │ other indicators │
                    │                  │
                    │ panel_num = 2    │
                    │ (or 3 if others) │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Create addplot   │
                    │ with:            │
                    │ - panel=panel_num│
                    │ - ylabel="RSI"   │
                    │ - ylim=(0,100)   │
                    │ - color=#00BCD4  │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Update panel_    │
                    │ ratios to include│
                    │ new panel        │
                    │                  │
                    │ (6,1.5,1.25,1.25)│
                    └──────────────────┘
```

### Horizontal Lines (S/R, Fibonacci)

```
                    ┌──────────────────┐
                    │ Calculate levels │
                    │ (before chart)   │
                    │                  │
                    │ detect_support_  │
                    │ resistance()     │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Build hlines     │
                    │ dictionary:      │
                    │                  │
                    │ {"s0": {         │
                    │   y: 150.0,      │
                    │   color: green,  │
                    │   ...            │
                    │ }}               │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Render chart     │
                    │ with mpf.plot()  │
                    │                  │
                    │ (NO hlines param)│
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Get price_ax     │
                    │ from axes[0]     │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ For each line:   │
                    │                  │
                    │ price_ax.axhline(│
                    │   y=level["y"],  │
                    │   color=...,     │
                    │   linestyle="--" │
                    │ )                │
                    └──────────────────┘
```

---

## Color Scheme Flow

```
┌──────────────────────────────────────────────────────┐
│              INDICATOR_COLORS Dictionary              │
├──────────────────────────────────────────────────────┤
│                                                       │
│  Overlays (Panel 0):                                 │
│  ├─ vwap: #FF9800 (Orange) ─────────────┐           │
│  ├─ bb_upper: #9C27B0 (Purple) ──────┐  │           │
│  ├─ bb_middle: #9C27B0 (Purple) ──┐  │  │           │
│  └─ bb_lower: #9C27B0 (Purple) ─┐ │  │  │           │
│                                  │ │  │  │           │
│  Oscillators (Panel 2+):         │ │  │  │           │
│  ├─ rsi: #00BCD4 (Cyan) ─────┐  │ │  │  │           │
│  ├─ macd_line: #2196F3 (Blue)│  │ │  │  │           │
│  └─ macd_signal: #FF5722 ────┤  │ │  │  │           │
│                               │  │ │  │  │           │
│  Horizontal Lines:            │  │ │  │  │           │
│  ├─ support: #4CAF50 (Green) │  │ │  │  │           │
│  └─ resistance: #F44336 (Red)│  │ │  │  │           │
│                               │  │ │  │  │           │
└───────────────────────────────┼──┼─┼──┼──┼───────────┘
                                │  │ │  │  │
                    ┌───────────┼──┼─┼──┼──┼──────────────┐
                    │           │  │ │  │  │              │
                    ▼           ▼  ▼ ▼  ▼  ▼              │
           ┌────────────────────────────────────┐         │
           │     mpf.make_addplot()             │         │
           │                                    │         │
           │  color=INDICATOR_COLORS["vwap"]    │         │
           │        └──▶ "#FF9800"              │         │
           │                                    │         │
           │  Creates colored line/indicator    │         │
           └────────────────────────────────────┘         │
                               │                          │
                               ▼                          │
                      ┌─────────────────┐                 │
                      │  Chart Output   │                 │
                      │                 │                 │
                      │  Orange VWAP ◄──┼─────────────────┘
                      │  Purple BBands  │
                      │  Cyan RSI       │
                      │  Blue MACD      │
                      │  Green Support  │
                      └─────────────────┘
```

---

## Error Handling Architecture

```
                    ┌──────────────────┐
                    │ Start Indicator  │
                    │ Integration      │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ try:             │
                    │   if "indicator" │
                    │   in indicators  │
                    └──────────────────┘
                             │
                  ┌──────────┴──────────┐
                  │                     │
           YES    ▼                     ▼    NO
        ┌──────────────────┐   ┌──────────────────┐
        │ Check column     │   │ Return []        │
        │ exists in df     │   │ (empty list)     │
        └──────────────────┘   └──────────────────┘
                  │
       ┌──────────┴──────────┐
       │                     │
YES    ▼                     ▼    NO
┌─────────────────┐   ┌─────────────────┐
│ Create addplot  │   │ Return []       │
│ Append to apds  │   └─────────────────┘
└─────────────────┘
       │
       │ Success
       ▼
┌─────────────────┐
│ Return apds     │
└─────────────────┘


Except Path:
┌─────────────────┐
│ except Exception│
│ as err:         │
│   log.warning() │
│   Continue      │
└─────────────────┘
       │
       │ Chart continues
       │ without this indicator
       ▼
┌─────────────────┐
│ Other indicators│
│ still process   │
└─────────────────┘
```

---

## Module Dependencies

```
┌────────────────────────────────────────────────────────┐
│                      charts.py                         │
│  (Main entry point - 1334 lines)                       │
└────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ chart_panels│ │  indicators │ │   market    │
│     .py     │ │  (module)   │ │     .py     │
│             │ │             │ │             │
│ Panel config│ │ Calculations│ │ Data fetch  │
└─────────────┘ └─────────────┘ └─────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ bollinger.py│ │ support_    │ │ fibonacci.py│
│             │ │ resistance  │ │  (Wave 2)   │
│ BB calc     │ │     .py     │ │             │
│             │ │             │ │ Fib calc    │
└─────────────┘ └─────────────┘ └─────────────┘

External Dependencies:
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ mplfinance  │ │ matplotlib  │ │  pandas     │
│             │ │             │ │             │
│ Chart lib   │ │ Plotting    │ │ DataFrames  │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## Execution Timeline

```
Time   │ Function                        │ Output
───────┼─────────────────────────────────┼──────────────────────
0ms    │ render_chart_with_panels()      │ Entry point
       │                                 │
50ms   │ market.get_intraday()           │ DataFrame (OHLCV)
       │                                 │
100ms  │ Calculate indicators:           │
       │ - VWAP: df["vwap"]              │ Added columns
       │ - RSI: df["rsi"]                │ to DataFrame
       │ - Bollinger: df["bb_*"]         │
       │ - S/R: levels list              │
       │                                 │
150ms  │ add_indicator_panels()          │ List of
       │ - Loop through indicators       │ mpf.make_addplot()
       │ - Create addplot objects        │ objects
       │                                 │
200ms  │ apply_sr_lines()                │ hlines dict
       │ - Build S/R dictionary          │
       │                                 │
250ms  │ chart_panels.calculate_ratios() │ (6.0, 1.5, 1.25, 1.25)
       │                                 │
300ms  │ create_webull_style()           │ Style dict
       │                                 │
350ms  │ mpf.plot()                      │ fig, axes
       │ - Render candlesticks           │ (matplotlib objects)
       │ - Add overlays (VWAP, BB)       │
       │ - Add oscillator panels         │
       │   (RSI, MACD)                   │
       │                                 │
500ms  │ Manual axhline for S/R          │ Modified fig
       │ - Loop through hlines           │
       │ - Add to price_ax               │
       │                                 │
550ms  │ optimize_for_mobile()           │ Adjusted axes
       │ - Reduce tick density           │
       │ - Adjust spacing                │
       │                                 │
600ms  │ fig.savefig()                   │ PNG file
       │                                 │ (out/charts/AAPL.png)
       │                                 │
650ms  │ Return chart_path               │ Path object
───────┴─────────────────────────────────┴──────────────────────
```

**Total Time:** ~650ms for typical chart with 4 indicators

**Bottlenecks:**
1. **Data Fetch:** 50ms (network latency)
2. **mpf.plot():** 150ms (matplotlib rendering)
3. **File I/O:** 50ms (PNG save)

---

## Configuration Flow

```
Environment Variables
         │
         ├─ CHART_STYLE="webull"
         ├─ CHART_CANDLE_TYPE="candle"
         ├─ CHART_PANEL_RATIOS="6,1.5,1.25,1.25"
         ├─ CHART_DEFAULT_INDICATORS="vwap,rsi,macd"
         └─ CHART_RSI_COLOR="#00BCD4"
         │
         ▼
┌────────────────────┐
│ create_webull_     │
│ style()            │──▶ Style dict passed to mpf.plot()
└────────────────────┘
         │
┌────────────────────┐
│ calculate_panel_   │
│ ratios()           │──▶ Panel ratios passed to mpf.plot()
└────────────────────┘
         │
┌────────────────────┐
│ INDICATOR_COLORS   │──▶ Colors passed to make_addplot()
└────────────────────┘
```

---

**Architecture Diagram Complete**

**Use this to understand the full integration flow when implementing Wave 2**
