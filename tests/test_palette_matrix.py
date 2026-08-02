"""Style and palette as two independent axes of one build.

A build used to have one palette. It now has all of them, and the things that
used to choose that one palette choose something else instead -- so every test
here guards a meaning that changed rather than a behaviour that is new.
"""

import pathlib
import tempfile
import unittest

from _paths import DATA
from panos_response_pages import palettes
from panos_response_pages.builder import build_all, load_themes
from panos_response_pages.errors import BuildError
from panos_response_pages.validate import PAGE_TOKENS

THEMES = [t["name"] for t in load_themes(DATA)]
PALETTES = palettes.available(DATA / "palettes")


class TestSelect(unittest.TestCase):
    def test_no_choice_means_every_palette(self):
        self.assertEqual(palettes.select(DATA / "palettes", None), PALETTES)

    def test_a_choice_narrows_to_one(self):
        self.assertEqual(palettes.select(DATA / "palettes", "prisma-blue"), ["prisma-blue"])

    def test_an_unknown_name_is_refused_with_the_list(self):
        with self.assertRaises(BuildError) as caught:
            palettes.select(DATA / "palettes", "lilac")
        self.assertIn("lilac", str(caught.exception))
        for name in PALETTES:
            self.assertIn(name, str(caught.exception))


class TestMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pathlib.Path(cls.tmp.name)
        cls.result = build_all(data_dir=DATA, out_dir=cls.out, preview=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_style_is_built_in_every_palette(self):
        got = {(r.theme, r.palette) for r in self.result.results}
        self.assertEqual(got, {(t, p) for t in THEMES for p in PALETTES})

    def test_a_pin_does_not_shrink_the_matrix(self):
        """nyan pins its own palette. That decides what the gallery opens on,
        not what exists on disk -- the customer asked for every combination so
        they can choose one, and a pin silently removing three of nyan's four
        would be a choice made for them."""
        nyan = {r.palette for r in self.result.results if r.theme == "nyan"}
        self.assertEqual(nyan, set(PALETTES))

    def test_the_deploy_tree_is_style_then_palette(self):
        for theme in THEMES:
            for palette in PALETTES:
                folder = self.out / "deploy" / theme / palette
                with self.subTest(theme=theme, palette=palette):
                    got = sorted(p.stem for p in folder.glob("*.html"))
                    self.assertEqual(got, sorted(set(PAGE_TOKENS)))

    def test_the_portal_stays_one_level_below_the_pages(self):
        folder = self.out / "deploy" / "glass" / "prisma-blue" / "portal"
        self.assertEqual(sorted(p.name for p in folder.glob("*.html")), ["home.html", "login.html"])

    def test_the_preview_tree_mirrors_the_deploy_tree(self):
        got = sorted(p.stem for p in (self.out / "preview" / "glass" / "nyan").glob("*.html"))
        self.assertIn("url-block-page", got)

    def test_nothing_lands_at_the_old_flat_path(self):
        """The layout is a breaking change, and a leftover file at the old path
        is worse than none: an upload script would keep finding a stale page."""
        self.assertEqual(list((self.out / "deploy" / "glass").glob("*.html")), [])


class TestNarrowing(unittest.TestCase):
    def test_palette_narrows_the_run_the_way_theme_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            result = build_all(data_dir=DATA, out_dir=out, palette_name="nyan", theme="glass")
            self.assertEqual({(r.theme, r.palette) for r in result.results}, {("glass", "nyan")})
            self.assertTrue((out / "deploy" / "glass" / "nyan" / "url-block-page.html").is_file())
            self.assertFalse((out / "deploy" / "glass" / "cyber-orange").exists())


if __name__ == "__main__":
    unittest.main()
