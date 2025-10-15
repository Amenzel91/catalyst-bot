"""
End-to-End Test of SEC Document Extraction and LLM Analysis
=============================================================

This script tests the complete pipeline:
1. Fetch actual SEC 8-K document using enhanced fetcher
2. Extract full document text content
3. Use Gemini LLM with specialized prompts to analyze
4. Display keywords, sentiment, and analysis results

Tests both basic keyword extraction and deep analysis modes.
"""

import asyncio
import os
from pathlib import Path

# Ensure .env is loaded
from dotenv import load_dotenv
load_dotenv()

from src.catalyst_bot.sec_document_fetcher import fetch_sec_document_text
from src.catalyst_bot.sec_llm_analyzer import extract_keywords_from_document


async def test_end_to_end_sec_analysis():
    """Test complete SEC document extraction and LLM analysis pipeline."""

    print("=" * 80)
    print("END-TO-END TEST: SEC Document Extraction + LLM Analysis")
    print("=" * 80)
    print()

    # Use a real SEC 8-K link from rejected_items.jsonl
    # American Airlines 8-K: Item 1.01 Material Agreement
    test_link = "https://www.sec.gov/Archives/edgar/data/6201/000119312524249922/0001193125-24-249922-index.htm"
    test_title = "8-K - American Airlines Group Inc. (0000006201)"
    test_filing_type = "8-K"
    test_accession = "0001193125-24-249922"

    print(f"Test Filing: {test_title}")
    print(f"Link: {test_link}")
    print(f"Accession: {test_accession}")
    print()
    print("-" * 80)
    print()

    # STEP 1: Fetch actual SEC document
    print("[STEP 1] Fetching SEC document using enhanced fetcher...")
    print("          (Uses Submissions API -> Index parsing -> Original link)")
    print()

    doc_text = fetch_sec_document_text(test_link)

    if not doc_text:
        print("[FAILED] Document fetcher returned 0 characters")
        print("Cannot proceed with LLM analysis")
        return

    print(f"[SUCCESS] Document fetched: {len(doc_text)} characters")
    print()
    print("First 500 characters:")
    print("-" * 80)
    print(doc_text[:500])
    print("-" * 80)
    print()

    # STEP 2: Test with BASIC keyword extraction mode
    print("[STEP 2] Testing BASIC keyword extraction (5K char limit)...")
    print()

    # Temporarily set basic mode
    os.environ["FEATURE_SEC_DEEP_ANALYSIS"] = "0"

    try:
        basic_result = await extract_keywords_from_document(
            document_text=doc_text,
            title=test_title,
            filing_type=test_filing_type
        )

        if basic_result:
            print("[SUCCESS] Basic Analysis Complete!")
            print("=" * 80)
            print()
            print(f"Keywords: {basic_result.get('keywords', [])}")
            print(f"Sentiment: {basic_result.get('sentiment', 0.0):.2f}")
            print(f"Confidence: {basic_result.get('confidence', 0.0):.2f}")
            print(f"Material: {basic_result.get('material', False)}")
            print(f"Summary: {basic_result.get('summary', 'N/A')}")
            print()
        else:
            print("[WARNING] Basic analysis returned empty result")
            print()

    except Exception as e:
        print(f"[ERROR] Basic analysis failed: {e}")
        import traceback
        traceback.print_exc()
        print()

    # STEP 3: Test with DEEP analysis mode (specialized prompts)
    print("[STEP 3] Testing DEEP analysis (20K char limit, specialized prompts)...")
    print()

    # Enable deep analysis mode
    os.environ["FEATURE_SEC_DEEP_ANALYSIS"] = "1"

    try:
        deep_result = await extract_keywords_from_document(
            document_text=doc_text,
            title=test_title,
            filing_type=test_filing_type
        )

        if deep_result:
            print("[SUCCESS] Deep Analysis Complete!")
            print("=" * 80)
            print()
            print(f"Keywords: {deep_result.get('keywords', [])}")
            print(f"Sentiment: {deep_result.get('sentiment', 0.0):.2f}")
            print(f"Confidence: {deep_result.get('confidence', 0.0):.2f}")
            print(f"Material: {deep_result.get('material', False)}")
            print(f"Summary: {deep_result.get('summary', 'N/A')}")
            print()

            # Show additional fields if available
            if 'risk_level' in deep_result:
                print(f"Risk Level: {deep_result['risk_level']}")
            if 'deal_size' in deep_result:
                print(f"Deal Size: {deep_result['deal_size']}")
            if 'dilution_pct' in deep_result:
                print(f"Dilution: {deep_result['dilution_pct']}%")
            print()

            if deep_result.get('keywords'):
                print("[SUCCESS] LLM successfully extracted keywords from actual SEC filing!")
                print()
                print("Keywords for classification:")
                for kw in deep_result.get('keywords', []):
                    print(f"  - {kw}")
            else:
                print("[INFO] No material keywords found (may be routine filing)")
        else:
            print("[WARNING] Deep analysis returned empty result")
            print()

    except Exception as e:
        print(f"[ERROR] Deep analysis failed: {e}")
        import traceback
        traceback.print_exc()
        print()

    # STEP 4: Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    print(f"Document Fetched: {len(doc_text)} chars")
    print(f"Basic Analysis: {'PASS' if basic_result and basic_result.get('keywords') else 'FAIL'}")
    print(f"Deep Analysis: {'PASS' if deep_result and deep_result.get('keywords') else 'FAIL'}")
    print()

    if deep_result and deep_result.get('keywords'):
        print("[SUCCESS] End-to-end pipeline working correctly!")
        print("Ready for historical bootstrap and production deployment.")
    else:
        print("[WARNING] Pipeline needs debugging")
        print("Check:")
        print("  1. GEMINI_API_KEY is set correctly in .env")
        print("  2. Gemini API has quota remaining")
        print("  3. Document content is being fetched correctly")

    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_end_to_end_sec_analysis())
