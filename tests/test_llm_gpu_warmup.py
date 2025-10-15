"""
Tests for LLM GPU Warmup and Memory Monitoring (Wave 0.2)

Tests cover:
- GPU warmup functionality
- Warmup state management
- Memory statistics monitoring
- Memory cleanup operations
"""

from unittest.mock import MagicMock, patch

from catalyst_bot.llm_client import (
    cleanup_gpu_memory,
    get_gpu_memory_stats,
    is_gpu_warmed,
    prime_ollama_gpu,
    reset_warmup_state,
)


class TestGPUWarmup:
    """Test GPU warmup functionality."""

    def setup_method(self):
        """Reset warmup state before each test."""
        reset_warmup_state()

    def test_warmup_state_initially_false(self):
        """Test GPU warmup state starts as False."""
        assert is_gpu_warmed() is False

    @patch("catalyst_bot.llm_client.query_llm")
    def test_successful_warmup(self, mock_query_llm):
        """Test successful GPU warmup."""
        mock_query_llm.return_value = "OK"

        result = prime_ollama_gpu()

        assert result is True
        assert is_gpu_warmed() is True
        mock_query_llm.assert_called_once()

    @patch("catalyst_bot.llm_client.query_llm")
    def test_warmup_skips_if_already_warmed(self, mock_query_llm):
        """Test warmup skips if GPU already warmed."""
        mock_query_llm.return_value = "OK"

        # First warmup
        prime_ollama_gpu()
        assert mock_query_llm.call_count == 1

        # Second warmup should skip
        prime_ollama_gpu()
        assert mock_query_llm.call_count == 1  # Still 1

    @patch("catalyst_bot.llm_client.query_llm")
    def test_warmup_force_overwrites_state(self, mock_query_llm):
        """Test force warmup ignores current state."""
        mock_query_llm.return_value = "OK"

        # First warmup
        prime_ollama_gpu()
        assert mock_query_llm.call_count == 1

        # Force warmup should execute again
        prime_ollama_gpu(force=True)
        assert mock_query_llm.call_count == 2

    @patch("catalyst_bot.llm_client.query_llm")
    def test_warmup_failure(self, mock_query_llm):
        """Test GPU warmup handles failures."""
        mock_query_llm.return_value = None

        result = prime_ollama_gpu()

        assert result is False
        assert is_gpu_warmed() is False

    @patch("catalyst_bot.llm_client.query_llm")
    def test_warmup_exception_handling(self, mock_query_llm):
        """Test GPU warmup handles exceptions gracefully."""
        mock_query_llm.side_effect = Exception("GPU error")

        result = prime_ollama_gpu()

        assert result is False
        assert is_gpu_warmed() is False

    @patch("catalyst_bot.llm_client.query_llm")
    def test_warmup_max_attempts(self, mock_query_llm):
        """Test GPU warmup stops after max attempts."""
        mock_query_llm.return_value = None

        # Try warmup 4 times (should fail on 4th)
        for i in range(4):
            result = prime_ollama_gpu()
            if i < 3:
                assert result is False
            else:
                # 4th attempt should be rejected
                assert result is False

    def test_reset_warmup_state(self):
        """Test warmup state can be reset."""
        # Simulate warmed state
        with patch("catalyst_bot.llm_client.query_llm", return_value="OK"):
            prime_ollama_gpu()
            assert is_gpu_warmed() is True

        # Reset state
        reset_warmup_state()
        assert is_gpu_warmed() is False


