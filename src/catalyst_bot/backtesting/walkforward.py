"""
Walk-Forward Optimization

Implements walk-forward testing to avoid overfitting in strategy optimization.

Key Concepts:
- Training Window: 12-18 months (in-sample)
- Testing Window: 3-6 months (out-of-sample)
- Step Size: 1 month (rolling window)
- Walk-Forward Efficiency: OOS Sharpe / IS Sharpe (target: >0.6-0.7)

Expect 30-50% degradation from in-sample to out-of-sample. This is normal.
Efficiency >0.6 indicates genuine edge, not overfitting.

Based on MOA_DESIGN_V2.md specifications.

Author: Claude Code (MOA Phase 0)
Date: 2025-10-10
"""

from datetime import datetime, timedelta
from typing import Dict, List, Callable, Tuple, Optional, Any
import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class WalkForwardWindow:
    """
    Represents a single walk-forward window.
    """
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    optimal_params: Optional[Dict[str, Any]] = None
    is_sharpe: float = 0.0
    oos_sharpe: float = 0.0
    efficiency: float = 0.0
    is_backtest_id: Optional[int] = None
    oos_backtest_id: Optional[int] = None


class WalkForwardOptimizer:
    """
    Perform walk-forward optimization on trading strategies.

    Walk-forward optimization splits historical data into overlapping
    train/test windows, optimizes parameters on training data, then tests
    on out-of-sample data to validate the strategy.
    """

    def __init__(
        self,
        training_months: int = 12,
        testing_months: int = 3,
        step_months: int = 1,
        min_efficiency: float = 0.6
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            training_months: Size of training window (default 12)
            testing_months: Size of testing window (default 3)
            step_months: Step size for rolling window (default 1)
            min_efficiency: Minimum acceptable efficiency (default 0.6)
        """
        self.training_months = training_months
        self.testing_months = testing_months
        self.step_months = step_months
        self.min_efficiency = min_efficiency

        self.windows: List[WalkForwardWindow] = []

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[WalkForwardWindow]:
        """
        Generate walk-forward windows for date range.

        Args:
            start_date: Start of historical data
            end_date: End of historical data

        Returns:
            List of WalkForwardWindow objects
        """
        windows = []
        current_date = start_date

        while True:
            # Calculate window dates
            train_start = current_date
            train_end = train_start + timedelta(days=30 * self.training_months)
            test_start = train_end
            test_end = test_start + timedelta(days=30 * self.testing_months)

            # Check if we've reached the end
            if test_end > end_date:
                break

            # Create window
            window = WalkForwardWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end
            )
            windows.append(window)

            # Move to next window
            current_date += timedelta(days=30 * self.step_months)

        self.windows = windows
        return windows

    def optimize_window(
        self,
        window: WalkForwardWindow,
        optimization_func: Callable[[pd.DataFrame], Dict[str, Any]],
        backtest_func: Callable[[pd.DataFrame, Dict[str, Any]], Dict[str, float]],
        train_data: pd.DataFrame,
        test_data: pd.DataFrame
    ) -> WalkForwardWindow:
        """
        Optimize parameters for a single window.

        Args:
            window: WalkForwardWindow to optimize
            optimization_func: Function that finds optimal parameters
                Takes: train_data (DataFrame)
                Returns: Dict of optimal parameters
            backtest_func: Function that runs backtest with parameters
                Takes: data (DataFrame), parameters (Dict)
                Returns: Dict of metrics including 'sharpe_ratio'
            train_data: Training data for this window
            test_data: Testing data for this window

        Returns:
            Updated WalkForwardWindow with results
        """
        # Step 1: Optimize on training data
        optimal_params = optimization_func(train_data)
        window.optimal_params = optimal_params

        # Step 2: Backtest on training data (in-sample)
        is_results = backtest_func(train_data, optimal_params)
        window.is_sharpe = is_results.get('sharpe_ratio', 0.0)

        # Step 3: Backtest on testing data (out-of-sample)
        oos_results = backtest_func(test_data, optimal_params)
        window.oos_sharpe = oos_results.get('sharpe_ratio', 0.0)

        # Step 4: Calculate efficiency
        if window.is_sharpe > 0:
            window.efficiency = window.oos_sharpe / window.is_sharpe
        else:
            window.efficiency = 0.0

        return window

    def run(
        self,
        data: pd.DataFrame,
        optimization_func: Callable[[pd.DataFrame], Dict[str, Any]],
        backtest_func: Callable[[pd.DataFrame, Dict[str, Any]], Dict[str, float]],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Run complete walk-forward optimization.

        Args:
            data: Historical price/news data with datetime index
            optimization_func: Function to find optimal parameters
            backtest_func: Function to run backtest with parameters
            start_date: Optional start date (uses data.index[0] if None)
            end_date: Optional end date (uses data.index[-1] if None)

        Returns:
            Dict with results:
                - windows: List of WalkForwardWindow objects
                - avg_efficiency: Average efficiency across windows
                - median_efficiency: Median efficiency
                - is_valid: Whether strategy passes validation (efficiency >= min_efficiency)
                - rejection_reason: Reason if rejected
        """
        # Determine date range
        if start_date is None:
            start_date = data.index[0]
        if end_date is None:
            end_date = data.index[-1]

        # Generate windows
        windows = self.generate_windows(start_date, end_date)

        if len(windows) == 0:
            return {
                'windows': [],
                'avg_efficiency': 0.0,
                'median_efficiency': 0.0,
                'is_valid': False,
                'rejection_reason': 'Insufficient data for walk-forward windows'
            }

        # Optimize each window
        for window in windows:
            # Extract data for this window
            train_data = data.loc[window.train_start:window.train_end]
            test_data = data.loc[window.test_start:window.test_end]

            # Skip if insufficient data
            if len(train_data) < 20 or len(test_data) < 5:
                continue

            # Optimize window
            self.optimize_window(
                window,
                optimization_func,
                backtest_func,
                train_data,
                test_data
            )

        # Calculate aggregate statistics
        efficiencies = [w.efficiency for w in windows if w.efficiency > 0]

        if len(efficiencies) == 0:
            return {
                'windows': windows,
                'avg_efficiency': 0.0,
                'median_efficiency': 0.0,
                'is_valid': False,
                'rejection_reason': 'No valid windows produced'
            }

        avg_efficiency = np.mean(efficiencies)
        median_efficiency = np.median(efficiencies)

        # Validate
        is_valid = avg_efficiency >= self.min_efficiency
        rejection_reason = None

        if not is_valid:
            rejection_reason = (
                f"Walk-forward efficiency too low: {avg_efficiency:.2f} < {self.min_efficiency:.2f}. "
                f"This indicates severe overfitting. Expected 30-50% degradation from in-sample, "
                f"but observed {(1 - avg_efficiency) * 100:.1f}% degradation."
            )

        return {
            'windows': windows,
            'avg_efficiency': avg_efficiency,
            'median_efficiency': median_efficiency,
            'min_efficiency': min(efficiencies),
            'max_efficiency': max(efficiencies),
            'num_windows': len(windows),
            'valid_windows': len(efficiencies),
            'is_valid': is_valid,
            'rejection_reason': rejection_reason
        }

    def get_best_parameters(
        self,
        metric: str = 'oos_sharpe'
    ) -> Optional[Dict[str, Any]]:
        """
        Get parameter set with best out-of-sample performance.

        Args:
            metric: Metric to optimize ('oos_sharpe', 'efficiency', etc.)

        Returns:
            Dict of best parameters, or None if no windows
        """
        if not self.windows:
            return None

        if metric == 'oos_sharpe':
            best_window = max(self.windows, key=lambda w: w.oos_sharpe)
        elif metric == 'efficiency':
            best_window = max(self.windows, key=lambda w: w.efficiency)
        elif metric == 'is_sharpe':
            best_window = max(self.windows, key=lambda w: w.is_sharpe)
        else:
            raise ValueError(f"Unknown metric: {metric}")

        return best_window.optimal_params

    def get_robust_parameters(
        self,
        min_windows: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Get parameters that perform well across multiple windows.

        Uses frequency analysis to find parameter values that appear
        in top-performing windows most often.

        Args:
            min_windows: Minimum windows to consider

        Returns:
            Dict of robust parameters, or None if insufficient data
        """
        if len(self.windows) < min_windows:
            return None

        # Get top 50% of windows by OOS Sharpe
        sorted_windows = sorted(
            self.windows,
            key=lambda w: w.oos_sharpe,
            reverse=True
        )
        top_windows = sorted_windows[:len(sorted_windows) // 2]

        if len(top_windows) < min_windows:
            return None

        # Aggregate parameters from top windows
        param_keys = set()
        for window in top_windows:
            if window.optimal_params:
                param_keys.update(window.optimal_params.keys())

        # For each parameter, find most common value
        robust_params = {}
        for key in param_keys:
            values = []
            for window in top_windows:
                if window.optimal_params and key in window.optimal_params:
                    values.append(window.optimal_params[key])

            if values:
                # Use median for numeric values, mode for categorical
                if isinstance(values[0], (int, float)):
                    robust_params[key] = float(np.median(values))
                else:
                    # Mode (most common value)
                    robust_params[key] = max(set(values), key=values.count)

        return robust_params

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert windows to DataFrame for analysis.

        Returns:
            DataFrame with one row per window
        """
        if not self.windows:
            return pd.DataFrame()

        records = []
        for i, window in enumerate(self.windows):
            records.append({
                'window_id': i + 1,
                'train_start': window.train_start,
                'train_end': window.train_end,
                'test_start': window.test_start,
                'test_end': window.test_end,
                'is_sharpe': window.is_sharpe,
                'oos_sharpe': window.oos_sharpe,
                'efficiency': window.efficiency,
                'optimal_params': str(window.optimal_params)
            })

        return pd.DataFrame(records)

    def summary(self) -> str:
        """
        Generate text summary of walk-forward results.

        Returns:
            Formatted string summary
        """
        if not self.windows:
            return "No walk-forward windows generated."

        efficiencies = [w.efficiency for w in self.windows if w.efficiency > 0]

        if not efficiencies:
            return "No valid walk-forward results."

        summary_lines = [
            "Walk-Forward Optimization Summary",
            "=" * 50,
            f"Training Window: {self.training_months} months",
            f"Testing Window: {self.testing_months} months",
            f"Step Size: {self.step_months} month(s)",
            f"Total Windows: {len(self.windows)}",
            f"Valid Windows: {len(efficiencies)}",
            "",
            "Efficiency Statistics:",
            f"  Average: {np.mean(efficiencies):.3f}",
            f"  Median: {np.median(efficiencies):.3f}",
            f"  Min: {np.min(efficiencies):.3f}",
            f"  Max: {np.max(efficiencies):.3f}",
            "",
            f"Validation: {'PASS' if np.mean(efficiencies) >= self.min_efficiency else 'FAIL'}",
            f"  (Minimum efficiency: {self.min_efficiency:.2f})",
            "",
            "Interpretation:",
        ]

        avg_eff = np.mean(efficiencies)
        degradation = (1 - avg_eff) * 100

        if avg_eff >= 0.8:
            summary_lines.append(f"  ✓ Excellent - Only {degradation:.1f}% degradation (< 20%)")
        elif avg_eff >= 0.6:
            summary_lines.append(f"  ✓ Good - {degradation:.1f}% degradation (within 30-50% expected)")
        elif avg_eff >= 0.4:
            summary_lines.append(f"  ⚠ Marginal - {degradation:.1f}% degradation (>40%)")
        else:
            summary_lines.append(f"  ✗ Severe overfitting - {degradation:.1f}% degradation")

        return "\n".join(summary_lines)


def simple_optimization_example(train_data: pd.DataFrame) -> Dict[str, Any]:
    """
    Example optimization function for testing.

    In practice, this would run parameter grid search, genetic algorithms, etc.

    Args:
        train_data: Training data

    Returns:
        Dict of optimal parameters
    """
    # Simple example: just return some fixed parameters
    return {
        'min_score': 0.25,
        'take_profit_pct': 0.20,
        'stop_loss_pct': 0.10
    }


def simple_backtest_example(
    data: pd.DataFrame,
    parameters: Dict[str, Any]
) -> Dict[str, float]:
    """
    Example backtest function for testing.

    In practice, this would run a full backtest with the given parameters.

    Args:
        data: Historical data
        parameters: Strategy parameters

    Returns:
        Dict of performance metrics
    """
    # Simple example: return dummy metrics
    # In real implementation, would run actual backtest
    return {
        'sharpe_ratio': np.random.uniform(0.5, 2.0),
        'total_return': np.random.uniform(-0.1, 0.3),
        'total_trades': len(data) // 10
    }
