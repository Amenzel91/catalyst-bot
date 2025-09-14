"""Market database access helpers.

This module provides a thin wrapper around the core storage
implementation for the bot's market database.  It exposes simple
``connect`` and ``migrate`` functions that mirror those defined in
``catalyst_bot.storage`` but with a more descriptive name.  Using
these helpers avoids leaking implementation details (like the
underlying file name) throughout the codebase and makes it easier to
override or extend the storage behaviour in future patches.

The default database path is controlled by the ``MARKET_DB_PATH``
environment variable and falls back to ``data/market.db`` if unset.
See ``catalyst_bot.storage`` for more information on the schema.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from . import storage

# Re-export the default DB path so callers can inspect it if needed.
DB_PATH: str = os.getenv("MARKET_DB_PATH", "data/market.db")


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a SQLite connection to the market database.

    Parameters
    ----------
    db_path : str, optional
        Explicit database file to open.  If omitted, the path defined by
        ``MARKET_DB_PATH`` or ``data/market.db`` is used.

    Returns
    -------
    sqlite3.Connection
        An open connection to the requested database with WAL mode and
        busy timeout configured.
    """
    return storage.connect(db_path or DB_PATH)


def migrate(conn: sqlite3.Connection) -> None:
    """Ensure all required tables exist in the market database.

    This forwards to ``catalyst_bot.storage.migrate`` and is safe to
    call multiple times.  The function does not close the connection.

    Parameters
    ----------
    conn : sqlite3.Connection
        An open SQLite connection obtained via :func:`connect`.
    """
    storage.migrate(conn)
