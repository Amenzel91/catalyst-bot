"""
Text mining module for extracting keyword candidates from news titles.

This module provides functionality to:
- Extract n-grams (1-4 word phrases) from text
- Filter out stop words and common non-catalyst phrases
- Count and rank keyword candidates by frequency
- Calculate statistical scores for phrase relevance
"""

import re
from typing import List, Dict, Tuple, Set
from collections import Counter
import logging

logger = logging.getLogger(__name__)


# Stop words to filter out
STOP_WORDS = {
    # Common words
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'can', 'its', 'it', 'this',
    'that', 'these', 'those', 'their', 'them', 'they', 'we', 'our', 'us',
    # Business common words
    'company', 'companies', 'inc', 'corp', 'ltd', 'llc', 'announces',
    'announced', 'reports', 'reported', 'says', 'said', 'plans', 'expected',
    'following', 'after', 'over', 'under', 'between', 'through', 'during',
    'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'again',
    'further', 'then', 'once'
}

# Important abbreviations and terms to preserve (case-sensitive)
PRESERVE_TERMS = {
    'FDA', 'SEC', 'NASDAQ', 'NYSE', 'IPO', 'M&A', 'CEO', 'CFO', 'CTO',
    'Phase I', 'Phase II', 'Phase III', 'Phase 1', 'Phase 2', 'Phase 3',
    '8-K', '10-K', '10-Q', '424B5', 'S-1', 'S-3', 'Q1', 'Q2', 'Q3', 'Q4',
    'EPS', 'P/E', 'ROI', 'EBITDA', 'YoY', 'QoQ', 'AI', 'ML', 'API', 'SaaS',
    'EV', 'AV', 'R&D', 'IP', 'NDA', 'BLA', 'IND'
}

# Non-catalyst phrases to filter out
NON_CATALYST_PHRASES = {
    'press release', 'news release', 'business wire', 'globe newswire',
    'pr newswire', 'accesswire', 'marketwatch', 'seeking alpha',
    'yahoo finance', 'stock market', 'wall street', 'new york',
    'san francisco', 'los angeles', 'united states', 'north america'
}


def normalize_text(text: str) -> str:
    """
    Normalize text while preserving important abbreviations.

    Args:
        text: Input text to normalize

    Returns:
        Normalized text with preserved important terms
    """
    if not text:
        return ""

    # Create a mapping of preserved terms to placeholders
    preserved_map = {}
    temp_text = text

    for term in PRESERVE_TERMS:
        if term in temp_text:
            placeholder = f"__PRESERVED_{len(preserved_map)}__"
            preserved_map[placeholder] = term
            temp_text = temp_text.replace(term, placeholder)

    # Convert to lowercase
    temp_text = temp_text.lower()

    # Remove possessives
    temp_text = re.sub(r"'s\b", '', temp_text)

    # Replace hyphens with spaces (except in preserved terms)
    temp_text = temp_text.replace('-', ' ')

    # Remove punctuation except for preserved placeholders
    # Keep only alphanumeric, spaces, and underscores (for placeholders)
    temp_text = re.sub(r'[^a-z0-9\s_]', ' ', temp_text)

    # Normalize whitespace
    temp_text = ' '.join(temp_text.split())

    # Restore preserved terms (in lowercase for consistency)
    for placeholder, original in preserved_map.items():
        temp_text = temp_text.replace(placeholder.lower(), original.lower())

    return temp_text


def is_valid_ngram(ngram: str, tokens: List[str]) -> bool:
    """
    Check if an n-gram is valid (not stop words only, not non-catalyst phrase).

    Args:
        ngram: The n-gram string to check
        tokens: List of tokens in the n-gram

    Returns:
        True if n-gram is valid, False otherwise
    """
    # Check if it's a non-catalyst phrase
    if ngram in NON_CATALYST_PHRASES:
        return False

    # Single token check
    if len(tokens) == 1:
        token = tokens[0]
        # Keep if not a stop word, or if it's very short (likely an abbreviation)
        if token in STOP_WORDS and len(token) > 2:
            return False
        # Filter out purely numeric tokens
        if token.isdigit():
            return False
        return True

    # Multi-token check
    # At least one token should not be a stop word
    has_non_stop = any(token not in STOP_WORDS for token in tokens)
    if not has_non_stop:
        return False

    # Should not start or end with a stop word (unless it's a preserved term)
    if tokens[0] in STOP_WORDS and tokens[0] not in [t.lower() for t in PRESERVE_TERMS]:
        return False
    if tokens[-1] in STOP_WORDS and tokens[-1] not in [t.lower() for t in PRESERVE_TERMS]:
        return False

    return True


def extract_ngrams(text: str, n: int) -> List[str]:
    """
    Extract all n-grams of size n from text.

    Args:
        text: Input text
        n: Size of n-grams to extract (1 for unigrams, 2 for bigrams, etc.)

    Returns:
        List of n-gram strings
    """
    if not text or n < 1:
        return []

    # Normalize and tokenize
    normalized = normalize_text(text)
    tokens = normalized.split()

    if len(tokens) < n:
        return []

    ngrams = []
    for i in range(len(tokens) - n + 1):
        ngram_tokens = tokens[i:i + n]
        ngram = ' '.join(ngram_tokens)

        # Validate n-gram
        if is_valid_ngram(ngram, ngram_tokens):
            ngrams.append(ngram)

    return ngrams


