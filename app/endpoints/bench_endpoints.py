"""
Benchmark endpoints for testing async vs sync database operations.

You can add new endpoints to test at the bottom, the benchmark script will test it automatically!
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db import get_async_db_session, get_sync_db_session
from app.db.schema import BenchItemDB

# Router configuration
bench_router = APIRouter(prefix="/api/bench", tags=["Benchmark"])


@bench_router.post("/seed")
async def seed_data(db: Annotated[AsyncSession, Depends(get_async_db_session)]) -> dict[str, int]:
    """Seed the bench_items table with sample rows if empty."""
    result = await db.execute(select(BenchItemDB).limit(1))
    if result.first() is None:
        values = [{"name": f"item-{i}", "value": i} for i in range(1, 2001)]
        await db.execute(insert(BenchItemDB), values)
        await db.commit()
        return {"inserted": len(values)}
    return {"inserted": 0}


@bench_router.get("/items/{item_id}")
async def get_item_async(item_id: int, db: Annotated[AsyncSession, Depends(get_async_db_session)]) -> dict:
    """Async endpoint that queries the database."""
    row = (await db.execute(select(BenchItemDB).where(BenchItemDB.id == item_id))).scalar_one_or_none()
    if row is None:
        return {"found": False}
    return {"found": True, "id": row.id, "name": row.name, "value": row.value}


@bench_router.get("/items-sync-threadpool/{item_id}")
def get_item_sync_threadpool(item_id: int) -> dict:
    """Call sync SQLAlchemy from async endpoint via threadpool to avoid blocking loop."""
    with get_sync_db_session() as session:
        row = session.get(BenchItemDB, item_id)
        if row is None:
            return {"found": False}
        return {"found": True, "id": row.id, "name": row.name, "value": row.value}


@bench_router.get("/items-sync-blocking/{item_id}")
async def get_item_sync_blocking(item_id: int) -> dict:
    """Intentionally execute sync DB call inline to demonstrate event-loop blocking."""
    with get_sync_db_session() as session:
        row = session.get(BenchItemDB, item_id)
        if row is None:
            return {"found": False}
        return {"found": True, "id": row.id, "name": row.name, "value": row.value}
