# Prometheus Metrics Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** CRITICAL
**Estimated Implementation Time:** 4-6 hours
**Target Files:** `src/catalyst_bot/monitoring/metrics.py`, `src/catalyst_bot/monitoring/metrics_server.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Implementation Files](#implementation-files)
5. [Core Metrics Module](#core-metrics-module)
6. [Metrics Server Module](#metrics-server-module)
7. [Integration Points](#integration-points)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)
10. [Deployment Configuration](#deployment-configuration)

---

## Overview

### Problem Statement

The Catalyst-Bot has comprehensive monitoring documentation in `docs/deployment/monitoring.md` (lines 78-305) that defines a complete Prometheus metrics infrastructure. However, **no `metrics.py` file exists in the codebase**.

### Current State

| Component | Status | Location |
|-----------|--------|----------|
| Health endpoints | ✅ Exists | `src/catalyst_bot/health_endpoint.py` (port 8080) |
| LLM usage tracking | ✅ Exists | `src/catalyst_bot/llm_usage_monitor.py` |
| JSON logging | ✅ Exists | `src/catalyst_bot/logging_utils.py` |
| **Prometheus metrics** | ❌ Missing | `src/catalyst_bot/monitoring/metrics.py` |
| **Metrics HTTP server** | ❌ Missing | `src/catalyst_bot/monitoring/metrics_server.py` |

### Missing Metrics Categories

1. **Portfolio Metrics** - portfolio_value, cash, buying_power
2. **Performance Metrics** - daily_pnl, cumulative_pnl, sharpe_ratio, max_drawdown, win_rate
3. **Trading Activity** - orders_total, trades_total, order_success_rate
4. **Latency Histograms** - order_latency, api_latency, signal_processing_time
5. **Error Counters** - errors_total, api_errors_total
6. **System Metrics** - CPU, memory, disk usage

### Data Benefit

Real-time visibility into performance, latency trends, error patterns, and system health - enabling proactive optimization and alerting.

---

## Prerequisites

### 1. Install Python Dependencies

Add to `requirements.txt`:

```
prometheus-client==0.19.0
psutil>=5.9.0
```

Install:

```bash
pip install prometheus-client==0.19.0 psutil
```

### 2. Create Monitoring Directory

```bash
mkdir -p src/catalyst_bot/monitoring
touch src/catalyst_bot/monitoring/__init__.py
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Catalyst-Bot Application                                               │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  runner.py (main loop)                                             │ │
│  │  Lines 3959-4153                                                   │ │
│  │  • Calls metrics.update_cycle_metrics() after each cycle           │ │
│  │  • Calls metrics.update_system_metrics() every 15s                 │ │
│  └───────────────────┬────────────────────────────────────────────────┘ │
│                      │                                                   │
│  ┌───────────────────┴────────────────────────────────────────────────┐ │
│  │  trading_engine.py                                                  │ │
│  │  Lines 271-606                                                      │ │
│  │  • Records order/trade metrics in _execute_signal()                 │ │
│  │  • Updates portfolio metrics in update_positions()                  │ │
│  │  • Tracks latency with context managers                            │ │
│  └───────────────────┬────────────────────────────────────────────────┘ │
│                      │                                                   │
│  ┌───────────────────┴────────────────────────────────────────────────┐ │
│  │  monitoring/metrics.py                                              │ │
│  │  • All Prometheus Gauge, Counter, Histogram definitions            │ │
│  │  • Helper functions for updating metrics                           │ │
│  └───────────────────┬────────────────────────────────────────────────┘ │
│                      │                                                   │
│  ┌───────────────────┴────────────────────────────────────────────────┐ │
│  │  monitoring/metrics_server.py                                       │ │
│  │  • HTTP server on port 9090                                        │ │
│  │  • /metrics endpoint for Prometheus scraping                       │ │
│  └───────────────────┬────────────────────────────────────────────────┘ │
└──────────────────────┼──────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Prometheus Server (scrapes every 15s)                                  │
│  → Grafana Dashboards                                                   │
│  → AlertManager                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Files

### File Structure

```
src/catalyst_bot/
├── monitoring/
│   ├── __init__.py           # NEW: Package init with exports
│   ├── metrics.py            # NEW: All Prometheus metrics definitions
│   └── metrics_server.py     # NEW: HTTP server for /metrics endpoint
├── runner.py                 # MODIFY: Add metrics integration
├── trading/
│   └── trading_engine.py     # MODIFY: Add trading metrics
├── health_monitor.py         # MODIFY: Bridge to Prometheus metrics
└── health_endpoint.py        # EXISTING: Keep as-is (port 8080)
```

---

## Core Metrics Module

### File: `src/catalyst_bot/monitoring/__init__.py`

```python
"""
Catalyst-Bot Monitoring Package

Provides Prometheus metrics instrumentation for observability.
"""

from .metrics import (
    # Portfolio metrics
    portfolio_value,
    portfolio_cash,
    portfolio_buying_power,

    # Position metrics
    open_positions_count,
    position_value,
    position_pnl,

    # Performance metrics
    daily_pnl,
    cumulative_pnl,
    sharpe_ratio,
    max_drawdown,
    win_rate,

    # Trading activity
    orders_total,
    trades_total,
    order_success_rate,

    # Latency metrics
    order_latency,
    api_latency,
    signal_processing_time,
    cycle_duration,

    # Error metrics
    errors_total,
    api_errors_total,

    # System metrics
    system_cpu_percent,
    system_memory_mb,
    system_disk_usage_percent,

    # Cycle metrics
    cycles_total,
    alerts_total,
    items_processed,
    items_deduped,

    # Helper functions
    update_portfolio_metrics,
    update_position_metrics,
    update_performance_metrics,
    record_order,
    record_trade,
    record_error,
    record_api_call,
    record_cycle,
    measure_api_call,
    measure_signal_processing,
    update_system_metrics,
)

from .metrics_server import start_metrics_server, stop_metrics_server

__all__ = [
    # Metrics
    'portfolio_value', 'portfolio_cash', 'portfolio_buying_power',
    'open_positions_count', 'position_value', 'position_pnl',
    'daily_pnl', 'cumulative_pnl', 'sharpe_ratio', 'max_drawdown', 'win_rate',
    'orders_total', 'trades_total', 'order_success_rate',
    'order_latency', 'api_latency', 'signal_processing_time', 'cycle_duration',
    'errors_total', 'api_errors_total',
    'system_cpu_percent', 'system_memory_mb', 'system_disk_usage_percent',
    'cycles_total', 'alerts_total', 'items_processed', 'items_deduped',

    # Functions
    'update_portfolio_metrics', 'update_position_metrics', 'update_performance_metrics',
    'record_order', 'record_trade', 'record_error', 'record_api_call', 'record_cycle',
    'measure_api_call', 'measure_signal_processing', 'update_system_metrics',
    'start_metrics_server', 'stop_metrics_server',
]
```

