# Patch Status Review & Priority Order
**Generated:** 2025-10-13
**Source:** patches1.txt analysis + current codebase verification

---

## ✅ COMPLETED PATCHES (From patches1.txt)

### Quick Wins - All Completed 2025-10-13

#### 1. Float Data Collection (Priority 9/10) ✅
- **Status:** FULLY IMPLEMENTED
- **Files:** `float_data.py` (465 lines), integrated in classify.py, alerts.py
- **Expected Impact:** 4.2x volatility predictor
- **Actual Implementation:** Complete with FinViz scraping, cache, classification
- **.env Status:** `FEATURE_FLOAT_DATA=1` ✅

#### 2. SEC EDGAR Real-Time Monitor (Priority 9/10) ✅
- **Status:** FULLY IMPLEMENTED
- **Files:** `sec_monitor.py` (646 lines), integrated in runner.py, classify.py, alerts.py
- **Expected Impact:** 5-min latency on catalysts (15-30 min advantage)
- **Actual Implementation:** Background daemon, 5-min polling, filing classification
- **.env Status:** `FEATURE_SEC_MONITOR=1`, `SEC_MONITOR_USER_EMAIL=menzad05@gmail.com` ✅

#### 3. 424B5 Offering Parser (Priority 7/10) ✅
- **Status:** FULLY IMPLEMENTED
- **Files:** `offering_parser.py` (683 lines), integrated in classify.py, alerts.py
- **Expected Impact:** 30-40% reduction in dilution losses
- **Actual Implementation:** Complete with severity classification, dilution calculation
- **.env Status:** `FEATURE_OFFERING_PARSER=1` ✅

#### 4. RVol Calculation (Priority 8/10) ✅
- **Status:** FULLY IMPLEMENTED
- **Files:** `rvol.py` (enhanced), integrated in classify.py, alerts.py
- **Expected Impact:** "Strongest predictor of post-catalyst moves"
- **Actual Implementation:** Time-of-day adjustment, 5-min cache, classification
- **.env Status:** `FEATURE_RVOL=1` ✅

#### 5. MOA Nightly Scheduler ✅
- **Status:** FULLY IMPLEMENTED
- **Files:** runner.py (lines 1610-1732)
- **Expected Impact:** Automated learning loop
- **Actual Implementation:** 2 AM UTC scheduler, background thread, complete logging
- **.env Status:** Not in .env yet (uses default enabled) ⚠️

#### 6. Market Regime Detection ✅
- **Status:** FULLY IMPLEMENTED
- **Files:** `market_regime.py` (600+ lines), integrated everywhere
- **Expected Impact:** Context-aware scoring (0.5x-1.2x multipliers)
- **Actual Implementation:** 5 regimes, VIX + SPY trend, confidence scoring
- **.env Status:** Not in .env yet (uses default enabled) ⚠️

---

## 🔄 IN PROGRESS / PARTIALLY COMPLETED

### From patches1.txt - Phase 1 Remaining

#### 7. Robust Statistics (Priority 6/10) 🟡
- **Status:** PARTIALLY IMPLEMENTED
- **What Exists:** Bootstrap, t-tests, p-values
- **What's Missing:** Winsorization, trimmed means, MAD, robust z-scores
- **Complexity:** Low (3-5 days)
- **Expected Impact:** Statistical validity for penny stocks
- **Next Steps:** Implement robust stats in `backtesting/validator.py`

#### 8. VWAP Calculation (Priority 8/10) 🟡
- **Status:** NOT IMPLEMENTED
- **From patches1.txt:** "VWAP: Critical exit signal (91% accuracy)"
- **Complexity:** Low (2 days)
- **Expected Impact:** Prevents 91% of failed trades
- **Next Steps:** Create `vwap_calculator.py`, integrate with real-time price monitoring

#### 9. Bid/Ask Spread Tracking (Priority 6/10) 🟡
- **Status:** NOT IMPLEMENTED
- **Complexity:** Low (2 days)
- **Expected Impact:** Slippage awareness
- **Next Steps:** Add to market data pipeline

---

## ❌ NOT YET IMPLEMENTED - PRIORITY ORDER

Based on patches1.txt analysis and impact/complexity, here's the recommended implementation order:

---

