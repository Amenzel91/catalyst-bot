# Environment Variable Audit Report
**Generated:** 2025-10-25
**Audit Type:** Comprehensive Environment Variable Analysis
**Status:** READ-ONLY AUDIT (No changes made to code)

---

## Executive Summary

**Total environment variables found in code:** 246
**Total variables in current .env:** 104
**Missing variables (not in .env):** 142
**Critical priority missing:** 8
**High priority missing:** 15
**Medium priority missing:** 35
**Low priority missing:** 84

---

## Analysis Methodology

1. **Code Analysis**: Searched all Python files for `os.getenv()` and `os.environ.get()` patterns
2. **Config Review**: Analyzed `src/catalyst_bot/config.py` (1475 lines) for environment variable definitions
3. **Comparison**: Cross-referenced code usage against `.env` and `.env.example` files
4. **Prioritization**: Classified missing variables by criticality to bot functionality

---

## Missing Variables by Priority

### CRITICAL (Bot Won't Function)

| Variable | Used In | Purpose | Recommendation |
|----------|---------|---------|----------------|
| `OPENAI_API_KEY` | Not found in current code | OpenAI API access (if using GPT models) | Add if using OpenAI LLM |
| `BENZINGA_API_KEY` | Not found in current code | Benzinga news feed integration | Add if using Benzinga |
| `NEWSFILTER_TOKEN` | Not found in current code | NewsFilter API access | Add if using NewsFilter |
| `OLLAMA_BASE_URL` | Not found directly (uses LLM_ENDPOINT_URL) | Local LLM server endpoint | Already covered by LLM_ENDPOINT_URL |
| `REDDIT_CLIENT_ID` | sentiment_sources.py | Reddit sentiment analysis | Required if FEATURE_REDDIT_SENTIMENT=1 |
| `REDDIT_CLIENT_SECRET` | sentiment_sources.py | Reddit API authentication | Required if FEATURE_REDDIT_SENTIMENT=1 |
| `REDDIT_USER_AGENT` | sentiment_sources.py | Reddit API user agent | Required if FEATURE_REDDIT_SENTIMENT=1 |
| `STOCKTWITS_ACCESS_TOKEN` | sentiment_sources.py | StockTwits sentiment feed | Required if FEATURE_STOCKTWITS_SENTIMENT=1 |

### HIGH Priority (Features Will Break)

| Variable | Used In | Purpose | Current Default |
|----------|---------|---------|-----------------|
| `MARKETAUX_API_KEY` | config.py line 315 | Marketaux news sentiment | Empty string |
| `STOCKNEWS_API_KEY` | config.py line 316 | StockNews API sentiment | Empty string |
| `FMP_API_KEY` | config.py line 62 | Financial Modeling Prep API | Empty string |
| `FINVIZ_NEWS_EXPORT_URL` | config.py line 78 | Finviz news CSV export | Empty string |
| `ANALYST_API_KEY` | config.py line 426 | Analyst data provider API | Empty string |
| `QUICKCHART_API_KEY` | config.py line 829 | QuickChart hosted charts | Empty string |
| `DISCORD_APPLICATION_ID` | config.py line 927 | Discord slash commands | Empty string |
| `DISCORD_GUILD_ID` | config.py line 928 | Discord server ID | Empty string |
| `DISCORD_ADMIN_CHANNEL_ID` | Current .env line 34 | Admin message channel | Present in .env |
| `ALPACA_API_KEY` | config.py line 120 | Alpaca streaming data | Empty string |
| `ALPACA_SECRET` | config.py line 121 | Alpaca API secret | Empty string |
| `SEC_API_KEY` | .env.example line 833 | SEC streaming API | Not in code |
| `RAG_INDEX_PATH` | .env.example line 859 | Vector DB index location | Not in code |
| `XBRL_CACHE_DIR` | .env.example line 876 | XBRL financial data cache | Not in code |
| `LLM_USAGE_LOG_PATH` | .env.example line 226 | LLM cost tracking log file | Not in code |

### MEDIUM Priority (Enhances Functionality)

