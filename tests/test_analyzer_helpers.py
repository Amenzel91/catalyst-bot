"""Tests for analyzer helper functions.

These tests ensure that the new reporting and pending change helpers
produce files with expected contents. We avoid running the full
`analyze_once` function here because it depends on the project root
layout. Instead, we test the helpers in isolation using a temporary
directory.
"""

import json
from datetime import date
from pathlib import Path

from catalyst_bot.analyzer import _write_markdown_report, _write_pending_changes


def test_write_markdown_report(tmp_path):
    """_write_markdown_report writes a Markdown file with expected sections."""
    out_dir: Path = tmp_path
    target_date = date(2025, 1, 1)
    events = []  # no events needed for this helper
    category_stats = {"demo": [1, 0, 2]}
    weight_proposals = {"demo": 1.5}
    unknown_keywords = {"newterm": 3}
    report_path = _write_markdown_report(
        out_dir, target_date, events, category_stats, weight_proposals, unknown_keywords
    )
    # The helper should create a Markdown file in the given directory
    assert report_path.is_file()
    text = report_path.read_text(encoding="utf-8")
    # Basic headings and table content
    assert "Daily Analyzer Report" in text
    assert "Category Performance" in text
    assert "demo" in text
    assert "Proposed Weight Adjustments" in text
    assert "newterm" in text


def test_write_pending_changes(tmp_path):
    """_write_pending_changes writes a JSON file with plan and proposals."""
    analyzer_dir: Path = tmp_path
    target_date = date(2025, 1, 2)
    weight_proposals = {"demo": 0.8}
    unknown_keywords = {"anotherterm": 1}
    pending_path = _write_pending_changes(
        analyzer_dir, target_date, weight_proposals, unknown_keywords
    )
    assert pending_path.is_file()
    data = json.loads(pending_path.read_text(encoding="utf-8"))
    # Should include a plan id
    assert data.get("plan_id")
    assert data["date"] == target_date.isoformat()
    assert data["weights"] == weight_proposals
    assert data["new_keywords"] == unknown_keywords
