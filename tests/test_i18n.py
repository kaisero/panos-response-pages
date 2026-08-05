"""Language selection, strings loading and dictionary assembly."""

import json
import pathlib
import re
import unittest
from typing import ClassVar

import pytest

from _paths import DATA
from panos_response_pages import i18n
from panos_response_pages.errors import BuildError
from panos_response_pages.validate import PAGE_TOKENS

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


class TestPageValues(unittest.TestCase):
    def test_builds_the_placeholder_values_for_one_page(self):
        doc = {
            "shared": {"reportLabel": "Report to IT", "contactAlt": ["Or email ", " with the details above."]},
            "pages": {
                "application-block-page": {
                    "title": "Application blocked",
                    "headline": "This application is blocked",
                    "gloss": "Company policy restricts this application on the network.",
                    "facts": ["Application", "User", "Time"],
                    "extra": (
                        "If you need this application for your work, send the report above and IT will review it."
                    ),
                    "report": {
                        "subject": "Blocked application report",
                        "intro": "Please review this application block.",
                        "prompt": "Why I need this application:",
                    },
                }
            },
        }
        v = i18n.page_values(doc, "application-block-page", {})
        self.assertEqual(v["T_TITLE"], "Application blocked")
        self.assertEqual(v["T_FACT1"], "Application")
        self.assertEqual(v["T_FACT3"], "Time")
        self.assertEqual(v["T_REPORT_LABEL"], "Report to IT")
        self.assertEqual(v["T_CONTACT_ALT1"], "Or email ")
        self.assertEqual(v["T_REPORT_SUBJECT"], "Blocked application report")

    def test_an_array_extra_becomes_numbered_fragments(self):
        """safe-search interrupts its own sentence with the contact anchor, and
        the anchor is the build's rather than the translator's -- its href and
        data-* attributes are decided at build time. The slot arrives as an
        array and each fragment gets its own numbered placeholder, so a
        translation can move the words around the markup it cannot carry."""
        doc = {
            "shared": {"reportLabel": "R", "contactAlt": ["a", "b"]},
            "pages": {
                "safe-search-block-page": {
                    "title": "t",
                    "headline": "h",
                    "gloss": "g",
                    "facts": ["User", "Time"],
                    "action2": "Open search settings",
                    "extra": ["first para", "Contact ", " and IT will look."],
                    "report": {"subject": "s", "intro": "i", "prompt": "p"},
                }
            },
        }
        v = i18n.page_values(doc, "safe-search-block-page", {})
        self.assertEqual(v["T_EXTRA1"], "first para")
        self.assertEqual(v["T_EXTRA2"], "Contact ")
        self.assertEqual(v["T_EXTRA3"], " and IT will look.")
        self.assertNotIn("T_EXTRA", v, "a split slot has no single-string form to fall back on")
        self.assertEqual(v["T_ACTION2_LABEL"], "Open search settings")

    def test_a_second_action_label_is_only_emitted_where_a_page_declares_one(self):
        doc = {
            "shared": {"reportLabel": "R", "contactAlt": ["a", "b"]},
            "pages": {
                "url-block-page": {
                    "title": "t",
                    "headline": "h",
                    "gloss": "g",
                    "facts": ["User"],
                    "extra": "e",
                    "report": {"subject": "s", "intro": "i", "prompt": "p"},
                }
            },
        }
        self.assertNotIn("T_ACTION2_LABEL", i18n.page_values(doc, "url-block-page", {}))

    def test_names_the_page_when_it_is_absent(self):
        with self.assertRaises(BuildError) as ctx:
            i18n.page_values({"shared": {}, "pages": {}}, "url-block-page", {})
        self.assertIn("url-block-page", str(ctx.exception))


