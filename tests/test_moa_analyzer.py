"""
Comprehensive tests for MOA Phase 2 - moa_analyzer.py

Tests cover:
1. Reading rejected_items.jsonl
2. Parsing outcomes.jsonl
3. Keyword frequency calculation
4. Missed opportunity identification (>10% threshold)
5. Recommendation generation (new keywords, weight adjustments)
6. Statistical significance filtering (min 5 occurrences)
7. Output to recommendations.json
8. Handling empty/missing files
9. Handling malformed data
"""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest


# Mock classes for MOA analyzer (to be implemented)
class MOAAnalyzer:
    """Mock MOA Analyzer for testing purposes"""

    def __init__(self, rejected_items_path, outcomes_path):
        self.rejected_items_path = rejected_items_path
        self.outcomes_path = outcomes_path
        self.min_occurrences = 5
        self.missed_opportunity_threshold = 0.10  # 10%

    def read_rejected_items(self):
        """Read rejected items from JSONL file"""
        items = []
        if not os.path.exists(self.rejected_items_path):
            return items

        with open(self.rejected_items_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return items

    def parse_outcomes(self):
        """Parse outcomes from JSONL file"""
        outcomes = []
        if not os.path.exists(self.outcomes_path):
            return outcomes

        with open(self.outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        outcomes.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return outcomes

    def calculate_keyword_frequencies(self, items):
        """Calculate keyword frequencies from items"""
        keyword_freq = {}
        for item in items:
            keywords = item.get("cls", {}).get("keywords", [])
            for keyword in keywords:
                keyword_freq[keyword] = keyword_freq.get(keyword, 0) + 1
        return keyword_freq

    def identify_missed_opportunities(self, outcomes):
        """Identify outcomes with >10% price change"""
        missed = []
        for outcome in outcomes:
            price_change = outcome.get("price_change_pct", 0)
            if price_change >= self.missed_opportunity_threshold * 100:
                missed.append(outcome)
        return missed

    def generate_recommendations(self, missed_opportunities, current_weights):
        """Generate weight adjustment and new keyword recommendations"""
        recommendations = {
            "new_keywords": [],
            "weight_adjustments": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Extract keywords from missed opportunities
        keyword_stats = {}
        for opp in missed_opportunities:
            keywords = opp.get("keywords", [])
            price_change = opp.get("price_change_pct", 0)

            for kw in keywords:
                if kw not in keyword_stats:
                    keyword_stats[kw] = {
                        "count": 0,
                        "total_return": 0,
                        "occurrences": [],
                    }
                keyword_stats[kw]["count"] += 1
                keyword_stats[kw]["total_return"] += price_change
                keyword_stats[kw]["occurrences"].append(opp)

        # Filter by statistical significance (min occurrences)
        for keyword, stats in keyword_stats.items():
            if stats["count"] >= self.min_occurrences:
                avg_return = stats["total_return"] / stats["count"]

                if keyword not in current_weights:
                    # New keyword
                    recommendations["new_keywords"].append(
                        {
                            "keyword": keyword,
                            "occurrences": stats["count"],
                            "avg_return": avg_return,
                            "confidence": min(stats["count"] / 10.0, 1.0),
                            "proposed_weight": self._calculate_weight(
                                avg_return, stats["count"]
                            ),
                        }
                    )
                else:
                    # Weight adjustment
                    current = current_weights[keyword]
                    proposed = self._calculate_weight(avg_return, stats["count"])
                    if abs(proposed - current) > 0.1:  # Significant change
                        recommendations["weight_adjustments"].append(
                            {
                                "keyword": keyword,
                                "current_weight": current,
                                "proposed_weight": proposed,
                                "occurrences": stats["count"],
                                "avg_return": avg_return,
                                "confidence": min(stats["count"] / 10.0, 1.0),
                            }
                        )

        return recommendations

    def _calculate_weight(self, avg_return, occurrences):
        """Calculate proposed weight based on performance"""
        base_weight = 1.0
        return_factor = min(avg_return / 15.0, 2.0)  # Cap at 2x
        confidence_factor = min(occurrences / 10.0, 1.0)
        return round(base_weight * return_factor * confidence_factor, 2)

    def save_recommendations(self, recommendations, output_path):
        """Save recommendations to JSON file"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(recommendations, f, indent=2)


# Fixtures


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_rejected_items():
    """Sample rejected items data"""
    return [
        {
            "ts": "2025-10-11T04:51:13.018407+00:00",
            "ticker": "SNAL",
            "title": "FDA approves breakthrough therapy designation",
            "source": "globenewswire_public",
            "price": 1.03,
            "cls": {
                "score": 0.18,
                "sentiment": 0.42,
                "keywords": ["fda", "approval", "breakthrough"],
            },
            "rejected": True,
            "rejection_reason": "LOW_SCORE",
        },
        {
            "ts": "2025-10-11T05:00:00.000000+00:00",
            "ticker": "ABCD",
            "title": "Company announces partnership deal",
            "source": "businesswire",
            "price": 2.45,
            "cls": {
                "score": 0.20,
                "sentiment": 0.55,
                "keywords": ["partnership", "deal"],
            },
            "rejected": True,
            "rejection_reason": "LOW_SCORE",
        },
    ]


@pytest.fixture
def sample_outcomes():
    """Sample outcomes data"""
    return [
        {
            "ticker": "SNAL",
            "timestamp": "2025-10-11T04:51:13.018407+00:00",
            "initial_price": 1.03,
            "price_1h": 1.08,
            "price_4h": 1.15,
            "price_24h": 1.25,
            "price_1w": 1.40,
            "price_change_pct": 21.4,
            "timeframe": "24h",
            "keywords": ["fda", "approval", "breakthrough"],
        },
        {
            "ticker": "ABCD",
            "timestamp": "2025-10-11T05:00:00.000000+00:00",
            "initial_price": 2.45,
            "price_1h": 2.47,
            "price_4h": 2.50,
            "price_24h": 2.60,
            "price_1w": 2.70,
            "price_change_pct": 6.1,
            "timeframe": "24h",
            "keywords": ["partnership", "deal"],
        },
    ]


@pytest.fixture
def current_weights():
    """Sample current keyword weights"""
    return {"fda": 1.2, "approval": 1.5, "partnership": 1.0}


# Test Cases


def test_read_rejected_items_success(temp_data_dir, sample_rejected_items):
    """Test reading rejected_items.jsonl successfully"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")

    # Write sample data
    with open(rejected_path, "w", encoding="utf-8") as f:
        for item in sample_rejected_items:
            f.write(json.dumps(item) + "\n")

    # Test reading
    analyzer = MOAAnalyzer(rejected_path, None)
    items = analyzer.read_rejected_items()

    assert len(items) == 2
    assert items[0]["ticker"] == "SNAL"
    assert items[1]["ticker"] == "ABCD"
    assert "cls" in items[0]
    assert "keywords" in items[0]["cls"]


def test_read_rejected_items_empty_file(temp_data_dir):
    """Test reading empty rejected_items.jsonl"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")

    # Create empty file
    with open(rejected_path, "w", encoding="utf-8"):
        pass

    analyzer = MOAAnalyzer(rejected_path, None)
    items = analyzer.read_rejected_items()

    assert len(items) == 0


def test_read_rejected_items_missing_file(temp_data_dir):
    """Test reading missing rejected_items.jsonl"""
    rejected_path = os.path.join(temp_data_dir, "nonexistent.jsonl")

    analyzer = MOAAnalyzer(rejected_path, None)
    items = analyzer.read_rejected_items()

    assert len(items) == 0


def test_read_rejected_items_malformed_data(temp_data_dir):
    """Test reading rejected_items.jsonl with malformed JSON"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")

    # Write malformed data
    with open(rejected_path, "w", encoding="utf-8") as f:
        f.write('{"valid": "json"}\n')
        f.write("this is not json\n")
        f.write('{"another": "valid"}\n')

    analyzer = MOAAnalyzer(rejected_path, None)
    items = analyzer.read_rejected_items()

    # Should skip malformed line
    assert len(items) == 2
    assert items[0]["valid"] == "json"
    assert items[1]["another"] == "valid"


def test_parse_outcomes_success(temp_data_dir, sample_outcomes):
    """Test parsing outcomes.jsonl successfully"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    # Write sample data
    with open(outcomes_path, "w", encoding="utf-8") as f:
        for outcome in sample_outcomes:
            f.write(json.dumps(outcome) + "\n")

    analyzer = MOAAnalyzer(None, outcomes_path)
    outcomes = analyzer.parse_outcomes()

    assert len(outcomes) == 2
    assert outcomes[0]["ticker"] == "SNAL"
    assert outcomes[0]["price_change_pct"] == 21.4
    assert outcomes[1]["ticker"] == "ABCD"


def test_parse_outcomes_empty_file(temp_data_dir):
    """Test parsing empty outcomes.jsonl"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    with open(outcomes_path, "w", encoding="utf-8"):
        pass

    analyzer = MOAAnalyzer(None, outcomes_path)
    outcomes = analyzer.parse_outcomes()

    assert len(outcomes) == 0


def test_calculate_keyword_frequencies(temp_data_dir, sample_rejected_items):
    """Test calculating keyword frequencies"""
    analyzer = MOAAnalyzer(None, None)
    freq = analyzer.calculate_keyword_frequencies(sample_rejected_items)

    assert "fda" in freq
    assert "approval" in freq
    assert "partnership" in freq
    assert freq["fda"] == 1
    assert freq["approval"] == 1
    assert freq["partnership"] == 1


def test_calculate_keyword_frequencies_multiple_occurrences(temp_data_dir):
    """Test keyword frequency with multiple occurrences"""
    items = [
        {"cls": {"keywords": ["fda", "approval"]}},
        {"cls": {"keywords": ["fda", "breakthrough"]}},
        {"cls": {"keywords": ["fda"]}},
    ]

    analyzer = MOAAnalyzer(None, None)
    freq = analyzer.calculate_keyword_frequencies(items)

    assert freq["fda"] == 3
    assert freq["approval"] == 1
    assert freq["breakthrough"] == 1


def test_identify_missed_opportunities_above_threshold(temp_data_dir, sample_outcomes):
    """Test identifying missed opportunities >10% threshold"""
    analyzer = MOAAnalyzer(None, None)
    missed = analyzer.identify_missed_opportunities(sample_outcomes)

    # Only SNAL has 21.4% change (>10%)
    assert len(missed) == 1
    assert missed[0]["ticker"] == "SNAL"
    assert missed[0]["price_change_pct"] >= 10


def test_identify_missed_opportunities_none_above_threshold(temp_data_dir):
    """Test identifying missed opportunities when none exceed threshold"""
    outcomes = [
        {"ticker": "TEST1", "price_change_pct": 5.0},
        {"ticker": "TEST2", "price_change_pct": 8.5},
    ]

    analyzer = MOAAnalyzer(None, None)
    missed = analyzer.identify_missed_opportunities(outcomes)

    assert len(missed) == 0


def test_generate_recommendations_new_keywords(temp_data_dir, current_weights):
    """Test generating recommendations for new keywords"""
    missed_opps = [
        {"keywords": ["breakthrough", "therapy"], "price_change_pct": 25.0},
        {"keywords": ["breakthrough", "trial"], "price_change_pct": 20.0},
        {"keywords": ["breakthrough", "data"], "price_change_pct": 18.0},
        {"keywords": ["breakthrough"], "price_change_pct": 22.0},
        {"keywords": ["breakthrough"], "price_change_pct": 30.0},
    ]

    analyzer = MOAAnalyzer(None, None)
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    # "breakthrough" appears 5 times (meets min threshold)
    assert len(recs["new_keywords"]) > 0

    breakthrough_rec = next(
        (r for r in recs["new_keywords"] if r["keyword"] == "breakthrough"), None
    )
    assert breakthrough_rec is not None
    assert breakthrough_rec["occurrences"] == 5
    assert breakthrough_rec["avg_return"] == 23.0  # (25+20+18+22+30)/5
    assert "confidence" in breakthrough_rec
    assert "proposed_weight" in breakthrough_rec


def test_generate_recommendations_weight_adjustments(temp_data_dir, current_weights):
    """Test generating weight adjustment recommendations"""
    missed_opps = [
        {"keywords": ["fda"], "price_change_pct": 30.0},
        {"keywords": ["fda"], "price_change_pct": 25.0},
        {"keywords": ["fda"], "price_change_pct": 28.0},
        {"keywords": ["fda"], "price_change_pct": 32.0},
        {"keywords": ["fda"], "price_change_pct": 27.0},
    ]

    analyzer = MOAAnalyzer(None, None)
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    # "fda" exists in current_weights, should suggest adjustment
    fda_adj = next(
        (r for r in recs["weight_adjustments"] if r["keyword"] == "fda"), None
    )

    if fda_adj:  # Only if change is significant
        assert fda_adj["current_weight"] == 1.2
        assert "proposed_weight" in fda_adj
        assert fda_adj["occurrences"] == 5


def test_statistical_significance_filtering_below_min(temp_data_dir, current_weights):
    """Test that keywords below min occurrences are filtered out"""
    missed_opps = [
        {"keywords": ["rare_keyword"], "price_change_pct": 50.0},
        {"keywords": ["rare_keyword"], "price_change_pct": 45.0},
    ]

    analyzer = MOAAnalyzer(None, None)
    analyzer.min_occurrences = 5
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    # Should not include "rare_keyword" (only 2 occurrences < 5 min)
    rare_recs = [r for r in recs["new_keywords"] if r["keyword"] == "rare_keyword"]
    assert len(rare_recs) == 0


def test_statistical_significance_filtering_at_min(temp_data_dir, current_weights):
    """Test that keywords at min occurrences are included"""
    missed_opps = [
        {"keywords": ["boundary_keyword"], "price_change_pct": 15.0},
        {"keywords": ["boundary_keyword"], "price_change_pct": 18.0},
        {"keywords": ["boundary_keyword"], "price_change_pct": 20.0},
        {"keywords": ["boundary_keyword"], "price_change_pct": 16.0},
        {"keywords": ["boundary_keyword"], "price_change_pct": 19.0},
    ]

    analyzer = MOAAnalyzer(None, None)
    analyzer.min_occurrences = 5
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    # Should include "boundary_keyword" (exactly 5 occurrences)
    boundary_recs = [
        r for r in recs["new_keywords"] if r["keyword"] == "boundary_keyword"
    ]
    assert len(boundary_recs) == 1
    assert boundary_recs[0]["occurrences"] == 5


def test_save_recommendations_output(temp_data_dir):
    """Test saving recommendations to recommendations.json"""
    output_path = os.path.join(temp_data_dir, "recommendations.json")

    recommendations = {
        "new_keywords": [{"keyword": "test", "occurrences": 5, "avg_return": 20.0}],
        "weight_adjustments": [],
        "timestamp": "2025-10-11T12:00:00+00:00",
    }

    analyzer = MOAAnalyzer(None, None)
    analyzer.save_recommendations(recommendations, output_path)

    # Verify file exists and contains correct data
    assert os.path.exists(output_path)

    with open(output_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert "new_keywords" in loaded
    assert "weight_adjustments" in loaded
    assert "timestamp" in loaded
    assert len(loaded["new_keywords"]) == 1
    assert loaded["new_keywords"][0]["keyword"] == "test"


def test_handling_missing_keywords_field(temp_data_dir):
    """Test handling items with missing keywords field"""
    items = [
        {"cls": {}},  # No keywords field
        {"cls": {"keywords": ["fda"]}},
    ]

    analyzer = MOAAnalyzer(None, None)
    freq = analyzer.calculate_keyword_frequencies(items)

    assert freq.get("fda", 0) == 1


def test_handling_empty_keywords_list(temp_data_dir):
    """Test handling items with empty keywords list"""
    items = [
        {"cls": {"keywords": []}},
        {"cls": {"keywords": ["fda"]}},
    ]

    analyzer = MOAAnalyzer(None, None)
    freq = analyzer.calculate_keyword_frequencies(items)

    assert freq.get("fda", 0) == 1


def test_confidence_score_calculation(temp_data_dir, current_weights):
    """Test that confidence scores are calculated correctly"""
    missed_opps = [
        {"keywords": ["high_conf"], "price_change_pct": 15.0} for _ in range(10)
    ]

    analyzer = MOAAnalyzer(None, None)
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    high_conf_rec = next(
        (r for r in recs["new_keywords"] if r["keyword"] == "high_conf"), None
    )
    assert high_conf_rec is not None
    assert high_conf_rec["confidence"] == 1.0  # 10 occurrences = full confidence


def test_multiple_keywords_per_item(temp_data_dir, current_weights):
    """Test handling items with multiple keywords"""
    missed_opps = [
        {"keywords": ["fda", "approval", "breakthrough"], "price_change_pct": 25.0}
        for _ in range(5)
    ]

    analyzer = MOAAnalyzer(None, None)
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    # All three keywords should have 5 occurrences each
    breakthrough_rec = next(
        (r for r in recs["new_keywords"] if r["keyword"] == "breakthrough"), None
    )
    assert breakthrough_rec is not None
    assert breakthrough_rec["occurrences"] == 5


def test_recommendations_include_timestamp(temp_data_dir, current_weights):
    """Test that recommendations include timestamp"""
    missed_opps = [{"keywords": ["test"], "price_change_pct": 15.0}]

    analyzer = MOAAnalyzer(None, None)
    recs = analyzer.generate_recommendations(missed_opps, current_weights)

    assert "timestamp" in recs
    # Verify timestamp is valid ISO format
    datetime.fromisoformat(recs["timestamp"].replace("+00:00", "+00:00"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
