"""
EventQueue - Priority queue for simulation events.

Maintains chronological ordering of all events (price updates, news, SEC filings)
and delivers them at the appropriate virtual time.

Usage:
    from catalyst_bot.simulation.event_queue import (
        EventQueue, EventReplayer, EventType, SimulationEvent
    )

    # Create event queue
    queue = EventQueue()

    # Add events
    queue.push(SimulationEvent.news_item(timestamp=..., title="..."))
    queue.push(SimulationEvent.price_update(timestamp=..., ticker="AAPL", price=150.0))

    # Process events
    while not queue.is_empty():
        event = queue.pop()
        # Handle event...

    # Or use EventReplayer for automated playback
    replayer = EventReplayer(clock)
    replayer.load_historical_data(historical_data)
    replayer.register_handler(EventType.NEWS_ITEM, handle_news)
    await replayer.process_events_until(end_time)
"""

import heapq
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .clock import SimulationClock

log = logging.getLogger(__name__)


class EventType(Enum):
    """Types of simulation events."""

    PRICE_UPDATE = "price_update"
    NEWS_ITEM = "news_item"
    SEC_FILING = "sec_filing"
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"
    CUSTOM = "custom"


@dataclass(order=True)
class SimulationEvent:
    """
    A single event in the simulation timeline.

    Events are ordered by (timestamp, priority) for the priority queue.
    Lower priority values are processed first (higher urgency).
    """

    # Fields used for ordering (timestamp first, then priority)
    timestamp: datetime
    priority: int = field(compare=True, default=0)

    # Non-comparison fields
    event_type: EventType = field(compare=False, default=EventType.CUSTOM)
    data: Dict[str, Any] = field(compare=False, default_factory=dict)

    @classmethod
    def price_update(
        cls,
        timestamp: datetime,
        ticker: str,
        price: float,
        volume: int = 0,
        **kwargs,
    ) -> "SimulationEvent":
        """
        Create a price update event.

        Args:
            timestamp: When the price update occurred
            ticker: Stock ticker symbol
            price: Current price
            volume: Trading volume
            **kwargs: Additional data (open, high, low, etc.)

        Returns:
            SimulationEvent for price update
        """
        return cls(
            timestamp=timestamp,
            priority=1,  # Price updates are medium priority
            event_type=EventType.PRICE_UPDATE,
            data={
                "ticker": ticker,
                "price": price,
                "volume": volume,
                **kwargs,
            },
        )

    @classmethod
    def news_item(
        cls,
        timestamp: datetime,
        title: str,
        ticker: Optional[str] = None,
        **kwargs,
    ) -> "SimulationEvent":
        """
        Create a news item event.

        Args:
            timestamp: When the news was published
            title: News headline
            ticker: Related ticker (if any)
            **kwargs: Additional data (summary, source, url, etc.)

        Returns:
            SimulationEvent for news
        """
        return cls(
            timestamp=timestamp,
            priority=0,  # News is highest priority (triggers alerts)
            event_type=EventType.NEWS_ITEM,
            data={
                "title": title,
                "ticker": ticker,
                **kwargs,
            },
        )

    @classmethod
    def sec_filing(
        cls,
        timestamp: datetime,
        ticker: str,
        form_type: str,
        **kwargs,
    ) -> "SimulationEvent":
        """
        Create an SEC filing event.

        Args:
            timestamp: When the filing was published
            ticker: Company ticker
            form_type: SEC form type (8-K, 10-Q, etc.)
            **kwargs: Additional data

        Returns:
            SimulationEvent for SEC filing
        """
        return cls(
            timestamp=timestamp,
            priority=0,  # SEC filings are highest priority
            event_type=EventType.SEC_FILING,
            data={
                "ticker": ticker,
                "form_type": form_type,
                **kwargs,
            },
        )

    @classmethod
    def market_open(cls, timestamp: datetime) -> "SimulationEvent":
        """Create a market open event."""
        return cls(
            timestamp=timestamp,
            priority=-1,  # Market events are very high priority
            event_type=EventType.MARKET_OPEN,
            data={},
        )

    @classmethod
    def market_close(cls, timestamp: datetime) -> "SimulationEvent":
        """Create a market close event."""
        return cls(
            timestamp=timestamp,
            priority=-1,
            event_type=EventType.MARKET_CLOSE,
            data={},
        )

    @classmethod
    def custom(
        cls,
        timestamp: datetime,
        event_name: str,
        priority: int = 5,
        **kwargs,
    ) -> "SimulationEvent":
        """
        Create a custom event.

        Args:
            timestamp: When the event occurs
            event_name: Name/identifier for the event
            priority: Processing priority (lower = higher urgency)
            **kwargs: Event data

        Returns:
            Custom SimulationEvent
        """
        return cls(
            timestamp=timestamp,
            priority=priority,
            event_type=EventType.CUSTOM,
            data={
                "event_name": event_name,
                **kwargs,
            },
        )


