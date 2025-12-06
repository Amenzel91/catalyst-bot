# SEC LLM Enhancement - Phase 1 Implementation Plan

**Status:** Ready for Implementation
**Estimated Time:** 8-10 hours
**Expected Impact:** 30% improvement in actionable intelligence
**Priority:** After chart/sentiment fixes complete

---

## Overview

Phase 1 focuses on three critical enhancements to SEC filing extraction:
1. 8-K item-specific routing and extraction
2. Numeric value parsing (dollar amounts, percentages)
3. Forward-looking guidance extraction

---

## Task 1: 8-K Item-Specific Extraction (4-6 hours)

### Files to Modify
- `src/catalyst_bot/llm_prompts.py` - Add 6 new prompts
- `src/catalyst_bot/sec_llm_analyzer.py` - Add item detection logic
- `src/catalyst_bot/llm_schemas.py` - Add item-specific schemas

### Step 1.1: Add Item-Specific Prompts (2 hours)

Add to `llm_prompts.py` after line 323:

```python
# 8-K Item 1.01: Material Agreements
ITEM_1_01_PROMPT = """Analyze 8-K Item 1.01 Material Agreement.

Extract structured information about this material agreement:

**Required Fields:**
- Counterparty name and industry type
- Agreement type (license, supply, distribution, joint development, settlement)
- Financial terms (upfront payment, milestone payments, royalty rates)
- Duration and term
- Effective date and closing conditions
- Key contract terms
- Termination rights

Return JSON:
{{
  "item": "1.01",
  "item_title": "Material Agreements",
  "counterparty": "<company name>",
  "counterparty_type": "pharma|tech|financial|government|consumer|industrial|other",
  "agreement_type": "license|supply|distribution|joint_development|settlement|strategic_alliance|manufacturing",
  "deal_size_usd": <number or null>,
  "upfront_payment_usd": <number or null>,
  "milestone_payments_usd": <number or null>,
  "royalty_rate_pct": <float or null>,
  "duration_years": <number or null>,
  "effective_date": "YYYY-MM-DD or null",
  "key_terms": [<list of important clauses or conditions>],
  "exclusivity": <true|false|null>,
  "geographic_scope": "us|global|regional|null",
  "has_termination_rights": <bool>,
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "risk_level": "low|medium|high",
  "trading_thesis": "<1 sentence: why traders would buy/sell on this news>",
  "expected_price_action": "rally|breakout|neutral|selloff|volatility_spike"
}}

If unable to extract a field, return null. Focus on extracting concrete financial terms and timeline information.
"""

# 8-K Item 1.02: Termination of Material Agreements
ITEM_1_02_PROMPT = """Analyze 8-K Item 1.02 Termination of Material Agreement.

Extract structured information about this agreement termination:

**Required Fields:**
- Which agreement was terminated
- Reason for termination (mutual, breach, strategic shift, etc.)
- Financial impact (settlement costs, write-downs, lost revenue)
- Effective termination date
- Whether a replacement agreement exists

Return JSON:
{{
  "item": "1.02",
  "item_title": "Termination of Material Agreement",
  "terminated_agreement": "<name/description of agreement>",
  "counterparty": "<company name>",
  "termination_reason": "mutual|breach|strategic_shift|merger|bankruptcy|other",
  "termination_type": "voluntary|involuntary|automatic_expiration",
  "settlement_cost_usd": <number or null>,
  "lost_revenue_impact_usd": <number or null>,
  "write_down_usd": <number or null>,
  "effective_date": "YYYY-MM-DD or null",
  "replacement_exists": <bool>,
  "replacement_party": "<name or null>",
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "risk_level": "low|medium|high",
  "trading_thesis": "<1 sentence explanation>",
  "expected_price_action": "rally|neutral|selloff|volatility_spike"
}}

Note: Terminations are generally negative unless replaced by better agreement or mutual/strategic.
"""

# 8-K Item 2.01: Acquisition or Disposition
ITEM_2_01_PROMPT = """Analyze 8-K Item 2.01 Acquisition or Disposition of Assets.

Extract structured information about this M&A transaction:

**Required Fields:**
- Target/asset name and description
- Transaction type (acquisition, merger, asset sale, divestiture)
- Purchase price and financing structure
- Expected closing date
- Accretion/dilution impact
- Strategic rationale

Return JSON:
{{
  "item": "2.01",
  "item_title": "Acquisition or Disposition of Assets",
  "transaction_type": "acquisition|merger|asset_sale|divestiture|joint_venture",
  "target_name": "<company or asset name>",
  "target_description": "<brief description of business/asset>",
  "purchase_price_usd": <number or null>,
  "cash_component_usd": <number or null>,
  "stock_component_shares": <number or null>,
  "debt_assumed_usd": <number or null>,
  "earnout_max_usd": <number or null>,
  "financing_source": "cash|stock|debt|combination",
  "expected_close_date": "YYYY-MM-DD or null",
  "regulatory_approvals_required": <bool>,
  "accretion_dilution": "accretive|dilutive|neutral|unknown",
  "accretion_pct": <float or null>,
  "strategic_rationale": "<brief explanation>",
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "risk_level": "low|medium|high",
  "trading_thesis": "<1 sentence explanation>",
  "expected_price_action": "rally|breakout|neutral|selloff|volatility_spike"
}}

Note: Acquisitions generally positive if strategic fit, negative if overpriced or poorly financed.
"""

# 8-K Item 5.02: Departure/Appointment of Officers or Directors
ITEM_5_02_PROMPT = """Analyze 8-K Item 5.02 Officer/Director Departure or Appointment.

Extract structured information about this leadership change:

**Required Fields:**
- Person name and previous role
- Type of change (resignation, termination, appointment, retirement)
- New role/title (if appointment)
- Reason for change (if disclosed)
- Replacement identified

Return JSON:
{{
  "item": "5.02",
  "item_title": "Departure/Appointment of Officers or Directors",
  "change_type": "resignation|termination|appointment|retirement|promotion",
  "person_name": "<name>",
  "previous_role": "<title/position>",
  "new_role": "<title/position or null>",
  "is_ceo": <bool>,
  "is_cfo": <bool>,
  "is_board_member": <bool>,
  "departure_reason": "personal|strategic_differences|performance|health|other|not_disclosed",
  "departure_voluntary": <bool or null>,
  "replacement_identified": <bool>,
  "replacement_name": "<name or null>",
  "replacement_background": "<brief description or null>",
  "effective_date": "YYYY-MM-DD or null",
  "severance_usd": <number or null>,
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "risk_level": "low|medium|high",
  "trading_thesis": "<1 sentence explanation>",
  "expected_price_action": "rally|neutral|selloff|volatility_spike"
}}

Note: CEO/CFO departures are negative unless strong replacement. New appointments can be positive if experienced.
"""

# 8-K Item 7.01: Regulation FD Disclosure
ITEM_7_01_PROMPT = """Analyze 8-K Item 7.01 Regulation FD Disclosure.

This is a catch-all item for material non-public information disclosed under Reg FD.
Extract the key disclosure and assess trading implications.

**Required Fields:**
- Disclosure topic/type
- Key details
- Financial impacts (if any)
- Forward-looking implications

Return JSON:
{{
  "item": "7.01",
  "item_title": "Regulation FD Disclosure",
  "disclosure_type": "earnings_preview|business_update|contract_announcement|litigation_update|strategic_initiative|other",
  "disclosure_topic": "<brief description>",
  "key_details": "<summary of material information>",
  "financial_impact_usd": <number or null>,
  "revenue_impact": "positive|negative|neutral|unknown",
  "forward_guidance_provided": <bool>,
  "guidance_details": "<summary or null>",
  "presentation_or_conference": "<event name or null>",
  "event_date": "YYYY-MM-DD or null",
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "risk_level": "low|medium|high",
  "trading_thesis": "<1 sentence explanation>",
  "expected_price_action": "rally|breakout|neutral|selloff|volatility_spike"
}}

Note: Reg FD disclosures vary widely - positive or negative depends on content.
"""

# 8-K Item 8.01: Other Events
ITEM_8_01_PROMPT = """Analyze 8-K Item 8.01 Other Events.

This is the broadest catch-all item. Extract key event details and assess materiality.

**Required Fields:**
- Event type and description
- Material impacts
- Timeline and implications

Return JSON:
{{
  "item": "8.01",
  "item_title": "Other Events",
  "event_type": "business_update|product_announcement|legal_matter|regulatory_update|strategic_initiative|other",
  "event_description": "<detailed summary of event>",
  "involves_deal": <bool>,
  "deal_size_usd": <number or null>,
  "involves_product": <bool>,
  "product_name": "<name or null>",
  "involves_litigation": <bool>,
  "litigation_stage": "filed|settled|dismissed|ongoing|null",
  "involves_regulatory": <bool>,
  "regulatory_body": "<FDA|SEC|FTC|etc or null>",
  "timeline": "<expected dates or timeline>",
  "financial_impact_usd": <number or null>,
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "risk_level": "low|medium|high",
  "trading_thesis": "<1 sentence explanation>",
  "expected_price_action": "rally|breakout|neutral|selloff|volatility_spike"
}}

Note: Item 8.01 requires careful analysis as materiality varies widely.
"""
```

