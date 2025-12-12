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
    from .storage import init_optimized_connection

    p = Path(db_path) if db_path else _db_path()
    conn = init_optimized_connection(str(p))
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


def refresh_cik_mappings_from_sec(
    output_path: str = None, user_agent: str = "catalyst-bot/1.0 contact@example.com"
) -> bool:
    """
    Fetch latest CIK-to-ticker mappings from SEC and update local NDJSON.

    Downloads from official SEC API and converts to NDJSON format.
    CRITICAL: Uses "cik" field name to match _bootstrap_if_needed() at line 79.

    Parameters
    ----------
    output_path : str, optional
        Path to output NDJSON file. Defaults to repo root company_tickers.ndjson
    user_agent : str
        User-Agent header (SEC requires identification)

    Returns
    -------
    bool
        True if refresh succeeded, False otherwise

    Notes
    -----
    SEC rate limits API access. Don't call more than once per day.
    Bot must be restarted OR tickers.db deleted to reload mappings.
    """
    from pathlib import Path

    import requests

    if output_path is None:
        output_path = str(_ndjson_path())

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": user_agent}

    try:
        log.info("cik_refresh_started source=sec_api")

        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        data = r.json()

        if not data:
            log.error("cik_refresh_failed reason=empty_response")
            return False

        # Backup existing file
        output = Path(output_path)
        if output.exists():
            backup_path = output.with_suffix(".ndjson.backup")
            output.rename(backup_path)
            log.info("cik_refresh_backup created=%s", backup_path)

        # Write NDJSON with CORRECT field name
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for entry in data.values():
                cik_str = str(entry.get("cik_str", "")).strip()
                ticker = entry.get("ticker", "").strip()
                title = entry.get("title", "").strip()

                if not cik_str or not ticker:
                    continue

                cik_padded = cik_str.zfill(10)

                # CRITICAL: Use "cik" field to match line 79
                record = {"cik": cik_padded, "ticker": ticker.upper(), "title": title}

                f.write(json.dumps(record) + "\n")
                count += 1

        log.info("cik_refresh_complete entries=%d path=%s", count, output_path)

        return True

    except requests.exceptions.RequestException as e:
        log.error(
            "cik_refresh_http_error err=%s status=%s",
            e.__class__.__name__,
            getattr(getattr(e, "response", None), "status_code", "N/A"),
        )
        return False
    except Exception as e:
        log.error("cik_refresh_failed err=%s msg=%s", e.__class__.__name__, str(e))
        return False


def auto_refresh_cik_mappings_if_stale(
    max_age_days: int = 7, mapping_file: str = None
) -> None:
    """
    Automatically refresh CIK mappings if NDJSON file is older than max_age_days.

    Call this on bot startup to ensure mappings are fresh.

    Parameters
    ----------
    max_age_days : int
        Refresh if file is older than this many days
    mapping_file : str, optional
        Path to NDJSON file. Defaults to repo root.
    """
    from datetime import datetime, timedelta
    from pathlib import Path

    if mapping_file is None:
        mapping_file = str(_ndjson_path())

    try:
        path = Path(mapping_file)

        if not path.exists():
            log.warning("cik_mapping_missing attempting_refresh")
            refresh_cik_mappings_from_sec(output_path=mapping_file)
            return

        # Check file age
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age = datetime.now() - mtime

        if age > timedelta(days=max_age_days):
            log.info(
                "cik_mapping_stale age_days=%.1f threshold=%d refreshing",
                age.total_seconds() / 86400,
                max_age_days,
            )
            refresh_cik_mappings_from_sec(output_path=mapping_file)
        else:
            log.info("cik_mapping_fresh age_days=%.1f", age.total_seconds() / 86400)

    except Exception as e:
        log.warning(
            "cik_mapping_age_check_failed err=%s continuing", e.__class__.__name__
        )


def cik_from_text(text: str | None) -> str | None:
    """
    Extract a CIK from EDGAR text using the compiled regex ``_CIK_RE``.

    Returns the first matching CIK string if found, otherwise ``None``.
    """
    if not text:
        return None
    match = _CIK_RE.search(text)
    return match.group(1) if match else None
