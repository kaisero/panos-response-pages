"""The nyan style's artwork is compiled, not hand-written.

`_nyan_sprite.py` holds the pixel map a person edits; the shell holds the
compiled result, because neither family can build it at runtime. Two copies of
anything drift, so this is the thing that notices.

Only the block shell carries it: the portal imports take the palette, the sky
and the hairline, but no character -- a sign-in form is not somewhere to fly one
across, and PAN-OS owns the logout page's body.
"""

import re
import unittest

import _nyan_sprite as sprite
from _paths import DATA

SHELL = DATA / "templates" / "shells" / "nyan.html"
URI_RE = re.compile(r'url\("data:image/svg\+xml,(.*?)"\)')

# Comfortably above the 900 B the current artwork compiles to, and far below the
# point where it would threaten the page budget. A map edit that lands here has
# gone wrong in a way the byte-budget test would only report as a mystery.
MAX_URI = 2000


class TestSprite(unittest.TestCase):
    def test_the_map_is_a_rectangle_of_known_colours(self):
        widths = {len(row) for row in sprite.SPRITE}
        self.assertEqual(widths, {sprite.WIDTH}, "the pixel map is ragged")
        known = set(sprite.PALETTE) | {"."}
        for y, row in enumerate(sprite.SPRITE):
            self.assertTrue(set(row) <= known, f"row {y} uses a colour with no entry in PALETTE")

    def test_the_shell_carries_exactly_what_the_generator_produces(self):
        found = URI_RE.findall(SHELL.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, "expected exactly one data: URI in the shell")
        self.assertEqual(
            found[0],
            sprite.data_uri(),
            "the shell's artwork and _nyan_sprite.py have diverged -- "
            "run `python tests/_nyan_sprite.py` and paste the line it prints",
        )

    def test_merging_keeps_the_artwork_small(self):
        uri = sprite.data_uri()
        self.assertLess(len(uri), MAX_URI, f"artwork is {len(uri)} B; one rect per pixel is ~11 kB")

    def test_the_artwork_would_survive_the_portal_s_raw_lt_guard(self):
        """Not used there today, but the constraint is cheap to keep: a '<' not
        followed by a tag character stops PAN-OS substituting the form token."""
        self.assertIsNone(re.search(r"<(?![a-zA-Z/!])", sprite.data_uri()))

    def test_only_the_hash_is_escaped(self):
        """Left raw, '#' ends the URL and the artwork loses every colour after
        the first. Nothing else needs escaping inside a quoted url()."""
        self.assertNotIn("#", sprite.data_uri())
        self.assertIn("%23", sprite.data_uri())


if __name__ == "__main__":
    unittest.main()
