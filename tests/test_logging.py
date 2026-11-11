
import json

import structlog

from app.core.logging import get_logger, setup_logging


def test_console_logging(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.logging.settings.log_format", "console")
    monkeypatch.setattr("app.core.logging.settings.log_level", "INFO")

    setup_logging()

    logger = structlog.get_logger("test_console")
    logger.info("console_test_event", task="logging")

    captured = capsys.readouterr()

    assert "console_test_event" in captured.out
    assert "logging" in captured.out


def test_json_logging(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.logging.settings.log_format", "json")
    monkeypatch.setattr("app.core.logging.settings.log_level", "INFO")

    setup_logging()

    logger = structlog.get_logger("test_json")
    logger.info("json_test_event", task="logging")

    captured = capsys.readouterr()

    data = json.loads(captured.out.strip())

    assert data["event"] == "json_test_event"
    assert data["task"] == "logging"
    assert data["level"] == "info"


def test_exception_logging(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.logging.settings.log_format", "console")
    monkeypatch.setattr("app.core.logging.settings.log_level", "ERROR")

    setup_logging()

    logger = get_logger("test_exception")

    try:
        raise ValueError("test exception")
    except ValueError:
        logger.exception("exception_test_event")

    captured = capsys.readouterr()

    assert "exception_test_event" in captured.out
    assert "ValueError" in captured.out
    assert "test exception" in captured.out
