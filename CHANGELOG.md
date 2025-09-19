## [2025-09-21] SEC filing summarisation & QuickChart base URL
## [2025-09-21] Illiquid ticker filtering

### Added

- **Price floor filtering**: Introduced a `PRICE_FLOOR` environment
  variable and corresponding `price_floor` setting in `config.py`. When
  set to a value greater than zero, the feed ingestion pipeline in
  `feeds.py` skips any ticker whose last traded price falls below this
  threshold. This makes it easy to suppress alerts for highly illiquid
  penny stocks while still allowing normal symbols. The filter runs
  before the existing price ceiling check and does not affect the
  watchlist cascade or sentiment gauge. To enable, set
  `PRICE_FLOOR=1.00` (for example) in your `.env` file. By default it
  remains disabled.

### Changed

- **Feed processing**: Updated `feeds.py` to load and apply the
  `PRICE_FLOOR` value. The code now checks the last price for each
  ticker via `market.get_last_price_snapshot` and skips the item when
  the price is below the configured floor. This check occurs prior to
  the price ceiling and watchlist logic to minimise unnecessary
  lookups.

### Migration

- Added `PRICE_FLOOR` to `env.example.ini`. No database changes are
  required for this update.


### Added

- **SEC filing summarisation**: Introduced a heuristic summariser in
  `sec_digester.py` that compresses filing titles into concise
  keywords or categories (e.g. "offering", "buyback", "resignation").
  If no predefined patterns match, it extracts up to three
  significant tokens, ignoring common stopwords and company
  designations.  The summary is recorded for each filing and
  attached to events via `feeds.py`, replacing the verbose
  classifier reason.  This reduces the size of the "SEC Filings" field
  in Discord embeds and prevents HTTP 400 errors while preserving
  sentiment context.
- **QuickChart base URL**: Added a `QUICKCHART_BASE_URL` configuration
  variable and `quickchart_base_url` property in `config.py`.  The
  `charts.py` helper now respects this setting when constructing
  QuickChart image URLs.  This allows routing chart requests to a
  self‑hosted instance of QuickChart (e.g. `http://localhost:3400/chart`)
  rather than the public API.  The `env.example.ini` file includes
  a placeholder for this variable.

### Changed

- **SEC digester integration**: During the SEC classification pass in
  `feeds.py`, the bot now calls the summariser and records the
  resulting keyword instead of the raw classifier reason.  The
  `sec_reason` field on events reflects this concise summary.
- **Environment example**: Updated `env.example.ini` to document
  `QUICKCHART_BASE_URL`.

## [2025-09-20] Earnings alerts integration

### Added

- **Earnings alerts and sentiment integration**: Introduced a new module
  `earnings.py` which retrieves upcoming and historical earnings data
  for each ticker using the yfinance library.  The bot now attaches
  the next scheduled earnings date, EPS estimate, reported EPS and
  surprise percentage to events when `FEATURE_EARNINGS_ALERTS=1`.  Past
  earnings surprises are classified as Bullish, Neutral or Bearish
  based on a ±5 % threshold and contribute to the combined sentiment
  gauge via a configurable weight (`SENTIMENT_WEIGHT_EARNINGS`).  Alerts
  include an “Earnings” field summarising the next report and recent
  surprises.  Earnings sentiment can be toggled on/off and scoped via
  the lookahead window (`EARNINGS_LOOKAHEAD_DAYS`).

### Changed

- **Sentiment aggregator**: The `get_combined_sentiment_for_ticker()`
  function now incorporates earnings sentiment when
  `FEATURE_EARNINGS_ALERTS=1`.  Each earnings sentiment is treated as a
  single article and contributes to the weighted mean using
  `SENTIMENT_WEIGHT_EARNINGS`.  When no earnings data are available or
  upcoming earnings are beyond the lookahead window, the aggregator
  continues without them.
- **Alerts embed**: Added an “Earnings” field to alert embeds.  It
  displays the next earnings date (with relative days) and any
  surprise metrics from the most recent report.  When multiple
  elements are present they are shown on separate lines.  The
  sentiment score display now includes earnings along with local,
  external, SEC and analyst sources.
- **Heartbeat**: Added an `EarningsAlerts` flag to the heartbeat
  feature list.  The boot heartbeat lists it when enabled; interval
  heartbeats surface it only when failing to initialise.

### Environment

- Added `FEATURE_EARNINGS_ALERTS`, `EARNINGS_LOOKAHEAD_DAYS` and
  `SENTIMENT_WEIGHT_EARNINGS` to `env.example.ini`.  These control the
  activation, scope and influence of the earnings alerts system.

## [2025-09-18] SEC digester & SEC sentiment integration
## [2025-09-19] Chart warnings fix
## [2025-09-20] Heartbeat and noise filtering improvements

### Changed

- **Heartbeat metrics and feature display**: The heartbeat embed now
  distinguishes between boot and interval heartbeats.  At boot the
  bot reports all enabled features along with the watchlist size and
  cascade counts.  During interval heartbeats it only lists features
  that were enabled in the configuration but failed to initialise,
  keeping the message succinct.  The embed once again populates the
  `Items`, `Deduped`, `Skipped` and `Alerts` fields with counts from
  the last completed cycle instead of em dashes.  This restores the
  missing metrics seen in prior runs.

- **Finviz noise filter**: Added `_is_finviz_noise()` to
  `feeds.py` and applied it to both Finviz feeds.  The filter
  removes class‑action advertisements and shareholder
  investigation notices based on keywords (e.g. “recover your losses”,
  “class action”, “Pomerantz”, “Rosen Law”), reducing alert spam.
  Fixed an indentation bug in the Finviz export reader that
  prevented the filter from running.

- **Embed truncation for SEC filings**: The SEC digester now truncates
  the reasons in the “SEC Filings” field to ~80 characters and limits
  the number of filings shown to two.  When the combined text
  approaches Discord’s per‑field limit, it is truncated with an
  ellipsis.  These safeguards prevent HTTP 400 errors from Discord.

- **Sentiment score display**: Alert embeds now display available
  numeric sentiment scores (local, external and FMP) in the `Score`
  field.  When multiple sources are present the values are joined by
  slashes.  This aids diagnosis when the discrete sentiment label is
  “n/a”.

- **Chart fallback order**: Alerts always attempt QuickChart first when
  `FEATURE_QUICKCHART=1`.  Only when QuickChart is disabled will the
  bot try to render local matplotlib charts; otherwise it falls back
  directly to Finviz static charts.  This avoids repeated import
  errors for matplotlib when QuickChart is available.

- **Reduced log noise**: Downgraded the per‑item “item_parse_skip” and
  “skip_instrument_like_ticker” messages in `runner.py` from `info`
  level to `debug`, reducing clutter in normal logs.  Summary counts
  remain visible via the heartbeat metrics.

### Environment

- **Sentiment aggregator gating**: The default value of
  `SENTIMENT_MIN_ARTICLES` is now `1` (previously `2`), allowing
  external sentiment to contribute when only a single article is
  available.  The change is reflected in `env.example.ini`.  Set
  `SENTIMENT_MIN_ARTICLES` to a higher number in your `.env` if you
  prefer stricter gating.


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
