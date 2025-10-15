# Backtester Gaps & Implementation Plan
## Comprehensive Analysis of Missing Features

**Analysis Date:** 2025-10-14
**Sources:** patches1.txt + Weaponizing Backtesting Data Research Document
**Current Status:** 60% Complete (Core infrastructure solid, advanced features missing)

---

## Executive Summary

### ✅ What's Already Implemented (Strong Foundation)
1. **Walk-forward cross-validation** - Temporal order preserved
2. **Bootstrap confidence intervals** - 10,000 resamples for statistics
3. **CPCV (Combinatorial Purged CV)** - N=6, k=2 for overfitting detection
4. **Robust statistics** - Winsorization, MAD, trimmed mean, robust z-scores
5. **RVol calculation** - 20-day baseline with 5-min cache
6. **VWAP calculation** - Intraday exit signals
7. **Market regime detection** - VIX + SPY trend (5 regimes)
8. **MOA tracking** - Missed opportunities analyzer
9. **False Positive tracking** - Penalty recommendations
10. **LRU price cache** - Memory-safe backtesting

### ❌ Critical Gaps (High Priority for Production)

**From patches1.txt:**
1. **Bid/Ask Spread Tracking** (Priority 6/10) - **MOST CRITICAL FOR ACCURATE BACKTESTING**
2. **Real-Time Price Monitoring & Exit System** (Priority 7/10)
3. **TimescaleDB Migration** (Priority 9/10) - Enables O(1) incremental statistics
4. **EWMA Adaptive Thresholds** (Priority 8/10)
5. **Incremental Keyword Statistics** (Priority 9/10) - Welford's algorithm
6. **Source Credibility Feedback Loop** (Priority 7/10)
7. **Keyword Co-occurrence Matrix** (Priority 7/10)

**From Research Document (Not in patches1.txt):**
8. **Bayesian Confidence Scoring** - Beta-Binomial priors for keyword effectiveness
9. **Multiple Hypothesis Testing** - Benjamini-Hochberg FDR correction
10. **Effect Size Calculations** - Cohen's d for practical significance
11. **Time-Decay Modeling** - Exponential decay for catalyst aging
12. **PBO (Probability of Backtest Overfitting)** - Gold standard validation
13. **Probabilistic Sharpe Ratio (PSR)** - Accounts for skewness/kurtosis
14. **Deflated Sharpe Ratio (DSR)** - Adjusts for multiple testing
15. **Thompson Sampling** - Optimal exploration-exploitation
16. **Lift Metrics** - P(Profit|Keyword) / P(Profit)
17. **Log-Likelihood Ratio (LLR)** - Co-occurrence testing
18. **Hidden Markov Models (HMM)** - Regime detection (85-90% accuracy)
19. **Singular Spectrum Analysis (SSA)** - Noise reduction
20. **Slippage Modeling with Spread Multipliers** - Realistic transaction costs

---

## Priority 1: Slippage & Transaction Cost Modeling (CRITICAL)

### Why This Matters Most
Research shows low-priced stocks experience **spread bias up to 97%** versus 13-18% for large caps. Your backtests are likely **overestimating profitability by 30-50%** without proper slippage modeling.

### Current Implementation Gap
```python
# Current: Fixed commission/slippage (if any)
BACKTEST_COMMISSION=0.0  # Not modeling reality
BACKTEST_SLIPPAGE=0.0    # Missing entirely
```

### What's Needed: Bid/Ask Spread-Based Slippage

**Implementation (2 days):**

