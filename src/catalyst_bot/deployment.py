"""Deployment utilities for safe deployments and rollbacks.

This module provides functions for backing up configuration, creating deployment
tags, and rolling back to previous versions.

WAVE 2.3: 24/7 Deployment Infrastructure

Usage:
    from catalyst_bot.deployment import backup_config, create_deployment_tag

    # Before deployment
    backup_config()
    create_deployment_tag("v1.2.3")

    # If something goes wrong
    from catalyst_bot.deployment import rollback_to_tag
    rollback_to_tag("v1.2.2")
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

try:
    from .logging_utils import get_logger

    log = get_logger("deployment")
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("deployment")


def get_project_root() -> Path:
    """Get the project root directory.

    Returns
    -------
    Path
        Project root directory
    """
    # Assume this file is in src/catalyst_bot/deployment.py
    # Project root is two levels up
    return Path(__file__).parent.parent.parent


def backup_config(backup_name: Optional[str] = None) -> Path:
    """Backup the .env configuration file.

    Parameters
    ----------
    backup_name : str, optional
        Custom backup filename, defaults to .env.backup or timestamped name

    Returns
    -------
    Path
        Path to the backup file

    Raises
    ------
    FileNotFoundError
        If .env file doesn't exist
    IOError
        If backup fails
    """
    root = get_project_root()
    env_file = root / ".env"

    if not env_file.exists():
        raise FileNotFoundError(f".env file not found at {env_file}")

    if backup_name is None:
        # Create timestamped backup in backups/ directory
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = root / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_file = backup_dir / f"env_backup_{timestamp}.env"
    else:
        backup_file = root / backup_name

    try:
        shutil.copy2(env_file, backup_file)
        log.info(f"config_backup_created path={backup_file}")
        return backup_file
    except Exception as e:
        log.error(f"config_backup_failed err={e.__class__.__name__}", exc_info=True)
        raise IOError(f"Failed to backup config: {e}")


def restore_config(backup_file: Optional[Path] = None) -> None:
    """Restore configuration from a backup.

    Parameters
    ----------
    backup_file : Path, optional
        Path to backup file, defaults to .env.backup

    Raises
    ------
    FileNotFoundError
        If backup file doesn't exist
    IOError
        If restore fails
    """
    root = get_project_root()
    env_file = root / ".env"

    if backup_file is None:
        backup_file = root / ".env.backup"

    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found at {backup_file}")

    try:
        shutil.copy2(backup_file, env_file)
        log.info(f"config_restored from={backup_file}")
    except Exception as e:
        log.error(f"config_restore_failed err={e.__class__.__name__}", exc_info=True)
        raise IOError(f"Failed to restore config: {e}")


def get_current_commit() -> str:
    """Get the current git commit hash.

    Returns
    -------
    str
        Current commit hash (short form)

    Raises
    ------
    RuntimeError
        If not a git repository or git command fails
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=get_project_root(),
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get current commit: {e}")


def create_deployment_tag(
    tag_name: str, message: Optional[str] = None, push: bool = False
) -> None:
    """Create a git tag for a deployment.

    Parameters
    ----------
    tag_name : str
        Tag name (e.g., "v1.2.3")
    message : str, optional
        Tag annotation message
    push : bool
        Whether to push the tag to remote (default: False)

    Raises
    ------
    RuntimeError
        If git command fails
    """
    root = get_project_root()

    if message is None:
        message = f"Deployment {tag_name} - {datetime.now(timezone.utc).isoformat()}"

    try:
        # Create annotated tag
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", message],
            check=True,
            cwd=root,
            capture_output=True,
        )
        log.info(f"deployment_tag_created tag={tag_name}")

        # Optionally push to remote
        if push:
            subprocess.run(
                ["git", "push", "origin", tag_name],
                check=True,
                cwd=root,
                capture_output=True,
            )
            log.info(f"deployment_tag_pushed tag={tag_name}")

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else ""
        log.error(f"tag_creation_failed tag={tag_name} err={stderr}")
        raise RuntimeError(f"Failed to create tag: {stderr}")


