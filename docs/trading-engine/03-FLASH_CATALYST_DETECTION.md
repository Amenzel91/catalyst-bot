# Implementation Plan: Flash Catalyst Detection

## Overview

Flash Catalyst Detection monitors real-time price movements to identify rapid price spikes (>5% in 15-30 minutes) on sub-$10 stocks. These "flash catalysts" indicate breaking news or momentum plays that may not yet appear in traditional news feeds. The system generates priority signals that bypass the normal alert queue, enabling faster position entry.

**Key Metrics:**
- Target: Detect >5% price moves in 15-30 minute windows
- Stocks: Sub-$10 (penny stock focus, configurable)
- Volume: Require RVOL > 2x (relative volume spike)
- Latency: <60 seconds from price move to signal generation

---

## Current State Analysis

### Existing Price Monitoring

**MarketDataFeed** (`src/catalyst_bot/trading/market_data.py`):
- Batch price fetching with 30-second cache TTL
- Uses market.py providers: Tiingo, Alpha Vantage, yfinance
- Designed for position price updates, NOT real-time monitoring
- No streaming support, polling-based

**Gap:** No real-time flash detection or priority signal handling exists.

---

## Target State

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Watchlist   │────▶│  FlashDetector   │────▶│  Priority Signal │
│  Manager     │     │  (15m/30m scan)  │     │  Queue           │
└──────────────┘     └──────────────────┘     └──────────────────┘
       │                      │                        │
       │              ┌───────┴───────┐                │
       │              ▼               ▼                │
       │      ┌───────────┐   ┌───────────┐           │
       │      │  Price    │   │  Volume   │           │
       │      │  Monitor  │   │  Monitor  │           │
       │      └───────────┘   └───────────┘           │
       │                                               │
       ▼                                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      TradingEngine                                │
│  - Priority flash signals processed FIRST                        │
│  - Normal catalyst signals processed after                       │
│  - Cooldown prevents duplicate alerts (15 min per ticker)        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Dependencies & Libraries

**No new dependencies required:**
- `asyncio`: Async price monitoring loops
- `yfinance`: 1-minute bar data for intraday prices (already used)
- `aiohttp`: Async HTTP for future streaming support

---

## Implementation Steps

### Step 1: Create Flash Detector Module

**File:** `src/catalyst_bot/trading/flash_detector.py` (NEW)

Key components:
- `FlashDetectorConfig` dataclass
- `FlashCatalyst` dataclass (represents detected flash)
- `TickerPriceHistory` for rolling window tracking
- `FlashDetector` class with async monitoring

### Step 2: Integrate with TradingEngine

**File:** `src/catalyst_bot/trading/trading_engine.py`

Add flash detector initialization in `initialize()`:

```python
if self.config.flash_detection_enabled:
    flash_config = FlashDetectorConfig(
        price_change_pct_15m=self.config.flash_price_change_15m,
        price_change_pct_30m=self.config.flash_price_change_30m,
        min_rvol=self.config.flash_min_rvol,
    )
    self.flash_detector = FlashDetector(config=flash_config)
    self.flash_detector.add_callback(self._handle_flash_catalyst, is_async=True)
    await self.flash_detector.start()
```

### Step 3: Add Flash Signal Handler

**File:** `src/catalyst_bot/trading/trading_engine.py`

```python
async def _handle_flash_catalyst(self, flash: FlashCatalyst) -> None:
    """Handle detected flash catalyst with priority processing."""
    signal = self._generate_flash_signal(flash)
    if signal and self._check_risk_limits(signal, account.equity):
        position = await self._execute_signal(signal)
        if position:
            await self._send_flash_alert(flash, position)
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_FLASH_DETECTION` | `1` | Enable/disable flash detection |
| `FLASH_PRICE_CHANGE_15M` | `5.0` | Min % change for 15-min flash |
| `FLASH_PRICE_CHANGE_30M` | `7.0` | Min % change for 30-min flash |
| `FLASH_MIN_RVOL` | `2.0` | Minimum relative volume |
| `FLASH_REQUIRE_RVOL` | `1` | Require volume confirmation |
| `FLASH_SCAN_INTERVAL` | `30` | Scan interval (seconds) |
| `FLASH_COOLDOWN_MINUTES` | `15` | Cooldown per ticker |
| `FLASH_MAX_PRICE` | `10.0` | Maximum stock price |
| `FLASH_MIN_PRICE` | `0.50` | Minimum stock price |

---

## Flash Detection Logic

```python
def _detect_flash(self, ticker: str, current_price: float, history: TickerPriceHistory):
    # Check 15-minute window first
    price_15m_ago = history.get_price_at_minutes_ago(15)
    if price_15m_ago:
        change_15m = ((current_price - price_15m_ago) / price_15m_ago) * 100
        if abs(change_15m) >= self.config.price_change_pct_15m:
            return FlashCatalyst(
                ticker=ticker,
                price_change_pct=change_15m,
                timeframe="15m",
                priority=1,  # Highest priority
            )

    # Check 30-minute window
    price_30m_ago = history.get_price_at_minutes_ago(30)
    if price_30m_ago:
        change_30m = ((current_price - price_30m_ago) / price_30m_ago) * 100
        if abs(change_30m) >= self.config.price_change_pct_30m:
            return FlashCatalyst(
                ticker=ticker,
                price_change_pct=change_30m,
                timeframe="30m",
                priority=2,
            )

    return None
```

---

## Testing Plan

### Unit Tests

```python
def test_detect_flash_15m(self, detector):
    """Test detection of 15-minute flash."""
    history = TickerPriceHistory(ticker="TEST")

    # Price 15 minutes ago
    past_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    history.snapshots.append(PriceSnapshot(price=10.0, timestamp=past_time))
    history.add_snapshot(11.0)  # 10% move

    flash = detector._detect_flash("TEST", 11.0, history)

    assert flash is not None
    assert flash.timeframe == "15m"
    assert flash.price_change_pct == pytest.approx(10.0, rel=0.01)

def test_cooldown_prevents_duplicates(self, detector):
    """Test cooldown prevents duplicate alerts."""
    detector._set_cooldown("TEST")
    assert detector._is_in_cooldown("TEST") is True
```

### Validation Criteria

1. **Flash Detection Accuracy**
   - Detects >5% moves in 15-minute windows
   - Detects >7% moves in 30-minute windows
   - No false positives on normal fluctuations

2. **Volume Confirmation**
   - RVOL calculation integrates correctly
   - Rejects flashes with RVOL < 2x

3. **Cooldown Behavior**
   - Prevents duplicate alerts within cooldown
   - Per-ticker cooldown tracking

---

## Rollback Plan

### Immediate Disable

```bash
FEATURE_FLASH_DETECTION=0
```

### Code Rollback

Remove or revert:
- `src/catalyst_bot/trading/flash_detector.py`
- Flash-related changes in `trading_engine.py`

---

## Summary

| File | Action | Lines |
|------|--------|-------|
| `src/catalyst_bot/trading/flash_detector.py` | NEW | ~600 |
| `src/catalyst_bot/trading/market_data.py` | MODIFY | ~40 |
| `src/catalyst_bot/trading/trading_engine.py` | MODIFY | ~150 |
| `src/catalyst_bot/config.py` | MODIFY | ~35 |

---

**Document Version:** 1.0
**Created:** 2025-12-12
**Priority:** P1 (High)
