"""
SEC Integration Layer
=====================

Integration layer between the existing SEC monitoring infrastructure and the
new unified LLM Service Hub + SEC Processor.

This module provides backward-compatible functions that can replace the old
sec_llm_analyzer while maintaining the same interface.

Features:
- Pre-filter strategy: Apply cost/liquidity filters BEFORE LLM digestion
- Feature flag support for gradual rollout
- Backward-compatible with existing runner.py code
- Batch processing support
- Fallback to old analyzer if new processor fails
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger

log = get_logger("sec_integration")


def should_use_new_processor() -> bool:
    """
    Check if new SEC processor should be used.

    Returns:
        True if FEATURE_UNIFIED_LLM_SERVICE is enabled
    """
    return os.getenv("FEATURE_UNIFIED_LLM_SERVICE", "0") in ("1", "true", "yes", "on")


async def batch_extract_keywords_from_documents(
    filings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Extract keywords from SEC filings using unified processor or legacy analyzer.

    This function maintains backward compatibility with the existing runner.py code
    while enabling the new unified processor when the feature flag is enabled.

    Args:
        filings: List of filing dicts with keys:
            - item_id: Filing identifier
            - document_text: Filing content/summary
            - title: Filing title
            - filing_type: Type of filing (8-K, 424B5, etc.)

    Returns:
        Dict mapping item_id -> extracted keywords/analysis
    """
    if should_use_new_processor():
        log.info("using_new_unified_processor count=%d", len(filings))
        try:
            return await batch_process_with_new_processor(filings)
        except Exception as e:
            log.error(
                "new_processor_failed err=%s falling_back_to_legacy",
                str(e),
                exc_info=True
            )
            # Fallback to legacy analyzer
            return await batch_process_with_legacy_analyzer(filings)
    else:
        log.info("using_legacy_analyzer count=%d", len(filings))
        return await batch_process_with_legacy_analyzer(filings)


