"""
Test conference/exhibit announcement filter.

Ensures that:
1. Conference/exhibit announcements are correctly filtered out
2. Material news (FDA approvals, earnings, etc.) still passes through
3. Real-world examples from user feedback are handled correctly

Author: Claude Code
Date: 2025-10-28
"""

import pytest


# Test cases for conference/exhibit announcements (SHOULD BE FILTERED)
SHOULD_REJECT = [
    # Real examples from user feedback (Oct 28)
    {
        "title": "ZenaTech's ZenaDrone to Exhibit at Defense & Security 2025",
        "ticker": "ZENA",
        "reason": "exhibit at conference",
    },
    {
        "title": "Reviva to Present Negative Symptom Data at the CNS Summit 2025",
        "ticker": "RVPH",
        "reason": "present at conference",
    },
    # Additional test cases
    {
        "title": "Company X to Present Data at the Annual Healthcare Conference",
        "ticker": "TEST",
        "reason": "present data at conference",
    },
    {
        "title": "Biotech Inc. Will Exhibit at BIO International Convention 2025",
        "ticker": "TEST",
        "reason": "will exhibit at",
    },
    {
        "title": "Tech Corp Presenting at the Morgan Stanley Tech Summit",
        "ticker": "TEST",
        "reason": "presenting at conference",
    },
    {
        "title": "Pharma Co. to Present at the JPMorgan Healthcare Conference",
        "ticker": "TEST",
        "reason": "to present at",
    },
    {
        "title": "Medical Device Co. Exhibiting at MEDICA Trade Fair 2025",
        "ticker": "TEST",
        "reason": "exhibiting at",
    },
    {
        "title": "Company Announces Presentation of Clinical Data at ASCO 2025",
        "ticker": "TEST",
        "reason": "announces presentation",
    },
    {
        "title": "Biotech to Present Updated Data from Phase 2 Study at Conference",
        "ticker": "TEST",
        "reason": "present updated data",
    },
    {
        "title": "Company Will Present Interim Data at European Cancer Congress",
        "ticker": "TEST",
        "reason": "will present interim data",
    },
]


# Test cases for material news (SHOULD NOT BE FILTERED)
SHOULD_ACCEPT = [
    {
        "title": "FDA Grants Breakthrough Therapy Designation for Drug Candidate",
        "ticker": "TEST",
        "reason": "FDA breakthrough - material catalyst",
    },
    {
        "title": "Company Announces Positive Topline Results from Phase 3 Trial",
        "ticker": "TEST",
        "reason": "Phase 3 positive results - material catalyst",
    },
    {
        "title": "Biotech Receives FDA Approval for New Cancer Treatment",
        "ticker": "TEST",
        "reason": "FDA approval - material catalyst",
    },
    {
        "title": "Pharma Reports Strong Q3 Earnings Beat with 50% Revenue Growth",
        "ticker": "TEST",
        "reason": "earnings beat - material catalyst",
    },
    {
        "title": "Company Announces $100M Partnership with Major Pharma",
        "ticker": "TEST",
        "reason": "partnership - material catalyst",
    },
    {
        "title": "Tech Co. Secures $50M Series B Funding Round",
        "ticker": "TEST",
        "reason": "funding - material catalyst",
    },
    {
        "title": "Clinical Trial Met Primary Endpoint with Statistical Significance",
        "ticker": "TEST",
        "reason": "trial success - material catalyst",
    },
    {
        "title": "Company to Present FDA Approval Results in Webinar",
        "ticker": "TEST",
        "reason": "FDA approval (even if presenting) - material catalyst",
    },
    {
        "title": "Biotech Announces Pivotal Trial Results Exceeded Expectations",
        "ticker": "TEST",
        "reason": "pivotal results - material catalyst",
    },
    {
        "title": "First-in-Class Treatment Receives Accelerated Approval Pathway",
        "ticker": "TEST",
        "reason": "first-in-class + approval - material catalyst",
    },
]


def check_conference_filter(title: str, summary: str = "") -> bool:
    """
    Replicate the conference/presentation filter logic from runner.py.

    Args:
        title: News title
        summary: News summary (optional)

    Returns:
        True if item should be filtered (rejected), False if should pass
    """
    combined_text = f"{title.lower()} {summary.lower()}"

    # Keywords indicating data presentation or conference/exhibit announcements
    presentation_keywords = [
        "announces presentation",
        "announcement of presentation",
        "presentation of",
        "presents data",
        "presenting at",
        "to present",
        "will present",
        "interim data",
        "updated data",
        "preliminary data",
        "data presentation",
        # Conference/exhibit announcements (user feedback: not catalyst news)
        "to exhibit at",
        "will exhibit at",
        "exhibiting at",
        "exhibit at",
        "presenting data at",
        "present data at",
        "present at",
        "to present at the",
        "will present at the",
    ]

    # Breakthrough keywords that override the filter
    breakthrough_keywords = [
        "breakthrough",
        "pivotal",
        "phase 3",
        "phase iii",
        "fda approval",
        "accelerated approval",
        "positive topline",
        "met primary endpoint",
        "exceeded expectations",
        "novel",
        "first-in-class",
        "statistically significant",
    ]

    is_presentation = any(kw in combined_text for kw in presentation_keywords)
    is_breakthrough = any(kw in combined_text for kw in breakthrough_keywords)

    # Return True if should filter (presentation without breakthrough)
    return is_presentation and not is_breakthrough


