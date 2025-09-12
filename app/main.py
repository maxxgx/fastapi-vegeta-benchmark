"""Main FastAPI application for benchmark app."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from app.endpoints.simple_endpoints import simple_router
from app.endpoints.db_endpoints import bench_router
from app.db import init_models
import asyncio

# Initialize database
init_models()

app = FastAPI(
    title="Benchmark API",
    description="Self-contained FastAPI app for benchmarking async vs sync database operations",
    version="0.1.0",
)

# Add CORS middleware to prevent caching issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(simple_router)
app.include_router(bench_router)

# Add middleware to disable caching
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
    # Disable all caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Last-Modified"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return response


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