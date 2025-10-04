"""Simple health check endpoint for monitoring bot status.

This module provides a lightweight HTTP server that exposes a /health endpoint
for monitoring tools, container orchestrators, or uptime checks.

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
    from .logging_utils import get_logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(_):
        return logging.getLogger("health_endpoint")

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
    error: str = None
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
        _HEALTH_STATUS["errors"].append({
            "time": datetime.now(timezone.utc).isoformat(),
            "error": error
        })
        # Keep only last 10 errors
        _HEALTH_STATUS["errors"] = _HEALTH_STATUS["errors"][-10:]

    # Update uptime
    if _HEALTH_STATUS["start_time"]:
        start = datetime.fromisoformat(_HEALTH_STATUS["start_time"])
        _HEALTH_STATUS["uptime_seconds"] = (datetime.now(timezone.utc) - start).total_seconds()


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoint."""

    def log_message(self, format, *args):
        """Suppress default HTTP server logging to avoid noise."""
        pass

    def do_GET(self):
        """Handle GET requests to /health endpoint."""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/":
            self._handle_root()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def _handle_root(self):
        """Root endpoint returns simple message."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Catalyst-Bot Health Check Server\nGET /health for status")

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
            last_cycle_time=datetime.now(timezone.utc),
            total_cycles=10,
            total_alerts=5
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
