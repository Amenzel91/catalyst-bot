"""Enhanced health monitoring for Catalyst-Bot.

This module provides comprehensive health metrics including uptime, cycle timing,
error tracking, GPU utilization, and service status checks.

WAVE 2.3: 24/7 Deployment Infrastructure
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    def get_logger(_):
        return logging.getLogger("health_monitor")


log = get_logger("health_monitor")


# Global state tracking
_START_TIME: Optional[float] = None
_LAST_CYCLE_TIME: Optional[float] = None
_CYCLE_COUNT: int = 0
_ALERT_COUNT_TODAY: int = 0
_ALERT_COUNT_WEEK: int = 0
_ERROR_COUNT_HOUR: int = 0
_LAST_ERROR_RESET: float = 0
_LAST_DAY_RESET: int = 0
_LAST_WEEK_RESET: int = 0


def init_health_monitor() -> None:
    """Initialize health monitoring. Call this at bot startup."""
    global _START_TIME, _LAST_ERROR_RESET, _LAST_DAY_RESET, _LAST_WEEK_RESET
    _START_TIME = time.time()
    _LAST_ERROR_RESET = time.time()
    now = datetime.now(timezone.utc)
    _LAST_DAY_RESET = now.timetuple().tm_yday
    _LAST_WEEK_RESET = now.isocalendar()[1]
    log.info("health_monitor_initialized")


def record_cycle() -> None:
    """Record a successful cycle completion."""
    global _LAST_CYCLE_TIME, _CYCLE_COUNT
    _LAST_CYCLE_TIME = time.time()
    _CYCLE_COUNT += 1


def record_alert() -> None:
    """Record an alert being sent."""
    global _ALERT_COUNT_TODAY, _ALERT_COUNT_WEEK, _LAST_DAY_RESET, _LAST_WEEK_RESET

    now = datetime.now(timezone.utc)
    current_day = now.timetuple().tm_yday
    current_week = now.isocalendar()[1]

    # Reset daily counter if day changed
    if current_day != _LAST_DAY_RESET:
        _ALERT_COUNT_TODAY = 0
        _LAST_DAY_RESET = current_day

    # Reset weekly counter if week changed
    if current_week != _LAST_WEEK_RESET:
        _ALERT_COUNT_WEEK = 0
        _LAST_WEEK_RESET = current_week

    _ALERT_COUNT_TODAY += 1
    _ALERT_COUNT_WEEK += 1


def record_error() -> None:
    """Record an error occurrence."""
    global _ERROR_COUNT_HOUR, _LAST_ERROR_RESET

    now = time.time()
    # Reset hourly error counter
    if now - _LAST_ERROR_RESET > 3600:
        _ERROR_COUNT_HOUR = 0
        _LAST_ERROR_RESET = now

    _ERROR_COUNT_HOUR += 1


def get_uptime() -> float:
    """Get bot uptime in seconds.

    Returns
    -------
    float
        Uptime in seconds, or 0 if not initialized
    """
    if _START_TIME is None:
        return 0.0
    return time.time() - _START_TIME


def get_last_cycle_time() -> Optional[float]:
    """Get time (seconds) since last successful cycle.

    Returns
    -------
    float or None
        Seconds since last cycle, or None if no cycles yet
    """
    if _LAST_CYCLE_TIME is None:
        return None
    return time.time() - _LAST_CYCLE_TIME


def get_error_count() -> int:
    """Get error count in the last hour.

    Returns
    -------
    int
        Number of errors in the last hour
    """
    # Reset if hour has passed
    now = time.time()
    if now - _LAST_ERROR_RESET > 3600:
        return 0
    return _ERROR_COUNT_HOUR


def get_alert_stats() -> Dict[str, int]:
    """Get alert statistics.

    Returns
    -------
    dict
        Dictionary with 'today' and 'week' alert counts
    """
    return {"today": _ALERT_COUNT_TODAY, "week": _ALERT_COUNT_WEEK}


def get_gpu_stats() -> Dict[str, Any]:
    """Get GPU utilization and VRAM usage.

    Returns
    -------
    dict
        GPU statistics, or empty dict if unavailable
    """
    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]  # Use first GPU
            return {
                "utilization": round(gpu.load * 100, 1),
                "vram_used_mb": round(gpu.memoryUsed, 1),
                "vram_total_mb": round(gpu.memoryTotal, 1),
                "vram_percent": round((gpu.memoryUsed / gpu.memoryTotal) * 100, 1),
                "temperature": gpu.temperature,
            }
    except Exception:
        pass
    return {}


def get_disk_stats() -> Dict[str, Any]:
    """Get disk space information.

    Returns
    -------
    dict
        Disk statistics for the bot directory
    """
    try:
        import shutil

        from .config import get_settings

        settings = get_settings()
        total, used, free = shutil.disk_usage(settings.data_dir)
        return {
            "free_gb": round(free / (1024**3), 1),
            "total_gb": round(total / (1024**3), 1),
            "used_percent": round((used / total) * 100, 1),
        }
    except Exception:
        return {}


def check_service_health(service_name: str, check_fn) -> str:
    """Check health of a service.

    Parameters
    ----------
    service_name : str
        Name of the service (for logging)
    check_fn : callable
        Function that returns True if healthy

    Returns
    -------
    str
        "healthy", "degraded", or "unhealthy"
    """
    try:
        if check_fn():
            return "healthy"
        return "degraded"
    except Exception as e:
        log.debug(
            f"service_check_failed service={service_name} err={e.__class__.__name__}"
        )
        return "unhealthy"


def get_feature_status() -> Dict[str, bool]:
    """Get status of optional features.

    Returns
    -------
    dict
        Feature name -> enabled status
    """
    try:
        from .config import get_settings

        settings = get_settings()
        return {
            "quickchart": getattr(settings, "feature_quickchart", False),
            "ollama": getattr(settings, "feature_ollama", False),
            "feedback_loop": getattr(settings, "feature_feedback_loop", False),
            "rich_alerts": getattr(settings, "feature_rich_alerts", False),
            "indicators": getattr(settings, "feature_indicators", False),
            "watchlist": getattr(settings, "feature_watchlist", False),
            "tiingo": getattr(settings, "feature_tiingo", False),
            "analyst_signals": getattr(settings, "feature_analyst_signals", False),
            "earnings_alerts": getattr(settings, "feature_earnings_alerts", False),
        }
    except Exception:
        return {}


def check_api_service(service: str) -> str:
    """Check health of external API services.

    Parameters
    ----------
    service : str
        Service name: "tiingo", "finnhub", "discord"

    Returns
    -------
    str
        "healthy", "degraded", or "unknown"
    """
    # Basic connectivity check - could be enhanced with actual API calls
    if service == "discord":
        try:
            webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
            return "healthy" if webhook else "unknown"
        except Exception:
            return "unknown"

    elif service == "tiingo":
        try:
            from .config import get_settings

            settings = get_settings()
            api_key = getattr(settings, "tiingo_api_key", None)
            enabled = getattr(settings, "feature_tiingo", False)
            if enabled and api_key:
                return "healthy"
            return "unknown"
        except Exception:
            return "unknown"

    elif service == "finnhub":
        try:
            from .config import get_settings

            settings = get_settings()
            api_key = getattr(settings, "finnhub_api_key", None)
            return "healthy" if api_key else "unknown"
        except Exception:
            return "unknown"

    return "unknown"


def is_healthy() -> bool:
    """Simple boolean health check.

    Returns
    -------
    bool
        True if bot is healthy, False if degraded
    """
    # Consider unhealthy if:
    # - Last cycle was more than 10 minutes ago
    # - More than 10 errors in the last hour
    last_cycle = get_last_cycle_time()
    if last_cycle is not None and last_cycle > 600:
        return False

    if get_error_count() > 10:
        return False

    return True


def get_health_status() -> Dict[str, Any]:
    """Get comprehensive health status.

    Returns
    -------
    dict
        Complete health status including all metrics
    """
    uptime = get_uptime()
    last_cycle = get_last_cycle_time()
    alerts = get_alert_stats()
    gpu = get_gpu_stats()
    disk = get_disk_stats()
    features = get_feature_status()

    # Determine overall status
    if is_healthy():
        status = "healthy"
    elif last_cycle is None:
        status = "starting"
    else:
        status = "degraded"

    health = {
        "status": status,
        "uptime_seconds": int(uptime),
        "last_cycle_seconds_ago": int(last_cycle) if last_cycle is not None else None,
        "cycles_today": _CYCLE_COUNT,  # Approximation
        "alerts_today": alerts["today"],
        "alerts_week": alerts["week"],
        "errors_last_hour": get_error_count(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Add GPU stats if available
    if gpu:
        health["gpu_utilization"] = gpu["utilization"]
        health["vram_used_mb"] = gpu["vram_used_mb"]
        health["vram_total_mb"] = gpu["vram_total_mb"]
        health["gpu_temperature"] = gpu.get("temperature")

    # Add disk stats
    if disk:
        health["disk_free_gb"] = disk["free_gb"]
        health["disk_used_percent"] = disk["used_percent"]

    # Add feature flags
    health["features"] = features

    # Add service status
    health["services"] = {
        "discord": check_api_service("discord"),
        "tiingo": check_api_service("tiingo"),
        "finnhub": check_api_service("finnhub"),
    }

    return health


# Initialize on import
if _START_TIME is None:
    init_health_monitor()
