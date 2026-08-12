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
class ScmSettings:
    """Strata Cloud Manager credentials and defaults.

    Storing client_secret here is supported but not encouraged: the environment
    is the better home for it, and resolve() in importer/scm/config.py takes the
    environment over this file. The URLs are settings rather than constants
    because the auth and instance hosts differ on non-production tenants.
    """

    client_id: str | None = None
    client_secret: str | None = None
    tsg_id: str | None = None
    auth_url: str = "https://auth.apps.paloaltonetworks.com"
    mfe_url: str = "https://api.apps.paloaltonetworks.com/mfe/instances"
    folder: str = "Prisma Access"

    def __repr__(self) -> str:
        """Never print the secret.

        A dataclass repr lands in tracebacks, log records and pytest output. The
        secret is replaced rather than shortened: a prefix is still a leak. This
        `Settings` object lives in the CLI context (`ctx.obj["settings"]`) for
        the whole run, so it is one accidental `%r` or debug dump away from a
        leak -- the same rule importer/scm/config.py's `ScmConfig` obeys.

        This only guards repr()/str()/f-string interpolation. dataclasses.asdict(),
        dataclasses.astuple() and vars() all bypass __repr__ and return
        client_secret in plaintext -- do not reach for those on a ScmSettings.
        """
        return (
            f"ScmSettings(client_id={self.client_id!r}, client_secret='***', "
            f"tsg_id={self.tsg_id!r}, auth_url={self.auth_url!r}, mfe_url={self.mfe_url!r}, "
            f"folder={self.folder!r})"
        )


@dataclass
class Settings:
    log: LogSettings = field(default_factory=LogSettings)
    scm: ScmSettings = field(default_factory=ScmSettings)
    source: pathlib.Path | None = None


def _as_bool(value: Any, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _or_default(raw: dict[str, Any], key: str, default: str) -> str:
    """Read a string setting, treating an explicit ``null`` as "not set".

    ``dict.get(key, default)`` only substitutes ``default`` when ``key`` is
    absent; a key present with value ``None`` (an explicit ``key: null`` in
    YAML) sails straight through and gets stringified to the literal text
    "None" by ``str()``. A settings file rendered from a template with an
    unset variable produces exactly that YAML, so this is not a hypothetical:
    it silently turns into "None", which downstream code treats as a truthy
    string. None of the fields that use this helper have a meaningful empty
    string, so falling back on any falsy value (`` or default``) is safe and
    simpler than a dedicated ``is None`` check.
    """
    return str(raw.get(key) or default)


def _int_or_default(raw: dict[str, Any], key: str, default: int) -> int:
    """As :func:`_or_default`, but for the integer rotate.* settings.

    ``int(rotate.get(key, default))`` has the same "present but null" gap,
    and there ``int(None)`` doesn't even get a wrong answer -- it raises
    ``TypeError`` and takes the whole load() down with it.
    """
    value = raw.get(key)
    return int(value) if value is not None else default


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
        level=_or_default(log_raw, "level", defaults.level).lower(),
        file=_as_bool(log_raw.get("file"), defaults.file),
        dir=pathlib.Path(str(log_raw["dir"])).expanduser() if log_raw.get("dir") else defaults.dir,
        json=_as_bool(log_raw.get("json"), defaults.json),
        max_bytes=_int_or_default(rotate, "max_bytes", defaults.max_bytes),
        backups=_int_or_default(rotate, "backups", defaults.backups),
    )
    scm_raw = raw.get("scm") or {}
    if not isinstance(scm_raw, dict):
        raise ValueError(f"{path}: 'scm' must be a mapping")

    scm_defaults = ScmSettings()
    known = {"client_id", "client_secret", "tsg_id", "auth_url", "mfe_url", "folder"}
    unknown_scm = set(scm_raw) - known
    if unknown_scm:
        raise ValueError(f"{path}: unknown scm setting(s): {', '.join(sorted(unknown_scm))}")

    def _str_or_none(key: str) -> str | None:
        value = scm_raw.get(key)
        return None if value is None else str(value)

    scm = ScmSettings(
        client_id=_str_or_none("client_id"),
        client_secret=_str_or_none("client_secret"),
        # str(): YAML reads a bare tsg id as an int, and it is a scope suffix.
        tsg_id=_str_or_none("tsg_id"),
        auth_url=_or_default(scm_raw, "auth_url", scm_defaults.auth_url),
        mfe_url=_or_default(scm_raw, "mfe_url", scm_defaults.mfe_url),
        folder=_or_default(scm_raw, "folder", scm_defaults.folder),
    )

    return Settings(log=log, scm=scm, source=path)
