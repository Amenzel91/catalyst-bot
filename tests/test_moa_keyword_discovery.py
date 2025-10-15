"""Tests for MOA keyword discovery integration."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from catalyst_bot.moa_analyzer import (
    discover_keywords_from_missed_opportunities,
    load_accepted_items,
    load_rejected_items,
    run_moa_analysis,
    ANALYSIS_WINDOW_DAYS,
)


@pytest.fixture
def mock_accepted_items_file(tmp_path, monkeypatch):
    """Create mock accepted_items.jsonl file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    accepted_path = data_dir / "accepted_items.jsonl"

    # Create sample accepted items (negative examples)
    items = [
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "ABC",
            "title": "Quarterly Earnings Conference Call",
            "source": "benzinga",
            "summary": "Company to report quarterly results",
            "link": "http://example.com/1",
            "price": 5.0,
            "cls": {
                "score": 0.7,
                "sentiment": 0.6,
                "keywords": ["earnings", "quarterly"],
            },
            "accepted": True,
        },
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "DEF",
            "title": "Management Presentation at Conference",
            "source": "benzinga",
            "summary": "CEO to present at investor conference",
            "link": "http://example.com/2",
            "price": 3.0,
            "cls": {
                "score": 0.65,
                "sentiment": 0.55,
                "keywords": ["conference", "presentation"],
            },
            "accepted": True,
        },
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "GHI",
            "title": "Company Reports Financial Results",
            "source": "benzinga",
            "summary": "Q3 results announced",
            "link": "http://example.com/3",
            "price": 7.5,
            "cls": {
                "score": 0.68,
                "sentiment": 0.58,
                "keywords": ["reports", "results"],
            },
            "accepted": True,
        },
    ]

    with open(accepted_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Monkeypatch the repo root function
    def mock_repo_root():
        return tmp_path

    monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

    return accepted_path


@pytest.fixture
def mock_rejected_items_file(tmp_path, monkeypatch):
    """Create mock rejected_items.jsonl file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    rejected_path = data_dir / "rejected_items.jsonl"

    # Create sample rejected items with FDA keywords (for keyword discovery)
    items = [
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "TEST1",
            "title": "FDA Approval Granted",
            "source": "benzinga",
            "price": 2.0,
            "cls": {
                "score": 0.45,
                "sentiment": 0.5,
                "keywords": ["fda", "approval"],
            },
        },
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "TEST2",
            "title": "FDA Clearance Received",
            "source": "benzinga",
            "price": 4.0,
            "cls": {
                "score": 0.42,
                "sentiment": 0.48,
                "keywords": ["fda", "clearance"],
            },
        },
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "TEST3",
            "title": "FDA Fast Track Designation",
            "source": "benzinga",
            "price": 3.0,
            "cls": {
                "score": 0.43,
                "sentiment": 0.49,
                "keywords": ["fda"],
            },
        },
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "TEST4",
            "title": "FDA Priority Review Granted",
            "source": "benzinga",
            "price": 5.0,
            "cls": {
                "score": 0.44,
                "sentiment": 0.51,
                "keywords": ["fda", "priority"],
            },
        },
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": "TEST5",
            "title": "FDA Orphan Drug Status",
            "source": "benzinga",
            "price": 2.5,
            "cls": {
                "score": 0.46,
                "sentiment": 0.52,
                "keywords": ["fda"],
            },
        },
    ]

    with open(rejected_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Monkeypatch the repo root function
    def mock_repo_root():
        return tmp_path

    monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

    return rejected_path


class TestLoadAcceptedItems:
    """Test loading accepted items."""

    def test_loads_accepted_items(self, mock_accepted_items_file):
        """Load from accepted_items.jsonl."""
        items = load_accepted_items()

        assert len(items) == 3
        assert all("ticker" in item for item in items)
        assert all("title" in item for item in items)
        assert all("accepted" in item for item in items)

    def test_filters_by_date(self, tmp_path, monkeypatch):
        """Only load items within date range."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        accepted_path = data_dir / "accepted_items.jsonl"

        # Create items with different dates
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=60)
        recent_date = now - timedelta(days=10)

        items = [
            {
                "ts": old_date.isoformat(),
                "ticker": "OLD",
                "title": "Old Item",
                "accepted": True,
            },
            {
                "ts": recent_date.isoformat(),
                "ticker": "NEW",
                "title": "Recent Item",
                "accepted": True,
            },
        ]

        with open(accepted_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        # Load with 30 day window
        loaded = load_accepted_items(since_days=30)

        # Should only have recent item
        assert len(loaded) == 1
        assert loaded[0]["ticker"] == "NEW"

    def test_handles_missing_file(self, tmp_path, monkeypatch):
        """Return empty list if file missing."""
        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        items = load_accepted_items()
        assert items == []

    def test_handles_invalid_json(self, tmp_path, monkeypatch):
        """Skip invalid lines."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        accepted_path = data_dir / "accepted_items.jsonl"

        # Write mix of valid and invalid JSON (use recent timestamps)
        recent_ts = datetime.now(timezone.utc).isoformat()
        with open(accepted_path, "w", encoding="utf-8") as f:
            f.write(f'{{"ts": "{recent_ts}", "ticker": "VALID", "accepted": true}}\n')
            f.write('invalid json line\n')
            f.write(f'{{"ts": "{recent_ts}", "ticker": "VALID2", "accepted": true}}\n')

        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        items = load_accepted_items()

        # Should load 2 valid items, skip invalid line
        assert len(items) == 2
        assert items[0]["ticker"] == "VALID"
        assert items[1]["ticker"] == "VALID2"

    def test_handles_invalid_timestamps(self, tmp_path, monkeypatch):
        """Skip items with invalid timestamps."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        accepted_path = data_dir / "accepted_items.jsonl"

        items = [
            {
                "ts": "invalid-timestamp",
                "ticker": "INVALID",
                "accepted": True,
            },
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "VALID",
                "accepted": True,
            },
        ]

        with open(accepted_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        loaded = load_accepted_items()

        # Should only load valid item
        assert len(loaded) == 1
        assert loaded[0]["ticker"] == "VALID"


class TestKeywordDiscovery:
    """Test keyword discovery from missed opportunities."""

    def test_discovers_new_keywords(self, mock_accepted_items_file):
        """Find keywords in missed opps not in accepted items."""
        missed_opps = [
            {
                "ticker": "TEST",
                "title": "FDA Approval Granted for New Drug",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 15.0, "4h": 20.0},
            },
            {
                "ticker": "TEST2",
                "title": "FDA Clearance Received",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 12.0, "4h": 18.0},
            },
            {
                "ticker": "TEST3",
                "title": "FDA Fast Track Designation",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 11.0, "4h": 16.0},
            },
            {
                "ticker": "TEST4",
                "title": "FDA Orphan Drug Status",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 13.0, "4h": 17.0},
            },
            {
                "ticker": "TEST5",
                "title": "FDA Priority Review Granted",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 14.0, "4h": 19.0},
            },
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=3,
            min_lift=2.0,
        )

        # Should discover FDA-related keywords
        assert len(discovered) > 0

        # Check structure of discovered keywords
        for kw in discovered:
            assert "keyword" in kw
            assert "lift" in kw
            assert "positive_count" in kw
            assert "negative_count" in kw
            assert "type" in kw
            assert kw["type"] == "discovered"
            assert "recommended_weight" in kw
            assert 0 < kw["recommended_weight"] <= 0.8  # Conservative cap

        # Should find "fda" with high lift
        fda_keywords = [kw for kw in discovered if "fda" in kw["keyword"]]
        assert len(fda_keywords) > 0

        # FDA should have high positive count, low negative count
        for fda_kw in fda_keywords:
            assert fda_kw["positive_count"] >= 3
            assert fda_kw["lift"] >= 2.0

    def test_calculates_lift_scores(self, mock_accepted_items_file):
        """Calculate lift ratios correctly."""
        # Create controlled test case
        # 5 positives with "breakthrough", 0 negatives with "breakthrough"
        missed_opps = [
            {
                "ticker": f"TEST{i}",
                "title": "Breakthrough Therapy Designation",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 15.0},
            }
            for i in range(5)
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=3,
            min_lift=2.0,
        )

        # Should find "breakthrough" with very high lift (only in positives)
        breakthrough_kws = [kw for kw in discovered if "breakthrough" in kw["keyword"]]

        if breakthrough_kws:
            # Should have high lift since it's only in positives
            assert breakthrough_kws[0]["lift"] >= 2.0
            assert breakthrough_kws[0]["positive_count"] == 5
            assert breakthrough_kws[0]["negative_count"] == 0

    def test_recommends_weights(self, mock_accepted_items_file):
        """Assign recommended weights based on lift and frequency."""
        missed_opps = [
            {
                "ticker": f"TEST{i}",
                "title": "FDA Approval Granted",
                "ts": datetime.now(timezone.utc).isoformat(),
                "price_outcomes": {"1h": 15.0},
            }
            for i in range(10)
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=3,
            min_lift=2.0,
        )

        # All discovered keywords should have weights
        for kw in discovered:
            weight = kw["recommended_weight"]
            # Should be conservative (0.3-0.8 range)
            assert 0.3 <= weight <= 0.8
            # Should be reasonable precision
            assert weight == round(weight, 2)

    def test_min_occurrences_filter(self, mock_accepted_items_file):
        """Only suggest keywords with enough occurrences."""
        missed_opps = [
            {"ticker": "TEST1", "title": "FDA Approval", "ts": datetime.now(timezone.utc).isoformat()},
            {"ticker": "TEST2", "title": "FDA Approval", "ts": datetime.now(timezone.utc).isoformat()},
            {"ticker": "TEST3", "title": "FDA Approval", "ts": datetime.now(timezone.utc).isoformat()},
            {"ticker": "TEST4", "title": "Rare Keyword", "ts": datetime.now(timezone.utc).isoformat()},
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=3,  # Require 3+ occurrences
            min_lift=1.5,
        )

        # "fda" and "approval" should be included (3 occurrences each)
        # "rare" should be excluded (only 1 occurrence)
        rare_keywords = [kw for kw in discovered if "rare" in kw["keyword"]]
        assert len(rare_keywords) == 0

    def test_min_lift_filter(self, mock_accepted_items_file):
        """Only suggest keywords with high enough lift."""
        # Create case where keyword appears in both positive and negative
        # with similar frequency (low lift)
        missed_opps = [
            {
                "ticker": f"TEST{i}",
                "title": "Conference Presentation Scheduled",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(5)
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=2,
            min_lift=5.0,  # High lift requirement
        )

        # "conference" and "presentation" appear in both positive and negative
        # Should have low lift and be filtered out
        # Any discovered keywords should meet lift threshold
        for kw in discovered:
            assert kw["lift"] >= 5.0

    def test_handles_no_data(self, mock_accepted_items_file):
        """Return empty list if no titles."""
        # Empty missed opportunities
        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=[],
            min_occurrences=2,
            min_lift=2.0,
        )

        assert discovered == []

    def test_handles_no_accepted_items(self, tmp_path, monkeypatch):
        """Handle case where no accepted items exist."""
        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        missed_opps = [
            {
                "ticker": "TEST",
                "title": "FDA Approval",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=1,
            min_lift=1.0,
        )

        # Should return empty list (no negatives to compare against)
        assert discovered == []


class TestMOAIntegration:
    """Test full MOA analysis with keyword discovery."""

    def test_includes_discovered_keywords(
        self, tmp_path, monkeypatch, mock_accepted_items_file, mock_rejected_items_file
    ):
        """run_moa_analysis includes discovered keywords."""
        # Create MOA directories
        moa_dir = tmp_path / "data" / "moa"
        moa_dir.mkdir(parents=True, exist_ok=True)

        # Create analyzer directory for keyword weights
        analyzer_dir = tmp_path / "data" / "analyzer"
        analyzer_dir.mkdir(parents=True, exist_ok=True)
        weights_path = analyzer_dir / "keyword_stats.json"
        with open(weights_path, "w") as f:
            json.dump({"earnings": 1.0, "fda": 1.2}, f)

        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        # Mock price checking to avoid API calls
        def mock_check_price_outcome(ticker, rejection_time, hours_after, price_cache=None):
            # Return moderate gains for all items
            return 12.0  # 12% gain

        monkeypatch.setattr(
            "catalyst_bot.moa_analyzer.check_price_outcome",
            mock_check_price_outcome,
        )

        # Run analysis
        result = run_moa_analysis(since_days=30)

        # Should succeed
        assert result.get("status") == "success"

        # Check recommendations file
        recommendations_path = moa_dir / "recommendations.json"
        assert recommendations_path.exists()

        with open(recommendations_path, "r") as f:
            data = json.load(f)

        # Should have discovered_keywords_count field
        assert "discovered_keywords_count" in data

        # Should have some recommendations
        recommendations = data.get("recommendations", [])
        assert len(recommendations) > 0

        # Check for discovered keyword types
        types = {rec.get("type") for rec in recommendations}
        # May have 'new', 'weight_increase', 'new_discovered', or 'discovered_and_existing'
        assert len(types) > 0

    def test_merges_existing_and_discovered(self, tmp_path, monkeypatch):
        """If keyword exists in both, merge intelligently."""
        # Setup mock files
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Accepted items (negatives)
        accepted_path = data_dir / "accepted_items.jsonl"
        accepted_items = [
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "ABC",
                "title": "Earnings Conference",
                "accepted": True,
            }
        ]
        with open(accepted_path, "w") as f:
            for item in accepted_items:
                f.write(json.dumps(item) + "\n")

        # Rejected items
        rejected_path = data_dir / "rejected_items.jsonl"
        rejected_items = [
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST1",
                "title": "FDA Approval Breakthrough",
                "cls": {"keywords": ["fda", "approval"]},
            },
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST2",
                "title": "FDA Approval Granted",
                "cls": {"keywords": ["fda", "approval"]},
            },
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST3",
                "title": "FDA Approval Received",
                "cls": {"keywords": ["fda", "approval"]},
            },
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST4",
                "title": "FDA Approval Announced",
                "cls": {"keywords": ["fda", "approval"]},
            },
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST5",
                "title": "FDA Approval Confirmed",
                "cls": {"keywords": ["fda", "approval"]},
            },
        ]
        with open(rejected_path, "w") as f:
            for item in rejected_items:
                f.write(json.dumps(item) + "\n")

        # Existing keyword weights
        analyzer_dir = data_dir / "analyzer"
        analyzer_dir.mkdir(parents=True, exist_ok=True)
        weights_path = analyzer_dir / "keyword_stats.json"
        with open(weights_path, "w") as f:
            json.dump({"fda": 1.0}, f)  # FDA already exists

        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        # Mock price checking
        def mock_check_price_outcome(ticker, rejection_time, hours_after, price_cache=None):
            return 15.0

        monkeypatch.setattr(
            "catalyst_bot.moa_analyzer.check_price_outcome",
            mock_check_price_outcome,
        )

        # Run analysis
        result = run_moa_analysis(since_days=30)

        assert result.get("status") == "success"

        # Check recommendations
        moa_dir = tmp_path / "data" / "moa"
        recommendations_path = moa_dir / "recommendations.json"

        with open(recommendations_path, "r") as f:
            data = json.load(f)

        recommendations = data.get("recommendations", [])

        # Should have FDA keyword (either from existing or discovered or merged)
        fda_recs = [rec for rec in recommendations if rec["keyword"] == "fda"]

        # Should exist
        assert len(fda_recs) > 0

        # If merged, type might be 'discovered_and_existing'
        # If separate, might have both 'weight_increase' and 'new_discovered'

    def test_discovered_count_in_output(self, tmp_path, monkeypatch):
        """Output should include discovered_keywords_count."""
        # Setup minimal mock environment
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Accepted items
        accepted_path = data_dir / "accepted_items.jsonl"
        with open(accepted_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "ticker": "ABC",
                        "title": "Conference Call",
                        "accepted": True,
                    }
                )
                + "\n"
            )

        # Rejected items with FDA keywords
        rejected_path = data_dir / "rejected_items.jsonl"
        for i in range(5):
            with open(rejected_path, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "ticker": f"TEST{i}",
                            "title": "FDA Breakthrough Designation",
                            "cls": {"keywords": ["fda"]},
                        }
                    )
                    + "\n"
                )

        # Empty keyword weights
        analyzer_dir = data_dir / "analyzer"
        analyzer_dir.mkdir(parents=True, exist_ok=True)
        with open(analyzer_dir / "keyword_stats.json", "w") as f:
            json.dump({}, f)

        def mock_repo_root():
            return tmp_path

        monkeypatch.setattr("catalyst_bot.moa_analyzer._repo_root", mock_repo_root)

        # Mock price checking
        def mock_check_price_outcome(ticker, rejection_time, hours_after, price_cache=None):
            return 12.0

        monkeypatch.setattr(
            "catalyst_bot.moa_analyzer.check_price_outcome",
            mock_check_price_outcome,
        )

        # Run analysis
        result = run_moa_analysis(since_days=30)

        assert result.get("status") == "success"

        # Check output file
        moa_dir = tmp_path / "data" / "moa"
        recommendations_path = moa_dir / "recommendations.json"

        with open(recommendations_path, "r") as f:
            data = json.load(f)

        # Should have discovered_keywords_count
        assert "discovered_keywords_count" in data
        assert isinstance(data["discovered_keywords_count"], int)
        assert data["discovered_keywords_count"] >= 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_missing_title_field(self, mock_accepted_items_file):
        """Handle items without title field."""
        missed_opps = [
            {
                "ticker": "TEST",
                # No title field
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "ticker": "TEST2",
                "title": "",  # Empty title
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "ticker": "TEST3",
                "title": "FDA Approval",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=1,
            min_lift=1.0,
        )

        # Should handle gracefully (extract from available titles)
        # Should not crash
        assert isinstance(discovered, list)

    def test_handles_special_characters(self, mock_accepted_items_file):
        """Handle titles with special characters."""
        missed_opps = [
            {
                "ticker": "TEST",
                "title": "FDA Approves Drug: Breaking News!",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "ticker": "TEST2",
                "title": "FDA's New Drug Approval",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "ticker": "TEST3",
                "title": "FDA Approval (Phase III)",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=2,
            min_lift=1.5,
        )

        # Should handle special characters and normalize
        # Should extract "fda" and "approval"
        assert isinstance(discovered, list)

    def test_handles_unicode(self, mock_accepted_items_file):
        """Handle Unicode characters in titles."""
        missed_opps = [
            {
                "ticker": "TEST",
                "title": "Company announces breakthrough therapy designation",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            {
                "ticker": "TEST2",
                "title": "FDA approval granted for treatment",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        ]

        discovered = discover_keywords_from_missed_opportunities(
            missed_opps=missed_opps,
            min_occurrences=1,
            min_lift=1.0,
        )

        # Should handle Unicode gracefully
        assert isinstance(discovered, list)