def list_deployment_tags(limit: int = 10) -> list[Tuple[str, str]]:
    """List recent deployment tags.

    Parameters
    ----------
    limit : int
        Maximum number of tags to return

    Returns
    -------
    list of tuples
        List of (tag_name, commit_hash) tuples
    """
    root = get_project_root()

    try:
        result = subprocess.run(
            ["git", "tag", "-l", "--sort=-creatordate"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        )

        tags = []
        for tag in result.stdout.strip().split("\n")[:limit]:
            if not tag:
                continue
            # Get commit hash for this tag
            commit_result = subprocess.run(
                ["git", "rev-list", "-n", "1", tag],
                capture_output=True,
                text=True,
                check=True,
                cwd=root,
            )
            commit_hash = commit_result.stdout.strip()[:7]
            tags.append((tag, commit_hash))

        return tags
    except subprocess.CalledProcessError:
        return []


def rollback_to_tag(tag_name: str, restore_backup: bool = True) -> None:
    """Rollback to a previous git tag.

    Parameters
    ----------
    tag_name : str
        Tag to rollback to (e.g., "v1.2.2")
    restore_backup : bool
        Whether to also restore .env.backup (default: True)

    Raises
    ------
    RuntimeError
        If rollback fails
    """
    root = get_project_root()

    log.warning(f"rollback_initiated tag={tag_name}")

    try:
        # Verify tag exists
        subprocess.run(
            ["git", "rev-parse", tag_name],
            check=True,
            cwd=root,
            capture_output=True,
        )

        # Checkout the tag
        subprocess.run(
            ["git", "checkout", tag_name],
            check=True,
            cwd=root,
            capture_output=True,
        )

        log.info(f"git_rollback_complete tag={tag_name}")

        # Restore config backup if requested
        if restore_backup:
            backup_file = root / ".env.backup"
            if backup_file.exists():
                restore_config(backup_file)
                log.info("config_restored from=.env.backup")
            else:
                log.warning("config_backup_not_found skipping_restore=true")

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else ""
        log.error(f"rollback_failed tag={tag_name} err={stderr}")
        raise RuntimeError(f"Rollback failed: {stderr}")


def rollback_to_commit(commit_hash: str, restore_backup: bool = True) -> None:
    """Rollback to a specific commit.

    Parameters
    ----------
    commit_hash : str
        Commit hash to rollback to
    restore_backup : bool
        Whether to also restore .env.backup (default: True)

    Raises
    ------
    RuntimeError
        If rollback fails
    """
    root = get_project_root()

    log.warning(f"rollback_initiated commit={commit_hash}")

    try:
        # Verify commit exists
        subprocess.run(
            ["git", "rev-parse", commit_hash],
            check=True,
            cwd=root,
            capture_output=True,
        )

        # Checkout the commit
        subprocess.run(
            ["git", "checkout", commit_hash],
            check=True,
            cwd=root,
            capture_output=True,
        )

        log.info(f"git_rollback_complete commit={commit_hash}")

        # Restore config backup if requested
        if restore_backup:
            backup_file = root / ".env.backup"
            if backup_file.exists():
                restore_config(backup_file)
                log.info("config_restored from=.env.backup")
            else:
                log.warning("config_backup_not_found skipping_restore=true")

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else ""
        log.error(f"rollback_failed commit={commit_hash} err={stderr}")
        raise RuntimeError(f"Rollback failed: {stderr}")


def get_deployment_info() -> dict:
    """Get current deployment information.

    Returns
    -------
    dict
        Deployment information including commit, branch, tags
    """
    root = get_project_root()
    info = {}

    try:
        # Get current commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        )
        info["commit"] = result.stdout.strip()[:7]

        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        )
        info["branch"] = result.stdout.strip()

        # Get tags pointing to current commit
        result = subprocess.run(
            ["git", "tag", "--points-at", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        )
        tags = [t.strip() for t in result.stdout.split("\n") if t.strip()]
        info["tags"] = tags

        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
        )
        info["dirty"] = bool(result.stdout.strip())

    except subprocess.CalledProcessError:
        info["error"] = "Failed to get git info"

    return info


def main():
    """CLI entry point for deployment utilities."""
    import argparse

    parser = argparse.ArgumentParser(description="Catalyst-Bot Deployment Utilities")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup .env configuration")
    backup_parser.add_argument(
        "--name", help="Backup filename (default: timestamped)", default=None
    )

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore .env from backup")
    restore_parser.add_argument(
        "--file", help="Backup file to restore (default: .env.backup)", default=None
    )

    # Tag command
    tag_parser = subparsers.add_parser("tag", help="Create deployment tag")
    tag_parser.add_argument("tag_name", help="Tag name (e.g., v1.2.3)")
    tag_parser.add_argument("--message", help="Tag message", default=None)
    tag_parser.add_argument("--push", action="store_true", help="Push tag to remote")

    # List tags command
    subparsers.add_parser("list-tags", help="List recent deployment tags")

    # Rollback command
    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback to tag or commit"
    )
    rollback_parser.add_argument("target", help="Tag name or commit hash")
    rollback_parser.add_argument(
        "--no-restore", action="store_true", help="Don't restore .env.backup"
    )

    # Info command
    subparsers.add_parser("info", help="Show current deployment info")

    args = parser.parse_args()

    if args.command == "backup":
        backup_file = backup_config(args.name)
        print(f"Configuration backed up to: {backup_file}")

    elif args.command == "restore":
        restore_file = Path(args.file) if args.file else None
        restore_config(restore_file)
        print(f"Configuration restored from: {restore_file or '.env.backup'}")

    elif args.command == "tag":
        create_deployment_tag(args.tag_name, args.message, args.push)
        print(f"Tag created: {args.tag_name}")
        if args.push:
            print("Tag pushed to remote")

    elif args.command == "list-tags":
        tags = list_deployment_tags()
        if not tags:
            print("No tags found")
        else:
            print("Recent deployment tags:")
            for tag, commit in tags:
                print(f"  {tag} ({commit})")

    elif args.command == "rollback":
        # Detect if target is a tag or commit
        try:
            subprocess.run(
                ["git", "rev-parse", args.target],
                check=True,
                capture_output=True,
                cwd=get_project_root(),
            )
            # Check if it's a tag
            result = subprocess.run(
                ["git", "tag", "-l", args.target],
                capture_output=True,
                text=True,
                cwd=get_project_root(),
            )
            is_tag = bool(result.stdout.strip())

            if is_tag:
                rollback_to_tag(args.target, not args.no_restore)
                print(f"Rolled back to tag: {args.target}")
            else:
                rollback_to_commit(args.target, not args.no_restore)
                print(f"Rolled back to commit: {args.target}")

            if not args.no_restore:
                print("Configuration restored from .env.backup")

        except subprocess.CalledProcessError:
            print(f"Error: Invalid tag or commit: {args.target}")
            return 1

    elif args.command == "info":
        info = get_deployment_info()
        print("Current Deployment Info:")
        print(f"  Commit: {info.get('commit', 'unknown')}")
        print(f"  Branch: {info.get('branch', 'unknown')}")
        print(f"  Tags: {', '.join(info.get('tags', [])) or 'none'}")
        print(f"  Dirty: {info.get('dirty', False)}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
