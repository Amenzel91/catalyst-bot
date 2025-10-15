"""
Test Suite for Robust Statistics in Backtesting Validator
==========================================================

Tests the robust statistical methods (winsorize, trimmed_mean, MAD, robust_zscore)
that are CRITICAL for valid penny stock backtesting results.

These tests verify that outliers are handled correctly and statistics remain
stable even with extreme values (500%+ gains, -90% losses).
"""

import numpy as np
import pytest
from scipy import stats as scipy_stats

from catalyst_bot.backtesting.validator import (
    median_absolute_deviation,
    robust_zscore,
    trimmed_mean,
    winsorize,
)


class TestWinsorize:
    """Test winsorization for outlier handling."""

    def test_winsorize_basic(self):
        """Test basic winsorization at 1st/99th percentile."""
        # Data with extreme outliers
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])  # 100 is outlier

        # Winsorize at 1st/99th percentile
        result = winsorize(data, limits=(0.10, 0.10))

        # The outlier (100) should be clipped to a lower value
        assert result[-1] < 100, "Outlier should be clipped"
        assert result[-1] > 0, "Clipped value should be positive"

        # Non-outliers should be unchanged
        assert np.allclose(result[1:-1], data[1:-1]), "Middle values unchanged"

    def test_winsorize_penny_stock_returns(self):
        """Test winsorization with realistic penny stock returns."""
        # Realistic penny stock returns: need larger sample for winsorization
        np.random.seed(42)
        returns = np.random.normal(0.04, 0.10, 100)  # 100 trades

        # Add extreme outliers
        returns[0] = 5.0   # 500% gain
        returns[1] = -0.85  # 85% loss
        returns[2] = 3.5   # 350% gain

        # Original mean heavily skewed
        original_mean = np.mean(returns)
        assert original_mean > 0.08, "Original mean inflated by outlier"

        # Winsorize at 1st/99th percentile
        winsorized = winsorize(returns, limits=(0.01, 0.01))
        winsorized_mean = np.mean(winsorized)

        # Winsorized mean should be lower and more realistic
        assert winsorized_mean < original_mean, "Winsorized mean should be lower"
        assert 0.03 < winsorized_mean < 0.12, "Winsorized mean in realistic range"

    def test_winsorize_extreme_outliers(self):
        """Test winsorization handles multiple extreme outliers."""
        # 2-year backtest simulation: 500 trades with 5 extreme outliers
        np.random.seed(42)
        returns = np.random.normal(0.03, 0.12, 500)

        # Add extreme outliers (pump-and-dumps)
        returns[0] = 3.5  # 350% gain
        returns[1] = -0.85  # 85% loss
        returns[2] = 2.8  # 280% gain
        returns[3] = -0.92  # 92% loss
        returns[4] = 4.2  # 420% gain

        # Original statistics
        original_mean = np.mean(returns)
        original_std = np.std(returns, ddof=1)

        # Winsorize at 1st/99th percentile (removes top/bottom 1%)
        winsorized = winsorize(returns, limits=(0.01, 0.01))
        winsorized_mean = np.mean(winsorized)
        winsorized_std = np.std(winsorized, ddof=1)

        # Winsorized should be more stable
        assert winsorized_mean < original_mean, "Outliers inflated mean"
        assert winsorized_std < original_std, "Outliers inflated std dev"

        # Check that winsorized stats are reasonable
        assert 0.02 < winsorized_mean < 0.06, f"Mean should be realistic: {winsorized_mean}"
        assert 0.10 < winsorized_std < 0.20, f"Std dev should be realistic: {winsorized_std}"

    def test_winsorize_empty_array(self):
        """Test winsorization handles empty arrays gracefully."""
        data = np.array([])
        result = winsorize(data)
        assert len(result) == 0, "Empty array should return empty array"

    def test_winsorize_preserves_shape(self):
        """Test winsorization preserves array shape and length."""
        data = np.random.normal(0, 1, 100)
        result = winsorize(data)
        assert result.shape == data.shape, "Shape should be preserved"
        assert len(result) == len(data), "Length should be preserved"