class TestPlaceholderResolution(unittest.TestCase):
    """Copy may itself contain {{COMPANY}} or {{CONTINUE_GRANT}}.

    substitute() is one re.sub pass and re.sub does not rescan its replacement,
    so a placeholder inside a translated value is inserted literally. In the
    base language that surfaces as a BuildError from assert_resolved. In the
    runtime dictionary -- which never passes through substitute() at all --
    it would ship the literal braces to a user with no error anywhere.
    """

    VALUES: ClassVar = {"COMPANY": "Example Corp", "CONTINUE_GRANT": "15 minutes"}

    def test_resolves_inside_a_string(self):
        self.assertEqual(
            i18n.resolve("Report to {{COMPANY}} security.", self.VALUES),
            "Report to Example Corp security.",
        )

    def test_resolves_inside_a_list(self):
        self.assertEqual(
            i18n.resolve(["a {{COMPANY}} b", "c"], self.VALUES),
            ["a Example Corp b", "c"],
        )

    def test_resolves_inside_a_nested_dict(self):
        self.assertEqual(
            i18n.resolve({"r": {"intro": "for {{CONTINUE_GRANT}}"}}, self.VALUES),
            {"r": {"intro": "for 15 minutes"}},
        )

    def test_unknown_placeholder_still_raises(self):
        with self.assertRaises(BuildError):
            i18n.resolve("{{NOPE}}", self.VALUES)

    def test_page_values_are_resolved(self):
        doc = {
            "shared": {"reportLabel": "R", "contactAlt": ["a", "b"]},
            "pages": {
                "p": {
                    "title": "t",
                    "headline": "h",
                    "gloss": "g",
                    "facts": ["f"],
                    "extra": "Ask {{COMPANY}}.",
                    "report": {"subject": "s", "intro": "i", "prompt": "p"},
                }
            },
        }
        v = i18n.page_values(doc, "p", self.VALUES)
        self.assertEqual(v["T_EXTRA"], "Ask Example Corp.")
        self.assertNotIn("{{", "".join(str(x) for x in v.values()))


class TestEnglishCoversEveryPage(unittest.TestCase):
    def test_every_registered_page_has_a_strings_block(self):
        """PAGE_TOKENS is the source of truth for which pages exist. A page
        template with no strings block fails at build time with a KeyError from
        inside substitution; this says which page, before the build runs."""
        doc = i18n.load("en", DATA)
        self.assertEqual(sorted(doc["pages"]), sorted(PAGE_TOKENS))


class TestSeverityLabels(unittest.TestCase):
    def test_severity_labels_come_from_the_strings_file(self):
        """The third home of English copy. It cannot stay in Python once the
        other two are consolidated -- a German page would show 'Caution'."""
        doc = i18n.load("en", DATA)
        self.assertEqual(doc["shared"]["severity"], {"calm": "", "warn": "Caution", "crit": "Security risk"})

    def test_scripts_module_no_longer_defines_them(self):
        import panos_response_pages.scripts as scripts

        self.assertFalse(hasattr(scripts, "SEV_LABEL"), "SEV_LABEL must not survive in scripts.py")


class TestTemplatesCarryNoCopy(unittest.TestCase):
    def test_no_prose_left_in_page_slots(self):
        """Copy lives in the strings files now. A slot with words in it is copy
        that no language can override -- it would ship English into a German
        page, silently."""
        slots = ("TITLE", "HEADLINE", "GLOSS", "EXTRA")
        for f in sorted((DATA / "templates/pages").glob("*.html")):
            text = f.read_text(encoding="utf-8")
            for name, body in re.findall(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", text, re.S):
                if name not in slots:
                    continue
                stripped = re.sub(r"\{\{[A-Z_0-9]+\}\}|<[^>]+>", "", body).strip()
                self.assertEqual(stripped, "", f"{f.stem} {name} still contains copy: {stripped!r}")


class TestFactLabelCounts(unittest.TestCase):
    def test_every_language_has_one_label_per_dt(self):
        """Fact labels swap positionally against `dl dt` in document order. One
        short and every label below it shifts up by one, silently.

        check_complete compares the languages against each other, so a `facts`
        array that is wrong in EVERY language -- which is what an en.json with
        one label too many becomes as soon as it is translated -- passes it. The
        template is the only thing that knows how many rows there are."""
        for page in sorted(PAGE_TOKENS):
            body = (DATA / "templates/pages" / f"{page}.html").read_text(encoding="utf-8")
            facts = re.search(r"<!--@FACTS-->(.*?)<!--/@FACTS-->", body, re.S).group(1)
            want = len(re.findall(r"<dt>", facts))
            for f in sorted((DATA / "strings").glob("*.json")):
                doc = i18n.load(f.stem, DATA)
                got = len(doc["pages"][page]["facts"])
                self.assertEqual(got, want, f"{f.stem}/{page}: {got} labels for {want} <dt> rows")
