# LLM Enhancements: Low-Hanging Fruit for RX 6800 AMD GPU

**Generated**: 2025-10-12
**Hardware Constraint**: AMD RX 6800 (16GB VRAM) - Cannot run 2 LLMs simultaneously
**Budget Constraint**: <$50/month additional spend
**Source Document**: LLM Applications for Catalyst-Driven Penny Stock Trading Implementation Guide

## Executive Summary

This document identifies **7 practical LLM enhancements** that can be implemented without requiring large-scale infrastructure changes or exceeding budget constraints. All recommendations are compatible with single-LLM execution on AMD RX 6800.

## Priority Matrix

| Enhancement | Impact | Effort | Cost | ROI | Priority |
|------------|--------|--------|------|-----|----------|
| Multi-dimensional Sentiment | HIGH | 4-6h | FREE | ⭐⭐⭐⭐⭐ | 1 |
| Source Credibility Scoring | HIGH | 3-4h | FREE | ⭐⭐⭐⭐⭐ | 2 |
| Sentiment Velocity Tracking | HIGH | 6-8h | FREE | ⭐⭐⭐⭐ | 3 |
| Enhanced Pydantic Schemas | MED-HIGH | 4-5h | FREE | ⭐⭐⭐⭐ | 4 |
| Semantic Cache Optimization | MEDIUM | 3-4h | FREE | ⭐⭐⭐ | 5 |
| Prompt Compression | MEDIUM | 2-3h | SAVES $15-30/mo | ⭐⭐⭐ | 6 |
| FinBERT Confirmation | HIGH | 8-12h | FREE (CPU) | ⭐⭐⭐⭐ | 7 |

---

## 🥇 Enhancement #1: Multi-Dimensional Sentiment Extraction

### Current State
- Single-label sentiment: Bullish/Neutral/Bearish
- No confidence scores
- No granular dimensions

### Proposed Improvement
Extract **6 sentiment dimensions** from existing LLM calls:

1. **Market Sentiment**: Overall bullish/bearish direction
2. **Confidence Level**: 0-100% (how certain is the LLM?)
3. **Urgency**: Low/Medium/High/Critical
4. **Risk Level**: How risky is this catalyst?
5. **Institutional Interest**: Are big players mentioned?
6. **Retail Hype**: Social media/forum activity indicators

### Implementation
```python
# Update llm_schemas.py
class SentimentAnalysis(BaseModel):
    market_sentiment: Literal["bullish", "neutral", "bearish"]
    confidence: float  # 0.0-1.0
    urgency: Literal["low", "medium", "high", "critical"]
    risk_level: Literal["low", "medium", "high"]
    institutional_interest: bool
    retail_hype_score: float  # 0.0-1.0
    reasoning: str  # Brief explanation
```

### Benefits
- **Accuracy**: Research shows 75-78% accuracy (6% improvement)
- **Filtering**: Reject low-confidence classifications early
- **Urgency Scoring**: Prioritize time-sensitive catalysts
- **Zero Cost**: Uses existing LLM calls, just better prompts

### Effort
- 4-6 hours (update prompts, schemas, classification logic)
- No new dependencies
- Backward compatible with existing sentiment

---

## 🥈 Enhancement #2: Source Credibility Scoring

### Current State
- All news sources treated equally
- No historical accuracy tracking
- No domain reputation system

### Proposed Improvement
Implement **3-tier credibility system**:

**Tier 1 (HIGH Credibility - Weight: 1.5x)**
- SEC.gov filings
- Bloomberg Terminal
- Reuters
- WSJ, FT

**Tier 2 (MEDIUM Credibility - Weight: 1.0x)**
- GlobeNewswire
- Business Wire
- PR Newswire
- MarketWatch

**Tier 3 (LOW Credibility - Weight: 0.5x)**
- Unknown blogs
- Reddit/Twitter (unless verified accounts)
- Promotional sites

### Implementation
```python
# Create src/catalyst_bot/source_credibility.py
CREDIBILITY_TIERS = {
    "sec.gov": {"tier": 1, "weight": 1.5, "track_record": 0.95},
    "bloomberg.com": {"tier": 1, "weight": 1.5, "track_record": 0.92},
    "globenewswire.com": {"tier": 2, "weight": 1.0, "track_record": 0.78},
    # ... etc
}

def get_source_weight(url: str) -> float:
    domain = extract_domain(url)
    return CREDIBILITY_TIERS.get(domain, {}).get("weight", 0.5)
```

### Benefits
- **Reduces False Positives**: Filter out low-quality pump sources
- **Adaptive**: Can track accuracy over time
- **Simple**: Just a lookup table initially
- **Zero Cost**: No API calls needed

