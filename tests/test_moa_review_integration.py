"""
MOA Keyword Review Integration Tests
=====================================

Test the complete human-in-the-loop MOA review workflow from end to end.

This suite validates:
- Database initialization and CRUD operations
- Review creation from MOA recommendations
- Discord embed/component building
- Button interaction routing
- State transitions and workflow
- Timeout and expiry logic
- Rollback functionality

Author: Claude Code (MOA Human-in-the-Loop Enhancement)
Date: 2025-11-12
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    """Create temporary data directory for isolated tests."""
    # Change working directory to temp path
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    analyzer_dir = data_dir / "analyzer"
    analyzer_dir.mkdir()

    # Create minimal keyword_stats.json
    stats_path = analyzer_dir / "keyword_stats.json"
    stats_path.write_text(json.dumps({
        "weights": {
            "merger": 1.0,
            "partnership": 1.0,
            "dilution": 1.0,
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "test_fixture",
    }))

    # Update DB_PATH to point to temp directory
    db_path = data_dir / "keyword_review.db"
    monkeypatch.setattr("catalyst_bot.keyword_review_db.DB_PATH", db_path)

    yield data_dir


@pytest.fixture
def mock_recommendations() -> List[Dict[str, Any]]:
    """Generate sample MOA recommendations for testing."""
    return [
        {
            "keyword": "dilution",
            "current_weight": 1.0,
            "recommended_weight": 2.24,
            "confidence": 0.92,
            "occurrences": 45,
            "success_rate": 0.78,
            "avg_return_pct": 12.5,
            "weight_delta": 1.24,
            "evidence": {
                "examples": [
                    {"ticker": "ABCD", "return_pct": 18.2},
                    {"ticker": "EFGH", "return_pct": 15.8},
                ],
                "flash_catalyst": True,
                "intraday_rate": 0.82,
            }
        },
        {
            "keyword": "partnership",
            "current_weight": 1.0,
            "recommended_weight": 2.15,
            "confidence": 0.85,
            "occurrences": 32,
            "success_rate": 0.72,
            "avg_return_pct": 10.3,
            "weight_delta": 1.15,
            "evidence": {
                "examples": [
                    {"ticker": "IJKL", "return_pct": 12.4},
                ],
                "flash_catalyst": False,
                "intraday_rate": 0.65,
            }
        },
        {
            "keyword": "merger",
            "current_weight": 1.0,
            "recommended_weight": 0.78,
            "confidence": 0.68,
            "occurrences": 18,
            "success_rate": 0.44,
            "avg_return_pct": 3.2,
            "weight_delta": -0.22,
            "evidence": {
                "examples": [],
                "flash_catalyst": False,
            }
        },
    ]


class TestDatabaseOperations:
    """Test keyword_review_db.py database operations."""

    def test_init_database(self, temp_data_dir):
        """Test database initialization with correct schema."""
        from catalyst_bot.keyword_review_db import init_review_database

        db_path = temp_data_dir / "keyword_review.db"

        # Initialize database
        result_path = init_review_database()

        assert result_path.exists()

        # Verify tables exist
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "keyword_reviews" in tables
        assert "keyword_changes" in tables
        assert "keyword_stats_snapshots" in tables

    def test_create_review_record(self, temp_data_dir):
        """Test creating a review record."""
        from catalyst_bot.keyword_review_db import (
            create_review_record,
            get_review,
            init_review_database,
        )

        init_review_database()

        # Create review
        review_id = "test_review_2025-11-12_01-30"
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

        success = create_review_record(
            review_id=review_id,
            total_keywords=3,
            expires_at=expires_at,
            source_analysis_path="data/moa/analysis_report.json"
        )

        assert success is True

        # Verify record
        review = get_review(review_id)
        assert review is not None
        assert review["review_id"] == review_id
        assert review["state"] == "PENDING"
        assert review["total_keywords"] == 3

    def test_insert_keyword_changes(self, temp_data_dir, mock_recommendations):
        """Test inserting keyword changes."""
        from catalyst_bot.keyword_review_db import (
            create_review_record,
            get_keyword_changes,
            init_review_database,
            insert_keyword_change,
        )

        init_review_database()

        review_id = "test_review"
        create_review_record(review_id, total_keywords=3)

        # Insert changes
        for rec in mock_recommendations:
            success = insert_keyword_change(
                review_id=review_id,
                keyword=rec["keyword"],
                old_weight=rec["current_weight"],
                new_weight=rec["recommended_weight"],
                confidence=rec["confidence"],
                occurrences=rec["occurrences"],
                success_rate=rec["success_rate"],
                avg_return_pct=rec["avg_return_pct"],
                evidence=rec.get("evidence"),
            )
            assert success is True

        # Verify changes
        changes = get_keyword_changes(review_id)
        assert len(changes) == 3
        assert changes[0]["keyword"] == "dilution"  # Highest confidence first


class TestReviewWorkflow:
    """Test keyword_review.py workflow and state machine."""

    def test_create_pending_review(self, temp_data_dir, mock_recommendations):
        """Test creating a pending review from recommendations."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database

        init_review_database()

        # Create review
        review_id = create_pending_review(
            recommendations=mock_recommendations,
            min_confidence=0.6,
            timeout_hours=48
        )

        assert review_id is not None
        assert review_id.startswith("moa_review_")

    def test_approve_all_workflow(self, temp_data_dir, mock_recommendations):
        """Test approve all → apply workflow."""
        from catalyst_bot.keyword_review import (
            approve_all_changes,
            apply_approved_changes,
            create_pending_review,
            get_review_summary,
        )
        from catalyst_bot.keyword_review_db import init_review_database

        init_review_database()

        # Create review
        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Approve all
        success, message = approve_all_changes(review_id, reviewer_id="test_admin")
        assert success is True

        # Apply changes
        apply_success, apply_msg, count = apply_approved_changes(review_id, applied_by="test_admin")
        assert apply_success is True
        assert count == 3  # All 3 keywords applied

        # Verify state
        summary = get_review_summary(review_id)
        assert summary["review"]["state"] == "APPLIED"

    def test_individual_review_workflow(self, temp_data_dir, mock_recommendations):
        """Test individual approve/reject/skip workflow."""
        from catalyst_bot.keyword_review import (
            approve_keyword,
            create_pending_review,
            get_review_summary,
            reject_keyword,
            skip_keyword,
        )
        from catalyst_bot.keyword_review_db import init_review_database

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Approve first keyword
        success, _ = approve_keyword(review_id, "dilution", reviewer_id="test_admin")
        assert success is True

        # Reject second keyword
        success, _ = reject_keyword(review_id, "partnership", reviewer_id="test_admin")
        assert success is True

        # Skip third keyword
        success, _ = skip_keyword(review_id, "merger", reviewer_id="test_admin")
        assert success is True

        # Verify stats
        summary = get_review_summary(review_id)
        assert summary["stats"]["approved"] == 1
        assert summary["stats"]["rejected"] == 1
        assert summary["stats"]["skipped"] == 1

    def test_rollback_workflow(self, temp_data_dir, mock_recommendations):
        """Test rollback functionality."""
        from catalyst_bot.keyword_review import (
            approve_all_changes,
            apply_approved_changes,
            create_pending_review,
            rollback_changes,
        )
        from catalyst_bot.keyword_review_db import init_review_database

        init_review_database()

        # Save original stats
        stats_path = temp_data_dir / "analyzer" / "keyword_stats.json"
        original_stats = json.loads(stats_path.read_text())

        # Create and apply review
        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)
        approve_all_changes(review_id, reviewer_id="test_admin")
        apply_approved_changes(review_id, applied_by="test_admin")

        # Verify weights changed
        new_stats = json.loads(stats_path.read_text())
        assert new_stats["weights"]["dilution"] == 2.24

        # Rollback
        success, message = rollback_changes(review_id, rollback_by="test_admin")
        assert success is True

        # Verify restored
        restored_stats = json.loads(stats_path.read_text())
        assert restored_stats["weights"]["dilution"] == 1.0


