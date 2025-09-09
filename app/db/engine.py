"""Database engine configuration for benchmark app."""

import os
from contextlib import contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from .schema import Base

# Database URL - use a common SQLite file for both async and sync
DATABASE_URL = "sqlite:///./.benchmark.db"
ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./.benchmark.db"

# Create engines
sync_engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    # Enable WAL mode for better concurrency
    pool_pre_ping=True,
)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# Create session makers
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
AsyncSessionLocal = async_sessionmaker(
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    bind=async_engine,
)


def init_models():
    """Initialize database tables."""
    Base.metadata.create_all(bind=sync_engine)


@contextmanager
def get_sync_db_session() -> Generator:
    """Get synchronous database session."""
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get asynchronous database session."""
    async with AsyncSessionLocal() as session:
        yield session
