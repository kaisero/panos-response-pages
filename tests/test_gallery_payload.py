"""How the gallery carries 28 combinations without loading all of them.

Inlining every blob was fine at 1.56 MB and one palette. Four palettes makes it
5.9 MB, all of it parsed before the first frame renders and most of it never
looked at -- so each palette but the opening one is a sibling file, fetched the
first time it is asked for.

Language is the second axis of the same problem and it arrived later. A frame
used to carry every translation the tree shipped, so the document grew by every
language rather than by every palette: thirteen measured 2,884,739 B against the
2,500,000 B limit below. The frames now compile none, and the words for one
language are a sibling file of their own.
"""

import copy
import functools
import json
import pathlib
import re
import shutil
import tempfile
import unittest

from _build import preview_dir, translated_strings
from _paths import DATA
from panos_response_pages import palettes, redirect
from panos_response_pages.builder import build_all, load_themes
from panos_response_pages.errors import BuildError
from panos_response_pages.gallery import CHROME_KEYS, build_gallery
from panos_response_pages.palettes import load_palette

PALETTES = palettes.available(DATA / "palettes")

# The eleven the plan adds to the two that ship, so this measures the real
# thirteen rather than an arbitrary number of them.
EXTRA_LANGUAGES = ("es", "it", "fr", "ja", "zh", "ru", "sv", "uk", "vi", "nl", "da")


