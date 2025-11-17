"""
MOA Keyword Review Workflow Module
===================================

Business logic for managing keyword review lifecycle with state machine.

Workflow States:
- PENDING: Awaiting admin review
- APPROVED: Admin approved, ready to apply
- REJECTED: Admin rejected, will not apply
- APPLIED: Successfully applied to keyword_stats.json
- ROLLED_BACK: Applied then rolled back to previous snapshot

Author: Claude Code (MOA Human-in-the-Loop Enhancement)
Date: 2025-11-12
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .keyword_review_db import (
    create_review_record,
    create_snapshot,
    get_expired_reviews,
    get_keyword_changes,
    get_latest_snapshot,
    get_pending_reviews,
    get_review,
    init_review_database,
    insert_keyword_change,
    update_keyword_status,
    update_review_state,
)
from .logging_utils import get_logger

log = get_logger("keyword_review")


class ReviewState(str, Enum):
    """Review state enum for type safety."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"


class ChangeStatus(str, Enum):
    """Individual keyword change status enum."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


def create_pending_review(
    recommendations: List[Dict[str, Any]],
    min_confidence: float = 0.6,
    timeout_hours: int = 48,
    source_analysis_path: Optional[str] = None,
) -> str:
    """
    Create new pending review from MOA recommendations.

    Parameters
    ----------
    recommendations : list of dict
        List of keyword recommendations from MOA analysis
        Each dict should have: keyword, recommended_weight, confidence, occurrences, success_rate, avg_return_pct, examples
    min_confidence : float
        Minimum confidence threshold to include in review (default: 0.6)
    timeout_hours : int
        Hours until review auto-applies (default: 48)
    source_analysis_path : str, optional
        Path to MOA analysis_report.json

    Returns
    -------
    str
        Review ID (e.g., "moa_review_2025-11-12_01-30")

    Raises
    ------
    ValueError
        If no recommendations meet confidence threshold

    Notes
    -----
    - Initializes database if needed
    - Creates snapshot of current keyword_stats.json
    - Filters recommendations by confidence threshold
    - Calculates expiration timestamp
    """
    # Initialize database
    init_review_database()

    # Generate review ID with timestamp
    now = datetime.now(timezone.utc)
    review_id = f"moa_review_{now.strftime('%Y-%m-%d_%H-%M')}"

    # Filter by confidence
    filtered_recs = [r for r in recommendations if r.get("confidence", 0) >= min_confidence]

    if not filtered_recs:
        raise ValueError(f"No recommendations meet confidence threshold {min_confidence}")

    # Calculate expiration
    expires_at = (now + timedelta(hours=timeout_hours)).isoformat()

    # Load current keyword_stats.json for old weights
    current_weights = _load_current_keyword_stats()

    # Create snapshot BEFORE any changes
    if current_weights:
        create_snapshot(review_id, current_weights)

    # Create main review record
    success = create_review_record(
        review_id=review_id,
        total_keywords=len(filtered_recs),
        expires_at=expires_at,
        source_analysis_path=source_analysis_path,
    )

    if not success:
        raise RuntimeError(f"Failed to create review record: {review_id}")

    # Insert individual keyword changes
    for rec in filtered_recs:
        keyword = rec["keyword"]
        new_weight = rec["recommended_weight"]
        old_weight = current_weights.get("weights", {}).get(keyword) if current_weights else None

        # Build evidence dict from examples
        # Extract data from evidence dict (MOA recommendations structure)
        rec_evidence = rec.get("evidence", {})

        evidence = {
            "examples": rec_evidence.get("examples", [])[:3],  # Top 3 tickers
            "flash_catalyst": rec_evidence.get("is_flash_catalyst", False),
            "intraday_rate": rec_evidence.get("intraday_success_rate"),
            "intraday_performance": rec_evidence.get("intraday_performance"),
        }

        insert_keyword_change(
            review_id=review_id,
            keyword=keyword,
            old_weight=old_weight,
            new_weight=new_weight,
            confidence=rec["confidence"],
            occurrences=rec_evidence.get("occurrences", 0),
            success_rate=rec_evidence.get("success_rate", 0.0),
            avg_return_pct=rec_evidence.get("avg_return_pct", 0.0),
            evidence=evidence,
        )

    log.info(
        f"review_created review_id={review_id} keywords={len(filtered_recs)} "
        f"expires_at={expires_at} min_confidence={min_confidence}"
    )

    return review_id


def approve_all_changes(review_id: str, reviewer_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Approve all pending keywords in a review.

    Parameters
    ----------
    review_id : str
        Review identifier
    reviewer_id : str, optional
        ID of user approving (e.g., Discord user ID)

    Returns
    -------
    tuple of (bool, str)
        (success, message)

    Notes
    -----
    - Updates review state to APPROVED
    - Marks all PENDING keywords as APPROVED
    - Does NOT apply changes yet (call apply_approved_changes separately)
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}"

    if review["state"] != ReviewState.PENDING:
        return False, f"Review is not pending (state: {review['state']})"

    # Get all pending changes
    changes = get_keyword_changes(review_id, status=ChangeStatus.PENDING)

    if not changes:
        return False, "No pending changes to approve"

    # Mark all as approved
    for change in changes:
        update_keyword_status(review_id, change["keyword"], ChangeStatus.APPROVED, reviewer_id)

    # Update review state
    update_review_state(review_id, ReviewState.APPROVED, reviewer_id=reviewer_id)

    log.info(f"review_approved review_id={review_id} keywords={len(changes)} reviewer={reviewer_id}")

    return True, f"Approved {len(changes)} keyword changes"


def reject_all_changes(review_id: str, reviewer_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Reject all pending keywords in a review.

    Parameters
    ----------
    review_id : str
        Review identifier
    reviewer_id : str, optional
        ID of user rejecting

    Returns
    -------
    tuple of (bool, str)
        (success, message)

    Notes
    -----
    - Updates review state to REJECTED
    - Marks all PENDING keywords as REJECTED
    - Changes will NOT be applied
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}"

    if review["state"] != ReviewState.PENDING:
        return False, f"Review is not pending (state: {review['state']})"

    # Get all pending changes
    changes = get_keyword_changes(review_id, status=ChangeStatus.PENDING)

    if not changes:
        return False, "No pending changes to reject"

    # Mark all as rejected
    for change in changes:
        update_keyword_status(review_id, change["keyword"], ChangeStatus.REJECTED, reviewer_id)

    # Update review state
    update_review_state(review_id, ReviewState.REJECTED, reviewer_id=reviewer_id)

    log.info(f"review_rejected review_id={review_id} keywords={len(changes)} reviewer={reviewer_id}")

    return True, f"Rejected {len(changes)} keyword changes"


def approve_keyword(review_id: str, keyword: str, reviewer_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Approve individual keyword change.

    Parameters
    ----------
    review_id : str
        Review identifier
    keyword : str
        Keyword to approve
    reviewer_id : str, optional
        ID of user approving

    Returns
    -------
    tuple of (bool, str)
        (success, message)
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}"

    if review["state"] != ReviewState.PENDING:
        return False, f"Review is not pending (state: {review['state']})"

    # Update keyword status
    success = update_keyword_status(review_id, keyword, ChangeStatus.APPROVED, reviewer_id)

    if success:
        # Check if all keywords are now reviewed (none PENDING)
        pending = get_keyword_changes(review_id, status=ChangeStatus.PENDING)
        if not pending:
            # All reviewed - check if any were approved
            approved = get_keyword_changes(review_id, status=ChangeStatus.APPROVED)
            if approved:
                update_review_state(review_id, ReviewState.APPROVED, reviewer_id=reviewer_id)
                log.info(f"review_fully_approved review_id={review_id} approved={len(approved)}")
            else:
                # All rejected/skipped
                update_review_state(review_id, ReviewState.REJECTED, reviewer_id=reviewer_id)
                log.info(f"review_fully_rejected review_id={review_id}")

        log.info(f"keyword_approved review_id={review_id} keyword={keyword}")
        return True, f"Approved: {keyword}"

    return False, f"Failed to approve: {keyword}"


def reject_keyword(review_id: str, keyword: str, reviewer_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Reject individual keyword change.

    Parameters
    ----------
    review_id : str
        Review identifier
    keyword : str
        Keyword to reject
    reviewer_id : str, optional
        ID of user rejecting

    Returns
    -------
    tuple of (bool, str)
        (success, message)
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}"

    if review["state"] != ReviewState.PENDING:
        return False, f"Review is not pending (state: {review['state']})"

    # Update keyword status
    success = update_keyword_status(review_id, keyword, ChangeStatus.REJECTED, reviewer_id)

    if success:
        # Check if all keywords are now reviewed
        pending = get_keyword_changes(review_id, status=ChangeStatus.PENDING)
        if not pending:
            approved = get_keyword_changes(review_id, status=ChangeStatus.APPROVED)
            if approved:
                update_review_state(review_id, ReviewState.APPROVED, reviewer_id=reviewer_id)
            else:
                update_review_state(review_id, ReviewState.REJECTED, reviewer_id=reviewer_id)

        log.info(f"keyword_rejected review_id={review_id} keyword={keyword}")
        return True, f"Rejected: {keyword}"

    return False, f"Failed to reject: {keyword}"


def skip_keyword(review_id: str, keyword: str, reviewer_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Skip individual keyword change (neither approve nor reject).

    Parameters
    ----------
    review_id : str
        Review identifier
    keyword : str
        Keyword to skip
    reviewer_id : str, optional
        ID of user skipping

    Returns
    -------
    tuple of (bool, str)
        (success, message)

    Notes
    -----
    Skipped keywords are treated as rejected (will not be applied).
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}"

    if review["state"] != ReviewState.PENDING:
        return False, f"Review is not pending (state: {review['state']})"

    success = update_keyword_status(review_id, keyword, ChangeStatus.SKIPPED, reviewer_id)

    if success:
        log.info(f"keyword_skipped review_id={review_id} keyword={keyword}")
        return True, f"Skipped: {keyword}"

    return False, f"Failed to skip: {keyword}"


def apply_approved_changes(review_id: str, applied_by: Optional[str] = None) -> Tuple[bool, str, int]:
    """
    Apply approved keyword changes to keyword_stats.json.

    Parameters
    ----------
    review_id : str
        Review identifier
    applied_by : str, optional
        ID of user/system applying changes (e.g., "system" for auto-apply)

    Returns
    -------
    tuple of (bool, str, int)
        (success, message, count_applied)

    Notes
    -----
    - Only applies APPROVED keywords
    - Updates keyword_stats.json atomically
    - Records applied_at timestamp
    - Updates review state to APPLIED
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}", 0

    if review["state"] not in [ReviewState.PENDING, ReviewState.APPROVED]:
        return False, f"Review cannot be applied (state: {review['state']})", 0

    # Get approved changes only
    approved_changes = get_keyword_changes(review_id, status=ChangeStatus.APPROVED)

    if not approved_changes:
        log.warning(f"no_approved_changes review_id={review_id}")
        return False, "No approved changes to apply", 0

    # Load current keyword_stats.json
    current_stats = _load_current_keyword_stats()

    if not current_stats:
        return False, "Failed to load keyword_stats.json", 0

    # Apply changes
    weights = current_stats.get("weights", {})
    applied_count = 0

    for change in approved_changes:
        keyword = change["keyword"]
        new_weight = change["new_weight"]
        old_weight = weights.get(keyword)

        weights[keyword] = new_weight
        applied_count += 1

        log.info(
            f"keyword_applied review_id={review_id} keyword={keyword} "
            f"old={old_weight or 'new'} new={new_weight:.2f}"
        )

    # Update metadata
    current_stats["weights"] = weights
    current_stats["last_updated"] = datetime.now(timezone.utc).isoformat()
    current_stats["source"] = f"moa_review_{review_id}"
    current_stats["total_keywords"] = len(weights)
    current_stats["updates_applied"] = applied_count

    # Write atomically
    success = _save_keyword_stats(current_stats)

    if not success:
        return False, "Failed to write keyword_stats.json", 0

    # Update review state
    now = datetime.now(timezone.utc).isoformat()
    update_review_state(
        review_id,
        ReviewState.APPLIED,
        applied_at=now,
        applied_by=applied_by or "system",
    )

    log.info(
        f"review_applied review_id={review_id} keywords={applied_count} "
        f"applied_by={applied_by or 'system'}"
    )

    return True, f"Applied {applied_count} keyword changes", applied_count


