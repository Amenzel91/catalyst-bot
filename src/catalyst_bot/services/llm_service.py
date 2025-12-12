"""
Unified LLM Service Hub
========================

Central orchestrator for all LLM operations across Catalyst-Bot features.
Provides intelligent routing, semantic caching, cost tracking, and failover.

Features:
- Single entry point for all LLM requests
- Automatic complexity detection and model routing
- Semantic caching (target: 70% hit rate)
- Real-time cost monitoring and budget enforcement
- Multi-provider support (Gemini, Claude) with automatic failover
- Extensible for any feature (SEC digester, sentiment, news classification)

Usage:
    from catalyst_bot.services import LLMService, LLMRequest, TaskComplexity

    service = LLMService()

    # Simple request
    request = LLMRequest(
        prompt="Analyze this 8-K filing...",
        complexity=TaskComplexity.SIMPLE,
        feature_name="sec_8k_digest"
    )
    response = await service.query(request)

    # Batch processing
    requests = [LLMRequest(...) for item in items]
    responses = await service.query_batch(requests)
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..logging_utils import get_logger

log = get_logger("llm_service")


class TaskComplexity(Enum):
    """Task complexity levels for intelligent routing."""

    SIMPLE = "simple"        # Simple classification, keyword extraction (Gemini Flash Lite)
    MEDIUM = "medium"        # Standard analysis, short summaries (Gemini Flash)
    COMPLEX = "complex"      # Deep analysis, M&A deals, earnings (Gemini Pro)
    CRITICAL = "critical"    # High-stakes compliance, complex financial (Claude Sonnet)


class OutputFormat(Enum):
    """Expected output format from LLM."""

    TEXT = "text"           # Free-form text response
    JSON = "json"           # JSON object
    STRUCTURED = "structured"  # Pydantic model validation


@dataclass
class LLMRequest:
    """
    Standardized LLM request format used by all features.

    Attributes:
        prompt: The main prompt text
        system_prompt: Optional system/instruction prompt
        complexity: Task complexity level (auto-detected if None)
        output_format: Expected output format
        feature_name: Feature making the request (for cost tracking)
        enable_cache: Whether to use semantic caching
        compress_prompt: Whether to apply prompt compression
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
        timeout_seconds: Request timeout
    """

    prompt: str
    system_prompt: Optional[str] = None
    complexity: Optional[TaskComplexity] = None
    output_format: OutputFormat = OutputFormat.TEXT
    feature_name: str = "unknown"
    enable_cache: bool = True
    compress_prompt: bool = True
    max_tokens: int = 1000
    temperature: float = 0.1
    timeout_seconds: float = 10.0

    # Advanced options
    fallback_on_error: bool = True
    max_retries: int = 2
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """
    Standardized LLM response format.

    Attributes:
        text: Raw text response from LLM
        parsed_output: Parsed output (for JSON/structured formats)
        provider: Provider used (gemini_flash_lite, claude_sonnet, etc.)
        model: Specific model name
        cached: Whether response came from cache
        latency_ms: Response time in milliseconds
        tokens_input: Input token count
        tokens_output: Output token count
        cost_usd: Estimated cost in USD
        confidence: Model confidence score (if available)
        request_id: Original request ID
        error: Error message if request failed
    """

    text: str
    parsed_output: Optional[Union[Dict, Any]] = None
    provider: str = "unknown"
    model: str = "unknown"
    cached: bool = False
    latency_ms: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    confidence: Optional[float] = None
    request_id: Optional[str] = None
    error: Optional[str] = None

    # Debug info
    cache_key: Optional[str] = None
    prompt_compressed: bool = False
    retries: int = 0


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""
    pass


class LLMService:
    """
    Unified LLM Service Hub - Single entry point for all LLM operations.

    Handles:
    - Intelligent routing based on task complexity
    - Semantic caching for cost optimization
    - Real-time cost tracking and budget enforcement
    - Multi-provider failover (Gemini → Claude)
    - Batch processing for efficiency

    Thread-safe and async-compatible.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM service.

        Args:
            config: Optional configuration dict (loads from env if None)
        """
        self.config = config or self._load_config()
        self.enabled = self.config.get("enabled", True)

        # Lazy-load components
        self._router = None
        self._cache = None
        self._monitor = None
        self._providers = {}

        log.info(
            "llm_service_initialized enabled=%s cost_tracking=%s",
            self.enabled,
            self.config.get("cost_tracking_enabled", True)
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        return {
            "enabled": os.getenv("FEATURE_UNIFIED_LLM_SERVICE", "1") in ("1", "true", "yes"),
            "cost_tracking_enabled": os.getenv("LLM_COST_TRACKING", "1") in ("1", "true", "yes"),
            "cache_enabled": os.getenv("LLM_CACHE_ENABLED", "1") in ("1", "true", "yes"),
            "cache_ttl_seconds": int(os.getenv("LLM_CACHE_TTL_SECONDS", "86400")),  # 24 hours
            "prompt_compression": os.getenv("LLM_PROMPT_COMPRESSION", "1") in ("1", "true", "yes"),
            "compression_target": float(os.getenv("LLM_PROMPT_COMPRESSION_TARGET", "0.6")),  # 40% reduction
            "daily_cost_alert": float(os.getenv("LLM_COST_ALERT_DAILY", "30.00")),
            "monthly_cost_alert": float(os.getenv("LLM_COST_ALERT_MONTHLY", "800.00")),
            "monthly_cost_hard_limit": float(os.getenv("LLM_COST_HARD_LIMIT_MONTHLY", "1000.00")),
            "default_timeout": float(os.getenv("LLM_DEFAULT_TIMEOUT_SEC", "10.0")),
        }

    @property
    def router(self):
        """Lazy-load router."""
        if self._router is None:
            from .llm_router import LLMRouter
            self._router = LLMRouter(self.config)
        return self._router

    @property
    def cache(self):
        """Lazy-load cache."""
        if self._cache is None and self.config.get("cache_enabled"):
            try:
                from .llm_cache import LLMCache
                self._cache = LLMCache(self.config)
            except Exception as e:
                log.warning("llm_cache_init_failed err=%s fallback_to_nocache", str(e))
                self._cache = None
        return self._cache

    @property
    def monitor(self):
        """Lazy-load monitor."""
        if self._monitor is None and self.config.get("cost_tracking_enabled"):
            try:
                from .llm_monitor import LLMMonitor
                self._monitor = LLMMonitor(self.config)
            except Exception as e:
                log.warning("llm_monitor_init_failed err=%s fallback_to_nomonitor", str(e))
                self._monitor = None
        return self._monitor

    async def query(self, request: LLMRequest) -> LLMResponse:
        """
        Execute single LLM query with intelligent routing and optimization.

        Flow:
        1. Check if service is enabled
        2. Auto-detect complexity if not specified
        3. Check semantic cache
        4. Compress prompt if enabled
        5. Route to appropriate model
        6. Execute request with retry/failover
        7. Track cost and performance
        8. Cache response

        Args:
            request: LLM request object

        Returns:
            LLM response object

        Raises:
            LLMServiceError: On unrecoverable errors
        """
        if not self.enabled:
            log.warning("llm_service_disabled returning_empty_response")
            return LLMResponse(
                text="",
                error="LLM service is disabled (FEATURE_UNIFIED_LLM_SERVICE=0)"
            )

        start_time = datetime.now()
        request_id = request.request_id or self._generate_request_id()

        try:
            # 1. Auto-detect complexity if not specified
            if request.complexity is None:
                request.complexity = self._auto_detect_complexity(request.prompt)

            # 2. Check cache
            if request.enable_cache and self.cache:
                cached_response = await self.cache.get(request.prompt, request.feature_name)
                if cached_response:
                    log.info(
                        "llm_cache_hit feature=%s complexity=%s",
                        request.feature_name,
                        request.complexity.value if request.complexity else "auto"
                    )
                    cached_response.cached = True
                    cached_response.request_id = request_id
                    return cached_response

            # 3. Compress prompt if enabled
            prompt = request.prompt
            compressed = False
            if request.compress_prompt and self.config.get("prompt_compression"):
                prompt = self._compress_prompt(prompt, request.complexity)
                compressed = True

            # 4. Route to appropriate provider
            provider_name, model = self.router.select_provider(request.complexity)
            provider = self._get_provider(provider_name)

            log.info(
                "llm_query_start feature=%s complexity=%s provider=%s model=%s compressed=%s",
                request.feature_name,
                request.complexity.value if request.complexity else "auto",
                provider_name,
                model,
                compressed
            )

            # 5. Execute request with retry and fallback logic
            last_error = None
            retry_count = 0
            max_retries = request.max_retries if hasattr(request, 'max_retries') else 2

            for attempt in range(max_retries + 1):
                try:
                    response = await provider.query(
                        prompt=prompt,
                        system_prompt=request.system_prompt,
                        model=model,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        timeout=request.timeout_seconds
                    )
                    # Success - break out of retry loop
                    break

                except (TimeoutError, Exception) as e:
                    last_error = e
                    retry_count = attempt + 1

                    log.warning(
                        "llm_query_failed provider=%s attempt=%d/%d err=%s",
                        provider_name,
                        retry_count,
                        max_retries + 1,
                        str(e)[:100]
                    )

                    # If this isn't the last attempt and fallback is enabled, try fallback provider
                    if attempt < max_retries:
                        fallback_provider_name, fallback_model = self.router.get_fallback_provider(
                            failed_provider=provider_name,
                            complexity=request.complexity or TaskComplexity.MEDIUM
                        )

                        # Mark current provider as unhealthy temporarily (5 minutes)
                        self.router.mark_provider_unhealthy(provider_name, duration_seconds=300)

                        # Switch to fallback provider
                        provider_name = fallback_provider_name
                        model = fallback_model
                        provider = self._get_provider(provider_name)

                        log.info(
                            "llm_fallback_provider from=%s to=%s model=%s",
                            provider_name,
                            fallback_provider_name,
                            fallback_model
                        )
                    else:
                        # Last attempt failed - re-raise error
                        raise last_error

            # 6. Build response object
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            llm_response = LLMResponse(
                text=response.get("text", ""),
                parsed_output=response.get("parsed_output"),
                provider=provider_name,
                model=model,
                cached=False,
                latency_ms=latency_ms,
                tokens_input=response.get("tokens_input", 0),
                tokens_output=response.get("tokens_output", 0),
                cost_usd=response.get("cost_usd", 0.0),
                confidence=response.get("confidence"),
                request_id=request_id,
                prompt_compressed=compressed,
                retries=retry_count  # Track actual retry count
            )

            # 7. Track cost and performance
            if self.monitor:
                self.monitor.track_request(
                    feature=request.feature_name,
                    provider=provider_name,
                    model=model,
                    tokens_input=llm_response.tokens_input,
                    tokens_output=llm_response.tokens_output,
                    cost_usd=llm_response.cost_usd,
                    latency_ms=latency_ms,
                    cached=False,
                    error=None
                )

            # 7b. Bridge to legacy monitor for heartbeat display
            # The heartbeat reads from LLMUsageMonitor (JSONL), so we need
            # to also log there for metrics to appear in admin alerts.
            try:
                from ..llm_usage_monitor import get_monitor as get_legacy_monitor
                legacy_monitor = get_legacy_monitor()
                if legacy_monitor:
                    legacy_monitor.log_usage(
                        provider=provider_name,
                        model=model,
                        operation=request.feature_name,
                        input_tokens=llm_response.tokens_input,
                        output_tokens=llm_response.tokens_output,
                        cost_estimate=llm_response.cost_usd,
                        latency_ms=latency_ms,
                    )
            except Exception:
                pass  # Non-critical - don't fail request if logging fails

            # 8. Cache response
            if request.enable_cache and self.cache:
                await self.cache.set(request.prompt, request.feature_name, llm_response)

            log.info(
                "llm_query_success feature=%s provider=%s latency_ms=%.1f cost_usd=%.4f",
                request.feature_name,
                provider_name,
                latency_ms,
                llm_response.cost_usd
            )

            return llm_response

        except Exception as e:
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            log.error(
                "llm_query_failed feature=%s err=%s latency_ms=%.1f",
                request.feature_name,
                str(e),
                latency_ms,
                exc_info=True
            )

            # Track error
            if self.monitor:
                self.monitor.track_request(
                    feature=request.feature_name,
                    provider="unknown",
                    model="unknown",
                    tokens_input=0,
                    tokens_output=0,
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    cached=False,
                    error=str(e)
                )

            # Bridge error to legacy monitor
            try:
                from ..llm_usage_monitor import get_monitor as get_legacy_monitor
                legacy_monitor = get_legacy_monitor()
                if legacy_monitor:
                    legacy_monitor.log_usage(
                        provider="unknown",
                        model="unknown",
                        operation=request.feature_name,
                        input_tokens=0,
                        output_tokens=0,
                        cost_estimate=0.0,
                        latency_ms=latency_ms,
                        error=str(e),
                    )
            except Exception:
                pass

            return LLMResponse(
                text="",
                error=str(e),
                request_id=request_id,
                latency_ms=latency_ms
            )

    async def query_batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Execute multiple LLM queries in parallel.

        Efficiently processes multiple requests by:
        - Running in parallel (asyncio.gather)
        - Grouping by provider for connection reuse
        - Shared caching and monitoring

        Args:
            requests: List of LLM requests

        Returns:
            List of LLM responses (same order as requests)
        """
        log.info("llm_batch_start count=%d", len(requests))

        # Execute all requests in parallel
        responses = await asyncio.gather(
            *[self.query(req) for req in requests],
            return_exceptions=True
        )

        # Convert exceptions to error responses
        final_responses = []
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                final_responses.append(LLMResponse(
                    text="",
                    error=str(resp),
                    request_id=requests[i].request_id
                ))
            else:
                final_responses.append(resp)

        log.info("llm_batch_complete count=%d", len(final_responses))
        return final_responses

    def estimate_cost(self, request: LLMRequest) -> float:
        """
        Estimate cost in USD for a request (without executing it).

        Useful for:
        - Budget enforcement before execution
        - User warnings for expensive operations
        - Batch processing optimization

        Args:
            request: LLM request to estimate

        Returns:
            Estimated cost in USD
        """
        # Auto-detect complexity
        complexity = request.complexity or self._auto_detect_complexity(request.prompt)

        # Get provider and model
        provider_name, model = self.router.select_provider(complexity)
        provider = self._get_provider(provider_name)

        # Estimate tokens
        estimated_input_tokens = len(request.prompt) // 4  # ~4 chars per token
        estimated_output_tokens = request.max_tokens

        # Get cost from provider
        return provider.estimate_cost(
            model=model,
            tokens_input=estimated_input_tokens,
            tokens_output=estimated_output_tokens
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get service performance and cost statistics.

        Returns:
            Dict with keys:
            - total_requests: Total requests processed
            - cache_hit_rate: Cache hit percentage (0-100)
            - avg_latency_ms: Average latency
            - total_cost_usd: Total cost to date
            - cost_by_provider: Breakdown by provider
            - cost_by_feature: Breakdown by feature
            - error_rate: Error percentage
        """
        if self.monitor:
            return self.monitor.get_stats()
        return {}

    def _auto_detect_complexity(self, prompt: str) -> TaskComplexity:
        """
        Auto-detect task complexity from prompt.

        Heuristics:
        - Length < 500 chars → SIMPLE
        - Keywords like "M&A", "acquisition", "earnings" → COMPLEX
        - Keywords like "compliance", "legal" → CRITICAL
        - Default → MEDIUM
        """
        prompt_lower = prompt.lower()

        # Critical keywords
        if any(kw in prompt_lower for kw in ["compliance", "legal", "regulatory", "audit"]):
            return TaskComplexity.CRITICAL

        # Complex keywords
        if any(kw in prompt_lower for kw in [
            "m&a", "merger", "acquisition", "earnings", "10-k", "10-q",
            "partnership", "agreement", "contract"
        ]):
            return TaskComplexity.COMPLEX

        # Simple based on length
        if len(prompt) < 500:
            return TaskComplexity.SIMPLE

        # Medium by default
        return TaskComplexity.MEDIUM

    def _compress_prompt(self, prompt: str, complexity: Optional[TaskComplexity]) -> str:
        """
        Compress prompt to reduce token count (PHASE 4).

        Techniques:
        - Remove boilerplate and legal disclaimers
        - Extract key sections
        - Smart truncation with priority ranking
        - Remove redundant whitespace

        Target: 40% reduction
        """
        import re

        compressed = prompt

        # 1. Remove SEC filing boilerplate (common patterns that don't add value)
        boilerplate_patterns = [
            # SEC header boilerplate
            r"UNITED STATES\s+SECURITIES AND EXCHANGE COMMISSION\s+Washington, D\.C\. 20549",
            r"FORM \d+-[KQ]\s+CURRENT REPORT.*?Exchange Act of 1934",
            r"Pursuant to Section \d+ or Section \d+\(d\) of the.*?Exchange Act of 1934",
            r"Date of Report.*?Date of earliest event reported.*?\d{4}",
            r"Commission File Number:?\s*[\d-]+",
            r"I\.R\.S\. Employer Identification No\..*?\d{2}-\d{7}",
            r"State or other jurisdiction.*?incorporation.*?organization",
            # Legal disclaimers
            r"Check the appropriate box below.*?(\n.*?){0,3}",
            r"Indicate by check mark.*?(\n.*?){0,2}",
            r"If an emerging growth company.*?(\n.*?){0,2}",
            # Signature blocks
            r"Pursuant to the requirements.*?signature",
            r"Date:?\s*\d{1,2}/\d{1,2}/\d{4}",
            # Exhibit references (usually at end)
            r"Exhibit Index.*?$",
        ]

        for pattern in boilerplate_patterns:
            compressed = re.sub(pattern, '', compressed, flags=re.IGNORECASE | re.MULTILINE)

        # 2. Normalize whitespace (multiple newlines/spaces -> single)
        compressed = re.sub(r'\n\s*\n\s*\n+', '\n\n', compressed)  # Max 2 newlines
        compressed = re.sub(r' {2,}', ' ', compressed)  # Multiple spaces -> single
        compressed = re.sub(r'\t+', ' ', compressed)  # Tabs -> spaces

        # 3. Remove common SEC filing phrases that don't add meaning
        filler_phrases = [
            r"as filed with the securities and exchange commission on",
            r"for further information,? see",
            r"this current report on form \d+-[kq]",
            r"the information in this (?:item|section)",
            r"incorporated herein by reference",
            r"see also",
            r"as described (?:below|above|herein)",
        ]

        for phrase in filler_phrases:
            compressed = re.sub(phrase, '', compressed, flags=re.IGNORECASE)

        # 4. Smart truncation based on complexity
        target_ratio = self.config.get("compression_target", 0.6)  # Default: keep 60%
        max_chars = int(len(prompt) * target_ratio)

        if len(compressed) > max_chars:
            # Priority sections to keep (in order)
            priority_keywords = [
                "acquisition", "merger", "agreement", "partnership",
                "revenue", "earnings", "loss", "profit",
                "shares", "offering", "dilution",
                "bankruptcy", "delisting",
                "fda", "approval", "clinical",
                "ceo", "cfo", "resignation",
            ]

            # Find sentences containing priority keywords
            sentences = re.split(r'[.!?]+\s+', compressed)
            priority_sentences = []
            other_sentences = []

            for sentence in sentences:
                if any(kw in sentence.lower() for kw in priority_keywords):
                    priority_sentences.append(sentence)
                else:
                    other_sentences.append(sentence)

            # Reconstruct with priority sentences first, then others until max_chars
            result = []
            current_len = 0

            # Add all priority sentences
            for sent in priority_sentences:
                result.append(sent)
                current_len += len(sent)

            # Add other sentences until we hit limit
            for sent in other_sentences:
                if current_len + len(sent) < max_chars:
                    result.append(sent)
                    current_len += len(sent)
                else:
                    break

            compressed = '. '.join(result)

        # 5. Final cleanup
        compressed = compressed.strip()

        # Log compression stats
        original_len = len(prompt)
        compressed_len = len(compressed)
        reduction_pct = ((original_len - compressed_len) / original_len * 100) if original_len > 0 else 0

        log.debug(
            "prompt_compressed original_chars=%d compressed_chars=%d reduction=%.1f%%",
            original_len,
            compressed_len,
            reduction_pct
        )

        return compressed

    def _get_provider(self, provider_name: str):
        """Get or create provider instance."""
        if provider_name not in self._providers:
            if provider_name.startswith("gemini"):
                from .llm_providers.gemini import GeminiProvider
                self._providers[provider_name] = GeminiProvider(self.config)
            elif provider_name.startswith("claude"):
                from .llm_providers.claude import ClaudeProvider
                self._providers[provider_name] = ClaudeProvider(self.config)
            else:
                raise LLMServiceError(f"Unknown provider: {provider_name}")

        return self._providers[provider_name]

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        import uuid
        return str(uuid.uuid4())[:8]
