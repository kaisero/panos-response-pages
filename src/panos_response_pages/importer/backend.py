"""The contract a backend satisfies, and the record that registers one.

Two halves, deliberately apart.

`Target` is the *live* half: an open connection that writes pages and is closed
when the run ends. `Backend` is the *offline* half: a backend's name, how to
describe a config it has not contacted, which scope a page belongs in, and how
to connect once a real run needs to.

The split is what makes `--dry-run` honest. A dry run must contact nothing --
no `Target` is constructed and no request is made -- yet it has to report the
same scopes a real run would write to, because a dry run is where an operator
checks an irreversible write before committing to it. So everything a dry run
needs (`name`, `describe`, `scope_for`) is a pure function of the config, and
everything that touches the network sits behind `connect`. A new backend that
puts network I/O in `describe` or `scope_for` breaks that guarantee silently.

`upload()` is the other load-bearing contract: it must never raise. One page is
one mutation, so a failure is recorded as a failed `PageResult` and the run
carries on with the remaining pages instead of abandoning them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from panos_response_pages.importer.report import PageResult
from panos_response_pages.importer.source import ImportItem


class Target(Protocol):
    """A connected management plane, for the duration of one import run."""

    name: str

    def describe(self) -> str:
        """One human-readable line (or few) naming what is about to be written to.

        Free to make requests -- SCM's resolves the tenant's API host -- so a
        caller must be prepared for it to fail and must still close the target.
        """
        ...

    def upload(self, item: ImportItem) -> PageResult:
        """Write one page and verify it, converting any failure into a result.

        Never raises: see the module docstring.
        """
        ...

    def close(self) -> None:
        """Release whatever `connect` opened. Called on every path, including failure."""
        ...


# The config type is backend-specific -- ScmConfig here, something else for a
# future `panos` backend -- so `Backend` is generic in it. That keeps the three
# callables of one backend checked against each other and against `Target` at
# the point of registration, which is the only place the concrete type is known.
C = TypeVar("C")


@dataclass
class Backend(Generic[C]):
    """One backend, registered in `TARGETS` and handed to the shared runner.

    Not frozen: tests substitute `connect` with `monkeypatch.setattr` to prove a
    dry run never reaches it, and to drive a whole run against a fake target.
    That seam is the reason this is a record of callables rather than a class
    with methods -- there is exactly one thing to replace, and replacing it
    cannot accidentally leave a live client behind.
    """

    name: str
    describe: Callable[[C], str]
    """Dry-run header. Pure: it must not contact the target it is describing."""

    scope_for: Callable[[C, ImportItem], str]
    """Where one page will be written -- folder, vsys, device group. Pure, and
    shared with the live path, so a dry run cannot report a different scope from
    the one an upload would use."""

    connect: Callable[[C], Target]
    """Build the live object graph. The only member allowed to open a connection."""
