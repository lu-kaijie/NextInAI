"""Unified runtime logging helpers for NextInAI."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Callable, TypeVar

from nextinai.core.config import get_settings

_CONFIGURED = False
_LOG_FILE_NAME = "nextinai.log"
T = TypeVar("T")


def configure_logging() -> None:
    """Configure console and file logging once per process."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.data_dir / _LOG_FILE_NAME
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger("nextinai")
    root_logger.setLevel(level)
    root_logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the nextinai namespace."""

    configure_logging()
    return logging.getLogger(f"nextinai.{name}")


def format_fields(**fields: object) -> str:
    """Render structured fields into compact text."""

    parts: list[str] = []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    return " | ".join(parts)


def log_event(logger: logging.Logger, message: str, **fields: object) -> None:
    suffix = format_fields(**fields)
    logger.info("%s%s", message, f" | {suffix}" if suffix else "")


def log_warning(logger: logging.Logger, message: str, **fields: object) -> None:
    suffix = format_fields(**fields)
    logger.warning("%s%s", message, f" | {suffix}" if suffix else "")


def log_error(logger: logging.Logger, message: str, **fields: object) -> None:
    suffix = format_fields(**fields)
    logger.error("%s%s", message, f" | {suffix}" if suffix else "")


def timed_call(logger: logging.Logger, label: str, func: Callable[[], T], **fields: object) -> T:
    """Log start/end around a function call and return its result."""

    log_event(logger, f"{label}开始", **fields)
    started_at = time.perf_counter()
    try:
        result = func()
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        log_error(logger, f"{label}失败", elapsed_ms=elapsed_ms, error=exc, **fields)
        raise
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    log_event(logger, f"{label}完成", elapsed_ms=elapsed_ms, **fields)
    return result


def build_progress_callback(
    logger: logging.Logger,
    callback: Callable[[str], None] | None = None,
) -> Callable[[str], None]:
    """Bridge internal progress updates to both logger and UI callback."""

    def _emit(message: str) -> None:
        log_event(logger, message)
        if callback is not None:
            callback(message)

    return _emit


def get_log_path() -> Path:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / _LOG_FILE_NAME


def tail_logs(limit: int = 200) -> list[str]:
    path = get_log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[-limit:]
