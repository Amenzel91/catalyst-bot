# Narrow deprecation filter for tests only.
# Keeps application logging intact while preventing noisy utcnow warnings during pytest runs.
import sys
import types
import warnings

import pytest


def pytest_configure(config):
    # Suppress only the well-known Python 3.12+ deprecation for datetime.utcnow() in tests.
    warnings.filterwarnings(
        "ignore",
        message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
        category=DeprecationWarning,
    )


def pytest_collection_modifyitems(config, items):
    """Skip trio backend tests since trio is not installed."""
    skip_trio = pytest.mark.skip(reason="trio backend not installed")
    for item in items:
        if "trio" in item.nodeid:
            item.add_marker(skip_trio)


@pytest.fixture(autouse=True, scope="session")
def _stub_feedparser_module():
    """
    Ensure catalyst_bot.feeds imports without external dependency.
    We inject a minimal 'feedparser' module whose parse() returns an object
    with an empty 'entries' list by default. Individual tests can monkeypatch
    parse() to return custom entries.
    """
    if "feedparser" not in sys.modules:
        m = types.SimpleNamespace()

        def _parse(_text):
            class _R:
                pass

            _R.entries = []
            return _R

        m.parse = _parse
        sys.modules["feedparser"] = m
    yield


@pytest.fixture(autouse=True, scope="session")
def _ensure_market_db(tmp_path_factory):
    """
    Ensure that a SQLite database with the expected schema exists under the
    ``data`` directory for tests that depend on it.

    Tests such as ``test_db_integrity`` expect ``data/market.db`` to be present
    with a table named ``finviz_filings``.  This fixture creates that file and
    table if they do not already exist.
    """
    import os
    import sqlite3

    data_dir = os.path.join(os.getcwd(), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    db_path = os.path.join(data_dir, "market.db")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS finviz_filings ("
            "ticker TEXT, filing_type TEXT, filing_date TEXT, title TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS finviz_screener_snapshots ("
            "ticker TEXT, ts TEXT, preset TEXT)"
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    yield
