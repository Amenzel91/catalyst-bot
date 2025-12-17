"""
Tests for SimulationConfig.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch

from catalyst_bot.simulation import TIME_PRESETS, SimulationConfig


class TestSimulationConfigBasics:
    """Basic configuration tests."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SimulationConfig()

        assert config.enabled is False
        assert config.simulation_date == "2024-11-12"
        assert config.speed_multiplier == 6.0
        assert config.starting_cash == 10000.0
        assert config.llm_enabled is True
        assert config.charts_enabled is False

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SimulationConfig(
            enabled=True,
            simulation_date="2024-01-15",
            speed_multiplier=10.0,
            starting_cash=50000.0,
        )

        assert config.enabled is True
        assert config.simulation_date == "2024-01-15"
        assert config.speed_multiplier == 10.0
        assert config.starting_cash == 50000.0


class TestTimePresets:
    """Tests for time presets."""

    def test_all_presets_exist(self):
        """Test all expected presets are defined."""
        expected_presets = ["morning", "sec", "open", "close", "full"]
        for preset in expected_presets:
            assert preset in TIME_PRESETS

    def test_preset_has_required_keys(self):
        """Test each preset has start and end times."""
        for name, preset in TIME_PRESETS.items():
            assert "start" in preset, f"Preset {name} missing 'start'"
            assert "end" in preset, f"Preset {name} missing 'end'"

    def test_apply_preset_sets_times(self):
        """Test apply_preset sets start and end times."""
        config = SimulationConfig(time_preset="morning")
        config.apply_preset()

        assert config.start_time_cst == "07:45"
        assert config.end_time_cst == "08:45"

    def test_apply_preset_no_effect_without_preset(self):
        """Test apply_preset does nothing without preset."""
        config = SimulationConfig(
            start_time_cst="10:00",
            end_time_cst="11:00",
        )
        config.apply_preset()

        # Should keep original values
        assert config.start_time_cst == "10:00"
        assert config.end_time_cst == "11:00"

    def test_apply_preset_invalid_preset_ignored(self):
        """Test invalid preset is ignored."""
        config = SimulationConfig(time_preset="invalid")
        config.apply_preset()

        assert config.start_time_cst is None
        assert config.end_time_cst is None


class TestGetSimulationDate:
    """Tests for get_simulation_date method."""

    def test_returns_specified_date(self):
        """Test returns the specified simulation date."""
        config = SimulationConfig(simulation_date="2024-11-12")
        date = config.get_simulation_date()

        assert date.year == 2024
        assert date.month == 11
        assert date.day == 12
        assert date.tzinfo == timezone.utc

    def test_random_date_when_not_specified(self):
        """Test picks random trading day when date is None."""
        config = SimulationConfig(simulation_date=None)
        date = config.get_simulation_date()

        # Should be a weekday (Monday=0 to Friday=4)
        assert date.weekday() < 5
        assert date.tzinfo == timezone.utc


class TestGetStartEndTime:
    """Tests for get_start_time and get_end_time."""

    def test_start_time_from_cst(self):
        """Test start time conversion from CST."""
        config = SimulationConfig(start_time_cst="08:30")
        sim_date = datetime(2024, 11, 12, 0, 0, 0, tzinfo=timezone.utc)

        start = config.get_start_time(sim_date)

        # 08:30 CST = 14:30 UTC
        assert start.hour == 14
        assert start.minute == 30

    def test_end_time_from_cst(self):
        """Test end time conversion from CST."""
        config = SimulationConfig(end_time_cst="15:00")
        sim_date = datetime(2024, 11, 12, 0, 0, 0, tzinfo=timezone.utc)

        end = config.get_end_time(sim_date)

        # 15:00 CST = 21:00 UTC
        assert end.hour == 21
        assert end.minute == 0

    def test_default_start_time(self):
        """Test default start time when not specified."""
        config = SimulationConfig()
        sim_date = datetime(2024, 11, 12, 0, 0, 0, tzinfo=timezone.utc)

        start = config.get_start_time(sim_date)

        # Default is 9am UTC
        assert start.hour == 9
        assert start.minute == 0

    def test_default_end_time(self):
        """Test default end time when not specified."""
        config = SimulationConfig()
        sim_date = datetime(2024, 11, 12, 0, 0, 0, tzinfo=timezone.utc)

        end = config.get_end_time(sim_date)

        # Default is 10pm UTC
        assert end.hour == 22
        assert end.minute == 0


