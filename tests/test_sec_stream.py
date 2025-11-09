"""Tests for SEC WebSocket streaming client."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from catalyst_bot.sec_stream import (
    DEFAULT_MARKET_CAP_MAX,
    SECStreamClient,
    SECStreamException,
    FilingEvent,
    get_market_cap_max,
    get_reconnect_delay,
    get_sec_api_key,
    is_sec_stream_enabled,
    monitor_sec_stream,
    monitor_with_fallback,
)


@pytest.fixture
def sample_filing_payload():
    """Sample WebSocket payload from sec-api.io."""
    return {
        "type": "filing",
        "ticker": "AAPL",
        "companyName": "Apple Inc.",
        "formType": "8-K",
        "filedAt": "2025-01-15T14:30:00Z",
        "linkToFilingDetails": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193",
        "cik": "0000320193",
        "accessionNo": "0000320193-25-000001",
        "items": "1.01,2.02",
        "marketCap": 2500000000.0,
    }


@pytest.fixture
def high_market_cap_payload():
    """Filing with market cap > $5B (should be filtered)."""
    return {
        "type": "filing",
        "ticker": "MSFT",
        "companyName": "Microsoft Corporation",
        "formType": "10-Q",
        "filedAt": "2025-01-15T14:30:00Z",
        "linkToFilingDetails": "https://www.sec.gov/...",
        "cik": "0000789019",
        "accessionNo": "0000789019-25-000001",
        "items": "",
        "marketCap": 10000000000.0,  # $10B
    }


def test_filing_event_from_websocket_payload(sample_filing_payload):
    """Test parsing WebSocket payload into FilingEvent."""
    filing = FilingEvent.from_websocket_payload(sample_filing_payload)

    assert filing.ticker == "AAPL"
    assert filing.company_name == "Apple Inc."
    assert filing.filing_type == "8-K"
    assert filing.cik == "0000320193"
    assert filing.market_cap == 2500000000.0
    assert "1.01" in filing.item_codes
    assert "2.02" in filing.item_codes
    assert len(filing.item_codes) == 2


def test_filing_event_from_payload_missing_data():
    """Test parsing payload with missing fields."""
    minimal_payload = {"type": "filing"}

    filing = FilingEvent.from_websocket_payload(minimal_payload)

    assert filing.ticker == "UNKNOWN"
    assert filing.company_name == ""
    assert filing.filing_type == ""
    assert filing.item_codes == []
    assert filing.market_cap is None


def test_filing_event_json_serialization(sample_filing_payload):
    """Test JSON serialization round-trip."""
    filing = FilingEvent.from_websocket_payload(sample_filing_payload)

    json_str = filing.to_json()
    assert isinstance(json_str, str)

    filing_restored = FilingEvent.from_json(json_str)
    assert filing_restored.ticker == filing.ticker
    assert filing_restored.company_name == filing.company_name
    assert filing_restored.filing_type == filing.filing_type
    assert filing_restored.market_cap == filing.market_cap


def test_filing_event_datetime_parsing():
    """Test datetime parsing from ISO format."""
    payload = {
        "type": "filing",
        "ticker": "AAPL",
        "filedAt": "2025-01-15T14:30:00Z",
    }

    filing = FilingEvent.from_websocket_payload(payload)

    assert isinstance(filing.filed_at, datetime)
    assert filing.filed_at.year == 2025
    assert filing.filed_at.month == 1
    assert filing.filed_at.day == 15


def test_sec_stream_client_market_cap_filtering(sample_filing_payload, high_market_cap_payload):
    """Test market cap filtering logic."""
    client = SECStreamClient(api_key="test_key", market_cap_max=5_000_000_000)

    # Should pass: $2.5B < $5B
    filing_low = FilingEvent.from_websocket_payload(sample_filing_payload)
    assert client.filter_by_market_cap(filing_low)

    # Should fail: $10B > $5B
    filing_high = FilingEvent.from_websocket_payload(high_market_cap_payload)
    assert not client.filter_by_market_cap(filing_high)

    # Should pass: None market cap (err on inclusion)
    filing_unknown = FilingEvent.from_websocket_payload({"type": "filing", "ticker": "TEST"})
    assert client.filter_by_market_cap(filing_unknown)


def test_sec_stream_client_filing_type_filtering():
    """Test filing type filtering."""
    client = SECStreamClient(api_key="test_key", filing_types=["8-K", "10-Q"])

    filing_8k = FilingEvent.from_websocket_payload({"type": "filing", "ticker": "AAPL", "formType": "8-K"})
    assert client.filter_by_filing_type(filing_8k)

    filing_10q = FilingEvent.from_websocket_payload({"type": "filing", "ticker": "AAPL", "formType": "10-Q"})
    assert client.filter_by_filing_type(filing_10q)

    filing_s1 = FilingEvent.from_websocket_payload({"type": "filing", "ticker": "AAPL", "formType": "S-1"})
    assert not client.filter_by_filing_type(filing_s1)


@pytest.mark.asyncio
async def test_sec_stream_client_connection():
    """Test WebSocket connection establishment."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        # Mock auth response
        auth_response = json.dumps({"type": "auth_success"})
        mock_websocket.recv.return_value = auth_response

        client = SECStreamClient(api_key="test_key")
        await client.connect()

        assert client.is_connected
        assert client.reconnect_attempts == 0
        mock_ws.connect.assert_called_once()


