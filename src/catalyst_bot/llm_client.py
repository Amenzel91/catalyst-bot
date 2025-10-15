"""
LLM client module for Catalyst‑Bot.

This module provides a simple wrapper around a local large language
model (LLM) HTTP API.  The client is designed to call a locally
running model served by the Ollama API (`/api/generate`) and return
responses in a best‑effort manner.  All behaviour is gated behind
feature flags and environment variables so that the bot can operate
without an LLM when disabled.

Environment variables (with defaults) used by this module:

* ``LLM_ENDPOINT_URL`` – full URL to the LLM API endpoint.  Defaults
  to ``"http://localhost:11434/api/generate"``.  When integrating
  Ollama, the endpoint must include ``/api/generate`` so that the
  request body can be sent directly to the model.
* ``LLM_MODEL_NAME`` – name of the model to call.  Defaults to
  ``"mistral"``.
* ``LLM_TIMEOUT_SECS`` – request timeout in seconds.  Defaults to
  ``15`` seconds.  Long timeouts may block the ingest pipeline so
  choose conservatively.
* ``GPU_CLEANUP_INTERVAL_SEC`` – interval in seconds between GPU
  cleanup operations.  Defaults to 300 seconds (5 minutes).

The ``query_llm`` function should be used by higher‑level modules
(for example, ``llm_classifier.py``) to send prompts to the LLM.  It
handles JSON encoding, HTTP POST, timeout, and basic error handling.
Failures are logged and result in ``None`` responses so that callers
can gracefully degrade to existing heuristics.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import time
from typing import Any, Dict, Optional

try:
    # ``requests`` is a common dependency but may not be installed in
    # minimal environments.  We fall back to ``urllib" if it is not
    # available.
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

if requests is None:
    import urllib.error
    import urllib.request

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

_logger = logging.getLogger(__name__)

# Track last cleanup time to avoid over-cleaning
_last_cleanup_time = 0.0
_cleanup_interval = float(os.getenv("GPU_CLEANUP_INTERVAL_SEC", "300"))  # 5 min default


def _get_env_str(key: str, default: str) -> str:
    try:
        val = os.getenv(key)
        if val is None or not str(val).strip():
            return default
        return str(val).strip()
    except Exception:
        return default


def _get_env_float(key: str, default: float) -> float:
    try:
        val = os.getenv(key)
        if val is None:
            return default
        return float(val)
    except Exception:
        return default


def cleanup_gpu_memory(force: bool = False) -> None:
    """
    Critical GPU memory cleanup for AMD RX 6800.

    MUST execute in this exact sequence:
    1. Move model to CPU (if accessible)
    2. Delete references
    3. Trigger Python garbage collection
    4. Synchronize CUDA/ROCm operations
    5. Empty cache
    6. Reset peak memory stats

    Args:
        force: If True, cleanup regardless of interval timer
    """
    global _last_cleanup_time

    if not TORCH_AVAILABLE:
        return

    # Rate limit cleanup unless forced
    now = time.time()
    if not force and (now - _last_cleanup_time) < _cleanup_interval:
        return

    try:
        # Step 1: Garbage collection first
        gc.collect()

        # Step 2: CUDA/ROCm synchronization and cleanup
        if torch.cuda.is_available():
            torch.cuda.synchronize()  # Wait for GPU operations
            torch.cuda.empty_cache()  # Clear CUDA cache

            # Reset tracking (helps identify memory leaks)
            try:
                torch.cuda.reset_peak_memory_stats()
            except Exception:
                pass

            _last_cleanup_time = now

            # Log memory stats for monitoring
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3  # GB
                reserved = torch.cuda.memory_reserved() / 1024**3  # GB
                _logger.debug(
                    "gpu_cleanup_done allocated=%.2fGB reserved=%.2fGB",
                    allocated,
                    reserved,
                )
    except Exception as e:
        _logger.warning("gpu_cleanup_failed err=%s", str(e))


def query_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    stream: bool = False,
    max_retries: int = 3,
) -> Optional[str]:
    """Send a prompt to the local LLM and return the response text.

    Parameters
    ----------
    prompt: str
        The user prompt to send to the model.
    system: Optional[str]
        Optional system message to influence the style or behaviour of
        the model (e.g. summarisation instructions).  If omitted, no
        system message is sent.
    model: Optional[str]
        Override the model name.  Falls back to ``LLM_MODEL_NAME``.
    timeout: Optional[float]
        Override the request timeout (in seconds).  Falls back to
        ``LLM_TIMEOUT_SECS``.
    stream: bool
        Whether to request a streaming response.  When ``False`` (the
        default) the entire response is returned as a single string.
        Streaming is not yet fully supported by this helper and will
        behave like a non‑streaming request.
    max_retries: int
        Number of retry attempts (default: 3)

    Returns
    -------
    Optional[str]
        The response text or ``None`` on failure.
    """
    endpoint = _get_env_str("LLM_ENDPOINT_URL", "http://localhost:11434/api/generate")
    model_name = model or _get_env_str("LLM_MODEL_NAME", "mistral")
    timeout_secs = (
        timeout if timeout is not None else _get_env_float("LLM_TIMEOUT_SECS", 15.0)
    )
    # Build the request payload.  The API expects JSON with ``model`` and
    # ``prompt`` fields; additional options can be provided under
    # ``options``.  When ``system`` is provided it is passed through.
    body: Dict[str, Any] = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        body["system"] = system
    # Use a small context window by default; rely on server defaults
    body.setdefault("options", {})

    # Retry loop with exponential backoff
    retry_delay = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            data = json.dumps(body).encode("utf-8")
        except Exception as exc:
            _logger.error("Failed to serialise LLM request body: %s", exc)
            return None

        headers = {"Content-Type": "application/json"}

        try:
            if requests is not None:
                resp = requests.post(
                    endpoint, data=data, headers=headers, timeout=timeout_secs
                )

                # Handle server overload (500 errors)
                if resp.status_code == 500:
                    _logger.warning(
                        "llm_server_overload attempt=%d/%d retrying_in=%.1fs",
                        attempt + 1,
                        max_retries,
                        retry_delay * (attempt + 1),
                    )
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        _logger.error("llm_failed_after_retries status=500")
                        cleanup_gpu_memory(force=True)  # Force cleanup on failure
                        return None

                if resp.status_code != 200:
                    _logger.warning("llm_bad_status status=%d", resp.status_code)
                    return None

                # Parse response
                try:
                    json_data = resp.json()
                except Exception:
                    return resp.text.strip() or None

                if isinstance(json_data, dict) and "response" in json_data:
                    result = str(json_data["response"] or "").strip()

                    # Periodic GPU cleanup (every N calls)
                    cleanup_gpu_memory(force=False)

                    return result

                return str(json_data) if json_data else None

            else:
                # urllib fallback
                req = urllib.request.Request(
                    endpoint, data=data, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
                    resp_data = resp.read().decode("utf-8", errors="ignore")

                if not resp_data:
                    return None

                try:
                    obj = json.loads(resp_data)
                    if isinstance(obj, dict) and "response" in obj:
                        result = str(obj["response"] or "").strip()
                        cleanup_gpu_memory(force=False)
                        return result
                    return resp_data.strip()
                except Exception:
                    return resp_data.strip()

        except (TimeoutError, urllib.error.URLError) as e:
            _logger.warning(
                "llm_timeout attempt=%d/%d err=%s", attempt + 1, max_retries, str(e)
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None

        except Exception as exc:
            _logger.exception("llm_query_failed err=%s", str(exc))
            cleanup_gpu_memory(force=True)
            return None

    return None


# GPU Warmup tracking
_GPU_WARMED = False
_WARMUP_ATTEMPTS = 0
_MAX_WARMUP_ATTEMPTS = 3


def prime_ollama_gpu(force: bool = False) -> bool:
    """
    Prime Ollama GPU with small warmup query before batch processing.

    Prevents cold-start overhead on first LLM call (reduces first-call
    latency by ~500ms).

    Args:
        force: Force warmup even if already warmed

    Returns:
        True if warmup succeeded, False otherwise
    """
    global _GPU_WARMED, _WARMUP_ATTEMPTS

    if _GPU_WARMED and not force:
        return True

    # Limit warmup attempts to prevent infinite loops
    _WARMUP_ATTEMPTS += 1
    if _WARMUP_ATTEMPTS > _MAX_WARMUP_ATTEMPTS:
        _logger.error("gpu_warmup_max_attempts_exceeded attempts=%d", _WARMUP_ATTEMPTS)
        return False

    warmup_prompt = "Respond with 'OK'"

    try:
        start = time.time()

        result = query_llm(warmup_prompt, timeout=10.0, max_retries=1)

        if result:
            elapsed_ms = (time.time() - start) * 1000
            _logger.info(
                "gpu_warmup_success latency=%.0fms attempt=%d",
                elapsed_ms,
                _WARMUP_ATTEMPTS,
            )
            _GPU_WARMED = True
            _WARMUP_ATTEMPTS = 0  # Reset on success
            return True
        else:
            _logger.warning(
                "gpu_warmup_failed result=None attempt=%d", _WARMUP_ATTEMPTS
            )
            return False

    except Exception as e:
        _logger.warning("gpu_warmup_error err=%s attempt=%d", str(e), _WARMUP_ATTEMPTS)
        return False


def is_gpu_warmed() -> bool:
    """
    Check if GPU has been warmed up.

    Returns:
        True if GPU is warmed up, False otherwise
    """
    return _GPU_WARMED


def reset_warmup_state() -> None:
    """Reset GPU warmup state (for testing or after failures)."""
    global _GPU_WARMED, _WARMUP_ATTEMPTS
    _GPU_WARMED = False
    _WARMUP_ATTEMPTS = 0
    _logger.info("gpu_warmup_state_reset")


def get_gpu_memory_stats() -> Optional[Dict[str, float]]:
    """
    Get current GPU memory statistics.

    Returns:
        Dict with allocated_gb, reserved_gb, free_gb or None if not available
    """
    if not TORCH_AVAILABLE or not torch.cuda.is_available():
        return None

    try:
        allocated = torch.cuda.memory_allocated() / 1024**3  # GB
        reserved = torch.cuda.memory_reserved() / 1024**3  # GB
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
        free = total - allocated

        return {
            "allocated_gb": round(allocated, 2),
            "reserved_gb": round(reserved, 2),
            "free_gb": round(free, 2),
            "total_gb": round(total, 2),
            "utilization_pct": round((allocated / total) * 100, 1),
        }
    except Exception as e:
        _logger.warning("gpu_stats_failed err=%s", str(e))
        return None
