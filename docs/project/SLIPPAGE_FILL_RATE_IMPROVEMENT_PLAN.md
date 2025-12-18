# Slippage and Fill Rate Improvement Plan

**Date:** 2025-12-18
**Status:** PLANNING COMPLETE
**Priority:** High

---

## Executive Summary

**Problem:** Only 1 of 5 orders filled (20% fill rate). The current system uses exact current market price as the limit price during extended hours, providing no margin for bid-ask spread or price movement.

**Root Cause:** The `order_executor.py` and `paper_trader.py` set limit prices directly to `current_price` or with only 2% margin, which is insufficient for illiquid penny stocks with 5-15% bid-ask spreads.

**Recommended Solution:** Implement an **Adaptive Aggressive Limit Pricing Strategy** that dynamically calculates limit prices based on price tier, volatility, and spread estimates to achieve 70-85% fill rates while maintaining cost control.

---

## Current State Analysis

### Order Execution Flow

1. **Signal Generation** (`signal_generator.py` lines 356-363):
   - Sets `entry_price=current_price` with no spread adjustment

2. **Order Execution** (`order_executor.py` lines 635-644):
   ```python
   if extended_hours:
       order_type = OrderType.LIMIT
       time_in_force = TimeInForce.DAY
       raw_price = signal.current_price or signal.entry_price
       limit_price = self._round_price_for_alpaca(raw_price)  # No markup!
   ```

3. **Legacy Paper Trader** (`paper_trader.py` lines 226-242):
   - Uses 2% above current price for extended hours
   - Better than order_executor but still insufficient for sub-$5 stocks

### Extended Hours Requirements (Alpaca)

- Extended hours orders **must use DAY limit orders** (no market orders, no GTC)
- Pre-market: 4:00 AM - 9:30 AM ET
- After-hours: 4:00 PM - 8:00 PM ET
- Extended hours typically have **lower liquidity** and **wider spreads**

### Slippage Model from Backtesting

| Price Range | Slippage Multiplier | Effective Slippage |
|-------------|---------------------|-------------------|
| < $1.00 | 2.5x | 5.0% |
| $1.00 - $2.00 | 2.0x | 4.0% |
| $2.00 - $5.00 | 1.5x | 3.0% |
| $5.00 - $10.00 | 1.0x | 2.0% |

---

## Root Cause Analysis

### Primary Issue: Zero-Margin Limit Pricing

| Component | Limit Price Calculation | Margin |
|-----------|------------------------|--------|
| `order_executor.py` | `current_price` | 0% |
| `paper_trader.py` | `price * 1.02` | 2% |

### Example: December 18 Orders

| Stock | Price | Bid-Ask Spread | Required Margin | Order Result |
|-------|-------|----------------|-----------------|--------------|
| COCP | $0.97 | ~2-3% | 2% | FILLED |
| VWAV | $3.50 | ~5-7% | 5%+ | UNFILLED |
| WKEY | $2.80 | ~6-8% | 6%+ | UNFILLED |
| KWM | $1.20 | ~8-10% | 8%+ | UNFILLED |
| AEC | $4.00 | ~4-6% | 5%+ | UNFILLED |

### Secondary Issues

1. **No Spread Estimation**: System doesn't fetch or estimate bid-ask spread
2. **No Volatility Adjustment**: Flat margin regardless of recent price movement
3. **No Liquidity Check**: Orders placed without checking market depth
4. **No Retry Logic**: Orders expire without adaptive repricing

---

## Proposed Solutions

### Solution 1: Adaptive Aggressive Limit Pricing (RECOMMENDED)

**Strategy**: Calculate dynamic limit prices based on price tier, estimated spread, and volatility.

```
limit_price = current_price * (1 + spread_estimate + volatility_buffer)
```

**Price Tier Markups**:

| Price Range | Base Markup | Spread Estimate | Total Margin |
|-------------|-------------|-----------------|--------------|
| < $1.00 | 2.0% | 5.0% | 7.0% |
| $1.00 - $2.00 | 1.5% | 4.0% | 5.5% |
| $2.00 - $5.00 | 1.0% | 3.0% | 4.0% |
| $5.00 - $10.00 | 0.5% | 2.0% | 2.5% |

