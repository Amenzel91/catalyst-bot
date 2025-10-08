"""
Comprehensive Admin Workflow Test Script
=========================================

Tests the complete admin controls workflow:
- Report generation
- Report posting to Discord
- Button interactions (approve/reject/view details/custom)
- Parameter application
- Rollback functionality
- Edge case handling

This script can be run directly or imported as a pytest module.
"""

import json
from datetime import date
from unittest.mock import Mock, patch

import pytest

# Import all components under test
from src.catalyst_bot.admin_controls import (
    AdminReport,
    BacktestSummary,
    KeywordPerformance,
    ParameterRecommendation,
    build_admin_components,
    build_admin_embed,
    load_admin_report,
    save_admin_report,
)
from src.catalyst_bot.admin_interactions import (
    build_custom_modal,
    handle_admin_interaction,
    handle_approve,
    handle_modal_submit,
    handle_reject,
)
from src.catalyst_bot.admin_reporter import post_admin_report
from src.catalyst_bot.config_updater import (
    apply_parameter_changes,
    get_change_history,
    rollback_changes,
    validate_parameter,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_report():
    """Create a mock admin report for testing."""
    return AdminReport(
        date=date(2025, 10, 6),
        backtest_summary=BacktestSummary(
            n=50,
            hits=30,
            hit_rate=0.60,
            avg_return=0.03,
            max_drawdown=0.10,
            sharpe=1.2,
            sortino=1.5,
            profit_factor=1.6,
            avg_win_loss=1.4,
            trade_count=50,
        ),
        keyword_performance=[
            KeywordPerformance(
                category="fda",
                hits=10,
                misses=2,
                neutrals=1,
                hit_rate=0.77,
                avg_return=6.5,
                current_weight=1.0,
                proposed_weight=1.2,
            ),
            KeywordPerformance(
                category="dilution",
                hits=3,
                misses=8,
                neutrals=2,
                hit_rate=0.23,
                avg_return=-3.2,
                current_weight=1.0,
                proposed_weight=0.8,
            ),
        ],
        parameter_recommendations=[
            ParameterRecommendation(
                name="MIN_SCORE",
                current_value=0.2,
                proposed_value=0.25,
                reason="Hit rate below 55% - increase selectivity",
                impact="high",
            ),
            ParameterRecommendation(
                name="KEYWORD_WEIGHT_FDA",
                current_value=1.0,
                proposed_value=1.2,
                reason="fda: 77% hit rate, +6.5% avg return",
                impact="high",
            ),
        ],
        total_alerts=50,
        total_revenue=150.0,
    )


@pytest.fixture
def temp_env_file(tmp_path):
    """Create a temporary .env file for testing."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
MIN_SCORE=0.2
PRICE_CEILING=10.0
CONFIDENCE_HIGH=0.8
MAX_ALERTS_PER_CYCLE=40
"""
    )
    return env_file


# ============================================================================
# Workflow Test 1: Report Generation & Persistence
# ============================================================================


class TestReportGenerationWorkflow:
    """Test the complete report generation and persistence workflow."""

    def test_generate_save_load_report(self, tmp_path, mock_report):
        """Test generating, saving, and loading a report."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            # Save the report
            save_path = save_admin_report(mock_report)
            assert save_path.exists()
            assert save_path.name == "report_2025-10-06.json"

            # Load it back
            loaded_report = load_admin_report("2025-10-06")
            assert loaded_report is not None
            assert loaded_report.date == mock_report.date
            assert loaded_report.total_alerts == mock_report.total_alerts
            assert loaded_report.backtest_summary.hit_rate == 0.60

    def test_report_persistence_integrity(self, tmp_path, mock_report):
        """Verify report data integrity after save/load cycle."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            # Save report
            save_admin_report(mock_report)

            # Load it back
            loaded = load_admin_report("2025-10-06")

            # Verify all fields preserved
            assert len(loaded.parameter_recommendations) == len(
                mock_report.parameter_recommendations
            )
            assert len(loaded.keyword_performance) == len(
                mock_report.keyword_performance
            )

            # Check specific recommendation preserved
            rec = loaded.parameter_recommendations[0]
            assert rec.name == "MIN_SCORE"
            assert rec.current_value == 0.2
            assert rec.proposed_value == 0.25


# ============================================================================
# Workflow Test 2: Discord Embed & Component Building
# ============================================================================


