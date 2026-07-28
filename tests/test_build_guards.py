"""The PAN-OS guards.

PAN-OS accepts an oversize or malformed response page without complaint: the
import reports success, the commit succeeds, and users silently get the default
page or nothing at all. These guards are the only feedback loop that exists.
"""

import pathlib
import unittest

from _build import built
from _paths import DATA

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
        _size, errors, _warnings = build.validate("url-block-page", "assist", page)
        self.assertTrue(any("transmit" in e.lower() for e in errors), errors)


class TestPanOsGuards(unittest.TestCase):
    HEAD = (
        "<!DOCTYPE html>\n<html><head>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "</head><body>{}</body></html>"
    )

    def test_rejects_oversize_page(self):
        page = self.HEAD.format("x" * 18000)
        _size, errors, _warnings = build.validate("url-block-page", "assist", page)
        self.assertTrue(any("ceiling" in e for e in errors), errors)

    def test_warns_near_ceiling(self):
        page = self.HEAD.format("x" * 16500)
        _size, errors, warnings = build.validate("url-block-page", "assist", page)
        self.assertEqual(errors, [])
        self.assertTrue(any("ceiling" in w for w in warnings), warnings)

    def test_rejects_external_reference(self):
        page = self.HEAD.format('<link rel="stylesheet" href="https://x.test/a.css">')
        _size, errors, _warnings = build.validate("url-block-page", "assist", page)
        self.assertTrue(any("self-contained" in e for e in errors), errors)

    def test_allows_mailto(self):
        page = self.HEAD.format('<a href="mailto:it@example.com">Report to IT</a>')
        _size, errors, _warnings = build.validate("url-block-page", "assist", page)
        self.assertEqual(errors, [])

    def test_rejects_token_unavailable_on_page(self):
        page = self.HEAD.format("<p><category/></p>")
        _size, errors, _warnings = build.validate("safe-search-block-page", "assist", page)
        self.assertTrue(any("not available on safe-search-block-page" in e for e in errors), errors)

    def test_rejects_missing_doctype(self):
        _size, errors, _warnings = build.validate("url-block-page", "assist", "<html></html>")
        self.assertTrue(any("DOCTYPE" in e for e in errors), errors)


class TestRealBuild(unittest.TestCase):
    def test_real_build_is_clean(self):
        _out, result = built()
        failures = [f"{r.theme}/{r.page}: {e}" for r in result.results for e in r.errors]
        self.assertEqual(failures, [], "the shipped templates must build clean")

    def test_no_prototype_era_strings_remain(self):
        """The tool used to carry design-exploration language. It reads as an
        unfinished draft to anyone who meets it on a firewall."""
        import panos_response_pages

        pkg = pathlib.Path(panos_response_pages.__file__).parent
        for path in pkg.rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            self.assertNotIn("Three directions", src, path.name)
            self.assertNotIn("--theme calm", src, path.name)
        label = (DATA / "themes/assist.json").read_text(encoding="utf-8")
        self.assertNotIn("B · ", label, "prototype selection prefix left in theme label")


if __name__ == "__main__":
    unittest.main()
