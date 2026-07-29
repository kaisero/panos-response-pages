"""The one portal failure PAN-OS reports properly."""

import base64
import unittest

import pytest

from _build import portal_pages
from panos_response_pages.portal.validate import MAX_ENCODED, SOFT_MAX, WARN_AT

pytestmark = pytest.mark.integration


class TestPortalBudget(unittest.TestCase):
    def test_every_theme_fits_the_import_ceiling(self):
        for (theme, page), html in portal_pages().items():
            with self.subTest(theme=theme, page=page):
                raw = html.encode("utf-8")
                encoded = len(base64.encodebytes(raw))
                self.assertLessEqual(len(raw), SOFT_MAX, f"{theme}/{page} {len(raw)} B")
                self.assertLessEqual(encoded, MAX_ENCODED, f"{theme}/{page} {encoded} chars")

    def test_the_ceiling_arithmetic_still_holds(self):
        self.assertLessEqual(len(base64.encodebytes(b"x" * SOFT_MAX)), MAX_ENCODED)
        self.assertGreater(len(base64.encodebytes(b"x" * (SOFT_MAX + 1))), MAX_ENCODED)

    def test_headroom_is_reported_before_it_is_gone(self):
        self.assertLess(WARN_AT, SOFT_MAX)