**Extended Hours Multiplier**: Additional 1.5x during pre-market/after-hours

### Solution 2: IOC (Immediate-or-Cancel) with Retry

**Strategy**: Use IOC orders that fill immediately or cancel, with automatic retry at increasing prices.

**Flow**:
1. Place IOC limit order at `current_price + 2%`
2. If cancelled (no fill), retry at `current_price + 4%`
3. If cancelled again, retry at `current_price + 6%`
4. Max 3 retries, then give up

**Pros**: Avoids stale orders, gets best available price
**Cons**: Requires multiple API calls, may miss fast-moving opportunities

### Solution 3: Hybrid Market/Limit Approach

**Regular Hours (9:30 AM - 4:00 PM)**:
- Market orders for immediate fill (100% fill rate)
- Accept higher slippage for certainty of execution

**Extended Hours**:
- Aggressive limit orders (Solution 1)
- Accept lower fill rate for price protection

---

## Recommended Approach

### Phase 1: Adaptive Aggressive Limit Pricing

**New Configuration Options** (add to `config.py`):

```python
# Order Fill Rate Optimization
EXTENDED_HOURS_LIMIT_MARKUP_PCT = float(os.getenv("EXTENDED_HOURS_LIMIT_MARKUP_PCT", "5.0"))
EXTENDED_HOURS_VOLATILITY_BUFFER_PCT = float(os.getenv("EXTENDED_HOURS_VOLATILITY_BUFFER_PCT", "2.0"))
REGULAR_HOURS_USE_MARKET_ORDERS = _b("REGULAR_HOURS_USE_MARKET_ORDERS", True)
LIMIT_PRICE_TIER_MULTIPLIERS = {
    "<1.00": 1.07,   # 7% above current
    "1.00-2.00": 1.055,  # 5.5% above current
    "2.00-5.00": 1.04,   # 4% above current
    "5.00-10.00": 1.025, # 2.5% above current
}
```

**Core Pricing Logic**:

```python
def _calculate_aggressive_limit_price(
    self,
    current_price: Decimal,
    extended_hours: bool = False
) -> Decimal:
    """Calculate aggressive limit price based on price tier."""
    # Price tier multipliers
    if current_price < Decimal("1.00"):
        multiplier = Decimal("1.07")  # 7%
    elif current_price < Decimal("2.00"):
        multiplier = Decimal("1.055")  # 5.5%
    elif current_price < Decimal("5.00"):
        multiplier = Decimal("1.04")  # 4%
    else:
        multiplier = Decimal("1.025")  # 2.5%

    # Extended hours premium
    if extended_hours:
        multiplier *= Decimal("1.015")  # Additional 1.5%

    return (current_price * multiplier).quantize(Decimal("0.01"))
```

---

## Implementation Steps

### Step 1: Add Configuration (30 min)

**File**: `src/catalyst_bot/config.py`

1. Add new configuration options for limit price calculation
2. Add feature flag to enable/disable aggressive pricing
3. Document all new settings in CONFIGURATION_GUIDE.md

### Step 2: Create Pricing Utility (1 hour)

**File**: `src/catalyst_bot/execution/pricing.py` (new file)

1. Create `AggressiveLimitPricer` class
2. Implement price tier logic
3. Add volatility/spread estimation helpers
4. Add unit tests

### Step 3: Update Order Executor (2 hours)

**File**: `src/catalyst_bot/execution/order_executor.py`

1. Replace hardcoded limit price calculation (lines 612-660)
2. Use `AggressiveLimitPricer` for extended hours
3. Use market orders for regular hours (configurable)
4. Add logging for price calculations

### Step 4: Update Paper Trader (30 min)

**File**: `src/catalyst_bot/paper_trader.py`

1. Update deprecated paper_trader for consistency
2. Use same pricing logic as order_executor

### Step 5: Add Monitoring (1 hour)

1. Track fill rates by price tier
2. Log markup percentages and actual fill prices
3. Create execution stats view for analysis

### Step 6: Testing (2 hours)

1. Unit tests for pricing logic
2. Integration tests with mock broker
3. Paper trading validation

