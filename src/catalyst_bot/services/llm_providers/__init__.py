"""
LLM Provider Adapters
======================

Unified interface for different LLM providers (Gemini, Claude, etc.).

All providers implement the same interface:
- query(prompt, system_prompt, model, max_tokens, temperature, timeout)
- estimate_cost(model, tokens_input, tokens_output)

This allows easy swapping and failover between providers.
"""

from .base import BaseLLMProvider
from .gemini import GeminiProvider
from .claude import ClaudeProvider

__all__ = ["BaseLLMProvider", "GeminiProvider", "ClaudeProvider"]
