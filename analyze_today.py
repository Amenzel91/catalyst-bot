#!/usr/bin/env python3
"""Analyze today's bot logs for statistics and abnormalities."""

import json
from collections import Counter
from datetime import datetime

# Read log file
with open("data/logs/bot.jsonl", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Filter today's logs
today_logs = [json.loads(line) for line in lines if "2025-10-24" in line]

# Statistics
stats = {
    "total_lines": len(today_logs),
    "cycles": 0,
    "alerts": 0,
    "strong_negatives": 0,
    "chart_errors": 0,
    "bot_api_errors": 0,
    "bot_api_success": 0,
    "webhook_errors": 0,
    "webhook_success": 0,
    "errors": 0,
    "warnings": 0,
    "sec_filings": 0,
    "price_gate_rejections": 0,
}

# Collect data
error_types = Counter()
warning_types = Counter()
alert_tickers = []
error_tickers = Counter()

for log in today_logs:
    msg = log.get("msg", "")
    level = log.get("level", "")

    # Cycles
    if "CYCLE_DONE" in msg:
        stats["cycles"] += 1

    # Alerts
    if "alerted=" in msg:
        try:
            count = int(msg.split("alerted=")[1].split()[0])
            stats["alerts"] += count
        except:
            pass

    # Strong negatives
    if "strong_negative_detected" in msg or "min_score_bypassed" in msg:
        stats["strong_negatives"] += 1
        if "ticker=" in msg:
            ticker = msg.split("ticker=")[1].split()[0]
            alert_tickers.append(ticker)

    # Chart errors
    if "CHART_ERROR" in msg:
        stats["chart_errors"] += 1
        if "ticker=" in msg:
            ticker = msg.split("ticker=")[1].split()[0]
            error_tickers[ticker] += 1

    # Bot API
    if "BOT_API_ERROR" in msg:
        stats["bot_api_errors"] += 1
    if "BOT_API_SUCCESS" in msg:
        stats["bot_api_success"] += 1

    # Webhook
    if "WEBHOOK_ERROR" in msg:
        stats["webhook_errors"] += 1
    if "WEBHOOK_SUCCESS" in msg:
        stats["webhook_success"] += 1

    # SEC filings
    if "sec_8k=" in msg or "sec_424b5=" in msg:
        stats["sec_filings"] += 1

    # Price gate
    if "skipped_price_gate=" in msg:
        try:
            count = int(msg.split("skipped_price_gate=")[1].split()[0])
            stats["price_gate_rejections"] += count
        except:
            pass

    # Errors and warnings
    if level == "ERROR":
        stats["errors"] += 1
        error_types[msg.split()[0] if msg else "unknown"] += 1
    if level == "WARNING":
        stats["warnings"] += 1
        warning_types[msg.split()[0] if msg else "unknown"] += 1

# Print report
print("=" * 70)
print(f"CATALYST BOT - TODAY'S LOG ANALYSIS (2025-10-24)")
print("=" * 70)
print()
print(f"OVERVIEW")
print(f"  Total log entries: {stats['total_lines']:,}")
print(f"  Cycles completed: {stats['cycles']}")
print(f"  Alerts sent: {stats['alerts']}")
print()
print(f"SMART NEGATIVE THRESHOLD")
print(f"  Strong negatives detected: {stats['strong_negatives']}")
if alert_tickers:
    print(f"  Tickers: {', '.join(set(alert_tickers))}")
print()
print(f"SEC FILING INTEGRATION")
print(f"  SEC feed fetches: {stats['sec_filings']}")
print(f"  Price gate rejections: {stats['price_gate_rejections']}")
print()
print(f"CHART UPLOADS")
print(f"  Chart errors: {stats['chart_errors']}")
print(f"  Bot API errors: {stats['bot_api_errors']}")
print(f"  Bot API success: {stats['bot_api_success']}")
print(f"  Webhook errors: {stats['webhook_errors']}")
print(f"  Webhook success: {stats['webhook_success']}")
if error_tickers:
    print(f"  Tickers with chart errors: {', '.join(error_tickers.keys())}")
print()
print(f"ISSUES")
print(f"  Total errors: {stats['errors']}")
print(f"  Total warnings: {stats['warnings']}")
if error_types:
    print(f"  Top error types:")
    for err, count in error_types.most_common(5):
        print(f"    - {err}: {count}")
if warning_types:
    print(f"  Top warning types:")
    for warn, count in warning_types.most_common(5):
        print(f"    - {warn}: {count}")
print()
print("=" * 70)
