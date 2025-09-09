"""Main FastAPI application for benchmark app."""

from fastapi import FastAPI
from app.endpoints.bench_endpoints import bench_router
from app.db import init_models

# Initialize database
init_models()

app = FastAPI(
    title="Benchmark API",
    description="Self-contained FastAPI app for benchmarking async vs sync database operations",
    version="0.1.0",
)

# Include routers
app.include_router(bench_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Benchmark API is running"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)