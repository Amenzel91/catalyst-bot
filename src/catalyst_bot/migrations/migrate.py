#!/usr/bin/env python3
"""
Database Migration Runner for Catalyst Bot Paper Trading System

This script manages database migrations for the paper trading bot.
It can run all migrations, specific migrations, or rollback changes.

Usage:
    # Run all migrations
    python -m catalyst_bot.migrations.migrate

    # Run all migrations with upgrade
    python -m catalyst_bot.migrations.migrate upgrade

    # Run specific migration
    python -m catalyst_bot.migrations.migrate upgrade --migration 001

    # Rollback all migrations
    python -m catalyst_bot.migrations.migrate downgrade

    # Rollback specific migration
    python -m catalyst_bot.migrations.migrate downgrade --migration 002

    # Check migration status
    python -m catalyst_bot.migrations.migrate status

Migrations:
    001: Create positions tables (positions.db)
    002: Create trading tables (trading.db)
    003: Create ML training tables (ml_training.db)
"""

from __future__ import annotations

import argparse
import importlib
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from catalyst_bot.storage import _ensure_dir, init_optimized_connection


MIGRATIONS_DIR = Path(__file__).parent
MIGRATION_TRACKER_DB = "data/migrations.db"


# Migration registry: (migration_number, module_name, database_path, description)
MIGRATIONS = [
    ("001", "001_create_positions_tables", "data/positions.db", "Create positions tables"),
    ("002", "002_create_trading_tables", "data/trading.db", "Create trading tables"),
    ("003", "003_create_ml_training_tables", "data/ml_training.db", "Create ML training tables"),
]


def init_migration_tracker() -> sqlite3.Connection:
    """
    Initialize the migration tracker database.

    This database keeps track of which migrations have been applied.
    """
    _ensure_dir(MIGRATION_TRACKER_DB)
    conn = init_optimized_connection(MIGRATION_TRACKER_DB)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_history (
            migration_id TEXT PRIMARY KEY,
            migration_name TEXT NOT NULL,
            database_path TEXT NOT NULL,
            applied_at INTEGER NOT NULL,
            applied_date TEXT NOT NULL,
            duration_seconds REAL,
            status TEXT NOT NULL CHECK(status IN ('applied', 'rolled_back', 'failed')),
            error_message TEXT
        );
        """
    )

    conn.commit()
    return conn


def get_applied_migrations(conn: sqlite3.Connection) -> List[str]:
    """
    Get list of migration IDs that have been successfully applied.
    """
    cursor = conn.execute(
        "SELECT migration_id FROM migration_history WHERE status = 'applied' ORDER BY migration_id"
    )
    return [row[0] for row in cursor.fetchall()]


def record_migration(
    conn: sqlite3.Connection,
    migration_id: str,
    migration_name: str,
    database_path: str,
    status: str,
    duration: float = None,
    error_message: str = None,
) -> None:
    """
    Record a migration in the history table.
    """
    now = int(time.time())
    date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

    conn.execute(
        """
        INSERT OR REPLACE INTO migration_history
        (migration_id, migration_name, database_path, applied_at, applied_date,
         duration_seconds, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (migration_id, migration_name, database_path, now, date_str, duration, status, error_message),
    )
    conn.commit()


