import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict

from .logging_utils import get_logger

_CIK_RE = re.compile(r"/edgar/data/(\d+)/", re.IGNORECASE)

log = get_logger("ticker_map")

_DEFAULT_DB_NAME = "tickers.db"
_DEFAULT_DB_DIR = "data"

_TICKERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    cik    TEXT PRIMARY KEY,
    ticker TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_tickers_ticker ON tickers(ticker);
"""


def _repo_root() -> Path:
    """Return the repository root based on this file's location."""
    return Path(__file__).resolve().parents[2]


def _ndjson_path() -> Path:
    """Return the absolute path to the bundled ``company_tickers.ndjson`` file."""
    return _repo_root() / "company_tickers.ndjson"


def _db_path() -> Path:
    """Compute the path to the tickers database.

    The path can be specified via the ``TICKERS_DB_PATH`` environment variable.
    Otherwise, it defaults to ``data/tickers.db`` under the current working directory.
    The directory is created if it does not exist.
    """
    env_path = os.getenv("TICKERS_DB_PATH")
    if env_path:
        p = Path(env_path)
    else:
        p = Path(_DEFAULT_DB_DIR) / _DEFAULT_DB_NAME
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        p = Path(_DEFAULT_DB_NAME)
    return p.resolve()


def _bootstrap_if_needed(conn: sqlite3.Connection) -> None:
    """Bootstrap the tickers table from NDJSON if it doesn't exist."""
    try:
        conn.execute("SELECT 1 FROM tickers LIMIT 1").fetchone()
        return  # Table exists
    except sqlite3.OperationalError:
        try:
            conn.executescript(_TICKERS_SCHEMA)
        except Exception as exc:
            log.error("ticker_bootstrap_schema_error", exc_info=exc)
            return
        ndj_path = _ndjson_path()
        if not ndj_path.exists():
            log.warning("ticker_bootstrap_missing_ndjson path=%s", str(ndj_path))
            return
        inserted = 0
        try:
            with ndj_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        cik = str(obj.get("cik") or "").strip()
                        ticker = str(obj.get("ticker") or "").strip().upper()
                        if cik and ticker:
                            conn.execute(
                                "INSERT OR REPLACE INTO tickers(cik,ticker) VALUES(?, ?)",
                                (cik, ticker),
                            )
                            inserted += 1
                    except Exception:
                        continue
            conn.commit()
            log.info("ticker_bootstrap_done rows=%s", inserted)
        except Exception as exc:
            log.error("ticker_bootstrap_failed", exc_info=exc)


#
# Public API
#
def load_cik_to_ticker(db_path: str | None = None) -> Dict[str, str]:
    """
    Return a mapping of CIK to ticker.

    On first use, this function bootstraps the database and ``tickers``
    table using the bundled ``company_tickers.ndjson`` file if necessary.

    The optional ``db_path`` parameter overrides the default location
    returned by ``_db_path()``; the path must be a file location for a
    SQLite database.
    """
    p = Path(db_path) if db_path else _db_path()
    conn = sqlite3.connect(str(p))
    try:
        _bootstrap_if_needed(conn)
        rows = conn.execute("SELECT cik, ticker FROM tickers").fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    mapping: Dict[str, str] = {}
    for cik, ticker in rows:
        if not cik or not ticker:
            continue
        # Normalize CIK to string and uppercase ticker
        try:
            key = str(int(cik))
        except Exception:
            key = str(cik)
        val = (str(ticker) or "").strip().upper()
        if not val:
            continue
        mapping[key] = val
        # SEC sometimes pads CIKs to 10 digits
        if len(key) < 10:
            mapping[key.zfill(10)] = val
    return mapping


def cik_from_text(text: str | None) -> str | None:
    """
    Extract a CIK from EDGAR text using the compiled regex ``_CIK_RE``.

    Returns the first matching CIK string if found, otherwise ``None``.
    """
    if not text:
        return None
    match = _CIK_RE.search(text)
    return match.group(1) if match else None
