# SEC Alert Integration - Quick Reference

## What Changed?

SEC filings now go through the **main alert system** (`alerts.py`) instead of a separate system. This means SEC filing alerts include BOTH standard metrics AND SEC-specific data.

## Alert Enhancement Logic

### Detection

```python
# In alerts.py, line 2872
is_sec_source = src.startswith("sec_")
```

If the source starts with `"sec_"`, the alert is enhanced with SEC-specific fields.

### Standard Fields (Always Present)

- **Price / Change**: Current price and % change
- **Sentiment**: Local/External/FMP sentiment
- **Score**: Composite sentiment score
- **Float**: Shares available for trading
- **RVol**: Relative volume vs average
- **Short Interest**: % of float shorted (if available)

### SEC-Specific Fields (Only for SEC Sources)

- **📄 SEC Filing Type**: 8-K, 10-Q, 10-K + Item code
- **🎯 Priority**: Critical/High/Medium/Low with score
- **💰 Key Metrics**: Revenue, EPS, margins (with YoY changes)
- **📈 Forward Guidance**: Raised/lowered/maintained
- **🎯 SEC Sentiment**: SEC-specific sentiment analysis

## Data Attachment (for Feed Adapters)

To enable SEC enhancements, attach these fields to `item_dict`:

```python
news_item = {
    "ticker": "AAPL",
    "title": "Apple Reports Q4 Earnings",
    "source": "sec_earnings",  # MUST start with "sec_"

    # Standard fields
    "link": "https://sec.gov/...",
    "ts": "2025-01-15T16:00:00Z",
    "summary": "Apple reported...",

    # SEC-specific fields (all optional)
    "filing_type": "8-K",
    "item_code": "2.02",
    "sec_metrics": NumericMetrics(...),      # Revenue, EPS, margins
    "sec_guidance": GuidanceAnalysis(...),   # Forward guidance
    "sec_sentiment": SECSentimentOutput(...),# SEC sentiment
    "sec_priority": PriorityScore(...),      # Priority tier
}
```

## Priority Tiers

| Tier | Score | Color | Usage |
|------|-------|-------|-------|
| **Critical** | ≥0.8 | 🔴 Red | M&A, earnings beats/misses |
| **High** | ≥0.6 | 🟡 Gold | Significant filings |
| **Medium** | ≥0.4 | 🔵 Blue | Routine filings |
| **Low** | <0.4 | ⚪ Gray | Minor updates |

**Note**: Priority is DISPLAY ONLY. All filings still go through classification and filters.

## Example Alert Output

### SEC Filing Alert (8-K Earnings)

```
🔴 AAPL | 8-K Item 2.02 - Earnings

Apple Inc. reported strong Q4 2024 earnings with revenue...

📄 SEC Filing Type: 8-K Item 2.02
🎯 Priority: 🔴 CRITICAL (0.88)
  • Urgency: 8-K Item 2.02 (earnings) - very time-sensitive

Price / Change: $150.25 / +2.50%
Sentiment: Bullish / External
Score: +0.85

💰 Key Metrics:
  Revenue: $125,000M (📈 +25.5%)
  EPS: $1.85 (📈 +15.2%)
  Gross Margin: 45.2%
  Operating Margin: 28.5%

📈 Forward Guidance:
  ✅ Raised Revenue: $150,000M - $175,000M (high)

🎯 SEC Sentiment: 🟢 Bullish (+0.75)
  *Strong revenue beat with positive forward guidance...*

Float: 🔥 Low Float (15.0M shares)
RVol: 🔥 High RVol (3.5x)
```

### Regular News Alert (Non-SEC)

```
[TSLA] Tesla Announces New Model Launch

Tesla unveiled its latest electric vehicle model...

Price / Change: $200.50 / +1.50%
Sentiment: Bullish
Score: +0.70

Float: 📊 Medium Float (45.0M shares)
RVol: ➡️ Normal RVol (1.2x)

(No SEC-specific fields)
```

