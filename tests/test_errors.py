"""The paths that stop a bad page shipping.

Each of these is a condition PAN-OS would accept without complaint. They are the
reason the build exists, so they get tested as deliberately as the happy path.
"""

import json
import pathlib
import shutil
import tempfile
import unittest

import pytest

from _paths import DATA
from panos_response_pages import page as page_mod
from panos_response_pages.builder import build_all, load_themes
from panos_response_pages.config import deep_merge, load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.palettes import load_palette
from panos_response_pages.templates import parse_sections, read, substitute
from panos_response_pages.validate import PAGE_TOKENS

pytestmark = pytest.mark.integration


def scratch_data() -> pathlib.Path:
    """A private, writable copy of the shipped data tree."""
    target = pathlib.Path(tempfile.mkdtemp()) / "data"
    shutil.copytree(DATA, target)
    return target


class TestConfig(unittest.TestCase):
    def test_a_customer_file_is_merged_over_the_defaults(self):
        data = scratch_data()
        (data / "config" / "acme.json").write_text(json.dumps({"company": "Acme"}), encoding="utf-8")
        cfg = load_config("acme", data / "config")
        self.assertEqual(cfg["company"], "Acme")
        self.assertIn("categories", cfg, "keys the override omits must survive")

    def test_an_unknown_customer_falls_back_to_the_defaults(self):
        cfg = load_config("nobody-by-that-name", DATA / "config")
        self.assertIn("company", cfg)

    def test_merge_is_deep_rather_than_wholesale_replacement(self):
        base = {"marks": {"warning": "W", "info": "I"}, "company": "X"}
        deep_merge(base, {"marks": {"info": "J"}})
        self.assertEqual(base["marks"], {"warning": "W", "info": "J"}, "a nested override must not drop siblings")
        self.assertEqual(base["company"], "X")


class TestPalettes(unittest.TestCase):
    def test_an_unknown_palette_names_the_available_ones(self):
        with self.assertRaises(BuildError) as caught:
            load_palette("lilac", DATA / "palettes")
        message = str(caught.exception)
        self.assertIn("lilac", message)
        self.assertIn("cyber-orange", message, "the error should answer the question it raises")


class TestTemplates(unittest.TestCase):
    def test_a_missing_file_is_reported_with_its_path(self):
        with self.assertRaises(BuildError) as caught:
            read(pathlib.Path("/nonexistent/shells/ghost.html"))
        self.assertIn("ghost.html", str(caught.exception))

    def test_an_unknown_placeholder_is_an_error_not_a_blank(self):
        """Silently leaving {{NOPE}} unresolved would ship the literal braces to
        a user; silently emptying it would ship a blank field."""
        with self.assertRaises(BuildError) as caught:
            substitute("<p>{{NOPE}}</p>", {"COMPANY": "X"})
        self.assertIn("NOPE", str(caught.exception))

    def test_sections_are_parsed_by_name(self):
        parsed = parse_sections("<!--@TITLE-->Hello<!--/@TITLE-->\n<!--@GLOSS-->World<!--/@GLOSS-->")
        self.assertEqual(parsed, {"TITLE": "Hello", "GLOSS": "World"})


class TestPageAssembly(unittest.TestCase):
    def _fixture(self):
        data = scratch_data()
        cfg = load_config("contoso", data / "config")
        palette = load_palette("cyber-orange", data / "palettes")
        theme = json.loads(read(data / "themes" / "assist.json"))
        return data, cfg, palette, theme

    def test_a_page_missing_a_required_section_is_rejected(self):
        data, cfg, palette, theme = self._fixture()
        target = data / "templates" / "pages" / "url-block-page.html"
        body = target.read_text(encoding="utf-8")
        target.write_text(body.replace("<!--@ACTIONS-->", "<!--@REMOVED-->"), encoding="utf-8")
        with self.assertRaises(BuildError) as caught:
            page_mod.build_page("url-block-page", theme, cfg, palette, False, data / "templates")
        self.assertIn("ACTIONS", str(caught.exception))

    def test_a_shell_placeholder_with_no_value_is_rejected(self):
        data, cfg, palette, theme = self._fixture()
        shell = data / "templates" / "shells" / "assist.html"
        shell.write_text(shell.read_text(encoding="utf-8").replace("</body>", "{{NO_SUCH_THING}}</body>"), "utf-8")
        with self.assertRaises(BuildError) as caught:
            page_mod.build_page("url-block-page", theme, cfg, palette, False, data / "templates")
        self.assertIn("NO_SUCH_THING", str(caught.exception))

    def test_an_unknown_category_tone_is_rejected(self):
        """A tone outside calm/warn/critical would render as an unstyled
        attribute -- the page would look calm regardless of the verdict."""
        data, cfg, palette, theme = self._fixture()
        cfg["categories"]["malware"]["tone"] = "spicy"
        with self.assertRaises(BuildError) as caught:
            page_mod.build_page("url-block-page", theme, cfg, palette, False, data / "templates")
        self.assertIn("spicy", str(caught.exception))


class TestThemeSelection(unittest.TestCase):
    def test_selecting_a_theme_that_does_not_exist_is_an_error(self):
        with self.assertRaises(BuildError):
            load_themes(DATA, "no-such-style")

    def test_a_data_directory_with_no_themes_is_an_error(self):
        with self.assertRaises(BuildError):
            load_themes(pathlib.Path(tempfile.mkdtemp()))

    def test_building_one_theme_builds_only_that_theme(self):
        result = build_all(DATA, pathlib.Path(tempfile.mkdtemp()), theme="mesh", preview=False, write=False)
        self.assertEqual({r.theme for r in result.results}, {"mesh"})
        self.assertEqual(len(result.results), len(PAGE_TOKENS))


class TestOversizePage(unittest.TestCase):
    def test_a_page_over_the_ceiling_fails_the_build(self):
        """The single most important guard: PAN-OS accepts an oversize page and
        then silently serves the default one instead."""
        data = scratch_data()
        shell = data / "templates" / "shells" / "assist.html"
        padding = "<!--" + "x" * 18000 + "-->"
        shell.write_text(shell.read_text(encoding="utf-8").replace("</body>", padding + "</body>"), encoding="utf-8")
        result = build_all(data, pathlib.Path(tempfile.mkdtemp()), theme="assist", preview=False, write=False)
        self.assertTrue(result.failed)
        self.assertTrue(any("ceiling" in e for r in result.results for e in r.errors))
