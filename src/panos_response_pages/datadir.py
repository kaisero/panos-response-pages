"""Where the shells, palettes, themes and default config are read from.

Resolution order, first hit wins, resolved as a whole tree rather than per file:

1. an explicit path (``--config-dir`` / ``$PANOS_RESPONSE_PAGES_DIR``)
2. ``~/.panos_response_pages``, if it exists
3. the data shipped inside this package

Whole-tree because themes and shells are coupled: a local ``themes/`` over a
packaged ``templates/shells/`` would let a theme name a shell that is not there.

Always a real ``pathlib.Path``. ``importlib.resources.files()`` returns a
``Traversable``, which is not ``os.PathLike`` in general -- ``init`` needs
``shutil.copytree`` and ``--config-dir`` needs ``Path`` parity. This package is
never zip-imported, so ``Path(__file__).parent`` is both correct and honest.
"""

from __future__ import annotations

import os
import pathlib

ENV_VAR = "PANOS_RESPONSE_PAGES_DIR"
USER_DIR = pathlib.Path.home() / ".panos_response_pages"
PACKAGED = pathlib.Path(__file__).parent / "data"

# Subdirectories that make a directory recognisably a data dir.
EXPECTED = ("templates", "palettes", "themes", "config", "fixtures")

# What the GlobalProtect portal family needs on top of that: its own templates,
# and the captured PAN-OS prefixes previews are spliced from. Both arrived after
# the block pages, so a data directory can be entirely valid for those and have
# neither of these.
PORTAL_EXPECTED = ("templates/portal", "fixtures")


def resolve(explicit: str | os.PathLike[str] | None = None) -> tuple[pathlib.Path, str]:
    """Return the data directory and a one-word description of why.

    The reason is returned rather than logged here so the caller can put it in
    ``--verbose`` output and in the build report: "which files did this actually
    use" is the first question when a build produces something unexpected.
    """
    if explicit is not None:
        return pathlib.Path(explicit).expanduser(), "explicit"
    env = os.environ.get(ENV_VAR)
    if env:
        return pathlib.Path(env).expanduser(), "environment"
    if USER_DIR.is_dir():
        return USER_DIR, "user"
    return PACKAGED, "packaged"


def portal_data(data_dir: pathlib.Path) -> pathlib.Path:
    """Where to read the portal templates and splice fixtures from.

    Normally ``data_dir`` itself. But ``resolve()`` takes a data directory whole,
    and anyone who ran ``init`` before the portal family existed has a
    ``~/.panos_response_pages`` with no ``templates/portal/`` and no
    ``fixtures/``. Reading those from it raises ``BuildError``, which would stop
    the *block* pages building too -- a family that user has been building
    happily for months, broken by an upgrade that added something else.

    So the portal falls back to the packaged data on its own, loudly. The
    fallback is deliberately not silent: the portal pages then ignore any theme
    or shell edits made in the user directory, and ``init --force`` is the fix.
    """
    if all((data_dir / sub).is_dir() for sub in PORTAL_EXPECTED):
        return data_dir

    from panos_response_pages import logs

    missing = ", ".join(sub for sub in PORTAL_EXPECTED if not (data_dir / sub).is_dir())
    logs.get().warning(
        "%s has no %s -- building the portal pages from the packaged data instead. "
        "Any portal edits there will be ignored; run `panos-response-pages init --force` to refresh it.",
        data_dir,
        missing,
    )
    return PACKAGED