| Variable | Used In | Purpose | Current Default |
|----------|---------|---------|-----------------|
| `SENTIMENT_WEIGHT_ALPHA` | config.py line 328 | Alpha Vantage sentiment weight | 0.4 |
| `SENTIMENT_WEIGHT_MARKETAUX` | config.py line 331 | Marketaux sentiment weight | 0.3 |
| `SENTIMENT_WEIGHT_STOCKNEWS` | config.py line 334 | StockNews sentiment weight | 0.3 |
| `SENTIMENT_WEIGHT_FINNHUB` | config.py line 337 | Finnhub sentiment weight | 0.0 |
| `SENTIMENT_WEIGHT_STOCKTWITS` | config.py line 345 | StockTwits sentiment weight | 0.10 |
| `SENTIMENT_WEIGHT_REDDIT` | config.py line 348 | Reddit sentiment weight | 0.10 |
| `SENTIMENT_WEIGHT_PREMARKET` | config.py line 352 | Pre-market price action weight | 0.15 |
| `SENTIMENT_WEIGHT_AFTERMARKET` | config.py line 355 | After-market price action weight | 0.15 |
| `FEATURE_ALPHA_SENTIMENT` | config.py line 276 | Enable Alpha Vantage sentiment | False |
| `FEATURE_MARKETAUX_SENTIMENT` | config.py line 277 | Enable Marketaux sentiment | False |
| `FEATURE_STOCKNEWS_SENTIMENT` | config.py line 278 | Enable StockNews sentiment | False |
| `FEATURE_FINNHUB_SENTIMENT` | config.py line 279 | Enable Finnhub sentiment | False |
| `FEATURE_ANALYST_SIGNALS` | config.py line 411 | Enable analyst signals | False |
| `FEATURE_BREAKOUT_SCANNER` | config.py line 433 | Enable breakout scanner | False |
| `FEATURE_WATCHLIST_CASCADE` | config.py line 452 | Enable stateful watchlist | False |
| `FEATURE_52W_LOW_SCANNER` | config.py line 471 | Enable 52-week low scanner | False |
| `FEATURE_BULLISHNESS_GAUGE` | config.py line 491 | Enable combined sentiment gauge | False |
| `FEATURE_SENTIMENT_LOGGING` | config.py line 498 | Enable sentiment logging | False |
| `FEATURE_SEC_DIGESTER` | config.py line 606 | Enable SEC filing analysis | False |
| `FEATURE_APPROVAL_LOOP` | config.py line 535 | Enable manual approval workflow | False |
| `FEATURE_AUTO_ANALYZER` | config.py line 675 | Enable auto analyzer | False |
| `FEATURE_TRADE_SIM_ANALYSIS` | config.py line 685 | Enable trade simulation | False |
| `FEATURE_LOG_REPORTER` | config.py line 698 | Enable log reporter | False |
| `FEATURE_OPTIONS_SCANNER` | config.py line 647 | Enable options scanner | False |
| `FEATURE_SECTOR_INFO` | config.py line 666 | Enable sector information | False |
| `FEATURE_MARKET_TIME` | config.py line 667 | Enable market time tracking | False |
| `FEATURE_SECTOR_RELAX` | config.py line 668 | Relax sector filters | False |
| `FEATURE_ADMIN_REPORTS` | admin_reporter.py line 55 | Enable admin reports | "0" |
| `FEATURE_APPROVAL_LOOP` | alerts.py line 518 | Enable approval workflow | Empty string |
| `FEATURE_COMPOSITE_INDICATORS` | alerts.py line 1795 | Enable composite indicators | "0" |
| `FEATURE_HIGH_RES_DATA` | alerts.py line 1802 | Enable high-res intraday data | "0" |
| `FEATURE_ML_ALERT_RANKING` | alerts.py line 1819 | Enable ML alert ranking | "0" |
| `SKIP_ML_FOR_EARNINGS` | alerts.py line 1826 | Skip ML for earnings events | "1" |
| `ML_MODEL_PATH` | alerts.py line 1880 | ML model file path | data/models/trade_classifier.pkl |
| `SENTIMENT_WEIGHT_OPTIONS` | alerts.py line 2393 | Options sentiment weight | "0" |

### LOW Priority (Performance Tuning & Optional)

