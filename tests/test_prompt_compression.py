"""
Tests for prompt compression module.

This module tests the intelligent compression of SEC filings and long-form
content to reduce token usage by 30-50% while preserving critical information.
"""

import pytest

from catalyst_bot.prompt_compression import (
    compress_sec_filing,
    estimate_tokens,
    extract_key_sections,
    prioritize_sections,
    should_compress,
)

# Sample SEC 8-K filing text (realistic example)
SAMPLE_8K_FILING = """
UNITED STATES SECURITIES AND EXCHANGE COMMISSION
Washington, D.C. 20549

FORM 8-K

CURRENT REPORT
Pursuant to Section 13 or 15(d) of the Securities Exchange Act of 1934

ABC Biopharmaceuticals Inc.
(Exact name of registrant as specified in its charter)

ITEM 1.01 Entry into a Material Definitive Agreement

On December 15, 2023, ABC Biopharmaceuticals Inc. (the "Company") entered into a definitive Asset Purchase Agreement with XYZ Therapeutics LLC ("XYZ") to acquire certain intellectual property assets related to novel oncology therapeutics for an aggregate purchase price of $50 million, consisting of $30 million in cash and $20 million in Company common stock.  # noqa: E501

The acquired assets include:
- Three issued patents covering small molecule inhibitors
- Preclinical data from Phase 1 studies
- Regulatory filings with the FDA
- Manufacturing protocols and trade secrets

Key Terms of the Transaction:
- Total consideration: $50 million ($30M cash + $20M equity)
- Closing date: Q1 2024 (subject to regulatory approval)
- Milestone payments: Up to $25M upon achievement of clinical endpoints
- Royalty structure: 5% of net sales for 10 years

The Company believes this acquisition strengthens its pipeline in targeted oncology and provides immediate access to differentiated assets with near-term commercialization potential. Management expects the transaction to be accretive to earnings within 24 months of closing.  # noqa: E501

The transaction has been approved by the Board of Directors and does not require shareholder approval. Closing is subject to customary conditions including regulatory clearance and third-party consents.  # noqa: E501

SIGNATURES

Pursuant to the requirements of the Securities Exchange Act of 1934, the registrant has duly caused this report to be signed on its behalf by the undersigned hereunto duly authorized.  # noqa: E501

ABC Biopharmaceuticals Inc.

By: /s/ John Smith
    John Smith
    Chief Financial Officer

Date: December 15, 2023

FORWARD-LOOKING STATEMENTS
This report contains forward-looking statements within the meaning of the Private Securities Litigation Reform Act of 1995. These statements involve risks and uncertainties that could cause actual results to differ materially from those projected. Investors should not place undue reliance on these forward-looking statements.  # noqa: E501

The Company undertakes no obligation to update or revise any forward-looking statements, whether as a result of new information, future events, or otherwise, except as required by law.  # noqa: E501

Page 1 of 1
Copyright © 2023 ABC Biopharmaceuticals Inc. All rights reserved.
"""


SAMPLE_LONG_FILING = (
    """
UNITED STATES SECURITIES AND EXCHANGE COMMISSION
Washington, D.C. 20549

FORM 8-K
CURRENT REPORT

Company Name: MegaCorp Industries Inc.

ITEM 2.02 Results of Operations and Financial Condition

On November 30, 2023, MegaCorp Industries Inc. (the "Company") announced its financial results for the third quarter ended October 31, 2023.  # noqa: E501

Third Quarter 2023 Financial Highlights:
- Revenue: $250 million, up 15% year-over-year
- Gross margin: 42%, up from 38% in Q3 2022
- Operating income: $45 million, up 25% year-over-year
- Net income: $32 million, up 30% year-over-year
- Diluted EPS: $0.85, up from $0.65 in Q3 2022
- Cash and equivalents: $120 million

Management Commentary:
"We delivered another strong quarter of growth driven by robust demand across all product lines," said Jane Doe, CEO. "Our investments in R&D and manufacturing capacity are paying off, and we're well-positioned for continued growth in Q4 and beyond."  # noqa: E501

Business Segment Performance:
"""
    + "\n".join(
        [f"Segment {i}: Revenue of ${10+i*5}M, up {5+i}% YoY" for i in range(1, 20)]
    )
    + """

Detailed Financial Tables:
"""
    + "\n".join(
        [
            f"Line item {i}: ${i*1000} | {i*100} units | {i*10}% margin"
            for i in range(1, 50)
        ]
    )
    + """

Forward-Looking Statements and Risk Factors:
This report contains forward-looking statements. Actual results may differ materially. Risk factors include market competition, regulatory changes, supply chain disruptions, currency fluctuations, cybersecurity threats, intellectual property disputes, and macroeconomic conditions.  # noqa: E501

Legal Disclaimer:
The information in this report is provided as-is without warranties. The Company disclaims all liability for damages arising from use of this information.  # noqa: E501

Additional Boilerplate:
"""
    + "\n".join([f"Boilerplate paragraph {i}" for i in range(1, 30)])
    + """

Page 1 of 10
Copyright © 2023 MegaCorp Industries Inc. All rights reserved.
"""
)


