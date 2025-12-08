# Prometheus Metrics Implementation Guide

**Version:** 2.0
**Created:** December 2025
**Updated:** December 2025
**Priority:** CRITICAL
**Estimated Implementation Time:** 3-4 hours
**Target Files:** `src/catalyst_bot/monitoring/metrics.py`, `src/catalyst_bot/monitoring/metrics_server.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Implementation Strategy](#implementation-strategy)
3. [Prerequisites](#prerequisites)
4. [Phase A: Core Metrics Module](#phase-a-core-metrics-module)
5. [Phase B: Integration](#phase-b-integration)
6. [Phase C: Local Visibility](#phase-c-local-visibility)
7. [Phase D: Cloud Migration (Future)](#phase-d-cloud-migration-future)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

The Catalyst-Bot has comprehensive monitoring documentation in `docs/deployment/monitoring.md` (lines 78-305) that defines a complete Prometheus metrics infrastructure. However, **no `metrics.py` file exists in the codebase**.

### Current State

| Component | Status | Location |
|-----------|--------|----------|
| Health endpoints | ✅ Exists | `src/catalyst_bot/health_endpoint.py` (port 8080) |
| Admin heartbeat | ✅ Exists | `src/catalyst_bot/runner.py` (Discord messages) |
| LLM usage tracking | ✅ Exists | `src/catalyst_bot/llm_usage_monitor.py` |
| JSON logging | ✅ Exists | `src/catalyst_bot/logging_utils.py` |
| **Prometheus metrics** | ❌ Missing | `src/catalyst_bot/monitoring/metrics.py` |
| **Metrics HTTP server** | ❌ Missing | `src/catalyst_bot/monitoring/metrics_server.py` |

### What We're Building

A lightweight metrics system that:
1. **Works locally** without Docker or external services
2. **Enhances existing Discord heartbeat** with performance data
3. **Exposes `/metrics` endpoint** for future Grafana Cloud integration
4. **Adds zero operational overhead** - no new services to manage

---

## Implementation Strategy

### Cloud-Ready Local Approach

```
NOW (Local Development)                    LATER (Hosted Production)
┌────────────────────────────────┐         ┌────────────────────────────────┐
│  Catalyst Bot                  │         │  Catalyst Bot                  │
│  + monitoring/metrics.py       │         │  + monitoring/metrics.py       │
│  + /metrics endpoint (9090)    │   ───►  │  + /metrics endpoint (9090)    │
│  + Enhanced Discord heartbeat  │         │  + Enhanced Discord heartbeat  │
│                                │         │                                │
│  View metrics via:             │         │  View metrics via:             │
│  • curl localhost:9090/metrics │         │  • Grafana Cloud (free tier)   │
│  • Discord heartbeat (hourly)  │         │  • Discord heartbeat (hourly)  │
│  • /health/detailed endpoint   │         │  • /health/detailed endpoint   │
└────────────────────────────────┘         └────────────────────────────────┘

No Docker required                         Just add Grafana Cloud credentials
No Prometheus server                       5-minute migration
No Grafana locally                         Same codebase, no changes needed
```

### What Gets Built vs What Gets Skipped

| Component | Build Now? | Reason |
|-----------|------------|--------|
| `metrics.py` (core definitions) | ✅ Yes | Required foundation |
| `metrics_server.py` (port 9090) | ✅ Yes | Cloud-ready endpoint |
| Enhanced Discord heartbeat | ✅ Yes | Immediate visibility |
| Health endpoint bridge | ✅ Yes | Quick metrics check |
| Docker Compose setup | ❌ Skip | Not needed locally |
| Local Prometheus server | ❌ Skip | Use Grafana Cloud later |
| Local Grafana instance | ❌ Skip | Use Grafana Cloud later |

---

## Prerequisites

### 1. Check Port Availability

Before starting, verify port 9090 is available:

```bash
# Linux/Mac
netstat -tuln 2>/dev/null | grep :9090 || ss -tuln 2>/dev/null | grep :9090 || echo "Port 9090 is FREE"

# Windows (PowerShell)
netstat -an | findstr ":9090" || Write-Host "Port 9090 is FREE"

