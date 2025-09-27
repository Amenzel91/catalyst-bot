## [2025-09-23] Heartbeat refinements, QuickChart fallback & classifier unification

### Added

- **End‑of‑day heartbeat and cumulative counters**: The bot now emits a final
  heartbeat (reason `endday`) at shutdown summarising the total number of
  items processed, deduped, skipped and alerted across all cycles.  Each
  interval heartbeat also displays both the counts from the most recent
  cycle and the cumulative totals (formatted as `new | total`).  No
  configuration is required; the feature is controlled by existing
  heartbeat flags.

- **Refined Finviz noise filter**: Expanded the built‑in keyword list used
  to filter out law‑firm spam and shareholder investigation adverts from
  Finviz feeds.  The noise filter now loads additional phrases from
  `data/filters/finviz_noise.txt` when this file exists (one keyword
  per line, `#` comments supported).  Users can customise noise
  filtering by editing this file without modifying code.

### Changed

- **QuickChart fallback**: When intraday (5‑minute) OHLC data is
  unavailable, QuickChart now falls back to rendering a daily line chart
  covering the past month.  All QuickChart URLs honour
  `QUICKCHART_BASE_URL`.  This reduces missing charts for illiquid
  tickers and after‑hours events.

- **Unified classifier default**: The `FEATURE_CLASSIFIER_UNIFY` flag
  now defaults to `1`, enabling the new dynamic classification bridge in
  feeds and analyzer modules.  This consolidates the scoring logic on
  `classify.classify()` and prepares for removal of the legacy
  `classifier.py`.  You can set `FEATURE_CLASSIFIER_UNIFY=0` in your
  `.env` to revert to the old classifier.

### Environment

- **Feature flags**: Updated `env.example.ini` to set
  `FEATURE_CLASSIFIER_UNIFY=1` by default.  No new environment variables
  are required for the heartbeat or chart changes.  To opt out of the
  unified classifier, set `FEATURE_CLASSIFIER_UNIFY=0`.

## [2025-09-24] Watchlist & screener boost

### Added

- **Screener boost support**: Introduced a new feature flag
  `FEATURE_SCREENER_BOOST`.  When enabled, the bot loads a Finviz
  screener CSV specified by `SCREENER_CSV` once per cycle and treats the
  tickers found in that file as part of the watchlist.  This allows
  operators to import their Finviz custom screens (e.g. high volume
  breakouts) and bypass the price ceiling filter for those names.  By
  default, `SCREENER_CSV` points to `data/finviz.csv`.

### Changed

- **Unified watchlist loading**: The feed pipeline now combines tickers
  from both the static watchlist (`WATCHLIST_CSV`) and the Finviz
  screener (`SCREENER_CSV`) when their respective flags (`FEATURE_WATCHLIST`
  and `FEATURE_SCREENER_BOOST`) are enabled.  The unified set is
  loaded once per cycle and used to bypass the price ceiling filter.
  Events whose ticker is in this combined set are marked with
  `watchlist=True` in the returned item dict.

### Environment

- Added `FEATURE_SCREENER_BOOST` and `SCREENER_CSV` to
  `env.example.ini`.  See that file for default values and usage.

## [2025-09-25] Watchlist & screener boost bug fixes

### Fixed

- **Screener loader crash**: `load_screener_set()` referenced the
  `List` type without importing it, leading to a `NameError` and a
  silent failure to load any tickers from Finviz screener CSVs.  This
  prevented the screener boost from taking effect.  We now import
  `List` from `typing` in `watchlist.py`.
- **Price ceiling bypass**: Tests monkeypatching
  `market.get_last_price_snapshot()` did not work because
  `feeds.py` imported the function directly, bypassing the patched
  attribute on the `market` module.  We now import the entire
  `market` module and call `market.get_last_price_snapshot()`, so
  monkeypatching the function in tests behaves correctly and avoids
  unnecessary network calls.

- **Stale settings in feeds**: `fetch_pr_feeds()` previously relied on
  `get_settings()`, which returns a cached `Settings` instance created
  at module import time.  When environment variables were modified in
  tests (e.g. enabling `FEATURE_SCREENER_BOOST`), the cached instance
  did not reflect these changes.  The function now instantiates a
  fresh `Settings()` object at runtime, falling back to the cached
  instance only on failure.  This ensures that watchlist and screener
  flags defined via environment variables are honoured during feed
  processing.

- **Environment‑first watchlist flags**: To better support test scenarios
  where environment variables override defaults, `fetch_pr_feeds()` now
  reads `FEATURE_WATCHLIST`, `WATCHLIST_CSV`, `FEATURE_SCREENER_BOOST`
  and `SCREENER_CSV` directly from the environment with fallbacks to
  settings.  This ensures that screener tickers are loaded even when
  `get_settings()` returns a stale instance.  Allowed exchanges are
  similarly read from the `ALLOWED_EXCHANGES` environment variable when
  present.

### Environment

There are no new environment variables or changes to existing defaults
for this bug‑fix release.

## [2025-09-22] Bullishness gauge, sentiment logging & exchange filter

### Added

