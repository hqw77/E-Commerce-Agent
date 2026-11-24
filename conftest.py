"""Global pytest isolation for the development workspace.

This file must be loaded before any test module imports ``app``. It points the
whole suite at the dedicated test database, Redis DB, Qdrant collection and
storage directory, and then verifies the live connections before collection.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from tests.guard import validate_grants, validate_test_settings

_ENV_PATH = Path(__file__).with_name(".env.test")


def _load_test_env() -> None:
    if not _ENV_PATH.exists():
        raise RuntimeError(
            "Refusing to run tests: .env.test is missing. "
            "Create an isolated test environment before running pytest."
        )
    values: dict[str, str] = {}
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    required = {
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "RAG_QDRANT_URL",
        "RAG_COLLECTION",
        "RAG_STORAGE_DIR",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise RuntimeError(
            "Refusing to run tests: .env.test is missing keys: "
            + ", ".join(missing)
        )
    # Force, rather than default, the isolated values. A stale shell variable
    # must never redirect pytest to the development schema.
    for key, value in values.items():
        os.environ[key] = value


async def _verify_live_resources() -> None:
    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal, engine
    from redis.asyncio import Redis
    from sqlalchemy import text

    settings = get_settings()
    validate_test_settings(settings)

    try:
        async with AsyncSessionLocal() as session:
            database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
            if database != "ecommerce_agent_test":
                raise RuntimeError(
                    "Refusing to run tests: live connection is not the test schema"
                )
            grants = [
                row[0] for row in (await session.execute(text("SHOW GRANTS"))).all()
            ]
            validate_grants(grants)
    finally:
        # This verification runs in a temporary event loop. Do not leave
        # loop-bound MySQL connections for the actual pytest loop.
        await engine.dispose()

    # Never ping the process-wide redis_client here: the Agent conftest and
    # application lifespan use the global client in the real pytest loop.
    password = (
        settings.redis_password.get_secret_value()
        if settings.redis_password
        else None
    )
    redis = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=password,
        decode_responses=True,
    )
    try:
        await redis.ping()
    finally:
        await redis.aclose()


def pytest_sessionstart(session) -> None:
    _load_test_env()
    asyncio.run(_verify_live_resources())


# Pytest imports child conftest modules before pytest_sessionstart. The Agent
# conftest imports app settings at module scope, so the isolated environment
# must be installed at root-conftest import time, not only at session start.
_load_test_env()

