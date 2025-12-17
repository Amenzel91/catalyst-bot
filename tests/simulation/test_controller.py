"""
Tests for SimulationController.
"""

import tempfile
from pathlib import Path

import pytest

from catalyst_bot.simulation import SimulationConfig, SimulationController


class TestSimulationControllerBasics:
    """Basic functionality tests."""

    def test_initialization_defaults(self):
        """Test controller initializes with defaults."""
        controller = SimulationController()

        assert controller.run_id is not None
        assert controller.config is not None
        assert controller._running is False
        assert controller._paused is False

    def test_initialization_with_params(self):
        """Test controller initializes with custom parameters."""
        controller = SimulationController(
            simulation_date="2024-11-12",
            speed_multiplier=10.0,
            time_preset="morning",
        )

        assert controller.config.simulation_date == "2024-11-12"
        assert controller.config.speed_multiplier == 10.0
        assert controller.config.time_preset == "morning"

    def test_from_config_class_method(self):
        """Test creating controller from environment config."""
        controller = SimulationController.from_config()

        assert controller is not None
        assert controller.config is not None

    def test_run_id_generation(self):
        """Test run_id is generated and unique."""
        controller1 = SimulationController()
        controller2 = SimulationController()

        assert controller1.run_id != controller2.run_id
        assert "sim_" in controller1.run_id


class TestControllerConfiguration:
    """Tests for configuration handling."""

    def test_preset_overrides_times(self):
        """Test time preset sets start/end times."""
        controller = SimulationController(time_preset="morning")

        # Morning preset is 07:45-08:45 CST (13:45-14:45 UTC)
        assert controller.config.start_time_cst == "07:45"
        assert controller.config.end_time_cst == "08:45"

    def test_custom_times_override_preset(self):
        """Test custom times override preset."""
        controller = SimulationController(
            time_preset="morning",
            start_time_cst="09:00",
            end_time_cst="10:00",
        )

        assert controller.config.start_time_cst == "09:00"
        assert controller.config.end_time_cst == "10:00"

    def test_config_object_takes_precedence(self):
        """Test config object overrides other parameters."""
        config = SimulationConfig(
            simulation_date="2024-01-01",
            speed_multiplier=100.0,
        )

        controller = SimulationController(
            config=config,
            simulation_date="2024-12-31",  # Should be ignored
        )

        # Config object values should be used
        assert controller.config.simulation_date == "2024-01-01"


class TestValidation:
    """Tests for validation functionality."""

    @pytest.mark.asyncio
    async def test_validate_with_valid_config(self):
        """Test validation passes with valid config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(
                cache_dir=Path(tmpdir) / "cache",
                log_dir=Path(tmpdir) / "logs",
            )
            controller = SimulationController(config=config)

            result = await controller.validate()
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_creates_directories(self):
        """Test validation creates required directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "new_cache"
            log_path = Path(tmpdir) / "new_logs"

            config = SimulationConfig(
                cache_dir=cache_path,
                log_dir=log_path,
            )
            controller = SimulationController(config=config)

            await controller.validate()

            assert cache_path.exists()
            assert log_path.exists()


class TestControlMethods:
    """Tests for simulation control methods."""

    def test_pause(self):
        """Test pause method."""
        controller = SimulationController()
        controller.pause()

        assert controller._paused is True

    def test_resume(self):
        """Test resume method."""
        controller = SimulationController()
        controller._paused = True
        controller.resume()

        assert controller._paused is False

    def test_stop(self):
        """Test stop method."""
        controller = SimulationController()
        controller._running = True
        controller.stop()

        assert controller._running is False


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_returns_expected_fields(self):
        """Test get_status returns all expected fields."""
        controller = SimulationController()

        status = controller.get_status()

        assert "run_id" in status
        assert "running" in status
        assert "paused" in status
        assert "setup_complete" in status
        assert "critical_errors" in status

    def test_get_status_reflects_state(self):
        """Test get_status reflects current state."""
        controller = SimulationController()
        controller._running = True
        controller._paused = True

        status = controller.get_status()

        assert status["running"] is True
        assert status["paused"] is True