@pytest.mark.asyncio
async def test_sec_stream_client_auth_failure():
    """Test handling of authentication failure."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        # Mock auth failure response
        auth_response = json.dumps({"type": "auth_failed", "message": "Invalid API key"})
        mock_websocket.recv.return_value = auth_response

        client = SECStreamClient(api_key="bad_key")

        with pytest.raises(SECStreamException, match="Authentication failed"):
            await client.connect()


@pytest.mark.asyncio
async def test_sec_stream_client_disconnect():
    """Test graceful disconnection."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        auth_response = json.dumps({"type": "auth_success"})
        mock_websocket.recv.return_value = auth_response

        client = SECStreamClient(api_key="test_key")
        await client.connect()
        await client.disconnect()

        assert not client.is_connected
        mock_websocket.close.assert_called_once()


@pytest.mark.asyncio
async def test_sec_stream_client_reconnection():
    """Test reconnection with exponential backoff."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        auth_response = json.dumps({"type": "auth_success"})
        mock_websocket.recv.return_value = auth_response

        client = SECStreamClient(api_key="test_key", reconnect_delay=1)

        # First connection fails
        mock_ws.connect.side_effect = [
            Exception("Connection refused"),
            mock_websocket,  # Succeeds on retry
        ]

        with pytest.raises(SECStreamException):
            await client.connect()

        # Reconnect should work
        mock_ws.connect.side_effect = [mock_websocket]
        await client._reconnect()

        assert client.is_connected
        assert client.reconnect_attempts == 1


@pytest.mark.asyncio
async def test_stream_filings_basic(sample_filing_payload):
    """Test basic filing streaming."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        # Mock responses
        auth_response = json.dumps({"type": "auth_success"})
        filing_message = json.dumps(sample_filing_payload)

        mock_websocket.recv.side_effect = [
            auth_response,
            filing_message,
            asyncio.CancelledError(),  # Stop after one filing
        ]

        client = SECStreamClient(api_key="test_key")

        filings_received = []
        try:
            async for filing in client.stream_filings():
                filings_received.append(filing)
        except asyncio.CancelledError:
            pass

        assert len(filings_received) == 1
        assert filings_received[0].ticker == "AAPL"
        assert filings_received[0].filing_type == "8-K"


