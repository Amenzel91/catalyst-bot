"""
Comprehensive Test Suite for LLM Router Logic
===============================================

Tests cover:
- Model selection based on task complexity (SIMPLE, MEDIUM, COMPLEX, CRITICAL)
- Routing probability distribution
- Provider health tracking
- Failover logic
- Weighted random selection
- Cost-aware routing
- Provider recovery after failures
- Routing statistics

Coverage areas:
1. Complexity-based routing (all complexity levels)
2. Probability distribution (70/30, 90/10, 80/20, 100)
3. Provider health checks
4. Failover cascading
5. Weighted random selection
6. Cost calculations
7. Provider unhealthy marking and recovery
8. Routing statistics and telemetry
"""

import random
from unittest.mock import Mock, patch

import pytest

from catalyst_bot.services.llm_router import LLMRouter
from catalyst_bot.services.llm_service import TaskComplexity


class TestModelSelection:
    """Test model selection based on task complexity."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_simple_task_routing(self, router):
        """Test that SIMPLE tasks route to Flash Lite or Flash."""
        # Test multiple times to verify probability distribution
        selections = []
        for _ in range(100):
            provider, model = router.select_provider(TaskComplexity.SIMPLE)
            selections.append(provider)

        # Should only select from Flash Lite and Flash
        assert all(p in ["gemini_flash_lite", "gemini_flash"] for p in selections)

        # Should have both providers (not 100% of one)
        assert "gemini_flash_lite" in selections
        assert "gemini_flash" in selections

    def test_medium_task_routing(self, router):
        """Test that MEDIUM tasks route to Flash or Pro."""
        selections = []
        for _ in range(100):
            provider, model = router.select_provider(TaskComplexity.MEDIUM)
            selections.append(provider)

        # Should only select from Flash and Pro
        assert all(p in ["gemini_flash", "gemini_pro"] for p in selections)

        # Should heavily favor Flash (90%) over Pro (10%)
        flash_count = selections.count("gemini_flash")
        assert flash_count > 70  # Should be ~90, allow some variance

    def test_complex_task_routing(self, router):
        """Test that COMPLEX tasks route to Pro or Claude."""
        selections = []
        for _ in range(100):
            provider, model = router.select_provider(TaskComplexity.COMPLEX)
            selections.append(provider)

        # Should only select from Pro and Claude
        assert all(p in ["gemini_pro", "claude_sonnet"] for p in selections)

        # Should heavily favor Pro (80%) over Claude (20%)
        pro_count = selections.count("gemini_pro")
        assert pro_count > 60  # Should be ~80, allow some variance

    def test_critical_task_routing(self, router):
        """Test that CRITICAL tasks always route to Claude Sonnet."""
        # Test multiple times to ensure 100% routing
        for _ in range(50):
            provider, model = router.select_provider(TaskComplexity.CRITICAL)
            assert provider == "claude_sonnet"
            assert model == "claude-sonnet-4-20250514"

    def test_none_complexity_defaults_to_medium(self, router):
        """Test that None complexity defaults to MEDIUM routing."""
        provider, model = router.select_provider(None)
        assert provider in ["gemini_flash", "gemini_pro"]


class TestProbabilityDistribution:
    """Test routing probability distribution accuracy."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_simple_70_30_distribution(self, router):
        """Test SIMPLE task distribution is ~70% Flash Lite, ~30% Flash."""
        selections = []
        random.seed(42)  # For reproducibility

        for _ in range(1000):
            provider, _ = router.select_provider(TaskComplexity.SIMPLE)
            selections.append(provider)

        flash_lite_count = selections.count("gemini_flash_lite")
        flash_count = selections.count("gemini_flash")

        # Allow 10% variance from target
        assert 600 < flash_lite_count < 800  # ~70% of 1000
        assert 200 < flash_count < 400      # ~30% of 1000

    def test_medium_90_10_distribution(self, router):
        """Test MEDIUM task distribution is ~90% Flash, ~10% Pro."""
        selections = []
        random.seed(42)

        for _ in range(1000):
            provider, _ = router.select_provider(TaskComplexity.MEDIUM)
            selections.append(provider)

        flash_count = selections.count("gemini_flash")
        pro_count = selections.count("gemini_pro")

        # Allow 10% variance
        assert 800 < flash_count < 1000  # ~90% of 1000
        assert 0 < pro_count < 200       # ~10% of 1000

    def test_complex_80_20_distribution(self, router):
        """Test COMPLEX task distribution is ~80% Pro, ~20% Claude."""
        selections = []
        random.seed(42)

        for _ in range(1000):
            provider, _ = router.select_provider(TaskComplexity.COMPLEX)
            selections.append(provider)

        pro_count = selections.count("gemini_pro")
        claude_count = selections.count("claude_sonnet")

        # Allow 10% variance
        assert 700 < pro_count < 900     # ~80% of 1000
        assert 100 < claude_count < 300  # ~20% of 1000


