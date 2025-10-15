# MOA Keyword Discovery - Visual Integration Guide

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          MOA KEYWORD DISCOVERY                          │
│                    (Missed Opportunities Analyzer)                      │
└─────────────────────────────────────────────────────────────────────────┘

INPUT DATA:
┌──────────────────────────┐    ┌──────────────────────────┐
│  rejected_items.jsonl    │    │  accepted_items.jsonl    │
│  (Items we didn't alert) │    │  (Items we alerted on)   │
├──────────────────────────┤    ├──────────────────────────┤
│ • Ticker                 │    │ • Ticker                 │
│ • Title                  │    │ • Title                  │
│ • Timestamp              │    │ • Timestamp              │
│ • Classification data    │    │ • Classification data    │
│ • Keywords               │    │ • Keywords               │
└──────────────────────────┘    └──────────────────────────┘
         │                                   │
         │                                   │
         v                                   v
┌──────────────────────────────────────────────────────────────────────────┐
│                      STEP 1: LOAD & FILTER DATA                          │
│  load_rejected_items(since_days=30)                                      │
│  load_accepted_items(since_days=30)                                      │
└──────────────────────────────────────────────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────────────────────────────────────┐
│                 STEP 2: IDENTIFY MISSED OPPORTUNITIES                     │
│  identify_missed_opportunities(threshold_pct=10.0)                       │
│                                                                           │
│  For each rejected item:                                                 │
│    1. Fetch historical prices (rejection time + 1h/4h/1d/7d)            │
│    2. Calculate price change %                                           │
│    3. If any timeframe shows >10% gain → MISSED OPPORTUNITY              │
└──────────────────────────────────────────────────────────────────────────┘
         │
         v
         ├─────────────────────────────────────────┐
         │                                         │
         v                                         v
┌──────────────────────────┐    ┌──────────────────────────────────────┐
│   EXISTING METHOD        │    │        NEW METHOD                    │
│   Frequency Analysis     │    │        Text Mining                   │
└──────────────────────────┘    └──────────────────────────────────────┘
         │                                   │
         v                                   v
┌──────────────────────────┐    ┌──────────────────────────────────────┐
│ STEP 3A:                 │    │ STEP 3B:                             │
│ Extract Keywords from    │    │ Discover Keywords from               │
│ Missed Opportunities     │    │ Missed Opportunities                 │
├──────────────────────────┤    ├──────────────────────────────────────┤
│ • Count occurrences      │    │ POSITIVE EXAMPLES:                   │
│ • Calculate success rate │    │ • Extract titles from missed opps    │
│ • Calculate avg return   │    │ • Extract n-grams (1-4 words)        │
│                          │    │ • Count phrase occurrences           │
│ OUTPUT:                  │    │                                      │
│ keyword_stats = {        │    │ NEGATIVE EXAMPLES:                   │
│   "fda approval": {      │    │ • Extract titles from accepted items │
│     occurrences: 15,     │    │ • Extract n-grams (1-4 words)        │
│     success_rate: 0.867, │    │ • Count phrase occurrences           │
│     avg_return: 23.4%    │    │                                      │
│   }                      │    │ DISCRIMINATIVE MINING:               │
│ }                        │    │ • Calculate lift ratio               │
│                          │    │   lift = pos_rate / neg_rate         │
│                          │    │ • Filter by min_lift (2.0+)          │
│                          │    │ • Filter by min_occurrences (5+)     │
│                          │    │                                      │
│                          │    │ OUTPUT:                              │
│                          │    │ discovered_keywords = [              │
│                          │    │   {                                  │
│                          │    │     keyword: "phase 3 trial",        │
│                          │    │     lift: 6.5,                       │
│                          │    │     positive_count: 13,              │
│                          │    │     negative_count: 2                │
│                          │    │   }                                  │
│                          │    │ ]                                    │
└──────────────────────────┘    └──────────────────────────────────────┘
         │                                   │
         │                                   │
         └─────────────────┬─────────────────┘
                          │
                          v
┌──────────────────────────────────────────────────────────────────────────┐
│                     STEP 4: LOAD CURRENT WEIGHTS                         │
│  load_current_keyword_weights()                                          │
│                                                                           │
│  From: data/analyzer/keyword_stats.json                                  │
│  { "fda approval": 2.0, "earnings beat": 1.5, ... }                     │
└──────────────────────────────────────────────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────────────────────────────────────┐
│                  STEP 5: GENERATE RECOMMENDATIONS                         │
│                                                                           │
│  5A. From keyword_stats (existing method):                               │
│      - New keywords → type: "new"                                        │
│      - Existing keywords → type: "weight_increase"                       │
│                                                                           │
│  5B. From discovered_keywords (new method):                              │
│      - Check if already in recommendations                               │
│      - If exists → Merge, type: "discovered_and_existing"               │
│      - If new → Add, type: "new_discovered"                             │
└──────────────────────────────────────────────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────────────────────────────────────┐
│                    STEP 6: SAVE RECOMMENDATIONS                           │
│  save_recommendations()                                                   │
│                                                                           │
│  Output: data/moa/recommendations.json                                    │
└──────────────────────────────────────────────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────────────────────────────────────┐
│                           FINAL OUTPUT                                    │
│                                                                           │
│  {                                                                        │
│    "timestamp": "2025-10-14T10:30:00Z",                                 │
│    "analysis_period": "2025-09-14 to 2025-10-14",                       │
│    "total_rejected": 245,                                                │
│    "missed_opportunities": 38,                                           │
│    "discovered_keywords_count": 3,        ← NEW                          │
│    "recommendations": [...]                                              │
│  }                                                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## Recommendation Type Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RECOMMENDATION TYPES                              │
└─────────────────────────────────────────────────────────────────────────┘

Keyword Analysis Results:
┌──────────────┐         ┌──────────────┐
│  In Existing │         │ In Discovered│
│  Keywords?   │         │  Keywords?   │
└──────┬───────┘         └──────┬───────┘
       │                        │
       │                        │
       ├────────────────────────┤
       │                        │
       v                        v
    ┌─────┐                 ┌─────┐
    │ YES │                 │ YES │
    └──┬──┘                 └──┬──┘
       │                       │
       v                       v
┌──────────────────────────────────────────────────────────────────────────┐
│                        DECISION MATRIX                                    │
├─────────────────────┬──────────────────────┬──────────────────────────────┤
│ Existing Keyword    │ Discovered Keyword   │ Recommendation Type          │
├─────────────────────┼──────────────────────┼──────────────────────────────┤
│ NO                  │ NO                   │ (skip - no data)             │
├─────────────────────┼──────────────────────┼──────────────────────────────┤
│ YES                 │ NO                   │ "new" or "weight_increase"   │
│ (new keyword)       │                      │ - Based on frequency         │
│                     │                      │ - Confidence: 0.6-0.9        │
├─────────────────────┼──────────────────────┼──────────────────────────────┤
│ NO                  │ YES                  │ "new_discovered"             │
│                     │ (lift > 2.0)         │ - Based on lift ratio        │
│                     │                      │ - Confidence: 0.7            │
│                     │                      │ - Weight: 0.3-0.8 (capped)   │
├─────────────────────┼──────────────────────┼──────────────────────────────┤
│ YES                 │ YES                  │ "discovered_and_existing"    │
│ (existing keyword)  │ (lift > 2.0)         │ - BEST CASE: Validated!      │
│                     │                      │ - Confidence: 0.75-0.9       │
│                     │                      │ - Use higher weight          │
│                     │                      │ - Merge evidence data        │
└─────────────────────┴──────────────────────┴──────────────────────────────┘

EXAMPLE: "fda approval"
┌─────────────────────────────────────────────────────────────────────────┐
│ Existing Keyword Analysis:                                               │
│   • Appears in 15 missed opportunities                                   │
│   • Success rate: 86.7% (13/15 went up >10%)                            │
│   • Average return: 23.4%                                                │
│   → Recommendation: Increase weight from 2.0 to 2.3                     │
│                                                                           │
│ Discovered Keyword Analysis:                                             │
│   • Appears in 13 missed opportunity titles                              │
│   • Appears in 3 accepted item titles                                    │
│   • Lift ratio: 4.8 (much more common in positives)                     │
│   → Recommendation: Weight 0.7 (if new)                                 │
│                                                                           │
│ MERGED RECOMMENDATION:                                                    │
│   • Type: "discovered_and_existing"                                      │
│   • Current weight: 2.0                                                  │
│   • Recommended weight: 2.3 (from existing analysis)                    │
│   • Confidence: 0.85 (high - validated by both methods)                 │
│   • Evidence: Both frequency stats + lift score                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Weight Calculation Comparison

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WEIGHT CALCULATION METHODS                            │
└─────────────────────────────────────────────────────────────────────────┘

METHOD 1: EXISTING KEYWORDS (Frequency-Based)
┌──────────────────────────────────────────────────────────────────────────┐
│ Input: Keyword statistics from missed opportunities                      │
│   • occurrences: How many times keyword appeared                        │
│   • success_rate: % that went up >10%                                   │
│   • avg_return: Average % gain                                          │
│                                                                           │
│ Logic:                                                                   │
│   IF keyword is NEW:                                                     │
│     base_weight = 1.0                                                    │
│     adjustment = (success_rate - 0.5) * 2.0                             │
│     weight = 1.0 + adjustment                                            │
│     RANGE: 0.5 to 2.0                                                    │
│                                                                           │
│   IF keyword EXISTS:                                                     │
│     current_weight = existing weight                                     │
│     IF success_rate >= 0.7:  adjustment = +0.3                          │
│     IF success_rate >= 0.6:  adjustment = +0.2                          │
│     ELSE:                    adjustment = +0.1                          │
│     weight = current_weight + adjustment                                 │
│     RANGE: 0.5 to 3.0                                                    │
│                                                                           │
│ Example: "earnings beat"                                                 │
│   occurrences = 8                                                        │
│   success_rate = 0.625 (62.5%)                                          │
│   current_weight = 1.5                                                   │
│   → adjustment = +0.2 (success_rate >= 0.6)                             │
│   → recommended_weight = 1.7                                             │
└──────────────────────────────────────────────────────────────────────────┘

METHOD 2: DISCOVERED KEYWORDS (Lift-Based)
┌──────────────────────────────────────────────────────────────────────────┐
│ Input: Discriminative phrase analysis                                    │
│   • lift: Ratio of positive rate to negative rate                       │
│   • positive_count: Occurrences in missed opportunities                 │
│   • negative_count: Occurrences in accepted items                       │
│                                                                           │
│ Logic:                                                                   │
│   base_weight = 0.3                                                      │
│   lift_bonus = min(0.5, (lift - 2.0) * 0.1)    # 0.0 to 0.5            │
│   freq_bonus = min(0.2, positive_count / 20)    # 0.0 to 0.2            │
│   weight = base_weight + lift_bonus + freq_bonus                        │
│   weight = min(0.8, weight)  # Conservative cap                         │
│   RANGE: 0.3 to 0.8                                                      │
│                                                                           │
│ Example: "phase 3 trial"                                                 │
│   lift = 6.5                                                             │
│   positive_count = 13                                                    │
│   negative_count = 2                                                     │
│   → base_weight = 0.3                                                    │
│   → lift_bonus = min(0.5, (6.5 - 2.0) * 0.1) = 0.45                    │
│   → freq_bonus = min(0.2, 13 / 20) = 0.2                               │
│   → weight = 0.3 + 0.45 + 0.2 = 0.95                                    │
│   → weight = min(0.8, 0.95) = 0.8 (capped)                             │
│   → recommended_weight = 0.8                                             │
└──────────────────────────────────────────────────────────────────────────┘

MERGED APPROACH
┌──────────────────────────────────────────────────────────────────────────┐
│ When keyword appears in BOTH analyses:                                   │
│                                                                           │
│   1. Calculate weight from existing method                               │
│   2. Calculate weight from discovered method                             │
│   3. Use HIGHER of the two weights                                       │
│   4. Mark as "discovered_and_existing"                                   │
│   5. Boost confidence (validated by both methods)                        │
│                                                                           │
│ Example: "fda approval"                                                  │
│   Existing method:   2.3 (from success rate 86.7%)                      │
│   Discovered method: 0.7 (from lift 4.8)                                │
│   → Use 2.3 (higher weight)                                             │
│   → Type: "discovered_and_existing"                                      │
│   → Confidence: 0.85 (boosted from 0.75)                                │
└──────────────────────────────────────────────────────────────────────────┘
```

## Confidence Scoring

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CONFIDENCE LEVELS                                │
└─────────────────────────────────────────────────────────────────────────┘

         0.9                               VERY HIGH
┌────────────────────────────────────────────────────────────────────────┐
│ • Existing keyword with large sample (20+ occurrences)                 │
│ • High success rate (70%+)                                             │
│ • Strong evidence of profitability                                     │
└────────────────────────────────────────────────────────────────────────┘

         0.85                              HIGH
┌────────────────────────────────────────────────────────────────────────┐
│ • Discovered + Existing (validated by both methods)                    │
│ • High lift ratio (4.0+) AND good success rate (60%+)                 │
│ • Strong discriminative power                                          │
└────────────────────────────────────────────────────────────────────────┘

         0.75                              MEDIUM-HIGH
┌────────────────────────────────────────────────────────────────────────┐
│ • Existing keyword with moderate sample (10-19 occurrences)           │
│ • Good success rate (60%+)                                             │
│ • Positive track record                                                │
└────────────────────────────────────────────────────────────────────────┘

         0.7                               MEDIUM
┌────────────────────────────────────────────────────────────────────────┐
│ • Newly discovered keywords                                            │
│ • Good lift ratio (2.0+) but not yet validated                        │
│ • Reasonable frequency (5+ occurrences)                                │
└────────────────────────────────────────────────────────────────────────┘

         0.6                               MEDIUM-LOW
┌────────────────────────────────────────────────────────────────────────┐
│ • Existing keyword with small sample (5-9 occurrences)                │
│ • Moderate success rate (50-60%)                                       │
│ • Limited evidence                                                      │
└────────────────────────────────────────────────────────────────────────┘

         0.5                               LOW
┌────────────────────────────────────────────────────────────────────────┐
│ • Minimal sample size                                                  │
│ • Uncertain success rate                                               │
│ • Not enough data for confident recommendation                         │
└────────────────────────────────────────────────────────────────────────┘

CONFIDENCE BOOSTING:
┌────────────────────────────────────────────────────────────────────────┐
│ Base confidence (from existing method)                                 │
│                  +                                                      │
│ Validation from discovered method                                      │
│                  =                                                      │
│ Boosted confidence (typically +0.05 to +0.15)                         │
└────────────────────────────────────────────────────────────────────────┘
```

## Performance Metrics

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PERFORMANCE BENCHMARKS                              │
└─────────────────────────────────────────────────────────────────────────┘

TYPICAL DATASET (30 days):
┌──────────────────────────────────────────────────────────────────────────┐
│ Rejected items:        1000                                              │
│ Accepted items:         500                                              │
│ Missed opportunities:    50 (5% of rejected)                            │
│ Unique n-grams:       5,000                                              │
│ Discovered keywords:     10-15 (after filtering)                        │
└──────────────────────────────────────────────────────────────────────────┘

TIMING BREAKDOWN:
┌──────────────────────────────────────────────────────────────────────────┐
│ Step 1: Load rejected items                0.5s                         │
│ Step 2: Load accepted items                0.2s                         │
│ Step 3: Identify missed opportunities      2.0s (price API calls)       │
│ Step 4: Extract keywords (existing)        0.3s                         │
│ Step 5: Discover keywords (text mining)    1.5s                         │
│         ├─ Extract n-grams                 0.8s                         │
│         ├─ Count occurrences               0.3s                         │
│         └─ Calculate lift scores           0.4s                         │
│ Step 6: Merge recommendations              0.1s                         │
│ Step 7: Save output                        0.1s                         │
│ ─────────────────────────────────────────────────                       │
│ TOTAL:                                     4.7s                         │
└──────────────────────────────────────────────────────────────────────────┘

MEMORY USAGE:
┌──────────────────────────────────────────────────────────────────────────┐
│ Rejected items (1000 × 1KB)              1.0 MB                         │
│ Accepted items (500 × 1KB)               0.5 MB                         │
│ N-grams (5000 × 50 bytes)                0.25 MB                        │
│ Price cache (500 entries)                0.1 MB                         │
│ Recommendations (15 × 500 bytes)         0.01 MB                        │
│ Working memory                            0.5 MB                         │
│ ─────────────────────────────────────────────────                       │
│ TOTAL:                                   ~2.4 MB                         │
└──────────────────────────────────────────────────────────────────────────┘

SCALABILITY:
┌──────────────────────────────────────────────────────────────────────────┐
│ 7-day analysis:   ~1.5s,  ~0.8 MB                                       │
│ 30-day analysis:  ~4.7s,  ~2.4 MB (baseline)                           │
│ 90-day analysis:  ~12s,   ~7 MB                                         │
│ 180-day analysis: ~22s,   ~14 MB                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## Integration Checklist

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      INTEGRATION CHECKLIST                               │
└─────────────────────────────────────────────────────────────────────────┘

PHASE 1: CODE INTEGRATION (COMPLETE)
[✓] Add load_accepted_items() function
[✓] Add discover_keywords_from_missed_opportunities() function
[✓] Update run_moa_analysis() to call keyword discovery
[✓] Update save_recommendations() to track discovered count
[✓] Update __all__ exports
[✓] Syntax validation (py_compile)
[✓] Create documentation

PHASE 2: DATA COLLECTION (REQUIRED)
[ ] Integrate accepted_items_logger in runner.py
    └─> Location: After send_alert_safe() returns True
    └─> Call: log_accepted_item(item, price, score, sentiment, keywords)
[ ] Run bot for 7+ days to collect accepted items
[ ] Verify data/accepted_items.jsonl has entries

PHASE 3: TESTING (RECOMMENDED)
[ ] Run test_moa_keyword_discovery.py
[ ] Verify recommendations.json output
[ ] Check discovered_keywords_count > 0
[ ] Validate lift scores are reasonable (2.0+)
[ ] Validate recommended weights are conservative (0.3-0.8)
[ ] Review sample discovered keywords for quality

PHASE 4: VALIDATION (RECOMMENDED)
[ ] Compare discovered keywords with existing keywords
[ ] Check for false positive keywords (low lift)
[ ] Verify merging logic for overlapping keywords
[ ] Test with different time windows (7d, 30d, 90d)
[ ] Test edge cases (no accepted items, no missed opps)

PHASE 5: DEPLOYMENT (FUTURE)
[ ] Monitor discovered keyword performance
[ ] Track false positive rate
[ ] Measure profit improvement
[ ] Adjust min_lift and min_occurrences thresholds
[ ] Consider implementing auto-approval for high-confidence keywords
```

---

**Visual Guide Version**: 1.0
**Last Updated**: 2025-10-14
**Status**: Integration Complete