class EventQueue:
    """
    Priority queue for simulation events.

    Events are ordered by timestamp, then by priority within same timestamp.
    Uses a heap for O(log n) push/pop operations.
    """

    def __init__(self):
        """Initialize empty event queue."""
        self._heap: List[SimulationEvent] = []
        self._total_pushed = 0
        self._total_popped = 0

    def push(self, event: SimulationEvent) -> None:
        """
        Add an event to the queue.

        Args:
            event: SimulationEvent to add
        """
        heapq.heappush(self._heap, event)
        self._total_pushed += 1

    def pop(self) -> Optional[SimulationEvent]:
        """
        Remove and return the next event.

        Returns:
            Next event, or None if queue is empty
        """
        if self._heap:
            self._total_popped += 1
            return heapq.heappop(self._heap)
        return None

    def peek(self) -> Optional[SimulationEvent]:
        """
        Return the next event without removing it.

        Returns:
            Next event, or None if queue is empty
        """
        if self._heap:
            return self._heap[0]
        return None

    def pop_until(self, until_time: datetime) -> List[SimulationEvent]:
        """
        Pop all events up to and including the specified time.

        Args:
            until_time: Process all events with timestamp <= this

        Returns:
            List of events in chronological order
        """
        events = []
        while self._heap and self._heap[0].timestamp <= until_time:
            events.append(heapq.heappop(self._heap))
            self._total_popped += 1
        return events

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._heap) == 0

    def __len__(self) -> int:
        """Return number of events in queue."""
        return len(self._heap)

    @property
    def total_events_pushed(self) -> int:
        """Total events that have been added."""
        return self._total_pushed

    @property
    def total_events_popped(self) -> int:
        """Total events that have been processed."""
        return self._total_popped

    def clear(self) -> None:
        """Clear all events from the queue."""
        self._heap.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "current_size": len(self._heap),
            "total_pushed": self._total_pushed,
            "total_popped": self._total_popped,
            "next_event_time": (
                self._heap[0].timestamp.isoformat() if self._heap else None
            ),
        }


# Type alias for event handlers
EventHandler = Callable[[SimulationEvent], Awaitable[None]]


