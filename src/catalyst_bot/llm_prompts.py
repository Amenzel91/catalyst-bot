"""
LLM Prompt Templates
====================

Specialized prompts for different SEC filing types optimized for Gemini 2.0 Flash.

Based on research findings:
- Zero-shot prompting works best for financial data
- Specialized prompts improve accuracy
- Context-aware sentiment calibration
- Filing-specific data extraction

Author: Claude Code
Date: 2025-10-11
"""

# Keyword Extraction Prompt (used for all SEC documents)
KEYWORD_EXTRACTION_PROMPT = """Analyze this SEC filing and extract trading keywords that indicate material events.  # noqa: E501

Filing Type: {filing_type}
Title: {title}

Document Content:
{document_text}

Identify material events related to:
- **FDA approvals, clinical trials**: Keywords: fda, clinical, phase_1, phase_2, phase_3, approval, pivotal, trial_results  # noqa: E501
- **Partnerships, collaborations**: Keywords: partnership, collaboration, agreement, joint_venture, strategic_alliance  # noqa: E501
- **Uplisting, exchange changes**: Keywords: uplisting, nasdaq, nyse, exchange, listing
- **Dilution events**: Keywords: dilution, offering, warrant, conversion, public_offering, registered_direct, atm  # noqa: E501
- **Going concern warnings**: Keywords: going_concern, bankruptcy, liquidation, wind_down
- **Earnings**: Keywords: earnings, revenue, eps, guidance, beat, miss
- **Institutional investment**: Keywords: institutional, insider_buying, 13d, 13g

Perform multi-dimensional sentiment analysis:
1. **market_sentiment**: "bullish", "neutral", or "bearish" - overall direction
2. **confidence**: 0.0-1.0 - how confident are you in this analysis?
3. **urgency**: "low", "medium", "high", "critical" - time sensitivity (e.g., FDA approval = high, routine filing = low)  # noqa: E501
4. **risk_level**: "low", "medium", "high" - trading risk (e.g., Phase 3 success = low, early trial = high)  # noqa: E501
5. **institutional_interest**: true/false - any signs of institutional involvement (13D/13G, large deals, tier 1 partners)?  # noqa: E501
6. **retail_hype_score**: 0.0-1.0 - potential for retail excitement (0=boring, 1=meme-worthy)
7. **reasoning**: Brief 1-2 sentence explanation of your assessment

Return JSON matching this schema:
{{
  "keywords": [<list of applicable keywords from above>],
  "sentiment": <float from -1 (bearish) to +1 (bullish)>,
  "confidence": <float from 0 to 1>,
  "summary": "<one sentence summary of material event>",
  "material": <true if material event, false if routine filing>,
  "sentiment_analysis": {{
    "market_sentiment": <"bullish"|"neutral"|"bearish">,
    "confidence": <float 0-1>,
    "urgency": <"low"|"medium"|"high"|"critical">,
    "risk_level": <"low"|"medium"|"high">,
    "institutional_interest": <true|false>,
    "retail_hype_score": <float 0-1>,
    "reasoning": "<brief explanation>"
  }}
}}

If no material events found, return: {{"keywords": [], "material": false, "sentiment": 0.0, "confidence": 0.5, "summary": "Routine filing with no material catalysts", "sentiment_analysis": {{"market_sentiment": "neutral", "confidence": 0.5, "urgency": "low", "risk_level": "low", "institutional_interest": false, "retail_hype_score": 0.0, "reasoning": "No significant catalysts identified"}}}}"""  # noqa: E501

# Earnings Report Prompt (Item 2.02)
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

3. **Calculate Sentiment**:
   - Beat + raised guidance = +0.8 to +1.0
   - Beat + maintained guidance = +0.4 to +0.6
   - Met estimates = -0.2 to +0.2
   - Missed estimates = -0.6 to -0.8
   - Missed + lowered guidance = -0.9 to -1.0

4. **Identify Catalysts**:
   - earnings_beat, earnings_miss, guidance_raise, guidance_cut, revenue_growth, eps_growth

5. **Risk Assessment**:
   - Low: Beat with raised guidance, strong fundamentals
   - Medium: Met estimates or mixed results
   - High: Miss with lowered guidance or going concern warnings

