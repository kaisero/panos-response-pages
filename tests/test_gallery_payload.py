"""How the gallery carries 28 combinations without loading all of them.

Inlining every blob was fine at 1.56 MB and one palette. Four palettes makes it
5.9 MB, all of it parsed before the first frame renders and most of it never
looked at -- so each palette but the opening one is a sibling file, fetched the
first time it is asked for.
"""

import json
import re
import unittest

from _paths import DATA
from panos_response_pages import palettes, redirect
from panos_response_pages.builder import build_all, load_themes

PALETTES = palettes.available(DATA / "palettes")


class TestSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pathlib
        import tempfile

        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pathlib.Path(cls.tmp.name)
        build_all(data_dir=DATA, out_dir=cls.out, preview=True)
        cls.index = (cls.out / "preview" / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_opening_palette_is_inline(self):
        """The first frame must render without a second file arriving, or the
        gallery opens on a blank iframe and looks broken."""
        self.assertIn("cyber-orange|url-block-page", self.index)

    def test_every_other_palette_is_a_sibling_file(self):
        for name in PALETTES:
            if name == "cyber-orange":
                continue
            with self.subTest(palette=name):
                self.assertTrue((self.out / "preview" / f"blobs-{name}.js").is_file())

    def test_the_other_palettes_are_not_also_inline(self):
        """The whole point. If they are inline as well, the split cost a file
        and saved nothing."""
        self.assertNotIn("prisma-blue|url-block-page", self.index)

    def test_a_payload_file_registers_itself(self):
        text = (self.out / "preview" / "blobs-prisma-blue.js").read_text(encoding="utf-8")
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


class TestChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pathlib
        import tempfile

        cls.tmp = tempfile.TemporaryDirectory()
        out = pathlib.Path(cls.tmp.name)
        build_all(data_dir=DATA, out_dir=out, preview=True)
        cls.index = (out / "preview" / "index.html").read_text(encoding="utf-8")
        cls.css = cls.index.split("<style>", 1)[1].split("</style>", 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_palette_has_a_light_chrome_block(self):
        for name in PALETTES:
            with self.subTest(palette=name):
                self.assertIn(f':root[data-pal="{name}"]{{--bg:', self.css)

    def test_every_palette_has_a_dark_chrome_block(self):
        """Half the reviewers are in dark mode. A palette whose dark block was
        dropped falls back to the opening palette's, so the toolbar and the
        frame disagree about which palette is being previewed."""
        for name in PALETTES:
            with self.subTest(palette=name):
                self.assertIn(f'@media(prefers-color-scheme:dark){{:root[data-pal="{name}"]{{--bg:', self.css)

    def test_the_opening_palette_also_paints_without_the_attribute(self):
        """data-pal is set by the dropdown's handler. Before anyone touches it
        there is no attribute, and a toolbar with no colours is not a preview."""
        self.assertIn(":root{--bg:", self.css)

    def test_the_chrome_blocks_carry_real_colours(self):
        """`.format()` on a sheet that still held placeholders used to be how
        these were produced; a block reading `--bg:{ground}` would satisfy every
        assertion above."""
        self.assertNotIn("{ground}", self.css)
        self.assertRegex(self.css, r':root\[data-pal="nyan"\]\{--bg:#[0-9a-fA-F]{3,8}')


if __name__ == "__main__":
    unittest.main()
