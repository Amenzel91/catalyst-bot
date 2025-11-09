# Wave 3-4 Implementation Roadmap

**Status**: Wave 1-2 Complete (60% overall) | Wave 3 In Progress (33%) | Wave 4 Pending

## Overview

This roadmap covers the remaining implementation work for Waves 3-4 of the SEC filing analysis enhancement project. Waves 1-2 (Foundation + Intelligence layers) are complete with 97.8% test coverage.

---

## Wave 3: Infrastructure & Scale (33% Complete)

**Goal**: Real-time streaming, cost optimization, and performance scaling

### ✅ Wave 3C: LLM Caching (COMPLETE)
**Status**: Already implemented and EXCEEDS requirements

**Existing Implementation** (`src/catalyst_bot/llm_cache.py`):
- Redis-backed semantic caching using sentence-transformers
- Cosine similarity matching (threshold: 0.95)
- 24-hour TTL with per-ticker scoping
- Expected 15-30% cache hit rate

**Originally Planned**: Simple file-based caching + rate limiting
**Actual**: Semantic matching with embeddings (BETTER)

**No Action Required** ✅

---

### ⏳ Wave 3A: SEC Streaming Infrastructure

**File to Create**: `src/catalyst_bot/sec_stream.py` (~450 lines)

#### Purpose
Real-time SEC filing delivery via WebSocket API instead of polling RSS feeds.

#### Key Features
```python
class SECStreamClient:
    """WebSocket client for real-time SEC filing stream from sec-api.io"""

    def __init__(self, api_key: str, market_cap_max: float = 5_000_000_000):
        """
        Parameters
        ----------
        api_key : str
            sec-api.io API key
        market_cap_max : float
            Maximum market cap for filtering (default: $5B for penny stocks)
        """

    async def connect(self):
        """Establish WebSocket connection with reconnection logic."""

    async def stream_filings(self) -> AsyncIterator[FilingEvent]:
        """
        Yield filings in real-time as they're published.

        Yields
        ------
        FilingEvent
            dataclass with: ticker, filing_type, url, timestamp, cik
        """

    def filter_by_market_cap(self, filing: FilingEvent) -> bool:
        """Apply market cap filter (< $5B for penny stock focus)."""
```

#### Integration Points
1. **Runner Integration**: Add to `src/catalyst_bot/runner.py`
   ```python
   async def monitor_sec_stream():
       """Monitor SEC WebSocket stream instead of polling RSS."""
       async with SECStreamClient(os.getenv("SEC_API_KEY")) as client:
           async for filing in client.stream_filings():
               # Process filing through existing pipeline
               await process_sec_filing(filing)
   ```

2. **Queue Management**: Add Redis queue for filing backlog
   ```python
   # When filings arrive faster than processing
   await redis_client.lpush("sec_filing_queue", filing.to_json())
   ```

3. **Graceful Degradation**: Fallback to RSS polling if WebSocket fails
   ```python
   try:
       await monitor_sec_stream()
   except SECStreamException:
       log.warning("WebSocket failed, falling back to RSS polling")
       await monitor_sec_rss()  # Existing implementation
   ```

#### Environment Variables
Add to `.env.example`:
```bash
# SEC Streaming API (sec-api.io)
SEC_API_KEY=your_sec_api_key_here
SEC_STREAM_ENABLED=true
SEC_STREAM_MARKET_CAP_MAX=5000000000  # $5B max (penny stocks)
SEC_STREAM_RECONNECT_DELAY=5  # seconds
```

#### Tests to Create
`tests/test_sec_stream.py`:
- `test_websocket_connection()`
- `test_filing_event_parsing()`
- `test_market_cap_filtering()`
- `test_reconnection_logic()`
- `test_queue_backlog_handling()`
- `test_graceful_fallback_to_rss()`

#### Success Criteria
- [ ] WebSocket connects to sec-api.io and receives filings
- [ ] Market cap filtering works (<$5B)
- [ ] Reconnection logic handles disconnects
- [ ] Queue prevents overload during bursts
- [ ] Graceful fallback to RSS if streaming fails
- [ ] 90%+ test coverage

---