```python
# src/catalyst_bot/backtesting/slippage.py
def calculate_realistic_slippage(
    ticker: str,
    price: float,
    volume: int,
    position_size: int,
    market_regime: str
) -> float:
    """
    Calculate slippage based on bid-ask spread + market conditions.

    Research-backed formula:
    Slippage = 0.5 × Bid_Ask_Spread × Spread_Multiplier

    Spread_Multiplier varies by:
    - Price level: $1-$10 = 1.5x, <$1 = 2.5x
    - Volume: Low volume = 2.0x, High = 1.0x
    - Regime: High volatility = 1.5x, Normal = 1.0x
    - Time: Market close = 1.3x, Open = 1.1x
    """
    # Estimate spread from price (when historical spread unavailable)
    if price < 1.0:
        estimated_spread_pct = 0.03  # 3% typical for sub-$1
    elif price < 5.0:
        estimated_spread_pct = 0.015  # 1.5% for $1-$5
    else:
        estimated_spread_pct = 0.01  # 1% for $5-$10

    # Base slippage from spread
    base_slippage = 0.5 * (price * estimated_spread_pct)

    # Volume impact (position size vs daily volume)
    volume_ratio = position_size / max(volume, 100000)
    volume_multiplier = 1.0 + (volume_ratio * 2.0)  # Larger orders = more slippage

    # Regime multiplier
    regime_multipliers = {
        "BULL": 1.0,
        "BEAR": 1.2,
        "HIGH_VOL": 1.5,
        "CRASH": 2.0,
        "NEUTRAL": 1.1
    }
    regime_mult = regime_multipliers.get(market_regime, 1.1)

    # Price level multiplier
    if price < 1.0:
        price_mult = 2.5
    elif price < 5.0:
        price_mult = 1.5
    else:
        price_mult = 1.0

    total_slippage = base_slippage * volume_multiplier * regime_mult * price_mult

    # Entry vs Exit asymmetry (exits typically worse)
    return total_slippage

def get_entry_slippage(ticker, price, volume, position_size, regime):
    return calculate_realistic_slippage(ticker, price, volume, position_size, regime)

def get_exit_slippage(ticker, price, volume, position_size, regime):
    # Exits 20% worse on average due to urgency
    return calculate_realistic_slippage(ticker, price, volume, position_size, regime) * 1.2
```

**Expected Impact:**
- Backtest returns drop 2-5% (more realistic)
- Win rate may drop 3-8% (eliminates marginal winners that fail in reality)
- Max drawdown increases 5-10% (closer to reality)
- **Critical: Prevents strategy deployment that looks profitable in backtest but loses money in production**

**Integration Points:**
1. `trade_simulator.py` - `execute_trade()` function
2. `engine.py` - Call slippage functions on entry/exit
3. Add historical bid-ask data collection (Tiingo provides this)

---

## Priority 2: Bayesian Keyword Confidence Scoring

### Why This Matters
Current keyword scoring is frequentist (requires large samples). Bayesian methods work with **limited data** and naturally handle uncertainty.

### Research-Backed Approach: Beta-Binomial Model

**Formula:**
```
P(Win | Keyword) ~ Beta(α + wins, β + losses)

Win_Rate_Estimate = (wins + α) / (wins + losses + α + β)
Confidence_Interval = Beta quantiles (5th, 95th percentile)
```

**Implementation (3-4 days):**

```python
# src/catalyst_bot/backtesting/bayesian_scoring.py
from scipy.stats import beta

class BayesianKeywordScorer:
    """
    Bayesian keyword effectiveness scoring with Beta-Binomial conjugate priors.

    Research: "Bayesian methods excel for catalyst-driven trading with limited samples."
    """

    def __init__(self, prior_alpha=2.0, prior_beta=2.0):
        """
        Initialize with weak informative prior.

        α=2, β=2 represents: "We think win rate is around 50%,
        but we're not very confident (equivalent to 4 prior observations)"
        """
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.keyword_stats = {}  # {keyword: {wins: int, losses: int}}

    def update_keyword(self, keyword: str, won: bool):
        """Update keyword statistics with new outcome."""
        if keyword not in self.keyword_stats:
            self.keyword_stats[keyword] = {"wins": 0, "losses": 0}

        if won:
            self.keyword_stats[keyword]["wins"] += 1
        else:
            self.keyword_stats[keyword]["losses"] += 1

    def get_confidence_score(self, keyword: str) -> dict:
        """
        Get Bayesian confidence score with credible intervals.

        Returns:
            {
                'mean_win_rate': float,
                'lower_95': float,  # 5th percentile
                'upper_95': float,  # 95th percentile
                'confidence_width': float,  # uncertainty measure
                'sample_size': int
            }
        """
        if keyword not in self.keyword_stats:
            # No data: return prior distribution
            stats = {"wins": 0, "losses": 0}
        else:
            stats = self.keyword_stats[keyword]

        # Posterior parameters
        alpha_post = self.prior_alpha + stats["wins"]
        beta_post = self.prior_beta + stats["losses"]

        # Posterior distribution
        posterior = beta(alpha_post, beta_post)

        mean_win_rate = posterior.mean()
        lower_95 = posterior.ppf(0.05)
        upper_95 = posterior.ppf(0.95)
        confidence_width = upper_95 - lower_95

        return {
            "mean_win_rate": mean_win_rate,
            "lower_95": lower_95,
            "upper_95": upper_95,
            "confidence_width": confidence_width,
            "sample_size": stats["wins"] + stats["losses"],
            "wins": stats["wins"],
            "losses": stats["losses"]
        }

    def get_lift_metric(self, keyword: str, baseline_win_rate: float) -> float:
        """
        Calculate Lift = P(Win|Keyword) / P(Win)

        Lift > 1.2: Strong positive association
        Lift < 0.8: Predicts losses
        Lift ≈ 1.0: No relationship
        """
        conf = self.get_confidence_score(keyword)
        return conf["mean_win_rate"] / max(baseline_win_rate, 0.01)

    def rank_keywords_by_effectiveness(self, min_sample_size=5):
        """
        Rank all keywords by lower confidence bound (conservative).

        Using lower bound ensures we don't over-rely on keywords with
        high win rates but small sample sizes.
        """
        rankings = []
        for keyword in self.keyword_stats:
            conf = self.get_confidence_score(keyword)
            if conf["sample_size"] >= min_sample_size:
                rankings.append({
                    "keyword": keyword,
                    "score": conf["lower_95"],  # Conservative estimate
                    "mean": conf["mean_win_rate"],
                    "samples": conf["sample_size"]
                })

        return sorted(rankings, key=lambda x: x["score"], reverse=True)
```

