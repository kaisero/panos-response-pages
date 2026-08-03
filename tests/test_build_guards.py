"""The PAN-OS guards.

PAN-OS accepts an oversize or malformed response page without complaint: the
import reports success, the commit succeeds, and users silently get the default
page or nothing at all. These guards are the only feedback loop that exists.
"""

import unittest

from _build import built

# The guards moved into the package; the alias keeps the assertions below
# reading the way they always did.
from panos_response_pages import validate as build


class TestCopyAudit(unittest.TestCase):
    def test_flags_transmission_claim(self):
        errs = build.audit_copy("<p>Nothing you typed was sent.</p>")
        self.assertTrue(errs)
        self.assertTrue(any("transmit" in e.lower() for e in errs), errs)

    def test_flags_universality_claim(self):
        errs = build.audit_copy("<p>This is blocked for everyone.</p>")
        self.assertTrue(errs)
        self.assertTrue(any("all users" in e.lower() for e in errs), errs)

    def test_passes_clean_copy(self):
        self.assertEqual(build.audit_copy("<p>Report to IT and we will review it.</p>"), [])

    def test_is_case_insensitive(self):
        self.assertTrue(build.audit_copy("<p>NOTHING YOU TYPED was sent</p>"))

    def test_validate_surfaces_copy_errors(self):
        page = (
            "<!DOCTYPE html>\n<html><head>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "</head><body><p>Nothing you typed was sent.</p></body></html>"
        )
        _size, errors, _warnings = build.validate("url-block-page", page)
        self.assertTrue(any("transmit" in e.lower() for e in errors), errors)


class TestPanOsGuards(unittest.TestCase):
    HEAD = (
        "<!DOCTYPE html>\n<html><head>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "</head><body>{}</body></html>"
    )

    def test_rejects_oversize_page(self):
        page = self.HEAD.format("x" * 18000)
        _size, errors, _warnings = build.validate("url-block-page", page)
        self.assertTrue(any("ceiling" in e for e in errors), errors)

    def test_warns_near_ceiling(self):
        page = self.HEAD.format("x" * 16500)
        _size, errors, warnings = build.validate("url-block-page", page)
        self.assertEqual(errors, [])
        self.assertTrue(any("ceiling" in w for w in warnings), warnings)

    def test_rejects_external_reference(self):
        page = self.HEAD.format('<link rel="stylesheet" href="https://x.test/a.css">')
        _size, errors, _warnings = build.validate("url-block-page", page)
        self.assertTrue(any("self-contained" in e for e in errors), errors)

    def test_allows_mailto(self):
        page = self.HEAD.format('<a href="mailto:it@example.com">Report to IT</a>')
        _size, errors, _warnings = build.validate("url-block-page", page)
        self.assertEqual(errors, [])

    def test_rejects_token_unavailable_on_page(self):
        page = self.HEAD.format("<p><category/></p>")
        _size, errors, _warnings = build.validate("safe-search-block-page", page)
        self.assertTrue(any("not available on safe-search-block-page" in e for e in errors), errors)

    def test_rejects_missing_doctype(self):
        _size, errors, _warnings = build.validate("url-block-page", "<html></html>")
        self.assertTrue(any("DOCTYPE" in e for e in errors), errors)


class TestRealBuild(unittest.TestCase):
    def test_real_build_is_clean(self):
        _out, result = built()
        failures = [f"{r.theme}/{r.page}: {e}" for r in result.results for e in r.errors]
        self.assertEqual(failures, [], "the shipped templates must build clean")


CONTACT_OK = (
    '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
    '</head><body><a id="rep" href="https://tickets.example.com/new">Report to IT</a></body></html>'
)
CONTACT_HTTP = CONTACT_OK.replace("https://", "http://")
STRAY_LINK = CONTACT_OK.replace('id="rep" ', "")
STRAY_IMG = CONTACT_OK.replace(
    '<a id="rep" href="https://tickets.example.com/new">Report to IT</a>',
    '<img src="https://cdn.example.com/logo.png">',
)


class TestContactAnchor(unittest.TestCase):
    """The one link allowed to leave the page, and only that one."""

    def test_https_on_the_contact_anchor_is_allowed(self):
        _size, errors, _warnings = build.validate("url-block-page", CONTACT_OK)
        self.assertFalse(any("not self-contained" in e for e in errors), errors)

    def test_http_on_the_contact_anchor_is_refused(self):
        """Cleartext on a page whose whole job is to be trusted."""
        _size, errors, _warnings = build.validate("url-block-page", CONTACT_HTTP)
        self.assertTrue(any("not self-contained" in e for e in errors))

    def test_https_on_any_other_link_is_still_refused(self):
        _size, errors, _warnings = build.validate("url-block-page", STRAY_LINK)
        self.assertTrue(any("not self-contained" in e for e in errors))

    def test_external_image_is_still_refused(self):
        _size, errors, _warnings = build.validate("url-block-page", STRAY_IMG)
        self.assertTrue(any("not self-contained" in e for e in errors))

    def test_an_attribute_merely_ending_in_id_is_not_the_contact_anchor(self):
        """`'id="rep"' in tag` would wave this through; the exemption is for the
        real id attribute, not for anything whose name happens to end in one."""
        html = CONTACT_OK.replace('id="rep"', 'xid="rep"')
        _size, errors, _warnings = build.validate("url-block-page", html)
        self.assertTrue(any("not self-contained" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
