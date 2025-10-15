#!/usr/bin/env python3
"""
LLM Usage Report Tool
=====================

View LLM API usage statistics and costs.

Usage:
    python scripts/llm_usage_report.py              # Today's usage
    python scripts/llm_usage_report.py --daily      # Today's usage
    python scripts/llm_usage_report.py --monthly    # This month's usage
    python scripts/llm_usage_report.py --since "2025-01-01"  # Custom range
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_bot.llm_usage_monitor import LLMUsageMonitor


def main():
    """Run LLM usage report."""
    parser = argparse.ArgumentParser(
        description="View LLM API usage statistics and costs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--daily",
        action="store_true",
        help="Show today's usage (default)",
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="Show this month's usage",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Show usage since date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        type=str,
        help="Show usage until date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help="Custom path to usage log file",
    )

    args = parser.parse_args()

    # Initialize monitor
    monitor = LLMUsageMonitor(log_path=args.log_path)

    # Determine time range
    if args.monthly:
        summary = monitor.get_monthly_stats()
        period_desc = "This Month"
    elif args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
            if args.until:
                until = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc)
            else:
                until = datetime.now(timezone.utc)
            summary = monitor.get_stats(since=since, until=until)
            period_desc = f"Custom Range ({args.since} to {args.until or 'now'})"
        except ValueError as e:
            print(f"ERROR: Invalid date format: {e}")
            print("Use YYYY-MM-DD format (e.g., 2025-01-15)")
            return 1
    else:  # Default: daily
        summary = monitor.get_daily_stats()
        period_desc = "Today"

    # Print header
    print("\n" + "=" * 70)
    print(f"LLM USAGE REPORT - {period_desc}")
    print("=" * 70)

    # Print summary
    monitor.print_summary(summary)

    # Print cost projections
    if summary.total_cost > 0:
        print("=" * 70)
        print("COST PROJECTIONS")
        print("=" * 70)

        # Calculate daily average
        since_dt = datetime.fromisoformat(summary.period_start)
        until_dt = datetime.fromisoformat(summary.period_end)
        period_hours = (until_dt - since_dt).total_seconds() / 3600

        if period_hours > 0:
            cost_per_hour = summary.total_cost / period_hours
            daily_projection = cost_per_hour * 24
            monthly_projection = daily_projection * 30

            print(f"Cost per hour:   ${cost_per_hour:.4f}")
            print(f"Daily projection: ${daily_projection:.4f}")
            print(f"Monthly projection: ${monthly_projection:.2f}")

            # Budget warnings
            import os
            daily_budget = float(os.getenv("LLM_COST_ALERT_DAILY", "5.00"))
            monthly_budget = float(os.getenv("LLM_COST_ALERT_MONTHLY", "50.00"))

            if daily_projection > daily_budget:
                print(f"\n[WARNING] Projected daily cost (${daily_projection:.2f}) "
                      f"exceeds budget (${daily_budget:.2f})")
            if monthly_projection > monthly_budget:
                print(f"[WARNING] Projected monthly cost (${monthly_projection:.2f}) "
                      f"exceeds budget (${monthly_budget:.2f})")

        print("\n" + "=" * 70 + "\n")

    # Return success
    return 0


if __name__ == "__main__":
    sys.exit(main())