Return JSON matching this schema:
{{
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "beat_or_miss": <"beat"|"meet"|"miss"|"unknown">,
  "guidance": <"raised"|"maintained"|"lowered"|"none"|"unknown">,
  "revenue_actual": "<amount>" or null,
  "revenue_estimate": "<amount>" or null,
  "eps_actual": "<amount>" or null,
  "eps_estimate": "<amount>" or null,
  "catalysts": [<list of catalyst keywords>],
  "summary": "<brief summary>",
  "risk_level": <"low"|"medium"|"high">
}}"""

# Clinical Trial Prompt (Biotech/Pharma)
CLINICAL_TRIAL_PROMPT = """Analyze this biotech/pharma clinical trial SEC filing.

FILING TEXT:
{document_text}

ANALYSIS TASK:
1. **Identify Trial Phase**:
   - Phase 1 (safety) → Sentiment: +0.3 to +0.5
   - Phase 2 (efficacy) → Sentiment: +0.6 to +0.8 if endpoint met
   - Phase 3 (pivotal) → Sentiment: +0.8 to +1.0 if successful
   - Pivotal → Same as Phase 3

2. **Extract Trial Data**:
   - Medical indication (e.g., cancer, diabetes)
   - Primary endpoint status (met/not met)
   - Statistical significance (p-value)
   - Safety profile (favorable/acceptable/concerning)

3. **Determine Sentiment**:
   - Phase 3 success = +0.8 to +1.0
   - Phase 2 success = +0.6 to +0.8
   - Phase 1 success = +0.3 to +0.5
   - Trial failure = -0.7 to -1.0
   - Safety concerns = -0.5 to -0.8

4. **Identify Catalysts**:
   - clinical_success, clinical_failure, fda, phase_1, phase_2, phase_3, pivotal, endpoint_met

5. **Risk Assessment**:
   - Low: Phase 3 success with clear FDA path
   - Medium: Phase 2 success or mixed results
   - High: Trial failure or safety concerns

Return JSON matching this schema:
{{
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "phase": <"phase_1"|"phase_2"|"phase_3"|"pivotal"|"unknown">,
  "indication": "<medical indication>" or null,
  "endpoint_met": <true|false|null>,
  "p_value": "<p-value>" or null,
  "safety_profile": <"favorable"|"acceptable"|"concerning"|"unknown">,
  "catalysts": [<list of catalyst keywords>],
  "summary": "<brief summary>",
  "risk_level": <"low"|"medium"|"high">
}}"""

# Partnership/Deal Prompt
PARTNERSHIP_PROMPT = """Analyze this partnership or collaboration SEC filing.

FILING TEXT:
{document_text}

ANALYSIS TASK:
1. **Extract Partner Information**:
   - Partner name
   - Partner tier:
     * Tier 1: Major pharma (Pfizer, Merck), Fortune 500
     * Tier 2: Mid-size established companies
     * Tier 3: Small/unknown companies

2. **Extract Deal Terms**:
   - Upfront payment amount
   - Total milestone payments
   - Equity component (dilution risk)

3. **Calculate Sentiment**:
   - Tier 1 partner + large deal = +0.7 to +1.0
   - Tier 2 partner + moderate deal = +0.4 to +0.6
   - Tier 3 partner or small deal = +0.1 to +0.3
   - Deal with heavy dilution = -0.3 to +0.2

4. **Identify Catalysts**:
   - partnership, collaboration, tier_1_partner, agreement, strategic_alliance

5. **Risk Assessment**:
   - Low: Tier 1 partner, no dilution, large upfront payment
   - Medium: Tier 2 partner or moderate terms
   - High: Tier 3 partner or significant dilution

Return JSON matching this schema:
{{
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "partner_name": "<partner name>" or null,
  "partner_tier": <"tier_1"|"tier_2"|"tier_3"|"unknown">,
  "deal_value_upfront": "<amount>" or null,
  "deal_value_milestones": "<amount>" or null,
  "dilution_risk": <true|false>,
  "catalysts": [<list of catalyst keywords>],
  "summary": "<brief summary>",
  "risk_level": <"low"|"medium"|"high">
}}"""

# Dilution Event Prompt (424B5, FWP, Offerings)
DILUTION_PROMPT = """Analyze this dilution event (offering, 424B5, FWP).

FILING TEXT:
{document_text}

ANALYSIS TASK:
1. **Identify Offering Type**:
   - Public offering → Sentiment: -0.7 to -0.9
   - Registered direct → Sentiment: -0.6 to -0.8
   - ATM (at-the-market) → Sentiment: -0.3 to -0.5
   - PIPE → Sentiment: -0.5 to -0.7

2. **Extract Deal Terms**:
   - Gross proceeds
   - Number of shares
   - Price per share
   - Discount to market price (%)
   - Warrant coverage (%)
   - Estimated dilution (%)

