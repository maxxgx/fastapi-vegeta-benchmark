"""Database schema for benchmark app."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BenchItemDB(Base):
    """Benchmark item model for testing database performance."""
    
    __tablename__ = "bench_items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    value = Column(Integer, nullable=False)