# Alternative: Python one-liner
python -c "import socket; s=socket.socket(); result=s.connect_ex(('localhost',9090)); print('Port 9090 is FREE' if result != 0 else 'Port 9090 is IN USE'); s.close()"
```

If port 9090 is in use, set `METRICS_PORT` environment variable to a different port.

### 2. Install Python Dependencies

Add to `requirements.txt`:

```
prometheus-client==0.19.0
psutil>=5.9.0
```

Install:

```bash
pip install prometheus-client==0.19.0 psutil
```

### 3. Create Monitoring Directory

```bash
mkdir -p src/catalyst_bot/monitoring
touch src/catalyst_bot/monitoring/__init__.py
```

---

## Phase A: Core Metrics Module

### File Structure

```
src/catalyst_bot/
├── monitoring/
│   ├── __init__.py           # Package exports
│   ├── metrics.py            # Prometheus metrics definitions
│   └── metrics_server.py     # HTTP server for /metrics
```

### File: `src/catalyst_bot/monitoring/__init__.py`

```python
"""
Catalyst-Bot Monitoring Package

Provides Prometheus metrics instrumentation for observability.
Designed for local development with easy cloud migration path.
"""

from .metrics import (
    # Portfolio metrics
    portfolio_value,
    portfolio_cash,
    portfolio_buying_power,
    open_positions_count,

    # Performance metrics
    daily_pnl,
    win_rate,

    # Trading activity
    orders_total,
    trades_total,

    # Latency metrics
    order_latency,
    api_latency,
    cycle_duration,

    # Error metrics
    errors_total,
    api_errors_total,

    # Cycle metrics
    cycles_total,
    alerts_total,

    # Helper functions
    update_portfolio_metrics,
    record_order,
    record_trade,
    record_error,
    record_cycle,
    record_alert,
    measure_api_call,
    get_metrics_summary,
)

from .metrics_server import (
    start_metrics_server,
    stop_metrics_server,
    is_metrics_server_running,
)