### 🔥 PHASE 2A: Critical Short-Term Wins (1-2 weeks)

#### PATCH 1: VWAP Real-Time Calculation & Exit Signals
- **Priority:** 8/10 (HIGH)
- **Complexity:** Low (2 days)
- **Impact:** Prevents 91% of failed trades per research
- **Dependencies:** None (yfinance provides intraday data)
- **Implementation:**
  - Create `src/catalyst_bot/vwap_calculator.py`
  - Add VWAP calculation for intraday prices
  - Integrate into classify.py as exit signal metadata
  - Add to alerts.py (show VWAP break status)
  - Config: `FEATURE_VWAP=1`

#### PATCH 2: Robust Statistics (Winsorization + MAD)
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Low (3-5 days)
- **Impact:** Statistical validity for outlier-prone penny stocks
- **Dependencies:** None (scipy has these methods)
- **Implementation:**
  - Enhance `src/catalyst_bot/backtesting/validator.py`
  - Add `winsorize()` function (clip at 1st/99th percentile)
  - Add `trimmed_mean()` function (exclude top/bottom 5%)
  - Add `median_absolute_deviation()` for robust std dev
  - Add `robust_zscore()` using MAD
  - Integrate into bootstrap confidence interval calculations

#### PATCH 3: Bid/Ask Spread Tracking
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Low (2 days)
- **Impact:** Slippage awareness for backtests
- **Dependencies:** Tiingo or Alpaca (bid/ask data)
- **Implementation:**
  - Add spread fetching to `src/catalyst_bot/market.py`
  - Calculate estimated slippage: `slippage = spread / 2`
  - Store in metadata for backtest adjustments
  - Config: `FEATURE_BID_ASK_SPREAD=1`

**Phase 2A Expected Impact:** +5-10% win rate, improved backtest accuracy

---

### 🚀 PHASE 2B: Real-Time Systems (2-3 weeks)

#### PATCH 4: Real-Time Price Monitoring (1-Minute Updates)
- **Priority:** 7/10 (HIGH)
- **Complexity:** Medium-High (1-2 weeks)
- **Impact:** Dynamic exits, position management
- **Dependencies:** Alpaca subscription ($9/mo) or Polygon
- **Implementation:**
  - Create `src/catalyst_bot/realtime_monitor.py`
  - WebSocket connection to Alpaca/Polygon
  - 1-minute price update loop
  - VWAP monitoring for active positions
  - Position manager integration
  - Config: `FEATURE_REALTIME_PRICE=1`, `ALPACA_API_KEY=...`

#### PATCH 5: Dynamic Exit System
- **Priority:** 7/10 (HIGH)
- **Complexity:** Medium (1 week)
- **Impact:** Prevents holding losers, captures winners
- **Dependencies:** PATCH 4 (Real-Time Price Monitoring)
- **Implementation:**
  - Create `src/catalyst_bot/exit_manager.py`
  - Exit conditions: VWAP break, stop loss, take profit, time-based
  - Position tracking with entry/exit logic
  - Discord alerts for exits
  - Config: `FEATURE_DYNAMIC_EXITS=1`

#### PATCH 6: Social Sentiment Integration (StockTwits + Reddit)
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Medium (1 week)
- **Impact:** Early warning 2-6 hours before moves
- **Dependencies:** StockTwits API (free), Reddit API (free)
- **Implementation:**
  - Create `src/catalyst_bot/social_sentiment.py`
  - StockTwits API client with rate limiting
  - Reddit API client (r/wallstreetbets, r/pennystocks)
  - Sentiment aggregation and spike detection
  - Divergence alerts (negative sentiment + positive catalyst)
  - Config: `FEATURE_SOCIAL_SENTIMENT=1`, `STOCKTWITS_API_KEY=...`

**Phase 2B Expected Impact:** +10-15% win rate, prevents large losses

---

### 📊 PHASE 3A: Advanced Analytics (2-3 weeks)

#### PATCH 7: EWMA Adaptive Thresholds
- **Priority:** 8/10 (HIGH)
- **Complexity:** Medium (1 week)
- **Impact:** 15-20% reduction in false negatives
- **Dependencies:** None
- **Implementation:**
  - Create `src/catalyst_bot/adaptive_thresholds.py`
  - EWMA calculation with lambda 0.90-0.94
  - EWMA variance tracking
  - Percentile-based dynamic thresholds (95th/97.5th)
  - Integrate into classify.py for adaptive MIN_SCORE
  - Config: `FEATURE_ADAPTIVE_THRESHOLDS=1`, `EWMA_LAMBDA=0.92`

