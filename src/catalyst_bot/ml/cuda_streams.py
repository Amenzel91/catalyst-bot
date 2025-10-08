"""
CUDA Streams Optimization for Catalyst-Bot

This module implements CUDA stream-based parallel execution for running
multiple ML models concurrently on GPU. This is an advanced optimization
that can improve throughput when running multiple models (e.g., sentiment
model + LLM) simultaneously.

Features:
- Parallel execution of sentiment analysis and LLM inference
- CUDA stream management and synchronization
- Automatic fallback to sequential execution if streams unavailable
- Performance monitoring and metrics

Requirements:
- PyTorch with CUDA support
- CUDA-capable GPU
- FEATURE_CUDA_STREAMS=1 in environment

Usage:
    from catalyst_bot.ml.cuda_streams import CUDAStreamManager

    manager = CUDAStreamManager()

    # Run sentiment and LLM in parallel
    sentiment_results, llm_results = manager.parallel_inference(
        sentiment_fn=lambda: score_sentiment(texts),
        llm_fn=lambda: query_llm(prompt)
    )

Note:
    This is an advanced optimization. Most use cases should stick to
    sequential execution or batch processing for simplicity.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)


@dataclass
class StreamResult:
    """Result from stream execution."""

    success: bool
    result: Any
    execution_time_ms: float
    stream_id: int
    error: Optional[str] = None


class CUDAStreamManager:
    """Manager for CUDA stream-based parallel execution.

    This class handles creation and management of CUDA streams for
    running multiple operations in parallel on the GPU.
    """

    def __init__(self, num_streams: int = 2):
        """Initialize CUDA stream manager.

        Args:
            num_streams: Number of CUDA streams to create (default: 2)
        """
        self.num_streams = num_streams
        self.streams = []
        self.cuda_available = False
        self.enabled = self._check_enabled()

        if self.enabled:
            self._initialize_streams()
        else:
            _logger.info("CUDA streams disabled or unavailable")

    def _check_enabled(self) -> bool:
        """Check if CUDA streams are enabled and available.

        Returns:
            True if CUDA streams can be used
        """
        # Check environment flag
        if os.getenv("FEATURE_CUDA_STREAMS", "0") != "1":
            _logger.debug("CUDA streams disabled in config")
            return False

        # Check CUDA availability
        try:
            import torch

            if not torch.cuda.is_available():
                _logger.info("CUDA not available, streams disabled")
                return False

            self.cuda_available = True
            return True

        except ImportError:
            _logger.info("PyTorch not available, CUDA streams disabled")
            return False

    def _initialize_streams(self) -> None:
        """Initialize CUDA streams."""
        try:
            import torch

            self.streams = [torch.cuda.Stream() for _ in range(self.num_streams)]
            _logger.info("Initialized %d CUDA streams", self.num_streams)

        except Exception as e:
            _logger.error("Failed to initialize CUDA streams: %s", e)
            self.enabled = False
            self.streams = []

    def parallel_inference(
        self,
        sentiment_fn: Callable[[], Any],
        llm_fn: Callable[[], Any],
    ) -> Tuple[StreamResult, StreamResult]:
        """Run sentiment and LLM inference in parallel using CUDA streams.

        Args:
            sentiment_fn: Function that runs sentiment inference
            llm_fn: Function that runs LLM inference

        Returns:
            Tuple of (sentiment_result, llm_result)
        """
        if not self.enabled or len(self.streams) < 2:
            # Fallback to sequential execution
            return self._sequential_execution(sentiment_fn, llm_fn)

        try:
            import torch

            sentiment_stream = self.streams[0]
            llm_stream = self.streams[1]

            sentiment_result = None
            llm_result = None
            sentiment_error = None
            llm_error = None

            # Execute sentiment in stream 0
            sentiment_start = time.perf_counter()
            with torch.cuda.stream(sentiment_stream):
                try:
                    sentiment_result = sentiment_fn()
                except Exception as e:
                    sentiment_error = str(e)
                    _logger.error("Sentiment inference failed in stream: %s", e)
            sentiment_time = (time.perf_counter() - sentiment_start) * 1000

            # Execute LLM in stream 1
            llm_start = time.perf_counter()
            with torch.cuda.stream(llm_stream):
                try:
                    llm_result = llm_fn()
                except Exception as e:
                    llm_error = str(e)
                    _logger.error("LLM inference failed in stream: %s", e)
            llm_time = (time.perf_counter() - llm_start) * 1000

            # Synchronize all streams
            torch.cuda.synchronize()

            return (
                StreamResult(
                    success=sentiment_error is None,
                    result=sentiment_result,
                    execution_time_ms=sentiment_time,
                    stream_id=0,
                    error=sentiment_error,
                ),
                StreamResult(
                    success=llm_error is None,
                    result=llm_result,
                    execution_time_ms=llm_time,
                    stream_id=1,
                    error=llm_error,
                ),
            )

        except Exception as e:
            _logger.error("CUDA streams parallel execution failed: %s", e)
            # Fallback to sequential
            return self._sequential_execution(sentiment_fn, llm_fn)

    def _sequential_execution(
        self,
        sentiment_fn: Callable[[], Any],
        llm_fn: Callable[[], Any],
    ) -> Tuple[StreamResult, StreamResult]:
        """Fallback sequential execution when streams unavailable.

        Args:
            sentiment_fn: Function that runs sentiment inference
            llm_fn: Function that runs LLM inference

        Returns:
            Tuple of (sentiment_result, llm_result)
        """
        _logger.debug("Using sequential execution (CUDA streams unavailable)")

        # Execute sentiment
        sentiment_start = time.perf_counter()
        sentiment_error = None
        sentiment_result = None
        try:
            sentiment_result = sentiment_fn()
        except Exception as e:
            sentiment_error = str(e)
            _logger.error("Sentiment inference failed: %s", e)
        sentiment_time = (time.perf_counter() - sentiment_start) * 1000

        # Execute LLM
        llm_start = time.perf_counter()
        llm_error = None
        llm_result = None
        try:
            llm_result = llm_fn()
        except Exception as e:
            llm_error = str(e)
            _logger.error("LLM inference failed: %s", e)
        llm_time = (time.perf_counter() - llm_start) * 1000

        return (
            StreamResult(
                success=sentiment_error is None,
                result=sentiment_result,
                execution_time_ms=sentiment_time,
                stream_id=-1,  # Sequential mode
                error=sentiment_error,
            ),
            StreamResult(
                success=llm_error is None,
                result=llm_result,
                execution_time_ms=llm_time,
                stream_id=-1,  # Sequential mode
                error=llm_error,
            ),
        )

    def parallel_batch_inference(
        self,
        tasks: List[Callable[[], Any]],
    ) -> List[StreamResult]:
        """Run multiple inference tasks in parallel across streams.

        Args:
            tasks: List of functions to execute in parallel

        Returns:
            List of StreamResult objects
        """
        if not self.enabled or not self.streams:
            return self._sequential_batch_execution(tasks)

        try:
            import torch

            results = []
            num_streams = len(self.streams)

            # Distribute tasks across streams
            for i, task in enumerate(tasks):
                stream_idx = i % num_streams
                stream = self.streams[stream_idx]

                task_error = None
                task_result = None

                start = time.perf_counter()
                with torch.cuda.stream(stream):
                    try:
                        task_result = task()
                    except Exception as e:
                        task_error = str(e)
                        _logger.error(
                            "Task %d failed in stream %d: %s", i, stream_idx, e
                        )
                elapsed = (time.perf_counter() - start) * 1000

                results.append(
                    StreamResult(
                        success=task_error is None,
                        result=task_result,
                        execution_time_ms=elapsed,
                        stream_id=stream_idx,
                        error=task_error,
                    )
                )

            # Synchronize all streams
            torch.cuda.synchronize()

            return results

        except Exception as e:
            _logger.error("Parallel batch inference failed: %s", e)
            return self._sequential_batch_execution(tasks)

    def _sequential_batch_execution(
        self,
        tasks: List[Callable[[], Any]],
    ) -> List[StreamResult]:
        """Sequential fallback for batch execution.

        Args:
            tasks: List of functions to execute

        Returns:
            List of StreamResult objects
        """
        results = []

        for i, task in enumerate(tasks):
            task_error = None
            task_result = None

            start = time.perf_counter()
            try:
                task_result = task()
            except Exception as e:
                task_error = str(e)
                _logger.error("Task %d failed: %s", i, e)
            elapsed = (time.perf_counter() - start) * 1000

            results.append(
                StreamResult(
                    success=task_error is None,
                    result=task_result,
                    execution_time_ms=elapsed,
                    stream_id=-1,  # Sequential mode
                    error=task_error,
                )
            )

        return results

    def cleanup(self) -> None:
        """Clean up CUDA streams and free resources."""
        try:
            import torch

            if self.streams:
                for stream in self.streams:
                    stream.synchronize()

            self.streams = []

            if self.cuda_available:
                torch.cuda.empty_cache()

            _logger.debug("CUDA streams cleaned up")

        except Exception as e:
            _logger.error("Failed to cleanup CUDA streams: %s", e)

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()


# Singleton instance
_STREAM_MANAGER: Optional[CUDAStreamManager] = None


def get_stream_manager() -> CUDAStreamManager:
    """Get or create the global CUDA stream manager.

    Returns:
        CUDAStreamManager instance
    """
    global _STREAM_MANAGER

    if _STREAM_MANAGER is None:
        _STREAM_MANAGER = CUDAStreamManager()

    return _STREAM_MANAGER


# Convenience functions
def is_cuda_streams_enabled() -> bool:
    """Check if CUDA streams are enabled and available.

    Returns:
        True if CUDA streams can be used
    """
    manager = get_stream_manager()
    return manager.enabled


def run_parallel_inference(
    sentiment_fn: Callable[[], Any],
    llm_fn: Callable[[], Any],
) -> Tuple[Any, Any]:
    """Run sentiment and LLM inference in parallel.

    Args:
        sentiment_fn: Function that runs sentiment inference
        llm_fn: Function that runs LLM inference

    Returns:
        Tuple of (sentiment_result, llm_result)

    Note:
        Automatically falls back to sequential if streams unavailable
    """
    manager = get_stream_manager()
    sentiment_result, llm_result = manager.parallel_inference(sentiment_fn, llm_fn)

    return sentiment_result.result, llm_result.result


def run_parallel_batch(
    tasks: List[Callable[[], Any]],
) -> List[Any]:
    """Run multiple tasks in parallel across CUDA streams.

    Args:
        tasks: List of functions to execute

    Returns:
        List of results
    """
    manager = get_stream_manager()
    results = manager.parallel_batch_inference(tasks)

    return [r.result for r in results]


def benchmark_streams(iterations: int = 10) -> Dict[str, Any]:
    """Benchmark CUDA streams vs sequential execution.

    Args:
        iterations: Number of test iterations

    Returns:
        Benchmark results dict
    """
    _logger.info("Benchmarking CUDA streams (%d iterations)", iterations)

    # Dummy inference functions
    def dummy_sentiment():
        try:
            import torch

            x = torch.randn(100, 100).cuda()
            return torch.matmul(x, x).cpu()
        except Exception:
            import time

            time.sleep(0.01)  # Simulate work
            return None

    def dummy_llm():
        try:
            import torch

            x = torch.randn(200, 200).cuda()
            return torch.matmul(x, x).cpu()
        except Exception:
            import time

            time.sleep(0.02)  # Simulate work
            return None

    manager = get_stream_manager()

    # Benchmark parallel execution
    parallel_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        manager.parallel_inference(dummy_sentiment, dummy_llm)
        elapsed = (time.perf_counter() - start) * 1000
        parallel_times.append(elapsed)

    # Benchmark sequential execution
    sequential_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        manager._sequential_execution(dummy_sentiment, dummy_llm)
        elapsed = (time.perf_counter() - start) * 1000
        sequential_times.append(elapsed)

    avg_parallel = sum(parallel_times) / len(parallel_times)
    avg_sequential = sum(sequential_times) / len(sequential_times)
    speedup = avg_sequential / avg_parallel if avg_parallel > 0 else 1.0

    return {
        "streams_enabled": manager.enabled,
        "cuda_available": manager.cuda_available,
        "num_streams": manager.num_streams,
        "avg_parallel_ms": round(avg_parallel, 2),
        "avg_sequential_ms": round(avg_sequential, 2),
        "speedup": round(speedup, 2),
        "recommendation": (
            f"Use CUDA streams (speedup: {speedup:.2f}x)"
            if speedup > 1.1
            else "Sequential execution recommended (minimal benefit)"
        ),
    }


# Example integration
def example_parallel_workflow(texts: List[str], llm_prompt: str) -> Dict[str, Any]:
    """Example workflow using parallel CUDA streams.

    Args:
        texts: List of texts for sentiment analysis
        llm_prompt: Prompt for LLM

    Returns:
        Dict with sentiment and LLM results
    """
    from catalyst_bot.llm_client import query_llm
    from catalyst_bot.ml.batch_sentiment import batch_score_texts

    # Define inference functions
    def sentiment_inference():
        # Load model (cached)
        from catalyst_bot.ml.model_switcher import load_sentiment_model

        model = load_sentiment_model()
        return batch_score_texts(texts, model, batch_size=10)

    def llm_inference():
        return query_llm(llm_prompt)

    # Run in parallel
    sentiment_results, llm_result = run_parallel_inference(
        sentiment_inference, llm_inference
    )

    return {
        "sentiment": sentiment_results,
        "llm": llm_result,
    }


if __name__ == "__main__":
    # Run benchmark
    results = benchmark_streams(iterations=10)

    print("\n=== CUDA Streams Benchmark ===")
    print(f"Streams enabled: {results['streams_enabled']}")
    print(f"CUDA available: {results['cuda_available']}")
    print(f"Number of streams: {results['num_streams']}")
    print(f"Average parallel time: {results['avg_parallel_ms']:.2f} ms")
    print(f"Average sequential time: {results['avg_sequential_ms']:.2f} ms")
    print(f"Speedup: {results['speedup']:.2f}x")
    print(f"\nRecommendation: {results['recommendation']}")