### ⏳ Wave 3B: Tiered LLM Strategy

**File to Enhance**: `src/catalyst_bot/llm_hybrid.py`

#### Purpose
Route SEC filing analysis to Gemini Flash (cheap, fast) vs Gemini Pro (deep, accurate) based on filing complexity.

#### Current State
Existing `llm_hybrid.py` has:
- Gemini → Claude fallback chain
- Exponential backoff retry logic
- Basic routing via `route_request(prompt, task_type)`

#### Enhancements Needed

**1. Complexity Scoring**
```python
def calculate_filing_complexity(filing: FilingSection, metrics: NumericMetrics) -> float:
    """
    Score filing complexity on 0-1 scale.

    Factors:
    - Filing type: 8-K Item 1.01 (M&A) = high, Item 8.01 = low
    - Text length: >5000 chars = high
    - Numeric density: >10 numbers = high
    - Guidance presence: Forward guidance = high

    Returns
    -------
    float
        0.0-0.3: Simple (use Flash)
        0.3-0.7: Medium (use Flash, fallback to Pro)
        0.7-1.0: Complex (use Pro)
    """
    score = 0.0

    # Filing type impact
    high_impact_items = ["1.01", "1.03", "2.02"]  # M&A, bankruptcy, earnings
    if filing.item_code in high_impact_items:
        score += 0.3

    # Text length
    if len(filing.text) > 5000:
        score += 0.2

    # Numeric density
    if metrics and len(metrics.revenue + metrics.eps) > 10:
        score += 0.2

    # Guidance presence
    if has_raised_guidance(filing.text) or has_lowered_guidance(filing.text):
        score += 0.3

    return min(1.0, score)
```

**2. Model Selection Logic**
```python
def select_model_tier(complexity: float, strategy: str = "auto") -> str:
    """
    Select Gemini model based on complexity.

    Parameters
    ----------
    complexity : float
        0-1 complexity score
    strategy : str
        "auto", "flash", "pro", or "adaptive"

    Returns
    -------
    str
        "gemini-1.5-flash-002" or "gemini-1.5-pro-002"
    """
    if strategy == "flash":
        return "gemini-1.5-flash-002"
    elif strategy == "pro":
        return "gemini-1.5-pro-002"
    elif strategy == "auto":
        return "gemini-1.5-pro-002" if complexity > 0.7 else "gemini-1.5-flash-002"
    elif strategy == "adaptive":
        # Start with Flash, upgrade to Pro if confidence < 0.6
        return "gemini-1.5-flash-002"  # Will upgrade in retry logic
```

**3. Cost Tracking**
```python
# Add to llm_hybrid.py
GEMINI_COSTS = {
    "gemini-1.5-flash-002": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},  # per token
    "gemini-1.5-pro-002": {"input": 1.25 / 1_000_000, "output": 5.00 / 1_000_000},
}

def log_llm_cost(model: str, input_tokens: int, output_tokens: int):
    """Log cost per LLM call for monitoring."""
    costs = GEMINI_COSTS.get(model, {"input": 0, "output": 0})
    total_cost = (input_tokens * costs["input"]) + (output_tokens * costs["output"])
    log.info(f"LLM Cost: ${total_cost:.4f} ({model}, {input_tokens}+{output_tokens} tokens)")
```

**4. Integration with LLM Chain**
```python
# Modify llm_chain.py to pass complexity hint
def run_llm_chain(
    filing_text: str,
    numeric_metrics: Optional[NumericMetrics] = None,
    filing_section: Optional[FilingSection] = None,  # NEW
    max_retries: int = 3,
) -> LLMChainOutput:
    """Execute 4-stage LLM chain with tiered model selection."""

    # Calculate complexity
    complexity = 0.5  # Default
    if filing_section and numeric_metrics:
        complexity = calculate_filing_complexity(filing_section, numeric_metrics)

    # Select model tier
    model = select_model_tier(complexity, strategy=os.getenv("LLM_TIER_STRATEGY", "auto"))
    log.info(f"Selected {model} for complexity={complexity:.2f}")

    # Run stages with selected model
    extraction = _stage1_extraction(filing_text, numeric_metrics, xbrl_financials, max_retries, model_override=model)
    # ... rest of pipeline
```

