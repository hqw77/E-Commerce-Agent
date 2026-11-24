
"""健康检查 API.

/live 只代表进程存活, 供容器重启策略使用.
/ready 额外检查 MySQL 和 Redis, 供流量接入判断使用.
"""

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
    """进程存活探针. 不访问数据库, 避免依赖故障导致容器被误杀."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def health_ready() -> JSONResponse:
    """就绪探针. 只有数据库和 Redis 都可用时才允许接收业务流量."""

    checks = {
        "database": "ok",
        "redis": "ok",
    }

    # 用最小 SQL 验证连接池能否拿到可用连接.
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        checks["database"] = "error"

    # PING 验证 Redis 客户端和连接池状态.
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
