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

from _build import LANGUAGE_BLOCK, built, built_with_languages, translated_strings
from _paths import DATA, ROOT
from panos_response_pages import i18n, redirect
from panos_response_pages.builder import build_all, format_report, load_themes
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


def stand_in_strings(*langs: str) -> dict:
    """Documents for the languages the packaged tree does not ship.

    A language the tree DOES ship is left alone, so a test that wants German
    weight gets real German. The rest get the prefixed stand-in, because
    check_complete() refuses a configured language with no file and a test about
    the byte ceiling would otherwise fail for a reason that is not the ceiling.
    """
    return {lang: translated_strings(f"{lang}:") for lang in langs if not (DATA / "strings" / f"{lang}.json").exists()}


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

    def test_the_language_block_is_the_same_bytes_in_every_shell_that_carries_it(self):
        """The other axis. The shells differ in markup, not in what the swap
        looks for, so none of them may change a byte of it.

        A style declaring `"i18n": false` carries no swap at all, which is not a
        counterexample to that claim -- it is the absence of the thing the claim
        is about. Skipped by reading the flag rather than by naming nyan, and
        counted, because a skip that silently emptied this sweep would leave the
        golden block asserted against nothing.
        """
        themes = load_themes(language_root())
        checked = 0
        for shell, theme in enumerate(themes):
            if not i18n.enabled(theme):
                continue
            with self.subTest(shell=shell, theme=theme["name"]):
                html = multi_language_page("url-block-page", shell=shell)
                self.assertIn("," + LANGUAGE_BLOCK, html, "the emitted language block is shell-dependent")
                checked += 1
        self.assertEqual(checked, sum(1 for t in themes if i18n.enabled(t)))
        self.assertGreater(checked, 1, "the sweep is asserting the golden block against one shell or none")

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


class TestThemeOptOut(unittest.TestCase):
    """A style with no room for a second language says so, in its own file.

    nyan's URL block page is 15108 B in English against a 17999 B ceiling: 2891
    B of headroom, and one language costs it 2262 B. Its star field and its
    sprite artwork are half the file, so capping the design around a dictionary
    would be the tail wagging the dog -- it is a novelty style. The flag is what
    lets the other six carry as many languages as they fit while nyan carries
    none.
    """

    def test_nyan_declares_no_i18n(self):
        theme = json.loads((DATA / "themes/nyan.json").read_text(encoding="utf-8"))
        self.assertFalse(theme.get("i18n", True))

    def test_opted_out_theme_ships_base_language_only(self):
        """Both halves. `nyan` carrying no runtime is only correct if the same
        build gives every other style one -- otherwise this passes on a build
        that compiled no languages at all."""
        out, _result = built_with_languages(("en", "de"))
        nyan = (out / "deploy/nyan/prisma-blue/url-block-page.html").read_text(encoding="utf-8")
        glass = (out / "deploy/glass/prisma-blue/url-block-page.html").read_text(encoding="utf-8")
        self.assertNotIn("navigator.languages", nyan, "nyan must not carry the language runtime")
        self.assertIn("navigator.languages", glass)

    def test_the_opted_out_theme_carries_no_dictionary_either(self):
        """The runtime is the smaller half. A style that emitted the selector's
        absence but kept the JSON would pay the whole cost for nothing."""
        out, _result = built_with_languages(("en", "de"))
        nyan = (out / "deploy/nyan/prisma-blue/url-block-page.html").read_text(encoding="utf-8")
        self.assertNotIn("var T={", nyan)

    def test_the_opt_out_is_what_keeps_nyan_under_the_ceiling(self):
        """The number the flag exists for, measured rather than asserted from a
        comment. If nyan ever fits a second language this test says so, and the
        flag can go."""
        _out, result = built_with_languages(("en", "de"))
        sizes = {r.theme: max(x.size for x in result.results if x.theme == r.theme) for r in result.results}
        self.assertEqual(sizes["nyan"], max(x.size for x in built()[1].results if x.theme == "nyan"))
        self.assertGreater(sizes["glass"], max(x.size for x in built()[1].results if x.theme == "glass"))

    def test_every_other_theme_ships_every_language(self):
        """The opt-out is one style's decision, not a licence for any style to
        quietly ship less than the config asked for."""
        _out, result = built_with_languages(("en", "de"))
        for theme in load_themes(DATA):
            with self.subTest(theme=theme["name"]):
                want = ["en"] if theme["name"] == "nyan" else ["en", "de"]
                self.assertEqual(result.theme_languages[theme["name"]], want)


