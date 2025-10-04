"""Discord message components and interaction handling for timeframe switching.

This module provides helper functions to add interactive buttons to Discord
alert messages, allowing users to switch between chart timeframes (1D, 5D, 1M, 3M, 1Y).

Note: Full interaction handling requires a Discord Application with an interaction
endpoint URL configured. For webhook-only setups, buttons can be disabled or
alternative approaches (like reaction-based switching) can be used.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(_):
        return logging.getLogger("discord_interactions")

try:
    from .validation import validate_ticker, validate_timeframe
except Exception:
    # Fallback validation if module not available
    def validate_ticker(t, allow_empty=False):
        if not t:
            return None if not allow_empty else ""
        return str(t).strip().upper() or None

    def validate_timeframe(tf):
        if not tf:
            return None
        return str(tf).strip().upper()

log = get_logger("discord_interactions")


# Timeframe button labels and emoji
TIMEFRAME_BUTTONS = [
    {"label": "1D", "custom_id": "chart_1D", "emoji": "📊"},
    {"label": "5D", "custom_id": "chart_5D", "emoji": "📈"},
    {"label": "1M", "custom_id": "chart_1M", "emoji": "📉"},
    {"label": "3M", "custom_id": "chart_3M", "emoji": "📊"},
    {"label": "1Y", "custom_id": "chart_1Y", "emoji": "📈"},
]


def create_timeframe_buttons(
    ticker: str,
    current_timeframe: str = "1D",
) -> List[Dict[str, Any]]:
    """Create Discord button components for timeframe selection.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    current_timeframe : str
        Currently displayed timeframe (will be styled as disabled/primary)

    Returns
    -------
    List[Dict[str, Any]]
        List of action rows containing button components
    """
    buttons = []

    for btn_config in TIMEFRAME_BUTTONS:
        tf = btn_config["label"]
        is_current = (tf == current_timeframe)

        button = {
            "type": 2,  # Button component
            "style": 1 if is_current else 2,  # Primary (blue) if current, else Secondary (gray)
            "label": btn_config["label"],
            "custom_id": f"chart_{ticker}_{tf}",  # Include ticker in custom_id
            "disabled": is_current,  # Disable current timeframe button
        }

        # Add emoji if available
        if "emoji" in btn_config:
            button["emoji"] = {"name": btn_config["emoji"]}

        buttons.append(button)

    # Discord requires buttons in action rows (max 5 buttons per row)
    action_row = {
        "type": 1,  # Action row
        "components": buttons
    }

    return [action_row]


def add_components_to_payload(
    payload: Dict[str, Any],
    ticker: str,
    current_timeframe: str = "1D"
) -> Dict[str, Any]:
    """Add interactive components (buttons) to a Discord webhook payload.

    Parameters
    ----------
    payload : Dict[str, Any]
        Discord webhook payload (must have 'embeds' or 'content')
    ticker : str
        Stock ticker symbol
    current_timeframe : str
        Currently displayed timeframe

    Returns
    -------
    Dict[str, Any]
        Updated payload with components added
    """
    # Only add components if feature is enabled
    if not _components_enabled():
        return payload

    components = create_timeframe_buttons(ticker, current_timeframe)
    payload["components"] = components

    return payload


def _components_enabled() -> bool:
    """Check if Discord components are enabled via environment variable."""
    return os.getenv("FEATURE_CHART_BUTTONS", "1").strip().lower() in {
        "1", "true", "yes", "on"
    }


def handle_interaction(
    interaction_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Handle a Discord interaction (button click).

    This function processes the interaction and returns a response payload
    that should be sent back to Discord.

    Parameters
    ----------
    interaction_data : Dict[str, Any]
        Interaction payload from Discord

    Returns
    -------
    Dict[str, Any] or None
        Response payload to send to Discord, or None if interaction is invalid
    """
    try:
        interaction_type = interaction_data.get("type")

        # Type 3 = Message Component (button click)
        if interaction_type != 3:
            log.warning("unsupported_interaction_type type=%s", interaction_type)
            return None

        # Extract custom_id
        component_data = interaction_data.get("data", {})
        custom_id = component_data.get("custom_id", "")

        # Route admin interactions to admin handler
        if custom_id.startswith("admin_"):
            from .admin_interactions import handle_admin_interaction
            return handle_admin_interaction(interaction_data)

        if not custom_id.startswith("chart_"):
            log.warning("unknown_custom_id id=%s", custom_id)
            return None

        # Parse custom_id: chart_{ticker}_{timeframe}
        parts = custom_id.split("_")
        if len(parts) != 3:
            log.warning("invalid_custom_id_format id=%s", custom_id)
            return None

        _, ticker, timeframe = parts

        # Validate ticker and timeframe to prevent injection attacks
        ticker = validate_ticker(ticker)
        timeframe = validate_timeframe(timeframe)

        if not ticker or not timeframe:
            log.warning("validation_failed ticker=%s timeframe=%s", ticker, timeframe)
            return {
                "type": 4,
                "data": {
                    "content": "❌ Invalid ticker or timeframe",
                    "flags": 64,
                }
            }

        log.info(
            "interaction_received ticker=%s tf=%s",
            ticker, timeframe
        )

        # Generate new chart for the requested timeframe
        from .charts_advanced import generate_multi_panel_chart
        from .chart_cache import get_cache

        cache = get_cache()

        # Try cache first
        chart_path = cache.get(ticker, timeframe)

        if chart_path is None:
            # Generate new chart
            chart_path = generate_multi_panel_chart(
                ticker,
                timeframe=timeframe,
                style="dark"
            )

            if chart_path:
                cache.put(ticker, timeframe, chart_path)

        if chart_path is None:
            # Failed to generate chart
            return {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": f"❌ Failed to generate {timeframe} chart for {ticker}",
                    "flags": 64,  # Ephemeral (only visible to user who clicked)
                }
            }

        # Extract metadata from interaction for editing
        message = interaction_data.get("message")
        message_id = message.get("id") if isinstance(message, dict) else None
        channel_id = interaction_data.get("channel_id")

        # Get bot token from environment
        bot_token = os.getenv("DISCORD_BOT_TOKEN")

        if not (bot_token and message_id and channel_id):
            log.warning("missing_bot_metadata bot_token=%s msg_id=%s ch_id=%s",
                       bool(bot_token), bool(message_id), bool(channel_id))
            return {
                "type": 4,
                "data": {
                    "content": "❌ Failed to update chart (missing configuration)",
                    "flags": 64,
                }
            }

        # Build new embed
        embed = {
            "color": 0x2ECC71,  # Green
            "image": {
                "url": f"attachment://{chart_path.name}"
            },
            "footer": {
                "text": f"Timeframe: {timeframe} | Click a button to switch"
            }
        }

        # Edit message with new chart via bot API
        import requests
        import json

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"

        headers = {
            "Authorization": f"Bot {bot_token}"
        }

        payload = {
            "embeds": [embed],
            "components": create_timeframe_buttons(ticker, timeframe),
        }

        data = {
            "payload_json": json.dumps(payload)
        }

        try:
            with open(chart_path, "rb") as f:
                files = {
                    "file": (chart_path.name, f, "image/png")
                }
                resp = requests.patch(url, headers=headers, data=data, files=files, timeout=15)

            if resp.ok:
                log.info("chart_switched ticker=%s tf=%s", ticker, timeframe)
                # Return deferred update (type 6) to acknowledge interaction
                return {"type": 6}
            else:
                log.warning("chart_switch_failed status=%d body=%s", resp.status_code, resp.text[:200])
                return {
                    "type": 4,
                    "data": {
                        "content": f"❌ Failed to update chart (HTTP {resp.status_code})",
                        "flags": 64,
                    }
                }
        except Exception as e:
            log.warning("chart_switch_exception err=%s", str(e))
            return {
                "type": 4,
                "data": {
                    "content": f"❌ Failed to update chart: {str(e)}",
                    "flags": 64,
                }
            }

    except Exception as e:
        log.warning("interaction_handle_failed err=%s", str(e))
        return {
            "type": 4,
            "data": {
                "content": "❌ An error occurred while processing your request",
                "flags": 64,
            }
        }


