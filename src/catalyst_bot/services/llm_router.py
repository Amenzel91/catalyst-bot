"""
LLM Router - Intelligent Model Selection
==========================================

Routes requests to optimal model based on task complexity and cost optimization.

Routing Strategy:
- SIMPLE tasks → Gemini Flash Lite (70%) or Gemini Flash (30%)
- MEDIUM tasks → Gemini Flash (90%) or Gemini Pro (10%)
- COMPLEX tasks → Gemini Pro (80%) or Claude Sonnet (20%)
- CRITICAL tasks → Claude Sonnet (100%)

Features:
- Provider health checks and failover
- Cost-aware routing (prefer cheaper models)
- Load balancing across providers
- A/B testing support
"""

from __future__ import annotations

import random
from typing import Optional, Tuple

from ..logging_utils import get_logger
from .llm_service import TaskComplexity

log = get_logger("llm_router")


class LLMRouter:
    """Intelligent router for LLM model selection."""

    # Cost per 1M input tokens (USD)
    MODEL_COSTS = {
        "gemini_flash_lite": 0.02,
        "gemini_flash": 0.075,
        "gemini_pro": 1.25,
        "claude_sonnet": 3.00,
    }

    # Model routing probabilities by complexity
    # Format: {complexity: [(provider, probability), ...]}
    ROUTING_TABLE = {
        TaskComplexity.SIMPLE: [
            ("gemini_flash_lite", 0.70),  # 70% Flash Lite (cheapest)
            ("gemini_flash", 0.30),       # 30% Flash (better quality)
        ],
        TaskComplexity.MEDIUM: [
            ("gemini_flash", 0.90),       # 90% Flash
            ("gemini_pro", 0.10),         # 10% Pro (complex cases)
        ],
        TaskComplexity.COMPLEX: [
            ("gemini_pro", 0.80),         # 80% Pro
            ("claude_sonnet", 0.20),      # 20% Sonnet (highest quality)
        ],
        TaskComplexity.CRITICAL: [
            ("claude_sonnet", 1.00),      # 100% Sonnet (mission-critical)
        ],
    }

    # Model name mappings (provider → actual model name)
    MODEL_NAMES = {
        "gemini_flash_lite": "gemini-2.0-flash-lite",     # Cheapest, fastest
        "gemini_flash": "gemini-2.0-flash-exp",           # Main workhorse (experimental but stable)
        "gemini_pro": "gemini-2.5-pro",                   # Pro tier
        "claude_sonnet": "claude-sonnet-4-20250514",      # Premium fallback
    }

    def __init__(self, config: dict):
        """
        Initialize router.

        Args:
            config: Configuration dict from LLMService
        """
        self.config = config
        self.provider_health = {}  # Track provider availability
        log.info("llm_router_initialized")

    def select_provider(
        self,
        complexity: Optional[TaskComplexity] = None
    ) -> Tuple[str, str]:
        """
        Select optimal provider and model based on complexity.

        Args:
            complexity: Task complexity level

        Returns:
            Tuple of (provider_name, model_name)

        Example:
            >>> router.select_provider(TaskComplexity.SIMPLE)
            ('gemini_flash_lite', 'gemini-2.0-flash-lite-001')
        """
        complexity = complexity or TaskComplexity.MEDIUM

        # Get routing options for this complexity
        options = self.ROUTING_TABLE.get(complexity, [])
        if not options:
            log.warning(
                "no_routing_options complexity=%s fallback_to_medium",
                complexity.value if complexity else "none"
            )
            options = self.ROUTING_TABLE[TaskComplexity.MEDIUM]

        # Filter out unhealthy providers
        healthy_options = [
            (provider, prob)
            for provider, prob in options
            if self._is_provider_healthy(provider)
        ]

        if not healthy_options:
            log.warning(
                "no_healthy_providers complexity=%s using_all_options",
                complexity.value if complexity else "none"
            )
            healthy_options = options

        # Select provider based on probability distribution
        provider_name = self._weighted_random_choice(healthy_options)
        model_name = self.MODEL_NAMES.get(provider_name, provider_name)

        log.debug(
            "provider_selected complexity=%s provider=%s model=%s",
            complexity.value if complexity else "none",
            provider_name,
            model_name
        )

        return provider_name, model_name

    def get_fallback_provider(
        self,
        failed_provider: str,
        complexity: TaskComplexity
    ) -> Tuple[str, str]:
        """
        Get fallback provider when primary fails.

        Fallback strategy:
        - Gemini Flash Lite → Gemini Flash
        - Gemini Flash → Gemini Pro
        - Gemini Pro → Claude Sonnet
        - Claude Sonnet → Gemini Pro (last resort)

        Args:
            failed_provider: Provider that failed
            complexity: Task complexity

        Returns:
            Tuple of (fallback_provider, model)
        """
        fallback_map = {
            "gemini_flash_lite": "gemini_flash",
            "gemini_flash": "gemini_pro",
            "gemini_pro": "claude_sonnet",
            "claude_sonnet": "gemini_pro",  # Last resort
        }

        fallback = fallback_map.get(failed_provider, "gemini_flash")
        model = self.MODEL_NAMES.get(fallback, fallback)

        log.warning(
            "provider_fallback failed=%s fallback=%s model=%s",
            failed_provider,
            fallback,
            model
        )

        return fallback, model

    def mark_provider_unhealthy(self, provider: str, duration_seconds: int = 300):
        """
        Mark provider as temporarily unhealthy.

        Args:
            provider: Provider name
            duration_seconds: How long to mark as unhealthy (default: 5 minutes)
        """
        import time
        self.provider_health[provider] = {
            "healthy": False,
            "until": time.time() + duration_seconds
        }
        log.warning(
            "provider_marked_unhealthy provider=%s duration_sec=%d",
            provider,
            duration_seconds
        )

    def _is_provider_healthy(self, provider: str) -> bool:
        """Check if provider is healthy."""
        import time

        if provider not in self.provider_health:
            return True  # Assume healthy if unknown

        health = self.provider_health[provider]
        if health["healthy"]:
            return True

        # Check if unhealthy period has expired
        if time.time() > health["until"]:
            self.provider_health[provider]["healthy"] = True
            log.info("provider_recovered provider=%s", provider)
            return True

        return False

    def _weighted_random_choice(self, options: list) -> str:
        """
        Select option based on weighted probabilities.

        Args:
            options: List of (value, probability) tuples

        Returns:
            Selected value
        """
        if not options:
            return "gemini_flash"  # Default fallback

        # Normalize probabilities to sum to 1.0
        total_prob = sum(prob for _, prob in options)
        normalized = [(val, prob / total_prob) for val, prob in options]

        # Random selection based on probabilities
        rand = random.random()
        cumulative = 0.0
        for value, prob in normalized:
            cumulative += prob
            if rand <= cumulative:
                return value

        # Fallback to last option
        return normalized[-1][0]

    def get_model_cost(self, provider: str) -> float:
        """Get cost per 1M input tokens for provider."""
        return self.MODEL_COSTS.get(provider, 1.0)

    def get_routing_stats(self) -> dict:
        """
        Get routing statistics.

        Returns:
            Dict with routing distribution and health status
        """
        return {
            "routing_table": {
                complexity.value: [
                    {"provider": p, "probability": prob}
                    for p, prob in options
                ]
                for complexity, options in self.ROUTING_TABLE.items()
            },
            "provider_health": self.provider_health,
            "model_costs": self.MODEL_COSTS,
        }