def rollback_changes(review_id: str, rollback_by: Optional[str] = None) -> Tuple[bool, str]:
    """
    Rollback applied changes to previous snapshot.

    Parameters
    ----------
    review_id : str
        Review identifier
    rollback_by : str, optional
        ID of user/system rolling back

    Returns
    -------
    tuple of (bool, str)
        (success, message)

    Notes
    -----
    - Only works for APPLIED reviews
    - Restores from snapshot created before review
    - Updates review state to ROLLED_BACK
    """
    review = get_review(review_id)
    if not review:
        return False, f"Review not found: {review_id}"

    if review["state"] != ReviewState.APPLIED:
        return False, f"Review not applied (state: {review['state']}), cannot rollback"

    # Get snapshot
    snapshot = get_latest_snapshot(review_id)

    if not snapshot:
        return False, f"No snapshot found for review: {review_id}"

    # Restore from snapshot
    success = _save_keyword_stats(snapshot)

    if not success:
        return False, "Failed to restore from snapshot"

    # Update review state
    update_review_state(review_id, ReviewState.ROLLED_BACK, applied_by=rollback_by or "system")

    log.info(f"review_rolled_back review_id={review_id} by={rollback_by or 'system'}")

    return True, f"Rolled back changes from {review_id}"


def expire_old_reviews(timeout_hours: int = 48) -> int:
    """
    Auto-apply expired pending reviews.

    Parameters
    ----------
    timeout_hours : int
        Hours after which a review is considered expired (default: 48)

    Returns
    -------
    int
        Number of reviews auto-applied

    Notes
    -----
    - Finds PENDING reviews past expiration
    - Approves all pending keywords
    - Applies changes automatically
    - Logs as applied_by="system_timeout"
    """
    expired_reviews = get_expired_reviews(timeout_hours)

    if not expired_reviews:
        return 0

    applied_count = 0

    for review in expired_reviews:
        review_id = review["review_id"]

        # Approve all pending keywords
        success, msg = approve_all_changes(review_id, reviewer_id="system_timeout")

        if not success:
            log.warning(f"expire_approve_failed review_id={review_id} msg={msg}")
            continue

        # Apply changes
        success, msg, count = apply_approved_changes(review_id, applied_by="system_timeout")

        if success:
            applied_count += 1
            log.info(
                f"review_auto_applied review_id={review_id} keywords={count} "
                f"reason=timeout_expired"
            )
        else:
            log.warning(f"expire_apply_failed review_id={review_id} msg={msg}")

    if applied_count > 0:
        log.info(f"expired_reviews_auto_applied count={applied_count}")

    return applied_count


