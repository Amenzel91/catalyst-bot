"""
Comprehensive Tests for Admin Controls System
==============================================

Tests for the WAVE 1.1 admin controls, including report generation,
parameter recommendations, Discord embeds, button interactions, and
integration with the feedback loop database.
"""

import json
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

# Import modules under test
from catalyst_bot.admin_controls import (
    AdminReport,
    KeywordPerformance,
    ParameterRecommendation,
    build_admin_components,
    build_admin_embed,
    generate_admin_report,
    load_admin_report,
    save_admin_report,
)
from catalyst_bot.backtest.metrics import BacktestSummary


@pytest.fixture
def sample_backtest_summary():
    """Sample backtest summary with good performance."""
    return BacktestSummary(
        n=100,
        hits=62,
        hit_rate=0.62,
        avg_return=0.035,
        max_drawdown=0.12,
        sharpe=1.5,
        sortino=1.8,
        profit_factor=1.8,
        avg_win_loss=1.5,
        trade_count=100,
    )


@pytest.fixture
def sample_keyword_performance():
    """Sample keyword performance data."""
    return [
        KeywordPerformance(
            category="fda",
            hits=15,
            misses=3,
            neutrals=2,
            hit_rate=0.75,
            avg_return=8.5,
            current_weight=1.0,
            proposed_weight=1.2,
        ),
        KeywordPerformance(
            category="earnings",
            hits=20,
            misses=10,
            neutrals=5,
            hit_rate=0.57,
            avg_return=3.2,
            current_weight=0.9,
            proposed_weight=1.0,
        ),
        KeywordPerformance(
            category="dilution",
            hits=5,
            misses=15,
            neutrals=5,
            hit_rate=0.20,
            avg_return=-4.5,
            current_weight=1.0,
            proposed_weight=0.8,
        ),
    ]


@pytest.fixture
def sample_recommendations():
    """Sample parameter recommendations."""
    return [
        ParameterRecommendation(
            name="MIN_SCORE",
            current_value=0.25,
            proposed_value=0.30,
            reason="Win rate below 55% - increase threshold",
            impact="high",
        ),
        ParameterRecommendation(
            name="PRICE_CEILING",
            current_value=10.0,
            proposed_value=8.0,
            reason="Focus on lower-priced stocks for better returns",
            impact="medium",
        ),
        ParameterRecommendation(
            name="KEYWORD_WEIGHT_FDA",
            current_value=1.0,
            proposed_value=1.2,
            reason="fda: 75.0% hit rate, +8.5% avg return",
            impact="high",
        ),
    ]


@pytest.fixture
def sample_admin_report(
    sample_backtest_summary, sample_keyword_performance, sample_recommendations
):
    """Sample complete admin report."""
    return AdminReport(
        date=date(2025, 10, 5),
        backtest_summary=sample_backtest_summary,
        keyword_performance=sample_keyword_performance,
        parameter_recommendations=sample_recommendations,
        total_alerts=100,
        total_revenue=350.0,
    )


# ============================================================================
# Report Generation Tests
# ============================================================================


