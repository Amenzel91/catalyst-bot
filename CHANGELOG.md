## [2025-09-18] SEC digester & SEC sentiment integration
## [2025-09-19] Chart warnings fix

### Changed

- **Chart rendering (QuickChart)**: Updated `charts.py` to explicitly set
  `auto_adjust=False` when downloading intraday data via yfinance and to
  extract OHLC values using `.iloc[0]` when pandas returns a
  single‑element `Series`.  This silences FutureWarning messages and
  future‑proofs the candlestick chart generation used by QuickChart.  The
  change does not affect chart appearance or behaviour.


### Added

- **SEC filings digester**: Introduced a new module `sec_digester.py` to
  classify SEC filings (8‑K, 424B5, FWP, 13D/G) into bullish, neutral or
  bearish sentiment using simple keyword heuristics derived from
  historical market reactions.  Classified filings are recorded in an
  in‑memory cache keyed by ticker.  The digester aggregates filings
  within a configurable lookback window to compute a mean score and
  majority label, updating the watchlist cascade (HOT/WARM/COOL) when
  `FEATURE_WATCHLIST_CASCADE=1`.

- **Recent SEC filings context**: When `FEATURE_SEC_DIGESTER=1` each
  event gains `recent_sec_filings`, `sec_sentiment_label` and
  `sec_sentiment_score` fields.  Alert embeds now include a "SEC
  Filings" section summarising up to three recent filings with their
  reasons and relative ages.  The SEC sentiment label is appended to
  the overall sentiment string alongside local, external and FMP
  sentiment.

- **Sentiment gauge integration**: The existing sentiment aggregator
  (`sentiment_sources.get_combined_sentiment_for_ticker()`) now
  incorporates SEC sentiment when `FEATURE_SEC_DIGESTER=1`.  The
  contribution is weighted by `SENTIMENT_WEIGHT_SEC`.

### Changed

- **Heartbeat**: Added a `SecDigester` flag to the heartbeat embed to
  reflect whether the SEC digester feature is active.  Feature flags
  continue to be presented one per line for readability.

### Environment

- Added new environment variables: `FEATURE_SEC_DIGESTER`,
  `SEC_LOOKBACK_DAYS` and `SENTIMENT_WEIGHT_SEC`.  See
  `env.example.ini` for default values and documentation.

## [2025-09-18] Logging improvements

### Changed

- **Feed summary logging**: The `feeds.py` module now emits a concise summary
  line instead of dumping the entire `feeds_summary` dictionary. The new
  format lists the number of sources, total items, total processing time and
  per‑source metrics (ok, entries, errors, HTTP4/5 counts and duration)
  in a single line, making it easier to scan the run output.

## [2025-09-17] Analyst signals & heartbeat layout

### Added

- **Analyst signals**: Introduced a new module `analyst_signals.py` that fetches
  consensus price targets from external providers (Financial Modeling Prep or
  Yahoo Finance) and computes the implied return relative to the current
  price.  When `FEATURE_ANALYST_SIGNALS=1`, each event gains the fields
  `analyst_target`, `analyst_implied_return` and `analyst_label`, allowing
  alerts to show the target price and bullish/neutral/bearish classification.

### Changed

- **Heartbeat layout**: The heartbeat embed now lists active feature flags
  one per line instead of a comma‑separated string.  The list also includes
  the new `AnalystSignals` flag when enabled.
- **Alert embeds**: Added an "Analyst Target / Return" field to alert
  embeds.  When analyst signals are available, the field displays the
  consensus target price, the implied return percentage and the bullish/
  neutral/bearish label.

### Environment

- Added new environment flags: `FEATURE_ANALYST_SIGNALS`,
  `ANALYST_RETURN_THRESHOLD`, `ANALYST_PROVIDER` and `ANALYST_API_KEY`, plus
  `FEATURE_FINVIZ_CHART`, `FINVIZ_SCREENER_VIEW`, `ANALYZER_UTC_HOUR`,
  `ANALYZER_UTC_MINUTE` and `TZ`.
  See `env.example.ini` for documentation and defaults.

@@

### Added

- **External news sentiment sources (Phase D)**: Introduced a pluggable
  sentiment aggregation layer that queries multiple providers (Alpha Vantage
  NEWS_SENTIMENT, Marketaux, StockNewsAPI and Finnhub) to compute a
  weighted sentiment score for each ticker.  When `FEATURE_NEWS_SENTIMENT=1`
  the bot attaches `sentiment_ext_score`, `sentiment_ext_label` and
  `sentiment_ext_details` to each event.  The aggregator normalises
  per‑provider weights and falls back gracefully when providers return
  insufficient data or respond with 401/429 errors.
- **Config flags**: Added environment variables `FEATURE_NEWS_SENTIMENT`,
  `FEATURE_ALPHA_SENTIMENT`, `FEATURE_MARKETAUX_SENTIMENT`,
  `FEATURE_STOCKNEWS_SENTIMENT`, `FEATURE_FINNHUB_SENTIMENT`,
  `SENTIMENT_WEIGHT_ALPHA`, `SENTIMENT_WEIGHT_MARKETAUX`,
  `SENTIMENT_WEIGHT_STOCKNEWS`, `SENTIMENT_WEIGHT_FINNHUB`,
  `SENTIMENT_MIN_ARTICLES`, `MARKETAUX_API_KEY`, `STOCKNEWS_API_KEY` and
  `FINNHUB_API_KEY`.  See `env.example.ini` for defaults and guidance.
- **Heartbeat**: The heartbeat embed now surfaces the new sentiment
  feature flags (`NewsSent`, `AlphaSent`, `MarketauxSent`, `StockNewsSent`,
  `FinnhubSent`) when enabled, providing operators with visibility into
  active sentiment sources.
 ### Changed

 - **Price lookup**: Updated `get_last_price_snapshot()` in
   `src/catalyst_bot/market.py` to use the new cached Alpha Vantage
   fetcher and to respect the configured TTL.
+
+### Analyzer Enhancements
+
+- **Daily report & pending changes**: The analyzer now produces a
+  Markdown report summarizing each day's events, per‑category hit/miss
+  statistics and newly discovered keywords. Reports are written to
+  `out/analyzer/summary_<date>.md`.
+- **Weight proposals & unknown keywords**: Based on price change
+  thresholds (configurable via `ANALYZER_HIT_UP_THRESHOLD_PCT` and
+  `ANALYZER_HIT_DOWN_THRESHOLD_PCT`), the analyzer computes hit/miss
+  ratios for each keyword category and generates proposed weight
+  adjustments. It also records keywords observed in titles that are
+  absent from `keyword_weights.json`. These proposals are serialized
+  to `data/analyzer/pending_<planId>.json` for admin review.
+- **Classification integration**: Integrated the `classifier.classify`
+  helper to evaluate news relevance and sentiment. This enables
+  categorization by configured keyword categories and identification
+  of unknown keywords.
+- **Environment thresholds**: Added support for the environment
+  variables `ANALYZER_HIT_UP_THRESHOLD_PCT` and
+  `ANALYZER_HIT_DOWN_THRESHOLD_PCT` to tune the price move criteria
+  used when computing hit/miss statistics (default ±5 %).
+
+### Notes
+
+These analyzer enhancements lay the groundwork for a fully automated
+daily workflow. Reports and pending changes are generated but not
+automatically applied; an admin must review and approve the proposed
+updates by promoting the pending JSON file into `keyword_stats.json`.
+Future phases will integrate the approval loop and backtesting
+framework.
