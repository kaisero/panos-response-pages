"""Multi-language builds, and the promise that single-language builds are free.

The byte-identity assertion is the load-bearing one. `languages: ["en"]` must
produce exactly the bytes a build produced before this feature existed -- that
is what makes multi-language support cost nothing for every customer who does
not want it, and asserting it is how it stays true.

If this test fails, the change that broke it is wrong. Do NOT regenerate the
snapshot to make it pass.
"""

import functools
import hashlib
import json
import pathlib
import re
import shutil
import tempfile
import unittest

import pytest

from _build import LANGUAGE_BLOCK, built, translated_strings
from _paths import DATA, ROOT
from panos_response_pages.builder import build_all, load_themes
from panos_response_pages.config import load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.validate import PAGE_TOKENS

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


@functools.cache
def language_root(base: str = "en") -> pathlib.Path:
    """A data directory with English and German configured, built once.

    Cached because broken_data_dir() copies the whole shipped tree, and the
    page-independence sweep below asks for eleven pages of it.
    """
    return broken_data_dir(strings={"de": translated_strings()}, baseLanguage=base, languages=["en", "de"])


@functools.cache
def multi_language_page(name: str, base: str = "en", shell: int = 0) -> str:
    """One page built with a second language configured, as HTML.

    A real build_page, not the emitted script in isolation: the dictionary has
    to survive JSON encoding into a <script> body, and the selector has to be
    emitted before the category lookup that depends on it.
    """
    root = language_root(base)
    cfg = load_config("contoso", root / "config")
    palette = load_palette("cyber-orange", root / "palettes")
    return build_page(name, load_themes(root)[shell], cfg, palette, False, root / "templates")


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

    def test_an_empty_string_fails_the_build(self):
        """An empty fragment has the right key at the right index, so it passes
        every other check in the file -- and renders no text node, which
        collapses the sentence the runtime swaps and leaves it in the base
        language. Silent in the output, so it has to be loud here."""
        doc = translated_strings()
        doc["pages"]["safe-search-block-page"]["extra"][0] = ""
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(strings={"de": doc}, languages=["en", "de"]))
        message = str(err.value)
        assert "de.json" in message
        assert "pages.safe-search-block-page.extra[0]" in message


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

    def test_the_language_block_is_the_same_bytes_on_every_page(self):
        """The claim the golden string rests on.

        The swap selects by DOM shape and never by page name, so every page
        emits the identical block -- which is what makes one golden assertion
        cover the whole build. Asserted rather than assumed: a page-conditional
        branch added here would quietly halve the coverage of that assertion.
        """
        for page in sorted(PAGE_TOKENS):
            with self.subTest(page=page):
                self.assertIn("," + LANGUAGE_BLOCK, self._page(page), f"{page}: the emitted language block moved")

    def test_the_language_block_is_the_same_bytes_in_every_shell(self):
        """The other axis. The shells differ in markup, not in what the swap
        looks for, so none of them may change a byte of it."""
        for shell in range(len(load_themes(language_root()))):
            with self.subTest(shell=shell):
                html = multi_language_page("url-block-page", shell=shell)
                self.assertIn("," + LANGUAGE_BLOCK, html, "the emitted language block is shell-dependent")

    def test_the_severity_pill_consults_the_selected_language(self):
        """BLOCKER. The category script re-sets .sev after the swap. Reading the
        baked-in base map there reverts the pill to English on exactly the two
        category-bearing pages without COPY_LOCK."""
        for page in ("url-block-page", "url-coach-text"):
            with self.subTest(page=page):
                html = self._page(page)
                self.assertIn(
                    "var v=document.querySelector('.sev');if(v)v.textContent=(t?t.s:",
                    html,
                    f"{page}: .sev is re-set from the base map alone",
                )
                # "Caution" may appear as the base-language fallback map and as
                # the static pill, but never as the only source the runtime has.
                self.assertIn('"warn":"de:Caution"', html, f"{page}: the German label never reached the page")

    def test_no_placeholder_reaches_the_page_inside_the_dictionary(self):
        """The dictionary is JSON handed to textContent. assert_resolved does
        not look inside it, so this is the only thing that would notice."""
        for page in ("credential-block-page", "url-coach-text"):
            with self.subTest(page=page):
                self.assertNotIn("{{", self._page(page))

    def test_a_per_language_categories_block_reaches_the_page_resolved(self):
        """The optional block, end to end. en.json ships none, so no build from
        the shipped tree touches this path -- and the value it carries is copy
        like any other, free to contain {{COMPANY}}. Assigned raw it reached
        assert_resolved and failed the build naming the page and nothing else;
        the German reader would have been the one to find out what was wrong."""
        doc = translated_strings()
        doc["categories"] = {"malware": "Von {{COMPANY}} gesperrt."}
        root = broken_data_dir(strings={"de": doc}, languages=["en", "de"])
        cfg = load_config("contoso", root / "config")
        palette = load_palette("cyber-orange", root / "palettes")
        html = build_page("url-block-page", load_themes(root)[0], cfg, palette, False, root / "templates")
        self.assertIn(f'"c":{{"malware":"Von {cfg["company"]} gesperrt."}}', html)
        self.assertNotIn("{{", html)

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

    # The three statements the page shapes below are distinguished by, whole.
    # Asserted entire rather than by a fragment of themselves: `Q('a.btn')`
    # appears in a correct line and in one that writes the report label into
    # whatever control the firewall injected, and a test that cannot tell those
    # apart is not testing the thing it names.
    BUTTON = "var B=Q('a.btn#rep')||Q('a.btn');if(B)B.textContent=t.a2||t.rl;"
    REPORT = (
        "var R=Q('#rep');if(R){R.setAttribute('data-subject',t.rs);"
        "R.setAttribute('data-intro',t.ri);R.setAttribute('data-prompt',t.rp)}"
    )
    EXTRA = (
        "var X=Q('.infobox span,.warnline span'),x=t.x||'';"
        "if(x.pop){if(S(X,x[0],x[2],x[1]))X=0;else S(Q('.note'),x[1],x[2]);x=x[0]}"
        "if(X&&x)X.textContent=x;"
    )

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
        self.assertIn(self.EXTRA, code, "the .note fragments are never swapped")

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
        self.assertIn(self.BUTTON, code, "nothing scopes the label to the report button")
        # The mail body IS copy and must still follow the language.
        self.assertIn(self.REPORT, code, "the mail body fields stopped being swapped")

    def test_the_report_button_still_takes_the_label_on_every_other_page(self):
        """The other half of the scoping: ten pages DO want t.rl in their
        button, and there the button and `#rep` are the same element."""
        html = self._page("url-block-page")
        self.assertIn('<a class="btn" id="rep"', html)
        self.assertIn(self.BUTTON, runtime_code(html), "the report label is no longer swapped anywhere")

    def test_the_label_prefers_the_report_button_over_injected_markup(self):
        """querySelector returns the first match in DOCUMENT ORDER, and three
        pages carry a PAN-OS token ahead of their report anchor: <pan_form/> on
        both coach pages, <cookie/> on file-block-continue. The firewall expands
        those at serve time into markup this repository never sees.

        A bare Q('a.btn') therefore makes the label's destination depend on what
        PAN-OS injects -- on the two pages the report feature is built around.
        Whether its Continue control carries an a.btn cannot be established
        here, which is the point: preferring #rep, which is ours and which the
        firewall never injects, removes the question instead of betting on it.
        """
        for page, token in (
            ("url-coach-text", "<pan_form/>"),
            ("credential-coach-text", "<pan_form/>"),
            ("file-block-continue-page", "<cookie/>"),
        ):
            with self.subTest(page=page):
                html = self._page(page)
                # The premise: the injected token really does precede the anchor.
                self.assertLess(html.index(token), html.index('id="rep"'), f"{page}: {token} no longer leads")
                self.assertIn(self.BUTTON, runtime_code(html), f"{page}: the label is not scoped to #rep first")

    def test_the_second_action_label_is_swapped(self):
        """`a2` is compiled for this page and nothing read it, so the settings
        button stayed in the base language on an otherwise-swapped page."""
        html = self._page("safe-search-block-page")
        self.assertIn('"a2":"de:Open search settings"', html)
        self.assertIn(self.BUTTON, runtime_code(html), "a2 is compiled into the dictionary and never read")


