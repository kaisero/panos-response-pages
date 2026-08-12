"""Sending built pages to a management plane.

One backend today (`scm`), with `panos` and `panorama` to follow. The split is
core-versus-backend rather than a module per protocol: the catalogue, the source
loader, the report and the run loop are the same work regardless of what is
being talked to, and only the Target knows about hosts, scopes and auth.

Adding a backend is three things and no fourth: a module that provides a
`Target` (see `backend.py` for the contract) plus the pure `describe`/
`scope_for` a dry run needs, one entry in `TARGETS` below, and a CLI command
that parses its own flags, resolves its own config and calls
`run_import` -- there is no orchestration left to copy.
"""

from __future__ import annotations

from typing import Any

from panos_response_pages.importer.backend import Backend, Target
from panos_response_pages.importer.catalogue import CATALOGUE, PORTAL, RESPONSE, PageSpec
from panos_response_pages.importer.report import ImportReport, PageResult, format_report
from panos_response_pages.importer.run import run_import
from panos_response_pages.importer.scm import SCM
from panos_response_pages.importer.source import ImportItem, load

# Backend name -> backend, and the name is the `import <name>` subcommand.
# `Backend[Any]`, not a union: each backend carries its own config type, and
# they have nothing in common. The parameter is checked where it is known --
# `SCM` is declared `Backend[ScmConfig]` at its definition, which is also what
# forces mypy to check `ScmTarget` against the `Target` protocol -- and erased
# here, where a heterogeneous table cannot say more than "some config".
TARGETS: dict[str, Backend[Any]] = {SCM.name: SCM}

__all__ = [
    "CATALOGUE",
    "PORTAL",
    "RESPONSE",
    "TARGETS",
    "Backend",
    "ImportItem",
    "ImportReport",
    "PageResult",
    "PageSpec",
    "Target",
    "format_report",
    "load",
    "run_import",
]
