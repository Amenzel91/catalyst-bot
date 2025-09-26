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

The ``query_llm`` function should be used by higher‑level modules
(for example, ``llm_classifier.py``) to send prompts to the LLM.  It
handles JSON encoding, HTTP POST, timeout, and basic error handling.
Failures are logged and result in ``None`` responses so that callers
can gracefully degrade to existing heuristics.
"""

from __future__ import annotations

import json
import logging
import os
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

_logger = logging.getLogger(__name__)


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


def query_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    stream: bool = False,
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
            if resp.status_code != 200:
                _logger.warning("LLM API returned non‑200 status: %s", resp.status_code)
                return None
            try:
                json_data = resp.json()
            except Exception:
                return resp.text.strip() or None
            # If streaming is disabled the API returns a single JSON
            # object with a ``response`` field; otherwise it may stream
            # multiple JSON lines.
            if isinstance(json_data, dict) and "response" in json_data:
                return str(json_data["response"] or "").strip()
            # Unexpected shape; return as string
            return str(json_data) if json_data else None
        else:
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
                    return str(obj["response"] or "").strip()
                return resp_data.strip()
            except Exception:
                return resp_data.strip()
    except Exception as exc:
        _logger.exception("LLM query failed: %s", exc)
        return None
