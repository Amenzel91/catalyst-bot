# Technical Indicators Quick Reference
## Catalyst-Bot Implementation Guide

**Date:** 2025-11-26
**Purpose:** Quick lookup for implementing technical indicators in catalyst-driven trading

---

## Top 5 Indicators - At a Glance

| Rank | Indicator | Priority | Score | Primary Use | Timeframe |
|------|-----------|----------|-------|-------------|-----------|
| 1 | RVOL + OBV | CRITICAL | 95/100 | Volume confirmation | Realtime |
| 2 | ATR + Bollinger | HIGH | 88/100 | Volatility/breakout | 5-15 min |
| 3 | RSI | MODERATE | 75/100 | Overbought/oversold filter | 5-15 min |
| 4 | MACD | MODERATE | 72/100 | Momentum confirmation | 15-30 min |
| 5 | Stochastic | LOW | 65/100 | Range-bound (skip) | N/A |

---

## Recommended Parameters for Penny Stocks

### Volume Indicators
```python
RVOL_THRESHOLD = 1.5  # Minimum relative volume
MIN_ABSOLUTE_VOLUME = 500_000  # 500K shares/day minimum
OBV_LOOKBACK = 20  # periods for trend calculation
```

### Volatility Indicators
```python
# Bollinger Bands
BB_PERIOD = 20
BB_STD_DEV = 2.5  # Higher for penny stocks (vs 2.0 standard)
BB_SQUEEZE_THRESHOLD = 0.05  # 5% band width = squeeze

# ATR
ATR_PERIOD = 10  # Faster than standard 14
ATR_SPIKE_THRESHOLD = 1.2  # 20% above 10-period average
```

### Momentum Indicators
```python
# RSI
RSI_PERIOD = 7  # Faster than standard 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_EXTREME_HIGH = 85
RSI_EXTREME_LOW = 20

# MACD (faster settings)
MACD_FAST = 8  # vs standard 12
MACD_SLOW = 17  # vs standard 26
MACD_SIGNAL = 9  # keep standard
```

---

## Chart Timeframes

### Primary Analysis:
- **15-minute:** Best for catalyst reaction time
- **5-minute:** Entry timing refinement
- **1-hour/Daily:** Trend context (avoid counter-trend)

### Multi-Timeframe Strategy:
```python
# 1. Check daily trend (avoid counter-trend trades)
# 2. Identify 1-hour support/resistance
# 3. Confirm 15-min momentum (MACD cross)
# 4. Execute on 5-min volume spike
```

---

## Integration Strategy: Weighted Scoring

### Recommended Approach:
**WEIGHTED SCORING SYSTEM** (not hard filters)

### Formula:
```python
technical_multiplier = (
    volume_score * 0.40 +      # RVOL + OBV
    volatility_score * 0.30 +   # ATR + Bollinger
    momentum_score * 0.20 +     # RSI + MACD
    divergence_penalty * 0.10   # Price/RSI divergence
)

final_score = catalyst_score * technical_multiplier
```

### Score Ranges:
- **0.5** = Very weak technicals (reduce score 50%)
- **1.0** = Neutral (no change)
- **1.5** = Strong technicals (boost score 50%)
- **2.0** = Exceptional (double score)

---

## Critical Failure Modes to Avoid

### 1. Pump and Dump Trap
```python
if (price_surge > 50% and
    rsi > 85 and
    obv_declining and
    not high_quality_catalyst):
    score *= 0.3  # 70% penalty
```

### 2. Illiquid Spike
```python
if total_volume_today < 500_000:
    return False  # Reject even if RVOL high
```

### 3. Late Entry
```python
if (minutes_since_catalyst > 15 and
    price_move > 15%):
    return False  # Too late
```

### 4. Choppy Market
```python
if adx < 20 or price_range_pct < 0.05:
    score *= 0.7  # 30% penalty
```

### 5. Extended Hours Gap
```python
if catalyst_time in [4-9.5 AM ET, 4-8 PM ET]:
    action = 'wait_for_open'  # Don't use indicators
```

---

## Implementation Checklist

### Week 1: Core Development
- [ ] Add `compute_rsi()` to `indicator_utils.py`
- [ ] Add `compute_macd()` to `indicator_utils.py`
- [ ] Add `compute_relative_volume()` to `indicator_utils.py`
- [ ] Create `src/catalyst_bot/technical_scoring.py`
- [ ] Write unit tests for each indicator

### Week 2: Integration
- [ ] Integrate into `runner_impl.py` scoring pipeline
- [ ] Add `.env` configuration: `FEATURE_TECHNICAL_SCORING=1`
- [ ] Implement caching layer (5-minute TTL)
- [ ] Add logging for debugging

### Week 3: Validation
- [ ] Run 30-day backtest vs baseline
- [ ] Analyze false positive reduction (target: 60-70%)
- [ ] Tune weights based on results
- [ ] Document findings

### Week 4: Production
- [ ] Enable in production with monitoring
- [ ] A/B test: 50/50 split
- [ ] Measure win rate improvement (target: +15-30%)
- [ ] Adjust thresholds as needed

