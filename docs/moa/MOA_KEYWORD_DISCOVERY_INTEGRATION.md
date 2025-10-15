# MOA Keyword Discovery Integration

## Overview

The keyword discovery pipeline has been successfully integrated into the MOA (Missed Opportunities Analyzer). This enhancement enables the system to automatically discover new catalyst keywords by mining discriminative phrases from news titles, comparing missed opportunities (rejected items that went up >10%) against accepted items (alerts we sent).

## Integration Summary

### File Modified
- `src/catalyst_bot/moa_analyzer.py`

### New Functions Added

#### 1. `load_accepted_items(since_days: int) -> List[Dict[str, Any]]`
Loads accepted items from `data/accepted_items.jsonl` within the specified time window.

**Purpose**: Provides the negative examples (items we alerted on) for discriminative keyword mining.

**Returns**: List of accepted item dictionaries with timestamps, titles, keywords, and classification data.

#### 2. `discover_keywords_from_missed_opportunities(...) -> List[Dict[str, Any]]`
Core keyword discovery function that mines discriminative phrases using text analysis.

**Algorithm**:
1. Extracts titles from missed opportunities (positive examples)
2. Loads and extracts titles from accepted items (negative examples)
3. Uses `keyword_miner.mine_discriminative_keywords()` to find phrases with high lift scores
4. Converts discovered phrases to recommendation format with calculated weights

**Parameters**:
- `missed_opps`: List of missed opportunity items
- `min_occurrences`: Minimum frequency threshold (default: 5)
- `min_lift`: Minimum lift ratio threshold (default: 2.0)

**Returns**: List of discovered keyword dictionaries with lift scores and recommended weights

**Weight Calculation**:
```python
base_weight = 0.3
lift_bonus = min(0.5, (lift - min_lift) * 0.1)  # 0.0-0.5 based on lift
freq_bonus = min(0.2, pos_count / 20.0)         # 0.0-0.2 based on frequency
recommended_weight = min(0.8, base_weight + lift_bonus + freq_bonus)
```

### Modified Functions

#### `run_moa_analysis(since_days: int) -> Dict[str, Any]`
Enhanced to integrate keyword discovery into the main analysis pipeline.

**New Steps**:
1. Extract keywords from missed opportunities (existing)
2. **NEW**: Discover keywords using text mining
3. Merge discovered keywords with existing keyword recommendations
4. Include discovered keyword count in output

**Keyword Merging Logic**:
- If discovered keyword already exists in recommendations from existing analysis:
  - Use higher recommended weight
  - Mark type as `'discovered_and_existing'`
  - Add lift score and discovery counts to evidence
- If discovered keyword is new:
  - Add as `'new_discovered'` type
  - Set confidence to 0.7 (medium confidence)
  - Include lift score and occurrence counts

#### `save_recommendations(...) -> Path`
Updated to track discovered keywords count.

**New Output Field**:
```json
{
  "discovered_keywords_count": 3,
  "recommendations": [...]
}
```

## How Discovered Keywords are Merged

### Scenario 1: New Discovered Keyword
A keyword found through text mining that doesn't exist in current keyword_stats.json.

**Example**:
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

**Interpretation**:
- Phrase appears in 12 missed opportunities but only 2 accepted items
- Lift of 5.2 means it's 5.2x more common in successful catalysts
- Recommended weight of 0.65 (conservative due to being newly discovered)

### Scenario 2: Discovered + Existing Keyword
A keyword that appears in both the existing keyword analysis and the text mining results.

**Example**:
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

**Interpretation**:
- Confirmed through both methods (higher confidence)
- Strong lift score (4.8) validates the high success rate
- Recommendation to increase weight from 2.0 to 2.3

### Scenario 3: Existing Keyword Only
A keyword that appears in current tracking but wasn't discovered through text mining.

**Example**:
```json
{
  "keyword": "earnings beat",
  "type": "weight_increase",
  "current_weight": 1.5,
  "recommended_weight": 1.8,
  "confidence": 0.75,
  "evidence": {
    "occurrences": 8,
    "success_rate": 0.625,
    "avg_return": 0.156
  }
}
```

**Interpretation**:
- Not discovered through text mining (may appear in both positive and negative)
- Still valuable based on historical performance in missed opportunities

## Example Output

### Full Recommendations JSON
```json
{
  "timestamp": "2025-10-14T10:30:00Z",
  "analysis_period": "2025-09-14 to 2025-10-14",
  "total_rejected": 245,
  "missed_opportunities": 38,
  "discovered_keywords_count": 3,
  "recommendations": [
    {
      "keyword": "phase 3 trial",
      "type": "new_discovered",
      "current_weight": null,
      "recommended_weight": 0.7,
      "confidence": 0.7,
      "evidence": {
        "lift": 6.5,
        "positive_count": 13,
        "negative_count": 2
      }
    },
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
    },
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
    },
    {
      "keyword": "breakthrough therapy",
      "type": "new_discovered",
      "current_weight": null,
      "recommended_weight": 0.6,
      "confidence": 0.7,
      "evidence": {
        "lift": 4.2,
        "positive_count": 8,
        "negative_count": 2
      }
    },
    {
      "keyword": "earnings beat",
      "type": "weight_increase",
      "current_weight": 1.5,
      "recommended_weight": 1.8,
      "confidence": 0.75,
      "evidence": {
        "occurrences": 8,
        "success_rate": 0.625,
        "avg_return": 0.156
      }
    }
  ]
}
```

### Interpreting the Results

