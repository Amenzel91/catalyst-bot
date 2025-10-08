"""
GPU Monitoring for Catalyst-Bot

This module provides real-time GPU monitoring capabilities for integration
with health checks, admin reports, and alerting systems.

Features:
- GPU utilization tracking
- VRAM usage monitoring
- Temperature monitoring
- Health check endpoint integration
- Performance metrics collection

Usage:
    from catalyst_bot.gpu_monitor import get_gpu_stats, is_gpu_healthy

    # Get current stats
    stats = get_gpu_stats()
    print(f"GPU usage: {stats['utilization_pct']}%")

    # Health check
    if not is_gpu_healthy():
        logger.warning("GPU health check failed!")
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

_logger = logging.getLogger(__name__)


@dataclass
class GPUStats:
    """GPU statistics snapshot."""

    gpu_available: bool
    gpu_count: int
    utilization_pct: float
    vram_used_mb: float
    vram_total_mb: float
    vram_free_mb: float
    temperature_c: float
    power_draw_w: float
    power_limit_w: float
    driver_version: str
    gpu_name: str


def get_gpu_stats(gpu_index: int = 0) -> Dict[str, any]:
    """Get comprehensive GPU statistics.

    Args:
        gpu_index: GPU device index (default: 0)

    Returns:
        Dict with GPU stats, or empty dict if no GPU available
    """
    # Try PyTorch first (most accurate for ML workloads)
    stats = _get_stats_pytorch(gpu_index)
    if stats:
        return stats

    # Fallback to nvidia-smi
    stats = _get_stats_nvidia_smi(gpu_index)
    if stats:
        return stats

    # No GPU detected
    return {
        "gpu_available": False,
        "gpu_count": 0,
        "utilization_pct": 0.0,
        "vram_used_mb": 0.0,
        "vram_total_mb": 0.0,
        "vram_free_mb": 0.0,
        "temperature_c": 0.0,
        "power_draw_w": 0.0,
        "power_limit_w": 0.0,
        "driver_version": "N/A",
        "gpu_name": "None",
    }


def _get_stats_pytorch(gpu_index: int = 0) -> Optional[Dict]:
    """Get GPU stats using PyTorch.

    Args:
        gpu_index: GPU device index

    Returns:
        Dict with stats or None if PyTorch unavailable
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return None

        device_props = torch.cuda.get_device_properties(gpu_index)

        stats = {
            "gpu_available": True,
            "gpu_count": torch.cuda.device_count(),
            "utilization_pct": 0.0,  # PyTorch doesn't expose this easily
            "vram_used_mb": torch.cuda.memory_allocated(gpu_index) / (1024**2),
            "vram_total_mb": device_props.total_memory / (1024**2),
            "vram_free_mb": (
                device_props.total_memory - torch.cuda.memory_allocated(gpu_index)
            )
            / (1024**2),
            "temperature_c": 0.0,  # Not available via PyTorch
            "power_draw_w": 0.0,  # Not available via PyTorch
            "power_limit_w": 0.0,  # Not available via PyTorch
            "driver_version": "Unknown",
            "gpu_name": device_props.name,
        }

        # Try to get utilization via nvidia-smi to complement PyTorch stats
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,temperature.gpu,power.draw,power.limit,driver_version",  # noqa: E501
                    "--format=csv,noheader,nounits",
                    f"--id={gpu_index}",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                stats["utilization_pct"] = float(parts[0].strip())
                stats["temperature_c"] = float(parts[1].strip())
                stats["power_draw_w"] = float(parts[2].strip())
                stats["power_limit_w"] = float(parts[3].strip())
                stats["driver_version"] = parts[4].strip()
        except Exception:
            pass

        return stats

    except ImportError:
        return None
    except Exception as e:
        _logger.debug("Failed to get PyTorch GPU stats: %s", e)
        return None


