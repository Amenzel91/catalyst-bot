# Paper Trading Bot - Monitoring and Alerting Guide

**Version:** 1.0
**Last Updated:** November 2025
**Stack:** Prometheus + Grafana + AlertManager

---

## Table of Contents

1. [Overview](#overview)
2. [Prometheus Metrics Export](#prometheus-metrics-export)
3. [Grafana Dashboard Setup](#grafana-dashboard-setup)
4. [Key Metrics to Monitor](#key-metrics-to-monitor)
5. [Alert Thresholds](#alert-thresholds)
6. [Notification Channels](#notification-channels)
7. [Logging Strategy](#logging-strategy)
8. [Log Aggregation](#log-aggregation)
9. [Performance Monitoring](#performance-monitoring)
10. [Troubleshooting Monitoring Issues](#troubleshooting-monitoring-issues)

---

## Overview

Comprehensive monitoring is critical for paper trading bot operations. This guide covers metrics collection, visualization, and alerting for all critical system components.

**Monitoring Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│  Trading Bot Application                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Metrics Instrumentation                           │    │
│  │  • Portfolio value (gauge)                         │    │
│  │  • Trade count (counter)                           │    │
│  │  • Order latency (histogram)                       │    │
│  │  • Error count (counter)                           │    │
│  └───────────────────┬────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Prometheus Client (port 9090)                     │    │
│  │  • /metrics endpoint                               │    │
│  │  • Exposition format                               │    │
│  └───────────────────┬────────────────────────────────┘    │
└────────────────────────┼────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Prometheus Server                                          │
│  • Scrapes metrics every 15s                                │
│  • Stores time-series data (90d retention)                  │
│  • Evaluates alert rules                                    │
└───────────────────┬─────────────────────────────────────────┘
                    │
         ┌──────────┼──────────┐
         │          │           │
         ▼          ▼           ▼
┌─────────────┐ ┌─────────┐ ┌────────────────┐
│  Grafana    │ │ Alert   │ │ Discord/Email  │
│  Dashboards │ │ Manager │ │ Notifications  │
└─────────────┘ └─────────┘ └────────────────┘
```

---

## Prometheus Metrics Export

### 1. Install Prometheus Client

```bash
pip install prometheus-client==0.19.0
```

### 2. Metrics Instrumentation

Create `/app/src/catalyst_bot/monitoring/metrics.py`:

```python
"""
Prometheus metrics for paper trading bot
"""
from prometheus_client import Counter, Gauge, Histogram, Summary
import time

# =============================================================================
# Portfolio Metrics
# =============================================================================
portfolio_value = Gauge(
    'catalyst_bot_portfolio_value',
    'Current total portfolio value in USD'
)

portfolio_cash = Gauge(
    'catalyst_bot_portfolio_cash',
    'Available cash balance in USD'
)

portfolio_buying_power = Gauge(
    'catalyst_bot_portfolio_buying_power',
    'Total buying power (including leverage)'
)

# =============================================================================
# Position Metrics
# =============================================================================
open_positions_count = Gauge(
    'catalyst_bot_open_positions',
    'Number of currently open positions'
)

position_value = Gauge(
    'catalyst_bot_position_value',
    'Value of individual position',
    ['ticker', 'side']
)

position_pnl = Gauge(
    'catalyst_bot_position_pnl',
    'Unrealized P&L for individual position',
    ['ticker', 'side']
)

# =============================================================================
# Performance Metrics
# =============================================================================
daily_pnl = Gauge(
    'catalyst_bot_daily_pnl',
    'Daily profit/loss in USD'
)

cumulative_pnl = Gauge(
    'catalyst_bot_cumulative_pnl',
    'Cumulative profit/loss since inception'
)

sharpe_ratio = Gauge(
    'catalyst_bot_sharpe_ratio',
    'Rolling 30-day Sharpe ratio'
)

max_drawdown = Gauge(
    'catalyst_bot_max_drawdown',
    'Maximum drawdown from peak (negative value)'
)

win_rate = Gauge(
    'catalyst_bot_win_rate',
    'Percentage of profitable trades (0-100)'
)

# =============================================================================
# Trading Activity Metrics
# =============================================================================
orders_total = Counter(
    'catalyst_bot_orders_total',
    'Total orders placed',
    ['side', 'status']  # side: buy/sell, status: filled/rejected/cancelled
)

trades_total = Counter(
    'catalyst_bot_trades_total',
    'Total trades executed',
    ['ticker', 'side', 'result']  # result: win/loss
)

order_success_rate = Gauge(
    'catalyst_bot_order_success_rate',
    'Percentage of successfully filled orders (0-100)'
)

# =============================================================================
# Latency Metrics
# =============================================================================
order_latency = Histogram(
    'catalyst_bot_order_latency_seconds',
    'Order execution latency',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

api_latency = Histogram(
    'catalyst_bot_api_latency_seconds',
    'External API call latency',
    ['api_name'],  # api_name: alpaca/tiingo/gemini
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

signal_processing_time = Histogram(
    'catalyst_bot_signal_processing_seconds',
    'Time to process trading signal',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# =============================================================================
# Error Metrics
# =============================================================================
errors_total = Counter(
    'catalyst_bot_errors_total',
    'Total errors by type',
    ['error_type', 'component']
)

api_errors_total = Counter(
    'catalyst_bot_api_errors_total',
    'API errors by provider',
    ['api_name', 'status_code']
)

# =============================================================================
# RL Agent Metrics
# =============================================================================
rl_confidence = Gauge(
    'catalyst_bot_rl_confidence',
    'RL agent confidence score (0-1)',
    ['model_name']
)

rl_predictions_total = Counter(
    'catalyst_bot_rl_predictions_total',
    'Total RL predictions made',
    ['model_name', 'action']  # action: buy/sell/hold
)

# =============================================================================
# System Metrics
# =============================================================================
system_cpu_percent = Gauge(
    'catalyst_bot_cpu_percent',
    'CPU usage percentage'
)

system_memory_mb = Gauge(
    'catalyst_bot_memory_mb',
    'Memory usage in MB'
)

system_disk_usage_percent = Gauge(
    'catalyst_bot_disk_usage_percent',
    'Disk usage percentage'
)

# =============================================================================
# Helper Functions
# =============================================================================
def update_portfolio_metrics(portfolio_data):
    """Update portfolio-related metrics"""
    portfolio_value.set(portfolio_data['portfolio_value'])
    portfolio_cash.set(portfolio_data['cash'])
    portfolio_buying_power.set(portfolio_data['buying_power'])
    daily_pnl.set(portfolio_data['daily_pnl'])
    cumulative_pnl.set(portfolio_data['cumulative_pnl'])

def update_position_metrics(positions):
    """Update position-related metrics"""
    open_positions_count.set(len(positions))

    for pos in positions:
        position_value.labels(
            ticker=pos['ticker'],
            side=pos['side']
        ).set(pos['market_value'])

        position_pnl.labels(
            ticker=pos['ticker'],
            side=pos['side']
        ).set(pos['unrealized_pnl'])

def record_order(side, status):
    """Record order execution"""
    orders_total.labels(side=side, status=status).inc()

def record_trade(ticker, side, result):
    """Record completed trade"""
    trades_total.labels(ticker=ticker, side=side, result=result).inc()

def measure_api_call(api_name):
    """Context manager to measure API latency"""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        api_latency.labels(api_name=api_name).observe(duration)

# =============================================================================
# System Resource Collection
# =============================================================================
import psutil
import os

def update_system_metrics():
    """Update system resource metrics"""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)
    system_cpu_percent.set(cpu_percent)

    # Memory
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    system_memory_mb.set(memory_mb)

    # Disk
    disk = psutil.disk_usage('/')
    system_disk_usage_percent.set(disk.percent)
```

### 3. Metrics HTTP Server

```python
# In catalyst_bot/monitoring/metrics_server.py
from prometheus_client import start_http_server
import time
import logging

logger = logging.getLogger(__name__)

def start_metrics_server(port=9090):
    """Start Prometheus metrics HTTP server"""
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
        logger.info(f"Metrics available at http://localhost:{port}/metrics")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        raise

# In main application
if __name__ == '__main__':
    from catalyst_bot.monitoring.metrics_server import start_metrics_server
    from catalyst_bot.monitoring.metrics import update_system_metrics

    # Start metrics server
    start_metrics_server(port=9090)

    # Update system metrics every 15 seconds
    while True:
        update_system_metrics()
        time.sleep(15)
```

### 4. Verify Metrics Endpoint

```bash
# Test metrics endpoint
curl http://localhost:9090/metrics

# Expected output (sample):
# HELP catalyst_bot_portfolio_value Current total portfolio value in USD
# TYPE catalyst_bot_portfolio_value gauge
catalyst_bot_portfolio_value 105432.50

# HELP catalyst_bot_open_positions Number of currently open positions
# TYPE catalyst_bot_open_positions gauge
catalyst_bot_open_positions 3

# HELP catalyst_bot_orders_total Total orders placed
# TYPE catalyst_bot_orders_total counter
catalyst_bot_orders_total{side="buy",status="filled"} 45
catalyst_bot_orders_total{side="sell",status="filled"} 42
catalyst_bot_orders_total{side="buy",status="rejected"} 3
```

---

## Grafana Dashboard Setup

### 1. Prometheus Configuration

Create `config/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'catalyst-bot'
    environment: 'production'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load alert rules
rule_files:
  - '/etc/prometheus/alerts/*.yml'

# Scrape configurations
scrape_configs:
  # Trading bot metrics
  - job_name: 'catalyst-trading-bot'
    static_configs:
      - targets: ['trading-bot:9090']
        labels:
          app: 'trading-bot'

  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Node exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
```

### 2. Alert Rules

Create `config/prometheus/alerts/trading-bot.yml`:

```yaml
groups:
  - name: trading_bot_alerts
    interval: 30s
    rules:
      # Daily loss exceeded
      - alert: DailyLossLimitExceeded
        expr: catalyst_bot_daily_pnl < -3000
        for: 1m
        labels:
          severity: critical
          component: risk_management
        annotations:
          summary: "Daily loss limit exceeded"
          description: "Daily P&L is {{ $value | humanize }}. Limit is -$3000."

      # Max drawdown exceeded
      - alert: MaxDrawdownExceeded
        expr: catalyst_bot_max_drawdown < -0.10
        for: 2m
        labels:
          severity: critical
          component: risk_management
        annotations:
          summary: "Maximum drawdown exceeded"
          description: "Drawdown is {{ $value | humanizePercentage }}. Limit is -10%."

      # High error rate
      - alert: HighErrorRate
        expr: rate(catalyst_bot_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanize }} errors/sec."

      # Order success rate low
      - alert: LowOrderSuccessRate
        expr: catalyst_bot_order_success_rate < 80
        for: 10m
        labels:
          severity: warning
          component: execution
        annotations:
          summary: "Order success rate below threshold"
          description: "Success rate is {{ $value }}%. Expected >80%."

      # API latency high
      - alert: HighAPILatency
        expr: histogram_quantile(0.95, rate(catalyst_bot_api_latency_seconds_bucket[5m])) > 2.0
        for: 10m
        labels:
          severity: warning
          component: api
        annotations:
          summary: "High API latency detected"
          description: "95th percentile latency is {{ $value | humanize }}s for {{ $labels.api_name }}."

      # Memory usage high
      - alert: HighMemoryUsage
        expr: catalyst_bot_memory_mb > 4096
        for: 5m
        labels:
          severity: warning
          component: system
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanize }}MB. Limit is 4GB."

      # Bot offline
      - alert: TradingBotOffline
        expr: up{job="catalyst-trading-bot"} == 0
        for: 2m
        labels:
          severity: critical
          component: system
        annotations:
          summary: "Trading bot is offline"
          description: "Cannot scrape metrics from trading bot."
```

### 3. Grafana Provisioning

Create `config/grafana/provisioning/datasources/prometheus.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

### 4. Grafana Dashboard JSON

Create `config/grafana/dashboards/trading-bot-overview.json`:

```json
{
  "dashboard": {
    "title": "Catalyst Trading Bot - Overview",
    "tags": ["trading", "paper-trading"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Portfolio Value",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "catalyst_bot_portfolio_value",
            "legendFormat": "Portfolio Value"
          }
        ],
        "yaxes": [
          {"format": "currencyUSD", "label": "Value"}
        ]
      },
      {
        "title": "Daily P&L",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "catalyst_bot_daily_pnl",
            "legendFormat": "Daily P&L"
          }
        ],
        "yaxes": [
          {"format": "currencyUSD"}
        ],
        "thresholds": [
          {
            "value": -3000,
            "colorMode": "critical",
            "op": "lt",
            "fill": true,
            "line": true
          }
        ]
      },
      {
        "title": "Open Positions",
        "type": "stat",
        "gridPos": {"h": 4, "w": 4, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "catalyst_bot_open_positions"
          }
        ],
        "options": {
          "graphMode": "none",
          "colorMode": "value",
          "textMode": "value_and_name"
        }
      },
      {
        "title": "Win Rate",
        "type": "gauge",
        "gridPos": {"h": 4, "w": 4, "x": 4, "y": 8},
        "targets": [
          {
            "expr": "catalyst_bot_win_rate"
          }
        ],
        "options": {
          "min": 0,
          "max": 100,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"value": 0, "color": "red"},
              {"value": 50, "color": "yellow"},
              {"value": 60, "color": "green"}
            ]
          }
        }
      },
      {
        "title": "Sharpe Ratio",
        "type": "gauge",
        "gridPos": {"h": 4, "w": 4, "x": 8, "y": 8},
        "targets": [
          {
            "expr": "catalyst_bot_sharpe_ratio"
          }
        ],
        "options": {
          "min": 0,
          "max": 3,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"value": 0, "color": "red"},
              {"value": 1.0, "color": "yellow"},
              {"value": 1.5, "color": "green"}
            ]
          }
        }
      }
    ],
    "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"}
  }
}
```

See full dashboard configuration in Appendix A below.

---

## Key Metrics to Monitor

### Portfolio Metrics

| Metric | Description | Alert Threshold | Action |
|--------|-------------|-----------------|--------|
| **Portfolio Value** | Total account value | < Initial - 10% | Review strategy |
| **Daily P&L** | Today's profit/loss | < -$3,000 | Kill switch |
| **Cumulative P&L** | All-time P&L | Negative | Retrain model |
| **Sharpe Ratio** | Risk-adjusted returns | < 1.0 | Tune parameters |
| **Max Drawdown** | Peak to trough decline | < -10% | Kill switch |
| **Win Rate** | % profitable trades | < 40% | Review signals |

### Position Metrics

| Metric | Description | Alert Threshold | Action |
|--------|-------------|-----------------|--------|
| **Open Positions** | Current open trades | > 5 | Check limits |
| **Position Concentration** | Largest position % | > 20% | Rebalance |
| **Avg Position Duration** | Hours per trade | > 168h (7d) | Review exits |
| **Unrealized P&L** | Open position P&L | < -15% | Check stops |

### Execution Metrics

| Metric | Description | Alert Threshold | Action |
|--------|-------------|-----------------|--------|
| **Order Success Rate** | % orders filled | < 80% | Check API |
| **Order Latency (p95)** | 95th %ile execution time | > 2s | Optimize code |
| **Slippage** | Price vs expected | > 0.1% | Use limit orders |
| **Rejected Orders** | Orders rejected by broker | > 5/hour | Check balances |

### API Metrics

| Metric | Description | Alert Threshold | Action |
|--------|-------------|-----------------|--------|
| **Alpaca Latency (p95)** | API response time | > 1s | Check network |
| **API Error Rate** | Failed API calls | > 5% | Implement retry |
| **Rate Limit Hits** | 429 errors | > 0 | Slow down |
| **Tiingo Latency** | Data feed latency | > 5s | Switch provider |

### System Metrics

| Metric | Description | Alert Threshold | Action |
|--------|-------------|-----------------|--------|
| **CPU Usage** | Average CPU % | > 80% | Scale up |
| **Memory Usage** | RAM consumption | > 4GB | Optimize code |
| **Disk Usage** | Storage used | > 80% | Clean logs |
| **Error Rate** | Application errors | > 1/min | Debug logs |

---

## Alert Thresholds

### Critical Alerts (Immediate Action)

```yaml
# Daily loss limit exceeded (-3%)
- alert: DailyLossLimitExceeded
  expr: catalyst_bot_daily_pnl < -3000
  for: 1m
  severity: critical
  action: Trigger kill switch

# Max drawdown exceeded (-10%)
- alert: MaxDrawdownExceeded
  expr: catalyst_bot_max_drawdown < -0.10
  for: 2m
  severity: critical
  action: Trigger kill switch

# Trading bot offline
- alert: TradingBotOffline
  expr: up{job="catalyst-trading-bot"} == 0
  for: 2m
  severity: critical
  action: Restart service
```

### High Priority Alerts (Review Within 1 Hour)

```yaml
# Low order success rate
- alert: LowOrderSuccessRate
  expr: catalyst_bot_order_success_rate < 80
  for: 10m
  severity: high
  action: Check API connectivity

# High error rate
- alert: HighErrorRate
  expr: rate(catalyst_bot_errors_total[5m]) > 0.1
  for: 5m
  severity: high
  action: Check logs

# Position limit exceeded
- alert: TooManyOpenPositions
  expr: catalyst_bot_open_positions > 5
  for: 5m
  severity: high
  action: Review position limits
```

### Medium Priority Alerts (Review Within 4 Hours)

```yaml
# Sharpe ratio degradation
- alert: LowSharpeRatio
  expr: catalyst_bot_sharpe_ratio < 1.0
  for: 1h
  severity: medium
  action: Analyze strategy performance

# High API latency
- alert: HighAPILatency
  expr: histogram_quantile(0.95, rate(catalyst_bot_api_latency_seconds_bucket[5m])) > 2.0
  for: 10m
  severity: medium
  action: Check network/API status
```

---

## Notification Channels

### 1. Discord Webhook Integration

```python
# catalyst_bot/monitoring/notifications.py
import requests
import logging

logger = logging.getLogger(__name__)

def send_discord_alert(webhook_url, alert_data):
    """Send alert to Discord channel"""
    embed = {
        "title": f"🚨 {alert_data['severity'].upper()}: {alert_data['alert']}",
        "description": alert_data['description'],
        "color": get_color_by_severity(alert_data['severity']),
        "fields": [
            {"name": "Metric", "value": alert_data['metric'], "inline": True},
            {"name": "Value", "value": str(alert_data['value']), "inline": True},
            {"name": "Threshold", "value": str(alert_data['threshold']), "inline": True}
        ],
        "timestamp": alert_data['timestamp']
    }

    payload = {"embeds": [embed]}

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Alert sent to Discord: {alert_data['alert']}")
    except Exception as e:
        logger.error(f"Failed to send Discord alert: {e}")

def get_color_by_severity(severity):
    """Map severity to Discord embed color"""
    colors = {
        'critical': 0xFF0000,  # Red
        'high': 0xFF6600,      # Orange
        'medium': 0xFFCC00,    # Yellow
        'low': 0x00CC00        # Green
    }
    return colors.get(severity, 0x808080)  # Default: Gray
```

### 2. Email Notifications

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_alert(smtp_config, alert_data):
    """Send alert via email"""
    msg = MIMEMultipart()
    msg['From'] = smtp_config['from']
    msg['To'] = smtp_config['to']
    msg['Subject'] = f"[{alert_data['severity'].upper()}] {alert_data['alert']}"

    body = f"""
    Alert: {alert_data['alert']}
    Severity: {alert_data['severity']}
    Metric: {alert_data['metric']}
    Current Value: {alert_data['value']}
    Threshold: {alert_data['threshold']}
    Description: {alert_data['description']}
    Timestamp: {alert_data['timestamp']}
    """

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_config['server'], smtp_config['port']) as server:
            server.starttls()
            server.login(smtp_config['username'], smtp_config['password'])
            server.send_message(msg)
        logger.info(f"Email alert sent: {alert_data['alert']}")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
```

### 3. Slack Integration (Optional)

```python
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def send_slack_alert(slack_token, channel, alert_data):
    """Send alert to Slack channel"""
    client = WebClient(token=slack_token)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":rotating_light: {alert_data['alert']}"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity:*\n{alert_data['severity']}"},
                {"type": "mrkdwn", "text": f"*Metric:*\n{alert_data['metric']}"},
                {"type": "mrkdwn", "text": f"*Value:*\n{alert_data['value']}"},
                {"type": "mrkdwn", "text": f"*Threshold:*\n{alert_data['threshold']}"}
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": alert_data['description']
            }
        }
    ]

    try:
        response = client.chat_postMessage(channel=channel, blocks=blocks)
        logger.info(f"Slack alert sent: {alert_data['alert']}")
    except SlackApiError as e:
        logger.error(f"Failed to send Slack alert: {e.response['error']}")
```

### 4. AlertManager Configuration

```yaml
# config/alertmanager/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'discord-critical'

  routes:
    # Critical alerts → Discord + Email
    - match:
        severity: critical
      receiver: 'discord-critical'
      continue: true

    - match:
        severity: critical
      receiver: 'email-admin'

    # High priority → Discord only
    - match:
        severity: high
      receiver: 'discord-high'

    # Medium priority → Daily digest
    - match:
        severity: medium
      receiver: 'email-digest'

receivers:
  - name: 'discord-critical'
    webhook_configs:
      - url: 'http://localhost:5001/alerts/discord/critical'
        send_resolved: true

  - name: 'discord-high'
    webhook_configs:
      - url: 'http://localhost:5001/alerts/discord/high'
        send_resolved: true

  - name: 'email-admin'
    email_configs:
      - to: 'admin@example.com'
        from: 'alerts@catalyst-bot.com'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'alerts@catalyst-bot.com'
        auth_password: '${SMTP_PASSWORD}'
        headers:
          Subject: '[CRITICAL] {{ .GroupLabels.alertname }}'

  - name: 'email-digest'
    email_configs:
      - to: 'team@example.com'
        from: 'alerts@catalyst-bot.com'
        smarthost: 'smtp.gmail.com:587'
        send_resolved: false

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname']
```

---

## Logging Strategy

### 1. Structured Logging Configuration

```python
# catalyst_bot/logging_config.py
import logging
import json
import sys
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for easy parsing"""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add custom fields
        if hasattr(record, 'ticker'):
            log_data['ticker'] = record.ticker
        if hasattr(record, 'order_id'):
            log_data['order_id'] = record.order_id
        if hasattr(record, 'trade_id'):
            log_data['trade_id'] = record.trade_id

        return json.dumps(log_data)

def setup_logging(log_level='INFO', log_dir='/data/logs'):
    """Configure application logging"""
    logger = logging.getLogger('catalyst_bot')
    logger.setLevel(getattr(logging, log_level))

    # Console handler (human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)

    # JSON file handler (structured logs)
    json_handler = logging.FileHandler(f'{log_dir}/trading-bot.jsonl')
    json_handler.setLevel(logging.DEBUG)
    json_handler.setFormatter(JSONFormatter())

    # Error file handler (errors only)
    error_handler = logging.FileHandler(f'{log_dir}/trading-bot.error.log')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(json_handler)
    logger.addHandler(error_handler)

    return logger
```

### 2. Logging Best Practices

```python
# Example usage in trading bot
logger = setup_logging()

# Log order execution
logger.info(
    "Order placed",
    extra={
        'ticker': 'AAPL',
        'order_id': 'abc123',
        'side': 'buy',
        'quantity': 100,
        'price': 150.25
    }
)

# Log errors with context
try:
    execute_order(order)
except Exception as e:
    logger.error(
        f"Order execution failed: {e}",
        exc_info=True,
        extra={'order_id': order.id, 'ticker': order.ticker}
    )

# Log performance metrics
logger.info(
    "Daily performance",
    extra={
        'daily_pnl': 1250.50,
        'win_rate': 0.62,
        'sharpe_ratio': 2.1,
        'trades_today': 12
    }
)
```

### 3. Log Levels

| Level | Usage | Examples |
|-------|-------|----------|
| **DEBUG** | Detailed diagnostic info | Variable values, function calls |
| **INFO** | Normal operations | Order placed, position closed, metrics |
| **WARNING** | Unexpected but handled | High latency, API throttling |
| **ERROR** | Errors requiring attention | Order rejection, API failures |
| **CRITICAL** | Severe errors | Kill switch activated, database corruption |

---

## Log Aggregation

### Option 1: ELK Stack (Elasticsearch + Logstash + Kibana)

**Docker Compose Addition:**

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - elasticsearch-data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"

  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.0
    volumes:
      - ./config/logstash/logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    depends_on:
      - elasticsearch

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    ports:
      - "5601:5601"
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
    depends_on:
      - elasticsearch

volumes:
  elasticsearch-data:
    driver: local
```

**Logstash Configuration:**

```
# config/logstash/logstash.conf
input {
  file {
    path => "/data/logs/trading-bot.jsonl"
    codec => "json"
    type => "trading-bot"
  }
}

filter {
  # Parse timestamp
  date {
    match => ["timestamp", "ISO8601"]
    target => "@timestamp"
  }

  # Add geolocation for API calls
  if [api_name] {
    geoip {
      source => "remote_ip"
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "trading-bot-%{+YYYY.MM.dd}"
  }
}
```

### Option 2: Loki + Promtail (Lightweight Alternative)

```yaml
services:
  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    volumes:
      - ./config/loki/loki-config.yml:/etc/loki/loki-config.yml
      - loki-data:/loki
    command: -config.file=/etc/loki/loki-config.yml

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - ./config/promtail/promtail-config.yml:/etc/promtail/promtail-config.yml
      - ./data/logs:/data/logs:ro
    command: -config.file=/etc/promtail/promtail-config.yml
```

---

## Performance Monitoring

### 1. Application Profiling

```python
# catalyst_bot/monitoring/profiler.py
import cProfile
import pstats
import io
from functools import wraps

def profile(func):
    """Decorator to profile function performance"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()

        result = func(*args, **kwargs)

        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats(20)  # Top 20 functions

        logger.debug(f"Profile for {func.__name__}:\n{s.getvalue()}")
        return result

    return wrapper

# Usage
@profile
def process_trading_signals(signals):
    # ... processing logic ...
    pass
```

### 2. Database Query Performance

```python
# Monitor slow queries
import time
import sqlite3

class ProfilingConnection(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        start = time.time()
        result = super().execute(sql, *args, **kwargs)
        duration = time.time() - start

        if duration > 0.5:  # Log queries taking >500ms
            logger.warning(
                f"Slow query detected: {duration:.2f}s",
                extra={'query': sql[:100], 'duration': duration}
            )

        return result

# Use profiling connection
conn = sqlite3.connect('positions.db', factory=ProfilingConnection)
```

### 3. Memory Profiling

```python
# catalyst_bot/monitoring/memory_profiler.py
import tracemalloc
import logging

logger = logging.getLogger(__name__)

def start_memory_profiling():
    """Start tracking memory allocations"""
    tracemalloc.start()

def get_memory_snapshot():
    """Get current memory usage snapshot"""
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')

    logger.info("Top 10 memory allocations:")
    for stat in top_stats[:10]:
        logger.info(f"{stat.filename}:{stat.lineno}: {stat.size / 1024:.1f} KB")

    return snapshot
```

---

## Troubleshooting Monitoring Issues

### Issue 1: Prometheus Not Scraping Metrics

**Symptoms:**
- No data in Grafana dashboards
- `up{job="catalyst-trading-bot"} = 0`

**Diagnosis:**
```bash
# Check Prometheus targets
curl http://localhost:9091/api/v1/targets | jq '.data.activeTargets'

# Test metrics endpoint directly
curl http://trading-bot:9090/metrics
```

**Solution:**
```bash
# Verify network connectivity
docker exec prometheus ping -c 3 trading-bot

# Check Prometheus config
docker exec prometheus cat /etc/prometheus/prometheus.yml

# Restart Prometheus
docker compose restart prometheus
```

---

### Issue 2: Grafana Dashboard Shows No Data

**Symptoms:**
- Dashboard panels empty
- "No data" message

**Diagnosis:**
```bash
# Check Prometheus datasource in Grafana
# Settings → Data Sources → Prometheus → Test

# Query Prometheus directly
curl 'http://localhost:9091/api/v1/query?query=catalyst_bot_portfolio_value'
```

**Solution:**
```bash
# Verify time range
# Check that dashboard time range includes recent data

# Re-import dashboard
# Copy dashboard JSON and import again

# Check query syntax
# Use Prometheus query builder to test queries
```

---

## Appendix A: Complete Grafana Dashboard JSON

See `/home/user/catalyst-bot/config/grafana/dashboards/trading-bot-overview.json` for full dashboard configuration.

**Key Panels:**
1. Portfolio value (time series graph)
2. Daily P&L (bar chart)
3. Open positions (stat panel)
4. Win rate (gauge)
5. Sharpe ratio (gauge)
6. Position breakdown (pie chart)
7. Recent trades (table)
8. API latency heatmap
9. Error rate (graph)
10. System resource usage (graph)

---

## Next Steps

1. **Set up monitoring**: Deploy Prometheus and Grafana
2. **Configure alerts**: Set thresholds for your risk tolerance
3. **Test notifications**: Send test alerts to Discord/Email
4. **Establish baselines**: Monitor for 1 week to establish normal ranges
5. **Refine thresholds**: Adjust based on observed patterns

---

**End of Monitoring and Alerting Guide**
