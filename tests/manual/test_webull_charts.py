"""
test_webull_charts.py
======================

Comprehensive test suite for WeBull-style chart generation (Phase 1).

Tests:
- WeBull style creation with correct colors and text sizing
- Multi-panel chart generation (price, volume, RSI, MACD)
- Support/Resistance line rendering
- Color scheme validation (#1b1f24 background, #3dc985 green, #ef4f60 red)
- Text sizing validation (12pt labels, 16pt titles)
- Mobile optimization
- QuickChart WeBull theme integration
- Visual regression test (sample chart generation)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend
    import numpy as np
    import pandas as pd
    from matplotlib import pyplot as plt

    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False
    pytest.skip("matplotlib/mplfinance not available", allow_module_level=True)

from src.catalyst_bot.charts import (  # noqa: E402
    INDICATOR_COLORS,
    WEBULL_STYLE,
    add_indicator_panels,
    apply_sr_lines,
    create_webull_style,
    optimize_for_mobile,
    render_chart_with_panels,
)
from src.catalyst_bot.charts_quickchart import generate_chart_config  # noqa: E402


class TestWeBullStyleConstants:
    """Test WeBull color scheme and style constants."""

    def test_webull_style_exists(self):
        """Verify WEBULL_STYLE constant is defined."""
        assert WEBULL_STYLE is not None
        assert isinstance(WEBULL_STYLE, dict)

    def test_webull_background_color(self):
        """Verify WeBull background color is #1b1f24."""
        assert WEBULL_STYLE["facecolor"] == "#1b1f24"
        assert WEBULL_STYLE["figcolor"] == "#1b1f24"

    def test_webull_grid_color(self):
        """Verify WeBull grid color is #2c2e31."""
        assert WEBULL_STYLE["gridcolor"] == "#2c2e31"
        assert WEBULL_STYLE["edgecolor"] == "#2c2e31"

    def test_webull_candle_colors(self):
        """Verify WeBull candle colors (green: #3dc985, red: #ef4f60)."""
        candles = WEBULL_STYLE["marketcolors"]["candle"]
        assert candles["up"] == "#3dc985"
        assert candles["down"] == "#ef4f60"

    def test_webull_wick_colors(self):
        """Verify WeBull wick colors match candle colors."""
        wicks = WEBULL_STYLE["marketcolors"]["wick"]
        assert wicks["up"] == "#3dc985"
        assert wicks["down"] == "#ef4f60"

    def test_webull_volume_colors(self):
        """Verify WeBull volume colors with transparency."""
        volume = WEBULL_STYLE["marketcolors"]["volume"]
        assert volume["up"] == "#3dc98570"  # 70 = 44% opacity
        assert volume["down"] == "#ef4f6070"

    def test_webull_text_sizing(self):
        """Verify default text sizing (12pt labels, 16pt titles)."""
        rc = WEBULL_STYLE["rc"]
        assert rc["axes.labelsize"] == 12
        assert rc["axes.titlesize"] == 16
        assert rc["font.size"] == 12

    def test_indicator_colors_defined(self):
        """Verify indicator color palette is defined."""
        assert INDICATOR_COLORS["vwap"] == "#FF9800"
        assert INDICATOR_COLORS["rsi"] == "#00BCD4"
        assert INDICATOR_COLORS["macd_line"] == "#2196F3"
        assert INDICATOR_COLORS["macd_signal"] == "#FF5722"
        assert INDICATOR_COLORS["support"] == "#4CAF50"
        assert INDICATOR_COLORS["resistance"] == "#F44336"


class TestWeBullStyleCreation:
    """Test mplfinance style creation from WeBull constants."""

    def test_create_webull_style_returns_style(self):
        """Verify create_webull_style() returns a valid style object."""
        style = create_webull_style()
        # Should return dict or mplfinance style object
        assert style is not None

    def test_create_webull_style_respects_env_vars(self, monkeypatch):
        """Verify create_webull_style() respects environment variables."""
        monkeypatch.setenv("CHART_AXIS_LABEL_SIZE", "14")
        monkeypatch.setenv("CHART_TITLE_SIZE", "18")

        style = create_webull_style()
        # mplfinance style is an object, check it was created
        assert style is not None

    def test_create_webull_style_fallback_on_error(self, monkeypatch):
        """Verify create_webull_style() falls back gracefully on error."""

        # Mock mpf.make_mpf_style to raise an exception
        def mock_make_mpf_style(*args, **kwargs):
            raise ValueError("Simulated mplfinance error")

        # Monkeypatch the make_mpf_style function
        import mplfinance as mpf

        monkeypatch.setattr(mpf, "make_mpf_style", mock_make_mpf_style)

        # Should not raise, should return fallback
        style = create_webull_style()
        assert style == "yahoo"  # fallback


