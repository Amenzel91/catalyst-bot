"""CLI entry point for the catalyst bot.

This module allows you to invoke the main live runner or the
end‑of‑day/premarket analyzer from the command line. Use the
following patterns when calling this script:

.. code-block:: bash

    # Run a single iteration of the live bot
    python -m catalyst_bot.runner --once

    # Run the live bot in a continuous loop (default configured period)
    python -m catalyst_bot.runner --loop

    # Run the analyzer for a specific date (YYYY-MM-DD)
    python -m catalyst_bot.analyzer --date 2025-08-21

This file does not implement any runtime logic itself; it simply
dispatches execution to the appropriate submodules.
"""

from __future__ import annotations

import argparse
import importlib
import sys


def main(argv: list[str] | None = None) -> None:
    """Parse command line arguments and invoke the appropriate module.

    Parameters
    ----------
    argv : list[str] | None, optional
        Optional argument vector to parse instead of :data:`sys.argv`.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Catalyst bot CLI. Use this entrypoint to run the live bot or the"
            " analyzer."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Runner subcommand
    parser_run = subparsers.add_parser(
        "run", help="Run the live catalyst bot (once or continuously)"
    )
    parser_run.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Run a single iteration of the live bot and exit.",
    )
    parser_run.add_argument(
        "--loop",
        action="store_true",
        default=False,
        help="Run the live bot continuously until stopped.",
    )

    # Analyzer subcommand
    parser_analyze = subparsers.add_parser(
        "analyze", help="Run the end‑of‑day or pre‑market analyzer"
    )
    parser_analyze.add_argument(
        "--date",
        type=str,
        required=False,
        help=(
            "Date to analyze in YYYY‑MM‑DD format. Defaults to the current date in"
            " the configured timezone."
        ),
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        # Defer import until invoked to reduce startup cost and avoid side effects
        runner = importlib.import_module("catalyst_bot.runner")
        # If neither --once nor --loop is specified, default to a single run
        once = args.once or not args.loop
        runner.main(once=once, loop=args.loop)
    elif args.command == "analyze":
        analyzer = importlib.import_module("catalyst_bot.analyzer")
        analyzer.main(date=args.date)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()