### Step 1.2: Add Item Detection Logic (1 hour)

Add to `sec_llm_analyzer.py` after line 380:

```python
import re
from typing import List, Tuple, Optional

def extract_8k_items(document_text: str) -> List[Tuple[str, str, str]]:
    """
    Extract 8-K item numbers and their content from document.

    Args:
        document_text: Full 8-K filing text

    Returns:
        List of (item_number, item_title, item_content) tuples

    Example:
        [
            ("1.01", "Entry into Material Agreement", "On October 21..."),
            ("9.01", "Financial Statements", "See attached...")
        ]
    """
    items = []

    # Regex to match Item headers (e.g., "Item 1.01", "Item 2.02")
    # Matches: Item 1.01, Item 1.01., Item 1.01:, ITEM 1.01, etc.
    item_pattern = re.compile(
        r'Item\s+(\d+)\.(\d+)[.:\s]*([^\n]+)?',
        re.IGNORECASE
    )

    # Find all item matches
    matches = list(item_pattern.finditer(document_text))

    for i, match in enumerate(matches):
        item_num = f"{match.group(1)}.{match.group(2).zfill(2)}"
        item_title = (match.group(3) or "").strip()

        # Extract content between this item and next item
        start_pos = match.end()
        if i < len(matches) - 1:
            end_pos = matches[i + 1].start()
        else:
            # Last item - take rest of document (up to signatures)
            signature_match = re.search(r'SIGNATURE', document_text[start_pos:], re.IGNORECASE)
            if signature_match:
                end_pos = start_pos + signature_match.start()
            else:
                end_pos = len(document_text)

        item_content = document_text[start_pos:end_pos].strip()

        # Only include items with substantial content (>100 chars)
        if len(item_content) > 100:
            items.append((item_num, item_title, item_content))

    return items


def select_prompt_for_8k_item(item_number: str, item_content: str) -> Tuple[str, str]:
    """
    Route 8-K items to specialized prompts.

    Args:
        item_number: Item number (e.g., "1.01", "2.02")
        item_content: Text content of the item

    Returns:
        (prompt_template, analysis_type) tuple
    """
    from .llm_prompts import (
        ITEM_1_01_PROMPT, ITEM_1_02_PROMPT, ITEM_2_01_PROMPT,
        ITEM_5_02_PROMPT, ITEM_7_01_PROMPT, ITEM_8_01_PROMPT,
        EARNINGS_PROMPT, GENERAL_8K_PROMPT
    )

    # Map item numbers to prompts
    item_routing = {
        "1.01": (ITEM_1_01_PROMPT, "Item101Analysis"),
        "1.02": (ITEM_1_02_PROMPT, "Item102Analysis"),
        "2.01": (ITEM_2_01_PROMPT, "Item201Analysis"),
        "2.02": (EARNINGS_PROMPT, "EarningsAnalysis"),  # Existing earnings prompt
        "5.02": (ITEM_5_02_PROMPT, "Item502Analysis"),
        "7.01": (ITEM_7_01_PROMPT, "Item701Analysis"),
        "8.01": (ITEM_8_01_PROMPT, "Item801Analysis"),
    }

    # Get prompt for this item (or use general fallback)
    return item_routing.get(item_number, (GENERAL_8K_PROMPT, "SEC8KAnalysis"))
```

