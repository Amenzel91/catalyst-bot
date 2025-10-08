"""
Backtesting Engine for Catalyst Bot
====================================

Production-grade backtesting system for validating trading strategies with
realistic penny stock simulations including slippage, fees, and volume constraints.

Components:
- trade_simulator: Realistic penny stock trade execution with slippage
- portfolio: Position tracking and P&L calculation
- engine: Main backtesting engine for replaying historical alerts
- analytics: Performance metrics (Sharpe, drawdown, win rate)
- monte_carlo: Parameter sensitivity and optimization
- reports: Comprehensive backtest reporting
- validator: Before/after parameter validation

Example usage:
    from catalyst_bot.backtesting import BacktestEngine

    engine = BacktestEngine(
        start_date="2025-08-01",
        end_date="2025-09-01",
        initial_capital=10000.0
    )
    results = engine.run_backtest()
    print(f"Total Return: {results['metrics']['total_return_pct']:.2f}%")
    print(f"Sharpe Ratio: {results['metrics']['sharpe_ratio']:.2f}")
"""

from .analytics import (
    analyze_catalyst_performance,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from .engine import BacktestEngine
from .portfolio import Portfolio, Position
from .trade_simulator import PennyStockTradeSimulator

__all__ = [
    "BacktestEngine",
    "Portfolio",
    "Position",
    "PennyStockTradeSimulator",
    "calculate_sharpe_ratio",
    "calculate_max_drawdown",
    "calculate_win_rate",
    "calculate_profit_factor",
    "analyze_catalyst_performance",
]
