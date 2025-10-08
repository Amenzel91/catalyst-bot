"""Watchdog process for monitoring and restarting the Catalyst-Bot.

This module provides a watchdog that monitors the main bot process via the health
endpoint and can restart it if it becomes unresponsive or crashes.

WAVE 2.3: 24/7 Deployment Infrastructure

Usage:
    python -m catalyst_bot.watchdog

    Or use the provided batch file:
    run_watchdog.bat
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .logging_utils import get_logger

    log = get_logger("watchdog")
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("watchdog")


def get_health_check_url() -> str:
    """Get the health check URL from environment.

    Returns
    -------
    str
        Health check URL (defaults to http://localhost:8080/health/ping)
    """
    port = os.getenv("HEALTH_CHECK_PORT", "8080")
    return f"http://localhost:{port}/health/ping"


def check_bot_alive() -> bool:
    """Check if the bot is alive by pinging the health endpoint.

    Returns
    -------
    bool
        True if bot responds, False otherwise
    """
    url = get_health_check_url()
    try:
        req = Request(
            url,
            headers={"User-Agent": "Catalyst-Bot-Watchdog/1.0"},
            method="GET",
        )
        with urlopen(req, timeout=5) as response:
            data = response.read().decode("utf-8").strip()
            # Expect "ok" response
            return data == "ok"
    except (URLError, HTTPError, Exception) as e:
        log.debug(f"health_check_failed err={e.__class__.__name__}")
        return False


def check_service_running() -> bool:
    """Check if the CatalystBot Windows service is running.

    Returns
    -------
    bool
        True if service is running, False otherwise
    """
    try:
        result = subprocess.run(
            ["nssm", "status", "CatalystBot"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # NSSM returns "SERVICE_RUNNING" when active
        return "SERVICE_RUNNING" in result.stdout
    except Exception as e:
        log.debug(f"service_check_failed err={e.__class__.__name__}")
        return False


def restart_bot(method: str = "auto") -> bool:
    """Restart the bot using the specified method.

    Parameters
    ----------
    method : str
        Restart method: "service", "process", or "auto" (default)
        - "service": Use Windows service (nssm)
        - "process": Kill and restart Python process
        - "auto": Try service first, fall back to process

    Returns
    -------
    bool
        True if restart was initiated successfully
    """
    log.warning("restart_initiated method=%s", method)

    if method in ("auto", "service"):
        # Try service restart first
        try:
            # Stop service
            log.info("stopping_service")
            subprocess.run(
                ["net", "stop", "CatalystBot"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            time.sleep(2)

            # Start service
            log.info("starting_service")
            result = subprocess.run(
                ["net", "start", "CatalystBot"],
                capture_output=True,
                timeout=30,
                check=False,
            )

            if result.returncode == 0:
                log.info("service_restarted")
                return True
            else:
                log.warning(
                    f"service_restart_failed stderr={result.stderr.decode('utf-8', errors='ignore')}"  # noqa: E501
                )

                if method == "service":
                    return False
                # Fall through to process restart if method is "auto"
        except Exception as e:
            log.error(
                f"service_restart_error err={e.__class__.__name__}", exc_info=True
            )
            if method == "service":
                return False

    if method in ("auto", "process"):
        # Process-based restart (last resort)
        log.warning("process_restart_not_implemented")
        # This would require tracking the process ID, which is complex
        # Better to use service-based restart
        return False

    return False


def send_alert_to_admin(message: str, severity: str = "warning") -> None:
    """Send an alert to the admin webhook.

    Parameters
    ----------
    message : str
        Alert message
    severity : str
        Severity level: "info", "warning", "error"
    """
    webhook_url = os.getenv("ADMIN_ALERT_WEBHOOK", "") or os.getenv(
        "DISCORD_ADMIN_WEBHOOK", ""
    )
    if not webhook_url:
        log.debug("admin_alert_skipped reason=no_webhook")
        return

    try:
        color_map = {
            "info": 0x3498DB,  # Blue
            "warning": 0xF39C12,  # Orange
            "error": 0xE74C3C,  # Red
        }

        payload = {
            "embeds": [
                {
                    "title": "Watchdog Alert",
                    "description": message,
                    "color": color_map.get(severity, 0xF39C12),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {"text": "Catalyst-Bot Watchdog"},
                }
            ]
        }

        req = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Catalyst-Bot-Watchdog/1.0",
            },
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            log.info(f"admin_alert_sent severity={severity} status={response.status}")
    except Exception as e:
        log.error(f"admin_alert_failed err={e.__class__.__name__}", exc_info=True)


def run_watchdog() -> None:
    """Run the watchdog monitoring loop.

    This function runs indefinitely, checking the bot health at regular intervals
    and restarting it if necessary.
    """
    # Configuration from environment
    check_interval = int(os.getenv("WATCHDOG_CHECK_INTERVAL", "60"))
    restart_on_freeze = os.getenv("WATCHDOG_RESTART_ON_FREEZE", "1") == "1"
    freeze_threshold = int(os.getenv("WATCHDOG_FREEZE_THRESHOLD", "300"))
    max_restart_attempts = int(os.getenv("WATCHDOG_MAX_RESTARTS", "3"))

    log.info(
        "watchdog_started interval=%ds freeze_threshold=%ds restart_on_freeze=%s",
        check_interval,
        freeze_threshold,
        restart_on_freeze,
    )

    consecutive_failures = 0
    restart_count = 0
    last_restart_time = 0

    while True:
        try:
            # Check if bot is alive
            alive = check_bot_alive()

            if alive:
                # Bot is healthy, reset failure counter
                if consecutive_failures > 0:
                    log.info("bot_recovered after=%d_failures", consecutive_failures)
                    send_alert_to_admin(
                        f"Bot recovered after {consecutive_failures} failed health checks",
                        severity="info",
                    )
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                log.warning(
                    "health_check_failed consecutive=%d threshold=%d",
                    consecutive_failures,
                    max_restart_attempts,
                )

                # Check if we should restart
                if restart_on_freeze and consecutive_failures >= (
                    freeze_threshold // check_interval
                ):
                    # Prevent restart loops (max 3 restarts per hour)
                    now = time.time()
                    if now - last_restart_time < 3600:
                        if restart_count >= max_restart_attempts:
                            log.error(
                                "restart_limit_reached count=%d window=1h",
                                restart_count,
                            )
                            send_alert_to_admin(
                                f"Bot restart limit reached ({restart_count} restarts in 1 hour). "
                                "Manual intervention required.",
                                severity="error",
                            )
                            # Reset counter after alerting
                            restart_count = 0
                            last_restart_time = 0
                            time.sleep(check_interval)
                            continue
                    else:
                        # Reset counter after 1 hour
                        restart_count = 0

                    # Attempt restart
                    log.error(
                        "bot_frozen consecutive_failures=%d restarting=true",
                        consecutive_failures,
                    )
                    send_alert_to_admin(
                        f"Bot appears frozen (no response for {consecutive_failures * check_interval}s). "  # noqa: E501
                        "Attempting automatic restart...",
                        severity="warning",
                    )

                    if restart_bot(method="auto"):
                        restart_count += 1
                        last_restart_time = time.time()
                        consecutive_failures = 0
                        log.info("restart_successful count=%d", restart_count)

                        # Wait for bot to start
                        time.sleep(30)
                    else:
                        log.error("restart_failed")
                        send_alert_to_admin(
                            "Failed to restart bot automatically. Manual intervention required.",
                            severity="error",
                        )

        except KeyboardInterrupt:
            log.info("watchdog_stopped reason=keyboard_interrupt")
            break
        except Exception as e:
            log.error(f"watchdog_error err={e.__class__.__name__}", exc_info=True)

        # Sleep until next check
        time.sleep(check_interval)


def main():
    """Entry point for watchdog module."""
    # Check if watchdog is enabled
    if os.getenv("WATCHDOG_ENABLED", "0") != "1":
        print("Watchdog is disabled. Set WATCHDOG_ENABLED=1 to enable.")
        print("Note: Watchdog is optional and only needed for production deployments.")
        return 1

    print("Starting Catalyst-Bot Watchdog...")
    print(f"Health check URL: {get_health_check_url()}")
    print(f"Check interval: {os.getenv('WATCHDOG_CHECK_INTERVAL', '60')}s")
    print(f"Freeze threshold: {os.getenv('WATCHDOG_FREEZE_THRESHOLD', '300')}s")
    print("")
    print("Press Ctrl+C to stop")
    print("")

    try:
        run_watchdog()
    except KeyboardInterrupt:
        print("\nWatchdog stopped.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
