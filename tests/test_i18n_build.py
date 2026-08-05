"""Multi-language builds, and the promise that single-language builds are free.

The byte-identity assertion is the load-bearing one. `languages: ["en"]` must
produce exactly the bytes a build produced before this feature existed -- that
is what makes multi-language support cost nothing for every customer who does
not want it, and asserting it is how it stays true.

If this test fails, the change that broke it is wrong. Do NOT regenerate the
snapshot to make it pass.
"""

import hashlib
import json
import pathlib
import re
import shutil
import tempfile
import unittest

import pytest

from _build import built, translated_strings
from _paths import DATA, ROOT
from panos_response_pages.builder import build_all, load_themes
from panos_response_pages.config import load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette

pytestmark = pytest.mark.integration

SNAPSHOT = json.loads((ROOT / "tests/fixtures/byte-identity.json").read_text(encoding="utf-8"))


def broken_data_dir(strings=None, **over) -> pathlib.Path:
    """A copy of the shipped data directory, with `_defaults.json` overridden.

    A copy, never DATA itself: that tree is the installed package every other
    test builds from, and `_build.built()` caches one build of it for the whole
    run -- editing it in place would decide the outcome of tests that have
    nothing to do with languages.

    `strings` writes extra strings/<lang>.json documents, which is the only way
    to reach check_complete: it compares a language against the base language,
    so a language with no file at all fails the earlier existence rule instead.
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-i18n-")) / "data"
    shutil.copytree(DATA, root)
    path = root / "config" / "_defaults.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.update(over)
    path.write_text(json.dumps(cfg), encoding="utf-8")
    for lang, doc in (strings or {}).items():
        (root / "strings" / f"{lang}.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


def build(root: pathlib.Path) -> None:
    """Build `root` for its verdict only -- nothing is written and nothing kept."""
    build_all(root, root / "out", preview=False, write=False)


def multi_language_page(name: str) -> str:
    """One page built with a second language configured, as HTML.

    A real build_page, not the emitted script in isolation: the dictionary has
    to survive JSON encoding into a <script> body, and the selector has to be
    emitted before the category lookup that depends on it.
    """
    root = broken_data_dir(strings={"de": translated_strings()}, languages=["en", "de"])
    cfg = load_config("contoso", root / "config")
    palette = load_palette("cyber-orange", root / "palettes")
    return build_page(name, load_themes(root)[0], cfg, palette, False, root / "templates")


def runtime_code(html: str) -> str:
    """The runtime script of a built page, with the dictionary elided.

    The dictionary is most of the script's bytes and none of its logic, and a
    failing assertion that prints it is unreadable.
    """
    script = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "navigator.languages" in s)
    return re.sub(r"var T=\{.*?\},LS=", "var T={...},LS=", script, flags=re.S)


class TestABuildRunsTheLanguageValidators(unittest.TestCase):
    """Every rule i18n.check and i18n.check_complete enforce, exercised through
    a build.

    Deliberately through build_all rather than by calling the validator: that
    the validators work is already pinned by tests/test_i18n.py, and every one
    of these configurations passed the whole suite anyway -- because nothing in
    the build ever called them. What is under test here is the CALL SITE. A test
    that called check() directly would pass against the bug it exists to catch.
    """

    def test_a_base_language_outside_languages_fails_the_build(self):
        """The reported symptom: this used to fail incidentally, deep inside
        i18n.load(), with a bare `missing strings file:` and no mention of the
        key that was actually wrong."""
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="qq", languages=["en", "zz"]))
        message = str(err.value)
        assert "baseLanguage" in message
        assert "qq" in message

    def test_a_configured_language_with_no_strings_file_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=["en", "zz"]))
        assert "zz.json" in str(err.value)

    def test_a_language_key_that_is_not_two_letters_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=["en", "de-AT"]))
        assert "de-AT" in str(err.value)

    def test_an_empty_language_list_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=[]))
        assert "languages" in str(err.value)

    def test_a_translations_block_for_an_unconfigured_language_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=["en"], translations={"fr": {"defaultGloss": "x"}}))
        message = str(err.value)
        assert "fr" in message
        assert "translations" in message

    def test_a_language_missing_keys_fails_the_build(self):
        """Spec Decision 7 -- "a missing key is a build error" -- was simply not
        true of a build until the validator had a call site."""
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(strings={"de": {"shared": {"reportLabel": "Melden"}}}, languages=["en", "de"]))
        message = str(err.value)
        assert "de.json" in message
        assert "missing" in message

    def test_a_language_with_an_unknown_key_fails_the_build(self):
        """The other half of `exactly`: an extra key is a typo or a stale entry,
        and either way it is a string no page will ever show."""
        doc = json.loads((DATA / "strings" / "en.json").read_text(encoding="utf-8"))
        doc["shared"]["nosuchkey"] = "x"
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(strings={"de": doc}, languages=["en", "de"]))
        message = str(err.value)
        assert "de.json" in message
        assert "shared.nosuchkey" in message


class TestAMultiLanguagePageCarriesTheRuntime(unittest.TestCase):
    """A real built page, not the emitted string in isolation.

    Everything here is reachable only through build_page: the dictionary has to
    survive JSON encoding into a <script> body, the selector has to be emitted
    before the category lookup that depends on it, and the severity fix has to
    land on the page it exists for.
    """

    _page = staticmethod(multi_language_page)

    def test_the_selector_runs_before_the_category_lookup(self):
        """The lookup reads the words the selector chose. Emitted the other way
        round it would rewrite the gloss and then have it overwritten."""
        html = self._page("url-block-page")
        self.assertIn("navigator.languages", html)
        self.assertLess(html.index("navigator.languages"), html.index("getElementById('cat')"))

    def test_the_severity_pill_consults_the_selected_language(self):
        """BLOCKER. The category script re-sets .sev after the swap. Reading the
        baked-in base map there reverts the pill to English on exactly the two
        category-bearing pages without COPY_LOCK."""
        for page in ("url-block-page", "url-coach-text"):
            with self.subTest(page=page):
                html = self._page(page)
                self.assertIn("(t?t.s:", html, f"{page}: .sev is re-set from the base map alone")
                # "Caution" may appear as the base-language fallback map and as
                # the static pill, but never as the only source the runtime has.
                self.assertIn('"warn":"de:Caution"', html, f"{page}: the German label never reached the page")

    def test_no_placeholder_reaches_the_page_inside_the_dictionary(self):
        """The dictionary is JSON handed to textContent. assert_resolved does
        not look inside it, so this is the only thing that would notice."""
        for page in ("credential-block-page", "url-coach-text"):
            with self.subTest(page=page):
                self.assertNotIn("{{", self._page(page))

    def test_the_base_language_is_not_shipped_twice(self):
        """It is already the markup. A dictionary carrying it would be the
        largest single waste in the design."""
        html = self._page("url-block-page")
        self.assertIn('"de":{', html)
        self.assertNotIn('"en":{', html)


class TestTheRuntimeHandlesTheSafeSearchShape(unittest.TestCase):
    """safe-search-block-page is the one page whose EXTRA and ACTIONS do not
    look like everyone else's, and every assumption the runtime makes about
    page shape lands on it.

    It has no report button: its only `a.btn` is the settings link, and its
    `#rep` is an inline anchor inside a sentence whose text is the configured
    contact name -- not copy, and not the report label. Its `extra` is three
    fragments rather than one run of prose.

    None of this fires with a single language, which is exactly why it needs
    pinning: the first real `de.json` would ship all three at once.
    """

    _page = staticmethod(multi_language_page)

    def test_the_note_is_text_anchor_text(self):
        """The structural fact the childNodes[0] / childNodes[2] swap rests on.
        If the template ever grows a fourth node the indices move, and the
        swap would write the fragments into the wrong places in silence."""
        html = self._page("safe-search-block-page")
        note = re.search(r'<p class="note">(.*?)</p>', html, re.S)
        self.assertIsNotNone(note, "safe-search lost its .note paragraph")
        text, _anchor, tail = re.match(r'(.*?)(<a id="rep".*?</a>)(.*)', note.group(1), re.S).groups()
        self.assertTrue(text.strip(), "no text node before the contact anchor")
        self.assertTrue(tail.strip(), "no text node after the contact anchor")
        self.assertNotIn("<", text)
        self.assertNotIn("<", tail)
        self.assertIn("Still blocked", text)
        self.assertIn("IT will take a look", tail)

    def test_a_list_valued_extra_is_split_across_the_infobox_and_the_note(self):
        """`extra` here is [infobox sentence, note lead-in, note tail].

        Handed whole to textContent it stringifies: the infobox renders all
        three joined by commas, and the two halves of the .note sentence are
        never swapped at all.
        """
        html = self._page("safe-search-block-page")
        self.assertIn('"x":["de:Set SafeSearch', html, "the dictionary lost the split extra")
        code = runtime_code(html)
        self.assertNotIn("textContent=t.x", code, "a list-valued extra is assigned straight to textContent")
        self.assertIn("'.note'", code, "the .note fragments are never swapped")

    def test_the_report_label_is_scoped_to_the_report_button(self):
        """`#rep` is the report button on ten pages and an inline contact
        anchor on this one. Writing the report label into whatever `#rep`
        resolves to turns "Contact <address>" into "Contact Report to IT"."""
        html = self._page("safe-search-block-page")
        # The structural difference the scoping keys on.
        self.assertNotIn('class="btn" id="rep"', html)
        self.assertIn('<a id="rep"', html)
        code = runtime_code(html)
        self.assertNotIn("R.lastChild.nodeValue=t.rl", code, "the label is written into every #rep")
        self.assertIn("Q('a.btn')", code, "nothing scopes the label to the report button")
        # The mail body IS copy and must still follow the language.
        for field, key in (("data-subject", "t.rs"), ("data-intro", "t.ri"), ("data-prompt", "t.rp")):
            self.assertIn(f"R.setAttribute('{field}',{key})", code, f"{field} stopped being swapped")

    def test_the_report_button_still_takes_the_label_on_every_other_page(self):
        """The other half of the scoping: ten pages DO want t.rl in their
        button, and there the button and `#rep` are the same element."""
        html = self._page("url-block-page")
        self.assertIn('<a class="btn" id="rep"', html)
        self.assertIn("t.rl", runtime_code(html), "the report label is no longer swapped anywhere")

    def test_the_second_action_label_is_swapped(self):
        """`a2` is compiled for this page and nothing read it, so the settings
        button stayed in the base language on an otherwise-swapped page."""
        html = self._page("safe-search-block-page")
        self.assertIn('"a2":"de:Open search settings"', html)
        self.assertIn("t.a2", runtime_code(html), "a2 is compiled into the dictionary and never read")


class TestSingleLanguageIsFree(unittest.TestCase):
    def test_english_only_build_is_byte_identical(self):
        out, _result = built()
        checked = 0
        for key, want in SNAPSHOT.items():
            f = pathlib.Path(out) / "deploy" / key
            self.assertTrue(f.is_file(), f"{key} is missing from the build")
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertEqual(got, want, f"{key} changed; single-language output must stay byte-identical")
            checked += 1
        self.assertEqual(checked, len(SNAPSHOT))

    def test_built_file_set_matches_snapshot_exactly(self):
        out, _result = built()
        deploy_dir = pathlib.Path(out) / "deploy"

        # Walk deploy dir and collect all .html files as snapshot-style keys
        built_files = set()
        for html_file in deploy_dir.rglob("*.html"):
            # Get relative path from deploy_dir and convert to posix-style key
            rel_path = html_file.relative_to(deploy_dir)
            key = rel_path.as_posix()
            built_files.add(key)

        snapshot_files = set(SNAPSHOT.keys())

        # Check for extras and missing
        extras = built_files - snapshot_files
        missing = snapshot_files - built_files

        if extras or missing:
            msg_parts = []
            if extras:
                msg_parts.append(f"Extra files in build: {sorted(extras)}")
            if missing:
                msg_parts.append(f"Missing files from build: {sorted(missing)}")
            self.fail("; ".join(msg_parts))

        self.assertEqual(built_files, snapshot_files)
