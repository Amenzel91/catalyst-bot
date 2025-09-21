## [Unreleased]

### Configuration

This patch introduces a new pluggable sentiment layer powered by multiple
external news providers.  To enable the feature and tune provider
behaviour, several environment variables have been added.  No schema
changes or data migrations are required; updating your `.env` file is
sufficient.

#### New environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `FEATURE_NEWS_SENTIMENT` | Global switch to turn on the external news sentiment aggregator. | `0` |
| `FEATURE_ALPHA_SENTIMENT` | Enable Alpha Vantage NEWS_SENTIMENT provider.  Requires `ALPHAVANTAGE_API_KEY`. | `0` |
| `FEATURE_MARKETAUX_SENTIMENT` | Enable Marketaux sentiment provider.  Requires `MARKETAUX_API_KEY`. | `0` |
| `FEATURE_STOCKNEWS_SENTIMENT` | Enable StockNewsAPI sentiment provider.  Requires `STOCKNEWS_API_KEY`. | `0` |
| `FEATURE_FINNHUB_SENTIMENT` | Enable Finnhub news sentiment provider.  Requires `FINNHUB_API_KEY`. | `0` |
| `MARKETAUX_API_KEY` | API key for Marketaux. | — |
| `STOCKNEWS_API_KEY` | API key for StockNewsAPI. | — |
| `FINNHUB_API_KEY` | API key for Finnhub. | — |
| `SENTIMENT_WEIGHT_ALPHA` | Weight assigned to the Alpha Vantage provider when aggregating scores. | `0.4` |
| `SENTIMENT_WEIGHT_MARKETAUX` | Weight assigned to the Marketaux provider. | `0.3` |
| `SENTIMENT_WEIGHT_STOCKNEWS` | Weight assigned to the StockNewsAPI provider. | `0.3` |
| `SENTIMENT_WEIGHT_FINNHUB` | Weight assigned to the Finnhub provider. | `0.0` |
| `SENTIMENT_MIN_ARTICLES` | Minimum total article count across providers required before a combined score is considered valid. | `1` |

| `FEATURE_ANALYST_SIGNALS` | Enable consensus analyst price target and implied return classification. When on, events are annotated with `analyst_target`, `analyst_implied_return` and `analyst_label`. | `0` |
| `ANALYST_RETURN_THRESHOLD` | Percentage threshold to determine bullish/bearish classification (e.g. 10.0 means ±10 % return for classification). | `10.0` |
| `ANALYST_PROVIDER` | Provider for analyst targets. Supported values: `fmp` (Financial Modeling Prep) or `yahoo` (yfinance). | `fmp` |
| `ANALYST_API_KEY` | Optional API key for the chosen provider (fallbacks to `FMP_API_KEY` when provider=`fmp`). | — |
| `FEATURE_FINVIZ_CHART` | Enable Finviz chart fallback for alerts when QuickChart or rich alerts are disabled. | `0` |
| `FINVIZ_SCREENER_VIEW` | Finviz screener view ID used by the breakout scanner and Finviz charts. | `152` |
| `ANALYZER_UTC_HOUR` | Hour (UTC) when the analyzer daily job runs. | `21` |
| `ANALYZER_UTC_MINUTE` | Minute (UTC) for the analyzer job. | `30` |
| `TZ` | Default timezone for log formatting and scheduling. | `America/Chicago` |

| `FEATURE_SEC_DIGESTER` | Enable classification and aggregation of SEC filings (8‑K, 424B5, FWP, 13D/G). When on, the bot annotates events with recent SEC filings and updates the watchlist cascade. | `0` |
| `SEC_LOOKBACK_DAYS` | Number of days to consider when aggregating SEC filings for sentiment. Older filings are ignored. | `7` |
| `SENTIMENT_WEIGHT_SEC` | Weight assigned to the SEC sentiment score when aggregating with other sentiment providers. Set to `0` to exclude SEC sentiment from the combined gauge. | `0.2` |