**Integration with Backtester:**
```python
# In engine.py
scorer = BayesianKeywordScorer()

# After each trade closes
for keyword in trade.keywords:
    scorer.update_keyword(keyword, trade.profit > 0)

# When evaluating new alert
confidence_scores = [
    scorer.get_confidence_score(kw)["lower_95"]  # Conservative
    for kw in alert.keywords
]
combined_confidence = np.mean(confidence_scores)
```

**Expected Impact:**
- Keyword scores update continuously (no batch retraining)
- Small sample keywords get lower confidence (safer)
- Confidence intervals inform position sizing
- Naturally handles exploration-exploitation

---

## Priority 3: Multiple Hypothesis Testing (FDR Correction)

### Why This Matters
Testing 100+ keywords at α=0.05 yields **99.4% chance of false positive**. You're likely finding "significant" keywords that are statistical flukes.

### Benjamini-Hochberg Procedure (2 days)

```python
# src/catalyst_bot/backtesting/hypothesis_testing.py
import numpy as np
from scipy import stats

def benjamini_hochberg_correction(p_values, alpha=0.05):
    """
    Apply Benjamini-Hochberg FDR correction for multiple testing.

    Controls False Discovery Rate (FDR) - acceptable ~5% false discoveries
    vs Bonferroni (too conservative for exploration).

    Args:
        p_values: dict {keyword: p_value}
        alpha: FDR threshold (0.05 = 5% false discovery rate)

    Returns:
        dict {keyword: {'p_value': float, 'significant': bool, 'adjusted_alpha': float}}
    """
    keywords = list(p_values.keys())
    p_vals = [p_values[k] for k in keywords]
    m = len(p_vals)

    # Sort p-values
    sorted_indices = np.argsort(p_vals)
    sorted_p = np.array(p_vals)[sorted_indices]
    sorted_keywords = [keywords[i] for i in sorted_indices]

    # Find largest k where p_k <= (k/m) * alpha
    significant_keywords = set()
    adjusted_alphas = {}

    for k in range(m, 0, -1):
        threshold = (k / m) * alpha
        if sorted_p[k-1] <= threshold:
            # Reject H_1, ..., H_k
            for i in range(k):
                significant_keywords.add(sorted_keywords[i])
                adjusted_alphas[sorted_keywords[i]] = (i+1) / m * alpha
            break

    # Build results
    results = {}
    for keyword in keywords:
        results[keyword] = {
            'p_value': p_values[keyword],
            'significant': keyword in significant_keywords,
            'adjusted_alpha': adjusted_alphas.get(keyword, alpha)
        }

    return results

def calculate_keyword_p_values(keyword_stats, baseline_win_rate=0.50):
    """
    Calculate p-values for keyword effectiveness using proportion test.

    H0: Keyword win rate = baseline win rate
    H1: Keyword win rate != baseline win rate
    """
    p_values = {}

    for keyword, stats in keyword_stats.items():
        wins = stats['wins']
        total = wins + stats['losses']

        if total < 5:  # Skip keywords with too few samples
            continue

        # Two-proportion z-test
        keyword_rate = wins / total
        pooled_p = baseline_win_rate
        pooled_se = np.sqrt(pooled_p * (1 - pooled_p) * (1/total + 1/total))

        z = (keyword_rate - baseline_win_rate) / pooled_se
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))  # Two-tailed

        p_values[keyword] = p_value

    return p_values

def calculate_effect_size_cohens_d(keyword_stats, all_trade_returns):
    """
    Calculate Cohen's d for practical significance.

    d = (Mean_With_Keyword - Mean_Without) / Pooled_SD

    Small: d=0.2, Medium: d=0.5, Large: d=0.8

    A keyword can be statistically significant but have d=0.15 (negligible value).
    Prioritize large effect sizes - they translate to actual profit.
    """
    effect_sizes = {}

    for keyword, stats in keyword_stats.items():
        # Get returns for trades with this keyword
        with_keyword = stats['returns']  # List of returns

        # Get returns for trades without this keyword
        without_keyword = [r for r in all_trade_returns if r not in with_keyword]

        if len(with_keyword) < 5 or len(without_keyword) < 5:
            continue

        mean_with = np.mean(with_keyword)
        mean_without = np.mean(without_keyword)

        # Pooled standard deviation
        sd_with = np.std(with_keyword, ddof=1)
        sd_without = np.std(without_keyword, ddof=1)
        n1, n2 = len(with_keyword), len(without_keyword)
        pooled_sd = np.sqrt(((n1-1)*sd_with**2 + (n2-1)*sd_without**2) / (n1+n2-2))

        cohens_d = (mean_with - mean_without) / pooled_sd

        effect_sizes[keyword] = {
            'd': cohens_d,
            'interpretation': _interpret_effect_size(abs(cohens_d)),
            'mean_with': mean_with,
            'mean_without': mean_without
        }

    return effect_sizes

def _interpret_effect_size(d):
    if d < 0.2:
        return "negligible"
    elif d < 0.5:
        return "small"
    elif d < 0.8:
        return "medium"
    else:
        return "large"
```