#### Environment Variables
Add to `.env.example`:
```bash
# LLM Tiering Strategy
LLM_TIER_STRATEGY=auto  # auto, flash, pro, adaptive
LLM_COMPLEXITY_THRESHOLD=0.7  # Pro threshold for auto mode
LLM_COST_TRACKING=true  # Log per-call costs
```

#### Tests to Create
Add to `tests/test_llm_hybrid.py`:
- `test_complexity_scoring_simple_filing()`
- `test_complexity_scoring_complex_ma()`
- `test_model_selection_auto_mode()`
- `test_model_selection_flash_forced()`
- `test_model_selection_adaptive_upgrade()`
- `test_cost_calculation_accuracy()`

#### Success Criteria
- [ ] Complexity scoring correctly identifies simple vs complex filings
- [ ] Flash model used for >60% of filings (cost savings)
- [ ] Pro model used for high-impact events (M&A, earnings)
- [ ] Cost tracking logs accurate per-call costs
- [ ] Average cost per filing < $0.02 (vs $0.05 without tiering)
- [ ] 90%+ test coverage

---

### Wave 3 Overseer Checklist

Before marking Wave 3 complete, verify:

- [ ] **sec_stream.py created** with WebSocket client and queue management
- [ ] **llm_hybrid.py enhanced** with complexity scoring and tiered routing
- [ ] **Tests passing**: All new tests in test_sec_stream.py and test_llm_hybrid.py
- [ ] **Integration verified**: Stream connects to runner.py, tiering works in llm_chain.py
- [ ] **.env.example updated** with SEC_API_KEY, LLM_TIER_STRATEGY, etc.
- [ ] **No regressions**: Existing functionality still works (RSS polling, basic LLM routing)
- [ ] **Performance tested**: WebSocket handles 10+ concurrent filings without lag
- [ ] **Cost savings**: Average LLM cost reduced by 40-60% with tiering

---

## Wave 4: User Experience & Intelligence (0% Complete)

**Goal**: Advanced retrieval, smart prioritization, enhanced Discord UX

### ⏸️ Wave 4A: RAG System for Deep Analysis

**File to Create**: `src/catalyst_bot/rag_system.py` (~500 lines)

#### Purpose
Vector search for "dig deeper" functionality - let users ask follow-up questions about filings.

#### Key Features
```python
class SECFilingRAG:
    """RAG system for interactive SEC filing Q&A."""

    def __init__(self, vector_db: str = "faiss"):
        """
        Parameters
        ----------
        vector_db : str
            "faiss" or "chromadb"
        """
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.index = self._load_or_create_index()

    def index_filing(self, filing: FilingSection, summary: str, keywords: list[str]):
        """
        Index a filing for vector search.

        Stores:
        - Filing text chunks (512 tokens each)
        - Summary embedding
        - Keyword embeddings
        - Metadata (ticker, filing_type, date)
        """

    def search(self, query: str, ticker: Optional[str] = None, top_k: int = 3) -> list[SearchResult]:
        """
        Search indexed filings by natural language query.

        Examples
        --------
        >>> rag.search("What were the acquisition terms?", ticker="AAPL")
        >>> rag.search("Show me guidance changes", top_k=5)
        """

    async def answer_question(self, query: str, ticker: str) -> str:
        """
        Answer user question about a filing using RAG.

        Flow:
        1. Search for relevant filing chunks
        2. Construct context from top 3 results
        3. Send to LLM: "Based on this SEC filing, answer: {query}"
        4. Return concise answer (50-100 words)
        """
```

#### Integration Points
1. **Discord Button**: Add "Dig Deeper 🔍" button to SEC alerts
   ```python
   # In alerts.py
   button = discord.ui.Button(label="Dig Deeper 🔍", custom_id=f"rag:{ticker}:{filing_url}")
   ```

2. **Question Flow**:
   - User clicks "Dig Deeper"
   - Bot responds: "What would you like to know about this filing?"
   - User asks: "What were the revenue projections?"
   - RAG searches filing, generates answer with LLM