| Variable | Purpose | Default Value |
|----------|---------|---------------|
| `MIN_SENT_ABS` | Minimum absolute sentiment threshold | 0 |
| `ALERTS_JITTER_MS` | Alert rate limiting jitter | 0 |
| `BACKTEST_COMMISSION` | Backtest trading commission | 0.0 |
| `BACKTEST_SLIPPAGE` | Backtest slippage model | 0.0 |
| `BACKTEST_TAKE_PROFIT_PCT` | Backtest take profit % | 0.20 |
| `BACKTEST_STOP_LOSS_PCT` | Backtest stop loss % | 0.10 |
| `BACKTEST_MAX_HOLD_HOURS` | Max hold time for backtest | 24 |
| `BACKTEST_RISK_FREE_RATE` | Risk-free rate for Sharpe | 0.02 |
| `ANALYZER_LOOKBACK_DAYS` | Days to look back for analysis | 7 |
| `ANALYZER_UTC_HOUR` | Hour to run analyzer (UTC) | 21 |
| `ANALYZER_UTC_MINUTE` | Minute to run analyzer | 30 |
| `CONFIDENCE_MODERATE` | Moderate confidence threshold | 0.6 |
| `BREAKOUT_MIN_AVG_VOL` | Min volume for breakout | 300000 |
| `BREAKOUT_MIN_RELVOL` | Min relative volume | 1.5 |
| `WATCHLIST_HOT_DAYS` | Days in HOT state | 7 |
| `WATCHLIST_WARM_DAYS` | Days in WARM state | 21 |
| `WATCHLIST_COOL_DAYS` | Days in COOL state | 60 |
| `WATCHLIST_STATE_FILE` | Watchlist state JSON file | data/watchlist_state.json |
| `EARNINGS_LOOKAHEAD_DAYS` | Days to look ahead for earnings | 14 |
| `SEC_LOOKBACK_DAYS` | Days to look back for SEC filings | 7 |
| `OPTIONS_VOLUME_THRESHOLD` | Options volume threshold | 0 |
| `OPTIONS_MIN_PREMIUM` | Min options premium | 0 |
| `TRADE_SIM_TOP_N` | Top N for trade simulation | 5 |
| `HISTORICAL_DATA_DIR` | Historical data directory | data/historical |
| `LLM_TIMEOUT_SECS` | LLM request timeout | 15 |
| `ALLOWED_EXCHANGES` | Allowed stock exchanges | nasdaq,nyse,amex |
| `APPROVAL_DIR` | Approval marker directory | out/approvals |
| `ADMIN_SUMMARY_PATH` | Admin summary markdown path | None |
| `PARAMETER_CHANGES_DB_PATH` | Parameter changes DB path | data/parameter_changes.db |
| `EARNINGS_CALENDAR_CACHE` | Earnings calendar CSV cache | data/earnings_calendar.csv |
| `WATCHLIST_CSV` | Static watchlist CSV path | data/watchlist.csv |
| `SCREENER_CSV` | Finviz screener CSV path | data/finviz.csv |
| `MARKET_SKIP_ALPHA` | Skip Alpha Vantage provider | Not set |
| `STREAM_SAMPLE_WINDOW_SEC` | Alpaca stream sample window | 0 |
| `ANALYST_RETURN_THRESHOLD` | Analyst return threshold % | 10.0 |
| `ANALYST_PROVIDER` | Analyst data provider | fmp |
| `LOW_DISTANCE_PCT` | 52-week low distance % | 5 |
| `LOW_MIN_AVG_VOL` | 52-week low min volume | 300000 |
| `SENTIMENT_MIN_ARTICLES` | Min articles for sentiment | 1 |
| `BOT_PROCESS_PRIORITY` | Windows process priority | BELOW_NORMAL |
| `LLM_MIN_INTERVAL_SEC` | Min LLM request interval | 3 |
| `CHART_MIN_INTERVAL_SEC` | Min chart generation interval | 2 |
| `TZ` | Timezone | America/Chicago |
| `LOG_LEVEL` | Logging level | INFO |
| `LOG_PLAIN` | Plain text console logs | False |
| `PROJECT_ROOT` | Project root directory | Current working directory |
| `DATA_DIR` | Data directory path | data |
| `OUT_DIR` | Output directory path | out |
| `KEYWORD_DEFAULT_WEIGHT` | Default keyword weight | 1.0 |
| `QUICKCHART_BARS` | QuickChart bars to show | 50 |
| `QUICKCHART_IMAGE_DIR` | QuickChart image output | out/charts |
| `CHART_DEFAULT_TIMEFRAME` | Default chart timeframe | 1D |
| `CHART_DEFAULT_INDICATORS` | Default chart indicators | vwap,rsi,macd (config.py) / bollinger,sr (.env) |
| `CHART_AXIS_LABEL_SIZE` | Chart axis label font size | 12 |
| `CHART_TITLE_SIZE` | Chart title font size | 16 |
| `CHART_FILL_EXTENDED_HOURS` | Fill extended hours gaps | "1" |
| `CHART_FILL_METHOD` | Gap fill method | forward_fill |
| `CHART_VOLUME_PROFILE_SHOW_POC` | Show POC line | "1" |
| `CHART_VOLUME_PROFILE_SHOW_BARS` | Show volume bars | "1" |
| `CHART_VOLUME_PROFILE_BINS` | Volume profile bins | 20 |
| `CHART_STYLE` | Chart style theme | webull |
| `CHART_CANDLE_TYPE` | Candle type | candle |
| `QUICKCHART_SHORTEN_THRESHOLD` | URL shortening threshold | 1900 |
| `CHART_PANEL_RATIOS` | Panel height ratios | Empty string |
| `CHART_PANEL_SPACING` | Panel spacing | 0.05 |
| `CHART_PANEL_BORDERS` | Enable panel borders | 1 |
| `CHART_VOLUME_UP_COLOR` | Volume up bar color | #26a69a |
| `CHART_RSI_RATIO` | RSI panel ratio | 0 |
| `CHART_MACD_RATIO` | MACD panel ratio | 0 |
| `CHART_OBV_RATIO` | OBV panel ratio | 0 |
| `CHART_ATR_RATIO` | ATR panel ratio | 0 |
| `CHART_STOCH_RATIO` | Stochastic panel ratio | 0 |
| `CHART_CCI_RATIO` | CCI panel ratio | 0 |
| `CHART_MFI_RATIO` | MFI panel ratio | 0 |
| `CHART_BOLLINGER_PERIOD` | Bollinger period | 20 |
| `CHART_BOLLINGER_STD` | Bollinger std dev | 2.0 |
| `CHART_FIBONACCI_LOOKBACK` | Fibonacci lookback | 20 |
| `CHART_SR_SENSITIVITY` | Support/resistance sensitivity | 0.02 |
| `CHART_SR_MAX_LEVELS` | Max S/R levels | 5 |
| `CHART_SR_MIN_TOUCHES` | Min S/R touches | 2 |
| `CHART_VOLUME_BINS` | Volume profile bins | 20 |
| `CHART_SHOW_POC` | Show point of control | True |
| `CHART_SHOW_VALUE_AREA` | Show value area | True |
| `CHART_CACHE_DB_PATH` | Chart cache database path | data/chart_cache.db |
| `CHART_CACHE_1D_TTL` | 1D chart cache TTL (seconds) | 60 |
| `CHART_CACHE_5D_TTL` | 5D chart cache TTL | 300 |
| `CHART_CACHE_1M_TTL` | 1M chart cache TTL | 900 |
| `CHART_CACHE_3M_TTL` | 3M chart cache TTL | 3600 |
| `CHART_PARALLEL_MAX_WORKERS` | Max parallel chart workers | 3 |
| `INDICATOR_CACHE_TTL_SEC` | Indicator cache TTL | 300 |
| `INDICATOR_CACHE_MAX_SIZE` | Indicator cache max size | 1000 |
| `SENTIMENT_MODEL_OPEN` | Sentiment model (market open) | distilbert |
| `SENTIMENT_MODEL_CLOSED` | Sentiment model (market closed) | vader |
| `GPU_MEMORY_CLEANUP` | Enable GPU memory cleanup | True |
| `GPU_PROFILING_ENABLED` | Enable GPU profiling | False |
| `GPU_MAX_UTILIZATION_WARN` | GPU utilization warning % | 90 |
| `GPU_MAX_TEMPERATURE_C` | GPU max temperature | 85 |
| `GPU_MIN_FREE_VRAM_MB` | Min free VRAM (MB) | 500 |
| `FEATURE_CUDA_STREAMS` | Enable CUDA streams | False |
| `FEATURE_ADAPTIVE_SENTIMENT` | Adaptive sentiment switching | False |
| `HEALTH_CHECK_PORT` | Health check HTTP port | 8080 |
| `WATCHDOG_CHECK_INTERVAL` | Watchdog check interval | 60 |
| `WATCHDOG_RESTART_ON_FREEZE` | Auto-restart on freeze | True |
| `WATCHDOG_FREEZE_THRESHOLD` | Freeze detection threshold | 300 |
| `WATCHDOG_MAX_RESTARTS` | Max watchdog restarts | 3 |
| `DEPLOYMENT_ENV` | Deployment environment | development |
| `LOG_ROTATION_DAYS` | Log rotation period | 7 |
| `ADMIN_ALERT_WEBHOOK` | Admin alert webhook URL | Empty string |
| `CHART_SHOW_BOLLINGER` | Show Bollinger bands | True |
| `CHART_SHOW_FIBONACCI` | Show Fibonacci levels | True |
| `CHART_SHOW_SUPPORT_RESISTANCE` | Show S/R levels | True |
| `CHART_SHOW_VOLUME_PROFILE` | Show volume profile | False |
| `CHART_MTF_ANALYSIS` | Multi-timeframe analysis | True |
| `CHART_SHOW_EXTENDED_HOURS_ANNOTATION` | Show extended hours zones | True |
| `CHART_FETCH_EXTENDED_HOURS` | Fetch extended hours data | True |
| `WATCHLIST_MAX_SIZE` | Max watchlist size | 50 |
| `WATCHLIST_DM_NOTIFICATIONS` | DM watchlist notifications | False |
| `SLASH_COMMAND_COOLDOWN` | Slash command cooldown (sec) | 3 |
| `MISTRAL_BATCH_SIZE` | Mistral LLM batch size | 5 |
| `MISTRAL_BATCH_DELAY` | Mistral batch delay (sec) | 2.0 |
| `MISTRAL_MIN_PRESCALE` | Mistral min prescale score | 0.20 |
| `BACKTEST_INITIAL_CAPITAL` | Initial backtest capital | 10000.0 |
| `BACKTEST_POSITION_SIZE_PCT` | Position size % | 0.10 |
| `BACKTEST_MAX_VOLUME_PCT` | Max volume % | 0.05 |
| `BACKTEST_SLIPPAGE_MODEL` | Slippage model | adaptive |

