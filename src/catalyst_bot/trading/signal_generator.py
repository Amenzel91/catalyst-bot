"""
Signal generator for converting keyword-scored alerts into trading signals.

This module implements the SignalGenerator class which converts ScoredItem
alerts (from classify.py) into TradingSignal objects (for order_executor.py).
It maps keyword categories to trading actions (BUY/SELL/AVOID/CLOSE) and
calculates position sizing, stop-loss, and take-profit levels.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from ..config import get_settings
from ..execution.order_executor import TradingSignal
from ..logging_utils import get_logger
from ..models import ScoredItem

# Module logger
log = get_logger(__name__)


# Keyword category configurations
# These map keywords to trading parameters based on historical performance
# and risk/reward profiles from backtesting and live trading data.


@dataclass
class KeywordConfig:
    """Configuration for a specific keyword category."""

    action: str  # "buy", "sell", "avoid", "close"
    base_confidence: float  # Base confidence score (0.0-1.0)
    size_multiplier: float  # Position size multiplier (applied to base%)
    stop_loss_pct: float  # Stop loss percentage
    take_profit_pct: float  # Take profit percentage
    rationale: str  # Human-readable explanation


# BUY KEYWORDS - High-conviction bullish signals
BUY_KEYWORDS: Dict[str, KeywordConfig] = {
    "fda": KeywordConfig(
        action="buy",
        base_confidence=0.92,
        size_multiplier=1.6,
        stop_loss_pct=5.0,
        take_profit_pct=12.0,
        rationale="FDA approval = strong catalyst",
    ),
    "merger": KeywordConfig(
        action="buy",
        base_confidence=0.95,
        size_multiplier=2.0,
        stop_loss_pct=4.0,
        take_profit_pct=15.0,
        rationale="Merger/acquisition = high probability event",
    ),
    "partnership": KeywordConfig(
        action="buy",
        base_confidence=0.85,
        size_multiplier=1.4,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        rationale="Strategic partnership = positive catalyst",
    ),
    "trial": KeywordConfig(
        action="buy",
        base_confidence=0.88,
        size_multiplier=1.5,
        stop_loss_pct=6.0,
        take_profit_pct=12.0,
        rationale="Successful trial results = strong move",
    ),
    "clinical": KeywordConfig(
        action="buy",
        base_confidence=0.88,
        size_multiplier=1.5,
        stop_loss_pct=6.0,
        take_profit_pct=12.0,
        rationale="Clinical trial progress = biotech catalyst",
    ),
    "acquisition": KeywordConfig(
        action="buy",
        base_confidence=0.90,
        size_multiplier=1.7,
        stop_loss_pct=4.5,
        take_profit_pct=14.0,
        rationale="Acquisition = growth catalyst",
    ),
    "uplisting": KeywordConfig(
        action="buy",
        base_confidence=0.87,
        size_multiplier=1.3,
        stop_loss_pct=5.5,
        take_profit_pct=11.0,
        rationale="Exchange uplisting = legitimacy boost",
    ),
}

# EXTENDED BUY KEYWORDS - Controlled by FEATURE_EXTENDED_KEYWORDS flag
# These are additional keyword categories that generate trading signals
# when the feature flag is enabled. See KW-1 in implementation plan.
EXTENDED_BUY_KEYWORDS: Dict[str, KeywordConfig] = {
    "earnings": KeywordConfig(
        action="buy",
        base_confidence=0.82,
        size_multiplier=1.3,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        rationale="Positive earnings surprise = momentum catalyst",
    ),
    "guidance": KeywordConfig(
        action="buy",
        base_confidence=0.80,
        size_multiplier=1.2,
        stop_loss_pct=5.5,
        take_profit_pct=9.0,
        rationale="Raised guidance = forward-looking bullish signal",
    ),
    "energy_discovery": KeywordConfig(
        action="buy",
        base_confidence=0.85,
        size_multiplier=1.5,
        stop_loss_pct=6.0,
        take_profit_pct=15.0,
        rationale="Oil/gas discovery = significant asset value increase",
    ),
    "advanced_therapies": KeywordConfig(
        action="buy",
        base_confidence=0.86,
        size_multiplier=1.4,
        stop_loss_pct=6.0,
        take_profit_pct=12.0,
        rationale="Gene/cell therapy progress = biotech moonshot",
    ),
    "tech_contracts": KeywordConfig(
        action="buy",
        base_confidence=0.83,
        size_multiplier=1.3,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        rationale="Government/enterprise contract = revenue catalyst",
    ),
    "ai_quantum": KeywordConfig(
        action="buy",
        base_confidence=0.84,
        size_multiplier=1.4,
        stop_loss_pct=5.5,
        take_profit_pct=12.0,
        rationale="AI/quantum partnership = high-growth sector exposure",
    ),
    "crypto_blockchain": KeywordConfig(
        action="buy",
        base_confidence=0.78,
        size_multiplier=1.2,
        stop_loss_pct=7.0,
        take_profit_pct=15.0,
        rationale="Crypto/blockchain adoption = speculative momentum",
    ),
    "mining_resources": KeywordConfig(
        action="buy",
        base_confidence=0.82,
        size_multiplier=1.3,
        stop_loss_pct=6.0,
        take_profit_pct=12.0,
        rationale="Mineral discovery/feasibility = asset value catalyst",
    ),
    "compliance": KeywordConfig(
        action="buy",
        base_confidence=0.80,
        size_multiplier=1.2,
        stop_loss_pct=5.0,
        take_profit_pct=8.0,
        rationale="Compliance regained = delisting fear removed",
    ),
    "activist_institutional": KeywordConfig(
        action="buy",
        base_confidence=0.81,
        size_multiplier=1.3,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        rationale="Activist/institutional interest = potential catalyst",
    ),
}

# AVOID KEYWORDS - Wait for better entry or skip trade
AVOID_KEYWORDS: List[str] = [
    "offering",
    "dilution",
    "warrant",
    "rs",
    "reverse_split",
    "offering_negative",
    "warrant_negative",
    "dilution_negative",
]

# CLOSE KEYWORDS - Exit positions immediately
CLOSE_KEYWORDS: List[str] = [
    "bankruptcy",
    "delisting",
    "going_concern",
    "fraud",
    "distress_negative",
]


class SignalGenerator:
    """
    Converts keyword-based ScoredItem alerts into TradingSignal objects.

    This class implements the keyword → trading action mapping logic,
    calculating position sizes, stop-loss, and take-profit levels based
    on the keyword category and scoring confidence.

    The signal generator uses configuration from environment variables
    and applies risk management rules to ensure all signals are within
    acceptable risk parameters.

    Example:
        >>> generator = SignalGenerator()
        >>> scored_item = ScoredItem(
        ...     relevance=3.7,
        ...     sentiment=0.85,
        ...     keyword_hits=["fda", "approval"],
        ...     tags=["fda"],
        ... )
        >>> signal = generator.generate_signal(
        ...     scored_item,
        ...     ticker="XYPH",
        ...     current_price=Decimal("25.50")
        ... )
        >>> assert signal.action == "buy"
        >>> assert signal.confidence > 0.8
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize signal generator with configuration.

        Args:
            config: Optional configuration dictionary. If None, uses
                   settings from environment variables via get_settings().
        """
        self.settings = get_settings()
        self.config = config or {}

        # Load configuration with fallbacks
        self.min_confidence = self.config.get(
            "min_confidence",
            float(self.settings.__dict__.get("SIGNAL_MIN_CONFIDENCE", 0.6)),
        )
        self.min_score = self.config.get(
            "min_score", float(self.settings.__dict__.get("SIGNAL_MIN_SCORE", 1.5))
        )
        self.base_position_pct = self.config.get(
            "base_position_pct",
            float(self.settings.__dict__.get("POSITION_SIZE_BASE_PCT", 2.0)),
        )
        self.max_position_pct = self.config.get(
            "max_position_pct",
            float(self.settings.__dict__.get("POSITION_SIZE_MAX_PCT", 5.0)),
        )
        self.default_stop_pct = self.config.get(
            "default_stop_pct",
            float(self.settings.__dict__.get("DEFAULT_STOP_LOSS_PCT", 5.0)),
        )
        self.default_tp_pct = self.config.get(
            "default_tp_pct",
            float(self.settings.__dict__.get("DEFAULT_TAKE_PROFIT_PCT", 10.0)),
        )

        # Lazy-loaded keyword performance provider for feedback loop integration
        self._keyword_performance_provider = None

        log.info(
            "signal_generator_initialized min_confidence=%.2f min_score=%.2f "
            "base_position_pct=%.2f max_position_pct=%.2f",
            self.min_confidence,
            self.min_score,
            self.base_position_pct,
            self.max_position_pct,
        )

    @property
    def keyword_performance_provider(self):
        """Lazy-load keyword performance provider."""
        if self._keyword_performance_provider is None:
            from .keyword_performance import KeywordPerformanceProvider

            self._keyword_performance_provider = KeywordPerformanceProvider()
        return self._keyword_performance_provider

    def _get_active_buy_keywords(self) -> Dict[str, KeywordConfig]:
        """
        Get active BUY keywords based on feature flag.

        Returns:
            Dict mapping keyword name to KeywordConfig.
            Includes extended keywords if FEATURE_EXTENDED_KEYWORDS is enabled.
        """
        # Start with core keywords (always active)
        active = dict(BUY_KEYWORDS)

        # Add extended keywords if feature flag is enabled
        if getattr(self.settings, "feature_extended_keywords", False):
            active.update(EXTENDED_BUY_KEYWORDS)
            log.debug(
                "extended_keywords_enabled count=%d",
                len(EXTENDED_BUY_KEYWORDS),
            )

        return active

    def generate_signal(
        self,
        scored_item: ScoredItem,
        ticker: str,
        current_price: Decimal,
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal from scored item.

        Args:
            scored_item: Classified alert with keyword scoring
            ticker: Stock ticker symbol
            current_price: Current market price

        Returns:
            TradingSignal if actionable, None if AVOID or insufficient confidence

        Raises:
            ValueError: If current_price is invalid (<=0)
        """
        # Validate inputs
        if current_price <= 0:
            log.warning(
                "invalid_price_skipping_signal ticker=%s price=%.2f",
                ticker,
                float(current_price),
            )
            return None

        if not ticker or not ticker.strip():
            log.warning("invalid_ticker_skipping_signal ticker=%s", ticker)
            return None

        # Extract keyword hits - handle both list and dict formats
        keyword_hits = self._extract_keyword_hits(scored_item)

        if not keyword_hits:
            log.debug(
                "no_keywords_found ticker=%s score=%.2f",
                ticker,
                (
                    scored_item.total
                    if hasattr(scored_item, "total")
                    else scored_item.relevance
                ),
            )
            return None

        # Get total score (use total property if available, else relevance)
        total_score = (
            scored_item.total
            if hasattr(scored_item, "total")
            else scored_item.relevance
        )

        # Check minimum score threshold
        if total_score < self.min_score:
            log.debug(
                "score_below_minimum ticker=%s score=%.2f min_score=%.2f",
                ticker,
                total_score,
                self.min_score,
            )
            return None

        # Determine trading action from keywords
        action, keyword_config = self._determine_action(keyword_hits)

        # Handle AVOID signals
        if action == "avoid":
            log.info(
                "avoid_signal_generated ticker=%s keywords=%s reason=dilution_or_offering_detected",
                ticker,
                list(keyword_hits.keys()),
            )
            return None

        # Handle CLOSE signals (exit positions)
        if action == "close":
            signal = TradingSignal(
                signal_id=str(uuid.uuid4()),
                ticker=ticker,
                timestamp=datetime.now(timezone.utc),
                action="close",
                confidence=1.0,  # Close signals are always high confidence
                entry_price=current_price,
                current_price=current_price,
                position_size_pct=0.0,  # Not relevant for close signals
                signal_type="risk_management",
                timeframe="immediate",
                strategy="keyword_signal_generator",
                metadata={
                    "keywords": keyword_hits,
                    "reason": "distress_signal_detected",
                    "total_score": float(total_score),
                },
            )
            log.warning(
                "close_signal_generated ticker=%s keywords=%s reason=distress_detected",
                ticker,
                list(keyword_hits.keys()),
            )
            return signal

        # Calculate confidence score
        confidence = self._calculate_confidence(
            scored_item,
            action,
            keyword_config,
            total_score,
        )

        # Check minimum confidence threshold
        if confidence < self.min_confidence:
            log.debug(
                "confidence_below_minimum ticker=%s confidence=%.2f min_confidence=%.2f",
                ticker,
                confidence,
                self.min_confidence,
            )
            return None

        # Calculate position size
        position_size_pct = self._calculate_position_size(
            confidence,
            keyword_config,
        )

        # Calculate stop-loss price
        stop_loss_price = self._calculate_stop_loss(
            action,
            current_price,
            keyword_config,
        )

        # Calculate take-profit price
        take_profit_price = self._calculate_take_profit(
            action,
            current_price,
            keyword_config,
        )

        # Verify risk/reward ratio
        if not self._verify_risk_reward_ratio(
            current_price,
            stop_loss_price,
            take_profit_price,
        ):
            log.warning(
                "insufficient_risk_reward_ratio ticker=%s entry=%.2f stop=%.2f target=%.2f",
                ticker,
                float(current_price),
                float(stop_loss_price),
                float(take_profit_price),
            )
            return None

        # Create trading signal
        signal = TradingSignal(
            signal_id=str(uuid.uuid4()),
            ticker=ticker,
            timestamp=datetime.now(timezone.utc),
            action=action,
            confidence=confidence,
            entry_price=current_price,
            current_price=current_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            position_size_pct=position_size_pct,
            signal_type="catalyst",
            timeframe="intraday",
            strategy="keyword_signal_generator",
            metadata={
                "keywords": keyword_hits,
                "keyword_category": (
                    keyword_config.rationale if keyword_config else "unknown"
                ),
                "total_score": float(total_score),
                "sentiment": scored_item.sentiment,
                "base_confidence": (
                    keyword_config.base_confidence if keyword_config else 0.0
                ),
            },
        )

        log.info(
            "signal_generated ticker=%s action=%s confidence=%.2f position_size_pct=%.2f "
            "entry=%.2f stop=%.2f target=%.2f keywords=%s",
            ticker,
            action,
            confidence,
            position_size_pct,
            float(current_price),
            float(stop_loss_price),
            float(take_profit_price),
            list(keyword_hits.keys()),
        )

        return signal

    def _extract_keyword_hits(self, scored_item: ScoredItem) -> Dict[str, float]:
        """
        Extract keyword hits from ScoredItem.

        Handles both list format (old) and dict format (new) for keyword_hits.

        Args:
            scored_item: ScoredItem with keyword_hits

        Returns:
            Dict mapping keyword to score/weight
        """
        keyword_hits = {}

        # Check if keyword_hits is a dict (new format)
        if isinstance(scored_item.keyword_hits, dict):
            keyword_hits = scored_item.keyword_hits
        # Check if keyword_hits is a list (old format)
        elif isinstance(scored_item.keyword_hits, list):
            # Convert list to dict with weight 1.0 for each keyword
            for keyword in scored_item.keyword_hits:
                if isinstance(keyword, str):
                    keyword_hits[keyword.lower()] = 1.0

        # Also check tags field (some classifiers use this)
        if hasattr(scored_item, "tags") and scored_item.tags:
            for tag in scored_item.tags:
                if isinstance(tag, str):
                    tag_lower = tag.lower()
                    if tag_lower not in keyword_hits:
                        keyword_hits[tag_lower] = 0.5  # Lower weight for tags

        return keyword_hits

    def _determine_action(
        self,
        keywords: Dict[str, float],
    ) -> tuple[str, Optional[KeywordConfig]]:
        """
        Analyze keyword_hits to determine trading action.

        Priority order:
        1. CLOSE keywords (highest priority - exit immediately)
        2. AVOID keywords (skip trade)
        3. BUY keywords (enter position)

        If multiple BUY keywords present, returns strongest signal.

        Args:
            keywords: Dict of keyword to score/weight

        Returns:
            Tuple of (action, keyword_config) where action is
            "buy", "sell", "avoid", or "close"
        """
        # Check for CLOSE keywords first (highest priority)
        for keyword, weight in keywords.items():
            if keyword.lower() in CLOSE_KEYWORDS:
                return ("close", None)

        # Check for AVOID keywords
        for keyword, weight in keywords.items():
            if keyword.lower() in AVOID_KEYWORDS:
                return ("avoid", None)

        # Find strongest BUY keyword (uses feature flag for extended keywords)
        strongest_config = None
        strongest_score = 0.0
        active_buy_keywords = self._get_active_buy_keywords()

        for keyword, weight in keywords.items():
            keyword_lower = keyword.lower()
            if keyword_lower in active_buy_keywords:
                config = active_buy_keywords[keyword_lower]
                # Calculate combined score: keyword weight * base confidence
                combined_score = weight * config.base_confidence

                if combined_score > strongest_score:
                    strongest_score = combined_score
                    strongest_config = config

        if strongest_config:
            return ("buy", strongest_config)

        # No actionable keywords found
        log.debug(
            "no_actionable_keywords keywords=%s",
            list(keywords.keys()),
        )
        return ("avoid", None)

    def _calculate_confidence(
        self,
        scored_item: ScoredItem,
        action: str,
        keyword_config: Optional[KeywordConfig],
        total_score: float,
    ) -> float:
        """
        Calculate confidence score for the signal.

        Formula: (score / 5.0) * sentiment_alignment_bonus
        - Score is normalized to 0-5 range
        - Sentiment alignment adds +20% if sentiment matches action
        - Final confidence is clamped to [0.0, 1.0]

        Args:
            scored_item: ScoredItem with sentiment
            action: Trading action ("buy" or "sell")
            keyword_config: Keyword configuration (if any)
            total_score: Total keyword score

        Returns:
            Confidence score in range [0.0, 1.0]
        """
        # Start with base confidence from keyword config
        if keyword_config:
            base_confidence = keyword_config.base_confidence
        else:
            # Fallback: normalize score to 0-1 range
            base_confidence = min(total_score / 5.0, 1.0)

        # Calculate sentiment alignment bonus
        sentiment = scored_item.sentiment
        sentiment_aligned = False

        if action == "buy" and sentiment > 0.3:
            sentiment_aligned = True
        elif action == "sell" and sentiment < -0.3:
            sentiment_aligned = True

        # Apply sentiment alignment bonus (+20%)
        if sentiment_aligned:
            confidence = base_confidence * 1.2
        else:
            confidence = base_confidence

        # Apply feedback loop multiplier (if feature enabled)
        if keyword_config and action in ("buy", "sell"):
            # Get the keyword name from the config's action field
            # Look up performance multiplier for this keyword category
            keyword_name = None
            active_buy_keywords = self._get_active_buy_keywords()
            for kw, cfg in active_buy_keywords.items():
                if cfg is keyword_config:
                    keyword_name = kw
                    break
            # Note: AVOID_KEYWORDS is a List[str] without KeywordConfig,
            # so feedback multipliers only apply to BUY_KEYWORDS

            if keyword_name:
                multiplier = self.keyword_performance_provider.get_multiplier(
                    keyword_name
                )
                if multiplier != 1.0:
                    original_conf = confidence
                    confidence *= multiplier
                    log.debug(
                        "feedback_multiplier_applied keyword=%s original=%.3f "
                        "multiplier=%.2f adjusted=%.3f",
                        keyword_name,
                        original_conf,
                        multiplier,
                        confidence,
                    )

        # Clamp to valid range
        confidence = max(0.0, min(1.0, confidence))

        return confidence

    def _calculate_position_size(
        self,
        confidence: float,
        keyword_config: Optional[KeywordConfig],
    ) -> float:
        """
        Calculate position size as percentage of portfolio.

        Formula: base_pct * confidence * keyword_multiplier
        - Base size from config (default 2%)
        - Scaled by confidence (0.6-1.0)
        - Multiplied by keyword category multiplier (e.g., FDA = 1.6x)
        - Capped at MAX_POSITION_SIZE_PCT (5%)

        Args:
            confidence: Confidence score (0.0-1.0)
            keyword_config: Keyword configuration with size multiplier

        Returns:
            Position size as percentage (e.g., 3.5 for 3.5%)
        """
        # Start with base position size
        position_size = self.base_position_pct

        # Scale by confidence
        position_size *= confidence

        # Apply keyword multiplier
        if keyword_config:
            position_size *= keyword_config.size_multiplier

        # Cap at maximum position size
        position_size = min(position_size, self.max_position_pct)

        # Ensure minimum position size (0.5%)
        position_size = max(position_size, 0.5)

        return round(position_size, 2)

    def _calculate_stop_loss(
        self,
        action: str,
        entry_price: Decimal,
        keyword_config: Optional[KeywordConfig],
    ) -> Decimal:
        """
        Calculate stop-loss price.

        - For BUY: stop is below entry (entry * (1 - stop_pct/100))
        - For SELL: stop is above entry (entry * (1 + stop_pct/100))
        - Uses keyword-specific stop percentage or default

        Args:
            action: Trading action ("buy" or "sell")
            entry_price: Entry price
            keyword_config: Keyword configuration with stop_loss_pct

        Returns:
            Stop-loss price (absolute price, not percentage)
        """
        # Get stop-loss percentage
        if keyword_config:
            stop_pct = keyword_config.stop_loss_pct
        else:
            stop_pct = self.default_stop_pct

        # Calculate stop price based on action
        if action == "buy":
            # Stop below entry for long positions
            stop_price = entry_price * (1 - Decimal(stop_pct) / 100)
        else:
            # Stop above entry for short positions
            stop_price = entry_price * (1 + Decimal(stop_pct) / 100)

        return stop_price.quantize(Decimal("0.01"))

    def _calculate_take_profit(
        self,
        action: str,
        entry_price: Decimal,
        keyword_config: Optional[KeywordConfig],
    ) -> Decimal:
        """
        Calculate take-profit price.

        - For BUY: target is above entry (entry * (1 + tp_pct/100))
        - For SELL: target is below entry (entry * (1 - tp_pct/100))
        - Uses keyword-specific take-profit percentage or default
        - Ensures minimum 2:1 risk/reward ratio

        Args:
            action: Trading action ("buy" or "sell")
            entry_price: Entry price
            keyword_config: Keyword configuration with take_profit_pct

        Returns:
            Take-profit price (absolute price, not percentage)
        """
        # Get take-profit percentage
        if keyword_config:
            tp_pct = keyword_config.take_profit_pct
        else:
            tp_pct = self.default_tp_pct

        # Calculate take-profit price based on action
        if action == "buy":
            # Target above entry for long positions
            tp_price = entry_price * (1 + Decimal(tp_pct) / 100)
        else:
            # Target below entry for short positions
            tp_price = entry_price * (1 - Decimal(tp_pct) / 100)

        return tp_price.quantize(Decimal("0.01"))

    def _verify_risk_reward_ratio(
        self,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        take_profit_price: Decimal,
    ) -> bool:
        """
        Verify minimum risk/reward ratio is met.

        Minimum ratio is 2:1 (reward must be at least 2x risk).

        Args:
            entry_price: Entry price
            stop_loss_price: Stop-loss price
            take_profit_price: Take-profit price

        Returns:
            True if risk/reward ratio meets minimum threshold
        """
        # Calculate risk (distance to stop)
        risk = abs(entry_price - stop_loss_price)

        # Calculate reward (distance to target)
        reward = abs(take_profit_price - entry_price)

        # Avoid division by zero
        if risk == 0:
            return False

        # Calculate ratio
        ratio = reward / risk

        # Minimum 2:1 ratio required
        min_ratio = Decimal("2.0")

        return ratio >= min_ratio
