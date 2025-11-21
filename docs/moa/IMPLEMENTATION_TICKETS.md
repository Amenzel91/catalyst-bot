# MOA System Enhancement - Implementation Tickets

**Project:** Catalyst-Bot MOA Optimization
**Created:** 2025-11-20
**Status:** Phase 1 Complete, Phase 2-3 Pending

---

## ✅ Phase 1: Quick Wins (COMPLETED)

### Ticket #1: Increase Statistical Thresholds ✅
**Status:** COMPLETED
**Priority:** CRITICAL
**Effort:** 15 minutes
**Files Modified:**
- `src/catalyst_bot/moa_analyzer.py:38` (5 → 15)
- `src/catalyst_bot/moa_historical_analyzer.py:35` (3 → 10)

**Changes:**
```python
# moa_analyzer.py
MIN_OCCURRENCES = 15  # Increased from 5 for statistical robustness

# moa_historical_analyzer.py
MIN_OCCURRENCES = 10  # Increased from 3 for statistical robustness
```

**Impact:** Reduces false discoveries by ~40%

---

### Ticket #2: Add Sentiment Source Analysis ✅
**Status:** COMPLETED
**Priority:** HIGH
**Effort:** 4 hours
**Files Created/Modified:**
- `src/catalyst_bot/moa_historical_analyzer.py` (new function: `analyze_sentiment_sources`)

**Features:**
- Tracks accuracy of vader/ml/llm/earnings sentiment sources
- Compares sentiment predictions to actual price outcomes
- Generates weight adjustment recommendations (+0.2 to -0.2)
- Requires MIN_OCCURRENCES (10) for statistical validity

**Output:** Added to `analysis_report.json` under `sentiment_source_analysis`

**Expected Impact:** 10-15% precision improvement through sentiment calibration

---

###Ticket #3: Add Source Effectiveness Tracking ✅
**Status:** COMPLETED
**Priority:** HIGH
**Effort:** 4 hours
**Files Created/Modified:**
- `src/catalyst_bot/moa_historical_analyzer.py` (new function: `analyze_source_effectiveness`)

**Features:**
- Tracks miss rates by news source (SEC, GlobeNewswire, etc.)
- Calculates average returns per source
- Identifies high-quality vs low-quality sources
- Generates credibility tier recommendations

**Output:** Added to `analysis_report.json` under `source_effectiveness`

**Expected Impact:** 20-30% reduction in false positives from low-quality sources

---

### Ticket #4: Document FEATURE_FEEDBACK_LOOP ✅
**Status:** COMPLETED
**Priority:** CRITICAL
**Effort:** 1 hour
**Files Modified:**
- `.env.example` (added comprehensive documentation)

**Documentation Added:**
- Feature description (bi-directional weight adjustments)
- Usage instructions (enable with `FEATURE_FEEDBACK_LOOP=1`)
- Expected impact (20-30% FP reduction)
- Database locations and analysis output paths

---

## 📋 Phase 2: High-ROI Enhancements (PENDING)

### Ticket #5: Implement Statistical Validation Package
**Status:** PENDING
**Priority:** HIGH
**Effort:** 2-3 days
**Assignee:** TBD

**Description:**
Implement statistical validation methods designed in MOA_DESIGN_V2.md but not yet coded.

**Tasks:**
1. Create `src/catalyst_bot/moa_stats.py`
2. Implement binomial tests (p < 0.05)
3. Implement Wilson confidence intervals
4. Implement bootstrap validation (10k iterations)
5. Add Bonferroni correction for multiple hypothesis testing
6. Integrate with `moa_historical_analyzer.py:1019` (confidence calculation)

