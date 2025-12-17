"""
Allow running simulation as a module.

Usage:
    python -m catalyst_bot.simulation
    python -m catalyst_bot.simulation --preset sec --speed 0
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
