"""Real-time SEC filing WebSocket streaming client.

This module provides WebSocket-based real-time SEC filing delivery via sec-api.io,
replacing periodic RSS polling with instant filing notifications.

Key features:
- WebSocket streaming from sec-api.io
- Market cap filtering (<$5B for penny stock focus)
- Automatic reconnection with exponential backoff
- Redis queue for filing backlog during processing spikes
- Graceful fallback to RSS polling on failure

Environment Variables:
- SEC_API_KEY: sec-api.io API key
- SEC_STREAM_ENABLED: Enable WebSocket streaming (default: true)
- SEC_STREAM_MARKET_CAP_MAX: Maximum market cap filter in USD (default: $5B)
- SEC_STREAM_RECONNECT_DELAY: Base reconnect delay in seconds (default: 5)

References:
- sec-api.io WebSocket API: https://sec-api.io/docs/websocket-api
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

try:
    import websockets
    from websockets.exceptions import WebSocketException
except ImportError:
    websockets = None
    WebSocketException = Exception

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("sec_stream")


log = get_logger("sec_stream")


# ============================================================================
# Configuration
# ============================================================================

SEC_API_WEBSOCKET_URL = "wss://socket.sec-api.io"
DEFAULT_MARKET_CAP_MAX = 5_000_000_000  # $5B (penny stock threshold)
DEFAULT_RECONNECT_DELAY = 5  # seconds
MAX_RECONNECT_DELAY = 300  # 5 minutes
BACKOFF_MULTIPLIER = 2.0


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class FilingEvent:
    """Real-time SEC filing event from WebSocket stream."""

    ticker: str
    company_name: str
    filing_type: str  # 8-K, 10-Q, 10-K, etc.
    filing_url: str
    filed_at: datetime
    cik: str  # Central Index Key
    accession_number: str
    market_cap: Optional[float] = None  # USD
    item_codes: list[str] = field(default_factory=list)  # 8-K items only
    raw_data: dict = field(default_factory=dict)  # Full WebSocket payload

    @classmethod
    def from_websocket_payload(cls, payload: dict) -> FilingEvent:
        """Parse WebSocket payload into FilingEvent.

        Parameters
        ----------
        payload : dict
            Raw WebSocket message from sec-api.io

        Returns
        -------
        FilingEvent
            Parsed filing event

        Example Payload
        ---------------
        {
            "ticker": "AAPL",
            "companyName": "Apple Inc.",
            "formType": "8-K",
            "filedAt": "2025-01-15T14:30:00Z",
            "linkToFilingDetails": "https://www.sec.gov/...",
            "cik": "0000320193",
            "accessionNo": "0000320193-25-000001",
            "items": "1.01,2.02",  # 8-K items
            "marketCap": 2500000000.0
        }
        """
        # Parse filed_at timestamp
        filed_at_str = payload.get("filedAt", "")
        try:
            filed_at = datetime.fromisoformat(filed_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            filed_at = datetime.now(timezone.utc)

        # Parse 8-K items
        items_str = payload.get("items", "")
        item_codes = (
            [item.strip() for item in items_str.split(",") if item.strip()]
            if items_str
            else []
        )

        return cls(
            ticker=payload.get("ticker", "UNKNOWN"),
            company_name=payload.get("companyName", ""),
            filing_type=payload.get("formType", ""),
            filing_url=payload.get("linkToFilingDetails", ""),
            filed_at=filed_at,
            cik=payload.get("cik", ""),
            accession_number=payload.get("accessionNo", ""),
            market_cap=payload.get("marketCap"),
            item_codes=item_codes,
            raw_data=payload,
        )

    def to_json(self) -> str:
        """Serialize to JSON for queue storage."""
        return json.dumps(
            {
                "ticker": self.ticker,
                "company_name": self.company_name,
                "filing_type": self.filing_type,
                "filing_url": self.filing_url,
                "filed_at": self.filed_at.isoformat(),
                "cik": self.cik,
                "accession_number": self.accession_number,
                "market_cap": self.market_cap,
                "item_codes": self.item_codes,
                "raw_data": self.raw_data,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> FilingEvent:
        """Deserialize from JSON."""
        data = json.loads(json_str)
        data["filed_at"] = datetime.fromisoformat(data["filed_at"])
        return cls(**data)


class SECStreamException(Exception):
    """Exception raised by SEC WebSocket stream."""


# ============================================================================
# WebSocket Stream Client
# ============================================================================


class SECStreamClient:
    """WebSocket client for real-time SEC filing stream.

    This client connects to sec-api.io WebSocket API and streams filings
    in real-time, applying market cap and filing type filters.

    Examples
    --------
    >>> async with SECStreamClient(api_key="your_key") as client:
    ...     async for filing in client.stream_filings():
    ...         print(f"New filing: {filing.ticker} - {filing.filing_type}")
    ...         await process_filing(filing)
    """

    def __init__(
        self,
        api_key: str,
        market_cap_max: Optional[float] = None,
        filing_types: Optional[list[str]] = None,
        reconnect_delay: int = DEFAULT_RECONNECT_DELAY,
    ):
        """Initialize SEC WebSocket stream client.

        Parameters
        ----------
        api_key : str
            sec-api.io API key
        market_cap_max : float, optional
            Maximum market cap for filtering (default: $5B)
        filing_types : list[str], optional
            Filing types to filter (default: ["8-K", "10-Q", "10-K"])
        reconnect_delay : int
            Base reconnect delay in seconds
        """
        if not websockets:
            raise ImportError("websockets package required: pip install websockets")

        self.api_key = api_key
        self.market_cap_max = market_cap_max or DEFAULT_MARKET_CAP_MAX
        self.filing_types = filing_types or ["8-K", "10-Q", "10-K"]
        self.base_reconnect_delay = reconnect_delay

        self.websocket = None
        self.is_connected = False
        self.reconnect_attempts = 0

        # Queue for filing backlog
        self.filing_queue: asyncio.Queue[FilingEvent] = asyncio.Queue(maxsize=1000)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self):
        """Establish WebSocket connection with authentication.

        Raises
        ------
        SECStreamException
            If connection fails after retries
        """
        try:
            log.info(f"Connecting to SEC WebSocket stream at {SEC_API_WEBSOCKET_URL}")

            # Connect to WebSocket
            self.websocket = await websockets.connect(
                SEC_API_WEBSOCKET_URL,
                ping_interval=30,  # Send ping every 30s
                ping_timeout=10,
            )

            # Authenticate with API key
            auth_message = json.dumps({"type": "auth", "apiKey": self.api_key})
            await self.websocket.send(auth_message)

            # Wait for auth confirmation
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            response_data = json.loads(response)

            if response_data.get("type") != "auth_success":
                raise SECStreamException(f"Authentication failed: {response_data}")

            self.is_connected = True
            self.reconnect_attempts = 0
            log.info("✅ Connected to SEC WebSocket stream")

        except Exception as e:
            log.error(f"WebSocket connection failed: {e}")
            raise SECStreamException(f"Failed to connect: {e}")

    async def disconnect(self):
        """Close WebSocket connection gracefully."""
        if self.websocket:
            try:
                await self.websocket.close()
                log.info("Disconnected from SEC WebSocket stream")
            except Exception as e:
                log.warning(f"Error during disconnect: {e}")
        self.is_connected = False

    async def _reconnect(self):
        """Reconnect with exponential backoff.

        Raises
        ------
        SECStreamException
            If max reconnect delay exceeded
        """
        self.reconnect_attempts += 1
        delay = min(
            self.base_reconnect_delay * (BACKOFF_MULTIPLIER**self.reconnect_attempts),
            MAX_RECONNECT_DELAY,
        )

        log.warning(f"Reconnecting in {delay:.0f}s (attempt {self.reconnect_attempts})")
        await asyncio.sleep(delay)

        try:
            await self.connect()
        except SECStreamException:
            if delay >= MAX_RECONNECT_DELAY:
                raise SECStreamException("Max reconnect delay exceeded, giving up")
            await self._reconnect()

    def filter_by_market_cap(self, filing: FilingEvent) -> bool:
        """Apply market cap filter.

        Parameters
        ----------
        filing : FilingEvent
            Filing to check

        Returns
        -------
        bool
            True if filing passes market cap filter
        """
        if filing.market_cap is None:
            # Allow if market cap unknown (err on side of inclusion)
            return True

        return filing.market_cap <= self.market_cap_max

    def filter_by_filing_type(self, filing: FilingEvent) -> bool:
        """Apply filing type filter.

        Parameters
        ----------
        filing : FilingEvent
            Filing to check

        Returns
        -------
        bool
            True if filing type matches filter
        """
        return filing.filing_type in self.filing_types

    async def stream_filings(self) -> AsyncIterator[FilingEvent]:
        """Stream filings in real-time with filtering.

        Yields
        ------
        FilingEvent
            Filtered SEC filing events

        Raises
        ------
        SECStreamException
            If stream fails and reconnection fails
        """
        if not self.is_connected:
            await self.connect()

        while True:
            try:
                # Receive WebSocket message
                message = await self.websocket.recv()
                data = json.loads(message)

                # Skip non-filing messages
                if data.get("type") != "filing":
                    continue

                # Parse filing event
                filing = FilingEvent.from_websocket_payload(data)

                # Apply filters
                if not self.filter_by_filing_type(filing):
                    log.debug(
                        f"Filtered out {filing.ticker} {filing.filing_type} (type mismatch)"
                    )
                    continue

                if not self.filter_by_market_cap(filing):
                    log.debug(
                        f"Filtered out {filing.ticker} (market cap ${filing.market_cap:,.0f})"
                    )
                    continue

                log.info(
                    f"📄 New filing: {filing.ticker} - {filing.filing_type} "
                    f"(market cap: ${filing.market_cap or 0:,.0f})"
                )

                # Add to queue for backpressure handling
                try:
                    self.filing_queue.put_nowait(filing)
                except asyncio.QueueFull:
                    log.warning(
                        f"Filing queue full, dropping {filing.ticker} {filing.filing_type}"
                    )

                yield filing

            except (WebSocketException, ConnectionError, asyncio.TimeoutError) as e:
                log.error(f"WebSocket error: {e}")
                self.is_connected = False
                await self._reconnect()

            except Exception as e:
                log.error(f"Unexpected stream error: {e}")
                await asyncio.sleep(1)


# ============================================================================
# Configuration Helpers
# ============================================================================


def get_sec_api_key() -> str:
    """Get SEC API key from environment.

    Returns
    -------
    str
        API key

    Raises
    ------
    ValueError
        If API key not configured
    """
    api_key = os.getenv("SEC_API_KEY")
    if not api_key:
        raise ValueError(
            "SEC_API_KEY not configured. Get one at https://sec-api.io and add to .env"
        )
    return api_key


def is_sec_stream_enabled() -> bool:
    """Check if SEC WebSocket streaming is enabled.

    Returns
    -------
    bool
        True if streaming should be used
    """
    return os.getenv("SEC_STREAM_ENABLED", "true").lower() in ("true", "1", "yes")


def get_market_cap_max() -> float:
    """Get maximum market cap filter from environment.

    Returns
    -------
    float
        Max market cap in USD
    """
    try:
        return float(os.getenv("SEC_STREAM_MARKET_CAP_MAX", DEFAULT_MARKET_CAP_MAX))
    except (ValueError, TypeError):
        return DEFAULT_MARKET_CAP_MAX


def get_reconnect_delay() -> int:
    """Get reconnect delay from environment.

    Returns
    -------
    int
        Base reconnect delay in seconds
    """
    try:
        return int(os.getenv("SEC_STREAM_RECONNECT_DELAY", DEFAULT_RECONNECT_DELAY))
    except (ValueError, TypeError):
        return DEFAULT_RECONNECT_DELAY


# ============================================================================
# High-Level Stream Monitor
# ============================================================================


async def monitor_sec_stream(
    on_filing_callback: callable,
    filing_types: Optional[list[str]] = None,
) -> None:
    """Monitor SEC WebSocket stream and process filings.

    This is the main entry point for integrating with runner.py.

    Parameters
    ----------
    on_filing_callback : callable
        Async function to call for each filing: async def callback(filing: FilingEvent)
    filing_types : list[str], optional
        Filing types to monitor (default: ["8-K", "10-Q", "10-K"])

    Examples
    --------
    >>> async def process_filing(filing: FilingEvent):
    ...     print(f"Processing {filing.ticker}")
    ...     # Run through LLM chain, sentiment analysis, etc.
    ...
    >>> await monitor_sec_stream(process_filing)

    Integration in runner.py
    ------------------------
    async def sec_stream_task():
        if not is_sec_stream_enabled():
            log.info("SEC streaming disabled, using RSS polling")
            return

        try:
            await monitor_sec_stream(process_sec_filing)
        except SECStreamException:
            log.warning("SEC stream failed, falling back to RSS polling")
            await monitor_sec_rss()  # Existing RSS implementation
    """
    api_key = get_sec_api_key()
    market_cap_max = get_market_cap_max()
    reconnect_delay = get_reconnect_delay()

    log.info(
        f"Starting SEC WebSocket stream monitor "
        f"(market cap < ${market_cap_max:,.0f}, types={filing_types or ['8-K', '10-Q', '10-K']})"
    )

    async with SECStreamClient(
        api_key=api_key,
        market_cap_max=market_cap_max,
        filing_types=filing_types,
        reconnect_delay=reconnect_delay,
    ) as client:
        async for filing in client.stream_filings():
            try:
                await on_filing_callback(filing)
            except Exception as e:
                log.error(f"Error processing filing {filing.ticker}: {e}")
                # Continue processing other filings


# ============================================================================
# Graceful Fallback
# ============================================================================


async def monitor_with_fallback(
    on_filing_callback: callable,
    rss_fallback_callback: callable,
    filing_types: Optional[list[str]] = None,
) -> None:
    """Monitor SEC stream with automatic fallback to RSS polling.

    Parameters
    ----------
    on_filing_callback : callable
        Async function for WebSocket filings
    rss_fallback_callback : callable
        Async function for RSS polling fallback
    filing_types : list[str], optional
        Filing types to monitor

    Examples
    --------
    >>> await monitor_with_fallback(
    ...     on_filing_callback=process_sec_filing,
    ...     rss_fallback_callback=monitor_sec_rss_legacy,
    ... )
    """
    if not is_sec_stream_enabled():
        log.info("SEC streaming disabled via config, using RSS polling")
        await rss_fallback_callback()
        return

    try:
        await monitor_sec_stream(on_filing_callback, filing_types)
    except SECStreamException as e:
        log.error(f"SEC WebSocket stream failed: {e}")
        log.warning("Falling back to RSS polling for SEC filings")
        await rss_fallback_callback()
    except Exception as e:
        log.error(f"Unexpected error in SEC stream: {e}")
        log.warning("Falling back to RSS polling for SEC filings")
        await rss_fallback_callback()
