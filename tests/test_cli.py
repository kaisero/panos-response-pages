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
from panos_response_pages import __version__
from panos_response_pages.cli import app
from panos_response_pages.validate import PAGE_TOKENS

pytestmark = pytest.mark.cli

runner = CliRunner()


class TestListings(unittest.TestCase):
    def test_version_matches_package_metadata(self):
        r = runner.invoke(app, ["--version"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(__version__, r.output)

    def test_themes_lists_every_style_with_its_label(self):
        r = runner.invoke(app, ["themes"])
        self.assertEqual(r.exit_code, 0, r.output)
        for name in ("assist", "record", "banner", "glass", "beacon", "mesh"):
            self.assertIn(name, r.output)
        self.assertIn("Assistive Panel", r.output, "the label is what tells them apart")

    def test_palettes_lists_every_palette(self):
        r = runner.invoke(app, ["palettes"])
        self.assertEqual(r.exit_code, 0, r.output)
        for name in ("cyber-orange", "prisma-blue", "strata-yellow"):
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
        r = runner.invoke(app, ["build", "--palette", "lilac"])
        self.assertEqual(r.exit_code, 2, r.output)
        self.assertIn("unknown palette", r.output)
        for name in ("cyber-orange", "prisma-blue", "strata-yellow"):
            self.assertIn(name, r.output)

    def test_unknown_theme_reports_what_is_available(self):
        r = runner.invoke(app, ["build", "--theme", "nope"])
        self.assertEqual(r.exit_code, 2, r.output)
        self.assertIn("unknown theme", r.output)
        self.assertIn("assist", r.output)


class TestBuild(unittest.TestCase):
    def test_builds_one_style_into_the_requested_directory(self):
        out = Path(tempfile.mkdtemp())
        r = runner.invoke(app, ["build", "--theme", "glass", "--no-preview", "-o", str(out)])
        self.assertEqual(r.exit_code, 0, r.output)
        built = sorted(p.name for p in (out / "deploy" / "glass").glob("*.html"))
        self.assertEqual(len(built), len(PAGE_TOKENS), built)
        self.assertIn("url-block-page.html", built)

    def test_reports_the_data_directory_it_used(self):
        r = runner.invoke(app, ["build", "--no-preview", "-o", tempfile.mkdtemp(), "--config-dir", str(DATA)])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("explicit", r.output, "the report should say which rule chose the data dir")

    def test_log_json_replaces_the_report_with_one_machine_readable_stream(self):
        r = runner.invoke(app, ["--log-json", "-v", "build", "--no-preview", "-o", tempfile.mkdtemp()])
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
        self.assertTrue((out / "deploy" / "assist" / "url-block-page.html").is_file())


class TestValidateCommand(unittest.TestCase):
    def test_passes_pages_this_tool_produced(self):
        out = Path(tempfile.mkdtemp())
        runner.invoke(app, ["build", "--theme", "assist", "--no-preview", "-o", str(out)])
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