class TestTheReportNamesTheLanguages(unittest.TestCase):
    """A style shipping fewer languages than the config lists is exactly the
    invisible failure this project refuses. It has to be on the row."""

    def test_the_table_names_the_language_set(self):
        _out, result = built_with_languages(("en", "de"))
        text = format_report(result)
        row = next(ln for ln in text.splitlines() if ln.split()[:2] == ["glass", "prisma-blue"])
        self.assertIn("en,de", row)

    def test_the_opted_out_row_says_so(self):
        _out, result = built_with_languages(("en", "de"))
        text = format_report(result)
        row = next(ln for ln in text.splitlines() if ln.split()[:2] == ["nyan", "prisma-blue"])
        self.assertIn("i18n:false", row)
        self.assertNotIn("en,de", row)

    def test_a_single_language_build_claims_no_opt_out(self):
        """Nothing is dropped when there is nothing to drop, so nyan's row must
        not carry a marker that would read as a missing language."""
        text = format_report(built()[1])
        self.assertNotIn("i18n:false", text)


class TestTheCeilingErrorNamesTheLanguageSet(unittest.TestCase):
    """An overflow that actually happens, so the message on it is one somebody
    has read.

    PAN-OS does not refuse an oversize response page -- it serves its own
    default instead, with the import still reporting success. This error is the
    entire feedback loop, so it has to say what made the page big and what the
    reader can take out. Twelve languages is well past anything sensible; that
    is the point. It is the shape of the config that walks into this, and the
    message has to be useful the first time it appears.

    Twelve rather than the ten it takes to break the first style, because at
    twelve every style that compiles languages is over -- which is what makes
    the survivor below mean something.
    """

    LANGS = ("en", "de", "fr", "it", "es", "nl", "pt", "pl", "cs", "sv", "da", "fi")

    @classmethod
    def setUpClass(cls):
        root = broken_data_dir(
            # Every language, German included, so the sizes here do not depend
            # on which real translations happen to have shipped.
            strings={lang: translated_strings(f"{lang}:") for lang in cls.LANGS[1:]},
            baseLanguage="en",
            languages=list(cls.LANGS),
        )
        cls.result = build_all(root, root / "out", preview=False, write=False)
        cls.errors = [e for r in cls.result.results for e in r.errors]

    def test_the_build_fails(self):
        self.assertTrue(self.result.failed, "ten languages fit under the ceiling; the fixture no longer overflows")
        self.assertTrue(self.errors)

    def test_the_error_states_the_overshoot(self):
        worst = max(self.result.results, key=lambda r: r.size)
        self.assertGreater(worst.size, 17999)
        self.assertTrue(
            any(f"by {worst.size - 17999} B" in e for e in self.errors),
            f"no error quotes the overshoot: {self.errors[:1]}",
        )

    def test_the_error_names_every_language_that_produced_the_size(self):
        """ "Too big" is not actionable on its own. The language set is the one
        thing about an oversize page the reader can change in a single line."""
        for error in self.errors:
            with self.subTest(error=error[:60]):
                self.assertIn(f"built with {len(self.LANGS)} languages", error)
                for lang in self.LANGS:
                    self.assertIn(lang, error)

    def test_the_error_offers_the_two_ways_out(self):
        """The optional block first, because it costs the least to give up, and
        the style-level opt-out second, for a style with no room for any of it."""
        for error in self.errors:
            with self.subTest(error=error[:60]):
                self.assertIn("`categories` block", error)
                self.assertIn('"i18n": false', error)

    def test_the_report_names_the_style_and_the_page(self):
        """The message says what is in the page; the row it hangs under says
        which page. Neither is any use without the other."""
        text = format_report(self.result)
        worst = max(self.result.results, key=lambda r: r.size)
        self.assertIn(f"{worst.theme}/{worst.palette}/{worst.page}", text)
        self.assertIn("exceeds the 17999 B ceiling", text)

    def test_the_opted_out_style_is_the_one_that_survives(self):
        """nyan is the largest style in the tree and the only one still under
        the ceiling, because it compiled none of these languages. This is what
        the flag buys, measured rather than argued."""
        failed = {r.theme for r in self.result.results if r.errors}
        self.assertNotIn("nyan", failed)
        self.assertEqual(failed, {t["name"] for t in load_themes(DATA) if t["name"] != "nyan"})


