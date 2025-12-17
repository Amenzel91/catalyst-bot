"""
Tests for SimulationLogger.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from catalyst_bot.simulation import Severity, SimulationLogger


class TestSimulationLoggerBasics:
    """Basic functionality tests."""

    def test_initialization(self):
        """Test logger initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test_run_123",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            assert logger.run_id == "test_run_123"
            assert logger.simulation_date == "2024-11-12"
            assert logger.jsonl_path.exists()
            assert logger.md_path.exists()

    def test_creates_log_directory(self):
        """Test log directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "new_logs"

            _logger = SimulationLogger(  # noqa: F841
                run_id="test",
                log_dir=log_path,
                simulation_date="2024-11-12",
            )

            assert log_path.exists()

    def test_file_naming(self):
        """Test log files are named correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="sim_abc123",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            assert logger.jsonl_path.name == "sim_abc123.jsonl"
            assert logger.md_path.name == "sim_abc123.md"


class TestEventLogging:
    """Tests for event logging functionality."""

    def test_log_event_writes_jsonl(self):
        """Test log_event writes to JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_event("test_event", {"key": "value"})

            with open(logger.jsonl_path) as f:
                lines = f.readlines()

            assert len(lines) == 1
            event = json.loads(lines[0])
            assert event["event_type"] == "test_event"
            assert event["key"] == "value"
            assert event["run_id"] == "test"

    def test_log_event_with_severity(self):
        """Test log_event includes severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_event(
                "warning_event",
                {"message": "test warning"},
                severity=Severity.WARNING,
            )

            with open(logger.jsonl_path) as f:
                event = json.loads(f.readline())

            assert event["severity"] == "WARNING"

    def test_log_event_with_sim_time(self):
        """Test log_event includes simulation time."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            sim_time = datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc)
            logger.log_event("test", {"data": "value"}, sim_time=sim_time)

            with open(logger.jsonl_path) as f:
                event = json.loads(f.readline())

            assert "sim_time" in event
            assert "2024-11-12" in event["sim_time"]


class TestSpecificLogMethods:
    """Tests for specific logging methods."""

    def test_log_alert(self):
        """Test log_alert method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            sim_time = datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc)
            logger.log_alert(
                ticker="AAPL",
                headline="Breaking News",
                classification="bullish",
                confidence=0.85,
                sim_time=sim_time,
                score=75.0,
            )

            assert len(logger.alerts_fired) == 1
            alert = logger.alerts_fired[0]
            assert alert["ticker"] == "AAPL"
            assert alert["classification"] == "bullish"
            assert alert["confidence"] == 0.85

    def test_log_trade(self):
        """Test log_trade method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            sim_time = datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc)
            logger.log_trade(
                ticker="AAPL",
                side="buy",
                quantity=100,
                price=150.50,
                sim_time=sim_time,
            )

            assert len(logger.trades_executed) == 1
            trade = logger.trades_executed[0]
            assert trade["ticker"] == "AAPL"
            assert trade["side"] == "buy"
            assert trade["quantity"] == 100
            assert trade["price"] == 150.50

    def test_log_skip(self):
        """Test log_skip method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_skip(ticker="AAPL", reason="No price data")

            assert len(logger.skipped_tickers) == 1
            skip = logger.skipped_tickers[0]
            assert skip["ticker"] == "AAPL"
            assert skip["reason"] == "No price data"

    def test_log_warning(self):
        """Test log_warning method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_warning("Something unexpected happened")

            assert len(logger.warnings) == 1
            assert logger.warnings[0]["message"] == "Something unexpected happened"

    def test_log_error(self):
        """Test log_error method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_error("Critical failure", context={"code": 500})

            assert len(logger.errors) == 1
            assert logger.errors[0]["message"] == "Critical failure"
            assert logger.errors[0]["code"] == 500

    def test_log_price_update(self):
        """Test log_price_update method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_price_update("AAPL", 150.50, volume=1000000)

            assert logger.price_updates == 1

    def test_log_news(self):
        """Test log_news method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_news("news_123", "Breaking news headline")

            assert logger.news_events == 1

    def test_log_sec_filing(self):
        """Test log_sec_filing method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_sec_filing("AAPL", "8-K")

            assert logger.sec_events == 1


class TestFinalize:
    """Tests for finalize functionality."""

    def test_finalize_writes_markdown(self):
        """Test finalize writes markdown summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            # Log some events
            sim_time = datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc)
            logger.log_alert("AAPL", "News", "bullish", 0.85, sim_time)
            logger.log_trade("AAPL", "buy", 100, 150.0, sim_time)
            logger.log_warning("Test warning")

            # Finalize
            portfolio_stats = {
                "starting_cash": 10000.0,
                "total_value": 10500.0,
                "total_return": 500.0,
                "total_return_pct": 5.0,
                "total_trades": 1,
                "win_rate": 100.0,
                "max_drawdown_pct": 1.5,
            }
            logger.finalize(portfolio_stats)

            # Check markdown file
            md_content = logger.md_path.read_text()

            assert "Quick Glance" in md_content
            assert "Portfolio Summary" in md_content
            assert "Alerts Fired" in md_content
            assert "$10,000.00" in md_content
            assert "$10,500.00" in md_content

    def test_finalize_includes_errors_section(self):
        """Test finalize includes errors section when errors exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            logger.log_error("Critical error occurred")
            logger.finalize({"starting_cash": 10000.0, "total_value": 10000.0})

            md_content = logger.md_path.read_text()
            assert "Errors (CRITICAL)" in md_content
            assert "Critical error occurred" in md_content


class TestGetSummary:
    """Tests for get_summary method."""

    def test_get_summary_returns_counts(self):
        """Test get_summary returns correct counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SimulationLogger(
                run_id="test",
                log_dir=Path(tmpdir),
                simulation_date="2024-11-12",
            )

            sim_time = datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc)

            # Log various events
            logger.log_alert("AAPL", "News", "bullish", 0.85, sim_time)
            logger.log_alert("TSLA", "News", "bearish", 0.75, sim_time)
            logger.log_trade("AAPL", "buy", 100, 150.0, sim_time)
            logger.log_warning("Warning 1")
            logger.log_warning("Warning 2")
            logger.log_error("Error")
            logger.log_price_update("AAPL", 150.0)
            logger.log_price_update("AAPL", 151.0)
            logger.log_price_update("AAPL", 152.0)

            summary = logger.get_summary()

            assert summary["run_id"] == "test"
            assert summary["simulation_date"] == "2024-11-12"
            assert summary["alerts_fired"] == 2
            assert summary["trades_executed"] == 1
            assert summary["warnings"] == 2
            assert summary["errors"] == 1
            assert summary["price_updates"] == 3
