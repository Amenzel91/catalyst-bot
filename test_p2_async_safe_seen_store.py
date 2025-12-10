#!/usr/bin/env python3
"""Test P2 async-safe SeenStore implementation."""

import asyncio
import threading

from src.catalyst_bot.seen_store import SeenStore

print("=" * 80)
print("TEST 1: Basic Functionality (Same Thread)")
print("=" * 80)

store = SeenStore()
store.mark_seen("test_id_1")
assert store.is_seen("test_id_1"), "Same thread check failed"
print("[PASS] Same-thread operations work")
store.close()

print("\n" + "=" * 80)
print("TEST 2: Multi-threaded Access")
print("=" * 80)

store = SeenStore()
results = []


def thread_func(thread_id):
    item_id = f"test_id_{thread_id}"
    store.mark_seen(item_id)
    is_seen = store.is_seen(item_id)
    results.append((thread_id, is_seen))


threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()

for tid, seen in results:
    assert seen, f"Thread {tid} check failed"
print(f"[PASS] All {len(results)} threads work correctly")

print("\n" + "=" * 80)
print("TEST 3: Async Context Access")
print("=" * 80)


async def async_func(item_id):
    store.mark_seen(item_id)
    return store.is_seen(item_id)


async def main():
    results = await asyncio.gather(
        async_func("async_1"), async_func("async_2"), async_func("async_3")
    )
    assert all(results), "Async tests failed"
    print(f"[PASS] Async contexts work ({len(results)} items)")


asyncio.run(main())
store.close()

print("\n" + "=" * 80)
print("ALL TESTS PASSED")
print("=" * 80)
print("\nSeenStore is now async-safe and ready for pre-filtering!")
