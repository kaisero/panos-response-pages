"""Both imports must have the exact shape PAN-OS expects, in every theme.

Each assertion here maps to a [verified] rule in docs/architecture/. All of
them fail silently on a firewall.
"""

import re
import unittest

import pytest

from _build import portal_pages
from panos_response_pages.portal.validate import detect_kind, validate_portal

pytestmark = pytest.mark.integration


class TestPortalShape(unittest.TestCase):
    def test_every_theme_and_page_passes_the_guards(self):
        for (theme, page), html in portal_pages().items():
            with self.subTest(theme=theme, page=page):
                _size, errors, _warnings = validate_portal(html)
                self.assertEqual(errors, [], f"{theme}/{page}: {errors}")

    def test_login_is_a_fragment_and_home_is_script_only(self):
        for (theme, page), html in portal_pages().items():
            with self.subTest(theme=theme, page=page):
                self.assertEqual(detect_kind(html), page)
                self.assertNotIn("<!DOCTYPE", html)
                if page == "login":
                    self.assertIn("</head>", html)
                    self.assertTrue(html.rstrip().endswith("</html>"))
                else:
                    for tag in ("</head>", "<body", "</html>"):
                        self.assertNotIn(tag, html)

    def test_home_gates_its_restyle_to_logout(self):
        """Disabling Bootstrap on the portal home page would leave
        navbar-and-tiles with nothing to replace it. That body has never been
        captured."""
        for (theme, page), html in portal_pages().items():
            if page == "home":
                with self.subTest(theme=theme):
                    self.assertIn("logout.esp", html)

    def test_detection_script_comes_after_the_form_token(self):
        """Placed before it, getElementById('getsoftwarepage_form') returns
        null and the download page shows login wording forever."""
        for (theme, page), html in portal_pages().items():
            if page == "login":
                with self.subTest(theme=theme):
                    self.assertLess(html.index("<pan_form/>"), html.index("getsoftwarepage_form"))

    def test_login_heading_is_not_overwritten_by_gp_portal_name(self):
        """PAN-OS does $('#heading').html(gp_portal_name) when non-empty, which
        would wipe the login/download switch spans."""
        for (theme, page), html in portal_pages().items():
            if page == "login":
                with self.subTest(theme=theme):
                    self.assertRegex(html, r"var\s+gp_portal_name\s*=\s*''")

    def test_home_shows_the_agent_download_entry(self):
        """'' is falsy and would remove the entry from the portal home page,
        which this work leaves untouched."""
        for (theme, page), html in portal_pages().items():
            if page == "home":
                with self.subTest(theme=theme):
                    self.assertRegex(html, r"var\s+display_globalprotect_agent\s*=\s*1")

    def test_built_logout_array_still_has_seven_entries(self):
        """A --customer override replaces lists wholesale; the config test
        alone does not cover the emitted import."""
        for (theme, page), html in portal_pages().items():
            if page == "home":
                with self.subTest(theme=theme):
                    arr = re.search(r"var logout_text_array=(\[.*?\]);", html, re.S)
                    self.assertIsNotNone(arr, "logout_text_array not emitted")
                    self.assertEqual(arr.group(1).count("','") + 1, 7)