__all__ = [
    # Metrics
    'portfolio_value', 'portfolio_cash', 'portfolio_buying_power',
    'open_positions_count', 'daily_pnl', 'win_rate',
    'orders_total', 'trades_total',
    'order_latency', 'api_latency', 'cycle_duration',
    'errors_total', 'api_errors_total',
    'cycles_total', 'alerts_total',

    # Functions
    'update_portfolio_metrics', 'record_order', 'record_trade',
    'record_error', 'record_cycle', 'record_alert',
    'measure_api_call', 'get_metrics_summary',
    'start_metrics_server', 'stop_metrics_server', 'is_metrics_server_running',
]
```

### File: `src/catalyst_bot/monitoring/metrics.py`

```python
"""
Prometheus metrics for Catalyst-Bot paper trading system.

Focused on actionable metrics:
- Portfolio performance (what matters for trading)
- Trading activity (orders, trades, outcomes)
- Latency (API performance)
- Errors (problems to fix)

Reference: docs/deployment/monitoring.md (lines 78-305)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from prometheus_client import Counter, Gauge, Histogram, REGISTRY

# =============================================================================
# Metric Prefix
# =============================================================================
METRIC_PREFIX = "catalyst_bot"


# =============================================================================
# Portfolio Metrics (Most Important)
# =============================================================================
portfolio_value = Gauge(
    f'{METRIC_PREFIX}_portfolio_value',
    'Current total portfolio value in USD'
)

portfolio_cash = Gauge(
    f'{METRIC_PREFIX}_portfolio_cash',
    'Available cash balance in USD'
)

portfolio_buying_power = Gauge(
    f'{METRIC_PREFIX}_portfolio_buying_power',
    'Total buying power (including margin)'
)

open_positions_count = Gauge(
    f'{METRIC_PREFIX}_open_positions',
    'Number of currently open positions'
)

daily_pnl = Gauge(
    f'{METRIC_PREFIX}_daily_pnl',
    'Daily profit/loss in USD'
)

win_rate = Gauge(
    f'{METRIC_PREFIX}_win_rate',
    'Percentage of profitable trades (0-100)'
)


# =============================================================================
# Trading Activity Metrics
# =============================================================================
orders_total = Counter(
    f'{METRIC_PREFIX}_orders_total',
    'Total orders placed',
    ['side', 'status']  # side: buy/sell, status: filled/rejected/cancelled
)

trades_total = Counter(
    f'{METRIC_PREFIX}_trades_total',
    'Total trades closed',
    ['result']  # result: win/loss/breakeven
)


# =============================================================================
# Latency Metrics
# =============================================================================
order_latency = Histogram(
    f'{METRIC_PREFIX}_order_latency_seconds',
    'Order execution latency (signal to fill)',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

api_latency = Histogram(
    f'{METRIC_PREFIX}_api_latency_seconds',
    'External API call latency',
    ['api_name'],  # alpaca, tiingo, gemini, discord
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

cycle_duration = Histogram(
    f'{METRIC_PREFIX}_cycle_duration_seconds',
    'Duration of each main loop cycle',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)


# =============================================================================
# Error Metrics
# =============================================================================
errors_total = Counter(
    f'{METRIC_PREFIX}_errors_total',
    'Total errors by type',
    ['error_type', 'component']
)

api_errors_total = Counter(
    f'{METRIC_PREFIX}_api_errors_total',
    'API errors by provider',
    ['api_name', 'status_code']
)


# =============================================================================
# Cycle Metrics
# =============================================================================
cycles_total = Counter(
    f'{METRIC_PREFIX}_cycles_total',
    'Total main loop cycles completed'
)

alerts_total = Counter(
    f'{METRIC_PREFIX}_alerts_sent_total',
    'Total alerts sent to Discord',
    ['category']  # breakout, sec_filing, earnings, catalyst
)

items_processed = Counter(
    f'{METRIC_PREFIX}_items_processed_total',
    'Total feed items processed',
    ['source']  # rss, sec, social
)


# =============================================================================
# Internal Tracking (for summary calculations)
# =============================================================================
_orders_filled = 0
_orders_total = 0
_trades_won = 0
_trades_total = 0
_errors_last_hour = []


# =============================================================================
# Helper Functions
# =============================================================================

def update_portfolio_metrics(data: Dict[str, Any]) -> None:
    """
    Update portfolio metrics.

    Args:
        data: Dict with portfolio_value, cash, buying_power, daily_pnl, positions

    Integration Point:
        runner.py - After trading_engine.update_positions()
        trading_engine.py:update_positions() - Line 372-384
    """
    if 'portfolio_value' in data:
        portfolio_value.set(data['portfolio_value'])
    if 'cash' in data:
        portfolio_cash.set(data['cash'])
    if 'buying_power' in data:
        portfolio_buying_power.set(data['buying_power'])
    if 'daily_pnl' in data:
        daily_pnl.set(data['daily_pnl'])
    if 'positions' in data:
        open_positions_count.set(data['positions'])


def record_order(side: str, status: str) -> None:
    """
    Record an order.

    Args:
        side: 'buy' or 'sell'
        status: 'filled', 'rejected', 'cancelled'

    Integration Point:
        trading_engine.py:_execute_signal() - Line 567-571
    """
    global _orders_filled, _orders_total
    orders_total.labels(side=side, status=status).inc()
    _orders_total += 1
    if status == 'filled':
        _orders_filled += 1


def record_trade(result: str) -> None:
    """
    Record a closed trade.

    Args:
        result: 'win', 'loss', or 'breakeven'

    Integration Point:
        trading_engine.py:_handle_close_signal() - Line 631-636
    """
    global _trades_won, _trades_total
    trades_total.labels(result=result).inc()
    _trades_total += 1
    if result == 'win':
        _trades_won += 1

    # Update win rate
    if _trades_total > 0:
        win_rate.set((_trades_won / _trades_total) * 100)


def record_error(error_type: str, component: str) -> None:
    """
    Record an error.

    Args:
        error_type: api_error, validation_error, timeout, etc.
        component: runner, trading_engine, broker, etc.

    Integration Point:
        All exception handlers throughout codebase
    """
    import time
    errors_total.labels(error_type=error_type, component=component).inc()
    _errors_last_hour.append(time.time())

    # Clean old errors (keep last hour only)
    cutoff = time.time() - 3600
    while _errors_last_hour and _errors_last_hour[0] < cutoff:
        _errors_last_hour.pop(0)


def record_cycle(duration_seconds: float, items: int, deduped: int, alerts: int,
                 source_breakdown: Optional[Dict[str, int]] = None) -> None:
    """
    Record cycle completion.

    Args:
        duration_seconds: How long the cycle took
        items: Items processed
        deduped: Items filtered
        alerts: Alerts sent
        source_breakdown: Optional {'rss': N, 'sec': N, 'social': N}

    Integration Point:
        runner.py - After _cycle() completes, Line 4099-4100
    """
    cycles_total.inc()
    cycle_duration.observe(duration_seconds)

    if source_breakdown:
        for source, count in source_breakdown.items():
            items_processed.labels(source=source).inc(count)


def record_alert(category: str = 'general') -> None:
    """
    Record alert sent.

    Args:
        category: breakout, sec_filing, earnings, catalyst, general

    Integration Point:
        alerts.py:send_alert_safe() - After successful send
    """
    alerts_total.labels(category=category).inc()


@contextmanager
def measure_api_call(api_name: str):
    """
    Context manager to measure API latency.

    Example:
        with measure_api_call('alpaca'):
            response = client.get_account()

    Integration Point:
        broker/alpaca_client.py - Wrap API calls
    """
    start = time.time()
    status = 'success'
    try:
        yield
    except Exception as e:
        status = type(e).__name__
        raise
    finally:
        duration = time.time() - start
        api_latency.labels(api_name=api_name).observe(duration)
        if status != 'success':
            api_errors_total.labels(api_name=api_name, status_code=status).inc()


def get_metrics_summary() -> Dict[str, Any]:
    """
    Get a summary of current metrics for heartbeat/health endpoint.

    Returns:
        Dict with key metrics formatted for display

    Usage:
        summary = get_metrics_summary()
        # Use in Discord heartbeat or /health/detailed
    """
    # Calculate order success rate
    order_success = 0
    if _orders_total > 0:
        order_success = round((_orders_filled / _orders_total) * 100, 1)

    # Get latency percentiles from histogram
    # Note: This is approximate - histograms don't store individual values
    avg_latency = "N/A"

    return {
        'portfolio': {
            'value': _get_gauge_value(portfolio_value),
            'cash': _get_gauge_value(portfolio_cash),
            'daily_pnl': _get_gauge_value(daily_pnl),
            'positions': int(_get_gauge_value(open_positions_count)),
        },
        'trading': {
            'orders_filled': _orders_filled,
            'orders_rejected': _orders_total - _orders_filled,
            'order_success_pct': order_success,
            'trades_won': _trades_won,
            'trades_lost': _trades_total - _trades_won,
            'win_rate_pct': round(_get_gauge_value(win_rate), 1),
        },
        'health': {
            'cycles_total': int(_get_counter_value(cycles_total)),
            'errors_last_hour': len(_errors_last_hour),
            'alerts_sent': _get_counter_total(alerts_total),
        },
    }


def _get_gauge_value(gauge: Gauge) -> float:
    """Extract current value from a Gauge."""
    try:
        return gauge._value.get()
    except Exception:
        return 0.0


def _get_counter_value(counter: Counter) -> float:
    """Extract current value from a Counter without labels."""
    try:
        return counter._value.get()
    except Exception:
        return 0.0


def _get_counter_total(counter: Counter) -> int:
    """Sum all label values for a Counter."""
    try:
        total = 0
        for metric in REGISTRY.collect():
            if metric.name == counter._name:
                for sample in metric.samples:
                    if sample.name.endswith('_total'):
                        total += int(sample.value)
        return total
    except Exception:
        return 0
```

### File: `src/catalyst_bot/monitoring/metrics_server.py`

```python
"""
Prometheus metrics HTTP server for Catalyst-Bot.