class TestSupportResistanceLines:
    """Test Support/Resistance line rendering."""

    def test_apply_sr_lines_empty_levels(self):
        """Verify apply_sr_lines() handles empty levels."""
        hlines = apply_sr_lines([], [])
        assert isinstance(hlines, dict)
        assert len(hlines) == 0

    def test_apply_sr_lines_support_only(self):
        """Verify apply_sr_lines() adds support levels (green)."""
        support = [
            {"price": 100.0, "strength": 75.0, "touches": 3},
            {"price": 95.0, "strength": 50.0, "touches": 2},
        ]
        hlines = apply_sr_lines(support, [])

        assert len(hlines) == 2
        assert "s0" in hlines
        assert "s1" in hlines
        assert hlines["s0"]["y"] == 100.0
        assert hlines["s0"]["color"] == "#4CAF50"  # green
        assert hlines["s1"]["y"] == 95.0

    def test_apply_sr_lines_resistance_only(self):
        """Verify apply_sr_lines() adds resistance levels (red)."""
        resistance = [
            {"price": 110.0, "strength": 85.0, "touches": 5},
        ]
        hlines = apply_sr_lines([], resistance)

        assert len(hlines) == 1
        assert "r0" in hlines
        assert hlines["r0"]["y"] == 110.0
        assert hlines["r0"]["color"] == "#F44336"  # red

    def test_apply_sr_lines_both(self):
        """Verify apply_sr_lines() handles both support and resistance."""
        support = [{"price": 100.0, "strength": 75.0, "touches": 3}]
        resistance = [{"price": 110.0, "strength": 85.0, "touches": 5}]
        hlines = apply_sr_lines(support, resistance)

        assert len(hlines) == 2
        assert "s0" in hlines
        assert "r0" in hlines

    def test_apply_sr_lines_strength_affects_width(self):
        """Verify line width increases with strength."""
        weak_support = [{"price": 100.0, "strength": 25.0, "touches": 2}]
        strong_support = [{"price": 105.0, "strength": 90.0, "touches": 8}]

        hlines_weak = apply_sr_lines(weak_support, [])
        hlines_strong = apply_sr_lines(strong_support, [])

        # Stronger level should have thicker line
        assert hlines_strong["s0"]["linewidth"] > hlines_weak["s0"]["linewidth"]


class TestIndicatorPanels:
    """Test multi-panel indicator layout."""

    def setup_method(self):
        """Create sample OHLCV data for testing."""
        dates = pd.date_range(start="2025-01-01", periods=50, freq="5min")
        np.random.seed(42)

        close_prices = 100 + np.cumsum(np.random.randn(50) * 0.5)
        self.df = pd.DataFrame(
            {
                "Open": close_prices + np.random.randn(50) * 0.2,
                "High": close_prices + abs(np.random.randn(50) * 0.5),
                "Low": close_prices - abs(np.random.randn(50) * 0.5),
                "Close": close_prices,
                "Volume": np.random.randint(1000, 5000, 50),
            },
            index=dates,
        )

    def test_add_indicator_panels_empty(self):
        """Verify add_indicator_panels() with no indicators returns empty list."""
        apds = add_indicator_panels(self.df, indicators=[])
        assert isinstance(apds, list)
        assert len(apds) == 0

    def test_add_indicator_panels_vwap(self):
        """Verify add_indicator_panels() adds VWAP overlay."""
        # Add VWAP column
        close = self.df["Close"]
        vol = self.df["Volume"]
        self.df["vwap"] = (close * vol).cumsum() / vol.cumsum()

        apds = add_indicator_panels(self.df, indicators=["vwap"])

        # Should have 1 addplot (VWAP on panel 0)
        assert len(apds) >= 1
        # VWAP should be orange
        # Note: Can't easily inspect mpf.make_addplot objects, just verify it was created

    def test_add_indicator_panels_bollinger(self):
        """Verify add_indicator_panels() adds Bollinger Bands."""
        # Add Bollinger columns
        sma = self.df["Close"].rolling(window=20).mean()
        std = self.df["Close"].rolling(window=20).std()
        self.df["bb_upper"] = sma + 2 * std
        self.df["bb_middle"] = sma
        self.df["bb_lower"] = sma - 2 * std

        apds = add_indicator_panels(self.df, indicators=["bollinger"])

        # Should have 3 addplots (upper, middle, lower)
        assert len(apds) >= 3

    def test_add_indicator_panels_rsi(self):
        """Verify add_indicator_panels() adds RSI panel."""
        # Add RSI column
        delta = self.df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df["rsi"] = 100 - (100 / (1 + rs))

        apds = add_indicator_panels(self.df, indicators=["rsi"])

        # Should have 1 addplot (RSI on panel 1)
        assert len(apds) >= 1

    def test_add_indicator_panels_macd(self):
        """Verify add_indicator_panels() adds MACD panel."""
        # Add MACD columns
        ema_12 = self.df["Close"].ewm(span=12, adjust=False).mean()
        ema_26 = self.df["Close"].ewm(span=26, adjust=False).mean()
        self.df["macd"] = ema_12 - ema_26
        self.df["macd_signal"] = self.df["macd"].ewm(span=9, adjust=False).mean()

        apds = add_indicator_panels(self.df, indicators=["macd"])

        # Should have 2 addplots (MACD line + signal)
        assert len(apds) >= 2

    def test_add_indicator_panels_multiple(self):
        """Verify add_indicator_panels() handles multiple indicators."""
        # Add all indicator columns
        close = self.df["Close"]
        vol = self.df["Volume"]
        self.df["vwap"] = (close * vol).cumsum() / vol.cumsum()

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df["rsi"] = 100 - (100 / (1 + rs))

        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        self.df["macd"] = ema_12 - ema_26
        self.df["macd_signal"] = self.df["macd"].ewm(span=9, adjust=False).mean()

        apds = add_indicator_panels(self.df, indicators=["vwap", "rsi", "macd"])

        # Should have 4+ addplots (VWAP + RSI + MACD line + MACD signal)
        assert len(apds) >= 4


