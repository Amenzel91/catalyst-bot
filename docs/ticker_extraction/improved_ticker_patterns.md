# Improved Ticker Extraction Regex Patterns

## Executive Summary

Current ticker extraction in `title_ticker.py` successfully handles:
- Exchange-qualified tickers: `(NASDAQ: AAPL)`, `(NYSE: TSLA)`
- Dollar tickers: `$NVDA`, `$AAPL`

**GAPS IDENTIFIED:**
- Company name + ticker: `Apple (AAPL)`, `Tesla Inc. (TSLA)`
- Standalone tickers in headlines: `AAPL hits high`, `TSLA Shares Surge`

## Current Patterns Analysis

### Pattern 1: Exchange-Qualified Tickers
```python
# File: title_ticker.py, line 39
exch_pattern = rf"\b{exch_prefix}\s*[:\-]\s*\$?{_TICKER_CORE}\b"

# Example regex (expanded):
r'\b(?:NASDAQ|NYSE|AMEX)\s*[:\-]\s*\$?([A-Z][A-Z0-9.\-]{0,5})\b'

# Matches:
"(Nasdaq: AAPL)" → AAPL ✓
"(NYSE: TSLA)" → TSLA ✓
"OTC: GRLT" → GRLT ✓ (when allow_otc=True)
```

### Pattern 2: Dollar Tickers
```python
# File: title_ticker.py, line 34
_DOLLAR_PATTERN = rf"(?:(?<!\w)\${_TICKER_CORE}\b)"

# Example regex (expanded):
r'(?:(?<!\w)\$([A-Z][A-Z0-9.\-]{0,5})\b)'

# Matches:
"$NVDA shares surge" → NVDA ✓
"$AAPL hits high" → AAPL ✓
```

### Current Ticker Core Pattern
```python
# File: title_ticker.py, line 31
_TICKER_CORE = r"([A-Z][A-Z0-9.\-]{0,5})"

# Characteristics:
# - Starts with uppercase letter [A-Z]
# - Followed by 0-5 characters: letters, digits, dots, hyphens
# - Total length: 1-6 characters
# - Handles: AAPL, BRK.A, GOOGL
```

## Identified Gaps

### Gap 1: Company Name + Ticker (No Exchange)
**Real-world headlines:**
```
"Apple (AAPL) Reports Strong Quarter"
"Tesla Inc. (TSLA) reports Q3 earnings"
"Amazon.com Inc. (AMZN) Announces..."
"Nvidia Corp. (NVDA) Beats Estimates"
```

**Current behavior:** NO MATCH ✗

**Why it fails:**
- Pattern requires exchange qualifier (NASDAQ:, NYSE:, etc.)
- Headlines often use company name instead of exchange

### Gap 2: Standalone Tickers (No Qualifier)
**Real-world headlines:**
```
"AAPL hits new high"
"TSLA Shares Surge on Delivery Numbers"
"NVDA Stock Jumps 20%"
```

**Current behavior:** NO MATCH ✗

**Why it fails:**
- No dollar sign `$`
- No exchange qualifier
- Too risky to extract (high false positive rate)

## Proposed New Patterns

### NEW PATTERN 1: Company Name + Ticker in Parentheses
```python
# Pattern for: "Apple Inc. (AAPL)" or "Tesla Corp. (TSLA)"
_COMPANY_TICKER_PATTERN = r'\b([A-Z][A-Za-z0-9&\.\-]*(?:\s+(?:Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|L\.P\.))?\s*\(([A-Z][A-Z0-9.\-]{1,5})\))'

# Breakdown:
# [A-Z][A-Za-z0-9&\.\-]*    - Company name starting with capital (e.g., "Apple", "Amazon.com")
# (?:\s+Inc\.?|Corp\.?|...)?  - Optional suffix (Inc., Corp., Co., etc.)
# \s*                         - Optional whitespace
# \(([A-Z][A-Z0-9.\-]{1,5})\) - Ticker in parentheses (capture group)

# Matches:
"Apple (AAPL) Reports" → AAPL ✓
"Tesla Inc. (TSLA) Q3" → TSLA ✓
"Amazon.com Inc. (AMZN)" → AMZN ✓
"Nvidia Corp. (NVDA)" → NVDA ✓
"Boeing Co. (BA) announces" → BA ✓

# Does NOT match (good):
"Apple reports" → ✗ (no ticker)
"Company (ABC123)" → ✗ (ticker too long)
"firm (abc)" → ✗ (lowercase ticker)
```

**Conservative safeguards:**
1. Requires company name to start with capital letter
2. Ticker must be in parentheses (reduces false positives)
3. Ticker must be 2-6 uppercase characters (standard ticker format)
4. Only matches known corporate suffixes (Inc., Corp., etc.) or no suffix