3. **Calculate Sentiment**:
   - Large discount (>20%) = more bearish
   - Warrant coverage (100%+) = more bearish
   - Small ATM = less bearish (-0.3 to -0.4)
   - Large public offering = very bearish (-0.8 to -1.0)

4. **Identify Catalysts**:
   - dilution, offering, warrant, public_offering, registered_direct, atm, pipe

5. **Risk Assessment**:
   - Low: Small ATM with proceeds for growth
   - Medium: Moderate offering with reasonable terms
   - High: Large offering with heavy discount and warrants

Return JSON matching this schema:
{{
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "offering_type": <"public_offering"|"registered_direct"|"atm"|"pipe"|"unknown">,
  "gross_proceeds": "<amount>" or null,
  "shares_offered": "<number>" or null,
  "price_per_share": "<amount>" or null,
  "discount_to_market": <float percentage> or null,
  "warrant_coverage": "<percentage>" or null,
  "dilution_pct": <float percentage> or null,
  "catalysts": [<list of catalyst keywords>],
  "summary": "<brief summary>",
  "risk_level": <"low"|"medium"|"high">
}}"""

# General 8-K Prompt (fallback for other Item types)
GENERAL_8K_PROMPT = """Analyze this SEC 8-K filing for material trading catalysts.

FILING TEXT:
{document_text}

ANALYSIS TASK:
1. **Identify Filing Items**:
   - Item 1.01: Material agreements → Sentiment varies
   - Item 1.02: Termination agreements → Sentiment: -0.3 to -0.6
   - Item 2.01: Acquisition → Sentiment: +0.3 to +0.7
   - Item 5.02: Officer changes → Sentiment: -0.2 to +0.2
   - Item 8.01: Other events → Sentiment varies widely

2. **Extract Key Information**:
   - Deal size (if applicable)
   - Dilution percentage (if applicable)
   - Warrants/convertibles mentioned

3. **Identify Catalysts**:
   - Categorize event type: material_agreement, acquisition, management_change, etc.

4. **Calculate Sentiment**:
   - Positive catalysts: acquisitions, strategic agreements, major contracts
   - Negative catalysts: terminations, going concern, bankruptcy
   - Neutral: routine filings, minor updates

5. **Risk Assessment**:
   - Low: Positive catalyst with clear value
   - Medium: Mixed or unclear impact
   - High: Negative catalyst or significant uncertainty

Return JSON matching this schema:
{{
  "sentiment": <float -1 to +1>,
  "confidence": <float 0 to 1>,
  "deal_size": "<amount>" or null,
  "dilution_pct": <float> or null,
  "has_warrants": <true|false>,
  "catalysts": [<list of catalyst keywords>],
  "summary": "<brief summary>",
  "risk_level": <"low"|"medium"|"high">
}}"""


def select_prompt_for_filing(document_text: str, filing_type: str) -> tuple[str, str]:
    """
    Select appropriate prompt template based on filing content and type.

    Args:
        document_text: Full or partial filing text
        filing_type: Filing type (e.g., '8-K', '424B5')

    Returns:
        Tuple of (prompt_template, prompt_type) where prompt_type is the schema name
    """
    doc_lower = document_text.lower()

    # Check for earnings report (Item 2.02)
    if "item 2.02" in doc_lower or "results of operations" in doc_lower:
        return EARNINGS_PROMPT, "EarningsAnalysis"

    # Check for clinical trials (biotech/pharma keywords)
    clinical_keywords = [
        "clinical trial",
        "phase 1",
        "phase 2",
        "phase 3",
        "pivotal",
        "endpoint",
        "efficacy",
    ]
    if any(kw in doc_lower for kw in clinical_keywords):
        return CLINICAL_TRIAL_PROMPT, "ClinicalTrialAnalysis"

    # Check for partnerships
    partnership_keywords = [
        "partnership",
        "collaboration",
        "strategic alliance",
        "joint venture",
        "co-develop",
    ]
    if any(kw in doc_lower for kw in partnership_keywords):
        return PARTNERSHIP_PROMPT, "PartnershipAnalysis"

    # Check for dilution events (424B5, FWP, offerings)
    if filing_type in ["424B5", "FWP", "S-1", "S-3"]:
        return DILUTION_PROMPT, "DilutionAnalysis"

    dilution_keywords = [
        "public offering",
        "registered direct",
        "at-the-market",
        "atm offering",
        "pipe",
    ]
    if any(kw in doc_lower for kw in dilution_keywords):
        return DILUTION_PROMPT, "DilutionAnalysis"

    # Default to general 8-K analysis
    return GENERAL_8K_PROMPT, "SEC8KAnalysis"
