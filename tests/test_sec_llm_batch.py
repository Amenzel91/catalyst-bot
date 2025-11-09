"""Tests for SEC LLM batch processing optimization (Wave 4).

This module tests the batch_extract_keywords_from_documents() function
which eliminates the serial asyncio.run() bottleneck by processing all
SEC filings in parallel using asyncio.gather().
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from catalyst_bot.sec_llm_analyzer import batch_extract_keywords_from_documents


@pytest.mark.asyncio
async def test_batch_extract_empty_input():
    """Test that empty input returns empty dict."""
    result = await batch_extract_keywords_from_documents([])
    assert result == {}


@pytest.mark.asyncio
async def test_batch_extract_single_filing():
    """Test batch processing with single SEC filing."""
    filing = {
        "item_id": "test_8k_123",
        "document_text": "Company announces merger with strategic partner for $500M. Expected to close Q4 2024.",
        "title": "Form 8-K: Merger Announcement",
        "filing_type": "8-K",
    }

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document") as mock_extract:
        # Mock the async function to return keywords
        mock_extract.return_value = {
            "keywords": ["merger", "acquisition", "strategic"],
            "sentiment": 0.8,
            "confidence": 0.9,
        }

        result = await batch_extract_keywords_from_documents([filing])

        # Verify function was called with correct params
        mock_extract.assert_called_once_with(
            document_text=filing["document_text"],
            title=filing["title"],
            filing_type=filing["filing_type"],
        )

        # Verify result structure
        assert "test_8k_123" in result
        assert result["test_8k_123"]["keywords"] == ["merger", "acquisition", "strategic"]
        assert result["test_8k_123"]["sentiment"] == 0.8


@pytest.mark.asyncio
async def test_batch_extract_multiple_filings():
    """Test parallel processing of multiple SEC filings."""
    filings = [
        {
            "item_id": "filing_1",
            "document_text": "FDA approval granted for new drug candidate.",
            "title": "Form 8-K: FDA Approval",
            "filing_type": "8-K",
        },
        {
            "item_id": "filing_2",
            "document_text": "Shelf registration of $100M common stock.",
            "title": "Form 424B5: Shelf Offering",
            "filing_type": "424B5",
        },
        {
            "item_id": "filing_3",
            "document_text": "Quarterly earnings report shows 20% revenue growth.",
            "title": "Form 10-Q: Q3 Earnings",
            "filing_type": "10-Q",
        },
    ]

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document") as mock_extract:
        # Mock different results for each filing
        mock_extract.side_effect = [
            {"keywords": ["fda", "approval"], "sentiment": 0.9},
            {"keywords": ["offering", "dilution"], "sentiment": -0.3},
            {"keywords": ["earnings", "growth"], "sentiment": 0.7},
        ]

        result = await batch_extract_keywords_from_documents(filings)

        # Verify all tasks were submitted (3 calls)
        assert mock_extract.call_count == 3

        # Verify all results present
        assert len(result) == 3
        assert "filing_1" in result
        assert "filing_2" in result
        assert "filing_3" in result

        # Verify individual results
        assert result["filing_1"]["keywords"] == ["fda", "approval"]
        assert result["filing_2"]["keywords"] == ["offering", "dilution"]
        assert result["filing_3"]["keywords"] == ["earnings", "growth"]


@pytest.mark.asyncio
async def test_batch_extract_invalid_filings():
    """Test handling of invalid filings (missing required fields)."""
    filings = [
        # Valid filing
        {
            "item_id": "valid_filing",
            "document_text": "Substantive filing text here.",
            "title": "Valid Form 8-K",
            "filing_type": "8-K",
        },
        # Missing item_id
        {
            "document_text": "Some text",
            "title": "No ID",
            "filing_type": "8-K",
        },
        # Missing document_text
        {
            "item_id": "no_text",
            "title": "No Text Filing",
            "filing_type": "8-K",
        },
        # Empty document_text
        {
            "item_id": "empty_text",
            "document_text": "",
            "title": "Empty Text",
            "filing_type": "8-K",
        },
    ]

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document") as mock_extract:
        mock_extract.return_value = {"keywords": ["test"], "sentiment": 0.5}

        result = await batch_extract_keywords_from_documents(filings)

        # Only valid filing should be processed
        assert mock_extract.call_count == 1
        assert len(result) == 1
        assert "valid_filing" in result


@pytest.mark.asyncio
async def test_batch_extract_error_handling():
    """Test that errors from individual filings don't crash the batch."""
    filings = [
        {
            "item_id": "filing_success",
            "document_text": "This will succeed.",
            "title": "Success",
            "filing_type": "8-K",
        },
        {
            "item_id": "filing_error",
            "document_text": "This will fail.",
            "title": "Error",
            "filing_type": "8-K",
        },
        {
            "item_id": "filing_success2",
            "document_text": "This will also succeed.",
            "title": "Success 2",
            "filing_type": "8-K",
        },
    ]

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document") as mock_extract:
        # First call succeeds, second raises exception, third succeeds
        mock_extract.side_effect = [
            {"keywords": ["success1"], "sentiment": 0.8},
            Exception("LLM API timeout"),
            {"keywords": ["success2"], "sentiment": 0.6},
        ]

        result = await batch_extract_keywords_from_documents(filings)

        # All 3 calls should be attempted
        assert mock_extract.call_count == 3

        # All items should be in results
        assert len(result) == 3

        # Successful filings should have results
        assert result["filing_success"]["keywords"] == ["success1"]
        assert result["filing_success2"]["keywords"] == ["success2"]

        # Failed filing should have empty dict
        assert result["filing_error"] == {}