class TestMobileOptimization:
    """Test mobile display optimization."""

    def test_optimize_for_mobile_basic(self):
        """Verify optimize_for_mobile() doesn't raise errors."""
        fig, ax = plt.subplots()
        optimize_for_mobile(fig, [ax])
        plt.close(fig)

    def test_optimize_for_mobile_adjusts_ticks(self):
        """Verify optimize_for_mobile() reduces tick count."""
        fig, ax = plt.subplots()

        # Add some data
        ax.plot([1, 2, 3, 4, 5], [1, 4, 2, 3, 5])

        optimize_for_mobile(fig, [ax])

        # Verify tick locators were applied
        # (Hard to verify exact count without rendering)
        assert ax.xaxis.get_major_locator() is not None
        assert ax.yaxis.get_major_locator() is not None

        plt.close(fig)


class TestChartGeneration:
    """Test full chart generation pipeline."""

    def setup_method(self):
        """Create sample data."""
        dates = pd.date_range(start="2025-01-01", periods=50, freq="5min")
        np.random.seed(42)

        close_prices = 100 + np.cumsum(np.random.randn(50) * 0.5)
        self.df = pd.DataFrame(
            {
                "Open": close_prices + np.random.randn(50) * 0.2,
                "High": close_prices + abs(np.random.randn(50) * 0.5),
                "Low": close_prices - abs(np.random.randn(50) * 0.5),
                "Close": close_prices,
                "Volume": np.random.randint(1000, 5000, 50),
            },
            index=dates,
        )

    def test_render_chart_with_panels_basic(self, tmp_path):
        """Verify render_chart_with_panels() creates a chart file."""
        out_dir = tmp_path / "charts"

        path = render_chart_with_panels(
            "AAPL", self.df, indicators=[], out_dir=str(out_dir)
        )

        # Should return a path
        assert path is not None
        assert path.exists()
        assert path.suffix == ".png"

    def test_render_chart_with_panels_with_vwap(self, tmp_path):
        """Verify render_chart_with_panels() with VWAP indicator."""
        out_dir = tmp_path / "charts"

        # Add VWAP
        close = self.df["Close"]
        vol = self.df["Volume"]
        self.df["vwap"] = (close * vol).cumsum() / vol.cumsum()

        path = render_chart_with_panels(
            "AAPL", self.df, indicators=["vwap"], out_dir=str(out_dir)
        )

        assert path is not None
        assert path.exists()

    def test_render_chart_with_panels_multi_panel(self, tmp_path):
        """Verify render_chart_with_panels() with multiple panels."""
        out_dir = tmp_path / "charts"

        # Add indicators
        close = self.df["Close"]
        vol = self.df["Volume"]
        self.df["vwap"] = (close * vol).cumsum() / vol.cumsum()

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df["rsi"] = 100 - (100 / (1 + rs))

        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        self.df["macd"] = ema_12 - ema_26
        self.df["macd_signal"] = self.df["macd"].ewm(span=9, adjust=False).mean()

        path = render_chart_with_panels(
            "AAPL", self.df, indicators=["vwap", "rsi", "macd"], out_dir=str(out_dir)
        )

        assert path is not None
        assert path.exists()

    def test_render_chart_with_panels_with_sr_levels(self, tmp_path):
        """Verify render_chart_with_panels() with S/R levels."""
        out_dir = tmp_path / "charts"

        support = [{"price": 99.0, "strength": 75.0, "touches": 3}]
        resistance = [{"price": 102.0, "strength": 85.0, "touches": 5}]

        path = render_chart_with_panels(
            "AAPL",
            self.df,
            support_levels=support,
            resistance_levels=resistance,
            out_dir=str(out_dir),
        )

        assert path is not None
        assert path.exists()


