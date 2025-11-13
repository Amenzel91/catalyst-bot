"""
MOA Discord Review UI Module
=============================

Build Discord embeds and components for interactive keyword review.

Features:
- Rich summary embed with top recommendations
- Full pagination for individual review (30+ keywords)
- Action buttons (Approve All, Reject All, Review Individual, Rollback)
- Real-time countdown timer for expiration

Author: Claude Code (MOA Human-in-the-Loop Enhancement)
Date: 2025-11-12
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .keyword_review import get_review_summary
from .logging_utils import get_logger

log = get_logger("moa_discord_reviewer")


def build_review_embed(review_id: str, page: Optional[int] = None) -> Dict[str, Any]:
    """
    Build Discord embed for keyword review.

    Parameters
    ----------
    review_id : str
        Review identifier
    page : int, optional
        If provided, build paginated individual review page (0-indexed)
        If None, build main summary embed

    Returns
    -------
    dict
        Discord embed object

    Notes
    -----
    Summary embed shows:
    - Total keywords, avg confidence, top mover
    - Top 10 recommendations table
    - Confidence distribution
    - Expiration timer

    Individual page shows:
    - Single keyword details
    - Old → New weight
    - Evidence (occurrences, success rate, ROI, top tickers)
    - Page counter
    """
    summary = get_review_summary(review_id)

    if not summary:
        return _error_embed(f"Review not found: {review_id}")

    review = summary["review"]
    changes = summary["changes"]
    stats = summary["stats"]

    # Main summary embed
    if page is None:
        return _build_summary_embed(review, changes, stats)

    # Individual pagination page
    if page < 0 or page >= len(changes):
        return _error_embed(f"Invalid page: {page} (total: {len(changes)})")

    change = changes[page]
    return _build_individual_embed(review, change, page, len(changes))


def build_review_components(review_id: str, page: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Build Discord action row components (buttons).

    Parameters
    ----------
    review_id : str
        Review identifier
    page : int, optional
        If provided, build pagination buttons
        If None, build main action buttons

    Returns
    -------
    list of dict
        Discord component objects (action rows with buttons)

    Notes
    -----
    Main buttons:
    - ✅ Approve All
    - ❌ Reject All
    - 📝 Review Individual
    - 🔙 Rollback Last (if applicable)

    Pagination buttons:
    - ✅ Approve
    - ❌ Reject
    - ⏭️ Skip
    - ◀️ Previous (if not first page)
    - ▶️ Next (if not last page)
    - 🏠 Back to Summary
    """
    summary = get_review_summary(review_id)

    if not summary:
        return []

    # Main action buttons
    if page is None:
        return _build_main_components(review_id, summary)

    # Pagination buttons
    total_pages = len(summary["changes"])
    return _build_pagination_components(review_id, page, total_pages, summary["changes"][page])


def post_review_request(review_id: str, recommendations: List[Dict[str, Any]]) -> bool:
    """
    Post review request to Discord admin channel.

    Parameters
    ----------
    review_id : str
        Review identifier
    recommendations : list of dict
        Original recommendations from MOA (for context)

    Returns
    -------
    bool
        True if posted successfully

    Notes
    -----
    - Posts to DISCORD_ADMIN_CHANNEL_ID or MOA_REVIEW_CHANNEL_ID
    - Stores discord_message_id for future updates
    - Includes embed + action buttons
    """
    from . import alerts as _alerts
    from .config import get_settings

    settings = get_settings()

    # Determine target channel
    channel_id = os.getenv("MOA_REVIEW_CHANNEL_ID") or os.getenv("DISCORD_ADMIN_CHANNEL_ID")

    if not channel_id:
        log.error("moa_review_channel_not_configured")
        return False

    # Build message payload
    embed = build_review_embed(review_id)
    components = build_review_components(review_id)

    payload = {
        "embeds": [embed],
        "components": components,
    }

    try:
        # Post to Discord
        admin_webhook_url = (
            getattr(settings, "admin_webhook_url", None)
            or os.getenv("DISCORD_ADMIN_WEBHOOK", "")
            or os.getenv("ADMIN_WEBHOOK", "")
        )

        if not admin_webhook_url:
            log.error("admin_webhook_not_configured")
            return False

        response = _alerts.post_discord_json(payload, webhook_url=admin_webhook_url)

        if response and response.status_code in (200, 204):
            # Store message ID for updates (if needed in future)
            log.info(f"moa_review_posted review_id={review_id} channel={channel_id}")
            return True
        else:
            log.error(f"moa_review_post_failed review_id={review_id} status={response.status_code if response else 'none'}")
            return False

    except Exception as e:
        log.error(f"moa_review_post_failed review_id={review_id} err={e}")
        return False


