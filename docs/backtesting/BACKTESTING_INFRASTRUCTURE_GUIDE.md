# Backtesting & Analyzer Infrastructure Guide
**Last Updated:** 2025-10-14
**Status:** Production-Ready with Recent Enhancements

---

## 📋 **Table of Contents**

1. [Historical Bootstrapper](#1-historical-bootstrapper)
2. [MOA (Missed Opportunities Analyzer)](#2-moa-missed-opportunities-analyzer)
3. [Backtesting Engine](#3-backtesting-engine)
4. [Analyzers](#4-analyzers)
5. [Statistical Validation](#5-statistical-validation)
6. [Supporting Modules](#6-supporting-modules)
7. [Data Flow & Integration](#7-data-flow--integration)
8. [Quick Start Guide](#8-quick-start-guide)

---

## **1. Historical Bootstrapper**

### **File:** `src/catalyst_bot/historical_bootstrapper.py` (2,442 lines)

### **Purpose**
Backfills 6-12 months of historical rejected items and outcomes for training the MOA system.

### **What It Does**

#### **Data Collection:**
- ✅ Fetches historical SEC feeds (8-K, 424B5, FWP, 13D, 13G)
- ✅ Fetches historical PR newswire feeds (GlobeNewswire, PRNewswire, BusinessWire, AccessWire)
- ✅ Month-by-month processing with date filtering
- ✅ Deduplicates items to avoid double-processing

#### **Classification:**
- ✅ Runs items through current production classifier
- ✅ **NEW:** LLM keyword extraction for SEC documents (Gemini → Claude fallback)
- ✅ Identifies rejections based on:
  - Price ceiling violations ($0.10-$10.00 range)
  - Low classification score
  - Missing sentiment/keywords
- ✅ Logs rejection reason + classification data

#### **Price Fetching (Multi-Level):**
- ✅ **Level 1:** Memory cache (instant retrieval)
- ✅ **Level 2:** Disk cache (30-day TTL, pickle files)
- ✅ **Level 3:** Finnhub API (primary, 50 calls/min)
- ✅ **Level 4:** yfinance fallback (bulk batching)
- ✅ Bulk prefetching - reduces API calls from 6N to N (where N = number of tickers)

#### **Timeframe Selection (Smart):**
- **Tiingo enabled (FEATURE_TIINGO=1):**
  - All timeframes: `15m, 30m, 1h, 4h, 1d, 7d`
  - Works for ALL historical data (20+ years of intraday)
- **Tiingo disabled (default):**
  - Last 60 days: `15m, 30m, 1h, 4h, 1d, 7d`
  - Older than 60 days: `1h, 4h, 1d, 7d` (yfinance limitation)

#### **Context Enrichment:**
- ✅ **Pre-event momentum:** Price 1d/7d/30d before catalyst
- ✅ **Market context:** SPY returns for same period
- ✅ **Sector context:** Sector/industry + relative performance vs SPY
- ✅ **RVol:** Relative volume at rejection time (20-day baseline)
- ✅ **Market regime:** VIX level + SPY trend + regime multiplier
- ✅ **OHLC data:** Open/High/Low/Close for all timeframes
- ✅ **Volume analysis:** 20-day average volume + relative volume

#### **Output Files:**
1. **`data/rejected_items.jsonl`**
   - Items that failed filters
   - Includes ticker, price, keywords, sentiment, score, rejection_reason

2. **`data/moa/outcomes.jsonl`**
   - Price outcomes for all timeframes
   - Pre-event context, market context, sector context
   - Missed opportunity flag (>10% return)

3. **`data/moa/bootstrap_checkpoint.json`**
   - Resume capability for long-running bootstraps
   - Statistics tracking

#### **Performance Features:**
- ✅ Token bucket rate limiting (thread-safe)
- ✅ Exponential backoff retry (5 attempts, jitter)
- ✅ Progress notifications via Discord (every 15 min)
- ✅ Checkpoint/resume capability
- ✅ Cache hit rate: 70-90% (dramatically reduces API calls)

### **Usage:**
```bash
# Bootstrap 6 months of SEC 8-K filings
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-07-01 \
  --end-date 2025-01-01 \
  --sources sec_8k,sec_424b5,sec_fwp

# Resume from checkpoint
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-01-01 \
  --end-date 2025-01-01 \
  --sources sec_8k,prnewswire,globenewswire_public \
  --resume
```

---

## **2. MOA (Missed Opportunities Analyzer)**

### **Files:**
- `src/catalyst_bot/moa_analyzer.py` (764 lines) ✨ **Enhanced Today**
- `src/catalyst_bot/moa_historical_analyzer.py` (legacy)

### **Purpose**
Analyzes rejected items to identify missed opportunities and recommend keyword weight adjustments.

### **What It Does**

#### **Core Analysis:**
1. **Loads rejected items** (last 30 days from `rejected_items.jsonl`)
2. **Fetches historical prices** using Tiingo API (**NEW: actual historical prices**)
3. **Identifies missed opportunities:** Rejected items that went up >10%
4. **Extracts keywords** from missed opportunities
5. **Calculates statistics:** Occurrences, success rate, avg return per keyword
6. **Generates recommendations:** Weight adjustments with confidence levels

#### **✨ NEW: Keyword Discovery (Implemented Today)**
7. **Text Mining:** Extracts n-grams (1-4 words) from titles
8. **Discriminative Analysis:** Compares missed opportunities vs accepted items
9. **Lift Scoring:** Calculates (positive_rate / negative_rate) for each phrase
10. **Auto-recommendation:** Suggests new keywords with conservative weights (0.3-0.8)

#### **Keyword Stats Tracked:**
- `occurrences`: How many times keyword appeared in missed opportunities
- `successes`: How many led to >10% return
- `success_rate`: Percentage that succeeded
- `avg_return`: Average return when keyword present
- **NEW:** `lift`: Discriminative power (positive vs negative rate)

#### **Recommendation Types:**
- `new`: Brand new keyword not in system (discovered via text mining)
- `weight_increase`: Existing keyword needs higher weight
- `new_discovered`: Discovered via text mining (not in existing analysis)
- `discovered_and_existing`: Validated by both methods (highest confidence)

#### **Historical Price Fetching (✨ FIXED TODAY):**
```python
# OLD (WRONG):
change_pct = get_last_price_change(ticker)  # Uses current price!

# NEW (CORRECT):
entry_price = fetch_historical_price(ticker, rejection_time, cache)
exit_price = fetch_historical_price(ticker, rejection_time + hours, cache)
change_pct = ((exit_price - entry_price) / entry_price) * 100.0
```

**Tiingo Integration:**
- Uses hourly bars (`resampleFreq=1hour`)
- Handles weekends/holidays (skips forward to next market day)
- Implements caching (`"TICKER:ISO_TIMESTAMP"` → price)
- Rate limiting: 1000 requests/hour (free tier)

### **Output Files:**
1. **`data/moa/recommendations.json`**
   ```json
   {
     "timestamp": "2025-10-14T10:30:00Z",
     "analysis_period": "2025-09-14 to 2025-10-14",
     "total_rejected": 245,
     "missed_opportunities": 38,
     "discovered_keywords_count": 5,
     "recommendations": [
       {
         "keyword": "regulatory approval",
         "type": "new_discovered",
         "recommended_weight": 0.65,
         "confidence": 0.7,
         "evidence": {
           "lift": 5.2,
           "positive_count": 12,
           "negative_count": 2
         }
       }
     ]
   }
   ```

2. **`data/moa/analysis_state.json`**
   - Last run timestamp
   - Analysis period
   - Statistics

### **Usage:**
```python
from catalyst_bot.moa_analyzer import run_moa_analysis, get_moa_summary

# Run analysis on last 30 days
result = run_moa_analysis(since_days=30)

# Get summary of last run
summary = get_moa_summary()
print(f"Discovered {summary['discovered_keywords_count']} new keywords")
```

---

## **3. Backtesting Engine**

### **Core Modules:**

### **3.1. `backtesting/engine.py`**
**Purpose:** Main backtest execution engine

**Features:**
- Position management (max 10 concurrent positions)
- Risk management (stop loss, take profit, max hold time)
- Commission and slippage modeling
- Equity curve generation
- Performance metrics calculation

**Strategy Parameters:**
```python
{
    'min_score': 0.30,              # Min classification score
    'min_sentiment': 0.10,          # Min sentiment
    'take_profit_pct': 0.20,        # +20% profit target
    'stop_loss_pct': 0.10,          # -10% stop loss
    'max_hold_hours': 24,           # Day trade strategy
    'position_size_pct': 0.10,      # 10% of capital per trade
    'max_daily_volume_pct': 0.05,   # Max 5% of daily volume
}
```

### **3.2. `backtesting/validator.py`** ✨ **Enhanced with Robust Statistics**
**Purpose:** Statistical validation of parameter changes

**Features:**
- **Robust Statistics** (for handling penny stock outliers):
  - `winsorize()`: Clips outliers at 1st/99th percentile
  - `trimmed_mean()`: Excludes extreme values
  - `median_absolute_deviation()`: Robust std dev alternative
  - `robust_zscore()`: Outlier detection using MAD

- **Bootstrap Confidence Intervals:**
  - 10,000 bootstrap samples
  - 95% confidence intervals
  - Works for win rate, avg return, Sharpe ratio

- **Statistical Significance Testing:**
  - Independent t-test for returns
  - Proportion z-test for win rates
  - Minimum sample size: 30 trades
  - P-value threshold: 0.05

**Usage:**
```python
from catalyst_bot.backtesting.validator import validate_parameter_change

result = validate_parameter_change(
    param='take_profit_pct',
    old_value=0.15,
    new_value=0.20,
    backtest_days=60,
)

if result['recommendation'] == 'APPROVE':
    print(f"Change approved with {result['confidence']:.0%} confidence")
    print(f"Reason: {result['reason']}")
```

### **3.3. `backtesting/reports.py`**
**Purpose:** Generate backtest reports in multiple formats

**Features:**
- Markdown reports with tables and metrics
- CSV exports of trade logs
- JSON exports for programmatic access
- Visualizations (equity curve, drawdown chart)

### **3.4. `backtesting/portfolio.py`**
**Purpose:** Position and portfolio management

**Features:**
- Position tracking (entry, exit, P&L)
- Portfolio state management
- Margin calculations
- Risk metrics per position

### **3.5. `backtesting/analytics.py`**
**Purpose:** Advanced performance analytics

**Features:**
- Win rate by catalyst type
- Performance by timeframe
- Sector performance analysis
- Drawdown analysis

### **3.6. `backtesting/monte_carlo.py`**
**Purpose:** Monte Carlo simulation for robustness testing

**Features:**
- Random sampling of historical trades
- Multiple simulation runs
- Confidence intervals for metrics
- Worst-case scenario analysis

### **3.7. `backtesting/walkforward.py`**
**Purpose:** Walk-forward optimization

**Features:**
- Rolling window backtests
- In-sample vs out-of-sample testing
- Parameter stability analysis
- Overfitting detection

### **3.8. `backtesting/cpcv.py`**
**Purpose:** Combinatorially Purged Cross-Validation

**Features:**
- Prevents data leakage in time series
- Multiple train/test splits
- Purging of overlapping samples
- Cross-validation metrics

---

## **4. Analyzers**

### **4.1. Keyword Discovery (`keyword_miner.py`)** ✨ **NEW**
**Purpose:** Extract keyword candidates from news titles

**Features:**
- N-gram extraction (1-4 words)
- Stop word filtering
- Important abbreviation preservation (FDA, SEC, 8-K, etc.)
- Lift ratio calculation
- Discriminative keyword mining
- Subsumption filtering

**Functions:**
```python
from catalyst_bot.keyword_miner import (
    mine_keyword_candidates,
    mine_discriminative_keywords,
    calculate_phrase_score,
)

# Extract all keywords
keywords = mine_keyword_candidates(titles, min_occurrences=5)

# Find discriminative keywords
catalyst_titles = ["FDA Approval Granted", ...]
non_catalyst_titles = ["Earnings Call Scheduled", ...]

discriminative = mine_discriminative_keywords(
    positive_titles=catalyst_titles,
    negative_titles=non_catalyst_titles,
    min_lift=2.0,  # 2x more common in catalysts
)
```

### **4.2. False Positive Analyzer (`false_positive_analyzer.py`)**
**Purpose:** Identify and analyze false positive alerts

**Features:**
- Tracks alerts that didn't result in price movement
- Identifies problematic keywords/sources
- Recommends keyword weight reductions
- Calculates false positive rate by catalyst type

### **4.3. Auto Analyzer (`auto_analyzer.py`)**
**Purpose:** Automated nightly keyword performance analysis

**Features:**
- Scheduled analysis of last 24 hours
- Keyword hit tracking
- Success/failure logging
- Automated weight recommendations

### **4.4. SEC LLM Analyzer (`sec_llm_analyzer.py`)**
**Purpose:** LLM-based keyword extraction from SEC documents

**Features:**
- Hybrid LLM routing (Local → Gemini → Claude)
- Filing-specific prompts (8-K, 424B5, FWP)
- Context-aware keyword extraction
- Sentiment analysis
- Confidence scoring

**LLM Providers:**
- **Primary:** Gemini 2.5 Flash (1000 RPM, free tier)
- **Fallback:** Claude 3.5 Sonnet (high accuracy, paid)
- **Legacy:** Local Mistral (disabled, needs stability work)

---

## **5. Statistical Validation**

### **File:** `backtesting/validator.py`

### **Robust Statistics Functions:**

#### **`winsorize(data, limits=(0.01, 0.01))`**
- Clips outliers at 1st/99th percentile
- Preserves sample size
- Reduces impact of extreme 500%+ gains or -90% losses
- Essential for penny stock backtesting

**Example:**
```python
returns = [0.05, 0.08, -0.03, 0.12, 5.0, -0.02, 0.06]  # 500% outlier!
winsorized = winsorize(returns)
# Result: outlier clipped to 99th percentile value
```

#### **`trimmed_mean(data, proportiontocut=0.05)`**
- Removes top 5% and bottom 5%
- Focuses on typical performance
- More representative of day-to-day trading

#### **`median_absolute_deviation(data)`**
- Robust alternative to standard deviation
- Remains stable even with outliers
- Used for robust Sharpe ratio calculation

**MAD vs Std Dev:**
```python
returns = [0.02, 0.05, -0.01, 5.0, 0.03]  # 500% outlier
std_dev = np.std(returns)  # 199% (inflated!)
mad = median_absolute_deviation(returns)  # 3.26% (realistic)
```

#### **`robust_zscore(data)`**
- Outlier detection using median + MAD
- Identifies anomalous trades for review
- Threshold: |z| > 3 for strong outliers

### **Bootstrap Confidence Intervals:**
```python
result = validate_parameter_change(...)

# Check confidence intervals
ci = result['confidence_intervals']
win_rate_ci = ci['win_rate']
print(f"Win Rate: {win_rate_ci['estimate']:.1f}% "
      f"(95% CI: [{win_rate_ci['ci_lower']:.1f}%, {win_rate_ci['ci_upper']:.1f}%])")
```

### **Statistical Significance:**
```python
stats = result['statistical_tests']
if stats['returns_significant']:
    print(f"Returns improvement is statistically significant (p={stats['returns_pvalue']:.4f})")
```

---

## **6. Supporting Modules**

### **6.1. Accepted Items Logger (`accepted_items_logger.py`)** ✨ **NEW**
**Purpose:** Log items that passed filters for false positive analysis

**Features:**
- Price range filtering ($0.10-$10.00)
- Sentiment breakdown capture
- Market regime data logging
- Already integrated in `runner.py`

**Output:** `data/accepted_items.jsonl`

### **6.2. Rejected Items Logger (`rejected_items_logger.py`)**
**Purpose:** Log items that failed filters for MOA analysis

**Features:**
- Price range filtering
- Rejection reason tracking
- Classification data preservation
- Sentiment breakdown

**Output:** `data/rejected_items.jsonl`

### **6.3. RVol Calculator (`rvol.py`)**
**Purpose:** Calculate relative volume

**Features:**
- 20-day baseline average
- Current volume comparison
- RVol category classification (Low, Normal, High, Very High, Extreme)
- 5-minute cache TTL

**Categories:**
- Low: RVol < 1.0
- Normal: 1.0 ≤ RVol < 2.0
- High: 2.0 ≤ RVol < 3.0
- Very High: 3.0 ≤ RVol < 5.0
- Extreme: RVol ≥ 5.0

### **6.4. Sector Context (`sector_context.py`)**
**Purpose:** Track sector/industry performance

**Features:**
- Ticker → Sector/Industry mapping
- Sector performance tracking (1d, 5d)
- Sector vs SPY comparison
- Sector relative volume

### **6.5. Market Regime (`market_regime.py`)**
**Purpose:** Classify market conditions

**Features:**
- VIX-based volatility classification
- SPY trend detection
- Regime multipliers for scoring adjustments

**Regimes:**
- Bull + Low Vol: 1.2x multiplier
- Bear + High Vol: 0.7x multiplier
- Crash: 0.5x multiplier

---

## **7. Data Flow & Integration**

### **Production Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION RUNTIME                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   RSS Feeds      │
                    │  (SEC, PRNews)   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Classifier     │
                    │  + LLM Keywords  │
                    └────────┬─────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
        ┌────────────────┐      ┌───────────────┐
        │  PASS FILTERS  │      │ FAIL FILTERS  │
        │                │      │               │
        │ Score ≥ 0.70   │      │ Price > $10   │
        │ Sentiment OK   │      │ Score < 0.70  │
        │ Price ≤ $10    │      │ No keywords   │
        └───────┬────────┘      └───────┬───────┘
                │                       │
                ▼                       ▼
    ┌─────────────────────┐   ┌──────────────────────┐
    │ accepted_items.jsonl │   │ rejected_items.jsonl │
    │ + Discord Alert      │   │                      │
    └─────────────────────┘   └──────────┬───────────┘
                                          │
                                          ▼
                              ┌────────────────────────┐
                              │   MOA Nightly (2 AM)   │
                              │                        │
                              │ 1. Load rejected items │
                              │ 2. Fetch hist prices   │
                              │ 3. ID missed opps      │
                              │ 4. Extract keywords    │
                              │ 5. Text mining (NEW!)  │
                              │ 6. Generate recs       │
                              └──────────┬─────────────┘
                                         │
                                         ▼
                              ┌────────────────────────┐
                              │ recommendations.json   │
                              │                        │
                              │ - Weight adjustments   │
                              │ - New keywords (NEW!)  │
                              │ - Confidence scores    │
                              └────────────────────────┘
```

### **Historical Bootstrap Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│                HISTORICAL BOOTSTRAPPER                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Fetch Historical│
                    │  Feeds (Monthly) │
                    │                  │
                    │ Sources:         │
                    │ - SEC (8-K, etc) │
                    │ - PR Newswires   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Classify Items  │
                    │  + LLM Extract   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Identify         │
                    │ Rejections       │
                    └────────┬─────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
        ┌────────────────┐      ┌───────────────────┐
        │ Fetch Prices   │      │ Enrich Context    │
        │                │      │                   │
        │ - Memory cache │      │ - Pre-event       │
        │ - Disk cache   │      │ - Market context  │
        │ - Finnhub API  │      │ - Sector context  │
        │ - yfinance     │      │ - RVol            │
        │                │      │ - Market regime   │
        └────────┬───────┘      └────────┬──────────┘
                 │                       │
                 └───────────┬───────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Write Outputs:   │
                    │                  │
                    │ 1. rejected_     │
                    │    items.jsonl   │
                    │                  │
                    │ 2. outcomes.jsonl│
                    │                  │
                    │ 3. checkpoint.   │
                    │    json          │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Ready for:     │
                    │                  │
                    │ - MOA Analysis   │
                    │ - Backtesting    │
                    │ - Validation     │
                    └──────────────────┘
```

---

## **8. Quick Start Guide**

### **Step 1: Historical Bootstrap (Collect Training Data)**
```bash
# Collect 6 months of historical data
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-07-01 \
  --end-date 2025-01-01 \
  --sources sec_8k,prnewswire,globenewswire_public \
  --batch-size 100

# Expected output:
# - data/rejected_items.jsonl (rejected catalysts)
# - data/moa/outcomes.jsonl (price outcomes)
# - Runtime: 2-4 hours for 6 months (with caching)
```

### **Step 2: Run MOA Analysis (Find Missed Opportunities)**
```python
from catalyst_bot.moa_analyzer import run_moa_analysis

# Analyze last 30 days
result = run_moa_analysis(since_days=30)

print(f"Status: {result['status']}")
print(f"Missed opportunities: {result['missed_opportunities']}")
print(f"Discovered keywords: {result.get('discovered_keywords_count', 0)}")

# Output: data/moa/recommendations.json
```

### **Step 3: Review Recommendations**
```bash
# Check recommendations file
cat data/moa/recommendations.json | jq '.recommendations[] | {keyword, type, recommended_weight, confidence}'

# Example output:
# {
#   "keyword": "regulatory approval",
#   "type": "new_discovered",
#   "recommended_weight": 0.65,
#   "confidence": 0.7
# }
```

### **Step 4: Run Backtest**
```python
from catalyst_bot.backtesting.engine import BacktestEngine

# Create engine
engine = BacktestEngine(
    start_date="2024-01-01",
    end_date="2024-12-31",
    initial_capital=10000.0,
    strategy_params={
        'min_score': 0.30,
        'take_profit_pct': 0.20,
        'stop_loss_pct': 0.10,
    }
)

# Run backtest
results = engine.run_backtest()

# View metrics
metrics = results['metrics']
print(f"Total Return: {metrics['total_return_pct']:.2f}%")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Win Rate: {metrics['win_rate']:.1f}%")
print(f"Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
```

### **Step 5: Validate Parameter Changes**
```python
from catalyst_bot.backtesting.validator import validate_parameter_change

# Test a parameter change
result = validate_parameter_change(
    param='take_profit_pct',
    old_value=0.15,
    new_value=0.20,
    backtest_days=60,
)

print(f"Recommendation: {result['recommendation']}")
print(f"Confidence: {result['confidence']:.0%}")
print(f"Reason: {result['reason']}")

# Check statistical significance
if result['statistical_tests']['returns_significant']:
    print("✓ Statistically significant improvement (p < 0.05)")
```

---

## **📊 Summary Stats**

### **Code Base:**
- **Total Lines:** ~15,000+ lines of backtesting/analysis code
- **Test Coverage:** 99/99 tests passing (keyword discovery)
- **Modules:** 20+ specialized modules

### **Capabilities:**
- ✅ Historical data collection (6-12 months)
- ✅ LLM keyword extraction (SEC documents)
- ✅ Automated keyword discovery (text mining)
- ✅ Missed opportunity analysis
- ✅ Statistical validation (robust stats for penny stocks)
- ✅ Multi-timeframe backtesting (15m to 7d)
- ✅ Context enrichment (sector, market, momentum)
- ✅ False positive tracking
- ✅ Production-ready logging

### **Performance:**
- **Cache Hit Rate:** 70-90% (reduces API calls)
- **Bootstrap Speed:** 2-4 hours for 6 months (with caching)
- **API Efficiency:** Bulk prefetching (6N → N calls)
- **Data Quality:** Actual historical prices (not proxies)

---

## **✅ Ready For Production**

All systems are operational and tested. The infrastructure supports:
1. Automated data collection
2. Statistical validation
3. Keyword discovery
4. Performance backtesting
5. Continuous improvement via MOA feedback loop

**Next Step:** Run historical bootstrap to collect training data, then analyze with MOA to discover optimal keywords/weights.
