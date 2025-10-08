"""
Test Admin Report Generator
============================

Manually generates and posts an admin report to test the interactive
admin controls system.

Usage:
    python test_admin_report.py               # Generate report for yesterday
    python test_admin_report.py 2025-10-01    # Generate report for specific date
    python test_admin_report.py --no-post     # Generate but don't post to Discord
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load environment variables from env.env
from dotenv import load_dotenv  # noqa: E402

env_path = Path(__file__).parent / "env.env"
load_dotenv(env_path)

from catalyst_bot.admin_controls import (  # noqa: E402
    generate_admin_report,
    save_admin_report,
)
from catalyst_bot.admin_reporter import post_admin_report  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Test admin report generator")
    parser.add_argument(
        "date",
        nargs="?",
        help="Date to generate report for (YYYY-MM-DD). Defaults to yesterday.",
    )
    parser.add_argument(
        "--no-post",
        action="store_true",
        help="Generate report but don't post to Discord",
    )
    args = parser.parse_args()

    # Parse target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"[ERROR] Invalid date format: {args.date}. Use YYYY-MM-DD.")
            return 1
    else:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    print(f"[*] Generating admin report for {target_date}...")

    try:
        # Generate report
        report = generate_admin_report(target_date)

        # Save to disk
        report_path = save_admin_report(report)
        print(f"[OK] Report saved to: {report_path}")

        # Print summary
        print("\n" + "=" * 60)
        print(f"ADMIN REPORT SUMMARY - {target_date}")
        print("=" * 60)
        print(f"Total Alerts: {report.total_alerts}")
        print(f"Trades Analyzed: {report.backtest_summary.n}")
        print(f"Win Rate: {report.backtest_summary.hit_rate:.1%}")
        print(f"Avg Return: {report.backtest_summary.avg_return:+.2%}")
        print(f"Simulated P&L: ${report.total_revenue:+,.2f}")
        print(f"Sharpe Ratio: {report.backtest_summary.sharpe:.2f}")
        print(f"Max Drawdown: {report.backtest_summary.max_drawdown:.2%}")
        print()

        if report.keyword_performance:
            print("Top Keyword Categories:")
            for kp in report.keyword_performance[:5]:
                print(
                    f"  {kp.category}: {kp.hit_rate:.0%} win rate ({kp.hits}W/{kp.misses}L)"
                )
            print()

        if report.parameter_recommendations:
            print(f"Parameter Recommendations: {len(report.parameter_recommendations)}")
            for rec in report.parameter_recommendations[:5]:
                print(f"  {rec.impact.upper()}: {rec.name}")
                print(f"    {rec.current_value} → {rec.proposed_value}")
                print(f"    Reason: {rec.reason}")
            print()

        # Post to Discord if requested
        if not args.no_post:
            print("[*] Posting to Discord...")
            success = post_admin_report(target_date)
            if success:
                print("[OK] Successfully posted admin report to Discord!")
            else:
                print("[ERROR] Failed to post report to Discord. Check logs.")
                return 1
        else:
            print("[INFO] Skipping Discord post (--no-post flag)")

        print("\n[*] Done!")
        return 0

    except Exception as e:
        print(f"[ERROR] Error generating report: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