@pytest.mark.asyncio
async def test_batch_extract_parallel_execution():
    """Test that filings are processed in parallel, not serially."""
    import time

    filings = [
        {
            "item_id": f"filing_{i}",
            "document_text": f"Filing {i} text",
            "title": f"Filing {i}",
            "filing_type": "8-K",
        }
        for i in range(5)
    ]

    async def slow_extract(*args, **kwargs):
        """Simulate slow LLM call (0.5 seconds)."""
        await asyncio.sleep(0.5)
        return {"keywords": ["test"], "sentiment": 0.5}

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document", side_effect=slow_extract):
        start = time.time()
        result = await batch_extract_keywords_from_documents(filings)
        elapsed = time.time() - start

        # 5 filings @ 0.5s each = 2.5s serial, but should be ~0.5s parallel
        # Allow some overhead, but verify it's clearly parallel (< 1.5s)
        assert elapsed < 1.5, f"Took {elapsed}s - should be parallel execution (~0.5s), not serial (2.5s)"

        # All filings processed
        assert len(result) == 5


def test_batch_extract_return_exceptions():
    """Test that return_exceptions=True in asyncio.gather is used correctly."""
    # This is a sync test that verifies the structure of the code
    # The actual async behavior is tested in test_batch_extract_error_handling

    # Verify the function exists and has correct signature
    assert callable(batch_extract_keywords_from_documents)

    # Verify it's an async function
    assert asyncio.iscoroutinefunction(batch_extract_keywords_from_documents)


@pytest.mark.asyncio
async def test_batch_extract_result_structure():
    """Test that results have expected structure and data types."""
    filing = {
        "item_id": "structure_test",
        "document_text": "Test filing text.",
        "title": "Test Filing",
        "filing_type": "8-K",
    }

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document") as mock_extract:
        mock_extract.return_value = {
            "keywords": ["keyword1", "keyword2"],
            "sentiment": 0.75,
            "confidence": 0.88,
            "extracted_numbers": {"revenue": "100M"},
        }

        result = await batch_extract_keywords_from_documents([filing])

        # Verify result is dict
        assert isinstance(result, dict)

        # Verify item_id is key
        assert "structure_test" in result

        # Verify nested result structure preserved
        item_result = result["structure_test"]
        assert isinstance(item_result, dict)
        assert "keywords" in item_result
        assert isinstance(item_result["keywords"], list)
        assert item_result["keywords"] == ["keyword1", "keyword2"]
        assert item_result["sentiment"] == 0.75


@pytest.mark.asyncio
async def test_batch_extract_logging(caplog):
    """Test that batch processing logs appropriate messages."""
    import logging

    caplog.set_level(logging.INFO)

    filings = [
        {
            "item_id": "log_test_1",
            "document_text": "Filing 1",
            "title": "Test 1",
            "filing_type": "8-K",
        },
        {
            "item_id": "log_test_2",
            "document_text": "Filing 2",
            "title": "Test 2",
            "filing_type": "8-K",
        },
    ]

    with patch("catalyst_bot.sec_llm_analyzer.extract_keywords_from_document") as mock_extract:
        mock_extract.return_value = {"keywords": ["test"], "sentiment": 0.5}

        await batch_extract_keywords_from_documents(filings)

        # Check for expected log messages
        log_messages = [record.message for record in caplog.records]

        # Should log batch start
        assert any("batch_extract_starting" in msg for msg in log_messages)

        # Should log batch completion with statistics
        assert any("batch_extract_complete" in msg for msg in log_messages)