def verify_discord_signature(
    signature: str,
    timestamp: str,
    body: bytes,
    public_key: str
) -> bool:
    """Verify that a Discord interaction request is authentic.

    Parameters
    ----------
    signature : str
        X-Signature-Ed25519 header from Discord
    timestamp : str
        X-Signature-Timestamp header from Discord
    body : bytes
        Raw request body
    public_key : str
        Discord application public key

    Returns
    -------
    bool
        True if signature is valid, False otherwise
    """
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        verify_key = VerifyKey(bytes.fromhex(public_key))
        message = timestamp.encode() + body

        verify_key.verify(message, bytes.fromhex(signature))
        return True

    except BadSignatureError:
        log.warning("invalid_discord_signature")
        return False
    except Exception as e:
        log.warning("signature_verification_failed err=%s", str(e))
        return False


# ============================================================================
# Flask endpoint example (for reference - not auto-registered)
# ============================================================================

def create_interaction_endpoint_flask():
    """Create a Flask endpoint to handle Discord interactions.

    Returns
    -------
    Flask app
        Flask application with /interactions endpoint configured

    Example
    -------
    >>> app = create_interaction_endpoint_flask()
    >>> app.run(host='0.0.0.0', port=3000)
    """
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        raise ImportError(
            "Flask is required for interaction endpoints. "
            "Install it with: pip install flask"
        )

    app = Flask(__name__)

    PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY", "")

    @app.route("/interactions", methods=["POST"])
    def interactions():
        # Verify signature
        signature = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")

        if PUBLIC_KEY and not verify_discord_signature(
            signature, timestamp, request.data, PUBLIC_KEY
        ):
            return jsonify({"error": "Invalid signature"}), 401

        data = request.json

        # Type 1 = PING (Discord verification)
        if data.get("type") == 1:
            return jsonify({"type": 1})

        # Type 3 = MESSAGE_COMPONENT
        if data.get("type") == 3:
            response = handle_interaction(data)
            if response:
                return jsonify(response)

        return jsonify({"error": "Unknown interaction"}), 400

    return app


