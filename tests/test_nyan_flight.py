"""The nyan flight is simulated, and the script has a contract with the page.

The trail is a record of where the cat has been, so it has to be drawn rather
than tiled -- which means a canvas, a script that reads the sprite's box every
frame, and a paint order that puts the drawing behind both the flight and the
notice. None of those announce themselves when they break: the page still
renders, just without a sky, or with the rainbow painted over the text.
"""

import re
import unittest

from _build import built
from _paths import DATA

SHELL = (DATA / "templates" / "shells" / "nyan.html").read_text(encoding="utf-8")
SCRIPT = SHELL[SHELL.rindex("<script>") : SHELL.rindex("</script>")]


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


if __name__ == "__main__":
    unittest.main()