### Step 1.3: Update Main Extraction Function (1 hour)

Modify `extract_keywords_from_document()` in `sec_llm_analyzer.py` around line 461:

```python
async def extract_keywords_from_document(
    document_text: str,
    filing_type: str = "8-K",
    ticker: str = "",
    use_multi_item_extraction: bool = True  # NEW PARAMETER
) -> Dict[str, Any]:
    """
    Extract keywords from SEC document using LLM with item-level routing.

    If use_multi_item_extraction=True and filing is 8-K:
    - Parse document into items
    - Extract each item separately
    - Combine results with item-level context

    Otherwise uses existing single-pass extraction.
    """

    # Check if this is an 8-K that should use multi-item extraction
    if use_multi_item_extraction and filing_type == "8-K":
        items = extract_8k_items(document_text)

        if items:
            # Multi-item extraction
            log.info(
                "sec_8k_multi_item_extraction ticker=%s items=%s",
                ticker,
                [item[0] for item in items]
            )

            all_results = []
            combined_keywords = set()
            combined_sentiment = 0.0
            combined_confidence = 0.0

            for item_num, item_title, item_content in items:
                # Select prompt for this specific item
                prompt_template, analysis_type = select_prompt_for_8k_item(item_num, item_content)

                # Format prompt with item content
                prompt = prompt_template.format(
                    filing_type=filing_type,
                    title=item_title,
                    document_text=item_content[:5000]  # Limit to 5KB per item
                )

                # Extract for this item
                try:
                    item_result = await _extract_single_item(prompt, analysis_type, ticker)
                    item_result["item_number"] = item_num
                    item_result["item_title"] = item_title
                    all_results.append(item_result)

                    # Accumulate keywords and sentiment
                    combined_keywords.update(item_result.get("keywords", []))
                    combined_sentiment += item_result.get("sentiment", 0.0)
                    combined_confidence += item_result.get("confidence", 0.5)

                except Exception as e:
                    log.warning(
                        "sec_item_extraction_failed ticker=%s item=%s err=%s",
                        ticker, item_num, str(e)
                    )

            # Combine results
            num_items = len(all_results) if all_results else 1
            return {
                "keywords": list(combined_keywords),
                "sentiment": combined_sentiment / num_items,
                "confidence": combined_confidence / num_items,
                "material": any(r.get("material", False) for r in all_results),
                "summary": _combine_item_summaries(all_results),
                "items": all_results,  # Include item-level details
                "filing_type": filing_type,
                "ticker": ticker,
            }

    # Fallback to existing single-pass extraction
    # (existing code continues here...)
```