def _get_stats_nvidia_smi(gpu_index: int = 0) -> Optional[Dict]:
    """Get GPU stats using nvidia-smi.

    Args:
        gpu_index: GPU device index

    Returns:
        Dict with stats or None if nvidia-smi unavailable
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=count,utilization.gpu,memory.used,memory.total,memory.free,temperature.gpu,power.draw,power.limit,driver_version,name",  # noqa: E501
                "--format=csv,noheader,nounits",
                f"--id={gpu_index}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if not lines:
            return None

        parts = lines[0].split(",")
        if len(parts) < 10:
            return None

        return {
            "gpu_available": True,
            "gpu_count": 1,  # Query returns single GPU
            "utilization_pct": float(parts[1].strip()),
            "vram_used_mb": float(parts[2].strip()),
            "vram_total_mb": float(parts[3].strip()),
            "vram_free_mb": float(parts[4].strip()),
            "temperature_c": float(parts[5].strip()),
            "power_draw_w": float(parts[6].strip()),
            "power_limit_w": float(parts[7].strip()),
            "driver_version": parts[8].strip(),
            "gpu_name": parts[9].strip(),
        }

    except FileNotFoundError:
        _logger.debug("nvidia-smi not found in PATH")
        return None
    except Exception as e:
        _logger.debug("Failed to get nvidia-smi GPU stats: %s", e)
        return None


def get_all_gpu_stats() -> List[Dict]:
    """Get stats for all available GPUs.

    Returns:
        List of GPU stats dicts
    """
    stats_list = []

    # Try to detect GPU count
    gpu_count = 0
    try:
        import torch

        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
    except ImportError:
        # Try nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                gpu_count = len(lines)
        except Exception:
            pass

    if gpu_count == 0:
        return [get_gpu_stats(0)]

    # Get stats for each GPU
    for i in range(gpu_count):
        stats = get_gpu_stats(i)
        if stats.get("gpu_available"):
            stats_list.append(stats)

    return stats_list if stats_list else [get_gpu_stats(0)]


def is_gpu_healthy(
    max_utilization: Optional[float] = None,
    max_temperature: Optional[float] = None,
    min_free_vram_mb: Optional[float] = None,
) -> bool:
    """Check if GPU is healthy based on thresholds.

    Args:
        max_utilization: Max GPU utilization % (default: from env or 95%)
        max_temperature: Max temperature in Celsius (default: from env or 85°C)
        min_free_vram_mb: Minimum free VRAM in MB (default: from env or 500 MB)

    Returns:
        True if GPU is healthy, False otherwise
    """
    stats = get_gpu_stats()

    if not stats.get("gpu_available"):
        # No GPU is not necessarily unhealthy (CPU mode is fine)
        return True

    # Get thresholds from env or use defaults
    if max_utilization is None:
        max_utilization = float(os.getenv("GPU_MAX_UTILIZATION_WARN", "95"))
    if max_temperature is None:
        max_temperature = float(os.getenv("GPU_MAX_TEMPERATURE_C", "85"))
    if min_free_vram_mb is None:
        min_free_vram_mb = float(os.getenv("GPU_MIN_FREE_VRAM_MB", "500"))

    # Check thresholds
    if stats.get("utilization_pct", 0) > max_utilization:
        _logger.warning(
            "GPU utilization too high: %.1f%% > %.1f%%",
            stats["utilization_pct"],
            max_utilization,
        )
        return False

    if stats.get("temperature_c", 0) > max_temperature:
        _logger.warning(
            "GPU temperature too high: %.1f°C > %.1f°C",
            stats["temperature_c"],
            max_temperature,
        )
        return False

    if stats.get("vram_free_mb", 0) < min_free_vram_mb:
        _logger.warning(
            "GPU free VRAM too low: %.0f MB < %.0f MB",
            stats["vram_free_mb"],
            min_free_vram_mb,
        )
        return False

    return True


def get_gpu_health_status() -> Dict[str, any]:
    """Get comprehensive GPU health status for health check endpoints.

    Returns:
        Dict with health status and metrics
    """
    stats = get_gpu_stats()
    healthy = is_gpu_healthy()

    return {
        "healthy": healthy,
        "gpu_available": stats.get("gpu_available", False),
        "gpu_name": stats.get("gpu_name", "None"),
        "utilization_pct": stats.get("utilization_pct", 0.0),
        "vram_used_mb": stats.get("vram_used_mb", 0.0),
        "vram_total_mb": stats.get("vram_total_mb", 0.0),
        "vram_utilization_pct": (
            (stats.get("vram_used_mb", 0) / stats.get("vram_total_mb", 1)) * 100
            if stats.get("vram_total_mb", 0) > 0
            else 0.0
        ),
        "temperature_c": stats.get("temperature_c", 0.0),
        "driver_version": stats.get("driver_version", "N/A"),
    }


def format_gpu_stats_text(stats: Optional[Dict] = None) -> str:
    """Format GPU stats as human-readable text.

    Args:
        stats: GPU stats dict (fetches current if None)

    Returns:
        Formatted text string
    """
    if stats is None:
        stats = get_gpu_stats()

    if not stats.get("gpu_available"):
        return "GPU: Not available (CPU mode)"

    vram_pct = (
        (stats["vram_used_mb"] / stats["vram_total_mb"]) * 100
        if stats["vram_total_mb"] > 0
        else 0.0
    )

    lines = [
        f"GPU: {stats['gpu_name']}",
        f"  Driver: {stats['driver_version']}",
        f"  Utilization: {stats['utilization_pct']:.1f}%",
        f"  VRAM: {stats['vram_used_mb']:.0f}/{stats['vram_total_mb']:.0f} MB ({vram_pct:.1f}%)",
        f"  Temperature: {stats['temperature_c']:.0f}°C",
    ]

    if stats.get("power_draw_w", 0) > 0:
        lines.append(
            f"  Power: {stats['power_draw_w']:.0f}/{stats['power_limit_w']:.0f} W"
        )

    return "\n".join(lines)


def log_gpu_stats() -> None:
    """Log current GPU stats at INFO level."""
    text = format_gpu_stats_text()
    for line in text.split("\n"):
        _logger.info(line)


def get_gpu_summary() -> str:
    """Get one-line GPU summary for logs.

    Returns:
        Compact summary string
    """
    stats = get_gpu_stats()

    if not stats.get("gpu_available"):
        return "GPU: N/A"

    vram_pct = (
        (stats["vram_used_mb"] / stats["vram_total_mb"]) * 100
        if stats["vram_total_mb"] > 0
        else 0.0
    )

    return (
        f"GPU: {stats['utilization_pct']:.0f}% util, "
        f"{stats['vram_used_mb']:.0f}MB VRAM ({vram_pct:.0f}%), "
        f"{stats['temperature_c']:.0f}°C"
    )


# Integration helpers for health check endpoints
def add_gpu_to_health_check(health_dict: Dict) -> Dict:
    """Add GPU stats to existing health check response.

    Args:
        health_dict: Existing health check dict

    Returns:
        Updated health dict with GPU stats
    """
    gpu_health = get_gpu_health_status()
    health_dict["gpu"] = gpu_health

    # Update overall health status if GPU is unhealthy
    if not gpu_health["healthy"]:
        health_dict["status"] = "degraded"

    return health_dict


# Example health check endpoint (FastAPI/Flask compatible)
def create_health_check_response() -> Dict:
    """Create a complete health check response including GPU stats.

    Returns:
        Health check response dict
    """
    import time

    return {
        "status": "ok",
        "timestamp": time.time(),
        "gpu": get_gpu_health_status(),
    }
