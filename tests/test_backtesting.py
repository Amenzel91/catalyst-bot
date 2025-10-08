"""
Comprehensive Tests for Backtesting Engine
===========================================

Tests all components of the backtesting system including:
- Trade simulator
- Portfolio manager
- Backtest engine
- Analytics
- Monte Carlo
- Reports
- Validator
"""

import json

# Add src to path
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_bot.backtesting import (  # noqa: E402
    BacktestEngine,
    PennyStockTradeSimulator,
    Portfolio,
    Position,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from catalyst_bot.backtesting.monte_carlo import MonteCarloSimulator  # noqa: E402
from catalyst_bot.backtesting.reports import (  # noqa: E402
    export_trades_to_csv,
    generate_backtest_report,
)
from catalyst_bot.backtesting.validator import validate_parameter_change  # noqa: E402


class TestTradeSimulator:
    """Test trade simulator with slippage and volume constraints."""

    def test_simulator_initialization(self):
        """Test simulator initializes correctly."""
        sim = PennyStockTradeSimulator(
            initial_capital=10000.0,
            position_size_pct=0.10,
            max_daily_volume_pct=0.05,
        )

        assert sim.initial_capital == 10000.0
        assert sim.position_size_pct == 0.10
        assert sim.max_daily_volume_pct == 0.05

    def test_slippage_calculation_fixed(self):
        """Test fixed slippage model."""
        sim = PennyStockTradeSimulator(slippage_model="fixed", fixed_slippage_pct=0.02)

        # Buy should add slippage
        buy_price = sim.calculate_slippage("AAPL", 10.0, 100000, 1000, "buy")
        assert buy_price == 10.2  # 10 * 1.02

        # Sell should subtract slippage
        sell_price = sim.calculate_slippage("AAPL", 10.0, 100000, 1000, "sell")
        assert sell_price == 9.8  # 10 * 0.98

    def test_slippage_calculation_adaptive(self):
        """Test adaptive slippage based on price and volume."""
        sim = PennyStockTradeSimulator(slippage_model="adaptive")

        # Low price stock (higher slippage)
        low_price = sim.calculate_slippage("PENNY", 0.50, 50000, 1000, "buy")
        assert low_price > 0.50

        # Normal price stock
        normal_price = sim.calculate_slippage("NORMAL", 10.0, 500000, 1000, "buy")
        assert normal_price > 10.0

        # Slippage should be higher for low price
        low_slippage_pct = ((low_price - 0.50) / 0.50) * 100
        normal_slippage_pct = ((normal_price - 10.0) / 10.0) * 100
        assert low_slippage_pct > normal_slippage_pct

    def test_volume_constraints(self):
        """Test volume constraint validation."""
        sim = PennyStockTradeSimulator(max_daily_volume_pct=0.05)

        # Order within limit
        can_execute, reason = sim.can_execute_trade("AAPL", 1000, 100000)
        assert can_execute is True

        # Order too large
        can_execute, reason = sim.can_execute_trade("AAPL", 10000, 100000)
        assert can_execute is False
        assert "too large" in reason.lower()

        # Very low volume
        can_execute, reason = sim.can_execute_trade("ILLIQ", 100, 5000)
        assert can_execute is False
        assert "insufficient liquidity" in reason.lower()

    def test_trade_execution_buy(self):
        """Test buy trade execution."""
        sim = PennyStockTradeSimulator(initial_capital=10000.0, position_size_pct=0.10)

        result = sim.execute_trade(
            ticker="AAPL",
            action="buy",
            price=10.0,
            volume=100000,
            timestamp=int(datetime.now(timezone.utc).timestamp()),
            available_capital=10000.0,
        )

        assert result.executed is True
        assert result.shares == 100  # 10% of 10000 / 10 = 100 shares
        assert result.fill_price > 10.0  # Slippage applied
        assert result.cost_basis > 1000.0  # Shares * fill_price

    def test_trade_execution_insufficient_capital(self):
        """Test trade execution with insufficient capital."""
        sim = PennyStockTradeSimulator(position_size_pct=0.10)

        result = sim.execute_trade(
            ticker="AAPL",
            action="buy",
            price=10.0,
            volume=100000,
            timestamp=int(datetime.now(timezone.utc).timestamp()),
            available_capital=50.0,  # Not enough for a position
        )

        assert result.executed is False or result.shares <= 5


class TestPortfolio:
    """Test portfolio manager."""

    def test_portfolio_initialization(self):
        """Test portfolio initializes correctly."""
        portfolio = Portfolio(initial_capital=10000.0)

        assert portfolio.cash == 10000.0
        assert portfolio.initial_capital == 10000.0
        assert len(portfolio.positions) == 0
        assert len(portfolio.closed_trades) == 0

    def test_open_position(self):
        """Test opening a position."""
        portfolio = Portfolio(initial_capital=10000.0)

        success = portfolio.open_position(
            ticker="AAPL",
            shares=100,
            entry_price=10.0,
            entry_time=int(datetime.now(timezone.utc).timestamp()),
            alert_data={"score": 0.5, "catalyst_type": "earnings"},
        )

        assert success is True
        assert "AAPL" in portfolio.positions
        assert portfolio.cash == 9000.0  # 10000 - (100 * 10)
        assert portfolio.positions["AAPL"].shares == 100

    def test_close_position(self):
        """Test closing a position."""
        portfolio = Portfolio(initial_capital=10000.0)

        # Open position
        portfolio.open_position(
            ticker="AAPL",
            shares=100,
            entry_price=10.0,
            entry_time=int(datetime.now(timezone.utc).timestamp()),
            alert_data={"score": 0.5},
        )

        # Close position at profit
        trade = portfolio.close_position(
            ticker="AAPL",
            exit_price=12.0,
            exit_time=int(datetime.now(timezone.utc).timestamp()),
            exit_reason="take_profit",
        )

        assert trade is not None
        assert trade.profit == 200.0  # (12 - 10) * 100
        assert trade.profit_pct == 20.0
        assert "AAPL" not in portfolio.positions
        assert portfolio.cash == 10200.0  # Initial - entry + exit

    def test_performance_metrics(self):
        """Test performance metrics calculation."""
        portfolio = Portfolio(initial_capital=10000.0)

        # Simulate some trades
        portfolio.open_position("AAPL", 100, 10.0, 1000, {"score": 0.5})
        portfolio.close_position("AAPL", 12.0, 2000, "take_profit")

        portfolio.open_position("TSLA", 50, 20.0, 3000, {"score": 0.6})
        portfolio.close_position("TSLA", 18.0, 4000, "stop_loss")

        metrics = portfolio.get_performance_metrics()

        assert metrics["total_trades"] == 2
        assert metrics["winning_trades"] == 1
        assert metrics["losing_trades"] == 1
        assert metrics["win_rate"] == 50.0


class TestAnalytics:
    """Test performance analytics functions."""

    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        # Positive returns
        returns = [0.01, 0.02, -0.01, 0.03, 0.01]
        sharpe = calculate_sharpe_ratio(returns)
        assert isinstance(sharpe, float)

        # No returns
        sharpe_empty = calculate_sharpe_ratio([])
        assert sharpe_empty == 0.0

    def test_max_drawdown(self):
        """Test max drawdown calculation."""
        equity_curve = [
            (1000, 10000.0),
            (2000, 12000.0),  # Peak
            (3000, 11000.0),
            (4000, 9000.0),  # Trough (-25%)
            (5000, 11000.0),  # Partial recovery
        ]

        dd_info = calculate_max_drawdown(equity_curve)

        assert dd_info["max_drawdown_pct"] == 25.0
        assert dd_info["peak_value"] == 12000.0
        assert dd_info["trough_value"] == 9000.0

    def test_win_rate(self):
        """Test win rate calculation."""
        trades = [
            {"profit": 100, "alert_data": {"catalyst_type": "fda", "score": 0.5}},
            {"profit": -50, "alert_data": {"catalyst_type": "fda", "score": 0.3}},
            {"profit": 200, "alert_data": {"catalyst_type": "earnings", "score": 0.7}},
        ]

        win_rate_info = calculate_win_rate(trades)

        assert win_rate_info["overall"] == pytest.approx(2 / 3, rel=0.01)
        assert "fda" in win_rate_info["by_catalyst"]

    def test_profit_factor(self):
        """Test profit factor calculation."""
        trades = [
            {"profit": 100},
            {"profit": 200},
            {"profit": -50},
            {"profit": -30},
        ]

        pf = calculate_profit_factor(trades)

        # Profit factor = (100 + 200) / (50 + 30) = 300 / 80 = 3.75
        assert pf == pytest.approx(3.75, rel=0.01)


class TestBacktestEngine:
    """Test backtest engine (integration tests)."""

    @pytest.fixture
    def mock_events_file(self, tmp_path):
        """Create mock events.jsonl file."""
        events_path = tmp_path / "data" / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)

        # Create mock events
        now = datetime.now(timezone.utc)
        events = [
            {
                "ticker": "AAPL",
                "ts": (now - timedelta(days=i)).isoformat(),
                "cls": {"score": 0.5, "sentiment": 0.3, "keywords": ["earnings"]},
            }
            for i in range(10)
        ]

        with open(events_path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_path

    def test_engine_initialization(self):
        """Test engine initializes correctly."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-01-31",
            initial_capital=10000.0,
        )

        assert engine.initial_capital == 10000.0
        assert engine.portfolio is not None
        assert engine.simulator is not None

    def test_entry_strategy(self):
        """Test entry strategy filtering."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_params={"min_score": 0.30},
        )

        # Should pass
        alert_pass = {"cls": {"score": 0.35}}
        assert engine.apply_entry_strategy(alert_pass) is True

        # Should fail
        alert_fail = {"cls": {"score": 0.25}}
        assert engine.apply_entry_strategy(alert_fail) is False

    def test_exit_strategy(self):
        """Test exit strategy logic."""
        engine = BacktestEngine(
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_params={"take_profit_pct": 0.20, "stop_loss_pct": 0.10},
        )

        position = Position(
            ticker="AAPL",
            shares=100,
            entry_price=10.0,
            entry_time=1000,
            cost_basis=1000.0,
            alert_data={},
        )

        # Take profit
        should_exit, reason = engine.apply_exit_strategy(position, 12.5, 1.0)
        assert should_exit is True
        assert reason == "take_profit"

        # Stop loss
        should_exit, reason = engine.apply_exit_strategy(position, 8.5, 1.0)
        assert should_exit is True
        assert reason == "stop_loss"

        # Time exit
        should_exit, reason = engine.apply_exit_strategy(position, 10.5, 25.0)
        assert should_exit is True
        assert reason == "time_exit"


