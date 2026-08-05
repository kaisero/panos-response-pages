"""The gallery's Language control, and the preview-only runtime behind it.

Three claims, and each of them is invisible in the output if it stops being
true. The dropdown offers every language the tree ships even though the shipped
config turns on exactly one, so a config-driven regression would empty it
silently. The swap has to be callable from outside the page, because language is
not CSS and the gallery only reaches a frame after `load`. And none of it may
reach `deploy/`, where a dictionary the config never asked for is a page whose
language a customer cannot account for.

The byte-identity half of that last claim lives in tests/test_i18n_build.py,
which measures every built deploy file against a committed snapshot. What is
here is the shape: the name, the guard, the emitted script and the control.
"""

import json
import pathlib
import re
import shutil
import tempfile
import unittest
from typing import ClassVar

import pytest

from _build import DEFAULT_PALETTE, deploy_dir, preview_dir, translated_strings
from _paths import DATA
from panos_response_pages import i18n, scripts
from panos_response_pages.builder import load_themes
from panos_response_pages.config import load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.gallery import build_gallery
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette

pytestmark = pytest.mark.integration

SHIPPED = sorted(p.stem for p in (DATA / "strings").glob("*.json"))


def data_copy(**strings: dict) -> pathlib.Path:
    """A copy of the shipped tree with extra (or replaced) strings documents.

    A copy, never DATA: that tree is the installed package every other test
    builds from, and a file written into it would decide the outcome of tests
    that have nothing to do with languages.
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-preview-lang-")) / "data"
    shutil.copytree(DATA, root)
    for lang, doc in strings.items():
        (root / "strings" / f"{lang}.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


class TestEveryShippedLanguageNamesItself(unittest.TestCase):
    """The friendly name lives in the strings document, not in a table here.

    check_complete() enforces exact key parity, so a language physically cannot
    ship without one -- which is the whole reason it is there rather than in a
    Python map that could fall out of step.
    """

    def test_every_strings_file_carries_a_display_name(self):
        for lang in SHIPPED:
            with self.subTest(lang=lang):
                name = i18n.display_name(lang, DATA)
                self.assertTrue(name.strip(), f"{lang}.json has no `{i18n.NAME_KEY}`")
                self.assertNotEqual(name, lang, f"{lang}.json names itself with its own code")

    def test_the_names_are_the_ones_a_reviewer_reads(self):
        self.assertEqual(i18n.display_name("en", DATA), "English")
        self.assertEqual(i18n.display_name("de", DATA), "German")

    def test_a_document_without_one_falls_back_to_the_code(self):
        """A data directory made before this key existed must not fail a build
        over a string only the preview reads."""
        doc = translated_strings()
        doc.pop(i18n.NAME_KEY, None)
        self.assertEqual(i18n.display_name("zz", data_copy(zz=doc)), "zz")


class TestPreviewableIsEveryShippedLanguage(unittest.TestCase):
    """The owner's ruling: the dropdown offers every strings/*.json, whatever
    `languages` says. The shipped default is `languages: ["en"]`, so a
    config-driven list would be empty and the German in this tree unreachable."""

    CFG: ClassVar = {"baseLanguage": "en", "languages": ["en"]}

    def test_it_ignores_the_configured_language_list(self):
        self.assertEqual(sorted(i18n.previewable(self.CFG, DATA)), SHIPPED)
        self.assertEqual(i18n.languages(self.CFG), ["en"])

    def test_the_base_language_comes_first(self):
        """It is what the frames are served in, so it is the control's default
        and the one selection that calls nothing."""
        self.assertEqual(i18n.previewable({"baseLanguage": "de", "languages": ["de"]}, DATA)[0], "de")

    def test_a_file_out_of_step_with_the_base_is_left_out(self):
        """It would reach runtime_dict() as a KeyError naming a template key
        rather than the file. A half-written translation nobody configured must
        not be able to fail a build that is otherwise correct -- and left out of
        this list it is also left out of the dropdown, so there is no entry that
        selects nothing."""
        short = translated_strings("zz:")
        del short["shared"]["reportLabel"]
        self.assertNotIn("zz", i18n.previewable(self.CFG, data_copy(zz=short)))

    def test_a_complete_file_is_picked_up(self):
        """The other half: the exclusion above is about the key set, not about
        the language being unconfigured."""
        self.assertIn("zz", i18n.previewable(self.CFG, data_copy(zz=translated_strings("zz:"))))


class TestTheSwapIsPreviewOnly(unittest.TestCase):
    """Guarded the way redirect_demo is, and asserted over the real build."""

    def _page(self, preview: bool, **over):
        cfg = load_config("contoso", DATA / "config")
        palette = load_palette(DEFAULT_PALETTE, DATA / "palettes")
        return build_page("url-block-page", load_themes(DATA)[0], cfg, palette, preview, DATA / "templates", **over)

    def test_a_deploy_build_refuses_the_preview_language_list(self):
        with pytest.raises(BuildError) as err:
            self._page(False, preview_languages=("en", "de"))
        assert "preview" in str(err.value)
        assert "deploy" in str(err.value)

    def test_no_deploy_file_carries_the_swap(self):
        """Over every built file, not one sample: the global is emitted from a
        branch that would land on all of them at once."""
        hits = [p.name for p in sorted(deploy_dir().rglob("*.html")) if scripts.PREVIEW_SWAP in p.read_text("utf-8")]
        self.assertEqual(hits, [])

    def test_no_deploy_file_compiles_a_language_the_config_did_not_ask_for(self):
        """The shipped config lists `en` alone, so a deploy page must carry no
        runtime dictionary at all. This is what the byte-identity snapshot means
        in words."""
        hits = [p.name for p in sorted(deploy_dir().rglob("*.html")) if "navigator.languages" in p.read_text("utf-8")]
        self.assertEqual(hits, [])

    def test_a_preview_page_carries_both(self):
        page = self._page(True, preview_languages=("en", "de"))
        self.assertIn(scripts.PREVIEW_SWAP, page)
        self.assertIn('"de"', page.split("navigator.languages")[0])

    def test_a_preview_build_without_the_list_carries_neither(self):
        """`preview` alone is not the trigger. The list is, so a caller that
        wants a preview page without the gallery's machinery still gets the
        page the config describes."""
        page = self._page(True)
        self.assertNotIn(scripts.PREVIEW_SWAP, page)
        self.assertNotIn("navigator.languages", page)


class TestTheEmittedSwap(unittest.TestCase):
    """The apply half is the SAME bytes either way.

    That is the property that makes the preview worth looking at: a swap with
    its own copy of the runtime would be a preview of itself, not of the page.
    """

    SEVERITY: ClassVar = {"calm": "", "warn": "Caution", "crit": "Security risk"}

    def _js(self, **over):
        kwargs = {
            "lock_copy": True,
            "has_category": False,
            "email_mode": False,
            "severity": self.SEVERITY,
            "lang_dict": '{"de":{}}',
        }
        kwargs.update(over)
        categories = kwargs.pop("categories", {})
        return scripts.category_js(categories, "d", "r", **kwargs)

    def test_the_apply_half_is_identical_in_both_forms(self):
        deploy = self._js()
        preview = self._js(swap_global="X")
        body = deploy.split("if(t){", 1)[1].rsplit("}", 2)[0]
        self.assertGreater(len(body), 800, "the apply half was not found; this test is asserting nothing")
        self.assertIn(body, preview)

    def test_the_deploy_form_gains_nothing(self):
        """swap_global defaults to empty, so every existing caller keeps the
        bytes tests/_build.py's golden LANGUAGE_BLOCK pins."""
        self.assertEqual(self._js(), self._js(swap_global=""))
        self.assertNotIn("window.", self._js())

    def test_the_swap_refuses_a_language_it_does_not_carry(self):
        self.assertIn("function(L){if(!T[L])return;", self._js(swap_global="X"))

    def test_the_swap_re_resolves_the_category_gloss(self):
        """The lookup that owns the gloss destroys the raw category name it
        reads, so it cannot run twice. Without this the swap puts the page's own
        gloss back over the category's, and the preview shows a generic sentence
        where the served page shows the tailored one."""
        js = self._js(swap_global="X", lock_copy=False, has_category=True, categories={})
        self.assertIn("if(g)g.textContent=m?((t.c&&t.c[k])||(m[0]=='calm'?t.dg:t.rg)):t.dg;", js)

    def test_a_copy_locked_page_does_not_re_resolve_it(self):
        """It declares no `m` to read: the lookup's tone/gloss half is exactly
        what COPY_LOCK drops, so the statement would be a ReferenceError."""
        self.assertNotIn("t.dg:t.rg", self._js(swap_global="X", has_category=True))

    def test_a_single_language_build_emits_no_swap_even_in_preview(self):
        self.assertNotIn("window.", self._js(lang_dict="", swap_global="X"))


class TestTheGalleryControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (preview_dir() / "index.html").read_text(encoding="utf-8")

    def test_the_control_lists_friendly_names_not_codes(self):
        rows = re.findall(r'<li role="option" data-value="(\w+)"[^>]*>([^<]*)</li>', self.index)
        offered = {code: label for code, label in rows if code in SHIPPED}
        self.assertEqual(offered, {"en": "English", "de": "German"})

    def test_the_control_opens_on_the_base_language(self):
        self.assertIn('<span id="langlabel">English</span>', self.index)
        self.assertIn('var BASELANG="en"', self.index)

    def test_the_frame_is_swapped_on_load_and_before_it_is_measured(self):
        """fit() sizes the frame to its content, and the swap changes how much
        content there is."""
        squeezed = re.sub(r"\s+", "", self.index)
        self.assertIn('if(S.lang!==BASELANG&&w&&typeofw[SWAP]==="function")w[SWAP](S.lang);', squeezed)
        self.assertLess(squeezed.index("w[SWAP](S.lang)"), squeezed.index("fit(i);"))

    def test_langok_names_exactly_the_styles_that_compiled_the_languages(self):
        """A style that declares `"i18n": false` renders the base language and
        nothing else, so selecting it must take the control away rather than
        leave a dropdown whose frames cannot answer it."""
        themes = load_themes(DATA)
        expected = {t["name"] for t in themes if i18n.enabled(t)}
        self.assertNotIn("nyan", expected)

        match = re.search(r"LANGOK=(\{.*?\}),SWAP=", self.index)
        self.assertIsNotNone(match, "LANGOK not found in generated index.html")
        self.assertEqual(set(json.loads(match.group(1))), expected)

    def test_the_control_hides_itself_on_a_style_that_carries_none(self):
        self.assertIn("if(L) L.hidden = !LANGOK[S.theme];", self.index)
        self.assertIn(".ctl[hidden]{display:none}", self.index)

    def test_a_single_language_tree_gets_no_control(self):
        """A data directory predating the strings tree has exactly one, and a
        one-entry dropdown is a label pretending to be a control."""
        theme = load_themes(DATA)[0]
        palette = load_palette(DEFAULT_PALETTE, DATA / "palettes")
        blobs = {(theme["name"], palette["name"], "url-block-page"): "<html></html>"}
        gallery, _ = build_gallery(
            [theme],
            ["url-block-page"],
            blobs,
            {"company": "Acme"},
            palette,
            [palette],
            languages=[("en", "English")],
            base_language="en",
        )
        self.assertNotIn('id="langgrp"', gallery)


if __name__ == "__main__":
    unittest.main()
