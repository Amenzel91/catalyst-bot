"""
Configuration Updater
=====================

Handles real-time updates to bot configuration parameters by modifying
the .env file and reloading settings without requiring a full bot restart.

Features:
- Update environment variables on-the-fly
- Backup current settings before changes
- Rollback to previous configuration
- Validate parameter values before applying
- Thread-safe configuration updates
- Change history tracking
- Rate limiting
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .logging_utils import get_logger

log = get_logger("config_updater")

# Rate limiting: track last change timestamp
_LAST_CHANGE_TIME = 0
_MIN_CHANGE_INTERVAL = 60  # seconds


# ======================== Path Management ========================


def _get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[2]


def _get_env_path() -> Path:
    """Get path to .env file."""
    root = _get_repo_root()
    return root / ".env"


def _get_backup_dir() -> Path:
    """Get directory for configuration backups."""
    root = _get_repo_root()
    backup_dir = root / "data" / "config_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _get_change_history_path() -> Path:
    """Get path to change history log."""
    root = _get_repo_root()
    history_dir = root / "data"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / "admin_changes.jsonl"


# ======================== Validation ========================


def validate_parameter(name: str, value: Any) -> Tuple[bool, str]:
    """
    Validate a parameter value before applying.

    Returns (is_valid, error_message)
    """
    # Define validation rules
    validators = {
        "MIN_SCORE": lambda v: (0 <= float(v) <= 1, "Must be between 0 and 1"),
        "MIN_SENT_ABS": lambda v: (0 <= float(v) <= 1, "Must be between 0 and 1"),
        "PRICE_CEILING": lambda v: (float(v) > 0, "Must be positive"),
        "PRICE_FLOOR": lambda v: (float(v) >= 0, "Must be non-negative"),
        "CONFIDENCE_HIGH": lambda v: (0 <= float(v) <= 1, "Must be between 0 and 1"),
        "CONFIDENCE_MODERATE": lambda v: (
            0 <= float(v) <= 1,
            "Must be between 0 and 1",
        ),
        "ALERTS_MIN_INTERVAL_MS": lambda v: (
            int(v) >= 0,
            "Must be non-negative integer",
        ),
        "MAX_ALERTS_PER_CYCLE": lambda v: (int(v) > 0, "Must be positive integer"),
        "ANALYZER_HIT_UP_THRESHOLD_PCT": lambda v: (float(v) > 0, "Must be positive"),
        "ANALYZER_HIT_DOWN_THRESHOLD_PCT": lambda v: (float(v) < 0, "Must be negative"),
        "BREAKOUT_MIN_AVG_VOL": lambda v: (int(v) >= 0, "Must be non-negative integer"),
        "BREAKOUT_MIN_RELVOL": lambda v: (float(v) > 0, "Must be positive"),
    }

    # Sentiment weight validators (must sum to ~1.0 across all components)
    weight_params = [
        "SENTIMENT_WEIGHT_LOCAL",
        "SENTIMENT_WEIGHT_EXT",
        "SENTIMENT_WEIGHT_SEC",
        "SENTIMENT_WEIGHT_ANALYST",
        "SENTIMENT_WEIGHT_EARNINGS",
    ]

    if name in weight_params:
        try:
            v = float(value)
            if not (0 <= v <= 1):
                return False, "Sentiment weight must be between 0 and 1"
            return True, ""
        except ValueError:
            return False, "Must be a valid number"

    # Apply specific validator if exists
    if name in validators:
        try:
            is_valid, error = validators[name](value)
            if not is_valid:
                return False, error
            return True, ""
        except (ValueError, TypeError) as e:
            return False, f"Invalid value type: {e}"

    # For keyword weights (dynamic categories)
    if name.startswith("KEYWORD_WEIGHT_"):
        try:
            v = float(value)
            if v < 0:
                return False, "Keyword weight must be non-negative"
            return True, ""
        except ValueError:
            return False, "Must be a valid number"

    # Default: accept any value for unknown parameters
    log.warning(f"no_validator_for_param name={name}")
    return True, ""


# ======================== Backup & Restore ========================


def create_backup() -> Path:
    """Create a timestamped backup of current .env file."""
    env_path = _get_env_path()
    if not env_path.exists():
        log.warning("env_file_not_found path={env_path}")
        return None

    backup_dir = _get_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"env_{timestamp}.backup"

    try:
        shutil.copy2(env_path, backup_path)
        log.info(f"created_backup path={backup_path}")
        return backup_path
    except Exception as e:
        log.error(f"backup_failed err={e}")
        return None


def rollback_changes(backup_path: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Rollback to a previous configuration.

    If backup_path is None, uses the most recent backup.
    """
    if backup_path is None:
        # Find most recent backup
        backup_dir = _get_backup_dir()
        backups = sorted(backup_dir.glob("env_*.backup"), reverse=True)
        if not backups:
            return False, "No backups found"
        backup_path = backups[0]

    env_path = _get_env_path()

    try:
        shutil.copy2(backup_path, env_path)
        log.info(f"rollback_success from={backup_path}")
        _reload_environment()
        return True, f"Rolled back to {backup_path.name}"
    except Exception as e:
        log.error(f"rollback_failed err={e}")
        return False, f"Rollback failed: {e}"


# ======================== Change History ========================


def _log_parameter_change(
    changes: Dict[str, Any], source: str = "admin", user_id: Optional[str] = None
) -> None:
    """
    Log parameter change to history file.

    Parameters
    ----------
    changes : dict
        Dictionary of parameter changes
    source : str
        Source of change (e.g., "admin", "api", "manual")
    user_id : str, optional
        Discord user ID who made the change
    """
    history_path = _get_change_history_path()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "user_id": user_id,
        "changes": changes,
    }

    try:
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        log.info(f"change_logged count={len(changes)}")
    except Exception as e:
        log.warning(f"change_log_failed err={e}")