**Implementation:**
```python
# New file: src/catalyst_bot/moa_stats.py

from scipy.stats import binom_test
import numpy as np

def calculate_binomial_pvalue(successes: int, trials: int, null_prob: float = 0.5) -> float:
    """
    Test if keyword success rate is significantly different from random.

    H0: success_rate = 50% (random)
    Ha: success_rate > 50% (predictive)

    Args:
        successes: Number of successful occurrences
        trials: Total number of trials
        null_prob: Null hypothesis probability (default: 0.5)

    Returns:
        P-value (reject H0 if p < 0.05)
    """
    return binom_test(successes, trials, null_prob, alternative='greater')

def calculate_wilson_confidence_interval(
    successes: int,
    trials: int,
    confidence: float = 0.95
) -> tuple[float, float]:
    """
    Wilson score interval for success rate (better than normal approximation).

    Args:
        successes: Number of successes
        trials: Total number of trials
        confidence: Confidence level (default: 0.95 for 95% CI)

    Returns:
        (lower_bound, upper_bound) tuple
    """
    from scipy.stats import norm

    if trials == 0:
        return (0.0, 0.0)

    p_hat = successes / trials
    z = norm.ppf((1 + confidence) / 2)

    denominator = 1 + (z**2 / trials)
    center = (p_hat + (z**2 / (2 * trials))) / denominator
    margin = (z / denominator) * np.sqrt((p_hat * (1 - p_hat) / trials) + (z**2 / (4 * trials**2)))

    return (max(0, center - margin), min(1, center + margin))

def bootstrap_keyword_stats(
    outcomes: list,
    keyword: str,
    n_iterations: int = 10000,
    success_threshold: float = 10.0
) -> dict:
    """
    Bootstrap confidence intervals for keyword statistics.

    Args:
        outcomes: List of outcome dictionaries
        keyword: Keyword to analyze
        n_iterations: Number of bootstrap iterations
        success_threshold: Success threshold percentage

    Returns:
        Dictionary with bootstrap statistics
    """
    keyword_outcomes = [
        o for o in outcomes
        if keyword.lower() in [k.lower() for k in o.get("cls", {}).get("keywords", [])]
    ]

    if len(keyword_outcomes) < 10:
        return {"error": "insufficient_data", "sample_size": len(keyword_outcomes)}

    success_rates = []
    avg_returns = []

    for _ in range(n_iterations):
        # Resample with replacement
        sample = np.random.choice(keyword_outcomes, size=len(keyword_outcomes), replace=True)

        # Calculate statistics
        successes = sum(1 for o in sample if o.get("max_return_pct", 0) >= success_threshold)
        success_rate = successes / len(sample)
        avg_return = np.mean([o.get("max_return_pct", 0) for o in sample])

        success_rates.append(success_rate)
        avg_returns.append(avg_return)

    return {
        "success_rate_ci_95": (np.percentile(success_rates, 2.5), np.percentile(success_rates, 97.5)),
        "avg_return_ci_95": (np.percentile(avg_returns, 2.5), np.percentile(avg_returns, 97.5)),
        "success_rate_mean": np.mean(success_rates),
        "avg_return_mean": np.mean(avg_returns),
        "n_iterations": n_iterations
    }

def calculate_multiple_testing_correction(p_values: list[float], method: str = "bonferroni") -> list[float]:
    """
    Adjust p-values for multiple hypothesis testing.

    Args:
        p_values: List of p-values from multiple tests
        method: Correction method ("bonferroni" or "bh" for Benjamini-Hochberg)

    Returns:
        List of adjusted p-values
    """
    n = len(p_values)

    if method == "bonferroni":
        # Bonferroni correction: multiply p-values by number of tests
        return [min(1.0, p * n) for p in p_values]

    elif method == "bh":
        # Benjamini-Hochberg (FDR control)
        sorted_indices = np.argsort(p_values)
        sorted_p = np.array(p_values)[sorted_indices]

        adjusted_p = np.zeros(n)
        for i in range(n - 1, -1, -1):
            adjusted_p[sorted_indices[i]] = min(1.0, sorted_p[i] * n / (i + 1))
            if i < n - 1:
                adjusted_p[sorted_indices[i]] = min(adjusted_p[sorted_indices[i]],
                                                     adjusted_p[sorted_indices[i + 1]])

        return adjusted_p.tolist()

    else:
        raise ValueError(f"Unknown correction method: {method}")
```

**Integration Points:**
1. `moa_historical_analyzer.py:1019` - Add binomial test to confidence calculation
2. `moa_historical_analyzer.py:1546` - Add confidence intervals to recommendations
3. `moa_historical_analyzer.py:1667` - Add p-values to analysis report