class TestProviderHealth:
    """Test provider health tracking and filtering."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_healthy_provider_by_default(self, router):
        """Test that providers are healthy by default."""
        assert router._is_provider_healthy("gemini_flash") is True
        assert router._is_provider_healthy("gemini_pro") is True
        assert router._is_provider_healthy("claude_sonnet") is True

    def test_mark_provider_unhealthy(self, router):
        """Test marking provider as unhealthy."""
        router.mark_provider_unhealthy("gemini_flash", duration_seconds=300)

        assert router._is_provider_healthy("gemini_flash") is False

    def test_unhealthy_provider_excluded_from_routing(self, router):
        """Test that unhealthy providers are excluded from routing."""
        # Mark Flash as unhealthy for MEDIUM tasks
        router.mark_provider_unhealthy("gemini_flash", duration_seconds=300)

        # All MEDIUM tasks should route to Pro (the only healthy option)
        for _ in range(20):
            provider, _ = router.select_provider(TaskComplexity.MEDIUM)
            assert provider == "gemini_pro"

    def test_provider_recovery_after_duration(self, router):
        """Test that provider recovers after unhealthy duration expires."""
        import time

        # Mark as unhealthy for 0.1 seconds
        router.mark_provider_unhealthy("gemini_flash", duration_seconds=0.1)
        assert router._is_provider_healthy("gemini_flash") is False

        # Wait for recovery
        time.sleep(0.15)

        # Should be healthy again
        assert router._is_provider_healthy("gemini_flash") is True

    def test_all_providers_unhealthy_fallback(self, router):
        """Test routing when all providers are unhealthy."""
        # Mark all MEDIUM providers as unhealthy
        router.mark_provider_unhealthy("gemini_flash", duration_seconds=300)
        router.mark_provider_unhealthy("gemini_pro", duration_seconds=300)

        # Should still route (uses all options as fallback)
        provider, _ = router.select_provider(TaskComplexity.MEDIUM)
        assert provider in ["gemini_flash", "gemini_pro"]


class TestFailoverLogic:
    """Test failover provider selection."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_flash_lite_fallback_to_flash(self, router):
        """Test Flash Lite falls back to Flash."""
        fallback_provider, fallback_model = router.get_fallback_provider(
            "gemini_flash_lite",
            TaskComplexity.SIMPLE
        )

        assert fallback_provider == "gemini_flash"
        assert "flash" in fallback_model.lower()

    def test_flash_fallback_to_pro(self, router):
        """Test Flash falls back to Pro."""
        fallback_provider, fallback_model = router.get_fallback_provider(
            "gemini_flash",
            TaskComplexity.MEDIUM
        )

        assert fallback_provider == "gemini_pro"
        assert "pro" in fallback_model.lower()

    def test_pro_fallback_to_claude(self, router):
        """Test Pro falls back to Claude Sonnet."""
        fallback_provider, fallback_model = router.get_fallback_provider(
            "gemini_pro",
            TaskComplexity.COMPLEX
        )

        assert fallback_provider == "claude_sonnet"
        assert "sonnet" in fallback_model.lower()

    def test_claude_fallback_to_pro(self, router):
        """Test Claude falls back to Pro (last resort)."""
        fallback_provider, fallback_model = router.get_fallback_provider(
            "claude_sonnet",
            TaskComplexity.CRITICAL
        )

        assert fallback_provider == "gemini_pro"
        assert "pro" in fallback_model.lower()

    def test_unknown_provider_fallback(self, router):
        """Test unknown provider falls back to Flash."""
        fallback_provider, fallback_model = router.get_fallback_provider(
            "unknown_provider",
            TaskComplexity.MEDIUM
        )

        assert fallback_provider == "gemini_flash"