# ============================================================================
# Message editing helper (for webhook-based approach)
# ============================================================================

def edit_message_with_chart(
    webhook_url: str,
    message_id: str,
    ticker: str,
    timeframe: str,
    chart_path: Path
) -> bool:
    """Edit a Discord message to update its chart image.

    Parameters
    ----------
    webhook_url : str
        Discord webhook URL
    message_id : str
        ID of the message to edit
    ticker : str
        Stock ticker symbol
    timeframe : str
        New timeframe to display
    chart_path : Path
        Path to the chart image

    Returns
    -------
    bool
        True if edit was successful, False otherwise
    """
    try:
        import requests

        # Extract webhook ID and token from URL
        # Format: https://discord.com/api/webhooks/{id}/{token}
        parts = webhook_url.rstrip("/").split("/")
        webhook_id = parts[-2]
        webhook_token = parts[-1]

        # Build edit endpoint
        edit_url = (
            f"https://discord.com/api/v10/webhooks/{webhook_id}/"
            f"{webhook_token}/messages/{message_id}"
        )

        # Build new embed
        embed = {
            "title": f"{ticker} - {timeframe} Chart",
            "color": 0x2ECC71,
            "image": {
                "url": f"attachment://{chart_path.name}"
            },
            "footer": {
                "text": f"Timeframe: {timeframe} | Generated charts"
            }
        }

        # Build components (buttons)
        components = create_timeframe_buttons(ticker, timeframe)

        # Prepare multipart upload
        files = {
            "file": (chart_path.name, chart_path.open("rb"), "image/png")
        }

        payload = {
            "embeds": [embed],
            "components": components,
        }

        data = {
            "payload_json": json.dumps(payload)
        }

        # Send PATCH request
        resp = requests.patch(
            edit_url,
            data=data,
            files=files,
            timeout=15
        )

        if resp.ok:
            log.info(
                "message_edited message_id=%s ticker=%s tf=%s",
                message_id, ticker, timeframe
            )
            return True
        else:
            log.warning(
                "message_edit_failed status=%d message_id=%s",
                resp.status_code, message_id
            )
            return False

    except Exception as e:
        log.warning(
            "message_edit_exception message_id=%s err=%s",
            message_id, str(e)
        )
        return False
