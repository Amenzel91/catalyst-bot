# 🤖 LLM Integration Features

Catalyst-Bot uses a **local LLM** (Mistral via Ollama) running on GPU to enhance catalyst detection beyond keyword matching.

---

## Current LLM Features

### 1. **SEC Filing Deep Analysis** 📄
**Status**: ✅ Implemented
**Feature Flag**: `FEATURE_LLM_SEC_ANALYSIS=1`

**What it does:**
- Analyzes 8-K, 424B5, FWP, 13D/G filings in detail
- Extracts:
  - Deal size (e.g., "$5.2 million offering")
  - Dilution percentage
  - Warrant coverage (bearish signal)
  - Risk level (low/medium/high)
  - Sentiment (-1 to +1)
  - Key catalysts
- Provides 1-2 sentence summary for Discord embed

**Example prompt:**
```
Filing Type: 424B5
Title: XYZ Corp Files $10M Registered Direct Offering

LLM Response:
{
  "sentiment": -0.6,
  "confidence": 0.85,
  "deal_size": "$10 million",
  "dilution": "~15%",
  "has_warrants": true,
  "catalysts": ["capital_raise", "dilution"],
  "summary": "Dilutive $10M offering with warrants. Bearish for existing shareholders.",
  "risk_level": "high"
}
```

---

### 2. **Low-Confidence Fallback** 🎯
**Status**: ✅ Implemented
**Feature Flag**: `FEATURE_LLM_FALLBACK=1`

**What it does:**
- Activates when keyword scanner confidence < 0.6 (configurable)
- LLM re-evaluates the headline with full context
- Can "rescue" alerts that keywords missed
- Prevents false negatives

**Use case:**
```
Headline: "ACME announces strategic partnership for AI chip development"
Keywords detected: ["partnership"]
Keyword confidence: 0.45 (below threshold)

LLM analysis:
{
  "is_catalyst": true,
  "sentiment": 0.7,
  "confidence": 0.82,
  "catalysts": ["partnership", "ai_exposure", "tech_innovation"],
  "reason": "High-value AI partnership likely to drive price action",
  "should_boost": true
}
→ Alert APPROVED by LLM override
```

---

### 3. **Standard News Classification** 📰
**Status**: ✅ Implemented
**Feature Flag**: `FEATURE_LLM_CLASSIFIER=1`

**What it does:**
- Classifies all news items with LLM tags
- Adds `llm_sentiment`, `llm_tags`, `llm_relevance` to scoring
- Merges with VADER sentiment for hybrid approach

---

## 🚀 Brainstormed LLM Features (Future)

### 4. **Discord Natural Language Commands** 💬

**Implementation**: Slash commands + LLM parsing

**Examples:**
```
/ask "Why did TSLA get flagged today?"
→ LLM: "TSLA triggered on 8-K Item 8.01 regarding Cybertruck production milestone.
        Sentiment: +0.6. Keywords: production, milestone. Price up 3.2% since alert."

/research NVDA "What catalysts are coming up this week?"
→ LLM: Checks events.jsonl + external data
     "NVDA has Q4 earnings on Thursday 2/22. Analyst estimates: $5.28 EPS.
      No SEC filings this week. Recent momentum: +12% over 5 days."

/compare AAPL MSFT "Which has better technical setup?"
→ LLM: Pulls charts, RSI, VWAP, recent alerts
     "MSFT: RSI 58, above VWAP, 2 alerts last week (positive).
      AAPL: RSI 72 (overbought), below VWAP, 0 alerts.
      Edge: MSFT for continuation, AAPL for mean reversion."

/tune "I want more biotech alerts but fewer dilution warnings"
→ LLM: Translates to parameter changes
     Recommendation:
       - KEYWORD_WEIGHT_FDA: 1.5 → 1.8
       - KEYWORD_WEIGHT_BIOTECH: 1.2 → 1.5
       - SKIP_KEYWORDS: add "dilution", "offering"
     [Approve Changes] [Reject]
```

---

### 5. **Automated Research Reports** 📊

**Trigger**: Weekly or on-demand via `/report <ticker>`

**What it generates:**
```markdown
## Weekly Deep Dive: TSLA

**Catalysts This Week:**
- 2/18: 8-K filed - Cybertruck production milestone (+0.7 sentiment)
- 2/20: Analyst upgrade from Morgan Stanley (PT $250 → $280)
- 2/21: Unusual whale activity detected (dark pool: 500k shares)

**Technical Setup:**
- RSI: 62 (neutral)
- VWAP: $215 (current: $218, +1.4%)
- Support: $210 | Resistance: $225

**Sentiment Analysis:**
- Social: +0.65 (bullish, trending on StockTwits)
- News: +0.42 (moderately positive)
- Institutional: +0.80 (high conviction)

**LLM Summary:**
"TSLA showing strong momentum post-Cybertruck milestone.
 Institutional flow supportive. Watch for breakout above $225
 resistance with Q1 delivery numbers as next catalyst."

**Alert Performance (Last 7 Days):**
- Alerts fired: 3
- Avg return: +5.2%
- Win rate: 67% (2/3)
```