def get_review_summary(review_id: str) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive review summary with all changes.

    Parameters
    ----------
    review_id : str
        Review identifier

    Returns
    -------
    dict or None
        Review summary with metadata and changes, or None if not found

    Structure
    ---------
    {
        "review": {...},  # Main review record
        "changes": [...],  # All keyword changes
        "approved": [...],  # Approved changes only
        "rejected": [...],  # Rejected changes only
        "pending": [...],   # Pending changes only
        "stats": {
            "total": int,
            "approved": int,
            "rejected": int,
            "pending": int,
            "avg_confidence": float,
            "top_mover": {...}
        }
    }
    """
    review = get_review(review_id)
    if not review:
        return None

    all_changes = get_keyword_changes(review_id)
    approved = [c for c in all_changes if c["status"] == ChangeStatus.APPROVED]
    rejected = [c for c in all_changes if c["status"] == ChangeStatus.REJECTED]
    pending = [c for c in all_changes if c["status"] == ChangeStatus.PENDING]

    # Calculate stats
    avg_confidence = sum(c["confidence"] for c in all_changes) / len(all_changes) if all_changes else 0
    top_mover = max(all_changes, key=lambda c: abs(c["weight_delta"])) if all_changes else None

    return {
        "review": review,
        "changes": all_changes,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "stats": {
            "total": len(all_changes),
            "approved": len(approved),
            "rejected": len(rejected),
            "pending": len(pending),
            "avg_confidence": avg_confidence,
            "top_mover": top_mover,
        },
    }


# ============================================================================
# Private Helper Functions
# ============================================================================


def _load_current_keyword_stats() -> Optional[Dict[str, Any]]:
    """
    Load current keyword_stats.json file.

    Returns
    -------
    dict or None
        Parsed JSON content, or None if file doesn't exist
    """
    stats_path = Path("data/analyzer/keyword_stats.json")

    if not stats_path.exists():
        log.warning("keyword_stats_file_not_found path=%s", stats_path)
        return None

    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    except Exception as e:
        log.error(f"load_keyword_stats_failed err={e}")
        return None


def _save_keyword_stats(data: Dict[str, Any]) -> bool:
    """
    Save keyword_stats.json atomically.

    Parameters
    ----------
    data : dict
        Full keyword stats data to save

    Returns
    -------
    bool
        True if saved successfully
    """
    stats_path = Path("data/analyzer/keyword_stats.json")
    stats_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Write to temp file first
        temp_path = stats_path.with_suffix(".json.tmp")

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        temp_path.replace(stats_path)

        log.info(f"keyword_stats_saved path={stats_path} keywords={len(data.get('weights', {}))}")
        return True

    except Exception as e:
        log.error(f"save_keyword_stats_failed err={e}")
        return False
