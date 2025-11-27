# Alert → Order Flow Integration Map

## Current Flow
```
NewsItem → classify() → ScoredItem → send_alert_safe() → execute_paper_trade() → Alpaca API
```

**Call Site**: `src/catalyst_bot/alerts.py:1337`

## Target Flow
```
NewsItem → classify() → ScoredItem → send_alert_safe() → TradingSignal → TradingEngine.execute_signal() → OrderExecutor → BrokerInterface
```

---

## ScoredItem Structure
**Source**: `src/catalyst_bot/models.py:128`

```python
@dataclass
class ScoredItem:
    relevance: float              # Keyword match score
    sentiment: float              # Sentiment score (-1.0 to 1.0)
    tags: List[str]               # Matched keyword categories
    source_weight: float = 1.0    # Source credibility multiplier
    keyword_hits: List[str]       # Explicit category hits
    enriched: bool = False        # RVOL/VWAP enrichment flag

    @property
    def total(self) -> float:     # relevance * source_weight
```

**Dynamic Attributes** (attached during classification):
- `category` / `catalyst_type`: e.g., "merger", "earnings", "fda"
- `rvol_score`, `vwap_score`, `float_score`: Enrichment scores
- `ai_sentiment`: LLM sentiment (optional)

---

## TradingSignal Structure
**Source**: `src/catalyst_bot/execution/order_executor.py:81`

```python
@dataclass
class TradingSignal:
    # Identity
    signal_id: str
    ticker: str
    timestamp: datetime

    # Decision
    action: str                   # "buy", "sell", "hold"
    confidence: float             # 0.0 to 1.0

    # Pricing
    entry_price: Optional[Decimal]
    current_price: Optional[Decimal]

    # Risk
    stop_loss_price: Optional[Decimal]
    take_profit_price: Optional[Decimal]
    position_size_pct: float = 0.05  # % of portfolio

    # Metadata
    signal_type: str = "momentum"     # catalyst, momentum, breakout
    timeframe: str = "intraday"       # intraday, swing, position
    strategy: str = "default"
    metadata: Dict = field(default_factory=dict)
```

---

## Field Mapping: ScoredItem → TradingSignal

| TradingSignal | Source | Logic |
|---------------|--------|-------|
| `signal_id` | `alert_id` | MD5 hash from `{ticker}:{title}:{link}` |
| `ticker` | `item_dict["ticker"]` | From NewsItem |
| `timestamp` | `datetime.now()` | Signal generation time |
| `action` | **"buy"** | Phase 1: buy all alerts |
| `confidence` | `scored.total` | Clamped to 0.0-1.0 |
| `current_price` | `last_price` | From alerts.py price lookup |
| `entry_price` | `last_price` | Same as current |
| `stop_loss_price` | ENV var | `entry * (1 - STOP_LOSS_PCT)` |
| `take_profit_price` | ENV var | `entry * (1 + TAKE_PROFIT_PCT)` |
| `position_size_pct` | Calculated | $500 → % of portfolio |
| `signal_type` | `catalyst_type` | From scored.category |
| `timeframe` | **"intraday"** | Fixed |
| `strategy` | **"catalyst_alerts_v1"** | Fixed |
| `metadata["source"]` | `source` | e.g., "finviz" |
| `metadata["keywords"]` | `scored.keyword_hits` | Matched categories |
| `metadata["sentiment"]` | `scored.sentiment` | Original sentiment |
| `metadata["alert_id"]` | `alert_id` | For feedback |

---

## execute_paper_trade() Parameters

**Current Call** (alerts.py:1337):
```python
order_id = execute_paper_trade(
    ticker=ticker,                    # str: "AAPL"
    price=last_price,                 # float: 150.25
    alert_id=alert_id,                # str: MD5 hash (16 chars)
    source=source,                    # str: "finviz", "benzinga"
    catalyst_type=str(catalyst_type), # str: "merger", "earnings"
)
```