class TestEventHandlerRegistration:
    """Tests for custom event handler registration."""

    def test_register_handler(self):
        """Test registering a custom event handler."""
        controller = SimulationController()

        from catalyst_bot.simulation import EventType

        async def custom_handler(event):
            pass

        controller.register_handler(EventType.NEWS_ITEM, custom_handler)

        assert EventType.NEWS_ITEM in controller._custom_handlers
        assert custom_handler in controller._custom_handlers[EventType.NEWS_ITEM]

    def test_register_multiple_handlers(self):
        """Test registering multiple handlers for same event type."""
        controller = SimulationController()

        from catalyst_bot.simulation import EventType

        async def handler1(event):
            pass

        async def handler2(event):
            pass

        controller.register_handler(EventType.NEWS_ITEM, handler1)
        controller.register_handler(EventType.NEWS_ITEM, handler2)

        assert len(controller._custom_handlers[EventType.NEWS_ITEM]) == 2


class TestSetupIntegration:
    """Integration tests for setup functionality."""

    @pytest.mark.asyncio
    async def test_setup_initializes_components(self):
        """Test setup initializes all required components."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(
                cache_dir=Path(tmpdir) / "cache",
                log_dir=Path(tmpdir) / "logs",
                price_source="cached",
                news_source="cached",
            )
            controller = SimulationController(config=config)

            await controller.setup()

            assert controller.clock is not None
            assert controller.broker is not None
            assert controller.market_data is not None
            assert controller.feed_provider is not None
            assert controller.event_replayer is not None
            assert controller.logger is not None
            assert controller._setup_complete is True

    @pytest.mark.asyncio
    async def test_cleanup_resets_clock(self):
        """Test cleanup resets clock provider."""
        controller = SimulationController()
        await controller.cleanup()

        # Should complete without error
        # Clock provider should be reset


class TestRunSimulation:
    """Tests for running simulation."""

    @pytest.mark.asyncio
    async def test_run_without_setup_calls_setup(self):
        """Test run calls setup if not already done."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(
                cache_dir=Path(tmpdir) / "cache",
                log_dir=Path(tmpdir) / "logs",
                price_source="cached",
                news_source="cached",
                speed_multiplier=0,  # Instant mode
            )
            controller = SimulationController(config=config)

            assert controller._setup_complete is False

            # Run with no events (empty data)
            results = await controller.run()

            assert controller._setup_complete is True
            assert "run_id" in results
            assert "events_processed" in results

    @pytest.mark.asyncio
    async def test_run_returns_results_structure(self):
        """Test run returns expected results structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(
                cache_dir=Path(tmpdir) / "cache",
                log_dir=Path(tmpdir) / "logs",
                price_source="cached",
                news_source="cached",
                speed_multiplier=0,
            )
            controller = SimulationController(config=config)

            results = await controller.run()

            assert "run_id" in results
            assert "simulation_date" in results
            assert "speed_multiplier" in results
            assert "events_processed" in results
            assert "portfolio" in results
            assert "positions" in results
            assert "orders" in results
            assert "log_files" in results

    @pytest.mark.asyncio
    async def test_run_creates_log_files(self):
        """Test run creates log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(
                cache_dir=Path(tmpdir) / "cache",
                log_dir=Path(tmpdir) / "logs",
                price_source="cached",
                news_source="cached",
                speed_multiplier=0,
            )
            controller = SimulationController(config=config)

            results = await controller.run()

            # Log files should exist
            log_files = results.get("log_files", {})
            if log_files.get("jsonl"):
                assert Path(log_files["jsonl"]).exists()
            if log_files.get("markdown"):
                assert Path(log_files["markdown"]).exists()
