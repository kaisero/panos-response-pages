"""Language selection, strings loading and dictionary assembly."""

import json
import pathlib
import re
import shutil
import tempfile
import unittest
from typing import ClassVar

import pytest

from _build import LANGUAGE_BLOCK, translated_strings
from _paths import DATA
from panos_response_pages import i18n, scripts
from panos_response_pages.builder import load_themes
from panos_response_pages.config import load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
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


class TestNoStringIsEmpty(unittest.TestCase):
    """An empty leaf passes every other check and breaks the page anyway.

    check_complete compares key SETS and flat_keys indexes list positions, so an
    empty fragment sits at a valid key with a valid index and is invisible to
    both. What it is not invisible to is the DOM: a fragment that renders no
    text node drops the sentence from three child nodes to two, and the runtime
    swap -- which keys on childNodes.length>2 -- then does nothing at all. The
    sentence silently stays in the base language on an otherwise translated
    page. Task 9 is where real German prose arrives, which is why this is a
    build error now rather than a review note then.
    """

    def _write(self, tmp, name, doc):
        d = tmp / "strings"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def _check(self, tmp, base="en"):
        i18n.check_complete({"baseLanguage": base, "languages": ["en", "de"]}, tmp)

    def test_rejects_an_empty_string_and_names_the_language_and_the_key(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}})
            self._write(tmp, "de", {"shared": {"a": ""}})
            with self.assertRaises(BuildError) as ctx:
                self._check(tmp)
            msg = str(ctx.exception)
            self.assertIn("de.json", msg)
            self.assertIn("shared.a", msg)

    def test_rejects_an_empty_fragment_of_a_split_sentence(self):
        """The case this exists for: a translation whose sentence OPENS with the
        emphasised phrase or with the anchor has nothing to put in fragment 0."""
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"pages": {"p": {"extra": ["a", "b", "c"]}}})
            self._write(tmp, "de", {"pages": {"p": {"extra": ["", "b", "c"]}}})
            with self.assertRaises(BuildError) as ctx:
                self._check(tmp)
            self.assertIn("pages.p.extra[0]", str(ctx.exception))

    def test_rejects_it_in_the_base_language_too(self):
        """Worse there, not better: the base language IS the markup, so an empty
        fragment collapses the shape for every language at once."""
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": ""}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            with self.assertRaises(BuildError) as ctx:
                self._check(tmp)
            self.assertIn("en.json", str(ctx.exception))

    def test_a_fragment_that_is_only_a_space_is_fine(self):
        """Empty, not blank. " " renders a text node and keeps the shape, and
        several shipped fragments legitimately end in one."""
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"contactAlt": ["Or email ", " straight away."]}})
            self._write(tmp, "de", {"shared": {"contactAlt": ["de:Or email ", " "]}})
            self._check(tmp)

    def test_the_shipped_document_passes(self):
        """The one deliberate exception: the calm severity pill carries no
        words, and the runtime's `if(V&&V.textContent)` guard depends on it."""
        self.assertEqual(i18n.empty_leaves(i18n.load("en", DATA)), [])
        i18n.check_complete({"baseLanguage": "en", "languages": ["en"]}, DATA)


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


