"""Source credibility scoring system.

This module implements a 3-tier source credibility system that weights
news sources based on reliability and quality. The credibility weights
are applied during classification to prioritize high-quality sources
and de-emphasize low-quality or unverified sources.

Tier Structure:
    - Tier 1 (HIGH, weight 1.5x): Regulatory filings and premium financial news
        * SEC.gov - Official regulatory filings
        * Bloomberg, Reuters, WSJ, FT - Premium financial journalism

    - Tier 2 (MEDIUM, weight 1.0x): Professional PR wires and financial news
        * GlobeNewswire, Business Wire, PR Newswire - Professional PR distribution
        * MarketWatch - Established financial news

    - Tier 3 (LOW, weight 0.5x): Unknown sources and unverified outlets
        * Any domain not explicitly listed above
        * Blogs, personal sites, unverified sources

Usage:
    >>> from catalyst_bot.source_credibility import get_source_weight
    >>> weight = get_source_weight("https://www.sec.gov/filing.html")
    >>> print(weight)  # 1.5
    >>> weight = get_source_weight("https://unknown-blog.com/article")
    >>> print(weight)  # 0.5
"""

from __future__ import annotations

from typing import Dict
from urllib.parse import urlparse

# Tier definitions with metadata
CREDIBILITY_TIERS: Dict[str, Dict[str, any]] = {
    # ===================================================================
    # TIER 1: HIGH CREDIBILITY (weight 1.5x)
    # ===================================================================
    # Regulatory sources - Official government filings and disclosures
    "sec.gov": {
        "tier": 1,
        "weight": 1.5,
        "category": "regulatory",
        "description": "U.S. Securities and Exchange Commission official filings",
    },
    # Premium financial news - Subscription-based, fact-checked journalism
    "bloomberg.com": {
        "tier": 1,
        "weight": 1.5,
        "category": "premium_news",
        "description": "Bloomberg Terminal news and analysis",
    },
    "reuters.com": {
        "tier": 1,
        "weight": 1.5,
        "category": "premium_news",
        "description": "Reuters financial news and data",
    },
    "wsj.com": {
        "tier": 1,
        "weight": 1.5,
        "category": "premium_news",
        "description": "Wall Street Journal",
    },
    "ft.com": {
        "tier": 1,
        "weight": 1.5,
        "category": "premium_news",
        "description": "Financial Times",
    },
    # ===================================================================
    # TIER 2: MEDIUM CREDIBILITY (weight 1.0x)
    # ===================================================================
    # Professional PR wires - Paid distribution, verified company sources
    "globenewswire.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "pr_wire",
        "description": "GlobeNewswire press release distribution",
    },
    "businesswire.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "pr_wire",
        "description": "Business Wire press release distribution",
    },
    "prnewswire.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "pr_wire",
        "description": "PR Newswire press release distribution",
    },
    "accesswire.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "pr_wire",
        "description": "AccessWire press release distribution",
    },
    # Financial news outlets - Established but less stringent than premium
    "marketwatch.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "financial_news",
        "description": "MarketWatch financial news",
    },
    "cnbc.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "financial_news",
        "description": "CNBC financial news",
    },
    "benzinga.com": {
        "tier": 2,
        "weight": 1.0,
        "category": "financial_news",
        "description": "Benzinga financial news",
    },
    # ===================================================================
    # TIER 3: LOW CREDIBILITY (weight 0.5x)
    # ===================================================================
    # Any unknown domain defaults to tier 3 (no explicit entries needed)
    # Examples include: personal blogs, unverified sources, promotional sites
}

# Default tier for unknown sources
DEFAULT_TIER = 3
DEFAULT_WEIGHT = 0.5
DEFAULT_CATEGORY = "unknown"