class TestTheRedirectAndASecondLanguageShareTheMargin(unittest.TestCase):
    """Both features spend the same headroom, and nothing refuses the pair.

    The redirect notice is a flat 3347 B and German is ~2260 B on the page they
    both land on, so together they put `beacon`, `glass` and `mesh` into the warn
    band -- inside 2000 B of a ceiling PAN-OS enforces silently. No style
    breaches it.

    THE DECISION, recorded here because this is where it is checkable: the
    combination stays ALLOWED and stays a warning.

    * Refusing it would punish a correct, opt-in configuration for a property of
      a style the customer may not even deploy -- which is the reasoning
      `redirect.supported` already gives for being a declared flag rather than a
      measured one. Inverting it here would make the module contradict itself.
    * Making `supported()` language-aware would drop the notice from three
      styles the moment a second language was configured, for every user of
      them, to protect a margin the English page never approaches -- and the
      customer would see a feature disappear because they turned on German.
      That is a silent failure with a config key for a cause, which is the exact
      class of thing this project exists to refuse.
    * What the warn band protects is serve-time `<url/>` expansion, and 1350 B
      -- the tightest case -- is still a longer URL than the fact row can show.

    So it warns, the warning names the language set that spent the margin, and
    this test fails the day the pair stops fitting.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = broken_data_dir(
            strings=stand_in_strings("de"),
            baseLanguage="en",
            languages=["en", "de"],
            redirect={
                "enabled": True,
                "seconds": 10,
                "message": "Taking you to {app} -- the approved alternative for this.",
                "categories": {
                    "online-storage-and-backup": {"app": "Company Drive", "url": "https://drive.example.com/"}
                },
            },
        )
        cls.result = build_all(cls.root, cls.root / "out", preview=False, write=False)

    def test_the_pair_is_allowed(self):
        """`redirect.supported` takes a theme and nothing else. It has no notion
        of language and this test says that is deliberate."""
        self.assertTrue(self.result.results)
        self.assertFalse(self.result.failed, "the redirect and a second language no longer fit together")

    def test_nothing_breaches_the_ceiling(self):
        for r in self.result.results:
            with self.subTest(theme=r.theme, page=r.page):
                self.assertLessEqual(r.size, 17999, f"{r.theme}/{r.page} would be dropped silently by PAN-OS")

    def test_a_page_that_spends_the_margin_says_what_spent_it(self):
        """The warn line is the margin `<url/>` needs at serve time. A page that
        entered the band by gaining a language has to say so, or the reader has
        no way to tell a tight style from a tight configuration."""
        for r in self.result.results:
            for w in r.warnings:
                if "of the ceiling" in w:
                    with self.subTest(theme=r.theme, page=r.page):
                        self.assertIn("built with 2 languages (en, de)", w)

    def test_the_notice_still_reaches_every_style_that_declares_it(self):
        """The alternative this decision rejects, asserted as an absence: no
        style loses the notice for having gained a language."""
        cfg = load_config("contoso", self.root / "config")
        for theme in load_themes(self.root):
            with self.subTest(theme=theme["name"]):
                html = build_page(
                    "url-block-page",
                    theme,
                    cfg,
                    load_palette("cyber-orange", self.root / "palettes"),
                    False,
                    self.root / "templates",
                )
                self.assertEqual(redirect.supported(theme), 'id="rx"' in html)


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