**Discovered Keywords (3)**:
1. "phase 3 trial" - New phrase with very high lift (6.5x)
2. "regulatory approval" - New phrase with high lift (5.2x)
3. "breakthrough therapy" - New phrase with good lift (4.2x)
4. "fda approval" - Confirmed through both methods (discovered + existing)

**Recommendation Types**:
- `new_discovered`: Add these as new keywords with conservative weights (0.6-0.7)
- `discovered_and_existing`: Strong validation, increase weights moderately
- `weight_increase`: Continue tracking, adjust based on performance

**Confidence Levels**:
- 0.7: Medium confidence for newly discovered keywords
- 0.75-0.85: Higher confidence when validated by multiple methods
- 0.9+: Very high confidence (requires large sample size + high success rate)

## Benefits of Integration

### 1. Automatic Discovery
- No manual keyword curation needed
- Discovers multi-word phrases (n-grams up to 4 words)
- Finds domain-specific terminology automatically

### 2. Statistical Validation
- Lift ratio ensures keywords discriminate between success/failure
- Minimum occurrence threshold prevents overfitting on rare phrases
- Confidence scoring reflects sample size and performance

### 3. False Positive Prevention
- Compares against accepted items (alerts we sent)
- Avoids suggesting keywords that increase noise
- Only recommends phrases with positive signal

### 4. Dual-Method Validation
- Combines frequency analysis (existing keywords) with text mining (discovered keywords)
- Higher confidence when both methods agree
- Conservative weighting for discovered-only keywords

## Integration with Existing Workflow

### Data Flow
```
rejected_items.jsonl
        |
        v
identify_missed_opportunities()
        |
        +---> extract_keywords_from_missed_opps()  [Existing method]
        |           |
        |           v
        |     keyword_stats (occurrences, success_rate, avg_return)
        |
        +---> discover_keywords_from_missed_opportunities()  [NEW method]
                    |
                    v
              Load accepted_items.jsonl
                    |
                    v
              mine_discriminative_keywords()
                    |
                    v
              discovered_keywords (lift, positive_count, negative_count)
                    |
                    v
        MERGE both keyword sources
                    |
                    v
        calculate_weight_recommendations()
                    |
                    v
        save_recommendations() -> data/moa/recommendations.json
```

### Usage
```python
from catalyst_bot.moa_analyzer import run_moa_analysis

# Run complete analysis with keyword discovery
result = run_moa_analysis(since_days=30)

if result["status"] == "success":
    print(f"Discovered keywords: {result.get('discovered_keywords_count', 0)}")
    print(f"Total recommendations: {result['recommendations_count']}")
```

### Output Files
- `data/moa/recommendations.json` - Contains both discovered and existing keyword recommendations
- `data/moa/analysis_state.json` - Tracks last run timestamp and summary statistics

## Future Enhancements

### Phase 1 (Current)
- [x] Load accepted items for negative examples
- [x] Discover keywords using text mining
- [x] Merge discovered keywords with existing recommendations
- [x] Track discovered keyword count in output

### Phase 2 (Future)
- [ ] Track actual outcomes for accepted items (true positive vs false positive)
- [ ] Filter accepted items by outcome to improve negative example quality
- [ ] Implement confidence boosting when outcome data is available
- [ ] Add keyword removal recommendations for consistently negative lift

### Phase 3 (Advanced)
- [ ] Temporal analysis: track keyword effectiveness over time
- [ ] Sector-specific keyword discovery
- [ ] Multi-language keyword support
- [ ] Automated A/B testing of keyword weights

## Dependencies

### Required Modules
- `keyword_miner.py` - Text mining and n-gram extraction
- `accepted_items_logger.py` - Logging accepted items for negative examples

### Optional Dependencies
- `breakout_feedback.py` - For outcome tracking (future enhancement)

## Testing

To test the integration:

```bash
# Run MOA analysis
python -c "from src.catalyst_bot.moa_analyzer import run_moa_analysis; print(run_moa_analysis(since_days=30))"

# Check recommendations file
cat data/moa/recommendations.json | python -m json.tool

# View discovered keywords
python -c "
from src.catalyst_bot.moa_analyzer import run_moa_analysis
import json

result = run_moa_analysis(since_days=30)

# Load recommendations
with open('data/moa/recommendations.json') as f:
    data = json.load(f)

# Show discovered keywords
discovered = [r for r in data['recommendations'] if 'discovered' in r.get('type', '')]
print(f'Discovered {len(discovered)} new keywords:')
for rec in discovered:
    print(f\"  - {rec['keyword']}: weight={rec['recommended_weight']}, lift={rec['evidence'].get('lift', 'N/A')}\")
"
```

## Troubleshooting

### Issue: No discovered keywords
**Possible causes**:
- Insufficient accepted items (need negative examples)
- All phrases appear in both positive and negative sets (low lift)
- Minimum occurrence threshold too high

**Solution**: Lower `min_occurrences` or `min_lift` parameters

### Issue: Too many low-quality discovered keywords
**Possible causes**:
- Lift threshold too low
- Minimum occurrence threshold too low

**Solution**: Increase `min_lift` to 3.0+ or `min_occurrences` to 10+

### Issue: ImportError for keyword_miner
**Cause**: keyword_miner.py not in path

**Solution**: Verify module exists at `src/catalyst_bot/keyword_miner.py`

## Summary

The keyword discovery integration provides a powerful automated method for finding new catalyst keywords by analyzing the discriminative power of phrases in news titles. By comparing missed opportunities against accepted items, the system can identify high-value keywords that predict price movements while avoiding false positive generators.

The dual-method approach (existing frequency analysis + new text mining) provides robust validation and enables conservative, data-driven keyword recommendations.