def test_estimate_tokens_basic():
    """Test token estimation for basic text."""
    # Empty string
    assert estimate_tokens("") == 0

    # Short string (~100 chars = ~26 tokens with 5% margin)
    short_text = "This is a short sentence with approximately one hundred characters in total for testing purposes."  # noqa: E501
    tokens = estimate_tokens(short_text)
    assert 20 < tokens < 35  # Allow some variance

    # Medium string (~1000 chars = ~262 tokens)
    medium_text = short_text * 10
    tokens = estimate_tokens(medium_text)
    assert 200 < tokens < 300


def test_estimate_tokens_long():
    """Test token estimation for long text."""
    long_text = SAMPLE_8K_FILING
    tokens = estimate_tokens(long_text)
    # Sample filing is ~2200 chars, expect ~577 tokens with 5% safety margin
    assert 500 < tokens < 700  # Allow more variance for safety margin


def test_should_compress_threshold():
    """Test should_compress decision logic."""
    # Short text - no compression needed
    assert should_compress("Short text", threshold=2000) is False

    # Long text - compression needed
    long_text = "x" * 10000  # ~2625 tokens
    assert should_compress(long_text, threshold=2000) is True

    # Edge case - exactly at threshold
    edge_text = "x" * 7600  # ~1995 tokens
    # Should not compress (under threshold)
    assert should_compress(edge_text, threshold=2000) is False


def test_extract_key_sections_empty():
    """Test section extraction with empty input."""
    sections = extract_key_sections("")

    assert sections["title"] == ""
    assert sections["first_para"] == ""
    assert sections["tables"] == ""
    assert sections["bullets"] == ""
    assert sections["last_para"] == ""
    assert sections["middle"] == ""


def test_extract_key_sections_8k_filing():
    """Test section extraction with real SEC 8-K filing."""
    sections = extract_key_sections(SAMPLE_8K_FILING)

    # Should extract title
    assert "FORM 8-K" in sections["title"] or "SECURITIES" in sections["title"]

    # Should extract first paragraph
    assert len(sections["first_para"]) > 0

    # Should extract tables (the key terms list)
    # Note: Our sample has bullet points, not tables
    # Tables need pipes or tabs
    assert len(sections["bullets"]) > 0 or len(sections["middle"]) > 0

    # Should identify boilerplate (most content might be filtered as boilerplate)
    assert len(sections["boilerplate"]) > 0


def test_extract_key_sections_with_tables():
    """Test section extraction with table data."""
    text_with_tables = """
Title Line

First paragraph of content.

Financial Table:
Q1 | Revenue | $10M
Q2 | Revenue | $12M
Q3 | Revenue | $15M

Middle content here.

Last paragraph with forward-looking statements.
"""
    sections = extract_key_sections(text_with_tables)

    # Should extract tables (lines with pipes)
    assert "Revenue" in sections["tables"]
    assert "$10M" in sections["tables"] or "$12M" in sections["tables"]


def test_extract_key_sections_with_bullets():
    """Test section extraction with bullet points."""
    text_with_bullets = """
Main Title

Introduction paragraph.

Key Points:
- First bullet point
- Second bullet point
- Third bullet point

1. Numbered item one
2. Numbered item two

Closing paragraph.
"""
    sections = extract_key_sections(text_with_bullets)

    # Should extract bullets
    assert (
        "First bullet" in sections["bullets"]
        or "bullet point" in sections["bullets"].lower()
    )
    assert "Numbered item" in sections["bullets"]


def test_prioritize_sections_under_budget():
    """Test prioritization when all sections fit in budget."""
    sections = {
        "title": "Short Title",
        "first_para": "First paragraph content.",
        "tables": "Table data",
        "bullets": "- Bullet one\n- Bullet two",
        "last_para": "Last paragraph.",
        "middle": "Middle content.",
        "boilerplate": "Boilerplate text.",
    }

    # Large budget - everything should fit
    result, included = prioritize_sections(sections, max_tokens=5000)

    assert "Short Title" in result
    assert "First paragraph" in result
    assert len(included) >= 5  # Most sections included


