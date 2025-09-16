## Catalyst‑Bot Technical Guide — Patch 02

This document supplements the existing technical guide by describing the
additions and changes introduced in Patch 02.

### Dynamic watchlist API

Patch 02 introduces a dynamic watchlist API in `watchlist.py`.
The module now exposes three helpers:

* `list_watchlist(path: str) -> Set[str]`: return the set of tickers in the
  watchlist CSV.
* `add_to_watchlist(ticker: str, path: str) -> bool`: add a ticker to the
  CSV, creating the file if needed.  Existing metadata is preserved.
* `remove_from_watchlist(ticker: str, path: str) -> bool`: remove a ticker
  from the CSV, rewriting the file.  The header row is always retained.

These functions are designed to be invoked from Discord slash commands so
operators can modify the watchlist without editing `.env`.  They work on
the same CSV defined by `WATCHLIST_CSV` in your environment.

### Local sentiment fallback

When `FEATURE_LOCAL_SENTIMENT=1`, the bot computes a fallback sentiment
score for each event using the VADER sentiment analyser.  If VADER is
not available, a lightweight keyword lexicon is used instead.  The
score is attached as `sentiment_local` and a discrete label
(`Bullish`, `Neutral`, `Bearish`) is attached as
`sentiment_local_label`.  Local sentiment is computed after merging FMP
sentiment so both values can coexist.

### Proactive breakout scanner

The new `scanner.py` module implements a proactive breakout scanner.
When `FEATURE_BREAKOUT_SCANNER=1`, the runner calls
`scan_breakouts_under_10()` once per cycle.  This function builds a
Finviz screener filter for sub‑$10 tickers with unusually high volume
(`BREAKOUT_MIN_AVG_VOL` shares and `BREAKOUT_MIN_RELVOL` relative
volume, configurable via environment variables).  It queries the
Finviz Elite export API and returns event‑shaped dicts that are merged
into the normal feed pipeline.  The events contain a `finviz_breakout`
source and link to the Finviz quote page for that ticker.

### QuickChart short URL support

`charts.get_quickchart_url()` now automatically shortens long Chart.js
configurations using QuickChart’s `/chart/create` endpoint when the
generated URL exceeds `QUICKCHART_SHORTEN_THRESHOLD` characters (default
1900).  This prevents Discord’s message length limit from being
exceeded and produces cleaner URLs.  You can adjust the threshold or
disable shortening by setting `QUICKCHART_SHORTEN_THRESHOLD` in your
environment.

### Heartbeat improvements

The heartbeat embed has been enhanced to aid diagnostics:

* **Price ceiling** — displays the numeric ceiling if set or “∞” when
  unset (previously blank).
* **Watchlist size** — always shows the number of tickers loaded from
  `WATCHLIST_CSV`, even when `FEATURE_WATCHLIST=0`.
* **Features** — lists all active feature flags including QuickChart,
  Momentum, LocalSentiment and BreakoutScanner.
* **Cycle metrics** — displays the number of items processed, items
  surviving deduplication, skipped items (sum of all skip categories)
  and alerts sent during the last cycle.

These metrics are surfaced via a global `LAST_CYCLE_STATS` in
`runner.py` and updated at the end of each run loop.

### Configuration variables

Patch 02 adds several new environment variables.  Update your
`.env` or `.env.example.ini` accordingly:

```ini
# QuickChart & momentum
FEATURE_QUICKCHART=0           # enable hosted candlestick charts via QuickChart
FEATURE_MOMENTUM_INDICATORS=0  # compute MACD, EMA crosses, VWAP delta (requires FEATURE_INDICATORS)

# Local sentiment fallback
FEATURE_LOCAL_SENTIMENT=0      # compute VADER/lexicon sentiment when FMP is unavailable

# Breakout scanner
FEATURE_BREAKOUT_SCANNER=0     # enable proactive sub‑$10 breakout scanner
BREAKOUT_MIN_AVG_VOL=300000    # minimum average volume (shares) filter
BREAKOUT_MIN_RELVOL=1.5        # minimum relative volume filter (>1 indicates above‑normal activity)

# QuickChart URL shortening
QUICKCHART_SHORTEN_THRESHOLD=1900  # shorten URLs longer than this many characters
```

Set these variables to “1” or adjust thresholds to activate the new
functionality.