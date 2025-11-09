"""Multi-pass LLM chain for SEC filing analysis.

This module implements a 4-stage LLM processing pipeline that transforms raw
SEC filing text into structured, actionable intelligence:

Stage 1: EXTRACTION - Key facts, dates, parties, dollar amounts
Stage 2: SUMMARY - Concise 100-150 word digest
Stage 3: KEYWORDS - Catalyst tags (merger, FDA approval, offering, etc.)
Stage 4: SENTIMENT - Market impact score with justification

Each stage builds on the previous, creating a progressive refinement of
understanding. The pipeline uses the existing llm_hybrid router for
Gemini→Claude fallback and includes exponential backoff retry logic.

References:
- Multi-pass prompting: https://arxiv.org/abs/2203.11171
- Chain-of-thought: https://arxiv.org/abs/2201.11903
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .llm_hybrid import query_hybrid_llm
    from .logging_utils import get_logger
    from .numeric_extractor import NumericMetrics
    from .xbrl_parser import XBRLFinancials
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("llm_chain")

    async def query_hybrid_llm(*args, **kwargs):
        raise NotImplementedError("llm_hybrid not available")


log = get_logger("llm_chain")


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ExtractionOutput:
    """Stage 1: Extracted key facts."""

    key_facts: list[str]  # Bullet points of key information
    parties: list[str]  # Companies, people involved
    dates: list[str]  # Important dates mentioned
    dollar_amounts: list[str]  # Financial figures
    raw_response: str  # Raw LLM output


@dataclass
class SummaryOutput:
    """Stage 2: Concise summary."""

    summary: str  # 100-150 word digest
    raw_response: str


@dataclass
class KeywordOutput:
    """Stage 3: Keyword tags."""

    keywords: list[str]  # Catalyst tags
    raw_response: str


@dataclass
class SentimentOutput:
    """Stage 4: Sentiment analysis."""

    score: float  # -1.0 (very bearish) to +1.0 (very bullish)
    justification: str  # 1-sentence explanation
    confidence: float  # 0.0 to 1.0
    raw_response: str


@dataclass
class LLMChainOutput:
    """Complete output from all 4 stages."""

    extraction: ExtractionOutput
    summary: SummaryOutput
    keywords: KeywordOutput
    sentiment: SentimentOutput
    total_time_sec: float
    stages_completed: int


# ============================================================================
# Prompt Templates
# ============================================================================

PROMPT_STAGE1_EXTRACTION = """You are analyzing an SEC filing. Extract the key information.

FILING TEXT:
{filing_text}

NUMERIC METRICS (already extracted):
{numeric_metrics}

XBRL FINANCIALS (if available):
{xbrl_financials}

TASK: Extract and list:
1. KEY FACTS (3-7 bullet points of the most important information)
2. PARTIES (companies, executives, entities involved)
3. DATES (important dates mentioned)
4. DOLLAR AMOUNTS (financial figures like "$150M acquisition")

Format your response as JSON:
{{
  "key_facts": ["fact 1", "fact 2", ...],
  "parties": ["party 1", "party 2", ...],
  "dates": ["date 1", "date 2", ...],
  "dollar_amounts": ["$150M", "$2.50/share", ...]
}}

Be concise and factual. Focus on market-moving information."""

PROMPT_STAGE2_SUMMARY = """You are creating a brief summary of an SEC filing for traders.

EXTRACTED KEY FACTS:
{key_facts}

TASK: Write a 100-150 word summary that:
- Starts with the company name and filing type
- Explains what happened and why it matters
- Includes key numbers (revenue, deals, etc.)
- Ends with potential market impact

Write in active voice. Be direct and factual. This will be shown to traders."""

PROMPT_STAGE3_KEYWORDS = """You are tagging an SEC filing with catalyst keywords.

SUMMARY:
{summary}

KEY FACTS:
{key_facts}

AVAILABLE KEYWORDS (choose 1-5 that apply):
- merger, acquisition, takeover
- earnings, revenue_beat, revenue_miss, eps_beat, eps_miss
- offering, dilution, warrant_exercise, shelf_registration
- fda_approval, clinical_trial, drug_approval
- partnership, collaboration, contract, deal
- management_change, ceo_departure, board_change
- bankruptcy, delisting, going_concern
- guidance_raise, guidance_lower
- buyback, dividend
- restructuring, layoffs, cost_cutting
- expansion, new_market, international
- product_launch, new_product
- lawsuit, settlement, regulatory_action

TASK: Return ONLY a JSON list of keywords that apply:
{{"keywords": ["keyword1", "keyword2", ...]}}

Be selective - only tag clear, relevant catalysts. Maximum 5 keywords."""

PROMPT_STAGE4_SENTIMENT = """You are scoring the market impact of an SEC filing.

SUMMARY:
{summary}

KEY FACTS:
{key_facts}

KEYWORDS:
{keywords}