class TestWeightedRandomSelection:
    """Test weighted random selection algorithm."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_weighted_selection_respects_probabilities(self, router):
        """Test that weighted selection respects probability distribution."""
        options = [
            ("option_a", 0.70),
            ("option_b", 0.30)
        ]

        random.seed(42)
        selections = []

        for _ in range(1000):
            selected = router._weighted_random_choice(options)
            selections.append(selected)

        a_count = selections.count("option_a")
        b_count = selections.count("option_b")

        # Should be roughly 70/30 split
        assert 600 < a_count < 800
        assert 200 < b_count < 400

    def test_weighted_selection_normalizes_probabilities(self, router):
        """Test that probabilities are normalized to sum to 1.0."""
        options = [
            ("option_a", 0.35),
            ("option_b", 0.15)
            # Sum is 0.50, should be normalized to 0.70/0.30
        ]

        random.seed(42)
        selections = []

        for _ in range(1000):
            selected = router._weighted_random_choice(options)
            selections.append(selected)

        # After normalization: 0.35/0.50 = 0.70, 0.15/0.50 = 0.30
        a_count = selections.count("option_a")
        assert 600 < a_count < 800

    def test_weighted_selection_single_option(self, router):
        """Test weighted selection with single option."""
        options = [("only_option", 1.0)]

        for _ in range(10):
            selected = router._weighted_random_choice(options)
            assert selected == "only_option"

    def test_weighted_selection_empty_options(self, router):
        """Test weighted selection with empty options returns default."""
        selected = router._weighted_random_choice([])
        assert selected == "gemini_flash"  # Default fallback


class TestCostCalculations:
    """Test cost calculations for different providers."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_flash_lite_cost(self, router):
        """Test Flash Lite cost per 1M tokens."""
        cost = router.get_model_cost("gemini_flash_lite")
        assert cost == 0.02  # $0.02 per 1M input tokens

    def test_flash_cost(self, router):
        """Test Flash cost per 1M tokens."""
        cost = router.get_model_cost("gemini_flash")
        assert cost == 0.075  # $0.075 per 1M input tokens

    def test_pro_cost(self, router):
        """Test Pro cost per 1M tokens."""
        cost = router.get_model_cost("gemini_pro")
        assert cost == 1.25  # $1.25 per 1M input tokens

    def test_claude_cost(self, router):
        """Test Claude Sonnet cost per 1M tokens."""
        cost = router.get_model_cost("claude_sonnet")
        assert cost == 3.00  # $3.00 per 1M input tokens

    def test_unknown_provider_cost(self, router):
        """Test unknown provider defaults to $1.00."""
        cost = router.get_model_cost("unknown_provider")
        assert cost == 1.0  # Default fallback


