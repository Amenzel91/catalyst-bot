"""
Admin Discord Interactions Handler
===================================

Handles Discord interaction callbacks for admin control buttons:
- View Details: Expands backtest breakdown
- Approve Changes: Applies recommended parameter adjustments
- Reject Changes: Keeps current settings
- Custom Adjust: Opens modal for manual parameter tweaking

This module processes Discord interaction payloads and updates bot
configuration in real-time without requiring a full restart.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict

from .admin_controls import load_admin_report
from .config_updater import apply_parameter_changes
from .logging_utils import get_logger

log = get_logger("admin_interactions")


# ======================== Interaction Types ========================

INTERACTION_TYPE_PING = 1
INTERACTION_TYPE_COMMAND = 2
INTERACTION_TYPE_COMPONENT = 3  # Button clicks
INTERACTION_TYPE_MODAL_SUBMIT = 5


RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_MESSAGE = 4
RESPONSE_TYPE_DEFERRED_UPDATE = 6
RESPONSE_TYPE_UPDATE_MESSAGE = 7
RESPONSE_TYPE_MODAL = 9


# ======================== Response Builders ========================


def build_details_embed(report_id: str) -> Dict[str, Any]:
    """Build detailed breakdown embed for a report."""
    report = load_admin_report(report_id)
    if not report:
        return {"content": "❌ Report not found.", "flags": 64}  # Ephemeral

    # Build detailed fields
    fields = []

    # Backtest details
    bt = report.backtest_summary
    misses = bt.n - bt.hits  # Calculate misses
    fields.append(
        {
            "name": "📊 Backtest Breakdown",
            "value": (
                f"**Total Trades:** {bt.n}\n"
                f"**Wins:** {bt.hits} ({bt.hit_rate:.1%})\n"
                f"**Losses:** {misses} ({(1 - bt.hit_rate):.1%})\n"
                f"**Avg Win/Loss:** {bt.avg_win_loss:.2f}\n"
                f"**Avg Return:** {bt.avg_return:+.2%}\n"
                f"**Max Drawdown:** {bt.max_drawdown:.2%}"
            ),
            "inline": False,
        }
    )

    # Top 5 keyword performers
    if report.keyword_performance:
        kw_lines = []
        for kp in report.keyword_performance[:5]:
            kp.hits + kp.misses + kp.neutrals
            kw_lines.append(
                f"**{kp.category}:** {kp.hit_rate:.0%} win rate "
                f"({kp.hits}W/{kp.misses}L/{kp.neutrals}N) | "
                f"Avg: {kp.avg_return:+.1f}%"
            )
        fields.append(
            {
                "name": "🏆 Top Keyword Categories",
                "value": "\n".join(kw_lines),
                "inline": False,
            }
        )

    # Parameter recommendations
    if report.parameter_recommendations:
        rec_lines = []
        for rec in report.parameter_recommendations:
            impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                rec.impact, "⚪"
            )

            rec_lines.append(
                f"{impact_emoji} **{rec.name}:** "
                f"{rec.current_value} → {rec.proposed_value}\n"
                f"   _{rec.reason}_"
            )

        fields.append(
            {
                "name": "⚙️ Recommended Parameter Changes",
                "value": "\n\n".join(rec_lines[:5]),  # Show top 5
                "inline": False,
            }
        )

    embed = {
        "title": f"📊 Detailed Report – {report.date}",
        "color": 0x3498DB,
        "fields": fields,
        "footer": {"text": "Use Approve/Reject buttons to apply or dismiss changes"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {"embeds": [embed], "flags": 64}  # Ephemeral (only visible to admin)


def build_approval_response(
    report_id: str, success: bool, message: str
) -> Dict[str, Any]:
    """Build response for approval/rejection actions."""
    color = 0x2ECC71 if success else 0xE74C3C  # Green or Red
    emoji = "✅" if success else "❌"

    embed = {
        "title": f"{emoji} Parameter Update",
        "description": message,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {"embeds": [embed], "flags": 64}  # Ephemeral


def build_custom_modal(report_id: str) -> Dict[str, Any]:
    """Build modal for custom parameter adjustment."""
    report = load_admin_report(report_id)
    if not report:
        return build_approval_response(report_id, False, "Report not found.")

    # Build modal with input fields for key parameters
    components = [
        {
            "type": 1,  # Action Row
            "components": [
                {
                    "type": 4,  # Text Input
                    "custom_id": "min_score",
                    "label": "Minimum Sentiment Score (0-1)",
                    "style": 1,  # Short
                    "placeholder": str(os.getenv("MIN_SCORE", "0")),
                    "required": False,
                }
            ],
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 4,
                    "custom_id": "price_ceiling",
                    "label": "Price Ceiling ($)",
                    "style": 1,
                    "placeholder": str(os.getenv("PRICE_CEILING", "10")),
                    "required": False,
                }
            ],
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 4,
                    "custom_id": "confidence_high",
                    "label": "High Confidence Threshold (0-1)",
                    "style": 1,
                    "placeholder": str(os.getenv("CONFIDENCE_HIGH", "0.8")),
                    "required": False,
                }
            ],
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 4,
                    "custom_id": "max_alerts_per_cycle",
                    "label": "Max Alerts Per Cycle",
                    "style": 1,
                    "placeholder": str(os.getenv("MAX_ALERTS_PER_CYCLE", "40")),
                    "required": False,
                }
            ],
        },
    ]

    return {
        "type": RESPONSE_TYPE_MODAL,
        "data": {
            "custom_id": f"admin_modal_{report_id}",
            "title": "Custom Parameter Adjustment",
            "components": components,
        },
    }


# ======================== Interaction Handler ========================


def handle_admin_interaction(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle admin control button interactions.

    Parameters
    ----------
    interaction_data : dict
        Discord interaction payload

    Returns
    -------
    dict
        Discord interaction response
    """
    interaction_type = interaction_data.get("type")

    # Handle ping (Discord verification)
    if interaction_type == INTERACTION_TYPE_PING:
        return {"type": RESPONSE_TYPE_PONG}

    # Extract custom_id from button click
    if interaction_type != INTERACTION_TYPE_COMPONENT:
        component_data = interaction_data.get("data", {})
        if component_data.get("component_type") == 3:  # Button
            interaction_type = INTERACTION_TYPE_COMPONENT

    if interaction_type == INTERACTION_TYPE_COMPONENT:
        data = interaction_data.get("data", {})
        custom_id = data.get("custom_id", "")

        log.info(f"admin_interaction custom_id={custom_id}")

        # Parse custom_id: admin_{action}_{report_id}
        if not custom_id.startswith("admin_"):
            return {
                "type": RESPONSE_TYPE_UPDATE_MESSAGE,
                "data": {"content": "❌ Invalid interaction", "flags": 64},
            }

        parts = custom_id.split("_")
        if len(parts) < 3:
            return {
                "type": RESPONSE_TYPE_UPDATE_MESSAGE,
                "data": {"content": "❌ Invalid interaction format", "flags": 64},
            }

        action = parts[1]
        report_id = "_".join(parts[2:])

        # Route to appropriate handler
        if action == "details":
            response_data = build_details_embed(report_id)
            return {"type": RESPONSE_TYPE_MESSAGE, "data": response_data}

        elif action == "approve":
            return handle_approve(report_id)

        elif action == "reject":
            return handle_reject(report_id)

        elif action == "custom":
            modal_response = build_custom_modal(report_id)
            return modal_response

    # Handle modal submission
    elif interaction_type == INTERACTION_TYPE_MODAL_SUBMIT:
        return handle_modal_submit(interaction_data)

    return {
        "type": RESPONSE_TYPE_UPDATE_MESSAGE,
        "data": {"content": "❌ Unknown interaction type", "flags": 64},
    }


