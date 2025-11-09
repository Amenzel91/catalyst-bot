"""
SEC Filing LLM Analyzer
========================

Uses local LLM (Ollama/Mistral) to analyze SEC filings and extract:
- Deal size and terms
- Dilution risk
- Warrant coverage
- Overall sentiment (-1 to +1)
- Key catalysts

Designed to work with 8-K, 424B5, FWP, and other material filings.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from .llm_client import query_llm
from .logging_utils import get_logger
from .prompt_compression import compress_sec_filing, should_compress

log = get_logger("sec_llm_analyzer")


def _extract_amount(text: str) -> Optional[float]:
    """Extract dollar amount from text (e.g., '$5.2 million' -> 5200000)."""
    if not text:
        return None

    # Match patterns like "$5.2M", "$10 million", "5.2MM"
    patterns = [
        r"\$?(\d+\.?\d*)\s*million",
        r"\$?(\d+\.?\d*)\s*M(?:M)?(?!\w)",
        r"\$(\d+,?\d*,?\d*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value_str = match.group(1).replace(",", "")
            try:
                value = float(value_str)
                if "million" in pattern or "M" in pattern:
                    return value * 1_000_000
                return value
            except ValueError:
                continue

    return None


def analyze_sec_filing(
    title: str,
    filing_type: str,
    summary: Optional[str] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    Analyze SEC filing using LLM.

    Parameters
    ----------
    title : str
        Filing title/headline
    filing_type : str
        Type of filing (e.g., '8-K', '424B5', 'FWP')
    summary : str, optional
        Optional filing summary or first paragraph
    timeout : float
        LLM query timeout in seconds

    Returns
    -------
    dict
        Analysis results with keys:
        - llm_sentiment: float (-1 to +1)
        - llm_confidence: float (0 to 1)
        - deal_size_usd: float or None
        - dilution_pct: float or None
        - has_warrants: bool
        - catalysts: list of str
        - summary: str (LLM-generated summary)
        - risk_level: str ('low', 'medium', 'high')
    """
    # Check if LLM is enabled
    if not os.getenv("FEATURE_LLM_CLASSIFIER", "0") in ("1", "true", "yes", "on"):
        log.debug("llm_disabled skipping_sec_analysis")
        return {}

    # Build context-aware prompt
    filing_context = f"Filing Type: {filing_type}\nTitle: {title}"
    if summary:
        filing_context += f"\nSummary: {summary[:500]}"  # Limit to 500 chars

    system_prompt = """You are a financial analyst specializing in SEC filings for penny stocks and day trading alerts.
Analyze the filing and respond with a JSON object containing:
{
  "sentiment": <float from -1 (very bearish) to +1 (very bullish)>,
  "confidence": <float from 0 to 1>,
  "deal_size": "<amount with unit, e.g., '$5.2 million' or 'N/A'>",
  "dilution": "<estimated dilution percentage or 'N/A'>",
  "has_warrants": <true/false>,
  "catalysts": [<list of key catalysts like "capital raise", "debt conversion", etc.>],
  "summary": "<1-2 sentence summary with EXPLICIT trading context>",
  "risk_level": "<'low', 'medium', or 'high'>"
}

IMPORTANT - Summary Format:
Your summary MUST start with clear trading context:
- BULLISH filings: Start with "BULLISH: [reason]..." or "POSITIVE: [reason]..."
- BEARISH filings: Start with "BEARISH: [reason]..." or "NEGATIVE: [reason]..."
- NEUTRAL filings: Start with "NEUTRAL: [reason]..." or "MIXED: [reason]..."

Examples:
- "BULLISH: $10M institutional investment at premium to market price, non-dilutive financing strengthens balance sheet."
- "BEARISH: $5M dilutive offering with full warrant coverage, represents 15% dilution to existing shareholders."
- "NEUTRAL: Standard 8-K disclosure with no material financial impact, administrative filing only."

Key factors:
- 424B5/FWP: Usually offerings (dilutive, bearish unless priced well)
- 8-K Item 1.01: Material agreements (context-dependent, analyze terms)
- 8-K Item 2.02: Earnings (positive if beats, negative if misses)
- 8-K Item 8.01: General updates (usually neutral, analyze specifics)
- Warrants/convertibles: Dilution risk (bearish due to future dilution)
- Large deal size relative to market cap: Higher dilution (bearish)
- Institutional investment: Bullish signal (validates company)
- Debt restructuring: Mixed (reduces pressure but may dilute)

CRITICAL: Traders need immediate clarity on whether to BUY or AVOID. Make your summary actionable."""

    user_prompt = f"""Analyze this SEC filing:

{filing_context}

Respond ONLY with valid JSON. No additional text."""

    try:
        response = query_llm(
            prompt=user_prompt,
            system=system_prompt,
            timeout=timeout,
        )

        if not response:
            log.warning("llm_no_response filing_type=%s", filing_type)
            return {}

        # Parse JSON response
        import json

        # Try to extract JSON from response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            response = json_match.group(0)

        analysis = json.loads(response)

        # Normalize and validate
        result = {
            "llm_sentiment": float(analysis.get("sentiment", 0.0)),
            "llm_confidence": float(analysis.get("confidence", 0.5)),
            "deal_size_str": str(analysis.get("deal_size", "N/A")),
            "dilution_str": str(analysis.get("dilution", "N/A")),
            "has_warrants": bool(analysis.get("has_warrants", False)),
            "catalysts": list(analysis.get("catalysts", [])),
            "summary": str(analysis.get("summary", "")),
            "risk_level": str(analysis.get("risk_level", "medium")),
        }

        # Extract numeric values
        result["deal_size_usd"] = _extract_amount(result["deal_size_str"])

        dilution_match = re.search(r"(\d+\.?\d*)%?", result["dilution_str"])
        if dilution_match:
            try:
                result["dilution_pct"] = float(dilution_match.group(1))
            except ValueError:
                result["dilution_pct"] = None
        else:
            result["dilution_pct"] = None

        log.info(
            f"sec_analysis_complete filing={filing_type} "
            f"sentiment={result['llm_sentiment']:.2f} "
            f"risk={result['risk_level']}"
        )

        return result

    except json.JSONDecodeError as e:
        log.warning(f"llm_json_parse_failed filing={filing_type} err={e}")
        return {}
    except Exception as e:
        log.error(f"sec_analysis_failed filing={filing_type} err={e}")
        return {}