def run_migration(migration_id: str, action: str = "upgrade") -> Tuple[bool, str]:
    """
    Run a specific migration.

    Args:
        migration_id: Migration number (e.g., "001")
        action: "upgrade" or "downgrade"

    Returns:
        (success, message)
    """
    # Find migration in registry
    migration_info = None
    for mig in MIGRATIONS:
        if mig[0] == migration_id:
            migration_info = mig
            break

    if not migration_info:
        return False, f"Migration {migration_id} not found in registry"

    migration_num, module_name, db_path, description = migration_info

    print(f"\n{'='*70}")
    print(f"{'UPGRADE' if action == 'upgrade' else 'DOWNGRADE'}: Migration {migration_num}")
    print(f"Description: {description}")
    print(f"Database: {db_path}")
    print(f"{'='*70}\n")

    start_time = time.time()

    try:
        # Import migration module
        module = importlib.import_module(f"catalyst_bot.migrations.{module_name}")

        # Run upgrade or downgrade
        if action == "upgrade":
            module.upgrade(db_path)
        elif action == "downgrade":
            module.downgrade(db_path)
        else:
            return False, f"Invalid action: {action}"

        duration = time.time() - start_time

        # Record in migration history
        tracker_conn = init_migration_tracker()
        status = "applied" if action == "upgrade" else "rolled_back"
        record_migration(tracker_conn, migration_num, module_name, db_path, status, duration)
        tracker_conn.close()

        print(f"\n✅ Migration {migration_num} {action} completed in {duration:.2f} seconds")
        return True, f"Migration {migration_num} {action} successful"

    except Exception as e:
        duration = time.time() - start_time

        # Record failure
        tracker_conn = init_migration_tracker()
        record_migration(tracker_conn, migration_num, module_name, db_path, "failed", duration, str(e))
        tracker_conn.close()

        print(f"\n❌ Migration {migration_num} {action} failed: {e}")
        return False, f"Migration {migration_num} failed: {e}"


def run_all_migrations(action: str = "upgrade") -> None:
    """
    Run all migrations in order.

    Args:
        action: "upgrade" or "downgrade"
    """
    tracker_conn = init_migration_tracker()
    applied_migrations = get_applied_migrations(tracker_conn)
    tracker_conn.close()

    if action == "upgrade":
        # Run migrations that haven't been applied
        migrations_to_run = [m for m in MIGRATIONS if m[0] not in applied_migrations]

        if not migrations_to_run:
            print("\n✅ All migrations already applied!")
            return

        print(f"\nFound {len(migrations_to_run)} migration(s) to apply:")
        for m in migrations_to_run:
            print(f"  • {m[0]}: {m[3]}")

        total_start = time.time()
        success_count = 0
        fail_count = 0

        for migration_info in migrations_to_run:
            migration_id = migration_info[0]
            success, message = run_migration(migration_id, "upgrade")

            if success:
                success_count += 1
            else:
                fail_count += 1
                print(f"\n⚠️  Stopping migrations due to failure")
                break

        total_duration = time.time() - total_start

        print(f"\n{'='*70}")
        print(f"MIGRATION SUMMARY")
        print(f"{'='*70}")
        print(f"Total duration: {total_duration:.2f} seconds")
        print(f"Successful: {success_count}")
        print(f"Failed: {fail_count}")
        print(f"{'='*70}\n")

    elif action == "downgrade":
        # Rollback applied migrations in reverse order
        migrations_to_rollback = [m for m in reversed(MIGRATIONS) if m[0] in applied_migrations]

        if not migrations_to_rollback:
            print("\n✅ No migrations to rollback!")
            return

        print(f"\n⚠️  WARNING: Rolling back {len(migrations_to_rollback)} migration(s):")
        for m in migrations_to_rollback:
            print(f"  • {m[0]}: {m[3]}")

        confirm = input("\nThis will delete data! Are you sure? (yes/no): ")
        if confirm.lower() != "yes":
            print("Rollback cancelled.")
            return

        total_start = time.time()
        success_count = 0
        fail_count = 0

        for migration_info in migrations_to_rollback:
            migration_id = migration_info[0]
            success, message = run_migration(migration_id, "downgrade")

            if success:
                success_count += 1
            else:
                fail_count += 1

        total_duration = time.time() - total_start

        print(f"\n{'='*70}")
        print(f"ROLLBACK SUMMARY")
        print(f"{'='*70}")
        print(f"Total duration: {total_duration:.2f} seconds")
        print(f"Successful: {success_count}")
        print(f"Failed: {fail_count}")
        print(f"{'='*70}\n")