class EventReplayer:
    """
    Replay historical events through the simulation.

    Converts raw historical data into simulation events and feeds them
    to registered handlers at the appropriate virtual times.
    """

    def __init__(self, clock: SimulationClock):
        """
        Initialize event replayer.

        Args:
            clock: SimulationClock for time management
        """
        self.clock = clock
        self.queue = EventQueue()

        # Event handlers by type
        self._handlers: Dict[EventType, List[EventHandler]] = {
            et: [] for et in EventType
        }

        # Statistics
        self._events_dispatched = 0
        self._events_skipped = 0

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """
        Safely parse timestamp from various formats.

        Args:
            ts: Timestamp in any supported format

        Returns:
            Parsed datetime or None
        """
        if ts is None:
            return None

        try:
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts

            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts, tz=timezone.utc)

            if isinstance(ts, str):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))

        except (ValueError, TypeError) as e:
            log.warning(f"Failed to parse timestamp '{ts}': {e}")

        return None

    def load_historical_data(self, data: Dict[str, Any]) -> None:
        """
        Load historical data package and queue all events.

        Args:
            data: Output from HistoricalDataFetcher or sample data
                  Should have: news_items, sec_filings, price_bars
        """
        skipped = 0

        # Queue news items
        for item in data.get("news_items", []):
            timestamp = self._parse_timestamp(item.get("timestamp"))
            if not timestamp:
                skipped += 1
                continue

            # Get first related ticker if available
            related = item.get("related_tickers", [])
            ticker = related[0] if related and isinstance(related, list) else None

            self.queue.push(
                SimulationEvent.news_item(
                    timestamp=timestamp,
                    title=item.get("title", ""),
                    ticker=ticker,
                    summary=item.get("summary", ""),
                    source=item.get("source", ""),
                    url=item.get("url", ""),
                    raw=item,
                )
            )

        # Queue SEC filings
        for filing in data.get("sec_filings", []):
            timestamp = self._parse_timestamp(filing.get("timestamp"))
            if not timestamp:
                skipped += 1
                continue

            self.queue.push(
                SimulationEvent.sec_filing(
                    timestamp=timestamp,
                    ticker=filing.get("ticker", ""),
                    form_type=filing.get("form_type", ""),
                    raw=filing,
                )
            )

        # Queue price updates (sample every N bars to reduce volume)
        sample_rate = 5  # Every 5th bar
        for ticker, bars in data.get("price_bars", {}).items():
            for i, bar in enumerate(bars):
                if i % sample_rate != 0:
                    continue

                timestamp = self._parse_timestamp(bar.get("timestamp"))
                if not timestamp:
                    skipped += 1
                    continue

                self.queue.push(
                    SimulationEvent.price_update(
                        timestamp=timestamp,
                        ticker=ticker,
                        price=bar.get("close", 0),
                        volume=bar.get("volume", 0),
                        open=bar.get("open", 0),
                        high=bar.get("high", 0),
                        low=bar.get("low", 0),
                    )
                )

        self._events_skipped = skipped
        log.info(
            f"Loaded {len(self.queue)} events (skipped {skipped} with invalid timestamps)"
        )

    def register_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of events to handle
            handler: Async function that takes SimulationEvent
        """
        self._handlers[event_type].append(handler)

    def unregister_handler(self, event_type: EventType, handler: EventHandler) -> bool:
        """
        Unregister a handler.

        Args:
            event_type: Event type
            handler: Handler to remove

        Returns:
            True if handler was found and removed
        """
        try:
            self._handlers[event_type].remove(handler)
            return True
        except ValueError:
            return False

    async def process_next_event(self) -> Optional[SimulationEvent]:
        """
        Process the next event in the queue.

        Waits until the event's timestamp (in virtual time) then dispatches it.

        Returns:
            The processed event, or None if queue is empty
        """
        event = self.queue.peek()
        if not event:
            return None

        # Wait until event time (in virtual time)
        current = self.clock.now()
        if event.timestamp > current:
            wait_seconds = (event.timestamp - current).total_seconds()
            self.clock.sleep(wait_seconds)

        # Pop and dispatch
        event = self.queue.pop()
        if event:
            await self._dispatch_event(event)

        return event

    async def process_events_until(self, until_time: datetime) -> int:
        """
        Process all events up to specified time.

        Args:
            until_time: Process all events with timestamp <= this

        Returns:
            Number of events processed
        """
        events = self.queue.pop_until(until_time)

        for event in events:
            await self._dispatch_event(event)

        return len(events)

    async def _dispatch_event(self, event: SimulationEvent) -> None:
        """
        Dispatch event to registered handlers.

        Args:
            event: Event to dispatch
        """
        handlers = self._handlers.get(event.event_type, [])

        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                log.error(f"Handler error for {event.event_type}: {e}")

        self._events_dispatched += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get replayer statistics."""
        return {
            "queue_stats": self.queue.get_stats(),
            "events_dispatched": self._events_dispatched,
            "events_skipped": self._events_skipped,
            "handlers_registered": {
                et.value: len(handlers)
                for et, handlers in self._handlers.items()
                if handlers
            },
        }
