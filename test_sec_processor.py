"""
Test: SEC Processor with Unified LLM Service
=============================================

Validates that the new SEC processor correctly analyzes 8-K filings.
"""

import asyncio
import sys
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.processors import SECProcessor


async def test_sec_processor():
    """Test SEC processor with different 8-K items."""

    print("=" * 60)
    print("Testing SEC Processor")
    print("=" * 60)

    # Initialize processor
    print("\n1. Initializing SEC Processor...")
    processor = SECProcessor()
    print("   [OK] Processor initialized")

    # Test Case 1: Material Agreement (Item 1.01) - COMPLEX
    print("\n2. Testing Item 1.01 (Material Agreement) - COMPLEX...")
    result = await processor.process_8k(
        filing_url="https://www.sec.gov/Archives/edgar/data/...",
        ticker="AAPL",
        item="1.01",
        title="Entry into Material Definitive Agreement - Acquisition of XYZ Corp",
        summary="""
        Apple Inc. (the "Company") entered into a definitive agreement to acquire
        XYZ Corp for $500 million in cash. The acquisition is expected to close
        in Q2 2025 subject to regulatory approvals. XYZ Corp specializes in AI
        technology and has 200 employees. The Company expects this acquisition
        to be accretive to earnings within 12 months.
        """
    )

    print(f"   [OK] Analysis complete:")
    print(f"     - Sentiment: {result.sentiment} (confidence: {result.sentiment_confidence:.2f})")
    print(f"     - Material Events: {len(result.material_events)}")
    for event in result.material_events:
        print(f"       * {event.event_type}: {event.description} ({event.significance})")
    print(f"     - Financial Metrics: {len(result.financial_metrics)}")
    for metric in result.financial_metrics:
        print(f"       * {metric.metric_name}: {metric.value:,.0f} {metric.unit}")
    print(f"     - Summary: {result.llm_summary}")
    print(f"     - Provider: {result.llm_provider}")
    print(f"     - Cost: ${result.llm_cost_usd:.6f}")
    print(f"     - Latency: {result.llm_latency_ms:.0f}ms")

    # Test Case 2: Earnings Results (Item 2.02) - COMPLEX
    print("\n3. Testing Item 2.02 (Earnings Results) - COMPLEX...")
    result = await processor.process_8k(
        filing_url="https://www.sec.gov/Archives/edgar/data/...",
        ticker="TSLA",
        item="2.02",
        title="Results of Operations and Financial Condition",
        summary="""
        Tesla, Inc. announces Q4 2024 results. Revenue of $25.2 billion,
        up 15% year-over-year. Net income of $2.3 billion. Delivered
        500,000 vehicles in Q4, exceeding guidance. Full year revenue
        of $96.8 billion. Guidance for 2025: 1.8M vehicles.
        """
    )

    print(f"   [OK] Analysis complete:")
    print(f"     - Sentiment: {result.sentiment} (confidence: {result.sentiment_confidence:.2f})")
    print(f"     - Material Events: {len(result.material_events)}")
    print(f"     - Financial Metrics: {len(result.financial_metrics)}")
    for metric in result.financial_metrics:
        print(f"       * {metric.metric_name}: {metric.value:,.0f} {metric.unit}")
    print(f"     - Summary: {result.llm_summary}")
    print(f"     - Cost: ${result.llm_cost_usd:.6f}")

    # Test Case 3: Other Events (Item 8.01) - SIMPLE
    print("\n4. Testing Item 8.01 (Other Events) - SIMPLE...")
    result = await processor.process_8k(
        filing_url="https://www.sec.gov/Archives/edgar/data/...",
        ticker="NVDA",
        item="8.01",
        title="Other Events - Press Release",
        summary="""
        NVIDIA Corporation issued a press release announcing a new
        data center partnership with a major cloud provider.
        """
    )

    print(f"   [OK] Analysis complete:")
    print(f"     - Sentiment: {result.sentiment} (confidence: {result.sentiment_confidence:.2f})")
    print(f"     - Material Events: {len(result.material_events)}")
    print(f"     - Summary: {result.llm_summary}")
    print(f"     - Cost: ${result.llm_cost_usd:.6f}")

    # Show cost summary
    print("\n5. Cost Summary:")
    stats = processor.llm_service.get_stats()
    if stats:
        print(f"   - Total requests: {stats.get('total_requests', 0)}")
        print(f"   - Total cost: ${stats.get('total_cost_usd', 0):.6f}")
        print(f"   - Avg latency: {stats.get('avg_latency_ms', 0):.0f}ms")
        print(f"   - Cache hit rate: {stats.get('cache_hit_rate', 0):.1f}%")
    else:
        print("   - No stats available")

    print("\n" + "=" * 60)
    print("[OK] All SEC processor tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_sec_processor())