**Workflow:**
1. **Exploratory Phase:** BH with FDR=0.10 (find candidates)
2. **Refinement:** BH with FDR=0.05 (validate top keywords)
3. **Final Validation:** Bonferroni on top 5-10 keywords
4. **Out-of-Sample:** Mandatory forward test before production

**Expected Impact:**
- Eliminates 30-50% of "significant" keywords (they were flukes)
- Remaining keywords have genuine predictive power
- Effect size focus = actual profit improvement

---

## Priority 4: Time-Decay Modeling for Catalysts

### Why This Matters
"FDA approval" keyword is predictive **before** the event but worthless 2 weeks after. Current system doesn't decay old catalysts.

### Exponential Decay Implementation (2 days)

```python
# src/catalyst_bot/backtesting/time_decay.py
import numpy as np
from datetime import datetime, timedelta

class CatalystTimeDecay:
    """
    Model catalyst aging with exponential decay.

    Research: "Exponential decay works best for most catalysts"
    Weight(t) = e^(-λt) where t = time since catalyst
    """

    # Research-backed decay rates by catalyst type
    DECAY_RATES = {
        "earnings": 0.30,       # λ=0.30, half-life 2.3 days (fast)
        "fda": 0.15,            # λ=0.15, half-life 4.6 days (moderate-fast)
        "clinical": 0.15,       # Clinical trial results
        "partnership": 0.10,    # λ=0.10, half-life 7 days (moderate)
        "contract": 0.10,
        "approval": 0.15,
        "merger": 0.03,         # λ=0.03, half-life 23 days (slow)
        "acquisition": 0.03,
        "default": 0.10         # Generic catalyst
    }

    def calculate_decay_weight(
        self,
        catalyst_keywords: list,
        catalyst_timestamp: datetime,
        current_timestamp: datetime
    ) -> dict:
        """
        Calculate time-decayed weight for each keyword.

        Returns:
            {
                'total_weight': float,
                'keyword_weights': dict {keyword: weight},
                'hours_elapsed': float
            }
        """
        hours_elapsed = (current_timestamp - catalyst_timestamp).total_seconds() / 3600

        keyword_weights = {}
        for keyword in catalyst_keywords:
            # Determine decay rate based on keyword type
            lambda_rate = self._get_decay_rate(keyword)

            # Exponential decay: e^(-λt)
            weight = np.exp(-lambda_rate * (hours_elapsed / 24))  # Convert hours to days
            keyword_weights[keyword] = weight

        # Multi-keyword attribution (proportional credit)
        total_weight = sum(keyword_weights.values())

        return {
            'total_weight': total_weight,
            'keyword_weights': keyword_weights,
            'hours_elapsed': hours_elapsed,
            'days_elapsed': hours_elapsed / 24
        }

    def _get_decay_rate(self, keyword: str) -> float:
        """Map keyword to decay rate."""
        keyword_lower = keyword.lower()
        for catalyst_type, lambda_rate in self.DECAY_RATES.items():
            if catalyst_type in keyword_lower:
                return lambda_rate
        return self.DECAY_RATES["default"]

    def calculate_multi_catalyst_attribution(
        self,
        catalysts: list,  # [(keywords, timestamp), ...]
        trade_timestamp: datetime
    ) -> dict:
        """
        Attribute credit across multiple catalysts for same trade.

        Credit_i = e^(-λ(T_trade - T_catalyst_i)) / Σⱼ e^(-λ(T_trade - T_catalyst_j))

        Recent catalysts receive highest attribution (normalized to sum=1).
        """
        weights = []
        catalyst_data = []

        for keywords, cat_timestamp in catalysts:
            decay_result = self.calculate_decay_weight(keywords, cat_timestamp, trade_timestamp)
            weights.append(decay_result['total_weight'])
            catalyst_data.append({
                'keywords': keywords,
                'timestamp': cat_timestamp,
                'raw_weight': decay_result['total_weight'],
                'days_old': decay_result['days_elapsed']
            })

        # Normalize to sum=1
        total_weight = sum(weights)
        if total_weight == 0:
            # All catalysts extremely old, equal attribution
            normalized = [1.0 / len(catalysts)] * len(catalysts)
        else:
            normalized = [w / total_weight for w in weights]

        # Assign normalized weights
        for i, catalyst in enumerate(catalyst_data):
            catalyst['attribution_weight'] = normalized[i]

        return {
            'catalysts': catalyst_data,
            'primary_catalyst': catalyst_data[np.argmax(normalized)]
        }
```

