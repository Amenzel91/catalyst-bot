"""
Persistent Event Loop Manager for Trading Engine

Provides a singleton event loop running in a dedicated thread to bridge
synchronous and asynchronous code without repeated loop creation/destruction.
"""

import asyncio
import threading
import logging
from typing import Any, Coroutine, Optional, TypeVar

_logger = logging.getLogger(__name__)
T = TypeVar('T')


class EventLoopManager:
    """Manages a persistent event loop in a background thread."""

    _instance: Optional['EventLoopManager'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._stopping = False

    @classmethod
    def get_instance(cls) -> 'EventLoopManager':
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = EventLoopManager()
        return cls._instance

    def start(self) -> bool:
        """Start the background event loop thread."""
        if self._started:
            _logger.debug("EventLoopManager already started")
            return False

        def run_event_loop():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                _logger.info("event_loop_manager_started thread_id=%s", threading.get_ident())
                self._loop.run_forever()
            except Exception as e:
                _logger.error("event_loop_manager_error err=%s", str(e), exc_info=True)
            finally:
                _logger.info("event_loop_manager_stopping")
                if self._loop:
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                    self._loop.close()
                _logger.info("event_loop_manager_stopped")

        self._thread = threading.Thread(
            target=run_event_loop,
            name="EventLoopManager",
            daemon=True
        )
        self._thread.start()

        # Wait for loop to be ready (with timeout)
        timeout = 5.0
        while self._loop is None and timeout > 0:
            threading.Event().wait(0.05)
            timeout -= 0.05

        if self._loop is None:
            _logger.error("event_loop_manager_start_timeout")
            return False

        self._started = True
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background event loop thread."""
        if not self._started or self._stopping:
            return

        self._stopping = True
        _logger.info("event_loop_manager_stopping_requested")

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                _logger.warning("event_loop_manager_stop_timeout")

        self._started = False
        self._stopping = False

    def run_async(self, coro: Coroutine[Any, Any, T],
                  timeout: Optional[float] = None) -> T:
        """Run async coroutine from sync context."""
        if not self._started or not self._loop:
            raise RuntimeError("EventLoopManager not started - call start() first")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            _logger.error("event_loop_manager_timeout coro=%s", coro)
            future.cancel()
            raise
        except Exception as e:
            _logger.error("event_loop_manager_exception err=%s", str(e))
            raise

    def is_running(self) -> bool:
        """Check if event loop is running."""
        return self._started and self._loop is not None and self._loop.is_running()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing only)."""
        if cls._instance:
            cls._instance.stop()
        cls._instance = None


def run_async(coro: Coroutine[Any, Any, T],
              timeout: Optional[float] = None) -> T:
    """
    Run async function from synchronous context using shared event loop.

    Args:
        coro: Async coroutine to execute
        timeout: Optional timeout in seconds

    Returns:
        Result from coroutine
    """
    manager = EventLoopManager.get_instance()

    if not manager.is_running():
        _logger.info("event_loop_manager_auto_starting")
        manager.start()

    return manager.run_async(coro, timeout=timeout)