@pytest.mark.asyncio
async def test_stream_filings_filters_high_market_cap(sample_filing_payload, high_market_cap_payload):
    """Test that high market cap filings are filtered out."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        auth_response = json.dumps({"type": "auth_success"})
        filing1 = json.dumps(sample_filing_payload)  # $2.5B - should pass
        filing2 = json.dumps(high_market_cap_payload)  # $10B - should be filtered

        mock_websocket.recv.side_effect = [
            auth_response,
            filing1,
            filing2,
            asyncio.CancelledError(),
        ]

        client = SECStreamClient(api_key="test_key", market_cap_max=5_000_000_000)

        filings_received = []
        try:
            async for filing in client.stream_filings():
                filings_received.append(filing)
        except asyncio.CancelledError:
            pass

        # Only the low market cap filing should be received
        assert len(filings_received) == 1
        assert filings_received[0].ticker == "AAPL"
        assert filings_received[0].market_cap == 2500000000.0


@pytest.mark.asyncio
async def test_stream_filings_queue_full_handling(sample_filing_payload):
    """Test handling of queue overflow."""
    with patch("catalyst_bot.sec_stream.websockets") as mock_ws:
        mock_websocket = AsyncMock()
        mock_ws.connect.return_value = mock_websocket

        client = SECStreamClient(api_key="test_key")
        # Fill the queue manually
        for _ in range(1000):  # Max queue size
            await client.filing_queue.put(FilingEvent.from_websocket_payload(sample_filing_payload))

        assert client.filing_queue.full()

        # Next filing should be dropped (logged, not raised)
        auth_response = json.dumps({"type": "auth_success"})
        filing_message = json.dumps(sample_filing_payload)

        mock_websocket.recv.side_effect = [
            auth_response,
            filing_message,
            asyncio.CancelledError(),
        ]

        # Should not raise exception
        try:
            async for _ in client.stream_filings():
                break
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_monitor_sec_stream():
    """Test high-level stream monitor function."""
    callback_results = []

    async def mock_callback(filing: FilingEvent):
        callback_results.append(filing.ticker)

    with patch("catalyst_bot.sec_stream.get_sec_api_key", return_value="test_key"):
        with patch("catalyst_bot.sec_stream.SECStreamClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock stream_filings to yield one filing then stop
            async def mock_stream():
                yield FilingEvent.from_websocket_payload(
                    {"type": "filing", "ticker": "AAPL", "formType": "8-K"}
                )

            mock_client.stream_filings.return_value = mock_stream()

            # Run monitor with timeout to prevent hanging
            try:
                await asyncio.wait_for(
                    monitor_sec_stream(mock_callback, filing_types=["8-K"]),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                pass

            # Callback should have been called
            assert "AAPL" in callback_results


@pytest.mark.asyncio
async def test_monitor_with_fallback_stream_enabled():
    """Test fallback monitor when streaming is enabled."""
    callback_results = []

    async def mock_callback(filing: FilingEvent):
        callback_results.append(filing.ticker)

    async def mock_rss_fallback():
        callback_results.append("RSS_FALLBACK")

    with patch("catalyst_bot.sec_stream.is_sec_stream_enabled", return_value=True):
        with patch("catalyst_bot.sec_stream.monitor_sec_stream", new_callable=AsyncMock) as mock_monitor:
            # Simulate successful stream
            await monitor_with_fallback(mock_callback, mock_rss_fallback)

            mock_monitor.assert_called_once_with(mock_callback, None)


@pytest.mark.asyncio
async def test_monitor_with_fallback_stream_disabled():
    """Test fallback monitor when streaming is disabled."""
    callback_results = []

    async def mock_callback(filing: FilingEvent):
        callback_results.append(filing.ticker)

    async def mock_rss_fallback():
        callback_results.append("RSS_FALLBACK")

    with patch("catalyst_bot.sec_stream.is_sec_stream_enabled", return_value=False):
        await monitor_with_fallback(mock_callback, mock_rss_fallback)

        # RSS fallback should have been called
        assert "RSS_FALLBACK" in callback_results


@pytest.mark.asyncio
async def test_monitor_with_fallback_on_exception():
    """Test that fallback is triggered when stream raises exception."""
    callback_results = []

    async def mock_callback(filing: FilingEvent):
        callback_results.append(filing.ticker)

    async def mock_rss_fallback():
        callback_results.append("RSS_FALLBACK")

    with patch("catalyst_bot.sec_stream.is_sec_stream_enabled", return_value=True):
        with patch("catalyst_bot.sec_stream.monitor_sec_stream", new_callable=AsyncMock) as mock_monitor:
            # Simulate stream failure
            mock_monitor.side_effect = SECStreamException("WebSocket failed")

            await monitor_with_fallback(mock_callback, mock_rss_fallback)

            # RSS fallback should have been called
            assert "RSS_FALLBACK" in callback_results


def test_get_sec_api_key_configured():
    """Test getting API key from environment."""
    with patch.dict("os.environ", {"SEC_API_KEY": "my_api_key"}):
        assert get_sec_api_key() == "my_api_key"


def test_get_sec_api_key_not_configured():
    """Test error when API key not configured."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="SEC_API_KEY not configured"):
            get_sec_api_key()


def test_is_sec_stream_enabled():
    """Test stream enabled check."""
    with patch.dict("os.environ", {"SEC_STREAM_ENABLED": "true"}):
        assert is_sec_stream_enabled() is True

    with patch.dict("os.environ", {"SEC_STREAM_ENABLED": "false"}):
        assert is_sec_stream_enabled() is False

    with patch.dict("os.environ", {}, clear=True):
        # Default is true
        assert is_sec_stream_enabled() is True


def test_get_market_cap_max():
    """Test getting market cap max from environment."""
    with patch.dict("os.environ", {"SEC_STREAM_MARKET_CAP_MAX": "10000000000"}):
        assert get_market_cap_max() == 10_000_000_000

    with patch.dict("os.environ", {}, clear=True):
        assert get_market_cap_max() == DEFAULT_MARKET_CAP_MAX


def test_get_reconnect_delay():
    """Test getting reconnect delay from environment."""
    with patch.dict("os.environ", {"SEC_STREAM_RECONNECT_DELAY": "10"}):
        assert get_reconnect_delay() == 10

    with patch.dict("os.environ", {}, clear=True):
        assert get_reconnect_delay() == 5  # DEFAULT_RECONNECT_DELAY


def test_filing_event_dataclass():
    """Test FilingEvent dataclass initialization."""
    filing = FilingEvent(
        ticker="AAPL",
        company_name="Apple Inc.",
        filing_type="8-K",
        filing_url="https://sec.gov/...",
        filed_at=datetime(2025, 1, 15, 14, 30),
        cik="0000320193",
        accession_number="0000320193-25-000001",
        market_cap=2500000000.0,
        item_codes=["1.01", "2.02"],
    )

    assert filing.ticker == "AAPL"
    assert filing.filing_type == "8-K"
    assert len(filing.item_codes) == 2
    assert filing.market_cap == 2500000000.0
