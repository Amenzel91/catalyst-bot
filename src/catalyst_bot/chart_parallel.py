"""Parallel chart generation using ThreadPoolExecutor.

This module provides utilities for generating multiple charts concurrently
to reduce overall generation time and improve responsiveness.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("chart_parallel")


log = get_logger("chart_parallel")


def generate_charts_parallel(
    ticker: str,
    timeframes: List[str],
    chart_generator: Callable[[str, str], Optional[Any]],
    *,
    max_workers: Optional[int] = None,
) -> Dict[str, Optional[Any]]:
    """Generate charts for multiple timeframes in parallel.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframes : List[str]
        List of timeframes to generate (e.g., ["1D", "5D", "1M"])
    chart_generator : Callable[[str, str], Optional[Any]]
        Function that takes (ticker, timeframe) and returns chart result
    max_workers : Optional[int]
        Maximum number of parallel workers (defaults to CHART_PARALLEL_MAX_WORKERS env var or 3)

    Returns
    -------
    Dict[str, Optional[Any]]
        Mapping of timeframe -> chart result (or None if failed)
    """
    # Determine max workers from environment or default to 3
    if max_workers is None:
        try:
            max_workers = int(os.getenv("CHART_PARALLEL_MAX_WORKERS", "3"))
        except ValueError:
            max_workers = 3

    # Limit max workers to reasonable range
    max_workers = max(1, min(max_workers, 10))

    results = {}
    start_time = time.time()

    log.info(
        "parallel_chart_generation_start ticker=%s timeframes=%s workers=%d",
        ticker,
        timeframes,
        max_workers,
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all chart generation tasks
        futures = {
            executor.submit(chart_generator, ticker, tf): tf for tf in timeframes
        }

        # Collect results as they complete
        for future in as_completed(futures):
            tf = futures[future]
            try:
                result = future.result()
                results[tf] = result
                log.info(
                    "parallel_chart_complete ticker=%s tf=%s success=%s",
                    ticker,
                    tf,
                    result is not None,
                )
            except Exception as e:
                log.warning(
                    "parallel_chart_failed ticker=%s tf=%s err=%s",
                    ticker,
                    tf,
                    str(e),
                )
                results[tf] = None

    elapsed = time.time() - start_time
    log.info(
        "parallel_chart_generation_complete ticker=%s count=%d elapsed=%.2fs",
        ticker,
        len(results),
        elapsed,
    )

    return results


def generate_chart_with_cache(
    ticker: str,
    timeframe: str,
    chart_generator: Callable[[str, str], Optional[Any]],
    cache_get: Optional[Callable[[str, str], Optional[Any]]] = None,
    cache_put: Optional[Callable[[str, str, Any], None]] = None,
) -> Optional[Any]:
    """Generate chart with caching support.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe (1D, 5D, 1M, etc.)
    chart_generator : Callable[[str, str], Optional[Any]]
        Function that generates a chart
    cache_get : Optional[Callable[[str, str], Optional[Any]]]
        Function to retrieve cached chart
    cache_put : Optional[Callable[[str, str, Any], None]]
        Function to store chart in cache

    Returns
    -------
    Optional[Any]
        Chart result (from cache or freshly generated)
    """
    # Try cache first if available
    if cache_get:
        try:
            cached = cache_get(ticker, timeframe)
            if cached is not None:
                log.debug(
                    "chart_cache_hit ticker=%s tf=%s",
                    ticker,
                    timeframe,
                )
                return cached
        except Exception as e:
            log.debug(
                "chart_cache_get_failed ticker=%s tf=%s err=%s",
                ticker,
                timeframe,
                str(e),
            )

    # Generate new chart
    result = chart_generator(ticker, timeframe)

    # Store in cache if available and generation succeeded
    if result is not None and cache_put:
        try:
            cache_put(ticker, timeframe, result)
        except Exception as e:
            log.debug(
                "chart_cache_put_failed ticker=%s tf=%s err=%s",
                ticker,
                timeframe,
                str(e),
            )

    return result


def generate_charts_parallel_cached(
    ticker: str,
    timeframes: List[str],
    chart_generator: Callable[[str, str], Optional[Any]],
    cache_get: Optional[Callable[[str, str], Optional[Any]]] = None,
    cache_put: Optional[Callable[[str, str, Any], None]] = None,
    *,
    max_workers: Optional[int] = None,
) -> Dict[str, Optional[Any]]:
    """Generate charts in parallel with caching.

    Combines parallel generation with cache lookup/storage for optimal performance.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframes : List[str]
        List of timeframes to generate
    chart_generator : Callable[[str, str], Optional[Any]]
        Function that generates a chart
    cache_get : Optional[Callable[[str, str], Optional[Any]]]
        Function to retrieve cached chart
    cache_put : Optional[Callable[[str, str, Any], None]]
        Function to store chart in cache
    max_workers : Optional[int]
        Maximum number of parallel workers

    Returns
    -------
    Dict[str, Optional[Any]]
        Mapping of timeframe -> chart result
    """

    def _cached_generator(t: str, tf: str) -> Optional[Any]:
        return generate_chart_with_cache(t, tf, chart_generator, cache_get, cache_put)

    return generate_charts_parallel(
        ticker, timeframes, _cached_generator, max_workers=max_workers
    )


def benchmark_chart_generation(
    ticker: str,
    timeframes: List[str],
    chart_generator: Callable[[str, str], Optional[Any]],
    *,
    parallel: bool = True,
    max_workers: Optional[int] = None,
) -> Tuple[Dict[str, Optional[Any]], float]:
    """Benchmark chart generation performance.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframes : List[str]
        List of timeframes to generate
    chart_generator : Callable[[str, str], Optional[Any]]
        Function that generates a chart
    parallel : bool
        Use parallel generation (True) or sequential (False)
    max_workers : Optional[int]
        Maximum number of parallel workers (only used if parallel=True)

    Returns
    -------
    Tuple[Dict[str, Optional[Any]], float]
        (results, elapsed_seconds)
    """
    start_time = time.time()

    if parallel:
        results = generate_charts_parallel(
            ticker, timeframes, chart_generator, max_workers=max_workers
        )
    else:
        # Sequential generation for comparison
        results = {}
        for tf in timeframes:
            try:
                results[tf] = chart_generator(ticker, tf)
            except Exception as e:
                log.warning(
                    "sequential_chart_failed ticker=%s tf=%s err=%s",
                    ticker,
                    tf,
                    str(e),
                )
                results[tf] = None

    elapsed = time.time() - start_time

    log.info(
        "chart_generation_benchmark ticker=%s mode=%s timeframes=%d elapsed=%.2fs",
        ticker,
        "parallel" if parallel else "sequential",
        len(timeframes),
        elapsed,
    )

    return results, elapsed