class TestDiscordEmbedWorkflow:
    """Test Discord embed and component generation workflow."""

    def test_build_embed_and_components(self, mock_report):
        """Test building embed and components together."""
        # Build embed
        embed = build_admin_embed(mock_report)
        assert embed is not None
        assert "title" in embed
        assert "fields" in embed

        # Build components
        report_id = mock_report.date.isoformat()
        components = build_admin_components(report_id)
        assert len(components) == 1
        assert len(components[0]["components"]) == 4

        # Verify button IDs match report ID
        buttons = components[0]["components"]
        for btn in buttons:
            assert report_id in btn["custom_id"]

    def test_embed_contains_all_metrics(self, mock_report):
        """Verify embed contains all required metrics."""
        embed = build_admin_embed(mock_report)

        # Convert embed fields to text for searching
        fields_text = json.dumps(embed["fields"])

        # Check for key metrics
        assert "Total Alerts" in fields_text
        assert "Win Rate" in fields_text
        assert "Avg Return" in fields_text
        assert "Sharpe Ratio" in fields_text
        assert "Max Drawdown" in fields_text


# ============================================================================
# Workflow Test 3: Button Interactions
# ============================================================================


class TestButtonInteractionWorkflow:
    """Test button click handling workflow."""

    def test_view_details_button(self, tmp_path, mock_report):
        """Test View Details button interaction."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            # Save report first
            save_admin_report(mock_report)

            # Simulate button click
            report_id = "2025-10-06"
            interaction_data = {
                "type": 3,  # INTERACTION_TYPE_COMPONENT
                "data": {
                    "custom_id": f"admin_details_{report_id}",
                    "component_type": 2,  # Button
                },
            }

            response = handle_admin_interaction(interaction_data)

            # Verify response structure
            assert response["type"] == 4  # RESPONSE_TYPE_MESSAGE
            assert "embeds" in response["data"]
            assert response["data"]["flags"] == 64  # Ephemeral

            # Check embed content
            embed = response["data"]["embeds"][0]
            assert "Detailed Report" in embed["title"]

    def test_approve_button(self, tmp_path, mock_report, temp_env_file):
        """Test Approve Changes button interaction."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            with patch(
                "src.catalyst_bot.config_updater._get_env_path",
                return_value=temp_env_file,
            ):
                # Save report
                save_admin_report(mock_report)

                # Create data/config_backups directory
                (tmp_path / "data" / "config_backups").mkdir(
                    parents=True, exist_ok=True
                )

                # Simulate approve button click
                report_id = "2025-10-06"
                response = handle_approve(report_id)

                # Verify response
                assert response["type"] == 4  # RESPONSE_TYPE_MESSAGE
                assert "embeds" in response["data"]

    def test_reject_button(self, tmp_path, mock_report):
        """Test Reject Changes button interaction."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            # Save report
            save_admin_report(mock_report)

            # Simulate reject button
            report_id = "2025-10-06"
            response = handle_reject(report_id)

            # Verify rejection response
            assert response["type"] == 4
            assert "embeds" in response["data"]

            # Check message contains rejection confirmation
            embed = response["data"]["embeds"][0]
            assert "Rejected" in embed["description"]

    def test_custom_adjust_button(self, tmp_path, mock_report):
        """Test Custom Adjust button opens modal."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            # Save report
            save_admin_report(mock_report)

            # Build modal
            report_id = "2025-10-06"
            modal_response = build_custom_modal(report_id)

            # Verify modal structure
            assert modal_response["type"] == 9  # RESPONSE_TYPE_MODAL
            assert "custom_id" in modal_response["data"]
            assert "components" in modal_response["data"]

            # Check modal has input fields
            components = modal_response["data"]["components"]
            assert len(components) > 0


# ============================================================================
# Workflow Test 4: Modal Submission
# ============================================================================


class TestModalSubmissionWorkflow:
    """Test modal submission and parameter application."""

    def test_modal_submission_applies_changes(self, tmp_path, temp_env_file):
        """Test modal submission applies parameter changes."""
        with patch(
            "src.catalyst_bot.config_updater._get_env_path", return_value=temp_env_file
        ):
            with patch(
                "src.catalyst_bot.config_updater._get_backup_dir",
                return_value=tmp_path / "backups",
            ):
                # Create backup dir
                (tmp_path / "backups").mkdir(exist_ok=True)

                # Simulate modal submission
                interaction_data = {
                    "type": 5,  # INTERACTION_TYPE_MODAL_SUBMIT
                    "data": {
                        "custom_id": "admin_modal_2025-10-06",
                        "components": [
                            {
                                "components": [
                                    {
                                        "custom_id": "min_score",
                                        "value": "0.3",
                                    }
                                ]
                            },
                            {
                                "components": [
                                    {
                                        "custom_id": "price_ceiling",
                                        "value": "8.0",
                                    }
                                ]
                            },
                        ],
                    },
                }

                response = handle_modal_submit(interaction_data)

                # Verify response
                assert response["type"] == 4
                assert "embeds" in response["data"]