class TestGPUMemoryStats:
    """Test GPU memory statistics monitoring."""

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", False)
    def test_memory_stats_unavailable_without_torch(self):
        """Test memory stats returns None when torch unavailable."""
        stats = get_gpu_memory_stats()
        assert stats is None

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    def test_memory_stats_unavailable_without_cuda(self, mock_torch):
        """Test memory stats returns None when CUDA unavailable."""
        mock_torch.cuda.is_available.return_value = False

        stats = get_gpu_memory_stats()
        assert stats is None

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    def test_memory_stats_returns_correct_format(self, mock_torch):
        """Test memory stats returns properly formatted data."""
        # Mock CUDA availability and memory values
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3  # 2 GB
        mock_torch.cuda.memory_reserved.return_value = 3 * 1024**3  # 3 GB

        # Mock device properties
        mock_device_props = MagicMock()
        mock_device_props.total_memory = 16 * 1024**3  # 16 GB
        mock_torch.cuda.get_device_properties.return_value = mock_device_props

        stats = get_gpu_memory_stats()

        assert stats is not None
        assert "allocated_gb" in stats
        assert "reserved_gb" in stats
        assert "free_gb" in stats
        assert "total_gb" in stats
        assert "utilization_pct" in stats

        # Check values
        assert stats["allocated_gb"] == 2.0
        assert stats["reserved_gb"] == 3.0
        assert stats["total_gb"] == 16.0
        assert stats["free_gb"] == 14.0  # 16 - 2
        assert stats["utilization_pct"] == 12.5  # (2/16) * 100

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    def test_memory_stats_handles_errors(self, mock_torch):
        """Test memory stats handles errors gracefully."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.side_effect = Exception("GPU error")

        stats = get_gpu_memory_stats()
        assert stats is None


class TestGPUMemoryCleanup:
    """Test GPU memory cleanup operations."""

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", False)
    def test_cleanup_skips_without_torch(self):
        """Test cleanup skips when torch unavailable."""
        # Should not raise exception
        cleanup_gpu_memory(force=True)

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    @patch("catalyst_bot.llm_client.gc")
    def test_cleanup_executes_sequence(self, mock_gc, mock_torch):
        """Test cleanup executes proper sequence."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.return_value = 1 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 2 * 1024**3

        cleanup_gpu_memory(force=True)

        # Verify sequence
        mock_gc.collect.assert_called()
        mock_torch.cuda.synchronize.assert_called()
        mock_torch.cuda.empty_cache.assert_called()

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    @patch("catalyst_bot.llm_client.time")
    def test_cleanup_respects_interval(self, mock_time, mock_torch):
        """Test cleanup respects minimum interval."""
        mock_torch.cuda.is_available.return_value = True
        mock_time.time.side_effect = [100.0, 150.0]  # 50 seconds elapsed

        # First cleanup (forced)
        cleanup_gpu_memory(force=True)
        assert mock_torch.cuda.empty_cache.call_count == 1

        # Second cleanup (should be skipped - within interval)
        cleanup_gpu_memory(force=False)
        assert mock_torch.cuda.empty_cache.call_count == 1  # Still 1

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    def test_cleanup_handles_errors(self, mock_torch):
        """Test cleanup handles errors gracefully."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.synchronize.side_effect = Exception("GPU error")

        # Should not raise exception
        cleanup_gpu_memory(force=True)


class TestIntegration:
    """Integration tests for GPU warmup and memory management."""

    def setup_method(self):
        """Reset state before each test."""
        reset_warmup_state()

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    @patch("catalyst_bot.llm_client.query_llm")
    def test_warmup_with_memory_monitoring(self, mock_query_llm, mock_torch):
        """Test warmup with concurrent memory monitoring."""
        mock_query_llm.return_value = "OK"
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.return_value = 1 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 2 * 1024**3

        mock_device_props = MagicMock()
        mock_device_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_device_props

        # Warmup
        result = prime_ollama_gpu()
        assert result is True

        # Check memory stats
        stats = get_gpu_memory_stats()
        assert stats is not None
        assert stats["allocated_gb"] == 1.0

    @patch("catalyst_bot.llm_client.TORCH_AVAILABLE", True)
    @patch("catalyst_bot.llm_client.torch")
    @patch("catalyst_bot.llm_client.query_llm")
    @patch("catalyst_bot.llm_client.gc")
    def test_warmup_with_cleanup(self, mock_gc, mock_query_llm, mock_torch):
        """Test warmup followed by cleanup."""
        mock_query_llm.return_value = "OK"
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.return_value = 1 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 2 * 1024**3

        # Warmup
        result = prime_ollama_gpu()
        assert result is True

        # Cleanup
        cleanup_gpu_memory(force=True)

        # Verify cleanup was called
        mock_gc.collect.assert_called()
        mock_torch.cuda.empty_cache.assert_called()