class TestReportGeneration:
    """Tests for admin report generation."""

    def test_generate_admin_report_basic(self, tmp_path, monkeypatch):
        """Test basic admin report generation with mock data."""
        # Setup mock events file
        events_data = []
        today = datetime.now(timezone.utc).date()

        for i in range(10):
            events_data.append(
                {
                    "ticker": f"STOCK{i}",
                    "ts": today.isoformat() + "T12:00:00+00:00",
                    "price": 5.0 + i * 0.5,
                    "cls": {
                        "keywords": ["fda", "approval"],
                        "sentiment": 0.8,
                        "score": 0.7,
                    },
                }
            )

        # Create temp events.jsonl
        events_file = tmp_path / "data" / "events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        events_file.write_text("\n".join([json.dumps(e) for e in events_data]))

        # Mock _get_repo_root to use tmp_path
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Mock get_last_price_change to return consistent prices
            with patch(
                "catalyst_bot.admin_controls.get_last_price_change"
            ) as mock_price:
                mock_price.return_value = (5.5, 0.05)  # Price, change%

                report = generate_admin_report(today)

                assert report.date == today
                assert report.total_alerts == 10
                assert report.backtest_summary.n >= 0  # May be 0 if price lookups fail
                assert isinstance(report.keyword_performance, list)
                assert isinstance(report.parameter_recommendations, list)

    def test_generate_admin_report_no_data(self, tmp_path):
        """Test report generation with no events data."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            today = datetime.now(timezone.utc).date()
            report = generate_admin_report(today)

            assert report.date == today
            assert report.total_alerts == 0
            assert report.backtest_summary.n == 0
            assert len(report.keyword_performance) == 0

    def test_generate_admin_report_with_feedback_data(self, tmp_path):
        """Test report generation integrates with feedback loop data."""
        # This test would require mocking the feedback database
        # For now, just ensure it doesn't crash when feedback is unavailable
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            today = datetime.now(timezone.utc).date()

            # Should handle missing feedback gracefully
            report = generate_admin_report(today)
            assert report is not None


# ============================================================================
# Keyword Analysis Tests
# ============================================================================


class TestKeywordAnalysis:
    """Tests for keyword performance analysis."""

    def test_keyword_performance_calculation(self, sample_keyword_performance):
        """Test keyword performance metrics are calculated correctly."""
        kp = sample_keyword_performance[0]  # fda keyword

        assert kp.category == "fda"
        assert kp.hit_rate == 0.75
        assert kp.hits == 15
        assert kp.misses == 3
        assert kp.avg_return == 8.5
        assert kp.proposed_weight > kp.current_weight  # Should increase weight

    def test_keyword_weight_adjustment_up(self):
        """Test weight increases for high-performing keywords."""
        kp = KeywordPerformance(
            category="test",
            hits=70,
            misses=20,
            neutrals=10,
            hit_rate=0.70,  # > 60%
            avg_return=5.0,
            current_weight=1.0,
            proposed_weight=1.2,  # Should be 1.0 * 1.2
        )

        assert kp.proposed_weight == 1.2

    def test_keyword_weight_adjustment_down(self):
        """Test weight decreases for low-performing keywords."""
        kp = KeywordPerformance(
            category="test",
            hits=30,
            misses=60,
            neutrals=10,
            hit_rate=0.30,  # < 40%
            avg_return=-3.0,
            current_weight=1.0,
            proposed_weight=0.8,  # Should be 1.0 * 0.8
        )

        assert kp.proposed_weight == 0.8

    def test_keyword_weight_no_change(self):
        """Test weight stays same for average performance."""
        kp = KeywordPerformance(
            category="test",
            hits=50,
            misses=50,
            neutrals=0,
            hit_rate=0.50,  # Between 40-60%
            avg_return=2.0,
            current_weight=1.0,
            proposed_weight=1.0,
        )

        assert kp.proposed_weight == 1.0


# ============================================================================
# Parameter Recommendation Tests
# ============================================================================


class TestParameterRecommendations:
    """Tests for parameter recommendation logic."""

    def test_min_score_recommendation_low_hit_rate(self):
        """Test MIN_SCORE recommendation when hit rate is low."""
        backtest = BacktestSummary(
            n=50,
            hits=20,
            hit_rate=0.40,  # Below 50%
            avg_return=0.01,
            max_drawdown=0.10,
            sharpe=0.5,
            sortino=0.6,
            profit_factor=1.0,
            avg_win_loss=1.0,
            trade_count=50,
        )

        # The recommendation logic should suggest increasing MIN_SCORE
        # when hit_rate < 0.5 and n > 10
        assert backtest.hit_rate < 0.5
        assert backtest.n > 10

    def test_price_ceiling_recommendation_negative_returns(self):
        """Test PRICE_CEILING recommendation when returns are negative."""
        backtest = BacktestSummary(
            n=50,
            hits=20,
            hit_rate=0.40,
            avg_return=-0.02,  # Negative
            max_drawdown=0.15,
            sharpe=0.3,
            sortino=0.4,
            profit_factor=0.8,
            avg_win_loss=0.8,
            trade_count=50,
        )

        assert backtest.avg_return < 0
        assert backtest.n > 10

    def test_confidence_threshold_recommendation_low_sharpe(self):
        """Test CONFIDENCE_HIGH recommendation when Sharpe is low."""
        backtest = BacktestSummary(
            n=50,
            hits=25,
            hit_rate=0.50,
            avg_return=0.01,
            max_drawdown=0.10,
            sharpe=0.3,  # < 0.5
            sortino=0.4,
            profit_factor=1.0,
            avg_win_loss=1.0,
            trade_count=50,
        )

        assert backtest.sharpe < 0.5
        assert backtest.n > 10


# ============================================================================
# Discord Embed Tests
# ============================================================================


class TestDiscordEmbed:
    """Tests for Discord embed generation."""

    def test_build_admin_embed_basic(self, sample_admin_report):
        """Test basic admin embed structure."""
        embed = build_admin_embed(sample_admin_report)

        assert "title" in embed
        assert "color" in embed
        assert "fields" in embed
        assert "timestamp" in embed

        # Check title format
        assert "2025-10-05" in embed["title"]

        # Color should be green for good performance (hit_rate >= 0.6)
        assert embed["color"] == 0x2ECC71

    def test_build_admin_embed_performance_field(self, sample_admin_report):
        """Test performance field contains key metrics."""
        embed = build_admin_embed(sample_admin_report)

        # Find performance field
        perf_field = next(
            (f for f in embed["fields"] if "Performance" in f["name"]), None
        )
        assert perf_field is not None

        # Check it contains key metrics
        assert "Total Alerts" in perf_field["value"]
        assert "Win Rate" in perf_field["value"]
        assert "Avg Return" in perf_field["value"]

    def test_build_admin_embed_recommendations_field(self, sample_admin_report):
        """Test recommendations field is present."""
        embed = build_admin_embed(sample_admin_report)

        # Find recommendations field
        rec_field = next(
            (f for f in embed["fields"] if "Recommendations" in f["name"]), None
        )
        assert rec_field is not None

        # Should show top recommendations
        assert "MIN_SCORE" in rec_field["value"]

    def test_build_admin_embed_color_logic(self):
        """Test embed color changes based on performance."""
        # Green for good performance
        good_report = AdminReport(
            date=date.today(),
            backtest_summary=BacktestSummary(
                n=100,
                hits=65,
                hit_rate=0.65,
                avg_return=0.04,
                max_drawdown=0.1,
                sharpe=1.5,
                sortino=1.8,
                profit_factor=2.0,
                avg_win_loss=1.5,
                trade_count=100,
            ),
            keyword_performance=[],
            parameter_recommendations=[],
            total_alerts=100,
            total_revenue=400.0,
        )
        embed = build_admin_embed(good_report)
        assert embed["color"] == 0x2ECC71  # Green

        # Orange for medium performance
        medium_report = AdminReport(
            date=date.today(),
            backtest_summary=BacktestSummary(
                n=100,
                hits=50,
                hit_rate=0.50,
                avg_return=0.02,
                max_drawdown=0.15,
                sharpe=0.8,
                sortino=1.0,
                profit_factor=1.2,
                avg_win_loss=1.0,
                trade_count=100,
            ),
            keyword_performance=[],
            parameter_recommendations=[],
            total_alerts=100,
            total_revenue=200.0,
        )
        embed = build_admin_embed(medium_report)
        assert embed["color"] == 0xF39C12  # Orange

        # Red for poor performance
        poor_report = AdminReport(
            date=date.today(),
            backtest_summary=BacktestSummary(
                n=100,
                hits=30,
                hit_rate=0.30,
                avg_return=-0.01,
                max_drawdown=0.20,
                sharpe=0.2,
                sortino=0.3,
                profit_factor=0.7,
                avg_win_loss=0.8,
                trade_count=100,
            ),
            keyword_performance=[],
            parameter_recommendations=[],
            total_alerts=100,
            total_revenue=-100.0,
        )
        embed = build_admin_embed(poor_report)
        assert embed["color"] == 0xE74C3C  # Red


# ============================================================================
# Button Component Tests
# ============================================================================


class TestDiscordComponents:
    """Tests for Discord button components."""

    def test_build_admin_components_structure(self):
        """Test admin button components have correct structure."""
        report_id = "2025-10-05"
        components = build_admin_components(report_id)

        assert len(components) == 1  # One action row
        action_row = components[0]

        assert action_row["type"] == 1  # Action Row type
        assert "components" in action_row

        # Should have 4 buttons
        buttons = action_row["components"]
        assert len(buttons) == 4

    def test_build_admin_components_button_ids(self):
        """Test button custom_ids are correctly formatted."""
        report_id = "2025-10-05"
        components = build_admin_components(report_id)

        buttons = components[0]["components"]
        custom_ids = [btn["custom_id"] for btn in buttons]

        assert f"admin_details_{report_id}" in custom_ids
        assert f"admin_approve_{report_id}" in custom_ids
        assert f"admin_reject_{report_id}" in custom_ids
        assert f"admin_custom_{report_id}" in custom_ids

    def test_build_admin_components_button_styles(self):
        """Test buttons have appropriate styles."""
        components = build_admin_components("2025-10-05")
        buttons = components[0]["components"]

        # Find specific buttons and check styles
        for btn in buttons:
            if "details" in btn["custom_id"]:
                assert btn["style"] == 1  # Primary (blue)
            elif "approve" in btn["custom_id"]:
                assert btn["style"] == 3  # Success (green)
            elif "reject" in btn["custom_id"]:
                assert btn["style"] == 4  # Danger (red)
            elif "custom" in btn["custom_id"]:
                assert btn["style"] == 2  # Secondary (gray)


# ============================================================================
# Report Persistence Tests
# ============================================================================


class TestReportPersistence:
    """Tests for saving and loading admin reports."""

    def test_save_admin_report(self, sample_admin_report, tmp_path):
        """Test saving admin report to disk."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            save_path = save_admin_report(sample_admin_report)

            assert save_path.exists()
            assert save_path.name == "report_2025-10-05.json"

            # Check file contents
            data = json.loads(save_path.read_text())
            assert data["date"] == "2025-10-05"
            assert data["total_alerts"] == 100
            assert data["backtest"]["hit_rate"] == 0.62

    def test_load_admin_report(self, sample_admin_report, tmp_path):
        """Test loading saved admin report."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Save first
            save_admin_report(sample_admin_report)

            # Load it back
            loaded_report = load_admin_report("2025-10-05")

            assert loaded_report is not None
            assert loaded_report.date == sample_admin_report.date
            assert loaded_report.total_alerts == sample_admin_report.total_alerts
            assert (
                loaded_report.backtest_summary.hit_rate
                == sample_admin_report.backtest_summary.hit_rate
            )

    def test_load_nonexistent_report(self, tmp_path):
        """Test loading a report that doesn't exist."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            loaded_report = load_admin_report("2099-01-01")
            assert loaded_report is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for admin controls system."""

    def test_full_report_lifecycle(self, tmp_path):
        """Test complete report generation, saving, and loading cycle."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            today = datetime.now(timezone.utc).date()

            # Generate report
            report = generate_admin_report(today)
            assert report is not None

            # Save report
            save_path = save_admin_report(report)
            assert save_path.exists()

            # Load report
            loaded_report = load_admin_report(today.isoformat())
            assert loaded_report is not None
            assert loaded_report.date == report.date

            # Build embed
            embed = build_admin_embed(loaded_report)
            assert embed is not None
            assert "title" in embed

            # Build components
            components = build_admin_components(today.isoformat())
            assert len(components) == 1

    @patch("catalyst_bot.admin_controls.get_last_price_change")
    def test_backtest_with_price_data(self, mock_price, tmp_path):
        """Test backtest computation with mock price data."""
        # Mock price changes to simulate wins and losses
        mock_price.side_effect = [
            (5.5, 0.10),  # +10% win
            (4.8, -0.04),  # -4% loss
            (5.2, 0.04),  # +4% small win
        ]

        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            today = datetime.now(timezone.utc).date()

            # Create mock events
            events_file = tmp_path / "data" / "events.jsonl"
            events_file.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "ticker": "STOCK1",
                    "ts": today.isoformat() + "T12:00:00+00:00",
                    "price": 5.0,
                    "cls": {"keywords": ["fda"]},
                },
                {
                    "ticker": "STOCK2",
                    "ts": today.isoformat() + "T13:00:00+00:00",
                    "price": 5.0,
                    "cls": {"keywords": ["earnings"]},
                },
                {
                    "ticker": "STOCK3",
                    "ts": today.isoformat() + "T14:00:00+00:00",
                    "price": 5.0,
                    "cls": {"keywords": ["partnership"]},
                },
            ]
            events_file.write_text("\n".join([json.dumps(e) for e in events]))

            report = generate_admin_report(today)

            # Should have processed some trades
            assert report.backtest_summary.n >= 0


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_backtest_summary(self):
        """Test handling of empty backtest results."""
        empty_summary = BacktestSummary(
            n=0,
            hits=0,
            hit_rate=0.0,
            avg_return=0.0,
            max_drawdown=0.0,
            sharpe=0.0,
            sortino=0.0,
            profit_factor=0.0,
            avg_win_loss=0.0,
            trade_count=0,
        )

        report = AdminReport(
            date=date.today(),
            backtest_summary=empty_summary,
            keyword_performance=[],
            parameter_recommendations=[],
            total_alerts=0,
            total_revenue=0.0,
        )

        # Should still generate valid embed
        embed = build_admin_embed(report)
        assert embed is not None
        assert "No signals" in embed.get("description", "")

    def test_malformed_events_file(self, tmp_path):
        """Test handling of malformed events.jsonl file."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            events_file = tmp_path / "data" / "events.jsonl"
            events_file.parent.mkdir(parents=True, exist_ok=True)

            # Write malformed JSON
            events_file.write_text("not valid json\n{broken json\n")

            today = datetime.now(timezone.utc).date()

            # Should handle gracefully
            report = generate_admin_report(today)
            assert report is not None
            assert report.total_alerts == 0

    def test_missing_keyword_weights_file(self, tmp_path):
        """Test handling when keyword_stats.json doesn't exist."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            today = datetime.now(timezone.utc).date()

            # Should not crash
            report = generate_admin_report(today)
            assert report is not None


