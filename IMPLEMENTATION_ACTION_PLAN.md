# Implementation Action Plan: Cloud-First LLM + WebSocket SEC Digester

**Version**: 1.0
**Date**: 2025-11-17
**Status**: Ready for Implementation
**Timeline**: 7 weeks
**Development Tools**: Claude Code, Codex CLI

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Phase 1: Foundation - LLM Service Hub](#phase-1-foundation---llm-service-hub)
5. [Phase 2: WebSocket SEC Digester Service](#phase-2-websocket-sec-digester-service)
6. [Phase 3: Client Integration](#phase-3-client-integration)
7. [Phase 4: Migration & Optimization](#phase-4-migration--optimization)
8. [Phase 5: Production Deployment](#phase-5-production-deployment)
9. [Testing Strategy](#testing-strategy)
10. [Rollback Plan](#rollback-plan)
11. [Appendix: Scripts & Templates](#appendix-scripts--templates)

---

## Overview

This plan implements a **cloud-first, microservices architecture** combining:
- **Unified LLM Service Hub** - Centralized API-only LLM routing (Gemini + Claude)
- **WebSocket SEC Digester** - Standalone service for real-time filing analysis
- **Lightweight Main Bot** - WebSocket client for Discord alerts

### Key Decisions Made

✅ **No Local LLM** - API-only (fixes GPU overload)
✅ **WebSocket Architecture** - SEC Digester as standalone service
✅ **Redis Streams** - Message persistence and reliability
✅ **Cloud Deployment** - SEC service in cloud, bot runs anywhere

### Success Criteria

- [ ] SEC filings analyzed in <2s average
- [ ] 70%+ cache hit rate on LLM queries
- [ ] <50ms WebSocket latency
- [ ] Zero message loss (Redis Streams)
- [ ] Monthly cost < $1,000
- [ ] 50% code reduction (5,100 → 2,500 lines)

---

## Prerequisites

### Required Before Starting

#### 1. API Keys
```bash
# Google Cloud - Gemini API
# Get key from: https://makersuite.google.com/app/apikey
export GEMINI_API_KEY="your_key_here"

# Anthropic - Claude API
# Get key from: https://console.anthropic.com/
export ANTHROPIC_API_KEY="your_key_here"

# Test connectivity
curl -H "Content-Type: application/json" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  https://generativelanguage.googleapis.com/v1beta/models
```

#### 2. Infrastructure
```bash
# Redis (for caching + streams)
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Or managed Redis (recommended for production)
# AWS ElastiCache, Redis Cloud, etc.

# Verify Redis
redis-cli ping  # Should return "PONG"
```

#### 3. Development Environment
```bash
# Python 3.11+
python --version  # Should be 3.11 or higher

# Install poetry for dependency management
curl -sSL https://install.python-poetry.org | python3 -

# Verify
poetry --version
```

#### 4. Git Branch
```bash
# Create feature branch
git checkout -b feature/cloud-llm-websocket-integration

# Set up tracking
git push -u origin feature/cloud-llm-websocket-integration
```

#### 5. Disable Local Mistral
```bash
# Stop Ollama service
sudo systemctl stop ollama
sudo systemctl disable ollama

# Verify GPU is idle
watch -n 1 rocm-smi  # Should show low usage
```

### Verification Checklist

- [ ] Gemini API key working (1,500 free requests/day)
- [ ] Claude API key working
- [ ] Redis running locally or cloud instance ready
- [ ] Python 3.11+ installed
- [ ] Poetry installed
- [ ] Git branch created
- [ ] Ollama disabled (GPU at idle)

---

## Project Structure

### New Directory Layout

```
catalyst-bot/
├── src/
│   ├── catalyst_bot/              # Existing bot code
│   │   ├── services/              # NEW: Centralized services
│   │   │   ├── __init__.py
│   │   │   ├── llm/               # LLM service hub
│   │   │   │   ├── __init__.py
│   │   │   │   ├── service.py     # Main service interface
│   │   │   │   ├── router.py      # Intelligent routing
│   │   │   │   ├── cache.py       # Semantic caching
│   │   │   │   ├── prompts.py     # Template management
│   │   │   │   ├── monitor.py     # Usage tracking
│   │   │   │   └── providers/     # API adapters
│   │   │   │       ├── __init__.py
│   │   │   │       ├── base.py    # Abstract base
│   │   │   │       ├── gemini.py  # Google Gemini
│   │   │   │       └── claude.py  # Anthropic Claude
│   │   │   └── websocket/         # WebSocket client
│   │   │       ├── __init__.py
│   │   │       ├── client.py      # SEC WebSocket client
│   │   │       └── handlers.py    # Message handlers
│   │   │
│   │   └── [existing files...]
│   │
│   └── sec_digester_service/      # NEW: Standalone SEC service
│       ├── __init__.py
│       ├── main.py                # FastAPI app
│       ├── config.py              # Service configuration
│       ├── models.py              # Data models
│       ├── edgar/                 # EDGAR integration
│       │   ├── __init__.py
│       │   ├── monitor.py         # Filing monitor
│       │   ├── fetcher.py         # Document fetcher
│       │   └── parser.py          # Filing parser
│       ├── analysis/              # Analysis logic
│       │   ├── __init__.py
│       │   ├── analyzer.py        # Main analyzer
│       │   ├── numeric.py         # Numeric extraction
│       │   └── xbrl.py            # XBRL parsing
│       ├── websocket/             # WebSocket server
│       │   ├── __init__.py
│       │   ├── server.py          # WebSocket endpoints
│       │   └── broadcaster.py     # Redis → WebSocket
│       └── streams/               # Redis Streams
│           ├── __init__.py
│           ├── publisher.py       # Publish to Redis
│           └── consumer.py        # Consume from Redis
│
├── tests/
│   ├── services/                  # NEW: Service tests
│   │   ├── llm/
│   │   │   ├── test_service.py
│   │   │   ├── test_router.py
│   │   │   ├── test_cache.py
│   │   │   └── test_providers.py
│   │   └── websocket/
│   │       └── test_client.py
│   │
│   └── sec_digester_service/      # NEW: SEC service tests
│       ├── test_main.py
│       ├── test_analyzer.py
│       └── test_websocket.py
│
├── docs/
│   ├── architecture/              # NEW: Architecture docs
│   │   ├── LLM_SERVICE.md
│   │   ├── SEC_WEBSOCKET.md
│   │   └── DEPLOYMENT.md
│   └── guides/                    # NEW: Implementation guides
│       ├── LLM_INTEGRATION.md
│       ├── WEBSOCKET_CLIENT.md
│       └── TESTING.md
│
├── scripts/
│   ├── setup_dev_env.sh           # NEW: Dev environment setup
│   ├── test_llm_providers.py      # NEW: Test API connectivity
│   ├── test_websocket.py          # NEW: Test WebSocket
│   └── migrate_sec_code.py        # NEW: Migration helper
│
├── deployments/
│   ├── docker-compose.yml         # NEW: Local development
│   ├── docker-compose.prod.yml    # NEW: Production
│   └── k8s/                       # NEW: Kubernetes configs (optional)
│       ├── sec-digester.yaml
│       └── redis.yaml
│
├── .env.example                   # NEW: Example environment vars
├── pyproject.toml                 # Updated dependencies
└── README.md                      # Updated docs

```

### Key Changes from Current Structure

**Additions:**
- `services/llm/` - Unified LLM hub (replaces scattered LLM files)
- `services/websocket/` - WebSocket client for main bot
- `sec_digester_service/` - Standalone SEC service
- `deployments/` - Docker and K8s configs
- `scripts/` - Helper scripts for setup and testing

**Removals (to be deprecated):**
- `llm_client.py` → Replaced by `services/llm/`
- `llm_async.py` → Replaced by `services/llm/`
- `llm_hybrid.py` → Replaced by `services/llm/router.py`
- `llm_chain.py` → Replaced by `services/llm/service.py`
- `sec_llm_analyzer.py` → Moved to `sec_digester_service/analysis/`
- `sec_llm_cache.py` → Merged into `services/llm/cache.py`

---

## Phase 1: Foundation - LLM Service Hub

**Duration**: 2 weeks
**Goal**: Build centralized, cloud-only LLM service

### Context for Claude Code

When implementing this phase, you're building a **unified abstraction layer** over multiple LLM providers. The key pattern is:

1. **Single Interface** (`LLMService`) - All features call this
2. **Intelligent Router** - Selects best model for task complexity
3. **Semantic Cache** - Avoids duplicate API calls (70% hit rate target)
4. **Provider Adapters** - Swap providers without changing callers

**Design Philosophy**:
- Async-first (use `asyncio` everywhere)
- Type-safe (use `Pydantic` for all data)
- Fail-fast (validate early, clear errors)
- Observable (log everything, track costs)

---

### Ticket 1.1: Project Setup & Dependencies

**Priority**: Critical
**Estimated Time**: 2 hours
**Dependencies**: None

#### Context

Setting up the foundation for cloud-first development. We're removing all local LLM dependencies (Ollama) and adding cloud API clients.

#### Implementation Steps

1. **Update `pyproject.toml`**

```toml
# pyproject.toml
[tool.poetry]
name = "catalyst-bot"
version = "2.0.0"
description = "Trading bot with cloud-first LLM and WebSocket SEC digester"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"

# Web frameworks
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
websockets = "^12.0"
aiohttp = "^3.9.0"

# LLM providers (NO Ollama)
google-generativeai = "^0.3.0"  # Gemini
anthropic = "^0.18.0"            # Claude

# Data & validation
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"

# Caching & messaging
redis = {extras = ["hiredis"], version = "^5.0.0"}
sentence-transformers = "^2.3.0"  # Semantic cache

# Monitoring
prometheus-client = "^0.19.0"

# Utilities
python-dotenv = "^1.0.0"
structlog = "^24.1.0"

# Existing dependencies...
discord-py = "^2.3.2"
# ... (keep all existing)

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.23.0"
pytest-cov = "^4.1.0"
black = "^23.12.0"
ruff = "^0.1.0"
mypy = "^1.8.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

2. **Install dependencies**

```bash
# Remove old dependencies (Ollama-related)
poetry remove ollama llama-cpp-python  # If present

# Install new dependencies
poetry install

# Update lock file
poetry lock --no-update
```

3. **Create `.env.example`**

```bash
# .env.example

# ============================================================================
# LLM Provider Configuration
# ============================================================================

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL_DEFAULT=gemini-2.5-flash

# Anthropic Claude API
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL_DEFAULT=claude-3-5-sonnet-20241022

# ============================================================================
# LLM Service Configuration
# ============================================================================

# Routing strategy: cost_optimized, performance, balanced
LLM_ROUTING_STRATEGY=cost_optimized

# Complexity threshold for Pro tier (0.0 - 1.0)
LLM_COMPLEXITY_THRESHOLD=0.7

# Enable cost tracking
LLM_COST_TRACKING=true
LLM_COST_ALERT_DAILY=30.00
LLM_COST_ALERT_MONTHLY=800.00
LLM_COST_HARD_LIMIT_MONTHLY=1000.00

# ============================================================================
# Caching Configuration
# ============================================================================

# Redis connection
REDIS_URL=redis://localhost:6379

# Cache settings
LLM_CACHE_ENABLED=true
LLM_CACHE_TTL_SECONDS=86400
LLM_CACHE_SIMILARITY_THRESHOLD=0.95

# ============================================================================
# SEC Digester Service
# ============================================================================

# WebSocket connection (will be set in Phase 2)
# SEC_DIGESTER_URL=ws://localhost:8765/ws/filings

# ============================================================================
# Existing Configuration
# ============================================================================

# Discord
DISCORD_TOKEN=your_discord_token

# ... (keep all existing vars)
```

4. **Copy to actual `.env`**

```bash
cp .env.example .env

# Edit .env with real keys
nano .env  # or your preferred editor
```

5. **Create setup script**

```bash
# scripts/setup_dev_env.sh
#!/bin/bash
set -e

echo "🚀 Setting up development environment..."

# Check Python version
python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
if (( $(echo "$python_version < 3.11" | bc -l) )); then
    echo "❌ Python 3.11+ required (found $python_version)"
    exit 1
fi
echo "✅ Python $python_version"

# Check Poetry
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry not found. Install from https://python-poetry.org/"
    exit 1
fi
echo "✅ Poetry installed"

# Install dependencies
echo "📦 Installing dependencies..."
poetry install

# Check Redis
if ! redis-cli ping &> /dev/null; then
    echo "⚠️  Redis not running. Start with: docker run -d -p 6379:6379 redis:7-alpine"
else
    echo "✅ Redis connected"
fi

# Check environment
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "📝 Edit .env with your API keys"
else
    echo "✅ .env file exists"
fi

# Disable Ollama
if systemctl is-active --quiet ollama; then
    echo "⚠️  Ollama is running. Disabling..."
    sudo systemctl stop ollama
    sudo systemctl disable ollama
    echo "✅ Ollama disabled"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your API keys"
echo "2. Start Redis: docker run -d -p 6379:6379 redis:7-alpine"
echo "3. Run tests: poetry run pytest"
echo "4. Start development: poetry run python -m catalyst_bot"
```

Make executable:
```bash
chmod +x scripts/setup_dev_env.sh
```

#### Acceptance Criteria

- [ ] `poetry install` succeeds with no errors
- [ ] `.env` file exists with API keys
- [ ] Redis running and accessible
- [ ] Ollama disabled (GPU idle)
- [ ] Setup script runs successfully

#### Testing

```bash
# Run setup
./scripts/setup_dev_env.sh

# Verify dependencies
poetry run python -c "import google.generativeai; import anthropic; print('✅ LLM providers imported')"

# Verify Redis
poetry run python -c "import redis; r = redis.Redis(); r.ping(); print('✅ Redis connected')"
```

#### Documentation

Create `docs/guides/SETUP.md`:

```markdown
# Development Setup Guide

## Prerequisites
- Python 3.11+
- Poetry
- Redis (local or cloud)
- API keys (Gemini, Claude)

## Quick Start
\`\`\`bash
./scripts/setup_dev_env.sh
\`\`\`

## Manual Setup
[Include manual steps if script fails]

## Verification
[Include test commands]
```

---

### Ticket 1.2: LLM Service Core Interface

**Priority**: Critical
**Estimated Time**: 6 hours
**Dependencies**: Ticket 1.1

#### Context

This is the **heart of the new architecture**. Every feature (SEC digester, sentiment analysis, news classification) will use this interface.

**Key Design Decisions**:
- Async-only (use `async def` and `await`)
- Pydantic for type safety
- Provider-agnostic (caller doesn't know if using Gemini or Claude)
- Observable (log all requests, track costs)

#### Implementation Steps

1. **Create base models**

```python
# src/catalyst_bot/services/llm/models.py
"""
Data models for LLM service.

These models define the contract between callers and the LLM service.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class TaskComplexity(str, Enum):
    """Task complexity levels for routing."""
    SIMPLE = "simple"       # Local or Flash Lite
    MEDIUM = "medium"       # Gemini Flash
    COMPLEX = "complex"     # Gemini Pro
    CRITICAL = "critical"   # Claude Opus


class OutputFormat(str, Enum):
    """Supported output formats."""
    TEXT = "text"           # Free-form text
    JSON = "json"           # Structured JSON
    PYDANTIC = "pydantic"   # Pydantic model validation


class LLMRequest(BaseModel):
    """
    Standardized LLM request format.

    All features use this to interact with LLM service.

    Example:
        request = LLMRequest(
            prompt="Analyze this 8-K filing...",
            complexity=TaskComplexity.MEDIUM,
            output_format=OutputFormat.JSON
        )
    """
    # Core fields
    prompt: str = Field(..., description="The prompt to send to LLM")
    system_prompt: Optional[str] = Field(None, description="System prompt (optional)")

    # Routing hints
    complexity: TaskComplexity = Field(
        default=TaskComplexity.MEDIUM,
        description="Task complexity for routing"
    )
    max_tokens: int = Field(default=1024, ge=1, le=100000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Output control
    output_format: OutputFormat = Field(default=OutputFormat.TEXT)
    output_schema: Optional[type[BaseModel]] = Field(
        None,
        description="Pydantic model for validation (if output_format=PYDANTIC)"
    )

    # Optimization
    enable_cache: bool = Field(default=True, description="Enable semantic caching")
    cache_ttl_seconds: int = Field(default=86400, description="Cache TTL (24 hours)")
    compress_prompt: bool = Field(default=True, description="Enable prompt compression")

    # Metadata
    request_id: Optional[str] = Field(None, description="Unique request ID")
    user_id: Optional[str] = Field(None, description="User/ticker ID for scoping")
    feature_name: str = Field(default="unknown", description="Calling feature name")

    # Advanced
    fallback_on_error: bool = Field(default=True, description="Try fallback provider on error")
    max_retries: int = Field(default=3, ge=0, le=5)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)

    class Config:
        use_enum_values = True


class LLMResponse(BaseModel):
    """
    Standardized LLM response format.

    Contains both the response text and extensive metadata for monitoring.
    """
    # Core response
    text: str = Field(..., description="Generated text")
    parsed_output: Optional[Any] = Field(None, description="Parsed JSON/Pydantic output")

    # Metadata
    provider: str = Field(..., description="Provider used (gemini, claude, etc.)")
    model: str = Field(..., description="Specific model (gemini-2.5-flash, etc.)")
    cached: bool = Field(default=False, description="Was response from cache?")

    # Performance
    latency_ms: float = Field(..., description="Total request latency")
    tokens_input: int = Field(default=0, description="Input tokens")
    tokens_output: int = Field(default=0, description="Output tokens")
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD")

    # Quality
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    finish_reason: str = Field(default="complete", description="Completion reason")

    # Debugging
    cache_key: Optional[str] = Field(None, description="Cache key (if cached)")
    prompt_compressed: bool = Field(default=False, description="Was prompt compressed?")
    retries: int = Field(default=0, description="Number of retries")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Apple reports strong Q4 earnings...",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "cached": False,
                "latency_ms": 324.5,
                "tokens_input": 450,
                "tokens_output": 120,
                "cost_usd": 0.000045
            }
        }


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""
    pass


class ProviderError(LLMServiceError):
    """Error from LLM provider (API error, rate limit, etc.)."""
    pass


class ValidationError(LLMServiceError):
    """Error validating request or response."""
    pass
```

2. **Create main service interface**

```python
# src/catalyst_bot/services/llm/service.py
"""
Unified LLM Service - Central orchestrator for all LLM operations.

This is the main entry point for all LLM interactions across Catalyst-Bot.

Usage:
    # Initialize service (singleton recommended)
    llm_service = LLMService()

    # Simple query
    request = LLMRequest(
        prompt="Classify this news headline...",
        complexity=TaskComplexity.SIMPLE
    )
    response = await llm_service.query(request)

    # Structured output
    request = LLMRequest(
        prompt="Analyze this filing...",
        output_format=OutputFormat.PYDANTIC,
        output_schema=FilingAnalysis
    )
    response = await llm_service.query(request)
    analysis = response.parsed_output  # FilingAnalysis instance
"""

import asyncio
import time
from typing import List, Optional
import structlog

from .models import LLMRequest, LLMResponse, LLMServiceError
from .router import ModelRouter
from .cache import SemanticCache
from .monitor import UsageMonitor
from .config import LLMServiceConfig

logger = structlog.get_logger()


class LLMService:
    """
    Unified LLM service hub.

    Provides centralized access to multiple LLM providers with:
    - Intelligent routing based on task complexity
    - Semantic caching (60-80% hit rate)
    - Cost tracking and budget enforcement
    - Automatic failover and retry logic
    """

    def __init__(self, config: Optional[LLMServiceConfig] = None):
        """Initialize LLM service with configuration."""
        self.config = config or LLMServiceConfig.from_env()

        # Components (lazy initialization)
        self._router: Optional[ModelRouter] = None
        self._cache: Optional[SemanticCache] = None
        self._monitor: Optional[UsageMonitor] = None
        self._providers: dict = {}

        self._initialized = False
        logger.info("llm_service.init", config=self.config.dict())

    async def initialize(self):
        """Initialize service components (call once at startup)."""
        if self._initialized:
            return

        logger.info("llm_service.initializing")

        # Initialize components
        from .router import ModelRouter
        from .cache import SemanticCache
        from .monitor import UsageMonitor

        self._router = ModelRouter(config=self.config)
        self._cache = SemanticCache(config=self.config)
        self._monitor = UsageMonitor(config=self.config)

        # Initialize providers (lazy load)
        await self._router.initialize()
        await self._cache.initialize()

        self._initialized = True
        logger.info("llm_service.initialized")

    async def query(self, request: LLMRequest) -> LLMResponse:
        """
        Execute LLM query with intelligent routing and optimization.

        This is the main entry point for all LLM operations.

        Args:
            request: Standardized LLM request

        Returns:
            LLMResponse with result and metadata

        Raises:
            LLMServiceError: On unrecoverable errors

        Example:
            request = LLMRequest(
                prompt="Analyze: revenue grew 25% YoY",
                complexity=TaskComplexity.SIMPLE,
                feature_name="sentiment_analysis"
            )
            response = await llm.query(request)
            print(response.text)
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        logger.info(
            "llm_service.query.start",
            feature=request.feature_name,
            complexity=request.complexity,
            prompt_len=len(request.prompt)
        )

        try:
            # 1. Check cache (if enabled)
            if request.enable_cache:
                cached = await self._check_cache(request)
                if cached:
                    logger.info("llm_service.query.cache_hit")
                    return cached

            # 2. Route to appropriate provider
            provider_name, model_name = self._router.select_provider(request)
            logger.info("llm_service.query.routed", provider=provider_name, model=model_name)

            # 3. Execute query (with retry logic)
            response = await self._execute_with_retry(request, provider_name, model_name)

            # 4. Cache response (if enabled)
            if request.enable_cache:
                await self._save_to_cache(request, response)

            # 5. Track usage
            await self._monitor.track_usage(request, response)

            # 6. Return response
            elapsed_ms = (time.time() - start_time) * 1000
            response.latency_ms = elapsed_ms

            logger.info(
                "llm_service.query.complete",
                provider=response.provider,
                latency_ms=elapsed_ms,
                cost_usd=response.cost_usd,
                cached=response.cached
            )

            return response

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "llm_service.query.error",
                error=str(e),
                latency_ms=elapsed_ms
            )
            raise LLMServiceError(f"Query failed: {e}") from e

    async def query_batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Process multiple requests efficiently with batching.

        Executes requests concurrently while respecting rate limits.

        Args:
            requests: List of LLM requests

        Returns:
            List of responses (same order as requests)

        Example:
            requests = [
                LLMRequest(prompt="Classify: ...") for _ in range(10)
            ]
            responses = await llm.query_batch(requests)
        """
        logger.info("llm_service.query_batch.start", count=len(requests))

        # Execute concurrently with semaphore for rate limiting
        semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

        async def query_with_limit(req):
            async with semaphore:
                return await self.query(req)

        responses = await asyncio.gather(
            *[query_with_limit(req) for req in requests],
            return_exceptions=True
        )

        # Convert exceptions to error responses
        results = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                logger.error("llm_service.query_batch.error", index=i, error=str(response))
                # Return error response
                results.append(LLMResponse(
                    text=f"Error: {response}",
                    provider="error",
                    model="error",
                    latency_ms=0.0,
                    finish_reason="error"
                ))
            else:
                results.append(response)

        logger.info("llm_service.query_batch.complete", count=len(results))
        return results

    async def estimate_cost(self, request: LLMRequest) -> float:
        """
        Estimate cost in USD before executing.

        Useful for budget checks before expensive operations.

        Args:
            request: LLM request to estimate

        Returns:
            Estimated cost in USD

        Example:
            request = LLMRequest(prompt=long_filing_text)
            cost = await llm.estimate_cost(request)
            if cost < 0.10:
                response = await llm.query(request)
        """
        if not self._initialized:
            await self.initialize()

        # Select provider/model
        provider_name, model_name = self._router.select_provider(request)

        # Estimate tokens
        estimated_tokens = len(request.prompt) // 4  # Rough estimate

        # Get cost per token
        cost_per_million = self._router.get_cost_per_million(provider_name, model_name)
        estimated_cost = (estimated_tokens / 1_000_000) * cost_per_million

        return estimated_cost

    def get_stats(self) -> dict:
        """
        Get usage statistics and performance metrics.

        Returns:
            Dict with stats (requests, costs, latency, cache hits, etc.)
        """
        if not self._initialized:
            return {}

        return {
            "monitor": self._monitor.get_stats(),
            "cache": self._cache.get_stats(),
            "router": self._router.get_stats(),
        }

    # ========================================================================
    # Private methods
    # ========================================================================

    async def _check_cache(self, request: LLMRequest) -> Optional[LLMResponse]:
        """Check semantic cache for similar request."""
        return await self._cache.get(request)

    async def _save_to_cache(self, request: LLMRequest, response: LLMResponse):
        """Save response to cache."""
        await self._cache.set(request, response, ttl=request.cache_ttl_seconds)

    async def _execute_with_retry(
        self,
        request: LLMRequest,
        provider_name: str,
        model_name: str
    ) -> LLMResponse:
        """Execute query with automatic retry and fallback logic."""
        max_retries = request.max_retries
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # Get provider instance
                provider = await self._router.get_provider(provider_name)

                # Execute query
                response = await provider.query(
                    prompt=request.prompt,
                    system_prompt=request.system_prompt,
                    model=model_name,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature
                )

                # Validate output format
                if request.output_format == OutputFormat.PYDANTIC and request.output_schema:
                    response = await self._validate_pydantic(response, request.output_schema)

                response.retries = retry_count
                return response

            except Exception as e:
                retry_count += 1
                logger.warning(
                    "llm_service.retry",
                    retry=retry_count,
                    max_retries=max_retries,
                    error=str(e)
                )

                if retry_count > max_retries:
                    # Try fallback provider if enabled
                    if request.fallback_on_error:
                        fallback_provider, fallback_model = self._router.get_fallback()
                        if fallback_provider != provider_name:
                            logger.info("llm_service.fallback", provider=fallback_provider)
                            provider_name = fallback_provider
                            model_name = fallback_model
                            retry_count = 0  # Reset retries for fallback
                            continue

                    raise

                # Exponential backoff
                await asyncio.sleep(2 ** retry_count)

        raise LLMServiceError("Max retries exceeded")

    async def _validate_pydantic(self, response: LLMResponse, schema: type[BaseModel]) -> LLMResponse:
        """Validate and parse Pydantic output."""
        import json

        try:
            # Parse JSON from response
            data = json.loads(response.text)

            # Validate with Pydantic
            parsed = schema(**data)
            response.parsed_output = parsed

            return response

        except Exception as e:
            raise LLMServiceError(f"Failed to validate Pydantic output: {e}") from e


# ============================================================================
# Singleton instance (recommended pattern)
# ============================================================================

_llm_service_instance: Optional[LLMService] = None


async def get_llm_service() -> LLMService:
    """
    Get singleton LLM service instance.

    Usage:
        llm = await get_llm_service()
        response = await llm.query(request)
    """
    global _llm_service_instance

    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
        await _llm_service_instance.initialize()

    return _llm_service_instance
```

#### Acceptance Criteria

- [ ] `LLMRequest` and `LLMResponse` models defined
- [ ] `LLMService` class with `query()` method
- [ ] `query_batch()` for concurrent requests
- [ ] `estimate_cost()` for budget checks
- [ ] Singleton pattern implemented
- [ ] Type hints on all methods
- [ ] Docstrings with examples

#### Testing

```python
# tests/services/llm/test_service.py
import pytest
from catalyst_bot.services.llm import LLMService, LLMRequest, TaskComplexity

@pytest.mark.asyncio
async def test_llm_service_initialization():
    """Test service initializes correctly."""
    service = LLMService()
    await service.initialize()
    assert service._initialized

@pytest.mark.asyncio
async def test_llm_query_simple():
    """Test simple LLM query."""
    service = LLMService()
    await service.initialize()

    request = LLMRequest(
        prompt="Say 'Hello, World!'",
        complexity=TaskComplexity.SIMPLE,
        max_tokens=20
    )

    response = await service.query(request)

    assert "hello" in response.text.lower()
    assert response.provider in ["gemini", "claude"]
    assert response.latency_ms > 0
    assert response.cost_usd >= 0

@pytest.mark.asyncio
async def test_cost_estimation():
    """Test cost estimation."""
    service = LLMService()
    await service.initialize()

    request = LLMRequest(
        prompt="A" * 1000,  # Long prompt
        complexity=TaskComplexity.COMPLEX
    )

    cost = await service.estimate_cost(request)
    assert cost > 0
    assert cost < 1.0  # Should be < $1
```

Run tests:
```bash
poetry run pytest tests/services/llm/test_service.py -v
```

---

### Ticket 1.3: Provider Adapters (Gemini + Claude)

**Priority**: Critical
**Estimated Time**: 6 hours
**Dependencies**: Ticket 1.2

#### Context

Provider adapters wrap the actual API clients (Gemini, Claude) and provide a **uniform interface**. The router selects a provider, but the calling code doesn't need to know which one.

**Key Pattern**: Abstract base class + concrete implementations

#### Implementation Steps

1. **Create base provider interface**

```python
# src/catalyst_bot/services/llm/providers/base.py
"""
Abstract base class for LLM providers.

All provider implementations (Gemini, Claude, etc.) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Optional
import structlog

from ..models import LLMResponse

logger = structlog.get_logger()


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Subclasses must implement query() method and provide pricing info.
    """

    def __init__(self, api_key: str, **kwargs):
        """Initialize provider with API key."""
        self.api_key = api_key
        self.config = kwargs
        logger.info(f"{self.__class__.__name__}.init")

    @abstractmethod
    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Execute LLM query.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            model: Specific model name
            max_tokens: Max tokens to generate
            temperature: Sampling temperature

        Returns:
            LLMResponse with text and metadata

        Raises:
            ProviderError: On API errors
        """
        raise NotImplementedError

    @abstractmethod
    def get_cost_per_million(self, model: str) -> float:
        """
        Get cost per million tokens for model.

        Args:
            model: Model name

        Returns:
            Cost in USD per 1M input tokens
        """
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        List available models for this provider.

        Returns:
            List of model names
        """
        raise NotImplementedError

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Simple heuristic: ~4 chars per token.
        Override for provider-specific tokenizers.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4

    def calculate_cost(self, tokens_input: int, tokens_output: int, model: str) -> float:
        """
        Calculate cost for request.

        Args:
            tokens_input: Input tokens
            tokens_output: Output tokens
            model: Model name

        Returns:
            Cost in USD
        """
        cost_per_million = self.get_cost_per_million(model)
        total_tokens = tokens_input + tokens_output
        return (total_tokens / 1_000_000) * cost_per_million
```

2. **Implement Gemini provider**

```python
# src/catalyst_bot/services/llm/providers/gemini.py
"""
Google Gemini API provider.

Supports:
- gemini-2.0-flash-lite
- gemini-2.5-flash
- gemini-2.5-pro
"""

import time
from typing import Optional
import structlog
import google.generativeai as genai

from .base import BaseLLMProvider
from ..models import LLMResponse, ProviderError

logger = structlog.get_logger()


# Pricing (as of 2025-01)
GEMINI_PRICING = {
    "gemini-2.0-flash-lite": 0.02,      # $0.02 per 1M tokens
    "gemini-2.5-flash": 0.075,          # $0.075 per 1M tokens
    "gemini-1.5-flash-002": 0.075,
    "gemini-2.5-pro": 1.25,             # $1.25 per 1M tokens
    "gemini-1.5-pro-002": 1.25,
}


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini API provider.

    Uses google-generativeai Python SDK.

    Rate Limits (Free Tier):
    - 1,500 requests/day
    - 60 requests/minute

    Example:
        provider = GeminiProvider(api_key="your_key")
        response = await provider.query(
            prompt="Explain quantum physics",
            model="gemini-2.5-flash"
        )
    """

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)

        # Configure SDK
        genai.configure(api_key=api_key)

        # Default model
        self.default_model = kwargs.get("default_model", "gemini-2.5-flash")

        logger.info("gemini.initialized", default_model=self.default_model)

    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """Execute Gemini API query."""
        model = model or self.default_model
        start_time = time.time()

        logger.info("gemini.query.start", model=model, prompt_len=len(prompt))

        try:
            # Create model instance
            gemini_model = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                }
            )

            # Build prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # Generate
            response = await gemini_model.generate_content_async(full_prompt)

            # Extract response text
            text = response.text

            # Calculate tokens (Gemini doesn't provide token count in response)
            tokens_input = self.estimate_tokens(full_prompt)
            tokens_output = self.estimate_tokens(text)
            cost = self.calculate_cost(tokens_input, tokens_output, model)

            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(
                "gemini.query.complete",
                latency_ms=elapsed_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost
            )

            return LLMResponse(
                text=text,
                provider="gemini",
                model=model,
                cached=False,
                latency_ms=elapsed_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost,
                finish_reason=response.candidates[0].finish_reason.name if response.candidates else "unknown"
            )

        except Exception as e:
            logger.error("gemini.query.error", error=str(e))
            raise ProviderError(f"Gemini API error: {e}") from e

    def get_cost_per_million(self, model: str) -> float:
        """Get cost per million tokens."""
        return GEMINI_PRICING.get(model, 0.075)  # Default to Flash pricing

    def list_models(self) -> list[str]:
        """List available Gemini models."""
        return list(GEMINI_PRICING.keys())
```

3. **Implement Claude provider**

```python
# src/catalyst_bot/services/llm/providers/claude.py
"""
Anthropic Claude API provider.

Supports:
- claude-3-5-sonnet-20241022
- claude-3-haiku-20240307
- claude-3-opus-20240229
"""

import time
from typing import Optional
import structlog
from anthropic import AsyncAnthropic

from .base import BaseLLMProvider
from ..models import LLMResponse, ProviderError

logger = structlog.get_logger()


# Pricing (as of 2025-01)
CLAUDE_PRICING = {
    "claude-3-5-sonnet-20241022": 3.00,     # $3.00 per 1M input tokens
    "claude-3-haiku-20240307": 0.25,        # $0.25 per 1M tokens
    "claude-3-opus-20240229": 15.00,        # $15.00 per 1M tokens
}


class ClaudeProvider(BaseLLMProvider):
    """
    Anthropic Claude API provider.

    Uses anthropic Python SDK.

    Rate Limits:
    - Varies by tier (check console.anthropic.com)

    Example:
        provider = ClaudeProvider(api_key="your_key")
        response = await provider.query(
            prompt="Explain quantum physics",
            model="claude-3-5-sonnet-20241022"
        )
    """

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)

        # Initialize async client
        self.client = AsyncAnthropic(api_key=api_key)

        # Default model
        self.default_model = kwargs.get("default_model", "claude-3-5-sonnet-20241022")

        logger.info("claude.initialized", default_model=self.default_model)

    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """Execute Claude API query."""
        model = model or self.default_model
        start_time = time.time()

        logger.info("claude.query.start", model=model, prompt_len=len(prompt))

        try:
            # Build messages
            messages = [{"role": "user", "content": prompt}]

            # Call API
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else None,
                messages=messages
            )

            # Extract text
            text = response.content[0].text

            # Get token counts (Claude provides these!)
            tokens_input = response.usage.input_tokens
            tokens_output = response.usage.output_tokens
            cost = self.calculate_cost(tokens_input, tokens_output, model)

            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(
                "claude.query.complete",
                latency_ms=elapsed_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost
            )

            return LLMResponse(
                text=text,
                provider="claude",
                model=model,
                cached=False,
                latency_ms=elapsed_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost,
                finish_reason=response.stop_reason
            )

        except Exception as e:
            logger.error("claude.query.error", error=str(e))
            raise ProviderError(f"Claude API error: {e}") from e

    def get_cost_per_million(self, model: str) -> float:
        """Get cost per million tokens."""
        return CLAUDE_PRICING.get(model, 3.00)  # Default to Sonnet pricing

    def list_models(self) -> list[str]:
        """List available Claude models."""
        return list(CLAUDE_PRICING.keys())
```

4. **Create provider factory**

```python
# src/catalyst_bot/services/llm/providers/__init__.py
"""
LLM provider implementations.

Supported providers:
- Gemini (Google)
- Claude (Anthropic)
"""

from .base import BaseLLMProvider
from .gemini import GeminiProvider
from .claude import ClaudeProvider

__all__ = [
    "BaseLLMProvider",
    "GeminiProvider",
    "ClaudeProvider",
    "get_provider",
]


def get_provider(provider_name: str, api_key: str, **kwargs) -> BaseLLMProvider:
    """
    Factory function to get provider instance.

    Args:
        provider_name: Provider name ("gemini", "claude")
        api_key: API key for provider
        **kwargs: Additional configuration

    Returns:
        Provider instance

    Raises:
        ValueError: If provider not found

    Example:
        provider = get_provider("gemini", api_key="your_key")
        response = await provider.query("Hello, world!")
    """
    providers = {
        "gemini": GeminiProvider,
        "claude": ClaudeProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown provider: {provider_name}")

    return provider_class(api_key=api_key, **kwargs)
```

#### Acceptance Criteria

- [ ] `BaseLLMProvider` abstract class defined
- [ ] `GeminiProvider` implemented with pricing
- [ ] `ClaudeProvider` implemented with pricing
- [ ] Provider factory function
- [ ] Token estimation method
- [ ] Cost calculation method
- [ ] Error handling for API failures

#### Testing

```python
# scripts/test_llm_providers.py
"""Test script to verify LLM provider connectivity."""

import asyncio
import os
from catalyst_bot.services.llm.providers import get_provider

async def test_gemini():
    """Test Gemini provider."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set")
        return

    print("Testing Gemini provider...")
    provider = get_provider("gemini", api_key=api_key)

    response = await provider.query(
        prompt="Say 'Gemini test successful' and nothing else.",
        model="gemini-2.5-flash",
        max_tokens=20
    )

    print(f"✅ Response: {response.text}")
    print(f"   Model: {response.model}")
    print(f"   Latency: {response.latency_ms:.0f}ms")
    print(f"   Cost: ${response.cost_usd:.6f}")

async def test_claude():
    """Test Claude provider."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set")
        return

    print("\nTesting Claude provider...")
    provider = get_provider("claude", api_key=api_key)

    response = await provider.query(
        prompt="Say 'Claude test successful' and nothing else.",
        model="claude-3-5-sonnet-20241022",
        max_tokens=20
    )

    print(f"✅ Response: {response.text}")
    print(f"   Model: {response.model}")
    print(f"   Latency: {response.latency_ms:.0f}ms")
    print(f"   Cost: ${response.cost_usd:.6f}")

async def main():
    """Run all tests."""
    await test_gemini()
    await test_claude()
    print("\n✅ All providers working!")

if __name__ == "__main__":
    asyncio.run(main())
```

Run test:
```bash
poetry run python scripts/test_llm_providers.py
```

Expected output:
```
Testing Gemini provider...
✅ Response: Gemini test successful
   Model: gemini-2.5-flash
   Latency: 324ms
   Cost: $0.000012

Testing Claude provider...
✅ Response: Claude test successful
   Model: claude-3-5-sonnet-20241022
   Latency: 456ms
   Cost: $0.000045

✅ All providers working!
```

---

### Ticket 1.4: Intelligent Router

**Priority**: High
**Estimated Time**: 4 hours
**Dependencies**: Ticket 1.3

#### Context

The router decides **which model to use** based on task complexity. This is where cost optimization happens.

**Routing Logic**:
- Simple tasks → Gemini Flash Lite (cheapest)
- Medium tasks → Gemini Flash (best value)
- Complex tasks → Gemini Pro (deep analysis)
- Critical tasks → Claude Sonnet (highest accuracy)

#### Implementation

```python
# src/catalyst_bot/services/llm/router.py
"""
Intelligent model router with complexity-based selection.

Automatically selects the best model for each task based on:
- Task complexity (simple/medium/complex/critical)
- Content length
- Required accuracy
- Cost budget
- Provider availability
"""

import random
from typing import Tuple, Dict
import structlog

from .models import LLMRequest, TaskComplexity
from .providers import get_provider, BaseLLMProvider
from .config import LLMServiceConfig

logger = structlog.get_logger()


class ModelRouter:
    """
    Routes requests to optimal model based on task characteristics.

    Routing Strategy:
    - 60% → Gemini Flash Lite (simple tasks)
    - 30% → Gemini Flash (medium tasks)
    - 8% → Gemini Pro (complex tasks)
    - 2% → Claude Sonnet (critical tasks)
    """

    # Routing decision matrix
    ROUTING_RULES = {
        TaskComplexity.SIMPLE: [
            ("gemini_flash_lite", 0.70),     # 70% to Flash Lite
            ("gemini_flash", 0.25),          # 25% to Flash
            ("gemini_pro", 0.05),            # 5% fallback to Pro
        ],
        TaskComplexity.MEDIUM: [
            ("gemini_flash", 0.90),          # 90% to Flash
            ("gemini_pro", 0.10),            # 10% to Pro
        ],
        TaskComplexity.COMPLEX: [
            ("gemini_pro", 0.80),            # 80% to Pro
            ("claude_sonnet", 0.20),         # 20% to Claude
        ],
        TaskComplexity.CRITICAL: [
            ("claude_sonnet", 1.0),          # 100% to Claude
        ],
    }

    # Model name mapping
    MODEL_NAMES = {
        "gemini_flash_lite": "gemini-2.0-flash-lite",
        "gemini_flash": "gemini-2.5-flash",
        "gemini_pro": "gemini-2.5-pro",
        "claude_sonnet": "claude-3-5-sonnet-20241022",
        "claude_haiku": "claude-3-haiku-20240307",
    }

    def __init__(self, config: LLMServiceConfig):
        self.config = config
        self._providers: Dict[str, BaseLLMProvider] = {}
        self._stats = {
            "requests_by_provider": {},
            "requests_by_complexity": {},
        }

    async def initialize(self):
        """Initialize provider instances."""
        # Gemini provider
        if self.config.gemini_api_key:
            from .providers.gemini import GeminiProvider
            self._providers["gemini"] = GeminiProvider(
                api_key=self.config.gemini_api_key
            )
            logger.info("router.provider.initialized", provider="gemini")

        # Claude provider
        if self.config.anthropic_api_key:
            from .providers.claude import ClaudeProvider
            self._providers["claude"] = ClaudeProvider(
                api_key=self.config.anthropic_api_key
            )
            logger.info("router.provider.initialized", provider="claude")

    def select_provider(self, request: LLMRequest) -> Tuple[str, str]:
        """
        Select optimal provider and model for request.

        Returns:
            (provider_name, model_name)

        Example:
            provider, model = router.select_provider(request)
            # ("gemini", "gemini-2.5-flash")
        """
        # Auto-detect complexity if needed
        complexity = request.complexity
        if complexity == TaskComplexity.MEDIUM:
            complexity = self._auto_detect_complexity(request)

        # Get routing rules for complexity
        rules = self.ROUTING_RULES.get(complexity, self.ROUTING_RULES[TaskComplexity.MEDIUM])

        # Select based on probability distribution
        rand = random.random()
        cumulative = 0.0

        for model_key, prob in rules:
            cumulative += prob
            if rand < cumulative:
                provider_name = self._get_provider_name(model_key)
                model_name = self.MODEL_NAMES[model_key]

                # Track stats
                self._stats["requests_by_provider"][provider_name] = \
                    self._stats["requests_by_provider"].get(provider_name, 0) + 1
                self._stats["requests_by_complexity"][complexity.value] = \
                    self._stats["requests_by_complexity"].get(complexity.value, 0) + 1

                logger.info(
                    "router.select",
                    complexity=complexity.value,
                    provider=provider_name,
                    model=model_name
                )

                return provider_name, model_name

        # Fallback to first option
        model_key = rules[0][0]
        provider_name = self._get_provider_name(model_key)
        model_name = self.MODEL_NAMES[model_key]
        return provider_name, model_name

    async def get_provider(self, provider_name: str) -> BaseLLMProvider:
        """Get provider instance by name."""
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider not initialized: {provider_name}")
        return provider

    def get_fallback(self) -> Tuple[str, str]:
        """
        Get fallback provider and model.

        Returns:
            (provider_name, model_name) for fallback
        """
        # Use Claude Sonnet as ultimate fallback
        return "claude", self.MODEL_NAMES["claude_sonnet"]

    def get_cost_per_million(self, provider_name: str, model_name: str) -> float:
        """Get cost per million tokens for model."""
        provider = self._providers.get(provider_name)
        if provider:
            return provider.get_cost_per_million(model_name)
        return 0.0

    def get_stats(self) -> dict:
        """Get routing statistics."""
        return self._stats

    # ========================================================================
    # Private methods
    # ========================================================================

    def _auto_detect_complexity(self, request: LLMRequest) -> TaskComplexity:
        """
        Automatically detect task complexity based on request characteristics.

        Heuristics:
        - Prompt length
        - Keywords ("analyze", "extract", "compare")
        - Output format (Pydantic = more complex)
        - Max tokens requested
        """
        score = 0.0

        # Length-based scoring
        prompt_len = len(request.prompt)
        if prompt_len > 2000:
            score += 0.4
        elif prompt_len > 500:
            score += 0.2

        # Keyword-based scoring
        complex_keywords = ["analyze", "extract", "summarize", "compare", "evaluate", "explain"]
        text_lower = request.prompt.lower()
        keyword_count = sum(1 for kw in complex_keywords if kw in text_lower)
        score += min(0.3, keyword_count * 0.1)

        # Output format scoring
        if request.output_format == OutputFormat.PYDANTIC:
            if request.output_schema:
                field_count = len(request.output_schema.__fields__)
                if field_count > 5:
                    score += 0.2

        # Token limit scoring
        if request.max_tokens > 2048:
            score += 0.1

        # Map score to complexity
        if score < 0.3:
            return TaskComplexity.SIMPLE
        elif score < 0.7:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.COMPLEX

    def _get_provider_name(self, model_key: str) -> str:
        """Get provider name from model key."""
        if model_key.startswith("gemini"):
            return "gemini"
        elif model_key.startswith("claude"):
            return "claude"
        else:
            return "unknown"
```

#### Acceptance Criteria

- [ ] Router selects models based on complexity
- [ ] Auto-detection of complexity works
- [ ] Fallback provider configured
- [ ] Stats tracking implemented
- [ ] Cost estimation per model

#### Testing

```python
# tests/services/llm/test_router.py
import pytest
from catalyst_bot.services.llm import ModelRouter, LLMRequest, TaskComplexity
from catalyst_bot.services.llm.config import LLMServiceConfig

@pytest.fixture
def router():
    config = LLMServiceConfig.from_env()
    router = ModelRouter(config)
    return router

def test_router_simple_task(router):
    """Test routing for simple task."""
    request = LLMRequest(
        prompt="Hello",
        complexity=TaskComplexity.SIMPLE
    )

    provider, model = router.select_provider(request)

    assert provider == "gemini"
    assert "flash" in model.lower()

def test_router_complex_task(router):
    """Test routing for complex task."""
    request = LLMRequest(
        prompt="Analyze this complex financial document...",
        complexity=TaskComplexity.COMPLEX
    )

    provider, model = router.select_provider(request)

    assert provider in ["gemini", "claude"]
    assert "pro" in model.lower() or "sonnet" in model.lower()

def test_router_auto_detect(router):
    """Test automatic complexity detection."""
    # Long prompt with complex keywords
    request = LLMRequest(
        prompt="Analyze and extract all financial metrics from this 10-K filing, comparing YoY growth..." * 10,
        max_tokens=2048
    )

    complexity = router._auto_detect_complexity(request)

    assert complexity in [TaskComplexity.MEDIUM, TaskComplexity.COMPLEX]
```

---

### Ticket 1.5: Semantic Cache Implementation

**Priority**: High
**Estimated Time**: 6 hours
**Dependencies**: Ticket 1.2

#### Context

Semantic caching is **critical for cost savings**. Instead of exact string matching, we use **embeddings** to find similar prompts.

**Example**:
- Prompt A: "What is AAPL revenue?"
- Prompt B: "Tell me Apple's revenue"
- Traditional cache: MISS (different strings)
- Semantic cache: HIT (same meaning, similarity > 0.95)

**Target**: 70% cache hit rate

#### Implementation

```python
# src/catalyst_bot/services/llm/cache.py
"""
Semantic LLM response caching using Redis and sentence embeddings.

Matches prompts based on semantic similarity rather than exact string matching.
Expected cache hit rate: 60-80% for similar queries.
"""

import hashlib
import json
import time
from typing import Optional, Tuple
import structlog
import redis.asyncio as redis
import numpy as np
from sentence_transformers import SentenceTransformer

from .models import LLMRequest, LLMResponse
from .config import LLMServiceConfig

logger = structlog.get_logger()


class SemanticCache:
    """
    Semantic LLM response caching.

    Caches responses based on semantic similarity of prompts,
    not exact string matching.

    Example:
        "What is AAPL revenue?" and "Tell me Apple's revenue"
        will match despite different wording.

    Backend: Redis with embeddings stored as byte arrays
    Embedding Model: sentence-transformers/all-MiniLM-L6-v2 (fast, good quality)
    """

    def __init__(self, config: LLMServiceConfig):
        self.config = config
        self.redis: Optional[redis.Redis] = None
        self.encoder: Optional[SentenceTransformer] = None

        # Stats
        self.hits = 0
        self.misses = 0
        self.saves = 0

    async def initialize(self):
        """Initialize Redis connection and embedding model."""
        # Connect to Redis
        self.redis = await redis.from_url(
            self.config.redis_url,
            encoding="utf-8",
            decode_responses=False  # We handle bytes for embeddings
        )

        # Test connection
        await self.redis.ping()
        logger.info("cache.redis.connected")

        # Load embedding model (small, fast model)
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("cache.encoder.loaded", model="all-MiniLM-L6-v2")

    async def get(self, request: LLMRequest) -> Optional[LLMResponse]:
        """
        Retrieve cached response for semantically similar prompt.

        Args:
            request: LLM request to check

        Returns:
            Cached response if found (similarity > threshold), else None
        """
        if not self.config.cache_enabled:
            return None

        start_time = time.time()

        try:
            # Generate embedding for prompt
            embedding = self.encoder.encode(request.prompt)

            # Search for similar prompts in cache
            # Key pattern: llm:cache:{feature}:{user_id}:*
            cache_pattern = self._get_cache_pattern(request)

            # Scan for matching keys (could use Redis Streams or Sorted Sets for efficiency)
            cursor = 0
            best_match = None
            best_similarity = 0.0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=cache_pattern,
                    count=100
                )

                for key in keys:
                    # Get cached data
                    cached_data = await self.redis.hgetall(key)
                    if not cached_data:
                        continue

                    # Check TTL
                    ttl = await self.redis.ttl(key)
                    if ttl <= 0:
                        continue

                    # Get stored embedding
                    stored_embedding = np.frombuffer(cached_data[b"embedding"], dtype=np.float32)

                    # Calculate similarity
                    similarity = self._cosine_similarity(embedding, stored_embedding)

                    # Check if better match
                    if similarity > best_similarity and similarity >= self.config.cache_similarity_threshold:
                        best_similarity = similarity
                        best_match = cached_data

                if cursor == 0:
                    break

            # Return best match if found
            if best_match:
                self.hits += 1
                response = self._deserialize_response(best_match[b"response"])
                response.cached = True

                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(
                    "cache.hit",
                    similarity=best_similarity,
                    elapsed_ms=elapsed_ms,
                    hit_rate=self.get_hit_rate()
                )

                return response

            self.misses += 1
            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug("cache.miss", elapsed_ms=elapsed_ms)
            return None

        except Exception as e:
            logger.error("cache.get.error", error=str(e))
            return None

    async def set(
        self,
        request: LLMRequest,
        response: LLMResponse,
        ttl: int = None
    ):
        """
        Cache response with semantic embedding.

        Args:
            request: Original request
            response: Response to cache
            ttl: Time-to-live in seconds (default from config)
        """
        if not self.config.cache_enabled:
            return

        ttl = ttl or self.config.cache_ttl_seconds

        try:
            # Generate embedding
            embedding = self.encoder.encode(request.prompt)

            # Generate cache key
            cache_key = self._get_cache_key(request)

            # Serialize response
            response_data = self._serialize_response(response)

            # Store in Redis
            data = {
                b"embedding": embedding.tobytes(),
                b"response": response_data.encode("utf-8"),
                b"prompt_hash": hashlib.sha256(request.prompt.encode()).hexdigest().encode("utf-8"),
                b"created_at": str(time.time()).encode("utf-8"),
            }

            await self.redis.hset(cache_key, mapping=data)
            await self.redis.expire(cache_key, ttl)

            self.saves += 1
            logger.debug("cache.set", key=cache_key, ttl=ttl)

        except Exception as e:
            logger.error("cache.set.error", error=str(e))

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "saves": self.saves,
            "hit_rate": self.get_hit_rate(),
        }

    def get_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    # ========================================================================
    # Private methods
    # ========================================================================

    def _get_cache_key(self, request: LLMRequest) -> str:
        """Generate unique cache key for request."""
        # Hash prompt for uniqueness
        prompt_hash = hashlib.sha256(request.prompt.encode()).hexdigest()[:16]

        # Include feature and user for scoping
        feature = request.feature_name or "default"
        user = request.user_id or "global"

        return f"llm:cache:{feature}:{user}:{prompt_hash}"

    def _get_cache_pattern(self, request: LLMRequest) -> str:
        """Get Redis key pattern for scanning."""
        feature = request.feature_name or "default"
        user = request.user_id or "global"
        return f"llm:cache:{feature}:{user}:*"

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _serialize_response(self, response: LLMResponse) -> str:
        """Serialize response to JSON string."""
        return response.model_dump_json()

    def _deserialize_response(self, data: bytes) -> LLMResponse:
        """Deserialize response from JSON bytes."""
        return LLMResponse.model_validate_json(data)
```

#### Acceptance Criteria

- [ ] Semantic similarity matching works
- [ ] Cache hit/miss tracked
- [ ] TTL expiration configured
- [ ] Scoped by feature and user
- [ ] Stats reporting

#### Testing

```python
# tests/services/llm/test_cache.py
import pytest
from catalyst_bot.services.llm import SemanticCache, LLMRequest, LLMResponse, TaskComplexity

@pytest.mark.asyncio
async def test_cache_hit():
    """Test cache hit for similar prompts."""
    cache = SemanticCache(config)
    await cache.initialize()

    # First request
    request1 = LLMRequest(prompt="What is Apple's revenue?", feature_name="test")
    response1 = LLMResponse(
        text="Apple's revenue is $394.3B",
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=100.0
    )

    # Cache response
    await cache.set(request1, response1)

    # Similar request (different wording)
    request2 = LLMRequest(prompt="Tell me AAPL revenue", feature_name="test")

    # Should hit cache
    cached = await cache.get(request2)

    assert cached is not None
    assert cached.text == response1.text
    assert cached.cached == True

    # Check hit rate
    assert cache.get_hit_rate() > 0

@pytest.mark.asyncio
async def test_cache_miss():
    """Test cache miss for different prompts."""
    cache = SemanticCache(config)
    await cache.initialize()

    request = LLMRequest(prompt="Explain quantum physics", feature_name="test")

    cached = await cache.get(request)

    assert cached is None
    assert cache.misses > 0
```

---

*Due to length constraints, I'll continue with remaining tickets in the next response. Would you like me to continue with:*

1. **Remaining Phase 1 tickets** (Usage Monitor, Config, etc.)
2. **Phase 2: WebSocket SEC Digester Service**
3. **Phase 3: Client Integration**
4. **Phase 4-5: Migration & Deployment**
5. **Testing Strategy & Scripts**

Let me know which sections you'd like me to detail next, or if you'd like me to package this all into the comprehensive document now!