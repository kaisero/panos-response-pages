"""What can be imported, under what remote name, and in which family.

The remote names are not a new vocabulary. PAGE_TOKENS already spells the block
pages exactly as SCM's `blockPage` enum does, and cli.PORTAL_PAGES already
carries the two GlobalProtect object names. This module states that
correspondence once; test_import_catalogue.py fails if either side drifts.

Family matters because the two are not interchangeable at the API: a response
page is an overwritable value, a portal page is a named object whose name must
be unique across the folder tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from panos_response_pages.validate import PAGE_TOKENS

RESPONSE = "response"
PORTAL = "portal"


@dataclass(frozen=True)
class PageSpec:
    """One importable page.

    `local` is relative to a built variant directory, so it carries the
    `portal/` prefix for the GlobalProtect imports -- that is exactly where
    `build` writes them.
    """

    local: str
    remote: str
    family: str


# Imported here rather than from cli.py: importing the CLI to build a data table
# would make every consumer of the catalogue pull in Typer. The test asserts the
# two agree, which is the same guarantee without the import.
_PORTAL_OBJECTS = {
    "home": "global-protect-portal-custom-home-page",
    "login": "global-protect-portal-custom-login-page",
}

CATALOGUE: tuple[PageSpec, ...] = (
    *(PageSpec(local=f"{name}.html", remote=name, family=RESPONSE) for name in sorted(PAGE_TOKENS)),
    *(
        PageSpec(local=f"portal/{local}.html", remote=remote, family=PORTAL)
        for local, remote in sorted(_PORTAL_OBJECTS.items())
    ),
)

BY_LOCAL: dict[str, PageSpec] = {s.local: s for s in CATALOGUE}
BY_REMOTE: dict[str, PageSpec] = {s.remote: s for s in CATALOGUE}