def show_migration_status() -> None:
    """
    Show status of all migrations.
    """
    tracker_conn = init_migration_tracker()
    applied_migrations = get_applied_migrations(tracker_conn)

    print(f"\n{'='*70}")
    print("MIGRATION STATUS")
    print(f"{'='*70}\n")

    for migration_info in MIGRATIONS:
        migration_id, module_name, db_path, description = migration_info
        is_applied = migration_id in applied_migrations
        status = "✅ APPLIED" if is_applied else "⏸  PENDING"

        print(f"{status} | {migration_id} | {description}")
        print(f"         Database: {db_path}")

        if is_applied:
            cursor = tracker_conn.execute(
                """
                SELECT applied_date, duration_seconds
                FROM migration_history
                WHERE migration_id = ? AND status = 'applied'
                ORDER BY applied_at DESC
                LIMIT 1
                """,
                (migration_id,),
            )
            row = cursor.fetchone()
            if row:
                applied_date, duration = row
                print(f"         Applied: {applied_date} ({duration:.2f}s)")

        print()

    # Show migration history
    cursor = tracker_conn.execute(
        """
        SELECT migration_id, migration_name, status, applied_date, duration_seconds
        FROM migration_history
        ORDER BY applied_at DESC
        LIMIT 10
        """
    )

    history = cursor.fetchall()
    if history:
        print(f"\n{'='*70}")
        print("RECENT MIGRATION HISTORY")
        print(f"{'='*70}\n")

        for row in history:
            mig_id, mig_name, status, applied_date, duration = row
            print(f"{mig_id} | {status.upper()} | {applied_date} ({duration:.2f}s)")

    tracker_conn.close()
    print()


def verify_databases() -> None:
    """
    Verify that all databases exist and have correct schemas.
    """
    print(f"\n{'='*70}")
    print("DATABASE VERIFICATION")
    print(f"{'='*70}\n")

    databases = [
        ("data/positions.db", "positions"),
        ("data/trading.db", "orders"),
        ("data/ml_training.db", "training_runs"),
    ]

    all_ok = True

    for db_path, expected_table in databases:
        if not os.path.exists(db_path):
            print(f"❌ {db_path}: NOT FOUND")
            all_ok = False
            continue

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (expected_table,),
            )
            table_exists = cursor.fetchone() is not None
            conn.close()

            if table_exists:
                print(f"✅ {db_path}: OK (has '{expected_table}' table)")
            else:
                print(f"⚠️  {db_path}: EXISTS but missing '{expected_table}' table")
                all_ok = False

        except Exception as e:
            print(f"❌ {db_path}: ERROR - {e}")
            all_ok = False

    print()
    if all_ok:
        print("✅ All databases verified successfully!\n")
    else:
        print("⚠️  Some databases need migration. Run: python -m catalyst_bot.migrations.migrate\n")


def main():
    parser = argparse.ArgumentParser(
        description="Catalyst Bot Database Migration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m catalyst_bot.migrations.migrate                # Run all pending migrations
  python -m catalyst_bot.migrations.migrate upgrade         # Same as above
  python -m catalyst_bot.migrations.migrate upgrade --migration 001
  python -m catalyst_bot.migrations.migrate downgrade       # Rollback all migrations
  python -m catalyst_bot.migrations.migrate status          # Show migration status
  python -m catalyst_bot.migrations.migrate verify          # Verify databases
        """,
    )

    parser.add_argument(
        "action",
        nargs="?",
        default="upgrade",
        choices=["upgrade", "downgrade", "status", "verify"],
        help="Action to perform (default: upgrade)",
    )

    parser.add_argument(
        "--migration",
        "-m",
        help="Specific migration to run (e.g., 001)",
    )

    args = parser.parse_args()

    if args.action == "status":
        show_migration_status()

    elif args.action == "verify":
        verify_databases()

    elif args.action in ("upgrade", "downgrade"):
        if args.migration:
            # Run specific migration
            success, message = run_migration(args.migration, args.action)
            sys.exit(0 if success else 1)
        else:
            # Run all migrations
            run_all_migrations(args.action)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
