"""GDP Agent 独立文件日志配置。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from deerflow.config.app_config import logging_level_from_config

GDP_AGENT_LOG_FILE: Final = "gdpagents.log"
GDP_AGENT_LOGGER_NAMES: Final = ("app.gdp.agent_runtime",)
_HANDLER_MARKER: Final = "_gdp_agent_log_file"
_LOG_FORMAT: Final = "%(asctime)s - %(gdp_logger_name)s - %(gdp_level_name)s - %(message)s"
_DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"

_LEVEL_TEXT: Final = {
    "DEBUG": "调试",
    "INFO": "信息",
    "WARNING": "警告",
    "ERROR": "错误",
    "CRITICAL": "严重",
}

_LOGGER_TEXT: Final = {
    "app.gdp.agent_runtime": "GDP Agent 运行时",
    "app.gdp.agent_runtime.api": "GDP Agent 运行时接口",
    "app.gdp.agent_runtime.runner": "GDP Agent 运行时主流程",
    "app.gdp.agent_runtime.execution": "GDP Agent 运行时执行器",
    "app.gdp.agent_runtime.adapters.scene": "GDP Agent 场景适配器",
}


class GdpAgentLogFormatter(logging.Formatter):
    """为 gdpagents.log 补充中文模块名和日志级别。"""

    def format(self, record: logging.LogRecord) -> str:
        record.gdp_logger_name = _describe_logger_name(record.name)
        record.gdp_level_name = _LEVEL_TEXT.get(record.levelname, record.levelname)
        return super().format(record)


def configure_gdp_agent_file_logging(
    log_level: str | None,
    log_file: str | Path = GDP_AGENT_LOG_FILE,
) -> Path:
    """为 GDP Agent logger 树挂载独立文件日志 handler。"""
    level = logging_level_from_config(log_level)
    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = GdpAgentLogFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    for logger_name in GDP_AGENT_LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        handler = _find_existing_file_handler(logger, log_path)
        if handler is None:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            setattr(handler, _HANDLER_MARKER, str(log_path))
            logger.addHandler(handler)
        handler.setLevel(level)
        handler.setFormatter(formatter)

    return log_path


def _describe_logger_name(logger_name: str) -> str:
    if logger_name in _LOGGER_TEXT:
        return _LOGGER_TEXT[logger_name]
    if logger_name.startswith("app.gdp.agent_runtime."):
        suffix = logger_name.removeprefix("app.gdp.agent_runtime.")
        return f"GDP Agent 运行时/{suffix}"
    return logger_name


def _find_existing_file_handler(
    logger: logging.Logger,
    log_path: Path,
) -> logging.FileHandler | None:
    for handler in logger.handlers:
        marker = getattr(handler, _HANDLER_MARKER, None)
        if marker == str(log_path):
            return handler
        if isinstance(handler, logging.FileHandler):
            try:
                if Path(handler.baseFilename).resolve() == log_path:
                    setattr(handler, _HANDLER_MARKER, str(log_path))
                    return handler
            except OSError:
                continue
    return None
