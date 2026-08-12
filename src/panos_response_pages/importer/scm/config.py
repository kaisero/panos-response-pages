"""Resolved SCM credentials, and the precedence that produced them.

CLI flag > environment > settings.yaml > built-in default -- the same order the
tool already applies to logging, for the same reason: a value passed explicitly
on the command line must never be overridden by a file someone left behind.

Environment names are the unprefixed SCM_* set used by the Terraform provider
and the other SCM tooling in this ecosystem, so one exported environment serves
all of them. They are read from an injected mapping rather than os.environ
directly, which is what makes the precedence testable without monkeypatching.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from panos_response_pages.errors import ImportFailed
from panos_response_pages.settings import ScmSettings

# The fourth precedence layer: built-in defaults, sourced from ScmSettings'
# own field defaults so there is exactly one place that spells them out.
_DEFAULTS = ScmSettings()

# field name -> (environment variable, CLI flag) for the error message.
_SOURCES = {
    "client_id": ("SCM_CLIENT_ID", "--client-id"),
    "client_secret": ("SCM_CLIENT_SECRET", "--client-secret"),
    "tsg_id": ("SCM_TSG_ID", "--tsg-id"),
}


@dataclass(frozen=True)
class ScmConfig:
    """Everything needed to talk to one tenant."""

    client_id: str
    client_secret: str
    tsg_id: str
    auth_url: str
    mfe_url: str
    folder: str

    @property
    def scope(self) -> str:
        return f"tsg_id:{self.tsg_id}"

    def __repr__(self) -> str:
        """Never print the secret.

        A dataclass repr lands in tracebacks, log records and pytest output. The
        secret is replaced rather than shortened: a prefix is still a leak.

        This only guards repr()/str()/f-string interpolation. dataclasses.asdict(),
        dataclasses.astuple() and vars() all bypass __repr__ and return
        client_secret in plaintext -- do not reach for those on a ScmConfig.
        """
        return (
            f"ScmConfig(client_id={self.client_id!r}, client_secret='***', "
            f"tsg_id={self.tsg_id!r}, folder={self.folder!r})"
        )


def _pick(flag: str | None, env: Mapping[str, str], env_key: str, file_value: str | None) -> str | None:
    if flag:
        return flag
    if env.get(env_key):
        return env[env_key]
    return file_value


def resolve(
    scm: ScmSettings,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    tsg_id: str | None = None,
    folder: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ScmConfig:
    """Merge the three layers, or explain precisely what is missing."""
    env = os.environ if env is None else env

    resolved = {
        "client_id": _pick(client_id, env, "SCM_CLIENT_ID", scm.client_id),
        "client_secret": _pick(client_secret, env, "SCM_CLIENT_SECRET", scm.client_secret),
        "tsg_id": _pick(tsg_id, env, "SCM_TSG_ID", scm.tsg_id),
    }

    missing = [name for name, value in resolved.items() if not value]
    if missing:
        lines = [f"  {name}: set {_SOURCES[name][0]}, pass {_SOURCES[name][1]}" for name in missing]
        raise ImportFailed(
            "missing SCM credential(s):\n"
            + "\n".join(lines)
            + "\n  ...or add them under `scm:` in ~/.panos_response_pages/settings.yaml"
        )

    # The trailing `or scm.<field>` this used to end with compared scm.<field>
    # against itself -- a no-op that can never supply an independent built-in
    # value. `_DEFAULTS.<field>` is the real fourth layer: it only kicks in
    # when the flag, environment and settings.yaml all agree on "unset".
    return ScmConfig(
        client_id=str(resolved["client_id"]),
        client_secret=str(resolved["client_secret"]),
        tsg_id=str(resolved["tsg_id"]),
        auth_url=_pick(None, env, "SCM_AUTH_URL", scm.auth_url) or _DEFAULTS.auth_url,
        mfe_url=_pick(None, env, "SCM_MFE_URL", scm.mfe_url) or _DEFAULTS.mfe_url,
        folder=_pick(folder, env, "SCM_FOLDER", scm.folder) or _DEFAULTS.folder,
    )