def _leaves(value, path=""):
    """Every string leaf of a strings document, with its path."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _leaves(item, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


class TestNoCopyCarriesMarkup(unittest.TestCase):
    """Every string in the file has to survive being assigned to textContent.

    A strings document reaches the page down two paths: the base language goes
    through substitute() into the markup, where a `<strong>` renders; every
    other language goes through the runtime dictionary into textContent, where
    the same characters render as literal angle brackets. So markup inside copy
    reads correctly in exactly one language and is escaped in all the others.

    innerHTML is not the fix. It would make every string in every language file
    an injection surface, and on the portal a raw `<` stops PAN-OS substituting
    <pan_form/> at all. The fix is to split the string around the element and
    let the template own the tag -- which is what `contactAlt` does around its
    anchor, safe-search's `.note` around its contact anchor, and url-coach's
    info box around its <strong>.
    """

    def test_no_string_in_the_shipped_document_contains_a_tag(self):
        doc = i18n.load("en", DATA)
        bad = [(path, value) for path, value in _leaves(doc) if "<" in value or ">" in value]
        self.assertEqual(bad, [], "copy containing markup renders escaped in every non-base language")

    def test_the_split_reassembles_into_the_sentence_the_page_shows(self):
        """The split is a rendering detail, not an edit. Joined back up, the
        fragments plus the tag the template now owns are the sentence English
        readers see today, character for character."""
        extra = i18n.load("en", DATA)["pages"]["url-coach-text"]["extra"]
        self.assertIsInstance(extra, list, "the slot is three fragments the template wraps a <strong> around")
        self.assertEqual(len(extra), 3)
        self.assertEqual(
            extra[0] + "<strong>" + extra[1] + "</strong>" + extra[2],
            "Continuing grants access to <strong>every site in this category</strong> for {{CONTINUE_GRANT}}.",
        )


class TestSeverityLabels(unittest.TestCase):
    def test_severity_labels_come_from_the_strings_file(self):
        """The third home of English copy. It cannot stay in Python once the
        other two are consolidated -- a German page would show 'Caution'."""
        doc = i18n.load("en", DATA)
        self.assertEqual(doc["shared"]["severity"], {"calm": "", "warn": "Caution", "crit": "Security risk"})

    def test_scripts_module_no_longer_defines_them(self):
        self.assertFalse(hasattr(scripts, "SEV_LABEL"), "SEV_LABEL must not survive in scripts.py")


@pytest.mark.integration
class TestSeverityLabelsArePlaceholderResolved(unittest.TestCase):
    """A severity label is `shared` copy and may carry {{COMPANY}} like any
    other string in the file. Read straight off the loaded document it never
    meets substitute(), and the label reaches the page twice -- as the static
    {{SEVERITY}} pill and as JSON handed to textContent by the category script
    -- so an unresolved placeholder is a user-visible pair of braces, not a
    build error. Today's three labels contain none, which is precisely why this
    asserts on a strings file that does."""

    LABEL = "Caution for {{COMPANY}}"
    CFG: ClassVar[dict] = load_config("contoso", DATA / "config")
    RESOLVED = f"Caution for {CFG['company']}"

    def _data_copy(self, tmp: pathlib.Path, **severity) -> pathlib.Path:
        """The shipped templates and strings, with severity labels rewritten.

        Copied rather than monkeypatched: build_page resolves the base language
        relative to the template directory it is handed, so the strings file it
        actually reads is the one that has to carry the placeholder."""
        dest = tmp / "templates"
        shutil.copytree(DATA / "templates" / "shells", dest / "shells")
        shutil.copytree(DATA / "templates" / "pages", dest / "pages")
        shutil.copytree(DATA / "strings", tmp / "strings")
        doc = json.loads((tmp / "strings" / "en.json").read_text(encoding="utf-8"))
        doc["shared"]["severity"].update(severity)
        (tmp / "strings" / "en.json").write_text(json.dumps(doc), encoding="utf-8")
        return dest

    def _build(self, page: str, template_dir: pathlib.Path) -> str:
        palette = load_palette("cyber-orange", DATA / "palettes")
        return build_page(page, load_themes(DATA)[0], self.CFG, palette, False, template_dir)

    def _assert_resolved(self, html: str, page: str) -> None:
        """Asserted on membership rather than with assertIn: the container is a
        whole response page, and a failure that prints it buries its own
        message."""
        self.assertTrue(self.RESOLVED in html, f"{page}: severity label was not resolved against COMPANY")
        self.assertTrue("{{COMPANY}}" not in html, f"{page}: severity label shipped a literal {{{{COMPANY}}}}")

    def test_the_static_pill_label_is_resolved(self):
        """file-block-page declares TONE warn, so the label is written into the
        markup as real text."""
        with tempfile.TemporaryDirectory() as tmp_str:
            template_dir = self._data_copy(pathlib.Path(tmp_str), warn=self.LABEL)
            self._assert_resolved(self._build("file-block-page", template_dir), "file-block-page")

    def test_the_runtime_label_map_is_resolved(self):
        """url-block-page carries the category script, which ships the whole
        map as JSON and assigns from it to textContent in the browser."""
        with tempfile.TemporaryDirectory() as tmp_str:
            template_dir = self._data_copy(pathlib.Path(tmp_str), warn=self.LABEL)
            self._assert_resolved(self._build("url-block-page", template_dir), "url-block-page")


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


class TestCustomerTranslations(unittest.TestCase):
    """Customer-authored copy is translated in the customer's own config, not
    in the shipped strings files -- resolution is whole-tree, so putting it
    there would force a customer to fork the entire data directory to
    translate one sentence."""

    DOC: ClassVar = {"shared": {"defaultGloss": "shipped EN", "continueGrantText": "15 minutes"}}

    def test_falls_back_to_the_strings_file(self):
        got = i18n.config_strings({}, self.DOC, "en")
        self.assertEqual(got["defaultGloss"], "shipped EN")

    def test_customer_translation_wins(self):
        cfg = {"translations": {"de": {"defaultGloss": "Kunden-DE", "continueGrantText": "30 Minuten"}}}
        got = i18n.config_strings(cfg, self.DOC, "de")
        self.assertEqual(got["defaultGloss"], "Kunden-DE")
        self.assertEqual(got["continueGrantText"], "30 Minuten")

    def test_untranslated_customer_key_falls_back_to_the_strings_file(self):
        cfg = {"translations": {"de": {"defaultGloss": "Kunden-DE"}}}
        got = i18n.config_strings(cfg, self.DOC, "de")
        self.assertEqual(got["continueGrantText"], "15 minutes")

    def test_rejects_a_translation_for_an_unconfigured_language(self):
        cfg = {"baseLanguage": "en", "languages": ["en"], "translations": {"fr": {"defaultGloss": "x"}}}
        with self.assertRaises(BuildError) as ctx:
            i18n.check(cfg, DATA)
        self.assertIn("fr", str(ctx.exception))

    def test_the_rejection_names_both_lists_the_author_could_fix(self):
        """The block is in the config, not in a language file, and either list
        could be the one that is wrong. A message naming only the language
        leaves the author guessing which of the two to edit."""
        cfg = {"baseLanguage": "en", "languages": ["en"], "translations": {"fr": {"defaultGloss": "x"}}}
        with self.assertRaises(BuildError) as ctx:
            i18n.check(cfg, DATA)
        msg = str(ctx.exception)
        self.assertIn("translations", msg)
        self.assertIn("languages", msg)

    def test_a_configured_language_may_carry_a_block(self):
        i18n.check({"baseLanguage": "en", "languages": ["en"], "translations": {"en": {"supportLabel": "x"}}}, DATA)


class TestShippedConfigCopyMatchesTheDefaults(unittest.TestCase):
    """The four customer-authored strings exist twice on purpose.

    `_defaults.json` is what the BASE language page is built from; the `shared`
    block of a strings file is what every OTHER language falls back to when the
    customer has not translated it. English carries both, so the two have to
    agree -- a drift between them would change today's copy for a customer whose
    base language is not English, silently and only in that direction."""

    def test_english_strings_repeat_the_shipped_defaults_verbatim(self):
        cfg = json.loads((DATA / "config/_defaults.json").read_text(encoding="utf-8"))
        shared = i18n.load("en", DATA)["shared"]
        for key in i18n.CONFIG_STRING_KEYS:
            with self.subTest(key=key):
                self.assertEqual(shared[key], cfg[key], f"en.json and _defaults.json disagree about {key}")


class TestRuntimeDict(unittest.TestCase):
    CFG: ClassVar = {"baseLanguage": "en", "languages": ["en", "de"], "company": "Example Corp"}

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-rt-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "strings").mkdir()
        for name in ("en", "de"):
            shutil.copy(DATA / "strings/en.json", self.tmp / "strings" / f"{name}.json")
        (self.tmp / "strings/de.json").write_text(json.dumps(translated_strings()), encoding="utf-8")

    def test_base_language_is_not_shipped(self):
        """It is already in the markup as real text. Shipping it again would be
        the largest single waste in the design."""
        cfg = {"baseLanguage": "en", "languages": ["en"], "company": "Example Corp"}
        self.assertEqual(i18n.runtime_dict(cfg, "application-block-page", DATA), {})

    def test_carries_only_the_keys_that_page_uses(self):
        d = i18n.runtime_dict(self.CFG, "application-block-page", self.tmp)
        self.assertEqual(sorted(d), ["de"])
        self.assertEqual(
            set(d["de"]),
            {"t", "h", "g", "f", "x", "rl", "rs", "ri", "rp", "ca", "s", "dg", "rg"},
        )
        self.assertEqual(len(d["de"]["f"]), 3, "one label per dt on this page")

    def test_the_second_action_label_rides_only_on_the_page_that_has_one(self):
        d = i18n.runtime_dict(self.CFG, "safe-search-block-page", self.tmp)
        self.assertEqual(d["de"]["a2"], "de:Open search settings")
        self.assertEqual(len(d["de"]["x"]), 3, "the split extra keeps its fragments")
        self.assertNotIn("a2", i18n.runtime_dict(self.CFG, "url-block-page", self.tmp)["de"])

    def test_a_page_override_of_contact_alt_wins(self):
        """Two pages say "straight away" instead of "with the details above".
        Reading `shared` unconditionally would swap the urgent wording out for
        the calm one the moment a language was selected."""
        d = i18n.runtime_dict(self.CFG, "credential-block-page", self.tmp)
        self.assertEqual(d["de"]["ca"], ["de:Or email ", "de: straight away."])

    def test_the_customer_translation_of_a_config_string_wins(self):
        cfg = dict(self.CFG, translations={"de": {"defaultGloss": "Kunden-DE"}})
        d = i18n.runtime_dict(cfg, "url-block-page", self.tmp)
        self.assertEqual(d["de"]["dg"], "Kunden-DE")
        self.assertEqual(d["de"]["rg"], "de:" + "This site was blocked because it presents a security risk.")

    def test_continue_grant_is_resolved_from_the_target_language(self):
        """A German sentence with the English duration inside it is the failure
        this guards against: the value has to come from the language's own
        strings, not from cfg."""
        cfg = dict(self.CFG, translations={"de": {"continueGrantText": "30 Minuten"}}, continueGrantText="15 minutes")
        d = i18n.runtime_dict(cfg, "url-coach-text", self.tmp)
        # Split around its <strong>, so the duration lives in one fragment;
        # asserted against the reassembled sentence, as the reader sees it.
        x = "".join(d["de"]["x"])
        self.assertIn("30 Minuten", x)
        self.assertNotIn("15 minutes", x)

    def _with_categories(self, gloss: str) -> None:
        """Give the German fixture the optional per-language categories block.

        en.json ships none, so nothing that builds from the shipped tree can
        reach `entry["c"]` at all -- which is exactly how the one copy value in
        runtime_dict() that skipped resolve() stayed that way.
        """
        doc = translated_strings()
        doc["categories"] = {"malware": gloss}
        (self.tmp / "strings/de.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_the_categories_block_is_resolved_like_every_other_value(self):
        self._with_categories("{{COMPANY}} blockiert diese Seite.")
        d = i18n.runtime_dict(self.CFG, "url-block-page", self.tmp)
        self.assertEqual(d["de"]["c"]["malware"], "Example Corp blockiert diese Seite.")

    def test_no_placeholder_survives_into_the_dictionary(self):
        """The silent half of the placeholder bug.

        This dictionary is JSON handed to textContent. assert_resolved() does
        scan it -- it scans the whole built page -- so a survivor fails the
        build, but with a message naming the page and neither the language nor
        the key. Cheaper to refuse it here.

        Asserted against the two pages that actually carry a placeholder inside
        their copy, not against an easy one, and against a fixture carrying the
        optional categories block -- the shipped en.json has none, so without it
        this test cannot reach that value at all.
        """
        self._with_categories("Von {{COMPANY}} gesperrt.")
        for page in ("credential-block-page", "url-coach-text"):
            with self.subTest(page=page):
                blob = json.dumps(i18n.runtime_dict(self.CFG, page, self.tmp))
                self.assertIn('"c":', blob, f"{page}: the fixture's categories block never reached the dictionary")
                self.assertNotIn("{{", blob, f"{page}: unresolved placeholder in the runtime dictionary")


class TestEmittedRuntime(unittest.TestCase):
    SEVERITY: ClassVar = {"calm": "", "warn": "Caution", "crit": "Security risk"}

    TIMESTAMP = (
        "var ts=document.getElementById('ts');"
        "if(ts)ts.textContent=new Date().toLocaleString(document.documentElement.lang||undefined);"
    )

    def _js(self, **over):
        kwargs = {
            "lock_copy": True,
            "has_category": False,
            "email_mode": True,
            "severity": self.SEVERITY,
        }
        kwargs.update(over)
        categories = kwargs.pop("categories", {})
        return scripts.category_js(categories, "d", "r", **kwargs)

    def test_single_language_emits_nothing_new(self):
        """The byte-identity promise, at the level of the function that would
        break it."""
        self.assertEqual(self._js(), self._js(lang_dict=""))

    def test_the_emitted_language_block_is_exactly_the_golden(self):
        """Equality, not membership, and over the whole script.

        There is no JS engine in this suite, so the only property a test can
        check is the bytes emitted -- and a substring assertion checks almost
        none of them. Nine separate mutations of this block (transposed S()
        arguments, childNodes[1] for [2], x.length for x.pop, whole statements
        deleted) each produce a visibly broken page and each survives every
        assertion below this one. This is what refuses them.

        The block is page-independent, so this covers all eleven pages and all
        seven shells; test_i18n_build.py asserts that independence rather than
        assuming it.
        """
        js = self._js(lang_dict='{"de":{}}', email_mode=False)
        self.assertEqual(
            js, '<script>(function(){var T={"de":{}},' + LANGUAGE_BLOCK + self.TIMESTAMP + "})();</script>"
        )

    def test_multi_language_emits_the_selector(self):
        js = self._js(lang_dict='{"de":{"h":"Hallo"}}')
        self.assertIn(
            'var T={"de":{"h":"Hallo"}},LS=navigator.languages||[navigator.language||\'\'],t,lk,i;'
            'for(i=0;i<LS.length;i++){lk=LS[i].slice(0,2).toLowerCase();if(lk=="en")break;if(T[lk]){t=T[lk];break}}',
            js,
        )
        self.assertIn("document.documentElement.lang=lk;document.title=t.t;", js)

    def test_the_base_language_stops_the_search(self):
        """A browser that prefers the base language must keep the page it was
        served. Without the break it would fall through to the next entry in
        navigator.languages and swap to a language the user ranked lower."""
        js = self._js(lang_dict='{"de":{"h":"Hallo"}}', base_lang="fr")
        self.assertIn(
            'for(i=0;i<LS.length;i++){lk=LS[i].slice(0,2).toLowerCase();if(lk=="fr")break;if(T[lk]){t=T[lk];break}}',
            js,
        )

    def test_severity_label_consults_the_selected_language(self):
        """The category script runs AFTER the language swap and re-sets .sev.
        Without this it reverts the pill to English on url-block-page and
        url-coach-text -- the only category-bearing pages without COPY_LOCK."""
        js = self._js(
            categories={"gambling": {"tone": "warn", "gloss": ""}},
            lock_copy=False,
            has_category=True,
            lang_dict='{"de":{"s":{"warn":"Achtung"}}}',
        )
        self.assertIn(
            "var v=document.querySelector('.sev');"
            'if(v)v.textContent=(t?t.s:{"calm":"","warn":"Caution","crit":"Security risk"})[m[0]]||\'\';',
            js,
            "severity must fall back to the base map only when no language matched",
        )

    def test_the_single_language_severity_line_never_references_t(self):
        """`t` is not declared when there is no dictionary, so the ternary form
        would be a ReferenceError on every page of a single-language build."""
        js = self._js(categories={"gambling": {"tone": "warn", "gloss": ""}}, lock_copy=False, has_category=True)
        self.assertNotIn("t?t.s:", js)

    def test_the_generic_glosses_follow_the_selected_language(self):
        js = self._js(
            categories={"gambling": {"tone": "warn", "gloss": ""}},
            lock_copy=False,
            has_category=True,
            lang_dict='{"de":{"dg":"Standard","rg":"Risiko"}}',
        )
        self.assertIn('var g=document.getElementById(\'gloss\'),m=M[k],d="d",r="r";if(t){d=t.dg;r=t.rg}', js)
        self.assertIn("if(g)g.textContent=(t?t.c&&t.c[k]:m[1])||(m[0]=='calm'?d:r);}else if(g)g.textContent=d;", js)

    def test_the_timestamp_is_localised_only_in_multi_language_builds(self):
        self.assertIn(
            "var t=document.getElementById('ts');if(t)t.textContent=new Date().toLocaleString();",
            self._js(),
        )
        self.assertIn(self.TIMESTAMP, self._js(lang_dict='{"de":{}}'))


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