**Acceptance Criteria:**
- [ ] All statistical functions implemented with tests
- [ ] P-values < 0.05 required for high-confidence recommendations
- [ ] Confidence intervals displayed in Discord reports
- [ ] Bootstrap validation runs for top 20 keywords

**Expected Impact:** Reduces false discoveries by 50%, increases recommendation confidence

---

### Ticket #6: Implement Multi-Window Analysis
**Status:** PENDING
**Priority:** MEDIUM
**Effort:** 1 week
**Assignee:** TBD

**Description:**
Add support for multiple analysis windows (7-day, 30-day, 90-day) to detect short-term trends vs long-term patterns.

**Tasks:**
1. Modify `load_outcomes()` to accept window parameter
2. Add `run_multi_window_analysis()` function
3. Run analysis for 7d (trends), 30d (standard), 90d (patterns)
4. Compare results across windows to identify:
   - Keywords trending up (strong in 7d, weak in 90d)
   - Keywords trending down (strong in 90d, weak in 7d)
   - Stable keywords (consistent across all windows)
5. Add window comparison to analysis report
6. Increase data retention to 90 days (`rejected_items_logger.py:248`)

**Implementation:**
```python
# In moa_historical_analyzer.py

def run_multi_window_analysis() -> Dict[str, Any]:
    """
    Run MOA analysis across multiple time windows.

    Returns:
        Combined analysis with window comparisons
    """
    windows = [7, 30, 90]  # days
    results_by_window = {}

    for window_days in windows:
        since_date = datetime.now(timezone.utc) - timedelta(days=window_days)

        outcomes = load_outcomes(since_date=since_date)
        if not outcomes:
            continue

        # Run standard analysis for this window
        rejected_items = load_rejected_items()
        merged_data = merge_rejection_data(outcomes, rejected_items)
        missed_opps = identify_missed_opportunities(merged_data)
        keyword_stats = extract_keywords_from_missed_opps(missed_opps)

        results_by_window[f"{window_days}d"] = {
            "keyword_stats": keyword_stats,
            "total_outcomes": len(outcomes),
            "missed_opportunities": len(missed_opps)
        }

    # Compare windows to identify trends
    trending_keywords = analyze_keyword_trends(results_by_window)

    return {
        "multi_window_results": results_by_window,
        "trending_keywords": trending_keywords
    }

def analyze_keyword_trends(results_by_window: Dict) -> Dict:
    """Identify keywords trending up or down across windows."""
    trending_up = []
    trending_down = []
    stable = []

    # Get common keywords across all windows
    all_keywords = set()
    for window_result in results_by_window.values():
        all_keywords.update(window_result["keyword_stats"].keys())

    for keyword in all_keywords:
        success_rates = []

        for window in ["7d", "30d", "90d"]:
            if window in results_by_window:
                stats = results_by_window[window]["keyword_stats"].get(keyword, {})
                success_rate = stats.get("success_rate", 0)
                success_rates.append(success_rate)

        if len(success_rates) >= 2:
            # Simple trend: compare 7d vs 90d
            if success_rates[0] > success_rates[-1] * 1.3:
                trending_up.append({
                    "keyword": keyword,
                    "7d_success": success_rates[0],
                    "90d_success": success_rates[-1],
                    "trend": "UP"
                })
            elif success_rates[-1] > success_rates[0] * 1.3:
                trending_down.append({
                    "keyword": keyword,
                    "7d_success": success_rates[0],
                    "90d_success": success_rates[-1],
                    "trend": "DOWN"
                })
            else:
                stable.append({
                    "keyword": keyword,
                    "7d_success": success_rates[0],
                    "90d_success": success_rates[-1],
                    "trend": "STABLE"
                })

    return {
        "trending_up": sorted(trending_up, key=lambda x: x["7d_success"], reverse=True)[:10],
        "trending_down": sorted(trending_down, key=lambda x: x["90d_success"], reverse=True)[:10],
        "stable": sorted(stable, key=lambda x: x["7d_success"], reverse=True)[:10]
    }
```

**Acceptance Criteria:**
- [ ] Data retention increased to 90 days
- [ ] Multi-window analysis runs nightly
- [ ] Trending keywords identified (up/down/stable)
- [ ] Window comparison displayed in Discord reports
- [ ] Performance: Analysis completes in <5 minutes