class TestTrimmedMean:
    """Test trimmed mean for robust central tendency."""

    def test_trimmed_mean_basic(self):
        """Test basic trimmed mean calculation."""
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])

        # 10% trim removes 1 from each end
        result = trimmed_mean(data, proportiontocut=0.10)

        # Should be mean of [2, 3, 4, 5, 6, 7, 8, 9] = 5.5
        expected = np.mean([2, 3, 4, 5, 6, 7, 8, 9])
        assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"

    def test_trimmed_mean_penny_stock_outlier(self):
        """Test trimmed mean with pump-and-dump outlier."""
        # Returns with one massive outlier
        returns = np.array(
            [
                0.02,
                0.05,
                -0.01,
                0.08,
                0.03,
                0.06,
                -0.02,
                0.04,
                0.07,
                0.01,
                0.09,
                -0.03,
                12.0,  # 1200% pump-and-dump
                0.05,
                0.02,
                0.06,
                0.04,
                -0.01,
                0.03,
                0.08,
            ]
        )

        # Regular mean heavily skewed
        regular_mean = np.mean(returns)
        assert regular_mean > 0.60, "Regular mean inflated by outlier"

        # Trimmed mean (5% from each tail)
        trimmed = trimmed_mean(returns, proportiontocut=0.05)

        # Should be close to median and realistic
        median = np.median(returns)
        assert abs(trimmed - median) < 0.02, "Trimmed mean should be near median"
        assert 0.03 < trimmed < 0.06, f"Trimmed mean should be realistic: {trimmed}"

    def test_trimmed_mean_symmetry(self):
        """Test trimmed mean handles symmetric outliers correctly."""
        # Symmetric distribution with outliers on both ends
        data = np.array([-100, -10, -5, 0, 5, 10, 100])

        # 14% trim removes 1 from each end (rounded)
        result = trimmed_mean(data, proportiontocut=0.14)

        # Should be mean of [-10, -5, 0, 5, 10] = 0
        assert abs(result - 0.0) < 0.01, "Symmetric data should have mean near 0"

    def test_trimmed_mean_different_trim_levels(self):
        """Test different trimming proportions give stable results."""
        np.random.seed(42)
        returns = np.random.normal(0.03, 0.10, 200)
        returns[0] = 5.0  # Add outlier

        # Try different trim levels
        trim_5 = trimmed_mean(returns, 0.05)
        trim_10 = trimmed_mean(returns, 0.10)
        trim_20 = trimmed_mean(returns, 0.20)

        # All should be close to each other and near 0.03
        assert abs(trim_5 - 0.03) < 0.02, f"5% trim: {trim_5}"
        assert abs(trim_10 - 0.03) < 0.02, f"10% trim: {trim_10}"
        assert abs(trim_20 - 0.03) < 0.02, f"20% trim: {trim_20}"

        # Should be relatively stable across trim levels
        assert abs(trim_5 - trim_10) < 0.01, "Trim levels should give similar results"

    def test_trimmed_mean_empty_array(self):
        """Test trimmed mean handles empty arrays gracefully."""
        data = np.array([])
        result = trimmed_mean(data)
        assert result == 0.0, "Empty array should return 0.0"


