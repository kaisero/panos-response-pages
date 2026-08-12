"""The shared runner, driven by a backend that is not SCM.

This is the integration point a second backend (`panos`, `panorama`) plugs into,
written out in full: a config of its own shape, a pure `describe`, a pure
`scope_for`, a `connect` that hands back something satisfying the `Target`
protocol -- and nothing else. If a future backend needs more than what this file
defines to get a correct report, the seam has leaked and the runner is the place
to fix it, not the new backend.
"""

import pathlib
from dataclasses import dataclass

import pytest

from panos_response_pages.errors import ImportFailed
from panos_response_pages.importer import Backend, format_report, run_import
from panos_response_pages.importer.catalogue import BY_REMOTE
from panos_response_pages.importer.report import PageResult
from panos_response_pages.importer.source import ImportItem

pytestmark = pytest.mark.unit


@dataclass
class FakeConfig:
    """A backend's config is its own business -- this one looks nothing like ScmConfig."""

    device_group: str


def describe(config: FakeConfig) -> str:
    return f"appliance {config.device_group} (not contacted)"


def scope_for(config: FakeConfig, item: ImportItem) -> str:
    """Pure, and shared by the dry run and the live upload -- so the two agree."""
    return "shared" if item.spec.family == "portal" else config.device_group


class FakeTarget:
    """A live target. Satisfies the `Target` protocol structurally, as ScmTarget does."""

    name = "fake"

    def __init__(self, config: FakeConfig, fail: set[str] | None = None):
        self._config = config
        self._fail = fail or set()
        self.uploaded: list[str] = []
        self.closed = False

    def describe(self) -> str:
        return f"appliance {self._config.device_group} at 10.0.0.1"

    def upload(self, item: ImportItem) -> PageResult:
        # The contract: never raise. A failure is a failed result, so the
        # remaining pages still get their turn.
        self.uploaded.append(item.spec.remote)
        folder = scope_for(self._config, item)
        if item.spec.remote in self._fail:
            return PageResult(page=item.spec.remote, folder=folder, ok=False, detail="HTTP 400: nope")
        return PageResult(page=item.spec.remote, folder=folder, ok=True, size=len(item.payload))

    def close(self) -> None:
        self.closed = True


def backend(target: FakeTarget | None = None, *, connect_raises: Exception | None = None) -> Backend[FakeConfig]:
    def connect(config: FakeConfig) -> FakeTarget:
        if connect_raises is not None:
            raise connect_raises
        return target if target is not None else FakeTarget(config)

    return Backend(name="fake", describe=describe, scope_for=scope_for, connect=connect)


CONFIG = FakeConfig(device_group="Branch")
ITEMS = [
    ImportItem(spec=BY_REMOTE["url-block-page"], path=pathlib.Path("url-block-page.html"), payload=b"<html>1</html>"),
    ImportItem(
        spec=BY_REMOTE["global-protect-portal-custom-home-page"],
        path=pathlib.Path("portal/home.html"),
        payload=b"<html>22</html>",
    ),
]


def test_a_dry_run_reports_every_page_without_connecting():
    # The guarantee in one assertion: connect() raises, and the dry run still
    # produces the full report. A backend that reached the network from
    # describe() or scope_for() would fail here rather than in production.
    def boom(config: FakeConfig) -> FakeTarget:
        raise AssertionError("a dry run must not connect")

    fake = Backend(name="fake", describe=describe, scope_for=scope_for, connect=boom)

    report = run_import(fake, CONFIG, ITEMS, dry_run=True)

    assert report.dry_run is True
    assert report.target == "fake"
    assert report.describe == "appliance Branch (not contacted)"
    assert [(r.page, r.folder, r.ok, r.size) for r in report.results] == [
        ("url-block-page", "Branch", True, 14),
        ("global-protect-portal-custom-home-page", "shared", True, 15),
    ]
    assert report.failed is False

    text = format_report(report)
    assert "would import 2/2 page(s)" in text
    assert "nothing was sent" in text
    assert "not been pushed" not in text


def test_a_real_run_uploads_every_page_closes_the_target_and_reports_it():
    target = FakeTarget(CONFIG)

    report = run_import(backend(target), CONFIG, ITEMS)

    assert report.dry_run is False
    assert report.describe == "appliance Branch at 10.0.0.1"
    assert target.uploaded == ["url-block-page", "global-protect-portal-custom-home-page"]
    assert target.closed is True
    assert report.ok_count == 2
    assert report.failed is False
    assert "imported 2/2 page(s)" in format_report(report)


def test_the_dry_run_and_the_real_run_agree_on_every_scope():
    # The reason scope_for is pure and shared. An operator checks an
    # irreversible write by dry-running it first; a scope that differed between
    # the two would make that check worthless.
    planned = run_import(backend(), CONFIG, ITEMS, dry_run=True)
    actual = run_import(backend(), CONFIG, ITEMS)
    assert [r.folder for r in planned.results] == [r.folder for r in actual.results]


def test_a_failed_page_does_not_abandon_the_rest():
    target = FakeTarget(CONFIG, fail={"url-block-page"})

    report = run_import(backend(target), CONFIG, ITEMS)

    assert target.uploaded == ["url-block-page", "global-protect-portal-custom-home-page"]
    assert [r.ok for r in report.results] == [False, True]
    assert report.failed is True
    assert "not been pushed" not in format_report(report)


def test_the_target_is_closed_even_when_describe_fails():
    class Unreachable(FakeTarget):
        def describe(self) -> str:
            raise ImportFailed("HTTP 401")

    target = Unreachable(CONFIG)
    with pytest.raises(ImportFailed):
        run_import(backend(target), CONFIG, ITEMS)
    assert target.closed is True
    assert target.uploaded == []


def test_a_failure_to_connect_needs_nothing_closed():
    # connect() raised, so there is nothing to release -- the runner must not
    # try to close a target it never got.
    with pytest.raises(ImportFailed):
        run_import(backend(connect_raises=ImportFailed("no route to host")), CONFIG, ITEMS)