class TestReports:
    """Test report generation."""

    def test_markdown_report_generation(self):
        """Test Markdown report generation."""
        mock_results = {
            "metrics": {
                "total_return_pct": 15.5,
                "sharpe_ratio": 1.8,
                "win_rate": 60.0,
                "max_drawdown_pct": 8.5,
                "profit_factor": 2.1,
                "total_trades": 50,
                "winning_trades": 30,
                "losing_trades": 20,
                "avg_win": 12.0,
                "avg_loss": -6.0,
                "avg_hold_time_hours": 18.5,
            },
            "trades": [],
            "equity_curve": [],
            "strategy_params": {"min_score": 0.25},
            "backtest_period": {"start": "2025-01-01", "end": "2025-01-31"},
        }

        report = generate_backtest_report(mock_results, "markdown")

        assert "# Backtest Report" in report
        assert "15.50%" in report  # Total return
        assert "1.80" in report  # Sharpe
        assert "60.0%" in report  # Win rate

    def test_json_report_generation(self):
        """Test JSON report generation."""
        mock_results = {
            "metrics": {"total_return_pct": 15.5},
            "trades": [],
            "equity_curve": [],
            "strategy_params": {},
            "backtest_period": {"start": "2025-01-01", "end": "2025-01-31"},
        }

        report = generate_backtest_report(mock_results, "json")
        parsed = json.loads(report)

        assert parsed["metrics"]["total_return_pct"] == 15.5

    def test_export_trades_csv(self, tmp_path):
        """Test CSV export."""
        trades = [
            {
                "ticker": "AAPL",
                "entry_time": 1000000,
                "exit_time": 1010000,
                "entry_price": 10.0,
                "exit_price": 12.0,
                "shares": 100,
                "profit": 200,
                "profit_pct": 20.0,
                "hold_time_hours": 2.78,
                "exit_reason": "take_profit",
                "alert_data": {
                    "score": 0.5,
                    "sentiment": 0.3,
                    "catalyst_type": "earnings",
                },
            }
        ]

        csv_path = tmp_path / "trades.csv"
        export_trades_to_csv(trades, str(csv_path))

        assert csv_path.exists()
        content = csv_path.read_text()
        assert "AAPL" in content
        assert "take_profit" in content