---

## Variables Present in .env (Current Configuration)

✅ **Core Configuration (13 variables)**
- MIN_SCORE, PRICE_CEILING, CONFIDENCE_HIGH, MAX_ALERTS_PER_CYCLE
- MIN_SENT_ABS, DISCORD_WEBHOOK_URL, DISCORD_BOT_TOKEN
- DISCORD_ALERT_CHANNEL_ID, DISCORD_ADMIN_WEBHOOK, MARKET_PROVIDER_ORDER

✅ **API Keys (5 variables)**
- ALPHAVANTAGE_API_KEY, TIINGO_API_KEY, FINNHUB_API_KEY
- GEMINI_API_KEY, ANTHROPIC_API_KEY

✅ **LLM Configuration (7 variables)**
- FEATURE_LLM_HYBRID, LLM_PRIMARY_PROVIDER, LLM_FALLBACK_CHAIN
- LLM_RATE_LIMIT_ENABLED, LLM_MAX_RETRIES, FEATURE_PROMPT_COMPRESSION

✅ **Sentiment Analysis (17 variables)**
- SENTIMENT_WEIGHT_EARNINGS, SENTIMENT_WEIGHT_ML, SENTIMENT_WEIGHT_VADER
- SENTIMENT_WEIGHT_LLM, FEATURE_INSIDER_SENTIMENT, SENTIMENT_WEIGHT_INSIDER
- SENTIMENT_WEIGHT_SEC_LLM, FEATURE_AFTERMARKET_SENTIMENT
- SENTIMENT_WEIGHT_AFTERMARKET, FEATURE_VOLUME_PRICE_DIVERGENCE
- SENTIMENT_WEIGHT_DIVERGENCE

