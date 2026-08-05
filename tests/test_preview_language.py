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
from panos_response_pages import datadir, i18n, scripts
from panos_response_pages.builder import load_themes
from panos_response_pages.config import load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.gallery import build_gallery
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.portal.page import build_portal_page

pytestmark = pytest.mark.integration

SHIPPED = sorted(p.stem for p in (DATA / "strings").glob("*.json"))

PORTAL_TEMPLATES = datadir.portal_data(DATA) / "templates"


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


class TestThePortalPreviewAnswersTheSameControl(unittest.TestCase):
    """The GlobalProtect surfaces sit in the same gallery, under their own group
    in the Page control, and they used to ignore the Language control entirely:
    the swap global simply was not on them. A reviewer selected German, watched
    every block page translate, clicked a portal surface and got English -- with
    the control still sitting there implying otherwise.

    The fix is the same hook under the same name, so the gallery's load handler
    needs to know nothing about which family a frame belongs to. What is here is
    that it is present in preview, absent from deploy, and that the apply half a
    swap runs is the apply half the page ran at load.
    """

    THEME = "assist"
    OPTED_OUT = "nyan"

    @classmethod
    def theme(cls, name):
        return next(t for t in load_themes(DATA) if t["name"] == name)

    def _import(self, page, theme=None, **over):
        cfg = load_config("contoso", DATA / "config")
        palette = load_palette(DEFAULT_PALETTE, DATA / "palettes")
        return build_portal_page(page, self.theme(theme or self.THEME), cfg, palette, PORTAL_TEMPLATES, **over)

    def test_a_deploy_import_refuses_the_preview_language_list(self):
        """Guarded exactly as build_page's list is. This one matters more: the
        import is a file a customer uploads to a firewall by hand."""
        for page in ("login", "home"):
            with self.subTest(page=page), pytest.raises(BuildError) as err:
                self._import(page, preview_languages=("en", "de"))
            assert "preview" in str(err.value)
            assert "deploy" in str(err.value)

    def test_no_deploy_portal_import_carries_the_swap(self):
        """The block-page sweep walks deploy/ whole and so already covers these.
        Counted separately all the same, because that sweep would still pass if
        the portal imports stopped being written there at all."""
        found = sorted(deploy_dir().rglob("portal/*.html"))
        self.assertGreater(len(found), 40, "the portal sweep is asserting nothing")
        for path in found:
            with self.subTest(path=path.relative_to(deploy_dir())):
                text = path.read_text("utf-8")
                self.assertNotIn(scripts.PREVIEW_SWAP, text)
                self.assertNotIn("navigator.languages", text)

    def test_the_preview_imports_carry_the_swap_and_the_shipped_languages(self):
        """`languages` is `["en"]` on the shipped config, so the deploy imports
        carry no dictionary at all -- previewable() is what puts the German this
        tree ships in front of a reviewer."""
        for page in ("login", "home"):
            with self.subTest(page=page):
                text = self._import(page, preview=True, preview_languages=("en", "de"))
                self.assertIn(scripts.PREVIEW_SWAP, text)
                self.assertIn("navigator.languages", text)
                self.assertIn('"de"', text)

    def test_a_preview_import_without_the_list_carries_neither(self):
        """`preview` alone is not the trigger, exactly as it is not for a block
        page: a caller wanting the import the config describes still gets it."""
        for page in ("login", "home"):
            with self.subTest(page=page):
                text = self._import(page, preview=True)
                self.assertNotIn(scripts.PREVIEW_SWAP, text)
                self.assertNotIn("navigator.languages", text)

    def test_the_apply_half_is_identical_in_both_forms(self):
        """The property that makes the preview worth looking at, and the reason
        the emission is a split rather than a second runtime. Measured against a
        two-language DEPLOY import, which is the form a firewall serves."""
        from panos_response_pages.portal.page import _I18N, _I18N_TAIL, _i18n_script

        for page in ("login", "home"):
            with self.subTest(page=page):
                deploy = _i18n_script(page, '{"de":{}}', "en")
                preview = _i18n_script(page, '{"de":{}}', "en", swap=True)
                # home's apply half is three statements; login's is the form
                # swap and everything around it. A floor each, so neither can
                # empty out and leave this asserting a substring of "".
                self.assertGreater(len(_I18N[page]), {"login": 800, "home": 50}[page])
                self.assertIn(_I18N[page], deploy)
                self.assertIn(_I18N[page], preview)
                self.assertTrue(deploy.rstrip().endswith(_I18N_TAIL + "\n</script>".rstrip()))
                self.assertNotIn("window." + scripts.PREVIEW_SWAP, deploy)

    def test_the_deploy_form_gains_nothing_from_the_split(self):
        """`swap` defaults to False, so every existing caller keeps the bytes
        tests/test_i18n_build.py's committed sha256 snapshot pins."""
        from panos_response_pages.portal.page import _i18n_script

        self.assertEqual(_i18n_script("login", '{"de":{}}', "en"), _i18n_script("login", '{"de":{}}', "en", swap=False))

    def test_an_opted_out_style_gets_no_hook_either(self):
        """`i18n: false` is theme-level and disables BOTH families -- so the
        preview must not quietly hand nyan a control the gallery has already
        decided to hide for it."""
        for page in ("login", "home"):
            with self.subTest(page=page):
                text = self._import(page, theme=self.OPTED_OUT, preview=True, preview_languages=("en", "de"))
                self.assertNotIn(scripts.PREVIEW_SWAP, text)
                self.assertNotIn("navigator.languages", text)

    def test_the_swap_re_labels_the_computed_download_button(self):
        """The download widget's six strings are JS literals computed from the
        user agent, in a block that moves PAN-OS' own anchors into a menu and so
        cannot run twice. Left alone, a swap would put the LOGIN page's word
        over "Download for macOS" and leave the menu in English -- a preview
        that disagrees with the served page on the one element the download
        surface exists for."""
        preview = self._import("login", preview=True, preview_languages=("en", "de"))
        self.assertIn("if(lb){lb.textContent=p?t.downloadFor+p.textContent:t.chooseDownload}", preview)
        self.assertIn("if(dm&&D.documentElement.getAttribute('data-dl')=='on'){", preview)
        self.assertNotIn("t.downloadFor", self._import("login"))

    def test_the_swap_follows_the_logout_message_the_page_rendered(self):
        """PAN-OS' ready handler has already written one of the seven into
        #logout by the time a swap arrives, and WHICH one is decided by the
        firewall. The index is found by looking the rendered text up in the
        array the page still holds, before the apply half replaces it."""
        preview = self._import("home", preview=True, preview_languages=("en", "de"))
        self.assertIn("i0=(window.logout_text_array||[]).indexOf(e0&&e0.textContent)", preview)
        self.assertIn("if(e0&&i0!==-1&&t.lm[i0]){e0.textContent=t.lm[i0]}", preview)
        self.assertLess(preview.index("indexOf(e0"), preview.index("logout_text_array=t.lm"))

    def test_the_preview_login_import_never_names_the_home_discriminator(self):
        """portal/validate.py tells the two imports apart by looking for
        `logout_text_array`, and the preview additions are the newest thing that
        could put it on the wrong one."""
        self.assertNotIn("logout_text_array", self._import("login", preview=True, preview_languages=("en", "de")))

    def test_the_preview_login_import_carries_no_raw_less_than(self):
        """One raw '<' outside a tag stops PAN-OS substituting <pan_form/> and
        the login form is simply not there. The preview is spliced onto a
        captured prefix rather than imported, so validate_portal never sees it
        -- which is exactly why this rule has to be checked here."""
        from panos_response_pages.portal.validate import _RAW_LT

        for page in ("login", "home"):
            with self.subTest(page=page):
                text = self._import(page, preview=True, preview_languages=("en", "de"))
                self.assertEqual([m.group(0) for m in _RAW_LT.finditer(text)], [])

    def test_the_built_portal_previews_carry_it(self):
        """End to end, over the frames the gallery actually inlines: the file
        the report found the global missing from."""
        found = sorted(preview_dir().rglob("portal/*.html"))
        self.assertGreater(len(found), 40, "the portal preview sweep is asserting nothing")
        opted_out = [p for p in found if p.parts[-4] == self.OPTED_OUT]
        self.assertTrue(opted_out, "the opt-out half of this sweep is asserting nothing")
        for path in found:
            with self.subTest(path=path.relative_to(preview_dir())):
                carries = scripts.PREVIEW_SWAP in path.read_text("utf-8")
                self.assertEqual(carries, path not in opted_out)


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