def extract_all_ngrams(text: str, max_n: int = 4) -> List[str]:
    """
    Extract all n-grams from 1-gram to max_n-gram from text.

    Args:
        text: Input text
        max_n: Maximum n-gram size

    Returns:
        List of all n-grams
    """
    all_ngrams = []
    for n in range(1, max_n + 1):
        all_ngrams.extend(extract_ngrams(text, n))
    return all_ngrams


def mine_keyword_candidates(
    titles: List[str],
    min_occurrences: int = 5,
    max_ngram_size: int = 4
) -> Dict[str, int]:
    """
    Mine keyword candidates from titles.

    Args:
        titles: List of title strings
        min_occurrences: Minimum frequency to consider
        max_ngram_size: Maximum n-gram size (1-4)

    Returns:
        Dict mapping candidate phrase -> occurrence count, sorted by count descending
    """
    if not titles:
        return {}

    # Extract all n-grams from all titles
    all_ngrams = []
    for title in titles:
        if title:
            all_ngrams.extend(extract_all_ngrams(title, max_n=max_ngram_size))

    # Count occurrences
    ngram_counts = Counter(all_ngrams)

    # Filter by minimum occurrences
    candidates = {
        ngram: count
        for ngram, count in ngram_counts.items()
        if count >= min_occurrences
    }

    # Sort by count descending
    sorted_candidates = dict(
        sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    )

    logger.info(f"Extracted {len(sorted_candidates)} keyword candidates from {len(titles)} titles")

    return sorted_candidates


def calculate_phrase_score(
    phrase: str,
    positive_count: int,
    negative_count: int,
    total_positive: int,
    total_negative: int
) -> float:
    """
    Calculate statistical score for phrase being a good keyword.
    Uses lift ratio: (positive_rate / negative_rate).

    A score > 1.0 means the phrase appears more frequently in positive items.
    A score < 1.0 means the phrase appears more frequently in negative items.

    Args:
        phrase: The phrase to score
        positive_count: Number of positive items containing this phrase
        negative_count: Number of negative items containing this phrase
        total_positive: Total number of positive items
        total_negative: Total number of negative items

    Returns:
        Lift ratio score. Returns 0.0 if calculation is invalid.
    """
    if total_positive <= 0 or total_negative <= 0:
        logger.warning(f"Invalid totals for phrase scoring: pos={total_positive}, neg={total_negative}")
        return 0.0

    # Calculate rates
    positive_rate = positive_count / total_positive
    negative_rate = negative_count / total_negative

    # Avoid division by zero
    # If phrase never appears in negative items, it's a strong positive indicator
    if negative_rate == 0:
        if positive_rate > 0:
            # Return a high score (10x multiplier as proxy for "infinite" lift)
            return 10.0
        else:
            # Phrase appears nowhere
            return 0.0

    # Calculate lift ratio
    lift = positive_rate / negative_rate

    return lift


def mine_discriminative_keywords(
    positive_titles: List[str],
    negative_titles: List[str],
    min_occurrences: int = 3,
    min_lift: float = 2.0,
    max_ngram_size: int = 4
) -> List[Tuple[str, float, int, int]]:
    """
    Mine keywords that discriminate between positive and negative titles.

    Args:
        positive_titles: Titles from positive/catalyst items
        negative_titles: Titles from negative/non-catalyst items
        min_occurrences: Minimum occurrences in positive set
        min_lift: Minimum lift ratio to consider (positive_rate / negative_rate)
        max_ngram_size: Maximum n-gram size

    Returns:
        List of tuples (phrase, lift_score, positive_count, negative_count),
        sorted by lift score descending
    """
    if not positive_titles or not negative_titles:
        logger.warning("Need both positive and negative titles for discriminative mining")
        return []

    # Extract n-grams from both sets
    positive_ngrams = []
    for title in positive_titles:
        if title:
            positive_ngrams.extend(extract_all_ngrams(title, max_n=max_ngram_size))

    negative_ngrams = []
    for title in negative_titles:
        if title:
            negative_ngrams.extend(extract_all_ngrams(title, max_n=max_ngram_size))

    # Count occurrences in each set
    positive_counts = Counter(positive_ngrams)
    negative_counts = Counter(negative_ngrams)

    # Get all unique phrases that meet minimum occurrence threshold in positive set
    candidates = {
        phrase for phrase, count in positive_counts.items()
        if count >= min_occurrences
    }

    # Calculate lift scores
    total_positive = len(positive_titles)
    total_negative = len(negative_titles)

    scored_phrases = []
    for phrase in candidates:
        pos_count = positive_counts.get(phrase, 0)
        neg_count = negative_counts.get(phrase, 0)

        lift = calculate_phrase_score(
            phrase, pos_count, neg_count, total_positive, total_negative
        )

        if lift >= min_lift:
            scored_phrases.append((phrase, lift, pos_count, neg_count))

    # Sort by lift score descending
    scored_phrases.sort(key=lambda x: x[1], reverse=True)

    logger.info(
        f"Found {len(scored_phrases)} discriminative keywords "
        f"from {len(positive_titles)} positive and {len(negative_titles)} negative titles"
    )

    return scored_phrases