@functools.lru_cache(maxsize=2)
def gallery_shipping(extra: tuple[str, ...]) -> pathlib.Path:
    """A preview built against a tree that SHIPS `extra` languages as well.

    `languages` is left at the shipped default, so the deploy side of this build
    is the one every other test sees -- what changes is how many strings files
    the tree contains, which is what previewable() reads and therefore what the
    gallery has to carry.

    Against a COPY, never DATA: that tree is the installed package, and a file
    written into it would decide the outcome of tests that have nothing to do
    with languages.
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-gallery-langs-")) / "data"
    shutil.copytree(DATA, root)
    for lang in extra:
        doc = translated_strings(f"{lang}:")
        doc["lang"] = lang
        (root / "strings" / f"{lang}.json").write_text(json.dumps(doc), encoding="utf-8")
    out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-gallery-out-"))
    build_all(root, out, preview=True)
    return out / "preview"


class TestSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = preview_dir()
        cls.index = (cls.preview / "index.html").read_text(encoding="utf-8")

    def test_the_opening_palette_is_inline(self):
        """The first frame must render without a second file arriving, or the
        gallery opens on a blank iframe and looks broken."""
        self.assertIn("cyber-orange|url-block-page", self.index)

    def test_every_other_palette_is_a_sibling_file(self):
        for name in PALETTES:
            if name == "cyber-orange":
                continue
            with self.subTest(palette=name):
                self.assertTrue((self.preview / f"blobs-{name}.js").is_file())

    def test_the_other_palettes_are_not_also_inline(self):
        """The whole point. If they are inline as well, the split cost a file
        and saved nothing."""
        self.assertNotIn("prisma-blue|url-block-page", self.index)

    def test_a_payload_file_registers_itself(self):
        text = (self.preview / "blobs-prisma-blue.js").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("PP("))
        self.assertIn("prisma-blue|url-block-page", text)

    def test_it_is_a_classic_script_not_a_module(self):
        """ES modules are CORS-checked and fail on file://, which is exactly how
        this gallery is opened."""
        self.assertNotIn('type="module"', self.index)

    def test_the_key_carries_both_axes(self):
        self.assertIn('S.theme+"|"+S.palette+"|"+p', self.index)

    def test_rxok_names_exactly_the_redirect_capable_themes(self):
        """RXOK is what `draw()` checks to decide whether the Redirect toggle
        shows at all. A previous fix corrected its lookup, and the lookup
        beside it in `redirect_seg`, from 2-tuple to 3-tuple blob keys; had it
        been missed, the toggle would have silently vanished for every style
        -- including nyan, which never gets the toggle because its theme does
        not set `redirect: true` in the first place.
        """
        themes = load_themes(DATA)
        expected = {t["name"] for t in themes if redirect.supported(t)}
        self.assertNotIn("nyan", expected)

        m = re.search(r"RXOK=(\{.*?\});", self.index)
        self.assertIsNotNone(m, "RXOK not found in generated index.html")
        rxok = json.loads(m.group(1))
        self.assertEqual(set(rxok), expected)

    def test_the_index_stays_small(self):
        """One palette's worth, not four. A regression here is silent -- the
        gallery still works, it just takes four times as long to open."""
        self.assertLess(len(self.index.encode()), 2_500_000)


class TestTheDocumentDoesNotGrowByLanguage(unittest.TestCase):
    """The point of splitting the translations out, measured rather than argued.

    Every frame used to carry a dictionary per language, so the cost was one
    dictionary x every page x every style -- about 1 MB between two languages and
    thirteen, on a document with a 2.5 MB limit that exists because the browser
    parses all of it before the first frame renders.
    """

    @classmethod
    def setUpClass(cls):
        cls.two = gallery_shipping(())
        cls.thirteen = gallery_shipping(EXTRA_LANGUAGES)
        cls.index2 = (cls.two / "index.html").read_bytes()
        cls.index13 = (cls.thirteen / "index.html").read_bytes()

    def test_eleven_more_languages_barely_move_it(self):
        """Only the dropdown rows grow -- one <li> per language, some tens of
        bytes. Anything larger than this means a translation is inline again."""
        self.assertLess(len(self.index13) - len(self.index2), 5_000)

    def test_thirteen_languages_still_fit_the_limit(self):
        """The number the plan's table said was 115% of it."""
        self.assertLess(len(self.index13), 2_000_000)

    def test_every_language_but_the_base_is_a_sibling_file(self):
        for lang in (*EXTRA_LANGUAGES, "de"):
            with self.subTest(lang=lang):
                path = self.thirteen / f"lang-{lang}.js"
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text(encoding="utf-8").startswith("PL("))

    def test_the_base_language_has_no_file_at_all(self):
        """It is the text the frames are served in. A file for it would be a
        fetch that could only ever hand a frame the words it already has."""
        self.assertFalse((self.thirteen / "lang-en.js").exists())

    def test_a_translation_is_only_in_its_own_file(self):
        """The whole point, stated the way the palette split states it: if the
        words are inline as well, the split cost thirteen files and saved
        nothing."""
        index = self.index13.decode("utf-8")
        self.assertNotIn("ja:Blocked", index)
        self.assertIn("ja:Blocked", (self.thirteen / "lang-ja.js").read_text(encoding="utf-8"))

    def test_the_frames_are_never_fetched_for_the_base_language(self):
        """Opening the gallery must cost nothing beyond the document itself, so
        the loader is handed an empty source -- which it treats as done -- rather
        than a file named after the language the frames already carry."""
        self.assertIn('need(S.lang===BASELANG?"":LSRC(S.lang),draw);', self.index13.decode("utf-8"))

    def test_one_loader_serves_both_axes(self):
        """INFLIGHT exists because a duplicate script load was a real bug. Keying
        it on the file rather than on the palette is what extends that guard to
        the language files instead of leaving them their own copy of it."""
        index = self.index13.decode("utf-8")
        self.assertIn("if(INFLIGHT[src]){INFLIGHT[src].push(done);return}", index)
        self.assertIn("function PL(lang,obj){TT[lang]=obj;LOADED[LSRC(lang)]=1}", index)


class TestChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (preview_dir() / "index.html").read_text(encoding="utf-8")
        cls.css = cls.index.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_the_opening_palette_also_paints_without_the_attribute(self):
        """data-pal is set by the dropdown's handler. Before anyone touches it
        there is no attribute, and a toolbar with no colours is not a preview."""
        self.assertIn(":root{--bg:", self.css)

    @staticmethod
    def _block_tokens(css: str, pattern: str) -> dict[str, str]:
        """Parse one `--var:value;...` block into a dict.

        Fails loudly (KeyError from the caller, or a missing-block assertion
        upstream) rather than returning {} if the block is absent, so a typo in
        the selector does not silently compare two empty dicts as equal.
        """
        match = re.search(pattern, css)
        assert match, f"no CSS block matched {pattern!r}"
        body = match.group(1)
        return dict(item.split(":", 1) for item in body.split(";") if item)

    def test_each_palette_s_chrome_carries_its_own_colours(self):
        """The mutation this guards against: every block emitting the opening
        palette's colours instead of its own. Weaker forms of this test -- that
        the selector exists, that *something* hex-shaped follows it -- all pass
        under that mutation while the toolbar lies about every non-opening
        palette, so this asserts the parsed block equals the palette's real
        values. `_block_tokens` fails on a missing block, which is why the
        existence checks are not stated separately.

        Half the reviewers are in dark mode, and a palette whose dark block was
        dropped falls back to the opening palette's -- hence both schemes."""
        for name in PALETTES:
            with self.subTest(palette=name):
                colors = load_palette(name, DATA / "palettes")["colors"]
                light_expected = {var: str(colors[key]) for var, key in CHROME_KEYS}
                dark_expected = {var: str(colors["d_" + key]) for var, key in CHROME_KEYS}

                light_pattern = r':root\[data-pal="' + re.escape(name) + r'"\]\{([^}]*)\}'
                dark_pattern = (
                    r"@media\(prefers-color-scheme:dark\)\{"
                    r':root\[data-pal="' + re.escape(name) + r'"\]\{([^}]*)\}\}'
                )

                self.assertEqual(self._block_tokens(self.css, light_pattern), light_expected)
                self.assertEqual(self._block_tokens(self.css, dark_pattern), dark_expected)


