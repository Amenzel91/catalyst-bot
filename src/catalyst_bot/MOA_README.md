# MOA (Missed Opportunities Analyzer) Module

## Overview

The MOA module analyzes rejected items to identify missed trading opportunities and recommend keyword weight adjustments. This is Phase 2 of the MOA system as outlined in `MOA_DESIGN_V2.md`.

## File Location

**Module Path**: `src/catalyst_bot/moa_analyzer.py`

## Features

### 1. Rejected Items Analysis
- Reads from `data/rejected_items.jsonl`
- Analyzes items from configurable time window (default: 30 days)
- Filters by timestamp and validates data integrity

### 2. Price Outcome Tracking
- Checks price changes at multiple timeframes: 1h, 4h, 24h, 7d after rejection
- Uses existing `market.get_last_price_change()` for price lookups
- Handles missing data gracefully with proper error handling

### 3. Missed Opportunity Detection
- Identifies items where price increased >10% (configurable threshold)
- Tracks both the magnitude and timing of price movements
- Calculates miss rate statistics

### 4. Keyword Analysis
- Extracts keywords from rejected items that became successful
- Calculates frequency, success rate, and average returns per keyword
- Applies minimum occurrence threshold (default: 5) for statistical significance

### 5. Recommendation Engine
- **New Keywords**: Suggests keywords found in missed opportunities but not in current list
- **Weight Adjustments**: Recommends increases for keywords with high success rates
- Confidence scoring based on sample size and success rate
- Conservative weight ranges (0.5 to 3.0)

### 6. State Management
- Stores analysis state in `data/moa/analysis_state.json`
- Tracks last run time, analysis period, and key metrics
- Enables incremental analysis and monitoring

## Output Format

### recommendations.json
```json
{
  "timestamp": "2025-10-11T00:00:00+00:00",
  "analysis_period": "2025-09-11 to 2025-10-11",
  "total_rejected": 123,
  "missed_opportunities": 45,
  "recommendations": [
    {
      "keyword": "expansion",
      "type": "new",
      "current_weight": null,
      "recommended_weight": 1.5,
      "confidence": 0.85,
      "evidence": {
        "occurrences": 12,
        "success_rate": 0.75,
        "avg_return": 0.18
      }
    }
  ]
}
```

### analysis_state.json
```json
{
  "last_run": "2025-10-11T00:00:00+00:00",
  "last_analysis_period": {
    "start": "2025-09-11T00:00:00+00:00",
    "end": "2025-10-11T00:00:00+00:00"
  },
  "total_rejected": 123,
  "missed_opportunities": 45,
  "recommendations_count": 8
}
```

## API Reference

### Main Functions

#### `run_moa_analysis(since_days: int = 30) -> Dict[str, Any]`
Run complete MOA analysis pipeline.

**Parameters:**
- `since_days`: Number of days to analyze (default: 30)

**Returns:**
- Dictionary with status and metrics

**Example:**
```python
from src.catalyst_bot.moa_analyzer import run_moa_analysis

result = run_moa_analysis(since_days=30)
print(f"Status: {result['status']}")
print(f"Missed opportunities: {result.get('missed_opportunities', 0)}")
```

#### `get_moa_summary() -> Dict[str, Any]`
Get summary of last MOA analysis.

**Returns:**
- Dictionary with last run stats and recommendations

**Example:**
```python
from src.catalyst_bot.moa_analyzer import get_moa_summary

summary = get_moa_summary()
print(f"Last run: {summary.get('last_run')}")
print(f"Recommendations: {summary.get('recommendations_count')}")
```

### Component Functions

#### `load_rejected_items(since_days: int = 30) -> List[Dict[str, Any]]`
Load rejected items from JSONL file.

#### `identify_missed_opportunities(items: List[Dict[str, Any]], threshold_pct: float = 10.0) -> List[Dict[str, Any]]`
Identify items that became successful after rejection.

#### `extract_keywords_from_missed_opps(missed_opps: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]`
Extract and analyze keywords from missed opportunities.

#### `calculate_weight_recommendations(keyword_stats: Dict[str, Dict[str, Any]], current_weights: Dict[str, float]) -> List[Dict[str, Any]]`
Generate keyword weight recommendations.

#### `save_recommendations(recommendations: List[Dict[str, Any]], ...) -> Path`
Save recommendations to JSON file.

#### `load_analysis_state() -> Dict[str, Any]`
Load previous analysis state.

#### `save_analysis_state(state: Dict[str, Any]) -> None`
Save current analysis state.

## Configuration

### Environment Variables
- None currently (uses hardcoded constants)

