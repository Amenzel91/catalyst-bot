# Catalyst‑Bot — Patch 01 (Local Sentiment, Breakout Scanner, Heartbeat)

This patch introduces a VADER/keyword local sentiment fallback, an optional Finviz‑based breakout scanner for sub‑$10 tickers, and heartbeat enhancements. It keeps existing QuickChart + momentum indicator flows intact.

## What’s new

- **Local Sentiment (FEATURE_LOCAL_SENTIMENT)** — Computes a per‑headline sentiment score using VADER when available; otherwise uses a tiny keyword lexicon. Values are attached as `sentiment_local` and `sentiment_local_label`. Surfaced in the **Sentiment** field alongside FMP when present.  (Design aligns with the “local sentiment fallback” gap in the guide.) fileciteturn0file0 fileciteturn0file2

- **Proactive Breakout Scanner (FEATURE_BREAKOUT_SCANNER)** — Uses Finviz Elite’s CSV‑like export to scan **under $10** candidates with **unusual volume** and **new‑high candidates**, then generates alert items with a Finviz link. Thresholds: `BREAKOUT_MIN_AVG_VOL` and `BREAKOUT_MIN_RELVOL`. Based on Finviz Elite’s programmable export and signals for “New High”/“Unusual Volume”. fileciteturn0file3 fileciteturn0file4

- **Heartbeat Enhancements** — Adds feature visibility for QuickChart, Indicators, Momentum, LocalSentiment, and BreakoutScanner so you can confirm runtime posture at a glance. (The guide recommends surfacing active features in heartbeat.) fileciteturn0file0

## Configuration

Add the following to your `.env` or staging config:

```ini
# Charts & indicators
FEATURE_QUICKCHART=1
FEATURE_INDICATORS=1
FEATURE_MOMENTUM_INDICATORS=1
FEATURE_FINVIZ_CHART=1

# Local sentiment fallback
FEATURE_LOCAL_SENTIMENT=1

# Breakout scanner (Finviz Elite)
FEATURE_BREAKOUT_SCANNER=0
BREAKOUT_MIN_AVG_VOL=300000
BREAKOUT_MIN_RELVOL=1.5
FINVIZ_SCREENER_VIEW=152
```

**Prereqs:** Finviz Elite auth token in `FINVIZ_AUTH_TOKEN`. Respect polite polling (≈60s+) per export call as detailed in the Finviz docs. fileciteturn0file3

## Runtime

- Runner will now, when `FEATURE_BREAKOUT_SCANNER=1`, union `scan_breakouts_under_10()` results with PR/SEC feeds before dedupe. Each breakout item carries `source=finviz_breakout_scan`, a Finviz quote link, and a concise reason (“Unusual Volume; Price < $10” or “New High Candidate”).

- Local sentiment attaches automatically post‑dedupe and post‑FMP sentiment merge when `FEATURE_LOCAL_SENTIMENT=1`.

## PowerShell quickstart

```powershell
# 1) Create & activate venv, install deps
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3.12 -m pip install -r requirements.txt

# 2) Run once in record-only (safe), with features on
$env:FEATURE_RECORD_ONLY="1"
$env:FEATURE_QUICKCHART="1"
$env:FEATURE_INDICATORS="1"
$env:FEATURE_MOMENTUM_INDICATORS="1"
$env:FEATURE_FINVIZ_CHART="1"
$env:FEATURE_LOCAL_SENTIMENT="1"
$env:FEATURE_BREAKOUT_SCANNER="1"
$env:FINVIZ_AUTH_TOKEN="<your elite token>"
python -m catalyst_bot.runner --once

# 3) Loop mode with heartbeat every 15 min
$env:HEARTBEAT_INTERVAL_MIN="15"
python -m catalyst_bot.runner
```

## Notes & References

- **QuickChart** candlestick via Chart.js is already available and keeps URLs short; prefer hosted images over file uploads for Discord. fileciteturn0file2
- **Finviz Elite** screener export is CSV‑like and supports real‑time U.S. equities scanning; abide by polite cadence and token handling. fileciteturn0file3 fileciteturn0file4
- **Data feeds**: Tiingo/Alpaca are budget‑friendly realtime options; Alpha Vantage remains a good backup and provides technical indicators and earnings calendars. fileciteturn0file1

