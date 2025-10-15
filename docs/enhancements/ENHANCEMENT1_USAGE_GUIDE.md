# Enhancement #1: Multi-Dimensional Sentiment - Quick Usage Guide

## For Developers

### How the Data Flows

```
SEC Filing / News Item
         |
         v
    LLM Analysis (Gemini/Claude)
         |
         v
Enhanced Prompt Requests 6 Dimensions
         |
         v
JSON Response with sentiment_analysis
         |
         v
  Pydantic Validation (SentimentAnalysis model)
         |
         v
Confidence Filtering (>= 0.5)
         |
         v
   Blend with Existing Sentiment
         |
         v
Attach to ScoredItem Metadata
         |
         v
   Available for Downstream Use
```

## Quick Start Examples

### 1. Accessing Multi-Dimensional Sentiment in Alerts

```python
def format_alert(scored_item, news_item):
    # Basic info
    ticker = news_item.ticker
    sentiment = scored_item.sentiment

    # Multi-dimensional fields (if available)
    urgency = getattr(scored_item, 'urgency', 'medium')
    risk_level = getattr(scored_item, 'risk_level', 'medium')
    institutional = getattr(scored_item, 'institutional_interest', False)
    retail_hype = getattr(scored_item, 'retail_hype_score', 0.0)
    reasoning = getattr(scored_item, 'sentiment_reasoning', '')

    # Format based on urgency
    if urgency == 'critical':
        prefix = "🚨 URGENT"
    elif urgency == 'high':
        prefix = "⚡ HIGH PRIORITY"
    else:
        prefix = "📊"

    # Build alert message
    message = f"{prefix} {ticker}: {news_item.title}\n"
    message += f"Risk: {risk_level.upper()} | "
    message += f"Institutional: {'Yes' if institutional else 'No'}\n"

    if retail_hype > 0.7:
        message += f"🔥 High Retail Hype ({retail_hype:.0%})\n"

    if reasoning:
        message += f"📝 {reasoning}\n"

    return message
```

### 2. Priority-Based Alert Filtering

```python
def should_send_alert(scored_item):
    """Filter alerts based on multi-dimensional criteria."""

    # Get multi-dim fields
    urgency = getattr(scored_item, 'urgency', 'low')
    risk_level = getattr(scored_item, 'risk_level', 'high')
    confidence = getattr(scored_item, 'sentiment_confidence', 0.5)
    institutional = getattr(scored_item, 'institutional_interest', False)

    # Priority rules
    if urgency == 'critical':
        return True  # Always send critical alerts

    if urgency == 'high' and risk_level == 'low' and confidence > 0.8:
        return True  # High urgency + low risk + high confidence

    if institutional and confidence > 0.75:
        return True  # Institutional interest with good confidence

    if urgency in ['low', 'medium'] and risk_level == 'high':
        return False  # Skip low-urgency high-risk items

    # Default to existing scoring logic
    return scored_item.source_weight > threshold
```

### 3. Building Custom Analytics

```python
def analyze_sentiment_distribution(scored_items):
    """Analyze multi-dimensional sentiment across a batch of items."""

    urgency_counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
    risk_counts = {'low': 0, 'medium': 0, 'high': 0}
    institutional_count = 0
    high_hype_count = 0

    for item in scored_items:
        # Count urgency levels
        urgency = getattr(item, 'urgency', None)
        if urgency:
            urgency_counts[urgency] += 1

        # Count risk levels
        risk = getattr(item, 'risk_level', None)
        if risk:
            risk_counts[risk] += 1

        # Count institutional interest
        if getattr(item, 'institutional_interest', False):
            institutional_count += 1

        # Count high retail hype (>0.7)
        hype = getattr(item, 'retail_hype_score', 0.0)
        if hype > 0.7:
            high_hype_count += 1

    return {
        'urgency_distribution': urgency_counts,
        'risk_distribution': risk_counts,
        'institutional_interest': institutional_count,
        'high_retail_hype': high_hype_count
    }
```

### 4. Creating Smart Filters

```python
def create_institutional_filter():
    """Filter for institutional-interest events only."""
    def filter_func(scored_item):
        return getattr(scored_item, 'institutional_interest', False)
    return filter_func

def create_low_risk_filter():
    """Filter for low-risk opportunities."""
    def filter_func(scored_item):
        risk = getattr(scored_item, 'risk_level', 'high')
        confidence = getattr(scored_item, 'sentiment_confidence', 0.0)
        return risk == 'low' and confidence > 0.8
    return filter_func

def create_hype_detection_filter():
    """Filter for potential retail hype plays."""
    def filter_func(scored_item):
        hype = getattr(scored_item, 'retail_hype_score', 0.0)
        urgency = getattr(scored_item, 'urgency', 'low')
        return hype > 0.8 or (hype > 0.6 and urgency in ['high', 'critical'])
    return filter_func

# Usage
institutional_items = filter(create_institutional_filter(), scored_items)
low_risk_items = filter(create_low_risk_filter(), scored_items)
hype_plays = filter(create_hype_detection_filter(), scored_items)
```

## Field Reference

### market_sentiment
- **Type**: "bullish" | "neutral" | "bearish"
- **Use**: Overall market direction
- **Example**: Use for visual indicators (🟢 bullish, ⚪ neutral, 🔴 bearish)

### confidence
- **Type**: float (0.0-1.0)
- **Use**: Filter low-quality predictions
- **Threshold**: >= 0.5 (configurable)
- **Example**: `if confidence > 0.8: send_high_priority_alert()`

### urgency
- **Type**: "low" | "medium" | "high" | "critical"
- **Use**: Time sensitivity of the catalyst
- **Example**:
  - critical: FDA approval, merger announcement
  - high: Partnership deal, earnings beat
  - medium: Analyst upgrade, contract win
  - low: Routine filing, minor update