def get_phrase_contexts(
    titles: List[str],
    phrase: str,
    max_contexts: int = 10
) -> List[str]:
    """
    Get example contexts where a phrase appears in titles.

    Args:
        titles: List of title strings to search
        phrase: Phrase to find contexts for
        max_contexts: Maximum number of contexts to return

    Returns:
        List of titles containing the phrase (up to max_contexts)
    """
    contexts = []
    phrase_lower = phrase.lower()

    for title in titles:
        if not title:
            continue

        # Check if phrase appears in normalized version
        normalized = normalize_text(title)
        if phrase_lower in normalized:
            contexts.append(title)

            if len(contexts) >= max_contexts:
                break

    return contexts


def filter_subsumed_phrases(
    keyword_counts: Dict[str, int],
    subsume_threshold: float = 0.9
) -> Dict[str, int]:
    """
    Filter out n-grams that are subsumed by longer n-grams.

    For example, if "fda approval" appears 100 times and "fda" appears 105 times,
    "fda" is mostly subsumed by "fda approval" and can be filtered.

    Args:
        keyword_counts: Dict of phrase -> count
        subsume_threshold: If shorter_count / longer_count ratio is above this,
                          keep the shorter phrase. Otherwise filter it.

    Returns:
        Filtered dict with subsumed phrases removed
    """
    # Sort phrases by length (longer first) then by count (higher first)
    sorted_phrases = sorted(
        keyword_counts.items(),
        key=lambda x: (len(x[0].split()), x[1]),
        reverse=True
    )

    filtered = {}

    for phrase, count in sorted_phrases:
        is_subsumed = False

        # Check if this phrase is contained in any longer phrase we've kept
        for kept_phrase in filtered:
            if phrase in kept_phrase:
                # Calculate subsume ratio
                ratio = count / filtered[kept_phrase]

                # If most occurrences are within the longer phrase, skip it
                if ratio >= subsume_threshold:
                    is_subsumed = True
                    break

        if not is_subsumed:
            filtered[phrase] = count

    logger.info(
        f"Filtered {len(keyword_counts) - len(filtered)} subsumed phrases "
        f"({len(filtered)} remaining)"
    )

    return filtered


# Example usage and utilities
def print_keyword_report(
    keyword_counts: Dict[str, int],
    top_n: int = 50,
    group_by_ngram_size: bool = True
) -> None:
    """
    Print a formatted report of keyword candidates.

    Args:
        keyword_counts: Dict of phrase -> count
        top_n: Number of top keywords to show per group
        group_by_ngram_size: Whether to group by n-gram size
    """
    if not keyword_counts:
        print("No keywords found.")
        return

    if group_by_ngram_size:
        # Group by n-gram size
        grouped = {}
        for phrase, count in keyword_counts.items():
            n = len(phrase.split())
            if n not in grouped:
                grouped[n] = []
            grouped[n].append((phrase, count))

        # Print each group
        for n in sorted(grouped.keys()):
            phrases = grouped[n]
            phrases.sort(key=lambda x: x[1], reverse=True)

            print(f"\n{'='*60}")
            print(f"{n}-grams (Top {min(top_n, len(phrases))} of {len(phrases)})")
            print(f"{'='*60}")

            for phrase, count in phrases[:top_n]:
                print(f"{count:5d}  {phrase}")
    else:
        # Just print top N overall
        sorted_keywords = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        print(f"\nTop {min(top_n, len(sorted_keywords))} Keywords")
        print(f"{'='*60}")

        for phrase, count in sorted_keywords[:top_n]:
            n = len(phrase.split())
            print(f"{count:5d}  {phrase} ({n}-gram)")


def print_discriminative_report(
    scored_phrases: List[Tuple[str, float, int, int]],
    top_n: int = 30
) -> None:
    """
    Print a formatted report of discriminative keywords.

    Args:
        scored_phrases: List of (phrase, lift, pos_count, neg_count) tuples
        top_n: Number of top keywords to show
    """
    if not scored_phrases:
        print("No discriminative keywords found.")
        return

    print(f"\nTop {min(top_n, len(scored_phrases))} Discriminative Keywords")
    print(f"{'='*80}")
    print(f"{'Lift':>6}  {'Pos':>4}  {'Neg':>4}  {'Phrase'}")
    print(f"{'-'*80}")

    for phrase, lift, pos_count, neg_count in scored_phrases[:top_n]:
        print(f"{lift:6.2f}  {pos_count:4d}  {neg_count:4d}  {phrase}")
