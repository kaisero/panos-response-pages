"""The detected-platform download button on getsoftwarepage.esp.

PAN-OS builds that page as three equally weighted links -- Windows 32-bit
first -- over three rows of prose explaining which one to take. Every rule here
protects one of the four things that make replacing it safe rather than clever,
and every one of them fails silently on a firewall: the page still renders, it
just renders the wrong thing, or nothing.
"""

import re
import unittest

import pytest

from _build import portal_pages

pytestmark = pytest.mark.integration


def logins() -> dict[str, str]:
    return {theme: html for (theme, page), html in portal_pages().items() if page == "login"}


class TestDownloadButton(unittest.TestCase):
    def test_every_theme_ships_the_widget(self):
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                for el in ('id="dl"', 'id="dlmain"', 'id="dlcar"', 'id="dlmenu"', 'id="dllab"'):
                    self.assertIn(el, html)

    def test_it_ships_hidden_and_is_revealed_by_the_script(self):
        """A widget that starts visible is a widget that shows an empty box
        when the script throws, on a page whose only content is the download."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertRegex(html, r'<div class="dl" id="dl" hidden>')
                self.assertIn("dl.hidden=false;", html)

    def test_the_stock_list_is_hidden_only_by_the_attribute_set_last(self):
        """The rules that hide PAN-OS' links and description rows hang off
        data-dl, and the script sets it after everything else has succeeded.
        Hiding them any earlier means a thrown exception leaves a page with no
        way to download anything."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertIn("html[data-dl] #taGetSofewarePage p,", html)
                self.assertIn("html[data-dl] #taGetSofewarePage table{display:none}", html)
                script = html[html.index("dl.hidden=false;") :]
                self.assertIn("setAttribute('data-dl','on')", script)

    def test_it_moves_panos_anchors_rather_than_building_new_ones(self):
        """innerHTML with a '<' would stop the form token being substituted,
        and a retyped href is an href that can drift from the firewall's."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertIn("menu.appendChild(a)", html)
                self.assertNotIn("innerHTML", html)
                self.assertNotIn("getmsi.esp", html, "a download href is hardcoded instead of read")

    def test_it_detects_bitness_the_only_way_that_works(self):
        """Windows bit-ness is not otherwise exposed, and picking by DOM
        position lands on the 32-bit build PAN-OS happens to list first."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertIn("Win64|WOW64|x64|x86_64", html)
                self.assertIn("navigator.userAgent", html)

    def test_an_unrecognised_platform_is_told_to_choose(self):
        """Linux, ChromeOS, a spoofed agent -- the page says so instead of
        guessing, and the caret menu is still the way through."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertIn("Choose your download", html)

    def test_the_script_never_writes_a_raw_less_than(self):
        """One '<' outside a tag stops PAN-OS substituting the form token and
        dumps the login form at the end of the document. A counting loop is the
        usual way it gets in, so the widget iterates with forEach."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                script = html[html.index("var box=document.getElementById('taGetSofewarePage')") :]
                script = script[: script.index("</script>")]
                self.assertNotRegex(script, r"<(?![a-zA-Z/!])")
                self.assertNotIn(".length;", script, "a counting loop needs a '<'")

    def test_the_caret_is_reachable_by_keyboard(self):
        """The shells' focus rule covers a and input only; the caret is a
        button, so each shell carries its own."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertRegex(html, r"\.dlcar:focus-visible\{[^}]*outline")

    def test_the_fallback_links_stay_styled(self):
        """They are what a visitor sees when the script does not run, so they
        cannot be left to the stock stylesheet -- which this import disables."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                self.assertRegex(html, r"#taGetSofewarePage p a\{[^}]*padding")

    def test_no_theme_claims_a_download_id_panos_also_emits(self):
        """PAN-OS owns #taGetSofewarePage, #getsoftwarepage_form and the
        #dDescription* rows. The widget's own ids are all dl-prefixed."""
        for theme, html in logins().items():
            with self.subTest(theme=theme):
                for name in re.findall(r"getElementById\('([a-zA-Z_]+)'\)", html):
                    if name not in ("taGetSofewarePage", "getsoftwarepage_form"):
                        self.assertTrue(name.startswith("dl"), f"{name} is not ours")