### File: `src/catalyst_bot/monitoring/metrics.py`

```python
"""
Prometheus metrics for Catalyst-Bot paper trading system.

This module defines all Prometheus metrics for monitoring the bot's:
- Portfolio performance
- Trading activity
- API latencies
- System resources
- Error rates

Reference: docs/deployment/monitoring.md (lines 78-305)
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram, Summary

# Try to import psutil for system metrics
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# =============================================================================
# Metric Prefix
# =============================================================================
METRIC_PREFIX = "catalyst_bot"


# =============================================================================
# Portfolio Metrics (docs/deployment/monitoring.md:89-102)
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
    'Total buying power (including leverage)'
)


# =============================================================================
# Position Metrics (docs/deployment/monitoring.md:104-122)
# =============================================================================
open_positions_count = Gauge(
    f'{METRIC_PREFIX}_open_positions',
    'Number of currently open positions'
)

position_value = Gauge(
    f'{METRIC_PREFIX}_position_value',
    'Value of individual position',
    ['ticker', 'side']  # Labels: ticker=AAPL, side=long/short
)

position_pnl = Gauge(
    f'{METRIC_PREFIX}_position_pnl',
    'Unrealized P&L for individual position',
    ['ticker', 'side']
)


# =============================================================================
# Performance Metrics (docs/deployment/monitoring.md:127-151)
# =============================================================================
daily_pnl = Gauge(
    f'{METRIC_PREFIX}_daily_pnl',
    'Daily profit/loss in USD'
)

cumulative_pnl = Gauge(
    f'{METRIC_PREFIX}_cumulative_pnl',
    'Cumulative profit/loss since inception'
)

sharpe_ratio = Gauge(
    f'{METRIC_PREFIX}_sharpe_ratio',
    'Rolling 30-day Sharpe ratio'
)

max_drawdown = Gauge(
    f'{METRIC_PREFIX}_max_drawdown',
    'Maximum drawdown from peak (negative value, e.g., -0.10 = -10%)'
)

win_rate = Gauge(
    f'{METRIC_PREFIX}_win_rate',
    'Percentage of profitable trades (0-100)'
)


# =============================================================================
# Trading Activity Metrics (docs/deployment/monitoring.md:155-171)
# =============================================================================
orders_total = Counter(
    f'{METRIC_PREFIX}_orders_total',
    'Total orders placed',
    ['side', 'status']  # side: buy/sell, status: filled/rejected/cancelled/pending
)

trades_total = Counter(
    f'{METRIC_PREFIX}_trades_total',
    'Total trades executed',
    ['ticker', 'side', 'result']  # result: win/loss/breakeven
)

order_success_rate = Gauge(
    f'{METRIC_PREFIX}_order_success_rate',
    'Percentage of successfully filled orders (0-100)'
)


# =============================================================================
# Latency Metrics (docs/deployment/monitoring.md:175-193)
# =============================================================================
order_latency = Histogram(
    f'{METRIC_PREFIX}_order_latency_seconds',
    'Order execution latency (time from signal to fill)',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

api_latency = Histogram(
    f'{METRIC_PREFIX}_api_latency_seconds',
    'External API call latency',
    ['api_name'],  # api_name: alpaca, tiingo, gemini, finnhub, discord
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

signal_processing_time = Histogram(
    f'{METRIC_PREFIX}_signal_processing_seconds',
    'Time to process trading signal (from scored item to order placement)',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

cycle_duration = Histogram(
    f'{METRIC_PREFIX}_cycle_duration_seconds',
    'Duration of each main loop cycle',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)


# =============================================================================
# Error Metrics (docs/deployment/monitoring.md:197-208)
# =============================================================================
errors_total = Counter(
    f'{METRIC_PREFIX}_errors_total',
    'Total errors by type',
    ['error_type', 'component']
    # error_type: api_error, validation_error, execution_error, timeout, etc.
    # component: runner, trading_engine, broker, enrichment, etc.
)

api_errors_total = Counter(
    f'{METRIC_PREFIX}_api_errors_total',
    'API errors by provider',
    ['api_name', 'status_code']
    # api_name: alpaca, tiingo, gemini, finnhub, discord
    # status_code: 429, 500, 503, timeout, etc.
)


# =============================================================================
# Cycle Metrics (Catalyst-Bot specific)
# =============================================================================
cycles_total = Counter(
    f'{METRIC_PREFIX}_cycles_total',
    'Total number of main loop cycles completed'
)

alerts_total = Counter(
    f'{METRIC_PREFIX}_alerts_sent_total',
    'Total alerts sent to Discord',
    ['category']  # category: breakout, sec_filing, earnings, catalyst, etc.
)

items_processed = Counter(
    f'{METRIC_PREFIX}_items_processed_total',
    'Total feed items processed',
    ['source']  # source: rss, sec, social
)

items_deduped = Counter(
    f'{METRIC_PREFIX}_items_deduped_total',
    'Total items filtered by deduplication'
)


# =============================================================================
# System Metrics (docs/deployment/monitoring.md:227-240)
# =============================================================================
system_cpu_percent = Gauge(
    f'{METRIC_PREFIX}_cpu_percent',
    'CPU usage percentage (process)'
)

system_memory_mb = Gauge(
    f'{METRIC_PREFIX}_memory_mb',
    'Memory usage in MB (process RSS)'
)

system_disk_usage_percent = Gauge(
    f'{METRIC_PREFIX}_disk_usage_percent',
    'Disk usage percentage for data directory'
)


# =============================================================================
# LLM Metrics (Integration with llm_usage_monitor.py)
# =============================================================================
llm_requests_total = Counter(
    f'{METRIC_PREFIX}_llm_requests_total',
    'Total LLM API requests',
    ['provider', 'model']  # provider: gemini, anthropic, local
)

llm_tokens_total = Counter(
    f'{METRIC_PREFIX}_llm_tokens_total',
    'Total LLM tokens used',
    ['provider', 'direction']  # direction: input, output
)

llm_cost_total = Counter(
    f'{METRIC_PREFIX}_llm_cost_dollars',
    'Total LLM cost in dollars',
    ['provider']
)

llm_latency = Histogram(
    f'{METRIC_PREFIX}_llm_latency_seconds',
    'LLM API call latency',
    ['provider'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)


# =============================================================================
# Circuit Breaker Metrics
# =============================================================================
circuit_breaker_status = Gauge(
    f'{METRIC_PREFIX}_circuit_breaker_active',
    'Circuit breaker status (1 = active/trading disabled, 0 = inactive)'
)

circuit_breaker_triggers = Counter(
    f'{METRIC_PREFIX}_circuit_breaker_triggers_total',
    'Total circuit breaker activations',
    ['reason']  # reason: daily_loss, max_drawdown, error_rate
)


# =============================================================================
# Helper Functions (docs/deployment/monitoring.md:245-305)
# =============================================================================

def update_portfolio_metrics(portfolio_data: Dict[str, Any]) -> None:
    """
    Update portfolio-related metrics.

    Args:
        portfolio_data: Dictionary with keys:
            - portfolio_value (float): Total portfolio value
            - cash (float): Available cash
            - buying_power (float): Total buying power
            - daily_pnl (float): Today's P&L
            - cumulative_pnl (float): All-time P&L

    Example:
        >>> update_portfolio_metrics({
        ...     'portfolio_value': 105432.50,
        ...     'cash': 50000.00,
        ...     'buying_power': 100000.00,
        ...     'daily_pnl': 1250.50,
        ...     'cumulative_pnl': 5432.50,
        ... })

    Integration Point:
        trading_engine.py:update_positions() - Line 372-384
    """
    portfolio_value.set(portfolio_data.get('portfolio_value', 0))
    portfolio_cash.set(portfolio_data.get('cash', 0))
    portfolio_buying_power.set(portfolio_data.get('buying_power', 0))
    daily_pnl.set(portfolio_data.get('daily_pnl', 0))
    cumulative_pnl.set(portfolio_data.get('cumulative_pnl', 0))


def update_position_metrics(positions: List[Dict[str, Any]]) -> None:
    """
    Update position-related metrics.

    Args:
        positions: List of position dictionaries, each with:
            - ticker (str): Stock symbol
            - side (str): 'long' or 'short'
            - market_value (float): Current position value
            - unrealized_pnl (float): Unrealized P&L

    Example:
        >>> update_position_metrics([
        ...     {'ticker': 'AAPL', 'side': 'long', 'market_value': 15000.0, 'unrealized_pnl': 500.0},
        ...     {'ticker': 'TSLA', 'side': 'long', 'market_value': 8000.0, 'unrealized_pnl': -200.0},
        ... ])

    Integration Point:
        trading_engine.py:update_positions() - Line 349-355
    """
    # Update total count
    open_positions_count.set(len(positions))

    # Update per-position metrics
    for pos in positions:
        ticker = pos.get('ticker', 'UNKNOWN')
        side = pos.get('side', 'long')

        position_value.labels(ticker=ticker, side=side).set(
            pos.get('market_value', 0)
        )
        position_pnl.labels(ticker=ticker, side=side).set(
            pos.get('unrealized_pnl', 0)
        )


def update_performance_metrics(
    win_rate_pct: float,
    sharpe: float,
    drawdown: float,
) -> None:
    """
    Update performance-related metrics.

    Args:
        win_rate_pct: Win rate as percentage (0-100)
        sharpe: Sharpe ratio (typically 0-3)
        drawdown: Max drawdown as negative decimal (e.g., -0.10 for -10%)

    Example:
        >>> update_performance_metrics(
        ...     win_rate_pct=62.5,
        ...     sharpe=1.85,
        ...     drawdown=-0.08,
        ... )

    Integration Point:
        trading_engine.py:get_portfolio_metrics() - Line 887-916
    """
    win_rate.set(win_rate_pct)
    sharpe_ratio.set(sharpe)
    max_drawdown.set(drawdown)


def record_order(side: str, status: str) -> None:
    """
    Record order execution.

    Args:
        side: 'buy' or 'sell'
        status: 'filled', 'rejected', 'cancelled', 'pending', 'expired'

    Example:
        >>> record_order('buy', 'filled')
        >>> record_order('sell', 'rejected')

    Integration Points:
        trading_engine.py:_execute_signal() - Line 567-571
        execution/order_executor.py - After order submission
    """
    orders_total.labels(side=side, status=status).inc()

    # Update success rate
    # Note: This is a simplified calculation; for accuracy,
    # track filled/total in a separate counter
    _update_order_success_rate()


def _update_order_success_rate() -> None:
    """Internal: Recalculate order success rate."""
    # This would need access to the counter values
    # For now, this is a placeholder - actual implementation
    # should track filled vs total orders
    pass


def record_trade(ticker: str, side: str, result: str) -> None:
    """
    Record completed trade.

    Args:
        ticker: Stock symbol
        side: 'buy' or 'sell'
        result: 'win', 'loss', or 'breakeven'

    Example:
        >>> record_trade('AAPL', 'sell', 'win')
        >>> record_trade('TSLA', 'sell', 'loss')

    Integration Point:
        trading_engine.py:_handle_close_signal() - Line 631-636
        portfolio/position_manager.py - On position close
    """
    trades_total.labels(ticker=ticker, side=side, result=result).inc()


def record_error(error_type: str, component: str) -> None:
    """
    Record an error occurrence.

    Args:
        error_type: Type of error (api_error, validation_error, etc.)
        component: Component where error occurred (runner, trading_engine, etc.)

    Example:
        >>> record_error('api_error', 'trading_engine')
        >>> record_error('timeout', 'broker')

    Integration Points:
        runner.py:_cycle() - In exception handlers
        trading_engine.py - All except blocks
    """
    errors_total.labels(error_type=error_type, component=component).inc()


def record_api_call(api_name: str, status_code: str, latency_seconds: float) -> None:
    """
    Record an API call with latency and status.

    Args:
        api_name: API provider (alpaca, tiingo, gemini, finnhub, discord)
        status_code: HTTP status or 'success', 'timeout', 'error'
        latency_seconds: Call duration in seconds

    Example:
        >>> record_api_call('alpaca', 'success', 0.35)
        >>> record_api_call('tiingo', '429', 1.2)

    Integration Points:
        broker/alpaca_client.py - All API methods
        feeds.py - Data fetching calls
    """
    api_latency.labels(api_name=api_name).observe(latency_seconds)

    # Record errors for non-success calls
    if status_code not in ('success', '200', '201', '204'):
        api_errors_total.labels(api_name=api_name, status_code=status_code).inc()


def record_cycle(
    duration_seconds: float,
    items: int,
    deduped: int,
    alerts: int,
    source_breakdown: Optional[Dict[str, int]] = None,
) -> None:
    """
    Record cycle completion metrics.

    Args:
        duration_seconds: Cycle duration
        items: Total items processed
        deduped: Items filtered by dedup
        alerts: Alerts sent
        source_breakdown: Optional dict with {'rss': N, 'sec': N, 'social': N}

    Example:
        >>> record_cycle(
        ...     duration_seconds=15.5,
        ...     items=150,
        ...     deduped=45,
        ...     alerts=3,
        ...     source_breakdown={'rss': 100, 'sec': 30, 'social': 20},
        ... )

    Integration Point:
        runner.py - After _cycle() completes, around Line 4099-4100
    """
    cycles_total.inc()
    cycle_duration.observe(duration_seconds)

    # Note: For counters, we increment by the count
    items_deduped.inc(deduped)

    # Track source breakdown
    if source_breakdown:
        for source, count in source_breakdown.items():
            items_processed.labels(source=source).inc(count)
    else:
        items_processed.labels(source='unknown').inc(items)


def record_alert(category: str = 'general') -> None:
    """
    Record an alert sent to Discord.

    Args:
        category: Alert category (breakout, sec_filing, earnings, catalyst, etc.)

    Example:
        >>> record_alert('breakout')
        >>> record_alert('sec_filing')

    Integration Point:
        alerts.py:send_alert_safe() - After successful send
    """
    alerts_total.labels(category=category).inc()


@contextmanager
def measure_api_call(api_name: str):
    """
    Context manager to measure API call latency.

    Args:
        api_name: API provider name

    Example:
        >>> with measure_api_call('alpaca'):
        ...     response = broker.get_account()

    Integration Points:
        broker/alpaca_client.py - Wrap all API calls
        feeds.py - Wrap external API calls
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


@contextmanager
def measure_signal_processing():
    """
    Context manager to measure signal processing time.

    Example:
        >>> with measure_signal_processing():
        ...     signal = generator.generate_signal(scored_item)
        ...     position = await executor.execute(signal)

    Integration Point:
        trading_engine.py:process_scored_item() - Line 290-324
    """
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        signal_processing_time.observe(duration)


@contextmanager
def measure_order_execution():
    """
    Context manager to measure order execution latency.

    Example:
        >>> with measure_order_execution():
        ...     result = await executor.execute_signal(signal)

    Integration Point:
        trading_engine.py:_execute_signal() - Line 560-566
    """
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        order_latency.observe(duration)


def update_system_metrics() -> None:
    """
    Update system resource metrics.

    Should be called periodically (e.g., every 15-30 seconds).

    Example:
        >>> update_system_metrics()  # Call in background thread or main loop

    Integration Point:
        runner.py:runner_main() - In main loop, every N cycles
    """
    if not PSUTIL_AVAILABLE:
        return

    try:
        # CPU usage (for this process)
        process = psutil.Process(os.getpid())
        cpu_percent = process.cpu_percent(interval=0.1)
        system_cpu_percent.set(cpu_percent)

        # Memory usage (RSS in MB)
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        system_memory_mb.set(memory_mb)

        # Disk usage (for data directory)
        data_dir = os.getenv('DATA_DIR', 'data')
        if os.path.exists(data_dir):
            disk = psutil.disk_usage(data_dir)
            system_disk_usage_percent.set(disk.percent)
        else:
            # Fall back to root
            disk = psutil.disk_usage('/')
            system_disk_usage_percent.set(disk.percent)

    except Exception:
        # Don't crash on metrics collection errors
        pass


def update_circuit_breaker(active: bool, reason: Optional[str] = None) -> None:
    """
    Update circuit breaker status.

    Args:
        active: True if circuit breaker is active (trading disabled)
        reason: Reason for activation (daily_loss, max_drawdown, error_rate)

    Example:
        >>> update_circuit_breaker(True, 'daily_loss')
        >>> update_circuit_breaker(False)

    Integration Point:
        trading_engine.py:_update_circuit_breaker() - Line 506-514
    """
    circuit_breaker_status.set(1 if active else 0)
    if active and reason:
        circuit_breaker_triggers.labels(reason=reason).inc()


def record_llm_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    latency_seconds: float,
) -> None:
    """
    Record LLM API usage metrics.

    Args:
        provider: LLM provider (gemini, anthropic, local)
        model: Model name
        input_tokens: Input token count
        output_tokens: Output token count
        cost: Cost in dollars
        latency_seconds: API call latency

    Example:
        >>> record_llm_usage(
        ...     provider='gemini',
        ...     model='gemini-2.5-flash',
        ...     input_tokens=1500,
        ...     output_tokens=500,
        ...     cost=0.0025,
        ...     latency_seconds=2.3,
        ... )

    Integration Point:
        llm_usage_monitor.py:log_usage() - Line 199-278
    """
    llm_requests_total.labels(provider=provider, model=model).inc()
    llm_tokens_total.labels(provider=provider, direction='input').inc(input_tokens)
    llm_tokens_total.labels(provider=provider, direction='output').inc(output_tokens)
    llm_cost_total.labels(provider=provider).inc(cost)
    llm_latency.labels(provider=provider).observe(latency_seconds)
```

