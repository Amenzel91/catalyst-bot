# Keyword Discovery Guide
## How to Find and Add New Keywords to Increase Alert Coverage

**Problem**: The bot only alerts on news stories containing keywords from `config.py`. More keywords = more stories detected = more profitable opportunities.

**Solution**: This guide shows you 3 proven methods to discover high-value keywords systematically.

---

## Table of Contents

1. [How the Keyword System Works](#how-the-keyword-system-works)
2. [Method 1: Extract from Historical Missed Opportunities (MOA Data)](#method-1-extract-from-historical-missed-opportunities)
3. [Method 2: LLM Analysis of SEC Filings](#method-2-llm-analysis-of-sec-filings)
4. [Method 3: Manual Pattern Recognition](#method-3-manual-pattern-recognition)
5. [Adding Keywords to Config](#adding-keywords-to-config)
6. [Testing New Keywords](#testing-new-keywords)
7. [Keyword Weight Optimization](#keyword-weight-optimization)

---

## How the Keyword System Works

### Current Architecture

The bot scores news items using keyword matching:

```python
# From config.py (lines 371-520)
keyword_categories = {
    "fda": ["fda approval", "fda clearance", "510(k)"],
    "partnership": ["partnership", "collaboration", "licensing"],
    "merger": ["merger", "acquisition", "buyout"],
    # ... 30+ categories
}
```

### Scoring Flow (classify.py:610-630)

```python
for category, keywords in keyword_categories.items():
    for kw in keywords:
        if kw in combined_text:  # Checks title + summary
            weight = dynamic_weights.get(category, 0.50)  # Default 0.50
            total_keyword_score += weight
            break  # Max 1 hit per category
```

**Key Insights**:
- Keywords are case-insensitive and checked against title + summary
- Each category contributes at most once to the score
- More categories = higher potential scores = more alerts

---

## Method 1: Extract from Historical Missed Opportunities

### Step 1: Enable Rejected Items Logging

**File**: `src/catalyst_bot/feeds.py` (around line 450)

Add this code after rejection logging:

```python
# After this line:
log.info("price_ceiling_reject ticker=%s price=%.2f ceiling=%.2f", ...)

# Add rejected items logger:
from .rejected_items_logger import log_rejected_item

log_rejected_item(
    ticker=item.ticker,
    title=item.title,
    summary=getattr(item, "summary", ""),
    source=getattr(item, "source", ""),
    rejection_reason="HIGH_PRICE",
    rejection_ts=item.published_time,
    price=price,
)
```

Repeat for all rejection points:
- `HIGH_PRICE` rejection (~70% of rejections)
- `LOW_SCORE` rejection (~29% of rejections)
- `LOW_PRICE` rejection (~0.5% of rejections)

### Step 2: Run Historical Bootstrap

Collect 12 months of rejected items with outcomes:

```bash
.venv/Scripts/python -m catalyst_bot.historical_bootstrapper \
    --start-date 2024-10-16 \
    --end-date 2025-10-15 \
    --sources sec_8k,sec_424b5,sec_fwp,globenewswire_public,prnewswire \
    --batch-size 50 \
    --resume
```

**Output**: `data/moa/outcomes.jsonl` (3,000+ outcomes with profitability data)

### Step 3: Extract Keywords from Missed Opportunities

```bash
python extract_moa_keywords.py
```

**Output**:
```
=============================================================================
MISSED OPPORTUNITY KEYWORD ANALYSIS
=============================================================================

1. TOP KEYWORDS BY FREQUENCY
-----------------------------------------------------------------------------
Keyword                                       Count   Avg Return   Med Return
-----------------------------------------------------------------------------
fda approval                                     42      127.3%        38.2%
partnership agreement                            38       84.5%        22.1%
drilling results                                 27      312.4%       145.2%
uplisting                                        24       91.2%        45.8%
gene therapy                                     19      156.3%        67.4%
patent granted                                   17       73.8%        31.5%

2. KEYWORDS WITH HIGHEST AVERAGE RETURNS (min 5 occurrences)
-----------------------------------------------------------------------------
Keyword                                       Count   Avg Return   Max Return
-----------------------------------------------------------------------------
drilling results                                 27      312.4%     1,842.1%
oil discovery                                    12      428.7%     2,104.5%
gas discovery                                     9      385.2%     1,623.8%
fast track designation                           14      203.1%       847.3%
breakthrough therapy                              8      189.4%       623.2%
```

### Step 4: Compare to Existing Keywords

Check if discovered keywords already exist in `config.py`:

```bash
# Quick check
grep -i "drilling results" src/catalyst_bot/config.py
# No results = NEW KEYWORD TO ADD
```

---

## Method 2: LLM Analysis of SEC Filings

### The Power of SEC LLM Keyword Extraction

Your bot already has this feature! It uses Gemini/Claude to extract catalysts from SEC 8-K filings.

**File**: `src/catalyst_bot/sec_llm_analyzer.py`

### Step 1: Enable Feature and Monitor Output

```bash
# .env
FEATURE_SEC_LLM_KEYWORDS=1
```

### Step 2: Collect LLM Suggestions

The LLM identifies catalysts in SEC filings. Monitor logs for patterns:

```
sec_llm_keywords ticker=ABCD keywords="FDA approval, Phase 3 trial, clinical endpoint"
sec_llm_keywords ticker=EFGH keywords="M&A transaction, strategic buyer, earnout provision"
sec_llm_keywords ticker=IJKL keywords="oil well completion, reserves expansion, production ramp"
```

### Step 3: Extract Unique Phrases

Create a script to extract and count LLM-suggested keywords:

```python
#!/usr/bin/env python3
"""Extract LLM keyword suggestions from bot logs."""
import re
from collections import Counter

# Read bot.jsonl logs
keywords = Counter()
with open("data/logs/bot.jsonl", "r") as f:
    for line in f:
        if "sec_llm_keywords" in line:
            # Extract keywords="..." portion
            match = re.search(r'keywords="([^"]+)"', line)
            if match:
                kws = match.group(1).split(", ")
                keywords.update(kws)

# Print top 50 suggested keywords
for keyword, count in keywords.most_common(50):
    print(f"{keyword:<50} {count:>5}x")
```

**Output**:
```
FDA approval                                        127x
partnership agreement                               104x
clinical trial results                               89x
merger agreement                                     76x
uplisting notification                               62x
```

### Step 4: Add High-Frequency Keywords

Keywords appearing 10+ times across different filings are strong candidates for addition.

---

## Method 3: Manual Pattern Recognition

### Analyze Successful Alerts

Look at your `data/events.jsonl` file for alerts that led to big price moves:

```python
#!/usr/bin/env python3
"""Find keywords in successful alerts."""
import json

successes = []
with open("data/events.jsonl", "r") as f:
    for line in f:
        event = json.loads(line)
        # Assume you track price outcomes manually
        if event.get("max_return_pct", 0) > 50:
            successes.append(event)

# Extract common phrases
from collections import Counter

phrases = Counter()
for event in successes:
    title = event.get("title", "").lower()
    # Extract 2-3 word phrases
    words = title.split()
    for i in range(len(words) - 2):
        phrase = " ".join(words[i:i+3])
        phrases[phrase] += 1

# Print top phrases
for phrase, count in phrases.most_common(30):
    print(f"{phrase:<50} {count:>3}x")
```

### Industry Research

**Biotech Keywords** (from FDA.gov news):
- accelerated approval
- orphan drug designation
- rare disease
- biologics license application (BLA)
- new drug application (NDA)
- compassionate use
- expanded access
- adaptive trial design

**Energy Keywords** (from industry publications):
- proved reserves
- probable reserves
- horizontal drilling
- unconventional resources
- field development plan
- enhanced oil recovery
- upstream operations
- midstream assets

**Technology Keywords** (from tech news):
- cloud migration
- SaaS platform
- API integration
- machine learning deployment
- cybersecurity framework
- intellectual property portfolio

---

## Adding Keywords to Config

### File Location

`src/catalyst_bot/config.py` (lines 371-520)

### Step-by-Step Process

#### 1. Choose Appropriate Category

```python
keyword_categories = {
    # Clinical/Regulatory (biotech/pharma)
    "fda": [...],
    "clinical": [...],

    # Business Development
    "partnership": [...],
    "merger": [...],

    # Financial Events
    "uplisting": [...],
    "earnings": [...],

    # Sector-Specific
    "energy": [...],  # May need to create
    "tech": [...],    # May need to create
}
```

#### 2. Add Keywords to Existing Category

```python
# BEFORE
"fda": ["fda approval", "fda clearance", "510(k)"],

# AFTER
"fda": [
    "fda approval",
    "fda clearance",
    "510(k)",
    "fast track designation",      # NEW
    "breakthrough therapy",          # NEW
    "orphan drug designation",       # NEW
    "accelerated approval pathway",  # NEW
],
```

#### 3. Create New Category (if needed)

```python
# For energy sector catalysts
"energy_discovery": [
    "oil discovery",
    "gas discovery",
    "drilling results",
    "reserves expansion",
    "well completion",
    "production increase",
    "field development",
],
```

#### 4. Update .env with Weight (optional)

```bash
# .env
KEYWORD_WEIGHT_ENERGY_DISCOVERY=0.65  # Higher weight for proven catalysts
```

---

## Testing New Keywords

### Method 1: Dry Run with Historical Data

```bash
# Test on last 7 days without posting to Discord
FEATURE_RECORD_ONLY=1 .venv/Scripts/python -m catalyst_bot.runner --once
```

**Check Logs**:
```bash
grep "keyword_hit" data/logs/bot.jsonl | grep "energy_discovery"
```

**Expected Output**:
```
keyword_hit category=energy_discovery keyword="drilling results" ticker=XYZ score=0.65
keyword_hit category=energy_discovery keyword="oil discovery" ticker=ABC score=0.65
```

### Method 2: Backtest Against Historical Outcomes

```bash
# Run backtester with new keywords enabled
.venv/Scripts/python -m catalyst_bot.backtesting.engine \
    --start 2024-10-01 \
    --end 2025-10-01 \
    --output backtest_new_keywords.json
```

**Compare Results**:
```python
# Load old vs new backtest results
import json

old = json.load(open("backtest_baseline.json"))
new = json.load(open("backtest_new_keywords.json"))

print(f"Old: {old['total_alerts']} alerts, {old['hit_rate']:.1f}% hit rate")
print(f"New: {new['total_alerts']} alerts, {new['hit_rate']:.1f}% hit rate")
print(f"Additional alerts: {new['total_alerts'] - old['total_alerts']}")
```

### Method 3: A/B Test in Production

Run two instances side-by-side:

```bash
# Instance A: Baseline (old keywords)
DISCORD_WEBHOOK_URL=<webhook-a> python -m catalyst_bot.runner

# Instance B: New keywords
DISCORD_WEBHOOK_URL=<webhook-b> python -m catalyst_bot.runner
```

Track which webhook generates better returns over 1-2 weeks.

---

## Keyword Weight Optimization

### Default Weights

```python
# config.py
keyword_default_weight = 0.50  # Most categories
```

### When to Increase Weight

**Criteria for high weights (0.70-1.00)**:
1. **High Hit Rate**: Keyword appears in >60% of profitable alerts
2. **High Return**: Average return >100% when keyword present
3. **Low False Positives**: <20% of alerts with keyword fail to move

**Example** (from MOA data):
```
Keyword: "drilling results"
- Hit rate: 84% (27/32 alerts profitable)
- Avg return: 312.4%
- False positive rate: 16%

RECOMMENDATION: Increase weight from 0.50 → 0.85
```

### When to Decrease Weight

**Criteria for low weights (0.20-0.40)**:
1. **High False Positives**: >40% of alerts fail to move
2. **Low Return**: Average return <20%
3. **Noise Words**: Appears in many non-catalyst stories

**Example**:
```
Keyword: "business update"
- Hit rate: 31% (12/39 alerts profitable)
- Avg return: 8.2%
- False positive rate: 69%

RECOMMENDATION: Decrease weight from 0.50 → 0.25 OR REMOVE
```

### Dynamic Weight Updates

The bot supports analyzer-driven weight optimization:

```bash
# Run nightly analyzer to auto-tune weights
.venv/Scripts/python -m catalyst_bot.scripts.nightly_analyzer
```

**Output**: `data/analyzer/keyword_stats.json`

```json
{
  "weights": {
    "fda": 0.75,              // Increased (high hit rate)
    "clinical": 0.68,
    "partnership": 0.55,
    "energy_discovery": 0.85,  // Increased (312% avg return)
    "merger": 0.60,
    "generic_news": 0.15      // Decreased (low hit rate)
  }
}
```

---

## Recommended Workflow

### Weekly Keyword Discovery Cycle

**Monday**: Extract keywords from last week's MOA data
```bash
python extract_moa_keywords.py
```

**Tuesday**: Review LLM suggestions from SEC filings
```bash
grep "sec_llm_keywords" data/logs/bot.jsonl | tail -100
```

**Wednesday**: Add 3-5 new high-value keywords to config.py

**Thursday**: Backtest new keywords
```bash
.venv/Scripts/python -m catalyst_bot.backtesting.engine --start 2024-09-01 --end 2025-10-01
```

**Friday**: Deploy updated keywords if backtest shows improvement

**Weekend**: Monitor performance, collect data for next cycle

---

## Quick Reference: High-Value Keywords by Sector

### Biotech/Pharma (Highest ROI)
```python
"fda": [
    "fda approval", "fda clearance", "breakthrough therapy",
    "fast track", "orphan drug", "accelerated approval",
    "biologics license", "new drug application"
]

"clinical": [
    "phase 3 results", "clinical trial success", "primary endpoint met",
    "statistically significant", "pivotal trial", "clinical hold lifted"
]
```

### Energy (Highest Volatility)
```python
"energy_discovery": [
    "oil discovery", "gas discovery", "drilling results",
    "reserves expansion", "well completion", "production increase",
    "field development", "horizontal drilling"
]
```

### Technology (High Frequency)
```python
"tech_contracts": [
    "cloud contract", "government contract", "enterprise agreement",
    "strategic partnership", "licensing deal", "patent granted"
]
```

### Finance (Momentum Triggers)
```python
"uplisting": [
    "nasdaq uplisting", "nyse listing", "exchange upgrade",
    "listing approval", "minimum bid price"
]

"institutional": [
    "institutional investment", "venture funding", "series b",
    "strategic investment", "lead investor"
]
```

---

## Common Mistakes to Avoid

### 1. **Too Generic**
❌ BAD: "announces", "reports", "updates"
✅ GOOD: "fda approval", "merger agreement", "clinical trial success"

### 2. **Too Narrow**
❌ BAD: "phase 3 glioblastoma trial primary endpoint" (too specific)
✅ GOOD: "phase 3 trial", "primary endpoint met" (separate keywords)

### 3. **Duplicate Coverage**
❌ BAD: Adding "fda clearance" when "fda approval" already covers it
✅ GOOD: Add if nuance matters (clearance = 510k, approval = PMA)

### 4. **No Testing**
❌ BAD: Adding 20 keywords at once without backtesting
✅ GOOD: Add 3-5, backtest, measure impact, iterate

---

## Success Metrics

Track these KPIs to measure keyword effectiveness:

```python
# From backtester output
{
    "baseline": {
        "total_alerts": 847,
        "hit_rate": 41.2%,
        "avg_return": 23.4%,
        "coverage": 85.2%  # % of profitable catalysts caught
    },
    "with_new_keywords": {
        "total_alerts": 1039,
        "hit_rate": 38.7%,  # Slight decrease OK if coverage increases
        "avg_return": 24.1%,
        "coverage": 91.8%   # +6.6% coverage = SUCCESS
    }
}
```

**Goal**: Increase coverage (catch more opportunities) while maintaining hit rate >35%

---

## Next Steps

1. **Enable rejected_items logging** (add code to feeds.py)
2. **Run 12-month bootstrap** to collect MOA data
3. **Extract keywords** using extract_moa_keywords.py
4. **Add top 10 keywords** to config.py
5. **Backtest** to validate improvement
6. **Deploy** and monitor for 1 week
7. **Repeat** weekly to continuously improve

**Expected Outcome**: 15-25% increase in coverage (catching profitable catalysts) with <10% increase in false positives.

---

## Support & Resources

- **Config file**: `src/catalyst_bot/config.py:371-520`
- **Classifier logic**: `src/catalyst_bot/classify.py:610-630`
- **MOA analyzer**: `analyze_moa_data.py`
- **Keyword extractor**: `extract_moa_keywords.py`
- **SEC LLM analyzer**: `src/catalyst_bot/sec_llm_analyzer.py`

---

**Last Updated**: October 16, 2025
**Author**: Catalyst-Bot Team
**Version**: 2.0 (MOA-Enhanced)