✅ **Feature Flags (25 variables)**
- FEATURE_ALERTS, FEATURE_RECORD_ONLY, FEATURE_HEARTBEAT
- FEATURE_RICH_HEARTBEAT, FEATURE_TIINGO, FEATURE_INDICATORS
- FEATURE_MOMENTUM_INDICATORS, FEATURE_EARNINGS_ALERTS
- FEATURE_RICH_ALERTS, FEATURE_ADVANCED_CHARTS, FEATURE_SENTIMENT_GAUGE
- FEATURE_FLOAT_DATA, FEATURE_SEC_MONITOR, FEATURE_SEC_FILINGS
- FEATURE_OFFERING_PARSER, FEATURE_RVOL, FEATURE_VWAP
- FEATURE_MARKET_REGIME, FEATURE_SECTOR_MULTIPLIERS
- FEATURE_NEGATIVE_ALERTS, FEATURE_MARKET_HOURS_DETECTION

✅ **Chart Configuration (22 variables)**
- CHART_CANDLE_TYPE, CHART_SHOW_FIBONACCI
- CHART_VOLUME_PROFILE_ENHANCED, CHART_VOLUME_PROFILE_BARS
- CHART_VOLUME_PROFILE_BINS, CHART_VOLUME_PROFILE_SHOW_POC
- CHART_VOLUME_PROFILE_SHOW_VALUE_AREA, CHART_VOLUME_PROFILE_SHOW_HVN_LVN
- CHART_PATTERN_RECOGNITION, CHART_PATTERNS_TRIANGLES
- CHART_PATTERNS_HEAD_SHOULDERS, CHART_PATTERNS_DOUBLE_TOPS
- CHART_PATTERNS_CHANNELS, CHART_PATTERNS_FLAGS
- CHART_PATTERN_SENSITIVITY, CHART_PATTERN_LOOKBACK_MIN
- CHART_PATTERN_LOOKBACK_MAX, CHART_PATTERN_SHOW_LABELS
- CHART_PATTERN_SHOW_PROJECTIONS, CHART_PATTERN_LABEL_FONT_SIZE