class TestTheRuntimeHandlesInlineMarkupInACallout(unittest.TestCase):
    """url-coach-text is the second container shape a list-valued `extra` has.

    Its info box emphasises the phrase that IS the warning -- continuing grants
    the category, not the page -- so the span reads text, <strong>, text. That
    is the same three-node shape as .plain and .note, but the middle node is
    copy here rather than a build-time anchor, and there is no .note beneath it
    to take fragments 1 and 2.

    Read as one string the markup renders escaped in every language but the
    base one: a German reader sees the characters `<strong>`.
    """

    _page = staticmethod(multi_language_page)

    def test_the_callout_is_text_strong_text(self):
        """The structural fact the in-place swap rests on. A fourth node, or a
        second element, moves the indices and the fragments land wrong."""
        html = self._page("url-coach-text")
        span = re.search(r'<p class="infobox">.*?<span>(.*?)</span>', html, re.S).group(1)
        lead, _strong, tail = re.match(r"(.*?)(<strong>.*?</strong>)(.*)", span, re.S).groups()
        self.assertTrue(lead.strip() and tail.strip(), "no text node either side of the <strong>")
        self.assertNotIn("<", lead)
        self.assertNotIn("<", tail)
        self.assertIsNone(re.search(r'<p class="note">', html), "url-coach has no .note to take the fragments")

    def test_the_emphasised_phrase_is_swapped_with_the_text_around_it(self):
        html = self._page("url-coach-text")
        self.assertIn('"x":["de:Continuing grants access to ', html, "the dictionary lost the split extra")
        code = runtime_code(html)
        self.assertNotIn("textContent=t.x", code, "a list-valued extra is assigned straight to textContent")
        self.assertIn(
            "var S=function(e,a,b,c){if(e&&e.childNodes.length>2){"
            "e.childNodes[0].nodeValue=a;e.childNodes[2].nodeValue=b;"
            "if(c!=null)e.childNodes[1].textContent=c;return 1}};",
            code,
            "the emphasised phrase is never swapped",
        )

    def test_no_dictionary_value_carries_a_tag(self):
        """The whole point of the split: what reaches textContent is text."""
        for name in ("url-coach-text", "safe-search-block-page"):
            with self.subTest(page=name):
                html = self._page(name)
                dictionary = re.search(r"var T=(\{.*?\}),LS=", html, re.S).group(1)
                self.assertNotIn("<", dictionary, "markup inside the dictionary renders escaped")

    def test_the_other_shapes_are_untouched(self):
        """One expression covers three containers, so the two that worked
        before have to keep working: safe-search's fragments still straddle its
        .note anchor, and a string-valued extra still fills the callout."""
        extra = TestTheRuntimeHandlesTheSafeSearchShape.EXTRA
        self.assertIn(extra, runtime_code(self._page("safe-search-block-page")), "the .note fragments moved")
        self.assertIn(extra, runtime_code(self._page("url-block-page")), "a string-valued extra moved")