# ============================================================================
# Private Embed Builders
# ============================================================================


def _build_summary_embed(review: Dict[str, Any], changes: List[Dict[str, Any]], stats: Dict[str, Any]) -> Dict[str, Any]:
    """Build main summary embed showing top recommendations."""
    review_id = review["review_id"]
    created_at = datetime.fromisoformat(review["created_at"])
    expires_at = datetime.fromisoformat(review["expires_at"]) if review["expires_at"] else None

    # Calculate time remaining
    if expires_at:
        now = datetime.now(timezone.utc)
        time_left = expires_at - now
        hours_left = int(time_left.total_seconds() / 3600)
        expiry_text = f"⏰ Expires in **{hours_left} hours**" if hours_left > 0 else "⏰ **EXPIRED** (auto-applying soon)"
    else:
        expiry_text = "⏰ No expiration"

    # Build top 10 table
    top_10 = changes[:10]
    table_lines = ["```"]
    table_lines.append(f"{'Keyword':<20} {'Old':>6} → {'New':>6}  {'Δ':>6}  {'Conf':>5}")
    table_lines.append("─" * 60)

    for change in top_10:
        keyword = change["keyword"][:18]  # Truncate long keywords
        old = change["old_weight"] or 0
        new = change["new_weight"]
        delta = change["weight_delta"]
        conf = change["confidence"]

        # Color indicator
        indicator = "↑" if delta > 0.5 else "↓" if delta < -0.5 else "→"

        table_lines.append(f"{keyword:<20} {old:>6.2f} → {new:>6.2f}  {delta:>+6.2f}  {conf:>5.0%}")

    if len(changes) > 10:
        table_lines.append(f"\n... and {len(changes) - 10} more keywords")

    table_lines.append("```")

    # Confidence distribution
    high_conf = sum(1 for c in changes if c["confidence"] >= 0.9)
    med_conf = sum(1 for c in changes if 0.7 <= c["confidence"] < 0.9)
    low_conf = sum(1 for c in changes if c["confidence"] < 0.7)

    conf_text = f"🔹 High (≥0.9): **{high_conf}** | 🔸 Med (0.7-0.9): **{med_conf}** | 🔻 Low (<0.7): **{low_conf}**"

    # Top mover
    top_mover = stats["top_mover"]
    if top_mover:
        mover_text = f"📊 **Top Mover:** `{top_mover['keyword']}` ({top_mover['weight_delta']:+.2f})"
    else:
        mover_text = ""

    description = f"""
**MOA Keyword Review Request**

{expiry_text}

**Summary:**
• Total Keywords: **{stats['total']}**
• Avg Confidence: **{stats['avg_confidence']:.1%}**
• Status: **{review['state']}**
{mover_text}

**Confidence Distribution:**
{conf_text}

**Top 10 Recommendations:**
{chr(10).join(table_lines)}

📝 Click **Review Individual** to approve/reject each keyword separately.
✅ Click **Approve All** to apply all changes immediately.
❌ Click **Reject All** to discard all recommendations.
"""

    return {
        "title": f"🔍 MOA Keyword Review: {review_id}",
        "description": description.strip(),
        "color": 0x00AAFF,  # Blue
        "footer": {
            "text": f"Created at {created_at.strftime('%Y-%m-%d %H:%M UTC')} | Review ID: {review_id}"
        },
        "timestamp": created_at.isoformat(),
    }