---

## Code Snippets

### Basic Technical Score Calculation:
```python
from catalyst_bot.technical_scoring import compute_technical_score

# In event scoring function
ticker = event.get('ticker')
tech_multiplier = compute_technical_score(ticker, timeframe='5m')
final_score = catalyst_score * tech_multiplier
```

### Environment Configuration:
```ini
# .env
FEATURE_TECHNICAL_SCORING=1
TECHNICAL_SCORING_TIMEFRAME=5m
TECHNICAL_WEIGHT_VOLUME=0.40
TECHNICAL_WEIGHT_VOLATILITY=0.30
TECHNICAL_WEIGHT_MOMENTUM=0.20
TECHNICAL_RVOL_STRONG=2.0
TECHNICAL_BB_SQUEEZE_PCT=0.05
TECHNICAL_RSI_PERIOD=7
TECHNICAL_MACD_FAST=8
TECHNICAL_MACD_SLOW=17
```

### Caching for Performance:
```python
from functools import lru_cache
import time

_CACHE: Dict[str, Tuple[float, float]] = {}
_CACHE_TTL = 300  # 5 minutes

def compute_technical_score_cached(ticker: str) -> float:
    cache_key = ticker
    now = time.time()

    if cache_key in _CACHE:
        score, timestamp = _CACHE[cache_key]
        if now - timestamp < _CACHE_TTL:
            return score

    score = compute_technical_score(ticker)
    _CACHE[cache_key] = (score, now)
    return score
```

---

## Expected Performance Improvements

### Metrics:
- **False Positive Reduction:** 60-70%
- **Win Rate Improvement:** +15-30%
- **Alert Quality Score:** +40-50%
- **User Satisfaction:** +25-35%

### Validation Method:
```python
# 30-day backtest comparison
baseline_results = simulate_events(all_events)
technical_results = simulate_events(filtered_events)

improvement = (technical_win_rate - baseline_win_rate)
assert improvement >= 15  # Expect >15% improvement
```

---

## Quick Decision Tree

### Should I trade this catalyst?

1. **Is RVOL > 1.5x?**
   - No → SKIP (70% false positive)
   - Yes → Continue

2. **Is absolute volume > 500K shares?**
   - No → SKIP (illiquid)
   - Yes → Continue

3. **Is Bollinger Band squeezed OR price breaking out?**
   - No → REDUCE score by 20%
   - Yes → Continue

4. **Is ATR rising (>20% above average)?**
   - No → REDUCE score by 15%
   - Yes → Continue

5. **Is RSI showing bearish divergence?**
   - Yes → REDUCE score by 30%
   - No → Continue

6. **Is MACD bullish with expanding histogram?**
   - No → Neutral (1.0x multiplier)
   - Yes → BOOST score by 30%

**Final Action:** If score >= threshold → SEND ALERT

---

## Files to Create/Modify

### New Files:
1. `src/catalyst_bot/technical_scoring.py` (main scoring module)
2. `tests/test_technical_scoring.py` (unit tests)
3. `tests/test_technical_scoring_backtest.py` (validation)

### Modified Files:
1. `src/catalyst_bot/indicator_utils.py` (add RSI, MACD, RVOL)
2. `src/catalyst_bot/runner_impl.py` (integrate scoring)
3. `.env` (add configuration variables)

### Documentation:
1. `research/TECHNICAL_INDICATOR_INTEGRATION_RESEARCH.md` (full report)
2. `research/TECHNICAL_INDICATORS_QUICK_REFERENCE.md` (this file)
3. `docs/TECHNICAL_SCORING_GUIDE.md` (user guide)

---

## Python Libraries Required

### Already Installed:
- pandas >= 2.2
- numpy >= 1.26
- yfinance >= 0.2.40

### Optional (for advanced features):
```bash
pip install pandas-ta  # 130+ indicators
# OR
pip install TA-Lib  # Industry standard (requires C++ compilation)
```

### Current Approach:
Use self-contained implementations in `indicator_utils.py` to avoid external dependencies.

---

## Key Takeaways

1. **Volume is King** - RVOL and OBV are the #1 priority for penny stock catalysts
2. **Use Weighted Scoring** - Don't use hard filters, multiply catalyst scores
3. **Faster Parameters** - Penny stocks need shorter periods (RSI=7, MACD=8/17/9, ATR=10)
4. **Triple Confirmation** - Catalyst + Volume + Volatility = 91% accuracy
5. **Cache Everything** - 5-minute TTL prevents redundant API calls
6. **Fail Safe** - Default to 1.0x neutral multiplier on errors

---

## Contact & Questions

For implementation questions, see:
- Full research report: `research/TECHNICAL_INDICATOR_INTEGRATION_RESEARCH.md`
- Code examples in report Part 6
- Existing implementations: `src/catalyst_bot/indicator_utils.py`

---

**Last Updated:** 2025-11-26
**Version:** 1.0
**Author:** Research Agent 2