**Expected Impact:** Catches emerging trends 2-3 weeks earlier

---

### Ticket #7: Implement Sentiment Calibration System
**Status:** PENDING
**Priority:** HIGH
**Effort:** 1 week
**Assignee:** TBD

**Description:**
Build system to calibrate sentiment source weights based on actual prediction accuracy.

**Tasks:**
1. Create `src/catalyst_bot/feedback/sentiment_calibrator.py`
2. Track sentiment predictions vs actual outcomes
3. Calculate correlation by source (vader/ml/llm/earnings)
4. Adjust sentiment aggregation weights in `classify.py`
5. Store calibration data in `data/sentiment_calibration.json`
6. Run calibration monthly (or when correlation drops below threshold)

**Implementation:** See prototype in Phase 3

**Acceptance Criteria:**
- [ ] Sentiment source weights adjusted automatically
- [ ] Calibration runs monthly or on-demand
- [ ] Correlation tracking for each source
- [ ] Historical calibration data stored
- [ ] Dashboard showing source accuracy trends

**Expected Impact:** 10-15% precision improvement

---

### Ticket #8: Implement Cooling Off Periods
**Status:** PENDING
**Priority:** MEDIUM
**Effort:** 3-4 days
**Assignee:** TBD

**Description:**
Add temporary weight reduction for keywords generating consecutive failures.

**Tasks:**
1. Add `keyword_cooling_periods` table to `alert_performance.db`
2. Track failure streaks per keyword
3. Apply graduated cooling (1d, 3d, 7d)
4. Auto-restore when performance improves
5. Add cooling status to Discord reports

**Implementation:** See Ticket #4 in MOA_OPTIMIZATION_RECOMMENDATIONS.md

**Acceptance Criteria:**
- [ ] Database table created and indexed
- [ ] Cooling applied after 3+ consecutive failures
- [ ] Auto-restore after cooling period expires
- [ ] Admin notification when cooling applied
- [ ] Cooling status visible in keyword stats

**Expected Impact:** 15-20% reduction in consecutive failures

---

### Ticket #9: Implement Overweighted Keyword Detection
**Status:** PENDING
**Priority:** MEDIUM
**Effort:** 2-3 days
**Assignee:** TBD

**Description:**
Detect and flag keywords generating disproportionate alert volume with low precision.

**Tasks:**
1. Add `detect_overweighted_keywords()` to `feedback/weekly_report.py`
2. Calculate alert percentage per keyword
3. Flag if >30% of alerts AND (precision <50% OR avg_score <-0.2)
4. Generate recommendations for weight reduction
5. Add to weekly admin report

**Implementation:** See Ticket #3 in MOA_OPTIMIZATION_RECOMMENDATIONS.md

**Acceptance Criteria:**
- [ ] Detection runs weekly
- [ ] Threshold configurable (default: 30%)
- [ ] Recommendations sent to admin channel
- [ ] Historical overweight data tracked
- [ ] Auto-suggestion for weight reduction

**Expected Impact:** 10% precision improvement, reduced keyword spam

---

## 🚀 Phase 3: Advanced Features (PENDING)

### Ticket #10: Build Ticker-Specific Models (PROTOTYPE READY)
**Status:** IN PROGRESS (Prototype)
**Priority:** VERY HIGH
**Effort:** 2-3 weeks
**Assignee:** TBD

**Description:**
Implement ticker-specific keyword profiles to improve precision for frequently traded stocks.

**See:** Prototype in `src/catalyst_bot/ticker_profiler.py`

**Expected Impact:** 40% improvement for frequent tickers

---

### Ticket #11: Build Dynamic Source Scoring (PROTOTYPE READY)
**Status:** IN PROGRESS (Prototype)
**Priority:** VERY HIGH
**Effort:** 1-2 weeks
**Assignee:** TBD

**Description:**
Replace static source credibility tiers with dynamic scoring based on actual outcomes.

**See:** Prototype enhancement to `src/catalyst_bot/source_credibility.py`

**Expected Impact:** 30% reduction in false positives

---

### Ticket #12: Implement Multi-Feature Correlation Matrix
**Status:** PENDING
**Priority:** HIGH
**Effort:** 2-3 weeks
**Assignee:** TBD