| `FEATURE_BULLISHNESS_GAUGE` | Enable the combined bullishness sentiment gauge computed from local, external, SEC, analyst and earnings sentiment. When on, alerts include a **Bullishness** field summarising the weighted score and label (Bullish/Neutral/Bearish). | `0` |
| `FEATURE_SENTIMENT_LOGGING` | Enable per‑event sentiment logging. When set, the bot appends a JSON record for each processed event to `data/sentiment_logs/YYYY‑MM‑DD.jsonl` capturing the component scores and final gauge. | `0` |
| `ALLOWED_EXCHANGES` | Comma‑separated list of exchange codes to allow during feed ingestion. Tickers whose headlines specify an exchange not in this list are dropped before price filtering. Values are compared case‑insensitively. | `nasdaq,nyse,amex` |
| `SENTIMENT_WEIGHT_LOCAL` | Weight assigned to the local VADER sentiment score when aggregating into the bullishness gauge. | `0.4` |
| `SENTIMENT_WEIGHT_EXT` | Weight assigned to the aggregated external news sentiment when computing the gauge. | `0.3` |
| `SENTIMENT_WEIGHT_ANALYST` | Weight assigned to the analyst sentiment score (implied return) when computing the gauge. | `0.1` |

| `FEATURE_EARNINGS_ALERTS` | Enable earnings alerts and sentiment integration.  When set, the bot attaches upcoming earnings dates and surprise metrics to events and factors the surprise score into the sentiment gauge. | `0` |
| `EARNINGS_LOOKAHEAD_DAYS` | Number of days ahead to include upcoming earnings.  Earnings scheduled beyond this window are ignored. | `14` |
| `SENTIMENT_WEIGHT_EARNINGS` | Weight assigned to the earnings sentiment score when aggregating with other sentiment providers. Set to `0` to exclude earnings sentiment. | `0.1` |

| `FEATURE_SCREENER_BOOST` | Enable screener boost support.  When set, the bot loads tickers from the file defined by `SCREENER_CSV` once per cycle and treats them as part of the watchlist.  Tickers appearing in this CSV will bypass the price ceiling filter during feed processing. | `0` |
| `SCREENER_CSV` | Path to a Finviz screener CSV.  This file should include a `Ticker` or `Symbol` column (case insensitive) identifying each ticker.  If no standard header is present, the loader falls back to using the first column.  Used only when `FEATURE_SCREENER_BOOST=1`. | `data/finviz.csv` |

| `QUICKCHART_BASE_URL` | Base URL for the QuickChart API.  Override this to point to a self‑hosted QuickChart server (e.g. `http://localhost:3400/chart`).  When unset, the bot uses `https://quickchart.io/chart`. | — |

| `PRICE_FLOOR` | Minimum price threshold for tickers.  When set to a positive value, tickers with a last price below this threshold are skipped during feed ingestion.  Use this to ignore penny stocks. | `0` |

All new variables are optional; leaving them unset will disable the
corresponding provider or use sensible defaults.  When disabled or when
providers fail to return a score, the bot falls back to the local
sentiment analyser (`FEATURE_LOCAL_SENTIMENT`).

### Behaviour changes and refinements

- **Unified classifier now on by default**: `FEATURE_CLASSIFIER_UNIFY` now defaults
  to `1` in `env.example.ini`.  This flag directs feeds and analyzer
  modules to use `classify.classify()` for preliminary scoring instead of
  the legacy `classifier.py`.  The legacy classifier is retained for
  backward compatibility and may be removed in a future release.  Set
  `FEATURE_CLASSIFIER_UNIFY=0` in your `.env` to revert to the old
  implementation.

- **Heartbeat counters and end‑of‑day summary**: The heartbeat embed now
  displays both the counts from the most recent cycle and cumulative totals
  across the entire run (formatted as `new | total`).  At shutdown or
  end‑of‑day completion, the runner emits a final heartbeat with reason
  `endday` summarising the totals.  No configuration is required to
  enable this feature.

- **Refined Finviz noise filter**: Additional spam/legal phrases have been
  added to the built‑in Finviz noise filter.  Users can further extend
  the filter by creating a `data/filters/finviz_noise.txt` file with one
  keyword per line (lines starting with `#` are ignored).  When present,
  these custom terms are loaded automatically at runtime.

- **Chart fallback improvements**: The QuickChart helper now falls back to a
  daily line chart when intraday data is unavailable.  The helper also
  respects `QUICKCHART_BASE_URL` for all generated URLs.  No new
  environment variables are introduced; simply ensure `QUICKCHART_BASE_URL`
  includes the `/chart` path when using a self‑hosted QuickChart instance.