Exposes /metrics endpoint on port 9090 (configurable).
Designed for local development with cloud migration path.

Usage:
    from catalyst_bot.monitoring import start_metrics_server
    start_metrics_server(port=9090)

    # Check: curl http://localhost:9090/metrics
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Optional

from prometheus_client import start_http_server

# Get logger
try:
    from ..logging_utils import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger(__name__)

# Server state
_server_started = False


def is_port_available(port: int) -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check

    Returns:
        True if port is available, False if in use
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0  # 0 means connection succeeded (port in use)
    except Exception:
        return True  # Assume available if check fails


def start_metrics_server(port: Optional[int] = None) -> bool:
    """
    Start Prometheus metrics HTTP server.

    Args:
        port: Port to listen on (default: 9090 or METRICS_PORT env var)

    Returns:
        True if started successfully, False otherwise

    Integration Point:
        runner.py:runner_main() - After health server, Line 3848
    """
    global _server_started

    if _server_started:
        logger.debug("metrics_server_already_started")
        return True

    if port is None:
        port = int(os.getenv("METRICS_PORT", "9090"))

    # Check port availability first
    if not is_port_available(port):
        logger.warning(
            "metrics_server_port_in_use port=%d - try setting METRICS_PORT env var",
            port
        )
        return False

    try:
        start_http_server(port)
        _server_started = True
        logger.info(
            "metrics_server_started port=%d endpoint=http://localhost:%d/metrics",
            port, port
        )
        return True

    except Exception as e:
        logger.error("metrics_server_start_failed port=%d err=%s", port, str(e))
        return False


