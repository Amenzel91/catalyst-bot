# Paper Trading Integration Report - Phase 1

**Supervisor Agent:** Paper Trading Integration Supervisor
**Date:** 2025-01-25
**Status:** Research Complete | Design In Progress
**Phase:** 1 - Integration + Signal Generation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Research Findings](#research-findings)
3. [Architecture Design](#architecture-design)
4. [Implementation Plan](#implementation-plan)
5. [Advanced Signal Generation Research](#advanced-signal-generation-research)
6. [Next Steps](#next-steps)
7. [Appendices](#appendices)

---

## 1. Executive Summary

### Mission Status

The paper trading integration is proceeding according to plan with **Research Phase Complete**. The existing Catalyst-Bot infrastructure is well-suited for trading integration, with a mature keyword-based classification system and comprehensive alert pipeline.

### Key Findings

1. **Keyword System Status**: Fully operational with ~1,200+ keywords across 30+ categories
2. **Integration Points Identified**: 3 primary integration points in runner.py
3. **Existing Infrastructure**: 75-80% of trading components already implemented
4. **Signal Generation Gap**: No automated signal generation from keyword matches exists
5. **Market Data Available**: Multiple providers already integrated (Alpaca, Tiingo, Alpha Vantage)

### Deliverables Status

| Deliverable | Status | Progress |
|-------------|--------|----------|
| Research Findings | ✅ Complete | 100% |
| Architecture Design | 🔨 In Progress | 70% |
| Signal Generator Design | 🔨 In Progress | 60% |
| Advanced Research | 📋 Pending | 0% |
| Implementation | 📋 Pending | 0% |
| Testing | 📋 Pending | 0% |

---

## 2. Research Findings

### 2.1 Keyword System Architecture

#### Current Implementation

The Catalyst-Bot uses a sophisticated multi-layered keyword system:

**File: `src/catalyst_bot/classify.py`**
- **Function**: `classify(item: NewsItem) -> ScoredItem`
- **Lines**: 1669-2350 (full classification pipeline)
- **Keyword Matching**: Lines 1789-1810

```python
# Keyword matching logic (simplified)
keyword_categories = settings.keyword_categories  # 30+ categories
combined_text = f"{title_lower} {summary_lower}"

for category, keywords in keyword_categories.items():
    for kw in keywords:
        if kw in combined_text:
            hits.append(category)
            weight = dynamic_weights.get(category, default_weight)
            total_keyword_score += weight
            break  # One hit per category
```

#### Keyword Categories (30+ Categories)

**File: `src/catalyst_bot/config.py`**
- **Lines**: 1243-1580 (keyword_categories definition)

**High-Value Trading Categories:**

| Category | Keywords | Weight | Trading Signal |
|----------|----------|--------|----------------|
| `fda` | "fda approval", "fast track designation", "bla approval" | 3.0 | 🟢 STRONG BUY |
| `clinical` | "phase 3", "primary endpoint met", "pivotal trial" | 2.5 | 🟢 BUY |
| `merger_acquisition` | "merger agreement", "acquisition announced", "buyout offer" | 4.0 | 🟢 STRONG BUY |
| `partnership` | "strategic partnership", "collaboration agreement" | 2.0 | 🟢 BUY |
| `contract_award` | "contract awarded", "contract win", "multi-year agreement" | 2.5 | 🟢 BUY |
| `earnings_beat` | "earnings beat", "revenue exceeded", "raised guidance" | 2.5 | 🟢 BUY |
| `offering_negative` | "public offering", "registered direct offering", "shelf registration" | -3.0 | 🔴 SELL/AVOID |
| `dilution_negative` | "dilutive offering", "share dilution", "warrant exercise" | -2.5 | 🔴 SELL/AVOID |
| `distress_negative` | "bankruptcy", "going concern", "delisting notice" | -4.0 | 🔴 STRONG SELL |

**Total Keywords**: 1,200+ phrases across all categories

#### Dynamic Keyword Weights

**File**: `data/analyzer/keyword_stats.json`

The system uses machine learning to adjust keyword weights based on historical performance:

```json
{
  "weights": {
    "fda": 3.2,
    "clinical": 2.7,
    "merger_acquisition": 4.1,
    "offering_negative": -3.5
  },
  "accuracy": {
    "fda": 0.87,
    "clinical": 0.72
  }
}
```

**Loading Function**: `load_dynamic_keyword_weights()` (Line 232)

### 2.2 Alert Pipeline Architecture

#### Alert Flow Diagram

```
SEC Filing / News RSS
        ↓
  fetch_pr_feeds()  (feeds.py)
        ↓
    dedupe()
        ↓
  classify(item) ← [Keyword Matching Happens Here]
        ↓
  ScoredItem (with keyword_hits, total_score)
        ↓
  send_alert_safe() → Discord Webhook
        ↓
[INTEGRATION POINT: Convert to TradingSignal]
```

#### Integration Points in runner.py

**File**: `src/catalyst_bot/runner.py`

**Point 1: After Classification (Primary Integration Point)**
- **Location**: Line 1450-1550 (main item processing loop)
- **Data Available**:
  - `scored` (ScoredItem with keyword_hits)
  - `item` (NewsItem with ticker, title, summary)
  - `ticker` (stock symbol)
  - `price` (current price from batch fetch)
  - `sentiment` (multi-source sentiment score)

**Point 2: After Alert Sent**
- **Location**: Line 1800-1850 (post-alert processing)
- **Data Available**:
  - Alert was successfully sent
  - Ticker, score, sentiment
  - Perfect for: Signal generation + order placement

**Point 3: End of Cycle**
- **Location**: Line 2100-2150
- **Data Available**:
  - All alerts from cycle
  - Aggregate statistics
  - Perfect for: Batch signal generation

### 2.3 Scoring System

#### Score Components

**Total Score Formula:**
```
total_score = (sentiment * sentiment_weight)
            + (keyword_score * keyword_weight)
            + source_credibility
            + regime_adjustment
            + volume_adjustment
```

**Typical Score Ranges:**
- **Strong Buy**: 2.5 - 5.0
- **Moderate Buy**: 1.5 - 2.5
- **Weak Buy**: 0.8 - 1.5
- **Neutral**: 0.0 - 0.8
- **Sell**: < 0.0

#### Sentiment Sources

**File**: `src/catalyst_bot/classify.py` (Lines 262-604)

The system aggregates sentiment from 12+ sources:

1. **VADER** (rule-based, fast)
2. **ML/FinBERT** (trained financial model)
3. **Earnings Results** (hard data from earnings_scorer)
4. **Google Trends** (retail interest)
5. **Short Interest** (squeeze potential)
6. **Pre-market Action** (institutional flow)
7. **After-market Action** (earnings reaction)
8. **News Velocity** (momentum indicator)
9. **Insider Trading** (Form 4 analysis)
10. **Volume-Price Divergence** (technical)
11. **LLM Sentiment** (Mistral/Claude)
12. **Market Regime** (VIX adjustment)

**Weighted Average Example:**
```python
sentiment = (0.35 * earnings_sentiment
           + 0.25 * ml_sentiment
           + 0.25 * vader_sentiment
           + 0.15 * llm_sentiment)
```

### 2.4 Market Data Integration

#### Existing Market Data Providers

**File**: `src/catalyst_bot/market.py`

**Available Functions:**
- `get_last_price_snapshot(ticker)` - Current price
- `batch_get_prices(tickers)` - Batch price fetch (10-20x faster)
- `get_market_data(ticker)` - Full market data (volume, avg, etc.)

**Providers (in order of preference):**
1. **Tiingo** (if FEATURE_TIINGO=1 and API key set)
2. **Alpha Vantage** (if API key set)
3. **yfinance** (free fallback)
4. **Alpaca** (real-time for trading)

**Configuration:**
```bash
MARKET_PROVIDER_ORDER=tiingo,av,yf
TIINGO_API_KEY=your_key_here
ALPHAVANTAGE_API_KEY=your_key_here
```

### 2.5 SEC Filing Integration

#### SEC LLM Analysis

**File**: `src/catalyst_bot/sec_llm_analyzer.py`

The system performs deep LLM analysis on SEC filings:

**Features:**
- Keyword extraction from 8-K, 10-K, 10-Q filings
- Sentiment analysis of filing text
- Guidance extraction (raised/lowered/maintained)
- Numeric metrics extraction (revenue, EPS, margins)
- Priority scoring (critical/high/medium/low)

**Output Structure:**
```python
{
    "keywords": ["partnership", "contract_award"],
    "sentiment": 0.75,
    "guidance": "raised",
    "numeric_metrics": {
        "revenue": 125.5,  # millions
        "yoy_change": 25.3  # percent
    },
    "priority": "high"
}
```

**Integration Point:**
- SEC filings are processed before being passed to `classify()`
- LLM keywords are added to `item.raw["keywords"]`
- These keywords are then matched against keyword_categories

---

## 3. Architecture Design

### 3.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      CATALYST BOT RUNNER                     │
└─────────────────────────────────────────────────────────────┘
                              │
                    fetch_pr_feeds()
                              │
                    ┌─────────▼──────────┐
                    │  NEWS / SEC ITEMS  │
                    └─────────┬──────────┘
                              │
                      classify(item)
                              │
                    ┌─────────▼──────────┐
                    │   SCORED ITEM      │
                    │ - keyword_hits     │
                    │ - sentiment        │
                    │ - total_score      │
                    └─────────┬──────────┘
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
    ┌───────▼────────┐              ┌──────────▼──────────┐
    │ ALERT SYSTEM   │              │  TRADING ENGINE     │
    │  (Existing)    │              │     (NEW)           │
    └────────────────┘              └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  SIGNAL GENERATOR   │
                                    │  - Keyword Rules    │
                                    │  - Confidence Score │
                                    │  - Risk Params      │
                                    └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  ORDER EXECUTOR     │
                                    │  - Position Sizing  │
                                    │  - Bracket Orders   │
                                    │  - Risk Checks      │
                                    └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  ALPACA BROKER      │
                                    │  (Paper Trading)    │
                                    └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │ POSITION MANAGER    │
                                    │  - P&L Tracking     │
                                    │  - Stop Loss Check  │
                                    │  - Portfolio Metrics│
                                    └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  MARKET DATA FEED   │
                                    │  - Price Updates    │
                                    │  - Position MTM     │
                                    └─────────────────────┘
```

### 3.2 Component Specifications

#### TradingEngine Class

**File**: `src/catalyst_bot/trading/trading_engine.py` (NEW)

**Purpose**: Orchestrate signal generation → order execution → position management

**Class Definition:**
```python
class TradingEngine:
    """
    Central controller for paper trading system.

    Responsibilities:
    - Convert ScoredItem → TradingSignal
    - Execute trades via OrderExecutor
    - Monitor positions via PositionManager
    - Update market data
    - Report performance
    """

    def __init__(
        self,
        broker_client: BrokerInterface,
        order_executor: OrderExecutor,
        position_manager: PositionManager,
        signal_generator: SignalGenerator,
        market_data_feed: MarketDataFeed,
        config: TradingConfig
    ):
        pass

    async def process_scored_item(
        self,
        scored: ScoredItem,
        item: NewsItem
    ) -> Optional[TradingSignal]:
        """
        Main entry point from runner.py.

        1. Generate trading signal from scored item
        2. Validate signal (risk checks)
        3. Execute order if signal is strong
        4. Return signal for logging
        """
        pass

    async def update_positions(self) -> None:
        """
        Update all open positions with current prices.
        Check stop-loss and take-profit triggers.
        Auto-close triggered positions.
        """
        pass

    async def get_portfolio_metrics(self) -> PortfolioMetrics:
        """Get current portfolio status."""
        pass

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        pass
```

**Integration with runner.py:**
```python
# In runner.py _cycle() function
# After line 1800 (post-alert)

# Initialize trading engine once (global)
trading_engine = get_trading_engine()

# In main loop (after alert sent)
if alerted and settings.feature_paper_trading:
    signal = await trading_engine.process_scored_item(scored, item)
    if signal:
        log.info(
            "trading_signal_generated ticker=%s action=%s confidence=%.2f",
            signal.ticker,
            signal.action,
            signal.confidence
        )

# At end of cycle (after all items processed)
if settings.feature_paper_trading:
    await trading_engine.update_positions()
```

#### SignalGenerator Class

**File**: `src/catalyst_bot/trading/signal_generator.py` (NEW)

**Purpose**: Convert keyword matches + sentiment → actionable trading signals

**Class Definition:**
```python
@dataclass
class TradingSignal:
    """Trading signal with all parameters for execution."""
    ticker: str
    action: str  # "BUY", "SELL", "CLOSE"
    confidence: float  # 0.0-1.0
    position_size_pct: float  # % of portfolio
    stop_loss_pct: Optional[float]  # % below entry
    take_profit_pct: Optional[float]  # % above entry
    signal_source: str  # "fda_approval", "merger_announcement", etc.
    keyword_hits: List[str]  # Categories that triggered
    sentiment: float  # -1.0 to +1.0
    total_score: float  # Classification score
    created_at: datetime
    metadata: Dict[str, Any]


class SignalGenerator:
    """
    Convert keyword-based classifications into trading signals.

    Strategy:
    - Map keyword categories to trading actions
    - Calculate confidence based on score + sentiment
    - Set stop-loss/take-profit based on volatility
    - Filter low-confidence signals
    """

    def __init__(self, config: SignalGeneratorConfig):
        self.config = config
        self.keyword_action_map = self._build_keyword_action_map()

    def generate_signal(
        self,
        scored: ScoredItem,
        item: NewsItem
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal from scored item.

        Returns None if:
        - No keyword matches
        - Confidence below threshold
        - Conflicting signals (both buy and sell keywords)
        - Ticker filtered (price, volume, etc.)
        """
        pass

    def _build_keyword_action_map(self) -> Dict[str, str]:
        """
        Map keyword categories to trading actions.

        BUY signals:
        - fda, clinical, merger_acquisition, partnership
        - contract_award, earnings_beat, guidance_raised

        SELL/AVOID signals:
        - offering_negative, dilution_negative, distress_negative
        - warrant_negative, earnings_miss

        CLOSE signals:
        - distress_negative (close existing positions)
        """
        return {
            # Strong Buy Signals
            "fda": "BUY",
            "merger_acquisition": "BUY",
            "clinical": "BUY",
            "partnership": "BUY",
            "contract_award": "BUY",
            "earnings_beat": "BUY",
            "guidance_raised": "BUY",

            # Moderate Buy Signals
            "breakthrough": "BUY",
            "energy_discovery": "BUY",

            # Sell/Avoid Signals
            "offering_negative": "AVOID",
            "dilution_negative": "AVOID",
            "warrant_negative": "AVOID",

            # Close Existing Positions
            "distress_negative": "CLOSE",
            "bankruptcy": "CLOSE",
        }

    def _calculate_confidence(
        self,
        total_score: float,
        sentiment: float,
        keyword_hits: List[str]
    ) -> float:
        """
        Calculate signal confidence (0.0-1.0).

        Factors:
        - Total classification score (higher = more confident)
        - Sentiment alignment (score and sentiment same direction)
        - Keyword strength (high-value keywords = more confident)
        - Multiple keywords (confirmation = more confident)
        """
        pass

    def _calculate_position_size(
        self,
        confidence: float,
        action: str
    ) -> float:
        """
        Calculate position size as % of portfolio.

        High confidence (0.8-1.0): 5-10%
        Medium confidence (0.6-0.8): 2-5%
        Low confidence (0.4-0.6): 1-2%
        """
        pass

    def _calculate_stop_loss(
        self,
        ticker: str,
        action: str,
        confidence: float
    ) -> float:
        """
        Calculate stop-loss % based on volatility.

        Options:
        1. Fixed % (e.g., 5%)
        2. ATR-based (2x average true range)
        3. Confidence-based (lower confidence = tighter stop)
        """
        pass

    def _calculate_take_profit(
        self,
        ticker: str,
        action: str,
        confidence: float,
        stop_loss_pct: float
    ) -> float:
        """
        Calculate take-profit % based on risk/reward.

        Target: 2:1 or 3:1 risk/reward ratio
        Example: 5% stop-loss → 10-15% take-profit
        """
        pass
```

#### MarketDataFeed Class

**File**: `src/catalyst_bot/trading/market_data.py` (NEW)

**Purpose**: Provide real-time price updates for position monitoring

**Class Definition:**
```python
class MarketDataFeed:
    """
    Real-time market data provider for position updates.

    Uses existing market.py infrastructure with caching
    and batch fetching for efficiency.
    """

    def __init__(self, update_interval_seconds: int = 60):
        self.update_interval = update_interval_seconds
        self.price_cache: Dict[str, Tuple[float, datetime]] = {}
        self.last_update: Optional[datetime] = None

    async def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Get current price for ticker.
        Uses cache if recent, otherwise fetches fresh.
        """
        pass

    async def get_batch_prices(
        self,
        tickers: List[str]
    ) -> Dict[str, float]:
        """
        Batch fetch prices for multiple tickers.
        Uses market.batch_get_prices() for 10-20x speedup.
        """
        pass

    async def update_price_cache(self, tickers: List[str]) -> None:
        """
        Refresh price cache for all tracked tickers.
        Called every update_interval seconds.
        """
        pass

    def _is_cache_valid(self, ticker: str) -> bool:
        """Check if cached price is still fresh."""
        if ticker not in self.price_cache:
            return False

        price, timestamp = self.price_cache[ticker]
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return age < self.update_interval
```

### 3.3 Configuration Structure

**File**: `src/catalyst_bot/config.py` (modifications)

**New Settings:**
```python
@dataclass
class Settings:
    # ... existing fields ...

    # Paper Trading Settings
    feature_paper_trading: bool = _b("FEATURE_PAPER_TRADING", False)

    # Alpaca Credentials
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_api_secret: str = os.getenv("ALPACA_API_SECRET", "")
    alpaca_paper_mode: bool = _b("ALPACA_PAPER_MODE", True)

    # Signal Generation
    signal_min_confidence: float = float(os.getenv("SIGNAL_MIN_CONFIDENCE", "0.6"))
    signal_min_score: float = float(os.getenv("SIGNAL_MIN_SCORE", "1.5"))

    # Position Sizing
    position_size_pct: float = float(os.getenv("POSITION_SIZE_PCT", "5.0"))
    max_position_size_pct: float = float(os.getenv("MAX_POSITION_SIZE_PCT", "10.0"))
    max_portfolio_exposure_pct: float = float(os.getenv("MAX_PORTFOLIO_EXPOSURE_PCT", "50.0"))

    # Risk Management
    default_stop_loss_pct: float = float(os.getenv("DEFAULT_STOP_LOSS_PCT", "5.0"))
    default_take_profit_pct: float = float(os.getenv("DEFAULT_TAKE_PROFIT_PCT", "10.0"))
    max_daily_loss_pct: float = float(os.getenv("MAX_DAILY_LOSS_PCT", "10.0"))
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "10"))

    # Market Data
    market_data_update_interval: int = int(os.getenv("MARKET_DATA_UPDATE_INTERVAL", "60"))

    # Feature Flags
    trading_enabled_market_hours_only: bool = _b("TRADING_MARKET_HOURS_ONLY", True)
    trading_close_positions_eod: bool = _b("TRADING_CLOSE_EOD", False)
```

**Environment Variables (.env):**
```bash
# Paper Trading Enable
FEATURE_PAPER_TRADING=1

# Alpaca Credentials
ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxx
ALPACA_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALPACA_PAPER_MODE=1

# Signal Generation
SIGNAL_MIN_CONFIDENCE=0.6
SIGNAL_MIN_SCORE=1.5

# Position Sizing (% of portfolio)
POSITION_SIZE_PCT=5.0
MAX_POSITION_SIZE_PCT=10.0
MAX_PORTFOLIO_EXPOSURE_PCT=50.0

# Risk Management
DEFAULT_STOP_LOSS_PCT=5.0
DEFAULT_TAKE_PROFIT_PCT=10.0
MAX_DAILY_LOSS_PCT=10.0
MAX_OPEN_POSITIONS=10

# Market Data
MARKET_DATA_UPDATE_INTERVAL=60

# Trading Schedule
TRADING_MARKET_HOURS_ONLY=1
TRADING_CLOSE_EOD=0
```

### 3.4 Data Flow Specification

#### End-to-End Flow Example

**Scenario: FDA Approval Announcement**

```
1. News Item Received
   ├─ Title: "XYZ Pharma Receives FDA Approval for Cancer Drug"
   ├─ Ticker: XYZ
   └─ Source: prnewswire

2. Classification (classify.py)
   ├─ Keyword Match: "fda approval" → category: "fda"
   ├─ Sentiment: +0.85 (very bullish)
   ├─ Total Score: 3.7
   └─ Output: ScoredItem(keyword_hits=["fda"], sentiment=0.85, total_score=3.7)

3. Alert Sent
   └─ Discord webhook posted

4. Trading Engine (NEW)
   ├─ SignalGenerator.generate_signal()
   │  ├─ Keyword "fda" → Action: BUY
   │  ├─ Confidence: 0.92 (high score + high sentiment)
   │  ├─ Position Size: 8% (high confidence)
   │  ├─ Stop Loss: 5% (standard)
   │  └─ Take Profit: 12% (2.4:1 R/R)
   │
   ├─ OrderExecutor.execute_signal()
   │  ├─ Get account: $100,000 buying power
   │  ├─ Get current price: $25.50
   │  ├─ Calculate shares: ($100,000 * 0.08) / $25.50 = 313 shares
   │  ├─ Place bracket order:
   │  │  ├─ Entry: Market buy 313 shares @ $25.50
   │  │  ├─ Stop: Sell 313 shares @ $24.23 (5% below)
   │  │  └─ Limit: Sell 313 shares @ $28.56 (12% above)
   │  └─ Wait for fill
   │
   └─ PositionManager.open_position()
      ├─ Entry Price: $25.50
      ├─ Quantity: 313 shares
      ├─ Cost Basis: $7,981.50
      ├─ Stop Loss: $24.23
      ├─ Take Profit: $28.56
      └─ Save to positions table

5. Position Monitoring (every 60 seconds)
   ├─ MarketDataFeed.get_current_price("XYZ")
   ├─ Current Price: $26.80 (next update)
   ├─ Unrealized P&L: +$406.90 (+5.1%)
   ├─ Check stop-loss: $26.80 > $24.23 ✓
   └─ Check take-profit: $26.80 < $28.56 ✓

6. Take-Profit Triggered (eventually)
   ├─ Current Price: $28.60
   ├─ PositionManager.check_take_profits()
   ├─ Triggered: $28.60 > $28.56
   ├─ Auto-close position
   ├─ Realized P&L: +$967.90 (+12.1%)
   └─ Discord alert: "Position closed: XYZ +12.1% 🎉"
```

---

## 4. Implementation Plan

### 4.1 Phase 1A: Core Integration (8-12 hours)

#### Task 1: SignalGenerator Implementation (3-4 hours)

**File**: `src/catalyst_bot/trading/signal_generator.py`

**Subtasks:**
1. Define TradingSignal dataclass
2. Define SignalGeneratorConfig dataclass
3. Implement SignalGenerator class
4. Implement keyword → action mapping
5. Implement confidence calculation
6. Implement position sizing logic
7. Implement stop-loss/take-profit calculation
8. Add unit tests

**Test Cases:**
- FDA approval → BUY signal with high confidence
- Merger announcement → BUY signal with very high confidence
- Public offering → AVOID signal
- Bankruptcy → CLOSE signal for existing positions
- Conflicting keywords → No signal
- Low confidence → No signal

#### Task 2: TradingEngine Implementation (3-4 hours)

**File**: `src/catalyst_bot/trading/trading_engine.py`

**Subtasks:**
1. Define TradingConfig dataclass
2. Implement TradingEngine class
3. Implement process_scored_item()
4. Implement update_positions()
5. Implement risk checks (max exposure, daily loss limit)
6. Implement portfolio metrics
7. Add shutdown logic
8. Add unit tests

**Test Cases:**
- Process scored item → generate signal → execute order
- Risk check rejection (max exposure exceeded)
- Risk check rejection (daily loss limit hit)
- Multiple signals in one cycle
- Position update with price changes

#### Task 3: MarketDataFeed Implementation (2-3 hours)

**File**: `src/catalyst_bot/trading/market_data.py`

**Subtasks:**
1. Implement MarketDataFeed class
2. Integrate with existing market.py
3. Implement caching logic
4. Implement batch fetching
5. Add error handling for failed price fetches
6. Add unit tests

**Test Cases:**
- Single ticker price fetch
- Batch price fetch (10+ tickers)
- Cache hit vs cache miss
- Stale price handling
- API failure recovery

#### Task 4: Runner Integration (1-2 hours)

**File**: `src/catalyst_bot/runner.py`

**Subtasks:**
1. Add trading engine initialization
2. Add process_scored_item() call after alerts
3. Add update_positions() call at end of cycle
4. Add graceful shutdown
5. Add feature flag checks
6. Add error handling

**Integration Points:**
```python
# Line ~300: Global initialization
_trading_engine: Optional[TradingEngine] = None

def get_trading_engine(settings) -> Optional[TradingEngine]:
    global _trading_engine

    if not settings.feature_paper_trading:
        return None

    if _trading_engine is None:
        # Initialize components
        broker = AlpacaBrokerClient(
            api_key=settings.alpaca_api_key,
            api_secret=settings.alpaca_api_secret,
            paper_mode=settings.alpaca_paper_mode
        )

        executor = OrderExecutor(broker_client=broker)
        position_mgr = PositionManager(broker_client=broker)
        signal_gen = SignalGenerator(config=...)
        market_data = MarketDataFeed()

        _trading_engine = TradingEngine(
            broker_client=broker,
            order_executor=executor,
            position_manager=position_mgr,
            signal_generator=signal_gen,
            market_data_feed=market_data,
            config=...
        )

        # Connect to broker
        asyncio.run(broker.connect())

    return _trading_engine

# Line ~1850: After alert sent
if alerted and settings.feature_paper_trading:
    engine = get_trading_engine(settings)
    if engine:
        try:
            signal = await engine.process_scored_item(scored, item)
            if signal:
                log.info(
                    "trading_signal_generated ticker=%s action=%s confidence=%.2f",
                    signal.ticker, signal.action, signal.confidence
                )
        except Exception as e:
            log.error("trading_signal_failed err=%s", e, exc_info=True)

# Line ~2150: End of cycle
if settings.feature_paper_trading:
    engine = get_trading_engine(settings)
    if engine:
        try:
            await engine.update_positions()
            metrics = await engine.get_portfolio_metrics()
            log.info(
                "portfolio_update total_value=%.2f pnl=%.2f positions=%d",
                metrics.total_value,
                metrics.unrealized_pnl,
                metrics.num_positions
            )
        except Exception as e:
            log.error("position_update_failed err=%s", e, exc_info=True)
```

### 4.2 Phase 1B: Configuration & Testing (4-6 hours)

#### Task 5: Configuration Setup (1 hour)

**Files**:
- `src/catalyst_bot/config.py` (add trading settings)
- `.env.example` (add trading examples)
- `docs/TRADING_CONFIGURATION.md` (NEW - document all settings)

#### Task 6: Integration Testing (3-4 hours)

**File**: `tests/test_trading_integration.py` (NEW)

**Test Scenarios:**
1. End-to-end: Mock scored item → signal → order → position
2. Risk rejection: Max exposure limit
3. Risk rejection: Daily loss limit
4. Risk rejection: Max positions limit
5. Position monitoring: Stop-loss trigger
6. Position monitoring: Take-profit trigger
7. Multiple signals in one cycle
8. Market closed (no trading)
9. Broker connection failure
10. Position update failure

#### Task 7: Live Testing with Alpaca Paper (1-2 hours)

**Steps:**
1. Set FEATURE_PAPER_TRADING=1
2. Configure Alpaca credentials
3. Run bot for 1 full cycle
4. Verify signal generation
5. Verify order placement
6. Verify position tracking
7. Monitor for errors

---

## 5. Advanced Signal Generation Research

### 5.1 Research Objectives

This section will be populated by the Advanced Research Agent with:

1. **Sentiment Analysis Integration**
   - Multi-dimensional sentiment (not just -1 to +1)
   - Time-series sentiment momentum
   - Sentiment divergence detection

2. **Multi-Factor Scoring Models**
   - Combine technical + fundamental + catalyst signals
   - Machine learning feature engineering
   - Ensemble models (XGBoost, Random Forest)

3. **Machine Learning-Based Catalyst Detection**
   - Train classifier on historical filings
   - NER (Named Entity Recognition) for key terms
   - Sequence models (LSTM/Transformer) for context

4. **Time-Series Momentum Indicators**
   - Price momentum post-catalyst
   - Volume surge detection
   - Relative strength vs sector/market

5. **Industry Best Practices**
   - Quantitative research from academic papers
   - Commercial algo trading strategies
   - Risk management frameworks

### 5.2 Comparison Matrix (To Be Completed)

| Approach | Pros | Cons | Complexity | Expected ROI |
|----------|------|------|------------|--------------|
| Keyword-Based (Current) | Simple, fast, interpretable | Limited context, false positives | Low | Medium |
| Sentiment-Enhanced | Better accuracy, confidence | Requires tuning | Medium | High |
| Multi-Factor | Highest accuracy | Complex, slow | High | Very High |
| ML-Based | Learns patterns | Black box, needs data | Very High | High (long-term) |

---

## 6. Next Steps

### 6.1 Immediate Actions (This Week)

**Day 1: Architecture Finalization**
- [ ] Review this integration report
- [ ] Get stakeholder approval on architecture
- [ ] Finalize configuration parameters

**Day 2-3: Core Implementation**
- [ ] Implement SignalGenerator
- [ ] Implement TradingEngine
- [ ] Implement MarketDataFeed
- [ ] Integrate with runner.py

**Day 4: Testing**
- [ ] Write integration tests
- [ ] Test with mock broker
- [ ] Test with Alpaca paper account

**Day 5: Deployment**
- [ ] Deploy to staging environment
- [ ] Monitor for 24 hours
- [ ] Fix any issues discovered

### 6.2 Week 2: Refinement & Monitoring

**Week 2 Goals:**
- [ ] Monitor paper trading performance
- [ ] Tune signal generation parameters
- [ ] Analyze win rate and P&L
- [ ] Adjust risk parameters based on results

### 6.3 Week 3-4: Advanced Features

**Advanced Research Deployment:**
- [ ] Deploy sentiment-enhanced signals
- [ ] A/B test keyword-only vs multi-factor
- [ ] Implement machine learning model (if research positive)

---

## 7. Appendices

### Appendix A: File Structure

```
catalyst-bot/
├── src/catalyst_bot/
│   ├── trading/                    # NEW DIRECTORY
│   │   ├── __init__.py
│   │   ├── signal_generator.py    # NEW
│   │   ├── trading_engine.py      # NEW
│   │   └── market_data.py         # NEW
│   ├── broker/                     # EXISTING
│   │   ├── broker_interface.py    # ✅ Complete
│   │   └── alpaca_client.py       # ✅ 80% Complete
│   ├── execution/                  # EXISTING
│   │   └── order_executor.py      # ✅ 75% Complete
│   ├── portfolio/                  # EXISTING
│   │   └── position_manager.py    # ✅ 70% Complete
│   ├── runner.py                   # MODIFY (add trading integration)
│   ├── classify.py                 # EXISTING (no changes)
│   └── config.py                   # MODIFY (add trading settings)
├── tests/
│   ├── test_signal_generator.py   # NEW
│   ├── test_trading_engine.py     # NEW
│   └── test_trading_integration.py # NEW
├── docs/
│   ├── PAPER_TRADING_INTEGRATION_REPORT.md  # THIS FILE
│   ├── TRADING_CONFIGURATION.md   # NEW
│   └── SIGNAL_GENERATION_GUIDE.md # NEW
└── .env                            # MODIFY (add trading settings)
```

### Appendix B: Keyword → Action Mapping

| Keyword Category | Trading Action | Confidence Multiplier | Notes |
|------------------|----------------|----------------------|-------|
| fda | BUY | 1.5x | FDA approvals are strong catalysts |
| clinical | BUY | 1.3x | Positive trial results |
| merger_acquisition | BUY | 2.0x | Buyout premium |
| partnership | BUY | 1.2x | Revenue potential |
| contract_award | BUY | 1.3x | Revenue certainty |
| earnings_beat | BUY | 1.2x | Positive surprise |
| guidance_raised | BUY | 1.4x | Forward outlook |
| offering_negative | AVOID | - | Dilution risk |
| dilution_negative | AVOID | - | Shareholder dilution |
| distress_negative | CLOSE | - | Existential risk |
| bankruptcy | CLOSE | - | Total loss risk |

### Appendix C: Risk Parameters

| Parameter | Conservative | Moderate | Aggressive | Notes |
|-----------|-------------|----------|------------|-------|
| Position Size | 2-5% | 5-8% | 8-12% | % of portfolio per trade |
| Max Positions | 5 | 10 | 15 | Total open positions |
| Stop Loss | 3-5% | 5-8% | 8-12% | % loss before exit |
| Take Profit | 8-12% | 12-20% | 20-30% | % gain target |
| Max Portfolio Exposure | 30% | 50% | 75% | % of portfolio in positions |
| Daily Loss Limit | 5% | 10% | 15% | Stop trading if hit |

**Recommended Starting Values: CONSERVATIVE**

### Appendix D: Performance Metrics

**To Be Tracked:**

| Metric | Description | Target (Month 1) |
|--------|-------------|------------------|
| Win Rate | % of profitable trades | >50% |
| Avg Win | Average profit per winning trade | +8-12% |
| Avg Loss | Average loss per losing trade | -3-5% |
| Profit Factor | (Total Wins) / (Total Losses) | >2.0 |
| Sharpe Ratio | Risk-adjusted returns | >1.0 |
| Max Drawdown | Largest peak-to-trough decline | <15% |
| Recovery Time | Days to recover from drawdown | <30 days |
| Positions Per Week | Trading frequency | 5-10 |

---

**Report Version:** 1.0
**Last Updated:** 2025-01-25 (Research Phase Complete)
**Next Update:** 2025-01-26 (Implementation Phase Begin)
**Status:** Ready for Implementation

---

## Summary for Supervisor

**Research Phase: ✅ COMPLETE**

**Findings:**
1. Keyword system is mature and production-ready (1,200+ keywords, 30+ categories)
2. 3 integration points identified in runner.py
3. Existing trading infrastructure 75-80% complete
4. Market data providers already integrated

**Design Phase: 🔨 IN PROGRESS (70%)**

**Components Designed:**
1. ✅ TradingEngine class specification
2. ✅ SignalGenerator class specification
3. ✅ MarketDataFeed class specification
4. ✅ Configuration structure
5. ✅ Data flow diagrams

**Next Phase: Implementation (Ready to Begin)**

**Estimated Effort: 12-18 hours to MVP**
- Core implementation: 8-12 hours
- Testing: 4-6 hours

**Deployment Timeline:**
- Week 1: Implementation + Testing
- Week 2: Monitoring + Tuning
- Week 3-4: Advanced Features

**Risk Assessment: LOW**
- Infrastructure is solid
- Integration points are clear
- Conservative default parameters

**Recommendation: PROCEED WITH IMPLEMENTATION**