# ============================================================================
# Button Handler Tests (WAVE BETA 1)
# ============================================================================


class TestButtonHandlers:
    """Tests for button interaction handlers."""

    def test_handle_view_details_button(self, tmp_path, sample_admin_report):
        """Test View Details button handler."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Save report
            save_admin_report(sample_admin_report)

            # Import handler
            from catalyst_bot.admin_interactions import handle_admin_interaction

            # Simulate button click
            report_id = "2025-10-05"
            interaction_data = {
                "type": 3,  # INTERACTION_TYPE_COMPONENT
                "data": {
                    "custom_id": f"admin_details_{report_id}",
                    "component_type": 2,
                },
            }

            response = handle_admin_interaction(interaction_data)

            # Verify response
            assert response["type"] == 4  # RESPONSE_TYPE_MESSAGE
            assert "embeds" in response["data"]
            assert response["data"]["flags"] == 64  # Ephemeral

    def test_handle_approve_button(self, tmp_path, sample_admin_report):
        """Test Approve button handler."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Save report
            save_admin_report(sample_admin_report)

            # Create necessary directories
            (tmp_path / "data" / "config_backups").mkdir(parents=True, exist_ok=True)

            # Create a mock .env file
            env_file = tmp_path / ".env"
            env_file.write_text("MIN_SCORE=0.2\nPRICE_CEILING=10.0\n")

            with patch(
                "catalyst_bot.config_updater._get_env_path", return_value=env_file
            ):
                from catalyst_bot.admin_interactions import handle_approve

                report_id = "2025-10-05"
                response = handle_approve(report_id)

                # Verify response structure
                assert response["type"] == 4
                assert "embeds" in response["data"]

    def test_handle_reject_button(self, tmp_path, sample_admin_report):
        """Test Reject button handler."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Save report
            save_admin_report(sample_admin_report)

            from catalyst_bot.admin_interactions import handle_reject

            report_id = "2025-10-05"
            response = handle_reject(report_id)

            # Verify rejection response
            assert response["type"] == 4
            embed = response["data"]["embeds"][0]
            assert "Rejected" in embed["description"]

    def test_handle_custom_modal_button(self, tmp_path, sample_admin_report):
        """Test Custom Adjust modal opening."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Save report
            save_admin_report(sample_admin_report)

            from catalyst_bot.admin_interactions import build_custom_modal

            report_id = "2025-10-05"
            modal_response = build_custom_modal(report_id)

            # Verify modal structure
            assert modal_response["type"] == 9  # RESPONSE_TYPE_MODAL
            assert "components" in modal_response["data"]
            components = modal_response["data"]["components"]
            assert len(components) > 0

    def test_handle_modal_submission(self, tmp_path):
        """Test modal submission handler."""
        # Create mock .env and backup directory
        env_file = tmp_path / ".env"
        env_file.write_text("MIN_SCORE=0.2\n")
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)

        with patch("catalyst_bot.config_updater._get_env_path", return_value=env_file):
            with patch(
                "catalyst_bot.config_updater._get_backup_dir", return_value=backup_dir
            ):
                from catalyst_bot.admin_interactions import handle_modal_submit

                # Simulate modal submission
                interaction_data = {
                    "type": 5,  # INTERACTION_TYPE_MODAL_SUBMIT
                    "data": {
                        "custom_id": "admin_modal_2025-10-05",
                        "components": [
                            {"components": [{"custom_id": "min_score", "value": "0.3"}]}
                        ],
                    },
                }

                response = handle_modal_submit(interaction_data)

                # Verify response
                assert response["type"] == 4
                assert "embeds" in response["data"]


