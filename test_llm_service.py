"""
Quick Test: Unified LLM Service Hub
====================================

Validates that the new LLM service works correctly with Gemini and Claude APIs.
"""

import asyncio
import os
import sys
from pathlib import Path

# Load environment variables FIRST
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.services import LLMService, LLMRequest, TaskComplexity


async def test_llm_service():
    """Test the unified LLM service."""

    print("=" * 60)
    print("Testing Unified LLM Service Hub")
    print("=" * 60)

    # Verify API keys are loaded
    print("\n0. Checking API Keys...")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    print(f"   [OK] GEMINI_API_KEY: {'SET' if gemini_key else 'MISSING'}")
    print(f"   [OK] ANTHROPIC_API_KEY: {'SET' if claude_key else 'MISSING'}")

    if not gemini_key and not claude_key:
        print("\n   [ERR] No API keys found! Please set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env")
        return

    # Initialize service
    print("\n1. Initializing LLM Service...")
    service = LLMService()
    print(f"   [OK] Service initialized (enabled={service.enabled})")

    # Test 1: Simple query with Gemini Flash Lite
    print("\n2. Testing SIMPLE complexity (Gemini Flash Lite)...")
    request = LLMRequest(
        prompt="Classify this news: 'AAPL announces new iPhone'. Is this bullish, neutral, or bearish?",
        complexity=TaskComplexity.SIMPLE,
        feature_name="test_simple",
        max_tokens=100
    )

    try:
        response = await service.query(request)
        print(f"   [OK] Response received:")
        print(f"     - Provider: {response.provider}")
        print(f"     - Model: {response.model}")
        print(f"     - Latency: {response.latency_ms:.0f}ms")
        print(f"     - Cost: ${response.cost_usd:.6f}")
        print(f"     - Tokens: {response.tokens_input} in, {response.tokens_output} out")
        print(f"     - Cached: {response.cached}")
        print(f"     - Text: {response.text[:100]}...")
    except Exception as e:
        print(f"   [ERR] Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Complex query with Gemini Pro
    print("\n3. Testing COMPLEX complexity (Gemini Pro)...")
    request = LLMRequest(
        prompt="""Analyze this 8-K filing:

        Filing Type: 8-K
        Item: 1.01 (Material Agreement)
        Title: Entry into Material Definitive Agreement - Acquisition of XYZ Corp

        Extract:
        1. Deal type (M&A, partnership, etc.)
        2. Deal size if mentioned
        3. Sentiment (bullish/neutral/bearish)

        Respond in JSON format.
        """,
        complexity=TaskComplexity.COMPLEX,
        feature_name="test_complex",
        max_tokens=200
    )

    try:
        response = await service.query(request)
        print(f"   [OK] Response received:")
        print(f"     - Provider: {response.provider}")
        print(f"     - Model: {response.model}")
        print(f"     - Latency: {response.latency_ms:.0f}ms")
        print(f"     - Cost: ${response.cost_usd:.6f}")
        print(f"     - Text: {response.text[:200]}...")
    except Exception as e:
        print(f"   [ERR] Error: {e}")

    # Test 3: Cache hit test
    print("\n4. Testing cache (repeat same query)...")
    request = LLMRequest(
        prompt="Classify this news: 'AAPL announces new iPhone'. Is this bullish, neutral, or bearish?",
        complexity=TaskComplexity.SIMPLE,
        feature_name="test_cache",
        max_tokens=100
    )

    try:
        response = await service.query(request)
        print(f"   [OK] Response received:")
        print(f"     - Cached: {response.cached} (should be True!)")
        print(f"     - Latency: {response.latency_ms:.0f}ms (should be <10ms)")
        print(f"     - Cost: ${response.cost_usd:.6f} (should be $0.00)")
    except Exception as e:
        print(f"   [ERR] Error: {e}")

    # Test 4: Get stats
    print("\n5. Service Statistics:")
    stats = service.get_stats()
    if stats:
        print(f"   - Total requests: {stats.get('total_requests', 0)}")
        print(f"   - Cache hit rate: {stats.get('cache_hit_rate', 0)}%")
        print(f"   - Avg latency: {stats.get('avg_latency_ms', 0):.0f}ms")
        print(f"   - Total cost: ${stats.get('total_cost_usd', 0):.4f}")
        print(f"   - Daily cost: ${stats.get('daily_cost_usd', 0):.4f}")
        print(f"   - Cost by provider: {stats.get('cost_by_provider', {})}")
    else:
        print("   - No stats available")

    print("\n" + "=" * 60)
    print("[OK] All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Run async test
    asyncio.run(test_llm_service())
