"""
GPU Profiler for Catalyst-Bot ML Models

This module provides profiling utilities for measuring GPU usage, model
inference performance, and identifying optimization opportunities.

Features:
- Profile sentiment models (FinBERT, DistilBERT, etc.)
- Profile LLM inference (Ollama/Mistral)
- Measure batch processing speedup
- Track VRAM usage and memory efficiency
- Generate profiling reports for optimization decisions

Usage:
    python -m catalyst_bot.gpu_profiler --mode sentiment
    python -m catalyst_bot.gpu_profiler --mode llm
    python -m catalyst_bot.gpu_profiler --mode full
"""

from __future__ import annotations

import gc
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)


@dataclass
class ProfilingResult:
    """Container for profiling metrics."""

    model_name: str
    model_type: str  # 'sentiment' or 'llm'
    timestamp: str
    load_time_ms: float
    inference_time_ms: float
    items_per_second: float
    vram_used_mb: float
    vram_total_mb: float
    batch_results: List[Dict[str, Any]]
    notes: str = ""


def get_gpu_memory_info() -> Dict[str, float]:
    """Get current GPU memory usage.

    Returns:
        Dict with 'used_mb', 'total_mb', 'free_mb', 'utilization_pct'
    """
    try:
        import torch

        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated(0) / (1024**2)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**2)
            free = total - used
            return {
                "used_mb": used,
                "total_mb": total,
                "free_mb": free,
                "utilization_pct": (used / total * 100) if total > 0 else 0.0,
            }
    except Exception as e:
        _logger.warning("Failed to get GPU memory info: %s", e)

    # Fallback to nvidia-smi
    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                parts = lines[0].split(",")
                used = float(parts[0].strip())
                total = float(parts[1].strip())
                free = total - used
                return {
                    "used_mb": used,
                    "total_mb": total,
                    "free_mb": free,
                    "utilization_pct": (used / total * 100) if total > 0 else 0.0,
                }
    except Exception as e:
        _logger.warning("nvidia-smi unavailable: %s", e)

    return {"used_mb": 0.0, "total_mb": 0.0, "free_mb": 0.0, "utilization_pct": 0.0}