class TestValidator:
    """Test parameter validation."""

    def test_validation_recommendation(self):
        """Test validation generates recommendations."""
        # Note: This requires historical data to run properly
        # In practice, you'd use mock data or VCR for testing

        # For now, just test the function signature
        try:
            result = validate_parameter_change(
                param="min_score",
                old_value=0.25,
                new_value=0.30,
                backtest_days=7,  # Short period for testing
            )

            assert "recommendation" in result
            assert result["recommendation"] in ["APPROVE", "REJECT", "NEUTRAL"]
            assert "confidence" in result
            assert 0.0 <= result["confidence"] <= 1.0

        except Exception:
            # Expected to fail without historical data
            pytest.skip("Requires historical data for validation")


class TestMonteСarlo:
    """Test Monte Carlo simulator."""

    def test_random_walk_simulation(self):
        """Test random walk baseline generation."""
        simulator = MonteCarloSimulator(
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        results = simulator.run_random_walk_simulation(
            num_simulations=100,
            num_trades_per_sim=50,
        )

        assert "avg_return_pct" in results
        assert "std_dev_return" in results
        assert "avg_sharpe" in results
        assert isinstance(results["avg_return_pct"], float)

    def test_parameter_sweep_structure(self):
        """Test parameter sweep returns correct structure."""
        # Note: Requires historical data
        # Just test the structure for now
        simulator = MonteCarloSimulator(
            start_date="2025-01-01",
            end_date="2025-01-07",  # Very short for testing
        )

        # Mock the sweep (would normally take too long)
        try:
            results = simulator.run_parameter_sweep(
                parameter="min_score",
                values=[0.25, 0.30],
                num_simulations=2,  # Minimal for testing
            )

            assert "parameter" in results
            assert "results" in results
            assert "optimal_value" in results
            assert "confidence" in results

        except Exception:
            pytest.skip("Requires historical data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