def handle_approve(report_id: str) -> Dict[str, Any]:
    """Apply recommended parameter changes."""
    report = load_admin_report(report_id)
    if not report:
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response(report_id, False, "Report not found."),
        }

    # Build parameter changes dict
    changes = {}
    for rec in report.parameter_recommendations:
        changes[rec.name] = rec.proposed_value

    # Apply changes
    try:
        success, message = apply_parameter_changes(changes)
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response(report_id, success, message),
        }
    except Exception as e:
        log.error(f"failed_to_apply_changes err={e}")
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response(
                report_id, False, f"Failed to apply changes: {e}"
            ),
        }


def handle_reject(report_id: str) -> Dict[str, Any]:
    """Reject recommended changes and keep current settings."""
    message = (
        f"Rejected parameter changes for report {report_id}. "
        "Current settings remain unchanged."
    )
    return {
        "type": RESPONSE_TYPE_MESSAGE,
        "data": build_approval_response(report_id, True, message),
    }


def handle_modal_submit(interaction_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle custom parameter modal submission."""
    data = interaction_data.get("data", {})
    custom_id = data.get("custom_id", "")
    components = data.get("components", [])

    # Extract report_id from custom_id: admin_modal_{report_id}
    if not custom_id.startswith("admin_modal_"):
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response("", False, "Invalid modal submission"),
        }

    report_id = custom_id.replace("admin_modal_", "")

    # Parse submitted values
    changes = {}
    for action_row in components:
        for component in action_row.get("components", []):
            field_id = component.get("custom_id")
            value = component.get("value", "").strip()

            if not value:
                continue

            # Map field_id to environment variable name
            field_map = {
                "min_score": "MIN_SCORE",
                "price_ceiling": "PRICE_CEILING",
                "confidence_high": "CONFIDENCE_HIGH",
                "max_alerts_per_cycle": "MAX_ALERTS_PER_CYCLE",
            }

            env_var = field_map.get(field_id)
            if env_var:
                try:
                    # Convert to appropriate type
                    if env_var == "MAX_ALERTS_PER_CYCLE":
                        changes[env_var] = int(value)
                    else:
                        changes[env_var] = float(value)
                except ValueError:
                    continue

    # Apply changes
    if not changes:
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response(
                report_id, False, "No valid changes provided."
            ),
        }

    try:
        success, message = apply_parameter_changes(changes)
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response(report_id, success, message),
        }
    except Exception as e:
        log.error(f"failed_to_apply_custom_changes err={e}")
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": build_approval_response(
                report_id, False, f"Failed to apply changes: {e}"
            ),
        }