def cleanup_gpu_memory() -> None:
    """Force GPU memory cleanup."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()


def profile_sentiment_model(
    model_name: str = "finbert",
    batch_sizes: Optional[List[int]] = None,
    sample_texts: Optional[List[str]] = None,
) -> ProfilingResult:
    """Profile a sentiment analysis model.

    Args:
        model_name: Model identifier ('finbert', 'distilbert', 'vader')
        batch_sizes: List of batch sizes to test (default: [1, 5, 10, 20])
        sample_texts: Sample texts for inference (defaults to financial headlines)

    Returns:
        ProfilingResult with performance metrics
    """
    if batch_sizes is None:
        batch_sizes = [1, 5, 10, 20]

    if sample_texts is None:
        # Default financial headline samples
        sample_texts = [
            "FDA approves breakthrough cancer therapy from biotech startup",
            "Company announces unexpected quarterly loss amid market volatility",
            "Strategic partnership with Fortune 500 company boosts outlook",
            "Regulatory concerns lead to product recall and revenue warning",
            "Clinical trial shows promising results for phase 3 drug candidate",
        ]

    _logger.info("Profiling sentiment model: %s", model_name)
    cleanup_gpu_memory()

    mem_before = get_gpu_memory_info()

    # Load model
    load_start = time.perf_counter()
    model = None
    try:
        if model_name.lower() == "vader":
            # VADER is CPU-only, no GPU usage
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            model = SentimentIntensityAnalyzer()
        elif model_name.lower() in ["finbert", "distilbert", "roberta"]:
            # Try loading transformers-based model
            try:
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                    pipeline,
                )

                model_map = {
                    "finbert": "ProsusAI/finbert",
                    "distilbert": "distilbert-base-uncased-finetuned-sst-2-english",
                    "roberta": "cardiffnlp/twitter-roberta-base-sentiment",
                }
                hf_model_id = model_map.get(model_name.lower(), model_name)

                tokenizer = AutoTokenizer.from_pretrained(hf_model_id)
                torch_model = AutoModelForSequenceClassification.from_pretrained(
                    hf_model_id
                )

                # Try to move to GPU
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch_model = torch_model.cuda()
                        device = 0
                    else:
                        device = -1  # CPU
                except Exception:
                    device = -1

                model = pipeline(
                    "sentiment-analysis",
                    model=torch_model,
                    tokenizer=tokenizer,
                    device=device,
                )
            except ImportError:
                _logger.warning(
                    "transformers library not available, falling back to VADER"
                )
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

                model = SentimentIntensityAnalyzer()
                model_name = "vader"
    except Exception as e:
        _logger.error("Failed to load model %s: %s", model_name, e)
        raise

    load_time = (time.perf_counter() - load_start) * 1000  # ms
    mem_after = get_gpu_memory_info()
    vram_used = mem_after["used_mb"] - mem_before["used_mb"]

    _logger.info("Model loaded in %.2f ms, VRAM: +%.2f MB", load_time, vram_used)

    # Profile batch inference
    batch_results = []
    for batch_size in batch_sizes:
        # Create batch
        batch_texts = sample_texts * (batch_size // len(sample_texts) + 1)
        batch_texts = batch_texts[:batch_size]

        # Warmup run
        _run_sentiment_inference(model, batch_texts[:1], model_name)

        # Timed runs
        times = []
        for _ in range(3):
            start = time.perf_counter()
            _run_sentiment_inference(model, batch_texts, model_name)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        items_per_sec = (batch_size / avg_time) * 1000 if avg_time > 0 else 0

        batch_results.append(
            {
                "batch_size": batch_size,
                "avg_time_ms": round(avg_time, 2),
                "items_per_second": round(items_per_sec, 2),
                "speedup_vs_1": (
                    round(items_per_sec / batch_results[0]["items_per_second"], 2)
                    if batch_results
                    else 1.0
                ),
            }
        )

        _logger.info(
            "Batch %d: %.2f ms (%.2f items/sec)", batch_size, avg_time, items_per_sec
        )

    # Calculate overall metrics
    single_item_time = batch_results[0]["avg_time_ms"]
    single_item_throughput = batch_results[0]["items_per_second"]

    result = ProfilingResult(
        model_name=model_name,
        model_type="sentiment",
        timestamp=datetime.now().isoformat(),
        load_time_ms=round(load_time, 2),
        inference_time_ms=round(single_item_time, 2),
        items_per_second=round(single_item_throughput, 2),
        vram_used_mb=round(max(vram_used, mem_after["used_mb"]), 2),
        vram_total_mb=round(mem_after["total_mb"], 2),
        batch_results=batch_results,
        notes=f"Best speedup: {max(r['speedup_vs_1'] for r in batch_results):.2f}x at batch_size={max(batch_results, key=lambda x: x['speedup_vs_1'])['batch_size']}",  # noqa: E501
    )

    cleanup_gpu_memory()
    return result


def _run_sentiment_inference(model: Any, texts: List[str], model_type: str) -> List:
    """Run sentiment inference on a batch of texts."""
    if model_type.lower() == "vader":
        return [model.polarity_scores(text) for text in texts]
    else:
        # Transformers pipeline
        return model(texts)


def profile_llm_inference(
    endpoint_url: Optional[str] = None,
    model_name: Optional[str] = None,
    prompt_lengths: Optional[List[int]] = None,
) -> ProfilingResult:
    """Profile LLM inference (Ollama/Mistral).

    Args:
        endpoint_url: LLM API endpoint (defaults to env LLM_ENDPOINT_URL)
        model_name: Model name (defaults to env LLM_MODEL_NAME)
        prompt_lengths: List of prompt lengths to test in tokens

    Returns:
        ProfilingResult with LLM performance metrics
    """
    from catalyst_bot.llm_client import query_llm

    if endpoint_url is None:
        endpoint_url = os.getenv(
            "LLM_ENDPOINT_URL", "http://localhost:11434/api/generate"
        )
    if model_name is None:
        model_name = os.getenv("LLM_MODEL_NAME", "mistral")
    if prompt_lengths is None:
        prompt_lengths = [50, 100, 200, 500]

    _logger.info("Profiling LLM: %s at %s", model_name, endpoint_url)
    cleanup_gpu_memory()

    # Generate test prompts of varying lengths
    base_prompt = (
        "Analyze the following financial news headline and determine if it is bullish, "
        "bearish, or neutral for the stock price. Provide a brief explanation. "
    )
    test_prompts = []
    for length in prompt_lengths:
        # Approximate token count (rough estimate: 4 chars per token)
        char_count = length * 4
        padding = "x" * max(0, char_count - len(base_prompt))
        test_prompts.append(base_prompt + padding)

    batch_results = []
    get_gpu_memory_info()

    for i, prompt in enumerate(test_prompts):
        _logger.info("Testing prompt length: ~%d tokens", prompt_lengths[i])

        # Warmup
        query_llm(prompt[:100], model=model_name, timeout=30)

        # Timed runs
        times = []
        token_counts = []
        for _ in range(2):  # Fewer runs for LLM due to time
            start = time.perf_counter()
            response = query_llm(prompt, model=model_name, timeout=30)
            elapsed = (time.perf_counter() - start) * 1000  # ms

            if response:
                times.append(elapsed)
                # Estimate tokens (very rough)
                token_counts.append(len(response.split()))

        if times:
            avg_time = sum(times) / len(times)
            avg_tokens = sum(token_counts) / len(token_counts) if token_counts else 0
            tokens_per_sec = (avg_tokens / avg_time) * 1000 if avg_time > 0 else 0

            batch_results.append(
                {
                    "prompt_length_tokens": prompt_lengths[i],
                    "avg_time_ms": round(avg_time, 2),
                    "avg_response_tokens": round(avg_tokens, 2),
                    "tokens_per_second": round(tokens_per_sec, 2),
                }
            )

            _logger.info(
                "Prompt %d tokens: %.2f ms, %.2f tokens/sec",
                prompt_lengths[i],
                avg_time,
                tokens_per_sec,
            )

    mem_after = get_gpu_memory_info()

    # Calculate metrics
    if batch_results:
        avg_inference_time = sum(r["avg_time_ms"] for r in batch_results) / len(
            batch_results
        )
        avg_throughput = sum(r["tokens_per_second"] for r in batch_results) / len(
            batch_results
        )
    else:
        avg_inference_time = 0.0
        avg_throughput = 0.0

    result = ProfilingResult(
        model_name=model_name,
        model_type="llm",
        timestamp=datetime.now().isoformat(),
        load_time_ms=0.0,  # Model already loaded on server
        inference_time_ms=round(avg_inference_time, 2),
        items_per_second=round(avg_throughput, 2),
        vram_used_mb=round(mem_after["used_mb"], 2),
        vram_total_mb=round(mem_after["total_mb"], 2),
        batch_results=batch_results,
        notes=f"Average throughput: {avg_throughput:.2f} tokens/sec",
    )

    cleanup_gpu_memory()
    return result


def save_profiling_report(
    results: List[ProfilingResult], output_dir: str = "out/profiling"
) -> str:
    """Save profiling results to JSON report.

    Args:
        results: List of ProfilingResult objects
        output_dir: Directory to save report

    Returns:
        Path to saved report file
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gpu_profile_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    report = {
        "generated_at": datetime.now().isoformat(),
        "system_info": get_gpu_memory_info(),
        "results": [asdict(r) for r in results],
        "summary": {
            "total_models_profiled": len(results),
            "sentiment_models": [
                r.model_name for r in results if r.model_type == "sentiment"
            ],
            "llm_models": [r.model_name for r in results if r.model_type == "llm"],
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    _logger.info("Profiling report saved to: %s", filepath)
    return filepath


def main():
    """CLI entry point for GPU profiling."""
    import argparse

    parser = argparse.ArgumentParser(description="Profile Catalyst-Bot ML models")
    parser.add_argument(
        "--mode",
        choices=["sentiment", "llm", "full"],
        default="full",
        help="Profiling mode",
    )
    parser.add_argument(
        "--sentiment-model",
        default="finbert",
        help="Sentiment model to profile (finbert, distilbert, roberta, vader)",
    )
    parser.add_argument(
        "--output-dir", default="out/profiling", help="Output directory for reports"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    results = []

    if args.mode in ["sentiment", "full"]:
        _logger.info("=== Profiling Sentiment Model ===")
        try:
            result = profile_sentiment_model(model_name=args.sentiment_model)
            results.append(result)
            print(f"\nSentiment Model: {result.model_name}")
            print(f"  Load time: {result.load_time_ms:.2f} ms")
            print(f"  Single item inference: {result.inference_time_ms:.2f} ms")
            print(f"  Throughput: {result.items_per_second:.2f} items/sec")
            print(f"  VRAM used: {result.vram_used_mb:.2f} MB")
            print(f"  {result.notes}")
        except Exception as e:
            _logger.error("Failed to profile sentiment model: %s", e)

    if args.mode in ["llm", "full"]:
        _logger.info("\n=== Profiling LLM ===")
        try:
            result = profile_llm_inference()
            results.append(result)
            print(f"\nLLM Model: {result.model_name}")
            print(f"  Average inference: {result.inference_time_ms:.2f} ms")
            print(f"  Throughput: {result.items_per_second:.2f} tokens/sec")
            print(f"  VRAM used: {result.vram_used_mb:.2f} MB")
        except Exception as e:
            _logger.error("Failed to profile LLM: %s", e)

    if results:
        report_path = save_profiling_report(results, output_dir=args.output_dir)
        print(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    main()
