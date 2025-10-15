"""
Discord Interaction Server
===========================

Flask server that receives Discord interaction callbacks (button clicks)
and routes them to the appropriate handlers.

This server runs locally and is exposed via Cloudflare Tunnel.

Usage:
    python interaction_server.py

The server will listen on http://localhost:8081/interactions
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load environment variables from .env
from dotenv import load_dotenv  # noqa: E402

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from flask import Flask, jsonify, request  # noqa: E402

from catalyst_bot.discord_interactions import (  # noqa: E402
    handle_interaction,
    verify_discord_signature,
)
from catalyst_bot.logging_utils import get_logger  # noqa: E402
from catalyst_bot.slash_commands import handle_slash_command  # noqa: E402

app = Flask(__name__)
log = get_logger("interaction_server")

# Get Discord public key from environment
PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY", "")


@app.route("/interactions", methods=["POST"])
def discord_interactions():
    """
    Handle Discord interaction callbacks.

    Discord sends interaction payloads here when users click buttons.
    We route them to the appropriate handler and return the response.
    """
    try:
        print(f"[DEBUG] Received request from {request.remote_addr}")
        print(f"[DEBUG] Headers: {dict(request.headers)}")
        print(f"[DEBUG] Body: {request.data}")
        print(f"[DEBUG] PUBLIC_KEY configured: {bool(PUBLIC_KEY)}")

        # Verify Discord signature if public key is configured
        if PUBLIC_KEY:
            signature = request.headers.get("X-Signature-Ed25519", "")
            timestamp = request.headers.get("X-Signature-Timestamp", "")

            if not verify_discord_signature(
                signature, timestamp, request.data, PUBLIC_KEY
            ):
                log.warning("invalid_signature")
                print("[DEBUG] Signature verification FAILED")
                return jsonify({"error": "Invalid signature"}), 401

            print("[DEBUG] Signature verification PASSED")

        interaction_data = request.json

        # Log the interaction type
        interaction_type = interaction_data.get("type")
        custom_id = interaction_data.get("data", {}).get("custom_id", "")

        log.info(f"interaction_received type={interaction_type} custom_id={custom_id}")
        print(f"[DEBUG] Interaction type: {interaction_type}")

        # Handle PING verification (Discord endpoint verification)
        if interaction_type == 1:
            log.info("responding_to_ping")
            print("[DEBUG] Responding to PING with type=1")
            return jsonify({"type": 1}), 200

        # Handle APPLICATION_COMMAND (slash commands)
        if interaction_type == 2:
            log.info("handling_slash_command")
            print("[DEBUG] Handling slash command")
            response = handle_slash_command(interaction_data)
            if response:
                return jsonify(response), 200
            else:
                return "", 204

        # Handle MESSAGE_COMPONENT (button clicks)
        if interaction_type == 3:
            log.info("handling_button_interaction")
            print("[DEBUG] Handling button interaction")
            response = handle_interaction(interaction_data)
            if response:
                return jsonify(response), 200
            else:
                return "", 204

        # Unknown interaction type
        log.warning(f"unknown_interaction_type type={interaction_type}")
        return (
            jsonify(
                {
                    "type": 4,
                    "data": {"content": "Unknown interaction type", "flags": 64},
                }
            ),
            200,
        )

    except Exception as e:
        log.error(f"interaction_failed err={e}")
        return (
            jsonify(
                {
                    "type": 4,
                    "data": {
                        "content": "An error occurred processing your request.",
                        "flags": 64,
                    },
                }
            ),
            200,
        )


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for monitoring."""
    return jsonify({"status": "healthy"}), 200


@app.route("/", methods=["GET"])
def index():
    """Root endpoint - shows server is running."""
    return """
    <html>
        <head><title>Catalyst Bot Interaction Server</title></head>
        <body>
            <h1>Catalyst Bot Interaction Server</h1>
            <p>Server is running!</p>
            <p>Interaction endpoint: <code>POST /interactions</code></p>
            <p>Health check: <code>GET /health</code></p>
        </body>
    </html>
    """


if __name__ == "__main__":
    print("=" * 60)
    print("Discord Interaction Server")
    print("=" * 60)
    print("Server starting on http://localhost:8081")
    print("Interaction endpoint: POST /interactions")
    print("=" * 60)

    # Run server
    app.run(host="0.0.0.0", port=8081, debug=False)  # Set to True for development