---

## Metrics Server Module

### File: `src/catalyst_bot/monitoring/metrics_server.py`

```python
"""
Prometheus metrics HTTP server for Catalyst-Bot.

Exposes metrics on port 9090 (configurable via METRICS_PORT env var).
Runs in a daemon thread alongside the main bot.

Reference: docs/deployment/monitoring.md (lines 307-339)
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from prometheus_client import start_http_server, REGISTRY

# Get logger
try:
    from ..logging_utils import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger(__name__)


# Global server state
_server_thread: Optional[threading.Thread] = None
_server_started = False


def start_metrics_server(port: Optional[int] = None) -> bool:
    """
    Start Prometheus metrics HTTP server in background thread.

    Args:
        port: Port to listen on (default: 9090, or METRICS_PORT env var)

    Returns:
        True if server started successfully, False otherwise

    Example:
        >>> from catalyst_bot.monitoring import start_metrics_server
        >>> start_metrics_server(port=9090)
        True

    Integration Point:
        runner.py:runner_main() - After health server start, around Line 3844
    """
    global _server_thread, _server_started

    if _server_started:
        logger.warning("metrics_server_already_started")
        return True

    if port is None:
        port = int(os.getenv("METRICS_PORT", "9090"))

    try:
        # Start Prometheus HTTP server
        # This creates a daemon thread internally
        start_http_server(port)
        _server_started = True

        logger.info(
            "metrics_server_started port=%d endpoint=http://localhost:%d/metrics",
            port, port
        )
        return True

    except OSError as e:
        if "Address already in use" in str(e):
            logger.warning(
                "metrics_server_port_in_use port=%d - another instance may be running",
                port
            )
        else:
            logger.error("metrics_server_start_failed port=%d err=%s", port, str(e))
        return False
    except Exception as e:
        logger.error("metrics_server_start_failed port=%d err=%s", port, str(e))
        return False


def stop_metrics_server() -> None:
    """
    Stop the metrics server (if running).

    Note: The prometheus_client start_http_server() creates a daemon thread
    that will automatically stop when the main process exits. This function
    is provided for explicit cleanup if needed.

    Integration Point:
        runner.py:runner_main() - At end of main loop, around Line 4160
    """
    global _server_started
    _server_started = False
    logger.info("metrics_server_stopped")


def is_metrics_server_running() -> bool:
    """Check if metrics server is running."""
    return _server_started


# Standalone test
if __name__ == "__main__":
    import time
    from .metrics import update_system_metrics, record_cycle

    print("Starting metrics server on port 9090...")
    print("Try: curl http://localhost:9090/metrics")

    start_metrics_server(9090)

    # Simulate metrics updates
    cycle = 0
    while True:
        cycle += 1
        update_system_metrics()
        record_cycle(
            duration_seconds=15.0 + (cycle % 10),
            items=100 + cycle,
            deduped=20,
            alerts=cycle % 3,
        )
        print(f"Cycle {cycle} - Metrics updated")
        time.sleep(10)
```