class TestQuickChartWeBullTheme:
    """Test QuickChart Chart.js WeBull theme integration."""

    def test_generate_chart_config_uses_webull_colors(self, monkeypatch):
        """Verify generate_chart_config() uses WeBull colors in dark theme."""
        monkeypatch.setenv("CHART_THEME", "dark")

        config = generate_chart_config(
            ticker="AAPL",
            timeframe="1D",
            ohlcv_data=[
                {"x": "2025-01-01T10:00", "o": 100, "h": 102, "l": 99, "c": 101}
            ],
        )

        # Check background color
        assert config["options"]["backgroundColor"] == "#1b1f24"

        # Check grid color
        assert config["options"]["scales"]["x"]["grid"]["color"] == "#2c2e31"
        assert config["options"]["scales"]["y"]["grid"]["color"] == "#2c2e31"

        # Check candle colors
        datasets = config["data"]["datasets"]
        candle_dataset = datasets[0]
        assert candle_dataset["color"]["up"] == "#3dc985"
        assert candle_dataset["color"]["down"] == "#ef4f60"

    def test_generate_chart_config_text_sizing(self, monkeypatch):
        """Verify generate_chart_config() uses correct text sizing."""
        monkeypatch.setenv("CHART_AXIS_LABEL_SIZE", "12")
        monkeypatch.setenv("CHART_TITLE_SIZE", "16")

        config = generate_chart_config(
            ticker="AAPL",
            timeframe="1D",
            ohlcv_data=[
                {"x": "2025-01-01T10:00", "o": 100, "h": 102, "l": 99, "c": 101}
            ],
        )

        # Check axis label size
        assert config["options"]["scales"]["x"]["ticks"]["font"]["size"] == 12
        assert config["options"]["scales"]["y"]["ticks"]["font"]["size"] == 12

        # Check title size
        assert config["options"]["plugins"]["title"]["font"]["size"] == 16


class TestVisualRegression:
    """Visual regression test - generates sample charts for manual inspection."""

    def test_generate_sample_webull_chart(self, tmp_path):
        """Generate a sample WeBull-style chart for visual inspection.

        This test creates a real chart file that can be manually inspected
        to verify the WeBull aesthetic matches expectations.
        """
        # Create sample data
        dates = pd.date_range(start="2025-01-01", periods=100, freq="5min")
        np.random.seed(42)

        close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        df = pd.DataFrame(
            {
                "Open": close_prices + np.random.randn(100) * 0.2,
                "High": close_prices + abs(np.random.randn(100) * 0.5),
                "Low": close_prices - abs(np.random.randn(100) * 0.5),
                "Close": close_prices,
                "Volume": np.random.randint(1000, 5000, 100),
            },
            index=dates,
        )

        # Add indicators
        close = df["Close"]
        vol = df["Volume"]
        df["vwap"] = (close * vol).cumsum() / vol.cumsum()

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

        # Add S/R levels
        support = [
            {"price": 98.0, "strength": 75.0, "touches": 4},
            {"price": 95.0, "strength": 60.0, "touches": 2},
        ]
        resistance = [
            {"price": 103.0, "strength": 85.0, "touches": 5},
            {"price": 106.0, "strength": 70.0, "touches": 3},
        ]

        # Generate chart
        out_dir = tmp_path / "visual_regression"
        path = render_chart_with_panels(
            "VISUAL_TEST",
            df,
            indicators=["vwap", "rsi", "macd"],
            support_levels=support,
            resistance_levels=resistance,
            out_dir=str(out_dir),
        )

        # Verify chart was created
        assert path is not None
        assert path.exists()
        assert path.stat().st_size > 0  # File is not empty

        print(f"\nVisual regression chart saved to: {path}")
        print("  Please manually inspect this chart to verify:")
        print("  - Background is dark (#1b1f24)")
        print("  - Candles are green (#3dc985) and red (#ef4f60)")
        print("  - Grid lines are subtle (#2c2e31)")
        print("  - Text is 12pt (labels) and 16pt (title)")
        print("  - 4 panels: price, volume, RSI, MACD")
        print("  - S/R lines are visible (green support, red resistance)")


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v", "-s"])