class TestMedianAbsoluteDeviation:
    """Test MAD as robust alternative to standard deviation."""

    def test_mad_basic(self):
        """Test basic MAD calculation."""
        # Simple symmetric data
        data = np.array([1, 2, 3, 4, 5])

        mad = median_absolute_deviation(data)

        # Median is 3, deviations are [2, 1, 0, 1, 2]
        # Median of deviations is 1
        # Scaled MAD = 1 * 1.4826 = 1.4826
        expected = 1.4826
        assert abs(mad - expected) < 0.01, f"Expected {expected}, got {mad}"

    def test_mad_vs_std_no_outliers(self):
        """Test MAD ≈ std dev for normal data without outliers."""
        np.random.seed(42)
        data = np.random.normal(0, 1, 1000)  # Normal(0, 1)

        mad = median_absolute_deviation(data)
        std = np.std(data, ddof=1)

        # MAD should be close to std dev for normal data
        ratio = mad / std
        assert 0.8 < ratio < 1.2, f"MAD/StdDev ratio should be near 1.0, got {ratio}"

    def test_mad_robust_to_outliers(self):
        """Test MAD remains stable with outliers (unlike std dev)."""
        # Clean data
        np.random.seed(42)
        clean_data = np.random.normal(0.03, 0.10, 100)

        clean_std = np.std(clean_data, ddof=1)
        clean_mad = median_absolute_deviation(clean_data)

        # Add extreme outliers
        outlier_data = clean_data.copy()
        outlier_data = np.append(outlier_data, [5.0, -0.9, 3.5])  # Extreme outliers

        outlier_std = np.std(outlier_data, ddof=1)
        outlier_mad = median_absolute_deviation(outlier_data)

        # Std dev should increase significantly
        std_increase = (outlier_std - clean_std) / clean_std
        assert std_increase > 1.0, "Std dev should increase significantly with outliers"

        # MAD should remain relatively stable
        mad_increase = (outlier_mad - clean_mad) / clean_mad
        assert mad_increase < 0.5, f"MAD should be stable with outliers: {mad_increase:.2%}"

    def test_mad_penny_stock_returns(self):
        """Test MAD with realistic penny stock returns."""
        returns = np.array(
            [
                0.02,
                0.05,
                -0.01,
                0.08,
                0.03,
                0.06,
                -0.02,
                0.04,
                5.0,  # 500% outlier
                0.07,
                0.01,
                0.09,
                -0.03,
                0.05,
                0.02,
            ]
        )

        std = np.std(returns, ddof=1)
        mad = median_absolute_deviation(returns)

        # Std dev explodes with outlier
        assert std > 1.0, f"Std dev inflated: {std}"

        # MAD remains reasonable
        assert mad < 0.10, f"MAD should be stable: {mad}"

        # MAD/StdDev ratio indicates outliers
        ratio = mad / std
        assert ratio < 0.10, f"Low ratio indicates outliers: {ratio}"

    def test_mad_scale_factor(self):
        """Test MAD scale factor makes it comparable to std dev."""
        np.random.seed(42)
        data = np.random.normal(0, 2, 1000)  # Normal with std=2

        # MAD with default scale factor (1.4826)
        mad_scaled = median_absolute_deviation(data, scale_factor=1.4826)

        # MAD without scaling
        mad_unscaled = median_absolute_deviation(data, scale_factor=1.0)

        # Scaled should be ≈ 2.0 (the std dev)
        assert 1.5 < mad_scaled < 2.5, f"Scaled MAD should be near 2.0: {mad_scaled}"

        # Unscaled should be ≈ 1.35 (2.0 / 1.4826)
        assert 1.0 < mad_unscaled < 1.7, f"Unscaled MAD: {mad_unscaled}"

    def test_mad_empty_array(self):
        """Test MAD handles empty arrays gracefully."""
        data = np.array([])
        result = median_absolute_deviation(data)
        assert result == 0.0, "Empty array should return 0.0"

    def test_mad_constant_values(self):
        """Test MAD returns 0 for constant values."""
        data = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        result = median_absolute_deviation(data)
        assert result == 0.0, "Constant values should have MAD = 0"