#### PATCH 8: Source Credibility Feedback Loop
- **Priority:** 7/10 (HIGH)
- **Complexity:** Low-Medium (5 days)
- **Impact:** 10-15% reduction in false positives
- **Dependencies:** False Positive Analyzer (already implemented)
- **Implementation:**
  - Enhance `src/catalyst_bot/source_credibility.py`
  - Add `update_source_scores()` function
  - Exponential decay for source scores
  - Auto-blacklist threshold (>75% FP rate with >10 samples)
  - Store source history in `data/source_performance.jsonl`
  - Config: `FEATURE_SOURCE_FEEDBACK=1`, `SOURCE_BLACKLIST_THRESHOLD=0.75`

#### PATCH 9: Keyword Co-occurrence Matrix
- **Priority:** 7/10 (HIGH)
- **Complexity:** Medium-High (1-2 weeks)
- **Impact:** 8-12% precision improvement
- **Dependencies:** None
- **Implementation:**
  - Create `src/catalyst_bot/keyword_cooccurrence.py`
  - Matrix storage: `Dict[Tuple[str, str], KeywordPairStats]`
  - Track pair occurrences during classification
  - Synergy scoring (pair > sum of parts)
  - Limit to top 50 keywords to prevent explosion
  - Generate combination boost recommendations in MOA
  - Config: `FEATURE_KEYWORD_PAIRS=1`, `MAX_KEYWORDS_FOR_PAIRS=50`

**Phase 3A Expected Impact:** +15-25% precision, fewer false positives

---

### 🧠 PHASE 3B: Incremental Learning (3-4 weeks)

#### PATCH 10: Incremental Keyword Statistics (Welford's Algorithm)
- **Priority:** 9/10 (CRITICAL)
- **Complexity:** Medium (2 weeks)
- **Impact:** O(1) updates, real-time learning
- **Dependencies:** None
- **Implementation:**
  - Create `src/catalyst_bot/incremental_stats.py`
  - Implement `IncrementalKeywordTracker` class
  - Welford's algorithm for mean/variance (lines 34-141 in incremental stats doc)
  - M2 (sum of squared deviations) tracking
  - Integrate with runner.py for real-time updates
  - Persistence layer to save/load state
  - Config: `FEATURE_INCREMENTAL_STATS=1`

#### PATCH 11: Statistical Significance Testing (FDR Correction)
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Low-Medium (3-5 days)
- **Impact:** Reduces spurious recommendations by 30-40%
- **Dependencies:** scipy (already installed)
- **Implementation:**
  - Enhance `src/catalyst_bot/moa_historical_analyzer.py`
  - Add `false_discovery_rate_correction()` function
  - Calculate p-values for keyword performance (z-test or t-test)
  - Apply FDR correction before generating recommendations
  - Add "statistical_significance" field to outputs
  - Config: `FEATURE_FDR_CORRECTION=1`, `FDR_ALPHA=0.05`

#### PATCH 12: Database Storage Migration
- **Priority:** 7/10 (HIGH for scale)
- **Complexity:** Medium (1-2 weeks)
- **Impact:** Foundation for scaling, efficient queries
- **Dependencies:** Decision on SQLite vs PostgreSQL vs TimescaleDB
- **Implementation:**
  - Choose database: SQLite (simple) or TimescaleDB (scale)
  - Create schema from optimal_data_points_research.md
  - Build ORM/query layer
  - Data migration scripts from JSONL
  - Indexes for performance
  - Hybrid approach: keep JSONL as backup
  - Config: `FEATURE_DATABASE=1`, `DATABASE_URL=...`

**Phase 3B Expected Impact:** 10-100x faster analysis, real-time learning

---

### 🎯 PHASE 4: Advanced Features (4-6 weeks)