**Available But Not Passed**:
- `scored`: Full ScoredItem with relevance, sentiment, tags, scores
- `item_dict`: NewsItem data (title, link, summary)
- `last_change_pct`: Daily % change
- `market_info`: Market status

---

## execute_paper_trade() Logic
**Source**: `src/catalyst_bot/paper_trader.py:111`

1. **Position Sizing**: `qty = max(1, int($500 / price))`
2. **Market Hours Check**: `client.get_clock().is_open`
3. **Order Type**:
   - Market hours: `MarketOrderRequest` with `GTC`
   - Extended hours: `LimitOrderRequest` with `DAY`, limit = price * 1.02
4. **Submit**: `client.submit_order()`
5. **Position Tracking**:
   - Stop: `entry * 0.95` (5%)
   - Target: `entry * 1.15` (15%)
   - Track via `PositionManagerSync`

**Returns**: Order ID or None

---

## Code Example: Signal Builder

```python
def build_trading_signal_from_alert(
    ticker: str,
    alert_id: str,
    scored: ScoredItem,
    item_dict: dict,
    last_price: float,
    source: str,
    catalyst_type: str,
) -> TradingSignal:
    """Convert alert data to TradingSignal."""
    from decimal import Decimal
    from datetime import datetime
    import os

    entry = Decimal(str(last_price))
    stop_pct = float(os.getenv("PAPER_TRADE_STOP_LOSS_PCT", "0.05"))
    target_pct = float(os.getenv("PAPER_TRADE_TAKE_PROFIT_PCT", "0.15"))

    return TradingSignal(
        signal_id=alert_id,
        ticker=ticker,
        timestamp=datetime.now(),
        action="buy",
        confidence=max(0.0, min(1.0, scored.total)),
        entry_price=entry,
        current_price=entry,
        stop_loss_price=entry * Decimal(str(1 - stop_pct)),
        take_profit_price=entry * Decimal(str(1 + target_pct)),
        position_size_pct=0.05,
        signal_type=catalyst_type or "unknown",
        timeframe="intraday",
        strategy="catalyst_alerts_v1",
        metadata={
            "alert_id": alert_id,
            "source": source,
            "keywords": scored.keyword_hits,
            "sentiment": scored.sentiment,
            "relevance": scored.relevance,
            "title": item_dict.get("title", ""),
            "link": item_dict.get("link", ""),
        }
    )
```

---

## Environment Variables

**Current (paper_trader.py)**:
- `PAPER_TRADE_POSITION_SIZE`: "$500"
- `PAPER_TRADE_STOP_LOSS_PCT`: "0.05" (5%)
- `PAPER_TRADE_TAKE_PROFIT_PCT`: "0.15" (15%)
- `PAPER_TRADE_MAX_HOLD_HOURS`: "24"

**TradingEngine (order_executor.py)**:
- Position sizing: `max_position_size_pct=0.20`, `risk_per_trade_pct=0.02`
- Constraints: `min_position_size_dollars=100`, `max_position_size_dollars=10000`
- Shares: `min_shares=1`, `max_shares=1000`

---

## Key Differences

| Aspect | execute_paper_trade() | TradingEngine |
|--------|----------------------|---------------|
| Position Sizing | Fixed $500 | Portfolio % + risk-based |
| Order Type | Market/Limit by hours | Configurable |
| Risk Mgmt | Fixed % stop/target | Dynamic |
| Database | Position tracker only | Full execution log |
| Monitoring | Background thread | Async monitoring |
| Testing | Live Alpaca only | Mock broker support |

---

## Migration Steps

1. **Create** `build_trading_signal_from_alert()` in alerts.py
2. **Replace** `execute_paper_trade()` call with:
   ```python
   signal = build_trading_signal_from_alert(...)
   result = await trading_engine.execute_signal(signal)
   ```
3. **Test** with paper account
4. **Verify** execution logs match old behavior
5. **Deprecate** paper_trader.py after validation

---

**Lines**: 197 | **Version**: 1.0 | **Date**: 2025-11-26