class TestDiscordUI:
    """Test moa_discord_reviewer.py UI building."""

    def test_build_summary_embed(self, temp_data_dir, mock_recommendations):
        """Test building summary embed."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database
        from catalyst_bot.moa_discord_reviewer import build_review_embed

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Build summary embed
        embed = build_review_embed(review_id)

        assert embed["title"].startswith("🔍 MOA Keyword Review:")
        assert "Total Keywords:" in embed["description"]
        assert "dilution" in embed["description"]  # Top keyword should appear

    def test_build_individual_embed(self, temp_data_dir, mock_recommendations):
        """Test building individual page embed."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database
        from catalyst_bot.moa_discord_reviewer import build_review_embed

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Build page 0 (dilution)
        embed = build_review_embed(review_id, page=0)

        assert "Review Keyword: dilution" in embed["title"]
        assert "2.24" in embed["description"]  # New weight
        assert "Page 1 of 3" in embed["description"]

    def test_build_main_components(self, temp_data_dir, mock_recommendations):
        """Test building main action buttons."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database
        from catalyst_bot.moa_discord_reviewer import build_review_components

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Build components
        components = build_review_components(review_id)

        assert len(components) >= 1
        buttons = components[0]["components"]

        # Check button labels
        labels = [btn["label"] for btn in buttons]
        assert "✅ Approve All" in labels
        assert "❌ Reject All" in labels
        assert "📝 Review Individual" in labels

    def test_build_pagination_components(self, temp_data_dir, mock_recommendations):
        """Test building pagination buttons."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database
        from catalyst_bot.moa_discord_reviewer import build_review_components

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Build page 1 components (middle page)
        components = build_review_components(review_id, page=1)

        assert len(components) >= 2

        # Action buttons (row 1)
        action_buttons = components[0]["components"]
        action_labels = [btn["label"] for btn in action_buttons]
        assert "✅ Approve" in action_labels
        assert "❌ Reject" in action_labels

        # Navigation buttons (row 2)
        nav_buttons = components[1]["components"]
        nav_labels = [btn["label"] for btn in nav_buttons]
        assert "◀️ Previous" in nav_labels
        assert "Next ▶️" in nav_labels