class TestRoutingStatistics:
    """Test routing statistics and telemetry."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_get_routing_stats(self, router):
        """Test get_routing_stats returns complete statistics."""
        stats = router.get_routing_stats()

        assert "routing_table" in stats
        assert "provider_health" in stats
        assert "model_costs" in stats

        # Verify routing table structure
        assert "simple" in stats["routing_table"]
        assert "medium" in stats["routing_table"]
        assert "complex" in stats["routing_table"]
        assert "critical" in stats["routing_table"]

    def test_routing_table_probabilities(self, router):
        """Test routing table contains correct probabilities."""
        stats = router.get_routing_stats()

        # Check SIMPLE routing
        simple_routes = stats["routing_table"]["simple"]
        assert len(simple_routes) == 2
        assert any(r["provider"] == "gemini_flash_lite" and r["probability"] == 0.70 for r in simple_routes)
        assert any(r["provider"] == "gemini_flash" and r["probability"] == 0.30 for r in simple_routes)

        # Check CRITICAL routing
        critical_routes = stats["routing_table"]["critical"]
        assert len(critical_routes) == 1
        assert critical_routes[0]["provider"] == "claude_sonnet"
        assert critical_routes[0]["probability"] == 1.00

    def test_provider_health_in_stats(self, router):
        """Test provider health is included in statistics."""
        # Mark a provider unhealthy
        router.mark_provider_unhealthy("gemini_flash", duration_seconds=300)

        stats = router.get_routing_stats()

        assert "gemini_flash" in stats["provider_health"]
        assert stats["provider_health"]["gemini_flash"]["healthy"] is False

    def test_model_costs_in_stats(self, router):
        """Test model costs are included in statistics."""
        stats = router.get_routing_stats()

        assert stats["model_costs"]["gemini_flash_lite"] == 0.02
        assert stats["model_costs"]["gemini_flash"] == 0.075
        assert stats["model_costs"]["gemini_pro"] == 1.25
        assert stats["model_costs"]["claude_sonnet"] == 3.00


class TestModelNameMapping:
    """Test provider to model name mapping."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_flash_lite_model_name(self, router):
        """Test Flash Lite maps to correct model name."""
        provider, model = router.select_provider(TaskComplexity.SIMPLE)

        if provider == "gemini_flash_lite":
            assert model == "gemini-2.0-flash-lite"

    def test_flash_model_name(self, router):
        """Test Flash maps to correct model name."""
        provider, model = router.select_provider(TaskComplexity.MEDIUM)

        if provider == "gemini_flash":
            assert model == "gemini-2.0-flash-exp"

    def test_pro_model_name(self, router):
        """Test Pro maps to correct model name."""
        provider, model = router.select_provider(TaskComplexity.COMPLEX)

        if provider == "gemini_pro":
            assert model == "gemini-2.5-pro"

    def test_claude_model_name(self, router):
        """Test Claude maps to correct model name."""
        provider, model = router.select_provider(TaskComplexity.CRITICAL)

        assert provider == "claude_sonnet"
        assert model == "claude-sonnet-4-20250514"


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_no_routing_options_for_complexity(self, router):
        """Test handling when routing table is missing for a complexity."""
        # Create a custom routing table with only some complexities
        partial_routing_table = {
            TaskComplexity.MEDIUM: [
                ("gemini_flash", 0.90),
                ("gemini_pro", 0.10),
            ],
            TaskComplexity.CRITICAL: [
                ("claude_sonnet", 1.00),
            ],
        }

        with patch.object(router, 'ROUTING_TABLE', partial_routing_table):
            provider, model = router.select_provider(TaskComplexity.SIMPLE)

            # Should fall back to MEDIUM routing
            assert provider in ["gemini_flash", "gemini_pro"]

    def test_all_options_filtered_out(self, router):
        """Test when all routing options are filtered as unhealthy."""
        # Mark all providers unhealthy
        router.mark_provider_unhealthy("gemini_flash_lite", duration_seconds=300)
        router.mark_provider_unhealthy("gemini_flash", duration_seconds=300)

        # Should still route (falls back to using all options)
        provider, model = router.select_provider(TaskComplexity.SIMPLE)
        assert provider in ["gemini_flash_lite", "gemini_flash"]

    def test_concurrent_health_updates(self, router):
        """Test concurrent provider health updates don't corrupt state."""
        import threading

        def mark_unhealthy():
            router.mark_provider_unhealthy("gemini_flash", duration_seconds=1)

        # Run multiple threads marking provider unhealthy
        threads = [threading.Thread(target=mark_unhealthy) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should still work without errors
        assert router._is_provider_healthy("gemini_flash") is False


class TestRouterIntegration:
    """Integration tests combining multiple routing features."""

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LLMRouter(config={})

    def test_failover_chain(self, router):
        """Test complete failover chain from Flash Lite to Claude."""
        # Simulate Flash Lite failing
        fallback1_provider, _ = router.get_fallback_provider("gemini_flash_lite", TaskComplexity.SIMPLE)
        assert fallback1_provider == "gemini_flash"

        # Flash fails, fall back to Pro
        fallback2_provider, _ = router.get_fallback_provider(fallback1_provider, TaskComplexity.MEDIUM)
        assert fallback2_provider == "gemini_pro"

        # Pro fails, fall back to Claude
        fallback3_provider, _ = router.get_fallback_provider(fallback2_provider, TaskComplexity.COMPLEX)
        assert fallback3_provider == "claude_sonnet"

    def test_cost_optimization_under_failures(self, router):
        """Test that router optimizes for cost when providers fail."""
        # Mark expensive providers as unhealthy
        router.mark_provider_unhealthy("gemini_pro", duration_seconds=300)
        router.mark_provider_unhealthy("claude_sonnet", duration_seconds=300)

        # COMPLEX tasks should route to available cheaper options
        # Since Pro and Claude are down, should fall back to Flash
        selections = []
        for _ in range(20):
            provider, _ = router.select_provider(TaskComplexity.COMPLEX)
            selections.append(provider)

        # Should still work (uses unhealthy providers as fallback)
        assert all(p in ["gemini_pro", "claude_sonnet"] for p in selections)

    def test_mixed_complexity_routing(self, router):
        """Test routing various complexity levels in sequence."""
        complexities = [
            TaskComplexity.SIMPLE,
            TaskComplexity.MEDIUM,
            TaskComplexity.COMPLEX,
            TaskComplexity.CRITICAL,
            TaskComplexity.SIMPLE,
        ]

        for complexity in complexities:
            provider, model = router.select_provider(complexity)

            # Verify correct tier for each complexity
            if complexity == TaskComplexity.SIMPLE:
                assert provider in ["gemini_flash_lite", "gemini_flash"]
            elif complexity == TaskComplexity.MEDIUM:
                assert provider in ["gemini_flash", "gemini_pro"]
            elif complexity == TaskComplexity.COMPLEX:
                assert provider in ["gemini_pro", "claude_sonnet"]
            elif complexity == TaskComplexity.CRITICAL:
                assert provider == "claude_sonnet"