3. **Storage**: Index filings in FAISS/ChromaDB after processing
   ```python
   # After run_llm_chain() in sec_monitor.py
   rag_system.index_filing(filing, summary=chain_output.summary.summary, keywords=chain_output.keywords.keywords)
   ```

#### Environment Variables
```bash
# RAG System
RAG_ENABLED=true
RAG_VECTOR_DB=faiss  # faiss or chromadb
RAG_INDEX_PATH=data/rag_index/
RAG_MAX_CONTEXT_CHUNKS=3
RAG_ANSWER_MAX_TOKENS=150
```

#### Success Criteria
- [ ] Filings indexed with embeddings after processing
- [ ] Natural language queries return relevant chunks
- [ ] LLM generates accurate answers from context
- [ ] Discord "Dig Deeper" button triggers Q&A flow
- [ ] Response time < 3 seconds for typical query

---

### ⏸️ Wave 4B: Filing Prioritization Matrix

**File to Create**: `src/catalyst_bot/filing_prioritizer.py` (~350 lines)

#### Purpose
Score filings by urgency × impact × relevance to avoid alert fatigue.

#### Scoring Matrix
```python
@dataclass
class PriorityScore:
    urgency: float  # 0-1: Time sensitivity (earnings > M&A > routine)
    impact: float  # 0-1: Market impact (based on filing type + sentiment)
    relevance: float  # 0-1: User relevance (watchlist match, sector filter)
    total: float  # Weighted sum
    threshold_met: bool  # True if total > alert threshold

def calculate_priority(
    filing: FilingSection,
    sentiment: SECSentimentOutput,
    guidance: GuidanceAnalysis,
    user_watchlist: Optional[list[str]] = None,
) -> PriorityScore:
    """
    Calculate filing priority score.

    Formula:
    total = (urgency * 0.4) + (impact * 0.4) + (relevance * 0.2)

    Urgency factors:
    - 8-K Item 2.02 (earnings) = 0.9 (time-sensitive)
    - 8-K Item 1.01 (M&A) = 0.8
    - 10-Q = 0.7
    - 8-K Item 8.01 = 0.3 (routine)

    Impact factors:
    - Sentiment magnitude: abs(weighted_score)
    - Guidance change: raised/lowered = +0.3
    - Filing weight: use FILING_IMPACT_WEIGHTS

    Relevance factors:
    - On watchlist = 1.0
    - In tracked sector = 0.7
    - Not tracked = 0.3
    """
```

#### Alert Thresholds
```python
# Only send Discord alert if priority exceeds threshold
ALERT_THRESHOLDS = {
    "critical": 0.8,  # Always alert (M&A, earnings beats/misses)
    "high": 0.6,  # Alert if user online or watchlist
    "medium": 0.4,  # Queue for daily digest
    "low": 0.2,  # Log only, no alert
}

def should_send_alert(priority: PriorityScore, user_status: str = "online") -> bool:
    """Determine if filing should trigger immediate Discord alert."""
    if priority.total >= ALERT_THRESHOLDS["critical"]:
        return True
    if priority.total >= ALERT_THRESHOLDS["high"] and user_status == "online":
        return True
    return False
```

#### Integration
```python
# In sec_monitor.py after sentiment analysis
priority = calculate_priority(
    filing=filing_section,
    sentiment=sec_sentiment,
    guidance=guidance_analysis,
    user_watchlist=get_user_watchlist(user_id),
)

if should_send_alert(priority):
    await send_discord_alert(filing, priority)
else:
    log.info(f"Filing below alert threshold: {priority.total:.2f}")
    await queue_for_digest(filing, priority)
```

#### Environment Variables
```bash
# Filing Prioritization
PRIORITY_ALERT_THRESHOLD=0.6  # Minimum score to trigger alert
PRIORITY_WATCHLIST_BOOST=0.3  # Bonus for watchlist tickers
PRIORITY_DIGEST_ENABLED=true  # Send daily digest of medium-priority filings
```

#### Success Criteria
- [ ] Scoring accurately identifies high-impact events
- [ ] Alert fatigue reduced by 50-70% (fewer routine filings)
- [ ] Critical events (earnings, M&A) always trigger alerts
- [ ] User watchlist boosts relevant filings
- [ ] Daily digest aggregates medium-priority filings

