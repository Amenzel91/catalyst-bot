# Enhancement #2: Source Credibility Scoring System

## Overview

The Source Credibility Scoring System is a 3-tier framework that weights news sources based on reliability and quality. This enhancement automatically adjusts classification scores to prioritize high-credibility sources (regulatory filings, premium news) while de-emphasizing low-credibility sources (unknown blogs, unverified outlets).

## Architecture

### Components

1. **`src/catalyst_bot/source_credibility.py`** - Core credibility scoring module
   - Tier definitions and weights
   - Domain extraction utilities
   - Source classification functions

2. **`src/catalyst_bot/classify.py`** - Integration with classification pipeline
   - Applies credibility weights to relevance scores
   - Attaches credibility metadata to scored items
   - Logs credibility distribution metrics

3. **`test_source_credibility.py`** - Test suite
   - Validates domain extraction
   - Tests tier classification
   - Verifies weight calculations

## Tier Structure

### Tier 1: HIGH CREDIBILITY (1.5x multiplier)

**Regulatory Sources**
- `sec.gov` - U.S. Securities and Exchange Commission official filings

**Premium Financial News**
- `bloomberg.com` - Bloomberg Terminal news and analysis
- `reuters.com` - Reuters financial news and data
- `wsj.com` - Wall Street Journal
- `ft.com` - Financial Times

**Rationale**: These sources have rigorous fact-checking, editorial standards, and legal accountability. Regulatory filings are authoritative primary sources.

### Tier 2: MEDIUM CREDIBILITY (1.0x multiplier - neutral)

**Professional PR Wires**
- `globenewswire.com` - GlobeNewswire press release distribution
- `businesswire.com` - Business Wire press release distribution
- `prnewswire.com` - PR Newswire press release distribution
- `accesswire.com` - AccessWire press release distribution

**Financial News Outlets**
- `marketwatch.com` - MarketWatch financial news
- `cnbc.com` - CNBC financial news
- `benzinga.com` - Benzinga financial news

**Rationale**: Professional distribution channels with verified company sources, but content is promotional. Financial news outlets are established but less rigorous than premium sources.

### Tier 3: LOW CREDIBILITY (0.5x multiplier - downweighted)

**Unknown Sources**
- Any domain not explicitly listed in Tiers 1-2
- Personal blogs, promotional sites, unverified outlets

**Rationale**: Without verification, these sources may contain misinformation, pump-and-dump schemes, or low-quality analysis.

## How It Works

### 1. Domain Extraction

```python
from catalyst_bot.source_credibility import extract_domain

url = "https://www.sec.gov/Archives/edgar/filing.html"
domain = extract_domain(url)  # Returns: "sec.gov"
```

