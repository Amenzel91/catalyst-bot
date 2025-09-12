from pathlib import Path

from catalyst_bot.alerts import post_admin_summary_md
from catalyst_bot.config import get_settings


def test_post_admin_summary_md_noop_without_flag(tmp_path: Path, monkeypatch):
    # Ensure flag off -> returns False
    p = tmp_path / "summary_2025-09-10.md"
    p.write_text("A\nB\nC\n", encoding="utf-8")
    get_settings()
    monkeypatch.setenv("FEATURE_ADMIN_EMBED", "0")
    monkeypatch.setenv("ADMIN_SUMMARY_PATH", str(p))
    assert post_admin_summary_md(str(p)) is False


def test_post_admin_summary_md_path_missing_returns_false(monkeypatch):
    monkeypatch.setenv("FEATURE_ADMIN_EMBED", "1")
    monkeypatch.setenv(
        "DISCORD_ADMIN_WEBHOOK", "https://discord.com/api/webhooks/TEST/TEST"
    )
    assert post_admin_summary_md("does_not_exist.md") is False
