"""
StrategyEvaluator: Comprehensive backtesting and performance analysis for RL agents.

This module provides tools for evaluating trained RL agents on historical data,
calculating performance metrics, generating reports, and visualizing results.

Key Features:
  - Backtest agents on historical catalyst data
  - Calculate comprehensive performance metrics (Sharpe, Sortino, max drawdown, etc.)
  - Generate detailed performance reports (HTML, PDF, JSON)
  - Visualize equity curves, trades, drawdowns
  - Compare multiple strategies (ensemble vs single agents)
  - Monte Carlo simulation for robustness testing

Example usage:
    >>> from catalyst_bot.ml.evaluate import StrategyEvaluator
    >>> evaluator = StrategyEvaluator()
    >>> results = evaluator.backtest_agent("checkpoints/ppo.zip", "ppo", test_data)
    >>> evaluator.print_report(results)
    >>> evaluator.plot_equity_curve(results)

Architecture:
    - Uses CatalystTradingEnv for realistic simulation
    - Computes industry-standard performance metrics
    - Integrates with matplotlib/plotly for visualization
    - Exports results to multiple formats
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from stable_baselines3 import A2C, PPO, SAC

from ..config import get_settings
from ..logging_utils import get_logger
from .trading_env import CatalystTradingEnv

log = get_logger(__name__)

# Optional imports for visualization
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    log.warning("matplotlib_unavailable hint=install_for_visualization")

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics for backtesting results.

    Attributes
    ----------
    total_return : float
        Total return (%)
    annualized_return : float
        Annualized return (%)
    sharpe_ratio : float
        Sharpe ratio (risk-adjusted return)
    sortino_ratio : float
        Sortino ratio (downside risk-adjusted return)
    max_drawdown : float
        Maximum drawdown (%)
    max_drawdown_duration : int
        Maximum drawdown duration (days)
    calmar_ratio : float
        Calmar ratio (return / max drawdown)
    win_rate : float
        Percentage of winning trades
    profit_factor : float
        Ratio of gross profit to gross loss
    avg_trade_return : float
        Average return per trade (%)
    total_trades : int
        Total number of trades
    total_fees : float
        Total transaction fees paid
    final_portfolio_value : float
        Final portfolio value ($)
    """

    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    avg_trade_return: float
    total_trades: int
    total_fees: float
    final_portfolio_value: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "calmar_ratio": self.calmar_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_trade_return": self.avg_trade_return,
            "total_trades": self.total_trades,
            "total_fees": self.total_fees,
            "final_portfolio_value": self.final_portfolio_value,
        }


