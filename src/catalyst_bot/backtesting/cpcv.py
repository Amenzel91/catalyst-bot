"""
Combinatorial Purged Cross-Validation (CPCV)

Advanced cross-validation technique for time-series backtesting that addresses:
- Information leakage from overlapping samples
- Look-ahead bias from sequential dependency
- Sample size reduction from traditional embargo methods

Key Features:
- Purging: Remove training samples that overlap with test period
- Embargoing: Add buffer period to prevent information leakage
- Combinatorial: Test all combinations of train/test splits

Based on "Advances in Financial Machine Learning" by Marcos Lopez de Prado
and MOA_DESIGN_V2.md specifications.

Author: Claude Code (MOA Phase 0)
Date: 2025-10-10
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Callable, Optional, Any
from itertools import combinations
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CPCVResult:
    """
    Results from CPCV validation.
    """
    # Performance statistics
    mean_score: float
    median_score: float
    std_score: float
    min_score: float
    max_score: float

    # Individual fold results
    fold_scores: List[float]
    n_folds: int
    n_combinations: int

    # Validation
    is_valid: bool
    rejection_reason: Optional[str] = None


class CombinatorialPurgedCV:
    """
    Combinatorial Purged Cross-Validation for time-series backtesting.

    Prevents information leakage by:
    1. Purging overlapping training samples
    2. Adding embargo period between train and test
    3. Testing all combinations of folds
    """

    def __init__(
        self,
        n_folds: int = 5,
        embargo_pct: float = 0.01,
        purge_method: str = 'time_based',
        min_fold_size: int = 20
    ):
        """
        Initialize CPCV validator.

        Args:
            n_folds: Number of folds (default 5)
            embargo_pct: Embargo period as percentage of samples (default 1%)
            purge_method: 'time_based' or 'sample_based'
            min_fold_size: Minimum samples per fold
        """
        self.n_folds = n_folds
        self.embargo_pct = embargo_pct
        self.purge_method = purge_method
        self.min_fold_size = min_fold_size

    def _get_embargo_times(
        self,
        times: pd.DatetimeIndex,
        test_indices: np.ndarray
    ) -> Tuple[datetime, datetime]:
        """
        Calculate embargo period around test set.

        Args:
            times: DatetimeIndex of samples
            test_indices: Indices of test samples

        Returns:
            Tuple of (embargo_start, embargo_end)
        """
        test_times = times[test_indices]
        test_start = test_times.min()
        test_end = test_times.max()

        # Calculate embargo duration
        total_duration = times.max() - times.min()
        embargo_duration = total_duration * self.embargo_pct

        # Embargo period: before test and after test
        embargo_start = test_start - embargo_duration
        embargo_end = test_end + embargo_duration

        return embargo_start, embargo_end

    def _purge_training_set(
        self,
        times: pd.DatetimeIndex,
        train_indices: np.ndarray,
        test_indices: np.ndarray
    ) -> np.ndarray:
        """
        Remove training samples that overlap with test period or embargo.

        Args:
            times: DatetimeIndex of samples
            train_indices: Indices of training samples
            test_indices: Indices of test samples

        Returns:
            Purged training indices
        """
        # Get embargo period
        embargo_start, embargo_end = self._get_embargo_times(times, test_indices)

        # Remove training samples within embargo period
        train_times = times[train_indices]
        mask = (train_times < embargo_start) | (train_times > embargo_end)

        purged_train_indices = train_indices[mask]

        return purged_train_indices

    def get_train_test_splits(
        self,
        data: pd.DataFrame,
        n_test_folds: int = 1
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate all combinations of train/test splits with purging.

        Args:
            data: DataFrame with DatetimeIndex
            n_test_folds: Number of folds to use for testing (default 1)

        Returns:
            List of (train_indices, test_indices) tuples
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data must have DatetimeIndex")

        # Split data into k folds
        n_samples = len(data)
        fold_size = n_samples // self.n_folds

        if fold_size < self.min_fold_size:
            raise ValueError(
                f"Fold size {fold_size} too small. "
                f"Need at least {self.min_fold_size} samples per fold."
            )

        # Create fold indices
        fold_indices = []
        for i in range(self.n_folds):
            start = i * fold_size
            end = start + fold_size if i < self.n_folds - 1 else n_samples
            fold_indices.append(np.arange(start, end))

        # Generate all combinations of folds for testing
        test_fold_combinations = list(combinations(range(self.n_folds), n_test_folds))

        splits = []

        for test_fold_nums in test_fold_combinations:
            # Get test indices
            test_indices = np.concatenate([fold_indices[i] for i in test_fold_nums])

            # Get training indices (all other folds)
            train_fold_nums = [i for i in range(self.n_folds) if i not in test_fold_nums]
            train_indices = np.concatenate([fold_indices[i] for i in train_fold_nums])

            # Purge training set
            purged_train_indices = self._purge_training_set(
                data.index,
                train_indices,
                test_indices
            )

            # Skip if purged training set too small
            if len(purged_train_indices) < self.min_fold_size:
                continue

            splits.append((purged_train_indices, test_indices))

        return splits

    def validate(
        self,
        data: pd.DataFrame,
        backtest_func: Callable[[pd.DataFrame, pd.DataFrame], float],
        n_test_folds: int = 1,
        min_score: Optional[float] = None
    ) -> CPCVResult:
        """
        Perform CPCV validation.

        Args:
            data: Historical data with DatetimeIndex
            backtest_func: Function that takes (train_data, test_data) and returns score
            n_test_folds: Number of folds to use for testing
            min_score: Minimum acceptable score (optional)

        Returns:
            CPCVResult with validation metrics
        """
        # Get train/test splits
        splits = self.get_train_test_splits(data, n_test_folds)

        if len(splits) == 0:
            return CPCVResult(
                mean_score=0.0,
                median_score=0.0,
                std_score=0.0,
                min_score=0.0,
                max_score=0.0,
                fold_scores=[],
                n_folds=self.n_folds,
                n_combinations=0,
                is_valid=False,
                rejection_reason="No valid train/test splits generated"
            )

        # Run backtest on each split
        scores = []

        for train_indices, test_indices in splits:
            train_data = data.iloc[train_indices]
            test_data = data.iloc[test_indices]

            # Run backtest
            score = backtest_func(train_data, test_data)
            scores.append(score)

        # Calculate statistics
        mean_score = np.mean(scores)
        median_score = np.median(scores)
        std_score = np.std(scores, ddof=1) if len(scores) > 1 else 0.0
        min_score_val = np.min(scores)
        max_score_val = np.max(scores)

        # Validation
        is_valid = True
        rejection_reason = None

        if min_score is not None and mean_score < min_score:
            is_valid = False
            rejection_reason = (
                f"Mean CPCV score too low: {mean_score:.3f} < {min_score:.3f}"
            )

        # Check for high variance (unstable strategy)
        if std_score > abs(mean_score):
            is_valid = False
            rejection_reason = (
                f"High variance across folds (std={std_score:.3f}, mean={mean_score:.3f}). "
                f"Strategy performance is unstable."
            )

        return CPCVResult(
            mean_score=mean_score,
            median_score=median_score,
            std_score=std_score,
            min_score=min_score_val,
            max_score=max_score_val,
            fold_scores=scores,
            n_folds=self.n_folds,
            n_combinations=len(splits),
            is_valid=is_valid,
            rejection_reason=rejection_reason
        )

    def validate_parameters(
        self,
        data: pd.DataFrame,
        parameter_grid: Dict[str, List[Any]],
        backtest_func: Callable[[pd.DataFrame, pd.DataFrame, Dict], float],
        n_test_folds: int = 1
    ) -> Dict[str, Any]:
        """
        Find best parameters using CPCV.

        Args:
            data: Historical data
            parameter_grid: Dict of parameter names to lists of values
            backtest_func: Function(train_data, test_data, params) -> score
            n_test_folds: Number of folds for testing

        Returns:
            Dict with best parameters and scores
        """
        # Generate parameter combinations
        import itertools

        param_names = list(parameter_grid.keys())
        param_values = list(parameter_grid.values())
        param_combinations = list(itertools.product(*param_values))

        # Get train/test splits once
        splits = self.get_train_test_splits(data, n_test_folds)

        if len(splits) == 0:
            return {
                'best_params': None,
                'best_score': 0.0,
                'is_valid': False,
                'rejection_reason': 'No valid splits'
            }

        # Test each parameter combination
        results = []

        for param_vals in param_combinations:
            params = dict(zip(param_names, param_vals))

            # Test on all splits
            scores = []
            for train_indices, test_indices in splits:
                train_data = data.iloc[train_indices]
                test_data = data.iloc[test_indices]

                score = backtest_func(train_data, test_data, params)
                scores.append(score)

            # Store results
            results.append({
                'params': params,
                'mean_score': np.mean(scores),
                'median_score': np.median(scores),
                'std_score': np.std(scores, ddof=1) if len(scores) > 1 else 0.0,
                'min_score': np.min(scores),
                'max_score': np.max(scores)
            })

        # Find best parameters (highest mean score)
        best_result = max(results, key=lambda x: x['mean_score'])

        return {
            'best_params': best_result['params'],
            'best_score': best_result['mean_score'],
            'best_std': best_result['std_score'],
            'all_results': results,
            'is_valid': True
        }

    def summary(self, result: CPCVResult) -> str:
        """
        Generate text summary of CPCV results.

        Args:
            result: CPCVResult to summarize

        Returns:
            Formatted string summary
        """
        lines = [
            "Combinatorial Purged Cross-Validation Summary",
            "=" * 50,
            f"Number of Folds: {result.n_folds}",
            f"Number of Combinations: {result.n_combinations}",
            f"Embargo Period: {self.embargo_pct:.1%}",
            "",
            "Score Statistics:",
            f"  Mean: {result.mean_score:.3f}",
            f"  Median: {result.median_score:.3f}",
            f"  Std Dev: {result.std_score:.3f}",
            f"  Min: {result.min_score:.3f}",
            f"  Max: {result.max_score:.3f}",
            "",
            f"Validation: {'PASS' if result.is_valid else 'FAIL'}",
        ]

        if result.rejection_reason:
            lines.append(f"  Rejection: {result.rejection_reason}")

        lines.extend([
            "",
            "Interpretation:",
        ])

        # Calculate coefficient of variation
        if result.mean_score != 0:
            cv = result.std_score / abs(result.mean_score)
        else:
            cv = float('inf')

        if cv < 0.2:
            lines.append("  ✓ Stable - Low variance across folds (CV < 0.2)")
        elif cv < 0.5:
            lines.append("  ⚠ Moderate variance (0.2 < CV < 0.5)")
        else:
            lines.append("  ✗ High variance - Strategy performance is unstable")

        # Score quality
        if result.mean_score > 1.0:
            lines.append("  ✓ Good mean score (>1.0)")
        elif result.mean_score > 0.5:
            lines.append("  ⚠ Marginal mean score (0.5-1.0)")
        else:
            lines.append("  ✗ Low mean score (<0.5)")

        return "\n".join(lines)


def example_cpcv_backtest(
    train_data: pd.DataFrame,
    test_data: pd.DataFrame,
    params: Optional[Dict] = None
) -> float:
    """
    Example backtest function for CPCV testing.

    In practice, this would run a full backtest with the given parameters.

    Args:
        train_data: Training data
        test_data: Testing data
        params: Optional strategy parameters

    Returns:
        Sharpe ratio or other performance metric
    """
    # Simple example: return random score
    # In real implementation, would run actual backtest
    return np.random.uniform(0.5, 2.0)