### Effort
- 3-4 hours (implement scoring, integrate with classify.py)
- No new dependencies

---

## 🥉 Enhancement #3: Sentiment Velocity Tracking

### Current State
- Point-in-time sentiment snapshots
- No trend analysis
- Slow-building narratives missed

### Proposed Improvement
Track **sentiment change over time**:

- **15-minute velocity**: Rapid sentiment shifts (flash catalysts)
- **1-hour momentum**: Building momentum
- **24-hour trend**: Sustained narratives

### Implementation
```python
# Add to sentiment_sources.py
def calculate_sentiment_velocity(ticker: str, window: str = "1h") -> dict:
    """
    Compare current sentiment to historical sentiment.
    Returns:
        {
            "current_score": 0.75,
            "prev_score": 0.45,
            "velocity": +0.30,  # Bullish acceleration
            "trend": "accelerating",
            "confidence": 0.85
        }
    """
    # Pull from recent sentiment cache
    # Calculate delta
    # Return velocity metrics
```

### Storage
```python
# data/sentiment_history.jsonl
{"ticker": "TSLA", "ts": "2025-01-15T14:30:00Z", "score": 0.75, "label": "bullish"}
{"ticker": "TSLA", "ts": "2025-01-15T15:30:00Z", "score": 0.82, "label": "bullish"}
# Velocity = +0.07 (accelerating)
```

### Benefits
- **Narrative Tracking**: Identify multi-day buildups
- **Early Detection**: Catch momentum before peak
- **MOA Integration**: Analyze velocity vs. outcome patterns
- **Zero Cost**: Just adds timestamped logging

### Effort
- 6-8 hours (implement tracking, storage, velocity calculations)
- No new dependencies

---

## 🏅 Enhancement #4: Enhanced Pydantic Schemas with LLM Validation

### Current State
- Basic Pydantic validation
- No semantic consistency checks
- Keywords/sentiment sometimes misaligned

### Proposed Improvement
Add **LLM-powered validation layer**:

```python
class CatalystClassification(BaseModel):
    keywords: List[str]
    sentiment: Literal["bullish", "neutral", "bearish"]
    confidence: float

    @model_validator(mode='after')
    def validate_keyword_sentiment_alignment(self) -> 'CatalystClassification':
        """Ensure keywords match sentiment (using LLM)."""
        if self.confidence < 0.5:
            return self  # Skip validation for low confidence

        # Quick LLM check: "Do these keywords [{keywords}]
        # match {sentiment} sentiment?"
        # If mismatch: lower confidence or re-extract
        return self
```

### Benefits
- **Consistency**: Catch contradictory classifications
- **Quality Gates**: Block bad data from entering pipeline
- **Self-Healing**: Can auto-correct minor issues
- **Marginal Cost**: Only validates high-confidence items

### Effort
- 4-5 hours (implement validators, test edge cases)
- Uses existing LLM (Gemini/Claude), just adds extra validation calls

---

## 🏆 Enhancement #5: Semantic Cache Optimization

### Current State
- No semantic deduplication
- Same news from multiple sources = multiple LLM calls
- Wasted API quota

### Proposed Improvement
Implement **content fingerprinting** to detect duplicates:

```python
import hashlib

def get_content_fingerprint(title: str, summary: str) -> str:
    """Generate semantic fingerprint for deduplication."""
    # Normalize: lowercase, remove punctuation, extract key terms
    normalized = normalize_text(title + " " + summary)
    key_terms = extract_keywords(normalized)  # Just TF-IDF, no LLM
    fingerprint = hashlib.md5("".join(sorted(key_terms)).encode()).hexdigest()
    return fingerprint

# Cache structure
{
    "fingerprint_abc123": {
        "classification": {...},
        "ttl": "2025-01-15T16:00:00Z",  # 1 hour cache
        "sources": ["source1", "source2"]  # Track duplicates
    }
}
```

### Benefits
- **Cost Savings**: 20-30% reduction in LLM calls (research finding)
- **Faster**: Instant cache hits
- **Quota Protection**: Preserve Gemini free tier limits
- **Zero Cost**: Just adds local caching layer

### Effort
- 3-4 hours (implement fingerprinting, cache layer)
- No new dependencies (uses hashlib, built-in)

---

## 💰 Enhancement #6: Prompt Compression

### Current State
- Full article text sent to LLM
- High token usage on long SEC filings
- Billing scales with input length

### Proposed Improvement
Implement **smart truncation** before LLM calls:

1. **Extract Key Sections**: Focus on first/last paragraphs + tables
2. **Remove Boilerplate**: Strip legal disclaimers, footers
3. **Summarize Long Docs**: Use extractive summarization first