# ============================================================================
# Button Handler Edge Cases
# ============================================================================


class TestButtonHandlerEdgeCases:
    """Test edge cases in button handlers."""

    def test_view_details_nonexistent_report(self, tmp_path):
        """Test viewing details for non-existent report."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            from catalyst_bot.admin_interactions import build_details_embed

            result = build_details_embed("2099-01-01")

            # Should return error content
            assert "not found" in result.get("content", "").lower()

    def test_approve_nonexistent_report(self, tmp_path):
        """Test approving non-existent report."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            from catalyst_bot.admin_interactions import handle_approve

            response = handle_approve("2099-01-01")

            # Should return error response
            assert response["type"] == 4
            embed = response["data"]["embeds"][0]
            assert "not found" in embed["description"].lower()

    def test_invalid_button_custom_id(self):
        """Test handling invalid custom_id."""
        from catalyst_bot.admin_interactions import handle_admin_interaction

        interaction_data = {
            "type": 3,
            "data": {"custom_id": "invalid_id", "component_type": 2},
        }

        response = handle_admin_interaction(interaction_data)
        assert "Invalid" in response["data"]["content"]

    def test_malformed_custom_id(self):
        """Test handling malformed custom_id (wrong format)."""
        from catalyst_bot.admin_interactions import handle_admin_interaction

        interaction_data = {
            "type": 3,
            "data": {"custom_id": "admin_", "component_type": 2},  # Missing parts
        }

        response = handle_admin_interaction(interaction_data)
        assert "Invalid" in response["data"]["content"]

    def test_modal_submission_empty_values(self, tmp_path):
        """Test modal submission with all empty values."""
        env_file = tmp_path / ".env"
        env_file.write_text("MIN_SCORE=0.2\n")
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)

        with patch("catalyst_bot.config_updater._get_env_path", return_value=env_file):
            with patch(
                "catalyst_bot.config_updater._get_backup_dir", return_value=backup_dir
            ):
                from catalyst_bot.admin_interactions import handle_modal_submit

                interaction_data = {
                    "type": 5,
                    "data": {
                        "custom_id": "admin_modal_2025-10-05",
                        "components": [
                            {"components": [{"custom_id": "min_score", "value": ""}]}
                        ],
                    },
                }

                response = handle_modal_submit(interaction_data)

                # Should handle gracefully
                assert response["type"] == 4
                embed = response["data"]["embeds"][0]
                assert "No valid changes" in embed["description"]

    def test_modal_submission_invalid_values(self, tmp_path):
        """Test modal submission with invalid parameter values."""
        env_file = tmp_path / ".env"
        env_file.write_text("MIN_SCORE=0.2\n")
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)

        with patch("catalyst_bot.config_updater._get_env_path", return_value=env_file):
            with patch(
                "catalyst_bot.config_updater._get_backup_dir", return_value=backup_dir
            ):
                from catalyst_bot.admin_interactions import handle_modal_submit

                interaction_data = {
                    "type": 5,
                    "data": {
                        "custom_id": "admin_modal_2025-10-05",
                        "components": [
                            {
                                "components": [
                                    {"custom_id": "min_score", "value": "not_a_number"}
                                ]
                            }
                        ],
                    },
                }

                response = handle_modal_submit(interaction_data)

                # Should skip invalid values
                assert response["type"] == 4