class TestConferenceFilter:
    """Test suite for conference/exhibit announcement filter."""

    @pytest.mark.parametrize("test_case", SHOULD_REJECT)
    def test_filters_conference_announcements(self, test_case):
        """Verify that conference/exhibit announcements are filtered."""
        title = test_case["title"]
        should_filter = check_conference_filter(title)

        assert should_filter, (
            f"Expected to filter: {title}\n"
            f"Reason: {test_case['reason']}"
        )

    @pytest.mark.parametrize("test_case", SHOULD_ACCEPT)
    def test_allows_material_news(self, test_case):
        """Verify that material news passes through the filter."""
        title = test_case["title"]
        should_filter = check_conference_filter(title)

        assert not should_filter, (
            f"Should NOT filter: {title}\n"
            f"Reason: {test_case['reason']}"
        )

    def test_real_world_zena_example(self):
        """Test real-world ZENA example from user feedback (Oct 28)."""
        title = "ZenaTech's ZenaDrone to Exhibit at Defense & Security 2025"
        should_filter = check_conference_filter(title)

        assert should_filter, (
            "ZENA exhibit announcement should be filtered (user feedback)"
        )

    def test_real_world_rvph_example(self):
        """Test real-world RVPH example from user feedback (Oct 28)."""
        title = "Reviva to Present Negative Symptom Data at the CNS Summit 2025"
        should_filter = check_conference_filter(title)

        assert should_filter, (
            "RVPH present announcement should be filtered (user feedback)"
        )

    def test_breakthrough_overrides_presentation(self):
        """Verify that breakthrough keywords override presentation filter."""
        title = "Company to Present FDA Breakthrough Therapy Data at Conference"
        should_filter = check_conference_filter(title)

        assert not should_filter, (
            "Breakthrough therapy should override presentation filter"
        )

    def test_phase_3_overrides_presentation(self):
        """Verify that Phase 3 results override presentation filter."""
        title = "Biotech to Present Positive Phase 3 Results at ASCO"
        should_filter = check_conference_filter(title)

        assert not should_filter, (
            "Phase 3 results should override presentation filter"
        )

    def test_case_insensitive(self):
        """Verify filter is case-insensitive."""
        titles = [
            "Company TO EXHIBIT AT Conference",
            "Company to Exhibit at Conference",
            "Company To Exhibit At Conference",
        ]

        for title in titles:
            should_filter = check_conference_filter(title)
            assert should_filter, f"Filter should be case-insensitive: {title}"

    def test_summary_text_included(self):
        """Verify that summary text is also checked."""
        title = "Company Announces Conference Schedule"
        summary = "The company will exhibit at the Defense & Security 2025 conference."

        should_filter = check_conference_filter(title, summary)

        assert should_filter, (
            "Filter should check both title and summary"
        )

    def test_fda_approval_never_filtered(self):
        """Verify FDA approval news is never filtered."""
        titles = [
            "FDA Approval Granted for New Drug",
            "Company to Present FDA Approval Data at Conference",
            "FDA Accelerated Approval Pathway Announced",
        ]

        for title in titles:
            should_filter = check_conference_filter(title)
            assert not should_filter, f"FDA approval should never be filtered: {title}"


def test_filter_examples_manually():
    """
    Manual test function to verify filter behavior.
    Can be run directly with: pytest -k test_filter_examples_manually -s
    """
    print("\n" + "="*80)
    print("TESTING CONFERENCE/EXHIBIT FILTER")
    print("="*80)

    print("\n--- SHOULD BE FILTERED (Conference/Exhibit Announcements) ---")
    for test_case in SHOULD_REJECT:
        title = test_case["title"]
        result = check_conference_filter(title)
        status = "[OK] FILTERED" if result else "[BUG] NOT FILTERED"
        print(f"{status}: {title}")

    print("\n--- SHOULD NOT BE FILTERED (Material News) ---")
    for test_case in SHOULD_ACCEPT:
        title = test_case["title"]
        result = check_conference_filter(title)
        status = "[OK] ALLOWED" if not result else "[BUG] FILTERED"
        print(f"{status}: {title}")

    print("\n" + "="*80)


if __name__ == "__main__":
    # Run manual test if executed directly
    test_filter_examples_manually()
