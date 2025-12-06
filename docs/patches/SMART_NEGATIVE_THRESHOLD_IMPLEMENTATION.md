# Smart Negative Score Threshold Implementation

## Summary

Implemented dual threshold logic to ensure strong negative catalysts ALWAYS alert, regardless of MIN_SCORE threshold. This prevents important negative events (dilution, bankruptcy, etc.) from being filtered out when score adjustments push them below the threshold.

## Problem Statement

- MIN_SCORE=0.20 was blocking weak negatives (desired)
- However, strong negative catalysts were also being blocked if score adjustments (e.g., divergence penalty) pushed them below threshold
- Example: ELBM with score 0.386 after -0.100 divergence adjustment = 0.286, but should have alerted as negative

## Solution: Dual Threshold System

### Positive Alerts
- Must meet MIN_SCORE >= 0.20 (unchanged)

### Strong Negative Alerts
Alert if **EITHER**:
1. **Strong negative sentiment:** sentiment < -0.30
2. **Critical negative keywords:** Contains any of:
   - "dilution", "offering", "warrant", "delisting", "bankruptcy"
   - "trial failed", "fda rejected", "lawsuit"
   - "going concern", "chapter 11", "restructuring"
   - "default", "insolvent"

## Implementation Details

### File Modified
`src/catalyst_bot/runner.py`

### Changes Made

#### 1. Added Counter Tracking (Line 1124)
```python
strong_negatives_bypassed = 0
```

#### 2. Smart Threshold Logic (Lines 1549-1613)
```python
# Extract score and sentiment
scr = _score_of(scored)
snt = _sentiment_of(scored)

# Smart negative threshold: Strong negative catalysts bypass MIN_SCORE
is_strong_negative = False

# Check 1: Strong negative sentiment (< -0.30)
if snt < -0.30:
    is_strong_negative = True
    log.info(
        "strong_negative_detected ticker=%s sentiment=%.3f reason=strong_sentiment",
        ticker, snt
    )

# Check 2: Critical negative keywords (always alert)
if not is_strong_negative:
    critical_negative_keywords = [
        "dilution", "offering", "warrant", "delisting", "bankruptcy",
        "trial failed", "fda rejected", "lawsuit", "going concern",
        "chapter 11", "restructuring", "default", "insolvent"
    ]

    title_lower = (it.get("title") or "").lower()
    summary_lower = (it.get("summary") or "").lower()
    combined_text = f"{title_lower} {summary_lower}"

    for keyword in critical_negative_keywords:
        if keyword in combined_text:
            is_strong_negative = True
            log.info(
                "strong_negative_detected ticker=%s keyword='%s' reason=critical_keyword",
                ticker, keyword
            )
            break

# Apply dual threshold logic
if (min_score is not None) and (scr < min_score):
    if is_strong_negative:
        # Bypass MIN_SCORE for strong negatives
        strong_negatives_bypassed += 1
        log.info(
            "min_score_bypassed ticker=%s score=%.3f sentiment=%.3f reason=strong_negative",
            ticker, scr, snt
        )
        # Continue processing (don't skip)
    else:
        # Normal low score skip
        skipped_low_score += 1
        # ... log rejection ...
        continue
```

#### 3. Sentiment Gate Bypass (Lines 1615-1641)
Strong negatives also bypass the MIN_SENT_ABS gate for consistency:
```python
if (min_sent_abs is not None) and (abs(snt) < min_sent_abs):
    if is_strong_negative:
        # Strong negatives can also bypass sentiment gate (though typically not needed)
        log.info(
            "sent_gate_bypassed ticker=%s abs_sentiment=%.3f reason=strong_negative",
            ticker, abs(snt)
        )
        # Continue processing (don't skip)
    else:
        skipped_sent_gate += 1
        # ... log rejection ...
        continue
```

**Note:** This bypass is more for consistency than necessity, since strong negatives (sentiment < -0.30) naturally have high absolute sentiment (> 0.30) and typically pass MIN_SENT_ABS anyway.

#### 4. Updated Metrics Logging (Line 1829)
Added `strong_negatives_bypassed=%s` to cycle_metrics log output.

## Monitoring

### Log Messages to Watch

1. **Detection:**
   ```
   strong_negative_detected ticker=AAPL sentiment=-0.450 reason=strong_sentiment
   strong_negative_detected ticker=DFLI keyword='dilution' reason=critical_keyword
   ```

2. **Bypass:**
   ```
   min_score_bypassed ticker=AAPL score=0.150 sentiment=-0.450 reason=strong_negative
   sent_gate_bypassed ticker=DFLI abs_sentiment=0.250 reason=strong_negative
   ```

3. **Cycle Metrics:**
   ```
   cycle_metrics ... strong_negatives_bypassed=3 alerted=15
   ```

### Expected Behavior

| Scenario | Score | Sentiment | Keywords | Result |
|----------|-------|-----------|----------|--------|
| Weak negative | 0.12 | -0.08 | None | SKIP (below MIN_SCORE) |
| Strong negative sentiment | 0.15 | -0.45 | None | **ALERT** (bypassed) |
| Dilution news | 0.18 | -0.15 | "offering" | **ALERT** (bypassed) |
| Positive news | 0.18 | +0.50 | None | SKIP (below MIN_SCORE) |
| Strong positive | 0.85 | +0.70 | None | ALERT (above MIN_SCORE) |

## Testing

### Test Script
Created `test_negative_threshold_bypass.py` demonstrating:
- Strong negative sentiment bypass
- Critical keyword bypass
- Normal weak negative (properly skipped)
- ELBM case analysis

### Run Test
```bash
python test_negative_threshold_bypass.py
```

### Expected Output
All test cases should show correct bypass/skip behavior.

## Integration Notes

### Negative Alert Format
Strong negatives that bypass will automatically use:
- Red embed color (already exists in `alerts.py` for FEATURE_NEGATIVE_ALERTS)
- Warning emoji in title
- Integrates with existing negative alert infrastructure

### No Breaking Changes
- Positive alerts: Unchanged (still require MIN_SCORE >= 0.20)
- Normal weak negatives: Unchanged (still filtered)
- Strong negatives: NEW behavior (now bypass MIN_SCORE)

## ELBM Case Analysis

The ELBM example from the task:
- Score: 0.386 after -0.100 divergence = 0.286
- Sentiment: -0.25 (estimated from divergence)
- Title: "Electrum Special Acquisition Reports Strong Business Update"

**Result:** Would NOT bypass with current thresholds because:
- Sentiment -0.25 is not < -0.30 threshold
- No critical keywords present
- This suggests the divergence penalty may have been too aggressive

**Recommendation:** If ELBM-type cases should alert, consider:
1. Lowering sentiment threshold to -0.20 (from -0.30)
2. Adding "divergence" as a critical keyword
3. Reviewing divergence penalty calculation

## Next Steps

1. **Monitor logs** for strong_negative_detected and min_score_bypassed
2. **Track metrics** to see how many negatives are bypassing
3. **Review bypassed alerts** to ensure quality (not too noisy)
4. **Tune thresholds** if needed:
   - Sentiment threshold: Currently -0.30, could adjust to -0.20/-0.25
   - Keywords: Add/remove based on false positives

## Files Changed
- `src/catalyst_bot/runner.py` (modified)
- `test_negative_threshold_bypass.py` (created)
- `SMART_NEGATIVE_THRESHOLD_IMPLEMENTATION.md` (this file)

## Code Quality
- All changes syntax-checked with `python -m py_compile`
- Integrated with existing MOA logging infrastructure
- No breaking changes to existing filters
- Comprehensive logging for monitoring and debugging
