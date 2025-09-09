# scripts/db_migrations/create_indexes_and_views.py
from __future__ import annotations

import os
import sqlite3

DB_PATH = os.getenv("MARKET_DB_PATH", os.path.join("data", "market.db"))


def _col_missing(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table});")
    cols = {r[1].lower() for r in cur.fetchall()}
    return col.lower() not in cols


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    if _col_missing(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl};")


def _ensure_snapshots_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS finviz_screener_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticker TEXT
    );
    """
    )
    _ensure_column(conn, "finviz_screener_snapshots", "ts", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "finviz_screener_snapshots", "preset", "TEXT")
    _ensure_column(conn, "finviz_screener_snapshots", "company", "TEXT")
    _ensure_column(conn, "finviz_screener_snapshots", "sector", "TEXT")
    _ensure_column(conn, "finviz_screener_snapshots", "industry", "TEXT")
    _ensure_column(conn, "finviz_screener_snapshots", "country", "TEXT")
    _ensure_column(conn, "finviz_screener_snapshots", "price", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "change", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "volume", "INTEGER")
    _ensure_column(conn, "finviz_screener_snapshots", "avgvol", "INTEGER")
    _ensure_column(conn, "finviz_screener_snapshots", "relvolume", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "marketcap", "TEXT")
    _ensure_column(conn, "finviz_screener_snapshots", "perf_day", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "perf_week", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "perf_month", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "perf_quarter", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "perf_halfy", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "perf_year", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "vol_w", "REAL")
    _ensure_column(conn, "finviz_screener_snapshots", "vol_m", "REAL")


def _ensure_filings_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS finviz_filings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticker TEXT
    );
    """
    )
    _ensure_column(conn, "finviz_filings", "filing_date", "TEXT")
    _ensure_column(conn, "finviz_filings", "filing_type", "TEXT")
    _ensure_column(conn, "finviz_filings", "title", "TEXT")
    _ensure_column(conn, "finviz_filings", "url", "TEXT")


def _dedupe_filings(conn: sqlite3.Connection) -> int:
    """
    Keep the earliest row (MIN(id)) for each logical key:
    (ticker, filing_type, filing_date, title) after COALESCE to ''.
    Delete all others.
    """
    # Count duplicates to report
    cur = conn.execute(
        """
    SELECT COUNT(*) FROM finviz_filings f
    JOIN (
      SELECT
        COALESCE(ticker,'') AS k1,
        COALESCE(filing_type,'') AS k2,
        COALESCE(filing_date,'') AS k3,
        COALESCE(title,'') AS k4,
        COUNT(*) AS cnt
      FROM finviz_filings
      GROUP BY 1,2,3,4
      HAVING cnt > 1
    ) d
      ON COALESCE(f.ticker,'') = d.k1
     AND COALESCE(f.filing_type,'') = d.k2
     AND COALESCE(f.filing_date,'') = d.k3
     AND COALESCE(f.title,'') = d.k4;
    """
    )
    dup_rows = cur.fetchone()[0]

    # Delete all but MIN(id) per key
    conn.execute(
        """
    DELETE FROM finviz_filings
    WHERE id NOT IN (
      SELECT MIN(id) FROM finviz_filings
      GROUP BY
        COALESCE(ticker,''),
        COALESCE(filing_type,''),
        COALESCE(filing_date,''),
        COALESCE(title,'')
    );
    """
    )
    return dup_rows


def _dedupe_snapshots(conn: sqlite3.Connection) -> int:
    """
    Keep the earliest row (MIN(id)) for each (ticker, ts, preset) after COALESCE.
    """
    cur = conn.execute(
        """
    SELECT COUNT(*) FROM finviz_screener_snapshots s
    JOIN (
      SELECT
        COALESCE(ticker,'') AS k1,
        COALESCE(ts,'') AS k2,
        COALESCE(preset,'') AS k3,
        COUNT(*) AS cnt
      FROM finviz_screener_snapshots
      GROUP BY 1,2,3
      HAVING cnt > 1
    ) d
      ON COALESCE(s.ticker,'') = d.k1
     AND COALESCE(s.ts,'') = d.k2
     AND COALESCE(s.preset,'') = d.k3;
    """
    )
    dup_rows = cur.fetchone()[0]

    conn.execute(
        """
    DELETE FROM finviz_screener_snapshots
    WHERE id NOT IN (
      SELECT MIN(id) FROM finviz_screener_snapshots
      GROUP BY
        COALESCE(ticker,''),
        COALESCE(ts,''),
        COALESCE(preset,'')
    );
    """
    )
    return dup_rows


def _create_indexes_and_views(conn: sqlite3.Connection) -> None:
    # Indexes that don't enforce uniqueness can go in first
    conn.executescript(
        """
    CREATE INDEX IF NOT EXISTS idx_snapshots_preset_ts ON finviz_screener_snapshots(preset, ts);
    CREATE INDEX IF NOT EXISTS idx_snapshots_ticker ON finviz_screener_snapshots(ticker);
    CREATE INDEX IF NOT EXISTS idx_filings_ticker ON finviz_filings(ticker);
    """
    )

    # Deduplicate BEFORE creating unique constraints
    dup_f = _dedupe_filings(conn)
    dup_s = _dedupe_snapshots(conn)

    # Now unique indexes are safe to create
    conn.executescript(
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_key "
            "ON finviz_screener_snapshots(ticker, ts, COALESCE(preset,''));"
            "\n"
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_filings_key "
            "ON finviz_filings("
            "ticker, COALESCE(filing_type,''), COALESCE(filing_date,''), COALESCE(title,''));"
            "\n"
            "CREATE VIEW IF NOT EXISTS v_latest_snapshot AS "
            "SELECT s.* FROM finviz_screener_snapshots s "
            "    JOIN (SELECT ticker, MAX(ts) AS max_ts FROM finviz_screener_snapshots "
            "GROUP BY ticker) m "
            "ON m.ticker = s.ticker AND m.max_ts = s.ts;"
        )
    )

    print(f"Deduped filings rows removed (approx): {dup_f}")
    print(f"Deduped snapshot rows removed (approx): {dup_s}")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("BEGIN")

        _ensure_snapshots_columns(conn)
        _ensure_filings_columns(conn)

        _create_indexes_and_views(conn)

        conn.commit()
        print("Indexes & view created/verified at:", DB_PATH)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