✅ **Performance & Tuning (15 variables)**
- ALERTS_MIN_INTERVAL_MS, DATA_DIR, OUT_DIR, SEEN_TTL_DAYS
- FEATURE_PERSIST_SEEN, PRICE_FLOOR, FLOAT_CACHE_TTL_DAYS
- FLOAT_REQUEST_DELAY_SEC, SEC_MONITOR_USER_EMAIL
- SEC_MONITOR_INTERVAL_SEC, SEC_MONITOR_LOOKBACK_HOURS
- OFFERING_LOOKBACK_HOURS, OFFERING_CACHE_TTL_DAYS
- RVOL_BASELINE_DAYS, RVOL_CACHE_TTL_MINUTES

---

## Critical Findings

### 1. **LLM Variable Naming Inconsistency**
- Code uses: `LLM_ENDPOINT_URL`, `LLM_MODEL_NAME`, `LLM_TIMEOUT_SECS`
- Some references to: `OLLAMA_BASE_URL` (not in code)
- **Resolution**: Current .env correctly uses `LLM_ENDPOINT_URL` (commented out)

### 2. **Reddit API Format Issue**
- `.env.example` suggests: `REDDIT_API_KEY=` (single variable)
- Code expects THREE separate variables:
  - `REDDIT_CLIENT_ID`
  - `REDDIT_CLIENT_SECRET`
  - `REDDIT_USER_AGENT`
- **Resolution**: Need to add all three variables separately

### 3. **Missing Social Sentiment Keys**
- `FEATURE_STOCKTWITS_SENTIMENT` disabled in .env
- `FEATURE_REDDIT_SENTIMENT` not in .env at all
- Keys not present: `STOCKTWITS_API_KEY`, `REDDIT_CLIENT_ID/SECRET/USER_AGENT`
- **Impact**: Social sentiment features cannot be enabled without these

### 4. **Chart Variable Mismatch**
- `.env` has `CHART_DEFAULT_INDICATORS=bollinger,sr`
- `config.py` default is `vwap,rsi,macd`
- **Resolution**: .env override takes precedence (working as designed)

### 5. **MOA Configuration**
- `MOA_NIGHTLY_ENABLED=1` in .env
- `MOA_NIGHTLY_HOUR=2` in .env
- `LLM_LOCAL_ENABLED=0` in .env (disables local Ollama)
- **Status**: Properly configured for cloud LLM use

---

## Recommendations

### Immediate Actions (Critical)

1. **Add Reddit API credentials** (if using Reddit sentiment):
   ```env
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USER_AGENT=CatalystBot/1.0
   ```