TASK: Provide a sentiment analysis with:
1. SCORE: -1.0 (very bearish) to +1.0 (very bullish)
2. JUSTIFICATION: One sentence explaining why
3. CONFIDENCE: 0.0 (uncertain) to 1.0 (very confident)

Consider:
- Revenue growth = bullish
- Dilution/offerings = bearish
- FDA approval = bullish
- Management departure = bearish
- Positive guidance = bullish
- Going concern warnings = very bearish

Format as JSON:
{{
  "score": 0.5,
  "justification": "Explain your reasoning here",
  "confidence": 0.8
}}"""


# ============================================================================
# LLM Chain Execution
# ============================================================================


async def run_llm_chain(
    filing_text: str,
    numeric_metrics: Optional[NumericMetrics] = None,
    xbrl_financials: Optional[XBRLFinancials] = None,
    max_retries: int = 3,
) -> LLMChainOutput:
    """Execute the full 4-stage LLM chain.

    Parameters
    ----------
    filing_text : str
        Raw SEC filing text (first 5000 chars recommended)
    numeric_metrics : NumericMetrics, optional
        Pre-extracted numeric data from Wave 1B
    xbrl_financials : XBRLFinancials, optional
        Pre-extracted XBRL data from Wave 1C
    max_retries : int
        Maximum retry attempts per stage

    Returns
    -------
    LLMChainOutput
        Complete analysis from all 4 stages

    Examples
    --------
    >>> text = "FORM 8-K Item 2.02 Results of Operations..."
    >>> metrics = extract_all_metrics(text)
    >>> output = await run_llm_chain(text, numeric_metrics=metrics)
    >>> print(output.summary.summary)
    >>> print(output.sentiment.score)
    """
    start_time = time.time()
    stages_completed = 0

    log.info("Starting 4-stage LLM chain")

    # Stage 1: Extraction
    try:
        extraction = await _stage1_extraction(
            filing_text,
            numeric_metrics,
            xbrl_financials,
            max_retries,
        )
        stages_completed += 1
    except Exception as e:
        log.error(f"Stage 1 (extraction) failed: {e}")
        raise

    # Stage 2: Summary
    try:
        summary = await _stage2_summary(extraction, max_retries)
        stages_completed += 1
    except Exception as e:
        log.error(f"Stage 2 (summary) failed: {e}")
        raise

    # Stage 3: Keywords
    try:
        keywords = await _stage3_keywords(extraction, summary, max_retries)
        stages_completed += 1
    except Exception as e:
        log.error(f"Stage 3 (keywords) failed: {e}")
        raise

    # Stage 4: Sentiment
    try:
        sentiment = await _stage4_sentiment(extraction, summary, keywords, max_retries)
        stages_completed += 1
    except Exception as e:
        log.error(f"Stage 4 (sentiment) failed: {e}")
        raise

    total_time = time.time() - start_time
    log.info(f"LLM chain completed in {total_time:.1f}s ({stages_completed}/4 stages)")

    return LLMChainOutput(
        extraction=extraction,
        summary=summary,
        keywords=keywords,
        sentiment=sentiment,
        total_time_sec=total_time,
        stages_completed=stages_completed,
    )


async def _stage1_extraction(
    filing_text: str,
    numeric_metrics: Optional[NumericMetrics],
    xbrl_financials: Optional[XBRLFinancials],
    max_retries: int,
) -> ExtractionOutput:
    """Stage 1: Extract key facts, parties, dates, amounts."""
    log.debug("Running Stage 1: Extraction")

    # Prepare context
    numeric_str = numeric_metrics.summary() if numeric_metrics else "None extracted"
    xbrl_str = xbrl_financials.summary() if xbrl_financials else "None available"

    # Truncate filing text if too long (save tokens)
    filing_truncated = filing_text[:5000] if len(filing_text) > 5000 else filing_text

    prompt = PROMPT_STAGE1_EXTRACTION.format(
        filing_text=filing_truncated,
        numeric_metrics=numeric_str,
        xbrl_financials=xbrl_str,
    )

    # Call LLM with retry
    response = await _call_llm_with_retry(prompt, max_retries, stage="extraction")

    # Parse JSON response
    try:
        data = json.loads(response)
        return ExtractionOutput(
            key_facts=data.get("key_facts", []),
            parties=data.get("parties", []),
            dates=data.get("dates", []),
            dollar_amounts=data.get("dollar_amounts", []),
            raw_response=response,
        )
    except json.JSONDecodeError:
        log.warning("Stage 1 response not valid JSON, using fallback parsing")
        # Fallback: extract lists manually
        return ExtractionOutput(
            key_facts=["Failed to parse structured data"],
            parties=[],
            dates=[],
            dollar_amounts=[],
            raw_response=response,
        )


async def _stage2_summary(extraction: ExtractionOutput, max_retries: int) -> SummaryOutput:
    """Stage 2: Generate concise summary."""
    log.debug("Running Stage 2: Summary")

    key_facts_str = "\n".join(f"- {fact}" for fact in extraction.key_facts)

    prompt = PROMPT_STAGE2_SUMMARY.format(key_facts=key_facts_str)

    response = await _call_llm_with_retry(prompt, max_retries, stage="summary")

    return SummaryOutput(summary=response.strip(), raw_response=response)


async def _stage3_keywords(
    extraction: ExtractionOutput,
    summary: SummaryOutput,
    max_retries: int,
) -> KeywordOutput:
    """Stage 3: Generate keyword tags."""
    log.debug("Running Stage 3: Keywords")

    key_facts_str = "\n".join(f"- {fact}" for fact in extraction.key_facts)

    prompt = PROMPT_STAGE3_KEYWORDS.format(
        summary=summary.summary,
        key_facts=key_facts_str,
    )

    response = await _call_llm_with_retry(prompt, max_retries, stage="keywords")

    # Parse JSON response
    try:
        data = json.loads(response)
        keywords = data.get("keywords", [])
    except json.JSONDecodeError:
        log.warning("Stage 3 response not valid JSON, extracting keywords manually")
        # Fallback: look for words in response
        keywords = []

    return KeywordOutput(keywords=keywords, raw_response=response)


async def _stage4_sentiment(
    extraction: ExtractionOutput,
    summary: SummaryOutput,
    keywords: KeywordOutput,
    max_retries: int,
) -> SentimentOutput:
    """Stage 4: Sentiment analysis with justification."""
    log.debug("Running Stage 4: Sentiment")

    key_facts_str = "\n".join(f"- {fact}" for fact in extraction.key_facts)
    keywords_str = ", ".join(keywords.keywords)

    prompt = PROMPT_STAGE4_SENTIMENT.format(
        summary=summary.summary,
        key_facts=key_facts_str,
        keywords=keywords_str,
    )

    response = await _call_llm_with_retry(prompt, max_retries, stage="sentiment")

    # Parse JSON response
    try:
        data = json.loads(response)
        score = float(data.get("score", 0.0))
        justification = data.get("justification", "No justification provided")
        confidence = float(data.get("confidence", 0.5))

        # Clamp values
        score = max(-1.0, min(1.0, score))
        confidence = max(0.0, min(1.0, confidence))

    except (json.JSONDecodeError, ValueError, TypeError):
        log.warning("Stage 4 response not valid JSON, using neutral sentiment")
        score = 0.0
        justification = "Failed to parse sentiment"
        confidence = 0.0

    return SentimentOutput(
        score=score,
        justification=justification,
        confidence=confidence,
        raw_response=response,
    )


async def _call_llm_with_retry(prompt: str, max_retries: int, stage: str) -> str:
    """Call LLM via llm_hybrid with exponential backoff retry.

    Parameters
    ----------
    prompt : str
        Prompt to send to LLM
    max_retries : int
        Maximum number of retry attempts
    stage : str
        Stage name for logging

    Returns
    -------
    str
        LLM response text
    """
    for attempt in range(max_retries):
        try:
            # Call existing LLM router (async)
            response = await query_hybrid_llm(prompt, article_length=len(prompt), priority="normal")

            if response and len(response.strip()) > 10:
                log.debug(f"Stage {stage} completed on attempt {attempt + 1}")
                return response

            log.warning(f"Stage {stage} returned empty response, retrying...")

        except Exception as e:
            log.warning(f"Stage {stage} attempt {attempt + 1} failed: {e}")

            if attempt < max_retries - 1:
                # Exponential backoff: 2^attempt seconds
                sleep_time = 2**attempt
                log.info(f"Retrying in {sleep_time}s...")
                await asyncio.sleep(sleep_time)
            else:
                raise RuntimeError(f"Stage {stage} failed after {max_retries} attempts")

    raise RuntimeError(f"Stage {stage} failed: no valid response")


# ============================================================================
# Quick Access Functions
# ============================================================================


async def get_filing_summary(filing_text: str, numeric_metrics: Optional[NumericMetrics] = None) -> str:
    """Quick function to get just the summary (Stages 1+2 only).

    Parameters
    ----------
    filing_text : str
        SEC filing text
    numeric_metrics : NumericMetrics, optional
        Pre-extracted metrics

    Returns
    -------
    str
        100-150 word summary
    """
    extraction = await _stage1_extraction(filing_text, numeric_metrics, None, max_retries=3)
    summary = await _stage2_summary(extraction, max_retries=3)
    return summary.summary


async def get_filing_sentiment(filing_text: str) -> tuple[float, str]:
    """Quick function to get just sentiment score and justification.

    Returns
    -------
    tuple[float, str]
        (sentiment_score, justification)
    """
    output = await run_llm_chain(filing_text, max_retries=2)
    return output.sentiment.score, output.sentiment.justification
