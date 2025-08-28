# tests/test_db_integrity.py
from __future__ import annotations

import os
import sqlite3

DB_PATH = os.getenv("MARKET_DB_PATH", os.path.join("data", "market.db"))


def test_unique_keys():
    c = sqlite3.connect(DB_PATH)

    dup_filings = c.execute(
        """
        SELECT COALESCE(SUM(cnt-1),0)
        FROM (
          SELECT COUNT(*) AS cnt
          FROM finviz_filings
          GROUP BY
            COALESCE(ticker,''),
            COALESCE(filing_type,''),
            COALESCE(filing_date,''),
            COALESCE(title,'')
        ) t
        WHERE cnt > 1
        """
    ).fetchone()[0]

    dup_snapshots = c.execute(
        """
        SELECT COALESCE(SUM(cnt-1),0)
        FROM (
          SELECT COUNT(*) AS cnt
          FROM finviz_screener_snapshots
          GROUP BY
            COALESCE(ticker,''),
            COALESCE(ts,''),
            COALESCE(preset,'')
        ) t
        WHERE cnt > 1
        """
    ).fetchone()[0]

    assert dup_filings == 0
    assert dup_snapshots == 0
