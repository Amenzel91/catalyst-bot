# Catalyst-Bot

**AI-Powered Catalyst Trading Bot with Multi-Timeframe Backtesting & Analysis**

Catalyst-Bot is an event-driven trading system that monitors SEC filings, press releases, and news feeds in real-time, uses LLM-based classification to identify high-probability catalysts, and provides comprehensive backtesting and analysis tools to continuously improve performance.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Running the Bot](#running-the-bot)
  - [Backtesting & Analysis](#backtesting--analysis)
  - [False Positive Analysis](#false-positive-analysis)
- [Data Providers](#data-providers)
- [Backtesting System](#backtesting-system)
- [Analysis System](#analysis-system)
- [Development](#development)
- [Testing](#testing)
- [Roadmap](#roadmap)

---

## Features

### Real-Time Trading
- **Multi-source monitoring**: SEC 8-K, SEC 424B5, SEC FWP, SEC 13D/G, GlobeNewswire, PR Newswire, Business Wire
- **LLM-based classification**: Hybrid Gemini + Ollama for intelligent catalyst detection
- **Multi-factor scoring**: Keywords, sentiment, fundamentals, sector context, RVOL
- **Smart filtering**: Price ceiling, market cap, volume thresholds
- **Automated alerting**: Discord webhooks with rich embeds
- **Watchlist integration**: FinViz screener CSV import

### Backtesting & Analysis
- **Historical Bootstrapper**: Backfill 6-12 months of rejected items with price outcomes
- **Multi-timeframe tracking**: 15m, 30m, 1h, 4h, 1d, 7d
- **Full OHLC + volume**: Complete price action data for each timeframe
- **Tiingo integration**: 20+ years of intraday historical data
- **MOA (Mixture of Agents) Analyzer**: Identify missed opportunities and generate recommendations
- **False Positive Tracker**: Analyze accepted items that failed to perform
- **Statistical validation**: Bootstrap confidence intervals with 10,000 samples
- **Flash catalyst detection**: Identify >5% moves in 15-30 minutes

### Advanced Features (NEW)
- **RVOL (Relative Volume)**: Track volume vs 20-day average
- **Fundamental data integration**: Float shares and short interest scoring
- **Sector context tracking**: Sector performance and relative strength
- **LLM stability patches**: GPU memory management, batching, rate limiting
- **Multi-level caching**: Memory → Disk → API with intelligent TTL

---

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │       Data Sources                  │
                     │  SEC EDGAR │ News Feeds │ FinViz   │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │       Feed Aggregator               │
                     │  Deduplication │ Enrichment         │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────────────┐
                     │       Classification Pipeline       │
                     │  Prescale │ LLM │ Scoring          │
                     │  Keywords │ Sentiment │ Fundamentals│
                     │  RVOL │ Sector Context              │
                     └──────────────┬──────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          │                   │
             ┌────────────▼──────────┐   ┌───▼───────────────┐
             │   ACCEPTED            │   │   REJECTED        │
             │   Send Alert          │   │   Log for MOA     │
             └────────────┬──────────┘   └───┬───────────────┘
                          │                   │
             ┌────────────▼──────────┐   ┌───▼───────────────┐
             │  False Positive       │   │  Historical       │
             │  Tracker              │   │  Bootstrapper     │
             │  (Track failures)     │   │  (Backfill prices)│
             └────────────┬──────────┘   └───┬───────────────┘
                          │                   │
                          │   ┌───────────────▼────────────────┐
                          └───►  MOA Analyzer                  │
                              │  • Keyword correlation         │
                              │  • Timing patterns             │
                              │  • RVOL correlation            │
                              │  • Sector performance          │
                              │  • Generate recommendations    │
                              └────────────────────────────────┘
```

---

## Installation

### Prerequisites

- Python 3.10+
- Virtual environment (recommended)
- API keys (see Configuration)

### Steps

```bash
# Clone the repository
git clone https://github.com/yourusername/catalyst-bot.git
cd catalyst-bot

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks (for development)
pre-commit install
```

---

## Configuration

### 1. Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

### 2. Required API Keys

**Free Tier:**
```ini
# Google Gemini (1000 RPM, 4M TPM - $1.80/month)
GEMINI_API_KEY=your_gemini_key

# Finnhub (60 calls/min - FREE)
FINNHUB_API_KEY=your_finnhub_key

# Discord Webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**Recommended Paid Services:**
```ini
# Tiingo ($30/month - 20k calls/day, 20+ years intraday data)
FEATURE_TIINGO=1
TIINGO_API_KEY=your_tiingo_key

# FinViz Elite ($40/month - real-time screener, fundamentals)
FINVIZ_API_KEY=your_finviz_elite_cookie
```

**Optional Providers:**
```ini
# Alpha Vantage (25 calls/day free, or paid tiers)
ALPHA_VANTAGE_API_KEY=your_av_key

# Marketaux (100 articles/day free)
MARKETAUX_API_KEY=your_marketaux_key
```

### 3. Feature Flags

Enable optional features:

```ini
# LLM Features
FEATURE_LLM=1                      # Enable LLM classification (vs keywords-only)
FEATURE_OLLAMA_FALLBACK=1          # Enable local Ollama fallback

# Data Features
FEATURE_TIINGO=1                   # Enable Tiingo intraday data
FEATURE_FUNDAMENTAL_SCORING=1      # Enable float/short interest scoring

# Bot Features
FEATURE_SCREENER_BOOST=1           # Enable FinViz screener import
FEATURE_PRESCALE_SKIP=0            # Disable prescale filtering (not recommended)
```

### 4. LLM Stability Settings (Wave 0.2)

```ini
# Batching & Rate Limiting
LLM_BATCH_SIZE=5                   # Items per batch
LLM_BATCH_DELAY_SEC=2.0            # Delay between batches
LLM_MIN_PRESCALE_SCORE=0.20        # Pre-filter threshold (73% load reduction)
LLM_MIN_INTERVAL_SEC=3.0           # Min seconds between requests

# GPU Management
GPU_CLEANUP_INTERVAL_SEC=300       # Cleanup every 5 minutes
```

---

## Usage

### Running the Bot

#### Live Trading Mode

```bash
# Run once (single pass)
python -m catalyst_bot.runner

# Run in loop (continuous monitoring)
python -m catalyst_bot.runner --loop

# Custom loop interval
python -m catalyst_bot.runner --loop --sleep-secs 300  # 5 minutes
```

#### Dry Run Mode

Test without sending alerts:

```bash
python -m catalyst_bot.runner --dry-run
```

---

### Backtesting & Analysis

The backtesting system has two main components:

1. **Historical Bootstrapper**: Backfills price outcomes for rejected items
2. **MOA Analyzer**: Analyzes patterns and generates recommendations

#### Step 1: Historical Bootstrapper

Collect historical price outcomes for rejected items:

```bash
# Basic usage (1 month, SEC 8-K only)
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-11-01 \
  --end-date 2024-12-01 \
  --sources sec_8k

# Multiple sources
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-11-01 \
  --end-date 2024-12-01 \
  --sources sec_8k,globenewswire_public

# Large-scale backtest (3-6 months recommended)
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-10-01 \
  --end-date 2025-01-01 \
  --sources sec_8k,globenewswire_public
```

**What it does:**
- Reads `data/rejected_items.jsonl`
- Fetches price data for each rejected ticker at 6 timeframes (15m, 30m, 1h, 4h, 1d, 7d)
- Collects RVOL, fundamental data (float/SI), and sector context
- Stores results in `data/moa/outcomes.jsonl`

**Data collected per rejection:**
- Close price and return % for each timeframe
- High/low prices and max gains/losses
- Pre-event price context (1d, 7d, 30d history)
- RVOL (relative volume vs 20-day average)
- Fundamental data (float shares, short interest)
- Sector context (sector performance, relative strength)
- Market context (volume, ATR)

**Performance:**
- ~10-30 seconds per ticker (depends on cache hits)
- Tiingo: 20k calls/day = ~400-600 tickers/day
- Without Tiingo: Limited to last 60 days (yfinance)

#### Step 2: MOA Analyzer

Analyze patterns and generate keyword weight recommendations:

```bash
# Run full analysis
python -m catalyst_bot.moa_historical_analyzer

# Custom thresholds
python -m catalyst_bot.moa_historical_analyzer \
  --min-return 10.0 \
  --min-occurrences 3
```

**What it does:**
- Loads `data/moa/outcomes.jsonl`
- Identifies "missed opportunities" (rejected items with >10% gains)
- Analyzes keyword correlation with success
- Analyzes RVOL correlation
- Analyzes sector performance patterns
- Analyzes timing patterns (hour of day, day of week)
- Generates keyword weight recommendations
- Outputs comprehensive report to `data/moa/analysis_report.json`

**Key Insights Generated:**
- **Miss rate**: % of profitable catalysts that were rejected
- **Keyword correlation**: Which keywords predict success
- **Timing patterns**: Best hours/days for catalysts
- **RVOL impact**: How volume affects catalyst success
- **Sector patterns**: Which sectors respond best to catalysts
- **Flash catalysts**: Rapid price movements (>5% in 15-30min)
- **Recommendations**: Suggested keyword weight adjustments

**Example Output:**
```json
{
  "summary": {
    "total_outcomes": 450,
    "missed_opportunities": 67,
    "miss_rate": 14.9,
    "avg_return_missed": 24.3
  },
  "keyword_analysis": {
    "FDA approval": {
      "total": 23,
      "missed": 18,
      "miss_rate": 78.3,
      "avg_return": 31.2,
      "recommendation": "BOOST +2.0"
    }
  },
  "rvol_analysis": {
    "HIGH (>2.0)": {
      "miss_rate": 8.2,
      "avg_return": 28.5
    },
    "LOW (<1.0)": {
      "miss_rate": 21.7,
      "avg_return": 12.3
    }
  }
}
```

#### Step 3: Apply Recommendations

Review and apply keyword weight recommendations:

1. Open `data/moa/analysis_report.json`
2. Review keyword recommendations
3. Update keyword weights in `src/catalyst_bot/keywords.py`
4. Test with `--dry-run` mode
5. Deploy to production

---

### False Positive Analysis

Track and analyze accepted items that failed to perform:

#### Step 1: Automatic Logging

The bot automatically logs all accepted items to `data/accepted_items.jsonl` (no setup required).

#### Step 2: Track Outcomes

Fetch price outcomes for accepted items:

```bash
# Track last 7 days
python -m catalyst_bot.false_positive_tracker --lookback-days 7

# Track specific date range
python -m catalyst_bot.false_positive_tracker \
  --start-date 2024-11-01 \
  --end-date 2024-11-15
```

**What it does:**
- Reads `data/accepted_items.jsonl`
- Fetches price outcomes (1h, 4h, 1d)
- Classifies as SUCCESS (met thresholds) or FAILURE
- Stores results in `data/false_positives/outcomes.jsonl`

**Success Thresholds:**
- 1h return > 2% OR
- 4h return > 3% OR
- 1d return > 5%

#### Step 3: Analyze Patterns

Generate insights and recommendations:

```bash
python -m catalyst_bot.false_positive_analyzer
```

**What it does:**
- Analyzes keyword failure rates
- Identifies problematic news sources
- Finds score correlation with failures
- Detects time-of-day patterns
- Generates keyword penalty recommendations
- Outputs report to `data/false_positives/analysis_report.json`

**Key Insights:**
- **Precision**: % of accepted items that were profitable
- **False positive rate**: % of accepted items that failed
- **Keyword failures**: Which keywords generate bad signals
- **Source quality**: Which news sources are unreliable
- **Penalty recommendations**: Suggested keyword weight reductions

---

## Data Providers

### Price Data (Priority Chain)

1. **Tiingo** (PRIMARY - requires paid subscription)
   - 20+ years of intraday data (15m, 30m, 1h bars)
   - 20,000 calls/day
   - Real-time + historical
   - **Best for:** Multi-timeframe backtesting

2. **Alpha Vantage** (BACKUP)
   - Free tier: 25 calls/day
   - Paid tier: 75-1200 calls/day
   - Intraday + daily data
   - **Best for:** Free tier testing

3. **yfinance** (FALLBACK)
   - Free, no API key required
   - Last 60 days of intraday data only
   - Rate limited by IP
   - **Best for:** Recent data fallback

### Sentiment / News Data (Priority Chain)

1. **Finnhub** (PRIMARY - FREE)
   - 60 calls/minute free tier
   - Excellent news coverage
   - Real-time company news
   - **Best for:** Sentiment analysis

2. **Alpha Vantage** (BACKUP)
   - News + sentiment API
   - 25-50 calls/day free tier
   - **Best for:** Backup sentiment

3. **Marketaux** (OPTIONAL)
   - 100 articles/day free tier
   - Filtered, high-quality news
   - **Best for:** Additional news sources

### Fundamental Data

1. **FinViz Elite** (PAID - $40/month)
   - Real-time screener access
   - Float shares, short interest
   - 68+ data columns
   - **Best for:** Fundamental scoring

2. **yfinance** (FALLBACK - FREE)
   - Basic fundamental data
   - Market cap, shares outstanding
   - **Best for:** Free tier fallback

---

## Backtesting System

### Architecture

```
rejected_items.jsonl (input)
  ↓
Historical Bootstrapper
  ↓
┌─────────────────────────────────┐
│ For each rejected item:         │
│  1. Extract ticker + rejection  │
│     timestamp                   │
│  2. Fetch price data:           │
│     - Tiingo (if enabled)       │
│     - Fallback to yfinance      │
│  3. Calculate outcomes:         │
│     - 15m, 30m, 1h, 4h, 1d, 7d  │
│     - Close, high, low, volume  │
│  4. Enrich with context:        │
│     - RVOL (volume vs 20d avg)  │
│     - Fundamentals (float, SI)  │
│     - Sector (performance, rel) │
│  5. Store in outcomes.jsonl     │
└─────────────────────────────────┘
  ↓
outcomes.jsonl (output)
  ↓
MOA Analyzer
  ↓
┌─────────────────────────────────┐
│ Analysis:                       │
│  1. Identify missed opps        │
│     (return > threshold)        │
│  2. Keyword correlation         │
│  3. RVOL correlation            │
│  4. Sector patterns             │
│  5. Timing patterns             │
│  6. Flash catalyst detection    │
│  7. Generate recommendations    │
└─────────────────────────────────┘
  ↓
analysis_report.json (output)
```

### Data Flow

**Input:** `data/rejected_items.jsonl`
```json
{
  "ticker": "ABCD",
  "rejection_ts": "2024-11-15T14:30:00Z",
  "source": "sec_8k",
  "title": "FDA Approval Announcement",
  "prescale_score": 0.45,
  "keywords_matched": ["FDA", "approval"],
  "rejection_reason": "prescale_too_low"
}
```

**Output:** `data/moa/outcomes.jsonl`
```json
{
  "ticker": "ABCD",
  "rejection_ts": "2024-11-15T14:30:00Z",
  "rejection_price": 12.50,
  "outcomes": {
    "15m": {"close": 13.20, "return_pct": 5.6, "high": 13.50, "low": 12.45},
    "30m": {"close": 13.80, "return_pct": 10.4, "high": 14.20, "low": 12.40},
    "1h": {"close": 14.50, "return_pct": 16.0, "high": 15.30, "low": 12.50},
    "4h": {"close": 15.20, "return_pct": 21.6, "high": 16.80, "low": 12.30},
    "1d": {"close": 16.50, "return_pct": 32.0, "high": 17.20, "low": 12.00},
    "7d": {"close": 18.30, "return_pct": 46.4, "high": 19.50, "low": 11.80}
  },
  "rvol": 3.2,
  "fundamental_data": {
    "float_shares": 8500000,
    "short_interest": 18.5
  },
  "sector_context": {
    "sector": "Healthcare",
    "sector_1d_return": 0.8,
    "sector_vs_spy": 0.3
  }
}
```

### Caching Strategy

Multi-level caching minimizes API calls:

1. **Memory Cache** (instant)
   - In-process dictionary
   - Cleared on restart

2. **Disk Cache** (fast, persistent)
   - Parquet files in `data/cache/`
   - 2-level directory structure
   - TTL-based expiration (1-30 days depending on data type)

3. **API Call** (slow, rate-limited)
   - Only when cache misses occur
   - Results cached for future use

**Cache Hit Rates (typical):**
- First run: 0% (cold cache)
- Second run: 80-95% (warm cache)
- Incremental update: 95-99% (hot cache)

---

## Analysis System

### MOA (Mixture of Agents) Analyzer

The MOA Analyzer identifies patterns in missed opportunities and generates actionable recommendations.

#### Analysis Modules

1. **Keyword Correlation Analysis**
   - Tracks which keywords appear in missed opportunities
   - Calculates miss rate per keyword
   - Generates weight boost recommendations
   - Min occurrences filter (default: 3)

2. **RVOL Correlation Analysis**
   - Compares success rates across RVOL categories (HIGH/MODERATE/LOW)
   - Identifies volume thresholds for success
   - Recommends volume-based filtering

3. **Sector Performance Analysis**
   - Tracks which sectors have best catalyst response
   - Identifies hot vs cold sector patterns
   - Recommends sector-aware prioritization

4. **Timing Pattern Analysis**
   - Hour of day distribution
   - Day of week patterns
   - Pre-market vs regular hours vs after-hours

5. **Flash Catalyst Detection**
   - Identifies rapid price movements (>5% in 15-30min)
   - Tracks keyword patterns for flash catalysts
   - Recommends intraday optimization

6. **Statistical Validation**
   - Bootstrap resampling (10,000 samples)
   - 95% confidence intervals
   - Sample size validation

#### Recommendation Generation

The analyzer generates three types of recommendations:

1. **Keyword Weight Adjustments**
   ```python
   "FDA approval": {
     "current_weight": 1.0,
     "recommended_weight": 3.0,
     "boost": +2.0,
     "confidence": "high",
     "sample_size": 23
   }
   ```

2. **Filtering Rules**
   ```python
   "RVOL": {
     "recommendation": "Prioritize RVOL > 2.0",
     "impact": "8.2% miss rate vs 21.7% for low RVOL"
   }
   ```

3. **Timing Optimizations**
   ```python
   "timing": {
     "recommendation": "Focus on 9-11 AM EST catalysts",
     "impact": "35% of missed opportunities occur in this window"
   }
   ```

---

## Development

### Project Structure

```
catalyst-bot/
├── src/catalyst_bot/
│   ├── runner.py                      # Main bot runner
│   ├── feeds.py                       # Feed aggregation
│   ├── classify.py                    # Classification pipeline
│   ├── llm_hybrid.py                  # LLM interface
│   ├── keywords.py                    # Keyword definitions + weights
│   ├── market.py                      # Price data providers
│   ├── sentiment_sources.py           # Sentiment providers
│   ├── fundamental_data.py            # Fundamental data collection
│   ├── rvol.py                        # RVOL calculation (NEW)
│   ├── sector_context.py              # Sector tracking (NEW)
│   ├── fundamental_scoring.py         # Fundamental scoring (NEW)
│   ├── llm_stability.py               # LLM stability (NEW)
│   ├── historical_bootstrapper.py     # Backtesting engine
│   ├── moa_historical_analyzer.py     # MOA analyzer
│   ├── false_positive_tracker.py      # False positive tracking (NEW)
│   ├── false_positive_analyzer.py     # False positive analysis (NEW)
│   └── ...
├── tests/
│   ├── test_rvol.py                   # RVOL tests (17 tests)
│   ├── test_fundamental_scoring.py    # Fundamental tests (27 tests)
│   ├── test_sector_context.py         # Sector tests (24 tests)
│   ├── test_false_positive_tracker.py # False positive tests (13 tests)
│   ├── test_llm_stability.py          # LLM stability tests (40 tests)
│   └── ...
├── data/
│   ├── rejected_items.jsonl           # Rejected classifications
│   ├── accepted_items.jsonl           # Accepted classifications (NEW)
│   ├── moa/
│   │   ├── outcomes.jsonl             # Backtest outcomes
│   │   └── analysis_report.json       # MOA analysis
│   ├── false_positives/
│   │   ├── outcomes.jsonl             # False positive outcomes (NEW)
│   │   └── analysis_report.json       # FP analysis (NEW)
│   └── cache/                         # Disk cache
├── docs/
│   └── patches/                       # Patch documentation
├── .env                               # Configuration (create from .env.example)
├── requirements.txt                   # Python dependencies
├── README.md                          # This file
└── BACKTESTING_ANALYZER_ROADMAP.md    # Detailed roadmap (NEW)
```

### Adding New Features

1. **New Data Source**
   - Add provider to `market.py` or `sentiment_sources.py`
   - Update priority chain documentation
   - Add tests in `tests/test_market.py` or `tests/test_sentiment.py`

2. **New Keyword**
   - Add to `keywords.py` with initial weight
   - Add to keyword extraction logic
   - Run backtest to validate impact
   - Adjust weight based on MOA recommendations

3. **New Scoring Factor**
   - Create module in `src/catalyst_bot/`
   - Add to classification pipeline in `classify.py`
   - Add to bootstrapper for backtest collection
   - Add to MOA analyzer for correlation analysis

---

## Testing

### Run All Tests

```bash
# Full test suite
pytest

# Specific test file
pytest tests/test_rvol.py

# With coverage
pytest --cov=catalyst_bot tests/

# Verbose output
pytest -v
```

### Test Coverage

- **Total Tests:** 366
- **Passing:** 357 (97.5%)
- **New Features:** 121 new tests
  - RVOL: 17 tests
  - Fundamental Scoring: 27 tests
  - Sector Context: 24 tests
  - False Positive: 13 tests
  - LLM Stability: 40 tests

### Pre-commit Hooks

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files

# Hooks included:
# - black (formatting)
# - isort (import sorting)
# - autoflake (unused imports)
# - flake8 (linting)
```

---

## Roadmap

See **[BACKTESTING_ANALYZER_ROADMAP.md](BACKTESTING_ANALYZER_ROADMAP.md)** for detailed roadmap.

### Current Status: 90% Complete

**Production Ready:**
- ✅ Multi-timeframe backtesting
- ✅ MOA analysis with recommendations
- ✅ False positive tracking
- ✅ RVOL, fundamentals, sector context
- ✅ LLM stability patches
- ✅ Statistical validation

**High Priority (Before Full Launch):**
- ⚠️ VIX / Market regime classification (2-3 days)
- ⚠️ Enhanced error handling (1 day)
- ⚠️ Large-scale integration test (1 day)

**Medium Priority (Post-Launch):**
- 🔮 Keyword co-occurrence analysis (2 days)
- 🔮 Multi-catalyst correlation (3 days)
- 🔮 Machine learning classifier (2 weeks)

**Low Priority (Future):**
- 🔮 Options chain integration (1 week)
- 🔮 Database backend (1 week)
- 🔮 Real-time dashboard (2 weeks)

---

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/catalyst-bot/issues)
- **Documentation**: [docs/](docs/)
- **Roadmap**: [BACKTESTING_ANALYZER_ROADMAP.md](BACKTESTING_ANALYZER_ROADMAP.md)

---

## License

[Your License Here]

---

## Acknowledgments

- Gemini API for LLM classification
- Tiingo for intraday historical data
- FinViz for fundamental data and screeners
- Finnhub for real-time news and sentiment

---

**Last Updated:** January 2025
**Version:** 2.0 (Backtesting & Analysis Release)
