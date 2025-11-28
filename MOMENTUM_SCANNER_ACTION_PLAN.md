# Momentum Scanner Action Plan

## Complete Implementation Guide for Day Trading Breakout Detection

**Date:** 2025-11-28
**Branch:** `claude/investigate-momentum-score-0157ryqaLg8ngtPcDeXsh8tY`
**Target:** Day trading breakout alerts for stocks under $10
**CLI Tools:** ClaudeCode, Codex

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Implementation Tickets](#implementation-tickets)
4. [Finviz Elite Scanner Strategies](#finviz-elite-scanner-strategies)
5. [Code Examples](#code-examples)
6. [ClaudeCode/Codex CLI Workflows](#claudecodecodex-cli-workflows)
7. [Context Management & Documentation](#context-management--documentation)
8. [Testing Strategy](#testing-strategy)
9. [Deployment Checklist](#deployment-checklist)

---

## Executive Summary

### Goal
Build a complete momentum scanner that detects **actionable breakout opportunities** in pre-market, intra-day, and after-hours for stocks under $10 using:
- Finviz Elite screener exports
- RVOL (Relative Volume) calculations
- Price change/gap detection
- Technical indicator confirmation (RSI, ATR)
- Rejected catalyst re-evaluation (MOA integration)

### Key Metrics for Day Trading Breakouts
| Indicator | Threshold | Priority |
|-----------|-----------|----------|
| RVOL | >= 2.0x (extrapolated) | **CRITICAL** |
| Pre-market Gap | >= 4% | **HIGH** |
| Intraday Move | >= 5% | **HIGH** |
| Average Volume | >= 500k | **MEDIUM** |
| ATR | >= $0.25 | **MEDIUM** |
| RSI | 55-70 (momentum zone) | **LOW** |
| Float | < 50M shares | **LOW** |

---

## Current State Analysis

### What's Working (80% complete)

```
src/catalyst_bot/
├── scanner.py          # Finviz breakout scanner - WORKING
├── finviz_elite.py     # Elite CSV export - WORKING
├── rvol.py             # Real-time RVOL calculation - WORKING
├── rejected_items_logger.py  # MOA data capture - WORKING
├── indicator_utils.py  # ATR, Bollinger, ADX - WORKING (not integrated)
├── premarket_sentiment.py    # Pre-market detection - WORKING
└── aftermarket_sentiment.py  # After-hours detection - WORKING
```

### Critical Gaps

| Gap | Impact | File(s) Affected |
|-----|--------|------------------|
| No price change % filters | Missing gap/move detection | `scanner.py` |
| No RSI integration | False signals on overbought/oversold | `scanner.py` |
| No MOA priority queue | Missing "second chance" catalysts | `scanner.py`, `runner.py` |
| No real-time tick scanning | Only event-driven, not continuous | `runner.py` |
| Alert format missing technicals | Users can't assess quickly | `alerts.py` |

---

## Implementation Tickets

### Phase 1: Core Breakout Detection (Week 1)

---

#### TICKET-001: Add Price Change Filters to Scanner
**Priority:** P0 - CRITICAL
**Estimated Effort:** 4 hours
**Files:** `src/catalyst_bot/scanner.py`, `src/catalyst_bot/config.py`

**Description:**
Add gap % and intraday change % filters to the breakout scanner. Finviz Elite provides `ta_gap_u` (gap up) and performance filters.

**Acceptance Criteria:**
- [ ] Scanner filters for gap >= 4% in pre-market
- [ ] Scanner filters for intraday change >= 5%
- [ ] Config options for customizing thresholds
- [ ] Unit tests pass

**Code Changes:**

```python
# config.py - Add new settings
@dataclass
class Settings:
    # ... existing fields ...

    # Momentum Scanner Thresholds
    breakout_min_gap_pct: float = float(os.getenv("BREAKOUT_MIN_GAP_PCT", "4.0") or "4.0")
    breakout_min_change_pct: float = float(os.getenv("BREAKOUT_MIN_CHANGE_PCT", "5.0") or "5.0")
    breakout_min_relvol: float = float(os.getenv("BREAKOUT_MIN_RELVOL", "2.0") or "2.0")
    breakout_min_avg_vol: int = int(os.getenv("BREAKOUT_MIN_AVG_VOL", "500000") or "500000")
    breakout_min_atr: float = float(os.getenv("BREAKOUT_MIN_ATR", "0.25") or "0.25")
    breakout_price_floor: float = float(os.getenv("BREAKOUT_PRICE_FLOOR", "0.50") or "0.50")
    breakout_price_ceiling: float = float(os.getenv("BREAKOUT_PRICE_CEILING", "10.0") or "10.0")
```

```python
# scanner.py - Enhanced scan_breakouts_under_10()
def scan_breakouts_under_10(
    *,
    min_avg_vol: float = None,  # Use config default
    min_relvol: float = None,   # Use config default
    min_gap_pct: float = None,  # NEW
    min_change_pct: float = None,  # NEW
) -> List[Dict[str, object]]:
    """Return breakout candidates with price change filters."""
    settings = get_settings()
    if not getattr(settings, "feature_breakout_scanner", False):
        return []

    # Use config defaults if not specified
    min_avg_vol = min_avg_vol or settings.breakout_min_avg_vol
    min_relvol = min_relvol or settings.breakout_min_relvol
    min_gap_pct = min_gap_pct or settings.breakout_min_gap_pct
    min_change_pct = min_change_pct or settings.breakout_min_change_pct

    # Build Finviz filter string
    f_parts = []
    f_parts.append(f"sh_price_u{int(settings.breakout_price_ceiling)}")
    f_parts.append(f"sh_price_o{settings.breakout_price_floor:.2f}")

    if min_avg_vol > 0:
        k = int(min_avg_vol / 1000)
        f_parts.append(f"sh_avgvol_o{k}")

    if min_relvol > 0:
        rel_str = f"{float(min_relvol):.1f}".rstrip("0").rstrip(".")
        f_parts.append(f"sh_relvol_o{rel_str}")

    # NEW: Gap up filter (ta_gap_u = gap up %)
    if min_gap_pct > 0:
        f_parts.append(f"ta_gap_u{int(min_gap_pct)}")

    # NEW: Performance filter (ta_perf_d = day change %)
    if min_change_pct > 0:
        f_parts.append(f"ta_perf_do{int(min_change_pct)}")

    filters = ",".join(f_parts)
    # ... rest of function
```

**ClaudeCode Command:**
```bash
claude "Implement TICKET-001: Add price change filters to scanner.py. Add breakout_min_gap_pct and breakout_min_change_pct config options. Use Finviz filters ta_gap_u and ta_perf_do. Include unit tests."
```

---

#### TICKET-002: Integrate RSI Momentum Filter
**Priority:** P1 - HIGH
**Estimated Effort:** 3 hours
**Files:** `src/catalyst_bot/scanner.py`, `src/catalyst_bot/indicator_utils.py`

**Description:**
Add RSI filter to confirm momentum (RSI 55-70 = ideal zone for continuation). Filter out overbought (>70) signals that may reverse.

**Acceptance Criteria:**
- [ ] Add `compute_rsi()` function to indicator_utils.py
- [ ] Scanner fetches RSI for each candidate
- [ ] Filter out RSI > 70 (overbought)
- [ ] Add RSI to event metadata
- [ ] Config option to enable/disable

**Code Changes:**

```python
# indicator_utils.py - Add RSI calculation
def compute_rsi(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """Compute Relative Strength Index (RSI).

    RSI measures momentum by comparing average gains to average losses.
    Values above 70 indicate overbought, below 30 oversold.

    Parameters
    ----------
    df : pandas.DataFrame
        OHLCV data with 'Close' column.
    period : int
        RSI lookback period (default 14).

    Returns
    -------
    pandas.Series or None
        RSI values (0-100) or None if insufficient data.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None

    close = df["Close"]
    delta = close.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return rsi


def get_current_rsi(ticker: str, period: int = 14) -> Optional[float]:
    """Fetch current RSI for a single ticker.

    Uses yfinance to get recent price data and compute RSI.
    Returns the most recent RSI value.
    """
    import yfinance as yf

    try:
        # Get 30 days of data (enough for RSI calculation)
        data = yf.Ticker(ticker).history(period="1mo", interval="1d")
        if data.empty:
            return None

        rsi_series = compute_rsi(data, period)
        if rsi_series is None:
            return None

        return float(rsi_series.dropna().iloc[-1])
    except Exception:
        return None
```

```python
# scanner.py - Add RSI filter
from .indicator_utils import get_current_rsi

def scan_breakouts_under_10(...) -> List[Dict[str, object]]:
    # ... existing code ...

    # After basic filtering, add RSI check
    filtered_out = []
    for row in rows:
        ticker = row.get("ticker", "").upper()

        # Check RSI if enabled
        if getattr(settings, "feature_rsi_filter", False):
            rsi = get_current_rsi(ticker)
            if rsi is not None:
                row["rsi"] = rsi
                # Filter out overbought (RSI > 70)
                if rsi > 70:
                    filtered_out.append((ticker, "overbought", rsi))
                    continue
                # Filter out oversold (RSI < 30) - not ideal for breakouts
                if rsi < 30:
                    filtered_out.append((ticker, "oversold", rsi))
                    continue

        # ... build event ...
```

**ClaudeCode Command:**
```bash
claude "Implement TICKET-002: Add RSI momentum filter. Create compute_rsi() in indicator_utils.py. Integrate into scanner.py to filter overbought (>70) signals. Add feature_rsi_filter config option."
```

---

#### TICKET-003: MOA Priority Queue Integration
**Priority:** P1 - HIGH
**Estimated Effort:** 6 hours
**Files:** `src/catalyst_bot/scanner.py`, `src/catalyst_bot/rejected_items_logger.py`, `src/catalyst_bot/runner.py`

**Description:**
Load rejected catalysts from MOA log and prioritize them in scanner. If a previously rejected ticker shows breakout signals, it gets a "second chance" with boosted score.

**Acceptance Criteria:**
- [ ] Scanner reads from `data/rejected_items.jsonl`
- [ ] Extracts unique tickers from last 24h of rejections
- [ ] Prioritizes these tickers in Finviz scan
- [ ] Applies 1.3x score multiplier for "second chance" alerts
- [ ] Tags alerts with "Rejected Catalyst Re-evaluation"

**Code Changes:**

```python
# scanner.py - Add MOA priority queue
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

def get_moa_priority_tickers(hours: int = 24) -> List[str]:
    """Load recently rejected tickers from MOA log for priority scanning.

    Reads the rejected_items.jsonl file and extracts unique tickers
    from items rejected in the last N hours. These tickers are given
    priority in the breakout scanner for "second chance" evaluation.

    Args:
        hours: Look back this many hours (default 24)

    Returns:
        List of unique ticker symbols
    """
    log_path = Path("data/rejected_items.jsonl")
    if not log_path.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    tickers = set()

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    ts_str = item.get("ts", "")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                    if ts >= cutoff:
                        ticker = item.get("ticker", "").upper()
                        if ticker:
                            tickers.add(ticker)
                except Exception:
                    continue
    except Exception:
        return []

    return list(tickers)


def scan_breakouts_with_moa_priority(
    *,
    min_avg_vol: float = None,
    min_relvol: float = None,
    min_gap_pct: float = None,
    moa_score_boost: float = 1.3,  # 30% boost for rejected catalysts
) -> List[Dict[str, object]]:
    """Scan for breakouts with MOA priority queue.

    Combines standard Finviz scanning with MOA rejected items.
    Tickers that were previously rejected get boosted scoring
    if they now show breakout characteristics.
    """
    settings = get_settings()

    # Get priority tickers from MOA
    moa_tickers = get_moa_priority_tickers(hours=24)

    # Run standard scan
    results = scan_breakouts_under_10(
        min_avg_vol=min_avg_vol,
        min_relvol=min_relvol,
        min_gap_pct=min_gap_pct,
    )

    # Tag and boost MOA tickers
    for evt in results:
        ticker = evt.get("ticker", "").upper()
        if ticker in moa_tickers:
            evt["moa_second_chance"] = True
            evt["moa_score_boost"] = moa_score_boost
            evt["title"] = f"[Second Chance] {evt.get('title', '')}"

    return results
```

**ClaudeCode Command:**
```bash
claude "Implement TICKET-003: Add MOA priority queue to scanner. Create get_moa_priority_tickers() to read rejected_items.jsonl. Create scan_breakouts_with_moa_priority() that boosts score by 1.3x for previously rejected tickers."
```

---

### Phase 2: Enhanced Detection (Week 2)

---

#### TICKET-004: Pre-Market Gap Scanner
**Priority:** P0 - CRITICAL
**Estimated Effort:** 5 hours
**Files:** `src/catalyst_bot/scanner.py`, `src/catalyst_bot/premarket_scanner.py` (NEW)

**Description:**
Create dedicated pre-market scanner that detects gap-ups before market open. Uses Finviz's pre-market data when available, falls back to yfinance extended hours.

**Acceptance Criteria:**
- [ ] Detect gaps >= 4% from previous close
- [ ] Run between 4:00 AM - 9:30 AM ET
- [ ] Calculate pre-market RVOL
- [ ] Integrate with existing premarket_sentiment.py
- [ ] Send alerts at configurable intervals

**Code Changes:**

```python
# src/catalyst_bot/premarket_scanner.py (NEW FILE)
"""
Pre-Market Gap Scanner
======================

Scans for stocks gapping up in pre-market hours (4:00 AM - 9:30 AM ET).
Identifies breakout candidates before market open for day trading opportunities.

Key Features:
- Gap detection from previous close
- Pre-market volume tracking
- Integration with RVOL system
- Configurable alert thresholds
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import yfinance as yf

from .config import get_settings
from .finviz_elite import export_screener
from .logging_utils import get_logger
from .market_hours import MarketHours
from .rvol import calculate_rvol_intraday

log = get_logger("premarket_scanner")


def is_premarket_hours() -> bool:
    """Check if current time is within pre-market hours (4:00-9:30 AM ET)."""
    mh = MarketHours()
    return mh.is_premarket()


def get_premarket_gap(ticker: str) -> Optional[Dict]:
    """Calculate pre-market gap from previous close.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with gap data or None if unavailable:
        {
            "ticker": str,
            "prev_close": float,
            "premarket_price": float,
            "gap_pct": float,
            "gap_direction": "UP" | "DOWN",
            "calculated_at": str (ISO timestamp)
        }
    """
    try:
        tkr = yf.Ticker(ticker)

        # Get previous close
        hist = tkr.history(period="2d", interval="1d")
        if hist.empty or len(hist) < 2:
            return None

        prev_close = float(hist["Close"].iloc[-2])

        # Get pre-market price (fast_info or quote)
        try:
            info = tkr.info
            premarket_price = info.get("preMarketPrice")
            if premarket_price is None:
                # Fallback to regular market price
                premarket_price = info.get("regularMarketPrice") or info.get("currentPrice")
        except Exception:
            premarket_price = None

        if premarket_price is None or prev_close == 0:
            return None

        gap_pct = ((premarket_price - prev_close) / prev_close) * 100

        return {
            "ticker": ticker.upper(),
            "prev_close": round(prev_close, 2),
            "premarket_price": round(premarket_price, 2),
            "gap_pct": round(gap_pct, 2),
            "gap_direction": "UP" if gap_pct > 0 else "DOWN",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.debug(f"premarket_gap_failed ticker={ticker} err={e}")
        return None


def scan_premarket_gaps(
    *,
    min_gap_pct: float = 4.0,
    min_price: float = 0.50,
    max_price: float = 10.0,
    min_avg_vol: int = 500000,
) -> List[Dict]:
    """Scan for pre-market gap candidates.

    Uses Finviz screener to get candidate tickers, then
    fetches pre-market data to calculate actual gaps.

    Args:
        min_gap_pct: Minimum gap percentage to include (default 4%)
        min_price: Minimum price floor (default $0.50)
        max_price: Maximum price ceiling (default $10)
        min_avg_vol: Minimum average volume (default 500k)

    Returns:
        List of gap candidate events
    """
    settings = get_settings()

    if not is_premarket_hours():
        log.info("premarket_scanner_skipped reason=not_premarket_hours")
        return []

    # Get candidate tickers from Finviz (gap-up filter)
    f_parts = [
        f"sh_price_u{int(max_price)}",
        f"sh_price_o{min_price:.2f}",
        f"sh_avgvol_o{int(min_avg_vol / 1000)}",
        f"ta_gap_u{int(min_gap_pct)}",  # Gap up filter
    ]
    filters = ",".join(f_parts)

    try:
        rows = export_screener(filters)
    except Exception:
        rows = []

    results = []
    for row in rows:
        ticker = row.get("ticker", "").upper()
        if not ticker:
            continue

        # Get actual pre-market gap
        gap_data = get_premarket_gap(ticker)
        if gap_data is None:
            continue

        # Filter by minimum gap
        if abs(gap_data["gap_pct"]) < min_gap_pct:
            continue

        # Get RVOL if available
        rvol_data = calculate_rvol_intraday(ticker)

        # Build event
        evt = {
            "id": f"premarket_gap:{ticker}:{gap_data['calculated_at']}",
            "ticker": ticker,
            "title": f"{ticker} gaps {gap_data['gap_direction']} {abs(gap_data['gap_pct']):.1f}% pre-market",
            "link": f"https://finviz.com/quote.ashx?t={ticker}",
            "canonical_url": f"https://finviz.com/quote.ashx?t={ticker}",
            "source": "premarket_scanner",
            "source_host": "finviz.com",
            "published": gap_data["calculated_at"],
            "gap_pct": gap_data["gap_pct"],
            "prev_close": gap_data["prev_close"],
            "premarket_price": gap_data["premarket_price"],
        }

        if rvol_data:
            evt["rvol"] = rvol_data.get("rvol")
            evt["rvol_class"] = rvol_data.get("rvol_class")

        results.append(evt)

    log.info(f"premarket_scanner_complete candidates={len(results)}")
    return results
```

**ClaudeCode Command:**
```bash
claude "Implement TICKET-004: Create premarket_scanner.py with gap detection. Include is_premarket_hours(), get_premarket_gap(), and scan_premarket_gaps(). Use Finviz ta_gap_u filter. Calculate actual gaps using yfinance preMarketPrice."
```

---

#### TICKET-005: After-Hours Momentum Scanner
**Priority:** P1 - HIGH
**Estimated Effort:** 4 hours
**Files:** `src/catalyst_bot/afterhours_scanner.py` (NEW)

**Description:**
Mirror of pre-market scanner for after-hours (4:00 PM - 8:00 PM ET). Detect extended hours moves that may carry into next day.

**Code Structure:** Same as TICKET-004 but for after-hours window.

**ClaudeCode Command:**
```bash
claude "Implement TICKET-005: Create afterhours_scanner.py mirroring premarket_scanner.py. Adjust time checks for 4:00 PM - 8:00 PM ET. Use postMarketPrice from yfinance where available."
```

---

#### TICKET-006: Real-Time Continuous Scanner
**Priority:** P2 - MEDIUM
**Estimated Effort:** 8 hours
**Files:** `src/catalyst_bot/runner.py`, `src/catalyst_bot/realtime_scanner.py` (NEW)

**Description:**
Add continuous scanning loop that checks for breakouts every N minutes during market hours, not just on news events.

**Acceptance Criteria:**
- [ ] Scanner runs every 5 minutes during market hours
- [ ] Detects intraday breakouts (>5% move + RVOL > 2)
- [ ] Deduplicates alerts (same ticker within 30 min window)
- [ ] Integrates with existing runner.py loop

**Code Changes:**

```python
# runner.py - Add continuous scanner integration
from .realtime_scanner import scan_intraday_breakouts

async def _run_cycle(self):
    """Run one iteration of the main loop."""
    # ... existing feed processing ...

    # NEW: Run continuous breakout scanner every 5 minutes
    if self._should_run_continuous_scan():
        try:
            breakout_events = scan_intraday_breakouts()
            if breakout_events:
                log.info(f"continuous_scanner_found breakouts={len(breakout_events)}")
                for evt in breakout_events:
                    await self._process_breakout_event(evt)
        except Exception as e:
            log.warning(f"continuous_scanner_failed err={e}")


def _should_run_continuous_scan(self) -> bool:
    """Check if continuous scanner should run this cycle."""
    settings = get_settings()
    if not getattr(settings, "feature_continuous_scanner", False):
        return False

    # Run every 5 minutes (check if current minute is divisible by 5)
    from datetime import datetime
    now = datetime.now()
    return now.minute % 5 == 0 and now.second < 30
```

**ClaudeCode Command:**
```bash
claude "Implement TICKET-006: Add continuous breakout scanner to runner.py. Create realtime_scanner.py with scan_intraday_breakouts(). Run every 5 minutes during market hours. Deduplicate alerts within 30-minute windows."
```

---

### Phase 3: Alert Enhancement (Week 3)

---

#### TICKET-007: Enhanced Alert Format with Technicals
**Priority:** P1 - HIGH
**Estimated Effort:** 3 hours
**Files:** `src/catalyst_bot/alerts.py`

**Description:**
Add technical indicators to Discord alert embeds for quick assessment.

**Alert Format:**

```
BREAKOUT ALERT: $ACME
[Second Chance] Previous catalyst re-evaluation

Price: $4.50 (+8.5% from open)
Gap: +6.2% pre-market
RVOL: 3.5x (HIGH)
RSI: 62 (momentum)
ATR: $0.45 (good range)
Avg Vol: 1.2M

Source: Finviz Screener
Time: 10:32 AM ET
```

**ClaudeCode Command:**
```bash
claude "Implement TICKET-007: Update alerts.py to include RVOL, gap %, RSI, and ATR in Discord embeds. Use color coding: green for high confidence, yellow for moderate, red for caution."
```

---

#### TICKET-008: Alert Rate Limiting & Deduplication
**Priority:** P2 - MEDIUM
**Estimated Effort:** 2 hours
**Files:** `src/catalyst_bot/alerts.py`, `src/catalyst_bot/seen_store.py`

**Description:**
Prevent alert fatigue by limiting same-ticker alerts and implementing smart deduplication.

**Acceptance Criteria:**
- [ ] Max 1 alert per ticker per 30 minutes
- [ ] Aggregate multiple signals into single alert
- [ ] Track alert history in seen_store

**ClaudeCode Command:**
```bash
claude "Implement TICKET-008: Add rate limiting to alerts.py. Max 1 alert per ticker per 30 minutes. Use seen_store for tracking. Aggregate multiple signals if they arrive within 5 minutes."
```

---

## Finviz Elite Scanner Strategies

### Available Finviz Filters for Momentum

| Filter Code | Description | Recommended Value |
|-------------|-------------|-------------------|
| `sh_price_u10` | Price under $10 | Required |
| `sh_price_o0.5` | Price over $0.50 | Avoid penny stocks |
| `sh_avgvol_o500` | Avg volume > 500k | Liquidity |
| `sh_relvol_o2` | Relative volume > 2x | **Critical** |
| `ta_gap_u4` | Gap up > 4% | Pre-market gaps |
| `ta_perf_do5` | Day change > 5% | Intraday moves |
| `sh_float_u50` | Float < 50M | Squeeze potential |
| `ta_sma20_pa` | Price above SMA20 | Uptrend |
| `ta_sma50_pa` | Price above SMA50 | Strong uptrend |

### Optimal Screener Combinations

#### Pre-Market Gap Scanner
```
f=sh_price_u10,sh_price_o0.5,sh_avgvol_o500,sh_relvol_o1.5,ta_gap_u4
```

#### Intraday Momentum Scanner
```
f=sh_price_u10,sh_price_o0.5,sh_avgvol_o500,sh_relvol_o2,ta_perf_do5,ta_sma20_pa
```

#### High Squeeze Potential (Low Float)
```
f=sh_price_u10,sh_price_o0.5,sh_avgvol_o300,sh_relvol_o3,sh_float_u20,ta_gap_u5
```

#### Second Chance (After Rejection)
```
f=sh_price_u10,sh_avgvol_o200,sh_relvol_o2.5,ta_perf_do3
```

### Finviz API Usage Notes

1. **Rate Limits:** Finviz Elite allows ~100 requests/minute. Cache aggressively.
2. **CSV Export:** Use `/export.ashx?v=152&f=FILTERS` for CSV data
3. **View Codes:**
   - `v=111` = Overview (basic)
   - `v=152` = Performance (includes change %)
   - `v=161` = Financial (fundamentals)
4. **Signal Codes:**
   - `s=ta_newhigh` = New 52-week high
   - `s=ta_unusualvolume` = Unusual volume
   - `s=ta_topgainers` = Top gainers

---

## Code Examples

### Example 1: Complete Breakout Detection Flow

```python
# Example: Full breakout detection pipeline
from catalyst_bot.scanner import scan_breakouts_with_moa_priority
from catalyst_bot.premarket_scanner import scan_premarket_gaps
from catalyst_bot.rvol import calculate_rvol_intraday
from catalyst_bot.indicator_utils import get_current_rsi
from catalyst_bot.market_hours import MarketHours

def run_full_breakout_scan():
    """Run complete breakout detection across all time periods."""
    mh = MarketHours()
    results = []

    if mh.is_premarket():
        # Pre-market gap scan
        gaps = scan_premarket_gaps(
            min_gap_pct=4.0,
            min_price=0.50,
            max_price=10.0,
            min_avg_vol=500000
        )
        results.extend(gaps)

    elif mh.is_market_hours():
        # Intraday breakout scan
        breakouts = scan_breakouts_with_moa_priority(
            min_avg_vol=500000,
            min_relvol=2.0,
            min_gap_pct=5.0,
            moa_score_boost=1.3
        )

        # Enrich with RSI
        for b in breakouts:
            ticker = b.get("ticker")
            rsi = get_current_rsi(ticker)
            if rsi:
                b["rsi"] = rsi
                # Filter overbought
                if rsi > 70:
                    continue
            results.append(b)

    return results
```

### Example 2: Config-Driven Scanner Setup

```python
# .env file configuration
FEATURE_BREAKOUT_SCANNER=1
FEATURE_PREMARKET_SCANNER=1
FEATURE_CONTINUOUS_SCANNER=1
FEATURE_RSI_FILTER=1

BREAKOUT_MIN_GAP_PCT=4.0
BREAKOUT_MIN_CHANGE_PCT=5.0
BREAKOUT_MIN_RELVOL=2.0
BREAKOUT_MIN_AVG_VOL=500000
BREAKOUT_MIN_ATR=0.25
BREAKOUT_PRICE_FLOOR=0.50
BREAKOUT_PRICE_CEILING=10.0

# Scanner timing
CONTINUOUS_SCAN_INTERVAL_MIN=5
ALERT_RATE_LIMIT_MIN=30
```

---

## ClaudeCode/Codex CLI Workflows

### Setting Up Continuous Context

When working on multi-ticket implementations, maintain context across sessions:

#### 1. Create Context File
```bash
# Create .claude-context.md at repo root
cat > .claude-context.md << 'EOF'
# Momentum Scanner Implementation Context

## Current Sprint: Phase 1 - Core Breakout Detection
## Active Ticket: TICKET-001

## Key Files:
- src/catalyst_bot/scanner.py
- src/catalyst_bot/config.py
- src/catalyst_bot/finviz_elite.py
- src/catalyst_bot/rvol.py

## Completed:
- [x] Initial analysis
- [ ] TICKET-001: Price change filters
- [ ] TICKET-002: RSI integration
- [ ] TICKET-003: MOA priority queue

## Technical Decisions:
- Using Finviz Elite for screener data
- RVOL threshold: 2.0x minimum
- Gap threshold: 4% minimum
- Day trading focus (no swing trade logic)

## Testing Notes:
- Run tests with: pytest tests/test_scanner.py -v
- Mock Finviz API in tests (avoid rate limits)
EOF
```

#### 2. Start Session with Context
```bash
# Start ClaudeCode with context
claude --context .claude-context.md "Continue implementing TICKET-001"

# Or with Codex
codex --files src/catalyst_bot/scanner.py,src/catalyst_bot/config.py \
      "Add price change filters per TICKET-001 spec"
```

#### 3. Update Context After Changes
```bash
# After completing ticket, update context
claude "Update .claude-context.md to mark TICKET-001 complete and set TICKET-002 as active"
```

### Parallel Ticket Development

For independent tickets, run in parallel terminals:

```bash
# Terminal 1: TICKET-001
claude "Implement TICKET-001 price change filters in scanner.py"

# Terminal 2: TICKET-002 (independent)
claude "Implement TICKET-002 RSI calculation in indicator_utils.py"
```

### Code Review Workflow

```bash
# After implementing a ticket
claude "Review changes in scanner.py for TICKET-001. Check for:
1. Edge cases in filter logic
2. Proper error handling
3. Config integration
4. Missing tests"
```

### Testing Workflow

```bash
# Run specific tests
claude "Run tests for scanner.py and show any failures"

# Generate missing tests
claude "Generate unit tests for scan_breakouts_under_10() covering:
1. Empty results
2. Filter thresholds
3. MOA priority boost
4. Error handling"
```

---

## Context Management & Documentation

### File-Level Context Headers

Add context headers to each file for AI assistants:

```python
"""
scanner.py - Momentum Breakout Scanner
======================================

CONTEXT FOR AI ASSISTANTS:
- Part of Catalyst-Bot momentum detection system
- Uses Finviz Elite CSV exports for screening
- Integrates with rvol.py for volume analysis
- Integrates with rejected_items_logger.py for MOA
- Config options in config.py (breakout_* prefix)

DEPENDENCIES:
- finviz_elite.py: export_screener()
- rvol.py: calculate_rvol_intraday()
- config.py: Settings dataclass

KEY FUNCTIONS:
- scan_breakouts_under_10(): Main scanner
- scan_breakouts_with_moa_priority(): MOA-enhanced scanner
- get_moa_priority_tickers(): Load rejected items

TESTING:
- tests/test_scanner.py
- Mock Finviz API responses
"""
```

### Ticket Progress Tracking

Create `MOMENTUM_SCANNER_PROGRESS.md`:

```markdown
# Momentum Scanner Progress Tracker

## Phase 1: Core Breakout Detection

| Ticket | Status | Assignee | PR | Notes |
|--------|--------|----------|----|----|
| TICKET-001 | In Progress | - | - | Price change filters |
| TICKET-002 | Not Started | - | - | RSI integration |
| TICKET-003 | Not Started | - | - | MOA priority queue |

## Phase 2: Enhanced Detection

| Ticket | Status | Assignee | PR | Notes |
|--------|--------|----------|----|----|
| TICKET-004 | Not Started | - | - | Pre-market scanner |
| TICKET-005 | Not Started | - | - | After-hours scanner |
| TICKET-006 | Not Started | - | - | Continuous scanner |

## Phase 3: Alert Enhancement

| Ticket | Status | Assignee | PR | Notes |
|--------|--------|----------|----|----|
| TICKET-007 | Not Started | - | - | Enhanced alerts |
| TICKET-008 | Not Started | - | - | Rate limiting |

## Daily Standup Notes

### 2025-11-28
- Started Phase 1 implementation
- Action plan created
- Next: TICKET-001 implementation
```

### Git Commit Conventions

Use structured commits for easy tracking:

```bash
# Feature commits
git commit -m "feat(scanner): add price change filters [TICKET-001]

- Add ta_gap_u filter for pre-market gaps
- Add ta_perf_do filter for intraday changes
- Add config options: breakout_min_gap_pct, breakout_min_change_pct
- Update scan_breakouts_under_10() with new filters

Ref: MOMENTUM_SCANNER_ACTION_PLAN.md#ticket-001"

# Test commits
git commit -m "test(scanner): add tests for price change filters [TICKET-001]

- Test gap detection thresholds
- Test empty results handling
- Mock Finviz API responses"
```

---

## Testing Strategy

### Unit Tests Structure

```
tests/
├── test_scanner.py           # Breakout scanner tests
├── test_premarket_scanner.py # Pre-market gap tests
├── test_rvol.py              # RVOL calculation tests
├── test_indicator_utils.py   # RSI, ATR tests
├── fixtures/
│   ├── finviz_response.csv   # Mock Finviz data
│   └── rejected_items.jsonl  # Mock MOA data
└── conftest.py               # Shared fixtures
```

### Example Test

```python
# tests/test_scanner.py
import pytest
from unittest.mock import patch, MagicMock
from catalyst_bot.scanner import scan_breakouts_under_10, get_moa_priority_tickers

@pytest.fixture
def mock_finviz_response():
    return [
        {"ticker": "ACME", "price": 4.50, "relvolume": 3.2, "avgvol": 1200000},
        {"ticker": "BETA", "price": 2.10, "relvolume": 1.8, "avgvol": 800000},
        {"ticker": "GAMA", "price": 12.00, "relvolume": 4.0, "avgvol": 500000},  # Over $10
    ]

@patch("catalyst_bot.scanner.export_screener")
@patch("catalyst_bot.scanner.get_settings")
def test_scan_breakouts_filters_by_relvol(mock_settings, mock_export, mock_finviz_response):
    """Test that scanner filters by minimum relative volume."""
    mock_settings.return_value.feature_breakout_scanner = True
    mock_export.return_value = mock_finviz_response

    results = scan_breakouts_under_10(min_relvol=2.0)

    # Should only include ACME (RVOL 3.2), not BETA (RVOL 1.8)
    assert len(results) == 1
    assert results[0]["ticker"] == "ACME"


@patch("catalyst_bot.scanner.export_screener")
@patch("catalyst_bot.scanner.get_settings")
def test_scan_breakouts_excludes_over_10(mock_settings, mock_export, mock_finviz_response):
    """Test that scanner excludes stocks over $10."""
    mock_settings.return_value.feature_breakout_scanner = True
    mock_export.return_value = mock_finviz_response

    results = scan_breakouts_under_10(min_relvol=1.0)

    # Should not include GAMA (price $12)
    tickers = [r["ticker"] for r in results]
    assert "GAMA" not in tickers
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tickets in Phase 1 complete
- [ ] Unit tests passing (>90% coverage for new code)
- [ ] Config options documented in `.env.example`
- [ ] Feature flags default to OFF
- [ ] No hardcoded credentials

### Staging Deployment

```bash
# Deploy to staging with features OFF
FEATURE_BREAKOUT_SCANNER=0
FEATURE_PREMARKET_SCANNER=0
FEATURE_CONTINUOUS_SCANNER=0

# Run for 24h, check logs
tail -f logs/catalyst_bot.log | grep -E "scanner|breakout"
```

### Production Rollout

```bash
# Phase 1: Enable basic scanner
FEATURE_BREAKOUT_SCANNER=1
# Monitor for 2 days

# Phase 2: Enable pre-market
FEATURE_PREMARKET_SCANNER=1
# Monitor for 2 days

# Phase 3: Enable continuous
FEATURE_CONTINUOUS_SCANNER=1
```

### Rollback Plan

```bash
# Disable all scanners immediately
FEATURE_BREAKOUT_SCANNER=0
FEATURE_PREMARKET_SCANNER=0
FEATURE_CONTINUOUS_SCANNER=0

# Restart bot
systemctl restart catalyst-bot
```

---

## Appendix: Quick Reference

### Finviz Filter Cheat Sheet

```
Price Filters:
sh_price_u10    = Price under $10
sh_price_o0.5   = Price over $0.50

Volume Filters:
sh_avgvol_o500  = Avg volume > 500k
sh_relvol_o2    = Relative volume > 2x
sh_float_u50    = Float < 50M

Technical Filters:
ta_gap_u4       = Gap up > 4%
ta_gap_d4       = Gap down > 4%
ta_perf_do5     = Day performance > +5%
ta_perf_du5     = Day performance < -5%
ta_sma20_pa     = Price above SMA20
ta_sma50_pa     = Price above SMA50
ta_rsi_ob70     = RSI overbought (>70)
ta_rsi_os30     = RSI oversold (<30)
```

### Environment Variables

```bash
# Core Scanner
FEATURE_BREAKOUT_SCANNER=1
FEATURE_PREMARKET_SCANNER=1
FEATURE_CONTINUOUS_SCANNER=1
FEATURE_RSI_FILTER=1

# Thresholds
BREAKOUT_MIN_GAP_PCT=4.0
BREAKOUT_MIN_CHANGE_PCT=5.0
BREAKOUT_MIN_RELVOL=2.0
BREAKOUT_MIN_AVG_VOL=500000
BREAKOUT_MIN_ATR=0.25
BREAKOUT_PRICE_FLOOR=0.50
BREAKOUT_PRICE_CEILING=10.0

# Timing
CONTINUOUS_SCAN_INTERVAL_MIN=5
ALERT_RATE_LIMIT_MIN=30

# Finviz
FINVIZ_AUTH_TOKEN=your_elite_token
FINVIZ_SCREENER_VIEW=152
```

---

*Document Version: 1.0*
*Last Updated: 2025-11-28*
*Author: Claude (Anthropic)*
