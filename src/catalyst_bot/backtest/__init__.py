"""
Backtesting utilities for Catalyst Bot.

The backtest module provides helpers to replay historical news events and
simulate trading strategies. It is intentionally lightweight in this phase
and serves as a scaffold for future enhancements. See loader.py and
simulator.py for details.
"""

# Export top‑level submodules for ease of access.  ``scraper`` is new in
# Phase‑C Patch 14 and provides a CLI for historical event filtering.
__all__ = ["loader", "simulator", "scraper"]