- **Bullishness sentiment gauge**: Introduced a new feature flag
  `FEATURE_BULLISHNESS_GAUGE` and accompanying weight knobs
  (`SENTIMENT_WEIGHT_LOCAL`, `SENTIMENT_WEIGHT_EXT`,
  `SENTIMENT_WEIGHT_SEC`, `SENTIMENT_WEIGHT_ANALYST`,
  `SENTIMENT_WEIGHT_EARNINGS`) to compute a single composite
  bullishness score for each alert.  The gauge aggregates sentiment from
  local VADER analysis, external news providers, SEC filing sentiment,
  analyst signals and earnings surprises, then normalises the result to
  the range [–1, 1] and classifies it as Bullish/Neutral/Bearish.  When
  the feature flag is enabled, alerts include a **Bullishness** field
  showing the numeric score and label.
- **Sentiment logging**: Added a `FEATURE_SENTIMENT_LOGGING` flag.  When
  enabled, the bot writes a JSONL record to
  `data/sentiment_logs/YYYY-MM-DD.jsonl` for each processed event.
  Records capture the individual component scores (local, external,
  SEC, analyst, earnings) along with the final weighted score and
  discrete label.  Logging is off by default.
- **Exchange whitelist filter**: Added an `ALLOWED_EXCHANGES` setting
  to `config.py` and implemented a filter in `feeds.py`.  During feed
  ingestion, the bot extracts the exchange identifier from headline
  prefixes such as `(NASDAQ: XYZ)` and drops items whose exchange is
  not in the comma‑separated whitelist.  The default whitelist allows
  Nasdaq, NYSE and AMEX symbols while filtering out OTC markets.
- **Earnings field gating**: The earnings section of alert embeds is now
  displayed only when `FEATURE_EARNINGS_ALERTS=1`.  This prevents
  earnings information from appearing when earnings integration is
  disabled.

### Changed

- **Alert embeds**: Updated `_build_discord_embed()` in
  `alerts.py` to compute and display the bullishness gauge when
  enabled, to log sentiment components when logging is active, and to
  respect the `FEATURE_EARNINGS_ALERTS` flag when attaching the
  earnings field.  The function continues to fall back gracefully
  when sentiment data are incomplete.
- **Feed processing**: Added an exchange whitelist check early in
  `feeds.py`.  The filter canonicalises exchange names (e.g. OTCQB,
  OTCMKTS→`otc`) and skips any item whose exchange is not in
  `ALLOWED_EXCHANGES` before applying price ceiling/floor logic.

### Environment

- Added `FEATURE_BULLISHNESS_GAUGE`, `FEATURE_SENTIMENT_LOGGING`,
  `ALLOWED_EXCHANGES`, `SENTIMENT_WEIGHT_LOCAL`,
  `SENTIMENT_WEIGHT_EXT` and `SENTIMENT_WEIGHT_ANALYST` to
  `env.example.ini`.  See the file for default values and usage
  guidelines.  Existing weights (`SENTIMENT_WEIGHT_SEC`,
  `SENTIMENT_WEIGHT_EARNINGS`) are reused by the gauge when the
  corresponding features are enabled.

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

1. Tiingo Integration in market.py:

New Tiingo Helper Functions: Added _tiingo_intraday_series(ticker, api_key, interval, ...) to fetch intraday OHLCV bars from Tiingo’s IEX API, and _tiingo_daily_history(ticker, api_key, start_date, end_date) to fetch daily OHLCV from Tiingo’s daily prices API
GitHub
business-science.github.io
. These functions parse the JSON responses into pandas DataFrames, rename columns to match yfinance conventions (Open/High/Low/Close/Volume), and handle extended hours data via the afterHours parameter
GitHub
business-science.github.io
. They return None on any network or parsing error to allow graceful fallback.

get_last_price_snapshot: This function already had Tiingo support; no functional change to its logic aside from reformatting and documentation. It will attempt Tiingo first when FEATURE_TIINGO is enabled and a TIINGO_API_KEY is set, then Alpha Vantage, then yfinance, merging results from providers as before
GitHub
GitHub
. We preserved all fallback behavior and telemetry logging. Tests confirm that if Tiingo or Alpha Vantage returns data, yfinance is not called, and partial data is correctly supplemented by later providers
GitHub
GitHub
.

get_last_price_change: Simplified to use get_last_price_snapshot and then compute percentage change if possible
GitHub
. Returns (last, None) if previous close is missing or zero (avoiding division-by-zero)
GitHub
. This ensures no exceptions propagate; any error in computing change yields None for change_pct.

Intraday Data (get_intraday): This function now tries Tiingo intraday first. If FEATURE_TIINGO=1 and a TIINGO_API_KEY is available, it calls _tiingo_intraday_series. On success, it returns the DataFrame immediately
GitHub
GitHub
. If Tiingo is not enabled or returns no data, it falls back to the original yfinance logic (using yf.download). We map output_size to a date range for Tiingo: “compact” ~ last 5–7 days, “full” ~ ~60 days (noting Tiingo’s 2000-bar limit)
business-science.github.io
. Extended hours (prepost) are passed through via the afterHours flag. The returned DataFrame is in the same format as before (with columns Open, High, Low, Close, Volume). If no provider yields data, it returns None
GitHub
GitHub
.

