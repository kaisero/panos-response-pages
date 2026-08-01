"""The nyan flight, and the glass the two families share.

The trail is a record of where the cat has been, so it has to be drawn rather
than tiled -- which means a canvas, a script that reads the sprite's box every
frame, and a paint order that puts the drawing behind both the flight and the
notice. None of those announce themselves when they break: the page still
renders, just without a sky, or with the rainbow painted over the text.

The flight stops at the block pages, but the card does not. It is what makes
the portal imports read as the same style, and it lives in a second file that
nothing else compares against this one.
"""

import re
import unittest

from _build import built
from _paths import DATA

SHELL = (DATA / "templates" / "shells" / "nyan.html").read_text(encoding="utf-8")
SCRIPT = SHELL[SHELL.rindex("<script>") : SHELL.rindex("</script>")]
PORTAL = (DATA / "templates" / "portal" / "shells" / "nyan.html").read_text(encoding="utf-8")


def nyan_pages():
    out, result = built()
    for r in result.results:
        if r.theme == "nyan":
            yield r.page, (out / "deploy" / "nyan" / f"{r.page}.html").read_text(encoding="utf-8")


class TestFlight(unittest.TestCase):
    def test_the_script_only_reaches_for_things_the_shell_defines(self):
        """A renamed hook leaves the script throwing on the first line and the
        page with a bare background -- no stars, no trail, no bob."""
        for handle, pattern in (
            ('getElementById("sky")', r'<canvas id="sky"'),
            ('querySelector(".fly")', r'<div class="fly"'),
        ):
            with self.subTest(handle=handle):
                self.assertIn(handle, SCRIPT, f"the script no longer looks up {handle}")
                self.assertRegex(SHELL, pattern, f"nothing in the shell answers {handle}")

    def test_the_canvas_is_painted_before_the_flight_and_the_notice(self):
        """Both are positioned without a z-index of their own, so document order
        is what keeps the trail behind the cat and under the glass."""
        self.assertLess(SHELL.index('id="sky"'), SHELL.index('class="fly"'))
        self.assertLess(SHELL.index('class="fly"'), SHELL.index("<main>"))

    def test_the_star_colour_survives_as_something_canvas_can_fill_with(self):
        """The script hands --star straight to fillStyle. It carries its own
        alpha as a hex suffix, which only works while the palette keeps every
        colour a six-digit hex -- an rgb() or a named colour would silently
        produce a transparent sky."""
        for page, text in nyan_pages():
            for value in set(re.findall(r"--star:([^;}]+)", text)):
                with self.subTest(page=page, star=value):
                    self.assertRegex(value.strip(), r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

    def test_the_flight_holds_still_when_motion_is_declined(self):
        """The blanket reduced-motion rule stops CSS animation, and would leave
        a script-driven flight running on its own. It has to opt out itself."""
        self.assertIn("prefers-reduced-motion", SCRIPT)
        self.assertIn("if(!still)requestAnimationFrame", SCRIPT)

    def test_steering_is_off_where_the_lane_is_a_reserved_band(self):
        """Below the stacked breakpoint the stylesheet parks the flight above
        the notice. An inline `top` from a pointer would beat that rule and drop
        the cat behind the card."""
        self.assertIn("steer=W>820", SCRIPT)
        self.assertIn("if(steer)fly.style.top", SCRIPT)
        self.assertRegex(SHELL, r"@media\(max-width:820px\)")


class TestGlassCrossesTheFamilies(unittest.TestCase):
    """The block shell and the portal imports are separate files that have to
    agree about what the style looks like. The cat and the canvas deliberately
    stop at the block pages -- the Home Page import is script-only, so there is
    no element to draw a sky on -- but the glass is the part that makes the two
    read as one, and nothing else notices when only one of them is adjusted.
    """

    def veils(self, text):
        return set(re.findall(r"--veil:(\.\d+)", text))

    def test_both_families_settle_on_the_same_two_veils(self):
        self.assertEqual(self.veils(SHELL), self.veils(PORTAL), "the two shells' glass has drifted apart")
        self.assertEqual(len(self.veils(SHELL)), 2, "expected one veil per colour scheme")

    def test_the_card_is_a_surface_in_both_and_never_the_ground_again(self):
        """A veil of --gr is the sky with the life turned off: the panel lands
        the same colour as the page behind it, which is what made this style
        read flat before the surface token was used."""
        for name, text in (("block", SHELL), ("portal", PORTAL)):
            with self.subTest(shell=name):
                self.assertIn("background:var(--sf);opacity:var(--veil)", text)
                self.assertNotIn("background:var(--gr);opacity:var(--veil)", text)
                self.assertIn("--sf:{{C_SURFACE}}", text)
                self.assertIn("--sf:{{C_D_SURFACE}}", text)

    def test_the_star_colour_carries_its_alpha_in_both(self):
        """Folded into --star so one token does the work of two. A leftover
        --dot would dim a field that is already dimmed."""
        for name, text in (("block", SHELL), ("portal", PORTAL)):
            with self.subTest(shell=name):
                self.assertNotIn("--dot", text)
                self.assertRegex(text, r"--star:\{\{C_ACCENT_TEXT\}\}[0-9a-f]{2}")
                self.assertRegex(text, r"--star:#[0-9a-f]{8}")

    def test_the_portal_stays_out_of_the_canvas_business(self):
        """Not a style choice: the Home Page import is embedded mid-<head> and
        PAN-OS writes both bodies, and a raw '<' anywhere in either file stops
        the form token being substituted."""
        self.assertNotIn("<canvas", PORTAL)
        self.assertNotIn("getContext", PORTAL)


if __name__ == "__main__":
    unittest.main()