**Integration:**
```python
# When updating keyword statistics after trade
decay_model = CatalystTimeDecay()

# Get all catalysts for this ticker in past 30 days
recent_catalysts = get_recent_catalysts(ticker, days=30)

# Calculate attribution
attribution = decay_model.calculate_multi_catalyst_attribution(
    catalysts=[(c.keywords, c.timestamp) for c in recent_catalysts],
    trade_timestamp=trade.exit_time
)

# Update keyword stats with weighted credit
for catalyst in attribution['catalysts']:
    weight = catalyst['attribution_weight']
    for keyword in catalyst['keywords']:
        update_keyword_with_weight(keyword, won=trade.profit > 0, weight=weight)
```

**Expected Impact:**
- Old catalysts don't pollute statistics
- Multi-catalyst trades credit properly attributed
- Adaptive decay rates by catalyst type

---

## Priority 5: PBO (Probability of Backtest Overfitting)

### Why This Matters
**Gold standard** for detecting overfitting. Your CPCV infrastructure provides the foundation, but PBO adds critical validation.

### Implementation (3 days)

```python
# src/catalyst_bot/backtesting/pbo.py
import numpy as np
from itertools import combinations

def calculate_pbo(
    backtest_results: dict,  # {config_id: {split_id: sharpe_ratio}}
    n_configs: int = 100,
    n_splits: int = 6
) -> dict:
    """
    Calculate Probability of Backtest Overfitting (PBO).

    Methodology:
    1. Generate M parameter configurations (M=100+)
    2. Split data into S subperiods (S=6-10)
    3. For each split: find best IS params, rank OOS performance
    4. PBO = Frequency(OOS rank > median)

    Thresholds:
    - PBO < 0.20: Acceptable
    - 0.20-0.50: Moderate concern
    - PBO > 0.50: High overfitting risk

    Args:
        backtest_results: Nested dict of Sharpe ratios

    Returns:
        {
            'pbo': float,
            'interpretation': str,
            'median_oos_rank': float,
            'config_rankings': list
        }
    """
    # For each split, rank configurations by OOS performance
    split_rankings = []

    for split_id in range(n_splits):
        # Get IS and OOS performance for this split
        is_performance = {}
        oos_performance = {}

        for config_id in range(n_configs):
            is_sharpe = backtest_results[config_id][f"split_{split_id}_IS"]
            oos_sharpe = backtest_results[config_id][f"split_{split_id}_OOS"]

            is_performance[config_id] = is_sharpe
            oos_performance[config_id] = oos_sharpe

        # Find best IS configuration
        best_is_config = max(is_performance, key=is_performance.get)

        # Rank this config's OOS performance
        oos_values = sorted(oos_performance.values(), reverse=True)
        rank = oos_values.index(oos_performance[best_is_config]) + 1

        # Normalize rank (1 = best, n_configs = worst)
        normalized_rank = rank / n_configs
        split_rankings.append(normalized_rank)

    # PBO = frequency where OOS rank > median (0.5)
    pbo = np.mean([rank > 0.5 for rank in split_rankings])

    return {
        'pbo': pbo,
        'interpretation': _interpret_pbo(pbo),
        'median_oos_rank': np.median(split_rankings),
        'split_rankings': split_rankings
    }

def _interpret_pbo(pbo: float) -> str:
    if pbo < 0.20:
        return "Low risk - Strategy appears robust"
    elif pbo < 0.50:
        return "Moderate risk - Review parameter stability"
    else:
        return "High risk - Likely overfit, do not deploy"
```