def extract_domain(url: str) -> str:
    """Extract the base domain from a URL.

    Handles various URL formats including:
        - Full URLs: https://www.example.com/path
        - URLs without protocol: www.example.com/path
        - URLs with subdomains: news.example.com
        - Bare domains: example.com

    Args:
        url: URL or domain string to parse

    Returns:
        Lowercase base domain (e.g., "example.com").
        Returns empty string if URL is invalid or empty.

    Examples:
        >>> extract_domain("https://www.sec.gov/filing.html")
        'sec.gov'
        >>> extract_domain("news.bloomberg.com/article")
        'bloomberg.com'
        >>> extract_domain("www.example.com")
        'example.com'
        >>> extract_domain("invalid")
        ''
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip().lower()
    if not url:
        return ""

    # Add scheme if missing (required for urlparse)
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or parsed.netloc

        if not hostname:
            return ""

        # Extract base domain (handle www. and subdomains)
        # e.g., "www.sec.gov" -> "sec.gov"
        # e.g., "news.bloomberg.com" -> "bloomberg.com"
        parts = hostname.split(".")

        # If we have at least 2 parts (domain.tld), take the last 2
        if len(parts) >= 2:
            # Handle special TLDs (co.uk, com.au, etc.)
            # For simplicity, we'll take the last 2 parts for most cases
            return ".".join(parts[-2:])

        return hostname

    except Exception:
        return ""


def get_source_tier(url: str) -> int:
    """Get the credibility tier for a source URL.

    Args:
        url: Source URL or domain to evaluate

    Returns:
        Integer tier (1=HIGH, 2=MEDIUM, 3=LOW)

    Examples:
        >>> get_source_tier("https://www.sec.gov/filing")
        1
        >>> get_source_tier("https://www.globenewswire.com/news")
        2
        >>> get_source_tier("https://unknown-blog.com/post")
        3
    """
    domain = extract_domain(url)
    if not domain:
        return DEFAULT_TIER

    # Look up domain in tier definitions
    tier_info = CREDIBILITY_TIERS.get(domain)
    if tier_info:
        return tier_info["tier"]

    return DEFAULT_TIER


def get_source_weight(url: str) -> float:
    """Get the credibility weight multiplier for a source URL.

    The weight is applied as a multiplier to classification scores,
    allowing high-credibility sources to have more impact while
    dampening the influence of low-credibility sources.

    Args:
        url: Source URL or domain to evaluate

    Returns:
        Float weight multiplier (1.5 for tier 1, 1.0 for tier 2, 0.5 for tier 3)

    Examples:
        >>> get_source_weight("https://www.bloomberg.com/news/article")
        1.5
        >>> get_source_weight("https://www.businesswire.com/news")
        1.0
        >>> get_source_weight("https://random-site.com/post")
        0.5
    """
    domain = extract_domain(url)
    if not domain:
        return DEFAULT_WEIGHT

    # Look up domain in tier definitions
    tier_info = CREDIBILITY_TIERS.get(domain)
    if tier_info:
        return float(tier_info["weight"])

    return DEFAULT_WEIGHT


def get_source_category(url: str) -> str:
    """Get the source category for a URL.

    Categories help classify the type of source:
        - regulatory: Official government sources
        - premium_news: High-quality subscription journalism
        - pr_wire: Professional press release distribution
        - financial_news: Established financial news outlets
        - unknown: Unverified or unrecognized sources

    Args:
        url: Source URL or domain to evaluate

    Returns:
        String category name

    Examples:
        >>> get_source_category("https://www.sec.gov/filing")
        'regulatory'
        >>> get_source_category("https://www.globenewswire.com/news")
        'pr_wire'
        >>> get_source_category("https://random-site.com/post")
        'unknown'
    """
    domain = extract_domain(url)
    if not domain:
        return DEFAULT_CATEGORY

    # Look up domain in tier definitions
    tier_info = CREDIBILITY_TIERS.get(domain)
    if tier_info:
        return tier_info["category"]

    return DEFAULT_CATEGORY


def get_tier_summary() -> Dict[int, Dict[str, any]]:
    """Get a summary of all credibility tiers and their sources.

    Returns:
        Dictionary mapping tier number to tier metadata:
            - weight: Multiplier for this tier
            - sources: List of domains in this tier
            - categories: List of unique categories in this tier

    Example:
        >>> summary = get_tier_summary()
        >>> print(summary[1]["weight"])
        1.5
        >>> print(summary[1]["sources"][:2])
        ['sec.gov', 'bloomberg.com']
    """
    tiers: Dict[int, Dict[str, any]] = {
        1: {"weight": 1.5, "sources": [], "categories": set()},
        2: {"weight": 1.0, "sources": [], "categories": set()},
        3: {"weight": 0.5, "sources": ["unknown"], "categories": {"unknown"}},
    }

    # Group sources by tier
    for domain, info in CREDIBILITY_TIERS.items():
        tier = info["tier"]
        tiers[tier]["sources"].append(domain)
        tiers[tier]["categories"].add(info["category"])

    # Convert category sets to sorted lists
    for tier_data in tiers.values():
        tier_data["categories"] = sorted(tier_data["categories"])

    return tiers