class TestGenerateRunId:
    """Tests for generate_run_id method."""

    def test_generates_unique_id(self):
        """Test generates unique run IDs."""
        config = SimulationConfig()

        id1 = config.generate_run_id()
        config.run_id = None  # Reset
        id2 = config.generate_run_id()

        assert id1.startswith("sim_")
        assert id2.startswith("sim_")
        # IDs should be different (uuid portion)
        assert id1 != id2

    def test_returns_existing_id_if_set(self):
        """Test returns existing run_id if already set."""
        config = SimulationConfig(run_id="custom_run_123")

        assert config.generate_run_id() == "custom_run_123"


class TestValidation:
    """Tests for configuration validation."""

    def test_valid_config_returns_empty_errors(self):
        """Test valid configuration returns no errors."""
        config = SimulationConfig(
            enabled=True,
            simulation_date="2024-11-12",
            speed_multiplier=6.0,
            time_preset="morning",
        )

        errors = config.validate()
        assert errors == []

    def test_invalid_date_format(self):
        """Test invalid date format is detected."""
        config = SimulationConfig(simulation_date="11-12-2024")  # Wrong format

        errors = config.validate()
        assert any("simulation_date" in e for e in errors)

    def test_invalid_time_format(self):
        """Test invalid time format is detected."""
        config = SimulationConfig(start_time_cst="8:30am")  # Wrong format

        errors = config.validate()
        assert any("start_time_cst" in e for e in errors)

    def test_invalid_preset(self):
        """Test invalid preset is detected."""
        config = SimulationConfig(time_preset="invalid_preset")

        errors = config.validate()
        assert any("time_preset" in e for e in errors)

    def test_negative_speed(self):
        """Test negative speed is detected."""
        config = SimulationConfig(speed_multiplier=-1.0)

        errors = config.validate()
        assert any("speed_multiplier" in e for e in errors)

    def test_invalid_slippage_model(self):
        """Test invalid slippage model is detected."""
        config = SimulationConfig(slippage_model="invalid")

        errors = config.validate()
        assert any("slippage_model" in e for e in errors)

    def test_invalid_alert_output(self):
        """Test invalid alert output is detected."""
        config = SimulationConfig(alert_output="invalid")

        errors = config.validate()
        assert any("alert_output" in e for e in errors)

    def test_invalid_percentages(self):
        """Test invalid percentages are detected."""
        config = SimulationConfig(slippage_pct=150.0)

        errors = config.validate()
        assert any("slippage_pct" in e for e in errors)

    def test_negative_cash(self):
        """Test negative cash is detected."""
        config = SimulationConfig(starting_cash=-1000.0)

        errors = config.validate()
        assert any("starting_cash" in e for e in errors)


class TestFromEnv:
    """Tests for from_env class method."""

    def test_loads_from_env(self):
        """Test loading config from environment variables."""
        env_vars = {
            "SIMULATION_MODE": "1",
            "SIMULATION_DATE": "2024-06-15",
            "SIMULATION_SPEED": "10.0",
            "SIMULATION_PRESET": "sec",
            "SIMULATION_STARTING_CASH": "25000.0",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = SimulationConfig.from_env()

        assert config.enabled is True
        assert config.simulation_date == "2024-06-15"
        assert config.speed_multiplier == 10.0
        assert config.time_preset == "sec"
        assert config.starting_cash == 25000.0

    def test_uses_defaults_when_env_not_set(self):
        """Test uses defaults when env vars not set."""
        # Clear simulation env vars
        env_clear = {k: "" for k in os.environ if k.startswith("SIMULATION_")}

        with patch.dict(os.environ, env_clear, clear=False):
            config = SimulationConfig.from_env()

        assert config.enabled is False
        assert config.speed_multiplier == 6.0


class TestToDict:
    """Tests for to_dict method."""

    def test_returns_dict(self):
        """Test to_dict returns a dictionary."""
        config = SimulationConfig()
        result = config.to_dict()

        assert isinstance(result, dict)

    def test_contains_all_fields(self):
        """Test to_dict contains all configuration fields."""
        config = SimulationConfig()
        result = config.to_dict()

        expected_keys = [
            "enabled",
            "simulation_date",
            "speed_multiplier",
            "start_time_cst",
            "end_time_cst",
            "time_preset",
            "starting_cash",
            "llm_enabled",
            "charts_enabled",
        ]

        for key in expected_keys:
            assert key in result

    def test_paths_converted_to_string(self):
        """Test Path objects are converted to strings."""
        config = SimulationConfig()
        result = config.to_dict()

        assert isinstance(result["cache_dir"], str)
        assert isinstance(result["db_path"], str)
        assert isinstance(result["log_dir"], str)
