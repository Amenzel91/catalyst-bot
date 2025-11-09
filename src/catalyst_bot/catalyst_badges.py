# src/catalyst_bot/catalyst_badges.py
"""Catalyst Badge System for Discord Alerts (Wave 2).

This module provides visual badge extraction for key catalysts to make
important triggers instantly recognizable in Discord alerts.
"""

from __future__ import annotations

from typing import List

# Badge definitions for key catalyst types
CATALYST_BADGES = {
    "earnings": "📊 EARNINGS",
    "fda": "💊 FDA NEWS",
    "merger": "🤝 M&A",
    "guidance": "📈 GUIDANCE",
    "sec_filing": "📄 SEC FILING",
    "offering": "💰 OFFERING",
    # Wave 3.4: Offering stage-specific badges
    "offering_closing": "✅ OFFERING - CLOSING",
    "offering_announcement": "💰 OFFERING - ANNOUNCED",
    "offering_pricing": "💵 OFFERING - PRICED",
    "offering_upsize": "📉 OFFERING - UPSIZED",
    "analyst": "🎯 ANALYST",
    "contract": "📝 CONTRACT",
    "partnership": "🤝 PARTNERSHIP",
    "product": "🚀 PRODUCT",
    "clinical": "🧪 CLINICAL",
    "regulatory": "⚖️ REGULATORY",
}

# Keyword patterns for catalyst detection (case-insensitive)
CATALYST_PATTERNS = {
    "earnings": ["earnings", "quarter", "q1", "q2", "q3", "q4", "revenue", "eps", "beat", "miss"],
    "fda": ["fda", "approval", "clinical trial", "phase", "drug", "therapy"],
    "merger": ["merger", "acquisition", "acquires", "m&a", "buyout", "takeover"],
    "guidance": ["guidance", "outlook", "raises", "lowers", "forecast", "projects"],
    "sec_filing": ["8-k", "10-k", "10-q", "s-1", "sec filing", "form"],
    "offering": ["offering", "priced", "upsized", "secondary", "share offering"],
    "analyst": ["rating", "upgrade", "downgrade", "price target", "analyst", "initiate"],
    "contract": ["contract", "deal", "agreement", "award", "wins"],
    "partnership": ["partnership", "collaboration", "joint venture", "partner"],
    "product": ["launch", "product", "release", "unveils", "introduces"],
    "clinical": ["data", "trial results", "patient", "study", "efficacy"],
    "regulatory": ["approval", "clearance", "patent", "granted", "authorized"],
}

# Priority order for badges (higher priority first)
BADGE_PRIORITY = [
    "fda",
    "earnings",
    "merger",
    # Wave 3.4: Stage-specific offering badges take priority over generic
    "offering_closing",      # Highest priority - positive signal
    "offering_upsize",       # Very negative - more dilution
    "offering_pricing",      # Negative - dilution confirmed
    "offering_announcement", # Negative - new dilution
    "offering",              # Generic fallback
    "guidance",
    "analyst",
    "sec_filing",
    "contract",
    "partnership",
    "product",
    "clinical",
    "regulatory",
]


def extract_catalyst_badges(
    classification: dict | None,
    title: str,
    text: str = "",
    max_badges: int = 3,
) -> List[str]:
    """
    Extract catalyst badges from classification results and text content.

    Analyzes both the classification keywords/tags and the title/text to identify
    key catalysts, returning visual badges for display in Discord alerts.

    Args:
        classification: Classification result dict (ScoredItem or dict)
        title: News title/headline
        text: News body/description (optional)
        max_badges: Maximum number of badges to return (default: 3)

    Returns:
        List of badge strings like ["📊 EARNINGS", "📈 GUIDANCE"]

    Example:
        >>> extract_catalyst_badges(
        ...     {"tags": ["earnings", "guidance"]},
        ...     "AAPL beats Q4 earnings, raises guidance"
        ... )
        ['📊 EARNINGS', '📈 GUIDANCE']
    """
    detected_catalysts = set()

    # Normalize text for searching
    combined_text = f"{title} {text}".lower()

    # 1. Check classification tags/keywords first (high confidence)
    if classification:
        tags = []
        if isinstance(classification, dict):
            tags = (
                classification.get("tags")
                or classification.get("keywords")
                or classification.get("keyword_hits")
                or []
            )
        else:
            # Handle ScoredItem dataclass
            tags = (
                getattr(classification, "tags", [])
                or getattr(classification, "keywords", [])
                or getattr(classification, "keyword_hits", [])
                or []
            )

        # Map classification tags to catalyst types
        for tag in tags:
            tag_lower = str(tag).lower()
            # Direct matches
            if tag_lower in CATALYST_BADGES:
                detected_catalysts.add(tag_lower)
            # Pattern-based matches
            for catalyst_type, patterns in CATALYST_PATTERNS.items():
                if tag_lower in patterns or any(p in tag_lower for p in patterns):
                    detected_catalysts.add(catalyst_type)

    # 2. Pattern matching on title and text (moderate confidence)
    for catalyst_type, patterns in CATALYST_PATTERNS.items():
        for pattern in patterns:
            if pattern in combined_text:
                detected_catalysts.add(catalyst_type)
                break  # Found at least one pattern for this catalyst

    # 3. Special case: SEC filing detection from source
    # Check if this is a SEC filing (common pattern in classify.py)
    if classification:
        source = None
        if isinstance(classification, dict):
            # Source might be in the parent item_dict, check common fields
            source = classification.get("source", "")
        else:
            source = getattr(classification, "source", "")

        if source and str(source).lower().startswith("sec_"):
            detected_catalysts.add("sec_filing")

    # 3.5. WAVE 3.4: Offering stage-specific badge detection
    # Check if classification has offering stage metadata
    if classification:
        offering_stage = None
        if isinstance(classification, dict):
            offering_stage = classification.get("offering_stage", "")
        else:
            offering_stage = getattr(classification, "offering_stage", "")

        if offering_stage:
            # Add stage-specific offering badge
            stage_badge_key = f"offering_{offering_stage}"
            detected_catalysts.add(stage_badge_key)
            # Also add generic offering for fallback
            detected_catalysts.add("offering")
        else:
            # No stage detected but offering tags present - use offering_sentiment module
            if "offering" in [str(t).lower() for t in tags]:
                # Try to detect stage from title/text using offering_sentiment module
                try:
                    from .offering_sentiment import detect_offering_stage

                    detection = detect_offering_stage(title, text)
                    if detection:
                        stage, confidence = detection
                        stage_badge_key = f"offering_{stage}"
                        detected_catalysts.add(stage_badge_key)
                        detected_catalysts.add("offering")
                except ImportError:
                    # Module not available, use generic offering badge
                    pass
                except Exception:
                    # Detection failed, use generic offering badge
                    pass

    # 4. Sort by priority and limit to max_badges
    prioritized_catalysts = []
    for catalyst in BADGE_PRIORITY:
        if catalyst in detected_catalysts:
            prioritized_catalysts.append(catalyst)
            if len(prioritized_catalysts) >= max_badges:
                break

    # 5. Convert to badge strings
    badges = [CATALYST_BADGES[c] for c in prioritized_catalysts]

    # 6. If no catalysts detected, return generic news badge
    if not badges:
        return ["📰 NEWS"]

    return badges