class StrategyEvaluator:
    """
    Comprehensive backtesting and evaluation for RL trading agents.

    This class provides tools to:
      1. Backtest agents on historical data
      2. Calculate performance metrics
      3. Generate performance reports
      4. Visualize results (equity curves, trades, etc.)
      5. Compare multiple strategies

    Parameters
    ----------
    initial_capital : float, optional
        Starting capital for backtests (default: 10000.0)
    risk_free_rate : float, optional
        Risk-free rate for Sharpe calculation (default: 0.02)
    output_dir : str, optional
        Directory for saving reports/plots (default: "evaluation/")
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        risk_free_rate: float = 0.02,
        output_dir: str = "evaluation/",
    ):
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        log.info(
            "evaluator_initialized initial_capital=%.2f risk_free_rate=%.4f "
            "output_dir=%s",
            initial_capital,
            risk_free_rate,
            output_dir,
        )

    def backtest_agent(
        self,
        model_path: str,
        model_type: str,
        test_data: pd.DataFrame,
        deterministic: bool = True,
    ) -> Dict[str, Any]:
        """
        Backtest a trained agent on historical data.

        Parameters
        ----------
        model_path : str
            Path to trained model
        model_type : str
            Model type ("ppo", "sac", "a2c")
        test_data : pd.DataFrame
            Test data with catalyst events
        deterministic : bool, optional
            Use deterministic actions (default: True)

        Returns
        -------
        dict
            Backtest results containing:
                - metrics: PerformanceMetrics object
                - equity_curve: List of portfolio values over time
                - positions: List of positions taken
                - trades: List of trade records
                - timestamps: List of timestamps
        """
        # TODO: Implement comprehensive backtesting
        # Consider:
        #   - Logging all trades for analysis
        #   - Handling edge cases (empty data, model failures)
        #   - Recording state/action/reward for debugging

        log.info(
            "backtest_start model=%s type=%s test_rows=%d",
            model_path,
            model_type,
            len(test_data),
        )

        # Load model
        if model_type.lower() == "ppo":
            model = PPO.load(model_path)
        elif model_type.lower() == "sac":
            model = SAC.load(model_path)
        elif model_type.lower() == "a2c":
            model = A2C.load(model_path)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        # Create environment
        env = CatalystTradingEnv(
            data_df=test_data,
            initial_capital=self.initial_capital,
        )

        # Run backtest
        obs, info = env.reset()
        done = False

        equity_curve = [self.initial_capital]
        positions = [0.0]
        trades = []
        timestamps = [test_data.iloc[0]["ts_utc"]]
        transaction_fees = 0.0

        step = 0
        while not done:
            # Get action from model
            action, _ = model.predict(obs, deterministic=deterministic)

            # Execute action
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated

            # Record state
            equity_curve.append(info["portfolio_value"])
            positions.append(info["position"])

            if step < len(test_data):
                timestamps.append(test_data.iloc[step]["ts_utc"])

            # Record trades (when position changes)
            if len(positions) >= 2 and positions[-1] != positions[-2]:
                trades.append(
                    {
                        "timestamp": timestamps[-1],
                        "action": "BUY" if positions[-1] > positions[-2] else "SELL",
                        "position_from": positions[-2],
                        "position_to": positions[-1],
                        "price": info["current_price"],
                        "portfolio_value": info["portfolio_value"],
                    }
                )

            transaction_fees += info.get("transaction_cost", 0.0)
            step += 1

        # Calculate metrics
        metrics = self._calculate_metrics(
            equity_curve,
            trades,
            transaction_fees,
            timestamps,
        )

        log.info(
            "backtest_complete steps=%d total_return=%.2f%% sharpe=%.3f "
            "max_drawdown=%.2f%% trades=%d",
            step,
            metrics.total_return,
            metrics.sharpe_ratio,
            metrics.max_drawdown,
            len(trades),
        )

        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "positions": positions,
            "trades": trades,
            "timestamps": timestamps,
            "model_path": model_path,
            "model_type": model_type,
        }

    def _calculate_metrics(
        self,
        equity_curve: List[float],
        trades: List[Dict[str, Any]],
        transaction_fees: float,
        timestamps: List[Any],
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.

        Parameters
        ----------
        equity_curve : list of float
            Portfolio value over time
        trades : list of dict
            Trade records
        transaction_fees : float
            Total transaction fees
        timestamps : list
            Timestamps for equity curve

        Returns
        -------
        PerformanceMetrics
            Calculated metrics
        """
        # TODO: Implement sophisticated metric calculation
        # Consider:
        #   - Handling edge cases (no trades, constant equity)
        #   - Using proper annualization factors
        #   - Calculating underwater curve for drawdown duration

        equity = np.array(equity_curve)
        initial_value = equity[0]
        final_value = equity[-1]

        # Total return
        total_return = (final_value / initial_value - 1.0) * 100.0

        # Annualized return (assuming daily data)
        n_days = len(equity)
        years = n_days / 252.0  # Trading days
        annualized_return = ((final_value / initial_value) ** (1 / years) - 1.0) * 100.0

        # Returns
        returns = np.diff(equity) / equity[:-1]

        # Sharpe ratio
        excess_returns = returns - (self.risk_free_rate / 252.0)
        sharpe_ratio = (
            np.mean(excess_returns) / (np.std(returns) + 1e-8) * np.sqrt(252.0)
        )

        # Sortino ratio (uses downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) + 1e-8
        sortino_ratio = np.mean(excess_returns) / downside_std * np.sqrt(252.0)

        # Max drawdown
        cumulative_max = np.maximum.accumulate(equity)
        drawdown = (equity - cumulative_max) / cumulative_max * 100.0
        max_drawdown = abs(drawdown.min())

        # Max drawdown duration
        underwater = drawdown < 0
        if underwater.any():
            # Find longest consecutive underwater period
            underwater_periods = []
            current_period = 0
            for is_underwater in underwater:
                if is_underwater:
                    current_period += 1
                else:
                    if current_period > 0:
                        underwater_periods.append(current_period)
                    current_period = 0
            if current_period > 0:
                underwater_periods.append(current_period)
            max_drawdown_duration = max(underwater_periods) if underwater_periods else 0
        else:
            max_drawdown_duration = 0

        # Calmar ratio
        calmar_ratio = (
            annualized_return / max_drawdown if max_drawdown > 0 else 0.0
        )

        # Trade statistics
        if trades:
            # Calculate win rate (simplified - based on trade direction vs return)
            # TODO: Improve this by tracking individual trade P&L
            winning_trades = sum(
                1 for t in trades if t.get("portfolio_value", 0) > initial_value
            )
            win_rate = winning_trades / len(trades) * 100.0

            # Profit factor (simplified)
            positive_returns = returns[returns > 0].sum()
            negative_returns = abs(returns[returns < 0].sum())
            profit_factor = (
                positive_returns / negative_returns
                if negative_returns > 0
                else float("inf")
            )

            # Avg trade return
            avg_trade_return = np.mean(returns) * 100.0

            total_trades = len(trades)
        else:
            win_rate = 0.0
            profit_factor = 0.0
            avg_trade_return = 0.0
            total_trades = 0

        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_drawdown_duration,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_return=avg_trade_return,
            total_trades=total_trades,
            total_fees=transaction_fees,
            final_portfolio_value=final_value,
        )

    def print_report(self, results: Dict[str, Any]) -> None:
        """
        Print human-readable performance report to console.

        Parameters
        ----------
        results : dict
            Backtest results from backtest_agent()
        """
        metrics = results["metrics"]

        print("\n" + "=" * 60)
        print("BACKTEST PERFORMANCE REPORT")
        print("=" * 60)
        print(f"Model: {results['model_path']}")
        print(f"Type: {results['model_type']}")
        print("-" * 60)
        print("\nRETURNS:")
        print(f"  Total Return:        {metrics.total_return:>10.2f}%")
        print(f"  Annualized Return:   {metrics.annualized_return:>10.2f}%")
        print(f"  Final Portfolio:     ${metrics.final_portfolio_value:>10.2f}")
        print("\nRISK-ADJUSTED METRICS:")
        print(f"  Sharpe Ratio:        {metrics.sharpe_ratio:>10.3f}")
        print(f"  Sortino Ratio:       {metrics.sortino_ratio:>10.3f}")
        print(f"  Calmar Ratio:        {metrics.calmar_ratio:>10.3f}")
        print("\nDRAWDOWN:")
        print(f"  Max Drawdown:        {metrics.max_drawdown:>10.2f}%")
        print(f"  Max DD Duration:     {metrics.max_drawdown_duration:>10d} days")
        print("\nTRADING ACTIVITY:")
        print(f"  Total Trades:        {metrics.total_trades:>10d}")
        print(f"  Win Rate:            {metrics.win_rate:>10.2f}%")
        print(f"  Profit Factor:       {metrics.profit_factor:>10.3f}")
        print(f"  Avg Trade Return:    {metrics.avg_trade_return:>10.2f}%")
        print(f"  Total Fees:          ${metrics.total_fees:>10.2f}")
        print("=" * 60 + "\n")

    def save_report(self, results: Dict[str, Any], output_path: str) -> None:
        """
        Save performance report to JSON file.

        Parameters
        ----------
        results : dict
            Backtest results
        output_path : str
            Output file path
        """
        # Convert metrics to dict
        report = {
            "model_path": results["model_path"],
            "model_type": results["model_type"],
            "metrics": results["metrics"].to_dict(),
            "n_trades": len(results["trades"]),
            "n_steps": len(results["equity_curve"]),
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        log.info("report_saved path=%s", output_path)

    def plot_equity_curve(
        self,
        results: Dict[str, Any],
        output_path: Optional[str] = None,
        use_plotly: bool = False,
    ) -> None:
        """
        Plot equity curve with trades marked.

        Parameters
        ----------
        results : dict
            Backtest results
        output_path : str, optional
            Output path for plot (default: None = show plot)
        use_plotly : bool, optional
            Use Plotly instead of Matplotlib (default: False)
        """
        # TODO: Implement rich visualization
        # Consider:
        #   - Marking buy/sell points
        #   - Showing drawdown overlay
        #   - Multiple subplots (equity, position, drawdown)

        if use_plotly and not PLOTLY_AVAILABLE:
            log.warning("plotly_unavailable falling_back_to_matplotlib")
            use_plotly = False

        if not use_plotly and not MATPLOTLIB_AVAILABLE:
            log.error("matplotlib_unavailable cannot_plot")
            return

        equity = results["equity_curve"]
        timestamps = results["timestamps"]
        trades = results["trades"]

        if use_plotly:
            # Plotly implementation
            fig = make_subplots(
                rows=2,
                cols=1,
                subplot_titles=("Portfolio Value", "Position Size"),
                row_heights=[0.7, 0.3],
            )

            # Equity curve
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=equity,
                    mode="lines",
                    name="Portfolio Value",
                    line=dict(color="blue", width=2),
                ),
                row=1,
                col=1,
            )

            # Mark trades
            buy_timestamps = [t["timestamp"] for t in trades if t["action"] == "BUY"]
            buy_values = [
                equity[timestamps.index(t)] for t in buy_timestamps if t in timestamps
            ]

            sell_timestamps = [t["timestamp"] for t in trades if t["action"] == "SELL"]
            sell_values = [
                equity[timestamps.index(t)] for t in sell_timestamps if t in timestamps
            ]

            fig.add_trace(
                go.Scatter(
                    x=buy_timestamps,
                    y=buy_values,
                    mode="markers",
                    name="Buy",
                    marker=dict(color="green", size=10, symbol="triangle-up"),
                ),
                row=1,
                col=1,
            )

            fig.add_trace(
                go.Scatter(
                    x=sell_timestamps,
                    y=sell_values,
                    mode="markers",
                    name="Sell",
                    marker=dict(color="red", size=10, symbol="triangle-down"),
                ),
                row=1,
                col=1,
            )

            # Position size
            positions = results["positions"]
            fig.add_trace(
                go.Scatter(
                    x=timestamps[: len(positions)],
                    y=positions,
                    mode="lines",
                    name="Position",
                    line=dict(color="purple", width=1),
                ),
                row=2,
                col=1,
            )

            fig.update_layout(
                title="Backtest Results",
                xaxis_title="Date",
                yaxis_title="Portfolio Value ($)",
                height=800,
            )

            if output_path:
                fig.write_html(output_path)
                log.info("plot_saved path=%s format=html", output_path)
            else:
                fig.show()

        else:
            # Matplotlib implementation
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

            # Equity curve
            ax1.plot(timestamps, equity, label="Portfolio Value", color="blue", linewidth=2)

            # Mark trades
            for trade in trades:
                ts = trade["timestamp"]
                if ts in timestamps:
                    idx = timestamps.index(ts)
                    if trade["action"] == "BUY":
                        ax1.scatter(ts, equity[idx], color="green", marker="^", s=100, zorder=5)
                    else:
                        ax1.scatter(ts, equity[idx], color="red", marker="v", s=100, zorder=5)

            ax1.axhline(
                y=self.initial_capital, color="gray", linestyle="--", alpha=0.5, label="Initial Capital"
            )
            ax1.set_ylabel("Portfolio Value ($)")
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax1.set_title("Backtest Results")

            # Position size
            positions = results["positions"]
            ax2.plot(
                timestamps[: len(positions)],
                positions,
                label="Position Size",
                color="purple",
                linewidth=1,
            )
            ax2.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
            ax2.set_xlabel("Date")
            ax2.set_ylabel("Position Size")
            ax2.legend()
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()

            if output_path:
                plt.savefig(output_path, dpi=300, bbox_inches="tight")
                log.info("plot_saved path=%s format=png", output_path)
            else:
                plt.show()

    def compare_strategies(
        self,
        results_list: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compare performance of multiple strategies.

        Parameters
        ----------
        results_list : list of dict
            List of backtest results to compare
        output_path : str, optional
            Path to save comparison table (CSV)

        Returns
        -------
        pd.DataFrame
            Comparison table with all metrics
        """
        # TODO: Implement strategy comparison
        # Consider:
        #   - Side-by-side metric comparison
        #   - Statistical significance testing
        #   - Overlaid equity curves

        comparison_data = []

        for results in results_list:
            metrics = results["metrics"]
            model_name = Path(results["model_path"]).stem

            comparison_data.append(
                {
                    "Model": model_name,
                    "Type": results["model_type"],
                    "Total Return (%)": metrics.total_return,
                    "Annualized Return (%)": metrics.annualized_return,
                    "Sharpe Ratio": metrics.sharpe_ratio,
                    "Sortino Ratio": metrics.sortino_ratio,
                    "Max Drawdown (%)": metrics.max_drawdown,
                    "Calmar Ratio": metrics.calmar_ratio,
                    "Win Rate (%)": metrics.win_rate,
                    "Total Trades": metrics.total_trades,
                }
            )

        df = pd.DataFrame(comparison_data)

        if output_path:
            df.to_csv(output_path, index=False)
            log.info("comparison_saved path=%s", output_path)

        return df


# Example usage
if __name__ == "__main__":
    # TODO: Add command-line interface for evaluation
    # Example:
    #   python evaluate.py --model checkpoints/ppo.zip --type ppo --data data/test.csv

    import argparse

    parser = argparse.ArgumentParser(description="Evaluate RL trading agent")
    parser.add_argument("--model", type=str, required=True, help="Path to trained model")
    parser.add_argument(
        "--type",
        type=str,
        required=True,
        choices=["ppo", "sac", "a2c"],
        help="Model type",
    )
    parser.add_argument("--data", type=str, required=True, help="Test data CSV path")
    parser.add_argument(
        "--output-dir", type=str, default="evaluation/", help="Output directory"
    )

    args = parser.parse_args()

    # Load test data
    test_data = pd.read_csv(args.data)

    # Create evaluator
    evaluator = StrategyEvaluator(output_dir=args.output_dir)

    # Run backtest
    results = evaluator.backtest_agent(args.model, args.type, test_data)

    # Print report
    evaluator.print_report(results)

    # Save report
    report_path = Path(args.output_dir) / "report.json"
    evaluator.save_report(results, str(report_path))

    # Plot equity curve
    plot_path = Path(args.output_dir) / "equity_curve.png"
    evaluator.plot_equity_curve(results, output_path=str(plot_path))

    print(f"\nEvaluation complete. Results saved to {args.output_dir}")
