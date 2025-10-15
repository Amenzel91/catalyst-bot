#!/usr/bin/env python3
"""
Test script for LLM Usage Monitor

This script demonstrates the LLM usage monitoring system with simulated API calls.

Usage:
    python test_llm_usage_monitor.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.llm_usage_monitor import LLMUsageMonitor


def test_monitor():
    """Test the LLM usage monitor with simulated events."""
    print("=" * 70)
    print("LLM USAGE MONITOR - TEST SUITE")
    print("=" * 70)

    # Create monitor with test log path
    test_log = Path("data/logs/llm_usage_test.jsonl")
    monitor = LLMUsageMonitor(log_path=test_log)

    print(f"\nTest log path: {test_log}")
    print("Logging simulated LLM API calls...\n")

    # Simulate Gemini calls (typical SEC filing keyword extraction)
    print("1. Simulating Gemini 2.5 Flash calls...")
    for i in range(5):
        monitor.log_usage(
            provider="gemini",
            model="gemini-2.5-flash",
            operation="sec_keyword_extraction",
            input_tokens=5000,  # ~5K chars filing excerpt
            output_tokens=500,  # JSON response with keywords
            success=True,
            article_length=20000,
            ticker=f"TEST{i}",
        )

    # Simulate Anthropic fallback calls (rare, for complex analysis)
    print("2. Simulating Anthropic Claude Haiku fallback calls...")
    for i in range(2):
        monitor.log_usage(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            operation="sec_keyword_extraction",
            input_tokens=8000,  # Larger filing
            output_tokens=800,  # More detailed analysis
            success=True,
            article_length=32000,
            ticker=f"FALLBACK{i}",
        )

    # Simulate local Mistral calls (free, short articles)
    print("3. Simulating local Mistral calls (FREE)...")
    for i in range(20):
        monitor.log_usage(
            provider="local",
            model="mistral",
            operation="sentiment_analysis",
            input_tokens=250,  # Short headline
            output_tokens=50,  # Simple sentiment score
            success=True,
            article_length=800,
            ticker=f"LOCAL{i}",
        )

    # Simulate some failures
    print("4. Simulating failed API calls...")
    monitor.log_usage(
        provider="gemini",
        model="gemini-2.5-flash",
        operation="sec_keyword_extraction",
        input_tokens=5000,
        output_tokens=0,
        success=False,
        error="rate_limit_exceeded",
    )

    print("\n" + "=" * 70)
    print("TEST COMPLETE - Generating Usage Report")
    print("=" * 70 + "\n")

    # Get and display stats
    summary = monitor.get_daily_stats()
    monitor.print_summary(summary)

    # Calculate per-call costs
    print("=" * 70)
    print("PER-CALL COST ANALYSIS")
    print("=" * 70)

    if summary.gemini.total_requests > 0:
        avg_gemini_cost = summary.gemini.total_cost / summary.gemini.total_requests
        print(f"Average Gemini cost per call: ${avg_gemini_cost:.6f}")

    if summary.anthropic.total_requests > 0:
        avg_anthropic_cost = summary.anthropic.total_cost / summary.anthropic.total_requests
        print(f"Average Anthropic cost per call: ${avg_anthropic_cost:.6f}")

    if summary.local.total_requests > 0:
        print(f"Average Local cost per call: $0.000000 (FREE)")

    # Calculate cost per 1000 filings
    total_paid_requests = summary.gemini.total_requests + summary.anthropic.total_requests
    if total_paid_requests > 0:
        cost_per_1000 = (summary.total_cost / total_paid_requests) * 1000
        print(f"\nCost per 1,000 SEC filings analyzed: ${cost_per_1000:.2f}")

    print("\n" + "=" * 70)
    print("COST SAVINGS FROM LOCAL MISTRAL")
    print("=" * 70)

    if summary.local.total_requests > 0:
        # Calculate what it would cost if we used Gemini for all local calls
        local_as_gemini_cost = (
            summary.local.total_input_tokens * 0.000_000_15
            + summary.local.total_output_tokens * 0.000_000_60
        )
        print(f"Local Mistral calls: {summary.local.total_requests}")
        print(f"Actual cost: $0.00 (FREE)")
        print(f"Would have cost with Gemini: ${local_as_gemini_cost:.4f}")
        print(f"Savings: ${local_as_gemini_cost:.4f}/day = "
              f"${local_as_gemini_cost * 30:.2f}/month")

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"[OK] Logged {summary.total_requests} API calls")
    print(f"[OK] Processed {summary.total_tokens:,} tokens")
    print(f"[OK] Total cost: ${summary.total_cost:.4f}")
    print(f"[OK] Test log saved to: {test_log}")
    print("\nTo view usage report:")
    print(f"  python scripts/llm_usage_report.py --log-path {test_log}")
    print("\n" + "=" * 70 + "\n")

    return True


if __name__ == "__main__":
    success = test_monitor()
    sys.exit(0 if success else 1)
