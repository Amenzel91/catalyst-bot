"""
MOA Interaction Handler Module
===============================

Handle Discord button interactions for keyword review workflow.

Supported Actions:
- Approve All / Reject All
- Individual Review (Approve/Reject/Skip individual keywords)
- Pagination (Next/Previous page navigation)
- Rollback (Restore previous weights)
- Back to Summary

Author: Claude Code (MOA Human-in-the-Loop Enhancement)
Date: 2025-11-12
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .keyword_review import (
    approve_all_changes,
    approve_keyword,
    apply_approved_changes,
    reject_all_changes,
    reject_keyword,
    rollback_changes,
    skip_keyword,
)
from .logging_utils import get_logger
from .moa_discord_reviewer import build_review_components, build_review_embed

log = get_logger("moa_interaction_handler")


def handle_moa_review_interaction(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route MOA review interaction to appropriate handler.

    Parameters
    ----------
    interaction_data : dict
        Discord interaction payload

    Returns
    -------
    dict
        Discord interaction response

    Notes
    -----
    Parses custom_id to route to:
    - moa_review_approve_all:{review_id}
    - moa_review_reject_all:{review_id}
    - moa_review_individual:{review_id}
    - moa_review_rollback:{review_id}
    - moa_review_approve:{review_id}:{keyword}:{page}
    - moa_review_reject:{review_id}:{keyword}:{page}
    - moa_review_skip:{review_id}:{keyword}:{page}
    - moa_review_page:{review_id}:{page}
    - moa_review_summary:{review_id}
    """
    try:
        custom_id = interaction_data["data"]["custom_id"]
        user_id = interaction_data.get("member", {}).get("user", {}).get("id", "unknown")

        log.info(f"moa_interaction_received custom_id={custom_id} user={user_id}")

        # Parse action and parameters
        parts = custom_id.split(":")

        if len(parts) < 2:
            return _error_response("Invalid custom_id format")

        action = parts[0]
        review_id = parts[1]

        # Route to appropriate handler
        if action == "moa_review_approve_all":
            return _handle_approve_all(review_id, user_id)

        elif action == "moa_review_reject_all":
            return _handle_reject_all(review_id, user_id)

        elif action == "moa_review_individual":
            return _handle_start_individual_review(review_id)

        elif action == "moa_review_rollback":
            return _handle_rollback(review_id, user_id)

        elif action == "moa_review_approve":
            keyword = parts[2] if len(parts) > 2 else None
            page = int(parts[3]) if len(parts) > 3 else 0
            return _handle_approve_keyword(review_id, keyword, page, user_id)

        elif action == "moa_review_reject":
            keyword = parts[2] if len(parts) > 2 else None
            page = int(parts[3]) if len(parts) > 3 else 0
            return _handle_reject_keyword(review_id, keyword, page, user_id)

        elif action == "moa_review_skip":
            keyword = parts[2] if len(parts) > 2 else None
            page = int(parts[3]) if len(parts) > 3 else 0
            return _handle_skip_keyword(review_id, keyword, page, user_id)

        elif action == "moa_review_page":
            page = int(parts[2]) if len(parts) > 2 else 0
            return _handle_page_navigation(review_id, page)

        elif action == "moa_review_summary":
            return _handle_back_to_summary(review_id)

        else:
            return _error_response(f"Unknown action: {action}")

    except Exception as e:
        log.error(f"moa_interaction_handler_failed err={e}", exc_info=True)
        return _error_response(f"Internal error: {str(e)}")


# ============================================================================
# Action Handlers
# ============================================================================


def _handle_approve_all(review_id: str, user_id: str) -> Dict[str, Any]:
    """Handle 'Approve All' button click."""
    # Approve all pending keywords
    success, message = approve_all_changes(review_id, reviewer_id=user_id)

    if not success:
        return _error_response(message)

    # Apply changes immediately
    apply_success, apply_msg, count = apply_approved_changes(review_id, applied_by=user_id)

    if not apply_success:
        return _error_response(f"Approved but failed to apply: {apply_msg}")

    # Update embed to show APPLIED state
    updated_embed = build_review_embed(review_id)
    updated_components = build_review_components(review_id)

    return {
        "type": 7,  # UPDATE_MESSAGE
        "data": {
            "embeds": [updated_embed],
            "components": updated_components,
        },
    }


def _handle_reject_all(review_id: str, user_id: str) -> Dict[str, Any]:
    """Handle 'Reject All' button click."""
    success, message = reject_all_changes(review_id, reviewer_id=user_id)

    if not success:
        return _error_response(message)

    # Update embed to show REJECTED state
    updated_embed = build_review_embed(review_id)
    updated_components = build_review_components(review_id)

    return {
        "type": 7,  # UPDATE_MESSAGE
        "data": {
            "embeds": [updated_embed],
            "components": updated_components,
        },
    }


def _handle_start_individual_review(review_id: str) -> Dict[str, Any]:
    """Handle 'Review Individual' button click - show first page."""
    # Show first keyword (page 0)
    page_embed = build_review_embed(review_id, page=0)
    page_components = build_review_components(review_id, page=0)

    return {
        "type": 7,  # UPDATE_MESSAGE
        "data": {
            "embeds": [page_embed],
            "components": page_components,
        },
    }


