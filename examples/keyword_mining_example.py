"""
Example usage of the keyword_miner module.

This demonstrates how to extract keyword candidates from news titles
and find discriminative keywords that distinguish catalyst from non-catalyst news.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

from catalyst_bot.keyword_miner import (
    mine_keyword_candidates,
    mine_discriminative_keywords,
    get_phrase_contexts,
    filter_subsumed_phrases,
    print_keyword_report,
    print_discriminative_report
)


# Example catalyst titles (positive examples)
catalyst_titles = [
    "FDA Approves Company XYZ's New Cancer Drug for Phase III Trial",
    "ABC Corp Announces Strategic Partnership with Major Tech Company",
    "Biotech Firm Receives FDA Breakthrough Therapy Designation",
    "Company Reports Record Q3 Earnings, Beats Estimates by 25%",
    "Tech Startup Secures $50M Series B Funding Round",
    "Pharmaceutical Company Files 8-K for Major Acquisition",
    "FDA Grants Priority Review for New Diabetes Treatment",
    "Company Announces Share Buyback Program Worth $1B",
    "Merger Agreement Signed with Industry Leader",
    "Clinical Trial Results Show 90% Efficacy Rate",
    "New Product Launch Exceeds Revenue Projections",
    "Strategic Partnership Expands Market Reach to Europe",
    "FDA Approval Expected for Blockbuster Drug Candidate",
    "Company Wins $200M Government Contract",
    "Breakthrough Technology Patent Granted",
    "Major Customer Agreement Signed with Fortune 500 Company",
    "IPO Pricing Announced, Oversubscribed 5x",
    "Phase II Trial Meets Primary Endpoint",
    "Activist Investor Takes Stake, Proposes Board Changes",
    "Company Upgrades Annual Revenue Guidance by 30%"
]

# Example non-catalyst titles (negative examples)
non_catalyst_titles = [
    "Company Provides Update on Business Operations",
    "Executive Team to Present at Industry Conference",
    "Annual Shareholder Meeting Scheduled for June",
    "Company Files Routine 10-Q with SEC",
    "CEO to Appear on CNBC Interview Tomorrow",
    "Analyst Maintains Hold Rating on Stock",
    "Company Announces Dividend Payment Date",
    "Quarterly Conference Call Scheduled",
    "Company Relocates Corporate Headquarters",
    "New CFO Appointed Following Retirement",
    "Company Reports In-Line Quarterly Results",
    "Stock Added to Small-Cap Index",
    "Company Provides General Business Update",
    "Management to Attend Investor Conference",
    "Annual Report Now Available on Website",
    "Company Announces Regular Board Meeting",
    "Routine SEC Filing Submitted on Schedule",
    "Executive Compensation Report Released",
    "Company Hosts Facility Tour for Investors",
    "Quarterly Dividend Maintained at $0.10 per Share"
]


def example_basic_mining():
    """Example: Basic keyword mining from all titles."""
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Keyword Mining")
    print("="*80)

    # Combine all titles
    all_titles = catalyst_titles + non_catalyst_titles

    # Mine keyword candidates
    keywords = mine_keyword_candidates(
        titles=all_titles,
        min_occurrences=3,  # Must appear at least 3 times
        max_ngram_size=4    # Up to 4-word phrases
    )

    # Print report
    print_keyword_report(keywords, top_n=20, group_by_ngram_size=True)


def example_discriminative_mining():
    """Example: Find keywords that discriminate catalyst from non-catalyst."""
    print("\n" + "="*80)
    print("EXAMPLE 2: Discriminative Keyword Mining")
    print("="*80)

    # Find discriminative keywords
    discriminative = mine_discriminative_keywords(
        positive_titles=catalyst_titles,
        negative_titles=non_catalyst_titles,
        min_occurrences=2,   # Must appear at least 2 times in positive set
        min_lift=2.0,        # Must be 2x more likely in positive set
        max_ngram_size=4
    )

    # Print report
    print_discriminative_report(discriminative, top_n=30)


def example_phrase_contexts():
    """Example: Get contexts where specific phrases appear."""
    print("\n" + "="*80)
    print("EXAMPLE 3: Phrase Context Extraction")
    print("="*80)

    # Find contexts for "fda"
    phrase = "fda"
    contexts = get_phrase_contexts(catalyst_titles, phrase, max_contexts=5)

    print(f"\nContexts where '{phrase}' appears:")
    print("-" * 80)
    for i, context in enumerate(contexts, 1):
        print(f"{i}. {context}")


def example_filtering_subsumed():
    """Example: Filter out subsumed phrases."""
    print("\n" + "="*80)
    print("EXAMPLE 4: Filtering Subsumed Phrases")
    print("="*80)

    # Mine keywords
    keywords = mine_keyword_candidates(
        titles=catalyst_titles,
        min_occurrences=2,
        max_ngram_size=4
    )

    print(f"\nBefore filtering: {len(keywords)} keywords")
    print("\nSample keywords (showing potential subsumption):")
    for phrase, count in list(keywords.items())[:15]:
        print(f"  {count:3d}  {phrase}")

    # Filter subsumed phrases
    filtered = filter_subsumed_phrases(keywords, subsume_threshold=0.9)

    print(f"\nAfter filtering: {len(filtered)} keywords")
    print("\nFiltered keywords:")
    for phrase, count in list(filtered.items())[:15]:
        print(f"  {count:3d}  {phrase}")


def example_custom_analysis():
    """Example: Custom analysis combining multiple techniques."""
    print("\n" + "="*80)
    print("EXAMPLE 5: Custom Analysis Pipeline")
    print("="*80)

    # Step 1: Mine discriminative keywords
    discriminative = mine_discriminative_keywords(
        positive_titles=catalyst_titles,
        negative_titles=non_catalyst_titles,
        min_occurrences=2,
        min_lift=3.0,  # Strong discriminators only
        max_ngram_size=3
    )

    # Step 2: Extract top phrases
    top_phrases = [phrase for phrase, _, _, _ in discriminative[:10]]

    print("\nTop 10 Discriminative Phrases (lift >= 3.0):")
    print("-" * 80)
    for phrase, lift, pos, neg in discriminative[:10]:
        print(f"  {lift:5.2f}x  {phrase:30s}  (pos={pos}, neg={neg})")

    # Step 3: Show contexts for top phrase
    if top_phrases:
        top_phrase = top_phrases[0]
        contexts = get_phrase_contexts(catalyst_titles, top_phrase, max_contexts=3)

        print(f"\nExample contexts for '{top_phrase}':")
        print("-" * 80)
        for i, context in enumerate(contexts, 1):
            print(f"{i}. {context}")


def main():
    """Run all examples."""
    print("\n" + "="*80)
    print("KEYWORD MINING MODULE - EXAMPLE USAGE")
    print("="*80)

    example_basic_mining()
    example_discriminative_mining()
    example_phrase_contexts()
    example_filtering_subsumed()
    example_custom_analysis()

    print("\n" + "="*80)
    print("All examples completed!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