#### PATCH 13: Sentiment Drift Detection
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Medium (1 week)
- **Impact:** Detects shifts before catalyst materialize
- **Implementation:**
  - Create `src/catalyst_bot/sentiment_drift.py`
  - Rolling 7-day sentiment baseline per ticker
  - CUSUM drift detection (cumulative sum of deviations)
  - Sentiment momentum scoring
  - Divergence alerts (sentiment + catalyst alignment)
  - Config: `FEATURE_SENTIMENT_DRIFT=1`

#### PATCH 14: Ticker-Specific Learning
- **Priority:** 5/10 (MEDIUM)
- **Complexity:** Medium (1 week)
- **Impact:** Personalized scoring per stock
- **Implementation:**
  - Add ticker-specific stats to `keyword_stats.json`
  - Hierarchical scoring: `global_weight * ticker_weight`
  - Minimum occurrence threshold per ticker (5 observations)
  - Fallback to global weights when insufficient data
  - Monitor for overfitting
  - Config: `FEATURE_TICKER_LEARNING=1`, `MIN_TICKER_SAMPLES=5`

#### PATCH 15: Catalyst Timing Pattern Analysis
- **Priority:** 7/10 (HIGH)
- **Complexity:** Low-Medium (3-5 days)
- **Impact:** Entry timing optimization
- **Implementation:**
  - Enhance `src/catalyst_bot/false_positive_analyzer.py`
  - Day-of-week patterns (Monday vs Friday)
  - Month-of-year seasonality
  - Time-to-peak analysis
  - Market hour heatmaps
  - Holiday/earnings season adjustments
  - Config: Already enabled in FP analyzer

#### PATCH 16: Regime-Aware Opportunity Scoring
- **Priority:** 5/10 (MEDIUM)
- **Complexity:** Medium (1 week)
- **Impact:** Optimizes for market conditions
- **Dependencies:** Market Regime (already implemented)
- **Implementation:**
  - Enhance `src/catalyst_bot/moa_historical_analyzer.py`
  - Calculate keyword performance by regime
  - Generate regime-specific recommendations
  - Regime transition alerts (VIX crossing thresholds)
  - Regime-adaptive thresholds
  - Config: Already integrated in MOA

**Phase 4 Expected Impact:** +10-15% from timing/personalization

---

### 🗄️ PHASE 5: Scalability (3-4 weeks)

#### PATCH 17: TimescaleDB Integration
- **Priority:** 9/10 (CRITICAL for scale)
- **Complexity:** High (2-3 weeks)
- **Impact:** 60-70% storage reduction, 10-100x faster queries
- **Dependencies:** PostgreSQL + TimescaleDB extension
- **Implementation:**
  - Set up TimescaleDB instance (local or cloud)
  - Create schema from incremental stats doc (lines 310-446)
  - Hypertables for time-series data
  - Continuous aggregates for real-time stats
  - Compression policies for old data
  - Data migration from JSONL
  - Config: `FEATURE_TIMESCALEDB=1`, `TIMESCALEDB_URL=...`

#### PATCH 18: Advanced Parameter Optimization
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Medium-High (1-2 weeks)
- **Impact:** Finds optimal parameters automatically
- **Dependencies:** scikit-optimize (for Bayesian optimization)
- **Implementation:**
  - Create `src/catalyst_bot/parameter_optimizer.py`
  - Grid search implementation
  - Bayesian optimization
  - Overfitting detection (train/test gap)
  - Parameter heatmap visualization
  - Multi-objective optimization (Sharpe + drawdown)
  - Config: `FEATURE_PARAM_OPT=1`

#### PATCH 19: Advanced Visualization Dashboard
- **Priority:** 5/10 (LOW - nice-to-have)
- **Complexity:** Medium (1-2 weeks)
- **Impact:** Better visibility, no strategy improvement
- **Dependencies:** Streamlit or Plotly Dash
- **Implementation:**
  - Create `src/catalyst_bot/dashboard/` directory
  - Streamlit app (recommended for simplicity)
  - Equity curve plots
  - Drawdown visualization
  - Parameter sensitivity charts
  - Real-time monitoring page
  - Config: `FEATURE_DASHBOARD=1`, `DASHBOARD_PORT=8501`

**Phase 5 Expected Impact:** Handle 1000s catalysts/day, scale to production

---

### 🔬 PHASE 6: Advanced Data Collection (3-4 weeks)

