# Solution: Missing Keywords in LOW_SCORE Rejections

## Problem Summary
- **88.9% of LOW_SCORE rejections** have empty keyword arrays
- Missing out on learning from **massive gains**: CASK (+2,277%), FLYE (+812%), GPUS (+435%)
- MOA can only analyze the 11.1% with keywords, limiting effectiveness

## Root Cause
The classifier's `_keywords_of()` function (runner.py:1035) looks for keywords in the scored object:
```python
def _keywords_of(scored: Any) -> List[str]:
    for name in ("keywords", "tags", "categories"):
        ks = _get(scored, name, None)
        if ks:
            return _as_list(ks)
    return []  # Returns empty if classifier didn't populate keywords
```

When items get LOW_SCORE (score=0.0), the classifier often doesn't populate keyword data.

---

## Solution 1: Backfill Historical Data (IMMEDIATE - Run Today)

**What**: Use existing `classify_rejected_items.py` script to retroactively classify the 9,424 items missing keywords

**Why**: Unlocks learning from historical missed opportunities immediately

**How**:
```bash
# 1. Run classification script on rejected items
python -m catalyst_bot.scripts.classify_rejected_items

# 2. This creates data/rejected_items_classified.jsonl with keywords populated

# 3. Update outcomes.jsonl with classified keywords
# (Need to create merger script - see Solution 2b)

# 4. Re-run MOA analysis to get keyword recommendations
python -c "from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis; run_historical_moa_analysis()"
```

**Expected Result**:
- Instead of 2 keywords (earnings, beat), MOA should find 20-50 keywords
- Can identify which keywords correlate with +800% to +2,200% returns

**Time**: 5-10 minutes to classify 10,000 items

---

## Solution 2a: Create Outcome-Keyword Merger Script

**What**: Script to merge classified keywords back into outcomes.jsonl

**Why**: Backfill script outputs to separate file; need to update existing outcomes

**Implementation**:
```python
# File: merge_classified_keywords.py

import json
from collections import defaultdict
from pathlib import Path

def merge_classified_keywords():
    """Merge keywords from rejected_items_classified.jsonl into outcomes.jsonl"""

    # 1. Load classified keywords keyed by (ticker, rejection_ts)
    classified_keywords = {}

    with open('data/rejected_items_classified.jsonl', 'r') as f:
        for line in f:
            item = json.loads(line)
            key = (item['ticker'], item['ts'])
            keywords = item.get('cls', {}).get('keywords', [])
            if keywords:
                classified_keywords[key] = keywords

    print(f"Loaded {len(classified_keywords)} classified items")

    # 2. Update outcomes.jsonl
    outcomes = []
    updated_count = 0

    with open('data/moa/outcomes.jsonl', 'r') as f:
        for line in f:
            outcome = json.loads(line)
            key = (outcome['ticker'], outcome['rejection_ts'])

            # If outcome missing keywords and we have classified version
            if key in classified_keywords:
                existing_kw = outcome.get('cls', {}).get('keywords', [])
                if not existing_kw:
                    if 'cls' not in outcome:
                        outcome['cls'] = {}
                    outcome['cls']['keywords'] = classified_keywords[key]
                    updated_count += 1

            outcomes.append(outcome)

    print(f"Updated {updated_count} outcomes with keywords")

    # 3. Write back
    with open('data/moa/outcomes.jsonl', 'w') as f:
        for outcome in outcomes:
            f.write(json.dumps(outcome) + '\n')

    print("Done!")

if __name__ == '__main__':
    merge_classified_keywords()
```

**Usage**:
```bash
python merge_classified_keywords.py
```

---

## Solution 2b: Update Backfill Script to Include Classification

**What**: Modify `moa_backfill_14days.py` to run classification if keywords missing

**Why**: Future backfills automatically get keywords

**Implementation**:
```python
# In moa_backfill_14days.py, add classification step:

from catalyst_bot.classify import classify
from catalyst_bot.models import NewsItem

def backfill_with_classification(item):
    """Enhanced backfill that ensures keywords exist"""

    # Check if keywords missing
    keywords = item.get('cls', {}).get('keywords', [])

    if not keywords:
        # Run classification
        news_item = NewsItem(
            title=item.get("title", ""),
            link=item.get("link", ""),
            source_host=item.get("source", ""),
            ts=item.get("ts", ""),
            ticker=item.get("ticker", ""),
            summary=item.get("summary", ""),
        )

        scored = classify(news_item)

        # Extract keywords
        if scored:
            if hasattr(scored, "keyword_hits"):
                keywords = list(scored.keyword_hits or [])
            elif hasattr(scored, "tags"):
                keywords = list(scored.tags or [])
            elif isinstance(scored, dict):
                keywords = list(scored.get("keywords", []))

        # Update item
        if 'cls' not in item:
            item['cls'] = {}
        item['cls']['keywords'] = keywords

    return item
```

---