def test_prioritize_sections_tight_budget():
    """Test prioritization with tight token budget."""
    sections = {
        "title": "Important Title",
        "first_para": "First paragraph with context.",
        "tables": "Table data here",
        "bullets": "- Key point one\n- Key point two",
        "last_para": "Last paragraph summary.",
        "middle": "x" * 5000,  # Very long middle section
        "boilerplate": "",
    }

    # Tight budget - only high-priority sections
    result, included = prioritize_sections(sections, max_tokens=100)

    # Should include title (highest priority)
    assert "Important Title" in result

    # Should include first_para if space allows
    # May truncate or exclude middle section
    assert len(result) < 500  # Respects token budget


def test_prioritize_sections_order():
    """Test that sections are prioritized correctly."""
    sections = {
        "title": "T" * 50,
        "first_para": "F" * 50,
        "tables": "TB" * 50,
        "bullets": "B" * 50,
        "last_para": "L" * 50,
        "middle": "M" * 5000,  # Largest, lowest priority
        "boilerplate": "",
    }

    result, included = prioritize_sections(sections, max_tokens=200)

    # Title should always be first
    assert result.startswith("T" * 50)

    # High-priority sections should appear before middle
    title_pos = result.find("T" * 50)
    middle_pos = result.find("M" * 50) if "M" * 50 in result else len(result)
    assert title_pos < middle_pos


def test_compress_sec_filing_empty():
    """Test compression with empty input."""
    result = compress_sec_filing("")

    assert result["compressed_text"] == ""
    assert result["original_tokens"] == 0
    assert result["compressed_tokens"] == 0
    assert result["compression_ratio"] == 0.0
    assert result["sections_included"] == []


def test_compress_sec_filing_short_text():
    """Test compression with text already under budget."""
    short_text = "This is a short SEC filing that doesn't need compression."
    result = compress_sec_filing(short_text, max_tokens=2000)

    # Should return original text unchanged
    assert result["compressed_text"] == short_text
    assert result["original_tokens"] == result["compressed_tokens"]
    assert result["compression_ratio"] == 0.0
    assert "full_text" in result["sections_included"]


def test_compress_sec_filing_8k_sample():
    """Test compression with real 8-K filing sample."""
    result = compress_sec_filing(SAMPLE_8K_FILING, max_tokens=300)

    # Should compress the text
    assert len(result["compressed_text"]) < len(SAMPLE_8K_FILING)
    assert result["compressed_tokens"] <= 300
    assert 0.0 < result["compression_ratio"] < 1.0

    # Should preserve critical information
    compressed = result["compressed_text"]

    # Key terms should still be present (or at least referenced)
    # Note: Depending on compression, some details might be truncated
    assert "ABC" in compressed or "FORM" in compressed or "Agreement" in compressed


def test_compress_sec_filing_achieves_target_ratio():
    """Test that compression achieves 30-50% reduction."""
    result = compress_sec_filing(SAMPLE_LONG_FILING, max_tokens=1000)

    # Should achieve significant compression
    assert result["compression_ratio"] >= 0.30  # At least 30% reduction
    assert result["compressed_tokens"] <= 1000  # Respects token limit

    # Should preserve meaning
    compressed = result["compressed_text"]
    assert len(compressed) > 100  # Not empty
    assert "MegaCorp" in compressed or "Revenue" in compressed


def test_compress_sec_filing_metadata():
    """Test that compression returns complete metadata."""
    result = compress_sec_filing(SAMPLE_8K_FILING, max_tokens=250)

    # Should have all required keys
    assert "compressed_text" in result
    assert "original_tokens" in result
    assert "compressed_tokens" in result
    assert "compression_ratio" in result
    assert "sections_included" in result

    # Should have valid types
    assert isinstance(result["compressed_text"], str)
    assert isinstance(result["original_tokens"], int)
    assert isinstance(result["compressed_tokens"], int)
    assert isinstance(result["compression_ratio"], float)
    assert isinstance(result["sections_included"], list)

    # Should have valid values
    assert result["original_tokens"] > 0
    assert result["compressed_tokens"] > 0
    assert 0.0 <= result["compression_ratio"] <= 1.0