---

## Integration Points

### 1. runner.py - Main Loop Integration

**File:** `src/catalyst_bot/runner.py`

#### Line 3835-3848: Start Metrics Server (After Health Server)

```python
# EXISTING CODE (Line 3835-3848):
# Start health check server if enabled
if os.getenv("FEATURE_HEALTH_ENDPOINT", "1").strip().lower() in (
    "1", "true", "yes", "on",
):
    try:
        health_port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
        start_health_server(port=health_port)
        log.info("health_endpoint_enabled port=%d", health_port)
        update_health_status(status="starting")
    except Exception as e:
        log.warning("health_endpoint_failed err=%s", str(e))

# ADD AFTER LINE 3848:
# Start Prometheus metrics server if enabled
if os.getenv("FEATURE_PROMETHEUS_METRICS", "1").strip().lower() in (
    "1", "true", "yes", "on",
):
    try:
        from .monitoring import start_metrics_server
        metrics_port = int(os.getenv("METRICS_PORT", "9090"))
        if start_metrics_server(port=metrics_port):
            log.info("prometheus_metrics_enabled port=%d", metrics_port)
    except Exception as e:
        log.warning("prometheus_metrics_failed err=%s", str(e))
```

#### Line 4097-4100: Record Cycle Metrics

```python
# EXISTING CODE (Line 4097-4100):
t0 = time.time()
_cycle(log, settings, market_info=current_market_info)
cycle_time = time.time() - t0
log.info("CYCLE_DONE took=%.2fs", cycle_time)

# ADD AFTER LINE 4100:
# Record Prometheus cycle metrics
try:
    from .monitoring import record_cycle, update_system_metrics
    record_cycle(
        duration_seconds=cycle_time,
        items=LAST_CYCLE_STATS.get('items', 0),
        deduped=LAST_CYCLE_STATS.get('deduped', 0),
        alerts=LAST_CYCLE_STATS.get('alerts', 0),
        source_breakdown=FEED_SOURCE_STATS.copy(),
    )
    # Update system metrics every cycle
    update_system_metrics()
except Exception:
    pass  # Never crash on metrics
```