def enhance_classification_with_llm(
    title: str,
    current_score: float,
    current_confidence: float,
    keywords: list[str],
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use LLM to enhance classification when keyword scanner has low confidence.

    Parameters
    ----------
    title : str
        News headline
    current_score : float
        Current aggregate score
    current_confidence : float
        Confidence level (0-1)
    keywords : list of str
        Keywords detected by scanner
    source : str, optional
        Source of the news

    Returns
    -------
    dict
        Enhanced classification with:
        - llm_sentiment: float
        - llm_tags: list of str
        - llm_confidence: float
        - should_boost: bool (True if LLM recommends alerting)
    """
    # Only invoke LLM for low-confidence items
    confidence_threshold = float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.6"))

    if current_confidence >= confidence_threshold:
        return {}

    if not os.getenv("FEATURE_LLM_FALLBACK", "0") in ("1", "true", "yes", "on"):
        return {}

    system_prompt = """You are a trading catalyst detector for penny stocks.
Analyze the headline and determine if it represents a meaningful trading catalyst.

Respond with JSON:
{
  "is_catalyst": <true/false>,
  "sentiment": <-1 to +1>,
  "confidence": <0 to 1>,
  "catalysts": [<list of catalyst types>],
  "reason": "<brief explanation>"
}

Catalyst types: earnings, fda, merger, acquisition, partnership, contract,
upgrade, downgrade, insider_buying, short_squeeze, dilution, bankruptcy, halt"""

    user_prompt = f"""Headline: {title}
Keywords detected: {', '.join(keywords) if keywords else 'None'}
Source: {source or 'Unknown'}

Is this a meaningful catalyst? Respond with JSON only."""

    try:
        response = query_llm(
            prompt=user_prompt,
            system=system_prompt,
            timeout=15.0,
        )

        if not response:
            return {}

        import json

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            response = json_match.group(0)

        analysis = json.loads(response)

        result = {
            "llm_sentiment": float(analysis.get("sentiment", 0.0)),
            "llm_tags": list(analysis.get("catalysts", [])),
            "llm_confidence": float(analysis.get("confidence", 0.5)),
            "should_boost": bool(analysis.get("is_catalyst", False)),
            "llm_reason": str(analysis.get("reason", "")),
        }

        if result["should_boost"]:
            log.info(
                f"llm_boost_recommended title='{title[:50]}...' "
                f"sentiment={result['llm_sentiment']:.2f}"
            )

        return result

    except Exception as e:
        log.debug(f"llm_fallback_failed err={e}")
        return {}


def should_use_llm_for_filing(filing_type: str) -> bool:
    """Check if LLM analysis should be used for this filing type."""
    # High-value filings that benefit from LLM analysis
    llm_worthy_filings = {
        "8-K",
        "424B5",  # Prospectus supplement (offerings)
        "FWP",  # Free writing prospectus
        "13D",  # Beneficial ownership (5%+)
        "13G",  # Passive ownership
        "SC 13D",
        "SC 13G",
    }

    return filing_type.upper() in llm_worthy_filings


def extract_keywords_from_document_sync(
    document_text: str,
    title: str,
    filing_type: str,
) -> Dict[str, Any]:
    """
    Synchronous wrapper for extracting keywords from SEC documents.

    This is a convenience function for synchronous contexts (like the bootstrapper).
    Uses asyncio.run() to call the async version.

    Parameters
    ----------
    document_text : str
        Full or partial text of SEC filing
    title : str
        Filing title
    filing_type : str
        Type of filing (e.g., '8-K', '424B5')

    Returns
    -------
    dict
        Keywords and analysis (same as async version)
    """
    import asyncio

    try:
        return asyncio.run(
            extract_keywords_from_document(document_text, title, filing_type)
        )
    except Exception as e:
        log.error(f"sync_keyword_extraction_failed filing={filing_type} err={e}")
        return {}


async def extract_keywords_from_document(
    document_text: str,
    title: str,
    filing_type: str,
) -> Dict[str, Any]:
    """
    Extract trading keywords from SEC document using hybrid LLM with specialized prompts.

    Uses Gemini 2.0 Flash with filing-specific prompts for:
    - Earnings reports (Item 2.02)
    - Clinical trials (biotech/pharma)
    - Partnerships
    - Dilution events (offerings, 424B5, FWP)
    - General 8-K analysis

    Parameters
    ----------
    document_text : str
        Full or partial text of SEC filing
    title : str
        Filing title
    filing_type : str
        Type of filing (e.g., '8-K', '424B5')

    Returns
    -------
    dict
        Keywords and analysis:
        - keywords: list of str (e.g., ['fda', 'clinical', 'phase_3'])
        - sentiment: float (-1 to +1)
        - confidence: float (0 to 1)
        - summary: str (one-line summary)
        - material: bool (is this a material event?)
        - Additional fields depending on filing type
    """
    # Check if LLM is enabled
    if not os.getenv("FEATURE_SEC_LLM_KEYWORDS", "1") in ("1", "true", "yes", "on"):
        log.debug("sec_llm_keywords_disabled")
        return {}

    # Import hybrid LLM router and prompts
    try:
        from .llm_hybrid import query_hybrid_llm
        from .llm_prompts import KEYWORD_EXTRACTION_PROMPT, select_prompt_for_filing
    except ImportError as e:
        log.warning(f"llm_imports_not_available err={e}")
        return {}

    # For keyword extraction, use limited excerpt (5000 chars = ~1250 tokens)
    # For deep analysis, use more (up to 20000 chars = ~5000 tokens)
    use_deep_analysis = os.getenv("FEATURE_SEC_DEEP_ANALYSIS", "1") in (
        "1",
        "true",
        "yes",
        "on",
    )

    # --- PROMPT COMPRESSION INTEGRATION ---
    # Use intelligent compression instead of naive truncation
    from .config import get_settings

    settings = get_settings()
    use_compression = getattr(settings, "feature_prompt_compression", True)

    if use_compression and should_compress(document_text, threshold=2000):
        # Determine target token limit based on analysis depth
        max_tokens = 5000 if use_deep_analysis else 2000

        # Apply intelligent compression
        compression_result = compress_sec_filing(document_text, max_tokens=max_tokens)
        doc_excerpt = compression_result["compressed_text"]

        # Log compression metrics
        if compression_result["compression_ratio"] > 0:
            log.info(
                "sec_filing_compressed filing=%s original_tokens=%d compressed_tokens=%d "
                "ratio=%.1f%% sections=%s",
                filing_type,
                compression_result["original_tokens"],
                compression_result["compressed_tokens"],
                compression_result["compression_ratio"] * 100,
                ",".join(compression_result["sections_included"]),
            )
    else:
        # Fallback to existing truncation logic when compression is disabled
        if use_deep_analysis:
            doc_excerpt = (
                document_text[:20000] if len(document_text) > 20000 else document_text
            )
        else:
            doc_excerpt = (
                document_text[:5000] if len(document_text) > 5000 else document_text
            )

    # Select appropriate prompt based on filing content and type
    try:
        prompt_template, analysis_type = select_prompt_for_filing(
            doc_excerpt, filing_type
        )

        # For keyword extraction (basic mode), always use keyword extraction prompt
        if not use_deep_analysis:
            prompt = KEYWORD_EXTRACTION_PROMPT.format(
                filing_type=filing_type, title=title, document_text=doc_excerpt
            )
        else:
            prompt = prompt_template.format(document_text=doc_excerpt)

        log.debug(
            f"using_prompt_type={analysis_type} filing={filing_type} deep_analysis={use_deep_analysis}"  # noqa: E501
        )

    except Exception as e:
        log.warning(f"prompt_selection_failed filing={filing_type} err={e}")
        # Fallback to basic keyword extraction
        prompt = KEYWORD_EXTRACTION_PROMPT.format(
            filing_type=filing_type, title=title, document_text=doc_excerpt
        )
        analysis_type = "SECKeywordExtraction"

    try:
        # Query hybrid LLM (routes through Local → Gemini → Anthropic)
        response = await query_hybrid_llm(
            prompt, article_length=len(doc_excerpt), priority="normal"
        )

        if not response:
            log.warning(f"llm_no_response filing={filing_type}")
            return {}

        # Parse JSON response
        import json

        # Extract JSON from response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            response = json_match.group(0)

        analysis = json.loads(response)

        # Safe float conversion helper
        def safe_float(value, default=0.0):
            """Convert value to float, handling 'unknown', 'N/A', None, etc."""
            if value is None or value == "":
                return default
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                value_lower = value.lower().strip()
                if value_lower in ("unknown", "n/a", "na", "none", "null"):
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            return default

        # Normalize result (convert to keyword extraction format)
        result = {
            "keywords": list(analysis.get("keywords", analysis.get("catalysts", []))),
            "sentiment": safe_float(analysis.get("sentiment"), 0.0),
            "confidence": safe_float(analysis.get("confidence"), 0.5),
            "summary": str(analysis.get("summary", "")),
            "material": bool(
                analysis.get(
                    "material",
                    bool(analysis.get("keywords")) or bool(analysis.get("catalysts")),
                )
            ),
        }

        # Add additional fields if available
        if "risk_level" in analysis:
            result["risk_level"] = str(analysis["risk_level"])
        if "deal_size" in analysis or "deal_value_upfront" in analysis:
            result["deal_size"] = analysis.get("deal_size") or analysis.get(
                "deal_value_upfront"
            )
        if "dilution_pct" in analysis:
            result["dilution_pct"] = analysis.get("dilution_pct")

        # Add enhanced LLM output fields
        if "reasoning" in analysis:
            result["llm_reasoning"] = str(analysis["reasoning"])
        if "event_context" in analysis:
            result["event_context"] = str(analysis["event_context"])
        if "trading_thesis" in analysis:
            result["trading_thesis"] = str(analysis["trading_thesis"])
        if "expected_price_action" in analysis:
            result["expected_price_action"] = str(analysis["expected_price_action"])

        if result["keywords"]:
            # Enhanced logging with LLM reasoning
            log_msg = (
                f"sec_keywords_extracted filing={filing_type} analysis_type={analysis_type} "
                f"keywords={result['keywords']} material={result['material']}"
            )

            # Add reasoning to log if available
            if "llm_reasoning" in result:
                log_msg += f" reasoning=\"{result['llm_reasoning'][:100]}...\""

            # Add event context for delisting scenarios
            if "event_context" in result and result["event_context"] != "null":
                log_msg += f" event_context={result['event_context']}"

            # Add expected price action
            if "expected_price_action" in result:
                log_msg += f" expected_action={result['expected_price_action']}"

            log.info(log_msg)
        else:
            log.debug(f"sec_no_keywords_found filing={filing_type}")

        return result

    except json.JSONDecodeError as e:
        log.warning(
            f"llm_json_parse_failed filing={filing_type} err={e} response={response[:200]}"
        )
        return {}
    except Exception as e:
        log.error(f"keyword_extraction_failed filing={filing_type} err={e}")
        return {}


# ============================================================================
# WAVE 4: Batch SEC LLM Processing
# ============================================================================


async def batch_extract_keywords_from_documents(
    sec_filings: list[dict],
) -> dict[str, dict]:
    """
    Batch process multiple SEC filings in parallel using asyncio.gather().

    Agent 2: Integrated with SEC LLM cache to avoid duplicate analysis.

    This eliminates the serial processing bottleneck from calling extract_keywords_from_document_sync()
    in a loop, which creates a new event loop for each filing.

    Parameters
    ----------
    sec_filings : list of dict
        List of SEC filing items, each containing:
        - 'item_id': Unique identifier for caching results
        - 'document_text': Full or partial text of SEC filing
        - 'title': Filing title
        - 'filing_type': Type of filing (e.g., '8-K', '424B5')
        - 'ticker': Stock ticker (optional, for cache key)
        - 'filing_id': Accession number or unique ID (optional, for cache key)

    Returns
    -------
    dict
        Dictionary mapping item_id -> extraction results (keywords, sentiment, etc.)

    Example
    -------
    >>> filings = [
    ...     {
    ...         'item_id': 'AAPL_8k_123',
    ...         'document_text': '...',
    ...         'title': 'Form 8-K - Apple Inc.',
    ...         'filing_type': '8-K',
    ...         'ticker': 'AAPL',
    ...         'filing_id': '0001234567-25-000123'
    ...     },
    ...     # ... more filings
    ... ]
    >>> results = await batch_extract_keywords_from_documents(filings)
    >>> print(results['AAPL_8k_123']['keywords'])
    ['earnings', 'revenue_beat']
    """
    if not sec_filings:
        return {}

    import asyncio
    import hashlib
    import time

    # Agent 2: Initialize SEC LLM cache
    from .sec_llm_cache import get_sec_llm_cache
    cache = get_sec_llm_cache()

    # Separate filings into cached and uncached
    tasks = []
    item_ids = []
    results_dict = {}
    cache_hits = 0

    for filing in sec_filings:
        item_id = filing.get("item_id")
        doc_text = filing.get("document_text", "")
        title = filing.get("title", "")
        filing_type = filing.get("filing_type", "8-K")
        ticker = filing.get("ticker", "UNKNOWN")
        filing_id = filing.get("filing_id", item_id)

        if not item_id or not doc_text:
            log.warning(
                "batch_extract_invalid_filing item_id=%s doc_len=%d",
                item_id,
                len(doc_text) if doc_text else 0,
            )
            continue

        # Agent 2: Check cache first
        doc_hash = hashlib.md5(doc_text[:1000].encode()).hexdigest()[:8]
        cached_result = cache.get_cached_sec_analysis(
            filing_id=filing_id,
            ticker=ticker,
            filing_type=filing_type,
            document_hash=doc_hash,
        )

        if cached_result is not None:
            # Cache hit - use cached result
            results_dict[item_id] = cached_result
            cache_hits += 1
            log.debug(
                "sec_llm_cache_hit_batch item_id=%s ticker=%s filing_type=%s",
                item_id,
                ticker,
                filing_type,
            )
        else:
            # Cache miss - create async task for LLM analysis
            task = extract_keywords_from_document(
                document_text=doc_text, title=title, filing_type=filing_type
            )
            tasks.append((task, item_id, filing_id, ticker, filing_type, doc_hash))
            item_ids.append(item_id)

    # Log cache performance
    if cache_hits > 0:
        log.info(
            "sec_llm_batch_cache_hits count=%d/%d (%.1f%% cached)",
            cache_hits,
            len(sec_filings),
            (cache_hits / len(sec_filings)) * 100,
        )

    if not tasks:
        # All results from cache
        return results_dict

    # Process uncached filings in parallel
    log.info("batch_extract_starting count=%d (cache_hits=%d)", len(tasks), cache_hits)
    start_time = time.time()

    try:
        # Extract just the async tasks for gather()
        async_tasks = [t[0] for t in tasks]
        results_list = await asyncio.gather(*async_tasks, return_exceptions=True)

        # Build results dictionary and cache new results
        success_count = 0
        error_count = 0

        for (_, item_id, filing_id, ticker, filing_type, doc_hash), result in zip(tasks, results_list):
            if isinstance(result, Exception):
                log.warning("batch_extract_failed item_id=%s err=%s", item_id, str(result))
                error_count += 1
                results_dict[item_id] = {}  # Empty result on error
            elif result and isinstance(result, dict):
                results_dict[item_id] = result
                success_count += 1

                # Agent 2: Cache the result
                cache.cache_sec_analysis(
                    filing_id=filing_id,
                    ticker=ticker,
                    filing_type=filing_type,
                    analysis_result=result,
                    document_hash=doc_hash,
                )
            else:
                log.debug("batch_extract_no_result item_id=%s", item_id)
                results_dict[item_id] = {}

        elapsed = time.time() - start_time
        log.info(
            "batch_extract_complete total=%d cached=%d analyzed=%d success=%d errors=%d elapsed=%.2fs avg=%.2fs",
            len(sec_filings),
            cache_hits,
            len(tasks),
            success_count,
            error_count,
            elapsed,
            elapsed / len(tasks) if tasks else 0,
        )

        return results_dict

    except Exception as e:
        log.error("batch_extract_gather_failed err=%s", str(e), exc_info=True)
        return {}
