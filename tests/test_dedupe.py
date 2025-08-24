"""Unit tests for the deduplication module."""

from catalyst_bot.dedupe import normalize_title, hash_title, is_near_duplicate


def test_normalize_title_strips_punctuation_and_lowercases() -> None:
    title = "FDA Approval for Biotech Co!"
    normalized = normalize_title(title)
    assert normalized == "fda approval for biotech co"


def test_hash_title_consistent_for_equivalent_titles() -> None:
    a = "FDA Approval for Biotech Co!"
    b = "Fda approval for biotech co"
    assert hash_title(a) == hash_title(b)


def test_is_near_duplicate_detects_similarity() -> None:
    existing = [normalize_title("company announces strategic partnership")]  # baseline
    # Title with similar wording
    new_title = "Company Announces Strategic Partnership"
    assert is_near_duplicate(new_title, existing, threshold=0.8)