def stop_metrics_server() -> None:
    """Mark metrics server as stopped."""
    global _server_started
    _server_started = False
    logger.info("metrics_server_stopped")


def is_metrics_server_running() -> bool:
    """Check if metrics server is running."""
    return _server_started
```

---

## Phase B: Integration

### 1. runner.py - Start Metrics Server

**File:** `src/catalyst_bot/runner.py`
**Location:** After Line 3848 (after health server start)

```python
# ADD AFTER LINE 3848 (after health server start):

# Start Prometheus metrics server if enabled
if os.getenv("FEATURE_PROMETHEUS_METRICS", "1").strip().lower() in ("1", "true", "yes", "on"):
    try:
        from .monitoring import start_metrics_server
        metrics_port = int(os.getenv("METRICS_PORT", "9090"))
        if start_metrics_server(port=metrics_port):
            log.info("prometheus_metrics_enabled port=%d", metrics_port)
    except ImportError:
        log.debug("prometheus_metrics_module_not_available")
    except Exception as e:
        log.warning("prometheus_metrics_failed err=%s", str(e))
```

### 2. runner.py - Record Cycle Metrics

**File:** `src/catalyst_bot/runner.py`
**Location:** After Line 4100 (after CYCLE_DONE log)

```python
# ADD AFTER LINE 4100 (after log.info("CYCLE_DONE...")):

# Record Prometheus cycle metrics
try:
    from .monitoring import record_cycle
    record_cycle(
        duration_seconds=cycle_time,
        items=LAST_CYCLE_STATS.get('items', 0),
        deduped=LAST_CYCLE_STATS.get('deduped', 0),
        alerts=LAST_CYCLE_STATS.get('alerts', 0),
        source_breakdown=FEED_SOURCE_STATS.copy() if FEED_SOURCE_STATS else None,
    )
except Exception:
    pass  # Never crash on metrics
```

### 3. runner.py - Update Portfolio Metrics

**File:** `src/catalyst_bot/runner.py`
**Location:** After Line 4127 (after trading_engine.update_positions())

```python
# MODIFY the existing trading_engine block (Lines 4113-4127):

if trading_engine and getattr(settings, "FEATURE_PAPER_TRADING", False):
    try:
        metrics = run_async(trading_engine.update_positions(), timeout=10.0)
        if metrics.get("positions", 0) > 0:
            log.info(
                "portfolio_update positions=%d exposure=$%.2f pnl=$%.2f",
                metrics.get("positions", 0),
                metrics.get("exposure", 0.0),
                metrics.get("pnl", 0.0),
            )

        # ADD: Update Prometheus portfolio metrics
        try:
            from .monitoring import update_portfolio_metrics
            portfolio_metrics = run_async(trading_engine.get_portfolio_metrics(), timeout=5.0)
            if portfolio_metrics:
                update_portfolio_metrics({
                    'portfolio_value': portfolio_metrics.get('account_value', 0),
                    'cash': portfolio_metrics.get('cash', 0),
                    'buying_power': portfolio_metrics.get('buying_power', 0),
                    'daily_pnl': portfolio_metrics.get('total_unrealized_pnl', 0),
                    'positions': portfolio_metrics.get('total_positions', 0),
                })
        except Exception:
            pass

    except Exception as e:
        log.error("position_update_error err=%s", str(e), exc_info=True)
