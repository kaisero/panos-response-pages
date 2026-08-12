"""The import command, driven through Typer with the network stubbed."""

import pathlib
import tempfile

import pytest
from typer.testing import CliRunner

from panos_response_pages import cli
from panos_response_pages.importer.report import PageResult

pytestmark = pytest.mark.cli

runner = CliRunner()
GOOD = "<!DOCTYPE html><html><body><p>blocked <user/> <url/> <category/></p></body></html>"


def build_dir() -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "url-block-page.html").write_text(GOOD, encoding="utf-8")
    return root


ENV = {
    "SCM_CLIENT_ID": "a@b.iam.panserviceaccount.com",
    "SCM_CLIENT_SECRET": "s3cret",
    "SCM_TSG_ID": "111",
}


def test_missing_credentials_exit_nonzero_and_explain(monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("panos_response_pages.settings.SETTINGS_FILE", pathlib.Path("/nonexistent/settings.yaml"))
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(build_dir())])
    assert result.exit_code == 1
    assert "SCM_CLIENT_ID" in result.output


def test_dry_run_lists_pages_without_building_a_client(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    def boom(*args, **kwargs):
        raise AssertionError("a dry run must not open a connection")

    monkeypatch.setattr(cli, "_scm_target", boom)
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(build_dir()), "--dry-run"])
    assert result.exit_code == 0
    assert "url-block-page" in result.output
    assert "nothing was sent" in result.output


def test_successful_import_reports_and_exits_zero(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    class FakeTarget:
        name = "scm"

        def describe(self):
            return "tenant 111"

        def folder_for(self, item):
            return "Prisma Access"

        def upload(self, item):
            return PageResult(item.spec.remote, "Prisma Access", True, "21643", len(item.payload))

    monkeypatch.setattr(cli, "_scm_target", lambda cfg: FakeTarget())
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(build_dir())])
    assert result.exit_code == 0
    assert "imported 1/1" in result.output
    assert "not been pushed" in result.output


def test_a_failed_page_exits_nonzero(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    class FakeTarget:
        name = "scm"

        def describe(self):
            return "tenant 111"

        def folder_for(self, item):
            return "Prisma Access"

        def upload(self, item):
            return PageResult(item.spec.remote, "Prisma Access", False, detail="HTTP 400")

    monkeypatch.setattr(cli, "_scm_target", lambda cfg: FakeTarget())
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(build_dir())])
    assert result.exit_code == 1
    assert "HTTP 400" in result.output


def test_a_page_that_would_fail_on_panos_stops_the_import(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "url-block-page.html").write_text("<html><body><a href='https://x'>x</a></body></html>", encoding="utf-8")
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(root)])
    assert result.exit_code == 1
    assert "--skip-validate" in result.output


def test_skip_validate_allows_it(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "url-block-page.html").write_text("<html><body><a href='https://x'>x</a></body></html>", encoding="utf-8")
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(root), "--skip-validate", "--dry-run"])
    assert result.exit_code == 0