class TestRobustZScore:
    """Test robust z-scores for outlier detection."""

    def test_robust_zscore_basic(self):
        """Test basic robust z-score calculation."""
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])

        z_scores = robust_zscore(data)

        # The outlier (100) should have a very high z-score
        assert z_scores[-1] > 10, f"Outlier should have high z-score: {z_scores[-1]}"

        # Middle values should have low z-scores
        assert abs(z_scores[4]) < 1, "Median should have z-score near 0"

    def test_robust_zscore_outlier_detection(self):
        """Test robust z-scores correctly identify outliers."""
        returns = np.array(
            [
                0.02,
                0.05,
                -0.01,
                0.08,
                0.03,
                0.06,
                -0.02,
                0.04,
                5.0,  # 500% outlier
                -0.85,  # 85% loss outlier
                0.07,
                0.01,
                0.09,
                -0.03,
                0.05,
                0.02,
            ]
        )

        z_scores = robust_zscore(returns)

        # Identify outliers with |z| > 3
        outlier_mask = np.abs(z_scores) > 3
        outlier_indices = np.where(outlier_mask)[0]

        # Should detect the two outliers
        assert 8 in outlier_indices, "Should detect 500% gain"
        assert 9 in outlier_indices, "Should detect 85% loss"

        # Should not flag normal returns
        normal_indices = [0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15]
        for idx in normal_indices:
            assert abs(z_scores[idx]) < 3, f"Normal return at {idx} should not be flagged"

    def test_robust_zscore_vs_traditional(self):
        """Test robust z-scores outperform traditional z-scores with outliers."""
        np.random.seed(42)
        data = np.random.normal(0, 1, 100)
        data[0] = 50  # Extreme outlier

        # Traditional z-scores
        z_traditional = (data - np.mean(data)) / np.std(data, ddof=1)

        # Robust z-scores
        z_robust = robust_zscore(data)

        # Traditional z-score for outlier is too low (outlier inflates std dev)
        assert z_traditional[0] < 10, f"Traditional z-score too low: {z_traditional[0]}"

        # Robust z-score correctly identifies extreme outlier
        assert z_robust[0] > 30, f"Robust z-score should be very high: {z_robust[0]}"

    def test_robust_zscore_filtering(self):
        """Test using robust z-scores to filter outliers."""
        np.random.seed(42)
        returns = np.random.normal(0.03, 0.12, 500)

        # Add pump-and-dumps
        returns[10] = 2.5
        returns[50] = -0.88
        returns[150] = 3.1

        # Calculate robust z-scores
        z_scores = robust_zscore(returns)

        # Filter to keep only |z| < 3
        clean_mask = np.abs(z_scores) < 3
        clean_returns = returns[clean_mask]

        # Should remove at least the 3 planted outliers (may remove a few more from random data)
        assert len(clean_returns) <= 497, f"Should remove outliers: {len(clean_returns)}"
        assert len(clean_returns) >= 490, f"Should not remove too many: {len(clean_returns)}"

        # Clean data should have mean near 0.03
        clean_mean = np.mean(clean_returns)
        assert 0.01 < clean_mean < 0.05, f"Clean mean should be near 0.03: {clean_mean}"

    def test_robust_zscore_empty_array(self):
        """Test robust z-score handles empty arrays gracefully."""
        data = np.array([])
        result = robust_zscore(data)
        assert len(result) == 0, "Empty array should return empty array"

    def test_robust_zscore_constant_values(self):
        """Test robust z-score handles constant values (MAD=0)."""
        data = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        result = robust_zscore(data)

        # All values equal to median should have z=0
        assert np.allclose(result, 0.0), "Constant values should have z=0"

    def test_robust_zscore_precomputed_mad(self):
        """Test robust z-score with precomputed MAD for efficiency."""
        np.random.seed(42)
        data = np.random.normal(0, 1, 1000)

        # Calculate MAD once
        mad = median_absolute_deviation(data)

        # Use precomputed MAD
        z_scores = robust_zscore(data, mad=mad)

        # Should still work correctly
        outlier_count = np.sum(np.abs(z_scores) > 3)

        # For normal data, ~0.3% should be outliers (3+ std devs)
        expected_outliers = 1000 * 0.003
        assert outlier_count < 20, f"Should have few outliers: {outlier_count}"