Intraday Snapshots (get_intraday_snapshots): Added Tiingo support for 1-minute data. If Tiingo is enabled, we call _tiingo_intraday_series for the day (±1 day buffer) instead of yf.download
GitHub
GitHub
. The same segmenting logic then applies to the DataFrame. If Tiingo fails or returns no data, we fallback to yfinance as before
GitHub
GitHub
. This improves snapshot reliability for extended hours, since Tiingo provides pre/post market data when available. The output format (dict of segment OHLCs) remains unchanged.

Volatility (get_volatility): Modified to prefer Tiingo for daily historical data. If Tiingo is enabled, we call _tiingo_daily_history for roughly (days+5) days of data (to ensure we have at least days trading days)
GitHub
GitHub
. If Tiingo returns data, we compute the average daily range% from that; if not, we fallback to yfinance (Ticker.history) as before. We continue to return None if insufficient data or on any exception
GitHub
GitHub
. The test for a 3-day volatility scenario passes (computed ~16.7% range) within tolerance, confirming consistency
GitHub
.

Intraday Indicators (get_intraday_indicators, get_momentum_indicators): These now attempt Tiingo 1-minute data if available. We fetch 1-minute bars for the target date (with a one-day buffer before/after) via Tiingo, else fallback to yfinance
GitHub
GitHub
. The computation of VWAP, RSI-14, MACD, EMAs, etc., is unchanged, but they will use Tiingo data when possible. We guarded these functions with feature_indicators and feature_momentum_indicators flags as before
GitHub
GitHub
. If Tiingo is used and fails (e.g., no data for illiquid ticker), we safely fall back to yfinance or return {}. This enhancement ensures indicators can be calculated even if yfinance is not installed or if it fails, as long as Tiingo is enabled.

QuickChart Integration: The get_quickchart_url function (in charts.py) calls market.get_intraday(..., output_size="compact"). With our changes, this call will use Tiingo (if enabled) to retrieve intraday data for the chart
GitHub
. We did not change charts.py directly; however, QuickChart will now prefer Tiingo data automatically through the modified get_intraday. The fallback to _quickchart_url_yfinance remains in place if both Tiingo and yfinance fail to provide intraday data
GitHub
. This means alert candlestick charts will benefit from Tiingo’s extended hours data and reliability when available, without altering the QuickChart logic.

2. Loader Updates (backtest/loader.py):

Daily History via Tiingo: In load_price_history, for daily interval we replaced the direct yfinance.download call with a new call to get_daily_history
GitHub
. We created get_daily_history(ticker, days) in market.py to encapsulate the logic of “Tiingo if possible, else yfinance” for daily bars. This function uses _tiingo_daily_history under the hood, falling back to yf.download if Tiingo is unavailable or empty. By using get_daily_history, the backtest simulator will retrieve daily price data from Tiingo (when enabled), improving consistency with live mode. If Tiingo is disabled, get_daily_history simply invokes yfinance as before. We preserved the period_days = days+7 buffer for weekends/holidays, so the behavior and output size remain consistent
GitHub
GitHub
. We also adjusted the loader’s comments to reflect using Tiingo instead of exclusively yfinance.

Import Changes: We added get_daily_history to market.py (but did not add it to __all__, as it’s mainly for internal use). The loader now does from ..market import get_daily_history inside the load_price_history function when needed, similar to how it imports yfinance on the fly. This keeps the import overhead minimal and avoids issues if market.py is imported without Tiingo configured.

3. Environment & Config Considerations:

The new code respects the FEATURE_TIINGO flag and TIINGO_API_KEY from settings or environment. If FEATURE_TIINGO is off or the API key is missing, all Tiingo code paths are skipped, and behavior remains exactly as before (using Alpha Vantage and yfinance only)
GitHub
GitHub
. We took care to not introduce any hard dependency on Tiingo – the bot will function without it.

If Tiingo is enabled but a particular API call fails (network issue, ticker not found, etc.), we catch exceptions and proceed to the next provider or return None as appropriate
GitHub
GitHub
. This ensures robust fallback. We also log provider usage (provider_usage telemetry) for Tiingo just like for Alpha and yfinance, so one can monitor in logs which source provided the data
GitHub
GitHub
.

No changes were made to Alpha Vantage logic aside from ensuring our code uses _alpha_last_prev_cached and _alpha_last_prev exactly as before. The Alpha cache and skip flag are honored. The yfinance usage is also unchanged except where we intercept it with Tiingo data earlier.

4. Minor Enhancements and Notes:

We updated docstrings and comments to reflect the new behavior (e.g., noting Tiingo as a provider in get_last_price_snapshot and others, updating loader’s documentation) for clarity
GitHub
GitHub
.

The Alpaca streaming stub (sample_alpaca_stream) was not part of the request, but we noticed it in __all__. We left its functionality intact, only reformatting slightly for consistency (no logic change).

We did not modify charts.py except indirectly via get_intraday, as mentioned. The Finviz and FMP integrations, and other parts of the bot unrelated to price fetching, remain untouched.