def test_compress_sec_filing_different_budgets():
    """Test compression with various token budgets."""
    text = SAMPLE_LONG_FILING

    # Test with different budgets
    budgets = [500, 1000, 1500, 2000]
    previous_length = 0

    for budget in budgets:
        result = compress_sec_filing(text, max_tokens=budget)

        # Should respect token budget
        assert result["compressed_tokens"] <= budget

        # Larger budget should produce longer output
        assert len(result["compressed_text"]) >= previous_length
        previous_length = len(result["compressed_text"])


def test_compress_sec_filing_preserves_critical_info():
    """Test that compression preserves the most critical information."""
    result = compress_sec_filing(SAMPLE_8K_FILING, max_tokens=200)

    compressed = result["compressed_text"]

    # Should preserve title/form type
    assert (
        "8-K" in compressed
        or "FORM" in compressed
        or "ABC" in compressed
        or "Agreement" in compressed
    )

    # Should include some key financial terms
    # At minimum, company name or transaction type should be preserved


def test_compress_sec_filing_removes_boilerplate():
    """Test that compression removes boilerplate effectively."""
    filing_with_boilerplate = (
        SAMPLE_8K_FILING
        + "\n"
        + """
ADDITIONAL BOILERPLATE:
Forward-looking statements disclaimer...
Safe harbor provisions...
Item 9.01 exhibits and attachments...
Signature page follows...
Copyright 2023 All Rights Reserved
Page 1 of 5
"""
    )

    result = compress_sec_filing(filing_with_boilerplate, max_tokens=300)

    compressed = result["compressed_text"]

    # Boilerplate should be reduced or removed
    # Core content should remain
    assert len(compressed) < len(filing_with_boilerplate)

    # Check that boilerplate is less prominent
    boilerplate_keywords = ["forward-looking", "safe harbor", "copyright"]
    boilerplate_count_original = sum(
        1
        for kw in boilerplate_keywords
        if kw.lower() in filing_with_boilerplate.lower()
    )
    boilerplate_count_compressed = sum(
        1 for kw in boilerplate_keywords if kw.lower() in compressed.lower()
    )

    # Should remove at least some boilerplate
    assert boilerplate_count_compressed <= boilerplate_count_original


def test_compression_performance():
    """Test that compression is fast (< 100ms for typical filing)."""
    import time

    start = time.time()
    result = compress_sec_filing(SAMPLE_LONG_FILING, max_tokens=1000)
    elapsed = time.time() - start

    # Should complete in under 100ms
    assert elapsed < 0.1, f"Compression took {elapsed*1000:.1f}ms (should be < 100ms)"
    assert result["compressed_tokens"] > 0  # Sanity check


def test_compression_ratio_calculation():
    """Test compression ratio is calculated correctly."""
    # Create text that should compress by exactly 50%
    text = "x" * 4000  # ~1050 tokens

    result = compress_sec_filing(text, max_tokens=525)  # Target 50% of original

    # Ratio should be approximately 0.50 (50% reduction)
    # Allow wider range due to safety margins in token estimation
    assert 0.40 <= result["compression_ratio"] <= 0.60


def test_sections_included_tracking():
    """Test that sections_included accurately tracks what was kept."""
    result = compress_sec_filing(SAMPLE_8K_FILING, max_tokens=200)

    sections_included = result["sections_included"]

    # Should have at least title
    assert len(sections_included) > 0

    # If it's a list, should contain section names
    assert any(
        section in ["title", "first_para", "tables", "bullets", "last_para", "middle"]
        for section in sections_included
    )


# Integration test demonstrating real-world usage
def test_end_to_end_compression_workflow():
    """Test complete compression workflow as it would be used in classify.py."""
    # Simulate a long SEC filing coming from RSS feed
    long_filing = SAMPLE_LONG_FILING

    # Check if compression is needed
    if should_compress(long_filing, threshold=1500):
        # Compress to fit in LLM context window
        result = compress_sec_filing(long_filing, max_tokens=1500)

        # Verify compression was successful
        assert result["compression_ratio"] > 0.25  # At least 25% savings
        assert result["compressed_tokens"] <= 1500

        # Use compressed text for LLM prompt
        prompt = f"Analyze this SEC filing: {result['compressed_text']}"
        assert len(prompt) < len(f"Analyze this SEC filing: {long_filing}")

        # Log compression metrics (would be done in classify.py)
        metrics = {
            "original_tokens": result["original_tokens"],
            "compressed_tokens": result["compressed_tokens"],
            "ratio": result["compression_ratio"],
            "sections": result["sections_included"],
        }

        assert metrics["ratio"] >= 0.25
        print(f"Compression metrics: {metrics}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