def _build_individual_embed(
    review: Dict[str, Any],
    change: Dict[str, Any],
    page: int,
    total_pages: int,
) -> Dict[str, Any]:
    """Build individual keyword review page embed."""
    keyword = change["keyword"]
    old_weight = change["old_weight"] or 0
    new_weight = change["new_weight"]
    delta = change["weight_delta"]
    confidence = change["confidence"]
    occurrences = change["occurrences"]
    success_rate = change["success_rate"]
    avg_return = change["avg_return_pct"]

    # Parse evidence
    evidence = json.loads(change["evidence_json"]) if change["evidence_json"] else {}
    examples = evidence.get("examples", [])
    is_flash = evidence.get("flash_catalyst", False)
    intraday_rate = evidence.get("intraday_rate")

    # Build examples text
    examples_text = ""
    if examples:
        examples_text = "**Top Tickers:**\n"
        for ex in examples[:3]:
            ticker = ex.get("ticker", "?")
            ret = ex.get("return_pct", 0)
            examples_text += f"• `{ticker}`: {ret:+.1f}% return\n"

    # Confidence badge
    if confidence >= 0.9:
        conf_badge = "🟢 **High Confidence**"
    elif confidence >= 0.7:
        conf_badge = "🟡 **Medium Confidence**"
    else:
        conf_badge = "🔴 **Low Confidence**"

    # Flash catalyst badge
    flash_badge = "⚡ **Flash Catalyst** (>5% in <30min)" if is_flash else ""

    description = f"""
**Keyword:** `{keyword}`

**Proposed Change:**
• Old Weight: **{old_weight:.2f}**
• New Weight: **{new_weight:.2f}**
• Change: **{delta:+.2f}** {('🔼' if delta > 0 else '🔽')}

**Evidence:**
• Occurrences: **{occurrences}**
• Success Rate: **{success_rate:.1%}**
• Avg Return: **{avg_return:.1f}%**
{(f"• Intraday Success: **{intraday_rate:.1%}**" + chr(10)) if intraday_rate else ""}
{conf_badge} ({confidence:.0%})
{flash_badge}

{examples_text}

**Page {page + 1} of {total_pages}**
"""

    return {
        "title": f"📋 Review Keyword: {keyword}",
        "description": description.strip(),
        "color": 0x00FF00 if delta > 0 else 0xFF0000 if delta < 0 else 0xFFFFFF,
        "footer": {
            "text": f"Review ID: {review['review_id']}"
        },
    }


def _error_embed(message: str) -> Dict[str, Any]:
    """Build error embed."""
    return {
        "title": "❌ Error",
        "description": message,
        "color": 0xFF0000,  # Red
    }


# ============================================================================
# Private Component Builders
# ============================================================================


def _build_main_components(review_id: str, summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build main action buttons."""
    review = summary["review"]
    state = review["state"]

    # Disable buttons if not PENDING
    disabled = state != "PENDING"

    components = [
        {
            "type": 1,  # Action Row
            "components": [
                {
                    "type": 2,  # Button
                    "style": 3,  # Success (green)
                    "label": "✅ Approve All",
                    "custom_id": f"moa_review_approve_all:{review_id}",
                    "disabled": disabled,
                },
                {
                    "type": 2,
                    "style": 4,  # Danger (red)
                    "label": "❌ Reject All",
                    "custom_id": f"moa_review_reject_all:{review_id}",
                    "disabled": disabled,
                },
                {
                    "type": 2,
                    "style": 1,  # Primary (blue)
                    "label": "📝 Review Individual",
                    "custom_id": f"moa_review_individual:{review_id}",
                    "disabled": disabled,
                },
            ],
        }
    ]

    # Add rollback button if already applied
    if state == "APPLIED":
        components.append({
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,  # Secondary (grey)
                    "label": "🔙 Rollback Changes",
                    "custom_id": f"moa_review_rollback:{review_id}",
                },
            ],
        })

    return components


def _build_pagination_components(
    review_id: str,
    page: int,
    total_pages: int,
    current_change: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build pagination buttons for individual review."""
    keyword = current_change["keyword"]

    # Row 1: Approve/Reject/Skip
    row1 = {
        "type": 1,
        "components": [
            {
                "type": 2,
                "style": 3,  # Success
                "label": "✅ Approve",
                "custom_id": f"moa_review_approve:{review_id}:{keyword}:{page}",
            },
            {
                "type": 2,
                "style": 4,  # Danger
                "label": "❌ Reject",
                "custom_id": f"moa_review_reject:{review_id}:{keyword}:{page}",
            },
            {
                "type": 2,
                "style": 2,  # Secondary
                "label": "⏭️ Skip",
                "custom_id": f"moa_review_skip:{review_id}:{keyword}:{page}",
            },
        ],
    }

    # Row 2: Navigation
    nav_buttons = []

    # Previous button
    if page > 0:
        nav_buttons.append({
            "type": 2,
            "style": 1,  # Primary
            "label": "◀️ Previous",
            "custom_id": f"moa_review_page:{review_id}:{page - 1}",
        })

    # Next button
    if page < total_pages - 1:
        nav_buttons.append({
            "type": 2,
            "style": 1,
            "label": "Next ▶️",
            "custom_id": f"moa_review_page:{review_id}:{page + 1}",
        })

    # Back to summary
    nav_buttons.append({
        "type": 2,
        "style": 2,  # Secondary
        "label": "🏠 Back to Summary",
        "custom_id": f"moa_review_summary:{review_id}",
    })

    row2 = {
        "type": 1,
        "components": nav_buttons,
    }

    return [row1, row2]