def _handle_rollback(review_id: str, user_id: str) -> Dict[str, Any]:
    """Handle 'Rollback' button click."""
    success, message = rollback_changes(review_id, rollback_by=user_id)

    if not success:
        return _error_response(message)

    # Update embed to show ROLLED_BACK state
    updated_embed = build_review_embed(review_id)
    updated_components = build_review_components(review_id)

    # Also send ephemeral success message
    return {
        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
        "data": {
            "content": f"✅ Successfully rolled back changes from {review_id}",
            "flags": 64,  # Ephemeral
        },
    }


def _handle_approve_keyword(review_id: str, keyword: str, page: int, user_id: str) -> Dict[str, Any]:
    """Handle individual keyword approval."""
    success, message = approve_keyword(review_id, keyword, reviewer_id=user_id)

    if not success:
        return _error_response(message)

    # Move to next page or back to summary if done
    return _advance_to_next_or_finish(review_id, page, "approved")


def _handle_reject_keyword(review_id: str, keyword: str, page: int, user_id: str) -> Dict[str, Any]:
    """Handle individual keyword rejection."""
    success, message = reject_keyword(review_id, keyword, reviewer_id=user_id)

    if not success:
        return _error_response(message)

    # Move to next page or back to summary if done
    return _advance_to_next_or_finish(review_id, page, "rejected")


def _handle_skip_keyword(review_id: str, keyword: str, page: int, user_id: str) -> Dict[str, Any]:
    """Handle individual keyword skip."""
    success, message = skip_keyword(review_id, keyword, reviewer_id=user_id)

    if not success:
        return _error_response(message)

    # Move to next page
    return _advance_to_next_or_finish(review_id, page, "skipped")


def _handle_page_navigation(review_id: str, page: int) -> Dict[str, Any]:
    """Handle Next/Previous page navigation."""
    # Show requested page
    page_embed = build_review_embed(review_id, page=page)
    page_components = build_review_components(review_id, page=page)

    return {
        "type": 7,  # UPDATE_MESSAGE
        "data": {
            "embeds": [page_embed],
            "components": page_components,
        },
    }


def _handle_back_to_summary(review_id: str) -> Dict[str, Any]:
    """Handle 'Back to Summary' button click."""
    # Show main summary embed
    summary_embed = build_review_embed(review_id)
    summary_components = build_review_components(review_id)

    return {
        "type": 7,  # UPDATE_MESSAGE
        "data": {
            "embeds": [summary_embed],
            "components": summary_components,
        },
    }


# ============================================================================
# Helper Functions
# ============================================================================


def _advance_to_next_or_finish(review_id: str, current_page: int, action: str) -> Dict[str, Any]:
    """
    After approving/rejecting/skipping a keyword, advance to next page or finish.

    Parameters
    ----------
    review_id : str
        Review identifier
    current_page : int
        Current page index
    action : str
        Action taken (approved/rejected/skipped)

    Returns
    -------
    dict
        Discord interaction response (either next page or summary)
    """
    from .keyword_review import get_review_summary

    summary = get_review_summary(review_id)

    if not summary:
        return _error_response("Review not found")

    total_pages = len(summary["changes"])
    next_page = current_page + 1

    # Check if there are more pages
    if next_page < total_pages:
        # Show next page
        page_embed = build_review_embed(review_id, page=next_page)
        page_components = build_review_components(review_id, page=next_page)

        return {
            "type": 7,  # UPDATE_MESSAGE
            "data": {
                "embeds": [page_embed],
                "components": page_components,
                "content": f"✅ Keyword {action}. Showing next keyword..."
            },
        }

    else:
        # All keywords reviewed - check if any approved
        approved_count = summary["stats"]["approved"]
        rejected_count = summary["stats"]["rejected"]
        skipped_count = summary["stats"]["skipped"]

        # Build completion message
        if approved_count > 0:
            completion_msg = (
                f"✅ Review complete!\n\n"
                f"• Approved: **{approved_count}**\n"
                f"• Rejected: **{rejected_count}**\n"
                f"• Skipped: **{skipped_count}**\n\n"
                f"Applying approved changes..."
            )

            # Apply approved changes
            success, msg, count = apply_approved_changes(review_id, applied_by="user_review")

            if success:
                completion_msg += f"\n\n🎉 Successfully applied **{count}** keyword changes!"
            else:
                completion_msg += f"\n\n❌ Failed to apply changes: {msg}"

        else:
            completion_msg = (
                f"✅ Review complete - all keywords rejected/skipped.\n\n"
                f"No changes will be applied."
            )

        # Show updated summary
        summary_embed = build_review_embed(review_id)
        summary_components = build_review_components(review_id)

        return {
            "type": 7,  # UPDATE_MESSAGE
            "data": {
                "content": completion_msg,
                "embeds": [summary_embed],
                "components": summary_components,
            },
        }


def _error_response(message: str, ephemeral: bool = True) -> Dict[str, Any]:
    """
    Build error response.

    Parameters
    ----------
    message : str
        Error message to display
    ephemeral : bool
        If True, only visible to user who clicked (default: True)

    Returns
    -------
    dict
        Discord interaction response
    """
    return {
        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
        "data": {
            "content": f"❌ {message}",
            "flags": 64 if ephemeral else 0,  # Ephemeral flag
        },
    }