---

## Task 2: Numeric Value Parsing (2-3 hours)

### Step 2.1: Update All Prompts with Numeric Fields (1.5 hours)

For each existing prompt in `llm_prompts.py`, ensure numeric fields return numbers:

**Before:**
```python
"deal_size": "<amount>",
"dilution_pct": "<percentage>"
```

**After:**
```python
"deal_size_usd": <number or null>,
"deal_size_display": "<$50M or null>",
"dilution_pct": <float 0-100 or null>
```

Files to update:
- EARNINGS_PROMPT (lines 67-110)
- CLINICAL_TRIAL_PROMPT (lines 112-158)
- PARTNERSHIP_PROMPT (lines 160-205)
- DILUTION_PROMPT (lines 207-256)
- GENERAL_8K_PROMPT (lines 258-323)

### Step 2.2: Update Pydantic Schemas (1 hour)

Add to `llm_schemas.py`:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List

class NumericFieldsMixin:
    """Mixin for schemas with USD amounts and percentages."""

    @validator('*', pre=True)
    def parse_numeric_strings(cls, v, field):
        """Convert string numbers to floats."""
        if field.name.endswith('_usd') or field.name.endswith('_pct'):
            if isinstance(v, str):
                # Handle "unknown", "N/A", etc.
                if v.lower().strip() in ('unknown', 'n/a', 'na', 'none', 'null', ''):
                    return None
                # Try to parse number
                try:
                    # Remove $ and common formatting
                    cleaned = v.replace('$', '').replace(',', '').strip()
                    # Handle millions/billions
                    if 'M' in cleaned or 'million' in cleaned.lower():
                        num = float(cleaned.replace('M', '').replace('million', '').strip())
                        return num * 1_000_000
                    elif 'B' in cleaned or 'billion' in cleaned.lower():
                        num = float(cleaned.replace('B', '').replace('billion', '').strip())
                        return num * 1_000_000_000
                    else:
                        return float(cleaned)
                except (ValueError, AttributeError):
                    return None
        return v


