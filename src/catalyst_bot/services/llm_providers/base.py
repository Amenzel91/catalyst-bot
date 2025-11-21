"""
Base LLM Provider Interface
============================

Abstract base class that all LLM providers must implement.
Ensures consistent interface across different providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: dict):
        """
        Initialize provider.

        Args:
            config: Configuration dict from LLMService
        """
        self.config = config

    @abstractmethod
    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "default",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Execute LLM query.

        Args:
            prompt: Main prompt text
            system_prompt: Optional system/instruction prompt
            model: Model name
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            timeout: Request timeout in seconds

        Returns:
            Dict with keys:
            - text: Response text
            - tokens_input: Input token count
            - tokens_output: Output token count
            - cost_usd: Estimated cost
            - parsed_output: Parsed JSON (if applicable)
            - confidence: Model confidence (if available)

        Raises:
            Exception: On API errors
        """
        pass

    @abstractmethod
    def estimate_cost(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int
    ) -> float:
        """
        Estimate cost for a request.

        Args:
            model: Model name
            tokens_input: Input token count
            tokens_output: Output token count

        Returns:
            Estimated cost in USD
        """
        pass

    def _count_tokens(self, text: str) -> int:
        """
        Estimate token count from text.

        Simple heuristic: ~4 characters per token.
        Override in subclass for model-specific tokenization.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4
