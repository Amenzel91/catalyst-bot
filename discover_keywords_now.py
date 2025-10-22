#!/usr/bin/env python3
"""
QUICK-START KEYWORD DISCOVERY

Extracts keywords from existing MOA data without needing rejected_items.jsonl.
Uses NLP to extract important phrases from the outcomes we already have.

Usage:
    python discover_keywords_now.py

Output:
    - Prints top keywords to console
    - Saves to data/moa/discovered_keywords.json
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set


def load_outcomes(path: str = "data/moa/outcomes.jsonl") -> list:
    """Load all outcomes from JSONL file."""
    outcomes = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                outcomes.append(json.loads(line))
    return outcomes


def extract_financial_phrases(text: str) -> List[str]:
    """
    Extract financial catalyst phrases using regex patterns.

    This catches multi-word phrases that are common catalysts.
    """
    if not text:
        return []

    text = text.lower()
    phrases = []

    # Define patterns for common catalyst phrases
    patterns = [
        # FDA/Regulatory (biotech gold mine)
        r"\bfda\s+(?:approval|clearance|authorization|designation)\b",
        r"\b(?:fast\s+track|breakthrough\s+therapy|orphan\s+drug)\b",
        r"\b510\s?\(k\)\b",
        r"\bde\s+novo\b",
        r"\bpma\s+approval\b",
        r"\bce\s+mark\b",
        r"\bbiologics\s+license\b",
        r"\bnew\s+drug\s+application\b",
        r"\binvestigational\s+new\s+drug\b",
        r"\bexpanded\s+access\b",
        r"\bcompassionate\s+use\b",

        # Clinical Trials
        r"\bphase\s+[123iiiIII]+(?:\s+trial)?\b",
        r"\bclinical\s+trial(?:\s+results)?\b",
        r"\bpivotal\s+(?:trial|study)\b",
        r"\bprimary\s+endpoint(?:\s+met)?\b",
        r"\bstatistically\s+significant\b",
        r"\bdata\s+readout\b",
        r"\btop[- ]?line\s+(?:data|results)\b",
        r"\bclinical\s+hold\s+lifted\b",

        # Partnerships & M&A
        r"\bstrategic\s+(?:partnership|alliance|collaboration)\b",
        r"\bcollaboration\s+agreement\b",
        r"\blicensing\s+(?:agreement|deal)\b",
        r"\bdistribution\s+(?:agreement|rights)\b",
        r"\bcontract\s+(?:award|win)\b",
        r"\bjoint\s+venture\b",
        r"\bmerger\s+agreement\b",
        r"\bacquisition\s+(?:agreement|completed)\b",
        r"\btakeover\s+(?:offer|bid)\b",
        r"\bletter\s+of\s+intent\b",
        r"\bdefinitive\s+agreement\b",

        # Financing
        r"\bsecured\s+(?:funding|financing|investment)\b",
        r"\bseries\s+[abcdefABCDEF]\s+funding\b",
        r"\bventure\s+(?:capital|funding)\b",
        r"\binstitutional\s+investment\b",
        r"\bprivate\s+placement\b",
        r"\bpublic\s+offering\b",
        r"\bfollow[- ]?on\s+offering\b",
        r"\bshelf\s+registration\b",
        r"\bdebt\s+financing\b",

        # Products & Revenue
        r"\bproduct\s+(?:launch|release)\b",
        r"\bcommercial\s+(?:launch|availability)\b",
        r"\brevenue\s+(?:guidance|milestone|target)\b",
        r"\bsales\s+milestone\b",
        r"\bearnings\s+(?:beat|guidance)\b",
        r"\bguidance\s+(?:raise|increase)\b",
        r"\buplist(?:ing)?\b",
        r"\bnasdaq\s+(?:listing|uplisting)\b",
        r"\bnyse\s+listing\b",

        # Energy Sector (huge returns in MOA data)
        r"\boil\s+(?:discovery|strike|find)\b",
        r"\bgas\s+discovery\b",
        r"\bdrilling\s+(?:results|success|program)\b",
        r"\bwell\s+(?:completion|test|results)\b",
        r"\bproved\s+reserves\b",
        r"\bprobable\s+reserves\b",
        r"\breserves?\s+(?:expansion|increase|upgrade)\b",
        r"\bproduction\s+(?:increase|ramp|milestone)\b",
        r"\bfield\s+development\b",
        r"\bhorizontal\s+drilling\b",
        r"\bunconventional\s+(?:resources|reserves)\b",

        # Technology
        r"\bpatent\s+(?:granted|issued|approved)\b",
        r"\bintellectual\s+property\b",
        r"\bcloud\s+(?:contract|migration|platform)\b",
        r"\bsaas\s+platform\b",
        r"\b(?:ai|artificial\s+intelligence)\s+(?:breakthrough|platform)\b",
        r"\bmachine\s+learning\b",
        r"\bgovernment\s+contract\b",
        r"\benterprise\s+(?:agreement|contract)\b",

        # Healthcare/Medical
        r"\bbiomarker\b",
        r"\bgene\s+therapy\b",
        r"\bcell\s+therapy\b",
        r"\bcrispr\b",
        r"\bcar[- ]?t\b",
        r"\bimmuno[- ]?oncology\b",
        r"\bmonoclonal\s+antibody\b",
        r"\bsmall\s+molecule\b",

        # Stock Events
        r"\bstock\s+split\b",
        r"\breverse\s+split\b",
        r"\bdividend\s+(?:increase|declared)\b",
        r"\bshare\s+buyback\b",
        r"\bshare\s+repurchase\b",
        r"\binsider\s+buying\b",
        r"\binstitutional\s+ownership\b",

        # Negative Keywords (exit signals)
        r"\boffering\s+(?:priced|closed|completed)\b",
        r"\bwarrant\s+(?:exercise|coverage)\b",
        r"\bdilut(?:ion|ive)\b",
        r"\bgoing\s+concern\b",
        r"\bchapter\s+11\b",
        r"\bbankruptcy\b",
        r"\bdelisting\b",
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            phrase = match.group(0).lower()
            # Normalize whitespace
            phrase = re.sub(r"\s+", " ", phrase).strip()
            phrases.append(phrase)

    return phrases


def extract_important_ngrams(text: str, n: int = 2) -> List[str]:
    """
    Extract n-grams (2-3 word phrases) that might be catalysts.

    Filters out common stop words and generic phrases.
    """
    if not text:
        return []

    # Stop words to exclude
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "should", "could", "may", "might", "must", "can", "about",
        "into", "through", "during", "before", "after", "above", "below",
        "between", "under", "over", "this", "that", "these", "those", "said",
        "says", "announced", "announces", "reports", "reported"
    }

    text = text.lower()
    # Remove punctuation except hyphens (for terms like "car-t", "fast-track")
    text = re.sub(r"[^\w\s-]", " ", text)
    words = text.split()

    ngrams = []
    for i in range(len(words) - n + 1):
        ngram = words[i : i + n]
        # Filter out ngrams with stop words at start or end
        if ngram[0] not in stop_words and ngram[-1] not in stop_words:
            phrase = " ".join(ngram)
            # Only include if contains at least one alphabetic char
            if re.search(r"[a-z]", phrase):
                ngrams.append(phrase)

    return ngrams


def analyze_missed_opportunities(outcomes: List[dict]) -> Dict:
    """Analyze keywords in missed opportunities."""
    # Counters for different metrics
    phrase_freq = Counter()
    phrase_returns = defaultdict(list)
    sector_phrases = defaultdict(lambda: Counter())

    missed_count = 0

    for outcome in outcomes:
        if not outcome.get("is_missed_opportunity"):
            continue

        missed_count += 1

        # Get metadata
        title = outcome.get("item_title", "")
        summary = outcome.get("item_summary", "")
        combined_text = f"{title} {summary}"
        max_return = outcome.get("max_return_pct", 0)
        sector = outcome.get("sector_context", {}).get("sector", "UNKNOWN")

        # Extract financial phrases using regex
        financial_phrases = extract_financial_phrases(combined_text)

        # Extract 2-grams and 3-grams
        bigrams = extract_important_ngrams(combined_text, n=2)
        trigrams = extract_important_ngrams(combined_text, n=3)

        all_phrases = financial_phrases + bigrams + trigrams

        for phrase in all_phrases:
            phrase_freq[phrase] += 1
            phrase_returns[phrase].append(max_return)
            sector_phrases[sector][phrase] += 1

    return {
        "total_missed": missed_count,
        "phrase_frequency": phrase_freq,
        "phrase_returns": phrase_returns,
        "sector_phrases": sector_phrases,
    }


def compare_to_existing_keywords(
    discovered_phrases: Counter, config_path: str = "src/catalyst_bot/config.py"
) -> Set[str]:
    """Compare discovered phrases to existing keywords in config.py."""
    # Read config file
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_text = f.read().lower()
    except FileNotFoundError:
        print(f"Warning: Could not find {config_path}")
        return set(discovered_phrases.keys())

    # Find keywords that are NOT in config
    new_keywords = set()
    for phrase in discovered_phrases.keys():
        # Check if phrase appears in config file (case-insensitive)
        if phrase not in config_text:
            new_keywords.add(phrase)

    return new_keywords


def print_analysis(analysis: Dict, top_n: int = 50):
    """Print keyword analysis report."""
    print("=" * 100)
    print("DISCOVERED KEYWORDS FROM MOA DATA (12-MONTH HISTORICAL ANALYSIS)")
    print("=" * 100)
    print(f"\nTotal Missed Opportunities Analyzed: {analysis['total_missed']}\n")

    phrase_freq = analysis["phrase_frequency"]
    phrase_returns = analysis["phrase_returns"]

    # Compare to existing keywords
    new_keywords = compare_to_existing_keywords(phrase_freq)

    print("=" * 100)
    print("1. NEW KEYWORDS NOT IN CONFIG.PY (High Priority)")
    print("=" * 100)
    print(f"{'Keyword':<50} {'Count':>8} {'Avg Return':>12} {'Max Return':>12}")
    print("-" * 100)

    new_phrase_freq = {k: v for k, v in phrase_freq.items() if k in new_keywords}
    for phrase, count in Counter(new_phrase_freq).most_common(top_n):
        if count >= 3:  # Only show phrases appearing 3+ times
            returns = phrase_returns[phrase]
            avg_return = sum(returns) / len(returns) if returns else 0
            max_return = max(returns) if returns else 0
            print(f"{phrase:<50} {count:>8} {avg_return:>11.2f}% {max_return:>11.2f}%")

    print("\n" + "=" * 100)
    print("2. ALL KEYWORDS BY FREQUENCY (Existing + New)")
    print("=" * 100)
    print(f"{'Keyword':<50} {'Count':>8} {'Avg Return':>12} {'Max Return':>12} {'NEW?':>8}")
    print("-" * 100)

    for phrase, count in phrase_freq.most_common(top_n):
        if count >= 3:
            returns = phrase_returns[phrase]
            avg_return = sum(returns) / len(returns) if returns else 0
            max_return = max(returns) if returns else 0
            is_new = "NEW" if phrase in new_keywords else ""
            print(
                f"{phrase:<50} {count:>8} {avg_return:>11.2f}% {max_return:>11.2f}% {is_new:>8}"
            )

    print("\n" + "=" * 100)
    print("3. KEYWORDS WITH HIGHEST AVERAGE RETURNS (min 5 occurrences)")
    print("=" * 100)
    print(f"{'Keyword':<50} {'Count':>8} {'Avg Return':>12} {'Max Return':>12}")
    print("-" * 100)

    phrase_avg_returns = []
    for phrase, returns in phrase_returns.items():
        if len(returns) >= 5:
            avg = sum(returns) / len(returns)
            max_ret = max(returns)
            phrase_avg_returns.append((phrase, len(returns), avg, max_ret))

    phrase_avg_returns.sort(key=lambda x: x[2], reverse=True)

    for phrase, count, avg, max_ret in phrase_avg_returns[:top_n]:
        print(f"{phrase:<50} {count:>8} {avg:>11.2f}% {max_ret:>11.2f}%")

    print("\n" + "=" * 100)
    print("4. SECTOR-SPECIFIC KEYWORDS")
    print("=" * 100)

    sector_phrases = analysis["sector_phrases"]
    top_sectors = ["Energy", "Technology", "Healthcare", "Financial Services"]

    for sector in top_sectors:
        if sector in sector_phrases and sector_phrases[sector]:
            print(f"\n{sector.upper()}:")
            print("-" * 100)
            top_sector_phrases = sector_phrases[sector].most_common(15)
            for phrase, count in top_sector_phrases:
                returns = phrase_returns[phrase]
                avg_return = sum(returns) / len(returns) if returns else 0
                is_new = "*NEW*" if phrase in new_keywords else ""
                print(f"  {phrase:<45} {count:>5}x  (avg {avg_return:>6.2f}%)  {is_new}")

    print("\n" + "=" * 100)


def main():
    """Main execution."""
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        print(f"ERROR: {outcomes_path} not found")
        print("Run historical_bootstrapper first to collect MOA data.")
        return 1

    print(f"Loading outcomes from {outcomes_path}...")
    outcomes = load_outcomes(str(outcomes_path))
    print(f"Loaded {len(outcomes):,} outcomes\n")

    # Analyze
    print("Extracting keywords from missed opportunities...")
    analysis = analyze_missed_opportunities(outcomes)
    print(f"Found {len(analysis['phrase_frequency']):,} unique phrases\n")

    # Print report
    print_analysis(analysis, top_n=100)

    # Save raw data
    output_path = Path("data/moa/discovered_keywords.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "total_missed_opportunities": analysis["total_missed"],
        "keywords_by_frequency": {
            k: v for k, v in analysis["phrase_frequency"].most_common(200)
        },
        "keywords_by_avg_return": {
            k: sum(v) / len(v) if v else 0
            for k, v in analysis["phrase_returns"].items()
            if len(v) >= 5
        },
        "sector_specific": {
            sector: dict(phrases.most_common(50))
            for sector, phrases in analysis["sector_phrases"].items()
        },
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n\nRaw data saved to: {output_path}")
    print("\nNext Steps:")
    print("1. Review the NEW keywords in section 1 above")
    print("2. Add high-frequency (10+ count) keywords to src/catalyst_bot/config.py")
    print("3. Add high-return (>100% avg) keywords even if lower frequency")
    print("4. Run backtest to validate improvement")
    print("5. See KEYWORD_DISCOVERY_GUIDE.md for detailed instructions")

    return 0


if __name__ == "__main__":
    exit(main())
