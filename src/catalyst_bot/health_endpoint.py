"""Enhanced health check endpoint for monitoring bot status.

This module provides a lightweight HTTP server that exposes multiple health endpoints:
- /health/ping - Simple "ok" response for uptime monitoring
- /health - Basic health status
- /health/detailed - Comprehensive health metrics with GPU, disk, services

WAVE 2.3: 24/7 Deployment Infrastructure

Usage:
    Run in a separate thread alongside the main bot:

    from catalyst_bot.health_endpoint import start_health_server
    start_health_server(port=8080)
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

try:
    from .health_monitor import get_health_status, is_healthy
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("health_endpoint")

    def get_health_status():
        return {"status": "unknown", "error": "health_monitor not available"}

    def is_healthy():
        return True


log = get_logger("health_endpoint")


# Global health status tracking
_HEALTH_STATUS: Dict[str, Any] = {
    "status": "starting",
    "uptime_seconds": 0,
    "start_time": None,
    "last_cycle_time": None,
    "total_cycles": 0,
    "total_alerts": 0,
    "errors": [],
}


def update_health_status(
    status: str = None,
    last_cycle_time: datetime = None,
    total_cycles: int = None,
    total_alerts: int = None,
    error: str = None,
) -> None:
    """Update the health status from the main bot loop.

    Parameters
    ----------
    status : str
        Overall status: "healthy", "degraded", "starting", "stopping"
    last_cycle_time : datetime
        Timestamp of the last successful cycle completion
    total_cycles : int
        Total number of cycles completed
    total_alerts : int
        Total number of alerts sent
    error : str
        Error message to add to error log (keeps last 10)
    """
    global _HEALTH_STATUS

    if status:
        _HEALTH_STATUS["status"] = status

    if last_cycle_time:
        _HEALTH_STATUS["last_cycle_time"] = last_cycle_time.isoformat()

    if total_cycles is not None:
        _HEALTH_STATUS["total_cycles"] = total_cycles

    if total_alerts is not None:
        _HEALTH_STATUS["total_alerts"] = total_alerts

    if error:
        _HEALTH_STATUS["errors"].append(
            {"time": datetime.now(timezone.utc).isoformat(), "error": error}
        )
        # Keep only last 10 errors
        _HEALTH_STATUS["errors"] = _HEALTH_STATUS["errors"][-10:]

    # Update uptime
    if _HEALTH_STATUS["start_time"]:
        start = datetime.fromisoformat(_HEALTH_STATUS["start_time"])
        _HEALTH_STATUS["uptime_seconds"] = (
            datetime.now(timezone.utc) - start
        ).total_seconds()


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoint."""

    def log_message(self, format, *args):
        """Suppress default HTTP server logging to avoid noise."""

    def do_GET(self):
        """Handle GET requests to health endpoints."""
        if self.path == "/health/ping":
            self._handle_ping()
        elif self.path == "/health/detailed":
            self._handle_detailed()
        elif self.path == "/health":
            self._handle_health()
        elif self.path == "/":
            self._handle_root()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        """Handle POST requests for Discord interactions."""
        if self.path == "/interactions":
            self._handle_discord_interaction()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def _handle_root(self):
        """Root endpoint returns simple message."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        msg = (
            b"Catalyst-Bot Health Check Server\n"
            b"Endpoints:\n"
            b"  GET /health/ping     - Simple uptime check\n"
            b"  GET /health          - Basic health status\n"
            b"  GET /health/detailed - Comprehensive metrics\n"
        )
        self.wfile.write(msg)

    def _handle_ping(self):
        """Simple ping endpoint for uptime monitoring (UptimeRobot compatible)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def _handle_detailed(self):
        """Detailed health endpoint with comprehensive metrics."""
        try:
            # Get comprehensive health status from health_monitor
            health = get_health_status()

            # Merge with existing _HEALTH_STATUS for backward compatibility
            health["start_time"] = _HEALTH_STATUS.get("start_time")

            status_code = 200 if health.get("status") == "healthy" else 503

            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(health, indent=2).encode())
        except Exception as e:
            log.error(
                f"detailed_health_error err={e.__class__.__name__}", exc_info=True
            )
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Return generic error to client, log full details server-side
            error_response = {
                "status": "error",
                "error": "Internal server error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.wfile.write(json.dumps(error_response).encode())

    def _handle_health(self):
        """Health endpoint returns JSON status."""
        # Calculate staleness - if last cycle was > 5 minutes ago, mark degraded
        status = _HEALTH_STATUS["status"]
        if _HEALTH_STATUS["last_cycle_time"]:
            last_cycle = datetime.fromisoformat(_HEALTH_STATUS["last_cycle_time"])
            staleness = (datetime.now(timezone.utc) - last_cycle).total_seconds()
            if staleness > 300 and status == "healthy":  # 5 minutes
                status = "degraded"

        # Build response
        response = {
            "status": status,
            "uptime_seconds": int(_HEALTH_STATUS["uptime_seconds"]),
            "start_time": _HEALTH_STATUS["start_time"],
            "last_cycle_time": _HEALTH_STATUS["last_cycle_time"],
            "total_cycles": _HEALTH_STATUS["total_cycles"],
            "total_alerts": _HEALTH_STATUS["total_alerts"],
            "recent_errors": _HEALTH_STATUS["errors"][-5:],  # Last 5 errors
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Return 200 if healthy, 503 if degraded/stopping
        status_code = 200 if status == "healthy" else 503

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response, indent=2).encode())

    def _handle_discord_interaction(self):
        """Handle Discord interaction (component interactions, slash commands).

        WARNING: This endpoint is missing Discord signature verification.
        If exposed publicly, it MUST implement signature verification using
        X-Signature-Ed25519 and X-Signature-Timestamp headers.

        See interaction_server.py for reference implementation with
        verify_discord_signature() from discord_interactions module.

        For production use, either:
        1. Add signature verification (requires DISCORD_PUBLIC_KEY)
        2. Only expose via authenticated proxy/tunnel
        3. Use interaction_server.py instead
        """
        try:
            # TODO: Add Discord signature verification before production deployment
            # signature = self.headers.get("X-Signature-Ed25519", "")
            # timestamp = self.headers.get("X-Signature-Timestamp", "")
            # if PUBLIC_KEY and not verify_discord_signature(
            #     signature, timestamp, body, PUBLIC_KEY
            # ):
            #     return 401 Unauthorized

            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # Parse interaction payload
            interaction = json.loads(body.decode())

            # Route based on interaction type
            interaction_type = interaction.get("type")

            # Type 1: PING (Discord verification)
            if interaction_type == 1:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"type": 1}).encode())
                return

            # Type 3: MESSAGE_COMPONENT (button/select menu interactions)
            elif interaction_type == 3:
                custom_id = interaction.get("data", {}).get("custom_id", "")

                # Route chart indicator toggle interactions
                if custom_id.startswith("chart_toggle_"):
                    try:
                        from .commands.chart_interactions import (
                            handle_chart_indicator_toggle,
                        )

                        response = handle_chart_indicator_toggle(interaction)

                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(response).encode())
                        return

                    except Exception as e:
                        log.error(f"chart_interaction_error err={e}", exc_info=True)
                        # Return generic error to user, log full details server-side
                        error_response = {
                            "type": 4,
                            "data": {
                                "content": "❌ Error processing chart interaction",
                                "flags": 64,
                            },
                        }
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(error_response).encode())
                        return

            # Unknown interaction type
            log.warning(f"unknown_interaction_type type={interaction_type}")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error = {"error": "Unknown interaction type"}
            self.wfile.write(json.dumps(error).encode())

        except Exception as e:
            log.error(f"interaction_handler_error err={e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Return generic error to client, log full details server-side
            error = {"error": "Internal server error"}
            self.wfile.write(json.dumps(error).encode())


def _run_server(port: int):
    """Run the health check HTTP server (blocking)."""
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    log.info("health_server_started port=%d", port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("health_server_stopped")
    finally:
        server.server_close()


def start_health_server(port: int = None) -> threading.Thread:
    """Start the health check server in a background thread.

    Parameters
    ----------
    port : int
        Port to listen on (default: 8080, or HEALTH_CHECK_PORT env var)

    Returns
    -------
    threading.Thread
        The server thread (daemon mode, will stop when main thread exits)
    """
    if port is None:
        port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))

    # Initialize health status
    _HEALTH_STATUS["start_time"] = datetime.now(timezone.utc).isoformat()
    _HEALTH_STATUS["status"] = "starting"

    # Start server in daemon thread
    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()

    log.info("health_server_thread_started port=%d", port)
    return thread


if __name__ == "__main__":
    # Standalone test
    print("Starting health check server on port 8080...")
    print("Try: curl http://localhost:8080/health")

    # Update status after 2 seconds to simulate bot starting
    def update_loop():
        time.sleep(2)
        update_health_status(status="healthy", total_cycles=1, total_alerts=0)
        print("Status updated to healthy")

        time.sleep(5)
        update_health_status(
            last_cycle_time=datetime.now(timezone.utc), total_cycles=10, total_alerts=5
        )
        print("Status updated with cycle data")

    threading.Thread(target=update_loop, daemon=True).start()
    start_health_server(8080)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