class TestTheDocumentDeclaresItsBaseLanguage(unittest.TestCase):
    """`<html lang>` has to say what the markup actually is.

    The markup IS the base language, and the selection loop breaks on the base
    language WITHOUT assigning documentElement.lang -- so with a hardcoded
    lang="en" a German-base page served to a German browser keeps `en`, and the
    timestamp, which formats to `document.documentElement.lang||undefined`,
    renders an en-US date on a German page. Nothing else on the page would
    look wrong, which is why it needs a test rather than an eye.
    """

    def test_an_english_base_still_renders_lang_en(self):
        """The byte-identity side of the substitution: every existing config
        has an English base, and for those this must render the same bytes the
        attribute was written with."""
        self.assertIn('<html lang="en" data-tone=', multi_language_page("url-block-page"))

    def test_a_german_base_renders_lang_de(self):
        html = multi_language_page("url-block-page", base="de")
        self.assertIn('<html lang="de" data-tone=', html)
        self.assertNotIn('<html lang="en"', html)

    def test_every_shell_declares_it(self):
        """Seven shells, one attribute each, and a shell that kept the literal
        would ship a German page claiming to be English in exactly one theme."""
        for shell in sorted((DATA / "templates" / "shells").glob("*.html")):
            with self.subTest(shell=shell.stem):
                self.assertIn('<html lang="{{BASE_LANG}}" data-tone=', shell.read_text(encoding="utf-8"))

    def test_the_declared_language_is_the_one_the_dictionary_omits(self):
        """The two halves of the same fact. The base language is the markup, so
        it is what `lang` declares AND the one language the runtime dictionary
        does not carry -- if they ever disagreed the page would advertise a
        language it also shipped a translation of."""
        html = multi_language_page("url-block-page", base="de")
        self.assertIn('var T={"en":{', html)
        self.assertNotIn('"de":{', html)


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