---

### ⏸️ Wave 4C: Enhanced Discord Embeds

**File to Enhance**: `src/catalyst_bot/alerts.py`

#### Purpose
SEC-specific Discord embeds with rich data, interactive buttons, and visual indicators.

#### Current State
Basic embeds with title, description, and single color.

#### Enhancements Needed

**1. SEC Filing Embed Template**
```python
def create_sec_filing_embed(
    filing: FilingSection,
    summary: str,
    sentiment: SECSentimentOutput,
    guidance: GuidanceAnalysis,
    metrics: NumericMetrics,
    priority: PriorityScore,
) -> discord.Embed:
    """
    Create rich SEC filing embed.

    Layout:
    ┌─────────────────────────────────────┐
    │ 🚨 {TICKER} | {Filing Type}          │
    │ {Catalyst Type} • Priority: ⚠️ HIGH │
    ├─────────────────────────────────────┤
    │ 📊 Summary (100-150 words)          │
    │ {summary}                            │
    ├─────────────────────────────────────┤
    │ 💰 Key Metrics                       │
    │ Revenue: $150M (+25% YoY)           │
    │ EPS: $0.75 (beat est. $0.65)        │
    ├─────────────────────────────────────┤
    │ 📈 Guidance                          │
    │ ✅ Raised Q2 revenue to $175M-$200M │
    │ ⚖️ Maintained margin at 45%         │
    ├─────────────────────────────────────┤
    │ 🎯 Sentiment: +0.7 (Bullish)        │
    │ Justification: Strong revenue...    │
    ├─────────────────────────────────────┤
    │ [View Filing 📄] [Dig Deeper 🔍]    │
    └─────────────────────────────────────┘
    """

    # Color based on sentiment
    color = discord.Color.green() if sentiment.score > 0.3 else \
            discord.Color.red() if sentiment.score < -0.3 else \
            discord.Color.gold()

    embed = discord.Embed(
        title=f"🚨 {filing.ticker} | {filing.filing_type} {filing.item_code or ''}",
        description=summary,
        color=color,
        url=filing.filing_url,
        timestamp=datetime.utcnow(),
    )

    # Priority indicator
    priority_emoji = "🔴" if priority.total > 0.8 else "🟡" if priority.total > 0.6 else "🟢"
    embed.add_field(name="Priority", value=f"{priority_emoji} {priority.total:.2f}", inline=True)

    # Key metrics
    if metrics.revenue:
        rev = metrics.revenue[0]
        yoy = f" (+{rev.yoy_change_pct:.1f}% YoY)" if rev.yoy_change_pct else ""
        embed.add_field(name="💰 Revenue", value=f"${rev.value}{rev.unit[0].upper()}{yoy}", inline=True)

    # Guidance summary
    if guidance.has_guidance:
        guidance_lines = []
        for g in guidance.guidance_items[:3]:  # Top 3
            emoji = "✅" if g.change_direction == "raised" else "❌" if g.change_direction == "lowered" else "⚖️"
            guidance_lines.append(f"{emoji} {g.change_direction.capitalize()} {g.metric}")
        embed.add_field(name="📈 Guidance", value="\n".join(guidance_lines), inline=False)

    # Sentiment with justification
    sentiment_emoji = "🟢" if sentiment.score > 0.3 else "🔴" if sentiment.score < -0.3 else "🟡"
    embed.add_field(
        name=f"{sentiment_emoji} Sentiment: {sentiment.score:+.2f}",
        value=sentiment.justification[:150],
        inline=False,
    )

    # Footer with impact weight
    embed.set_footer(text=f"Impact: {sentiment.impact_weight:.1f}x | Confidence: {sentiment.confidence:.0%}")

    return embed
```