async def batch_process_with_new_processor(
    filings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process SEC filings using the new unified processor.

    Flow:
    1. Pre-filter filings (cost/liquidity checks)
    2. For qualified filings, call SECProcessor
    3. Extract keywords from LLM analysis
    4. Return in legacy format for compatibility

    Args:
        filings: List of filing dicts

    Returns:
        Dict mapping item_id -> keywords (compatible with legacy format)
    """
    from .processors import SECProcessor
    from .sec_prefilter import should_process_filing, init_prefilter

    # Initialize pre-filter resources
    init_prefilter()

    # Initialize processor
    processor = SECProcessor()

    # Results dict (compatible with legacy format)
    results = {}

    # Track pre-filter statistics
    prefilter_stats = {
        "total": 0,
        "passed": 0,
        "rejected_no_ticker": 0,
        "rejected_otc": 0,
        "rejected_unit_warrant": 0,
        "rejected_price": 0,
        "rejected_volume": 0,
    }

    # Process each filing
    for filing in filings:
        item_id = filing.get("item_id", "")
        filing_type = filing.get("filing_type", "8-K")
        title = filing.get("title", "")
        document_text = filing.get("document_text", "")
        ticker_hint = filing.get("ticker")  # Get ticker from filing if available

        prefilter_stats["total"] += 1

        # Extract 8-K item number if present
        item_number = extract_8k_item_number(title, document_text)

        # PHASE 4: Pre-filter check (skip expensive LLM calls for filtered items)
        # Pass ticker hint if available to skip extraction step
        should_process, ticker, reject_reason = should_process_filing(filing, ticker=ticker_hint)

        if not should_process:
            # Filing rejected by pre-filter - skip LLM call (COST SAVINGS!)
            log.info(
                "filing_prefilter_rejected item_id=%s reason=%s ticker=%s",
                item_id[:50] if item_id else "none",
                reject_reason,
                ticker or "unknown"
            )

            # Track rejection reason
            if "no_ticker" in reject_reason:
                prefilter_stats["rejected_no_ticker"] += 1
            elif "otc" in reject_reason:
                prefilter_stats["rejected_otc"] += 1
            elif "unit_warrant" in reject_reason:
                prefilter_stats["rejected_unit_warrant"] += 1
            elif "price" in reject_reason:
                prefilter_stats["rejected_price"] += 1
            elif "volume" in reject_reason:
                prefilter_stats["rejected_volume"] += 1

            # Return empty result (no LLM call = no cost)
            results[item_id] = {
                "keywords": [],
                "sentiment": "neutral",
                "prefilter_rejected": True,
                "reject_reason": reject_reason
            }
            continue

        # Filing passed pre-filter - proceed with LLM analysis
        prefilter_stats["passed"] += 1

        try:
            log.debug(
                "processing_filing item_id=%s filing_type=%s item=%s ticker=%s",
                item_id[:50] if item_id else "none",
                filing_type,
                item_number or "unknown",
                ticker or "unknown"
            )

            # Call unified SEC processor
            result = await processor.process_8k(
                filing_url=item_id,  # Use item_id as filing URL
                ticker=ticker or "",  # Use pre-filtered ticker
                item=item_number or "8.01",  # Default to "Other Events"
                title=title,
                summary=document_text
            )

            # Extract keywords from analysis result
            keywords = extract_keywords_from_analysis_result(result)

            # Store in legacy format
            results[item_id] = {
                "keywords": keywords,
                "sentiment": result.sentiment,
                "confidence": result.sentiment_confidence,
                "summary": result.llm_summary,
                "material_events": len(result.material_events),
                "financial_metrics": len(result.financial_metrics),
                "llm_provider": result.llm_provider,
                "llm_cost_usd": result.llm_cost_usd,
            }

            log.info(
                "filing_processed item_id=%s keywords=%d sentiment=%s cost=$%.6f",
                item_id[:50] if item_id else "none",
                len(keywords),
                result.sentiment,
                result.llm_cost_usd
            )

        except Exception as e:
            log.error(
                "filing_processing_failed item_id=%s err=%s",
                item_id[:50] if item_id else "none",
                str(e),
                exc_info=True
            )
            # Return empty result on error
            results[item_id] = {"keywords": [], "sentiment": "neutral", "error": str(e)}

    # Log pre-filter statistics
    log.info(
        "batch_processing_complete processed=%d prefilter_total=%d prefilter_passed=%d "
        "prefilter_rejected=%d (no_ticker=%d otc=%d unit_warrant=%d price=%d volume=%d) "
        "cost_savings_pct=%.1f%%",
        len(results),
        prefilter_stats["total"],
        prefilter_stats["passed"],
        prefilter_stats["total"] - prefilter_stats["passed"],
        prefilter_stats["rejected_no_ticker"],
        prefilter_stats["rejected_otc"],
        prefilter_stats["rejected_unit_warrant"],
        prefilter_stats["rejected_price"],
        prefilter_stats["rejected_volume"],
        100.0 * (prefilter_stats["total"] - prefilter_stats["passed"]) / prefilter_stats["total"]
        if prefilter_stats["total"] > 0 else 0.0
    )

    return results


async def batch_process_with_legacy_analyzer(
    filings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process SEC filings using the legacy analyzer.

    Fallback path for when new processor is disabled or fails.

    Args:
        filings: List of filing dicts

    Returns:
        Dict mapping item_id -> keywords
    """
    try:
        from .sec_llm_analyzer import batch_extract_keywords_from_documents as legacy_batch

        # Call legacy analyzer
        return await legacy_batch(filings)

    except Exception as e:
        log.error("legacy_analyzer_failed err=%s", str(e), exc_info=True)
        # Return empty results to prevent crash
        return {filing.get("item_id", ""): {"keywords": []} for filing in filings}


def extract_8k_item_number(title: str, document_text: str) -> Optional[str]:
    """
    Extract 8-K item number from title or document text.

    Args:
        title: Filing title
        document_text: Filing content

    Returns:
        Item number (e.g., "1.01", "8.01") or None if not found
    """
    import re

    # Combine title and first part of document
    text = f"{title} {document_text[:500]}"

    # Pattern to match "Item 1.01", "ITEM 2.02", etc.
    patterns = [
        r"Item\s+(\d\.\d{2})",
        r"ITEM\s+(\d\.\d{2})",
        r"item\s+(\d\.\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


def extract_keywords_from_analysis_result(result) -> List[str]:
    """
    Extract keywords from SECAnalysisResult for backward compatibility.

    Converts the structured analysis result into a simple list of keywords
    that the legacy system expects.

    Args:
        result: SECAnalysisResult from processor

    Returns:
        List of keyword strings
    """
    keywords = []

    # Add keywords from material events
    for event in result.material_events:
        event_type = event.event_type.lower()
        keywords.append(event_type)

        # Map event types to legacy keywords
        if event_type in ["m&a", "acquisition", "merger"]:
            keywords.extend(["acquisition", "merger", "m&a"])
        elif event_type in ["partnership", "agreement"]:
            keywords.extend(["partnership", "agreement", "collaboration"])
        elif event_type in ["fda", "approval"]:
            keywords.extend(["fda", "approval", "drug approval"])
        elif event_type in ["bankruptcy"]:
            keywords.extend(["bankruptcy", "chapter 11"])
        elif event_type in ["leadership", "ceo", "cfo"]:
            keywords.extend(["leadership change", "executive departure"])

    # Add keywords from financial metrics
    for metric in result.financial_metrics:
        metric_name = metric.metric_name.lower()
        if "deal" in metric_name or "acquisition" in metric_name:
            keywords.append("deal")
        if "dilution" in metric_name:
            keywords.append("dilution")
        if "offering" in metric_name:
            keywords.append("offering")
        if "revenue" in metric_name or "earnings" in metric_name:
            keywords.append("earnings")

    # Add sentiment as keyword
    if result.sentiment != "neutral":
        keywords.append(result.sentiment)

    # Deduplicate while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            unique_keywords.append(kw)

    return unique_keywords


# Maintain backward compatibility with old function names
async def extract_keywords_from_document(
    document_text: str,
    filing_type: str = "8-K",
    timeout: float = 20.0
) -> List[str]:
    """
    Legacy function signature for backward compatibility.

    Extract keywords from a single SEC document.

    Args:
        document_text: Document content
        filing_type: Type of filing
        timeout: Timeout in seconds

    Returns:
        List of keywords
    """
    # Build filing dict for batch processor
    filings = [{
        "item_id": "single_filing",
        "document_text": document_text,
        "title": "",
        "filing_type": filing_type
    }]

    # Process batch
    results = await batch_extract_keywords_from_documents(filings)

    # Extract keywords from result
    result = results.get("single_filing", {})
    return result.get("keywords", [])


# Synchronous wrapper for backward compatibility
def extract_keywords_from_document_sync(
    document_text: str,
    filing_type: str = "8-K",
    timeout: float = 20.0
) -> List[str]:
    """
    Synchronous wrapper for extract_keywords_from_document.

    Used by historical_bootstrapper.py which expects sync interface.

    Args:
        document_text: Document content
        filing_type: Type of filing
        timeout: Timeout in seconds

    Returns:
        List of keywords
    """
    try:
        return asyncio.run(extract_keywords_from_document(
            document_text,
            filing_type,
            timeout
        ))
    except Exception as e:
        log.error("sync_extraction_failed err=%s", str(e))
        return []
