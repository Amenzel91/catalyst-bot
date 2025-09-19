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

| `FEATURE_EARNINGS_ALERTS` | Enable earnings alerts and sentiment integration.  When set, the bot attaches upcoming earnings dates and surprise metrics to events and factors the surprise score into the sentiment gauge. | `0` |
| `EARNINGS_LOOKAHEAD_DAYS` | Number of days ahead to include upcoming earnings.  Earnings scheduled beyond this window are ignored. | `14` |
| `SENTIMENT_WEIGHT_EARNINGS` | Weight assigned to the earnings sentiment score when aggregating with other sentiment providers. Set to `0` to exclude earnings sentiment. | `0.1` |

| `QUICKCHART_BASE_URL` | Base URL for the QuickChart API.  Override this to point to a self‑hosted QuickChart server (e.g. `http://localhost:3400/chart`).  When unset, the bot uses `https://quickchart.io/chart`. | — |

All new variables are optional; leaving them unset will disable the
corresponding provider or use sensible defaults.  When disabled or when
providers fail to return a score, the bot falls back to the local
sentiment analyser (`FEATURE_LOCAL_SENTIMENT`).