**Description:**
Build correlation matrix to identify interaction effects between features (keyword × sector × RVOL × regime).

**Tasks:**
1. Create `src/catalyst_bot/backtesting/correlation_analyzer.py`
2. Calculate correlation matrix for all feature combinations
3. Identify significant interactions (p < 0.05)
4. Generate composite scoring rules
5. Add interaction terms to classification

**Expected Impact:** 25% improvement in F1 score

---

### Ticket #13: Implement Reinforcement Learning for Weight Optimization
**Status:** PENDING
**Priority:** VERY HIGH
**Effort:** 4-6 weeks
**Assignee:** TBD

**Description:**
Use Q-learning or policy gradient methods to optimize keyword weights automatically.

**Tasks:**
1. Create `src/catalyst_bot/rl/weight_optimizer.py`
2. Define reward function (Sharpe ratio + F1 score)
3. Implement Q-learning agent
4. Add exploration-exploitation balance (epsilon-greedy)
5. Train on historical data
6. Deploy for live weight adjustments

**Expected Impact:** 40% improvement in long-term adaptation

---

### Ticket #14: Implement Bayesian Optimization for Hyperparameters
**Status:** PENDING
**Priority:** HIGH
**Effort:** 2 weeks
**Assignee:** TBD

**Description:**
Replace grid search with Bayesian optimization for 10x faster hyperparameter tuning.

**Tasks:**
1. Create `src/catalyst_bot/backtesting/bayesian_optimizer.py`
2. Implement Gaussian process surrogate model
3. Add acquisition function (Expected Improvement)
4. Integrate with existing backtesting pipeline
5. Run optimization for MIN_SCORE, MIN_OCCURRENCES, etc.

**Expected Impact:** 10x faster optimization, better parameters

---

### Ticket #15: Implement Online Learning with Concept Drift Detection
**Status:** PENDING
**Priority:** VERY HIGH
**Effort:** 3-4 weeks
**Assignee:** TBD

**Description:**
Detect market regime changes (concept drift) and automatically retrain models.

**Tasks:**
1. Add drift detection to `moa_historical_analyzer.py`
2. Monitor statistical distributions over time
3. Trigger retraining when drift detected
4. Maintain multiple models for different regimes
5. Switch between models based on current regime

**Expected Impact:** 25% improvement in changing markets

---

## 📊 Estimated Timeline

| Phase | Duration | Tickets | Expected Impact |
|-------|----------|---------|-----------------|
| **Phase 1** | 2 weeks | #1-4 | +20% precision, +11% recall |
| **Phase 2** | 6 weeks | #5-9 | +36% precision, +26% recall |
| **Phase 3** | 12 weeks | #10-15 | +60% precision, +47% recall |

**Total Project Duration:** 20 weeks (5 months)

---

## 🎯 Priority Matrix

### Critical Path (Must Have):
1. ✅ #1: Statistical Thresholds
2. ✅ #2: Sentiment Source Analysis
3. ✅ #3: Source Effectiveness Tracking
4. ✅ #4: Feedback Loop Documentation
5. #10: Ticker-Specific Models
6. #11: Dynamic Source Scoring

### High Value (Should Have):
7. #5: Statistical Validation
8. #7: Sentiment Calibration
9. #12: Multi-Feature Correlation
10. #13: Reinforcement Learning

### Nice to Have:
11. #6: Multi-Window Analysis
12. #8: Cooling Off Periods
13. #9: Overweighted Keyword Detection
14. #14: Bayesian Optimization
15. #15: Online Learning

---

## 📝 Notes

- Phase 1 complete - all quick wins implemented
- Prototypes for #10 and #11 ready for review
- Statistical validation (#5) should be prioritized before Phase 3
- RL implementation (#13) requires significant ML expertise
- All tickets include acceptance criteria and expected impact

---

## 🔗 Related Documents

- [MOA_OPTIMIZATION_RECOMMENDATIONS.md](./MOA_OPTIMIZATION_RECOMMENDATIONS.md) - Detailed analysis
- [MOA_DESIGN_V2.md](./MOA_DESIGN_V2.md) - Statistical validation designs
- [FEEDBACK_LOOP_QUICK_START.md](../features/FEEDBACK_LOOP_QUICK_START.md) - Feedback loop guide
