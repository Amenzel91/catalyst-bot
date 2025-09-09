# tests/test_db_integrity.py
import os
import sqlite3


def test_unique_keys():
    c = sqlite3.connect(os.path.join("data", "market.db"))
    f = c.execute(
        (
            "select coalesce(sum(cnt-1),0) "
            "from (select count(*) cnt from finviz_filings "
            "group by ifnull(ticker,''), "
            "ifnull(filing_type,''), "
            "ifnull(filing_date,''), "
            "ifnull(title,''))"
        )
    ).fetchone()[0]
    s = c.execute(
        (
            "select coalesce(sum(cnt-1),0) "
            "from (select count(*) cnt from finviz_screener_snapshots "
            "group by ifnull(ticker,''), "
            "ifnull(ts,''), "
            "ifnull(preset,''))"
        )
    ).fetchone()[0]
    assert f == 0 and s == 0
