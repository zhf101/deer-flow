from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.gdp.agent_logging import GDP_AGENT_LOGGER_NAMES, configure_gdp_agent_file_logging


@pytest.fixture()
def restore_gdp_agent_loggers() -> Iterator[None]:
    original_levels = {
        logger_name: logging.getLogger(logger_name).level
        for logger_name in GDP_AGENT_LOGGER_NAMES
    }
    original_handlers = {
        logger_name: list(logging.getLogger(logger_name).handlers)
        for logger_name in GDP_AGENT_LOGGER_NAMES
    }

    yield

    for logger_name in GDP_AGENT_LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        for handler in list(logger.handlers):
            if handler not in original_handlers[logger_name]:
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(original_levels[logger_name])


def _file_handlers(logger_name: str, log_path: Path) -> list[logging.FileHandler]:
    return [
        handler
        for handler in logging.getLogger(logger_name).handlers
        if isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == log_path
    ]


def test_configure_gdp_agent_file_logging_writes_runtime_logs(
    tmp_path: Path,
    restore_gdp_agent_loggers: None,
) -> None:
    log_path = tmp_path / "gdpagents.log"

    resolved_log_path = configure_gdp_agent_file_logging("debug", log_path)
    configure_gdp_agent_file_logging("debug", log_path)

    assert resolved_log_path.name == "gdpagents.log"
    for logger_name in GDP_AGENT_LOGGER_NAMES:
        assert logging.getLogger(logger_name).level == logging.DEBUG
        assert len(_file_handlers(logger_name, resolved_log_path)) == 1

    logging.getLogger("app.gdp.agent_runtime.runner").debug("runtime log probe")
    for logger_name in GDP_AGENT_LOGGER_NAMES:
        for handler in _file_handlers(logger_name, resolved_log_path):
            handler.flush()

    content = resolved_log_path.read_text(encoding="utf-8")
    assert "GDP Agent 运行时主流程" in content
    assert "调试" in content
    assert "runtime log probe" in content