```

### 4. trading_engine.py - Record Orders

**File:** `src/catalyst_bot/trading/trading_engine.py`
**Location:** After Line 25 (imports) and in _execute_signal()

```python
# ADD AFTER LINE 25 (after existing imports):

# Prometheus metrics integration
try:
    from ..monitoring import record_order, record_trade, record_error
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


# MODIFY _execute_signal() - After Line 567:

if not result.success:
    if METRICS_AVAILABLE:
        record_order(signal.action, 'rejected')
    self.logger.warning(f"Order execution failed: {result.error_message}")
    return None

# After successful order fill (around Line 598):
if METRICS_AVAILABLE:
    record_order(signal.action, 'filled')
```

### 5. alerts.py - Record Alerts

**File:** `src/catalyst_bot/alerts.py`
**Location:** In send_alert_safe() after successful send

```python
# ADD at top of file (after imports):
try:
    from .monitoring import record_alert as _record_alert
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

# ADD in send_alert_safe() after successful webhook post:
if _METRICS_AVAILABLE:
    category = 'general'
    title = str(alert_data.get('title', '')).lower()
    if 'sec' in title or '8-k' in title or '424' in title:
        category = 'sec_filing'
    elif 'breakout' in title:
        category = 'breakout'
    elif 'earning' in title:
        category = 'earnings'
    _record_alert(category)
```

---

## Phase C: Local Visibility

### 1. Enhanced Admin Heartbeat

Add metrics summary to your existing Discord heartbeat. This provides visibility without any new services.

**File:** `src/catalyst_bot/runner.py`
**Location:** In `_send_heartbeat()` function

```python
# ADD to _send_heartbeat() function - include metrics summary in embed

def _build_heartbeat_embed(log, settings, reason: str, stats: dict) -> dict:
    """Build heartbeat embed with metrics summary."""

    # Get metrics summary if available
    metrics_section = ""
    try:
        from .monitoring import get_metrics_summary
        summary = get_metrics_summary()

        # Only show if we have trading data
        if summary['portfolio']['value'] > 0:
            metrics_section = (
                f"\n\n📊 **Performance**\n"
                f"├─ Portfolio: ${summary['portfolio']['value']:,.2f}\n"
                f"├─ Daily P&L: ${summary['portfolio']['daily_pnl']:+,.2f}\n"
                f"├─ Positions: {summary['portfolio']['positions']}\n"
                f"└─ Win Rate: {summary['trading']['win_rate_pct']:.1f}%"
            )

        # Always show order stats if any orders placed
        if summary['trading']['orders_filled'] + summary['trading']['orders_rejected'] > 0:
            metrics_section += (
                f"\n\n📈 **Orders**\n"
                f"├─ Filled: {summary['trading']['orders_filled']}\n"
                f"├─ Rejected: {summary['trading']['orders_rejected']}\n"
                f"└─ Success: {summary['trading']['order_success_pct']:.1f}%"
            )

        # Show errors if any in last hour
        if summary['health']['errors_last_hour'] > 0:
            metrics_section += (
                f"\n\n⚠️ **Errors** (last hour): {summary['health']['errors_last_hour']}"
            )

    except ImportError:
        pass  # Metrics module not available
    except Exception:
        pass  # Don't crash heartbeat on metrics error

    # Build embed with existing fields + metrics
    embed = {
        "title": f"💓 Heartbeat ({reason})",
        "description": f"Cycles: {stats.get('cycles', '—')} | Alerts: {stats.get('alerts', '—')}{metrics_section}",
        # ... rest of existing embed fields
    }

    return embed
```

### 2. Health Endpoint Bridge

Add metrics summary to `/health/detailed` endpoint.

**File:** `src/catalyst_bot/health_endpoint.py`
**Location:** In `_handle_detailed()` method

```python
# MODIFY _handle_detailed() to include metrics summary:

