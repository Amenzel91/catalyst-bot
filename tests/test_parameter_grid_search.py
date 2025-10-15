"""
Tests for Parameter Grid Search Optimization
=============================================

Tests for validate_parameter_grid() function and integration with
VectorizedBacktester.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from catalyst_bot.backtesting.validator import (
    validate_parameter_grid,
    _load_data_for_grid_search
)


class TestValidateParameterGrid:
    """Tests for validate_parameter_grid function."""

    def test_empty_param_ranges_raises_error(self):
        """Empty param_ranges should raise ValueError."""
        with pytest.raises(ValueError, match="param_ranges cannot be empty"):
            validate_parameter_grid(
                param_ranges={},
                backtest_days=30
            )

    def test_invalid_backtest_days_raises_error(self):
        """Invalid backtest_days should raise ValueError."""
        with pytest.raises(ValueError, match="backtest_days must be >= 1"):
            validate_parameter_grid(
                param_ranges={'min_score': [0.25, 0.30]},
                backtest_days=0
            )

    def test_grid_search_with_mock_data(self):
        """Test grid search with mock price and signal data."""
        # Create mock data
        dates = pd.date_range(
            start='2024-01-01',
            end='2024-01-31',
            freq='1h'
        )

        # Mock price data (single ticker for simplicity)
        price_data = pd.DataFrame({
            'TEST': np.random.uniform(10, 20, len(dates))
        }, index=dates)

        # Mock signal data (scores between 0-1)
        signal_data = pd.DataFrame({
            'TEST': np.random.uniform(0, 1, len(dates))
        }, index=dates)

        # Run grid search
        results = validate_parameter_grid(
            param_ranges={
                'min_score': [0.20, 0.30],
                'take_profit_pct': [0.15, 0.20]
            },
            backtest_days=30,
            price_data=price_data,
            signal_data=signal_data
        )

        # Verify results structure
        assert 'best_params' in results
        assert 'best_metrics' in results
        assert 'n_combinations' in results
        assert 'execution_time_sec' in results
        assert 'speedup_estimate' in results

        # Verify number of combinations
        assert results['n_combinations'] == 4  # 2 x 2

        # Verify execution time is reasonable
        assert results['execution_time_sec'] > 0
        assert results['execution_time_sec'] < 60  # Should complete in < 60 seconds

    def test_single_parameter_grid(self):
        """Test grid search with single parameter."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={'min_score': [0.20, 0.25, 0.30, 0.35]},
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        assert results['n_combinations'] == 4
        assert 'min_score' in results['best_params']
        assert results['best_params']['min_score'] in [0.20, 0.25, 0.30, 0.35]

    def test_multi_dimensional_grid(self):
        """Test grid search with multiple parameters."""
        dates = pd.date_range(start='2024-01-01', periods=200, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 200)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 200)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={
                'min_score': [0.20, 0.30],
                'take_profit_pct': [0.15, 0.20, 0.25],
                'stop_loss_pct': [0.08, 0.10]
            },
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        # 2 * 3 * 2 = 12 combinations
        assert results['n_combinations'] == 12
        assert 'min_score' in results['best_params']
        assert 'take_profit_pct' in results['best_params']
        assert 'stop_loss_pct' in results['best_params']

    def test_speedup_calculation(self):
        """Test that speedup estimate is calculated correctly."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={
                'min_score': [0.20, 0.25, 0.30],
                'take_profit_pct': [0.15, 0.20]
            },
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        # Speedup should be positive and reasonable
        assert results['speedup_estimate'] > 0
        # With 6 combinations, speedup should be at least 2x
        assert results['speedup_estimate'] >= 2.0

    def test_no_data_returns_warning(self):
        """Test handling when no data is available."""
        results = validate_parameter_grid(
            param_ranges={'min_score': [0.25, 0.30]},
            backtest_days=30,
            price_data=None,
            signal_data=None
        )

        # Should return empty results with warning
        assert results['n_combinations'] == 0
        assert 'warning' in results or 'error' in results
        assert results['best_params'] == {}


class TestLoadDataForGridSearch:
    """Tests for _load_data_for_grid_search helper function."""

    def test_load_with_missing_file(self):
        """Test loading when events.jsonl doesn't exist."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        price_data, signal_data = _load_data_for_grid_search(start, end)

        # Should return None, None when file doesn't exist
        # (Current implementation is a placeholder)
        assert price_data is None
        assert signal_data is None

    def test_load_with_empty_date_range(self):
        """Test loading with date range that has no events."""
        # Use a far future date range with no events
        start = datetime(2030, 1, 1, tzinfo=timezone.utc)
        end = datetime(2030, 1, 31, tzinfo=timezone.utc)

        price_data, signal_data = _load_data_for_grid_search(start, end)

        # Should return None when no events in range
        assert price_data is None
        assert signal_data is None


