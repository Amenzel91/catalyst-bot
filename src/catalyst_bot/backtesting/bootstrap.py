"""
Bootstrap Validation for Trading Strategies

Implements bootstrap resampling to generate confidence intervals and
validate strategy robustness without parametric assumptions.

Key Features:
- 10,000 iterations (configurable)
- 95% confidence intervals
- Simulates execution failures (randomly skip 5-10% of trades)
- Probability of positive returns (target: >70% for deployment)

Based on MOA_DESIGN_V2.md specifications.

Author: Claude Code (MOA Phase 0)
Date: 2025-10-10
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class BootstrapResult:
    """
    Results from bootstrap validation.
    """
    # Return statistics
    prob_positive_return: float
    mean_return: float
    median_return: float
    ci_lower: float
    ci_upper: float

    # Sharpe statistics
    mean_sharpe: float
    median_sharpe: float
    sharpe_ci_lower: float
    sharpe_ci_upper: float

    # Metadata
    n_iterations: int
    confidence_level: float
    min_trades: int
    is_valid: bool
    rejection_reason: Optional[str] = None


class BootstrapValidator:
    """
    Validate trading strategies using bootstrap resampling.

    Bootstrap resampling creates thousands of alternative performance
    scenarios by randomly sampling trades with replacement. This provides
    robust confidence intervals without assuming normal distribution.
    """

    def __init__(
        self,
        n_iterations: int = 10000,
        confidence_level: float = 0.95,
        min_prob_positive: float = 0.70,
        simulate_failures: bool = True,
        failure_rate: Tuple[float, float] = (0.05, 0.10)
    ):
        """
        Initialize bootstrap validator.

        Args:
            n_iterations: Number of bootstrap iterations (default 10,000)
            confidence_level: Confidence level for intervals (default 0.95)
            min_prob_positive: Minimum probability of positive returns (default 0.70)
            simulate_failures: Whether to simulate execution failures (default True)
            failure_rate: Range of failure rates to simulate (default 5-10%)
        """
        self.n_iterations = n_iterations
        self.confidence_level = confidence_level
        self.min_prob_positive = min_prob_positive
        self.simulate_failures = simulate_failures
        self.failure_rate = failure_rate

        # Results storage
        self.bootstrap_returns: List[float] = []
        self.bootstrap_sharpes: List[float] = []

    def validate(
        self,
        trades: pd.DataFrame,
        return_column: str = 'pnl_pct',
        min_trades: int = 30
    ) -> BootstrapResult:
        """
        Perform bootstrap validation on trade results.

        Args:
            trades: DataFrame with trade results
            return_column: Column containing returns (default 'pnl_pct')
            min_trades: Minimum trades required (default 30)

        Returns:
            BootstrapResult with validation metrics
        """
        if len(trades) < min_trades:
            return BootstrapResult(
                prob_positive_return=0.0,
                mean_return=0.0,
                median_return=0.0,
                ci_lower=0.0,
                ci_upper=0.0,
                mean_sharpe=0.0,
                median_sharpe=0.0,
                sharpe_ci_lower=0.0,
                sharpe_ci_upper=0.0,
                n_iterations=0,
                confidence_level=self.confidence_level,
                min_trades=min_trades,
                is_valid=False,
                rejection_reason=f"Insufficient trades: {len(trades)} < {min_trades}"
            )

        # Extract returns
        returns = trades[return_column].values / 100.0  # Convert to decimal

        # Run bootstrap iterations
        self.bootstrap_returns = []
        self.bootstrap_sharpes = []

        np.random.seed(42)  # For reproducibility

        for _ in range(self.n_iterations):
            # Resample with replacement
            sample_returns = np.random.choice(
                returns,
                size=len(returns),
                replace=True
            )

            # Simulate execution failures (randomly skip 5-10% of trades)
            if self.simulate_failures:
                failure_pct = np.random.uniform(
                    self.failure_rate[0],
                    self.failure_rate[1]
                )
                keep_mask = np.random.random(len(sample_returns)) > failure_pct
                sample_returns = sample_returns[keep_mask]

            # Calculate metrics for this bootstrap sample
            if len(sample_returns) > 0:
                total_return = sample_returns.sum()
                self.bootstrap_returns.append(total_return)

                # Calculate Sharpe ratio
                if len(sample_returns) > 1:
                    mean_ret = np.mean(sample_returns)
                    std_ret = np.std(sample_returns, ddof=1)

                    if std_ret > 0:
                        sharpe = (mean_ret / std_ret) * np.sqrt(252)
                        self.bootstrap_sharpes.append(sharpe)
                    else:
                        self.bootstrap_sharpes.append(0.0)

        # Calculate statistics
        prob_positive = sum(r > 0 for r in self.bootstrap_returns) / len(self.bootstrap_returns)

        # Confidence intervals (percentile method)
        alpha = 1 - self.confidence_level
        ci_lower_pct = alpha / 2 * 100
        ci_upper_pct = (1 - alpha / 2) * 100

        return_ci_lower = np.percentile(self.bootstrap_returns, ci_lower_pct)
        return_ci_upper = np.percentile(self.bootstrap_returns, ci_upper_pct)

        sharpe_ci_lower = np.percentile(self.bootstrap_sharpes, ci_lower_pct) if self.bootstrap_sharpes else 0.0
        sharpe_ci_upper = np.percentile(self.bootstrap_sharpes, ci_upper_pct) if self.bootstrap_sharpes else 0.0

        # Validation
        is_valid = prob_positive >= self.min_prob_positive
        rejection_reason = None

        if not is_valid:
            rejection_reason = (
                f"Bootstrap probability of positive return too low: {prob_positive:.1%} < {self.min_prob_positive:.1%}. "
                f"Strategy lacks robust edge across resampled scenarios."
            )

        return BootstrapResult(
            prob_positive_return=prob_positive,
            mean_return=np.mean(self.bootstrap_returns),
            median_return=np.median(self.bootstrap_returns),
            ci_lower=return_ci_lower,
            ci_upper=return_ci_upper,
            mean_sharpe=np.mean(self.bootstrap_sharpes) if self.bootstrap_sharpes else 0.0,
            median_sharpe=np.median(self.bootstrap_sharpes) if self.bootstrap_sharpes else 0.0,
            sharpe_ci_lower=sharpe_ci_lower,
            sharpe_ci_upper=sharpe_ci_upper,
            n_iterations=self.n_iterations,
            confidence_level=self.confidence_level,
            min_trades=min_trades,
            is_valid=is_valid,
            rejection_reason=rejection_reason
        )

    def validate_multiple_metrics(
        self,
        trades: pd.DataFrame,
        metrics_to_bootstrap: List[str] = None,
        min_trades: int = 30
    ) -> Dict[str, any]:
        """
        Bootstrap multiple performance metrics simultaneously.

        Args:
            trades: DataFrame with trade results
            metrics_to_bootstrap: List of metric names to bootstrap (default: standard set)
            min_trades: Minimum trades required

        Returns:
            Dict with bootstrap results for each metric
        """
        if metrics_to_bootstrap is None:
            metrics_to_bootstrap = [
                'total_return',
                'sharpe_ratio',
                'sortino_ratio',
                'max_drawdown',
                'profit_factor',
                'win_rate'
            ]

        if len(trades) < min_trades:
            return {
                'is_valid': False,
                'rejection_reason': f"Insufficient trades: {len(trades)} < {min_trades}",
                'metrics': {}
            }

        from catalyst_bot.backtesting.advanced_metrics import PerformanceMetrics
        pm = PerformanceMetrics()

        # Extract returns and PnL
        returns = trades['pnl_pct'].values / 100.0
        pnl = trades['pnl'].values

        # Storage for bootstrap distributions
        bootstrap_distributions = {metric: [] for metric in metrics_to_bootstrap}

        np.random.seed(42)

        for _ in range(self.n_iterations):
            # Resample with replacement
            sample_indices = np.random.choice(
                len(trades),
                size=len(trades),
                replace=True
            )

            sample_trades = trades.iloc[sample_indices].copy()
            sample_returns = returns[sample_indices]
            sample_pnl = pnl[sample_indices]

            # Simulate execution failures
            if self.simulate_failures:
                failure_pct = np.random.uniform(
                    self.failure_rate[0],
                    self.failure_rate[1]
                )
                keep_mask = np.random.random(len(sample_trades)) > failure_pct
                sample_trades = sample_trades[keep_mask]
                sample_returns = sample_returns[keep_mask]
                sample_pnl = sample_pnl[keep_mask]

            if len(sample_trades) < 2:
                continue

            # Calculate metrics for this sample
            if 'total_return' in metrics_to_bootstrap:
                bootstrap_distributions['total_return'].append(sample_returns.sum())

            if 'sharpe_ratio' in metrics_to_bootstrap:
                sharpe = pm.sharpe_ratio(sample_returns)
                bootstrap_distributions['sharpe_ratio'].append(sharpe)

            if 'sortino_ratio' in metrics_to_bootstrap:
                sortino = pm.sortino_ratio(sample_returns)
                bootstrap_distributions['sortino_ratio'].append(sortino)

            if 'max_drawdown' in metrics_to_bootstrap:
                cumulative = (1 + sample_returns).cumprod()
                running_max = np.maximum.accumulate(cumulative)
                drawdown = (cumulative - running_max) / running_max
                max_dd = abs(drawdown.min())
                bootstrap_distributions['max_drawdown'].append(max_dd)

            if 'profit_factor' in metrics_to_bootstrap:
                pf = pm.profit_factor(sample_pnl)
                bootstrap_distributions['profit_factor'].append(pf)

            if 'win_rate' in metrics_to_bootstrap:
                wr = (sample_returns > 0.05).sum() / len(sample_returns)
                bootstrap_distributions['win_rate'].append(wr)

        # Calculate statistics for each metric
        results = {}
        alpha = 1 - self.confidence_level
        ci_lower_pct = alpha / 2 * 100
        ci_upper_pct = (1 - alpha / 2) * 100

        for metric, distribution in bootstrap_distributions.items():
            if len(distribution) > 0:
                results[metric] = {
                    'mean': np.mean(distribution),
                    'median': np.median(distribution),
                    'std': np.std(distribution),
                    'ci_lower': np.percentile(distribution, ci_lower_pct),
                    'ci_upper': np.percentile(distribution, ci_upper_pct),
                    'prob_positive': sum(v > 0 for v in distribution) / len(distribution)
                }

        return {
            'is_valid': True,
            'n_iterations': self.n_iterations,
            'confidence_level': self.confidence_level,
            'metrics': results
        }

    def plot_distribution(
        self,
        metric: str = 'returns',
        save_path: Optional[str] = None
    ):
        """
        Plot bootstrap distribution (requires matplotlib).

        Args:
            metric: 'returns' or 'sharpe'
            save_path: Optional path to save plot
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not available for plotting")
            return

        if metric == 'returns':
            data = self.bootstrap_returns
            xlabel = 'Total Return'
            title = f'Bootstrap Distribution of Returns ({self.n_iterations:,} iterations)'
        elif metric == 'sharpe':
            data = self.bootstrap_sharpes
            xlabel = 'Sharpe Ratio'
            title = f'Bootstrap Distribution of Sharpe Ratio ({self.n_iterations:,} iterations)'
        else:
            raise ValueError(f"Unknown metric: {metric}")

        if not data:
            print("No bootstrap data available. Run validate() first.")
            return

        plt.figure(figsize=(10, 6))
        plt.hist(data, bins=50, edgecolor='black', alpha=0.7)
        plt.axvline(np.mean(data), color='red', linestyle='--', label=f'Mean: {np.mean(data):.3f}')
        plt.axvline(np.median(data), color='green', linestyle='--', label=f'Median: {np.median(data):.3f}')

        # Confidence intervals
        alpha = 1 - self.confidence_level
        ci_lower = np.percentile(data, alpha / 2 * 100)
        ci_upper = np.percentile(data, (1 - alpha / 2) * 100)

        plt.axvline(ci_lower, color='blue', linestyle=':', label=f'{self.confidence_level:.0%} CI Lower: {ci_lower:.3f}')
        plt.axvline(ci_upper, color='blue', linestyle=':', label=f'{self.confidence_level:.0%} CI Upper: {ci_upper:.3f}')

        plt.xlabel(xlabel)
        plt.ylabel('Frequency')
        plt.title(title)
        plt.legend()
        plt.grid(True, alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")
        else:
            plt.show()

        plt.close()

    def summary(self, result: BootstrapResult) -> str:
        """
        Generate text summary of bootstrap results.

        Args:
            result: BootstrapResult to summarize

        Returns:
            Formatted string summary
        """
        lines = [
            "Bootstrap Validation Summary",
            "=" * 50,
            f"Iterations: {result.n_iterations:,}",
            f"Confidence Level: {result.confidence_level:.0%}",
            f"Minimum Trades: {result.min_trades}",
            "",
            "Return Statistics:",
            f"  Mean: {result.mean_return:.2%}",
            f"  Median: {result.median_return:.2%}",
            f"  {result.confidence_level:.0%} CI: [{result.ci_lower:.2%}, {result.ci_upper:.2%}]",
            f"  Prob(Positive): {result.prob_positive_return:.1%}",
            "",
            "Sharpe Ratio Statistics:",
            f"  Mean: {result.mean_sharpe:.2f}",
            f"  Median: {result.median_sharpe:.2f}",
            f"  {result.confidence_level:.0%} CI: [{result.sharpe_ci_lower:.2f}, {result.sharpe_ci_upper:.2f}]",
            "",
            f"Validation: {'PASS' if result.is_valid else 'FAIL'}",
            f"  (Minimum probability: {self.min_prob_positive:.0%})",
        ]

        if result.rejection_reason:
            lines.append("")
            lines.append(f"Rejection Reason: {result.rejection_reason}")

        lines.extend([
            "",
            "Interpretation:",
        ])

        prob = result.prob_positive_return

        if prob >= 0.80:
            lines.append(f"  [PASS] High confidence - {prob:.0%} of scenarios profitable")
        elif prob >= 0.70:
            lines.append(f"  [PASS] Acceptable - {prob:.0%} of scenarios profitable")
        elif prob >= 0.60:
            lines.append(f"  [WARN] Marginal - {prob:.0%} of scenarios profitable")
        else:
            lines.append(f"  [FAIL] Insufficient robustness - Only {prob:.0%} of scenarios profitable")

        return "\n".join(lines)