#### Line 4102-4111: Update Health and Portfolio Metrics

```python
# EXISTING CODE (Line 4102-4111):
# Update health status after successful cycle
try:
    update_health_status(
        status="healthy",
        last_cycle_time=datetime.now(timezone.utc),
        total_cycles=TOTAL_STATS.get("items", 0),
        total_alerts=TOTAL_STATS.get("alerts", 0),
    )
except Exception:
    pass

# ADD AFTER LINE 4111:
# Update Prometheus portfolio metrics if trading engine active
if trading_engine and getattr(trading_engine, "_initialized", False):
    try:
        from .monitoring import update_portfolio_metrics, update_position_metrics
        metrics = run_async(trading_engine.get_portfolio_metrics(), timeout=5.0)
        if metrics:
            update_portfolio_metrics({
                'portfolio_value': metrics.get('account_value', 0),
                'cash': metrics.get('cash', 0),
                'buying_power': metrics.get('buying_power', 0),
                'daily_pnl': metrics.get('total_unrealized_pnl', 0),
                'cumulative_pnl': 0,  # TODO: Track cumulative
            })
    except Exception:
        pass
```

---

### 2. trading_engine.py - Trading Metrics Integration

**File:** `src/catalyst_bot/trading/trading_engine.py`

#### Line 17-25: Add Import