## Testing

### Run Integration Tests

```bash
# Test SEC alert enhancements
pytest tests/test_sec_alert_integration.py -v

# Test backward compatibility
pytest tests/test_alerts_indicators_embed.py tests/test_dummy_alert_embed.py -v

# Test original SEC functionality
pytest tests/test_sec_filing_alerts.py -v

# Run all alert tests
pytest tests/test_sec_alert_integration.py tests/test_alerts_indicators_embed.py tests/test_dummy_alert_embed.py tests/test_sec_filing_alerts.py -v
```

### Expected Results

- **16 integration tests**: ✅ All passing
- **3 backward compatibility tests**: ✅ All passing
- **21 SEC filing tests**: ✅ All passing
- **Total**: 40/40 tests passing

## Error Handling

### Graceful Degradation

If SEC data is missing, the alert still works:

- No `sec_metrics`? → No "Key Metrics" field
- No `sec_guidance`? → No "Forward Guidance" field
- No `sec_priority`? → No "Priority" field
- No `sec_sentiment`? → No "SEC Sentiment" field

Filing type badge still appears if `filing_type` is present.

### Error Logging

If SEC enhancement fails, an error is logged but the alert is still sent:

```python
log.warning("sec_alert_enhancement_failed ticker=%s err=%s", ticker, str(e))
```

## Code Locations

### Main Implementation

- **File**: `src/catalyst_bot/alerts.py`
- **Function**: `_build_discord_embed()`
- **Lines**: 2868-3050 (~180 lines)

### Tests

- **Integration Tests**: `tests/test_sec_alert_integration.py` (580 lines)
- **Original SEC Tests**: `tests/test_sec_filing_alerts.py` (699 lines)
- **Backward Compat**: `tests/test_alerts_indicators_embed.py`, `tests/test_dummy_alert_embed.py`

### Related Modules

- **sec_filing_alerts.py**: Original SEC alert formatting (still available for advanced features)
- **filing_prioritizer.py**: Priority scoring logic
- **guidance_extractor.py**: Forward guidance extraction
- **numeric_extractor.py**: Financial metrics extraction

## Migration Notes

### For Developers

1. **Feed Adapters**: Ensure source starts with `"sec_"` for auto-enhancement
2. **Data Attachment**: Attach SEC objects to `item_dict` (see example above)
3. **Testing**: Use `test_sec_alert_integration.py` as template for new tests

### For Users

No changes needed! SEC alerts automatically include enhanced data.

### Deprecation Path

The standalone `sec_filing_alerts.py` can be:
- **Kept**: For advanced features (RAG, buttons, digest)
- **Deprecated**: If basic alerts suffice
- **Recommended**: Keep for now, use alerts.py for basic alerts

## Troubleshooting

### SEC Fields Not Appearing

1. Check source starts with `"sec_"`: `item_dict["source"].startswith("sec_")`
2. Check SEC data attached: `item_dict.get("sec_metrics")`, etc.
3. Check logs for errors: `grep "sec_alert_enhancement_failed" data/logs/bot.jsonl`

### Priority Color Not Applied

1. Check `sec_priority` is attached and has `tier` attribute
2. Check tier is one of: `"critical"`, `"high"`, `"medium"`, `"low"`
3. Verify `PRIORITY_CONFIG` imports correctly from `sec_filing_alerts.py`

### Import Errors

If you see `cannot import name 'PRIORITY_CONFIG'`:
- Ensure import is from `sec_filing_alerts`, not `filing_prioritizer`
- Correct: `from .sec_filing_alerts import PRIORITY_CONFIG`
- Wrong: `from .filing_prioritizer import PRIORITY_CONFIG`

## Summary

**Wave 3 Complete**: SEC filings now flow through the unified alert system with automatic enhancement based on source detection. All standard metrics are preserved, SEC-specific fields are added, and backward compatibility is maintained.

**Key Takeaway**: One alert system, two types of data (standard + SEC), zero regressions.
