"""
LLM‑based news classifier for Catalyst‑Bot.

This module defines a single function, :func:`classify_news`, which
uses a local large language model (LLM) to evaluate a news headline
and optional summary.  The classifier determines whether a piece of
news is catalyst‑worthy, identifies the relevant catalysts, rates the
potential impact on the stock from −1 (very negative) to +1 (very
positive), and returns a concise rationale.

The implementation relies on :func:`catalyst_bot.llm_client.query_llm`
to communicate with the local LLM API.  All invocations are
surrounded with a timeout and broad exception handling so that
upstream pipelines remain resilient when the model is unavailable or
returns unexpected output.  Feature flags control whether this
classification is executed at runtime.

The returned dictionary contains the following keys (when available):

* ``llm_tags`` – list of lower‑case catalyst tags (e.g., ``["earnings", "fda"]``) representing the primary catalysts extracted from the text.
* ``llm_relevance`` – float between 0 and 1 indicating how likely
  the news is to be a meaningful catalyst.
* ``llm_sentiment`` – float between −1 and 1 representing the
  predicted price impact (positive numbers for bullish news,
  negative for bearish news).
* ``llm_reason`` – short natural language explanation of the
  classification outcome.  Useful for debugging and admin embeds.

Callers are expected to merge these results into event dictionaries
without overwriting existing fields when the LLM is disabled or
returns ``None``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .llm_client import query_llm

_logger = logging.getLogger(__name__)


def _parse_json_response(text: str) -> Dict[str, Any]:
    """Attempt to parse a JSON object from the model's response.

    The LLM may return either raw JSON or a natural language reply.  This
    helper extracts a JSON object if present by searching for a JSON
    substring enclosed in braces.  If no JSON is found the entire
    string is returned under the ``"llm_reason"`` key.
    """
    if not text:
        return {}
    # Attempt full JSON parse first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # Search for a JSON object inside the text
    try:
        m = re.search(r"{.*}", text, re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    # Fall back to returning reason only
    return {"llm_reason": text.strip()}


def classify_news(headline: str, summary: Optional[str] = None) -> Dict[str, Any]:
    """Classify a news item using a local LLM.

    Parameters
    ----------
    headline: str
        The headline or title of the news item.
    summary: Optional[str]
        Optional short summary of the article.  When provided it is
        appended to the prompt to give the model more context.  The
        summary should be concise (≤ 1–2 sentences) to avoid hitting
        context limits.

    Returns
    -------
    Dict[str, Any]
        Dictionary containing LLM classification results.  When the
        request fails or returns unrecognised output the dictionary
        will be empty or contain only a ``"llm_reason"`` key.
    """
    if not headline or not isinstance(headline, str):
        return {}
    # Build the prompt.  Provide a clear instruction to the model to
    # respond in JSON format with tags, relevance, sentiment and reason.
    prompt_lines: List[str] = []
    prompt_lines.append(
        "You are an AI assistant helping a news trading bot classify news."
    )
    prompt_lines.append(
        "Given the following headline and optional summary, decide if the news is a catalyst for the stock."
    )
    prompt_lines.append(
        "Return a JSON object with keys: tags (list of catalysts), relevance (0–1 float), sentiment (-1 to 1 float), reason (short explanation)."
    )
    prompt_lines.append(f"Headline: {headline.strip()}")
    if summary:
        prompt_lines.append(f"Summary: {summary.strip()}")
    # Example output helps steer the model towards the expected JSON schema
    prompt_lines.append(
        "Example output: {\"tags\": [\"earnings\"], \"relevance\": 0.8, \"sentiment\": 0.6, \"reason\": \"Strong guidance above expectations\"}"
    )
    full_prompt = "\n".join(prompt_lines)
    try:
        raw = query_llm(full_prompt)
    except Exception as exc:
        _logger.exception("LLM classify_news query failed: %s", exc)
        return {}
    if not raw:
        return {}
    data = _parse_json_response(raw)
    # Normalise keys: prefix with 'llm_' to avoid clashing with existing fields
    result: Dict[str, Any] = {}
    try:
        tags = data.get("tags")
        if isinstance(tags, list):
            result["llm_tags"] = [str(t).strip().lower() for t in tags if t]
        relevance = data.get("relevance")
        if isinstance(relevance, (int, float)):
            result["llm_relevance"] = float(relevance)
        sentiment = data.get("sentiment")
        if isinstance(sentiment, (int, float)):
            # Clamp between −1 and 1
            s_val = max(-1.0, min(1.0, float(sentiment)))
            result["llm_sentiment"] = s_val
        reason = data.get("reason")
        if isinstance(reason, str) and reason.strip():
            result["llm_reason"] = reason.strip()
        # If no keys were parsed but we have a fallback llm_reason
        if not result and "llm_reason" in data:
            result["llm_reason"] = data["llm_reason"]
    except Exception as exc:
        _logger.exception("LLM classify_news parse error: %s", exc)
        # Keep whatever could be extracted
        if "llm_reason" not in result and "llm_reason" in data:
            result["llm_reason"] = data["llm_reason"]
    return result