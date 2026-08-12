"""The import catalogue must not invent a second set of page names.

PAGE_TOKENS and cli.PORTAL_PAGES already carry the names PAN-OS and SCM use.
If the catalogue drifts from either, an import silently stops covering a page
-- or targets one that does not exist -- so both correspondences are pinned.
"""

import pytest

from panos_response_pages.cli import PORTAL_PAGES
from panos_response_pages.importer.catalogue import BY_LOCAL, BY_REMOTE, CATALOGUE, PORTAL, RESPONSE
from panos_response_pages.validate import PAGE_TOKENS

pytestmark = pytest.mark.unit


def test_every_block_page_is_in_the_catalogue():
    remote = {s.remote for s in CATALOGUE if s.family == RESPONSE}
    assert remote == set(PAGE_TOKENS), "catalogue and PAGE_TOKENS disagree about the block pages"


def test_response_pages_map_filename_to_the_same_name():
    for spec in CATALOGUE:
        if spec.family == RESPONSE:
            assert spec.local == f"{spec.remote}.html"


def test_portal_pages_match_the_cli_table():
    expected = {f"portal/{local}.html": obj for local, (obj, _serves, _vars) in PORTAL_PAGES.items()}
    got = {s.local: s.remote for s in CATALOGUE if s.family == PORTAL}
    assert got == expected


def test_lookups_cover_every_spec():
    assert len(BY_LOCAL) == len(CATALOGUE)
    assert len(BY_REMOTE) == len(CATALOGUE)
    assert BY_REMOTE["url-block-page"].local == "url-block-page.html"
    assert BY_LOCAL["portal/home.html"].remote == "global-protect-portal-custom-home-page"
