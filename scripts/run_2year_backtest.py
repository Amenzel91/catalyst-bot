#!/usr/bin/env python3
"""
Production 2-Year Backtest Script
==================================

Runs a comprehensive 2-year backtest of the Catalyst-Bot penny stock strategy.

Date Range: 2023-01-01 to 2025-01-01
Strategy: Conservative penny stock catalyst trading
Output: Comprehensive markdown report with visualizations

Usage:
    python scripts/run_2year_backtest.py

Requirements:
    - data/events.jsonl with historical alerts
    - yfinance installed (pip install yfinance)
    - Sufficient disk space for price data cache (~500MB)
    - Stable internet connection for price data fetching
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from catalyst_bot.backtesting.engine import BacktestEngine
from catalyst_bot.backtesting.reports import (
    generate_backtest_report,
    export_trades_to_csv,
)
from catalyst_bot.logging_utils import get_logger

log = get_logger("backtest_2year")


def validate_environment():
    """
    Pre-flight checks before running backtest.

    Returns
    -------
    tuple
        (success: bool, messages: list)
    """
    messages = []
    success = True

    # Check events.jsonl exists
    events_file = repo_root / "data" / "events.jsonl"
    if not events_file.exists():
        messages.append("ERROR: data/events.jsonl not found")
        success = False
    else:
        # Count events
        try:
            with open(events_file, 'r', encoding='utf-8') as f:
                count = sum(1 for line in f if line.strip())
            messages.append(f"OK: Found {count} events in data/events.jsonl")

            if count < 10:
                messages.append("WARNING: Very few events in data/events.jsonl - backtest may be limited")
        except Exception as e:
            messages.append(f"ERROR: Failed to read events.jsonl: {e}")
            success = False

    # Check yfinance available
    try:
        import yfinance
        messages.append("OK: yfinance library available")
    except ImportError:
        messages.append("ERROR: yfinance not installed (pip install yfinance)")
        success = False

    # Check disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage(repo_root)
        free_gb = free // (2**30)
        messages.append(f"OK: {free_gb}GB disk space available")

        if free_gb < 1:
            messages.append("WARNING: Low disk space - price cache may fail")
    except Exception:
        messages.append("WARNING: Could not check disk space")

    # Check output directory
    output_dir = repo_root / "backtest_results"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        messages.append(f"OK: Output directory ready: {output_dir}")
    except Exception as e:
        messages.append(f"ERROR: Cannot create output directory: {e}")
        success = False

    return success, messages


def run_2year_backtest():
    """
    Execute 2-year backtest with production parameters.

    Returns
    -------
    dict or None
        Backtest results if successful, None on failure
    """
    log.info("=" * 80)
    log.info("CATALYST-BOT 2-YEAR BACKTEST")
    log.info("=" * 80)
    log.info("Period: 2023-01-01 to 2025-01-01")
    log.info("Strategy: Conservative penny stock catalyst trading")
    log.info("")

    # Pre-flight checks
    log.info("Running pre-flight checks...")
    success, messages = validate_environment()

    for msg in messages:
        if msg.startswith("ERROR"):
            log.error(msg)
        elif msg.startswith("WARNING"):
            log.warning(msg)
        else:
            log.info(msg)

    if not success:
        log.error("Pre-flight checks FAILED - aborting backtest")
        return None

    log.info("")
    log.info("Pre-flight checks PASSED")
    log.info("")

    # Configure strategy parameters
    # Conservative settings for penny stocks ($1-$10 range)
    strategy_params = {
        # Entry criteria
        'min_score': 0.30,              # Only high-quality alerts (30%+)
        'min_sentiment': 0.10,          # Require positive sentiment

        # Exit rules
        'take_profit_pct': 0.20,        # +20% profit target (conservative for pennies)
        'stop_loss_pct': 0.10,          # -10% stop loss (tight risk control)
        'max_hold_hours': 24,           # Day trade strategy (exit within 24h)

        # Position sizing
        'position_size_pct': 0.10,      # 10% of capital per trade (max 10 positions)
        'max_daily_volume_pct': 0.05,   # Max 5% of daily volume (avoid slippage)

        # Optional: Filter by catalyst type
        # 'required_catalysts': ['fda', 'earnings'],  # Uncomment to filter
    }

    log.info("Strategy Parameters:")
    for key, value in strategy_params.items():
        log.info(f"  {key}: {value}")
    log.info("")

    # Initialize backtest engine
    log.info("Initializing backtest engine...")
    try:
        engine = BacktestEngine(
            start_date="2023-01-01",
            end_date="2025-01-01",
            initial_capital=10000.0,
            strategy_params=strategy_params
        )
        log.info("Engine initialized successfully")
    except Exception as e:
        log.error(f"Failed to initialize engine: {e}")
        return None

    log.info("")
    log.info("Starting backtest execution...")
    log.info("This may take 30-60 minutes depending on data volume and network speed")
    log.info("")

    # Run backtest with progress tracking
    start_time = datetime.now(timezone.utc)

    try:
        results = engine.run_backtest()
    except KeyboardInterrupt:
        log.warning("Backtest interrupted by user")
        return None
    except Exception as e:
        log.error(f"Backtest failed: {e}", exc_info=True)
        return None

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    log.info("")
    log.info("=" * 80)
    log.info("BACKTEST COMPLETED")
    log.info("=" * 80)
    log.info(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    log.info("")

    # Display summary
    metrics = results['metrics']
    log.info("SUMMARY METRICS:")
    log.info(f"  Total Return:   {metrics['total_return_pct']:>10.2f}%")
    log.info(f"  Sharpe Ratio:   {metrics.get('sharpe_ratio', 0):>10.2f}")
    log.info(f"  Win Rate:       {metrics['win_rate']:>10.1f}%")
    log.info(f"  Max Drawdown:   {metrics['max_drawdown_pct']:>10.2f}%")
    log.info(f"  Profit Factor:  {metrics.get('profit_factor', 0):>10.2f}")
    log.info(f"  Total Trades:   {metrics['total_trades']:>10d}")
    log.info(f"  Winning Trades: {metrics['winning_trades']:>10d}")
    log.info(f"  Losing Trades:  {metrics['losing_trades']:>10d}")
    log.info(f"  Avg Hold Time:  {metrics['avg_hold_time_hours']:>10.1f} hours")
    log.info("")

    return results


def save_results(results):
    """
    Save backtest results to multiple formats.

    Parameters
    ----------
    results : dict
        Backtest results from engine
    """
    output_dir = repo_root / "backtest_results"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Save markdown report
    report_path = output_dir / f"backtest_2year_{timestamp}.md"
    try:
        generate_backtest_report(
            results,
            output_format='markdown',
            output_path=str(report_path)
        )
        log.info(f"Markdown report saved: {report_path}")
    except Exception as e:
        log.error(f"Failed to save markdown report: {e}")

    # Save JSON results
    json_path = output_dir / f"backtest_2year_{timestamp}.json"
    try:
        import json
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        log.info(f"JSON results saved: {json_path}")
    except Exception as e:
        log.error(f"Failed to save JSON results: {e}")

    # Save trades CSV
    csv_path = output_dir / f"backtest_2year_trades_{timestamp}.csv"
    try:
        export_trades_to_csv(results['trades'], str(csv_path))
        log.info(f"Trade log CSV saved: {csv_path}")
    except Exception as e:
        log.error(f"Failed to save trades CSV: {e}")

    log.info("")
    log.info(f"All results saved to: {output_dir}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run 2-year backtest")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    print("")
    print("=" * 80)
    print("CATALYST-BOT 2-YEAR BACKTEST")
    print("=" * 80)
    print("")
    print("This script will run a comprehensive 2-year backtest of the penny stock")
    print("catalyst trading strategy from 2023-01-01 to 2025-01-01.")
    print("")
    print("Expected runtime: 30-60 minutes")
    print("Network usage: ~200MB (price data)")
    print("Disk usage: ~500MB (price cache)")
    print("")

    if not args.yes:
        response = input("Continue? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("Backtest cancelled by user")
            return 1

    print("")

    # Run backtest
    results = run_2year_backtest()

    if results is None:
        log.error("Backtest failed - no results to save")
        return 1

    # Save results
    log.info("")
    log.info("Saving results...")
    save_results(results)

    log.info("")
    log.info("=" * 80)
    log.info("BACKTEST COMPLETE")
    log.info("=" * 80)
    log.info("")
    log.info("Check backtest_results/ directory for full report and trade log")
    log.info("")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nBacktest interrupted by user")
        sys.exit(130)
    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
