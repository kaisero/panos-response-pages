"""The import command, driven through Typer with the network stubbed."""

import json
import pathlib
import tempfile

import pytest
from typer.testing import CliRunner

from panos_response_pages import cli
from panos_response_pages.importer.report import PageResult
from panos_response_pages.importer.scm.config import ScmConfig

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

        def upload(self, item):
            return PageResult(item.spec.remote, "Prisma Access", True, "21643", len(item.payload))

        def close(self):
            pass

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

        def upload(self, item):
            return PageResult(item.spec.remote, "Prisma Access", False, detail="HTTP 400")

        def close(self):
            pass

    monkeypatch.setattr(cli, "_scm_target", lambda cfg: FakeTarget())
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(build_dir())])
    assert result.exit_code == 1
    assert "HTTP 400" in result.output


def test_a_mixed_run_reports_both_pages_and_exits_nonzero(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    # Two pages, one mutation each: a real run can half-succeed. Reporting
    # success while one of them failed would be the worst outcome this
    # feature can produce, so both the exit code and the report itself must
    # show it.
    class FakeTarget:
        name = "scm"

        def describe(self):
            return "tenant 111"

        def upload(self, item):
            if item.spec.remote == "url-block-page":
                return PageResult(item.spec.remote, "Prisma Access", True, "21643", len(item.payload))
            return PageResult(item.spec.remote, "Prisma Access", False, detail="HTTP 400")

        def close(self):
            pass

    monkeypatch.setattr(cli, "_scm_target", lambda cfg: FakeTarget())
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "url-block-page.html").write_text(GOOD, encoding="utf-8")
    (root / "credential-block-page.html").write_text(GOOD, encoding="utf-8")
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(root)])
    assert result.exit_code == 1
    assert "url-block-page" in result.output
    assert "credential-block-page" in result.output


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
    # Not just a green exit code: a real assertion that the page actually made
    # it into the report, or --skip-validate silently dropping a page instead
    # of importing it would still pass.
    assert "url-block-page" in result.output


def test_a_failure_during_describe_still_closes_the_client(monkeypatch):
    # describe() is the first thing that touches the network (it calls
    # config_host()), so a bad credential or an unreachable tenant raises here,
    # before any upload happens. The client must still be closed on this path.
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    class FakeTarget:
        name = "scm"
        closed = False

        def describe(self):
            raise cli.ImportFailed("HTTP 401")

        def upload(self, item):  # pragma: no cover - never reached
            raise AssertionError("upload must not run when describe() failed")

        def close(self):
            self.closed = True

    target = FakeTarget()
    monkeypatch.setattr(cli, "_scm_target", lambda cfg: target)
    result = runner.invoke(cli.app, ["import", "scm", "--from", str(build_dir())])
    assert result.exit_code == 1
    assert target.closed is True


def test_dry_run_reports_the_portal_lock_and_the_configured_folder_separately(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    # A response page and a portal page in the same source directory, so one
    # dry run reports both folders and the two can be told apart. The portal
    # fixture is a minimal stub -- it need not pass validate_portal, since
    # --skip-validate is used to get past the PAN-OS guards.
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "url-block-page.html").write_text(GOOD, encoding="utf-8")
    (root / "portal").mkdir()
    (root / "portal" / "home.html").write_text("var logout_text_array = [];", encoding="utf-8")

    result = runner.invoke(
        cli.app,
        ["import", "scm", "--from", str(root), "--folder", "Lab", "--skip-validate", "--dry-run"],
    )
    assert result.exit_code == 0
    lines = result.output.splitlines()
    response_line = next(line for line in lines if "url-block-page" in line)
    portal_line = next(line for line in lines if "global-protect-portal-custom-home-page" in line)
    # The configured folder ("Lab") is distinct from the fixed portal folder
    # ("Mobile Users"), so a report that mixed them up would fail this.
    assert "Lab" in response_line
    assert "Mobile Users" in portal_line
    assert "Lab" not in portal_line


def test_log_json_suppresses_the_dry_run_report(monkeypatch):
    # --log-json promises exactly one machine-readable stream. Before the fix,
    # import scm echoed the human report unconditionally, so a JSON log line
    # and the human report landed on the same stream together.
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    result = runner.invoke(cli.app, ["--log-json", "import", "scm", "--from", str(build_dir()), "--dry-run"])
    assert result.exit_code == 0
    assert "would import" not in result.output
    assert "dry run" not in result.output
    for line in result.output.splitlines():
        json.loads(line)  # every line, if any, must be a JSON object -- not report text


def test_log_json_suppresses_the_final_report_and_logs_failures_as_events(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    class FakeTarget:
        name = "scm"

        def describe(self):
            return "tenant 111"

        def upload(self, item):
            return PageResult(item.spec.remote, "Prisma Access", False, "21643", detail="HTTP 400: nope")

        def close(self):
            pass

    monkeypatch.setattr(cli, "_scm_target", lambda cfg: FakeTarget())
    result = runner.invoke(cli.app, ["--log-json", "import", "scm", "--from", str(build_dir())])
    assert result.exit_code == 1

    # Every line must be one JSON object -- format_import_report's multi-line
    # human report is not valid JSON, so this alone proves it never printed.
    events = [json.loads(line) for line in result.output.splitlines()]
    failures = [e for e in events if e["level"] == "error" and "HTTP 400" in e["event"]]
    assert failures, "the failed page must be logged as a structured event"
    assert failures[0]["mutation_id"] == "21643"


def test_scm_target_shares_one_httpx_client_between_the_token_source_and_the_config_api():
    # Every other test in this file patches _scm_target out, so nothing else
    # exercises it. It is the only place that constructs TokenSource and
    # ScmClient against the same httpx.Client -- the precondition both
    # ScmClient.close() and ScmTarget.close() docstrings rely on, since it is
    # what lets a single close() release the whole pool. A refactor giving
    # TokenSource its own client would leak a connection pool silently and
    # still pass the rest of the suite.
    config = ScmConfig(
        client_id="a@b.iam.panserviceaccount.com",
        client_secret="s3cret",
        tsg_id="111",
        auth_url="https://auth.example",
        mfe_url="https://api.example/mfe/instances",
        folder="Prisma Access",
    )
    # Constructing these objects makes no network request -- only close()
    # touches the connection, and that is called below.
    target = cli._scm_target(config)
    try:
        assert target._client._client is target._client._tokens._client
    finally:
        target.close()