### risk_level
- **Type**: "low" | "medium" | "high"
- **Use**: Trading risk assessment
- **Example**:
  - low: Phase 3 success, tier 1 partnership
  - medium: Phase 2 results, moderate deal
  - high: Early-stage trial, speculative news

### institutional_interest
- **Type**: boolean
- **Use**: Indicates institutional involvement
- **Signs**: 13D/13G filing, large deal, tier 1 partner
- **Example**: Create separate alert channel for institutional plays

### retail_hype_score
- **Type**: float (0.0-1.0)
- **Use**: Potential for retail excitement
- **Example**:
  - 0.8-1.0: High meme potential
  - 0.5-0.8: Moderate retail interest
  - 0.0-0.5: Low retail appeal

### reasoning
- **Type**: string
- **Use**: Human-readable explanation
- **Example**: "FDA approval removes major regulatory risk and opens path to commercialization"

## Common Patterns

### Pattern 1: High-Priority Alert
```python
def is_high_priority(item):
    return (
        item.urgency in ['high', 'critical'] and
        item.risk_level in ['low', 'medium'] and
        item.sentiment_confidence > 0.7
    )
```

### Pattern 2: Institutional Play
```python
def is_institutional_play(item):
    return (
        item.institutional_interest and
        item.confidence > 0.75 and
        item.retail_hype_score < 0.5  # Not overhyped
    )
```

### Pattern 3: Retail Momentum
```python
def is_retail_momentum(item):
    return (
        item.retail_hype_score > 0.7 and
        item.market_sentiment == 'bullish' and
        item.urgency in ['high', 'critical']
    )
```

### Pattern 4: Risk-Adjusted Alert
```python
def calculate_risk_adjusted_score(item):
    base_score = item.source_weight

    # Adjust for urgency
    urgency_multiplier = {
        'critical': 1.5,
        'high': 1.2,
        'medium': 1.0,
        'low': 0.8
    }

    # Adjust for risk
    risk_multiplier = {
        'low': 1.3,
        'medium': 1.0,
        'high': 0.7
    }

    urgency = getattr(item, 'urgency', 'medium')
    risk = getattr(item, 'risk_level', 'medium')

    return base_score * urgency_multiplier[urgency] * risk_multiplier[risk]
```

## Logging and Debugging

### Check if Multi-Dimensional Sentiment is Applied

Look for these log messages:

**Success:**
```
multi_dim_sentiment_applied ticker=XYZBIO market_sentiment=bullish urgency=critical risk=low confidence=0.95
```

**Rejection (low confidence):**
```
multi_dim_sentiment_rejected_low_confidence ticker=TEST confidence=0.35
```

**Parse Failure:**
```
multi_dim_sentiment_parse_failed err=ValidationError: 1 validation error...
```

### Debug Missing Fields

```python
def debug_multi_dim_fields(scored_item):
    """Print all multi-dimensional fields for debugging."""
    fields = [
        'market_sentiment',
        'sentiment_confidence',
        'urgency',
        'risk_level',
        'institutional_interest',
        'retail_hype_score',
        'sentiment_reasoning'
    ]

    print(f"Multi-dimensional fields for item:")
    for field in fields:
        value = getattr(scored_item, field, None)
        if value is not None:
            print(f"  {field}: {value}")
        else:
            print(f"  {field}: NOT SET")
```

## Best Practices

1. **Always use getattr() with defaults**: Fields may not be present in all items
   ```python
   urgency = getattr(scored_item, 'urgency', 'medium')  # Good
   urgency = scored_item.urgency  # Bad - may raise AttributeError
   ```

2. **Check confidence before trusting multi-dim data**:
   ```python
   if getattr(scored_item, 'sentiment_confidence', 0.0) > 0.7:
       # Use multi-dimensional fields
   ```

3. **Combine with existing scoring**:
   ```python
   if scored_item.source_weight > 2.0 and urgency == 'critical':
       # High confidence alert
   ```

4. **Log your filters**:
   ```python
   if should_alert:
       log.info(f"alert_sent urgency={urgency} risk={risk} confidence={conf}")
   ```

## Troubleshooting

### Issue: Multi-dimensional fields not appearing

**Check:**
1. Is LLM returning `sentiment_analysis` in JSON response?
2. Is confidence >= 0.5?
3. Are there any parse errors in logs?

**Solution:**
```python
# Check raw data
if hasattr(item, 'raw') and item.raw:
    sentiment_data = item.raw.get('sentiment_analysis')
    print(f"Raw sentiment data: {sentiment_data}")
```

### Issue: Confidence too low

**Check:**
- LLM prompt quality
- Document text quality
- Filing type appropriateness

**Solution:**
- Adjust confidence threshold if needed (currently 0.5)
- Improve prompt with more examples
- Use specialized prompts for filing type

### Issue: Unexpected validation errors

**Check:**
- LLM response format
- Field value constraints

**Solution:**
```python
from catalyst_bot.llm_schemas import SentimentAnalysis

try:
    sentiment = SentimentAnalysis(**data)
except Exception as e:
    print(f"Validation error: {e}")
    print(f"Data: {data}")
```

## Performance Notes

- **Minimal Overhead**: Pydantic validation is <1ms per item
- **No Extra LLM Calls**: Uses existing LLM responses
- **Opt-in Processing**: Only activates when multi-dim data present
- **Backward Compatible**: Existing flows unchanged

---

**For Questions or Issues:**
- Check logs for `multi_dim_sentiment_*` messages
- Run test suite: `python test_enhancement1.py`
- Review implementation in `src/catalyst_bot/classify.py` (lines 466-655)
