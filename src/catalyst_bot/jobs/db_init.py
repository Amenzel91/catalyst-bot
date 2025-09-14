"""Database initialization and maintenance script.

This module can be executed as a script (``python -m catalyst_bot.jobs.db_init``)
to bootstrap all of the SQLite databases used by Catalyst‑Bot.  It
creates missing tables, configures write‑ahead logging (WAL) and
busy‑timeout settings, and optionally vacuums the databases to
reclaim space.  Running the script multiple times is idempotent: it
will not overwrite existing data or cause errors if the tables are
already present.

The responsibilities of this module include:

* Initialising the **market database** used for Finviz screener and
  filings snapshots.  This is handled via the ``market_db`` module,
  which wraps ``storage.connect`` and ``storage.migrate``.
* Initialising the **dedupe database** (``data/dedup/first_seen.db`` by
  default) that stores first‑seen signatures.  The schema creation
  logic lives in ``dedupe.migrate``.
* Initialising the **seen IDs database** (``data/seen_ids.sqlite`` by
  default) used to persist alert IDs and avoid duplicate alerts.  The
  ``SeenStore`` class is used to ensure the schema exists.  WAL and
  vacuum pragmas are applied after construction.
* Bootstrapping the **tickers database** (``data/tickers.db`` by
  default) from the bundled ``company_tickers.ndjson``.  This is
  performed by calling ``ticker_map.load_cik_to_ticker``.  After the
  table is created, WAL and vacuum are applied.

By default, the script runs a full vacuum on each database after
setting WAL mode.  To skip vacuums (which can be slow on very large
files) set the environment variable ``DB_INIT_NO_VACUUM=1`` before
invoking the script.
"""

from __future__ import annotations

import os
import sqlite3

from .. import dedupe, market_db, ticker_map
from ..logging_utils import get_logger
from ..seen_store import SeenStore

log = get_logger("db_init")


def _should_vacuum() -> bool:
    """Return True if vacuum operations should be performed.

    Set the ``DB_INIT_NO_VACUUM`` environment variable to any truthy
    value (e.g., ``"1"``, ``"true"``) to skip vacuums.  Vacuuming
    compacts the database and can reduce file size but may take
    noticeable time for large databases.
    """
    return os.getenv("DB_INIT_NO_VACUUM", "0").strip().lower() in {
        "",
        "0",
        "false",
        "no",
        "off",
    }


def _set_wal_and_timeout(conn: sqlite3.Connection) -> None:
    """Configure WAL journal mode and busy timeout on a connection.

    Parameters
    ----------
    conn : sqlite3.Connection
        The connection on which to set pragmas.  Errors are ignored.
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=4000;")
    except Exception:
        pass


def _vacuum(conn: sqlite3.Connection) -> None:
    """Run VACUUM on a connection if configured to do so."""
    if _should_vacuum():
        try:
            conn.execute("VACUUM;")
        except Exception:
            pass


def init_market_db() -> None:
    """Initialise the market database (snapshots and filings).

    This function creates missing tables and configures WAL mode.
    """
    conn = market_db.connect()
    try:
        market_db.migrate(conn)
        _set_wal_and_timeout(conn)
        _vacuum(conn)
        log.info("market_db_initialised path=%s", market_db.DB_PATH)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_dedupe_db() -> None:
    """Initialise the dedupe database (first‑seen index)."""
    db_path = os.getenv("DEDUP_DB_PATH", os.path.join("data", "dedup", "first_seen.db"))
    # Ensure directory exists
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(db_path)
    try:
        _set_wal_and_timeout(conn)
        dedupe.migrate(conn)
        _vacuum(conn)
        log.info("dedupe_db_initialised path=%s", db_path)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_seen_db() -> None:
    """Initialise the seen IDs database.

    This uses ``SeenStore`` to ensure the schema exists and then
    applies WAL and vacuum.  ``SeenStore`` already purges expired
    entries on construction.
    """
    store = None
    try:
        store = SeenStore()
        path = str(store.cfg.path)
        conn = sqlite3.connect(path)
        _set_wal_and_timeout(conn)
        _vacuum(conn)
        log.info("seen_db_initialised path=%s", path)
    finally:
        # Close the SeenStore's connection and the temp connection
        try:
            if store and hasattr(store, "_conn"):
                store._conn.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def init_tickers_db() -> None:
    """Initialise the tickers database from the bundled NDJSON file."""
    # The load_cik_to_ticker call will create and populate the table if missing.
    try:
        ticker_map.load_cik_to_ticker()
    except Exception as exc:
        log.warning("ticker_db_bootstrap_failed", extra={"error": str(exc)})
        return
    # Determine the path used for the tickers DB
    db_path = os.getenv("TICKERS_DB_PATH")
    if not db_path:
        # Use default path computation from ticker_map.  We mimic the logic
        # here to avoid importing internal helpers.
        default_dir = os.getenv("TICKERS_DB_DIR", "data")  # not exposed in ticker_map
        default_name = os.getenv("TICKERS_DB_NAME", "tickers.db")
        db_path = os.path.join(default_dir, default_name)
    conn = sqlite3.connect(db_path)
    try:
        _set_wal_and_timeout(conn)
        _vacuum(conn)
        log.info("ticker_db_initialised path=%s", db_path)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> None:
    """Run all database initialisation steps."""
    init_market_db()
    init_dedupe_db()
    init_seen_db()
    init_tickers_db()


if __name__ == "__main__":  # pragma: no cover
    main()
