"""Style and palette as two independent axes of one build.

A build used to have one palette. It now has all of them, and the things that
used to choose that one palette choose something else instead -- so every test
here guards a meaning that changed rather than a behaviour that is new.
"""

import json
import pathlib
import shutil
import tempfile
import unittest

from _paths import DATA
from panos_response_pages import palettes
from panos_response_pages.builder import build_all, format_report, load_themes
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


class TestUnknownOpeningPalette(unittest.TestCase):
    """`loaded` is keyed only by the names `palettes.select` already validated
    against --palette. A name arriving some other way -- the customer's own
    config, or a theme's pin -- was never checked, and indexing straight into
    `loaded` with it raised a raw KeyError instead of the BuildError every
    other unknown palette name gets."""

    def test_an_unknown_customer_palette_is_a_build_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = pathlib.Path(tmp) / "data"
            shutil.copytree(DATA, data_dir)
            (data_dir / "config" / "acme.json").write_text(json.dumps({"palette": "lilac"}))

            with self.assertRaises(BuildError) as caught:
                build_all(data_dir=data_dir, out_dir=pathlib.Path(tmp) / "out", customer="acme", preview=False)
            self.assertIn("lilac", str(caught.exception))

    def test_an_unknown_theme_pin_is_a_build_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = pathlib.Path(tmp) / "data"
            shutil.copytree(DATA, data_dir)
            # assist sorts first alphabetically among the shipped themes, so
            # its pin is the one `opening_palette` consults with no --palette
            # and no customer override in play.
            theme_path = data_dir / "themes" / "assist.json"
            theme = json.loads(theme_path.read_text())
            theme["palette"] = "lilac"
            theme_path.write_text(json.dumps(theme))

            with self.assertRaises(BuildError) as caught:
                build_all(data_dir=data_dir, out_dir=pathlib.Path(tmp) / "out", preview=False)
            self.assertIn("lilac", str(caught.exception))


class TestNarrowing(unittest.TestCase):
    def test_palette_narrows_the_run_the_way_theme_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            result = build_all(data_dir=DATA, out_dir=out, palette_name="nyan", theme="glass")
            self.assertEqual({(r.theme, r.palette) for r in result.results}, {("glass", "nyan")})
            self.assertTrue((out / "deploy" / "glass" / "nyan" / "url-block-page.html").is_file())
            self.assertFalse((out / "deploy" / "glass" / "cyber-orange").exists())


class TestReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = build_all(data_dir=DATA, out_dir=pathlib.Path(cls.tmp.name), preview=False)
        cls.text = format_report(cls.result)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_row_per_combination_not_per_page(self):
        """252 page rows is long enough that a single warn in the middle scrolls
        past unread, which defeats the only purpose the table has.

        Sliced on "portal import" the way test_portal_build.py does, so this
        measures only the block-page table -- the portal table is a second,
        separately-fenced table with its own row count and its own test below.

        Counted between the rules rather than by matching `ok`, so the test still
        measures the table when a row's status is `warn` or `FAIL`. The real
        report is used as built, with nothing cleared or mutated: a build state
        that never occurs in production (no portal results at all) used to hide
        the fact that the portal table was never collapsed.
        """
        block = self.text.split("portal import")[0]
        lines = block.splitlines()
        rules = [i for i, ln in enumerate(lines) if set(ln.strip()) == {"-"}]
        self.assertEqual(len(rules), 2, "the table should be fenced by exactly two rules")
        self.assertEqual(rules[1] - rules[0] - 1, len(THEMES) * len(PALETTES))

    def test_the_portal_table_is_also_one_row_per_combination(self):
        """The same collapse, applied to the second table. Left uncollapsed,
        the shipped matrix produced four byte-identical `theme login ...`
        lines in a row with nothing on the row explaining why."""
        portal = self.text.split("portal import", 1)[1]
        lines = portal.splitlines()
        rules = [i for i, ln in enumerate(lines) if set(ln.strip()) == {"-"}]
        self.assertEqual(len(rules), 2, "the portal table should be fenced by exactly two rules")
        self.assertEqual(rules[1] - rules[0] - 1, len(THEMES) * len(PALETTES))

    def test_each_row_names_the_largest_page(self):
        """The only page that can breach the ceiling is the largest one, so it
        is the one the row has to be about."""
        row = next(ln for ln in self.text.splitlines() if "nyan" in ln and "cyber-orange" in ln)
        self.assertIn("url-block-page", row)
        self.assertIn("15558", row)

    def test_palette_does_not_change_page_size(self):
        """The collapsed row is only honest if a palette cannot make a page
        bigger. If this ever fails, the report must stop collapsing."""
        by_page: dict[tuple[str, str], set[int]] = {}
        for r in self.result.results:
            by_page.setdefault((r.theme, r.page), set()).add(r.size)
        for (theme, page), sizes in by_page.items():
            with self.subTest(theme=theme, page=page):
                self.assertEqual(len(sizes), 1, f"{theme}/{page} differs by palette: {sorted(sizes)}")

    def test_a_clean_build_says_so(self):
        self.assertIn("no page warns or fails", self.text)


if __name__ == "__main__":
    unittest.main()