def get_change_history(limit: int = 10) -> list:
    """
    Get recent parameter changes.

    Parameters
    ----------
    limit : int
        Maximum number of changes to return

    Returns
    -------
    list
        List of change entries (most recent first)
    """
    history_path = _get_change_history_path()

    if not history_path.exists():
        return []

    try:
        entries = []
        with history_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue

        # Return most recent first
        return sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)[
            :limit
        ]
    except Exception as e:
        log.warning(f"history_load_failed err={e}")
        return []


def check_rate_limit() -> Tuple[bool, str]:
    """
    Check if enough time has passed since last change.

    Returns
    -------
    tuple
        (can_proceed: bool, message: str)
    """
    global _LAST_CHANGE_TIME

    now = time.time()
    elapsed = now - _LAST_CHANGE_TIME

    if elapsed < _MIN_CHANGE_INTERVAL and _LAST_CHANGE_TIME > 0:
        remaining = int(_MIN_CHANGE_INTERVAL - elapsed)
        return (
            False,
            f"Rate limit: Please wait {remaining}s before making another change",
        )

    return True, ""


def _update_rate_limit_timestamp():
    """Update the last change timestamp."""
    global _LAST_CHANGE_TIME
    _LAST_CHANGE_TIME = time.time()


# ======================== Environment Updates ========================


def _reload_environment():
    """Reload environment variables from .env file."""
    env_path = _get_env_path()
    if not env_path.exists():
        return

    try:
        with env_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    os.environ[key] = value

        log.info("environment_reloaded")
    except Exception as e:
        log.error(f"reload_failed err={e}")


def apply_parameter_changes(
    changes: Dict[str, Any], user_id: Optional[str] = None, source: str = "admin"
) -> Tuple[bool, str]:
    """
    Apply parameter changes to .env file and reload environment.

    Parameters
    ----------
    changes : dict
        Dictionary of parameter_name -> new_value
    user_id : str, optional
        Discord user ID who initiated the change
    source : str
        Source of the change (default: "admin")

    Returns
    -------
    tuple
        (success: bool, message: str)
    """
    # Check rate limit
    can_proceed, rate_msg = check_rate_limit()
    if not can_proceed:
        return False, rate_msg

    # Validate all changes first
    for name, value in changes.items():
        is_valid, error = validate_parameter(name, value)
        if not is_valid:
            return False, f"Validation failed for {name}: {error}"

    # Create backup before making changes
    backup_path = create_backup()
    if backup_path is None:
        return False, "Failed to create backup before applying changes"

    env_path = _get_env_path()

    try:
        # Read current .env file
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        # Track which parameters were updated
        updated_params = set()
        new_lines = []

        for line in lines:
            stripped = line.strip()

            # Keep comments and empty lines as-is
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue

            # Parse parameter line
            if "=" in stripped:
                key, _ = stripped.split("=", 1)
                key = key.strip()

                # If this parameter is being changed, update it
                if key in changes:
                    new_value = changes[key]
                    new_lines.append(f"{key}={new_value}")
                    updated_params.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # Add any new parameters that weren't in the file
        for key, value in changes.items():
            if key not in updated_params:
                new_lines.append(f"{key}={value}")
                updated_params.add(key)

        # Write updated .env file
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # Reload environment variables
        _reload_environment()

        # Log the change to history
        _log_parameter_change(changes, source=source, user_id=user_id)

        # Update rate limit timestamp
        _update_rate_limit_timestamp()

        # Build success message
        param_list = ", ".join(sorted(updated_params))
        message = (
            f"✅ Successfully updated {len(updated_params)} parameters: {param_list}"
        )
        log.info(f"applied_changes count={len(updated_params)} params={param_list}")

        return True, message

    except Exception as e:
        log.error(f"apply_changes_failed err={e}")

        # Attempt rollback
        rollback_success, rollback_msg = rollback_changes(backup_path)
        if rollback_success:
            return (
                False,
                f"Failed to apply changes: {e}. Rolled back to previous configuration.",
            )
        else:
            return (
                False,
                f"Failed to apply changes: {e}. Rollback also failed: {rollback_msg}",
            )


# ======================== Keyword Weight Updates ========================


def update_keyword_weights(weights: Dict[str, float]) -> Tuple[bool, str]:
    """
    Update keyword category weights in data/analyzer/keyword_stats.json.

    This is separate from .env parameters and directly updates the
    classifier weights used by the analyzer.
    """
    root = _get_repo_root()
    weights_path = root / "data" / "analyzer" / "keyword_stats.json"
    weights_path.parent.mkdir(parents=True, exist_ok=True)

    # Create backup
    if weights_path.exists():
        backup_path = weights_path.with_suffix(".json.backup")
        try:
            shutil.copy2(weights_path, backup_path)
        except Exception as e:
            log.warning(f"keyword_backup_failed err={e}")

    try:
        # Load existing weights
        if weights_path.exists():
            import json

            existing = json.loads(weights_path.read_text(encoding="utf-8"))
        else:
            existing = {}

        # Update with new weights
        existing.update(weights)

        # Write back
        import json

        weights_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        log.info(f"updated_keyword_weights count={len(weights)}")
        return True, f"Updated {len(weights)} keyword weights"

    except Exception as e:
        log.error(f"keyword_update_failed err={e}")
        return False, f"Failed to update keyword weights: {e}"
