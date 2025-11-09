"""
Test suite for chart data gap filling functionality (Wave 3.2).

Tests gap detection, gap filling algorithms, extended hours handling,
and visual indicator application.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta


# Import gap filling functions
try:
    from catalyst_bot.charts import detect_gaps, fill_gaps
    HAS_CHARTS = True
except ImportError:
    HAS_CHARTS = False
    pytestmark = pytest.mark.skip(reason="Charts module not available")


class TestGapDetection:
    """Test gap detection in time series data."""

    def test_detect_gaps_with_missing_candles(self):
        """Test detection of gaps in 15-minute intraday data."""
        # Create sample data with a gap
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            '2024-01-01 09:45',
            # Gap here (10:00 missing)
            '2024-01-01 10:15',
            '2024-01-01 10:30',
        ])
        df = pd.DataFrame({
            'Close': [100, 101, 102, 103]
        }, index=dates)

        gaps = detect_gaps(df, expected_interval_minutes=15)

        assert len(gaps) == 1, "Should detect one gap"
        assert gaps[0][0] == dates[1], "Gap should start after 09:45"
        assert gaps[0][1] == dates[2], "Gap should end at 10:15"
        assert gaps[0][2] == 30.0, "Gap duration should be 30 minutes"

    def test_detect_gaps_no_gaps(self):
        """Test that no gaps are detected in continuous data."""
        # Create continuous 15-minute data
        dates = pd.date_range('2024-01-01 09:30', periods=10, freq='15min')
        df = pd.DataFrame({
            'Close': range(100, 110)
        }, index=dates)

        gaps = detect_gaps(df, expected_interval_minutes=15)

        assert len(gaps) == 0, "Should detect no gaps in continuous data"

    def test_detect_gaps_empty_dataframe(self):
        """Test gap detection with empty DataFrame."""
        df = pd.DataFrame()
        gaps = detect_gaps(df, expected_interval_minutes=15)
        assert len(gaps) == 0, "Should return empty list for empty DataFrame"

    def test_detect_gaps_single_row(self):
        """Test gap detection with single row DataFrame."""
        df = pd.DataFrame({
            'Close': [100]
        }, index=pd.to_datetime(['2024-01-01 09:30']))

        gaps = detect_gaps(df, expected_interval_minutes=15)
        assert len(gaps) == 0, "Should return empty list for single row"

    def test_detect_gaps_weekend(self):
        """Test detection of weekend gaps (expected behavior)."""
        # Friday close to Monday open
        dates = pd.to_datetime([
            '2024-01-05 15:45',  # Friday
            '2024-01-08 09:30',  # Monday
        ])
        df = pd.DataFrame({
            'Close': [100, 101]
        }, index=dates)

        gaps = detect_gaps(df, expected_interval_minutes=15)

        assert len(gaps) == 1, "Should detect weekend gap"
        # Weekend gap is much longer than 15 minutes
        assert gaps[0][2] > 1000, "Weekend gap should be many hours"


class TestGapFilling:
    """Test gap filling algorithms."""

    def test_fill_gaps_forward_fill(self):
        """Test forward fill method (last known price)."""
        # Create data with gap
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            '2024-01-01 09:45',
            # Gap (10:00 missing)
            '2024-01-01 10:15',
        ])
        df = pd.DataFrame({
            'Open': [100, 101, 102],
            'High': [101, 102, 103],
            'Low': [99, 100, 101],
            'Close': [100, 101, 102],
            'Volume': [1000, 1500, 2000]
        }, index=dates)

        filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)

        # Should have filled the gap at 10:00
        assert len(filled) > len(df), "Should add missing candles"
        assert '2024-01-01 10:00' in str(filled.index), "Should fill 10:00 candle"

        # Check that filled candle uses forward fill
        filled_idx = pd.to_datetime('2024-01-01 10:00')
        if filled_idx in filled.index:
            assert filled.loc[filled_idx, 'Close'] == 101, "Should use last known price"
            assert filled.loc[filled_idx, 'Volume'] == 0, "Volume should be 0 for filled candle"
            assert filled.loc[filled_idx, 'filled'] == True, "Should mark as filled"

    def test_fill_gaps_volume_zero(self):
        """Test that filled periods have volume = 0."""
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            '2024-01-01 10:00',  # 30-minute gap
        ])
        df = pd.DataFrame({
            'Open': [100, 102],
            'High': [101, 103],
            'Low': [99, 101],
            'Close': [100, 102],
            'Volume': [1000, 2000]
        }, index=dates)

        filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)

        # Check that filled candles have volume = 0
        for idx in filled.index:
            if filled.loc[idx, 'filled']:
                assert filled.loc[idx, 'Volume'] == 0, f"Filled candle at {idx} should have volume=0"

    def test_fill_gaps_no_gaps(self):
        """Test gap filling with continuous data (no changes expected)."""
        dates = pd.date_range('2024-01-01 09:30', periods=5, freq='15min')
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104],
            'High': [101, 102, 103, 104, 105],
            'Low': [99, 100, 101, 102, 103],
            'Close': [100, 101, 102, 103, 104],
            'Volume': [1000, 1500, 2000, 2500, 3000]
        }, index=dates)

        filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)

        assert len(filled) == len(df), "Should not add rows for continuous data"
        assert 'filled' in filled.columns, "Should add 'filled' column"
        assert filled['filled'].sum() == 0, "All rows should be marked as not filled"

    def test_fill_gaps_interpolate(self):
        """Test linear interpolation method (experimental)."""
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            '2024-01-01 09:45',
            # Gap (10:00 missing)
            '2024-01-01 10:15',
        ])
        df = pd.DataFrame({
            'Open': [100, 100, 102],
            'High': [101, 101, 103],
            'Low': [99, 99, 101],
            'Close': [100, 100, 102],
            'Volume': [1000, 1500, 2000]
        }, index=dates)

        filled = fill_gaps(df, method='interpolate', expected_interval_minutes=15)

        # Should have filled the gap
        assert len(filled) > len(df), "Should add missing candles"

        # Interpolated value should be between 100 and 102
        filled_idx = pd.to_datetime('2024-01-01 10:00')
        if filled_idx in filled.index:
            close_val = filled.loc[filled_idx, 'Close']
            assert 100 <= close_val <= 102, f"Interpolated close should be between 100-102, got {close_val}"
            assert filled.loc[filled_idx, 'Volume'] == 0, "Volume should be 0 for filled candle"

    def test_fill_gaps_multiple_gaps(self):
        """Test filling multiple gaps in the same dataset."""
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            # Gap 1 (09:45 missing)
            '2024-01-01 10:00',
            '2024-01-01 10:15',
            # Gap 2 (10:30 missing)
            '2024-01-01 10:45',
        ])
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103],
            'High': [101, 102, 103, 104],
            'Low': [99, 100, 101, 102],
            'Close': [100, 101, 102, 103],
            'Volume': [1000, 1500, 2000, 2500]
        }, index=dates)

        filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)

        # Should fill both gaps
        assert len(filled) == 6, "Should have 6 rows (4 original + 2 filled)"
        assert filled['filled'].sum() == 2, "Should mark 2 rows as filled"

    def test_fill_gaps_preserves_original_data(self):
        """Test that gap filling doesn't modify original data points."""
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            '2024-01-01 10:00',
        ])
        df_original = pd.DataFrame({
            'Open': [100, 102],
            'High': [101, 103],
            'Low': [99, 101],
            'Close': [100, 102],
            'Volume': [1000, 2000]
        }, index=dates)

        filled = fill_gaps(df_original, method='forward_fill', expected_interval_minutes=15)

        # Check original data points are preserved
        assert filled.loc[dates[0], 'Close'] == 100, "Original data should be preserved"
        assert filled.loc[dates[1], 'Close'] == 102, "Original data should be preserved"
        assert filled.loc[dates[0], 'Volume'] == 1000, "Original volume should be preserved"
        assert filled.loc[dates[1], 'Volume'] == 2000, "Original volume should be preserved"


