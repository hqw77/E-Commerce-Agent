"""Tests for the hard test-environment guard itself."""

from types import SimpleNamespace

import pytest

from tests.guard import validate_grants, validate_test_settings


def _settings(**overrides):
    values = {
        "mysql_database": "ecommerce_agent_test",
        "mysql_user": "ecommerce_agent_test",
        "redis_db": 15,
        "rag_collection": "knowledge_chunks_test_v1",
        "rag_storage_dir": "storage/test_knowledge",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_valid_test_settings_are_accepted():
    validate_test_settings(_settings())


@pytest.mark.parametrize(
    "overrides",
    [
        {"mysql_database": "ecommerce_agent"},
        {"mysql_user": "root"},
        {"redis_db": 0},
        {"rag_collection": "knowledge_chunks_bge_m3_v1"},
        {"rag_storage_dir": "storage/knowledge"},
    ],
)
def test_wrong_test_settings_are_rejected(overrides):
    with pytest.raises(RuntimeError):
        validate_test_settings(_settings(**overrides))


def test_development_schema_grant_is_rejected():
    with pytest.raises(RuntimeError):
        validate_grants(["GRANT ALL PRIVILEGES ON `ecommerce_agent`.* TO `x`@`%`"])


def test_test_schema_grant_is_accepted():
    validate_grants(
        ["GRANT ALL PRIVILEGES ON `ecommerce_agent_test`.* TO `x`@`%`"]
    )
