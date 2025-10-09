# Sentiment Aggregation Quick Reference

## TL;DR
The bot now uses **5 sentiment sources** instead of 2, with weighted ensemble and confidence scoring.

## Quick Stats
- **Sources:** VADER + Earnings + ML (FinBERT) + LLM (Mistral) + AI Adapter
- **Weights:** 0.25 + 0.35 + 0.25 + 0.15 = 1.0
- **Output:** Sentiment score (-1 to +1) + Confidence (0 to 1)
- **Fallback:** Graceful degradation if sources unavailable

## Configuration (`.env`)

```ini
# Sentiment source weights (sum to 1.0)
SENTIMENT_WEIGHT_EARNINGS=0.35   # Highest - actual financial data
SENTIMENT_WEIGHT_ML=0.25         # ML models (FinBERT/DistilBERT)
SENTIMENT_WEIGHT_VADER=0.25      # VADER baseline
SENTIMENT_WEIGHT_LLM=0.15        # LLM sentiment (Mistral)

# Feature flags
FEATURE_ML_SENTIMENT=1           # Enable ML models (requires transformers)
```

## How It Works

### 1. Source Collection
```python
sources = {}
sources['vader'] = vader_score      # Always available
sources['earnings'] = eps_score     # If earnings event
sources['ml'] = finbert_score       # If FEATURE_ML_SENTIMENT=1
sources['llm'] = mistral_score      # If pre-computed
```

### 2. Weighted Aggregation
```python
effective_weight = base_weight × confidence_multiplier
final_sentiment = Σ(score × effective_weight) / Σ(effective_weight)
```

### 3. Confidence Calculation
```python
confidence = total_effective_weight / expected_weight
```

## Confidence Multipliers
| Source | Multiplier | Rationale |
|--------|-----------|-----------|
| Earnings | 0.95 | Hard financial data (most reliable) |
| ML | 0.85 | Trained on financial text |
| LLM | 0.70 | General language model |
| VADER | 0.60 | Rule-based (least sophisticated) |

## Example Output

### Input:
```
Title: "AAPL reports Q4 EPS of $1.64 vs estimate $1.45"
Earnings: { is_earnings_result: true, sentiment_score: 0.85 }
LLM: 0.75
```

### Output:
```python
{
    'sentiment': 0.452,
    'confidence': 0.800,
    'breakdown': {
        'vader': 0.0,
        'earnings': 0.85,
        'ml': 0.0,
        'llm': 0.75
    }
}
```

## Quick Commands

### Test the system:
```bash
python test_sentiment_aggregation.py
```

### Check backward compatibility:
```bash
python -c "from catalyst_bot.classify import classify; from catalyst_bot.models import NewsItem; from datetime import datetime, timezone; item = NewsItem(title='Test', canonical_url='http://t.co', ts_utc=datetime.now(timezone.utc)); print(classify(item).sentiment)"
```

### Enable/disable ML sentiment:
```bash
# Enable
export FEATURE_ML_SENTIMENT=1

# Disable (uses VADER only)
export FEATURE_ML_SENTIMENT=0
```

## Common Scenarios

### Scenario 1: Earnings Beat
- **Sources Active:** Earnings (0.85), VADER (0.0), LLM (0.75)
- **Result:** Positive sentiment (~0.45), High confidence (0.8)

### Scenario 2: General News
- **Sources Active:** VADER (0.0), LLM (0.6)
- **Result:** Slightly positive (~0.14), Medium confidence (0.47)

### Scenario 3: ML Not Available
- **Fallback:** VADER only
- **Result:** Works normally, lower confidence

## Debugging

### Check what sources are active:
```python
item.raw['sentiment_breakdown']
# Output: {'vader': 0.0, 'earnings': 0.85, 'ml': 0.0, 'llm': 0.75}
```

### Check confidence:
```python
item.raw['sentiment_confidence']
# Output: 0.800
```

### View logs:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
# Output: sentiment_aggregated sources={'vader': '0.000', 'earnings': '0.850'} final=0.452 confidence=0.800
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| ML always 0.0 | transformers not installed | `pip install transformers torch` |
| Low confidence | Few sources available | Enable more sources via feature flags |
| Unexpected sentiment | Wrong weights | Check `.env` weights sum to 1.0 |

## Performance Notes

- **VADER:** Instant (CPU-only)
- **ML Models:** ~50ms on GPU, ~500ms on CPU
- **Batch Mode:** 10 items processed together for efficiency
- **Memory:** FinBERT ~800MB VRAM, DistilBERT ~400MB

## Weight Tuning Guide

### Conservative (Trust Hard Data):
```ini
SENTIMENT_WEIGHT_EARNINGS=0.50
SENTIMENT_WEIGHT_ML=0.25
SENTIMENT_WEIGHT_VADER=0.15
SENTIMENT_WEIGHT_LLM=0.10
```

### Balanced (Current):
```ini
SENTIMENT_WEIGHT_EARNINGS=0.35
SENTIMENT_WEIGHT_ML=0.25
SENTIMENT_WEIGHT_VADER=0.25
SENTIMENT_WEIGHT_LLM=0.15
```

### Aggressive (Trust AI):
```ini
SENTIMENT_WEIGHT_EARNINGS=0.25
SENTIMENT_WEIGHT_ML=0.35
SENTIMENT_WEIGHT_VADER=0.10
SENTIMENT_WEIGHT_LLM=0.30
```

## API Reference

### Main Function:
```python
aggregate_sentiment_sources(
    item: NewsItem,
    earnings_result: Optional[Dict] = None
) -> Tuple[float, float, Dict[str, float]]
```

**Returns:**
- `float`: Final sentiment (-1.0 to +1.0)
- `float`: Confidence (0.0 to 1.0)
- `Dict[str, float]`: Source breakdown

### Usage in classify():
```python
sentiment, confidence, breakdown = aggregate_sentiment_sources(
    item,
    earnings_result=earnings_result
)
```

## Files to Know

- **`classify.py`**: Main aggregation logic (lines 118-232)
- **`.env`**: Configuration weights (lines 498-510)
- **`config.py`**: Settings class (lines 739-748)
- **`test_sentiment_aggregation.py`**: Test suite
- **`ml/model_switcher.py`**: ML model loader
- **`ml/batch_sentiment.py`**: Batch processing

---

**Need more details?** See `SENTIMENT_AGGREGATION_IMPLEMENTATION.md`