class TestGapFillingIntegration:
    """Integration tests for gap filling in chart rendering."""

    def test_gap_filling_marks_filled_rows(self):
        """Test that filled rows are properly marked for visual distinction."""
        dates = pd.to_datetime([
            '2024-01-01 09:30',
            '2024-01-01 10:00',
        ])
        df = pd.DataFrame({
            'Open': [100, 102],
            'High': [101, 103],
            'Low': [99, 101],
            'Close': [100, 102],
            'Volume': [1000, 2000]
        }, index=dates)

        filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)

        # Check that 'filled' column exists and is boolean
        assert 'filled' in filled.columns, "Should have 'filled' column"
        assert filled['filled'].dtype == bool, "'filled' column should be boolean"

        # Original rows should not be marked as filled
        assert filled.loc[dates[0], 'filled'] == False, "Original row should not be marked filled"
        assert filled.loc[dates[1], 'filled'] == False, "Original row should not be marked filled"

    def test_gap_filling_handles_edge_cases(self):
        """Test gap filling with edge case data."""
        # Test with NaN values
        dates = pd.date_range('2024-01-01 09:30', periods=3, freq='30min')
        df = pd.DataFrame({
            'Open': [100, None, 102],
            'High': [101, None, 103],
            'Low': [99, None, 101],
            'Close': [100, None, 102],
            'Volume': [1000, 0, 2000]
        }, index=dates)

        filled = fill_gaps(df, method='forward_fill', expected_interval_minutes=15)

        # Should handle NaN values gracefully
        assert not filled['Close'].isna().any(), "Should fill all NaN values"


# Mark tests as integration tests
pytestmark = pytest.mark.integration


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
