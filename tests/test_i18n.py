"""Language selection, strings loading and dictionary assembly."""

import json
import pathlib
import unittest

import pytest

from _paths import DATA
from panos_response_pages import i18n
from panos_response_pages.errors import BuildError

pytestmark = pytest.mark.unit


class TestLanguageConfig(unittest.TestCase):
    def test_defaults_to_english_only(self):
        self.assertEqual(i18n.base_language({}), "en")
        self.assertEqual(i18n.languages({}), ["en"])

    def test_reads_configured_values(self):
        cfg = {"baseLanguage": "de", "languages": ["de", "en"]}
        self.assertEqual(i18n.base_language(cfg), "de")
        self.assertEqual(i18n.languages(cfg), ["de", "en"])

    def test_rejects_base_language_not_in_languages(self):
        cfg = {"baseLanguage": "fr", "languages": ["en", "de"]}
        with self.assertRaises(BuildError) as ctx:
            i18n.check(cfg, DATA)
        self.assertIn("baseLanguage", str(ctx.exception))
        self.assertIn("fr", str(ctx.exception))

    def test_rejects_empty_language_list(self):
        with self.assertRaises(BuildError):
            i18n.check({"baseLanguage": "en", "languages": []}, DATA)

    def test_rejects_non_two_letter_key(self):
        with self.assertRaises(BuildError) as ctx:
            i18n.check({"baseLanguage": "en", "languages": ["en", "de-AT"]}, DATA)
        self.assertIn("de-AT", str(ctx.exception))

    def test_rejects_language_with_no_strings_file(self):
        with self.assertRaises(BuildError) as ctx:
            i18n.check({"baseLanguage": "en", "languages": ["en", "zz"]}, DATA)
        self.assertIn("zz.json", str(ctx.exception))


class TestStringsCompleteness(unittest.TestCase):
    """Every language supplies every key. A missing key is a build error, not a
    runtime fallback: a warning in a build log is the kind of notice that gets
    scrolled past, and the half-translated page it permits ships to users."""

    def _write(self, tmp, name, doc):
        d = tmp / "strings"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_flat_keys_walks_nested_documents_and_lists(self):
        doc = {"shared": {"a": "x"}, "pages": {"p": {"facts": ["one", "two"]}}}
        self.assertEqual(
            i18n.flat_keys(doc),
            {"shared.a", "pages.p.facts[0]", "pages.p.facts[1]"},
        )

    def test_accepts_a_language_with_the_same_keys(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)

    def test_rejects_a_language_missing_a_key(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x", "b": "z"}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            with self.assertRaises(BuildError) as ctx:
                i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)
            msg = str(ctx.exception)
            self.assertIn("de.json", msg)
            self.assertIn("shared.b", msg)

    def test_rejects_a_language_with_an_extra_key(self):
        """An extra key is a typo or a stale key, both of which mean a string
        the page will never show. Silence there hides a real mistake."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}})
            self._write(tmp, "de", {"shared": {"a": "y", "typo": "z"}})
            with self.assertRaises(BuildError) as ctx:
                i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)
            self.assertIn("shared.typo", str(ctx.exception))

    def test_categories_block_is_exempt_from_completeness(self):
        """Per-language category glosses are optional by design: absent, the
        language falls back to the translated generic gloss and costs ~600 B
        instead of ~2400 B."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}, "categories": {"gambling": "en gloss"}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)
