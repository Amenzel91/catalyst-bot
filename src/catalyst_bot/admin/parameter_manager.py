"""
Parameter Manager
=================

Manages bot parameter changes with tracking, rollback, and impact analysis.

This module provides:
- Apply parameter changes to .env file
- Track all parameter changes in database
- Rollback capability to previous values
- Before/after performance tracking
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_utils import get_logger

log = get_logger("admin.parameter_manager")

# Default database path
DEFAULT_DB_PATH = Path("data/admin/parameter_changes.db")


def _get_db_path() -> Path:
    """Get the database path from env or use default."""
    db_path_str = os.getenv("PARAMETER_CHANGES_DB_PATH", str(DEFAULT_DB_PATH))
    db_path = Path(db_path_str).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory and optimized pragmas."""
    from ..storage import init_optimized_connection

    db_path = _get_db_path()
    conn = init_optimized_connection(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_parameter_database() -> None:
    """
    Create database and tables if they don't exist.

    This function is idempotent and safe to call multiple times.
    """
    db_path = _get_db_path()
    log.info("initializing_parameter_changes_database path=%s", db_path)

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Create parameter changes table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS parameter_changes (
                change_id TEXT PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                parameter TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                reason TEXT,
                approved_by TEXT,
                status TEXT NOT NULL,

                -- Performance metrics before change (7 days lookback)
                win_rate_before_15m REAL,
                win_rate_before_1h REAL,
                win_rate_before_4h REAL,
                win_rate_before_1d REAL,
                alerts_before INTEGER,

                -- Performance metrics after change (7 days lookback)
                win_rate_after_15m REAL,
                win_rate_after_1h REAL,
                win_rate_after_4h REAL,
                win_rate_after_1d REAL,
                alerts_after INTEGER,

                -- Impact metrics calculated
                impact_calculated INTEGER DEFAULT 0,
                impact_timestamp INTEGER,
                impact_positive INTEGER  -- 1 if positive impact, 0 if negative
            )
        """
        )

        # Create indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_parameter ON parameter_changes(parameter)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON parameter_changes(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_status ON parameter_changes(status)"
        )

        conn.commit()
        log.info("parameter_changes_database_initialized")

    except Exception as e:
        log.error("parameter_changes_database_init_failed error=%s", str(e))
        conn.rollback()
        raise
    finally:
        conn.close()


class ParameterManager:
    """
    Manages bot parameter changes with tracking and rollback.

    Example usage:
        manager = ParameterManager()
        success = manager.apply_parameter_change(
            param="MIN_SCORE",
            old_value=0.25,
            new_value=0.30,
            reason="Win rate below 55%",
            approved_by="admin_user"
        )
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize parameter manager.

        Parameters
        ----------
        config_path : str, optional
            Path to .env file. Defaults to .env in project root.
        """
        if config_path is None:
            # Find .env in project root
            project_root = Path(__file__).resolve().parents[3]
            config_path = str(project_root / ".env")

        self.config_path = Path(config_path)
        self.db_path = _get_db_path()

        # Ensure database exists
        init_parameter_database()

    def apply_parameter_change(
        self,
        param: str,
        old_value: Any,
        new_value: Any,
        reason: str,
        approved_by: str = "admin",
    ) -> tuple[bool, str]:
        """
        Apply parameter change to .env and track in database.

        Steps:
        1. Validate parameter exists in .env
        2. Backup current .env
        3. Update .env file
        4. Record change in parameter_changes.db
        5. Return success/failure

        Parameters
        ----------
        param : str
            Parameter name (e.g., "MIN_SCORE")
        old_value : Any
            Current value
        new_value : Any
            New value to apply
        reason : str
            Reason for the change
        approved_by : str
            User who approved the change

        Returns
        -------
        tuple[bool, str]
            (success, message)
        """
        try:
            # 1. Validate .env file exists
            if not self.config_path.exists():
                return False, f".env file not found at {self.config_path}"

            # 2. Get current performance metrics (before change)
            before_metrics = self._get_current_performance_metrics()

            # 3. Backup .env file
            backup_path = self._backup_env_file()
            log.info(
                "env_file_backed_up original=%s backup=%s",
                self.config_path,
                backup_path,
            )

            # 4. Update .env file
            success = self._update_env_file(param, str(new_value))
            if not success:
                return False, f"Failed to update {param} in .env file"

            # 5. Record change in database
            change_id = str(uuid.uuid4())[:8]
            self._record_change(
                change_id=change_id,
                param=param,
                old_value=str(old_value),
                new_value=str(new_value),
                reason=reason,
                approved_by=approved_by,
                before_metrics=before_metrics,
            )

            log.info(
                "parameter_change_applied change_id=%s param=%s old=%s new=%s",
                change_id,
                param,
                old_value,
                new_value,
            )

            return True, f"Successfully applied {param}: {old_value} → {new_value}"

        except Exception as e:
            log.error(
                "parameter_change_failed param=%s error=%s",
                param,
                str(e),
                exc_info=True,
            )
            return False, f"Error applying change: {str(e)}"

    def rollback_change(self, change_id: str) -> tuple[bool, str]:
        """
        Rollback a parameter change to previous value.

        Parameters
        ----------
        change_id : str
            Change ID to rollback

        Returns
        -------
        tuple[bool, str]
            (success, message)
        """
        try:
            # Get change record
            change = self._get_change_record(change_id)
            if not change:
                return False, f"Change {change_id} not found"

            if change["status"] == "rolled_back":
                return False, f"Change {change_id} already rolled back"

            # Apply rollback (swap new -> old)
            success, msg = self.apply_parameter_change(
                param=change["parameter"],
                old_value=change["new_value"],
                new_value=change["old_value"],
                reason=f"Rollback of {change_id}",
                approved_by="system",
            )

            if success:
                # Mark original change as rolled back
                self._mark_as_rolled_back(change_id)
                log.info("parameter_change_rolled_back change_id=%s", change_id)

            return success, msg

        except Exception as e:
            log.error(
                "rollback_failed change_id=%s error=%s",
                change_id,
                str(e),
                exc_info=True,
            )
            return False, f"Error rolling back: {str(e)}"

    def get_change_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent parameter changes and their impact.

        Parameters
        ----------
        limit : int
            Maximum number of changes to return

        Returns
        -------
        list of dict
            List of change records
        """
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM parameter_changes
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            log.error("get_change_history_failed error=%s", str(e))
            return []
        finally:
            conn.close()

    def track_change_impact(self, change_id: str, days: int = 7) -> bool:
        """
        Track performance before/after parameter change.

        Compare win rates 7 days before vs 7 days after.
        Store results in database.

        Parameters
        ----------
        change_id : str
            Change ID to track
        days : int
            Number of days to look back/forward

        Returns
        -------
        bool
            True if tracking was successful
        """
        try:
            # Get change record
            change = self._get_change_record(change_id)
            if not change:
                log.warning("change_not_found change_id=%s", change_id)
                return False

            change_timestamp = change["timestamp"]
            now = int(time.time())
            days_elapsed = (now - change_timestamp) / 86400

            if days_elapsed < days:
                log.debug(
                    "insufficient_time_elapsed change_id=%s days_elapsed=%.1f required=%d",
                    change_id,
                    days_elapsed,
                    days,
                )
                return False

            # Get after metrics
            after_metrics = self._get_performance_metrics_for_period(
                change_timestamp, change_timestamp + (days * 86400)
            )

            # Update database
            self._update_after_metrics(change_id, after_metrics)

            # Calculate impact
            self._calculate_impact(change_id)

            log.info("change_impact_tracked change_id=%s days=%d", change_id, days)
            return True

        except Exception as e:
            log.error(
                "track_change_impact_failed change_id=%s error=%s",
                change_id,
                str(e),
                exc_info=True,
            )
            return False

    # ======================== Private Methods ========================

    def _backup_env_file(self) -> Path:
        """Create timestamped backup of .env file."""
        timestamp = int(time.time())
        backup_path = self.config_path.parent / f".env.backup.{timestamp}"
        shutil.copy2(self.config_path, backup_path)
        return backup_path

    def _update_env_file(self, param: str, new_value: str) -> bool:
        """Update parameter in .env file."""
        try:
            lines = self.config_path.read_text(encoding="utf-8").splitlines()
            updated = False
            new_lines = []

            for line in lines:
                # Skip empty lines and comments
                if not line.strip() or line.strip().startswith("#"):
                    new_lines.append(line)
                    continue

                # Check if this is the parameter we're updating
                if "=" in line:
                    key = line.split("=")[0].strip()
                    if key == param:
                        new_lines.append(f"{param}={new_value}")
                        updated = True
                        continue

                new_lines.append(line)

            # If parameter wasn't found, add it
            if not updated:
                new_lines.append(f"{param}={new_value}")

            # Write back to file
            self.config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            return True

        except Exception as e:
            log.error("update_env_file_failed param=%s error=%s", param, str(e))
            return False

    def _record_change(
        self,
        change_id: str,
        param: str,
        old_value: str,
        new_value: str,
        reason: str,
        approved_by: str,
        before_metrics: Dict[str, Any],
    ) -> None:
        """Record parameter change in database."""
        conn = _get_connection()
        try:
            now = int(time.time())

            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO parameter_changes (
                    change_id, timestamp, parameter, old_value, new_value,
                    reason, approved_by, status,
                    win_rate_before_15m, win_rate_before_1h,
                    win_rate_before_4h, win_rate_before_1d,
                    alerts_before
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    now,
                    param,
                    old_value,
                    new_value,
                    reason,
                    approved_by,
                    "active",
                    before_metrics.get("win_rate_15m"),
                    before_metrics.get("win_rate_1h"),
                    before_metrics.get("win_rate_4h"),
                    before_metrics.get("win_rate_1d"),
                    before_metrics.get("alerts_count", 0),
                ),
            )

            conn.commit()

        except Exception as e:
            log.error("record_change_failed error=%s", str(e))
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get_change_record(self, change_id: str) -> Optional[Dict[str, Any]]:
        """Get change record from database."""
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM parameter_changes WHERE change_id = ?", (change_id,)
            )

            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            log.error(
                "get_change_record_failed change_id=%s error=%s", change_id, str(e)
            )
            return None
        finally:
            conn.close()

    def _mark_as_rolled_back(self, change_id: str) -> None:
        """Mark change as rolled back."""
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE parameter_changes SET status = ? WHERE change_id = ?",
                ("rolled_back", change_id),
            )
            conn.commit()

        except Exception as e:
            log.error("mark_as_rolled_back_failed error=%s", str(e))
            conn.rollback()
        finally:
            conn.close()

    def _get_current_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics from feedback database."""
        try:
            from ..feedback.database import get_performance_stats

            stats = get_performance_stats(lookback_days=7)

            # Extract win rates by timeframe
            # Note: feedback DB currently tracks 1d primarily
            # We'll use it for all timeframes as proxy
            return {
                "win_rate_15m": stats.get("win_rate", 0),
                "win_rate_1h": stats.get("win_rate", 0),
                "win_rate_4h": stats.get("win_rate", 0),
                "win_rate_1d": stats.get("win_rate", 0),
                "alerts_count": stats.get("total_alerts", 0),
            }

        except Exception as e:
            log.warning("get_current_performance_metrics_failed error=%s", str(e))
            return {
                "win_rate_15m": None,
                "win_rate_1h": None,
                "win_rate_4h": None,
                "win_rate_1d": None,
                "alerts_count": 0,
            }

    def _get_performance_metrics_for_period(
        self, start_timestamp: int, end_timestamp: int
    ) -> Dict[str, Any]:
        """Get performance metrics for specific time period."""
        try:
            # Calculate days in period
            (end_timestamp - start_timestamp) / 86400

            from ..feedback.database import _get_connection as get_feedback_conn

            conn = get_feedback_conn()
            try:
                cursor = conn.cursor()

                # Get stats for the period
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_alerts,
                        COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins,
                        COUNT(CASE WHEN outcome = 'loss' THEN 1 END) as losses,
                        COUNT(CASE WHEN outcome = 'neutral' THEN 1 END) as neutral
                    FROM alert_performance
                    WHERE posted_at >= ? AND posted_at < ?
                    """,
                    (start_timestamp, end_timestamp),
                )

                row = cursor.fetchone()
                stats = dict(row) if row else {}

                total_scored = (
                    (stats.get("wins", 0) or 0)
                    + (stats.get("losses", 0) or 0)
                    + (stats.get("neutral", 0) or 0)
                )
                win_rate = (
                    (stats.get("wins", 0) or 0) / total_scored
                    if total_scored > 0
                    else 0.0
                )

                return {
                    "win_rate_15m": win_rate,
                    "win_rate_1h": win_rate,
                    "win_rate_4h": win_rate,
                    "win_rate_1d": win_rate,
                    "alerts_count": stats.get("total_alerts", 0) or 0,
                }

            finally:
                conn.close()

        except Exception as e:
            log.warning("get_performance_metrics_for_period_failed error=%s", str(e))
            return {
                "win_rate_15m": None,
                "win_rate_1h": None,
                "win_rate_4h": None,
                "win_rate_1d": None,
                "alerts_count": 0,
            }

    def _update_after_metrics(
        self, change_id: str, after_metrics: Dict[str, Any]
    ) -> None:
        """Update after metrics in database."""
        conn = _get_connection()
        try:
            int(time.time())

            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE parameter_changes
                SET
                    win_rate_after_15m = ?,
                    win_rate_after_1h = ?,
                    win_rate_after_4h = ?,
                    win_rate_after_1d = ?,
                    alerts_after = ?
                WHERE change_id = ?
                """,
                (
                    after_metrics.get("win_rate_15m"),
                    after_metrics.get("win_rate_1h"),
                    after_metrics.get("win_rate_4h"),
                    after_metrics.get("win_rate_1d"),
                    after_metrics.get("alerts_count", 0),
                    change_id,
                ),
            )

            conn.commit()

        except Exception as e:
            log.error("update_after_metrics_failed error=%s", str(e))
            conn.rollback()
        finally:
            conn.close()

    def _calculate_impact(self, change_id: str) -> None:
        """Calculate impact (positive/negative) and update database."""
        conn = _get_connection()
        try:
            # Get change record with metrics
            change = self._get_change_record(change_id)
            if not change:
                return

            # Calculate impact based on win rate change
            before_wr = change.get("win_rate_before_1d")
            after_wr = change.get("win_rate_after_1d")

            if before_wr is None or after_wr is None:
                return

            # Positive impact if win rate improved
            impact_positive = 1 if after_wr > before_wr else 0

            now = int(time.time())

            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE parameter_changes
                SET
                    impact_calculated = 1,
                    impact_timestamp = ?,
                    impact_positive = ?
                WHERE change_id = ?
                """,
                (now, impact_positive, change_id),
            )

            conn.commit()

            log.info(
                "impact_calculated change_id=%s before_wr=%.2f after_wr=%.2f positive=%d",
                change_id,
                before_wr,
                after_wr,
                impact_positive,
            )

        except Exception as e:
            log.error("calculate_impact_failed error=%s", str(e))
            conn.rollback()
        finally:
            conn.close()


# ======================== Convenience Functions ========================


def get_change_history(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent parameter changes (convenience function)."""
    manager = ParameterManager()
    return manager.get_change_history(limit)


def rollback_change(change_id: str) -> tuple[bool, str]:
    """Rollback a parameter change (convenience function)."""
    manager = ParameterManager()
    return manager.rollback_change(change_id)