**2. Interactive Buttons**
```python
class SECFilingView(discord.ui.View):
    """Interactive buttons for SEC filing alerts."""

    def __init__(self, filing_url: str, ticker: str, filing_id: str):
        super().__init__(timeout=3600)  # 1 hour timeout

        # View Filing button
        self.add_item(discord.ui.Button(
            label="View Filing 📄",
            url=filing_url,
            style=discord.ButtonStyle.link,
        ))

        # Dig Deeper button (triggers RAG Q&A)
        self.dig_deeper_button = discord.ui.Button(
            label="Dig Deeper 🔍",
            custom_id=f"rag:{ticker}:{filing_id}",
            style=discord.ButtonStyle.primary,
        )
        self.dig_deeper_button.callback = self.dig_deeper_callback
        self.add_item(self.dig_deeper_button)

        # Chart button (show ticker chart)
        self.add_item(discord.ui.Button(
            label="Chart 📊",
            custom_id=f"chart:{ticker}",
            style=discord.ButtonStyle.secondary,
        ))

    async def dig_deeper_callback(self, interaction: discord.Interaction):
        """Handle Dig Deeper button click."""
        await interaction.response.send_message(
            "What would you like to know about this filing? Ask me anything!",
            ephemeral=True,
        )
        # Wait for user question and use RAG to answer
```

**3. Visual Indicators**
```python
# Emoji mappings for catalyst types
CATALYST_EMOJIS = {
    "acquisitions": "🤝",
    "earnings": "📊",
    "offering": "💵",
    "bankruptcy": "⚠️",
    "leadership": "👔",
    "partnership": "🤝",
}

# Priority badges
PRIORITY_BADGES = {
    "critical": "🔴 CRITICAL",
    "high": "🟡 HIGH",
    "medium": "🟢 MEDIUM",
    "low": "⚪ LOW",
}
```

#### Integration
```python
# In sec_monitor.py
async def send_sec_alert(filing, summary, sentiment, guidance, metrics, priority):
    """Send enhanced SEC filing alert to Discord."""
    embed = create_sec_filing_embed(filing, summary, sentiment, guidance, metrics, priority)
    view = SECFilingView(filing.filing_url, filing.ticker, filing.filing_id)

    channel = bot.get_channel(int(os.getenv("DISCORD_CHANNEL_SEC")))
    await channel.send(embed=embed, view=view)
```

#### Success Criteria
- [ ] Embeds show all key data (summary, metrics, guidance, sentiment)
- [ ] Color-coded by sentiment (green=bullish, red=bearish, yellow=neutral)
- [ ] Priority badges visible (🔴 CRITICAL, 🟡 HIGH, etc.)
- [ ] Interactive buttons work (View Filing, Dig Deeper, Chart)
- [ ] Footer shows impact weight and confidence
- [ ] Layout is clean and readable on mobile

---

### Wave 4 Overseer Checklist

Before marking Wave 4 complete, verify:

- [ ] **rag_system.py created** with FAISS/ChromaDB vector search
- [ ] **filing_prioritizer.py created** with urgency×impact×relevance scoring
- [ ] **alerts.py enhanced** with SEC-specific embeds and buttons
- [ ] **Tests passing**: test_rag_system.py, test_filing_prioritizer.py, test_alerts_sec.py
- [ ] **Integration verified**: RAG answers questions, prioritization reduces alerts, embeds render correctly
- [ ] **.env.example updated** with RAG_ENABLED, PRIORITY_ALERT_THRESHOLD, etc.
- [ ] **User testing**: Try "Dig Deeper" flow, verify daily digest works
- [ ] **Performance**: RAG query < 3s, embed rendering < 1s

---

## Final Integration & Testing

After Wave 4 completion, perform end-to-end verification:

### E2E Test Flow
1. **Mock SEC Filing**: Create realistic 8-K Item 2.02 (earnings beat)
2. **Stream Ingestion**: Verify sec_stream.py receives it
3. **Parsing**: sec_parser.py extracts Item 2.02 section
4. **Numeric Extraction**: numeric_extractor.py finds revenue/EPS
5. **LLM Chain**: llm_chain.py (4 stages) with Gemini Flash
6. **Guidance**: guidance_extractor.py detects raised guidance
7. **Sentiment**: sec_sentiment.py scores +0.8 (bullish)
8. **Prioritization**: filing_prioritizer.py scores 0.85 (high priority)
9. **Alert**: Enhanced embed sent to Discord with buttons
10. **RAG**: User clicks "Dig Deeper", asks question, gets answer

