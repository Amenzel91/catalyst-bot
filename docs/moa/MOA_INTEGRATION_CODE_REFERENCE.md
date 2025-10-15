# MOA Keyword Discovery - Code Reference

## Quick Reference: Key Code Changes

### 1. New Function: Load Accepted Items

**Location**: `src/catalyst_bot/moa_analyzer.py` (lines 114-167)

```python
def load_accepted_items(since_days: int = ANALYSIS_WINDOW_DAYS) -> List[Dict[str, Any]]:
    """
    Load accepted items from data/accepted_items.jsonl.

    Args:
        since_days: Only load items from the last N days

    Returns:
        List of accepted item dictionaries
    """
    root, _ = _ensure_moa_dirs()
    accepted_path = root / "data" / "accepted_items.jsonl"

    if not accepted_path.exists():
        log.warning(f"accepted_items_not_found path={accepted_path}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    items = []

    try:
        with open(accepted_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(line)

                    # Parse timestamp
                    ts_str = item.get("ts", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        log.debug(f"invalid_timestamp line={line_num} ts={ts_str}")
                        continue

                    # Skip old items
                    if ts < cutoff:
                        continue

                    items.append(item)

                except json.JSONDecodeError as e:
                    log.debug(f"invalid_json line={line_num} err={e}")
                    continue

        log.info(f"loaded_accepted_items count={len(items)} since_days={since_days}")
        return items

    except Exception as e:
        log.error(f"load_accepted_items_failed err={e}")
        return []
```

### 2. New Function: Discover Keywords

**Location**: `src/catalyst_bot/moa_analyzer.py` (lines 463-554)

```python
def discover_keywords_from_missed_opportunities(
    missed_opps: List[Dict[str, Any]],
    min_occurrences: int = 5,
    min_lift: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Discover new keyword candidates from missed opportunities using text mining.

    Compares keywords in missed opportunities vs false positives to find
    discriminative phrases that predict price movement.

    Args:
        missed_opps: List of missed opportunity items (went up >10% after rejection)
        min_occurrences: Minimum times keyword must appear
        min_lift: Minimum lift ratio (positive_rate / negative_rate)

    Returns:
        List of discovered keyword dicts with lift scores and weights
    """
    try:
        from .keyword_miner import mine_discriminative_keywords
    except ImportError:
        log.warning("keyword_miner module not available, skipping keyword discovery")
        return []

    # Extract titles from missed opportunities (positives)
    positive_titles = [item.get("title", "") for item in missed_opps if item.get("title")]

    # Load accepted items (items we alerted on)
    accepted_items = load_accepted_items(since_days=ANALYSIS_WINDOW_DAYS)

    negative_titles = [item.get("title", "") for item in accepted_items if item.get("title")]

    if not positive_titles or not negative_titles:
        log.info("insufficient_data_for_keyword_discovery "
                f"positive={len(positive_titles)} negative={len(negative_titles)}")
        return []

    # Mine discriminative keywords
    try:
        scored_phrases = mine_discriminative_keywords(
            positive_titles=positive_titles,
            negative_titles=negative_titles,
            min_occurrences=min_occurrences,
            min_lift=min_lift,
            max_ngram_size=4,
        )

        # Convert to recommendation format
        discovered = []
        for phrase, lift, pos_count, neg_count in scored_phrases:
            # Calculate recommended weight based on lift and frequency
            base_weight = 0.3
            lift_bonus = min(0.5, (lift - min_lift) * 0.1)
            freq_bonus = min(0.2, pos_count / 20.0)

            recommended_weight = round(base_weight + lift_bonus + freq_bonus, 2)
            recommended_weight = min(0.8, recommended_weight)  # Cap at 0.8

            discovered.append({
                'keyword': phrase,
                'lift': round(lift, 2),
                'positive_count': pos_count,
                'negative_count': neg_count,
                'type': 'discovered',
                'recommended_weight': recommended_weight,
            })

        log.info(f"discovered_keywords count={len(discovered)} "
                f"from_positive={len(positive_titles)} from_negative={len(negative_titles)}")

        return discovered

    except Exception as e:
        log.error(f"keyword_discovery_failed err={e}", exc_info=True)
        return []
```

### 3. Updated Function: run_moa_analysis()

**Location**: `src/catalyst_bot/moa_analyzer.py` (lines 803-856)

**Key changes** in the main analysis pipeline:

```python
# 3. Extract keywords and calculate statistics
keyword_stats = extract_keywords_from_missed_opps(missed_opps)

# 3b. DISCOVER NEW KEYWORDS using text mining
discovered_keywords = discover_keywords_from_missed_opportunities(
    missed_opps=missed_opps,
    min_occurrences=5,
    min_lift=2.0,
)

if not keyword_stats and not discovered_keywords:
    log.warning("no_significant_keywords")
    return {
        "status": "no_keywords",
        "message": "No keywords with sufficient occurrences",
        "total_rejected": len(rejected_items),
        "missed_opportunities": len(missed_opps),
    }

# 4. Load current keyword weights
current_weights = load_current_keyword_weights()

# 5. Generate recommendations (from existing keywords)
recommendations = calculate_weight_recommendations(
    keyword_stats, current_weights
)

# 5b. Add discovered keyword recommendations
for disc in discovered_keywords:
    # Check if keyword already exists in recommendations
    existing = next((r for r in recommendations if r['keyword'] == disc['keyword']), None)

    if existing:
        # Merge with existing recommendation (prefer discovered if higher weight)
        if disc['recommended_weight'] > existing.get('recommended_weight', 0):
            existing['recommended_weight'] = disc['recommended_weight']
            existing['type'] = 'discovered_and_existing'
            existing['evidence']['lift'] = disc['lift']
            existing['evidence']['discovered_positive_count'] = disc['positive_count']
            existing['evidence']['discovered_negative_count'] = disc['negative_count']
    else:
        # Add as new recommendation
        recommendations.append({
            'keyword': disc['keyword'],
            'type': 'new_discovered',
            'current_weight': None,
            'recommended_weight': disc['recommended_weight'],
            'confidence': 0.7,  # Medium confidence for discovered keywords
            'evidence': {
                'lift': disc['lift'],
                'positive_count': disc['positive_count'],
                'negative_count': disc['negative_count'],
            }
        })
```

### 4. Updated Function: save_recommendations()

**Location**: `src/catalyst_bot/moa_analyzer.py` (lines 692-705)

**Key change**: Track discovered keywords count

```python
# Count discovered keywords
discovered_count = len([
    r for r in recommendations
    if 'discovered' in r.get('type', '')
])

output = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "analysis_period": period_str,
    "total_rejected": total_rejected,
    "missed_opportunities": missed_opportunities,
    "discovered_keywords_count": discovered_count,  # NEW
    "recommendations": recommendations,
}
```

### 5. Updated Exports

**Location**: `src/catalyst_bot/moa_analyzer.py` (lines 945-957)

```python
__all__ = [
    "run_moa_analysis",
    "get_moa_summary",
    "load_rejected_items",
    "load_accepted_items",  # NEW
    "identify_missed_opportunities",
    "extract_keywords_from_missed_opps",
    "discover_keywords_from_missed_opportunities",  # NEW
    "calculate_weight_recommendations",
    "save_recommendations",
    "load_analysis_state",
    "save_analysis_state",
]
```

## Recommendation Types

After integration, the system produces four types of recommendations:

### Type 1: `new` (Existing System)
Keywords found in missed opportunities, not in current weights.
```json
{
  "keyword": "earnings beat",
  "type": "new",
  "current_weight": null,
  "recommended_weight": 1.5,
  "confidence": 0.75,
  "evidence": {
    "occurrences": 8,
    "success_rate": 0.625,
    "avg_return": 0.156
  }
}
```

### Type 2: `weight_increase` (Existing System)
Keywords already tracked, recommended for weight increase.
```json
{
  "keyword": "fda approval",
  "type": "weight_increase",
  "current_weight": 2.0,
  "recommended_weight": 2.3,
  "confidence": 0.85,
  "evidence": {
    "occurrences": 15,
    "success_rate": 0.867,
    "avg_return": 0.234
  }
}
```

### Type 3: `new_discovered` (NEW)
Keywords discovered through text mining, not in existing keywords.
```json
{
  "keyword": "regulatory approval",
  "type": "new_discovered",
  "current_weight": null,
  "recommended_weight": 0.65,
  "confidence": 0.7,
  "evidence": {
    "lift": 5.2,
    "positive_count": 12,
    "negative_count": 2
  }
}
```

### Type 4: `discovered_and_existing` (NEW)
Keywords validated by both methods (highest confidence).
```json
{
  "keyword": "fda approval",
  "type": "discovered_and_existing",
  "current_weight": 2.0,
  "recommended_weight": 2.3,
  "confidence": 0.85,
  "evidence": {
    "occurrences": 15,
    "success_rate": 0.867,
    "avg_return": 0.234,
    "lift": 4.8,
    "discovered_positive_count": 13,
    "discovered_negative_count": 3
  }
}
```

## Weight Calculation Formula

### Existing Keywords (frequency-based)
```python
if success_rate >= 0.7:
    adjustment = 0.3  # Strong performer
elif success_rate >= 0.6:
    adjustment = 0.2  # Good performer
else:
    adjustment = 0.1  # Moderate performer

recommended_weight = round(current_weight + adjustment, 2)
recommended_weight = max(0.5, min(recommended_weight, 3.0))
```

