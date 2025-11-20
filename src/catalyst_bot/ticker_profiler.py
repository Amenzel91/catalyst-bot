"""
Ticker-Specific Keyword Profile System

This module builds and maintains per-ticker keyword affinity profiles to improve
classification precision for frequently traded stocks. Different stocks respond
differently to the same catalysts (e.g., "FDA approval" → biotech vs device companies).

Expected Impact: 40% improvement for frequently traded tickers
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

from .logging_utils import get_logger

log = get_logger("ticker_profiler")

# Configuration
MIN_TICKER_OBSERVATIONS = 5  # Minimum observations before creating profile
PROFILE_CACHE_TTL_DAYS = 7  # Profile cache time-to-live
DEFAULT_KEYWORD_AFFINITY = 1.0  # Default multiplier when no profile exists


class TickerProfiler:
    """
    Builds and maintains ticker-specific keyword affinity profiles.

    Profiles track which keywords historically predict success for specific tickers,
    allowing for ticker-specific weight adjustments.

    Example:
        - "FDA approval" for ABCD (biotech) → high affinity (2.5x multiplier)
        - "FDA approval" for XYZ (medical device) → medium affinity (1.2x multiplier)
        - "earnings beat" for TECH (tech stock) → low affinity (0.8x multiplier)
    """

    def __init__(self, data_dir: Path = None):
        """
        Initialize ticker profiler.

        Args:
            data_dir: Directory for storing ticker profiles (default: data/ticker_profiles)
        """
        if data_dir is None:
            self.data_dir = Path("data/ticker_profiles")
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.profiles_path = self.data_dir / "ticker_profiles.json"
        self.profiles_cache: Dict[str, Dict] = {}
        self.cache_loaded_at: Optional[datetime] = None

        # Load profiles on initialization
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load ticker profiles from disk into memory cache."""
        if not self.profiles_path.exists():
            log.info("ticker_profiles_not_found creating_new")
            self.profiles_cache = {}
            self.cache_loaded_at = datetime.now(timezone.utc)
            return

        try:
            with open(self.profiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.profiles_cache = data.get("profiles", {})
            self.cache_loaded_at = datetime.now(timezone.utc)

            log.info(f"ticker_profiles_loaded count={len(self.profiles_cache)}")
        except Exception as e:
            log.error(f"ticker_profiles_load_failed err={e.__class__.__name__}", exc_info=True)
            self.profiles_cache = {}
            self.cache_loaded_at = datetime.now(timezone.utc)

    def _save_profiles(self) -> None:
        """Save ticker profiles to disk."""
        try:
            data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "profiles_count": len(self.profiles_cache),
                "profiles": self.profiles_cache,
            }

            with open(self.profiles_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            log.info(f"ticker_profiles_saved count={len(self.profiles_cache)}")
        except Exception as e:
            log.error(f"ticker_profiles_save_failed err={e.__class__.__name__}", exc_info=True)

    def get_ticker_multiplier(
        self,
        ticker: str,
        keywords: List[str],
        sector: Optional[str] = None
    ) -> float:
        """
        Get ticker-specific keyword affinity multiplier.

        Args:
            ticker: Stock ticker symbol
            keywords: List of keywords in the news item
            sector: Optional sector for fallback (e.g., "Technology")

        Returns:
            Multiplier to apply to classification score (0.5 to 2.5)

        Example:
            >>> profiler.get_ticker_multiplier("ABCD", ["fda approval"], "Healthcare")
            2.3  # High affinity - biotech with FDA catalyst
        """
        # Reload cache if stale
        if self.cache_loaded_at:
            cache_age = datetime.now(timezone.utc) - self.cache_loaded_at
            if cache_age > timedelta(days=PROFILE_CACHE_TTL_DAYS):
                log.info("ticker_profiles_cache_stale reloading")
                self._load_profiles()

        # Get ticker profile
        profile = self.profiles_cache.get(ticker.upper())

        if not profile:
            # No profile exists - use sector fallback if available
            if sector:
                return self._get_sector_fallback_multiplier(sector, keywords)

            # No profile, no sector - use default
            return DEFAULT_KEYWORD_AFFINITY

        # Check if profile has enough observations
        if profile.get("observation_count", 0) < MIN_TICKER_OBSERVATIONS:
            log.debug(f"ticker_profile_insufficient_data ticker={ticker} count={profile.get('observation_count')}")
            return DEFAULT_KEYWORD_AFFINITY

        # Calculate multiplier based on keyword affinity
        keyword_affinities = profile.get("keyword_affinities", {})

        # Get affinity for each keyword, weighted by historical success rate
        total_affinity = 0.0
        matched_keywords = 0

        for keyword in keywords:
            keyword_lower = keyword.lower()

            if keyword_lower in keyword_affinities:
                affinity_data = keyword_affinities[keyword_lower]

                # Affinity score = success_rate * avg_return_boost
                success_rate = affinity_data.get("success_rate", 0.5)
                avg_return = affinity_data.get("avg_return_pct", 0.0)

                # Convert to multiplier (0.5 to 2.5 range)
                affinity_score = success_rate * (1.0 + (avg_return / 50.0))
                affinity_score = max(0.5, min(2.5, affinity_score))

                total_affinity += affinity_score
                matched_keywords += 1

        if matched_keywords == 0:
            # No keyword matches - use ticker baseline
            return profile.get("baseline_multiplier", DEFAULT_KEYWORD_AFFINITY)

        # Average affinity across matched keywords
        multiplier = total_affinity / matched_keywords

        log.debug(
            f"ticker_multiplier_calculated ticker={ticker} matched_kw={matched_keywords} "
            f"multiplier={multiplier:.2f}"
        )

        return round(multiplier, 2)

    def _get_sector_fallback_multiplier(self, sector: str, keywords: List[str]) -> float:
        """
        Get sector-level keyword affinity when no ticker profile exists.

        Args:
            sector: Sector name (e.g., "Healthcare", "Technology")
            keywords: List of keywords

        Returns:
            Sector-based multiplier
        """
        # Look for sector profile in cache
        sector_key = f"SECTOR_{sector.upper()}"
        sector_profile = self.profiles_cache.get(sector_key)

        if not sector_profile:
            return DEFAULT_KEYWORD_AFFINITY

        # Same logic as ticker multiplier
        keyword_affinities = sector_profile.get("keyword_affinities", {})

        total_affinity = 0.0
        matched_keywords = 0

        for keyword in keywords:
            keyword_lower = keyword.lower()

            if keyword_lower in keyword_affinities:
                affinity_data = keyword_affinities[keyword_lower]
                success_rate = affinity_data.get("success_rate", 0.5)
                avg_return = affinity_data.get("avg_return_pct", 0.0)

                affinity_score = success_rate * (1.0 + (avg_return / 50.0))
                affinity_score = max(0.5, min(2.5, affinity_score))

                total_affinity += affinity_score
                matched_keywords += 1

        if matched_keywords == 0:
            return DEFAULT_KEYWORD_AFFINITY

        multiplier = total_affinity / matched_keywords
        return round(multiplier, 2)

    def build_profiles_from_outcomes(
        self,
        outcomes: List[Dict[str, Any]],
        accepted_items: List[Dict[str, Any]] = None
    ) -> int:
        """
        Build ticker profiles from historical outcomes.

        Analyzes MOA outcomes and (optionally) accepted items to determine
        which keywords predict success for specific tickers.

        Args:
            outcomes: List of MOA outcome dictionaries
            accepted_items: Optional list of accepted item outcomes

        Returns:
            Number of profiles created/updated
        """
        ticker_data = defaultdict(lambda: {
            "observations": [],
            "keyword_outcomes": defaultdict(lambda: {"successes": 0, "failures": 0, "total_return": 0.0}),
            "observation_count": 0
        })

        # Process MOA outcomes (missed opportunities)
        for outcome in outcomes:
            ticker = outcome.get("ticker")
            if not ticker:
                continue

            keywords = outcome.get("cls", {}).get("keywords", [])
            max_return = outcome.get("max_return_pct", 0.0)
            is_success = max_return >= 10.0  # SUCCESS_THRESHOLD_PCT

            ticker_data[ticker]["observation_count"] += 1
            ticker_data[ticker]["observations"].append({
                "keywords": keywords,
                "return_pct": max_return,
                "is_success": is_success
            })

            # Track keyword outcomes
            for keyword in keywords:
                kw_lower = keyword.lower()
                ticker_data[ticker]["keyword_outcomes"][kw_lower]["total_return"] += max_return

                if is_success:
                    ticker_data[ticker]["keyword_outcomes"][kw_lower]["successes"] += 1
                else:
                    ticker_data[ticker]["keyword_outcomes"][kw_lower]["failures"] += 1

        # Process accepted items (if provided)
        if accepted_items:
            for item in accepted_items:
                ticker = item.get("ticker")
                if not ticker:
                    continue

                keywords = item.get("cls", {}).get("keywords", [])

                # Assuming accepted items have outcome data
                max_return = item.get("max_return_pct", 0.0)
                is_success = max_return >= 5.0  # Lower threshold for accepted items

                ticker_data[ticker]["observation_count"] += 1
                ticker_data[ticker]["observations"].append({
                    "keywords": keywords,
                    "return_pct": max_return,
                    "is_success": is_success
                })

                for keyword in keywords:
                    kw_lower = keyword.lower()
                    ticker_data[ticker]["keyword_outcomes"][kw_lower]["total_return"] += max_return

                    if is_success:
                        ticker_data[ticker]["keyword_outcomes"][kw_lower]["successes"] += 1
                    else:
                        ticker_data[ticker]["keyword_outcomes"][kw_lower]["failures"] += 1

        # Build profiles
        profiles_updated = 0

        for ticker, data in ticker_data.items():
            if data["observation_count"] < MIN_TICKER_OBSERVATIONS:
                continue

            # Calculate keyword affinities
            keyword_affinities = {}

            for keyword, outcome_data in data["keyword_outcomes"].items():
                total = outcome_data["successes"] + outcome_data["failures"]

                if total >= 3:  # Minimum 3 observations per keyword
                    success_rate = outcome_data["successes"] / total
                    avg_return = outcome_data["total_return"] / total

                    keyword_affinities[keyword] = {
                        "success_rate": round(success_rate, 2),
                        "avg_return_pct": round(avg_return, 2),
                        "occurrences": total
                    }

            # Calculate baseline multiplier (average success rate across all keywords)
            all_success_rates = [kw["success_rate"] for kw in keyword_affinities.values()]
            baseline_multiplier = (
                sum(all_success_rates) / len(all_success_rates)
                if all_success_rates
                else DEFAULT_KEYWORD_AFFINITY
            )

            # Store profile
            self.profiles_cache[ticker] = {
                "ticker": ticker,
                "observation_count": data["observation_count"],
                "keyword_affinities": keyword_affinities,
                "baseline_multiplier": round(baseline_multiplier, 2),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

            profiles_updated += 1

        # Save profiles
        if profiles_updated > 0:
            self._save_profiles()

        log.info(f"ticker_profiles_built profiles_updated={profiles_updated}")
        return profiles_updated

    def build_sector_profiles(
        self,
        outcomes: List[Dict[str, Any]],
        sector_mapping: Dict[str, str]
    ) -> int:
        """
        Build sector-level profiles for tickers without individual profiles.

        Args:
            outcomes: List of MOA outcome dictionaries
            sector_mapping: Dict mapping ticker → sector (e.g., {"ABCD": "Healthcare"})

        Returns:
            Number of sector profiles created/updated
        """
        sector_data = defaultdict(lambda: {
            "observations": [],
            "keyword_outcomes": defaultdict(lambda: {"successes": 0, "failures": 0, "total_return": 0.0}),
            "observation_count": 0
        })

        # Aggregate by sector
        for outcome in outcomes:
            ticker = outcome.get("ticker")
            if not ticker:
                continue

            sector = sector_mapping.get(ticker)
            if not sector:
                continue

            keywords = outcome.get("cls", {}).get("keywords", [])
            max_return = outcome.get("max_return_pct", 0.0)
            is_success = max_return >= 10.0

            sector_data[sector]["observation_count"] += 1

            for keyword in keywords:
                kw_lower = keyword.lower()
                sector_data[sector]["keyword_outcomes"][kw_lower]["total_return"] += max_return

                if is_success:
                    sector_data[sector]["keyword_outcomes"][kw_lower]["successes"] += 1
                else:
                    sector_data[sector]["keyword_outcomes"][kw_lower]["failures"] += 1

        # Build sector profiles (same logic as ticker profiles)
        profiles_updated = 0

        for sector, data in sector_data.items():
            if data["observation_count"] < MIN_TICKER_OBSERVATIONS * 2:  # Higher threshold for sectors
                continue

            keyword_affinities = {}

            for keyword, outcome_data in data["keyword_outcomes"].items():
                total = outcome_data["successes"] + outcome_data["failures"]

                if total >= 5:  # Higher threshold for sector-level keywords
                    success_rate = outcome_data["successes"] / total
                    avg_return = outcome_data["total_return"] / total

                    keyword_affinities[keyword] = {
                        "success_rate": round(success_rate, 2),
                        "avg_return_pct": round(avg_return, 2),
                        "occurrences": total
                    }

            # Store sector profile with SECTOR_ prefix
            sector_key = f"SECTOR_{sector.upper()}"

            self.profiles_cache[sector_key] = {
                "sector": sector,
                "observation_count": data["observation_count"],
                "keyword_affinities": keyword_affinities,
                "baseline_multiplier": DEFAULT_KEYWORD_AFFINITY,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

            profiles_updated += 1

        if profiles_updated > 0:
            self._save_profiles()

        log.info(f"sector_profiles_built profiles_updated={profiles_updated}")
        return profiles_updated

    def get_profile(self, ticker: str) -> Optional[Dict]:
        """
        Get full profile for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Profile dictionary or None if doesn't exist
        """
        return self.profiles_cache.get(ticker.upper())

    def get_top_tickers(self, limit: int = 20) -> List[Dict]:
        """
        Get top N tickers by observation count.

        Args:
            limit: Maximum number of tickers to return

        Returns:
            List of ticker profile dictionaries sorted by observation count
        """
        # Filter out SECTOR_ profiles
        ticker_profiles = [
            profile for ticker, profile in self.profiles_cache.items()
            if not ticker.startswith("SECTOR_")
        ]

        # Sort by observation count
        sorted_profiles = sorted(
            ticker_profiles,
            key=lambda x: x.get("observation_count", 0),
            reverse=True
        )

        return sorted_profiles[:limit]


# Global profiler instance
_PROFILER_INSTANCE: Optional[TickerProfiler] = None


def get_ticker_profiler() -> TickerProfiler:
    """
    Get or create global ticker profiler instance.

    Returns:
        TickerProfiler singleton
    """
    global _PROFILER_INSTANCE

    if _PROFILER_INSTANCE is None:
        _PROFILER_INSTANCE = TickerProfiler()

    return _PROFILER_INSTANCE
