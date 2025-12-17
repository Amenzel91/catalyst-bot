"""
Simulation CLI - Command-line interface for running simulations.

Usage:
    # Run with defaults (Nov 12 2024, morning preset, 6x speed)
    python -m catalyst_bot.simulation.cli

    # Use preset for specific testing scenario
    python -m catalyst_bot.simulation.cli --preset morning  # 8:45-9:45 EST news rush
    python -m catalyst_bot.simulation.cli --preset sec      # 3:30-4:30 EST SEC filings

    # Custom time range
    python -m catalyst_bot.simulation.cli --start-time 08:00 --end-time 10:00

    # Maximum speed (instant)
    python -m catalyst_bot.simulation.cli --speed 0

    # Dry run (validate only)
    python -m catalyst_bot.simulation.cli --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import TIME_PRESETS
from .controller import SimulationController, SimulationSetupError
from .data_fetcher import HistoricalDataFetcher


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure logging for simulation."""
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    preset_list = ", ".join(TIME_PRESETS.keys())

    parser = argparse.ArgumentParser(
        description="Run trading day simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Presets:
    morning   8:45-9:45 EST  News rush, high activity
    sec       3:30-4:30 EST  SEC filing window
    open      9:30-10:30 EST Market open hour
    close     3:00-4:00 EST  Market close hour
    full      5:00am-6:00pm EST  Full trading day

Examples:
    # Quick morning test (default)
    python -m catalyst_bot.simulation.cli

    # Test SEC filing period at instant speed
    python -m catalyst_bot.simulation.cli --preset sec --speed 0

    # Custom date and time
    python -m catalyst_bot.simulation.cli --date 2024-11-12 --start-time 08:00

    # Local-only alerts (no Discord)
    python -m catalyst_bot.simulation.cli --alerts local

    # Validate configuration without running
    python -m catalyst_bot.simulation.cli --dry-run
        """,
    )

    parser.add_argument(
        "--date",
        type=str,
        default="2024-11-12",
        help="Simulation date (YYYY-MM-DD). Default: 2024-11-12",
    )

    parser.add_argument(
        "--preset",
        choices=list(TIME_PRESETS.keys()),
        default="morning",
        help=f"Time preset ({preset_list}). Default: morning",
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=6.0,
        help="Speed multiplier (0=instant, 1=realtime, 6=6x). Default: 6",
    )

    parser.add_argument(
        "--start-time",
        type=str,
        dest="start_time",
        help="Start time in CST (HH:MM). Overrides preset.",
    )

    parser.add_argument(
        "--end-time",
        type=str,
        dest="end_time",
        help="End time in CST (HH:MM). Overrides preset.",
    )

    parser.add_argument(
        "--cash",
        type=float,
        default=10000.0,
        help="Starting cash. Default: 10000",
    )

    parser.add_argument(
        "--alerts",
        choices=["discord", "local", "disabled"],
        default="local",
        help="Alert output mode. Default: local",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and check APIs without running simulation",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        dest="no_cache",
        help="Force fresh data fetch, ignore cached historical data",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (DEBUG level)",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Quiet output (WARNING level only)",
    )

    # Cache management
    parser.add_argument(
        "--list-cache",
        action="store_true",
        dest="list_cache",
        help="List available cached simulation dates and exit",
    )

    parser.add_argument(
        "--clear-cache",
        nargs="?",
        const="all",
        metavar="DATE",
        dest="clear_cache",
        help="Clear cache (specify DATE in YYYY-MM-DD or 'all')",
    )

    # Price and news source options
    parser.add_argument(
        "--price-source",
        choices=["tiingo", "yfinance", "cached"],
        default="tiingo",
        dest="price_source",
        help="Price data source. Default: tiingo",
    )

    parser.add_argument(
        "--news-source",
        choices=["finnhub", "cached"],
        default="finnhub",
        dest="news_source",
        help="News data source. Default: finnhub",
    )

    return parser.parse_args()


def print_banner() -> None:
    """Print simulation banner."""
    print()
    print("=" * 60)
    print("  CATALYST-BOT SIMULATION")
    print("=" * 60)
    print()


def print_results(results: dict) -> None:
    """Print simulation results."""
    print()
    print("=" * 60)
    print("SIMULATION RESULTS")
    print("=" * 60)
    print(f"Run ID: {results['run_id']}")
    print(f"Date: {results['simulation_date']}")
    print(f"Speed: {results['speed_multiplier']}x")
    print(f"Events Processed: {results['events_processed']}")
    if results.get("critical_errors"):
        print(f"Critical Errors: {results['critical_errors']}")
    print()

    portfolio = results.get("portfolio", {})
    if portfolio:
        print("Portfolio:")
        print(f"  Starting Cash: ${portfolio.get('starting_cash', 0):,.2f}")
        print(f"  Final Value:   ${portfolio.get('total_value', 0):,.2f}")
        total_return = portfolio.get("total_return", 0)
        return_pct = portfolio.get("total_return_pct", 0)
        print(f"  Return:        ${total_return:,.2f} ({return_pct:.2f}%)")
        print(f"  Total Trades:  {portfolio.get('total_trades', 0)}")
        if portfolio.get("total_trades", 0) > 0:
            print(f"  Win Rate:      {portfolio.get('win_rate', 0):.1f}%")
        print()

    positions = results.get("positions", {})
    if positions:
        print("Open Positions:")
        for ticker, pos in positions.items():
            print(
                f"  {ticker}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f} "
                f"(P&L: ${pos['unrealized_pnl']:.2f})"
            )
        print()

    log_files = results.get("log_files", {})
    if log_files.get("markdown"):
        print(f"Report: {log_files['markdown']}")
    if log_files.get("jsonl"):
        print(f"Events: {log_files['jsonl']}")


def handle_list_cache(cache_dir: Path) -> int:
    """List available cached simulation dates."""
    fetcher = HistoricalDataFetcher(cache_dir=cache_dir)
    dates = fetcher.get_cached_dates()

    if not dates:
        print("No cached simulation data found.")
        print(f"Cache directory: {cache_dir}")
        return 0

    print(f"Cached simulation dates ({len(dates)}):")
    print()
    for date in dates:
        print(f"  {date}")
    print()
    print(f"Cache directory: {cache_dir}")
    return 0


def handle_clear_cache(date_spec: str, cache_dir: Path) -> int:
    """Clear simulation cache."""
    fetcher = HistoricalDataFetcher(cache_dir=cache_dir)

    if date_spec == "all":
        confirm = input("Clear ALL cached simulation data? [y/N] ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return 0
        deleted = fetcher.clear_cache()
        print(f"Deleted {deleted} cache files.")
    else:
        try:
            date = datetime.strptime(date_spec, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            deleted = fetcher.clear_cache(date)
            print(f"Deleted {deleted} cache files for {date_spec}.")
        except ValueError:
            print(f"Invalid date format: {date_spec}")
            print("Use YYYY-MM-DD format or 'all'.")
            return 1

    return 0


async def run_simulation(args: argparse.Namespace) -> int:
    """Run the simulation with given arguments."""

    # Set SIMULATION_MODE environment variable
    os.environ["SIMULATION_MODE"] = "1"

    # Create controller with preset support
    controller = SimulationController(
        simulation_date=args.date,
        speed_multiplier=args.speed,
        time_preset=(args.preset if not (args.start_time or args.end_time) else None),
        start_time_cst=args.start_time,
        end_time_cst=args.end_time,
    )

    # Override config
    controller.config.starting_cash = args.cash
    controller.config.alert_output = {
        "discord": "discord_test",
        "local": "local_only",
        "disabled": "disabled",
    }.get(args.alerts, "local_only")
    controller.config.use_cache = not args.no_cache
    controller.config.price_source = args.price_source
    controller.config.news_source = args.news_source

    # Dry run mode - validate and exit
    if args.dry_run:
        print("Dry run mode - validating configuration...")
        try:
            await controller.validate()
            print("Configuration valid. Ready to run.")
            print()
            print(f"  Date: {controller.config.simulation_date or 'random'}")
            print(f"  Preset: {controller.config.time_preset or 'custom'}")
            print(f"  Speed: {controller.config.speed_multiplier}x")
            print(f"  Cash: ${controller.config.starting_cash:,.2f}")
            return 0
        except SimulationSetupError as e:
            print(f"Validation failed: {e}")
            return 1

    try:
        # Print startup info
        print(f"Date: {args.date}")
        print(f"Preset: {args.preset}")
        print(f"Speed: {args.speed}x")
        print(f"Cache: {'disabled' if args.no_cache else 'enabled'}")
        print()
        print("Starting simulation...")
        print()

        # Run simulation
        results = await controller.run()

        # Print results
        print_results(results)

        return 0

    except KeyboardInterrupt:
        print("\nSimulation cancelled")
        return 1

    except SimulationSetupError as e:
        print(f"\nSimulation setup failed: {e}")
        return 1

    except Exception as e:
        print(f"\nSimulation failed: {e}")
        logging.exception("Simulation error")
        return 1

    finally:
        await controller.cleanup()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose, args.quiet)

    # Default cache directory
    cache_dir = Path("data/simulation_cache")

    # Handle cache commands (no banner needed)
    if args.list_cache:
        return handle_list_cache(cache_dir)

    if args.clear_cache:
        return handle_clear_cache(args.clear_cache, cache_dir)

    print_banner()

    return asyncio.run(run_simulation(args))


if __name__ == "__main__":
    sys.exit(main())
