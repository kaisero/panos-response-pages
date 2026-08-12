"""Turning one loaded page into one write, and proving it landed.

The scope policy lives here rather than in the client because it is a product
decision, not an API fact: the API will happily write a GlobalProtect portal
page into any folder. Doing so is unrecoverable -- the object name must be
unique across the folder tree, and this API has no working delete -- so the
portal folder is fixed and no flag may override it.
"""

from __future__ import annotations

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.catalogue import PORTAL
from panos_response_pages.importer.report import PageResult
from panos_response_pages.importer.scm.client import ScmClient
from panos_response_pages.importer.scm.config import ScmConfig
from panos_response_pages.importer.source import ImportItem

# GlobalProtect portal pages live here and nowhere else. Not configurable: see
# the module docstring.
PORTAL_FOLDER = "Mobile Users"


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

    def folder_for(self, item: ImportItem) -> str:
        return PORTAL_FOLDER if item.spec.family == PORTAL else self._config.folder

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
                detail=f"the value in {folder!r} is inherited from {state.loc} -- the write did not land here",
            )

        return PageResult(
            page=item.spec.remote, folder=folder, ok=True, mutation_id=mutation_id, size=len(item.payload)
        )