def _handle_detailed(self):
    """Detailed health endpoint with metrics summary."""
    try:
        health = get_health_status()

        # ADD: Include metrics summary if available
        try:
            from .monitoring import get_metrics_summary
            health['metrics'] = get_metrics_summary()
        except ImportError:
            pass  # Metrics module not available
        except Exception:
            health['metrics'] = {'error': 'Failed to collect metrics'}

        status_code = 200 if health.get("status") == "healthy" else 503
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(health, indent=2).encode())

    except Exception as e:
        # ... existing error handling
```

### 3. Quick CLI Check

Test metrics locally:

```bash
# View raw Prometheus metrics
curl -s http://localhost:9090/metrics | grep catalyst_bot

# View formatted health summary
curl -s http://localhost:8080/health/detailed | python -m json.tool

# One-liner to check key metrics
curl -s http://localhost:9090/metrics | grep -E "(portfolio_value|daily_pnl|orders_total|errors_total)"
```

---

## Phase D: Cloud Migration (Future)

When ready to deploy to hosted platform (1-2 months), add Grafana Cloud:

### Option 1: Grafana Cloud Free Tier

1. Sign up at https://grafana.com (free tier includes 10k metrics)
2. Get your Prometheus remote_write URL and credentials
3. Add Grafana Cloud Agent to push metrics:

```bash
# Install Grafana Agent
# Linux
curl -O -L "https://github.com/grafana/agent/releases/latest/download/grafana-agent-linux-amd64.zip"

# Or Docker
docker run grafana/agent:latest
```

4. Configure agent to scrape your `/metrics` endpoint:

```yaml
# agent-config.yaml
metrics:
  configs:
    - name: catalyst-bot
      scrape_configs:
        - job_name: catalyst-bot
          static_configs:
            - targets: ['localhost:9090']
      remote_write:
        - url: https://prometheus-us-central1.grafana.net/api/prom/push
          basic_auth:
            username: YOUR_GRAFANA_CLOUD_USER
            password: YOUR_GRAFANA_CLOUD_API_KEY
```

### Option 2: Other Cloud Providers

The `/metrics` endpoint works with any Prometheus-compatible service:
- Datadog
- New Relic
- AWS CloudWatch (via Prometheus agent)
- Azure Monitor

**No code changes needed** - just point the cloud service at your `/metrics` endpoint.

---

## Coding Tickets

### Phase A: Core Infrastructure

#### Ticket A.1: Create Monitoring Package
```
Title: Create monitoring package with Prometheus metrics
Priority: Critical
Estimate: 1-2 hours

Files to Create:
- src/catalyst_bot/monitoring/__init__.py
- src/catalyst_bot/monitoring/metrics.py
- src/catalyst_bot/monitoring/metrics_server.py

Acceptance Criteria:
- [ ] Port check function works
- [ ] Metrics server starts on port 9090
- [ ] curl http://localhost:9090/metrics returns valid output
- [ ] get_metrics_summary() returns formatted dict
```

#### Ticket A.2: Add Dependencies
```
Title: Add prometheus-client to requirements.txt
Priority: Critical
Estimate: 5 minutes

Tasks:
1. Add prometheus-client==0.19.0 to requirements.txt
2. Add psutil>=5.9.0 to requirements.txt
3. pip install -r requirements.txt
```

### Phase B: Integration

#### Ticket B.1: Integrate with runner.py
```
Title: Add metrics collection to main loop
Priority: High
Estimate: 45 minutes

File: src/catalyst_bot/runner.py
Lines: 3848, 4100, 4127

Tasks:
1. Start metrics server after health endpoint
2. Record cycle metrics after _cycle()
3. Update portfolio metrics after trading_engine.update_positions()

Acceptance Criteria:
- [ ] Metrics server starts on bot boot
- [ ] catalyst_bot_cycles_total increments each cycle
- [ ] Portfolio metrics update when trading engine active
```

#### Ticket B.2: Integrate with trading_engine.py
```
Title: Add order/trade metrics to trading engine
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/trading/trading_engine.py

