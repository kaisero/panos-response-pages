"""Scope policy and per-page upload."""

import pathlib
from dataclasses import replace

import pytest

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer.catalogue import BY_REMOTE
from panos_response_pages.importer.scm.client import PageState
from panos_response_pages.importer.scm.config import ScmConfig
from panos_response_pages.importer.scm.target import PORTAL_FOLDER, ScmTarget
from panos_response_pages.importer.source import ImportItem

pytestmark = pytest.mark.unit

CFG = ScmConfig(
    client_id="a@b.iam.panserviceaccount.com",
    client_secret="s3cret",
    tsg_id="111",
    auth_url="https://auth.example",
    mfe_url="https://api.example/mfe/instances",
    folder="Prisma Access",
)


def item(remote: str, payload: bytes = b"hello") -> ImportItem:
    return ImportItem(spec=BY_REMOTE[remote], path=pathlib.Path(f"/tmp/{remote}"), payload=payload)  # noqa: S108


class FakeClient:
    """Records writes and answers reads from what it was told to hold."""

    def __init__(self, after: PageState | None = None, fail: Exception | None = None):
        self.writes: list[tuple[str, str, str]] = []
        self._after = after
        self._fail = fail

    def config_host(self) -> str:
        return "paas-4.prod.panorama.paloaltonetworks.com"

    def get_page(self, page: str, folder: str) -> PageState:
        if self._after is not None:
            return self._after
        content = self.writes[-1][2] if self.writes else None
        return PageState(present=content is not None, content=content, loc=folder, inherited=False)

    def put_page(self, page: str, folder: str, encoded: str) -> str:
        if self._fail:
            raise self._fail
        self.writes.append((page, folder, encoded))
        return "21643"


def test_response_pages_go_to_the_configured_folder():
    target = ScmTarget(CFG, FakeClient())
    assert target.folder_for(item("url-block-page")) == "Prisma Access"


def test_response_pages_follow_a_custom_folder():
    target = ScmTarget(replace(CFG, folder="Lab"), FakeClient())
    assert target.folder_for(item("url-block-page")) == "Lab"


def test_portal_pages_are_locked_to_mobile_users_whatever_the_folder_setting():
    # Writing a portal page to the wrong folder cannot be undone through this
    # API and permanently blocks the correct folder. The lock is the safeguard.
    target = ScmTarget(replace(CFG, folder="Lab"), FakeClient())
    assert target.folder_for(item("global-protect-portal-custom-home-page")) == PORTAL_FOLDER


def test_upload_writes_and_reports_success():
    client = FakeClient()
    result = ScmTarget(CFG, client).upload(item("url-block-page"))
    assert result.ok is True
    assert result.folder == "Prisma Access"
    assert result.mutation_id == "21643"
    assert client.writes[0][0] == "url-block-page"


def test_upload_sends_base64_of_the_payload():
    client = FakeClient()
    ScmTarget(CFG, client).upload(item("url-block-page", b"ABC"))
    assert client.writes[0][2] == "QUJD"


def test_verification_fails_when_the_readback_differs():
    client = FakeClient(after=PageState(present=True, content="WRONG", loc="Prisma Access", inherited=False))
    result = ScmTarget(CFG, client).upload(item("url-block-page"))
    assert result.ok is False
    assert "did not match" in result.detail


def test_verification_fails_when_the_value_is_inherited_from_another_folder():
    # The content matches, but it is the parent's value showing through -- the
    # write did not land in this folder.
    encoded = "aGVsbG8="
    client = FakeClient(after=PageState(present=True, content=encoded, loc="Prisma Access", inherited=True))
    target = ScmTarget(replace(CFG, folder="Mobile Users"), client)
    result = target.upload(item("url-block-page"))
    assert result.ok is False
    assert "inherited from Prisma Access" in result.detail


def test_api_failure_becomes_a_failed_result_not_an_exception():
    client = FakeClient(fail=ImportFailed("HTTP 400: nope"))
    result = ScmTarget(CFG, client).upload(item("url-block-page"))
    assert result.ok is False
    assert "HTTP 400" in result.detail


def test_describe_names_the_tenant_host_and_folder():
    text = ScmTarget(CFG, FakeClient()).describe()
    assert "111" in text and "paas-4" in text and "Prisma Access" in text
    assert "s3cret" not in text