**Expected Impact:**
- Objective overfitting measurement
- Prevents deploying overfit strategies
- Complements existing CPCV

---

## .env Configuration Review for Historical Bootstrap

### ✅ Configuration Status: **READY FOR PRODUCTION**

**Critical Variables (All Present):**
```bash
# API Keys
✅ TIINGO_API_KEY=8fe19137e6f36b25115f848c7d63fc38de4ab35c
✅ FINNHUB_API_KEY=d26q8dhr01qvrairld20d26q8dhr01qvrairld2g
✅ ALPHAVANTAGE_API_KEY=XJ96ZDK4WFJ6ISV8

# Feature Flags
✅ FEATURE_TIINGO=1  # CRITICAL: Enables 20+ years of intraday data
✅ FEATURE_PERSIST_SEEN=1  # Enables events.jsonl logging

# Email (SEC requires User-Agent)
✅ SEC_MONITOR_USER_EMAIL=menzad05@gmail.com

# Data Sources
✅ MARKET_PROVIDER_ORDER=tiingo,av,yf  # Tiingo first (best for historical)
```

**Optional Enhancements:**
```bash
# Add these for better bootstrap performance
BOOTSTRAP_DISCORD_NOTIFICATIONS=1  # Get progress updates
HISTORICAL_BOOTSTRAP_BATCH_SIZE=100  # Default is fine
CACHE_TTL_DAYS=30  # Already set via FLOAT_CACHE_TTL_DAYS
```

**Recommended Bootstrap Command:**
```bash
# 6-12 months of historical data (2024-2025)
python -m catalyst_bot.historical_bootstrapper \
  --start-date 2024-01-01 \
  --end-date 2025-01-01 \
  --sources sec_8k,sec_424b5,sec_fwp,globenewswire_public \
  --batch-size 100 \
  --resume

# This will:
# - Fetch ~500-1000 rejected items
# - Track outcomes across 6 timeframes (15m, 30m, 1h, 4h, 1d, 7d)
# - Use Tiingo for historical intraday data (15m/30m)
# - Cache aggressively to minimize API calls
# - Send Discord progress updates every 15 minutes
# - Support resume if interrupted
```

**Performance Expectations:**
- **Runtime:** 4-8 hours for 12 months (with caching)
- **API Calls:** ~2,000-5,000 (within free tier limits)
- **Disk Usage:** ~200-500 MB (cache)
- **Output:** `data/rejected_items.jsonl` + `data/moa/outcomes.jsonl`

### ⚠️ One Configuration Issue Found

```bash
# Current (line 12)
MIN_SCORE=0.1  # LOOSENED FOR TEST RUN - was 0.2

# Recommendation: Reset for bootstrap
MIN_SCORE=0.20  # Get realistic rejection data
```

**Why:** Historical bootstrap should use **production thresholds** to get accurate rejection data. If MIN_SCORE is too low, you'll have fewer rejections to analyze (the whole point of MOA).

---

## Implementation Roadmap (Production Launch)