```python
def compress_sec_filing(text: str, max_tokens: int = 2000) -> str:
    """
    Intelligently compress SEC filing for LLM processing.
    Priority:
    1. Title + first paragraph
    2. Any tables/bullet points
    3. Last paragraph
    4. Fill remaining tokens from middle sections
    """
    sections = extract_sections(text)
    compressed = prioritize_sections(sections, max_tokens)
    return compressed
```

### Benefits
- **Cost Reduction**: 30-50% fewer tokens = $15-30/month savings
- **Faster**: Smaller prompts = faster responses
- **Quality**: Focus LLM on relevant content only
- **Preserves Accuracy**: Research shows minimal accuracy loss

### Effort
- 2-3 hours (implement compression, test on sample filings)
- No new dependencies

---

## 🧪 Enhancement #7: FinBERT Sentiment Confirmation (CPU-Based)

### Current State
- Single LLM sentiment source (Gemini/Claude)
- No independent validation
- Potential for LLM hallucination

### Proposed Improvement
Add **FinBERT as secondary validator** (runs on CPU):

```python
# Uses HuggingFace transformers (CPU-optimized)
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

class FinBERTValidator:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        self.model.eval()  # CPU inference

    def validate_sentiment(self, text: str, llm_sentiment: str) -> dict:
        """
        Run FinBERT as secondary check.
        Returns:
            {
                "finbert_label": "positive",
                "finbert_confidence": 0.92,
                "agreement": True,  # Matches LLM?
                "confidence_delta": 0.15  # How much they disagree
            }
        """
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        outputs = self.model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        # Compare to LLM result
```

### Benefits
- **Validation**: 85-90% agreement = high confidence
- **Conflict Resolution**: When they disagree, flag for review
- **Cost**: FREE (CPU inference)
- **AMD Compatible**: Runs on CPU, doesn't require GPU

### **IMPORTANT Recommendation**
- **Run on CPU ONLY**: Don't try to use RX 6800 for this
- **Reason**: ROCm support for HuggingFace is experimental
- **CPU is fine**: FinBERT is small (110M params), fast on CPU

### Effort
- 8-12 hours (integration, testing, conflict resolution logic)
- New dependency: `transformers` (already in requirements.txt?)

---

## Implementation Roadmap

### Phase 1: Quick Wins (Week 1-2)
1. ✅ **Source Credibility Scoring** (3-4h) - Immediate false positive reduction
2. ✅ **Prompt Compression** (2-3h) - Immediate cost savings
3. ✅ **Multi-dimensional Sentiment** (4-6h) - Better classification quality

**Total Effort**: 9-13 hours
**Impact**: HIGH
**Cost**: $0 (actually saves money)

### Phase 2: Data Quality (Week 3-4)
4. ✅ **Enhanced Pydantic Schemas** (4-5h) - Validation layer
5. ✅ **Semantic Cache** (3-4h) - Reduce duplicate calls

**Total Effort**: 7-9 hours
**Impact**: MEDIUM-HIGH
**Cost**: $0

### Phase 3: Advanced Analytics (Week 5-6)
6. ✅ **Sentiment Velocity Tracking** (6-8h) - Narrative analysis
7. ✅ **FinBERT Validation** (8-12h) - Secondary confirmation

**Total Effort**: 14-20 hours
**Impact**: HIGH
**Cost**: $0

### **Total Project**
- **Effort**: 30-42 hours (~1-2 months part-time)
- **Cost**: **$0 (saves $15-30/month)**
- **ROI**: 🚀 Very High

---

## What We're NOT Doing (Too Complex / Expensive)

❌ **Multi-Agent Orchestration** - Requires running multiple LLMs simultaneously (RX 6800 can't do this)
❌ **Knowledge Graph Integration** - Requires Neo4j setup + significant data modeling
❌ **Real-time Position Sizing LLM** - Requires sub-second inference (too slow)
❌ **Fine-tuned Models** - Requires training infrastructure + labeled data
❌ **vLLM / TensorRT-LLM** - Complex setup, better suited for production scale

---

## Next Steps

1. **Review this document** with the user
2. **Select 2-3 enhancements** to start with (recommend: #1, #2, #6)
3. **Create implementation branches** for each
4. **Test against historical data** using MOA analyzer
5. **Measure impact** before/after on key metrics:
   - False positive rate
   - True positive rate (missed opportunities from MOA)
   - API cost per classification
   - Average classification confidence

---

## Questions for Discussion

1. Which 2-3 enhancements should we prioritize first?
2. Do you want to keep FinBERT CPU-only or explore ROCm support?
3. Should we integrate velocity tracking with the MOA historical analyzer?
4. Any other LLM pain points not covered here?