```python
# EXISTING IMPORTS (Line 17-25):
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ADD AFTER LINE 25:
# Prometheus metrics integration
try:
    from ..monitoring import (
        record_order,
        record_trade,
        record_error,
        measure_signal_processing,
        measure_order_execution,
        update_portfolio_metrics,
        update_position_metrics,
        update_circuit_breaker,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
```

#### Line 290-324: Wrap process_scored_item with Metrics

```python
# MODIFY METHOD: process_scored_item() - Line 271-333
async def process_scored_item(
    self,
    scored_item: ScoredItem,
    ticker: str,
    current_price: Decimal,
) -> Optional[str]:
    """Main entry point from runner.py."""
    try:
        # 1. Check if trading enabled
        if not self._check_trading_enabled():
            return None

        # ADD: Wrap signal processing with metrics
        if METRICS_AVAILABLE:
            from ..monitoring import measure_signal_processing
            with measure_signal_processing():
                return await self._process_scored_item_internal(
                    scored_item, ticker, current_price
                )
        else:
            return await self._process_scored_item_internal(
                scored_item, ticker, current_price
            )

    except Exception as e:
        # ADD: Record error metric
        if METRICS_AVAILABLE:
            record_error('execution_error', 'trading_engine')
        self.logger.error(
            f"execution_failed ticker={ticker} err={str(e)}",
            exc_info=True
        )
        return None
```

#### Line 560-571: Record Order Metrics in _execute_signal

```python
# MODIFY: _execute_signal() - Around Line 560-571
# ADD after line 566 (after execute_signal call):

if METRICS_AVAILABLE:
    with measure_order_execution():
        result: ExecutionResult = await self.order_executor.execute_signal(
            signal=signal,
            use_bracket_order=True,
            extended_hours=use_extended_hours,
        )
else:
    result: ExecutionResult = await self.order_executor.execute_signal(
        signal=signal,
        use_bracket_order=True,
        extended_hours=use_extended_hours,
    )

# ADD after Line 571:
if not result.success:
    if METRICS_AVAILABLE:
        record_order(signal.action, 'rejected')
    self.logger.warning(
        f"Order execution failed for {signal.ticker}: {result.error_message}"
    )
    return None
else:
    if METRICS_AVAILABLE:
        record_order(signal.action, 'filled')
```

#### Line 506-514: Update Circuit Breaker Metrics

```python
# MODIFY: _update_circuit_breaker() - Line 506-514
# After triggering circuit breaker:

if daily_pnl_pct < -self.config.max_daily_loss_pct:
    if not self.circuit_breaker_active:
        self.circuit_breaker_active = True
        self.circuit_breaker_triggered_at = datetime.now()

        # ADD: Update circuit breaker metric
        if METRICS_AVAILABLE:
            update_circuit_breaker(True, 'daily_loss')

        self.logger.error(
            f"CIRCUIT BREAKER TRIGGERED: Daily loss {daily_pnl_pct:.2f}% "
            f"exceeds limit {self.config.max_daily_loss_pct}%"
        )
```

#### Line 372-384: Update Position Metrics in update_positions

```python
# MODIFY: update_positions() - Around Line 372-384
# After calculating metrics:

# 7. Return metrics
account = await self.broker.get_account()
metrics = self.position_manager.calculate_portfolio_metrics(account.equity)

# ADD: Update Prometheus position metrics
if METRICS_AVAILABLE:
    positions = self.position_manager.get_all_positions()
    update_position_metrics([
        {
            'ticker': pos.ticker,
            'side': pos.side.value,
            'market_value': float(pos.market_value),
            'unrealized_pnl': float(pos.unrealized_pnl),
        }
        for pos in positions
    ])
    update_portfolio_metrics({
        'portfolio_value': float(account.equity),
        'cash': float(account.cash),
        'buying_power': float(account.buying_power),
        'daily_pnl': float(metrics.total_unrealized_pnl),
        'cumulative_pnl': 0,  # TODO: Track cumulative P&L
    })
```