class Item101Analysis(BaseModel, NumericFieldsMixin):
    """Schema for 8-K Item 1.01 Material Agreement analysis."""

    item: str = "1.01"
    item_title: str = "Material Agreements"
    counterparty: Optional[str] = None
    counterparty_type: Optional[str] = None
    agreement_type: Optional[str] = None
    deal_size_usd: Optional[float] = Field(None, description="Total deal size in USD")
    upfront_payment_usd: Optional[float] = None
    milestone_payments_usd: Optional[float] = None
    royalty_rate_pct: Optional[float] = Field(None, ge=0, le=100)
    duration_years: Optional[int] = None
    effective_date: Optional[str] = None
    key_terms: List[str] = []
    exclusivity: Optional[bool] = None
    geographic_scope: Optional[str] = None
    has_termination_rights: bool = False
    sentiment: float = Field(0.0, ge=-1.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    risk_level: str = "medium"
    trading_thesis: str = ""
    expected_price_action: str = "neutral"

# Similar for Item102Analysis, Item201Analysis, Item502Analysis, etc.
```

### Step 2.3: Add Validation Tests (0.5 hours)

Create `tests/test_numeric_extraction.py`:

```python
import pytest
from catalyst_bot.llm_schemas import Item101Analysis

def test_usd_parsing():
    """Test USD amount parsing from various formats."""

    # Test million notation
    data = {"deal_size_usd": "$50M"}
    result = Item101Analysis(**data)
    assert result.deal_size_usd == 50_000_000

    # Test billion notation
    data = {"deal_size_usd": "1.5B"}
    result = Item101Analysis(**data)
    assert result.deal_size_usd == 1_500_000_000

    # Test direct number
    data = {"deal_size_usd": 25000000}
    result = Item101Analysis(**data)
    assert result.deal_size_usd == 25_000_000

    # Test unknown value
    data = {"deal_size_usd": "unknown"}
    result = Item101Analysis(**data)
    assert result.deal_size_usd is None
```

---

## Task 3: Forward Guidance Extraction (2 hours)

### Step 3.1: Enhance Earnings Prompt (1 hour)

Update EARNINGS_PROMPT in `llm_prompts.py` (lines 67-110):

```python
EARNINGS_PROMPT = """You are analyzing an SEC 8-K Item 2.02 earnings report for a penny stock.

FILING TEXT:
{document_text}

ANALYSIS TASK:
1. **Extract Financial Metrics**:
   - Revenue (actual vs estimate)
   - EPS (actual vs estimate)

2. **Determine Beat/Miss/Meet**:
   - Compare actual to estimates
   - Consider guidance changes

3. **Extract Forward Guidance** (CRITICAL):
   - Previous guidance range (if any)
   - New/updated guidance range
   - Period (Q1 2025, FY 2025, etc.)
   - Key assumptions from management commentary
   - Change magnitude

4. **Calculate Sentiment**:
   - Beat + raised guidance = +0.8 to +1.0
   - Beat + maintained guidance = +0.4 to +0.6
   - Met estimates = -0.2 to +0.2
   - Missed estimates = -0.6 to -0.8
   - Missed + lowered guidance = -0.9 to -1.0

Return JSON matching this schema:
{{
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "beat_or_miss": <"beat"|"meet"|"miss"|"unknown">,
  "guidance": <"raised"|"maintained"|"lowered"|"none"|"unknown">,
  "revenue_actual_usd": <number or null>,
  "revenue_estimate_usd": <number or null>,
  "eps_actual": <number or null>,
  "eps_estimate": <number or null>,
  "forward_guidance": {{
    "guidance_provided": <bool>,
    "guidance_change": "raised|lowered|maintained|first_time|withdrawn|none",
    "metric": "revenue|eps|ebitda|margin|other",
    "previous_range_low": <number or null>,
    "previous_range_high": <number or null>,
    "new_range_low": <number or null>,
    "new_range_high": <number or null>,
    "change_magnitude_pct": <float or null>,
    "period": "<Q1 2025|FY 2025|etc or null>",
    "key_assumptions": "<management commentary or null>"
  }},
  "catalysts": [<list of catalyst keywords>],
  "summary": "<brief summary>",
  "risk_level": <"low"|"medium"|"high">
}}
"""
```

### Step 3.2: Update EarningsAnalysis Schema (0.5 hours)

Add to `llm_schemas.py`:

```python
class ForwardGuidance(BaseModel):
    """Forward-looking guidance extracted from earnings."""

    guidance_provided: bool = False
    guidance_change: str = "none"  # raised, lowered, maintained, first_time, withdrawn
    metric: str = "revenue"  # revenue, eps, ebitda, margin
    previous_range_low: Optional[float] = None
    previous_range_high: Optional[float] = None
    new_range_low: Optional[float] = None
    new_range_high: Optional[float] = None
    change_magnitude_pct: Optional[float] = Field(None, description="% change in midpoint")
    period: Optional[str] = None  # "Q1 2025", "FY 2025"
    key_assumptions: Optional[str] = None

class EarningsAnalysis(BaseModel, NumericFieldsMixin):
    """Enhanced earnings analysis with forward guidance."""

    sentiment: float = Field(0.0, ge=-1.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    beat_or_miss: str = "unknown"
    guidance: str = "unknown"
    revenue_actual_usd: Optional[float] = None
    revenue_estimate_usd: Optional[float] = None
    eps_actual: Optional[float] = None
    eps_estimate: Optional[float] = None
    forward_guidance: ForwardGuidance = ForwardGuidance()  # NEW
    catalysts: List[str] = []
    summary: str = ""
    risk_level: str = "medium"
```

### Step 3.3: Test Guidance Extraction (0.5 hours)

Create test with sample earnings filing:

```python
# tests/test_guidance_extraction.py

async def test_guidance_extraction():
    """Test forward guidance extraction from earnings filing."""

    sample_filing = """
    For the fiscal year 2025, the Company is raising its revenue guidance
    to a range of $180 million to $200 million, up from the previous
    range of $160 million to $180 million. This represents an increase
    of approximately 12.5% at the midpoint.

    EPS guidance is being increased to $2.00 to $2.10, from the prior
    range of $1.80 to $1.90.
    """

    result = await extract_keywords_from_document(
        sample_filing,
        filing_type="8-K",
        ticker="TEST"
    )

    assert result["forward_guidance"]["guidance_provided"] == True
    assert result["forward_guidance"]["guidance_change"] == "raised"
    assert result["forward_guidance"]["new_range_low"] == 180_000_000
    assert result["forward_guidance"]["new_range_high"] == 200_000_000
    assert result["forward_guidance"]["change_magnitude_pct"] > 10
```

---

## Testing & Validation

### Manual Testing Checklist

- [ ] Test 8-K Item 1.01 extraction with real filing
- [ ] Test 8-K Item 2.02 earnings with guidance
- [ ] Test 8-K with multiple items (1.01 + 2.02)
- [ ] Test numeric parsing ($50M → 50000000)
- [ ] Test percentage parsing (15% → 15.0)
- [ ] Test unknown/null value handling
- [ ] Test forward guidance extraction
- [ ] Verify sentiment scores improved

### Integration Testing

```bash
# Run on last 20 8-K filings
python -m catalyst_bot.scripts.test_sec_extraction --limit 20

# Compare before/after extraction quality
python -m catalyst_bot.scripts.compare_extraction \
    --before baseline_results.json \
    --after phase1_results.json
```

---

## Deployment Steps

1. **Backup current system:**
   ```bash
   git commit -am "Backup before Phase 1 SEC LLM enhancements"
   ```

2. **Apply changes:**
   - Update `llm_prompts.py` with 6 new item prompts
   - Update `sec_llm_analyzer.py` with item extraction
   - Update `llm_schemas.py` with numeric validation

3. **Test in isolation:**
   ```bash
   pytest tests/test_numeric_extraction.py -v
   pytest tests/test_guidance_extraction.py -v
   ```

4. **Test with real filings:**
   ```bash
   python -m catalyst_bot.scripts.test_sec_extraction --ticker YXT
   ```

5. **Monitor first 24 hours:**
   - Check LLM API costs (should stay within free tier)
   - Verify extraction quality on real alerts
   - Monitor error rates

---

## Expected Outcomes

**Before Phase 1:**
```
Alert: "ACME files 8-K - material event detected"
Sentiment: 0.6 (Bullish)
Score: 12.5
```

**After Phase 1:**
```
Alert: "ACME files 8-K Item 1.01 - $50M Partnership with Pfizer"
Sentiment: 0.75 (Bullish)
Score: 18.2
Details:
- Item: 1.01 (Material Agreement)
- Counterparty: Pfizer Inc. (Tier 1 Pharma)
- Deal Size: $50,000,000
  - Upfront: $20,000,000
  - Milestones: $30,000,000
- Duration: 5 years (exclusive in US)
- Effective: 2025-11-01
- Trading Thesis: Strategic validation from tier 1 partner signals product viability
- Expected Action: Rally on partnership announcement
```

---

## Cost Analysis

**LLM API Usage:**
- Current: ~50 8-K filings/day × 1 call = 50 calls/day
- After Phase 1: ~50 filings/day × 2-3 items = 100-150 calls/day
- Gemini free tier: 1500 calls/day ✅ (still within limit)
- Cost if exceeding: $0.00015/call × 150 = $0.02/day = $7.30/year

**Development Time:**
- Item routing: 4-6 hours
- Numeric parsing: 2-3 hours
- Forward guidance: 2 hours
- Testing: 2 hours
- **Total: 10-13 hours**

**Expected ROI:**
- 30% improvement in actionable intelligence
- Better position sizing decisions (numeric amounts)
- Earlier detection of guidance changes
- Reduced false signals from item misclassification

---

## Next Steps After Phase 1

Once Phase 1 is complete and validated:
- **Phase 2:** Add 10-K/10-Q support + activist investor analysis (12-15 hours)
- **Phase 3:** Multi-pass extraction + SQL deduplication + main loop integration (12-15 hours)

---

**Document Created:** 2025-10-22
**Status:** Ready for Implementation
**Priority:** After chart/sentiment fixes complete
