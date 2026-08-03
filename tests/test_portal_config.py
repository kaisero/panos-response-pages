"""Portal copy lives in config, not in templates.

logout_text_array is the ONLY supported way to change logout wording. Messages
3, 4 and 5 are visible to end users but actionable only by an administrator, so
they name a real contact rather than saying "contact system administrator".
"""

import re
import unittest

import pytest

from _build import portal_pages
from _paths import DATA
from panos_response_pages.config import load_config

pytestmark = pytest.mark.integration


class TestPortalConfig(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config("contoso", DATA / "config")

    def test_ships_a_portal_name_and_logo(self):
        self.assertIn("portalName", self.cfg)
        self.assertIn("portalLogoSvg", self.cfg)

    def test_logout_messages_keep_all_seven_in_order(self):
        """PAN-OS picks the index via ?code=N. Dropping or reordering one
        silently shows the wrong message."""
        msgs = self.cfg["logoutMessages"]
        self.assertEqual(len(msgs), 7)
        self.assertIn("logged out", msgs[0].lower())
        self.assertIn("license", msgs[1].lower())
        self.assertIn("expired", msgs[6].lower())

    def test_admin_only_errors_name_a_contact(self):
        """load_config performs no interpolation. The raw token survives here
        and is resolved during composition, where it becomes either the
        support address or the label and the ticket URL -- PAN-OS fills this
        text in with .text(), so it cannot carry a link of its own."""
        for i in (3, 4, 5):
            with self.subTest(index=i):
                self.assertIn("{{CONTACT_REACHABLE}}", self.cfg["logoutMessages"][i])

    def test_no_message_tells_a_user_to_contact_an_administrator(self):
        """The stock wording names a role the user has no way to reach."""
        for i, msg in enumerate(self.cfg["logoutMessages"]):
            with self.subTest(index=i):
                self.assertNotIn("system administrator", msg.lower())

    def test_portal_logo_is_svg_source_the_build_can_encode(self):
        """Source, not a data: URI -- the build percent-encodes it once per
        scheme, and it cannot do that to something already encoded."""
        self.assertTrue(self.cfg["portalLogoSvg"].lstrip().startswith("<svg"))

    def test_portal_logo_fetches_nothing(self):
        """An external URL is a third party who sees every portal visitor's IP
        and user-agent, and whose outage becomes a broken login page. The
        portal's CSP blocks it anyway, so the failure is silent and total."""
        self.assertNotIn("http://", self.cfg["portalLogoSvg"].replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", self.cfg["portalLogoSvg"])

    def test_portal_logo_takes_its_colours_from_the_palette(self):
        """The whole point of the S_* tokens. A literal hex here is a logo that
        stays cyan on an orange build -- which is exactly what shipped first."""
        self.assertNotRegex(self.cfg["portalLogoSvg"], r"#[0-9a-fA-F]{3,8}\b")
        for token in ("{{S_ACCENT}}", "{{S_ACCENT_INK}}"):
            self.assertIn(token, self.cfg["portalLogoSvg"])

    def test_portal_logo_is_a_symbol_with_no_lettering(self):
        """The company name is rendered as text beside it. Drawn into the SVG
        it could not follow a rename, and it would be clipped or shrunk -- an
        SVG has no way to measure text against a fixed viewBox."""
        self.assertNotIn("<text", self.cfg["portalLogoSvg"])
        self.assertNotIn("font-family", self.cfg["portalLogoSvg"])


class TestTerminology(unittest.TestCase):
    """The portal does not call itself a VPN.

    A deliberate decision with nothing else enforcing it, and the two strings it
    turns on live in six shell files each -- so the failure mode is one shell
    quietly drifting back while the other five are correct.
    """

    # Emitted comments are already stripped, so anything left is served. The
    # word is matched whole: it must not fire on a hypothetical "VPNv2" brand or
    # on a base64/URI fragment that happens to contain the letters.
    VPN = re.compile(r"\bVPN\b", re.I)

    def test_no_built_import_calls_itself_a_vpn(self):
        for (theme, page), html in portal_pages().items():
            with self.subTest(theme=theme, page=page):
                found = self.VPN.findall(html)
                self.assertEqual(found, [], f"{len(found)} occurrence(s) of VPN survived into {page}")

    def test_the_portal_name_names_the_service_not_the_company(self):
        """portalName is an eyebrow on two surfaces and the whole <h1> on the
        third. Carrying {{COMPANY}} wraps that heading to two lines as soon as
        the company name is long, and the company is already on the page as the
        wordmark beside the logo."""
        cfg = load_config("contoso", DATA / "config")
        self.assertNotIn("{{COMPANY}}", cfg["portalName"])


class TestRenamingTheCompany(unittest.TestCase):
    """A rename is one key. It has to reach every surface, including the logout
    page -- whose body is PAN-OS' own, so the name can only get there as CSS."""

    def setUp(self):
        from panos_response_pages.builder import load_themes
        from panos_response_pages.palettes import load_palette
        from panos_response_pages.portal.page import build_portal_page

        cfg = load_config("contoso", DATA / "config")
        cfg["company"] = "Northwind Logistics"
        palette = load_palette("cyber-orange", DATA / "palettes")
        theme = next(t for t in load_themes(DATA) if t["name"] == "glass")
        self.pages = {
            page: build_portal_page(page, theme, cfg, palette, template_dir=DATA / "templates")
            for page in ("login", "home")
        }

    def test_the_new_name_reaches_both_imports(self):
        for page, html in self.pages.items():
            with self.subTest(page=page):
                self.assertIn("Northwind Logistics", html)

    def test_nothing_still_says_the_old_one(self):
        """The failure this is here for: a wordmark baked into the artwork,
        which leaves the page showing one name and saying another."""
        for page, html in self.pages.items():
            with self.subTest(page=page):
                self.assertNotIn("Example", html)
