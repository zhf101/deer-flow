"""GDP Agent 独立文件日志配置。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from deerflow.config.app_config import logging_level_from_config

GDP_AGENT_LOG_FILE: Final = "gdpagents.log"
GDP_AGENT_LOGGER_NAMES: Final = ("app.gdp.agent_runtime", "app.gdp.agent")
_HANDLER_MARKER: Final = "_gdp_agent_log_file"
_LOG_FORMAT: Final = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"


def configure_gdp_agent_file_logging(
    log_level: str | None,
    log_file: str | Path = GDP_AGENT_LOG_FILE,
) -> Path:
    """为 GDP Agent logger 树挂载独立文件日志 handler。"""
    level = logging_level_from_config(log_level)
    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

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
