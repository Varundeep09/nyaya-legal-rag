"""
Main FastAPI application entrypoint for Nyaya Legal Assistant with database lifespan & readiness checks.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.db import init_db, engine, AsyncSessionLocal
from app.core.logging import logger
from app.api.search import router as search_router
from app.api.chat import router as chat_router


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

# Include API Routers
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)



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
