
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.redis import redis_client
from app.db.session import engine

router = APIRouter()


@router.get("/live", summary="Liveness probe")
async def health_live() -> dict[str, str]:
    """Check whether the application process is alive."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def health_ready() -> JSONResponse:
    """Check whether critical application dependencies are available."""

    checks = {
        "database": "ok",
        "redis": "ok",
    }

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        checks["database"] = "error"

    try:
        await redis_client.ping()
    except RedisError:
        checks["redis"] = "error"

    is_ready = all(status == "ok" for status in checks.values())

    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ok" if is_ready else "not_ready",
            "checks": checks,
        },
    )