class TestRobustStatisticsIntegration:
    """Integration tests for robust statistics working together."""

    def test_complete_workflow_2year_backtest(self):
        """Test complete robust statistics workflow for 2-year backtest."""
        # Simulate 2-year backtest: 520 trades with realistic penny stock returns
        np.random.seed(42)
        returns = np.random.normal(0.025, 0.12, 520)

        # Add realistic penny stock outliers (1% of trades)
        outlier_indices = [10, 50, 150, 300, 450]
        returns[outlier_indices] = [2.5, -0.85, 1.8, -0.78, 3.2]

        # Step 1: Identify outliers with robust z-scores
        z_scores = robust_zscore(returns)
        outlier_mask = np.abs(z_scores) > 3

        # Should detect the 5 planted outliers
        assert np.sum(outlier_mask) >= 5, f"Should detect outliers: {np.sum(outlier_mask)}"

        # Step 2: Calculate robust statistics
        # Winsorize for stable estimates
        winsorized = winsorize(returns, limits=(0.01, 0.01))

        # Trimmed mean for typical performance
        typical_return = trimmed_mean(returns, proportiontocut=0.05)

        # MAD for robust risk estimate
        risk_mad = median_absolute_deviation(returns)

        # Step 3: Compare with traditional statistics
        raw_mean = np.mean(returns)
        raw_std = np.std(returns, ddof=1)

        winsorized_mean = np.mean(winsorized)
        winsorized_std = np.std(winsorized, ddof=1)

        # Robust stats should be more stable
        assert winsorized_mean < raw_mean, "Outliers inflated mean"
        assert winsorized_std < raw_std, "Outliers inflated std dev"
        assert risk_mad < raw_std, "MAD more stable than std dev"

        # Robust stats should be realistic
        assert 0.01 < typical_return < 0.05, f"Typical return realistic: {typical_return}"
        assert 0.08 < risk_mad < 0.20, f"MAD risk realistic: {risk_mad}"

    def test_robust_sharpe_ratio(self):
        """Test calculating robust Sharpe ratio using MAD."""
        np.random.seed(42)
        returns = np.random.normal(0.03, 0.15, 252)  # 1 year daily
        returns[0] = 5.0  # Extreme outlier

        # Traditional Sharpe ratio
        traditional_sharpe = (np.mean(returns) / np.std(returns, ddof=1)) * np.sqrt(252)

        # Robust Sharpe ratio using MAD
        median_return = np.median(returns)
        mad = median_absolute_deviation(returns)
        robust_sharpe = (median_return / mad) * np.sqrt(252)

        # Both should be positive
        assert traditional_sharpe > 0, f"Traditional Sharpe: {traditional_sharpe}"
        assert robust_sharpe > 0, f"Robust Sharpe: {robust_sharpe}"

        # Robust Sharpe should be relatively stable
        # (MAD is less affected by the single outlier)
        assert 1.0 < robust_sharpe < 5.0, f"Robust Sharpe realistic: {robust_sharpe}"

    def test_robust_confidence_intervals(self):
        """Test robust confidence intervals using winsorized bootstrapping."""
        np.random.seed(42)
        returns = np.random.normal(0.03, 0.12, 200)
        returns[0] = 4.0  # Outlier

        # Winsorize first
        winsorized = winsorize(returns, limits=(0.01, 0.01))

        # Bootstrap confidence intervals on winsorized data
        result = scipy_stats.bootstrap(
            (winsorized,),
            np.mean,
            n_resamples=1000,
            confidence_level=0.95,
            random_state=42,
        )

        ci_lower = result.confidence_interval.low
        ci_upper = result.confidence_interval.high

        # CI should be realistic
        assert 0.0 < ci_lower < 0.05, f"CI lower bound realistic: {ci_lower}"
        assert 0.02 < ci_upper < 0.08, f"CI upper bound realistic: {ci_upper}"

        # CI should contain true mean (0.03)
        assert ci_lower < 0.03 < ci_upper, "CI should contain true mean"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
