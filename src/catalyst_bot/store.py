"""Persistence utilities for the catalyst bot.

This module contains helper functions for reading and writing data
to disk in a durable, append‑only manner. Most data is persisted
as JSON Lines (JSONL) files to facilitate incremental updates and
simple recovery in the event of a crash. Idempotent operations
such as deduplication and seen ID tracking are also provided.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Set


def append_jsonl(path: Path, record: Dict) -> None:
    """Append a single record as a JSON object to a JSONL file.

    Parameters
    ----------
    path : Path
        Path to the JSONL file. Parent directories are created if
        necessary.
    record : Dict
        The record to serialize and append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception:
        # Fail silently – persistence should not block execution
        pass


def read_jsonl(path: Path) -> Iterator[Dict]:
    """Yield each record from a JSONL file as a dict.

    Parameters
    ----------
    path : Path
        Path to the JSONL file.

    Yields
    ------
    Dict
        Parsed JSON object from each line of the file.
    """
    if not path.exists():
        return iter(())
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return iter(())


def rolling_last24(path: Path) -> List[Dict]:
    """Return records from a JSONL file within the last 24 hours.

    This helper is used to produce the ``last24.jsonl`` file from the raw
    ingest. It filters based on the ``ts_utc`` field if present.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)
    records: List[Dict] = []
    for rec in read_jsonl(path):
        try:
            ts = datetime.fromisoformat(rec.get("ts_utc"))  # type: ignore[arg-type]
        except Exception:
            continue
        if ts >= twenty_four_hours_ago:
            records.append(rec)
    return records


def load_seen_ids(path: Path) -> Set[str]:
    """Load a set of seen item identifiers from a JSON file.

    Parameters
    ----------
    path : Path
        Path to the JSON file storing a list of identifiers.

    Returns
    -------
    Set[str]
        A set of identifiers that have already been processed.
    """
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data)
    except Exception:
        return set()


def save_seen_ids(ids: Set[str], path: Path) -> None:
    """Persist the set of seen item identifiers to a JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(list(ids))), encoding="utf-8")
    except Exception:
        pass
