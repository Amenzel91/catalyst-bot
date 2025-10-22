#!/usr/bin/env python3
"""
Extract keywords from missed opportunity catalysts.

Analyzes rejected catalysts that became profitable to identify
underweighted keywords and phrases for keyword weight tuning.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
import re


def load_outcomes(path: str) -> list:
    """Load all outcomes from JSONL file."""
    outcomes = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                outcomes.append(json.loads(line))
    return outcomes


def load_rejected_items(path: str) -> dict:
    """Load rejected items by ticker and timestamp."""
    items = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    item = json.loads(line)
                    key = (item.get('ticker'), item.get('rejection_ts'))
                    items[key] = item
                except:
                    continue
    return items


def extract_keywords_from_text(text: str) -> list:
    """Extract potential keywords from text."""
    if not text:
        return []

    # Normalize text
    text = text.lower()

    # Common financial/catalyst keywords to look for
    patterns = [
        # Regulatory/FDA
        r'\bfda\s+approval\b', r'\bfda\s+clearance\b', r'\b510\(k\)\b',
        r'\bbreakthrough\s+therapy\b', r'\bfast\s+track\b', r'\borphan\s+drug\b',
        r'\bde\s+novo\b', r'\bpma\s+approval\b',

        # Clinical trials
        r'\bphase\s+[123iiiIII]+\b', r'\bclinical\s+trial\b', r'\btrial\s+results\b',
        r'\bpivotal\s+trial\b', r'\bdata\s+readout\b',

        # Partnerships
        r'\bstrategic\s+partnership\b', r'\bcollaboration\b', r'\bcollaboration\s+agreement\b',
        r'\bcontract\s+award\b', r'\bdistribution\s+agreement\b', r'\blicensing\s+agreement\b',
        r'\bjoint\s+venture\b',

        # M&A
        r'\bmerger\b', r'\bacquisition\b', r'\btakeover\b', r'\bbuyout\b',

        # Products/Revenue
        r'\bproduct\s+launch\b', r'\bnew\s+product\b', r'\bcommercial\s+launch\b',
        r'\brevenue\s+guidance\b', r'\bsales\s+milestone\b',

        # Financial events
        r'\bearnings\s+beat\b', r'\bguidance\s+raise\b', r'\buplisting\b',
        r'\bstock\s+split\b', r'\bdividend\b', r'\bshare\s+buyback\b',

        # Energy sector specific
        r'\boil\s+discovery\b', r'\bgas\s+discovery\b', r'\bdrilling\s+results\b',
        r'\breserves\b', r'\bproduction\s+increase\b', r'\bwell\s+completion\b',

        # Technology sector specific
        r'\bai\s+breakthrough\b', r'\bpatent\b', r'\bintellectual\s+property\b',
        r'\bcloud\s+contract\b', r'\bsoftware\s+launch\b',

        # Healthcare sector specific
        r'\bbiomarker\b', r'\bgene\s+therapy\b', r'\bcell\s+therapy\b',
        r'\bcrispr\b', r'\bcar-t\b',
    ]

    found_keywords = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found_keywords.extend(matches)

    return found_keywords


def analyze_missed_opportunity_keywords(outcomes: list, rejected_items: dict) -> dict:
    """
    Analyze keywords present in missed opportunities.

    Returns dict with:
    - keyword_frequency: Counter of keywords
    - keyword_returns: {keyword: [returns]}
    - sector_keywords: {sector: {keyword: count}}
    """
    keyword_freq = Counter()
    keyword_returns = defaultdict(list)
    sector_keywords = defaultdict(lambda: Counter())

    for outcome in outcomes:
        if not outcome.get('is_missed_opportunity'):
            continue

        # Get original rejection item
        key = (outcome.get('ticker'), outcome.get('rejection_ts'))
        item = rejected_items.get(key)
        if not item:
            continue

        # Extract keywords from title and summary
        title = item.get('title', '')
        summary = item.get('summary', '')
        text = f"{title} {summary}"

        keywords = extract_keywords_from_text(text)
        max_return = outcome.get('max_return_pct', 0)
        sector = outcome.get('sector_context', {}).get('sector', 'UNKNOWN')

        for keyword in keywords:
            keyword_freq[keyword] += 1
            keyword_returns[keyword].append(max_return)
            sector_keywords[sector][keyword] += 1

    return {
        'keyword_frequency': keyword_freq,
        'keyword_returns': keyword_returns,
        'sector_keywords': sector_keywords,
    }


def print_keyword_analysis(analysis: dict, top_n: int = 50):
    """Print keyword analysis report."""
    print("=" * 80)
    print("MISSED OPPORTUNITY KEYWORD ANALYSIS")
    print("=" * 80)
    print()

    # Top keywords by frequency
    print("1. TOP KEYWORDS BY FREQUENCY")
    print("-" * 80)
    print(f"{'Keyword':<40} {'Count':>10} {'Avg Return':>12} {'Med Return':>12}")
    print("-" * 80)

    keyword_freq = analysis['keyword_frequency']
    keyword_returns = analysis['keyword_returns']

    for keyword, count in keyword_freq.most_common(top_n):
        returns = keyword_returns[keyword]
        avg_return = sum(returns) / len(returns) if returns else 0
        med_return = sorted(returns)[len(returns)//2] if returns else 0
        print(f"{keyword:<40} {count:>10} {avg_return:>11.2f}% {med_return:>11.2f}%")

    print()

    # Keywords with highest average returns
    print("2. KEYWORDS WITH HIGHEST AVERAGE RETURNS (min 5 occurrences)")
    print("-" * 80)
    print(f"{'Keyword':<40} {'Count':>10} {'Avg Return':>12} {'Max Return':>12}")
    print("-" * 80)

    keyword_avg_returns = []
    for keyword, returns in keyword_returns.items():
        if len(returns) >= 5:  # Minimum sample size
            avg = sum(returns) / len(returns)
            max_ret = max(returns)
            keyword_avg_returns.append((keyword, len(returns), avg, max_ret))

    keyword_avg_returns.sort(key=lambda x: x[2], reverse=True)

    for keyword, count, avg, max_ret in keyword_avg_returns[:top_n]:
        print(f"{keyword:<40} {count:>10} {avg:>11.2f}% {max_ret:>11.2f}%")

    print()

    # Sector-specific keywords
    print("3. SECTOR-SPECIFIC KEYWORD PATTERNS")
    print("-" * 80)

    sector_keywords = analysis['sector_keywords']
    for sector in ['Energy', 'Technology', 'Healthcare']:
        if sector in sector_keywords:
            print(f"\n{sector}:")
            top_keywords = sector_keywords[sector].most_common(10)
            for keyword, count in top_keywords:
                returns = keyword_returns[keyword]
                avg_return = sum(returns) / len(returns) if returns else 0
                print(f"  {keyword:<35} {count:>5}x  (avg {avg_return:>6.2f}%)")

    print()
    print("=" * 80)


def main():
    outcomes_path = Path("data/moa/outcomes.jsonl")
    rejected_items_path = Path("data/rejected_items.jsonl")

    if not outcomes_path.exists():
        print(f"ERROR: {outcomes_path} not found")
        return 1

    if not rejected_items_path.exists():
        print(f"ERROR: {rejected_items_path} not found")
        print("Proceeding with outcomes-only analysis...")
        rejected_items = {}
    else:
        print(f"Loading rejected items from {rejected_items_path}...")
        rejected_items = load_rejected_items(rejected_items_path)
        print(f"Loaded {len(rejected_items):,} rejected items")

    print(f"Loading outcomes from {outcomes_path}...")
    outcomes = load_outcomes(outcomes_path)
    print(f"Loaded {len(outcomes):,} outcomes")
    print()

    # Analyze keywords
    analysis = analyze_missed_opportunity_keywords(outcomes, rejected_items)

    # Print report
    print_keyword_analysis(analysis)

    # Save raw data for further analysis
    output_path = Path("data/moa/keyword_analysis.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert defaultdict to regular dict for JSON serialization
    output_data = {
        'keyword_frequency': dict(analysis['keyword_frequency']),
        'keyword_avg_returns': {
            k: sum(v)/len(v) if v else 0
            for k, v in analysis['keyword_returns'].items()
        },
        'sector_keywords': {
            sector: dict(keywords)
            for sector, keywords in analysis['sector_keywords'].items()
        },
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nRaw analysis saved to: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