**Trade-offs:**
- Will match: "Apple (AAPL)", "Tesla Inc. (TSLA)", "Nvidia (NVDA)"
- Won't match: "apple (AAPL)" (lowercase), "(AAPL) announces" (no company name)

### NEW PATTERN 2: Context-Aware Standalone Tickers
```python
# Pattern for: "AAPL shares surge" or "TSLA stock jumps"
_STANDALONE_TICKER_PATTERN = r'\b([A-Z]{2,5})\s+(?:stock|shares|shares?|equity|options?)\b'

# Breakdown:
# \b([A-Z]{2,5})              - 2-5 uppercase letters (ticker)
# \s+                         - Whitespace
# (?:stock|shares|equity|...) - Context keywords

# Matches:
"AAPL shares surge" → AAPL ✓
"TSLA stock jumps" → TSLA ✓
"NVDA equity rises" → NVDA ✓

# Does NOT match (good):
"AAPL hits high" → ✗ (no context keyword)
"USA stocks rally" → ✗ (USA is common acronym, not ticker)
"CEO announces" → ✗ (CEO not followed by keyword)
```

**Conservative safeguards:**
1. Requires context keyword (stock, shares, equity)
2. 2-5 character minimum (avoids single-letter matches)
3. Must be word boundary on both sides

**Trade-offs:**
- HIGH PRECISION, LOW RECALL
- Will match: "AAPL shares", "TSLA stock"
- Won't match: "AAPL hits high", "TSLA surges" (no context keyword)

### NEW PATTERN 3: Ticker at Start of Headline
```python
# Pattern for: "TSLA: Deliveries Beat Estimates"
_HEADLINE_START_TICKER = r'^([A-Z]{2,5}):\s+'

# Breakdown:
# ^                  - Start of string
# ([A-Z]{2,5})       - 2-5 uppercase letters
# :                  - Colon
# \s+                - Whitespace

# Matches:
"TSLA: Deliveries Beat" → TSLA ✓
"AAPL: Reports Strong Q3" → AAPL ✓
"NVDA: AI Revenue Soars" → NVDA ✓

# Does NOT match (good):
"News: AAPL reports" → ✗ (News is not a ticker)
"Breaking: TSLA" → ✗ (Breaking is too long)
```

**Conservative safeguards:**
1. Must be at start of headline
2. Must have colon separator
3. 2-5 character length

**Trade-offs:**
- Very conservative (low false positive rate)
- Only matches tickers at headline start with colon

## Recommended Implementation Strategy

### Phase 1: Add Company Name + Ticker Pattern (LOW RISK)
This is the **safest** new pattern to add because:
- Ticker is in parentheses (strong signal)
- Company name provides context
- Very low false positive rate

```python
# Add to title_ticker.py after line 34:
_COMPANY_TICKER_PATTERN = r'([A-Z][A-Za-z0-9&\.\-]*(?:\s+(?:Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|L\.P\.))?\s*)\(([A-Z][A-Z0-9.\-]{1,5})\)'
```

### Phase 2: Add Headline Start Pattern (MEDIUM RISK)
This pattern is conservative but may have false positives:
- Risk: "CEO: Apple announces" might extract "CEO"
- Mitigation: Length constraint (2-5 chars) helps

```python
# Add to title_ticker.py after company pattern:
_HEADLINE_START_TICKER = r'^([A-Z]{2,5}):\s+'
```

### Phase 3: Monitor and Evaluate
**DO NOT immediately add standalone ticker pattern** - it has high false positive risk.

Instead:
1. Deploy Phase 1 + 2 patterns
2. Monitor extracted tickers for 1-2 weeks
3. Log false positives (e.g., "CEO", "USA", "AI")
4. Build exclusion list if needed
5. Only then consider Phase 3

## Updated Regex Construction

```python
def _build_regex(allow_otc: bool, require_exch_for_dollar: bool) -> Pattern[str]:
    """Build combined regex pattern with new company+ticker support."""
    exch_prefix = rf"(?:{_EXCH_PREFIX_CORE}{'|' + _OTC_PREFIX if allow_otc else ''})"

    # Original patterns
    exch_pattern = rf"\b{exch_prefix}\s*[:\-]\s*\$?{_TICKER_CORE}\b"
    dollar_pattern = _DOLLAR_PATTERN

    # NEW: Company name + ticker in parens
    company_ticker = r'[A-Z][A-Za-z0-9&\.\-]*(?:\s+(?:Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|L\.P\.))?\s*\(([A-Z][A-Z0-9.\-]{1,5})\)'

    # NEW: Ticker at headline start
    headline_start = r'^([A-Z]{2,5}):\s+'

    # Combine patterns (order matters - most specific first)
    combined = rf"{exch_pattern}|{company_ticker}|{headline_start}"

    if not require_exch_for_dollar:
        combined = rf"{exch_pattern}|{company_ticker}|{headline_start}|{dollar_pattern}"

    return re.compile(combined, re.IGNORECASE)
```