class TestIntegrationWithVectorizedBacktester:
    """Integration tests with VectorizedBacktester."""

    def test_vectorized_backtester_import(self):
        """Test that VectorizedBacktester can be imported."""
        try:
            from catalyst_bot.backtesting.vectorized_backtest import VectorizedBacktester
            assert VectorizedBacktester is not None
        except ImportError:
            pytest.skip("VectorBT not installed - skipping integration test")

    def test_grid_search_uses_vectorized_backtester(self):
        """Test that grid search correctly uses VectorizedBacktester."""
        pytest.skip("Requires VectorBT installation and proper data setup")

        # This would be a full integration test:
        # 1. Load real data
        # 2. Run grid search
        # 3. Verify results match expected format
        # 4. Compare with sequential backtesting for accuracy


class TestParameterValidation:
    """Tests for parameter validation and edge cases."""

    def test_valid_parameter_names(self):
        """Test that valid parameter names are accepted."""
        valid_params = {
            'min_score': [0.25, 0.30],
            'min_sentiment': [0.0, 0.1],
            'take_profit_pct': [0.15, 0.20],
            'stop_loss_pct': [0.08, 0.10],
            'max_hold_hours': [12, 24],
            'position_size_pct': [0.05, 0.10]
        }

        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        # Should not raise errors
        results = validate_parameter_grid(
            param_ranges=valid_params,
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        assert results is not None

    def test_parameter_ranges_with_single_value(self):
        """Test behavior with single value in parameter range."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={'min_score': [0.25]},  # Single value
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        assert results['n_combinations'] == 1
        assert results['best_params']['min_score'] == 0.25


class TestResultsFormat:
    """Tests for results format and structure."""

    def test_results_contain_required_fields(self):
        """Test that results contain all required fields."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={'min_score': [0.25, 0.30]},
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        required_fields = [
            'best_params',
            'best_metrics',
            'all_results',
            'n_combinations',
            'execution_time_sec',
            'speedup_estimate'
        ]

        for field in required_fields:
            assert field in results, f"Missing required field: {field}"

    def test_best_metrics_structure(self):
        """Test that best_metrics has expected structure."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={'min_score': [0.25, 0.30]},
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        best_metrics = results['best_metrics']
        expected_metrics = ['sharpe_ratio', 'sortino_ratio', 'total_trades']

        for metric in expected_metrics:
            assert metric in best_metrics, f"Missing expected metric: {metric}"

    def test_all_results_is_dataframe(self):
        """Test that all_results is a DataFrame with proper structure."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        price_data = pd.DataFrame({'TEST': np.random.uniform(10, 20, 100)}, index=dates)
        signal_data = pd.DataFrame({'TEST': np.random.uniform(0, 1, 100)}, index=dates)

        results = validate_parameter_grid(
            param_ranges={
                'min_score': [0.25, 0.30],
                'take_profit_pct': [0.15, 0.20]
            },
            backtest_days=7,
            price_data=price_data,
            signal_data=signal_data
        )

        all_results = results['all_results']

        if all_results is not None:
            assert isinstance(all_results, pd.DataFrame)
            assert len(all_results) == results['n_combinations']
            assert 'sharpe_ratio' in all_results.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
