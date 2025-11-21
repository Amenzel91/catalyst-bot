"""
Anthropic Claude Provider
==========================

Adapter for Anthropic Claude API (Haiku, Sonnet, Opus models).

Pricing (per 1M tokens):
- Haiku: $0.80 input, $4.00 output
- Sonnet (claude-sonnet-4): $3.00 input, $15.00 output
- Opus: $15.00 input, $75.00 output

API Documentation: https://docs.anthropic.com/claude/reference
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from ...logging_utils import get_logger
from .base import BaseLLMProvider

log = get_logger("claude_provider")


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude API provider."""

    # Pricing per 1M tokens (USD)
    PRICING = {
        "claude-haiku-3-20250301": {"input": 0.80, "output": 4.00},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    }

    def __init__(self, config: dict):
        """Initialize Claude provider."""
        super().__init__(config)
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

        if not self.api_key:
            log.warning("anthropic_api_key_missing provider_disabled")

        log.info("claude_provider_initialized has_key=%s", bool(self.api_key))

    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Execute Claude API query.

        Uses anthropic library for API calls.
        """
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        try:
            from anthropic import AsyncAnthropic

            # Create client
            client = AsyncAnthropic(api_key=self.api_key)

            # Build messages
            messages = [
                {"role": "user", "content": prompt}
            ]

            log.debug(
                "claude_query_start model=%s prompt_len=%d",
                model,
                len(prompt)
            )

            # Make API call
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=messages
            )

            # Extract text
            text = ""
            if response.content and len(response.content) > 0:
                text = response.content[0].text

            # Get token usage
            tokens_input = response.usage.input_tokens
            tokens_output = response.usage.output_tokens

            # Calculate cost
            cost_usd = self.estimate_cost(model, tokens_input, tokens_output)

            # Try to parse as JSON
            parsed_output = None
            if text.strip().startswith("{") or text.strip().startswith("["):
                try:
                    parsed_output = json.loads(text)
                except json.JSONDecodeError:
                    pass

            log.info(
                "claude_query_success model=%s tokens_in=%d tokens_out=%d cost_usd=%.4f",
                model,
                tokens_input,
                tokens_output,
                cost_usd
            )

            return {
                "text": text,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "cost_usd": cost_usd,
                "parsed_output": parsed_output,
                "confidence": None,
            }

        except ImportError:
            log.error("claude_library_not_installed install_with: pip install anthropic")
            raise ValueError("anthropic library not installed")

        except Exception as e:
            log.error("claude_query_failed model=%s err=%s", model, str(e), exc_info=True)
            raise

    def estimate_cost(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int
    ) -> float:
        """
        Estimate cost for Claude request.

        Args:
            model: Model name
            tokens_input: Input token count
            tokens_output: Output token count

        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(model, self.PRICING["claude-sonnet-4-20250514"])

        cost_input = (tokens_input / 1_000_000) * pricing["input"]
        cost_output = (tokens_output / 1_000_000) * pricing["output"]

        return cost_input + cost_output