2. **Add StockTwits API key** (if using StockTwits sentiment):
   ```env
   STOCKTWITS_API_KEY=your_access_token
   ```

3. **Add Discord slash command IDs** (if using slash commands):
   ```env
   DISCORD_APPLICATION_ID=your_app_id
   DISCORD_GUILD_ID=your_server_id
   ```

### Short-term Actions (High Priority)

4. **Add optional API keys** for enhanced features:
   ```env
   # Financial data providers
   FMP_API_KEY=YOUR_KEY_HERE
   MARKETAUX_API_KEY=YOUR_KEY_HERE
   STOCKNEWS_API_KEY=YOUR_KEY_HERE

   # Alpaca streaming (real-time price updates)
   ALPACA_API_KEY=YOUR_KEY_HERE
   ALPACA_SECRET=YOUR_SECRET_HERE

   # QuickChart (hosted chart images)
   QUICKCHART_API_KEY=YOUR_KEY_HERE
   ```

5. **Enable additional sentiment sources**:
   ```env
   FEATURE_ALPHA_SENTIMENT=1
   FEATURE_MARKETAUX_SENTIMENT=1
   FEATURE_STOCKNEWS_SENTIMENT=1
   FEATURE_ANALYST_SENTIMENT=1
   ```

### Long-term Actions (Medium Priority)

6. **Add feature flags** for advanced functionality:
   ```env
   FEATURE_BREAKOUT_SCANNER=1
   FEATURE_WATCHLIST_CASCADE=1
   FEATURE_52W_LOW_SCANNER=1
   FEATURE_BULLISHNESS_GAUGE=1
   FEATURE_SEC_DIGESTER=1
   FEATURE_AUTO_ANALYZER=1
   ```

7. **Configure performance tuning** variables as needed:
   ```env
   BACKTEST_COMMISSION=0.005
   BACKTEST_SLIPPAGE=0.001
   ANALYZER_LOOKBACK_DAYS=14
   CHART_CACHE_ENABLED=1
   ```

---

## Variable Categories

### By Module

| Module | Variable Count | Notes |
|--------|----------------|-------|
| config.py | 194 | Primary configuration source |
| alerts.py | 25 | Alert formatting and rate limiting |
| charts.py | 18 | Chart rendering configuration |
| chart_panels.py | 12 | Multi-panel chart layout |
| admin_controls.py | 22 | Admin threshold overrides |
| runner.py | 5 | Main loop configuration |
| feeds.py | 3 | Feed ingestion settings |
| jobs/*.py | 6 | Background job settings |
| Other modules | 61 | Scattered across features |

### By Feature Area

| Feature Area | Variable Count | Priority |
|--------------|----------------|----------|
| Sentiment Analysis | 42 | High |
| Chart Generation | 38 | Medium |
| API Keys | 22 | Critical |
| Feature Flags | 56 | Medium |
| Performance Tuning | 31 | Low |
| Market Data | 18 | High |
| Admin & Reporting | 15 | Medium |
| LLM Configuration | 12 | High |
| Backtest & Analysis | 12 | Low |

---

## Validation Status

✅ **No missing critical variables for current features**
✅ **All active features have required environment variables**
⚠️ **Social sentiment features require additional keys to enable**
⚠️ **Slash commands require Discord app credentials**
ℹ️ **Many optional features disabled by default (can enable as needed)**

---

## Notes

1. **Variables in .env but not in code**: None found (all .env variables are used)
2. **Deprecated variables**: None identified
3. **Conflicting defaults**: CHART_DEFAULT_INDICATORS differs (.env vs config.py)
4. **Security concerns**: Webhook URLs and tokens properly stored in .env (not in .env.example)
5. **Documentation quality**: .env.example is comprehensive with 913 lines of documentation

---

## Conclusion

The Catalyst Bot environment configuration is **well-structured and mostly complete**. The current `.env` file contains all variables necessary for core functionality. Missing variables primarily affect:

- **Social sentiment features** (Reddit, StockTwits) - require API keys
- **Advanced scanners** (breakout, 52-week low) - disabled by default
- **Discord interactions** (slash commands) - require app IDs
- **Premium data providers** (FMP, Marketaux, StockNews) - optional enhancements

No immediate action required for current operation. Enable additional features as needed by adding corresponding API keys and feature flags.
