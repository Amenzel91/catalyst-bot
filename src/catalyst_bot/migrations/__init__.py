"""
Database migrations for Catalyst Bot Paper Trading System.

This package contains migration scripts for:
- positions.db: Open and closed trading positions
- trading.db: Orders, fills, portfolio snapshots, and performance metrics
- ml_training.db: RL training runs, agent performance, and hyperparameters

Usage:
    python -m catalyst_bot.migrations.migrate

Each migration is versioned and idempotent (safe to run multiple times).
"""

__version__ = "1.0.0"