---

### 6. **Earnings Call Transcript Analysis** 🎙️

**Trigger**: After earnings call transcripts available

**What it extracts:**
- Forward guidance (bullish/bearish)
- Management tone (confident/cautious)
- Key initiatives mentioned
- Analyst question sentiment
- Red flags (debt, layoffs, writedowns)

**Example:**
```
Ticker: AAPL
Earnings Call: Q4 2024

LLM Analysis:
- Guidance: Raised Q1 revenue outlook by 5% (BULLISH +0.8)
- Tone: Confident (mentioned "record" 12 times, "strong" 18 times)
- Key Initiatives: Vision Pro launch, India expansion, AI features
- Analyst Sentiment: Positive (9/12 analysts asked about growth, not concerns)
- Red Flags: None detected

Overall: STRONG BUY signal (+0.85 sentiment)
```

---

### 7. **Competitor & Sector Analysis** 🏭

**Trigger**: `/compare-sector <ticker>` or auto-run with alerts

**What it does:**
- Identifies sector peers (e.g., NVDA → AMD, INTC, AVGO)
- Compares momentum, alerts, sentiment
- Detects sector rotation

**Example:**
```
/compare-sector NVDA

Semiconductor Sector Analysis:

NVDA: +0.75 (leading, 3 alerts this week, RSI 68)
AMD:  +0.55 (lagging, 1 alert, RSI 52)
INTC: -0.20 (weak, 0 alerts, RSI 38)
AVGO: +0.60 (strong, 2 alerts, RSI 61)

LLM Insight:
"Broad semiconductor strength with NVDA as sector leader.
 AMD lagging but oversold - potential rotation candidate.
 INTC showing structural weakness - avoid."
```

---

### 8. **Risk Assessment & Position Sizing** ⚠️

**Trigger**: Before sending alert

**What it calculates:**
```python
Risk factors:
- Recent dilution events: -0.2
- Penny stock (< $5): -0.1
- Low float (< 10M): +0.3 (squeeze potential)
- High short interest (> 20%): +0.2
- No earnings in 3 months: -0.1
- Recent bankruptcy mention: -0.5

Net Risk Score: 0.1 (MODERATE)

LLM Recommendation:
"Moderate risk due to recent dilution offset by squeeze setup.
 Suggested position: 2-3% of portfolio.
 Stop loss: -8% from entry.
 Target: +15% (R:R = 1.88)"
```

---

### 9. **Filing Comparison (Quarter-over-Quarter)** 📈

**Trigger**: New 10-Q or 10-K filed

**What it does:**
- Compares current filing to previous quarter
- Highlights changes in:
  - Revenue trends
  - Debt levels
  - Share count (dilution tracking)
  - Cash burn rate
  - Key metrics (gross margin, EBITDA, etc.)

**Example:**
```
ACME Corp - Q3 2024 vs Q2 2024

Revenue: $12.5M → $15.2M (+21.6%) ✅
Debt: $8M → $6.5M (-18.8%) ✅
Share Count: 50M → 58M (+16%) ⚠️ DILUTION
Cash Burn: $2M/month → $1.5M/month (-25%) ✅
Runway: 6 months → 8 months ✅

LLM Summary:
"Strong revenue growth but significant dilution from recent offering.
 Improved cash efficiency extends runway. Net positive but watch
 further dilution risk."
```

---

### 10. **Social Sentiment Aggregation** 🌐

**Trigger**: Hourly background task

**Sources:**
- StockTwits API
- Twitter/X mentions (via search)
- Reddit r/pennystocks, r/wallstreetbets

**What it does:**
- Aggregates mentions by ticker
- LLM classifies sentiment of each post
- Detects unusual spikes (potential pumps)
- Flags coordinated campaigns (avoid)

**Example:**
```
Ticker: GME
Social Sentiment (Last 24h):

StockTwits: +0.72 (3,500 mentions, +280% vs avg)
Twitter: +0.65 (12,000 mentions, +450% vs avg)
Reddit: +0.80 (850 posts, trending #2 on WSB)

LLM Analysis:
"Massive social spike driven by options activity speculation.
 Tone: Retail FOMO, not fundamental. Likely pump-and-dump.
 Recommendation: AVOID or short-term scalp only."
```

---

### 11. **Parameter Tuning via Natural Language** 🎛️

**Current**: Admin has to manually edit `.env`
**With LLM**: Natural language commands

