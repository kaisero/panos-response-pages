"""Portal guards. Every rule maps to a measured failure on a live firewall.

Only the size check fails loudly -- PAN-OS refuses the import and quotes the
encoded length back at you. Every other rule here fails silently: the import
succeeds, the commit succeeds, and the portal serves something other than what
was meant. A second form token hidden in a comment, or one stray '<' in a
script, otherwise costs a round-trip through the firewall to discover.
"""

import unittest

import pytest

from panos_response_pages.portal.validate import (
    HOME_VARS,
    LOGIN_VARS,
    SOFT_MAX,
    detect_kind,
    validate_portal,
)

pytestmark = pytest.mark.unit


def login_doc(body: str = "<pan_form/>") -> str:
    """A minimal VALID login fragment, so each test alters exactly one thing."""
    decls = "".join(f"var {v}='';" for v in LOGIN_VARS)
    return f"<script>{decls}</script></head><body>{body}</body></html>"


def home_doc() -> str:
    decls = "".join(f"var {v}='';" for v in HOME_VARS)
    return f"<script>{decls}var logout_text_array=['a'];</script>"


class TestKindDetection(unittest.TestCase):
    def test_logout_text_array_discriminates_the_two_shapes(self):
        """It is the cleanest signal: only the Home import has it."""
        self.assertEqual(detect_kind(home_doc()), "home")
        self.assertEqual(detect_kind(login_doc()), "login")


class TestFileShape(unittest.TestCase):
    def test_a_valid_fragment_passes(self):
        _size, errors, _warnings = validate_portal(login_doc())
        self.assertEqual(errors, [])

    def test_rejects_a_whole_document(self):
        _s, errors, _w = validate_portal("<!DOCTYPE html><html></html>")
        self.assertTrue(any("supplies <html>" in e for e in errors), errors)

    def test_login_must_close_head(self):
        decls = "".join(f"var {v}='';" for v in LOGIN_VARS)
        _s, errors, _w = validate_portal(f"<script>{decls}</script><body><pan_form/></body></html>")
        self.assertTrue(any("</head>" in e for e in errors), errors)

    def test_home_must_not_carry_structural_tags(self):
        _s, errors, _w = validate_portal(home_doc() + "<body>x</body>")
        self.assertTrue(any("script-only" in e for e in errors), errors)


class TestPanForm(unittest.TestCase):
    def test_login_requires_one(self):
        _s, errors, _w = validate_portal(login_doc(body=""))
        self.assertTrue(any("no <pan_form/>" in e for e in errors), errors)

    def test_two_tokens_are_rejected(self):
        """Only the first is substituted; a second -- comments included --
        leaves the form misplaced."""
        _s, errors, _w = validate_portal(login_doc(body="<pan_form/><pan_form/>"))
        self.assertTrue(any("only the first" in e for e in errors), errors)

    def test_home_must_not_carry_one(self):
        _s, errors, _w = validate_portal(home_doc().replace("</script>", "</script><pan_form/>"))
        self.assertTrue(any("no form is placed" in e for e in errors), errors)


class TestSilentBreakers(unittest.TestCase):
    def test_raw_angle_bracket_outside_a_tag(self):
        """`i < n` stops <pan_form/> being substituted at all."""
        _s, errors, _w = validate_portal(login_doc(body="<pan_form/><script>if(1 < 2){}</script>"))
        self.assertTrue(any("raw '<'" in e for e in errors), errors)

    def test_baked_csrf_token(self):
        """It is generated per page load; a stale one fails authentication."""
        _s, errors, _w = validate_portal(login_doc(body='<pan_form/><input name="csrf-token">'))
        self.assertTrue(any("csrf-token" in e for e in errors), errors)

    def test_external_reference_blocked_by_csp(self):
        _s, errors, _w = validate_portal(login_doc(body='<pan_form/><img src="https://x.test/a.png">'))
        self.assertTrue(any("CSP" in e for e in errors), errors)

    def test_an_attribute_merely_ending_in_id_is_not_the_contact_anchor(self):
        """`'id="rep"' in tag` would wave this through; the exemption is for the
        real id attribute, not for anything whose name happens to end in one."""
        body = '<pan_form/><a xid="rep" href="https://tickets.example.com/new">Report to IT</a>'
        _s, errors, _w = validate_portal(login_doc(body=body))
        self.assertTrue(any("CSP" in e for e in errors), errors)

    def test_a_data_uri_logo_is_not_mistaken_for_an_external_reference(self):
        """The logo carries xmlns=%27http://www.w3.org/2000/svg%27 percent-
        encoded, which must not trip the CSP check."""
        body = (
            "<pan_form/><script>var l='data:image/svg+xml,%3Csvg%20xmlns=%27http://www.w3.org/2000/svg%27%3E';</script>"
        )
        _s, errors, _w = validate_portal(login_doc(body=body))
        self.assertEqual([e for e in errors if "CSP" in e], [])

    def test_every_declared_variable_is_required(self):
        """PAN-OS's ready handler dereferences each one; a missing name throws
        and aborts the whole handler."""
        for var in LOGIN_VARS:
            with self.subTest(var=var):
                doc = login_doc().replace(f"var {var}='';", "")
                _s, errors, _w = validate_portal(doc)
                self.assertTrue(any(f"var {var}" in e for e in errors), var)

    def test_home_requires_all_fourteen(self):
        for var in HOME_VARS:
            if var == "logout_text_array":
                continue  # its absence changes the detected kind
            with self.subTest(var=var):
                doc = home_doc().replace(f"var {var}='';", "")
                _s, errors, _w = validate_portal(doc)
                self.assertTrue(any(f"var {var}" in e for e in errors), var)


class TestByteCeiling(unittest.TestCase):
    def test_accepts_at_the_ceiling(self):
        doc = login_doc(body="<pan_form/>" + "x" * (SOFT_MAX - 400))
        size, errors, _w = validate_portal(doc)
        self.assertLessEqual(size, SOFT_MAX)
        self.assertEqual([e for e in errors if "refuse the import" in e], [])

    def test_rejects_over_the_ceiling(self):
        doc = login_doc(body="<pan_form/>" + "x" * SOFT_MAX)
        _s, errors, _w = validate_portal(doc)
        self.assertTrue(any("refuse the import" in e for e in errors), errors)