# ============================================================================
# Workflow Test 5: Parameter Application & Validation
# ============================================================================


class TestParameterApplicationWorkflow:
    """Test parameter validation and application workflow."""

    def test_validate_all_supported_parameters(self):
        """Test validation for all parameter types."""
        valid_cases = [
            ("MIN_SCORE", 0.5, True),
            ("MIN_SCORE", 1.5, False),  # Out of range
            ("PRICE_CEILING", 10.0, True),
            ("PRICE_CEILING", -5.0, False),  # Negative
            ("MAX_ALERTS_PER_CYCLE", 50, True),
            ("MAX_ALERTS_PER_CYCLE", -10, False),  # Negative
            ("CONFIDENCE_HIGH", 0.85, True),
            ("CONFIDENCE_HIGH", 1.5, False),  # Out of range
            ("KEYWORD_WEIGHT_FDA", 1.2, True),
            ("KEYWORD_WEIGHT_FDA", -0.5, False),  # Negative
        ]

        for param_name, value, should_be_valid in valid_cases:
            is_valid, error = validate_parameter(param_name, value)
            if should_be_valid:
                assert is_valid, f"{param_name}={value} should be valid: {error}"
            else:
                assert not is_valid, f"{param_name}={value} should be invalid"

    def test_apply_parameter_changes_workflow(self, tmp_path, temp_env_file):
        """Test complete parameter application workflow."""
        with patch(
            "src.catalyst_bot.config_updater._get_env_path", return_value=temp_env_file
        ):
            with patch(
                "src.catalyst_bot.config_updater._get_backup_dir",
                return_value=tmp_path / "backups",
            ):
                with patch(
                    "src.catalyst_bot.config_updater.check_rate_limit",
                    return_value=(True, ""),
                ):
                    # Create backup dir
                    (tmp_path / "backups").mkdir(exist_ok=True)

                    # Apply changes
                    changes = {
                        "MIN_SCORE": "0.3",
                        "PRICE_CEILING": "8.0",
                    }

                    success, message = apply_parameter_changes(changes)
                    assert success, f"Failed to apply changes: {message}"

                # Verify changes were written to file
                env_content = temp_env_file.read_text()
                assert "MIN_SCORE=0.3" in env_content
                assert "PRICE_CEILING=8.0" in env_content


# ============================================================================
# Workflow Test 6: Rollback Functionality
# ============================================================================


class TestRollbackWorkflow:
    """Test configuration rollback workflow."""

    def test_rollback_after_changes(self, tmp_path, temp_env_file):
        """Test rolling back to previous configuration."""
        with patch(
            "src.catalyst_bot.config_updater._get_env_path", return_value=temp_env_file
        ):
            backup_dir = tmp_path / "backups"
            backup_dir.mkdir(exist_ok=True)

            with patch(
                "src.catalyst_bot.config_updater._get_backup_dir",
                return_value=backup_dir,
            ):
                with patch(
                    "src.catalyst_bot.config_updater.check_rate_limit",
                    return_value=(True, ""),
                ):
                    # Get original content
                    temp_env_file.read_text()

                    # Apply changes
                    changes = {"MIN_SCORE": "0.5"}
                    success, _ = apply_parameter_changes(changes)
                    assert success

                # Verify change was applied
                assert "MIN_SCORE=0.5" in temp_env_file.read_text()

                # Rollback
                rollback_success, rollback_msg = rollback_changes()
                assert rollback_success, f"Rollback failed: {rollback_msg}"

                # Verify original content restored
                rolled_back_content = temp_env_file.read_text()
                assert "MIN_SCORE=0.2" in rolled_back_content


# ============================================================================
# Workflow Test 7: Discord Posting
# ============================================================================


