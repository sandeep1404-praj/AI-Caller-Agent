"""Logging configuration for Class Call Agent."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGER_INITIALIZED = False


def configure_logging(logs_dir: Path, level: str = "INFO") -> logging.Logger:
    """Configure application-wide logging once and return the root logger."""

    global _LOGGER_INITIALIZED

    logger = logging.getLogger("caller_agent")
    if _LOGGER_INITIALIZED:
        return logger

    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        logs_dir / "caller_agent.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    errors_handler = RotatingFileHandler(
        logs_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(errors_handler)
    _LOGGER_INITIALIZED = True
    return logger