### Discovered Keywords (lift-based)
```python
base_weight = 0.3
lift_bonus = min(0.5, (lift - min_lift) * 0.1)  # 0.0-0.5
freq_bonus = min(0.2, pos_count / 20.0)         # 0.0-0.2

recommended_weight = round(base_weight + lift_bonus + freq_bonus, 2)
recommended_weight = min(0.8, recommended_weight)  # Conservative cap
```

## Confidence Scoring

### Existing Keywords
```python
if occurrences >= 20 and success_rate >= 0.7:
    confidence = 0.9  # Very high
elif occurrences >= 10 and success_rate >= 0.6:
    confidence = 0.75  # High
elif occurrences >= MIN_OCCURRENCES:
    confidence = 0.6  # Medium
else:
    confidence = 0.5  # Low
```

### Discovered Keywords
```python
confidence = 0.7  # Medium confidence for newly discovered
```

### Merged Keywords
```python
# Inherits higher confidence from existing keyword analysis
# Typically 0.75-0.9 if validated through both methods
```

## Usage Examples

### Basic Usage
```python
from catalyst_bot.moa_analyzer import run_moa_analysis

result = run_moa_analysis(since_days=30)
print(f"Status: {result['status']}")
print(f"Discovered keywords: {result.get('discovered_keywords_count', 0)}")
```

### Custom Parameters
```python
from catalyst_bot.moa_analyzer import (
    load_rejected_items,
    identify_missed_opportunities,
    discover_keywords_from_missed_opportunities
)

# Load data
rejected = load_rejected_items(since_days=30)
missed_opps = identify_missed_opportunities(rejected, threshold_pct=15.0)

# Discover keywords with custom thresholds
discovered = discover_keywords_from_missed_opportunities(
    missed_opps=missed_opps,
    min_occurrences=10,  # Higher threshold
    min_lift=3.0,        # Only very strong signals
)

print(f"Discovered {len(discovered)} high-confidence keywords")
```

### Filter by Recommendation Type
```python
import json

# Load recommendations
with open('data/moa/recommendations.json') as f:
    data = json.load(f)

# Get only discovered keywords
discovered = [r for r in data['recommendations'] if 'discovered' in r.get('type', '')]

# Get only high-confidence recommendations
high_conf = [r for r in data['recommendations'] if r.get('confidence', 0) >= 0.8]

# Get keywords needing action (weight increase or new)
actionable = [r for r in data['recommendations'] if r.get('current_weight') is None or
              r.get('recommended_weight', 0) > r.get('current_weight', 0)]
```

## Testing Checklist

- [x] Syntax validation (python -m py_compile)
- [ ] Unit test for load_accepted_items()
- [ ] Unit test for discover_keywords_from_missed_opportunities()
- [ ] Integration test for full pipeline
- [ ] Verify recommendations.json output format
- [ ] Test with empty accepted_items.jsonl
- [ ] Test with no keyword overlap
- [ ] Test with all keywords overlapping
- [ ] Verify weight calculation formulas
- [ ] Verify confidence scoring

## Performance Considerations

### Time Complexity
- `load_accepted_items()`: O(n) where n = lines in file
- `discover_keywords_from_missed_opportunities()`: O(m * k) where m = titles, k = avg title length
- `mine_discriminative_keywords()`: O(p + q) where p = positive n-grams, q = negative n-grams

### Memory Usage
- Accepted items: ~1 KB per item × item count
- N-grams: ~50 bytes per n-gram × n-gram count
- Recommendations: ~500 bytes per recommendation

### Optimization Tips
1. Adjust `since_days` to limit data volume
2. Increase `min_occurrences` to reduce n-gram count
3. Decrease `max_ngram_size` to reduce combinations
4. Cache accepted_items if running multiple analyses

## Dependencies

```python
# Internal
from .keyword_miner import mine_discriminative_keywords
from .accepted_items_logger import load_accepted_items  # Implicit via file read

# Standard library
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
```

## Files Affected

### Modified
- `src/catalyst_bot/moa_analyzer.py` (+150 lines)

### Read
- `data/rejected_items.jsonl` (existing)
- `data/accepted_items.jsonl` (new dependency)
- `data/analyzer/keyword_stats.json` (existing)

### Written
- `data/moa/recommendations.json` (updated format)
- `data/moa/analysis_state.json` (existing)

## Rollback Procedure

If issues occur, the integration can be rolled back without data loss:

1. Git revert to previous commit
2. Recommendations.json will continue working (new fields ignored)
3. No database migrations required
4. No configuration changes needed

The integration is backwards-compatible and additive only.
