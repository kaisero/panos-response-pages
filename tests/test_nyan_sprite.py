"""The nyan style's artwork is compiled, not hand-written.

`_nyan_sprite.py` holds the pixel maps a person edits; the shell holds the
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
SVG_RE = re.compile(r'<svg class="ny".*?</svg>', re.S)

# Comfortably above the ~1.9 kB the current artwork compiles to, and far below
# the point where it would threaten the page budget. A map edit that lands here
# has gone wrong in a way the byte-budget test would only report as a mystery.
MAX_SVG = 2600


def replay(layer):
    """Paint the compiled rectangles back onto a blank grid, in paint order.

    The compiler lets each colour's rectangles swallow pixels belonging to
    colours painted after it. That is only sound if the later colours really do
    cover every pixel they were promised, and the only honest way to check is to
    run the paint and compare.
    """
    rows = layer[2]
    canvas = [["."] * len(rows[0]) for _ in rows]
    for char in sprite.ORDER:
        for x, y, w, h in sprite.rectangles(rows, char):
            for j in range(y, y + h):
                for i in range(x, x + w):
                    canvas[j][i] = char
    return ["".join(row) for row in canvas]


class TestSprite(unittest.TestCase):
    def test_every_map_is_a_rectangle_of_known_colours(self):
        for cls, (_x, _y, rows) in sprite.LAYERS:
            with self.subTest(layer=cls or "body"):
                self.assertEqual({len(r) for r in rows}, {len(rows[0])}, "the pixel map is ragged")
                known = set(sprite.PALETTE) | {"."}
                for y, row in enumerate(rows):
                    self.assertTrue(set(row) <= known, f"row {y} uses a colour with no entry in PALETTE")

    def test_every_layer_fits_the_canvas_the_shell_scales(self):
        for cls, (x, y, rows) in sprite.LAYERS:
            with self.subTest(layer=cls or "body"):
                self.assertLessEqual(x + len(rows[0]), sprite.WIDTH)
                self.assertLessEqual(y + len(rows), sprite.HEIGHT)

    def test_merging_draws_exactly_the_picture_in_the_maps(self):
        for cls, layer in sprite.LAYERS:
            with self.subTest(layer=cls or "body"):
                self.assertEqual(
                    replay(layer),
                    layer[2],
                    "the occlusion pass dropped or misplaced a pixel -- a colour "
                    "swallowed pixels that its PALETTE order does not let it cover",
                )

    def test_the_shell_carries_exactly_what_the_generator_produces(self):
        found = SVG_RE.findall(SHELL.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, "expected exactly one sprite in the shell")
        self.assertEqual(
            found[0],
            sprite.compile_svg(),
            "the shell's artwork and _nyan_sprite.py have diverged -- "
            "run `python tests/_nyan_sprite.py` and paste what it prints",
        )

    def test_the_shell_animates_every_frame_layer_and_no_others(self):
        """The frame swap lives in CSS, keyed by class name. A layer the
        stylesheet does not name never shows; a rule naming a layer that no
        longer exists leaves a gap in the cycle. Neither shows up as an error."""
        shell = SHELL.read_text(encoding="utf-8")
        drawn = {cls for cls, _ in sprite.LAYERS if cls}
        animated = set(re.findall(r"\.([lt]\d)\{animation-name:", shell))
        self.assertEqual(animated, drawn, "the shell's frame rules and the sprite's layers disagree")

    def test_merging_keeps_the_artwork_small(self):
        svg = sprite.compile_svg()
        self.assertLess(len(svg), MAX_SVG, f"artwork is {len(svg)} B; one rect per pixel is ~11 kB")

    def test_the_artwork_would_survive_the_portal_s_raw_lt_guard(self):
        """Not used there today, but the constraint is cheap to keep: a '<' not
        followed by a tag character stops PAN-OS substituting the form token."""
        self.assertIsNone(re.search(r"<(?![a-zA-Z/!])", sprite.compile_svg()))


if __name__ == "__main__":
    unittest.main()
