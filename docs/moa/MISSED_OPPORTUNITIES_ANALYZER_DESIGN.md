# Missed Opportunities Analyzer - Comprehensive Design Document

**Date:** 2025-10-10
**Project:** Catalyst Bot - Trading Signal Optimization System
**Status:** Research & Design Phase

---

## Executive Summary

This document presents a comprehensive design for a "Missed Opportunities Analyzer" system that learns from rejected trading signals. The system will analyze the 150+ news items filtered out each cycle to identify stocks that moved significantly, extract predictive keywords, and recommend parameter adjustments to capture similar opportunities in the future.

**Key Innovation:** Rather than only analyzing executed trades (the standard approach), this system focuses on **false negatives** - opportunities the bot filtered out that would have been profitable.

---

## Table of Contents

1. [Research Findings](#1-research-findings)
2. [System Architecture](#2-system-architecture)
3. [Implementation Plan](#3-implementation-plan)
4. [Analysis Methods](#4-analysis-methods)
5. [Keyword Discovery Engine](#5-keyword-discovery-engine)
6. [Learning Loop Design](#6-learning-loop-design)
7. [Advanced Features](#7-advanced-features)
8. [Technical Implementation](#8-technical-implementation)
9. [Prioritized Feature List](#9-prioritized-feature-list)
10. [Potential Pitfalls & Mitigation](#10-potential-pitfalls--mitigation)
11. [Integration with Existing System](#11-integration-with-existing-system)

---

## 1. Research Findings

### 1.1 Missed Opportunity Analysis in Trading

**Key Insight from Research:**
- Professional trading systems use 24/7 monitoring to identify fleeting opportunities that human traders miss
- AI algorithms can identify opportunities in financial statements and market data that traditional methods overlook
- **Backtesting against historical data** is the primary method for refining strategies and minimizing future missed opportunities

**Relevant Papers:**
- Industry practice: "Even successful traders can only dedicate certain hours each day, which means trading opportunities could be missed—a problem automated bots solve"
- Speed advantage: "AI bots analyze vast amounts of data at lightning speed, allowing them to capitalize on fleeting market opportunities"

**Application to Catalyst Bot:**
- Our bot already monitors 24/7 but **filters aggressively** (330 items → 0-6 alerts)
- The 150+ rejected items are a **gold mine of data** - some contained signals we should have acted on
- By analyzing these rejections, we can **tune filters without manual observation**

### 1.2 Keyword Discovery & Machine Learning in Trading

**Key Findings:**
- Sentiment analysis using NLP has become a powerful tool for stock market prediction
- Research shows **integrating sentiment with technical indicators** enhances prediction precision, especially in volatile markets
- Hybrid approaches (GPT-2, FinBERT + MACD/SAR) deliver strong returns
- Proposed algorithms consider **public sentiment, opinions, news, and historical prices** together

**Academic Sources:**
- "Sentiment Analysis in Algorithmic Trading" (ResearchGate, 2024)
- "Trade the Event: Corporate Events Detection for News-Based Event-Driven Trading" (ACL 2021)
- "Integrating Sentiment and Technical Analysis with Machine Learning" (University of Dundee)

**Application to Catalyst Bot:**
- Current system uses **keyword-based classification** with manual weights
- Missed opportunities can reveal **new keyword patterns** not in current dictionary
- Can use **frequency + performance weighting** to auto-discover emerging catalysts
- Should track keyword **co-occurrence patterns** (e.g., "FDA + approval + Phase 3")

### 1.3 False Negative Analysis in Backtesting

**Key Findings:**
- Most backtesting focuses on **avoiding false positives** (strategies that look good but fail live)
- **Optimization bias** (curve-fitting) is the primary concern in backtest literature
- False negatives are rarely discussed as a distinct concept in academic literature
- However, event-driven trading research shows value in **retrospective event analysis**

**Important Quote from QuantStart:**
- "One of the most prevalent beginner mistakes is neglecting or underestimating the effects of transaction costs"
- "Optimization bias involves adjusting trading parameters until backtest performance is attractive, but live performance can be markedly different"

**Application to Catalyst Bot:**
- We must avoid **overfitting to recent missed opportunities**
- Need **statistical significance testing** for new keywords (not just "appeared once, stock went up")
- Should use **rolling window analysis** (not just last 7 days)
- Require **minimum sample size** before auto-applying weight changes

### 1.4 Adaptive Weighting & Signal Combination

**Key Findings:**
- KAMA (Kaufman Adaptive Moving Average) adjusts based on market conditions and volatility
- **Signal weighting** involves proportional weighting based on in-sample performance
- Warning: "Believing in multiple signals because they backtest well together does not imply any of the signals has power"
- Decision agents can give **dynamic weight** (e.g., 65% to events, 35% to technical)

**NBER Paper Insight:**
- "Backtesting strategies based on multiple signals" shows that combining signals requires careful statistical validation
- Simple weighting by past performance can lead to **false confidence**

**Application to Catalyst Bot:**
- Current system has **static keyword weights** in `keyword_weights.json`
- Should implement **dynamic weight adjustment** based on hit/miss ratios
- Need **confidence intervals** around weight recommendations
- Must track **correlation between keywords** (avoid double-counting)

### 1.5 Event-Driven Trading Retrospective Analysis

**Key Findings:**
- "Trade the Event" paper (ACL 2021) uses **bi-level event detection**:
  - Low-level: identify events from each token
  - High-level: incorporate entire article representation
- **EDT dataset** released for corporate event detection benchmarking
- Pure news signals showed **alpha in excess of 10% per year** (Leinweber & Sisk, 2006-2010)
- Tools exist for **scraping Reuters news back to 2017** with interactive analysis

**GitHub Implementation:** `Zhihan1996/TradeTheEvent`

**Application to Catalyst Bot:**
- Current system classifies events with **keyword matching + sentiment**
- Could implement **hierarchical event detection** (token-level + article-level)
- Should create **event taxonomy** (FDA approvals, partnerships, uplisting, etc.)
- Can benchmark against academic datasets like EDT for validation

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Catalyst Bot Main Loop                       │
│  (Processes ~330 news items/cycle)                              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ├─────────────────┬─────────────────┐
                 │                 │                 │
                 ▼                 ▼                 ▼
          ┌──────────┐      ┌──────────┐    ┌─────────────┐
          │ Passed   │      │ Filtered │    │  Filtered   │
          │ Filters  │      │ (Low     │    │  (High      │
          │ (0-6)    │      │  Score)  │    │  Price)     │
          └────┬─────┘      └────┬─────┘    └──────┬──────┘
               │                 │                  │
               ▼                 │                  │
        ┌─────────────┐          │                  │
        │ events.jsonl│          │                  │
        │ (alerted)   │          │                  │
        └─────────────┘          │                  │
                                 │                  │
                                 ▼                  ▼
                          ┌──────────────────────────────┐
                          │  NEW: rejected_items.jsonl   │
                          │  (filtered items with        │
                          │   rejection reason)          │
                          └──────────┬───────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────────┐
                          │  Missed Opportunities         │
                          │  Analyzer                     │
                          │  (Nightly job at 2:00 UTC)   │
                          └──────────┬───────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
            ┌───────────┐   ┌───────────┐   ┌────────────┐
            │ Price     │   │ Keyword   │   │ Parameter  │
            │ Lookup    │   │ Discovery │   │ Optimizer  │
            │ (YFinance)│   │ Engine    │   │            │
            └─────┬─────┘   └─────┬─────┘   └──────┬─────┘
                  │               │                 │
                  └───────────────┴─────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────┐
                    │  Analysis Report Generator    │
                    │  - Missed winners summary     │
                    │  - New keyword candidates     │
                    │  - Weight adjustments         │
                    │  - Confidence scores          │
                    └──────────┬───────────────────┘
                               │
                               ▼
                    ┌──────────────────────────────┐
                    │  Admin Approval Workflow      │
                    │  (Discord embed with buttons) │
                    └──────────┬───────────────────┘
                               │
                               ▼
                    ┌──────────────────────────────┐
                    │  Auto-Apply or Manual Review  │
                    │  - Update keyword_weights.json│
                    │  - Update MIN_SCORE threshold │
                    │  - Add new keywords to dict   │
                    └───────────────────────────────┘
```

### 2.2 Data Flow Architecture

**Phase 1: Capture (Real-time)**
```python
# In runner.py or feeds.py
for item in all_news_items:
    if item passes filters:
        log_to_events_jsonl(item)
    else:
        log_to_rejected_items_jsonl(item, rejection_reason)
```

**Phase 2: Analysis (Nightly)**
```python
# In missed_opportunities_analyzer.py (new module)
def analyze_missed_opportunities(target_date):
    # 1. Load rejected items for target_date
    rejected = load_rejected_items(target_date)

    # 2. Filter by price range ($0.10 - $10.00)
    in_range = [r for r in rejected if 0.10 <= r.price <= 10.00]

    # 3. Fetch price changes (1hr, 4hr, 24hr, 1week)
    for item in in_range:
        item.price_changes = fetch_price_changes(
            item.ticker,
            item.timestamp,
            timeframes=[1, 4, 24, 168]  # hours
        )

    # 4. Identify "missed winners"
    missed_winners = [
        r for r in in_range
        if max(r.price_changes.values()) >= 10.0  # 10%+ move
    ]

    # 5. Extract keywords from missed winners
    keywords = extract_keywords(missed_winners)

    # 6. Generate weight recommendations
    recommendations = generate_recommendations(
        missed_winners,
        keywords,
        current_weights=load_keyword_weights()
    )

    # 7. Create admin report
    report = create_report(missed_winners, keywords, recommendations)

    # 8. Post to Discord for approval
    post_admin_report(report)
```

**Phase 3: Learning Loop (On Approval)**
```python
def apply_approved_changes(plan_id):
    plan = load_pending_plan(plan_id)

    # 1. Update keyword weights
    update_keyword_weights(plan.weight_adjustments)

    # 2. Add new keywords
    add_keywords_to_dictionary(plan.new_keywords)

    # 3. Update filter thresholds
    update_environment_vars(plan.threshold_changes)

    # 4. Log change to audit trail
    log_change_to_admin_changes_jsonl(plan)

    # 5. Trigger backtest with new parameters
    backtest_results = run_backtest_with_new_params(
        start_date=today - 30 days,
        end_date=today
    )

    # 6. Post results to Discord
    post_backtest_results(backtest_results)
```

### 2.3 File Structure

```
catalyst-bot/
├── data/
│   ├── events.jsonl                    # Existing: alerted items
│   ├── rejected_items.jsonl            # NEW: filtered items log
│   ├── keyword_weights.json            # Existing: manual weights
│   ├── missed_opportunities/           # NEW directory
│   │   ├── analysis_YYYY-MM-DD.json   # Daily analysis results
│   │   ├── keywords_discovered.jsonl  # Incremental keyword log
│   │   ├── false_negatives.jsonl      # Items that should've alerted
│   │   └── performance_tracking.db    # SQLite: keyword performance
│   └── analyzer/
│       ├── keyword_stats.json          # Existing: analyzer output
│       └── pending_*.json              # Existing: approval workflow
│
├── src/catalyst_bot/
│   ├── feeds.py                        # MODIFY: add rejected logging
│   ├── runner.py                       # MODIFY: schedule MOA job
│   ├── analyzer.py                     # EXISTING: alerted items
│   ├── admin_controls.py               # MODIFY: add MOA section
│   ├── missed_opportunities/           # NEW module
│   │   ├── __init__.py
│   │   ├── analyzer.py                 # Core analysis logic
│   │   ├── keyword_discovery.py        # Keyword extraction
│   │   ├── price_fetcher.py            # Multi-timeframe prices
│   │   ├── recommendations.py          # Weight optimizer
│   │   └── reporter.py                 # Discord embed builder
│   └── backtest/
│       ├── simulator.py                # EXISTING
│       └── metrics.py                  # EXISTING
│
└── out/
    └── missed_opportunities/           # NEW: reports & charts
        ├── report_YYYY-MM-DD.md
        ├── keywords_heatmap_YYYY-MM-DD.png
        └── timeline_YYYY-MM-DD.png
```

---

## 3. Implementation Plan

### 3.1 Phase 1: Data Capture (Week 1)

**Goal:** Start logging rejected items without disrupting existing system

**Tasks:**
1. Create `rejected_items.jsonl` logger in `feeds.py`
2. Add rejection metadata:
   ```python
   {
       "ts": "2025-10-10T14:30:00Z",
       "ticker": "ABCD",
       "title": "...",
       "price": 2.45,
       "score": 0.18,              # Below MIN_SCORE
       "sentiment": 0.42,
       "rejection_reason": "LOW_SCORE",  # or HIGH_PRICE, DUPLICATE, etc.
       "rejection_threshold": 0.25,      # MIN_SCORE value at time
       "cls": {...},                     # Classification data
       "source": "finviz"
   }
   ```
3. Implement price range filter (only log $0.10-$10.00)
4. Add rotation (keep 30 days max)
5. Test with dry-run mode

**Success Metrics:**
- 150+ items logged per cycle
- File size < 50MB per day
- No performance degradation (< 10ms overhead)

### 3.2 Phase 2: Price Lookup System (Week 2)

**Goal:** Fetch historical prices for rejected items

**Tasks:**
1. Create `missed_opportunities/price_fetcher.py`
2. Implement multi-timeframe lookup:
   ```python
   def fetch_price_changes(ticker, timestamp, timeframes):
       """
       timeframes: [1, 4, 24, 168] hours
       returns: {
           "1h": 2.3,    # +2.3% after 1 hour
           "4h": 5.7,
           "24h": 12.4,  # MISSED OPPORTUNITY!
           "1w": -3.2
       }
       """
   ```
3. Use yfinance with caching (avoid API limits)
4. Handle weekends/market hours gracefully
5. Store in SQLite for fast re-analysis

**Success Metrics:**
- < 2 sec per ticker lookup
- 95%+ success rate (handle delisted stocks)
- Cache hit rate > 80%

### 3.3 Phase 3: Keyword Discovery Engine (Week 3)

**Goal:** Extract predictive keywords from missed winners

**Tasks:**
1. Create `missed_opportunities/keyword_discovery.py`
2. Implement extraction methods:
   - **TF-IDF** on missed winners vs. missed losers
   - **N-gram analysis** (2-word, 3-word phrases)
   - **Named Entity Recognition** (company names, drugs, etc.)
   - **Keyword co-occurrence matrix**
3. Filter criteria:
   ```python
   def is_keyword_candidate(keyword, occurrences):
       if occurrences < 3:  # Minimum sample size
           return False
       if keyword in STOPWORDS:
           return False
       if len(keyword) < 3:
           return False
       return True
   ```
4. Score keywords by:
   - **Frequency** in missed winners
   - **Avg price change** when present
   - **Hit rate** (wins / total appearances)
   - **Sharpe ratio** of returns

**Success Metrics:**
- Discover 5-10 new keywords per week
- Statistical significance (p < 0.05)
- No overlap with existing dictionary

### 3.4 Phase 4: Recommendation Engine (Week 4)

**Goal:** Generate actionable parameter adjustments

**Tasks:**
1. Create `missed_opportunities/recommendations.py`
2. Implement weight adjustment logic:
   ```python
   def recommend_weight_change(keyword, stats):
       current_weight = load_weight(keyword)
       hit_rate = stats.hits / stats.total

       if hit_rate > 0.6:
           new_weight = current_weight * 1.2  # Increase 20%
       elif hit_rate < 0.4:
           new_weight = current_weight * 0.8  # Decrease 20%
       else:
           return None  # No change

       # Confidence based on sample size
       confidence = min(stats.total / 20, 1.0)

       return {
           "keyword": keyword,
           "current": current_weight,
           "proposed": new_weight,
           "confidence": confidence,
           "reason": f"{hit_rate:.1%} hit rate over {stats.total} samples"
       }
   ```
3. Recommend MIN_SCORE adjustments
4. Recommend PRICE_CEILING adjustments
5. Generate **rollback plan** for each recommendation

**Success Metrics:**
- < 5 recommendations per day (avoid noise)
- Confidence scores > 0.5 for all recs
- Backtest validation shows improvement

### 3.5 Phase 5: Admin Interface (Week 5)

**Goal:** Discord-based approval workflow

**Tasks:**
1. Extend `admin_controls.py` with MOA section
2. Create daily report embed:
   ```
   📉 Missed Opportunities Report – 2025-10-10

   📊 Summary:
   - Rejected items analyzed: 324
   - Missed winners (10%+): 12
   - New keywords discovered: 3
   - Weight adjustments: 5

   🔥 Top Missed Opportunities:
   1. ABCD: +47.3% in 24h (reason: LOW_SCORE 0.18 < 0.25)
   2. EFGH: +23.1% in 4h (reason: HIGH_PRICE $12.50 > $10.00)
   3. IJKL: +18.7% in 1w (reason: LOW_SENTIMENT 0.41)

   🆕 New Keyword Candidates:
   1. "breakthrough therapy" (6 wins, 0 losses, +12.3% avg)
   2. "FDA fast track" (4 wins, 1 loss, +8.7% avg)

   ⚙️ Recommended Changes:
   1. Increase "fda" weight: 1.2 → 1.5 (confidence: 85%)
   2. Lower MIN_SCORE: 0.25 → 0.22 (confidence: 72%)

   [Approve All] [Review Details] [Reject]
   ```
3. Add interactive buttons
4. Create detailed drill-down views
5. Implement A/B testing mode

**Success Metrics:**
- Admin can review in < 5 minutes
- 1-click approval workflow
- Rollback in < 30 seconds if needed

### 3.6 Phase 6: Learning Loop (Week 6)

**Goal:** Auto-apply approved changes with safety checks

**Tasks:**
1. Implement approval handler
2. Create backup/rollback system:
   ```python
   def apply_changes_with_rollback(plan):
       # 1. Backup current state
       backup = create_backup()

       # 2. Apply changes
       apply_weight_changes(plan.weights)
       apply_threshold_changes(plan.thresholds)

       # 3. Run validation backtest
       results = backtest_last_30_days()

       # 4. Check if performance degraded
       if results.sharpe < baseline.sharpe * 0.9:
           # Rollback!
           restore_backup(backup)
           notify_admin("Changes rolled back - performance declined")
       else:
           # Success!
           commit_changes()
           notify_admin("Changes applied successfully")
   ```
3. Add **cooling period** (wait 24h before next change)
4. Implement **change log** for audit trail
5. Add manual override capability

**Success Metrics:**
- Auto-rollback on performance drop
- No more than 1 change per 24h
- Full audit trail for all changes

---

## 4. Analysis Methods

### 4.1 Identifying Missed Winners

**Multi-Threshold Approach:**
```python
THRESHOLDS = {
    "1h": 5.0,    # 5%+ in 1 hour = aggressive opportunity
    "4h": 8.0,    # 8%+ in 4 hours = day-trading opportunity
    "24h": 10.0,  # 10%+ in 24 hours = swing trade
    "1w": 15.0    # 15%+ in 1 week = position trade
}

def classify_missed_opportunity(price_changes):
    """
    Returns (timeframe, pct_change, severity)
    severity: "critical" | "high" | "medium" | "low"
    """
    max_gain = max(price_changes.values())
    max_tf = max(price_changes.items(), key=lambda x: x[1])[0]

    if max_gain >= 30:
        return (max_tf, max_gain, "critical")
    elif max_gain >= 20:
        return (max_tf, max_gain, "high")
    elif max_gain >= 10:
        return (max_tf, max_gain, "medium")
    else:
        return (max_tf, max_gain, "low")
```

**Statistical Significance Testing:**
```python
from scipy import stats

def is_keyword_significant(keyword_stats):
    """
    Use binomial test to determine if keyword performance
    is statistically better than random.
    """
    hits = keyword_stats.hits
    total = keyword_stats.total

    # Null hypothesis: hit_rate = 0.5 (coin flip)
    p_value = stats.binom_test(hits, total, p=0.5, alternative='greater')

    return p_value < 0.05  # 95% confidence
```

**Overfitting Prevention:**
```python
def validate_keyword_with_rolling_window(keyword, days=30):
    """
    Split data into 3 periods and check consistency:
    - Days 1-10: Training
    - Days 11-20: Validation
    - Days 21-30: Test
    """
    train_hit_rate = compute_hit_rate(keyword, days=range(1, 11))
    val_hit_rate = compute_hit_rate(keyword, days=range(11, 21))
    test_hit_rate = compute_hit_rate(keyword, days=range(21, 31))

    # Keyword must perform well in ALL periods
    if min(train_hit_rate, val_hit_rate, test_hit_rate) < 0.55:
        return False  # Inconsistent performance

    # Check for trend deterioration
    if test_hit_rate < train_hit_rate * 0.8:
        return False  # Performance degrading

    return True
```

### 4.2 Rejection Reason Analysis

**Categorize why items were filtered:**
```python
REJECTION_REASONS = {
    "LOW_SCORE": "Relevance score below MIN_SCORE",
    "HIGH_PRICE": "Price above PRICE_CEILING",
    "LOW_PRICE": "Price below PRICE_FLOOR",
    "LOW_SENTIMENT": "Sentiment score too low",
    "DUPLICATE": "Seen recently (dedupe filter)",
    "NOISE_FILTER": "Finviz lawsuit spam",
    "RATE_LIMIT": "Alert quota exceeded",
    "NO_TICKER": "Could not resolve ticker"
}

def analyze_rejection_distribution(rejected_items):
    """
    Identify which filters are causing most missed opportunities.
    """
    missed_by_reason = defaultdict(list)

    for item in rejected_items:
        if item.max_price_change >= 10:  # Missed winner
            reason = item.rejection_reason
            missed_by_reason[reason].append(item)

    # Sort by impact
    return sorted(
        missed_by_reason.items(),
        key=lambda x: (len(x[1]), sum(i.max_price_change for i in x[1])),
        reverse=True
    )
```

**Example Output:**
```
Rejection Reason Analysis (2025-10-10):

1. LOW_SCORE: 8 missed winners, +127.4% total opportunity
   → Recommendation: Lower MIN_SCORE from 0.25 to 0.22

2. HIGH_PRICE: 3 missed winners, +64.8% total opportunity
   → Recommendation: Raise PRICE_CEILING from $10 to $15

3. LOW_SENTIMENT: 1 missed winner, +12.3% total opportunity
   → Recommendation: Review sentiment scoring logic
```

### 4.3 Volatility-Adjusted Scoring

**Problem:** High volatility stocks naturally have bigger swings

**Solution:** Normalize by historical volatility
```python
def volatility_adjusted_return(ticker, actual_return, timestamp):
    """
    Adjust return by 30-day historical volatility (ATR)
    """
    volatility = get_avg_true_range(ticker, days=30)

    if volatility == 0:
        return actual_return

    # Return per unit of volatility
    return actual_return / volatility

# Example:
# Stock A: +20% return, 5% avg volatility → score = 4.0
# Stock B: +20% return, 25% avg volatility → score = 0.8
# Stock A is better (more predictable)
```

---

## 5. Keyword Discovery Engine

### 5.1 Extraction Techniques

**Method 1: TF-IDF Comparison**
```python
from sklearn.feature_extraction.text import TfidfVectorizer

def extract_keywords_tfidf(missed_winners, missed_losers):
    """
    Compare TF-IDF of titles in winners vs. losers.
    High-scoring words in winners are keyword candidates.
    """
    winner_titles = [w.title for w in missed_winners]
    loser_titles = [l.title for l in missed_losers]

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 3),  # 1-3 word phrases
        min_df=2,            # Must appear at least twice
        stop_words='english'
    )

    winner_tfidf = vectorizer.fit_transform(winner_titles)

    # Get top scoring terms
    feature_names = vectorizer.get_feature_names_out()
    scores = winner_tfidf.sum(axis=0).A1

    top_keywords = sorted(
        zip(feature_names, scores),
        key=lambda x: x[1],
        reverse=True
    )[:50]  # Top 50 candidates

    return top_keywords
```

**Method 2: Named Entity Recognition**
```python
import spacy

nlp = spacy.load("en_core_web_sm")

def extract_entities(missed_winners):
    """
    Extract named entities (ORG, PRODUCT, GPE, etc.)
    from missed winner titles.
    """
    entities = defaultdict(int)

    for winner in missed_winners:
        doc = nlp(winner.title)
        for ent in doc.ents:
            if ent.label_ in ["ORG", "PRODUCT", "GPE"]:
                entities[ent.text.lower()] += 1

    # Filter by frequency
    return {k: v for k, v in entities.items() if v >= 3}
```

**Method 3: N-Gram Co-occurrence**
```python
from itertools import combinations

def find_keyword_combinations(missed_winners):
    """
    Find keyword pairs that frequently appear together
    in successful catalysts.
    """
    cooccurrence = defaultdict(int)

    for winner in missed_winners:
        keywords = extract_keywords_from_title(winner.title)

        # Track all 2-keyword combinations
        for pair in combinations(sorted(keywords), 2):
            cooccurrence[pair] += 1

    # Find pairs with high joint probability
    significant_pairs = {
        pair: count
        for pair, count in cooccurrence.items()
        if count >= 3
    }

    return significant_pairs

# Example output:
# {
#     ("fda", "approval"): 8,
#     ("breakthrough", "therapy"): 6,
#     ("phase 3", "results"): 5
# }
```

### 5.2 Keyword Validation

**Before adding a keyword, validate it:**
```python
def validate_keyword(keyword, historical_data):
    """
    Checks:
    1. Sample size (min 5 occurrences)
    2. Hit rate > 60%
    3. Avg return > 5%
    4. Statistical significance (p < 0.05)
    5. Consistency across time periods
    """
    stats = compute_keyword_stats(keyword, historical_data)

    # 1. Sample size
    if stats.total < 5:
        return False, "Insufficient sample size"

    # 2. Hit rate
    if stats.hit_rate < 0.6:
        return False, f"Low hit rate: {stats.hit_rate:.1%}"

    # 3. Avg return
    if stats.avg_return < 5.0:
        return False, f"Low avg return: {stats.avg_return:.1%}"

    # 4. Statistical significance
    p_value = binomial_test(stats.hits, stats.total)
    if p_value >= 0.05:
        return False, f"Not significant (p={p_value:.3f})"

    # 5. Consistency check
    if not is_consistent_over_time(keyword, historical_data):
        return False, "Performance deteriorating over time"

    return True, "Validated"
```

### 5.3 Blacklist Generation

**Identify keywords that predict LOSSES:**
```python
def generate_keyword_blacklist(historical_data):
    """
    Find keywords with:
    - High frequency (>10 occurrences)
    - Low hit rate (<40%)
    - Negative avg return
    """
    blacklist = []

    for keyword in all_keywords:
        stats = compute_keyword_stats(keyword, historical_data)

        if (stats.total >= 10 and
            stats.hit_rate < 0.4 and
            stats.avg_return < 0):
            blacklist.append({
                "keyword": keyword,
                "hit_rate": stats.hit_rate,
                "avg_return": stats.avg_return,
                "total": stats.total
            })

    return blacklist

# Example:
# [
#     {"keyword": "going concern", "hit_rate": 0.12, "avg_return": -8.3%, "total": 23},
#     {"keyword": "delisting", "hit_rate": 0.18, "avg_return": -12.7%, "total": 15}
# ]
```

**Apply negative weights:**
```json
{
  "going_concern": -0.5,
  "delisting": -0.8,
  "reverse split": -0.3
}
```

### 5.4 Handling Keyword Evolution

**Keywords can become stale over time:**
```python
def track_keyword_lifecycle(keyword, window_days=90):
    """
    Track keyword performance over rolling windows
    to detect decay.
    """
    periods = split_into_periods(window_days, n_periods=3)

    performance = []
    for period in periods:
        stats = compute_keyword_stats(keyword, period)
        performance.append(stats.hit_rate)

    # Detect trend
    if performance[-1] < performance[0] * 0.7:
        return "DECLINING"
    elif performance[-1] > performance[0] * 1.3:
        return "IMPROVING"
    else:
        return "STABLE"

# Schedule: Weekly review of all keywords
def weekly_keyword_audit():
    for keyword in load_all_keywords():
        lifecycle = track_keyword_lifecycle(keyword)

        if lifecycle == "DECLINING":
            reduce_keyword_weight(keyword, factor=0.8)
            notify_admin(f"Keyword '{keyword}' declining, weight reduced")
```

---

## 6. Learning Loop Design

### 6.1 Update Frequency

**Recommendation: Tiered approach**

| Update Type | Frequency | Auto-Apply? | Reason |
|-------------|-----------|-------------|--------|
| Critical fixes (>3 critical missed opps) | Immediately | No, requires approval | High impact |
| Weekly weight adjustments | Sunday 2 AM UTC | Yes, if confidence > 80% | Routine optimization |
| New keyword additions | Manual review | No | Prevent noise |
| MIN_SCORE changes | Bi-weekly | No | Affects all alerts |
| Blacklist additions | Immediate | Yes | Prevent losses |

**Implementation:**
```python
def determine_update_urgency(analysis):
    """
    critical: 3+ missed opportunities >30% gain
    high: 5+ missed opportunities >20% gain
    medium: 10+ missed opportunities >10% gain
    low: routine weekly optimization
    """
    critical_misses = [
        m for m in analysis.missed_winners
        if m.max_gain >= 30
    ]

    if len(critical_misses) >= 3:
        return "CRITICAL"

    high_misses = [
        m for m in analysis.missed_winners
        if m.max_gain >= 20
    ]

    if len(high_misses) >= 5:
        return "HIGH"

    # ... etc
```

### 6.2 A/B Testing New Weights

**Run new weights in shadow mode before full deployment:**
```python
def shadow_mode_test(new_weights, days=7):
    """
    Run new weights alongside current weights for 7 days.
    Compare performance before full deployment.
    """
    results = {
        "current": [],
        "proposed": []
    }

    for day in range(days):
        items = load_items_for_day(today - timedelta(days=day))

        # Classify with current weights
        current_alerts = classify_with_weights(items, current_weights)
        current_perf = backtest(current_alerts)
        results["current"].append(current_perf)

        # Classify with proposed weights
        proposed_alerts = classify_with_weights(items, new_weights)
        proposed_perf = backtest(proposed_alerts)
        results["proposed"].append(proposed_perf)

    # Compare
    current_avg_sharpe = mean([r.sharpe for r in results["current"]])
    proposed_avg_sharpe = mean([r.sharpe for r in results["proposed"]])

    if proposed_avg_sharpe > current_avg_sharpe:
        return "APPROVED", f"Sharpe improved: {current_avg_sharpe:.2f} → {proposed_avg_sharpe:.2f}"
    else:
        return "REJECTED", f"Sharpe declined: {current_avg_sharpe:.2f} → {proposed_avg_sharpe:.2f}"
```

### 6.3 Rollback Mechanism

**Every change creates a checkpoint:**
```python
class ParameterCheckpoint:
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc)
        self.id = uuid4().hex[:8]
        self.weights = load_current_weights()
        self.thresholds = load_current_thresholds()
        self.performance_baseline = compute_baseline_performance()

    def save(self):
        path = f"data/checkpoints/checkpoint_{self.id}.json"
        with open(path, 'w') as f:
            json.dump({
                "timestamp": self.timestamp.isoformat(),
                "weights": self.weights,
                "thresholds": self.thresholds,
                "baseline": self.performance_baseline
            }, f)

    @classmethod
    def restore(cls, checkpoint_id):
        path = f"data/checkpoints/checkpoint_{checkpoint_id}.json"
        with open(path, 'r') as f:
            data = json.load(f)

        # Restore weights
        save_keyword_weights(data["weights"])

        # Restore thresholds
        for key, value in data["thresholds"].items():
            os.environ[key] = str(value)

        log.info(f"Restored checkpoint {checkpoint_id}")

# Usage:
checkpoint = ParameterCheckpoint()
checkpoint.save()

# ... apply changes ...

if performance_degraded():
    ParameterCheckpoint.restore(checkpoint.id)
```

### 6.4 Human-in-the-Loop Workflow

**Approval levels based on confidence:**
```python
def get_approval_requirement(recommendation):
    """
    confidence >= 90%: Auto-approve
    confidence 70-89%: Senior admin approval
    confidence 50-69%: Team consensus
    confidence < 50%: Manual A/B test required
    """
    if recommendation.confidence >= 0.90:
        return "AUTO_APPROVE"
    elif recommendation.confidence >= 0.70:
        return "SENIOR_ADMIN"
    elif recommendation.confidence >= 0.50:
        return "TEAM_CONSENSUS"
    else:
        return "MANUAL_TEST"

# Discord interaction:
async def handle_recommendation(recommendation):
    approval_level = get_approval_requirement(recommendation)

    if approval_level == "AUTO_APPROVE":
        apply_change_immediately(recommendation)
        post_notification(f"✅ Auto-approved: {recommendation.name}")
    else:
        # Post embed with approval buttons
        embed = build_approval_embed(recommendation)
        await post_embed_with_buttons(embed, approval_level)
```

---

## 7. Advanced Features

### 7.1 Multi-Timeframe Analysis

**Different trading styles need different horizons:**
```python
TIMEFRAME_PROFILES = {
    "scalping": {
        "thresholds": {"5m": 2.0, "15m": 3.0, "1h": 5.0},
        "weight": 0.2  # Low weight (not our focus)
    },
    "day_trading": {
        "thresholds": {"1h": 5.0, "4h": 8.0, "24h": 10.0},
        "weight": 0.5  # Medium weight
    },
    "swing_trading": {
        "thresholds": {"24h": 10.0, "3d": 15.0, "1w": 20.0},
        "weight": 0.8  # High weight (our primary focus)
    },
    "position_trading": {
        "thresholds": {"1w": 20.0, "1m": 30.0},
        "weight": 0.3  # Low weight (too long for news catalysts)
    }
}

def analyze_by_timeframe(missed_winners):
    """
    Categorize missed opportunities by optimal timeframe
    """
    results = defaultdict(list)

    for winner in missed_winners:
        best_tf = max(
            winner.price_changes.items(),
            key=lambda x: x[1]
        )[0]

        # Map to trading style
        for style, profile in TIMEFRAME_PROFILES.items():
            if best_tf in profile["thresholds"]:
                results[style].append(winner)
                break

    return results
```

**Adjust recommendations by timeframe:**
```
Missed Opportunities by Trading Style:

Day Trading (1-4h horizon):
- 8 missed winners, avg +12.3%
- Top keyword: "FDA approval" (5 wins)
- Recommendation: Increase "fda" weight for 1h-4h signals

Swing Trading (24h-1w horizon):
- 12 missed winners, avg +18.7%
- Top keyword: "breakthrough therapy" (7 wins)
- Recommendation: Add "breakthrough" to dictionary
```

### 7.2 Catalyst Type Correlation

**Different keywords work for different catalyst types:**
```python
CATALYST_TYPES = [
    "fda_approval",
    "clinical_trial",
    "partnership",
    "uplisting",
    "earnings_beat",
    "analyst_upgrade",
    "short_squeeze"
]

def build_keyword_catalyst_matrix(historical_data):
    """
    Create matrix showing which keywords predict which catalysts
    """
    matrix = defaultdict(lambda: defaultdict(int))

    for item in historical_data:
        catalyst_type = classify_catalyst(item)
        keywords = extract_keywords(item.title)

        for kw in keywords:
            if item.was_winner:
                matrix[kw][catalyst_type] += 1

    return matrix

# Example output:
# {
#     "fda": {
#         "fda_approval": 23,
#         "clinical_trial": 12,
#         "partnership": 3
#     },
#     "breakthrough": {
#         "clinical_trial": 18,
#         "fda_approval": 7
#     }
# }

# Use this to create specialized weights:
keyword_weights = {
    "fda": {
        "default": 1.2,
        "fda_approval": 1.8,  # Higher weight for FDA approvals
        "clinical_trial": 1.3,
        "partnership": 0.9
    }
}
```

### 7.3 Sector-Specific Weights

**Biotech keywords don't work for tech stocks:**
```python
SECTOR_KEYWORD_MAPPING = {
    "Biotechnology": {
        "fda": 2.0,
        "clinical": 1.8,
        "breakthrough": 1.5,
        "uplisting": 1.2
    },
    "Technology": {
        "partnership": 1.5,
        "earnings": 1.3,
        "acquisition": 1.4,
        "fda": 0.1  # Irrelevant
    },
    "Energy": {
        "oil": 1.5,
        "drilling": 1.3,
        "production": 1.2,
        "fda": 0.1  # Irrelevant
    }
}

def get_sector_adjusted_score(ticker, keywords):
    """
    Adjust keyword weights based on stock sector
    """
    sector = get_ticker_sector(ticker)

    if sector not in SECTOR_KEYWORD_MAPPING:
        return sum(keywords.values())  # Default

    sector_weights = SECTOR_KEYWORD_MAPPING[sector]

    adjusted_score = sum(
        sector_weights.get(kw, 1.0) * weight
        for kw, weight in keywords.items()
    )

    return adjusted_score
```

### 7.4 Volatility-Adjusted Opportunity Scoring

**Normalize returns by risk:**
```python
def compute_risk_adjusted_opportunity_score(item):
    """
    Score = (Return - RiskFreeRate) / Volatility

    This is essentially a Sharpe ratio for individual opportunities
    """
    # Get 30-day historical volatility
    volatility = get_historical_volatility(item.ticker, days=30)

    # Risk-free rate (assume 4% annual = 0.011% daily)
    risk_free_daily = 0.04 / 365

    # Actual return achieved
    actual_return = item.max_price_change / 100

    # Sharpe-like score
    if volatility == 0:
        return 0

    score = (actual_return - risk_free_daily) / volatility

    return score

# Prioritize high-score opportunities:
# Stock A: +20% return, 5% volatility → score = 4.0
# Stock B: +30% return, 40% volatility → score = 0.75
# Stock A is better (more return per unit risk)
```

### 7.5 False Positive Analysis

**Don't just analyze false negatives - also analyze false positives:**
```python
def analyze_false_positives(alerted_items):
    """
    Identify items that alerted but LOST money.
    Use this to strengthen filters.
    """
    false_positives = []

    for item in alerted_items:
        price_change = get_price_change(item.ticker, item.timestamp, hours=24)

        if price_change <= -5:  # Lost 5%+
            false_positives.append({
                "ticker": item.ticker,
                "title": item.title,
                "keywords": item.cls.keywords,
                "loss": price_change,
                "score": item.score
            })

    # Find common patterns in losers
    loser_keywords = defaultdict(int)
    for fp in false_positives:
        for kw in fp["keywords"]:
            loser_keywords[kw] += 1

    # Generate blacklist
    blacklist = {
        kw: count
        for kw, count in loser_keywords.items()
        if count >= 5  # Appeared in 5+ losses
    }

    return false_positives, blacklist

# Report:
"""
False Positive Analysis:

Top Loss Keywords (should reduce weight):
1. "investigation" - appeared in 8 losses, avg -12.3%
2. "class action" - appeared in 6 losses, avg -8.7%
3. "going concern" - appeared in 5 losses, avg -15.2%

Recommendation: Add these to negative weight list
"""
```

---

## 8. Technical Implementation

### 8.1 Python Libraries & Frameworks

**Core Dependencies:**
```python
# requirements_moa.txt

# Data processing
pandas>=2.0.0
numpy>=1.24.0

# Machine learning (keyword discovery)
scikit-learn>=1.3.0
scipy>=1.11.0

# NLP (keyword extraction)
spacy>=3.6.0
nltk>=3.8.0

# Statistical testing
statsmodels>=0.14.0

# Database (performance tracking)
sqlite3  # Built-in

# Price data
yfinance>=0.2.28
requests>=2.31.0

# Visualization (optional)
matplotlib>=3.7.0
seaborn>=0.12.0
plotly>=5.16.0

# Utilities
python-dateutil>=2.8.2
tqdm>=4.66.0  # Progress bars for batch processing
```

**Installation:**
```bash
pip install -r requirements_moa.txt
python -m spacy download en_core_web_sm
```

### 8.2 Data Storage Recommendations

**Comparison of storage options:**

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **JSONL** (current) | Simple, human-readable, append-only | Slow queries, no indexing | ✅ Keep for raw logs |
| **SQLite** | Fast queries, indexes, relations | Requires schema | ✅ Use for analysis DB |
| **PostgreSQL** | Full RDBMS, concurrent access | Overkill for single machine | ❌ Too heavy |
| **Parquet** | Columnar, compressed, fast | Requires pandas | ⚠️ Consider for archives |

**Recommended Hybrid Approach:**
```python
# 1. Raw logs: JSONL (append-only, never modify)
#    - rejected_items.jsonl (daily rotation)
#    - keywords_discovered.jsonl (incremental)

# 2. Analysis database: SQLite
#    - data/missed_opportunities/performance.db

CREATE TABLE keyword_performance (
    id INTEGER PRIMARY KEY,
    keyword TEXT NOT NULL,
    date DATE NOT NULL,
    total_occurrences INTEGER,
    wins INTEGER,
    losses INTEGER,
    neutrals INTEGER,
    avg_return REAL,
    max_return REAL,
    volatility REAL,
    sharpe REAL,
    UNIQUE(keyword, date)
);

CREATE INDEX idx_keyword ON keyword_performance(keyword);
CREATE INDEX idx_date ON keyword_performance(date);

CREATE TABLE missed_opportunities (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    ticker TEXT NOT NULL,
    title TEXT,
    price REAL,
    score REAL,
    sentiment REAL,
    rejection_reason TEXT,
    max_gain_1h REAL,
    max_gain_4h REAL,
    max_gain_24h REAL,
    max_gain_1w REAL,
    keywords TEXT  -- JSON array
);

CREATE INDEX idx_ticker ON missed_opportunities(ticker);
CREATE INDEX idx_date_mo ON missed_opportunities(date);
CREATE INDEX idx_rejection ON missed_opportunities(rejection_reason);
```

**Why SQLite?**
- Single file database (portable)
- No server process needed
- Supports 100k+ writes/sec
- Full SQL support (JOINs, aggregations)
- Built into Python standard library

### 8.3 Visualization Ideas

**1. Keyword Performance Heatmap**
```python
import seaborn as sns
import matplotlib.pyplot as plt

def create_keyword_heatmap(keyword_stats, days=30):
    """
    Show keyword hit rates over time
    """
    # Pivot data: rows=keywords, cols=dates, values=hit_rate
    pivot = pd.pivot_table(
        keyword_stats,
        values='hit_rate',
        index='keyword',
        columns='date',
        aggfunc='mean'
    )

    plt.figure(figsize=(15, 8))
    sns.heatmap(
        pivot,
        cmap='RdYlGn',
        center=0.5,
        vmin=0,
        vmax=1,
        annot=True,
        fmt='.0%'
    )
    plt.title('Keyword Hit Rate Heatmap (Last 30 Days)')
    plt.xlabel('Date')
    plt.ylabel('Keyword')
    plt.tight_layout()
    plt.savefig('out/missed_opportunities/keyword_heatmap.png')
```

**2. Missed Opportunity Timeline**
```python
import plotly.graph_objects as go

def create_opportunity_timeline(missed_winners):
    """
    Interactive timeline showing when missed opportunities occurred
    """
    fig = go.Figure()

    # Scatter plot: x=time, y=price change, size=opportunity score
    fig.add_trace(go.Scatter(
        x=[w.timestamp for w in missed_winners],
        y=[w.max_gain for w in missed_winners],
        mode='markers',
        marker=dict(
            size=[min(w.max_gain, 50) for w in missed_winners],
            color=[w.max_gain for w in missed_winners],
            colorscale='Reds',
            showscale=True,
            colorbar=dict(title="Gain %")
        ),
        text=[
            f"{w.ticker}: {w.title[:50]}...<br>Gain: {w.max_gain:.1f}%<br>Reason: {w.rejection_reason}"
            for w in missed_winners
        ],
        hoverinfo='text'
    ))

    fig.update_layout(
        title='Missed Opportunities Timeline',
        xaxis_title='Date',
        yaxis_title='Price Change %',
        hovermode='closest'
    )

    fig.write_html('out/missed_opportunities/timeline.html')
```

**3. Rejection Reason Pie Chart**
```python
def create_rejection_pie_chart(rejected_items):
    """
    Show distribution of rejection reasons
    """
    reason_counts = defaultdict(int)
    for item in rejected_items:
        reason_counts[item.rejection_reason] += 1

    plt.figure(figsize=(10, 6))
    plt.pie(
        reason_counts.values(),
        labels=reason_counts.keys(),
        autopct='%1.1f%%',
        startangle=90
    )
    plt.title('Rejection Reasons Distribution')
    plt.axis('equal')
    plt.savefig('out/missed_opportunities/rejection_pie.png')
```

**4. Cumulative Opportunity Loss Chart**
```python
def create_cumulative_loss_chart(missed_winners):
    """
    Show cumulative "money left on table" over time
    """
    # Sort by timestamp
    sorted_winners = sorted(missed_winners, key=lambda w: w.timestamp)

    cumulative_gain = 0
    dates = []
    cumulative_gains = []

    for winner in sorted_winners:
        cumulative_gain += winner.max_gain
        dates.append(winner.timestamp)
        cumulative_gains.append(cumulative_gain)

    plt.figure(figsize=(12, 6))
    plt.plot(dates, cumulative_gains, linewidth=2, color='red')
    plt.fill_between(dates, 0, cumulative_gains, alpha=0.3, color='red')
    plt.title('Cumulative Missed Opportunity (% Gain)')
    plt.xlabel('Date')
    plt.ylabel('Cumulative % Gain Missed')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('out/missed_opportunities/cumulative_loss.png')
```

### 8.4 Integration with Existing System

**Minimal changes to existing codebase:**

**1. Modify `src/catalyst_bot/feeds.py`:**
```python
# Add at top of file
from .missed_opportunities.logger import log_rejected_item

# In the filtering logic (around line 500-600):
def filter_and_classify_items(items):
    passed = []
    rejected = []

    for item in items:
        # ... existing classification logic ...

        if item.score < MIN_SCORE:
            # NEW: Log rejection
            log_rejected_item(item, reason="LOW_SCORE", threshold=MIN_SCORE)
            rejected.append(item)
            continue

        if item.price > PRICE_CEILING:
            # NEW: Log rejection
            log_rejected_item(item, reason="HIGH_PRICE", threshold=PRICE_CEILING)
            rejected.append(item)
            continue

        # ... other filters ...

        passed.append(item)

    return passed, rejected
```

**2. Modify `src/catalyst_bot/runner.py`:**
```python
# Add scheduled task for MOA
from .missed_opportunities.analyzer import run_missed_opportunities_analysis

def runner_loop():
    while True:
        # ... existing cycle logic ...

        # Check if it's time to run MOA (2:00 AM UTC daily)
        now = datetime.now(timezone.utc)
        if now.hour == 2 and now.minute == 0:
            try:
                run_missed_opportunities_analysis(target_date=now.date() - timedelta(days=1))
            except Exception as e:
                log.error(f"MOA failed: {e}")

        # ... continue cycle ...
```

**3. Extend `src/catalyst_bot/admin_controls.py`:**
```python
# Add MOA section to admin report
def generate_admin_report(target_date):
    # ... existing report generation ...

    # NEW: Add missed opportunities section
    try:
        from .missed_opportunities.reporter import build_moa_embed
        moa_embed = build_moa_embed(target_date)
        if moa_embed:
            embeds.append(moa_embed)
    except Exception as e:
        log.warning(f"MOA embed failed: {e}")

    return embeds
```

**4. No changes needed to:**
- `analyzer.py` (continues analyzing alerted items)
- `backtest/simulator.py` (continues backtesting executed trades)
- `models.py` (no new data models needed)

**Result:** MOA runs in parallel to existing analyzer, with minimal code coupling.

---

## 9. Prioritized Feature List

### 9.1 Must-Have Features (MVP - Weeks 1-3)

**Priority 1: Data Capture**
- ✅ Log rejected items to `rejected_items.jsonl`
- ✅ Include rejection reason and threshold values
- ✅ Filter by price range ($0.10-$10.00)
- ✅ Implement 30-day rotation

**Priority 2: Price Lookup**
- ✅ Fetch multi-timeframe price changes (1h, 4h, 24h, 1w)
- ✅ Handle market hours / weekends gracefully
- ✅ Cache results in SQLite
- ✅ Rate limiting for yfinance API

**Priority 3: Basic Analysis**
- ✅ Identify missed winners (>10% gain in any timeframe)
- ✅ Group by rejection reason
- ✅ Calculate opportunity cost (total % missed)
- ✅ Generate daily report (text format)

**Success Criteria:**
- ✅ 150+ rejected items logged per cycle
- ✅ < 5 sec to fetch prices for 50 tickers
- ✅ Daily report shows 5-10 missed opportunities
- ✅ No performance impact on main bot (<10ms overhead)

### 9.2 Should-Have Features (Weeks 4-6)

**Priority 4: Keyword Discovery**
- TF-IDF keyword extraction
- Minimum sample size validation (5+ occurrences)
- Statistical significance testing (p < 0.05)
- Keyword frequency tracking

**Priority 5: Recommendation Engine**
- Weight adjustment suggestions
- Confidence scoring
- Threshold optimization (MIN_SCORE, PRICE_CEILING)
- Rollback plan generation

**Priority 6: Admin Interface**
- Discord embed with MOA summary
- Interactive approval buttons
- Detailed drill-down views
- Change log / audit trail

**Success Criteria:**
- Discover 3-5 new keywords per week
- Generate 2-3 actionable recommendations per day
- Admin can review and approve in < 5 minutes
- All changes are reversible

### 9.3 Nice-to-Have Features (Weeks 7-12)

**Priority 7: Advanced Analytics**
- Named Entity Recognition (NER) for keyword extraction
- N-gram co-occurrence analysis
- Sector-specific keyword weights
- Catalyst type correlation matrix

**Priority 8: Learning Loop Automation**
- Auto-approval for high-confidence changes (>90%)
- A/B testing framework for new weights
- Performance degradation detection
- Automatic rollback on failure

**Priority 9: Visualization**
- Keyword performance heatmap
- Missed opportunity timeline (interactive)
- Rejection reason distribution charts
- Cumulative opportunity cost graph

**Priority 10: False Positive Analysis**
- Track alerted items that lost money
- Generate keyword blacklist
- Negative weight recommendations
- Cross-validate with backtest results

**Success Criteria:**
- 80%+ of recommendations auto-approved
- A/B testing shows 10%+ Sharpe improvement
- Visualizations used in weekly strategy meetings
- False positive rate reduced by 20%

### 9.4 Future Enhancements (Post-Launch)

**Priority 11: Multi-Timeframe Profiles**
- Separate scoring for day/swing/position trading
- Timeframe-specific keyword weights
- Dynamic timeframe selection based on market volatility

**Priority 12: Sentiment Evolution Tracking**
- Track how sentiment changes over time
- Identify sentiment inflection points
- Correlate sentiment shifts with price moves

**Priority 13: Market Regime Detection**
- Identify bull/bear/sideways markets
- Adjust keyword weights by regime
- Risk-on vs risk-off keyword sets

**Priority 14: Machine Learning Integration**
- Train supervised model (XGBoost/LightGBM)
- Features: keywords + sentiment + technical indicators
- Predict probability of >10% move
- Use ML predictions to override manual weights

**Priority 15: Real-Time Learning**
- Update keyword weights intraday (not just nightly)
- Adaptive filtering based on recent performance
- Online learning algorithm (incremental updates)

---

## 10. Potential Pitfalls & Mitigation

### 10.1 Overfitting to Recent Data

**Problem:** Optimizing for last week's winners may not predict next week

**Mitigation:**
- Use **rolling window validation** (train/val/test split)
- Require **minimum sample size** (5-10 occurrences)
- Track **keyword lifecycle** (detect decay)
- Implement **cooling period** (wait 7 days between changes)
- Use **statistical significance tests** (binomial, t-test)

**Code Example:**
```python
def validate_with_time_split(keyword, days=30):
    """
    Split data into 3 periods and validate consistency
    """
    train = days[0:10]
    val = days[10:20]
    test = days[20:30]

    train_perf = compute_hit_rate(keyword, train)
    val_perf = compute_hit_rate(keyword, val)
    test_perf = compute_hit_rate(keyword, test)

    # All periods must show positive results
    if min(train_perf, val_perf, test_perf) < 0.55:
        return False

    # Performance must not degrade
    if test_perf < train_perf * 0.8:
        return False

    return True
```

### 10.2 Data Snooping Bias

**Problem:** Looking at the same data multiple times increases false discoveries

**Mitigation:**
- **Bonferroni correction** for multiple hypothesis testing
- **Out-of-sample validation** (test on unseen data)
- **Holdout set** (never train on last 7 days)
- **Cross-validation** (k-fold)

**Code Example:**
```python
def bonferroni_correction(p_values, alpha=0.05):
    """
    Adjust significance level for multiple tests
    """
    n_tests = len(p_values)
    adjusted_alpha = alpha / n_tests

    significant = [p < adjusted_alpha for p in p_values]
    return significant

# Example:
# Testing 50 keywords → alpha = 0.05 / 50 = 0.001
# Much stricter threshold prevents false discoveries
```

### 10.3 Sample Size Issues

**Problem:** 2 wins out of 2 trials looks great, but is it significant?

**Mitigation:**
- **Minimum sample size requirement** (10+ occurrences)
- **Confidence intervals** around estimates
- **Bayesian priors** (start with skeptical prior)
- **Bootstrap resampling** to estimate variance

**Code Example:**
```python
def compute_confidence_interval(hits, total, confidence=0.95):
    """
    Calculate binomial proportion confidence interval
    """
    from scipy import stats

    if total < 10:
        return None, None  # Insufficient data

    # Wilson score interval (better for small samples)
    z = stats.norm.ppf((1 + confidence) / 2)
    p_hat = hits / total

    denominator = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denominator
    margin = z * np.sqrt(p_hat * (1 - p_hat) / total + z**2 / (4 * total**2)) / denominator

    lower = center - margin
    upper = center + margin

    return lower, upper

# Example:
# 8 wins / 10 trials → 80% hit rate
# 95% CI: [44%, 97%]  # Wide interval - not confident!
#
# 80 wins / 100 trials → 80% hit rate
# 95% CI: [71%, 87%]  # Narrow interval - more confident
```

### 10.4 Survivorship Bias

**Problem:** Only analyzing stocks that still exist (ignoring delistings)

**Mitigation:**
- **Include delisted stocks** in analysis
- **Track ticker changes** (mergers, acquisitions)
- **Note when price data unavailable** (don't assume 0% return)
- **Separate analysis for OTC vs. listed stocks**

**Code Example:**
```python
def fetch_price_with_survivorship_handling(ticker, timestamp):
    """
    Handle delisted / merged stocks gracefully
    """
    try:
        price_data = yfinance_lookup(ticker, timestamp)
        return price_data
    except TickerNotFound:
        # Check if ticker was delisted
        delisting_info = check_delisting_database(ticker)

        if delisting_info:
            # Stock was delisted - mark as total loss
            return {
                "status": "DELISTED",
                "delisting_date": delisting_info.date,
                "final_price": 0.0,
                "return": -100.0
            }

        # Check if ticker changed (merger/acquisition)
        new_ticker = check_ticker_change_history(ticker)

        if new_ticker:
            # Ticker changed - lookup new symbol
            return fetch_price_with_survivorship_handling(new_ticker, timestamp)

        # Unknown - can't determine return
        return {"status": "UNKNOWN", "return": None}
```

### 10.5 Look-Ahead Bias

**Problem:** Using information that wasn't available at decision time

**Mitigation:**
- **Point-in-time database** (snapshot what was known when)
- **Never use future prices** for keyword validation
- **Timestamp all data carefully**
- **Simulate realistic delays** (5-10 min from news to alert)

**Code Example:**
```python
def validate_at_decision_time(item, keyword_weights):
    """
    Only use information available when decision was made
    """
    # BAD: Using today's keyword weights to judge yesterday's decision
    # current_weights = load_keyword_weights()

    # GOOD: Use weights that existed at decision time
    decision_time = item.timestamp
    weights_at_time = load_keyword_weights_snapshot(decision_time)

    # Reclassify with historical weights
    score = classify_with_weights(item, weights_at_time)

    return score
```

### 10.6 Transaction Costs

**Problem:** Ignoring commissions, slippage, spread can invalidate backtest

**Mitigation:**
- **Model realistic costs** (0.1% commission + 0.2% slippage = 0.3% round-trip)
- **Account for bid-ask spread** (wider for low-volume stocks)
- **Impact cost** (large orders move the market)
- **Opportunity cost** (capital tied up)

**Code Example:**
```python
def compute_net_return(gross_return, trade_size=1000):
    """
    Adjust for transaction costs
    """
    # Assumptions:
    # - $0 commission (modern brokers)
    # - 0.2% slippage (0.1% entry + 0.1% exit)
    # - Bid-ask spread: 0.1% (for liquid stocks)

    slippage = 0.002  # 0.2%
    spread = 0.001    # 0.1%

    total_cost = slippage + spread

    net_return = gross_return - total_cost

    return net_return

# Example:
# Gross return: +10.0%
# Net return: +10.0% - 0.3% = +9.7%
#
# Small difference, but compounds over many trades!
```

### 10.7 Data Quality Issues

**Problem:** Bad data in = bad recommendations out

**Mitigation:**
- **Validate price data** (reject outliers, check for splits)
- **Handle corporate actions** (stock splits, dividends)
- **Cross-reference multiple sources** (yfinance vs Tiingo vs Alpha Vantage)
- **Flag suspicious returns** (>100% in 1 hour)
- **Manual review** of extreme cases

**Code Example:**
```python
def validate_price_data(price_data):
    """
    Sanity checks on price data
    """
    warnings = []

    # Check for impossible returns
    if price_data.pct_change > 200:
        warnings.append(f"Suspicious return: {price_data.pct_change:.1f}%")

    # Check for stock splits
    if price_data.volume > price_data.avg_volume * 10:
        warnings.append("Possible stock split detected")

    # Check for corporate actions
    if price_data.price_jumped and not price_data.volume_jumped:
        warnings.append("Price jump without volume - check for dividend")

    # Cross-reference sources
    if abs(price_data.yf_price - price_data.tiingo_price) > 0.05:
        warnings.append("Price discrepancy between sources")

    if warnings:
        return False, warnings

    return True, []
```

### 10.8 Performance Degradation

**Problem:** Adding analysis slows down main bot loop

**Mitigation:**
- **Run MOA asynchronously** (separate process)
- **Batch operations** (analyze daily, not per-item)
- **Cache aggressively** (price lookups, keyword stats)
- **Use indexes** (SQLite indexes on ticker, date)
- **Limit log file size** (30-day rotation)

**Code Example:**
```python
# BAD: Synchronous price lookup per item
for item in rejected_items:
    price_change = fetch_price_change(item.ticker)  # SLOW!
    item.price_change = price_change

# GOOD: Batch fetch with caching
tickers = list(set(item.ticker for item in rejected_items))
price_changes = batch_fetch_price_changes(tickers)  # Single API call

for item in rejected_items:
    item.price_change = price_changes.get(item.ticker)
```

### 10.9 Keyword Pollution

**Problem:** Adding too many low-quality keywords creates noise

**Mitigation:**
- **Strict validation criteria** (min 10 samples, p < 0.05, hit rate > 60%)
- **Periodic keyword pruning** (remove stale keywords)
- **Blacklist for losers** (negative weights)
- **Human review** for all new keywords
- **Max keywords per category** (top 50 only)

**Code Example:**
```python
def prune_stale_keywords(keyword_stats, days=90):
    """
    Remove keywords that no longer perform
    """
    to_remove = []

    for keyword, stats in keyword_stats.items():
        # Check recent performance (last 30 days)
        recent_stats = compute_stats(keyword, last_n_days=30)

        # Remove if:
        # 1. Hit rate dropped below 50%
        # 2. No occurrences in last 90 days
        # 3. Negative avg return

        if recent_stats.hit_rate < 0.5:
            to_remove.append(keyword)
        elif recent_stats.total == 0:
            to_remove.append(keyword)
        elif recent_stats.avg_return < 0:
            to_remove.append(keyword)

    # Archive removed keywords (don't delete - may be useful later)
    archive_keywords(to_remove)

    return to_remove
```

### 10.10 Feedback Loop Instability

**Problem:** Rapid parameter changes cause oscillation

**Mitigation:**
- **Cooling period** between changes (7 days)
- **Damping factor** (only adjust by 20% max)
- **Moving average smoothing** (don't react to single day)
- **Manual override** (admin can pause learning)
- **Exponential backoff** (slow down if changes fail)

**Code Example:**
```python
class AdaptiveWeightController:
    def __init__(self):
        self.last_change_time = None
        self.consecutive_failures = 0
        self.cooling_period_days = 7

    def can_make_change(self):
        """
        Rate limiting with exponential backoff
        """
        if self.last_change_time is None:
            return True

        days_since = (datetime.now() - self.last_change_time).days

        # Base cooling period
        required_cooling = self.cooling_period_days

        # Exponential backoff if changes keep failing
        if self.consecutive_failures > 0:
            required_cooling *= (2 ** self.consecutive_failures)

        return days_since >= required_cooling

    def apply_change(self, change):
        """
        Apply weight change with validation
        """
        if not self.can_make_change():
            return False, "Cooling period active"

        # Apply change
        old_performance = measure_performance()
        apply_weight_change(change)
        new_performance = measure_performance()

        # Validate
        if new_performance.sharpe < old_performance.sharpe * 0.9:
            # Performance degraded - rollback
            rollback_change(change)
            self.consecutive_failures += 1
            return False, "Performance degraded"

        # Success!
        self.last_change_time = datetime.now()
        self.consecutive_failures = 0
        return True, "Applied successfully"
```

---

## 11. Integration with Existing System

### 11.1 Current System Architecture

**Existing Components:**
```
catalyst-bot/
├── src/catalyst_bot/
│   ├── runner.py           # Main loop (processes ~330 items/cycle)
│   ├── feeds.py            # Fetches news from Finviz, etc.
│   ├── classifier.py       # Keyword-based classification
│   ├── analyzer.py         # Analyzes ALERTED items (nightly at 1 AM UTC)
│   ├── admin_controls.py   # Generates admin reports with recommendations
│   ├── backtest/
│   │   ├── simulator.py    # Backtests executed trades
│   │   └── metrics.py      # Sharpe, Sortino, etc.
│   └── market.py           # Price fetching (yfinance, Tiingo, Alpha Vantage)
│
└── data/
    ├── events.jsonl        # Log of ALERTED items only
    ├── keyword_weights.json # Manual keyword weights
    └── analyzer/
        ├── keyword_stats.json
        └── pending_*.json  # Approval workflow
```

**Current Flow:**
1. `runner.py` fetches 330 news items per cycle
2. `feeds.py` filters items (score, price, sentiment)
3. ~0-6 items pass filters → logged to `events.jsonl`
4. ~150+ items filtered out → **DISCARDED** (the problem!)
5. `analyzer.py` runs nightly at 1 AM UTC
6. Analyzes only the 0-6 alerted items
7. Generates weight recommendations
8. `admin_controls.py` creates Discord embed for review

### 11.2 MOA Integration Points

**Minimal changes needed:**

**Change 1: Add rejected item logging in `feeds.py`**
```python
# Around line 600-700 (filtering logic)

def process_feed_items(items):
    passed_items = []
    rejected_items = []  # NEW

    for item in items:
        # ... existing classification ...

        # Check filters
        if item.score < MIN_SCORE:
            # NEW: Log rejection
            if 0.10 <= item.price <= 10.00:  # Only log items in target price range
                log_rejected_item(
                    item,
                    reason="LOW_SCORE",
                    threshold=MIN_SCORE
                )
            rejected_items.append(item)
            continue

        # ... more filters ...

        passed_items.append(item)

    # NEW: Emit metrics
    log.info(f"filter_results passed={len(passed_items)} rejected={len(rejected_items)}")

    return passed_items
```

**Change 2: Schedule MOA in `runner.py`**
```python
# Around line 200-300 (main loop)

def runner_loop():
    last_moa_run = None

    while True:
        # ... existing cycle logic ...

        # Check if it's time to run MOA (2 AM UTC, daily)
        now_utc = datetime.now(timezone.utc)

        if now_utc.hour == 2 and now_utc.minute == 0:
            # Prevent running twice in same hour
            if last_moa_run is None or (now_utc - last_moa_run).total_seconds() > 3600:
                try:
                    from .missed_opportunities.analyzer import run_missed_opportunities_analysis

                    target_date = (now_utc - timedelta(days=1)).date()
                    run_missed_opportunities_analysis(target_date)

                    last_moa_run = now_utc
                    log.info(f"moa_complete date={target_date}")
                except Exception as e:
                    log.error(f"moa_failed err={e}", exc_info=True)

        # ... continue cycle ...
```

**Change 3: Extend admin report in `admin_controls.py`**
```python
# Around line 760-820 (generate_admin_report function)

def generate_admin_report(target_date):
    # ... existing report generation ...

    # Existing sections:
    # - Backtest summary
    # - Keyword performance
    # - Parameter recommendations

    # NEW: Add missed opportunities section
    try:
        from .missed_opportunities.reporter import build_moa_section

        moa_section = build_moa_section(target_date)

        if moa_section:
            # Add as new embed field
            fields.append({
                "name": "📉 Missed Opportunities (Beta)",
                "value": moa_section,
                "inline": False
            })
    except Exception as e:
        log.warning(f"moa_section_failed err={e}")

    return AdminReport(...)
```

### 11.3 Backward Compatibility

**Ensure existing functionality unchanged:**

✅ **No changes to:**
- `analyzer.py` - continues analyzing alerted items
- `backtest/simulator.py` - continues backtesting executed trades
- `models.py` - no breaking changes to data structures
- `classifier.py` - continues using existing keyword weights

✅ **Additive changes only:**
- New directory: `src/catalyst_bot/missed_opportunities/`
- New JSONL file: `data/rejected_items.jsonl`
- New SQLite DB: `data/missed_opportunities/performance.db`
- New admin report section (optional, can be disabled)

✅ **Feature flag for gradual rollout:**
```python
# Environment variable to enable/disable MOA
MOA_ENABLED = os.getenv("FEATURE_MOA_ENABLED", "0") == "1"

if MOA_ENABLED:
    # Run MOA analysis
    run_missed_opportunities_analysis(target_date)
else:
    # Skip (existing behavior)
    pass
```

### 11.4 Testing Strategy

**Unit Tests:**
```python
# tests/test_missed_opportunities.py

def test_rejected_item_logging():
    """Test that rejected items are logged correctly"""
    item = create_test_item(score=0.18, price=2.50)

    log_rejected_item(item, reason="LOW_SCORE", threshold=0.25)

    # Verify logged to file
    logged = load_rejected_items(today())
    assert len(logged) == 1
    assert logged[0].rejection_reason == "LOW_SCORE"

def test_keyword_discovery():
    """Test keyword extraction from missed winners"""
    missed_winners = [
        create_winner(title="FDA approval granted for breakthrough therapy", gain=25.0),
        create_winner(title="FDA fast track designation announced", gain=18.0),
        create_winner(title="Breakthrough therapy status received", gain=15.0)
    ]

    keywords = extract_keywords_tfidf(missed_winners, [])

    # Should discover "fda", "breakthrough", etc.
    assert "fda" in [kw[0] for kw in keywords]
    assert "breakthrough" in [kw[0] for kw in keywords]

def test_overfitting_prevention():
    """Test that keyword validation prevents overfitting"""
    # Create keyword with only 2 occurrences (below min threshold)
    keyword_stats = KeywordStats(keyword="rare_word", total=2, hits=2, avg_return=50.0)

    is_valid = validate_keyword(keyword_stats)

    # Should reject due to insufficient sample size
    assert not is_valid
```

**Integration Tests:**
```python
def test_end_to_end_moa_pipeline():
    """Test full MOA pipeline from logging to recommendations"""
    # 1. Generate fake rejected items
    generate_fake_rejected_items(count=100, date=yesterday())

    # 2. Run MOA analysis
    report = run_missed_opportunities_analysis(yesterday())

    # 3. Verify report contains expected sections
    assert report.missed_winners is not None
    assert report.keyword_candidates is not None
    assert report.weight_recommendations is not None

    # 4. Verify recommendations have confidence scores
    for rec in report.weight_recommendations:
        assert 0 <= rec.confidence <= 1.0
```

**Performance Tests:**
```python
def test_logging_overhead():
    """Ensure rejected item logging doesn't slow down main loop"""
    import time

    items = create_test_items(count=500)

    # Measure time with logging disabled
    start = time.time()
    process_items_without_logging(items)
    baseline_time = time.time() - start

    # Measure time with logging enabled
    start = time.time()
    process_items_with_logging(items)
    logging_time = time.time() - start

    # Overhead should be < 10%
    overhead = (logging_time - baseline_time) / baseline_time
    assert overhead < 0.10, f"Logging overhead too high: {overhead:.1%}"
```

### 11.5 Deployment Plan

**Phase 1: Shadow Mode (Week 1-2)**
- Deploy MOA code
- Enable rejected item logging
- Run analysis nightly
- Generate reports but **don't post to Discord**
- Monitor logs for errors

**Phase 2: Read-Only (Week 3-4)**
- Post MOA reports to Discord
- Admin can review but **can't approve changes**
- Gather feedback on report format
- Validate keyword discoveries manually

**Phase 3: Manual Approval (Week 5-8)**
- Enable approval workflow
- Admin must click button to apply changes
- Monitor impact on bot performance
- Collect 30 days of data

**Phase 4: Auto-Approval (Week 9+)**
- Enable auto-approval for high-confidence changes (>90%)
- Admin still reviews lower-confidence changes
- Implement rollback automation
- Full production deployment

**Rollback Plan:**
```python
# If MOA causes issues, disable via environment variable
MOA_ENABLED=0

# Or rollback code changes:
git revert <commit-hash>

# Rejected items log can be deleted if needed:
rm data/rejected_items.jsonl
```

---

## 12. Conclusion & Next Steps

### 12.1 Summary

The Missed Opportunities Analyzer represents a **novel approach** to trading bot optimization by focusing on **false negatives** rather than just executed trades. By analyzing the 150+ filtered items per cycle, we can:

1. **Discover new catalysts** before they become mainstream
2. **Optimize filter thresholds** (MIN_SCORE, PRICE_CEILING) systematically
3. **Learn from mistakes** without manual observation
4. **Avoid overfitting** through rigorous statistical validation
5. **Automate the feedback loop** with human oversight

### 12.2 Expected Outcomes

**Quantitative Goals (6 months):**
- **Discover 20-30 new keywords** with statistical significance
- **Reduce false negative rate by 30%** (fewer missed winners)
- **Improve Sharpe ratio by 15%** through better parameter tuning
- **Increase alert quality** (higher hit rate on alerted items)
- **Reduce manual review time by 50%** (automated recommendations)

**Qualitative Goals:**
- Shift from **reactive** (manual tuning) to **proactive** (data-driven)
- Create **institutional-grade** backtesting infrastructure
- Build **knowledge base** of what works (and what doesn't)
- Enable **rapid experimentation** with new strategies
- Establish **competitive advantage** through proprietary insights

### 12.3 Resource Requirements

**Engineering Time:**
- Phase 1 (MVP): 3 weeks (1 developer)
- Phase 2 (Full features): 6 weeks (1 developer)
- Phase 3 (Maintenance): 2 hours/week (ongoing)

**Infrastructure:**
- No additional servers needed (runs on existing machine)
- ~1 GB additional disk space per month (logs + database)
- yfinance API: Free tier sufficient (5-10 req/sec)

**Budget:**
- No additional costs (uses existing tools)

### 12.4 Next Steps

**Immediate Actions (This Week):**
1. Review this design document with team
2. Prioritize must-have vs nice-to-have features
3. Set up development branch: `feature/missed-opportunities-analyzer`
4. Create skeleton directory structure

**Week 1:**
1. Implement rejected item logging in `feeds.py`
2. Create `missed_opportunities/` module structure
3. Write unit tests for logging functionality
4. Deploy in shadow mode (logging only, no analysis)

**Week 2:**
1. Implement price fetcher with caching
2. Build SQLite database schema
3. Create basic analysis script (identify missed winners)
4. Test with 7 days of rejected items

**Week 3:**
1. Implement keyword discovery (TF-IDF)
2. Add statistical validation
3. Generate first MOA report (text format)
4. Review with team

**Week 4-6:**
1. Build recommendation engine
2. Create Discord embed interface
3. Implement approval workflow
4. Full integration with existing admin system

**Week 7+:**
1. Monitor performance in production
2. Tune confidence thresholds
3. Add advanced features (NER, sector weights, etc.)
4. Iterate based on admin feedback

### 12.5 Success Metrics

**Track weekly:**
- Number of rejected items logged
- Number of missed winners identified
- Number of new keywords discovered
- Number of recommendations generated
- Admin approval rate
- Bot Sharpe ratio (before/after changes)

**Dashboard:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Missed Opportunities Analyzer - Weekly Dashboard               │
├─────────────────────────────────────────────────────────────────┤
│  Week of 2025-10-10                                             │
│                                                                  │
│  📊 Data Collection:                                            │
│    - Rejected items logged: 1,247                               │
│    - Missed winners (>10%): 18                                  │
│    - Missed opportunity cost: +347% total                       │
│                                                                  │
│  🔍 Keyword Discovery:                                          │
│    - New keywords discovered: 3                                 │
│    - Keywords validated: 2                                      │
│    - Keywords rejected (low confidence): 1                      │
│                                                                  │
│  ⚙️ Recommendations:                                            │
│    - Weight adjustments: 5                                      │
│    - Threshold changes: 1                                       │
│    - Auto-approved: 2                                           │
│    - Admin-approved: 3                                          │
│    - Rejected: 1                                                │
│                                                                  │
│  📈 Performance Impact:                                         │
│    - Sharpe ratio: 0.87 → 0.94 (+8%)                           │
│    - Win rate: 54% → 58% (+4%)                                 │
│    - False negative rate: 12% → 9% (-3%)                       │
│                                                                  │
│  🎯 Top Missed Opportunity:                                     │
│    ABCD: +73% in 24h (rejected: LOW_SCORE 0.21 < 0.25)         │
│    Keywords: "breakthrough therapy", "fda fast track"           │
│    Action: Added "breakthrough" to dictionary, weight 1.5       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix A: Research Sources

### Academic Papers
1. **"Trade the Event: Corporate Events Detection for News-Based Event-Driven Trading"**
   - Authors: Zhihan et al., ACL 2021
   - URL: https://arxiv.org/abs/2105.12825
   - Key Insight: Bi-level event detection (token + article level)

2. **"Sentiment Analysis in Algorithmic Trading"**
   - ResearchGate, 2024
   - Key Insight: Hybrid sentiment + technical indicators outperform

3. **"Successful Backtesting of Algorithmic Trading Strategies"**
   - QuantStart, Parts I & II
   - URL: https://www.quantstart.com/articles/
   - Key Insight: Optimization bias is the #1 beginner mistake

4. **"Backtesting Strategies Based on Multiple Signals"**
   - NBER Working Paper
   - Key Insight: Combining signals requires statistical validation

### Industry Resources
5. **"Event-Driven Trading and the 'New News'"**
   - Journal of Portfolio Management, 2011
   - Key Insight: Pure news signals generated 10%+ alpha (2006-2010)

6. **Trade the Event GitHub Implementation**
   - https://github.com/Zhihan1996/TradeTheEvent
   - Includes EDT dataset and news scraping tools

7. **AlgoTest: Backtesting Platform**
   - https://algotest.in/
   - Examples of professional backtesting UX

### Libraries & Tools
8. **scikit-learn** - TF-IDF, clustering
9. **spaCy** - Named Entity Recognition
10. **yfinance** - Price data
11. **SQLite** - Time-series database
12. **plotly** - Interactive visualizations

---

## Appendix B: Code Examples

### Example 1: Complete MOA Pipeline
```python
# src/catalyst_bot/missed_opportunities/analyzer.py

from datetime import date, timedelta
from typing import List, Dict
import logging

from .logger import load_rejected_items
from .price_fetcher import batch_fetch_price_changes
from .keyword_discovery import extract_keywords_tfidf
from .recommendations import generate_weight_recommendations
from .reporter import build_moa_report

log = logging.getLogger("moa.analyzer")

def run_missed_opportunities_analysis(target_date: date):
    """
    Main entry point for MOA pipeline.

    Steps:
    1. Load rejected items from target_date
    2. Fetch price changes for all tickers
    3. Identify missed winners (>10% gain)
    4. Extract keywords from missed winners
    5. Generate weight recommendations
    6. Build report and post to Discord
    """
    log.info(f"moa_start date={target_date}")

    # 1. Load rejected items
    rejected = load_rejected_items(target_date)
    log.info(f"loaded_rejected count={len(rejected)}")

    # 2. Fetch prices (multi-timeframe)
    tickers = list(set(r.ticker for r in rejected))
    price_changes = batch_fetch_price_changes(
        tickers,
        reference_date=target_date,
        timeframes=[1, 4, 24, 168]  # hours
    )

    # 3. Identify missed winners
    missed_winners = []
    for item in rejected:
        changes = price_changes.get(item.ticker)
        if changes is None:
            continue

        max_gain = max(changes.values())
        if max_gain >= 10.0:  # 10%+ threshold
            item.price_changes = changes
            item.max_gain = max_gain
            missed_winners.append(item)

    log.info(f"missed_winners count={len(missed_winners)}")

    # 4. Extract keywords
    keyword_candidates = extract_keywords_tfidf(
        winners=missed_winners,
        losers=[r for r in rejected if r not in missed_winners]
    )

    # 5. Generate recommendations
    recommendations = generate_weight_recommendations(
        missed_winners=missed_winners,
        keyword_candidates=keyword_candidates
    )

    # 6. Build and post report
    report = build_moa_report(
        date=target_date,
        missed_winners=missed_winners,
        keyword_candidates=keyword_candidates,
        recommendations=recommendations
    )

    # Save to disk
    report.save(f"out/missed_opportunities/report_{target_date}.json")

    # Post to Discord
    from ..admin_controls import post_admin_embed
    post_admin_embed(report.to_discord_embed())

    log.info(f"moa_complete date={target_date}")
    return report
```

### Example 2: Keyword Discovery
```python
# src/catalyst_bot/missed_opportunities/keyword_discovery.py

from collections import defaultdict
from typing import List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

def extract_keywords_tfidf(
    winners: List[Dict],
    losers: List[Dict],
    top_n: int = 50
) -> List[Tuple[str, float]]:
    """
    Extract keywords using TF-IDF comparison.

    High-scoring words in winners (vs losers) are candidates.
    """
    winner_titles = [w.title for w in winners]
    loser_titles = [l.title for l in losers]

    if not winner_titles:
        return []

    # TF-IDF vectorizer
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 3),  # 1-3 word phrases
        min_df=2,            # Must appear at least twice
        max_df=0.7,          # Remove if in >70% of docs (too common)
        stop_words='english',
        lowercase=True
    )

    # Fit on winners
    winner_tfidf = vectorizer.fit_transform(winner_titles)

    # Get feature names and scores
    feature_names = vectorizer.get_feature_names_out()
    scores = winner_tfidf.sum(axis=0).A1

    # Sort by score
    sorted_keywords = sorted(
        zip(feature_names, scores),
        key=lambda x: x[1],
        reverse=True
    )[:top_n]

    # Filter by validation criteria
    validated = []
    for keyword, score in sorted_keywords:
        if validate_keyword_candidate(keyword, winners, losers):
            validated.append((keyword, score))

    return validated

def validate_keyword_candidate(
    keyword: str,
    winners: List[Dict],
    losers: List[Dict]
) -> bool:
    """
    Check if keyword meets validation criteria:
    - Appears in >=3 winners
    - Win rate > 60%
    - Avg return > 5%
    """
    winner_count = sum(1 for w in winners if keyword.lower() in w.title.lower())
    loser_count = sum(1 for l in losers if keyword.lower() in l.title.lower())

    total = winner_count + loser_count

    if total < 3:
        return False

    win_rate = winner_count / total
    if win_rate < 0.6:
        return False

    # Calculate avg return for winner
    returns = [
        w.max_gain for w in winners
        if keyword.lower() in w.title.lower()
    ]

    if not returns:
        return False

    avg_return = np.mean(returns)
    if avg_return < 5.0:
        return False

    return True
```

---

**End of Document**

*This design document is a living document and will be updated as the system evolves. Last updated: 2025-10-10*
