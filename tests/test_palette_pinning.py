"""A theme may pin its own palette. This is who wins when the sources disagree.

Order, first hit wins: --palette, then the customer's own config file, then the
theme's pin, then the shipped default.

The subtle rung is the customer file. `_defaults.json` ships a `palette`, and
`load_config` merges the customer document over it -- so the merged config always
carries one. Read naively, "config outranks the pin" means the pin never fires
and a style that owns its colour silently renders in someone else's. That is the
regression `customer_keys()` exists to prevent, and the fourth test here is the
one that would catch it coming back.
"""

import pathlib
import tempfile
import unittest

from _paths import DATA
from panos_response_pages import palettes
from panos_response_pages.builder import build_all, load_themes, opening_palette
from panos_response_pages.config import customer_keys, load_config


class TestOpeningPalette(unittest.TestCase):
    """The pin used to decide what got built. It now decides what a reviewer
    sees first, and nothing else -- every combination is on disk either way."""

    def opening(self, theme_name, customer="contoso", palette_name=None):
        cfg = load_config(customer, DATA / "config")
        chosen = customer_keys(customer, DATA / "config")
        theme = next(t for t in load_themes(DATA) if t["name"] == theme_name)
        return opening_palette(cfg, chosen, theme, palette_name)

    def test_a_pin_decides_when_nothing_else_speaks(self):
        self.assertEqual(self.opening("nyan"), "nyan")

    def test_other_themes_are_untouched_by_one_theme_s_pin(self):
        self.assertEqual(self.opening("glass"), "cyber-orange")

    def test_an_explicit_palette_outranks_everything(self):
        self.assertEqual(self.opening("nyan", palette_name="prisma-blue"), "prisma-blue")

    def test_the_shipped_default_does_not_outrank_the_pin(self):
        """_defaults.json always carries a palette, so a naive cfg['palette']
        would mean a pin could never fire."""
        self.assertEqual(self.opening("nyan"), "nyan")

    def test_a_pin_does_not_remove_anything_from_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_all(data_dir=DATA, out_dir=pathlib.Path(tmp), theme="nyan", preview=False)
            built = {r.palette for r in result.results}
            self.assertEqual(built, set(palettes.available(DATA / "palettes")))


if __name__ == "__main__":
    unittest.main()