---

### 3. alerts.py - Alert Metrics Integration

**File:** `src/catalyst_bot/alerts.py`

```python
# ADD at top of file (after imports):
try:
    from .monitoring import record_alert
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# MODIFY: send_alert_safe() - After successful Discord post
# Find the success path and add:

if METRICS_AVAILABLE:
    # Determine category from alert content
    category = 'general'
    if 'SEC' in str(alert_data.get('title', '')):
        category = 'sec_filing'
    elif 'breakout' in str(alert_data.get('title', '').lower()):
        category = 'breakout'
    elif 'earnings' in str(alert_data.get('title', '').lower()):
        category = 'earnings'
    record_alert(category)
```

---

### 4. llm_usage_monitor.py - LLM Metrics Bridge

**File:** `src/catalyst_bot/llm_usage_monitor.py`

```python
# MODIFY: log_usage() method - Around Line 199-278
# ADD at end of method, after logging to JSONL:

# Bridge to Prometheus metrics
try:
    from .monitoring import record_llm_usage
    record_llm_usage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        latency_seconds=latency_seconds,
    )
except ImportError:
    pass  # Metrics module not available
```

---

## Coding Tickets

### Phase 1: Core Infrastructure (Priority: CRITICAL)

#### Ticket 1.1: Create Monitoring Package
```
Title: Create monitoring package with Prometheus metrics definitions
Priority: Critical
Estimate: 1-2 hours

Tasks:
1. Create directory: src/catalyst_bot/monitoring/
2. Create __init__.py with exports
3. Create metrics.py with all metric definitions
4. Create metrics_server.py with HTTP server

Files to Create:
- src/catalyst_bot/monitoring/__init__.py
- src/catalyst_bot/monitoring/metrics.py
- src/catalyst_bot/monitoring/metrics_server.py

Acceptance Criteria:
- [ ] All metrics from monitoring.md (lines 89-240) defined
- [ ] Helper functions implemented
- [ ] Context managers working
- [ ] Server starts on port 9090
- [ ] curl http://localhost:9090/metrics returns valid Prometheus format
```

#### Ticket 1.2: Add Dependencies
```
Title: Add prometheus-client and psutil to requirements.txt
Priority: Critical
Estimate: 5 minutes

Tasks:
1. Add to requirements.txt:
   prometheus-client==0.19.0
   psutil>=5.9.0

2. Run: pip install -r requirements.txt
```

### Phase 2: Runner Integration (Priority: HIGH)

#### Ticket 2.1: Start Metrics Server in runner.py
```
Title: Start Prometheus metrics server on bot startup
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/runner.py
Lines to Modify: After 3848

Tasks:
1. Add FEATURE_PROMETHEUS_METRICS env var check
2. Import start_metrics_server
3. Start server after health endpoint
4. Add error handling

Acceptance Criteria:
- [ ] Server starts automatically on boot
- [ ] Respects FEATURE_PROMETHEUS_METRICS=0 to disable
- [ ] METRICS_PORT env var configures port
- [ ] Startup logged to bot.jsonl
```

#### Ticket 2.2: Record Cycle Metrics
```
Title: Record cycle duration and item counts
Priority: High
Estimate: 30 minutes

File: src/catalyst_bot/runner.py
Lines to Modify: After 4100

Tasks:
1. Import record_cycle, update_system_metrics
2. Call record_cycle() after _cycle() completes
3. Call update_system_metrics() every cycle
4. Pass LAST_CYCLE_STATS and FEED_SOURCE_STATS

Acceptance Criteria:
- [ ] catalyst_bot_cycles_total increments each cycle
- [ ] catalyst_bot_cycle_duration_seconds histogram populated
- [ ] catalyst_bot_items_processed_total by source
- [ ] System metrics (CPU, memory) updated
```

### Phase 3: Trading Engine Integration (Priority: HIGH)

#### Ticket 3.1: Import Metrics in trading_engine.py
```
Title: Add metrics imports to trading engine
Priority: High
Estimate: 15 minutes

File: src/catalyst_bot/trading/trading_engine.py
Lines to Modify: After 25

Tasks:
1. Add try/except import block for metrics
2. Set METRICS_AVAILABLE flag
3. Import all needed functions

Acceptance Criteria:
- [ ] Graceful fallback if metrics module unavailable
- [ ] No import errors on startup
```

#### Ticket 3.2: Instrument Order Execution
```
Title: Add order and trade metrics to trading engine
Priority: High
Estimate: 1 hour

File: src/catalyst_bot/trading/trading_engine.py
Lines to Modify: 560-606, 631-636

Tasks:
1. Wrap _execute_signal with measure_order_execution
2. Record order status (filled/rejected)
3. Record trade results (win/loss) on close
4. Track signal processing time

Acceptance Criteria:
- [ ] catalyst_bot_orders_total counts all orders
- [ ] catalyst_bot_order_latency_seconds histogram
- [ ] catalyst_bot_trades_total on position close
- [ ] catalyst_bot_signal_processing_seconds histogram
```

#### Ticket 3.3: Instrument Portfolio Metrics
```
Title: Update portfolio and position metrics
Priority: High
Estimate: 45 minutes

File: src/catalyst_bot/trading/trading_engine.py
Lines to Modify: 372-384, 887-916

Tasks:
1. Call update_portfolio_metrics() in update_positions()
2. Call update_position_metrics() with position list
3. Update circuit breaker metrics

Acceptance Criteria:
- [ ] catalyst_bot_portfolio_value gauge updates
- [ ] catalyst_bot_open_positions gauge accurate
- [ ] catalyst_bot_position_pnl per-ticker
- [ ] catalyst_bot_circuit_breaker_active toggles
```

