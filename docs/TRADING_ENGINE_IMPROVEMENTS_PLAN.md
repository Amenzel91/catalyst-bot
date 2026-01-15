# Trading Engine Improvements Implementation Plan

## Executive Summary

This document outlines the comprehensive implementation plan for four critical trading engine improvements:

1. **Hybrid Trailing Stop-Loss** - Fixed % initially, ATR-based after profit threshold
2. **Time-Based Exits** - 24-hour default max hold with configurable overrides
3. **Unified Feedback Path** - Merge weight_adjuster and classifier weight systems
4. **Real-Time Price Monitoring** - WebSocket (Alpaca) with polling fallback

**Total Estimated Files**: 8 new files, 8 modifications
**Feature Flag Gated**: All features disabled by default for safe rollout

---

## Table of Contents

1. [Feature 1: Hybrid Trailing Stop-Loss](#feature-1-hybrid-trailing-stop-loss)
2. [Feature 2: Time-Based Exits](#feature-2-time-based-exits)
3. [Feature 3: Unified Feedback Path](#feature-3-unified-feedback-path)
4. [Feature 4: Real-Time Price Monitoring](#feature-4-real-time-price-monitoring)
5. [Implementation Tickets](#implementation-tickets)
6. [Test Plan](#test-plan)
7. [Rollout Strategy](#rollout-strategy)
8. [Configuration Reference](#configuration-reference)
9. [Review Findings & Mitigations](#appendix-review-findings--mitigations)

---

## Feature 1: Hybrid Trailing Stop-Loss

### Problem Statement

Currently, positions have static stop-loss and take-profit levels set at entry. This approach:
- Doesn't protect gains when price moves favorably
- Can exit positions too early if market temporarily dips
- Doesn't adapt to volatility changes during hold period

### Solution: Hybrid Trailing Stop

A two-phase trailing stop system:

**Phase 1 - Fixed Stop (Protection)**
- Initial stop at fixed percentage (8-12%) below entry
- Protects against immediate adverse moves
- No trailing during this phase

**Phase 2 - ATR-Based Trailing (Profit Protection)**
- Activates when profit reaches 1x initial risk (e.g., if stop is 10% below entry, activate when up 10%)
- Switches to ATR-based trailing (14-period, 2x multiplier)
- Stop only moves UP, never down
- Bounded by min/max distance (5-15% for penny stocks)

### State Machine

```
POSITION OPENED
    |
[FIXED PHASE]
  - Stop = entry - (entry * fixed_pct)
  - Monitor: price vs fixed stop
  - Check: profit >= 1x risk unit?
    | NO -> Continue
    | YES -> ACTIVATE TRAILING

[TRAILING PHASE]
  - Fetch ATR (14-period)
  - trailing_stop = max(trailing_stop, highest_price - (ATR * 2))
  - Apply bounds (5%-15% of price)
  - Check: price <= trailing_stop?
    | NO -> Continue
    | YES -> TRIGGERED -> Close Position (exit_reason="trailing_stop")
```

### Files to Create

| File | Purpose | Lines |
|------|---------|-------|
| `src/catalyst_bot/portfolio/trailing_stop_manager.py` | State machine, ATR integration | ~350 |
| `src/catalyst_bot/trading/atr_provider.py` | ATR fetching with caching | ~200 |
| `tests/portfolio/test_trailing_stop_manager.py` | Unit tests | ~400 |

### Files to Modify

| File | Changes | Lines Added |
|------|---------|-------------|
| `src/catalyst_bot/portfolio/position_manager.py` | Add `get_trailing_stop_state()`, extend `should_stop_loss()` | ~50 |
| `src/catalyst_bot/trading/trading_engine.py` | Initialize trailing stops on position open | ~20 |
| `src/catalyst_bot/config.py` | Add trailing stop configuration | ~15 |

---

## Feature 2: Time-Based Exits

### Problem Statement

Positions can be held indefinitely, leading to:
- Capital tied up in stale positions
- Missed opportunities from catalyst decay
- News-driven moves fading over time

### Solution: Configurable Time Exits

Default 24-hour maximum hold with:
- Per-position override via metadata
- Per-keyword category override (e.g., `fda` = 48h, `earnings` = 12h)
- Graceful exit during market hours preferred
- Data collection for future adaptive optimization

### Files to Modify

| File | Changes | Lines Added |
|------|---------|-------------|
| `src/catalyst_bot/portfolio/position_manager.py` | Add `check_time_exits()`, `_get_max_hold_for_position()` | ~40 |
| `src/catalyst_bot/trading/trading_engine.py` | Call time exit check in `update_positions()` | ~15 |
| `src/catalyst_bot/config.py` | Add time exit settings | ~5 |

---

## Feature 3: Unified Feedback Path

### Problem Statement

Two parallel weight systems exist with a path disconnect:
- `weight_adjuster.py` writes to `out/dynamic_keyword_weights.json` (NEVER READ)
- `classify.py` reads from `data/analyzer/keyword_stats.json` (STALE DATA)

### Solution: Unified KeywordWeights Module

Create single source of truth with dual-weight schema:
- **Alert weights**: For scoring all alerts (positive + negative keywords)
- **Trading weights**: Only for BUY signal keywords (never trade on negative keywords)

### Files to Create

| File | Purpose | Lines |
|------|---------|-------|
| `src/catalyst_bot/keyword_weights.py` | Unified weight loading/saving | ~150 |
| `scripts/migrate_keyword_weights.py` | Migration script | ~100 |

### Files to Modify

| File | Changes | Lines Changed |
|------|---------|---------------|
| `src/catalyst_bot/classify.py` | Use `load_alert_weights()` | ~10 |
| `src/catalyst_bot/feedback/weight_adjuster.py` | Use `update_weights()` | ~15 |
| `src/catalyst_bot/trading/signal_generator.py` | Use `load_trading_weights()` | ~10 |

---

## Feature 4: Real-Time Price Monitoring

### Problem Statement

Current price fetching:
- Only occurs at end of each 5-minute cycle
- Stop-loss/take-profit checks may be delayed by up to 5+ minutes

### Solution: WebSocket + Polling Hybrid

**Primary**: Alpaca StockDataStream (IEX) for sub-second price updates
**Fallback**: 30-60 second polling using existing MarketDataFeed

### Files to Create

| File | Purpose | Lines |
|------|---------|-------|
| `src/catalyst_bot/trading/price_stream_manager.py` | WebSocket manager | ~400 |
| `src/catalyst_bot/trading/position_price_monitor.py` | Position/stream bridge | ~250 |
| `tests/trading/test_price_stream_manager.py` | Unit tests | ~300 |

### Files to Modify

| File | Changes | Lines Added |
|------|---------|-------------|
| `src/catalyst_bot/trading/trading_engine.py` | Initialize monitor, hook position events | ~30 |
| `src/catalyst_bot/config.py` | Add WebSocket config | ~10 |

---

## Implementation Tickets

| Ticket | Description | Priority | Effort | Depends On |
|--------|-------------|----------|--------|------------|
| TE-1 | Trailing Stop Manager | High | 1 day | - |
| TE-2 | Integrate Trailing Stops into Position Manager | High | 0.5 day | TE-1 |
| TE-3 | Time-Based Exits | Medium | 0.5 day | - |
| TE-4 | Unified Keyword Weights Module | High | 0.5 day | - |
| TE-5 | Integrate Unified Weights | High | 0.5 day | TE-4 |
| TE-6 | Price Stream Manager | Medium | 1 day | - |
| TE-7 | Position Price Monitor | Medium | 0.5 day | TE-6 |
| TE-8 | Unit Tests | High | 1 day | All above |

---

## Test Plan

### Smoke Tests (Pre-Commit)

```bash
pytest tests/portfolio/test_trailing_stop_manager.py -v
pytest tests/test_keyword_weights.py -v
pytest tests/trading/test_price_stream_manager.py -v
```

### E2E Tests (Simulation Mode)

```bash
SIMULATION_MODE=1 FEATURE_TRAILING_STOPS=1 \
timeout 120 python -m pytest tests/integration/test_trailing_stop_e2e.py -v
```

### Paper Trading Validation (1 Week)

1. Enable features one at a time
2. Monitor metrics: activation rate, trigger accuracy, uptime

---

## Rollout Strategy

| Phase | Duration | Features | Notes |
|-------|----------|----------|-------|
| Foundation | Days 1-5 | TE-1, TE-4 | Add serialization, dual-read |
| Integration | Days 6-8 | TE-2, TE-3, TE-5 | Add market hours checks |
| WebSocket | Days 9-11 | TE-6, TE-7 | Add thread safety fixes |
| Paper Trading | Week 2-3 | All | Extended validation |

---

## Configuration Reference

### Environment Variables (.env)

```bash
# --- Trailing Stop-Loss ---
FEATURE_TRAILING_STOPS=0
TRAILING_STOP_FIXED_PCT=10.0
TRAILING_STOP_ACTIVATION=1.0
TRAILING_STOP_ATR_PERIOD=14
TRAILING_STOP_ATR_MULT=2.0
TRAILING_STOP_MIN_DIST=5.0
TRAILING_STOP_MAX_DIST=15.0

# --- Time-Based Exits ---
FEATURE_TIME_EXITS=0
TIME_EXIT_MAX_HOLD_HOURS=24.0
TIME_EXIT_CHECK_INTERVAL=15

# --- WebSocket Price Monitoring ---
FEATURE_ALPACA_STREAM=0
WS_RECONNECT_MIN=1
WS_RECONNECT_MAX=300
WS_HEARTBEAT_INTERVAL=30
WS_FALLBACK_POLL_SEC=30

# --- Unified Keyword Weights ---
FEATURE_UNIFIED_WEIGHTS=1
```

---

## Appendix: Review Findings & Mitigations

### Critical Issues (Must Fix)

1. **Metadata Schema Breaking Change** (95%) - Add JSON serialization for Decimal/datetime
2. **Weight System Dual-Read Migration** (100%) - Implement 3-phase migration with fallback
3. **Thread Isolation Pattern** (95%) - Add finally block matching discord_listener.py
4. **Cache Thread Safety** (85%) - Add threading.Lock to keyword_weights caching

### High Priority Issues

5. **Time-Based Exit Market Hours** (80%) - Queue exits for market open if triggered after-hours
6. **ATR Fetch Failure Fallback** (82%) - Use 8% fixed fallback if ATR unavailable
7. **Configuration Pattern Alignment** (90%) - Use consistent `float(os.getenv())` pattern

### Rollback Procedure

```bash
# Immediate rollback (< 5 minutes)
export FEATURE_TRAILING_STOPS=0
export FEATURE_TIME_EXITS=0
export FEATURE_ALPACA_STREAM=0
export FEATURE_UNIFIED_WEIGHTS=0
systemctl restart catalyst-bot
```

---

## Success Metrics

- Trailing stop activation rate: 30-50% of winning positions
- Time exit positions: <20% exceeding 24h
- WebSocket uptime: >99% during market hours
- Unified weights: 100% signal generation without negative keyword trades

---

*Document created: 2026-01-14*
*Author: Claude Code (Feature Development)*
*Last reviewed: 2026-01-14 (Quality Review Phase)*
