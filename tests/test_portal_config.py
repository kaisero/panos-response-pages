"""Portal copy lives in config, not in templates.

logout_text_array is the ONLY supported way to change logout wording. Messages
3, 4 and 5 are visible to end users but actionable only by an administrator, so
they name a real contact rather than saying "contact system administrator".
"""

import unittest

import pytest

from _paths import DATA
from panos_response_pages.config import load_config

pytestmark = pytest.mark.integration


class TestPortalConfig(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config("contoso", DATA / "config")

    def test_ships_a_portal_name_and_logo(self):
        self.assertIn("portalName", self.cfg)
        self.assertIn("portalLogoUri", self.cfg)

    def test_logout_messages_keep_all_seven_in_order(self):
        """PAN-OS picks the index via ?code=N. Dropping or reordering one
        silently shows the wrong message."""
        msgs = self.cfg["logoutMessages"]
        self.assertEqual(len(msgs), 7)
        self.assertIn("logged out", msgs[0].lower())
        self.assertIn("license", msgs[1].lower())
        self.assertIn("expired", msgs[6].lower())

    def test_admin_only_errors_name_a_contact(self):
        """load_config performs no interpolation, so the raw token survives
        here and is resolved during composition."""
        for i in (3, 4, 5):
            with self.subTest(index=i):
                self.assertIn("{{SUPPORT_EMAIL}}", self.cfg["logoutMessages"][i])

    def test_no_message_tells_a_user_to_contact_an_administrator(self):
        """The stock wording names a role the user has no way to reach."""
        for i, msg in enumerate(self.cfg["logoutMessages"]):
            with self.subTest(index=i):
                self.assertNotIn("system administrator", msg.lower())

    def test_portal_logo_is_a_data_uri(self):
        """An external URL is a third party who sees every portal visitor's IP
        and user-agent, and whose outage becomes a broken login page."""
        self.assertTrue(self.cfg["portalLogoUri"].startswith("data:image/svg+xml,"))

    def test_portal_logo_carries_its_own_dark_scheme_swap(self):
        """An <img>-referenced SVG renders as an isolated document: the page's
        custom properties are out of scope, so the query must live inside it."""
        self.assertIn("prefers-color-scheme", self.cfg["portalLogoUri"])