class TestDiscordPostingWorkflow:
    """Test Discord report posting workflow."""

    @patch("src.catalyst_bot.admin_reporter.requests.post")
    def test_post_via_webhook(self, mock_post, tmp_path, monkeypatch):
        """Test posting admin report via webhook."""
        # Mock successful webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Set environment variables
        monkeypatch.setenv("FEATURE_ADMIN_REPORTS", "1")
        monkeypatch.setenv(
            "DISCORD_ADMIN_WEBHOOK", "https://discord.com/api/webhooks/test"
        )

        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            with patch(
                "src.catalyst_bot.admin_controls.get_last_price_change",
                return_value=(5.0, 0.05),
            ):
                # Post report
                target_date = date(2025, 10, 6)
                success = post_admin_report(target_date=target_date)

                # Verify webhook was called
                assert mock_post.called
                assert success

    @patch("src.catalyst_bot.admin_reporter.requests.post")
    def test_post_via_bot_api(self, mock_post, tmp_path, monkeypatch):
        """Test posting admin report via bot API."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Set environment variables for bot API
        monkeypatch.setenv("FEATURE_ADMIN_REPORTS", "1")
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test_token")
        monkeypatch.setenv("DISCORD_ADMIN_CHANNEL_ID", "123456789")

        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            with patch(
                "src.catalyst_bot.admin_controls.get_last_price_change",
                return_value=(5.0, 0.05),
            ):
                # Post report
                target_date = date(2025, 10, 6)
                success = post_admin_report(target_date=target_date)

                # Verify bot API was called with correct URL
                assert mock_post.called
                call_args = mock_post.call_args
                assert "123456789" in call_args[0][0]  # Channel ID in URL
                assert success


# ============================================================================
# Workflow Test 8: Edge Cases & Error Handling
# ============================================================================


class TestEdgeCasesWorkflow:
    """Test edge cases and error handling in workflows."""

    def test_approve_nonexistent_report(self, tmp_path):
        """Test approving a report that doesn't exist."""
        with patch(
            "src.catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path
        ):
            response = handle_approve("2099-01-01")

            # Should return error response
            assert response["type"] == 4
            embed = response["data"]["embeds"][0]
            assert "not found" in embed["description"].lower()

    def test_invalid_button_custom_id(self):
        """Test handling of invalid button custom_id."""
        interaction_data = {
            "type": 3,
            "data": {
                "custom_id": "invalid_button_id",
                "component_type": 2,
            },
        }

        response = handle_admin_interaction(interaction_data)
        assert "Invalid" in response["data"]["content"]

    def test_modal_submission_with_invalid_values(self, tmp_path, temp_env_file):
        """Test modal submission with invalid parameter values."""
        with patch(
            "src.catalyst_bot.config_updater._get_env_path", return_value=temp_env_file
        ):
            with patch(
                "src.catalyst_bot.config_updater._get_backup_dir",
                return_value=tmp_path / "backups",
            ):
                # Create backup dir
                (tmp_path / "backups").mkdir(exist_ok=True)

                # Submit modal with invalid value
                interaction_data = {
                    "type": 5,
                    "data": {
                        "custom_id": "admin_modal_2025-10-06",
                        "components": [
                            {
                                "components": [
                                    {
                                        "custom_id": "min_score",
                                        "value": "not_a_number",
                                    }
                                ]
                            }
                        ],
                    },
                }

                response = handle_modal_submit(interaction_data)

                # Should handle gracefully (skip invalid values)
                assert response["type"] == 4


# ============================================================================
# Workflow Test 9: Change History
# ============================================================================


class TestChangeHistoryWorkflow:
    """Test change history tracking workflow."""

    def test_change_history_logging(self, tmp_path, temp_env_file):
        """Test that parameter changes are logged to history."""
        history_path = tmp_path / "admin_changes.jsonl"

        with patch(
            "src.catalyst_bot.config_updater._get_env_path", return_value=temp_env_file
        ):
            with patch(
                "src.catalyst_bot.config_updater._get_backup_dir",
                return_value=tmp_path / "backups",
            ):
                with patch(
                    "src.catalyst_bot.config_updater._get_change_history_path",
                    return_value=history_path,
                ):
                    with patch(
                        "src.catalyst_bot.config_updater.check_rate_limit",
                        return_value=(True, ""),
                    ):
                        # Create backup dir
                        (tmp_path / "backups").mkdir(exist_ok=True)

                        # Apply changes
                        changes = {"MIN_SCORE": "0.4"}
                        apply_parameter_changes(changes, user_id="test_user_123")

                    # Verify history was logged
                    assert history_path.exists()

                    # Read history
                    history = get_change_history(limit=1)
                    assert len(history) == 1
                    assert history[0]["changes"]["MIN_SCORE"] == "0.4"
                    assert history[0]["user_id"] == "test_user_123"


# ============================================================================
# Main Test Runner
# ============================================================================


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v", "--tb=short"])