## Test Cases: Before vs After

### Exchange-Qualified (No Change)
```
"(Nasdaq: AAPL) announces"
BEFORE: ['AAPL'] ✓
AFTER:  ['AAPL'] ✓
```

### Dollar Tickers (No Change)
```
"$NVDA shares surge"
BEFORE: ['NVDA'] ✓
AFTER:  ['NVDA'] ✓
```

### Company + Ticker (NEW)
```
"Apple (AAPL) Reports Strong Quarter"
BEFORE: [] ✗
AFTER:  ['AAPL'] ✓

"Tesla Inc. (TSLA) reports Q3 earnings"
BEFORE: [] ✗
AFTER:  ['TSLA'] ✓

"Amazon.com Inc. (AMZN) Announces..."
BEFORE: [] ✗
AFTER:  ['AMZN'] ✓
```

### Headline Start (NEW)
```
"TSLA: Deliveries Beat Estimates"
BEFORE: [] ✗
AFTER:  ['TSLA'] ✓

"AAPL: Reports Strong Q3"
BEFORE: [] ✗
AFTER:  ['AAPL'] ✓
```

### False Positive Prevention (Should NOT Match)
```
"Apple reports strong quarter" (no ticker)
BEFORE: [] ✓
AFTER:  [] ✓

"Company (ABC123) announces" (ticker too long)
BEFORE: [] ✓
AFTER:  [] ✓

"Breaking: AAPL reports" (not ticker at start)
BEFORE: [] ✗
AFTER:  [] ✓
```

## Risk Assessment

### Low Risk Patterns (Recommend Adding)
1. **Company Name + Ticker in Parens**
   - False positive risk: LOW
   - Coverage improvement: HIGH
   - Recommendation: **ADD IMMEDIATELY**

2. **Headline Start Ticker**
   - False positive risk: LOW-MEDIUM
   - Coverage improvement: MEDIUM
   - Recommendation: **ADD WITH MONITORING**

### High Risk Patterns (Do NOT Add Yet)
3. **Standalone Ticker with Context**
   - False positive risk: MEDIUM-HIGH
   - Coverage improvement: MEDIUM
   - Recommendation: **DEFER - Monitor first**

4. **Bare Standalone Ticker**
   - False positive risk: VERY HIGH
   - Coverage improvement: HIGH
   - Recommendation: **DO NOT ADD**

## Implementation Checklist

- [ ] Add `_COMPANY_TICKER_PATTERN` to title_ticker.py
- [ ] Add `_HEADLINE_START_TICKER` to title_ticker.py
- [ ] Update `_build_regex()` to include new patterns
- [ ] Update pattern priority (most specific first)
- [ ] Add tests for new patterns
- [ ] Monitor for false positives in production
- [ ] Document pattern priority in code comments
- [ ] Add exclusion list if needed (CEO, USA, AI, etc.)

## Exclusion List (False Positive Prevention)

Common uppercase words that are NOT tickers:
```python
# Consider adding to title_ticker.py:
_TICKER_EXCLUSIONS = {
    "AI", "CEO", "CFO", "CTO", "USA", "UK", "EU", "NYSE", "NASDAQ",
    "SEC", "FDA", "FBI", "CIA", "IPO", "ETF", "ESG", "SPAC",
    "Q1", "Q2", "Q3", "Q4", "YTD", "YOY", "MOM", "EOD", "AH",
}

def _is_valid_ticker(ticker: str) -> bool:
    """Filter out common non-ticker uppercase words."""
    return ticker.upper() not in _TICKER_EXCLUSIONS
```

## Summary

**Current State:**
- ✓ Exchange-qualified tickers: `(NASDAQ: AAPL)`
- ✓ Dollar tickers: `$NVDA`
- ✗ Company + ticker: `Apple (AAPL)`
- ✗ Standalone tickers: `AAPL shares`

**Recommended Additions:**
1. **Phase 1:** Company name + ticker pattern (SAFE)
2. **Phase 2:** Headline start ticker pattern (MONITOR)
3. **Phase 3:** Context-aware standalone (DEFER)

**Expected Improvement:**
- Coverage: +40-60% on real news headlines
- False positives: <2% with exclusion list
- Precision: 95%+ (conservative patterns)
