"""
Main FastAPI application entrypoint for Nyaya Legal Assistant with database lifespan,
readiness checks, Prometheus metrics instrumentation, rate limiting, and feedback handling.
"""

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.db import init_db, engine, AsyncSessionLocal
from app.core.logging import logger
from app.core.limiter import limiter, RateLimitExceeded, _rate_limit_exceeded_handler, HAS_SLOWAPI
from app.core.metrics import (
    REQUEST_COUNT,
    REQUEST_DURATION,
    DB_HEALTH_GAUGE,
    REDIS_HEALTH_GAUGE,
    metrics_endpoint
)
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.forms import router as forms_router
from app.api.feedback import router as feedback_router
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager handling startup & shutdown events."""
    logger.info("Application startup: initializing database...")
    await init_db()
    yield
    logger.info("Application shutdown: closing engine...")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# SlowAPI Rate Limiter attachment
if HAS_SLOWAPI and _rate_limit_exceeded_handler:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prometheus HTTP Traffic Instrumentation Middleware
@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start_time

    path = request.url.path
    # Group parameterized paths to keep metric cardinalities bounded
    if path.startswith("/api/v1/forms/") and path not in ["/api/v1/forms/search", "/api/v1/forms/download-all"]:
        path = "/api/v1/forms/{id}"
    elif path.startswith("/api/v1/documents/") and path != "/api/v1/documents/upload":
        path = "/api/v1/documents/{id}"
    elif path.startswith("/api/v1/conversations/"):
        path = "/api/v1/conversations/{session_id}"

    REQUEST_COUNT.labels(method=request.method, endpoint=path, status_code=response.status_code).inc()
    REQUEST_DURATION.labels(endpoint=path).observe(duration)
    return response


# Add CORS Middleware for local frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],
)

# Include API Routers
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(forms_router, prefix=settings.API_V1_STR)
app.include_router(feedback_router, prefix=settings.API_V1_STR)

# Prometheus Metrics Route
app.add_api_route(
    f"{settings.API_V1_STR}/metrics",
    metrics_endpoint,
    methods=["GET"],
    tags=["Metrics"],
    include_in_schema=True
)


@app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
async def health_check():
    """Liveness health check endpoint."""
    return {"status": "ok"}


@app.get(f"{settings.API_V1_STR}/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check verifying real PostgreSQL and Redis connectivity."""
    db_ok = False
    redis_ok = False

    # 1. Check PostgreSQL Database Connectivity
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            if result.scalar() == 1:
                db_ok = True
    except Exception as e:
        logger.error(f"Database readiness check failed: {e}")

    # 2. Check Redis Server Connectivity
    try:
        r = aioredis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, socket_timeout=2)
        pong = await r.ping()
        if pong:
            redis_ok = True
        await r.close()
    except Exception as e:
        logger.error(f"Redis readiness check failed: {e}")

    # Update Prometheus Health Gauges
    DB_HEALTH_GAUGE.set(1.0 if db_ok else 0.0)
    REDIS_HEALTH_GAUGE.set(1.0 if redis_ok else 0.0)

    is_ready = db_ok and redis_ok
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "status": "ready" if is_ready else "not_ready",
    }

    return JSONResponse(status_code=status_code, content=payload)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