class TestPaletteInterpolationIsSafe(unittest.TestCase):
    """_tokens(), _chrome_tokens() and swatch() interpolate palette values into
    a stylesheet with no escaping. Palette JSON is maintainer-controlled at
    build time, so this is not currently exploitable, but a value containing
    `{`, `}`, `;` or `"` would otherwise corrupt every CSS rule after it, or
    break out of an attribute selector, with nothing to say why. Rejected
    outright rather than sanitised."""

    def setUp(self):
        self.theme = load_themes(DATA)[0]
        self.cfg = {"company": "Acme"}
        self.palette = copy.deepcopy(load_palette("cyber-orange", DATA / "palettes"))
        self.blobs = {(self.theme["name"], self.palette["name"], "url-block-page"): "<html></html>"}

    def test_a_sane_palette_still_builds(self):
        gallery, _sidecars = build_gallery(
            [self.theme], ["url-block-page"], self.blobs, self.cfg, self.palette, [self.palette]
        )
        self.assertIn("url-block-page", gallery)

    def test_an_unsafe_colour_value_is_refused(self):
        bad = copy.deepcopy(self.palette)
        bad["colors"]["accent"] = "red;}body{display:none"
        with self.assertRaises(BuildError) as caught:
            build_gallery([self.theme], ["url-block-page"], self.blobs, self.cfg, bad, [bad])
        self.assertIn("accent", str(caught.exception))

    def test_an_unsafe_palette_name_is_refused(self):
        bad = copy.deepcopy(self.palette)
        bad["name"] = 'evil"]{--bg:red};['
        blobs = {(self.theme["name"], bad["name"], "url-block-page"): "<html></html>"}
        with self.assertRaises(BuildError):
            build_gallery([self.theme], ["url-block-page"], blobs, self.cfg, bad, [bad])


class TestPaletteListboxFollowsClick(unittest.TestCase):
    """choose(i) updates aria-selected, S.palette, the swatch and the label,
    but used to never assign `at`, which is otherwise only set at init and by
    mark(). A keyboard user who clicked a row and then pressed ArrowDown got a
    popup that opened relative to whichever row was selected at load, not the
    one they had just picked."""

    def test_choose_updates_the_keyboard_cursor(self):
        index = (preview_dir() / "index.html").read_text(encoding="utf-8")
        squeezed = re.sub(r"\s+", "", index)
        self.assertIn("functionchoose(i){at=i;", squeezed)


class TestMissingSidecarIsVisible(unittest.TestCase):
    """A missing or interrupted blobs-<palette>.js sidecar used to settle
    silently, leaving a blank white frame with no console error and no retry.
    The load failure must now be visible in the frame itself."""

    def test_the_gallery_carries_a_note_for_a_failed_sidecar_load(self):
        index = (preview_dir() / "index.html").read_text(encoding="utf-8")
        self.assertIn("FAILED[src]=1", index)
        self.assertIn("failed to load", index)

    def test_a_failed_palette_and_a_failed_language_each_say_so(self):
        """Two families of sidecar now, and a missing one of either must reach
        the frame as a sentence. A language file that failed is the worse of the
        two to swallow: the frame would render in the base language and disagree
        with the control above it, which is the one comparison a reviewer opened
        the gallery to make."""
        index = (preview_dir() / "index.html").read_text(encoding="utf-8")
        self.assertIn("this palette's preview is missing.", index)
        self.assertIn("this language's translations are missing.", index)


if __name__ == "__main__":
    unittest.main()