class TestInteractionHandler:
    """Test moa_interaction_handler.py button routing."""

    def test_approve_all_interaction(self, temp_data_dir, mock_recommendations):
        """Test handling 'Approve All' button click."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database
        from catalyst_bot.moa_interaction_handler import handle_moa_review_interaction

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Simulate button click
        interaction_data = {
            "type": 3,  # MESSAGE_COMPONENT
            "data": {
                "custom_id": f"moa_review_approve_all:{review_id}"
            },
            "member": {
                "user": {"id": "test_user_123"}
            }
        }

        response = handle_moa_review_interaction(interaction_data)

        assert response["type"] == 7  # UPDATE_MESSAGE
        assert "embeds" in response["data"]

    def test_individual_review_interaction(self, temp_data_dir, mock_recommendations):
        """Test handling individual keyword approval."""
        from catalyst_bot.keyword_review import create_pending_review
        from catalyst_bot.keyword_review_db import init_review_database
        from catalyst_bot.moa_interaction_handler import handle_moa_review_interaction

        init_review_database()

        review_id = create_pending_review(mock_recommendations, min_confidence=0.6)

        # Approve first keyword
        interaction_data = {
            "type": 3,
            "data": {
                "custom_id": f"moa_review_approve:{review_id}:dilution:0"
            },
            "member": {
                "user": {"id": "test_user_123"}
            }
        }

        response = handle_moa_review_interaction(interaction_data)

        assert response["type"] == 7  # UPDATE_MESSAGE
        # Should advance to next page or show completion


class TestExpiryLogic:
    """Test expiry and timeout logic."""

    def test_expire_old_reviews(self, temp_data_dir, mock_recommendations):
        """Test auto-apply after timeout."""
        from catalyst_bot.keyword_review import create_pending_review, expire_old_reviews
        from catalyst_bot.keyword_review_db import get_review, init_review_database

        init_review_database()

        # Create review with very short timeout (0 hours = immediate expiry)
        review_id = create_pending_review(mock_recommendations, min_confidence=0.6, timeout_hours=0)

        # Trigger expiry check
        expired_count = expire_old_reviews(timeout_hours=0)

        assert expired_count == 1

        # Verify state changed to APPLIED
        review = get_review(review_id)
        assert review["state"] == "APPLIED"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
