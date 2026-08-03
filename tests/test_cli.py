"""The CLI, driven through CliRunner.

In-process on purpose: a subprocess would test the same behaviour and show up as
zero coverage, which is how this project ended up believing it had 31%.
"""

import json
import tempfile
import unittest
from pathlib import Path

import pytest
from typer.testing import CliRunner

from _paths import DATA
from panos_response_pages import __version__, builder, cli
from panos_response_pages.cli import app
from panos_response_pages.portal.page import FRAMES
from panos_response_pages.portal.validate import HOME_VARS, LOGIN_VARS
from panos_response_pages.validate import PAGE_TOKENS

pytestmark = pytest.mark.cli

runner = CliRunner()


class TestListings(unittest.TestCase):
    def test_version_matches_package_metadata(self):
        r = runner.invoke(app, ["--version"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(__version__, r.output)

    def test_themes_lists_every_style_with_its_label(self):
        r = runner.invoke(app, ["themes", "--config-dir", str(DATA)])
        self.assertEqual(r.exit_code, 0, r.output)
        for name in ("assist", "record", "banner", "glass", "beacon", "mesh"):
            self.assertIn(name, r.output)
        self.assertIn("Assistive Panel", r.output, "the label is what tells them apart")

    def test_palettes_lists_every_palette(self):
        # --config-dir, not the resolved default: on a machine with a
        # ~/.panos_response_pages this would otherwise assert against whatever
        # that directory holds rather than against what the repository ships.
        r = runner.invoke(app, ["palettes", "--config-dir", str(DATA)])
        self.assertEqual(r.exit_code, 0, r.output)
        for name in ("cyber-orange", "prisma-blue", "strata-yellow", "nyan"):
            self.assertIn(name, r.output)

    def test_pages_lists_the_tokens_each_page_type_provides(self):
        r = runner.invoke(app, ["pages"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("safe-search-block-page", r.output)
        self.assertIn("<ssurl/>", r.output)


class TestPossibleValues(unittest.TestCase):
    """The whole reason for moving to Typer: an unknown name should answer the
    question rather than just refuse."""

    def test_unknown_palette_reports_what_is_available(self):
        # Exit 1, not 2: `--palette` is no longer validated by the CLI itself.
        # `palettes.select` raises with the list from inside the build, the
        # same place an unknown value would be caught either way -- so there is
        # one message for the mistake instead of two.
        r = runner.invoke(app, ["build", "--palette", "lilac", "--config-dir", str(DATA)])
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("unknown palette", r.output)
        for name in ("cyber-orange", "prisma-blue", "strata-yellow", "nyan"):
            self.assertIn(name, r.output)

    def test_unknown_theme_reports_what_is_available(self):
        r = runner.invoke(app, ["build", "--theme", "nope"])
        self.assertEqual(r.exit_code, 2, r.output)
        self.assertIn("unknown theme", r.output)
        self.assertIn("assist", r.output)


class TestBuild(unittest.TestCase):
    def test_builds_one_style_into_the_requested_directory(self):
        out = Path(tempfile.mkdtemp())
        # --config-dir, not the resolved default: see the comment on
        # test_palettes_lists_every_palette -- a machine with a
        # ~/.panos_response_pages would otherwise build against whatever that
        # directory holds instead of what the repository ships.
        r = runner.invoke(
            app,
            [
                "build",
                "--theme",
                "glass",
                "--palette",
                "cyber-orange",
                "--no-preview",
                "-o",
                str(out),
                "--config-dir",
                str(DATA),
            ],
        )
        self.assertEqual(r.exit_code, 0, r.output)
        built = sorted(p.name for p in (out / "deploy" / "glass" / "cyber-orange").glob("*.html"))
        self.assertEqual(len(built), len(PAGE_TOKENS), built)
        self.assertIn("url-block-page.html", built)

    def test_reports_the_data_directory_it_used(self):
        r = runner.invoke(app, ["build", "--no-preview", "-o", tempfile.mkdtemp(), "--config-dir", str(DATA)])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("explicit", r.output, "the report should say which rule chose the data dir")

    def test_log_json_replaces_the_report_with_one_machine_readable_stream(self):
        # --config-dir, not the resolved default: see the comment on
        # test_palettes_lists_every_palette.
        r = runner.invoke(
            app,
            ["--log-json", "-v", "build", "--no-preview", "-o", tempfile.mkdtemp(), "--config-dir", str(DATA)],
        )
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertNotIn("of limit", r.output, "the pretty table must not interleave with JSON")
        first = json.loads(r.output.splitlines()[0])
        self.assertEqual(first["level"], "info")
        self.assertIn("event", first)

    def test_rejects_a_data_directory_that_has_no_templates(self):
        r = runner.invoke(app, ["build", "--config-dir", tempfile.mkdtemp(), "-o", tempfile.mkdtemp()])
        self.assertEqual(r.exit_code, 1, r.output)


class TestInit(unittest.TestCase):
    def test_copies_the_shipped_data_and_refuses_to_clobber(self):
        target = Path(tempfile.mkdtemp()) / "data"
        r = runner.invoke(app, ["init", str(target)])
        self.assertEqual(r.exit_code, 0, r.output)
        for sub in ("templates", "palettes", "themes", "config"):
            self.assertTrue((target / sub).is_dir(), f"{sub} missing from the copy")

        again = runner.invoke(app, ["init", str(target)])
        self.assertEqual(again.exit_code, 1, "a second init must not silently overwrite")
        self.assertIn("--force", again.output)

    def test_a_copied_tree_can_be_built_against(self):
        target = Path(tempfile.mkdtemp()) / "data"
        runner.invoke(app, ["init", str(target)])
        out = Path(tempfile.mkdtemp())
        r = runner.invoke(app, ["build", "--config-dir", str(target), "--no-preview", "-o", str(out)])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertTrue((out / "deploy" / "assist" / "cyber-orange" / "url-block-page.html").is_file())


class TestPortalTablesAgree(unittest.TestCase):
    def test_the_cli_describes_every_import_the_builder_emits(self):
        """cli.PORTAL_PAGES carries CLI-only metadata so it cannot simply BE
        builder.PORTAL_PAGES, which is itself derived from portal.page.FRAMES.
        A third frame added to FRAMES and not described here would build and
        ship a page the CLI can neither name nor route to `validate`."""
        self.assertEqual(set(cli.PORTAL_PAGES), set(builder.PORTAL_PAGES))
        self.assertEqual(set(builder.PORTAL_PAGES), set(FRAMES))


class TestValidateCommand(unittest.TestCase):
    def test_passes_pages_this_tool_produced(self):
        out = Path(tempfile.mkdtemp())
        # --config-dir, not the resolved default: see the comment on
        # test_palettes_lists_every_palette.
        runner.invoke(app, ["build", "--theme", "assist", "--no-preview", "-o", str(out), "--config-dir", str(DATA)])
        r = runner.invoke(app, ["validate", str(out)])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("0 would fail", r.output)

    def test_catches_a_page_that_would_fail_on_panos(self):
        bad = Path(tempfile.mkdtemp())
        (bad / "url-block-page.html").write_text("<html>no doctype</html>", encoding="utf-8")
        r = runner.invoke(app, ["validate", str(bad)])
        self.assertEqual(r.exit_code, 1, r.output)

    def test_says_so_when_nothing_recognisable_is_there(self):
        r = runner.invoke(app, ["validate", tempfile.mkdtemp()])
        self.assertEqual(r.exit_code, 1)
        self.assertIn("No recognised page types", r.output)


class TestValidateReachesThePortal(unittest.TestCase):
    """Before this, the loop skipped anything whose stem was not a block page.
    The portal imports fell through it with a debug line and no report -- which
    reads exactly like a pass, on the one family whose failures are silent."""

    def test_both_families_are_counted(self):
        # --config-dir, not the resolved default: a machine with a
        # ~/.panos_response_pages that predates a palette would otherwise
        # multiply by whatever that stale directory happens to hold.
        out = Path(tempfile.mkdtemp())
        # Every palette gets built (theme is the only axis narrowed here), and
        # `validate` walks the tree recursively -- so the count is per-palette
        # multiplied by how many palettes exist, not the single-palette figure
        # this asserted before the matrix existed.
        from panos_response_pages import palettes

        n_palettes = len(palettes.available(DATA / "palettes"))
        runner.invoke(app, ["build", "--theme", "assist", "--no-preview", "-o", str(out), "--config-dir", str(DATA)])
        r = runner.invoke(app, ["validate", str(out / "deploy")])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(f"checked {(len(PAGE_TOKENS) + 2) * n_palettes} page(s)", r.output)

    def test_a_portal_import_that_would_fail_is_reported(self):
        bad = Path(tempfile.mkdtemp())
        # A whole document rather than a body fragment, and no form token: two
        # of the failures PAN-OS accepts without complaint.
        (bad / "login.html").write_text("<html><body>no fragment</body></html>", encoding="utf-8")
        r = runner.invoke(app, ["validate", str(bad)])
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("1 would fail", r.output)

    def test_a_file_whose_name_disagrees_with_its_shape_is_called_out(self):
        """detect_kind looks for logout_text_array, so a home import that lost
        its variable block would be checked as a login page and every message
        would describe the wrong file shape."""
        odd = Path(tempfile.mkdtemp())
        (odd / "home.html").write_text("<script>var favicon='';</script>", encoding="utf-8")
        r = runner.invoke(app, ["-v", "validate", str(odd)])
        self.assertIn("reads as the login import", r.output)


class TestPagesListing(unittest.TestCase):
    def test_lists_the_portal_imports_and_how_many_variables_each_declares(self):
        """Every one of them must be declared: PAN-OS' ready handler
        dereferences the lot, and one missing name throws and loses the whole
        customization."""
        r = runner.invoke(app, ["pages"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("portal/login", r.output)
        self.assertIn("portal/home", r.output)
        self.assertIn(f"{len(LOGIN_VARS)} variables", r.output)
        self.assertIn(f"{len(HOME_VARS)} variables", r.output)
        self.assertIn("global-protect-portal-custom-login-page", r.output)

    def test_still_lists_every_block_page_and_its_tokens(self):
        r = runner.invoke(app, ["pages"])
        for page in PAGE_TOKENS:
            self.assertIn(page, r.output)
