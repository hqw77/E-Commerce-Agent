"""Hard safety checks for the isolated test environment.

The checks are intentionally independent from the application code so that a
wrong ``.env`` file cannot silently redirect pytest at the development schema.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

EXPECTED_DATABASE = "ecommerce_agent_test"
EXPECTED_USER = "ecommerce_agent_test"
EXPECTED_REDIS_DB = 15
EXPECTED_QDRANT_COLLECTION = "knowledge_chunks_test_v1"
EXPECTED_STORAGE_SUFFIX = Path("storage") / "test_knowledge"


def validate_test_settings(settings: Any) -> None:
    """Reject any settings that do not point at dedicated test resources."""

    if settings.mysql_database != EXPECTED_DATABASE:
        raise RuntimeError(
            "Refusing to run tests: MYSQL_DATABASE must be "
            f"{EXPECTED_DATABASE!r}, got {settings.mysql_database!r}"
        )
    if settings.mysql_user != EXPECTED_USER:
        raise RuntimeError(
            "Refusing to run tests: MYSQL_USER must be the dedicated test "
            f"account {EXPECTED_USER!r}, got {settings.mysql_user!r}"
        )
    if settings.redis_db != EXPECTED_REDIS_DB:
        raise RuntimeError(
            "Refusing to run tests: REDIS_DB must be "
            f"{EXPECTED_REDIS_DB}, got {settings.redis_db}"
        )
    if settings.rag_collection != EXPECTED_QDRANT_COLLECTION:
        raise RuntimeError(
            "Refusing to run tests: RAG_COLLECTION must be "
            f"{EXPECTED_QDRANT_COLLECTION!r}, got {settings.rag_collection!r}"
        )
    storage = Path(settings.rag_storage_dir).resolve()
    expected = (Path.cwd() / EXPECTED_STORAGE_SUFFIX).resolve()
    if storage != expected:
        raise RuntimeError(
            "Refusing to run tests: RAG_STORAGE_DIR must be "
            f"{expected}, got {storage}"
        )


def validate_grants(grants: Iterable[str]) -> None:
    """Ensure the test account has no grant on the development schema."""

    for grant in grants:
        normalized = " ".join(grant.upper().split())
        if re.search(r"ON\s+`?ECOMMERCE_AGENT`?\s*\.\*", normalized):
            raise RuntimeError(
                "Refusing to run tests: test account has a grant on the "
                "development schema"
            )
        if "ON *.*" in normalized and "USAGE" not in normalized:
            raise RuntimeError(
                "Refusing to run tests: test account has global privileges"
            )