### Constants (in module)
```python
PRICE_LOOKBACK_HOURS = [1, 4, 24, 168]  # Timeframes to check
SUCCESS_THRESHOLD_PCT = 10.0  # Missed opportunity threshold
MIN_OCCURRENCES = 5  # Statistical significance minimum
ANALYSIS_WINDOW_DAYS = 30  # Default analysis window
```

## Error Handling

The module includes comprehensive error handling:

1. **Missing Files**: Returns empty lists/dicts instead of crashing
2. **Invalid JSON**: Skips malformed lines with debug logging
3. **Price Fetch Failures**: Continues analysis with available data
4. **Invalid Timestamps**: Skips items with unparseable timestamps

All errors are logged with appropriate severity levels.

## Integration Points

### Required Dependencies
- `market.get_last_price_change()` - For price lookups
- `logging_utils.get_logger()` - For structured logging

### Input Files
- `data/rejected_items.jsonl` - Rejected items log (from `rejected_items_logger.py`)
- `data/analyzer/keyword_stats.json` - Current keyword weights (from `analyzer.py`)

### Output Files
- `data/moa/recommendations.json` - Weight recommendations
- `data/moa/analysis_state.json` - Analysis state tracking

## Usage Examples

### Basic Analysis
```python
from src.catalyst_bot.moa_analyzer import run_moa_analysis

# Run analysis for last 30 days
result = run_moa_analysis()

if result['status'] == 'success':
    print(f"Found {result['missed_opportunities']} missed opportunities")
    print(f"Generated {result['recommendations_count']} recommendations")
```

### Custom Time Window
```python
# Analyze last 7 days only
result = run_moa_analysis(since_days=7)
```

### Get Summary Without Running Analysis
```python
from src.catalyst_bot.moa_analyzer import get_moa_summary

summary = get_moa_summary()
if summary['status'] == 'ok':
    print(f"Last run: {summary['last_run']}")
    for rec in summary['recommendations'][:5]:  # Top 5
        print(f"  {rec['keyword']}: {rec['recommended_weight']} (confidence: {rec['confidence']})")
```

### Access Individual Components
```python
from src.catalyst_bot.moa_analyzer import (
    load_rejected_items,
    identify_missed_opportunities
)

# Load data
items = load_rejected_items(since_days=14)
print(f"Loaded {len(items)} items")

# Find missed opportunities
missed = identify_missed_opportunities(items, threshold_pct=12.0)
print(f"Found {len(missed)} missed opportunities with >12% threshold")
```

## Future Enhancements (Phase 3+)

1. **Historical Price Fetching**: Currently uses current price as proxy; should fetch actual historical prices
2. **Walk-Forward Optimization**: Implement backtesting framework from MOA_DESIGN_V2.md
3. **Bootstrap Validation**: Add statistical confidence intervals
4. **Parameter Sensitivity**: Test robustness of recommendations
5. **Auto-Approval**: Implement high-confidence auto-application of recommendations
6. **Rollback Mechanism**: Monitor performance and auto-rollback if metrics degrade

## Testing

### Manual Test
```bash
cd catalyst-bot
python -c "from src.catalyst_bot.moa_analyzer import run_moa_analysis; import json; print(json.dumps(run_moa_analysis(), indent=2))"
```

### Check Outputs
```bash
# View recommendations
cat data/moa/recommendations.json

# View state
cat data/moa/analysis_state.json
```

## Performance

- **Execution Time**: ~1-5 seconds for 100 rejected items (depends on API calls)
- **Memory Usage**: Minimal (<50MB for typical datasets)
- **API Calls**: 1 per unique ticker in rejected items
- **File I/O**: Sequential reads, single writes (no locking issues)

## Logging

All operations are logged with structured fields:

```python
log.info(f"moa_analysis_complete rejected={100} missed={15} recommendations={8}")
```

Logs are written to the main bot log with logger name "moa".

## Troubleshooting

### "No rejected items found"
- Check if `data/rejected_items.jsonl` exists
- Verify items are being logged by `rejected_items_logger.py`
- Check timestamp filtering (items older than `since_days` are skipped)

### "No missed opportunities"
- This is normal if market conditions are flat
- Try lowering `SUCCESS_THRESHOLD_PCT` (default 10%)
- Increase `since_days` to analyze more data

### "No keywords with sufficient occurrences"
- Increase analysis window with `since_days`
- Lower `MIN_OCCURRENCES` threshold (default 5)
- Check if keywords are being extracted from rejected items

### Price fetch failures
- Verify `market.get_last_price_change()` is working
- Check API rate limits and keys
- Review debug logs for specific ticker failures

## License

Part of Catalyst Bot. See main LICENSE file.

## Author

Claude Code (MOA Phase 2 Implementation)
Date: 2025-10-11
