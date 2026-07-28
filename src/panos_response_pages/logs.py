"""Logging setup.

Named logs.py, not logging.py: a module named logging.py inside the package
shadows the stdlib module for anything doing a non-absolute import, and the
resulting failures are obscure.

Diagnostics go to stdout. The build's size report also goes to stdout because it
is the tool's product rather than chatter -- so ``--log-json`` suppresses the
report and emits everything as structured events instead, leaving exactly one
machine-readable stream rather than two interleaved formats.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from panos_response_pages.settings import Settings

LOGGER_NAME = "panos_response_pages"

_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}

# Attributes LogRecord always carries; anything else was passed via `extra` and
# is genuinely part of the event.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime", "taskName"})


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with any `extra` fields merged in."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def resolve_level(settings: Settings, verbose: int, quiet: bool) -> int:
    """CLI beats settings file, always.

    A -q in a shell script must not be undone by a settings file the operator
    forgot about.
    """
    if quiet:
        return logging.ERROR
    if verbose >= 2:
        return logging.DEBUG
    if verbose == 1:
        return logging.INFO
    return _LEVELS.get(settings.log.level, logging.WARNING)


def configure(
    settings: Settings, *, verbose: int = 0, quiet: bool = False, json_output: bool = False
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(resolve_level(settings, verbose, quiet))
    # Ours alone: a library that reconfigures the root logger surprises anything
    # that imports it.
    logger.propagate = False

    stream: logging.Handler
    if json_output:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(JsonFormatter())
    else:
        stream = RichHandler(
            console=Console(file=sys.stdout),
            show_path=False,
            rich_tracebacks=True,
            omit_repeated_times=False,
        )
        stream.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(stream)

    if settings.log.file:
        settings.log.dir.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            settings.log.dir / "panos-response-pages.log",
            maxBytes=settings.log.max_bytes,
            backupCount=settings.log.backups,
            encoding="utf-8",
        )
        rotating.setFormatter(
            JsonFormatter() if settings.log.json else logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
        )
        logger.addHandler(rotating)

    return logger


def get() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
