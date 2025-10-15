#!/usr/bin/env python3
"""
Backtesting CLI
===============

Command-line interface for running backtests, parameter sweeps,
and validation.

Usage:
    # Run backtest for last 30 days
    python run_backtest.py --days 30

    # Run backtest with custom parameters
    python run_backtest.py --days 60 --min-score 0.30 --capital 10000

    # Test parameter sensitivity
    python run_backtest.py --sweep min_score --values 0.20,0.25,0.30,0.35

    # Validate parameter change
    python run_backtest.py --validate min_score --old 0.25 --new 0.30

    # Generate report only
    python run_backtest.py --days 30 --report-only --format markdown

    # Export trades to CSV
    python run_backtest.py --days 30 --export trades.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.backtesting import BacktestEngine  # noqa: E402
from catalyst_bot.backtesting.monte_carlo import MonteCarloSimulator  # noqa: E402
from catalyst_bot.backtesting.reports import (  # noqa: E402
    export_trades_to_csv,
    generate_backtest_report,
)
from catalyst_bot.backtesting.validator import validate_parameter_change  # noqa: E402
from catalyst_bot.logging_utils import get_logger  # noqa: E402

log = get_logger("run_backtest")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Catalyst Bot Backtesting CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Date range options
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backtest (default: 30)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD). Overrides --days.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD). Default: today.",
    )

    # Strategy parameters
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        help="Minimum relevance score filter",
    )
    parser.add_argument(
        "--take-profit-pct",
        type=float,
        help="Take profit percentage (e.g., 0.20 for 20%%)",
    )
    parser.add_argument(
        "--stop-loss-pct",
        type=float,
        help="Stop loss percentage (e.g., 0.10 for 10%%)",
    )
    parser.add_argument(
        "--max-hold-hours",
        type=int,
        help="Maximum hold time in hours",
    )

    # Parameter sweep mode
    parser.add_argument(
        "--sweep",
        type=str,
        help="Parameter to sweep (e.g., 'min_score')",
    )
    parser.add_argument(
        "--values",
        type=str,
        help="Comma-separated values to test (e.g., '0.20,0.25,0.30')",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=10,
        help="Number of simulations per value in sweep (default: 10)",
    )

    # Validation mode
    parser.add_argument(
        "--validate",
        type=str,
        help="Parameter to validate (e.g., 'min_score')",
    )
    parser.add_argument(
        "--old",
        type=str,
        help="Old parameter value",
    )
    parser.add_argument(
        "--new",
        type=str,
        help="New parameter value",
    )

    # Output options
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only generate report (skip backtest if results exist)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="markdown",
        choices=["markdown", "html", "json", "discord_embed"],
        help="Report format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for report",
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export trades to CSV file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        import logging

        logging.getLogger("catalyst_bot").setLevel(logging.DEBUG)

    # Calculate date range
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    else:
        end_date = datetime.now(timezone.utc)

    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    else:
        start_date = end_date - timedelta(days=args.days)

    # Build strategy params
    strategy_params = {}
    if args.min_score is not None:
        strategy_params["min_score"] = args.min_score
    if args.take_profit_pct is not None:
        strategy_params["take_profit_pct"] = args.take_profit_pct
    if args.stop_loss_pct is not None:
        strategy_params["stop_loss_pct"] = args.stop_loss_pct
    if args.max_hold_hours is not None:
        strategy_params["max_hold_hours"] = args.max_hold_hours

    # Parameter sweep mode
    if args.sweep:
        if not args.values:
            print("Error: --values required for sweep mode")
            sys.exit(1)

        values = [_parse_value(v.strip()) for v in args.values.split(",")]

        print(f"Running parameter sweep: {args.sweep}")
        print(f"Values: {values}")
        print(f"Simulations per value: {args.simulations}")
        print(f"Date range: {start_date.date()} to {end_date.date()}")
        print()

        simulator = MonteCarloSimulator(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            initial_capital=args.capital,
            base_strategy_params=strategy_params,
        )

        results = simulator.run_parameter_sweep(
            parameter=args.sweep,
            values=values,
            num_simulations=args.simulations,
        )

        # Print results
        print("\n=== Parameter Sweep Results ===\n")
        print(f"Parameter: {results['parameter']}")
        print(f"Optimal Value: {results['optimal_value']}")
        print(f"Confidence: {results['confidence']:.2%}")
        print()
        print("| Value | Avg Sharpe | Avg Return | Avg Win Rate | Std Dev |")
        print("|-------|------------|------------|--------------|---------|")
        for r in results["results"]:
            print(
                f"| {r['value']} | {r['avg_sharpe']:.2f} | {r['avg_return_pct']:.2f}% | "
                f"{r['avg_win_rate']*100:.1f}% | {r['std_dev_return']:.2f} |"
            )

        # Save results
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {args.output}")

        return

    # Validation mode
    if args.validate:
        if not args.old or not args.new:
            print("Error: --old and --new required for validation mode")
            sys.exit(1)

        old_value = _parse_value(args.old)
        new_value = _parse_value(args.new)

        print(f"Validating parameter change: {args.validate}")
        print(f"Old value: {old_value}")
        print(f"New value: {new_value}")
        print(f"Backtest period: {args.days} days")
        print()

        results = validate_parameter_change(
            param=args.validate,
            old_value=old_value,
            new_value=new_value,
            backtest_days=args.days,
            initial_capital=args.capital,
        )

        # Print results
        print("\n=== Validation Results ===\n")
        print(f"Recommendation: {results['recommendation']}")
        print(f"Confidence: {results['confidence']:.1%}")
        print(f"Reason: {results['reason']}")
        print()
        print("| Metric | Old Value | New Value | Change |")
        print("|--------|-----------|-----------|--------|")
        print(
            f"| Sharpe Ratio | {results['old_sharpe']:.2f} | {results['new_sharpe']:.2f} | "
            f"{results['new_sharpe'] - results['old_sharpe']:+.2f} |"
        )
        print(
            f"| Return % | {results['old_return_pct']:.2f}% | {results['new_return_pct']:.2f}% | "
            f"{results['new_return_pct'] - results['old_return_pct']:+.2f}% |"
        )
        print(
            f"| Win Rate | {results['old_win_rate']:.1f}% | {results['new_win_rate']:.1f}% | "
            f"{results['new_win_rate'] - results['old_win_rate']:+.1f}% |"
        )
        print(
            f"| Max Drawdown | {results['old_max_drawdown']:.2f}% | {results['new_max_drawdown']:.2f}% | "  # noqa: E501
            f"{results['new_max_drawdown'] - results['old_max_drawdown']:+.2f}% |"
        )
        print(
            f"| Total Trades | {results['old_total_trades']} | {results['new_total_trades']} | "
            f"{results['new_total_trades'] - results['old_total_trades']:+d} |"
        )

        # Save results
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {args.output}")

        return

    # Standard backtest mode
    print("Running backtest...")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Initial capital: ${args.capital:,.2f}")
    if strategy_params:
        print(f"Strategy params: {strategy_params}")
    print()

    engine = BacktestEngine(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=args.capital,
        strategy_params=strategy_params,
    )

    results = engine.run_backtest()

    # Print summary
    metrics = results["metrics"]
    print("\n=== Backtest Results ===\n")
    print(f"Total Return: {metrics['total_return_pct']:.2f}%")
    print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Win Rate: {metrics['win_rate']:.1f}%")
    print(f"Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
    print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
    print(f"Total Trades: {metrics['total_trades']}")
    print(f"Winning Trades: {metrics['winning_trades']}")
    print(f"Losing Trades: {metrics['losing_trades']}")
    print(f"Avg Hold Time: {metrics['avg_hold_time_hours']:.1f} hours")
    print()

    # Generate report
    if args.output or args.format:
        output_path = args.output
        if not output_path:
            # Auto-generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = "md" if args.format == "markdown" else args.format
            output_path = f"backtest_report_{timestamp}.{ext}"

        generate_backtest_report(results, args.format, output_path)
        print(f"Report saved to: {output_path}")

    # Export trades to CSV
    if args.export:
        export_trades_to_csv(results["trades"], args.export)
        print(f"Trades exported to: {args.export}")


def _parse_value(value_str: str):
    """Parse a value string into appropriate type."""
    # Try int
    try:
        return int(value_str)
    except ValueError:
        pass

    # Try float
    try:
        return float(value_str)
    except ValueError:
        pass

    # Return as string
    return value_str


if __name__ == "__main__":
    main()