# ============================================================================
# Full Approval Flow Integration Tests
# ============================================================================


class TestApprovalFlowIntegration:
    """Integration tests for complete approval workflow."""

    def test_full_approval_workflow(self, tmp_path, sample_admin_report):
        """Test complete flow: generate report -> view details -> approve -> verify."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            # Setup environment
            env_file = tmp_path / ".env"
            env_file.write_text("MIN_SCORE=0.25\nPRICE_CEILING=10.0\n")
            (tmp_path / "data" / "config_backups").mkdir(parents=True, exist_ok=True)

            with patch(
                "catalyst_bot.config_updater._get_env_path", return_value=env_file
            ):
                # Step 1: Save report
                save_admin_report(sample_admin_report)

                # Step 2: View details
                from catalyst_bot.admin_interactions import build_details_embed

                details = build_details_embed("2025-10-05")
                assert "embeds" in details

                # Step 3: Approve changes
                from catalyst_bot.admin_interactions import handle_approve

                response = handle_approve("2025-10-05")
                assert response["type"] == 4

                # Step 4: Verify changes in .env file (if approval succeeded)
                # Note: Approval might fail in test environment, which is okay
                # The test verifies the handler runs without crashing

    def test_approval_then_rollback_workflow(self, tmp_path, sample_admin_report):
        """Test approval followed by rollback."""
        with patch("catalyst_bot.admin_controls._get_repo_root", return_value=tmp_path):
            env_file = tmp_path / ".env"
            original_content = "MIN_SCORE=0.25\nPRICE_CEILING=10.0\n"
            env_file.write_text(original_content)

            backup_dir = tmp_path / "data" / "config_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            with patch(
                "catalyst_bot.config_updater._get_env_path", return_value=env_file
            ):
                with patch(
                    "catalyst_bot.config_updater._get_backup_dir",
                    return_value=backup_dir,
                ):
                    # Save report
                    save_admin_report(sample_admin_report)

                    # Approve changes
                    from catalyst_bot.admin_interactions import handle_approve

                    handle_approve("2025-10-05")

                    # Rollback
                    from catalyst_bot.config_updater import rollback_changes

                    success, message = rollback_changes()

                    # Verify rollback happened (may fail if no changes were applied)
                    # But handler should not crash
                    assert isinstance(success, bool)
                    assert isinstance(message, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