Tasks:
1. Import metrics functions with graceful fallback
2. Call record_order() on order fill/reject
3. Call record_trade() on position close

Acceptance Criteria:
- [ ] catalyst_bot_orders_total increments on orders
- [ ] catalyst_bot_trades_total increments on closes
- [ ] No crashes if metrics module unavailable
```

#### Ticket B.3: Integrate with alerts.py
```
Title: Track alerts by category
Priority: Medium
Estimate: 15 minutes

File: src/catalyst_bot/alerts.py

Tasks:
1. Import record_alert with fallback
2. Categorize alerts by content
3. Call record_alert() after successful send

Acceptance Criteria:
- [ ] catalyst_bot_alerts_sent_total increments
- [ ] Categories: sec_filing, breakout, earnings, general
```

### Phase C: Local Visibility

#### Ticket C.1: Enhance Admin Heartbeat
```
Title: Add metrics summary to Discord heartbeat
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/runner.py

Tasks:
1. Call get_metrics_summary() in heartbeat builder
2. Format metrics for Discord embed
3. Only show sections with data

Acceptance Criteria:
- [ ] Heartbeat shows portfolio value if trading active
- [ ] Heartbeat shows order success rate if orders placed
- [ ] Heartbeat shows error count if errors occurred
- [ ] Graceful fallback if metrics unavailable
```

#### Ticket C.2: Bridge to Health Endpoint
```
Title: Add metrics to /health/detailed
Priority: Medium
Estimate: 15 minutes

File: src/catalyst_bot/health_endpoint.py

Tasks:
1. Import get_metrics_summary
2. Add 'metrics' key to health response
3. Handle import/runtime errors gracefully

Acceptance Criteria:
- [ ] /health/detailed includes metrics object
- [ ] No errors if metrics module unavailable
```

---

## Testing & Verification

### 1. Quick Smoke Test

```bash
# 1. Check port availability
python -c "import socket; s=socket.socket(); print('Port 9090:', 'FREE' if s.connect_ex(('localhost',9090)) != 0 else 'IN USE'); s.close()"

# 2. Start bot with metrics
FEATURE_PROMETHEUS_METRICS=1 python -m catalyst_bot.runner --once

# 3. Check metrics endpoint
curl -s http://localhost:9090/metrics | head -20

# 4. Check health endpoint
curl -s http://localhost:8080/health/detailed | python -m json.tool
```

### 2. Verify Key Metrics

```bash
# After running a few cycles, verify:
curl -s http://localhost:9090/metrics | grep -E "^catalyst_bot"

# Expected output includes:
# catalyst_bot_cycles_total 5
# catalyst_bot_portfolio_value 100000
# catalyst_bot_alerts_sent_total{category="general"} 2
```

### 3. Unit Test

```python
# tests/test_metrics.py
import pytest

def test_metrics_import():
    """Verify metrics module imports cleanly."""
    from catalyst_bot.monitoring import (
        record_cycle,
        record_order,
        get_metrics_summary,
        start_metrics_server,
    )
    assert callable(record_cycle)
    assert callable(get_metrics_summary)

def test_metrics_summary():
    """Verify summary returns expected structure."""
    from catalyst_bot.monitoring import get_metrics_summary
    summary = get_metrics_summary()
    assert 'portfolio' in summary
    assert 'trading' in summary
    assert 'health' in summary
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_PROMETHEUS_METRICS` | `1` | Enable/disable metrics server |
| `METRICS_PORT` | `9090` | Port for /metrics endpoint |

---

## Summary

This implementation provides:

1. **Immediate Value** - Metrics in Discord heartbeat without new services
2. **Future Ready** - Standard `/metrics` endpoint for Grafana Cloud migration
3. **Zero Overhead** - No Docker, no Prometheus server, no Grafana locally
4. **Graceful Fallback** - Bot works fine if metrics module unavailable

**Implementation Order:**
1. Phase A: Create monitoring package (1-2 hours)
2. Phase B: Wire into runner.py and trading_engine.py (1 hour)
3. Phase C: Enhance heartbeat and health endpoint (45 min)
4. Phase D: Add Grafana Cloud when hosting (future, 30 min)

---

**End of Implementation Guide**