### Phase 4: Alert and API Metrics (Priority: MEDIUM)

#### Ticket 4.1: Alert Metrics in alerts.py
```
Title: Record alert metrics by category
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/alerts.py

Tasks:
1. Import record_alert
2. Categorize alerts (sec_filing, breakout, earnings, etc.)
3. Call record_alert() on successful send

Acceptance Criteria:
- [ ] catalyst_bot_alerts_sent_total increments
- [ ] Category labels populated
```

#### Ticket 4.2: Bridge LLM Usage to Prometheus
```
Title: Export LLM usage to Prometheus metrics
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/llm_usage_monitor.py
Lines to Modify: End of log_usage() method (~278)

Tasks:
1. Import record_llm_usage
2. Call at end of log_usage()

Acceptance Criteria:
- [ ] catalyst_bot_llm_requests_total by provider
- [ ] catalyst_bot_llm_tokens_total by direction
- [ ] catalyst_bot_llm_cost_dollars accumulates
```

### Phase 5: Deployment Configuration (Priority: MEDIUM)

#### Ticket 5.1: Update Docker Compose
```
Title: Add Prometheus and Grafana services to docker-compose.yml
Priority: Medium
Estimate: 1 hour

File: docker-compose.yml

Tasks:
1. Add prometheus service
2. Add grafana service
3. Configure volumes for persistence
4. Expose ports 9091 (Prometheus) and 3000 (Grafana)

See: docs/deployment/docker-setup.md for reference config
```

#### Ticket 5.2: Create Prometheus Config
```
Title: Create Prometheus scrape configuration
Priority: Medium
Estimate: 30 minutes

File: config/prometheus/prometheus.yml

Tasks:
1. Configure scrape_interval (15s)
2. Add catalyst-trading-bot job
3. Configure alert rules
4. Set retention (90 days)

See: docs/deployment/monitoring.md lines 367-408
```

#### Ticket 5.3: Import Grafana Dashboard
```
Title: Configure Grafana dashboard for Catalyst-Bot
Priority: Medium
Estimate: 30 minutes

File: config/grafana/dashboards/trading-bot-overview.json

Tasks:
1. Create dashboard JSON
2. Add portfolio value panel
3. Add daily P&L panel
4. Add positions panel
5. Add latency heatmap

See: docs/deployment/monitoring.md lines 513-625
```

---

## Testing & Verification

### 1. Unit Test: Metrics Module

```python
# tests/test_metrics.py
import pytest
from src.catalyst_bot.monitoring.metrics import (
    record_order,
    record_cycle,
    update_portfolio_metrics,
    orders_total,
    cycles_total,
    portfolio_value,
)

def test_record_order():
    """Test order metrics recording."""
    initial = orders_total.labels(side='buy', status='filled')._value.get()
    record_order('buy', 'filled')
    assert orders_total.labels(side='buy', status='filled')._value.get() == initial + 1

def test_record_cycle():
    """Test cycle metrics recording."""
    initial = cycles_total._value.get()
    record_cycle(duration_seconds=10.0, items=100, deduped=20, alerts=3)
    assert cycles_total._value.get() == initial + 1

def test_update_portfolio_metrics():
    """Test portfolio gauge updates."""
    update_portfolio_metrics({
        'portfolio_value': 100000.0,
        'cash': 50000.0,
        'buying_power': 100000.0,
        'daily_pnl': 1000.0,
        'cumulative_pnl': 5000.0,
    })
    assert portfolio_value._value.get() == 100000.0
```

### 2. Integration Test: Metrics Server

```bash
# Start bot with metrics enabled
FEATURE_PROMETHEUS_METRICS=1 METRICS_PORT=9090 python -m catalyst_bot.runner --once

# Verify metrics endpoint
curl -s http://localhost:9090/metrics | grep catalyst_bot

# Expected output:
# catalyst_bot_portfolio_value 0.0
# catalyst_bot_cycles_total 1.0
# catalyst_bot_cpu_percent 5.2
# ...
```

### 3. Prometheus Scrape Test

```bash
# Start Prometheus
docker run -d -p 9091:9090 -v $(pwd)/config/prometheus:/etc/prometheus prom/prometheus

# Query metrics
curl 'http://localhost:9091/api/v1/query?query=catalyst_bot_cycles_total'
```

---

## Deployment Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_PROMETHEUS_METRICS` | `1` | Enable/disable metrics server |
| `METRICS_PORT` | `9090` | Port for /metrics endpoint |
| `METRICS_UPDATE_INTERVAL` | `15` | System metrics update interval (seconds) |

### Docker Compose Addition

```yaml
# Add to docker-compose.yml
services:
  catalyst-bot:
    # ... existing config ...
    ports:
      - "8080:8080"   # Health endpoint
      - "9090:9090"   # Prometheus metrics
    environment:
      - FEATURE_PROMETHEUS_METRICS=1
      - METRICS_PORT=9090

  prometheus:
    image: prom/prometheus:v2.48.0
    ports:
      - "9091:9090"
    volumes:
      - ./config/prometheus:/etc/prometheus
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=90d'

  grafana:
    image: grafana/grafana:10.2.2
    ports:
      - "3000:3000"
    volumes:
      - ./config/grafana/provisioning:/etc/grafana/provisioning
      - grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}

volumes:
  prometheus-data:
  grafana-data:
```

---

## Summary

This implementation guide provides a complete roadmap for adding Prometheus metrics to the Catalyst-Bot. The key components are:

1. **Core Metrics Module** (`monitoring/metrics.py`) - All metric definitions
2. **Metrics Server** (`monitoring/metrics_server.py`) - HTTP endpoint on port 9090
3. **Integration Points** - Specific line numbers in runner.py, trading_engine.py
4. **Coding Tickets** - Phased implementation with acceptance criteria

The total estimated implementation time is **4-6 hours** for a complete working system.

---

**End of Implementation Guide**