**Examples:**
```
User: "Make the bot more selective overall"
LLM: Recommends MIN_SCORE: 0 → 0.3, CONFIDENCE_HIGH: 0.8 → 0.85

User: "I want more FDA alerts but fewer offerings"
LLM: Recommends KEYWORD_WEIGHT_FDA +0.3, add "424B5" to SKIP_SOURCES

User: "Focus on stocks under $3"
LLM: Recommends PRICE_CEILING: 10 → 3

User: "What would happen if I set MIN_SCORE to 0.5?"
LLM: Backtests last 30 days with MIN_SCORE=0.5
     "Would have filtered 65% of alerts. Win rate: 72% → 78%.
      Avg return: +2.1% → +3.4%. Recommendation: APPROVE"
```

---

### 12. **Auto-Generated Trade Plans** 📋

**Trigger**: Alert posted to Discord

**What it adds:**
```
Alert: ACME - 8-K filed regarding $10M contract win

[Standard Alert Info]

📋 LLM Trade Plan:
Entry: $2.45-$2.50 (current: $2.48)
Target 1: $2.75 (+11%)
Target 2: $3.10 (+26%)
Stop Loss: $2.20 (-11%)

Timeline: 3-5 trading days
Catalyst: Contract announcement likely to drive momentum

Risk Factors:
- Low volume (avg 200k/day) - may gap
- Recent dilution event 2 weeks ago
- No earnings until next month

Position Size: 2% (moderate risk)
```

---

## Setup Instructions

### 1. Install Ollama

```bash
# Download from https://ollama.com/download
# Windows: Install via exe

# Verify installation
ollama --version
```

### 2. Pull Mistral Model

```bash
ollama pull mistral

# For larger context (better for filings):
ollama pull mistral:latest

# Or use a smaller/faster model:
ollama pull llama3.2:1b
```

### 3. Start Ollama Server

```bash
# Start in background (keeps running)
ollama serve

# Verify it's running
curl http://localhost:11434/api/generate -d '{"model":"mistral","prompt":"test"}'
```

### 4. Enable in `.env`

```ini
FEATURE_LLM_CLASSIFIER=1
FEATURE_LLM_FALLBACK=1
FEATURE_LLM_SEC_ANALYSIS=1
LLM_MODEL_NAME=mistral
LLM_TIMEOUT_SECS=20
```

### 5. Test LLM

```python
python -c "from catalyst_bot.llm_client import query_llm; print(query_llm('What is 2+2?'))"
# Expected: "4" or similar response
```

---

## Performance Considerations

### GPU Usage
- **Mistral 7B**: ~4GB VRAM
- **Inference time**: 2-5 seconds per query (depends on prompt length)
- **Concurrent requests**: Queue via background thread to avoid blocking

### Optimization Strategies

1. **Batch processing**:
   ```python
   # Instead of LLM call per filing
   for filing in filings:
       analyze_sec_filing(filing)  # 10 filings = 20-50s

   # Batch approach
   analyze_sec_filings_batch(filings)  # 10 filings = 10-15s
   ```

2. **Caching**:
   - Cache LLM responses by content hash
   - TTL: 24 hours for news, 7 days for filings
   - Reduces redundant API calls

3. **Priority queue**:
   - High priority: SEC filings, low-confidence fallback
   - Medium priority: Standard classification
   - Low priority: Research commands (async)

4. **Model selection**:
   - `mistral:latest` (7B): Balanced (default)
   - `llama3.2:1b`: Fast but less accurate
   - `mixtral:8x7b`: Slow but very accurate (for complex filings)

---

## Monitoring

### Check LLM Status

```python
# Health check endpoint now includes LLM status
curl http://localhost:8080/health

{
  "status": "healthy",
  "llm_available": true,
  "llm_model": "mistral",
  "llm_avg_latency_ms": 2400
}
```

### LLM Metrics (in logs)

```
llm_query_success count=1 latency_ms=2350 model=mistral
llm_query_failed err=timeout count=1
sec_analysis_complete filing=8-K sentiment=0.65 risk=medium
llm_fallback_boost ticker=ACME original_conf=0.45 llm_conf=0.82
```

---

## Cost Analysis

### Local LLM (Ollama)
- **Hardware cost**: GPU (already owned)
- **Electricity**: ~$0.50/day for 24/7 operation
- **API costs**: $0 (fully local)
- **Total**: ~$15/month

### vs Cloud LLM (OpenAI GPT-4)
- **Cost per query**: ~$0.03 (1000 tokens avg)
- **Daily queries**: ~500 (filings + fallbacks)
- **Total**: ~$450/month

**Savings with local LLM: $435/month** ✅

---

## Roadmap

- [x] SEC filing deep analysis
- [x] Low-confidence fallback
- [x] Standard news classification
- [ ] Discord natural language commands
- [ ] Automated research reports
- [ ] Earnings call analysis
- [ ] Sector/competitor comparison
- [ ] Risk assessment & position sizing
- [ ] Filing QoQ comparison
- [ ] Social sentiment aggregation
- [ ] Natural language parameter tuning
- [ ] Auto-generated trade plans

---

**Questions?** Test the LLM with: `python -m catalyst_bot.llm_client`

**Last Updated**: October 4, 2025
