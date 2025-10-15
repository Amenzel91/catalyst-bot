"""
Advanced Performance Metrics for Backtesting

This module implements institutional-grade performance metrics for evaluating
trading strategies, as specified in MOA_DESIGN_V2.md.

Key Metrics:
- F1 Score: Harmonic mean of precision and recall (target: 0.4-0.6 for penny stocks)
- Sharpe Ratio: Risk-adjusted return (traditional metric)
- Sortino Ratio: Only penalizes downside volatility (target: >1.5-2.0)
- Calmar Ratio: Annual Return / Max Drawdown (target: >2.0)
- Omega Ratio: Probability-weighted ratio of gains vs losses (target: >2.0)
- Expectancy: Expected value per trade (target: >0.5)
- Profit Factor: Gross profits / Gross losses (target: >2.0)
- Information Coefficient: Spearman correlation of signals vs returns (target: >0.05)
- ROC-AUC: Receiver Operating Characteristic area under curve (target: >0.7)

Author: Claude Code (MOA Phase 0)
Date: 2025-10-10
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from scipy import stats
from sklearn.metrics import roc_auc_score, roc_curve


class PerformanceMetrics:
    """
    Calculate advanced performance metrics for trading strategies.

    All metrics handle edge cases (zero trades, zero variance, etc.) gracefully.
    """

    def __init__(self, trades: Optional[pd.DataFrame] = None):
        """
        Initialize with optional trades DataFrame.

        Args:
            trades: DataFrame with columns:
                - entry_time: Trade entry timestamp
                - exit_time: Trade exit timestamp
                - pnl: Profit/loss in currency units
                - pnl_pct: Profit/loss as percentage
                - ticker: Symbol traded
                - signal_score: Original signal strength (0-1)
                - outcome: 1 (win), -1 (loss), 0 (neutral)
        """
        self.trades = trades

    def f1_score(
        self,
        wins: int,
        losses: int,
        neutrals: int = 0,
        threshold_pct: float = 5.0
    ) -> float:
        """
        Calculate F1 score for trading signals.

        F1 = 2 * (precision * recall) / (precision + recall)

        Precision = TP / (TP + FP) = wins / (wins + losses)
        Recall = TP / (TP + FN) = wins / total_signals

        For penny stocks, expect F1 between 0.4-0.6. If F1 > 0.7, suspect overfitting.

        Args:
            wins: Number of winning trades (>threshold_pct)
            losses: Number of losing trades (<-threshold_pct)
            neutrals: Number of neutral trades (within threshold)
            threshold_pct: Threshold for win/loss classification (default 5%)

        Returns:
            F1 score between 0 and 1
        """
        total = wins + losses + neutrals

        if total == 0:
            return 0.0

        # Precision: wins / trades taken
        precision = wins / (wins + losses) if (wins + losses) > 0 else 0.0

        # Recall: wins / total signals
        recall = wins / total

        if precision + recall == 0:
            return 0.0

        f1 = 2 * (precision * recall) / (precision + recall)
        return f1

    def sharpe_ratio(
        self,
        returns: np.ndarray,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate Sharpe Ratio.

        Sharpe = (Mean Return - Risk-Free Rate) / Std Dev of Returns

        Args:
            returns: Array of period returns
            risk_free_rate: Annual risk-free rate (default 0.0)
            periods_per_year: Number of trading periods per year (252 for daily)

        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) == 0:
            return 0.0

        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)

        if std_return == 0:
            return 0.0

        sharpe = (mean_return - risk_free_rate / periods_per_year) / std_return
        return sharpe * np.sqrt(periods_per_year)

    def sortino_ratio(
        self,
        returns: np.ndarray,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
        target_return: float = 0.0
    ) -> float:
        """
        Calculate Sortino Ratio (only penalizes downside volatility).

        Sortino = (Mean Return - Target) / Downside Deviation

        Target for deployment: >1.5-2.0

        Args:
            returns: Array of period returns
            risk_free_rate: Annual risk-free rate
            periods_per_year: Number of trading periods per year
            target_return: Minimum acceptable return (default 0)

        Returns:
            Annualized Sortino ratio
        """
        if len(returns) == 0:
            return 0.0

        mean_return = np.mean(returns)

        # Downside deviation: only consider returns below target
        downside_returns = returns[returns < target_return]

        if len(downside_returns) == 0:
            # No downside risk - infinite Sortino, return large number
            return 999.0

        downside_std = np.std(downside_returns, ddof=1)

        if downside_std == 0:
            return 0.0

        sortino = (mean_return - risk_free_rate / periods_per_year) / downside_std
        return sortino * np.sqrt(periods_per_year)

    def calmar_ratio(
        self,
        returns: np.ndarray,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate Calmar Ratio.

        Calmar = Annualized Return / Maximum Drawdown

        Target for deployment: >2.0

        Args:
            returns: Array of period returns
            periods_per_year: Number of trading periods per year

        Returns:
            Calmar ratio
        """
        if len(returns) == 0:
            return 0.0

        # Calculate cumulative returns
        cumulative = (1 + returns).cumprod()

        # Calculate maximum drawdown
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdown.min())

        if max_drawdown == 0:
            return 0.0

        # Annualized return
        total_return = cumulative[-1] - 1
        annualized_return = (1 + total_return) ** (periods_per_year / len(returns)) - 1

        calmar = annualized_return / max_drawdown
        return calmar

    def omega_ratio(
        self,
        returns: np.ndarray,
        threshold: float = 0.0
    ) -> float:
        """
        Calculate Omega Ratio (probability-weighted gains vs losses).

        Omega = Sum(returns > threshold) / Sum(|returns < threshold|)

        Gold standard for non-normal return distributions.
        Target for deployment: >2.0

        Args:
            returns: Array of period returns
            threshold: Minimum acceptable return (default 0)

        Returns:
            Omega ratio
        """
        if len(returns) == 0:
            return 0.0

        gains = returns[returns > threshold]
        losses = returns[returns < threshold]

        if len(losses) == 0:
            # No losses - infinite omega
            return 999.0

        sum_gains = np.sum(gains - threshold)
        sum_losses = abs(np.sum(losses - threshold))

        if sum_losses == 0:
            return 0.0

        omega = sum_gains / sum_losses
        return omega

    def expectancy(
        self,
        pnl_values: np.ndarray
    ) -> float:
        """
        Calculate expectancy (expected profit per trade).

        Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)

        This is the only metric that matters for profitability.
        Target for deployment: >0.5 (accounting for transaction costs)

        Args:
            pnl_values: Array of profit/loss values in currency units

        Returns:
            Expected profit per trade
        """
        if len(pnl_values) == 0:
            return 0.0

        wins = pnl_values[pnl_values > 0]
        losses = pnl_values[pnl_values < 0]

        total_trades = len(pnl_values)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
        loss_rate = len(losses) / total_trades if total_trades > 0 else 0.0

        avg_win = np.mean(wins) if len(wins) > 0 else 0.0
        avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0.0

        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        return expectancy

    def profit_factor(
        self,
        pnl_values: np.ndarray
    ) -> float:
        """
        Calculate Profit Factor.

        Profit Factor = Gross Profits / Gross Losses

        Must be >2.0 to overcome 6-8% transaction costs for penny stocks.

        Args:
            pnl_values: Array of profit/loss values in currency units

        Returns:
            Profit factor (>1.0 means profitable)
        """
        if len(pnl_values) == 0:
            return 0.0

        wins = pnl_values[pnl_values > 0]
        losses = pnl_values[pnl_values < 0]

        gross_profit = np.sum(wins) if len(wins) > 0 else 0.0
        gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0.0

        if gross_loss == 0:
            return 999.0 if gross_profit > 0 else 0.0

        profit_factor = gross_profit / gross_loss
        return profit_factor

    def information_coefficient(
        self,
        signals: np.ndarray,
        returns: np.ndarray
    ) -> float:
        """
        Calculate Information Coefficient (IC).

        IC = Spearman correlation between signal strength and forward returns

        Measures if higher confidence signals actually perform better.
        Target for deployment: >0.05

        Args:
            signals: Array of signal scores (0-1)
            returns: Array of corresponding forward returns

        Returns:
            Spearman correlation coefficient (-1 to 1)
        """
        if len(signals) != len(returns):
            raise ValueError("Signals and returns must have same length")

        if len(signals) < 3:
            return 0.0

        # Remove NaN values
        mask = ~(np.isnan(signals) | np.isnan(returns))
        signals_clean = signals[mask]
        returns_clean = returns[mask]

        if len(signals_clean) < 3:
            return 0.0

        # Spearman correlation (rank-based, robust to outliers)
        ic, p_value = stats.spearmanr(signals_clean, returns_clean)

        # Return 0 if not statistically significant
        if p_value > 0.05:
            return 0.0

        return ic

    def roc_auc(
        self,
        signals: np.ndarray,
        outcomes: np.ndarray
    ) -> Dict[str, float]:
        """
        Calculate ROC-AUC (Receiver Operating Characteristic).

        Measures signal quality independent of threshold choice.
        Target for deployment: >0.7

        Args:
            signals: Array of signal scores (0-1)
            outcomes: Array of binary outcomes (1=win, 0=loss)

        Returns:
            Dict with 'auc', 'fpr', 'tpr', 'thresholds'
        """
        if len(signals) != len(outcomes):
            raise ValueError("Signals and outcomes must have same length")

        if len(signals) < 10:
            return {'auc': 0.0, 'fpr': [], 'tpr': [], 'thresholds': []}

        # Remove NaN values
        mask = ~(np.isnan(signals) | np.isnan(outcomes))
        signals_clean = signals[mask]
        outcomes_clean = outcomes[mask]

        if len(signals_clean) < 10:
            return {'auc': 0.0, 'fpr': [], 'tpr': [], 'thresholds': []}

        # Ensure outcomes are binary
        outcomes_binary = (outcomes_clean > 0).astype(int)

        try:
            auc = roc_auc_score(outcomes_binary, signals_clean)
            fpr, tpr, thresholds = roc_curve(outcomes_binary, signals_clean)

            return {
                'auc': auc,
                'fpr': fpr.tolist(),
                'tpr': tpr.tolist(),
                'thresholds': thresholds.tolist()
            }
        except ValueError:
            # All outcomes are same class
            return {'auc': 0.0, 'fpr': [], 'tpr': [], 'thresholds': []}

    def calculate_all(
        self,
        trades_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, float]:
        """
        Calculate all performance metrics at once.

        Args:
            trades_df: DataFrame with trade data (uses self.trades if not provided)

        Returns:
            Dict with all metrics
        """
        if trades_df is None:
            trades_df = self.trades

        if trades_df is None or len(trades_df) == 0:
            return {
                'f1_score': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'omega_ratio': 0.0,
                'expectancy': 0.0,
                'profit_factor': 0.0,
                'information_coefficient': 0.0,
                'roc_auc': 0.0,
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'max_drawdown': 0.0
            }

        # Extract data
        returns = trades_df['pnl_pct'].values / 100.0  # Convert to decimal
        pnl = trades_df['pnl'].values

        # Calculate wins/losses/neutrals
        wins = (returns > 0.05).sum()  # >5% threshold
        losses = (returns < -0.05).sum()  # <-5% threshold
        neutrals = ((returns >= -0.05) & (returns <= 0.05)).sum()

        # Calculate metrics
        metrics = {
            'f1_score': self.f1_score(wins, losses, neutrals),
            'sharpe_ratio': self.sharpe_ratio(returns),
            'sortino_ratio': self.sortino_ratio(returns),
            'calmar_ratio': self.calmar_ratio(returns),
            'omega_ratio': self.omega_ratio(returns),
            'expectancy': self.expectancy(pnl),
            'profit_factor': self.profit_factor(pnl),
            'total_trades': len(trades_df),
            'win_rate': wins / len(trades_df),
            'avg_win': pnl[pnl > 0].mean() if (pnl > 0).any() else 0.0,
            'avg_loss': pnl[pnl < 0].mean() if (pnl < 0).any() else 0.0,
        }

        # Calculate max drawdown
        cumulative = (1 + returns).cumprod()
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        metrics['max_drawdown'] = abs(drawdown.min())

        # Information Coefficient (if signal scores available)
        if 'signal_score' in trades_df.columns:
            signals = trades_df['signal_score'].values
            metrics['information_coefficient'] = self.information_coefficient(signals, returns)

            # ROC-AUC
            outcomes = (returns > 0.05).astype(int)  # Binary: win or not
            roc_result = self.roc_auc(signals, outcomes)
            metrics['roc_auc'] = roc_result['auc']
        else:
            metrics['information_coefficient'] = 0.0
            metrics['roc_auc'] = 0.0

        return metrics

    def deployment_ready(
        self,
        metrics: Dict[str, float],
        min_trades: int = 385
    ) -> Tuple[bool, List[str]]:
        """
        Check if strategy meets deployment criteria from MOA_DESIGN_V2.md.

        Deployment Criteria:
        - Minimum 385 trades (95% confidence)
        - F1 score: 0.4-0.65 (not too high = overfit)
        - Sortino ratio: >1.5
        - Calmar ratio: >2.0
        - Omega ratio: >2.0
        - Profit factor: >2.0 (to overcome transaction costs)
        - Expectancy: >0.5
        - ROC-AUC: >0.7

        Args:
            metrics: Dict of calculated metrics
            min_trades: Minimum trades required (default 385 for 95% confidence)

        Returns:
            Tuple of (is_ready: bool, issues: List[str])
        """
        issues = []

        # Check minimum trades
        if metrics['total_trades'] < min_trades:
            issues.append(f"Insufficient trades: {metrics['total_trades']} < {min_trades}")

        # Check F1 score (not too low, not too high)
        if metrics['f1_score'] < 0.4:
            issues.append(f"F1 score too low: {metrics['f1_score']:.3f} < 0.40")
        elif metrics['f1_score'] > 0.7:
            issues.append(f"F1 score suspiciously high (overfit?): {metrics['f1_score']:.3f} > 0.70")

        # Check Sortino ratio
        if metrics['sortino_ratio'] < 1.5:
            issues.append(f"Sortino ratio too low: {metrics['sortino_ratio']:.2f} < 1.5")

        # Check Calmar ratio
        if metrics['calmar_ratio'] < 2.0:
            issues.append(f"Calmar ratio too low: {metrics['calmar_ratio']:.2f} < 2.0")

        # Check Omega ratio
        if metrics['omega_ratio'] < 2.0:
            issues.append(f"Omega ratio too low: {metrics['omega_ratio']:.2f} < 2.0")

        # Check Profit Factor
        if metrics['profit_factor'] < 2.0:
            issues.append(f"Profit factor too low: {metrics['profit_factor']:.2f} < 2.0")

        # Check Expectancy
        if metrics['expectancy'] < 0.5:
            issues.append(f"Expectancy too low: ${metrics['expectancy']:.2f} < $0.50")

        # Check ROC-AUC
        if metrics['roc_auc'] > 0 and metrics['roc_auc'] < 0.7:
            issues.append(f"ROC-AUC too low: {metrics['roc_auc']:.3f} < 0.70")

        is_ready = len(issues) == 0
        return is_ready, issues
