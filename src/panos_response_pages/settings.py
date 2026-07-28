"""Tool settings from ``~/.panos_response_pages/settings.yaml``.

Named settings.yaml rather than config.yaml on purpose: the same directory holds
``config/*.json``, which is per-customer *page content* and the thing operators
edit daily. Two unrelated files one letter apart is a trap.

Every key is optional and the file itself is optional. Precedence is
CLI flag > environment > this file > built-in default, so a ``-q`` in a script
can never be overridden by a settings file someone left behind.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

from panos_response_pages.datadir import USER_DIR

SETTINGS_FILE = USER_DIR / "settings.yaml"
DEFAULT_LOG_DIR = USER_DIR / "logs"


@dataclass
class LogSettings:
    level: str = "warning"
    file: bool = False
    dir: pathlib.Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    json: bool = False
    max_bytes: int = 1_048_576
    backups: int = 5


@dataclass
class Settings:
    log: LogSettings = field(default_factory=LogSettings)
    source: pathlib.Path | None = None


def _as_bool(value: Any, fallback: bool) -> bool:
    return bool(value) if isinstance(value, bool) else fallback


def load(path: pathlib.Path | None = None) -> Settings:
    """Read settings, tolerating absence and partial files.

    A malformed settings file raises rather than being silently ignored: a
    typo'd key that quietly does nothing is how people end up believing file
    logging is on when it is not.
    """
    path = path or SETTINGS_FILE
    if not path.is_file():
        return Settings()

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level, got {type(raw).__name__}")

    log_raw = raw.get("log") or {}
    if not isinstance(log_raw, dict):
        raise ValueError(f"{path}: 'log' must be a mapping")

    unknown = set(log_raw) - {"level", "file", "dir", "json", "rotate"}
    if unknown:
        raise ValueError(f"{path}: unknown log setting(s): {', '.join(sorted(unknown))}")

    rotate = log_raw.get("rotate") or {}
    defaults = LogSettings()
    log = LogSettings(
        level=str(log_raw.get("level", defaults.level)).lower(),
        file=_as_bool(log_raw.get("file"), defaults.file),
        dir=pathlib.Path(str(log_raw["dir"])).expanduser() if log_raw.get("dir") else defaults.dir,
        json=_as_bool(log_raw.get("json"), defaults.json),
        max_bytes=int(rotate.get("max_bytes", defaults.max_bytes)),
        backups=int(rotate.get("backups", defaults.backups)),
    )
    return Settings(log=log, source=path)
