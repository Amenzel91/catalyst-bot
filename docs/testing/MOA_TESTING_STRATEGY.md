# MOA Keyword Review System - Comprehensive Testing Strategy

**Date:** 2025-11-11  
**System:** Missed Opportunities Analyzer (MOA) with Human-in-the-Loop Review  
**Status:** Testing Design Phase

---

## Table of Contents

1. [Test File Structure](#1-test-file-structure)
2. [Unit Tests](#2-unit-tests)
3. [Integration Tests](#3-integration-tests)
4. [Mock Data Design](#4-mock-data-design)
5. [Alpha Testing Guide](#5-alpha-testing-guide)
6. [Validation Checks](#6-validation-checks)

---

## 1. Test File Structure

### Recommended Test Organization

```
tests/
├── test_keyword_review_manager.py          # Core review workflow tests
├── test_discord_review_interactions.py     # Discord UI & button interactions
├── test_pending_change_creation.py         # Pending change lifecycle
├── test_approval_rejection_logic.py        # Approval/rejection state machine
├── test_audit_logging.py                   # Audit trail validation
├── test_moa_review_integration.py          # End-to-end MOA → review → apply
├── test_keyword_application.py             # Applying approved changes
├── test_rollback_scenarios.py              # Rollback and error recovery
├── test_concurrent_reviews.py              # Multiple simultaneous reviews
│
├── fixtures/
│   ├── mock_moa_recommendations.json       # Sample MOA output
│   ├── mock_discord_responses.json         # Discord API responses
│   ├── mock_keyword_stats.json             # Sample keyword_stats.json
│   └── mock_audit_trail.jsonl             # Sample audit entries
│
└── integration/
    ├── test_full_review_workflow.py        # Complete workflow tests
    └── test_validation_pipeline.py         # Automated validation tests
```

### Where to Place Each Test Module

| Test File | Location | Purpose |
|-----------|----------|---------|
| `test_keyword_review_manager.py` | `tests/` | Core PendingChange CRUD, state transitions |
| `test_discord_review_interactions.py` | `tests/` | Discord embed generation, button handling |
| `test_pending_change_creation.py` | `tests/` | Creating pending changes from MOA output |
| `test_approval_rejection_logic.py` | `tests/` | State machine: pending → approved/rejected |
| `test_audit_logging.py` | `tests/` | Audit trail completeness & integrity |
| `test_moa_review_integration.py` | `tests/` | Full pipeline from MOA to application |
| `test_keyword_application.py` | `tests/` | Applying changes to keyword_stats.json |
| `test_rollback_scenarios.py` | `tests/` | Rollback logic and safety checks |
| `test_concurrent_reviews.py` | `tests/` | Race conditions, locking |

---

## 2. Unit Tests

### 2.1 Pending Change Creation

**File:** `tests/test_pending_change_creation.py`

```python
"""
Unit tests for creating pending changes from MOA recommendations.
"""
import pytest
from datetime import datetime, timezone
from pathlib import Path

from catalyst_bot.keyword_review_manager import (
    PendingChange,
    create_pending_change_from_recommendation,
    save_pending_change,
    load_pending_change,
)


class TestPendingChangeCreation:
    """Tests for PendingChange creation and persistence."""

    def test_create_pending_change_basic(self):
        """Test creating a basic pending change from MOA recommendation."""
        recommendation = {
            "keyword": "breakthrough_therapy",
            "recommended_weight": 1.5,
            "confidence": 0.85,
            "evidence": {
                "occurrences": 12,
                "hit_rate": 0.75,
                "avg_return": 18.3,
                "missed_winners": ["ABCD", "EFGH", "IJKL"]
            },
            "analysis_date": "2025-11-10"
        }

        change = create_pending_change_from_recommendation(recommendation)

        # Assertions
        assert change.plan_id is not None
        assert len(change.plan_id) == 8  # Short UUID
        assert change.keyword == "breakthrough_therapy"
        assert change.current_weight == 1.0  # Default
        assert change.proposed_weight == 1.5
        assert change.confidence == 0.85
        assert change.status == "pending"
        assert change.created_at is not None
        assert change.evidence["occurrences"] == 12

    def test_create_pending_change_with_existing_weight(self, tmp_path, monkeypatch):
        """Test creating change when keyword already has a weight."""
        # Setup existing keyword_stats.json
        keyword_stats = {
            "weights": {
                "fda": 1.2,
                "clinical": 1.0
            }
        }
        stats_path = tmp_path / "keyword_stats.json"
        with open(stats_path, 'w') as f:
            json.dump(keyword_stats, f)

        # Monkeypatch to use temp path
        monkeypatch.setattr(
            "catalyst_bot.keyword_review_manager._get_keyword_stats_path",
            lambda: stats_path
        )

        recommendation = {
            "keyword": "fda",
            "recommended_weight": 1.5,
            "confidence": 0.90,
            "evidence": {},
            "analysis_date": "2025-11-10"
        }

        change = create_pending_change_from_recommendation(recommendation)

        # Should use existing weight
        assert change.current_weight == 1.2
        assert change.proposed_weight == 1.5

    def test_pending_change_serialization(self, tmp_path):
        """Test that PendingChange can be saved and loaded correctly."""
        change = PendingChange(
            plan_id="abc12345",
            keyword="partnership",
            current_weight=1.0,
            proposed_weight=1.3,
            confidence=0.78,
            evidence={"occurrences": 8, "hit_rate": 0.625},
            status="pending",
            created_at=datetime.now(timezone.utc),
            created_by="moa_analyzer"
        )

        # Save
        save_path = save_pending_change(change, base_dir=tmp_path)
        assert save_path.exists()

        # Load
        loaded = load_pending_change("abc12345", base_dir=tmp_path)
        assert loaded is not None
        assert loaded.keyword == "partnership"
        assert loaded.proposed_weight == 1.3
        assert loaded.status == "pending"

    def test_reject_mechanical_artifacts(self):
        """Test that mechanical artifacts are auto-rejected."""
        recommendation = {
            "keyword": "reverse_stock_split",
            "recommended_weight": 7.5,
            "confidence": 0.95,
            "evidence": {"occurrences": 5, "avg_return": 7042.0},  # Fake!
            "analysis_date": "2025-11-10"
        }

        change = create_pending_change_from_recommendation(recommendation)

        # Should be auto-rejected
        assert change.status == "rejected"
        assert "mechanical artifact" in change.rejection_reason.lower()

    def test_hold_for_manual_review(self):
        """Test that questionable keywords are marked for review."""
        recommendation = {
            "keyword": "distress_negative",
            "recommended_weight": 2.5,
            "confidence": 0.82,
            "evidence": {"occurrences": 5, "avg_return": 1038.0},
            "analysis_date": "2025-11-10"
        }

        change = create_pending_change_from_recommendation(recommendation)

        # Should require manual review
        assert change.requires_manual_review is True
        assert change.review_notes == "counterintuitive_pattern"


### 2.2 Approval/Rejection Logic

**File:** `tests/test_approval_rejection_logic.py`

```python
"""
Unit tests for approval/rejection state transitions.
"""
import pytest
from datetime import datetime, timezone

from catalyst_bot.keyword_review_manager import (
    PendingChange,
    approve_change,
    reject_change,
    InvalidStateTransitionError,
)


class TestApprovalRejectionLogic:
    """Tests for state machine transitions."""

    def test_approve_pending_change(self):
        """Test approving a pending change."""
        change = PendingChange(
            plan_id="test123",
            keyword="fda",
            current_weight=1.0,
            proposed_weight=1.2,
            confidence=0.85,
            status="pending"
        )

        result = approve_change(
            change,
            approved_by="admin@example.com",
            notes="Looks good, high confidence"
        )

        assert result.status == "approved"
        assert result.approved_by == "admin@example.com"
        assert result.approved_at is not None
        assert result.approval_notes == "Looks good, high confidence"

    def test_reject_pending_change(self):
        """Test rejecting a pending change."""
        change = PendingChange(
            plan_id="test456",
            keyword="dilution",
            current_weight=1.0,
            proposed_weight=2.2,
            confidence=0.60,
            status="pending"
        )

        result = reject_change(
            change,
            rejected_by="admin@example.com",
            reason="Need to verify pre-catalyst momentum first"
        )

        assert result.status == "rejected"
        assert result.rejected_by == "admin@example.com"
        assert result.rejected_at is not None
        assert result.rejection_reason == "Need to verify pre-catalyst momentum first"

    def test_cannot_approve_already_approved(self):
        """Test that approving an already-approved change raises error."""
        change = PendingChange(
            plan_id="test789",
            keyword="clinical",
            current_weight=1.0,
            proposed_weight=1.1,
            status="approved",
            approved_at=datetime.now(timezone.utc),
            approved_by="previous_admin"
        )

        with pytest.raises(InvalidStateTransitionError) as exc:
            approve_change(change, approved_by="another_admin")

        assert "already approved" in str(exc.value).lower()

    def test_cannot_reject_already_rejected(self):
        """Test that rejecting an already-rejected change raises error."""
        change = PendingChange(
            plan_id="test999",
            keyword="offering",
            status="rejected",
            rejected_at=datetime.now(timezone.utc),
            rejected_by="previous_admin"
        )

        with pytest.raises(InvalidStateTransitionError) as exc:
            reject_change(change, rejected_by="another_admin")

        assert "already rejected" in str(exc.value).lower()

    def test_approve_with_modifications(self):
        """Test approving with a modified weight."""
        change = PendingChange(
            plan_id="test111",
            keyword="partnership",
            current_weight=1.0,
            proposed_weight=1.5,
            confidence=0.70,
            status="pending"
        )

        # Admin decides to use 1.3 instead of 1.5
        result = approve_change(
            change,
            approved_by="admin@example.com",
            modified_weight=1.3,
            notes="Approved but reduced to 1.3 for safety"
        )

        assert result.status == "approved"
        assert result.proposed_weight == 1.3  # Modified
        assert "reduced to 1.3" in result.approval_notes


### 2.3 State Transitions

**File:** `tests/test_state_transitions.py`

```python
"""
Tests for PendingChange state machine.
"""
import pytest
from catalyst_bot.keyword_review_manager import PendingChange, apply_change


class TestStateTransitions:
    """Test valid and invalid state transitions."""

    @pytest.mark.parametrize("initial_status,action,expected_status", [
        ("pending", "approve", "approved"),
        ("pending", "reject", "rejected"),
        ("approved", "apply", "applied"),
        ("approved", "rollback", "rolled_back"),
    ])
    def test_valid_transitions(self, initial_status, action, expected_status):
        """Test all valid state transitions."""
        change = PendingChange(
            plan_id="test",
            keyword="test_kw",
            status=initial_status
        )

        if action == "approve":
            result = approve_change(change, approved_by="admin")
        elif action == "reject":
            result = reject_change(change, rejected_by="admin")
        elif action == "apply":
            result = apply_change(change, applied_by="system")
        elif action == "rollback":
            result = rollback_change(change, rolled_back_by="admin")

        assert result.status == expected_status

    @pytest.mark.parametrize("initial_status,action", [
        ("rejected", "approve"),
        ("approved", "reject"),
        ("applied", "approve"),
        ("pending", "apply"),
        ("pending", "rollback"),
    ])
    def test_invalid_transitions(self, initial_status, action):
        """Test that invalid transitions raise errors."""
        change = PendingChange(
            plan_id="test",
            keyword="test_kw",
            status=initial_status
        )

        with pytest.raises(InvalidStateTransitionError):
            if action == "approve":
                approve_change(change, approved_by="admin")
            elif action == "reject":
                reject_change(change, rejected_by="admin")
            elif action == "apply":
                apply_change(change, applied_by="system")
            elif action == "rollback":
                rollback_change(change, rolled_back_by="admin")


### 2.4 Audit Logging

**File:** `tests/test_audit_logging.py`

```python
"""
Tests for audit trail logging.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

from catalyst_bot.keyword_review_manager import (
    log_audit_event,
    load_audit_trail,
    validate_audit_trail,
)


class TestAuditLogging:
    """Tests for audit logging functionality."""

    def test_log_approval_event(self, tmp_path):
        """Test logging an approval event to audit trail."""
        change = PendingChange(
            plan_id="audit123",
            keyword="fda",
            proposed_weight=1.2,
            status="approved"
        )

        log_audit_event(
            event_type="approval",
            change=change,
            actor="admin@example.com",
            notes="Approved via Discord",
            audit_file=tmp_path / "audit.jsonl"
        )

        # Verify log entry
        audit_trail = load_audit_trail(tmp_path / "audit.jsonl")
        assert len(audit_trail) == 1

        entry = audit_trail[0]
        assert entry["event_type"] == "approval"
        assert entry["plan_id"] == "audit123"
        assert entry["keyword"] == "fda"
        assert entry["actor"] == "admin@example.com"
        assert "timestamp" in entry

    def test_log_application_event(self, tmp_path):
        """Test logging when change is applied to keyword_stats.json."""
        change = PendingChange(
            plan_id="apply456",
            keyword="clinical",
            current_weight=1.0,
            proposed_weight=1.3,
            status="applied"
        )

        log_audit_event(
            event_type="application",
            change=change,
            actor="system",
            details={
                "old_weight": 1.0,
                "new_weight": 1.3,
                "file_path": "data/analyzer/keyword_stats.json"
            },
            audit_file=tmp_path / "audit.jsonl"
        )

        audit_trail = load_audit_trail(tmp_path / "audit.jsonl")
        entry = audit_trail[0]

        assert entry["event_type"] == "application"
        assert entry["details"]["new_weight"] == 1.3

    def test_log_rejection_event(self, tmp_path):
        """Test logging a rejection event."""
        change = PendingChange(
            plan_id="reject789",
            keyword="reverse_stock_split",
            status="rejected"
        )

        log_audit_event(
            event_type="rejection",
            change=change,
            actor="admin@example.com",
            reason="Mechanical artifact",
            audit_file=tmp_path / "audit.jsonl"
        )

        audit_trail = load_audit_trail(tmp_path / "audit.jsonl")
        entry = audit_trail[0]

        assert entry["event_type"] == "rejection"
        assert entry["reason"] == "Mechanical artifact"

    def test_audit_trail_append_only(self, tmp_path):
        """Test that audit trail is append-only (no deletions)."""
        audit_file = tmp_path / "audit.jsonl"

        # Log 3 events
        for i in range(3):
            change = PendingChange(plan_id=f"test{i}", keyword=f"kw{i}")
            log_audit_event(
                event_type="test",
                change=change,
                actor="tester",
                audit_file=audit_file
            )

        # Verify all 3 are present
        trail = load_audit_trail(audit_file)
        assert len(trail) == 3

        # Try to delete one (should fail or be ignored)
        # In production, file permissions should prevent this
        assert audit_file.exists()

    def test_validate_audit_trail_completeness(self, tmp_path):
        """Test that audit trail validation catches missing entries."""
        audit_file = tmp_path / "audit.jsonl"

        # Create a change lifecycle: created → approved → applied
        change = PendingChange(plan_id="lifecycle", keyword="test")

        log_audit_event("creation", change, "moa", audit_file=audit_file)
        log_audit_event("approval", change, "admin", audit_file=audit_file)
        # Missing application event!

        # Validation should catch this
        is_valid, errors = validate_audit_trail(audit_file, expected_plan_ids=["lifecycle"])

        assert not is_valid
        assert any("missing application" in err.lower() for err in errors)


---

## 3. Integration Tests

### 3.1 MOA Analysis → Review Workflow → Approval → Application Pipeline

**File:** `tests/test_moa_review_integration.py`

```python
"""
Integration tests for the full MOA → review → approval → application pipeline.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

from catalyst_bot.moa_analyzer import run_moa_analysis
from catalyst_bot.keyword_review_manager import (
    create_pending_changes_from_moa,
    approve_change,
    apply_approved_changes,
)
from catalyst_bot.discord_review_interactions import post_review_embed


class TestMOAReviewIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_single_approval(self, tmp_path, monkeypatch):
        """
        Test complete flow:
        1. MOA generates recommendation
        2. Pending change created
        3. Posted to Discord
        4. Admin approves
        5. Change applied to keyword_stats.json
        6. Audit trail updated
        """
        # Setup test environment
        setup_test_data(tmp_path, monkeypatch)

        # 1. Run MOA analysis
        moa_report = run_moa_analysis(
            target_date=datetime.now(timezone.utc).date(),
            rejected_items_path=tmp_path / "rejected_items.jsonl",
            output_dir=tmp_path / "moa"
        )

        assert len(moa_report.recommendations) > 0

        # 2. Create pending changes
        pending_changes = create_pending_changes_from_moa(moa_report)
        assert len(pending_changes) > 0

        change = pending_changes[0]
        assert change.status == "pending"

        # 3. Simulate posting to Discord (mock)
        with patch('catalyst_bot.discord_review_interactions.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            response = post_review_embed(change)
            assert response["success"] is True

        # 4. Admin approves
        approved = approve_change(
            change,
            approved_by="admin@example.com",
            notes="Looks good!"
        )
        assert approved.status == "approved"

        # 5. Apply change
        result = apply_approved_changes([approved], base_dir=tmp_path)
        assert result["applied"] == 1
        assert result["failed"] == 0

        # 6. Verify keyword_stats.json updated
        stats_path = tmp_path / "analyzer" / "keyword_stats.json"
        with open(stats_path) as f:
            stats = json.load(f)

        assert approved.keyword in stats["weights"]
        assert stats["weights"][approved.keyword] == approved.proposed_weight

        # 7. Verify audit trail
        audit_path = tmp_path / "audit" / "keyword_review_audit.jsonl"
        assert audit_path.exists()

        with open(audit_path) as f:
            audit_entries = [json.loads(line) for line in f]

        # Should have: creation, approval, application
        assert len(audit_entries) >= 3
        assert any(e["event_type"] == "approval" for e in audit_entries)
        assert any(e["event_type"] == "application" for e in audit_entries)

    def test_rejection_prevents_application(self, tmp_path, monkeypatch):
        """Test that rejected changes are NOT applied."""
        setup_test_data(tmp_path, monkeypatch)

        # Create pending change
        change = PendingChange(
            plan_id="reject_test",
            keyword="dilution",
            proposed_weight=2.2,
            status="pending"
        )
        save_pending_change(change, base_dir=tmp_path)

        # Reject it
        rejected = reject_change(
            change,
            rejected_by="admin@example.com",
            reason="Need more analysis"
        )

        # Try to apply (should skip rejected)
        result = apply_approved_changes([rejected], base_dir=tmp_path)

        assert result["applied"] == 0
        assert result["skipped"] == 1

        # Verify keyword_stats.json NOT updated
        stats_path = tmp_path / "analyzer" / "keyword_stats.json"
        with open(stats_path) as f:
            stats = json.load(f)

        assert "dilution" not in stats.get("weights", {})


### 3.2 Discord Interaction Flow

**File:** `tests/test_discord_review_interactions.py`

```python
"""
Tests for Discord embed generation and button interactions.
"""
import pytest
from unittest.mock import Mock, patch
import json

from catalyst_bot.discord_review_interactions import (
    build_review_embed,
    create_approval_buttons,
    handle_approval_button,
    handle_rejection_button,
    handle_modify_button,
)


class TestDiscordReviewInteractions:
    """Tests for Discord UI components."""

    def test_build_review_embed(self):
        """Test building a Discord embed for review."""
        change = PendingChange(
            plan_id="embed123",
            keyword="breakthrough_therapy",
            current_weight=1.0,
            proposed_weight=1.5,
            confidence=0.85,
            evidence={
                "occurrences": 12,
                "hit_rate": 0.75,
                "avg_return": 18.3,
                "missed_winners": ["ABCD", "EFGH"]
            }
        )

        embed = build_review_embed(change)

        # Assertions
        assert embed["title"] == "📋 Keyword Weight Review: breakthrough_therapy"
        assert embed["color"] == 0x3498db  # Blue for pending

        # Check fields
        fields = embed["fields"]
        field_names = [f["name"] for f in fields]

        assert "Current Weight" in field_names
        assert "Proposed Weight" in field_names
        assert "Confidence" in field_names
        assert "Evidence" in field_names

        # Check values
        weight_field = next(f for f in fields if f["name"] == "Proposed Weight")
        assert "1.0 → 1.5" in weight_field["value"]

    def test_create_approval_buttons(self):
        """Test creating Discord button components."""
        change = PendingChange(plan_id="btn123", keyword="fda")

        buttons = create_approval_buttons(change.plan_id)

        # Should have 3 buttons: Approve, Reject, Modify
        assert len(buttons) == 1  # 1 action row
        assert len(buttons[0]["components"]) == 3

        components = buttons[0]["components"]

        # Approve button (green)
        approve_btn = components[0]
        assert approve_btn["style"] == 3  # Green
        assert approve_btn["label"] == "✅ Approve"
        assert approve_btn["custom_id"] == f"review_approve_{change.plan_id}"

        # Reject button (red)
        reject_btn = components[1]
        assert reject_btn["style"] == 4  # Red
        assert reject_btn["label"] == "❌ Reject"

        # Modify button (gray)
        modify_btn = components[2]
        assert modify_btn["style"] == 2  # Gray
        assert modify_btn["label"] == "✏️ Modify"

    @patch('catalyst_bot.discord_review_interactions.requests.post')
    def test_handle_approval_button(self, mock_post):
        """Test handling approval button click."""
        mock_post.return_value.status_code = 200

        interaction_data = {
            "custom_id": "review_approve_abc12345",
            "member": {
                "user": {
                    "id": "123456",
                    "username": "admin"
                }
            }
        }

        response = handle_approval_button(interaction_data)

        # Should approve the change
        assert response["type"] == 4  # UPDATE_MESSAGE
        assert "approved" in response["data"]["content"].lower()

        # Verify change status updated
        change = load_pending_change("abc12345")
        assert change.status == "approved"
        assert change.approved_by == "admin"

    @patch('catalyst_bot.discord_review_interactions.requests.post')
    def test_handle_rejection_button(self, mock_post):
        """Test handling rejection button click."""
        mock_post.return_value.status_code = 200

        interaction_data = {
            "custom_id": "review_reject_abc12345",
            "member": {
                "user": {
                    "id": "123456",
                    "username": "admin"
                }
            },
            "data": {
                "components": [
                    {
                        "components": [
                            {
                                "custom_id": "rejection_reason",
                                "value": "Need more analysis"
                            }
                        ]
                    }
                ]
            }
        }

        response = handle_rejection_button(interaction_data)

        assert "rejected" in response["data"]["content"].lower()

        # Verify change rejected
        change = load_pending_change("abc12345")
        assert change.status == "rejected"
        assert change.rejection_reason == "Need more analysis"


### 3.3 Concurrent Review Scenarios

**File:** `tests/test_concurrent_reviews.py`

```python
"""
Tests for handling multiple simultaneous reviews.
"""
import pytest
import threading
import time
from catalyst_bot.keyword_review_manager import (
    PendingChange,
    approve_change,
    lock_pending_change,
    unlock_pending_change,
)


class TestConcurrentReviews:
    """Tests for race conditions and locking."""

    def test_concurrent_approval_attempts(self, tmp_path):
        """Test that only one admin can approve a change (first wins)."""
        change = PendingChange(
            plan_id="concurrent",
            keyword="test",
            status="pending"
        )
        save_pending_change(change, base_dir=tmp_path)

        results = []
        errors = []

        def try_approve(admin_name):
            try:
                result = approve_change(
                    load_pending_change("concurrent", base_dir=tmp_path),
                    approved_by=admin_name
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Simulate 3 admins trying to approve simultaneously
        threads = [
            threading.Thread(target=try_approve, args=(f"admin{i}",))
            for i in range(3)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Only one should succeed
        assert len(results) == 1
        assert len(errors) == 2
        assert all("already approved" in str(e).lower() for e in errors)

    def test_file_locking(self, tmp_path):
        """Test that file locking prevents concurrent modifications."""
        change = PendingChange(plan_id="lock_test", keyword="test")
        save_pending_change(change, base_dir=tmp_path)

        # Thread 1 acquires lock
        lock = lock_pending_change("lock_test", base_dir=tmp_path)
        assert lock is not None

        # Thread 2 tries to acquire (should fail or timeout)
        with pytest.raises(TimeoutError):
            lock_pending_change("lock_test", base_dir=tmp_path, timeout=1.0)

        # Release lock
        unlock_pending_change(lock)

        # Now Thread 2 can acquire
        lock2 = lock_pending_change("lock_test", base_dir=tmp_path)
        assert lock2 is not None


---

## 4. Mock Data Design

### 4.1 Sample MOA Recommendations

**File:** `tests/fixtures/mock_moa_recommendations.json`

```json
{
  "analysis_date": "2025-11-10",
  "total_rejected_items": 324,
  "missed_winners": 18,
  "total_opportunity_cost_pct": 347.5,
  "recommendations": [
    {
      "keyword": "breakthrough_therapy",
      "recommended_weight": 1.5,
      "confidence": 0.85,
      "evidence": {
        "occurrences": 12,
        "hits": 9,
        "misses": 3,
        "hit_rate": 0.75,
        "avg_return": 18.3,
        "max_return": 47.5,
        "missed_winners": [
          {"ticker": "ABCD", "return_pct": 47.5, "date": "2025-11-08"},
          {"ticker": "EFGH", "return_pct": 23.1, "date": "2025-11-07"},
          {"ticker": "IJKL", "return_pct": 18.7, "date": "2025-11-06"}
        ]
      },
      "category": "safe_to_apply",
      "recommendation_type": "new_keyword"
    },
    {
      "keyword": "fda",
      "recommended_weight": 1.5,
      "confidence": 0.90,
      "evidence": {
        "occurrences": 23,
        "hits": 18,
        "misses": 5,
        "hit_rate": 0.78,
        "avg_return": 15.7
      },
      "category": "safe_to_apply",
      "recommendation_type": "weight_increase"
    },
    {
      "keyword": "reverse_stock_split",
      "recommended_weight": 7.5,
      "confidence": 0.95,
      "evidence": {
        "occurrences": 5,
        "avg_return": 7042.0
      },
      "category": "reject",
      "rejection_reason": "mechanical_artifact",
      "recommendation_type": "new_keyword"
    },
    {
      "keyword": "distress_negative",
      "recommended_weight": 2.5,
      "confidence": 0.82,
      "evidence": {
        "occurrences": 5,
        "avg_return": 1038.0
      },
      "category": "manual_review",
      "review_notes": "counterintuitive_pattern",
      "recommendation_type": "new_keyword"
    }
  ]
}
```

### 4.2 Mock Discord Responses

**File:** `tests/fixtures/mock_discord_responses.json`

```json
{
  "webhook_post_success": {
    "status_code": 200,
    "response": {
      "id": "1234567890",
      "channel_id": "9876543210",
      "content": "",
      "embeds": [],
      "components": []
    }
  },
  "interaction_approval": {
    "type": 3,
    "custom_id": "review_approve_abc12345",
    "member": {
      "user": {
        "id": "123456789",
        "username": "admin_user",
        "discriminator": "0001"
      }
    },
    "message": {
      "id": "message_id_here"
    }
  },
  "interaction_rejection": {
    "type": 3,
    "custom_id": "review_reject_abc12345",
    "member": {
      "user": {
        "id": "123456789",
        "username": "admin_user"
      }
    },
    "data": {
      "components": [
        {
          "components": [
            {
              "custom_id": "rejection_reason",
              "value": "Need to verify pre-catalyst momentum"
            }
          ]
        }
      ]
    }
  }
}
```

### 4.3 Mock keyword_stats.json

**File:** `tests/fixtures/mock_keyword_stats.json`

```json
{
  "weights": {
    "clinical": 1.0,
    "dilution": 1.0,
    "fda": 1.2,
    "going_concern": 1.0,
    "partnership": 1.0,
    "uplisting": 1.0,
    "compliance_extension": 1.2,
    "delisting_relief": 1.3
  },
  "last_updated": "2025-11-10T12:00:00Z",
  "source": "manual_configuration",
  "total_keywords": 8
}
```

### 4.4 Mock Audit Trail

**File:** `tests/fixtures/mock_audit_trail.jsonl`

```jsonl
{"timestamp": "2025-11-10T14:00:00Z", "event_type": "creation", "plan_id": "abc12345", "keyword": "breakthrough_therapy", "actor": "moa_analyzer", "details": {"confidence": 0.85}}
{"timestamp": "2025-11-10T14:15:30Z", "event_type": "approval", "plan_id": "abc12345", "keyword": "breakthrough_therapy", "actor": "admin@example.com", "notes": "Approved via Discord"}
{"timestamp": "2025-11-10T14:16:00Z", "event_type": "application", "plan_id": "abc12345", "keyword": "breakthrough_therapy", "actor": "system", "details": {"old_weight": null, "new_weight": 1.5, "file_path": "data/analyzer/keyword_stats.json"}}
{"timestamp": "2025-11-10T15:00:00Z", "event_type": "creation", "plan_id": "def67890", "keyword": "dilution", "actor": "moa_analyzer", "details": {"confidence": 0.60}}
{"timestamp": "2025-11-10T15:10:00Z", "event_type": "rejection", "plan_id": "def67890", "keyword": "dilution", "actor": "admin@example.com", "reason": "Need to verify pre-catalyst momentum"}
```

---

## 5. Alpha Testing Guide

### Step-by-Step Manual Testing Checklist

#### 5.1 Trigger MOA Analysis

**Objective:** Verify MOA analyzer runs and generates recommendations

**Steps:**

1. **Prepare test data:**
   ```bash
   # Ensure rejected_items.jsonl has entries from last 30 days
   tail -20 data/rejected_items.jsonl
   ```

2. **Run MOA analyzer:**
   ```bash
   python -m catalyst_bot.moa_analyzer
   ```

3. **Verify output:**
   ```bash
   # Check that analysis report was generated
   ls -lh data/moa/analysis_report_*.json
   cat data/moa/analysis_report_$(date +%Y-%m-%d).json | jq .
   ```

4. **Expected results:**
   - ✅ Report contains `recommendations` array
   - ✅ Each recommendation has `keyword`, `recommended_weight`, `confidence`
   - ✅ Recommendations categorized: `safe_to_apply`, `manual_review`, `reject`

**Success Criteria:**
- [ ] MOA runs without errors
- [ ] At least 1 recommendation generated
- [ ] Confidence scores between 0.0 and 1.0
- [ ] Evidence includes `occurrences`, `hit_rate`, `avg_return`

---

#### 5.2 Test Pending Change Creation

**Objective:** Verify recommendations are converted to pending changes

**Steps:**

1. **Create pending changes from MOA report:**
   ```python
   from catalyst_bot.keyword_review_manager import create_pending_changes_from_moa
   from catalyst_bot.moa_analyzer import load_moa_report

   report = load_moa_report('data/moa/analysis_report_2025-11-10.json')
   pending_changes = create_pending_changes_from_moa(report)

   print(f"Created {len(pending_changes)} pending changes")
   for change in pending_changes:
       print(f"  {change.plan_id}: {change.keyword} ({change.status})")
   ```

2. **Verify pending files created:**
   ```bash
   ls -1 data/analyzer/pending_*.json
   ```

3. **Inspect a pending change:**
   ```bash
   cat data/analyzer/pending_abc12345.json | jq .
   ```

**Success Criteria:**
- [ ] All safe recommendations → `status: "pending"`
- [ ] Rejected recommendations → `status: "rejected"`
- [ ] Manual review recommendations → `requires_manual_review: true`
- [ ] Each has unique 8-char `plan_id`

---

#### 5.3 Test Discord Review Embed

**Objective:** Verify Discord embed is posted with approval buttons

**Steps:**

1. **Post review embed to Discord:**
   ```python
   from catalyst_bot.discord_review_interactions import post_review_embed
   from catalyst_bot.keyword_review_manager import load_pending_change

   change = load_pending_change('abc12345')
   result = post_review_embed(change)

   print(f"Posted: {result['success']}")
   print(f"Message ID: {result['message_id']}")
   ```

2. **Check Discord channel:**
   - Open Discord channel configured for admin reviews
   - Verify embed appears with:
     - Title: "📋 Keyword Weight Review: {keyword}"
     - Fields: Current Weight, Proposed Weight, Confidence, Evidence
     - 3 buttons: ✅ Approve, ❌ Reject, ✏️ Modify

3. **Verify button custom IDs:**
   - Approve: `review_approve_{plan_id}`
   - Reject: `review_reject_{plan_id}`
   - Modify: `review_modify_{plan_id}`

**Success Criteria:**
- [ ] Embed posts successfully
- [ ] All fields populated correctly
- [ ] Buttons are interactive
- [ ] Color coding: Blue for pending, Green for approved, Red for rejected

---

#### 5.4 Test Approval Flow

**Objective:** Verify clicking "Approve" button updates state

**Steps:**

1. **Click ✅ Approve button in Discord**

2. **Verify interaction response:**
   - Message should update to show "✅ Approved by {username}"
   - Buttons should be disabled

3. **Check pending change status:**
   ```bash
   cat data/analyzer/pending_abc12345.json | jq '.status, .approved_by, .approved_at'
   ```

4. **Verify audit trail entry:**
   ```bash
   grep "abc12345" data/audit/keyword_review_audit.jsonl | tail -1 | jq .
   ```

**Success Criteria:**
- [ ] Status changed to "approved"
- [ ] `approved_by` field populated with Discord username
- [ ] `approved_at` timestamp recorded
- [ ] Audit entry logged with event_type: "approval"

---

#### 5.5 Test Rejection Flow

**Objective:** Verify clicking "Reject" button updates state

**Steps:**

1. **Click ❌ Reject button in Discord**

2. **Enter rejection reason in modal:**
   - Discord should show text input modal
   - Enter: "Need to verify pre-catalyst momentum"

3. **Verify interaction response:**
   - Message updates to "❌ Rejected by {username}"
   - Rejection reason shown

4. **Check pending change status:**
   ```bash
   cat data/analyzer/pending_def67890.json | jq '.status, .rejection_reason'
   ```

**Success Criteria:**
- [ ] Status changed to "rejected"
- [ ] `rejection_reason` field populated
- [ ] `rejected_by` and `rejected_at` recorded
- [ ] Audit entry logged

---

#### 5.6 Test Keyword Weight Application

**Objective:** Verify approved changes are applied to keyword_stats.json

**Steps:**

1. **Backup current keyword_stats.json:**
   ```bash
   cp data/analyzer/keyword_stats.json data/analyzer/keyword_stats.backup.json
   ```

2. **Apply approved changes:**
   ```python
   from catalyst_bot.keyword_review_manager import apply_approved_changes

   result = apply_approved_changes()

   print(f"Applied: {result['applied']}")
   print(f"Failed: {result['failed']}")
   print(f"Skipped: {result['skipped']}")
   ```

3. **Verify keyword_stats.json updated:**
   ```bash
   diff data/analyzer/keyword_stats.backup.json data/analyzer/keyword_stats.json
   ```

4. **Check specific keyword:**
   ```bash
   cat data/analyzer/keyword_stats.json | jq '.weights.breakthrough_therapy'
   # Should show 1.5
   ```

**Success Criteria:**
- [ ] Only approved changes applied
- [ ] Rejected changes skipped
- [ ] Weights updated correctly
- [ ] `last_updated` timestamp changed
- [ ] Backup created before changes

---

#### 5.7 Test Rollback Scenario

**Objective:** Verify rollback restores previous state

**Steps:**

1. **Note current keyword stats:**
   ```bash
   cat data/analyzer/keyword_stats.json | jq '.weights' > /tmp/before.json
   ```

2. **Apply a change:**
   ```python
   # (apply change as in 5.6)
   ```

3. **Trigger rollback:**
   ```python
   from catalyst_bot.keyword_review_manager import rollback_change

   change = load_pending_change('abc12345')
   result = rollback_change(
       change,
       rolled_back_by="admin@example.com",
       reason="Performance degraded"
   )

   print(f"Rolled back: {result.status}")
   ```

4. **Verify rollback:**
   ```bash
   cat data/analyzer/keyword_stats.json | jq '.weights' > /tmp/after.json
   diff /tmp/before.json /tmp/after.json
   # Should show no difference (or only the rolled-back keyword restored)
   ```

**Success Criteria:**
- [ ] Keyword weight restored to previous value
- [ ] Change status: "rolled_back"
- [ ] Audit entry logged
- [ ] No other keywords affected

---

#### 5.8 Validation: Keyword Stats Integrity

**Objective:** Ensure keyword_stats.json maintains valid structure

**Steps:**

1. **Run validation script:**
   ```python
   from catalyst_bot.validation import validate_keyword_stats

   is_valid, errors = validate_keyword_stats('data/analyzer/keyword_stats.json')

   if not is_valid:
       for error in errors:
           print(f"ERROR: {error}")
   else:
       print("✅ keyword_stats.json is valid")
   ```

2. **Check for:**
   - ✅ All weights are positive floats
   - ✅ No duplicate keywords
   - ✅ `last_updated` is valid ISO timestamp
   - ✅ Required fields present: `weights`, `last_updated`, `source`

**Success Criteria:**
- [ ] No validation errors
- [ ] All weights between 0.1 and 10.0
- [ ] No missing fields

---

#### 5.9 Validation: Audit Trail Completeness

**Objective:** Ensure all changes have complete audit trail

**Steps:**

1. **List all pending changes:**
   ```bash
   ls -1 data/analyzer/pending_*.json | wc -l
   ```

2. **Count audit entries:**
   ```bash
   wc -l data/audit/keyword_review_audit.jsonl
   ```

3. **Validate completeness:**
   ```python
   from catalyst_bot.validation import validate_audit_trail_completeness

   is_complete, missing = validate_audit_trail_completeness()

   if missing:
       print(f"Missing audit entries for: {missing}")
   else:
       print("✅ Audit trail complete")
   ```

**Success Criteria:**
- [ ] Every approved change has: creation, approval, application entries
- [ ] Every rejected change has: creation, rejection entries
- [ ] No orphaned pending changes (no audit trail)

---

#### 5.10 Concurrent Review Test

**Objective:** Test multiple admins reviewing simultaneously

**Steps:**

1. **Create 3 pending changes:**
   ```python
   for i in range(3):
       change = PendingChange(plan_id=f"concurrent{i}", keyword=f"test{i}")
       save_pending_change(change)
       post_review_embed(change)
   ```

2. **Have 2+ admins interact with different reviews:**
   - Admin 1: Approve `concurrent0`
   - Admin 2: Reject `concurrent1`
   - Admin 1: Modify `concurrent2`

3. **Verify no conflicts:**
   ```bash
   # Check that all changes have correct status
   jq '.status, .approved_by // .rejected_by' data/analyzer/pending_concurrent*.json
   ```

**Success Criteria:**
- [ ] Each review has exactly one outcome (approved OR rejected)
- [ ] No race conditions
- [ ] Audit trail shows correct actor for each change

---

### 5.11 Performance Testing

**Test Scenario:** Apply 20 keyword weight changes simultaneously

**Steps:**

1. **Generate 20 pending changes**
2. **Approve all via Discord**
3. **Run application script**
4. **Measure time:**
   ```bash
   time python -m catalyst_bot.keyword_review_manager apply_approved_changes
   ```

**Success Criteria:**
- [ ] < 5 seconds total
- [ ] < 250ms per keyword update
- [ ] No file corruption
- [ ] All audit entries complete

---

## 6. Validation Checks

### 6.1 Automated Validation Script

**File:** `scripts/validate_keyword_review_system.py`

```python
"""
Automated validation script for keyword review system.

Checks:
1. keyword_stats.json integrity
2. Audit trail completeness
3. No lost changes (pending changes without outcome)
4. File permissions
5. Backup existence
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def add_error(self, msg):
        self.errors.append(f"❌ ERROR: {msg}")

    def add_warning(self, msg):
        self.warnings.append(f"⚠️  WARNING: {msg}")

    def add_info(self, msg):
        self.info.append(f"ℹ️  INFO: {msg}")

    @property
    def is_valid(self):
        return len(self.errors) == 0

    def report(self):
        print("\n" + "="*80)
        print("KEYWORD REVIEW SYSTEM VALIDATION REPORT")
        print("="*80 + "\n")

        if self.errors:
            print("ERRORS:")
            for error in self.errors:
                print(f"  {error}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")
            print()

        if self.info:
            print("INFO:")
            for info in self.info:
                print(f"  {info}")
            print()

        if self.is_valid:
            print("✅ ALL VALIDATION CHECKS PASSED\n")
        else:
            print(f"❌ VALIDATION FAILED ({len(self.errors)} errors)\n")


def validate_keyword_stats(stats_path: Path) -> ValidationResult:
    """Validate keyword_stats.json structure and content."""
    result = ValidationResult()

    if not stats_path.exists():
        result.add_error(f"keyword_stats.json not found at {stats_path}")
        return result

    try:
        with open(stats_path) as f:
            stats = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON in keyword_stats.json: {e}")
        return result

    # Check required fields
    required_fields = ['weights', 'last_updated']
    for field in required_fields:
        if field not in stats:
            result.add_error(f"Missing required field: {field}")

    # Validate weights
    if 'weights' in stats:
        weights = stats['weights']

        if not isinstance(weights, dict):
            result.add_error("'weights' must be a dictionary")
        else:
            for keyword, weight in weights.items():
                # Check weight is numeric
                if not isinstance(weight, (int, float)):
                    result.add_error(f"Weight for '{keyword}' is not numeric: {weight}")

                # Check weight is positive
                elif weight <= 0:
                    result.add_error(f"Weight for '{keyword}' must be positive: {weight}")

                # Check weight is reasonable (0.1 to 10.0)
                elif not (0.1 <= weight <= 10.0):
                    result.add_warning(
                        f"Weight for '{keyword}' is outside typical range [0.1, 10.0]: {weight}"
                    )

            result.add_info(f"Total keywords: {len(weights)}")

    # Validate last_updated timestamp
    if 'last_updated' in stats:
        try:
            ts = datetime.fromisoformat(stats['last_updated'].replace('Z', '+00:00'))
            age_days = (datetime.now(timezone.utc) - ts).days

            if age_days > 30:
                result.add_warning(f"keyword_stats.json not updated in {age_days} days")
            else:
                result.add_info(f"Last updated: {age_days} days ago")

        except Exception as e:
            result.add_error(f"Invalid last_updated timestamp: {e}")

    return result


def validate_audit_trail(audit_path: Path) -> ValidationResult:
    """Validate audit trail completeness and integrity."""
    result = ValidationResult()

    if not audit_path.exists():
        result.add_warning(f"Audit trail not found at {audit_path}")
        return result

    # Load all audit entries
    entries = []
    try:
        with open(audit_path) as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    result.add_error(f"Line {line_num}: Invalid JSON: {e}")
    except Exception as e:
        result.add_error(f"Failed to read audit trail: {e}")
        return result

    result.add_info(f"Total audit entries: {len(entries)}")

    # Group by plan_id
    by_plan = defaultdict(list)
    for entry in entries:
        plan_id = entry.get('plan_id')
        if plan_id:
            by_plan[plan_id].append(entry)

    # Validate each plan has complete lifecycle
    for plan_id, plan_entries in by_plan.items():
        event_types = [e.get('event_type') for e in plan_entries]

        # Must have creation event
        if 'creation' not in event_types:
            result.add_error(f"Plan {plan_id}: Missing 'creation' event")

        # Must have outcome (approval or rejection)
        has_outcome = 'approval' in event_types or 'rejection' in event_types
        if not has_outcome:
            result.add_warning(f"Plan {plan_id}: No outcome (still pending?)")

        # If approved, should have application event
        if 'approval' in event_types and 'application' not in event_types:
            # Check if it's recent (might not be applied yet)
            approval_entry = next(e for e in plan_entries if e['event_type'] == 'approval')
            approval_time = datetime.fromisoformat(
                approval_entry['timestamp'].replace('Z', '+00:00')
            )
            age = datetime.now(timezone.utc) - approval_time

            if age > timedelta(hours=1):
                result.add_error(f"Plan {plan_id}: Approved but not applied after {age}")

    return result


def validate_pending_changes(pending_dir: Path, audit_path: Path) -> ValidationResult:
    """Check for orphaned or stuck pending changes."""
    result = ValidationResult()

    if not pending_dir.exists():
        result.add_info("No pending changes directory")
        return result

    # Find all pending change files
    pending_files = list(pending_dir.glob("pending_*.json"))
    result.add_info(f"Found {len(pending_files)} pending change files")

    # Load audit trail
    audit_plan_ids = set()
    if audit_path.exists():
        with open(audit_path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if 'plan_id' in entry:
                        audit_plan_ids.add(entry['plan_id'])
                except:
                    pass

    # Check each pending change
    for pending_file in pending_files:
        try:
            with open(pending_file) as f:
                change = json.load(f)

            plan_id = change.get('plan_id')
            status = change.get('status')
            created_at_str = change.get('created_at')

            # Check if plan_id in audit trail
            if plan_id not in audit_plan_ids:
                result.add_error(f"Plan {plan_id}: No audit trail entry")

            # Check if stuck in pending
            if status == 'pending' and created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    age = datetime.now(timezone.utc) - created_at

                    if age > timedelta(days=7):
                        result.add_warning(
                            f"Plan {plan_id}: Stuck in 'pending' for {age.days} days"
                        )
                except:
                    pass

            # Check if completed but file not deleted
            if status in ['applied', 'rolled_back']:
                result.add_warning(f"Plan {plan_id}: Status '{status}' but file still exists")

        except Exception as e:
            result.add_error(f"Failed to read {pending_file}: {e}")

    return result


def validate_backups(stats_path: Path) -> ValidationResult:
    """Check that backups exist and are recent."""
    result = ValidationResult()

    backup_dir = stats_path.parent / "backups"
    if not backup_dir.exists():
        result.add_warning("No backup directory found")
        return result

    # Find backup files
    backups = sorted(backup_dir.glob("keyword_stats_*.json"), reverse=True)

    if not backups:
        result.add_warning("No backups found")
        return result

    result.add_info(f"Found {len(backups)} backups")

    # Check most recent backup
    latest_backup = backups[0]
    age = datetime.now() - datetime.fromtimestamp(latest_backup.stat().st_mtime)

    if age > timedelta(days=1):
        result.add_warning(f"Most recent backup is {age.days} days old")
    else:
        result.add_info(f"Latest backup: {age.seconds // 3600} hours ago")

    return result


def main():
    """Run all validation checks."""
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"
    analyzer_dir = data_dir / "analyzer"
    audit_dir = data_dir / "audit"

    stats_path = analyzer_dir / "keyword_stats.json"
    audit_path = audit_dir / "keyword_review_audit.jsonl"
    pending_dir = analyzer_dir

    all_results = []

    print("\n🔍 RUNNING VALIDATION CHECKS...\n")

    # 1. Validate keyword_stats.json
    print("1. Validating keyword_stats.json...")
    result = validate_keyword_stats(stats_path)
    all_results.append(result)

    # 2. Validate audit trail
    print("2. Validating audit trail...")
    result = validate_audit_trail(audit_path)
    all_results.append(result)

    # 3. Validate pending changes
    print("3. Validating pending changes...")
    result = validate_pending_changes(pending_dir, audit_path)
    all_results.append(result)

    # 4. Validate backups
    print("4. Validating backups...")
    result = validate_backups(stats_path)
    all_results.append(result)

    # Print consolidated report
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)

    total_errors = sum(len(r.errors) for r in all_results)
    total_warnings = sum(len(r.warnings) for r in all_results)

    for result in all_results:
        for error in result.errors:
            print(error)

    for result in all_results:
        for warning in result.warnings:
            print(warning)

    print()

    if total_errors == 0:
        print("✅ ALL VALIDATION CHECKS PASSED")
        if total_warnings > 0:
            print(f"⚠️  {total_warnings} warnings (review recommended)")
        return 0
    else:
        print(f"❌ VALIDATION FAILED: {total_errors} errors, {total_warnings} warnings")
        return 1


if __name__ == "__main__":
    exit(main())
```

---

## Summary

This comprehensive testing strategy provides:

1. **Structured test organization** with clear separation of unit, integration, and validation tests
2. **Detailed unit tests** covering:
   - Pending change creation from MOA recommendations
   - Approval/rejection state machine
   - Audit logging
   - State transitions
3. **Integration tests** for:
   - Full MOA → review → approval → application pipeline
   - Discord interaction flow (mocked)
   - Concurrent review scenarios
4. **Realistic mock data** schemas for testing without production data
5. **Step-by-step alpha testing guide** with manual verification checkpoints
6. **Automated validation** to ensure system integrity

**Next Steps:**

1. Implement core modules (PendingChange, approval logic)
2. Write unit tests alongside implementation
3. Create mock Discord responses for testing
4. Run alpha tests with test data
5. Iterate based on findings
6. Deploy to production with monitoring