#### PATCH 20: Short Interest Tracking
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Low (2-3 days)
- **Impact:** Squeeze potential identification
- **Dependencies:** FinViz (already used for float)
- **Implementation:**
  - Enhance `src/catalyst_bot/float_data.py`
  - Already extracts short interest % from FinViz
  - Add squeeze scoring: high short % + positive catalyst
  - Config: Already in FEATURE_FLOAT_DATA

#### PATCH 21: Institutional Ownership Tracking
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Medium (3-5 days)
- **Impact:** Stability correlation
- **Dependencies:** SEC 13F data
- **Implementation:**
  - Create `src/catalyst_bot/institutional_ownership.py`
  - Parse SEC 13F filings
  - Track institutional % and changes
  - Correlation with catalyst success
  - Config: `FEATURE_INST_OWNERSHIP=1`

#### PATCH 22: Clinical Trial Database (Biotech-Specific)
- **Priority:** 5/10 (LOW - niche)
- **Complexity:** Medium (3-5 days)
- **Impact:** 15% value add for biotech sector only
- **Dependencies:** ClinicalTrials.gov
- **Implementation:**
  - Create `src/catalyst_bot/clinical_trials.py`
  - ClinicalTrials.gov scraper
  - Trial completion date tracking
  - FDA PDUFA date calendar
  - Trial design analysis
  - Config: `FEATURE_CLINICAL_TRIALS=1`

#### PATCH 23: First 30-Min Price Action Tracking
- **Priority:** 6/10 (MEDIUM)
- **Complexity:** Low (2-3 days)
- **Impact:** Breakout pattern detection
- **Dependencies:** Tiingo or Alpaca (intraday data)
- **Implementation:**
  - Enhance `src/catalyst_bot/market.py`
  - Track 9:30-10:00 AM ET price action
  - Calculate breakout percentage
  - Volume spike detection in first 30 min
  - Config: `FEATURE_FIRST_30MIN=1`

**Phase 6 Expected Impact:** +5-10% from niche signals

---

### 💰 PHASE 7: Premium Features (Optional)

#### PATCH 24: Options Flow Integration
- **Priority:** 4/10 (LOW - expensive)
- **Complexity:** High (1 week if data available)
- **Impact:** 12% value add, only for stocks >$3 with options
- **Dependencies:** Expensive data subscription ($100-500/mo)
- **Implementation:**
  - Evaluate ROI first
  - Create `src/catalyst_bot/options_flow.py`
  - Options data API integration
  - Unusual activity detection
  - Call/put ratio analysis
  - Config: `FEATURE_OPTIONS_FLOW=1`, `OPTIONS_API_KEY=...`

#### PATCH 25: Level 2 Order Book Analysis
- **Priority:** 3/10 (LOW - diminishing returns)
- **Complexity:** High (1-2 weeks)
- **Impact:** 8-10% edge but expensive and complex
- **Dependencies:** Level 2 subscription ($100-500/mo)
- **Implementation:**
  - Evaluate diminishing returns (not worth it for 30min-2hr holds)
  - Create `src/catalyst_bot/level2_analysis.py`
  - Bid/ask imbalance calculation
  - Large block detection
  - Config: `FEATURE_LEVEL2=1`

**Phase 7 Expected Impact:** +8-12% if data subscriptions are justified

---

## 📋 RECOMMENDED IMPLEMENTATION ORDER SUMMARY

### Immediate Next Steps (Next 2-4 Weeks)

**Week 1:**
1. VWAP Real-Time Calculation (2 days)
2. Robust Statistics - Winsorization + MAD (3 days)
3. Bid/Ask Spread Tracking (2 days)

**Week 2-3:**
4. Real-Time Price Monitoring (1-2 weeks) - requires Alpaca subscription
5. Dynamic Exit System (1 week)

**Week 4:**
6. EWMA Adaptive Thresholds (1 week)

**Expected Impact After Month 1:** +20-30% win rate, prevents large losses

### Month 2 Priority:
7. Source Credibility Feedback Loop (5 days)
8. Social Sentiment Integration (1 week)
9. Keyword Co-occurrence Matrix (1-2 weeks)

### Month 3 Priority:
10. Incremental Keyword Statistics - Welford (2 weeks)
11. Database Storage Migration (1-2 weeks)
12. Statistical Significance Testing (3-5 days)