### Performance Benchmarks
- **Latency**: Filing → Alert in < 10 seconds
- **Cost**: Average < $0.02 per filing (with Gemini Flash)
- **Cache Hit Rate**: 15-30% for similar filings
- **Alert Reduction**: 50-70% fewer alerts (via prioritization)
- **Accuracy**: 90%+ sentiment score alignment with market reaction

### Documentation Updates
- [ ] Update README.md with SEC features section
- [ ] Create SEC_USAGE_GUIDE.md for end users
- [ ] Update .env.example with all new variables
- [ ] Add SEC filing examples to docs/examples/

---

## Environment Variables Summary

All new variables to add to `.env.example`:

```bash
# ============================================================================
# SEC Filing Analysis (Waves 1-4)
# ============================================================================

# SEC Streaming (Wave 3A)
SEC_API_KEY=your_sec_api_key_here
SEC_STREAM_ENABLED=true
SEC_STREAM_MARKET_CAP_MAX=5000000000  # $5B max for penny stocks
SEC_STREAM_RECONNECT_DELAY=5

# LLM Tiering (Wave 3B)
LLM_TIER_STRATEGY=auto  # auto, flash, pro, adaptive
LLM_COMPLEXITY_THRESHOLD=0.7
LLM_COST_TRACKING=true

# RAG System (Wave 4A)
RAG_ENABLED=true
RAG_VECTOR_DB=faiss  # faiss or chromadb
RAG_INDEX_PATH=data/rag_index/
RAG_MAX_CONTEXT_CHUNKS=3
RAG_ANSWER_MAX_TOKENS=150

# Filing Prioritization (Wave 4B)
PRIORITY_ALERT_THRESHOLD=0.6
PRIORITY_WATCHLIST_BOOST=0.3
PRIORITY_DIGEST_ENABLED=true

# SEC Sentiment (Wave 2C - already added)
SENTIMENT_WEIGHT_SEC_LLM=0.10

# XBRL Caching (Wave 1C)
XBRL_CACHE_DIR=data/xbrl_cache/
XBRL_CACHE_DAYS=90
```

---

## Timeline Estimate

**Wave 3 (Remaining)**: 4-6 hours
- 3A (sec_stream.py): 2-3 hours
- 3B (llm_hybrid.py): 2-3 hours

**Wave 4 (Full)**: 8-10 hours
- 4A (rag_system.py): 3-4 hours
- 4B (filing_prioritizer.py): 2-3 hours
- 4C (alerts.py enhancements): 3-4 hours

**Total Remaining**: 12-16 hours

---

## Risk Mitigation

### Potential Issues

1. **SEC API Rate Limits**: sec-api.io has 10 requests/second limit
   - **Mitigation**: Queue filings, batch process, use WebSocket (no rate limit)

2. **LLM Costs**: Heavy usage could exceed budget
   - **Mitigation**: Gemini Flash tiering (60% cost reduction), semantic caching (15-30% cache hit)

3. **Vector DB Size**: FAISS index could grow large (>1GB)
   - **Mitigation**: TTL on old filings (90 days), compress embeddings, use quantization

4. **Alert Fatigue**: Too many filings trigger alerts
   - **Mitigation**: Prioritization matrix, daily digest for medium-priority

5. **RAG Accuracy**: LLM might hallucinate answers
   - **Mitigation**: Ground answers in retrieved context, show confidence score, allow user to view source

---

## Next Steps

1. ✅ Mark "Create implementation roadmap document for Waves 3-4" as **complete**
2. ⏭️ Implement **Wave 3A**: sec_stream.py
3. ⏭️ Implement **Wave 3B**: llm_hybrid.py enhancements
4. ⏭️ Run **Wave 3 Overseer**: Integration tests
5. ⏭️ Implement **Wave 4A-C**: RAG, prioritization, embeds
6. ⏭️ Run **Final Integration**: E2E testing
7. ⏭️ Deploy to production

---

**Document Version**: 1.0
**Last Updated**: 2025-10-22
**Status**: Wave 1-2 Complete, Wave 3 In Progress (33%)
