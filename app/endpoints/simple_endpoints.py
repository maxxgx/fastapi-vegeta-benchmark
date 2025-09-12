"""
Simple endpoints for testing different concurrency patterns.

EXPECTED RESULTS:
- sync_threadpool: Should scale linearly with workers (1 worker = ~10 RPS, 4 workers = ~40 RPS)
- async_blocking: Should NOT scale with workers due to event loop blocking (always ~10 RPS regardless of workers)
- async: Should scale well with workers, similar to sync_threadpool but more efficient

These endpoints help demonstrate the difference between proper async programming
and common async anti-patterns that can hurt performance.
"""

import time
import random
import asyncio
from fastapi import APIRouter

# Router configuration
simple_router = APIRouter(prefix="/api/simple", tags=["Simple"])
SLEEP_TIME = 0.05


@simple_router.get("/async/{item_id}")
async def simple_async(item_id: int) -> dict:
    """
    Proper async endpoint with non-blocking sleep.
    
    This endpoint correctly uses await asyncio.sleep() which doesn't block the event loop.
    This allows the event loop to process other requests while waiting, making it
    much more efficient than the blocking version.
    
    Expected scaling: Should scale well with workers, similar to sync_threadpool
    """
    await asyncio.sleep(SLEEP_TIME)  # This doesn't block the event loop
    
    return {
        "id": item_id,
        "timestamp": time.time(),
        "type": "async",
        "worker_scaling_test": True
    }


@simple_router.get("/sync_threadpool/{item_id}")
def simple_sync_threadpool(item_id: int) -> dict:
    """
    Sync endpoint with blocking sleep that should scale with workers.
    
    This endpoint uses a regular sync function with time.sleep(). When run with
    multiple workers, each worker can handle requests independently, so this
    should scale linearly with the number of workers.
    
    Expected scaling: 1 worker ≈ 10 RPS, 4 workers ≈ 40 RPS
    """
    time.sleep(SLEEP_TIME)
    
    return {
        "id": item_id,
        "timestamp": time.time(),
        "type": "sync_threadpool",
        "worker_scaling_test": True
    }


@simple_router.get("/async_blocking/{item_id}")
async def simple_async_blocking(item_id: int) -> dict:
    """
    Async endpoint with blocking sleep - demonstrates a common anti-pattern.
    
    This endpoint is declared as async but uses time.sleep() instead of await asyncio.sleep().
    This blocks the entire event loop, preventing other requests from being processed
    concurrently. This is a common mistake that makes async code perform worse than sync code.
    
    Expected scaling: Always ~10 RPS regardless of worker count (event loop blocked)
    """
    time.sleep(SLEEP_TIME)  # This blocks the event loop!
    
    return {
        "id": item_id,
        "timestamp": time.time(),
        "type": "sync_blocking",
        "worker_scaling_test": True
    }