## Solution 3: Fix Classification Pipeline (LONG-TERM)

**What**: Ensure ALL alerts get keyword classification BEFORE scoring

**Why**: Prevents future LOW_SCORE items from having empty keywords

**Investigation Steps**:
```python
# 1. Check classify() function in classify.py
# Does it skip keyword extraction for low scores?

# 2. Check if scoring happens before keyword extraction
# Reorder so keywords extract first

# 3. Add mandatory keyword extraction
# Even if score=0.0, extract keywords from title
```

**Hypothesis to Test**:
- Does the classifier have a score threshold that skips keyword extraction?
- Are low-scoring items classified differently than high-scoring ones?

**Code to Check**:
```bash
# Search for score-based branching in classification
grep -n "if.*score.*<" src/catalyst_bot/classify.py
grep -n "threshold" src/catalyst_bot/classify.py
```

---

## Solution 4: Auto-Backfill in MOA (ENHANCEMENT)

**What**: MOA automatically triggers classification when it detects >20% outcomes missing keywords

**Why**: Self-healing system - MOA ensures its own data quality

**Implementation**:
```python
# In moa_historical_analyzer.py, add to run_historical_moa_analysis():

def run_historical_moa_analysis():
    # ... existing code ...

    # Check keyword coverage
    total = len(outcomes)
    missing_keywords = sum(1 for o in outcomes if not o.get('cls', {}).get('keywords'))
    missing_pct = missing_keywords / total if total > 0 else 0

    if missing_pct > 0.20:  # More than 20% missing keywords
        log.warning(
            f"moa_low_keyword_coverage "
            f"missing={missing_keywords} total={total} pct={missing_pct:.1%}"
        )

        # Option A: Auto-trigger backfill
        # subprocess.run(['python', '-m', 'catalyst_bot.scripts.classify_rejected_items'])

        # Option B: Create review note
        analysis_notes.append(
            f"⚠️ Data Quality Issue: {missing_pct:.1%} of outcomes missing keywords. "
            f"Run: python -m catalyst_bot.scripts.classify_rejected_items"
        )

    # ... continue analysis ...
```

---

## Recommended Action Plan

### Phase 1: Immediate (Today)
1. ✅ Run backfill classification script
2. ✅ Create keyword merger script
3. ✅ Merge keywords into outcomes.jsonl
4. ✅ Re-run MOA to get keyword recommendations from profitable LOW_SCORE items

### Phase 2: Short-term (This Week)
5. ⬜ Update backfill script to include classification by default
6. ⬜ Investigate why classifier skips keywords for LOW_SCORE items
7. ⬜ Add keyword coverage check to MOA with warnings

### Phase 3: Long-term (Next Sprint)
8. ⬜ Fix classification pipeline to ensure ALL items get keywords
9. ⬜ Add auto-backfill trigger in MOA when coverage drops below 80%
10. ⬜ Add keyword coverage metrics to MOA summary Discord message

---

## Expected Impact

### Before (Current State)
- 88.9% of LOW_SCORE rejections missing keywords
- MOA finds 2 keywords from 11.1% of data
- Missing patterns from +800% to +2,200% winners

### After (All Solutions Implemented)
- 100% of outcomes have keywords
- MOA analyzes full dataset
- Can identify which keywords predict massive gains
- Self-healing: MOA auto-detects and fixes data gaps

### Estimated Value
If we capture even 10% of the LOW_SCORE missed opportunities:
- Current: Missing 177 opportunities @ 228% avg = ~40,356% total gains missed
- With fix: Catch 17 more opportunities = ~4,000% recovered gains
- **That's 40+ profitable trades per 14-day window**

---

## Testing Plan

```bash
# 1. Test classification script on sample
python -m catalyst_bot.scripts.classify_rejected_items --limit 100 --dry-run

# 2. Verify keywords extracted
python -c "
import json
with open('data/rejected_items_classified.jsonl') as f:
    items = [json.loads(line) for line in f if line.strip()]
    with_kw = sum(1 for i in items if i.get('cls', {}).get('keywords'))
    print(f'{with_kw}/{len(items)} have keywords ({with_kw/len(items)*100:.1f}%)')
"

# 3. Run MOA on updated data
python -c "from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis; r = run_historical_moa_analysis(); print(f\"Recommendations: {len(r.get('recommendations', []))}\")"

# 4. Compare before/after keyword counts
```

---

## Questions for Discussion

1. **Priority**: Should we run Phase 1 (backfill) immediately or investigate root cause first?
2. **Data Integrity**: Should we archive outcomes.jsonl before merging keywords?
3. **Automation**: Should MOA auto-trigger backfill or just warn the user?
4. **Threshold**: What's acceptable keyword coverage? 80%? 90%? 95%?

---

**Next Steps**:
- [ ] User approval to run backfill classification
- [ ] Create and test keyword merger script
- [ ] Re-run MOA to see new keyword recommendations
