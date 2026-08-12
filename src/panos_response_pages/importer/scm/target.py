"""Turning one loaded page into one write, and proving it landed.

The scope policy lives here rather than in the client because it is a product
decision, not an API fact: the API will happily write a GlobalProtect portal
page into any folder. Doing so is unrecoverable -- the object name must be
unique across the folder tree, and this API has no working delete -- so the
portal folder is fixed and no flag may override it.

This module is also where SCM registers itself: `SCM` at the bottom binds the
three offline capabilities (`describe`, `folder_for`, `connect`) that
`importer.run` drives. Annotating it `Backend[ScmConfig]` is what makes mypy
check `ScmTarget` against the `Target` protocol -- there is no explicit
inheritance to carry that check.
"""

from __future__ import annotations

import httpx

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.backend import Backend
from panos_response_pages.importer.catalogue import PORTAL
from panos_response_pages.importer.report import PageResult
from panos_response_pages.importer.scm.auth import TokenSource
from panos_response_pages.importer.scm.client import ScmClient
from panos_response_pages.importer.scm.config import ScmConfig
from panos_response_pages.importer.source import ImportItem

# GlobalProtect portal pages live here and nowhere else. Not configurable: see
# the module docstring. Kept in sync by hand with SCOPE_TYPES in
# scm/client.py -- that table's key must be this exact string, or Mobile
# Users writes get `type=container` and fail with a loud 400.
PORTAL_FOLDER = "Mobile Users"


def folder_for(config: ScmConfig, item: ImportItem) -> str:
    """Which folder one page belongs in -- the one statement of the portal-folder rule.

    Both `ScmTarget.upload()` (the live write) and the CLI's `--dry-run` report
    (which never builds a `ScmTarget`, and so cannot call the method) need this
    answer. A dry run is where an operator checks an irreversible write before
    committing to it, so it must be impossible for the two call sites to disagree
    -- hence one function, not a rule copied into each caller.
    """
    return PORTAL_FOLDER if item.spec.family == PORTAL else config.folder


def describe_config(config: ScmConfig) -> str:
    """What a dry run says it would write to. Says "not contacted" because it is true.

    The live counterpart is `ScmTarget.describe()`, which names the tenant's API
    host as well -- and can only do so by asking for it. This one must not, so
    it reports the tenant alone.
    """
    return f"tenant {config.tsg_id} (not contacted)"


class ScmTarget:
    """The Strata Cloud Manager import backend."""

    name = "scm"

    def __init__(self, config: ScmConfig, client: ScmClient):
        self._config = config
        self._client = client

    def describe(self) -> str:
        return (
            f"tenant {self._config.tsg_id} at {self._client.config_host()}\n"
            f"  response pages -> folder {self._config.folder!r}\n"
            f"  portal pages   -> folder {PORTAL_FOLDER!r} (fixed)"
        )

    def close(self) -> None:
        """Release the underlying HTTP connection pool.

        `connect()` below is the only place that constructs one of these
        against a real network client, and it has no other handle to close it
        with -- so `importer.run.run_import` closes whatever `connect()` handed
        it, on every path, and the close travels down to the `httpx.Client`
        from here.
        """
        self._client.close()

    def folder_for(self, item: ImportItem) -> str:
        return folder_for(self._config, item)

    def upload(self, item: ImportItem) -> PageResult:
        """Write one page and verify it, converting any API failure to a result.

        A raised exception would abandon the remaining pages. Each page is
        independent -- one mutation per write, no batching -- so a failure is
        recorded and the run continues.
        """
        folder = self.folder_for(item)
        encoded = item.encoded
        try:
            mutation_id = self._client.put_page(item.spec.remote, folder, encoded)
        except ImportFailed as exc:
            return PageResult(page=item.spec.remote, folder=folder, ok=False, detail=str(exc))

        try:
            state = self._client.get_page(item.spec.remote, folder)
        except ImportFailed as exc:
            return PageResult(
                page=item.spec.remote,
                folder=folder,
                ok=False,
                mutation_id=mutation_id,
                detail=f"written, but could not be read back: {exc}",
            )

        if not state.present:
            return PageResult(
                page=item.spec.remote,
                folder=folder,
                ok=False,
                mutation_id=mutation_id,
                detail="the write was accepted, but the page is absent on read-back",
            )
        if state.content != encoded:
            return PageResult(
                page=item.spec.remote,
                folder=folder,
                ok=False,
                mutation_id=mutation_id,
                detail="the page read back did not match what was sent",
            )
        if state.inherited:
            return PageResult(
                page=item.spec.remote,
                folder=folder,
                ok=False,
                mutation_id=mutation_id,
                detail=f"the value in {folder!r} is inherited from {state.loc!r} -- the write did not land here",
            )

        return PageResult(
            page=item.spec.remote, folder=folder, ok=True, mutation_id=mutation_id, size=len(item.payload)
        )


def connect(config: ScmConfig) -> ScmTarget:
    """Build a live SCM target: one httpx client, shared by auth and the config API.

    One client for both, so a single `close()` releases the whole connection
    pool -- ScmClient.close() and ScmTarget.close() both rely on that. Never
    called by a dry run; `importer.run` reaches it only on a real run, and the
    CLI tests substitute it to prove so.
    """
    client = httpx.Client()
    return ScmTarget(config, ScmClient(config, TokenSource(config, client), client))


# The registry entry. Everything above it is either pure (folder_for,
# describe_config -- what a dry run needs) or behind connect (what a real run
# needs); this line is the only place the two halves are named together.
SCM: Backend[ScmConfig] = Backend(
    name=ScmTarget.name,
    describe=describe_config,
    scope_for=folder_for,
    connect=connect,
)