### Month 4+ (Long-term):
13-19. Advanced features, scalability, visualization
20-23. Advanced data collection
24-25. Premium features (optional)

---

## 🎯 CRITICAL PATH DEPENDENCIES

Some patches depend on others. Here's the dependency chain:

1. **Real-Time Price Monitoring** → **Dynamic Exit System**
   - Exit system needs real-time prices to work

2. **Database Migration** → **TimescaleDB Integration**
   - Choose database strategy before TimescaleDB

3. **Incremental Stats** → **EWMA Adaptive Thresholds**
   - Adaptive thresholds benefit from incremental updates

4. **Float Data** (✅) → **Short Interest Tracking**
   - Already extracting from same FinViz page

5. **SEC Monitor** (✅) → **Institutional Ownership**
   - Both use SEC data

---

## 🔥 TOP 5 QUICK WINS (Next Sprint)

If you want maximum impact with minimum effort, prioritize these:

1. **VWAP Calculation** (2 days) - 91% accuracy on exits
2. **Robust Statistics** (3-5 days) - Statistical validity
3. **Bid/Ask Spread** (2 days) - Backtest accuracy
4. **EWMA Adaptive Thresholds** (1 week) - 15-20% FN reduction
5. **Source Credibility Feedback** (5 days) - 10-15% FP reduction

**Total Time:** 2-3 weeks
**Expected Impact:** +15-25% overall performance

---

## 📊 PATCHES BY PRIORITY SCORE

**Priority 9-10 (CRITICAL):**
- ✅ Float Data (9/10) - COMPLETED
- ✅ SEC Monitor (9/10) - COMPLETED
- Incremental Keyword Statistics (9/10) - Month 3
- TimescaleDB Integration (9/10) - Month 4+

**Priority 8 (HIGH):**
- ✅ RVol (8/10) - COMPLETED
- VWAP Calculation (8/10) - Week 1
- EWMA Adaptive Thresholds (8/10) - Week 4

**Priority 7 (HIGH):**
- ✅ 424B5 Parser (7/10) - COMPLETED
- Real-Time Price Monitoring (7/10) - Week 2-3
- Dynamic Exit System (7/10) - Week 2-3
- Source Credibility Feedback (7/10) - Month 2
- Keyword Co-occurrence (7/10) - Month 2
- Catalyst Timing Patterns (7/10) - Month 4
- Database Migration (7/10) - Month 3

**Priority 6 (MEDIUM):**
- Robust Statistics (6/10) - Week 1
- Statistical Significance Testing (6/10) - Month 3
- Social Sentiment (6/10) - Month 2
- Sentiment Drift (6/10) - Month 4
- Fundamental Correlations (6/10) - Month 4
- Advanced Parameter Optimization (6/10) - Month 4+
- Short Interest (6/10) - Month 4+
- Institutional Ownership (6/10) - Month 4+
- Bid/Ask Spread (6/10) - Week 1
- First 30-Min Tracking (6/10) - Month 4+

**Priority 5 (MEDIUM-LOW):**
- Regime-Aware Scoring (5/10) - Month 4
- Ticker-Specific Learning (5/10) - Month 4
- Clinical Trials (5/10) - Month 4+
- Visualization Dashboard (5/10) - Month 4+
- Monte Carlo Enhancement (5/10) - Already basic version

**Priority 4 (LOW):**
- Options Flow (4/10) - Optional/expensive
- ML Feature Engineering (4/10) - Long-term

**Priority 3 (LOW):**
- Level 2 Order Book (3/10) - Optional/expensive

---

## 📝 NOTES

- **4 Quick Wins Completed:** Float, SEC Monitor, 424B5, RVol (✅ Done 2025-10-13)
- **MOA Scheduler Running:** Nightly at 2 AM UTC (✅ Done 2025-10-13)
- **Market Regime Active:** Adjusting scores by regime (✅ Done 2025-10-13)
- **Test Suite Healthy:** 398/408 passing (97.8%)
- **Next Immediate Priority:** VWAP + Robust Stats + Bid/Ask (Week 1)
- **Critical for Scale:** Incremental Stats + TimescaleDB (Month 3-4)
- **Alpaca Subscription Needed:** For real-time price monitoring ($9/mo)

---

**End of Patch Status & Priority Order**