### Phase 1: Critical Foundations (1 week)
**Must-Have Before Launch:**

1. **Slippage Modeling** (2 days) - Priority #1
   - Implement bid-ask spread-based slippage
   - Add volume impact calculations
   - Integrate with trade simulator

2. **Bayesian Keyword Scoring** (3 days)
   - Beta-Binomial confidence intervals
   - Lift metrics
   - Integration with confidence scoring

3. **Historical Bootstrap Run** (1-2 days)
   - Reset MIN_SCORE=0.20
   - Run 12-month bootstrap (2024-2025)
   - Validate data quality

**Expected Impact:** Realistic backtests, continuous learning foundation

### Phase 2: Statistical Rigor (1 week)

4. **Multiple Hypothesis Testing** (2 days)
   - Benjamini-Hochberg FDR correction
   - Effect size (Cohen's d)
   - Keyword validation workflow

5. **Time-Decay Modeling** (2 days)
   - Exponential decay by catalyst type
   - Multi-catalyst attribution
   - Integration with keyword updates

6. **PBO Validation** (2 days)
   - Probability of Backtest Overfitting
   - Integration with CPCV
   - Dashboard reporting

**Expected Impact:** Eliminate false positive keywords, proper catalyst aging

### Phase 3: Advanced Learning (2 weeks)

7. **EWMA Adaptive Thresholds** (3-4 days)
   - Online learning for keyword scores
   - Regime-specific parameter sets
   - Feedback loops (MOA + False Positives)

8. **Welford's Incremental Statistics** (3 days)
   - O(1) memory statistics
   - Integration with TimescaleDB
   - Real-time dashboard updates

9. **Keyword Co-occurrence** (4-5 days)
   - Log-Likelihood Ratio testing
   - Network analysis (hubs, communities)
   - Synergy scoring

**Expected Impact:** Continuous adaptation, 15-20% performance improvement

### Phase 4: Production Polish (1 week)

10. **Probabilistic Sharpe Ratio** (2 days)
    - PSR accounting for skewness/kurtosis
    - Deflated Sharpe Ratio (DSR) for multiple testing
    - Benchmark dashboard

11. **Thompson Sampling** (2 days)
    - Exploration-exploitation optimization
    - Beta distributions for parameter configs
    - A/B testing framework

12. **Final Validation** (3 days)
    - 6-month out-of-sample forward test
    - Full walk-forward validation
    - Stress testing with crisis scenarios

**Expected Impact:** Production confidence, optimal parameter exploration

---

## Summary: Top 5 Immediate Actions

### Before Running Historical Bootstrap:
1. **Reset MIN_SCORE=0.20** in .env (from 0.1)
2. **Verify Tiingo API key** works (test market.py)
3. **Clear old cache** (rm -rf data/cache/*)

### For Backtester Production Readiness:
4. **Implement Slippage Modeling** (2 days) - CRITICAL GAP
5. **Run 12-Month Bootstrap** (2024-2025) - Get training data

### After Bootstrap Completes:
6. **Implement Bayesian Scoring** (3 days)
7. **Add FDR Correction** (2 days)
8. **Validate with PBO** (2 days)

**Total Time to Production:** 3-4 weeks (with slippage modeling as #1 priority)

---

## Research Document Highlights Not in patches1.txt

**Advanced Techniques Worth Considering (Post-Launch):**
1. Hidden Markov Models (HMM) - 85-90% regime detection accuracy
2. Singular Spectrum Analysis (SSA) - Better noise reduction than ARIMA
3. Kalman Filtering - Time-varying parameter extraction
4. Trade Reshuffling - Simpler validation than Monte Carlo
5. Numerical Stability for <$1 stocks - Use Decimal types, not floats

**Industry Benchmarks (Realistic Expectations):**
- Win Rate: 45-55% (momentum has lower win rates, larger winners)
- Profit Factor: 1.75+ target (1.5-2.0 acceptable, >3.0 excellent)
- Sharpe Ratio: 0.4-0.8 realistic for small-cap momentum
- Max Drawdown: <20% institutional limit, <30% high risk
- Calmar Ratio: >0.5 target, >1.0 excellent

**Transaction Cost Reality Check:**
- $1-$10 stocks: 0.5-1.0% slippage per trade
- <$1 stocks: 1.0-2.0% slippage per trade
- Exits typically 20% worse than entries
- Low float + high volatility = 2-3x normal slippage

---

**End of Analysis**
