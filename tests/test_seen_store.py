import time
from pathlib import Path

from catalyst_bot.seen_store import SeenStore, SeenStoreConfig, should_filter


def test_seen_store_mark_and_query_roundtrip(tmp_path: Path):
    db_path = tmp_path / "seen.sqlite"
    store = SeenStore(SeenStoreConfig(path=db_path, ttl_days=7))
    assert store.is_seen("id-1") is False
    store.mark_seen("id-1", ts=int(time.time()))
    assert store.is_seen("id-1") is True


def test_should_filter_with_env_flag_off(monkeypatch, tmp_path: Path):
    # Force off
    monkeypatch.setenv("FEATURE_PERSIST_SEEN", "false")
    db_path = tmp_path / "seen.sqlite"
    store = SeenStore(SeenStoreConfig(path=db_path, ttl_days=7))
    # First time, should not filter; and not persist because feature is off
    assert should_filter("abc", store) is False
    # Again false — because feature is off (we aren't checking DB)
    assert should_filter("abc", store) is False


def test_ttl_cleanup(tmp_path: Path):
    db_path = tmp_path / "seen.sqlite"
    store = SeenStore(SeenStoreConfig(path=db_path, ttl_days=0))
    # Insert seen with old timestamp
    old_ts = int(time.time()) - 999999
    store.mark_seen("dead", ts=old_ts)
    store.purge_expired()
    assert store.is_seen("dead") is False
