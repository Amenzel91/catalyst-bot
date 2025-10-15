"""Tests for keyword_miner.py text mining module."""

import pytest
from catalyst_bot.keyword_miner import (
    extract_ngrams,
    normalize_text,
    mine_keyword_candidates,
    mine_discriminative_keywords,
    calculate_phrase_score,
    filter_subsumed_phrases,
    get_phrase_contexts,
    is_valid_ngram,
    extract_all_ngrams,
    STOP_WORDS,
    PRESERVE_TERMS,
    NON_CATALYST_PHRASES,
)


class TestNormalization:
    """Test text normalization."""

    def test_normalize_preserves_abbreviations(self):
        """FDA, SEC, 8-K should be preserved (but lowercased)."""
        text = "FDA Approves New Drug for SEC Filing via 8-K"
        normalized = normalize_text(text)

        # Important terms are preserved but lowercased for consistency
        assert "fda" in normalized
        assert "sec" in normalized
        assert "8-k" in normalized  # Preserved terms kept intact with lowercase

    def test_normalize_lowercase(self):
        """Regular text should be lowercased."""
        text = "Company Announces Major Partnership Deal"
        normalized = normalize_text(text)

        assert normalized == normalized.lower()
        assert "company" in normalized
        assert "announces" in normalized

    def test_normalize_removes_possessives(self):
        """company's -> company"""
        text = "Company's new product"
        normalized = normalize_text(text)

        assert "company" in normalized
        assert "'s" not in normalized

    def test_normalize_handles_punctuation(self):
        """Smart punctuation handling."""
        text = "Breaking: FDA approves drug!"
        normalized = normalize_text(text)

        # Punctuation removed
        assert ":" not in normalized
        assert "!" not in normalized
        # Words preserved
        assert "breaking" in normalized
        assert "fda" in normalized

    def test_normalize_empty_string(self):
        """Handle empty strings gracefully."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_normalize_whitespace(self):
        """Normalize excessive whitespace."""
        text = "Multiple   spaces    here"
        normalized = normalize_text(text)

        assert "  " not in normalized
        assert normalized == "multiple spaces here"


class TestNgramExtraction:
    """Test n-gram extraction."""

    def test_extract_unigrams(self):
        """Single word extraction."""
        text = "FDA approves drug"
        unigrams = extract_ngrams(text, 1)

        assert "fda" in unigrams
        assert "approves" in unigrams
        assert "drug" in unigrams

    def test_extract_bigrams(self):
        """Two-word phrase extraction."""
        text = "FDA approves new drug"
        bigrams = extract_ngrams(text, 2)

        assert "fda approves" in bigrams
        assert "approves new" in bigrams
        assert "new drug" in bigrams

    def test_extract_trigrams(self):
        """Three-word phrase extraction."""
        text = "FDA approves new drug"
        trigrams = extract_ngrams(text, 3)

        assert "fda approves new" in trigrams
        assert "approves new drug" in trigrams

    def test_empty_text(self):
        """Handle empty strings."""
        assert extract_ngrams("", 1) == []
        assert extract_ngrams("", 2) == []
        assert extract_ngrams(None, 1) == []

    def test_invalid_n(self):
        """Handle invalid n values."""
        assert extract_ngrams("test", 0) == []
        assert extract_ngrams("test", -1) == []

    def test_text_shorter_than_n(self):
        """Handle text shorter than n-gram size."""
        text = "FDA"
        bigrams = extract_ngrams(text, 2)

        assert bigrams == []

    def test_stop_word_filtering(self):
        """Stop words should be filtered in unigrams."""
        text = "the company announces new drug"
        unigrams = extract_ngrams(text, 1)

        # Stop words filtered
        assert "the" not in unigrams
        assert "company" not in unigrams  # "company" is in STOP_WORDS
        # Content words kept
        assert "drug" in unigrams


class TestIsValidNgram:
    """Test n-gram validation."""

    def test_valid_unigram(self):
        """Valid single word."""
        assert is_valid_ngram("fda", ["fda"]) is True
        assert is_valid_ngram("approval", ["approval"]) is True

    def test_invalid_unigram_stop_word(self):
        """Stop words should be filtered."""
        assert is_valid_ngram("the", ["the"]) is False
        assert is_valid_ngram("company", ["company"]) is False

    def test_invalid_unigram_numeric(self):
        """Purely numeric tokens should be filtered."""
        assert is_valid_ngram("123", ["123"]) is False
        assert is_valid_ngram("2024", ["2024"]) is False

    def test_valid_bigram(self):
        """Valid two-word phrase."""
        assert is_valid_ngram("fda approval", ["fda", "approval"]) is True
        assert is_valid_ngram("new drug", ["new", "drug"]) is True

    def test_invalid_bigram_all_stop_words(self):
        """All stop words should be filtered."""
        assert is_valid_ngram("the company", ["the", "company"]) is False

    def test_invalid_bigram_starts_with_stop_word(self):
        """Phrases starting with stop words should be filtered."""
        assert is_valid_ngram("the approval", ["the", "approval"]) is False

    def test_invalid_bigram_ends_with_stop_word(self):
        """Phrases ending with stop words should be filtered."""
        assert is_valid_ngram("approval the", ["approval", "the"]) is False

    def test_non_catalyst_phrase(self):
        """Non-catalyst phrases should be filtered."""
        assert is_valid_ngram("press release", ["press", "release"]) is False
        assert is_valid_ngram("yahoo finance", ["yahoo", "finance"]) is False


class TestExtractAllNgrams:
    """Test extraction of all n-grams up to max size."""

    def test_extract_all_ngrams_default(self):
        """Extract 1-4 grams by default."""
        text = "FDA approves new drug treatment"
        all_ngrams = extract_all_ngrams(text)

        # Should have unigrams
        assert "fda" in all_ngrams
        assert "drug" in all_ngrams

        # Should have bigrams
        assert "fda approves" in all_ngrams
        assert "new drug" in all_ngrams

        # Should have trigrams
        assert "fda approves new" in all_ngrams

    def test_extract_all_ngrams_max_n(self):
        """Respect max_n parameter."""
        text = "FDA approves drug"
        ngrams_2 = extract_all_ngrams(text, max_n=2)

        # Should have unigrams and bigrams
        assert "fda" in ngrams_2
        assert "fda approves" in ngrams_2

        # Should not have trigrams
        assert "fda approves drug" not in ngrams_2


class TestKeywordMining:
    """Test keyword candidate mining."""

    def test_mine_basic_keywords(self):
        """Extract keywords from simple titles."""
        titles = [
            "FDA Approves New Drug",
            "FDA Approves Cancer Treatment",
            "FDA Grants Priority Review",
            "Company Reports Earnings",
            "Company Reports Earnings",
            "Company Reports Earnings",
        ]

        keywords = mine_keyword_candidates(titles, min_occurrences=2)

        # "fda" should appear (3 times)
        assert "fda" in keywords
        assert keywords["fda"] == 3

        # "approves" should appear (2 times)
        assert "approves" in keywords
        assert keywords["approves"] == 2

    def test_min_occurrences_filter(self):
        """Only return keywords with min occurrences."""
        titles = [
            "FDA Approves Drug",
            "FDA Approves Drug",
            "FDA Approves Drug",
            "SEC Files Report",  # Only once
        ]

        keywords = mine_keyword_candidates(titles, min_occurrences=2)

        # "fda" appears 3 times - should be included
        assert "fda" in keywords

        # "sec" appears 1 time - should be filtered
        assert "sec" not in keywords

    def test_stop_word_filtering(self):
        """Stop words should be filtered."""
        titles = [
            "The Company Announces Deal",
            "The Company Announces Deal",
            "The Company Announces Deal",
        ]

        keywords = mine_keyword_candidates(titles, min_occurrences=2)

        # Stop words filtered
        assert "the" not in keywords
        assert "company" not in keywords

    def test_phrase_preservation(self):
        """Multi-word phrases should be extracted."""
        titles = [
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Approval Granted",
        ]

        keywords = mine_keyword_candidates(titles, min_occurrences=3)

        # Multi-word phrase should be extracted
        assert "fda approval" in keywords
        assert keywords["fda approval"] == 5

    def test_empty_titles(self):
        """Handle empty title list."""
        keywords = mine_keyword_candidates([])
        assert keywords == {}

    def test_max_ngram_size(self):
        """Respect max_ngram_size parameter."""
        titles = [
            "FDA Approves New Cancer Drug Treatment",
            "FDA Approves New Cancer Drug Treatment",
            "FDA Approves New Cancer Drug Treatment",
            "FDA Approves New Cancer Drug Treatment",
            "FDA Approves New Cancer Drug Treatment",
        ]

        keywords_2 = mine_keyword_candidates(titles, min_occurrences=3, max_ngram_size=2)
        keywords_4 = mine_keyword_candidates(titles, min_occurrences=3, max_ngram_size=4)

        # Both should have bigrams
        assert "fda approves" in keywords_2
        assert "fda approves" in keywords_4

        # Only keywords_4 should have 4-grams
        assert "fda approves new cancer" in keywords_4
        assert "fda approves new cancer" not in keywords_2


class TestDiscriminativeKeywords:
    """Test discriminative keyword mining."""

    def test_finds_discriminative_phrases(self):
        """Find phrases that appear more in positives."""
        positive = [
            "FDA Approval Granted",
            "FDA Clearance Received",
            "FDA Approval Granted",
            "FDA Clearance Received",
            "FDA Approval Granted",
        ]
        negative = [
            "Quarterly Earnings Call",
            "Conference Presentation",
            "Quarterly Earnings Call",
            "Conference Presentation",
            "Quarterly Earnings Call",
        ]

        discriminative = mine_discriminative_keywords(
            positive, negative, min_occurrences=2, min_lift=1.5
        )

        # Should find "fda" with high lift
        fda_entries = [entry for entry in discriminative if entry[0] == "fda"]
        assert len(fda_entries) > 0

        phrase, lift, pos_count, neg_count = fda_entries[0]
        assert lift > 1.5  # High lift ratio
        assert pos_count >= 2
        assert neg_count == 0  # "fda" doesn't appear in negatives

    def test_lift_calculation(self):
        """Lift ratio should be calculated correctly."""
        # Simple case: phrase appears in 50% of positives, 10% of negatives
        # Lift = 0.5 / 0.1 = 5.0
        positive = ["test keyword"] * 5 + ["other"] * 5  # 10 total, 5 with keyword
        negative = ["test keyword"] * 1 + ["other"] * 9  # 10 total, 1 with keyword

        discriminative = mine_discriminative_keywords(
            positive, negative, min_occurrences=1, min_lift=2.0
        )

        test_entries = [entry for entry in discriminative if entry[0] == "test"]
        assert len(test_entries) > 0

        phrase, lift, pos_count, neg_count = test_entries[0]
        # pos_rate = 5/10 = 0.5, neg_rate = 1/10 = 0.1, lift = 5.0
        assert lift == pytest.approx(5.0, rel=0.1)

    def test_min_lift_filter(self):
        """Only return keywords above min_lift threshold."""
        positive = ["test"] * 6 + ["other"] * 4  # 60% positive rate
        negative = ["test"] * 4 + ["other"] * 6  # 40% negative rate
        # Lift = 0.6 / 0.4 = 1.5

        discriminative_low = mine_discriminative_keywords(
            positive, negative, min_occurrences=1, min_lift=1.0
        )
        discriminative_high = mine_discriminative_keywords(
            positive, negative, min_occurrences=1, min_lift=2.0
        )

        # Should be in low threshold results
        test_entries_low = [entry for entry in discriminative_low if entry[0] == "test"]
        assert len(test_entries_low) > 0

        # Should be filtered out by high threshold
        test_entries_high = [entry for entry in discriminative_high if entry[0] == "test"]
        assert len(test_entries_high) == 0

    def test_min_occurrences_filter(self):
        """Only suggest keywords with enough occurrences in positive set."""
        positive = ["rare"] * 2 + ["common"] * 10
        negative = ["other"] * 10

        discriminative = mine_discriminative_keywords(
            positive, negative, min_occurrences=5, min_lift=1.5
        )

        # "common" should be included (10 occurrences)
        common_entries = [entry for entry in discriminative if entry[0] == "common"]
        assert len(common_entries) > 0

        # "rare" should be filtered (only 2 occurrences)
        rare_entries = [entry for entry in discriminative if entry[0] == "rare"]
        assert len(rare_entries) == 0

    def test_handles_no_data(self):
        """Return empty list if no titles."""
        assert mine_discriminative_keywords([], ["test"]) == []
        assert mine_discriminative_keywords(["test"], []) == []
        assert mine_discriminative_keywords([], []) == []

    def test_sorted_by_lift(self):
        """Results should be sorted by lift score descending."""
        positive = [
            "high lift keyword",
            "high lift keyword",
            "high lift keyword",
            "medium lift term",
            "medium lift term",
            "other",
        ]
        negative = [
            "medium lift term",
            "other",
            "other",
            "other",
            "other",
            "other",
        ]

        discriminative = mine_discriminative_keywords(
            positive, negative, min_occurrences=2, min_lift=1.5
        )

        # Results should be sorted by lift descending
        if len(discriminative) > 1:
            for i in range(len(discriminative) - 1):
                assert discriminative[i][1] >= discriminative[i + 1][1]


class TestPhraseScoring:
    """Test phrase scoring."""

    def test_calculate_lift_ratio(self):
        """Lift = (pos_rate / neg_rate)."""
        score = calculate_phrase_score("test", 10, 2, 100, 100)
        # pos_rate = 10/100 = 0.1, neg_rate = 2/100 = 0.02
        # lift = 0.1 / 0.02 = 5.0
        assert score == pytest.approx(5.0)

    def test_handles_zero_negatives(self):
        """Handle cases where phrase only in positives."""
        score = calculate_phrase_score("test", 10, 0, 100, 100)
        # Phrase appears in positives but not negatives
        # Should return high score (10.0 as proxy for infinite)
        assert score == 10.0

    def test_handles_zero_positives(self):
        """Handle cases where phrase only in negatives."""
        score = calculate_phrase_score("test", 0, 10, 100, 100)
        # pos_rate = 0, neg_rate = 0.1, lift = 0
        assert score == 0.0

    def test_handles_zero_both(self):
        """Handle cases where phrase appears nowhere."""
        score = calculate_phrase_score("test", 0, 0, 100, 100)
        assert score == 0.0

    def test_handles_invalid_totals(self):
        """Handle invalid total counts."""
        assert calculate_phrase_score("test", 10, 5, 0, 100) == 0.0
        assert calculate_phrase_score("test", 10, 5, 100, 0) == 0.0
        assert calculate_phrase_score("test", 10, 5, -1, 100) == 0.0


class TestSubsumptionFiltering:
    """Test subsumption detection."""

    def test_filters_subsumed_phrases(self):
        """Remove 'fda' if 'fda approval' accounts for 90%+ occurrences."""
        keyword_counts = {
            "fda approval": 100,
            "fda": 105,  # Only 5 more than "fda approval" - mostly subsumed
        }

        filtered = filter_subsumed_phrases(keyword_counts, subsume_threshold=0.9)

        # "fda" should be filtered (105/100 = 1.05 > 0.9)
        assert "fda" not in filtered
        # "fda approval" should be kept
        assert "fda approval" in filtered

    def test_keeps_independent_phrases(self):
        """Filter phrases where shorter appears mostly within longer."""
        keyword_counts = {
            "fda approval": 100,
            "fda": 200,  # ratio = 200/100 = 2.0 >= 0.9, so IS subsumed
        }

        filtered = filter_subsumed_phrases(keyword_counts, subsume_threshold=0.9)

        # "fda approval" kept (processed first as longer)
        # "fda" filtered (ratio 2.0 >= 0.9 means subsumed)
        assert "fda approval" in filtered
        assert "fda" not in filtered

    def test_multiple_subsumptions(self):
        """Handle multiple levels of subsumption."""
        keyword_counts = {
            "fda": 102,
            "fda approval": 100,
            "fda approval granted": 98,
        }

        filtered = filter_subsumed_phrases(keyword_counts, subsume_threshold=0.9)

        # Longest phrase should be kept
        assert "fda approval granted" in filtered
        # Shorter phrases should be filtered if subsumed
        # "fda approval" is 100/98 = 1.02 > 0.9, filtered
        # "fda" is 102/98 = 1.04 > 0.9, filtered

    def test_empty_input(self):
        """Handle empty input."""
        filtered = filter_subsumed_phrases({})
        assert filtered == {}

    def test_threshold_parameter(self):
        """Subsumption threshold should be respected."""
        keyword_counts = {
            "fda approval": 100,
            "fda": 150,  # ratio = 150/100 = 1.5
        }

        # Low threshold (0.5) - "fda" filtered (1.5 >= 0.5)
        filtered_loose = filter_subsumed_phrases(keyword_counts, subsume_threshold=0.5)
        assert "fda approval" in filtered_loose
        assert "fda" not in filtered_loose

        # High threshold (2.0) - keep both (1.5 < 2.0, not subsumed)
        filtered_strict = filter_subsumed_phrases(keyword_counts, subsume_threshold=2.0)
        assert "fda" in filtered_strict
        assert "fda approval" in filtered_strict


class TestGetPhraseContexts:
    """Test phrase context extraction."""

    def test_get_contexts(self):
        """Get example contexts where phrase appears."""
        titles = [
            "FDA Approves New Drug",
            "Company Reports Earnings",
            "FDA Grants Priority Review",
            "Another FDA Approval",
        ]

        contexts = get_phrase_contexts(titles, "fda", max_contexts=10)

        assert len(contexts) == 3
        assert "FDA Approves New Drug" in contexts
        assert "FDA Grants Priority Review" in contexts
        assert "Another FDA Approval" in contexts

    def test_max_contexts_limit(self):
        """Respect max_contexts parameter."""
        titles = ["FDA Approval"] * 10

        contexts = get_phrase_contexts(titles, "fda", max_contexts=5)

        assert len(contexts) == 5

    def test_case_insensitive(self):
        """Search should be case insensitive."""
        titles = [
            "FDA Approves Drug",
            "fda grants clearance",
            "Fda Reviews Application",
        ]

        contexts = get_phrase_contexts(titles, "fda")

        assert len(contexts) == 3

    def test_phrase_not_found(self):
        """Return empty list if phrase not found."""
        titles = ["Company Reports Earnings"]

        contexts = get_phrase_contexts(titles, "fda")

        assert contexts == []

    def test_empty_titles(self):
        """Handle empty title list."""
        contexts = get_phrase_contexts([], "fda")
        assert contexts == []

    def test_multi_word_phrase(self):
        """Handle multi-word phrases."""
        titles = [
            "FDA Approval Granted",
            "FDA Approval Pending",
            "FDA Clearance Received",
        ]

        contexts = get_phrase_contexts(titles, "fda approval")

        assert len(contexts) == 2
        assert "FDA Approval Granted" in contexts
        assert "FDA Approval Pending" in contexts


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_end_to_end_keyword_discovery(self):
        """Test complete keyword discovery pipeline."""
        positive_titles = [
            "FDA Approves Breakthrough Drug",
            "FDA Grants Priority Review",
            "FDA Approval Granted for Treatment",
            "FDA Clearance Received",
            "FDA Approves New Therapy",
        ]

        negative_titles = [
            "Company Reports Quarterly Earnings",
            "Conference Call Scheduled",
            "Investor Presentation Announced",
            "Management Team Update",
            "Office Opening Planned",
        ]

        # 1. Mine discriminative keywords
        discriminative = mine_discriminative_keywords(
            positive_titles, negative_titles, min_occurrences=2, min_lift=2.0
        )

        # Should find FDA-related terms
        fda_terms = [entry for entry in discriminative if "fda" in entry[0]]
        assert len(fda_terms) > 0

        # 2. Get contexts for top keyword
        if discriminative:
            top_phrase = discriminative[0][0]
            contexts = get_phrase_contexts(positive_titles, top_phrase, max_contexts=3)
            assert len(contexts) > 0

    def test_keyword_mining_with_filtering(self):
        """Test mining with subsumption filtering."""
        titles = [
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Approval Granted",
            "FDA Clearance",
            "Other News",
        ]

        # 1. Mine candidates
        candidates = mine_keyword_candidates(titles, min_occurrences=2)

        # 2. Filter subsumed phrases
        filtered = filter_subsumed_phrases(candidates, subsume_threshold=0.9)

        # "fda approval granted" (3-gram) should be kept as longest
        assert "fda approval granted" in filtered
        # Shorter phrases get filtered if they're subsumed
