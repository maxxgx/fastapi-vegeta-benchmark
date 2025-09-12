"""
Benchmark endpoints for testing async vs sync database operations.

You can add new endpoints to test at the bottom, the benchmark script will test it automatically!
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db import get_async_db_session, get_sync_db_session
from app.db.schema import BenchItemDB

# Router configuration
bench_router = APIRouter(prefix="/api/db", tags=["Benchmark"])


@bench_router.post("/seed")
async def seed_data() -> dict[str, int]:
    """Seed the bench_items table with sample rows if empty."""
    try:
        with get_sync_db_session() as session:
            # Check if data already exists
            result = session.execute(select(BenchItemDB).limit(1))
            if result.first() is None:
                values = [{"name": f"item-{i}", "value": i} for i in range(1, 2001)]
                session.execute(insert(BenchItemDB), values)
                session.commit()
                return {"inserted": len(values)}
            return {"inserted": 0}
    except Exception as e:
        return {"inserted": 0, "error": str(e)}


@bench_router.get("/async/read/{item_id}")
async def get_item_async(item_id: int, db: Annotated[AsyncSession, Depends(get_async_db_session)]) -> dict:
    """Async endpoint that queries the database."""
    try:
        row = (await db.execute(select(BenchItemDB).where(BenchItemDB.id == item_id))).scalar_one_or_none()
        if row is None:
            return {"found": False}
        return {
            "found": True, 
            "id": row.id, 
            "name": row.name, 
            "value": row.value,
            "type": "async_db",
            "worker_scaling_test": True
        }
    except Exception as e:
        return {"found": False, "error": str(e)}


@bench_router.post("/async/write/{item_id}")
async def update_item_async_write(item_id: int, db: Annotated[AsyncSession, Depends(get_async_db_session)]) -> dict:
    """Async endpoint that writes to the database."""
    # First check if item exists
    row = (await db.execute(select(BenchItemDB).where(BenchItemDB.id == item_id))).scalar_one_or_none()
    if row is None:
        return {"found": False, "error": "Item not found"}
    
    # Update the item
    from sqlalchemy import update
    await db.execute(
        update(BenchItemDB)
        .where(BenchItemDB.id == item_id)
        .values(value=row.value + 1, name=f"item-{item_id}-updated")
    )
    
    return {
        "found": True, 
        "id": item_id, 
        "updated": True,
        "new_value": row.value + 1,
        "type": "async_write",
        "worker_scaling_test": True
    }


@bench_router.get("/sync_threadpool/read/{item_id}")
def get_item_sync_threadpool_read(item_id: int) -> dict:
    """Sync endpoint that reads from the database via threadpool."""
    try:
        with get_sync_db_session() as session:
            row = session.get(BenchItemDB, item_id)
            if row is None:
                return {"found": False}
            return {
                "found": True, 
                "id": row.id, 
                "name": row.name, 
                "value": row.value,
                "type": "sync_threadpool_read",
                "worker_scaling_test": True
            }
    except Exception as e:
        return {"found": False, "error": str(e)}


@bench_router.post("/sync_threadpool/write/{item_id}")
def update_item_sync_threadpool_write(item_id: int) -> dict:
    """Sync endpoint that writes to the database via threadpool."""
    try:
        with get_sync_db_session() as session:
            # First check if item exists
            row = session.get(BenchItemDB, item_id)
            if row is None:
                return {"found": False, "error": "Item not found"}
            
            # Update the item
            from sqlalchemy import update
            session.execute(
                update(BenchItemDB)
                .where(BenchItemDB.id == item_id)
                .values(value=row.value + 1, name=f"item-{item_id}-updated")
            )
            session.commit()
            
            return {
                "found": True, 
                "id": item_id, 
                "updated": True,
                "new_value": row.value + 1,
                "type": "sync_threadpool_write",
                "worker_scaling_test": True
            }
    except Exception as e:
        return {"found": False, "error": str(e)}


@bench_router.get("/async/blocking/read/{item_id}")
async def get_item_async_blocking_read(item_id: int) -> dict:
    """Async endpoint with blocking database read - demonstrates event-loop blocking."""
    # This blocks the event loop! (anti-pattern)
    try:
        with get_sync_db_session() as session:
            row = session.get(BenchItemDB, item_id)
            if row is None:
                return {"found": False}
            return {
                "found": True, 
                "id": row.id, 
                "name": row.name, 
                "value": row.value,
                "type": "async_blocking_read",
                "worker_scaling_test": True
            }
    except Exception as e:
        return {"found": False, "error": str(e)}


@bench_router.post("/async/blocking/write/{item_id}")
async def update_item_async_blocking_write(item_id: int) -> dict:
    """Async endpoint with blocking database write - demonstrates event-loop blocking."""
    # This blocks the event loop! (anti-pattern)
    try:
        with get_sync_db_session() as session:
            # First check if item exists
            row = session.get(BenchItemDB, item_id)
            if row is None:
                return {"found": False, "error": "Item not found"}
            
            # Update the item
            from sqlalchemy import update
            session.execute(
                update(BenchItemDB)
                .where(BenchItemDB.id == item_id)
                .values(value=row.value + 1, name=f"item-{item_id}-updated")
            )
            session.commit()
            
            return {
                "found": True, 
                "id": item_id, 
                "updated": True,
                "new_value": row.value + 1,
                "type": "async_blocking_write",
                "worker_scaling_test": True
            }
    except Exception as e:
        return {"found": False, "error": str(e)}
