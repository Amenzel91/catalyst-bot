"""
MockFeedProvider - Provides historical news/SEC data during simulation.

Replaces live RSS/API feeds with historical data replay.
Returns items that would have been available at the current simulation time.

Usage:
    from catalyst_bot.simulation import SimulationClock
    from catalyst_bot.simulation.mock_feeds import MockFeedProvider

    clock = SimulationClock(start_time=..., speed_multiplier=0)
    feed = MockFeedProvider(
        news_items=historical_data["news_items"],
        sec_filings=historical_data["sec_filings"],
        clock=clock
    )

    # Get new items since last check
    new_news = feed.get_new_items()
    new_filings = feed.get_new_sec_filings()

    # Peek at next event time (for scheduling)
    next_time = feed.peek_next_item_time()
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from .clock import SimulationClock

# Import the global clock provider to get the synchronized clock
from .clock_provider import get_clock as get_global_clock

log = logging.getLogger(__name__)


class MockFeedProvider:
    """
    Simulated feed provider using historical data.

    Returns news items and SEC filings that would have been
    available at the current simulation time. Items are delivered
    in chronological order as the simulation clock advances.

    Features:
    - Deduplication: Each item is only returned once
    - Chronological ordering: Items sorted by timestamp
    - Efficient traversal: Uses pointers instead of filtering
    """

    def __init__(
        self,
        news_items: List[Dict],
        sec_filings: List[Dict],
        clock: "SimulationClock",
    ):
        """
        Initialize with historical news and SEC data.

        Args:
            news_items: List of news item dicts with 'timestamp' field
            sec_filings: List of SEC filing dicts with 'timestamp' field
            clock: SimulationClock for time-aware delivery
        """
        self.clock = clock

        # Sort and index items by timestamp
        self._news_items = self._sort_by_timestamp(news_items)
        self._sec_filings = self._sort_by_timestamp(sec_filings)

        # Track what's been "seen" this simulation (for deduplication)
        self._seen_news_ids: Set[str] = set()
        self._seen_sec_ids: Set[str] = set()

        # Pointers to current position in timeline
        self._news_pointer = 0
        self._sec_pointer = 0

        log.debug(
            f"MockFeedProvider initialized: {len(self._news_items)} news, "
            f"{len(self._sec_filings)} SEC filings"
        )

    def _get_current_time(self) -> datetime:
        """
        Get current simulation time, preferring the global clock.

        This ensures MockFeedProvider uses the same clock that the runner
        advances via sim_sleep(), solving the dual-clock mismatch issue.

        Returns:
            Current simulation time from the global clock provider,
            falling back to the local clock if global not available.
        """
        # Prefer the global clock (which is advanced by sim_sleep in runner)
        global_clock = get_global_clock()
        if global_clock is not None:
            return global_clock.now()
        # Fallback to local clock (for tests that don't use global provider)
        return self.clock.now()

    def _sort_by_timestamp(self, items: List[Dict]) -> List[Dict]:
        """
        Sort items by timestamp.

        Args:
            items: List of dicts with 'timestamp' field

        Returns:
            Sorted list
        """
        return sorted(items, key=lambda x: x.get("timestamp", ""))

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """
        Parse timestamp from various formats.

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
                ts = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(ts)

        except (ValueError, TypeError) as e:
            log.warning(f"Failed to parse timestamp '{ts}': {e}")

        return None

    def _get_item_id(self, item: Dict, item_type: str = "news") -> str:
        """
        Get unique identifier for an item.

        Args:
            item: Item dict
            item_type: 'news' or 'sec'

        Returns:
            Unique identifier string
        """
        if item_type == "sec":
            return (
                item.get("accession_number")
                or item.get("url")
                or item.get("id")
                or str(hash(frozenset(item.items())))
            )
        else:
            return (
                item.get("id")
                or item.get("url")
                or item.get("title")
                or str(hash(frozenset(item.items())))
            )

    def get_new_items(self) -> List[Dict]:
        """
        Get news items that have "arrived" since last check.

        Returns items with timestamps <= current simulation time
        that haven't been returned before.

        Returns:
            List of new news items
        """
        current_time = self._get_current_time()
        new_items = []

        while self._news_pointer < len(self._news_items):
            item = self._news_items[self._news_pointer]
            item_time = self._parse_timestamp(item.get("timestamp"))

            if item_time is None:
                # Skip items without valid timestamps
                self._news_pointer += 1
                continue

            if item_time <= current_time:
                item_id = self._get_item_id(item, "news")

                if item_id not in self._seen_news_ids:
                    self._seen_news_ids.add(item_id)
                    new_items.append(item)

                self._news_pointer += 1
            else:
                # Future item, stop here
                break

        return new_items

    def get_new_sec_filings(self) -> List[Dict]:
        """
        Get SEC filings that have "arrived" since last check.

        Returns filings with timestamps <= current simulation time
        that haven't been returned before.

        Returns:
            List of new SEC filings
        """
        current_time = self._get_current_time()
        new_filings = []

        while self._sec_pointer < len(self._sec_filings):
            filing = self._sec_filings[self._sec_pointer]
            filing_time = self._parse_timestamp(filing.get("timestamp"))

            if filing_time is None:
                self._sec_pointer += 1
                continue

            if filing_time <= current_time:
                filing_id = self._get_item_id(filing, "sec")

                if filing_id not in self._seen_sec_ids:
                    self._seen_sec_ids.add(filing_id)
                    new_filings.append(filing)

                self._sec_pointer += 1
            else:
                break

        return new_filings

    def get_all_new(self) -> Dict[str, List[Dict]]:
        """
        Get all new items (news and SEC) since last check.

        Returns:
            Dict with 'news' and 'sec' keys containing new items
        """
        return {
            "news": self.get_new_items(),
            "sec": self.get_new_sec_filings(),
        }

    def peek_next_item_time(self) -> Optional[datetime]:
        """
        Get timestamp of next upcoming item (for scheduling).

        Returns:
            Datetime of next item, or None if no more items
        """
        times = []

        if self._news_pointer < len(self._news_items):
            news_time = self._parse_timestamp(
                self._news_items[self._news_pointer].get("timestamp")
            )
            if news_time:
                times.append(news_time)

        if self._sec_pointer < len(self._sec_filings):
            sec_time = self._parse_timestamp(
                self._sec_filings[self._sec_pointer].get("timestamp")
            )
            if sec_time:
                times.append(sec_time)

        return min(times) if times else None

    def peek_next_news_time(self) -> Optional[datetime]:
        """Get timestamp of next news item."""
        if self._news_pointer < len(self._news_items):
            return self._parse_timestamp(
                self._news_items[self._news_pointer].get("timestamp")
            )
        return None

    def peek_next_sec_time(self) -> Optional[datetime]:
        """Get timestamp of next SEC filing."""
        if self._sec_pointer < len(self._sec_filings):
            return self._parse_timestamp(
                self._sec_filings[self._sec_pointer].get("timestamp")
            )
        return None

    def has_more_items(self) -> bool:
        """
        Check if there are more items to deliver.

        Returns:
            True if more news or SEC items remain
        """
        return self._news_pointer < len(self._news_items) or self._sec_pointer < len(
            self._sec_filings
        )

    def get_items_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, List[Dict]]:
        """
        Get all items within a time range (without marking as seen).

        Useful for previewing or analysis.

        Args:
            start_time: Start of range (inclusive)
            end_time: End of range (inclusive)

        Returns:
            Dict with 'news' and 'sec' lists
        """
        news_in_range = []
        sec_in_range = []

        for item in self._news_items:
            item_time = self._parse_timestamp(item.get("timestamp"))
            if item_time and start_time <= item_time <= end_time:
                news_in_range.append(item)

        for filing in self._sec_filings:
            filing_time = self._parse_timestamp(filing.get("timestamp"))
            if filing_time and start_time <= filing_time <= end_time:
                sec_in_range.append(filing)

        return {
            "news": news_in_range,
            "sec": sec_in_range,
        }

    def reset(self) -> None:
        """Reset to beginning of timeline (start fresh)."""
        self._seen_news_ids.clear()
        self._seen_sec_ids.clear()
        self._news_pointer = 0
        self._sec_pointer = 0
        log.debug("MockFeedProvider reset to beginning")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the feed.

        Returns:
            Dict with feed statistics
        """
        return {
            "total_news": len(self._news_items),
            "total_sec": len(self._sec_filings),
            "delivered_news": len(self._seen_news_ids),
            "delivered_sec": len(self._seen_sec_ids),
            "remaining_news": len(self._news_items) - self._news_pointer,
            "remaining_sec": len(self._sec_filings) - self._sec_pointer,
            "has_more": self.has_more_items(),
        }

    def get_tickers_in_news(self) -> List[str]:
        """
        Get all unique tickers mentioned in news items.

        Returns:
            List of ticker symbols
        """
        tickers = set()

        for item in self._news_items:
            related = item.get("related_tickers", [])
            if isinstance(related, str):
                related = [t.strip() for t in related.split(",") if t.strip()]
            tickers.update(related)

        return list(tickers)

    def get_tickers_in_sec(self) -> List[str]:
        """
        Get all unique tickers in SEC filings.

        Returns:
            List of ticker symbols
        """
        tickers = set()

        for filing in self._sec_filings:
            ticker = filing.get("ticker")
            if ticker:
                tickers.add(ticker)

        return list(tickers)
