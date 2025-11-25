"""
Google Gemini Provider
=======================

Adapter for Google Gemini API (Flash Lite, Flash, Pro models).

Pricing (per 1M tokens):
- Flash Lite (gemini-1.5-flash-8b): $0.02 input, $0.08 output
- Flash (gemini-1.5-flash): $0.075 input, $0.30 output
- Pro (gemini-1.5-pro): $1.25 input, $5.00 output

API Documentation: https://ai.google.dev/gemini-api/docs
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from ...logging_utils import get_logger
from .base import BaseLLMProvider

log = get_logger("gemini_provider")


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider."""

    # Pricing per 1M tokens (USD)
    PRICING = {
        "gemini-2.0-flash-lite": {"input": 0.02, "output": 0.08},  # Cheapest
        "gemini-2.5-flash": {"input": 0.075, "output": 0.30},      # Main model
        "gemini-2.5-pro": {"input": 1.25, "output": 5.00},         # Pro (if available)
    }

    def __init__(self, config: dict):
        """Initialize Gemini provider."""
        super().__init__(config)
        self.api_key = os.getenv("GEMINI_API_KEY", "")

        if not self.api_key:
            log.warning("gemini_api_key_missing provider_disabled")

        log.info("gemini_provider_initialized has_key=%s", bool(self.api_key))

    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Execute Gemini API query.

        Uses google-generativeai library for API calls.
        """
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        try:
            import google.generativeai as genai

            # Configure API
            genai.configure(api_key=self.api_key)

            # Build generation config
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            # Create model
            model_instance = genai.GenerativeModel(
                model_name=model,
                generation_config=generation_config,
                system_instruction=system_prompt
            )

            # Generate response
            log.debug(
                "gemini_query_start model=%s prompt_len=%d",
                model,
                len(prompt)
            )

            response = model_instance.generate_content(prompt)

            # Extract text
            text = response.text if hasattr(response, "text") else ""

            # Count tokens (Gemini provides usage metadata)
            tokens_input = 0
            tokens_output = 0
            if hasattr(response, "usage_metadata"):
                tokens_input = getattr(response.usage_metadata, "prompt_token_count", 0)
                tokens_output = getattr(response.usage_metadata, "candidates_token_count", 0)

            # If no usage metadata, estimate
            if tokens_input == 0:
                tokens_input = self._count_tokens(prompt)
                if system_prompt:
                    tokens_input += self._count_tokens(system_prompt)
            if tokens_output == 0:
                tokens_output = self._count_tokens(text)

            # Calculate cost
            cost_usd = self.estimate_cost(model, tokens_input, tokens_output)

            # Try to parse as JSON if response looks like JSON
            parsed_output = None
            if text.strip().startswith("{") or text.strip().startswith("["):
                try:
                    parsed_output = json.loads(text)
                except json.JSONDecodeError:
                    pass

            log.info(
                "gemini_query_success model=%s tokens_in=%d tokens_out=%d cost_usd=%.4f",
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
                "confidence": None,  # Gemini doesn't provide confidence scores
            }

        except ImportError:
            log.error("gemini_library_not_installed install_with: pip install google-generativeai")
            raise ValueError("google-generativeai library not installed")

        except Exception as e:
            log.error("gemini_query_failed model=%s err=%s", model, str(e), exc_info=True)
            raise

    def estimate_cost(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int
    ) -> float:
        """
        Estimate cost for Gemini request.

        Args:
            model: Model name
            tokens_input: Input token count
            tokens_output: Output token count

        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(model, self.PRICING["gemini-2.5-flash"])

        cost_input = (tokens_input / 1_000_000) * pricing["input"]
        cost_output = (tokens_output / 1_000_000) * pricing["output"]

        return cost_input + cost_output