---

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXTENDED_HOURS_LIMIT_MARKUP_PCT` | 5.0 | Base markup % for extended hours |
| `EXTENDED_HOURS_VOLATILITY_BUFFER_PCT` | 2.0 | Additional buffer for volatile periods |
| `REGULAR_HOURS_USE_MARKET_ORDERS` | true | Use market orders during regular hours |
| `AGGRESSIVE_PRICING_ENABLED` | true | Master toggle for aggressive pricing |
| `LIMIT_ORDER_MAX_MARKUP_PCT` | 10.0 | Maximum allowed markup (cost control) |
| `IOC_RETRY_ENABLED` | false | Enable IOC with retry strategy |
| `IOC_MAX_RETRIES` | 3 | Maximum IOC retry attempts |

### Price Tier Configuration

```bash
LIMIT_TIER_SUB1=7.0    # Stocks < $1.00
LIMIT_TIER_1TO2=5.5    # Stocks $1.00-$2.00
LIMIT_TIER_2TO5=4.0    # Stocks $2.00-$5.00
LIMIT_TIER_5TO10=2.5   # Stocks $5.00-$10.00
```

---

## Risk Mitigation

### Overpaying Risk

**Concern**: Aggressive limit prices may result in paying significantly more than market price.

**Mitigation**:
1. **Cap maximum markup**: Never exceed 10% above current price
2. **Log all executions**: Track actual slippage vs estimated
3. **Monitor fill prices**: Alert if fill price differs significantly from quote
4. **Use backtesting data**: Price tiers calibrated from historical slippage analysis

### Extended Hours Liquidity Risk

**Concern**: Extended hours have thin order books, may not fill even with aggressive pricing.

**Mitigation**:
1. **Reduce position sizes**: Use smaller quantities during extended hours
2. **Accept partial fills**: Monitor and log partial fills separately
3. **Set realistic expectations**: Target 60-70% fill rate for extended hours

---

## Monitoring and Metrics

### Key Performance Indicators

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Fill Rate (Extended Hours) | 20% | 70% | Filled orders / Total orders |
| Fill Rate (Regular Hours) | N/A | 95%+ | With market orders |
| Average Slippage | Unknown | <3% | (Fill price - Quote price) / Quote price |
| Time to Fill | Unknown | <60s | Order submitted to filled |
| Order Expiration Rate | 80% | <30% | Expired / Total extended hours orders |

### Logging Requirements

```python
logger.info(
    "order_executed ticker=%s price_quote=%.4f limit_price=%.4f "
    "markup_pct=%.2f filled_price=%.4f actual_slippage_pct=%.2f "
    "extended_hours=%s fill_time_sec=%.1f",
    ticker, quote_price, limit_price, markup_pct, fill_price,
    actual_slippage, extended_hours, fill_time_seconds
)
```

---

## Testing Strategy

### Unit Tests

1. **Price tier calculation**: Verify correct markup for each price range
2. **Extended hours detection**: Ensure correct order type selection
3. **Round pricing**: Alpaca penny increment compliance
4. **Edge cases**: $0.99 vs $1.00 boundary, exactly $5.00, etc.

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| Sub-dollar stock | $0.85 quote | $0.91 limit (7%) |
| Dollar-range stock | $1.50 quote | $1.58 limit (5.5%) |
| Mid-range stock | $3.25 quote | $3.38 limit (4%) |
| Near-ceiling stock | $8.00 quote | $8.20 limit (2.5%) |
| Extended hours + volatile | $2.00 + high vol | $2.14 limit (7%) |
| Regular hours | $5.00 quote | Market order |

### Paper Trading Validation

1. **Monitor fill rates**: Track over 1-2 weeks
2. **Compare slippage**: Actual vs estimated
3. **Adjust tiers**: Fine-tune based on real data
4. **A/B testing**: Compare old vs new pricing logic

---

## Critical Files for Implementation

| File | Purpose |
|------|---------|
| `src/catalyst_bot/execution/order_executor.py` | Core order execution (lines 612-660) |
| `src/catalyst_bot/config.py` | Add new configuration options |
| `src/catalyst_bot/backtesting/trade_simulator.py` | Reference slippage model (lines 86-193) |
| `src/catalyst_bot/trading/signal_generator.py` | Entry price setting (lines 356-363) |
| `src/catalyst_bot/broker/alpaca_client.py` | Alpaca API integration (lines 547-614) |

---

*Generated: 2025-12-18*