Handles various URL formats:
- Full URLs with protocols
- URLs without protocols (adds https://)
- Subdomains (extracts base domain)
- Special TLDs (handles properly)

### 2. Tier Classification

```python
from catalyst_bot.source_credibility import get_source_tier

tier = get_source_tier("https://www.bloomberg.com/news")  # Returns: 1
tier = get_source_tier("https://www.globenewswire.com")   # Returns: 2
tier = get_source_tier("https://random-blog.com")         # Returns: 3
```

### 3. Weight Application

```python
from catalyst_bot.source_credibility import get_source_weight

weight = get_source_weight("https://www.sec.gov/filing")  # Returns: 1.5
weight = get_source_weight("https://www.marketwatch.com") # Returns: 1.0
weight = get_source_weight("https://unknown-blog.com")    # Returns: 0.5
```

### 4. Integration with Classification

The credibility weight is automatically applied during classification:

```python
# In classify.py
credibility_weight = get_source_weight(item.canonical_url)
combined_source_weight = legacy_source_weight * credibility_weight
relevance = keyword_score * combined_source_weight
```

**Example Impact**:

| Source | Base Score | Tier | Weight | Final Score |
|--------|-----------|------|--------|-------------|
| SEC.gov | 100 | 1 | 1.5x | **150** |
| GlobeNewswire | 100 | 2 | 1.0x | **100** |
| Unknown Blog | 100 | 3 | 0.5x | **50** |

This ensures that a regulatory filing gets 3x more weight than an unknown blog with the same keyword matches.

## Logging and Monitoring

### Individual Item Logging

When a low-credibility source is encountered, a debug log is emitted:

```
DEBUG source_credibility_downweight url=https://penny-stock-blog.com/pump tier=3 weight=0.50
```

### Batch Distribution Logging

Use `log_credibility_distribution()` to analyze batches of news items:

```python
from catalyst_bot.classify import log_credibility_distribution

# After fetching a batch of news items
log_credibility_distribution(news_items)
```

Outputs:
```
INFO source_credibility_distribution total=100 tier1_high=15(15.0%) tier2_medium=50(50.0%) tier3_low=35(35.0%) avg_weight=0.975
```

This helps identify:
- Overall source quality in your feeds
- Potential feed contamination (high % of tier 3)
- Source diversity metrics

## Metadata Attached to Scored Items

Each `ScoredItem` now includes credibility metadata:

```python
scored_item.source_credibility_tier      # int: 1, 2, or 3
scored_item.source_credibility_weight    # float: 1.5, 1.0, or 0.5
scored_item.source_credibility_category  # str: regulatory, premium_news, pr_wire, etc.
```

This metadata can be used for:
- Filtering alerts by minimum tier
- Analytics on source quality trends
- Debugging classification decisions

## Testing

### Running the Test Suite

```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
python test_source_credibility.py
```

**Expected Output**:
```
======================================================================
SOURCE CREDIBILITY SCORING SYSTEM - TEST SUITE
======================================================================

TEST 1: Domain Extraction ............................ PASSED
TEST 2: Tier Classification .......................... PASSED
TEST 3: Weight Calculation ........................... PASSED
TEST 4: Category Assignment .......................... PASSED
TEST 5: Tier Summary ................................. PASSED
TEST 6: Impact on Classification Scores .............. PASSED

FINAL RESULTS
======================================================================
Tests passed: 6/6
Success rate: 100.0%

[SUCCESS] All tests PASSED
```

### Test Coverage

1. **Domain Extraction** - Validates parsing of various URL formats
2. **Tier Classification** - Ensures correct tier assignment for known sources
3. **Weight Calculation** - Verifies multiplier values match tier definitions
4. **Category Assignment** - Checks source categorization (regulatory, premium_news, etc.)
5. **Tier Summary** - Validates summary generation with source counts
6. **Score Impact** - Demonstrates real-world effect on classification scores

## Extending the System

### Adding New Tier 1 Sources

Edit `src/catalyst_bot/source_credibility.py`:

```python
CREDIBILITY_TIERS = {
    # ... existing entries ...

    "barrons.com": {
        "tier": 1,
        "weight": 1.5,
        "category": "premium_news",
        "description": "Barron's financial news",
    },
}
```

### Adding New Tier 2 Sources

```python
CREDIBILITY_TIERS = {
    # ... existing entries ...

    "investors.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "financial_news",
        "description": "Investor's Business Daily",
    },
}
```

### Adjusting Weights (Advanced)

If you want to fine-tune the multipliers:

```python
# Current values
DEFAULT_TIER_WEIGHTS = {
    1: 1.5,  # HIGH
    2: 1.0,  # MEDIUM
    3: 0.5,  # LOW
}

# Example: More aggressive weighting
DEFAULT_TIER_WEIGHTS = {
    1: 2.0,  # HIGH - stronger boost
    2: 1.0,  # MEDIUM - unchanged
    3: 0.3,  # LOW - stronger penalty
}
```

**Note**: Update all tier definitions if you change weights globally.

## Integration Points

### 1. Classification Pipeline

The credibility weight is applied in `classify.py` during the relevance calculation:

```python
def classify(item: NewsItem, keyword_weights=None) -> ScoredItem:
    # ... existing code ...

    credibility_weight = get_source_weight(item.canonical_url)
    combined_source_weight = source_weight * credibility_weight
    relevance = keyword_score * combined_source_weight

    # ... rest of classification ...
```

### 2. Alert Filtering (Future Enhancement)

You can filter alerts by minimum tier:

```python
# Example: Only send alerts for Tier 1 and Tier 2 sources
min_tier = 2
if scored_item.source_credibility_tier <= min_tier:
    send_alert(scored_item)
```

### 3. Analytics and Reporting

Track source quality over time:

```python
from collections import Counter

tier_distribution = Counter()
for scored_item in daily_items:
    tier_distribution[scored_item.source_credibility_tier] += 1

print(f"Tier 1: {tier_distribution[1]} items")
print(f"Tier 2: {tier_distribution[2]} items")
print(f"Tier 3: {tier_distribution[3]} items")
```

## Performance Considerations

- **Domain extraction**: O(1) - Simple string parsing
- **Tier lookup**: O(1) - Dictionary lookup
- **Memory overhead**: Minimal - Only stores tier definitions (< 1KB)
- **Classification impact**: Negligible - Adds one multiplication per item

The credibility system adds virtually no performance overhead to the classification pipeline.

## Backward Compatibility

The system is fully backward compatible:

- Existing classification logic unchanged
- Legacy `source_weight` from `config.rss_sources` still applied
- Credibility weight multiplies with legacy weight (not replaces)
- If no URL available, defaults to neutral (1.0x weight)

Example:
```python
# Legacy source weight (from config.rss_sources)
legacy_weight = 1.2  # e.g., BusinessWire

# New credibility weight
credibility_weight = 1.0  # Tier 2 (BusinessWire)

# Combined (multiplicative)
final_weight = 1.2 * 1.0 = 1.2
```

## Common Issues and Troubleshooting

### Issue: Unexpected tier assignment

**Symptom**: A known source is classified as Tier 3 (unknown)

**Cause**: Domain extraction might be returning a subdomain or different format than expected

**Solution**: Check the extracted domain:
```python
from catalyst_bot.source_credibility import extract_domain
print(extract_domain(url))
```

Add the specific domain variant to `CREDIBILITY_TIERS`.

### Issue: Low credibility scores for legitimate sources

**Symptom**: Good sources getting downweighted

**Cause**: Source not in Tier 1 or Tier 2 definitions

**Solution**: Add the source to the appropriate tier in `source_credibility.py`

### Issue: Need to temporarily adjust weights

**Symptom**: Want to test different multiplier values

**Solution**: Edit tier definitions directly or add an environment variable override:

```python
import os

# In source_credibility.py
TIER_1_WEIGHT = float(os.getenv("CREDIBILITY_TIER1_WEIGHT", "1.5"))
TIER_2_WEIGHT = float(os.getenv("CREDIBILITY_TIER2_WEIGHT", "1.0"))
TIER_3_WEIGHT = float(os.getenv("CREDIBILITY_TIER3_WEIGHT", "0.5"))
```

Then set in environment:
```bash
export CREDIBILITY_TIER1_WEIGHT=2.0
export CREDIBILITY_TIER3_WEIGHT=0.3
```

## Summary of Changes

### Files Created

1. **`src/catalyst_bot/source_credibility.py`** (365 lines)
   - Core credibility scoring logic
   - Tier definitions and utilities
   - Fully documented with docstrings

2. **`test_source_credibility.py`** (247 lines)
   - Comprehensive test suite
   - 6 test categories
   - Clear pass/fail reporting

3. **`ENHANCEMENT_2_GUIDE.md`** (this file)
   - Complete implementation guide
   - Usage examples
   - Troubleshooting tips

### Files Modified

1. **`src/catalyst_bot/classify.py`**
   - Added credibility weight integration (lines 450-524)
   - Added metadata attachment (lines 657-675)
   - Added `log_credibility_distribution()` function (lines 98-149)
   - Imported credibility functions (line 27)

## Next Steps

1. **Monitor Impact**: Track how credibility weighting affects alert quality
2. **Tune Weights**: Adjust multipliers based on real-world performance
3. **Expand Tiers**: Add more sources as you discover them
4. **Analytics**: Build dashboards showing source quality trends
5. **Alert Filtering**: Implement minimum tier thresholds for critical alerts

## Support

For questions or issues:
1. Check the test suite for usage examples
2. Review docstrings in `source_credibility.py`
3. Enable debug logging to see credibility decisions in real-time
4. Consult this guide's troubleshooting section

---

**Implementation Date**: 2025-10-12
**Status**: Complete and Tested
**Test Coverage**: 100% (6/6 tests passing)
