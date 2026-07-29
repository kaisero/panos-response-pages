"""The preview splice, and the rules that keep it out of anything importable.

Splicing exists because neither portal import renders on its own -- one is a
body fragment, the other a bare script. Everything asserted here is a way the
simulator could lie: the wrong prefix on the wrong form, an asset path that
resolves nowhere, a state that silently did not apply, or spliced bytes
escaping into a tree the import guards walk.
"""

import pathlib
import tempfile
import unittest

import pytest

from _build import portal_pages
from _paths import DATA
from panos_response_pages.errors import BuildError
from panos_response_pages.portal.splice import (
    LOGIN_PREVIEWS,
    STATES,
    SURFACES,
    splice_home,
    splice_login,
)
from panos_response_pages.portal.validate import validate_portal

pytestmark = pytest.mark.integration

FIXTURES = DATA / "fixtures"


def login_import() -> str:
    return portal_pages()[("glass", "login")]


def home_import() -> str:
    return portal_pages()[("glass", "home")]


class TestSurfacePairing(unittest.TestCase):
    """The mistake this module was written to stop repeating."""

    def test_each_surface_gets_its_own_prefix_and_its_own_form(self):
        out = splice_login(login_import(), "login")
        self.assertIn("function loadPage()", out)
        self.assertIn('<form name="login"', out)
        self.assertNotIn('<form name="getsoftwarepage"', out)

        sw = splice_login(login_import(), "getsoftware")
        self.assertIn('<form name="getsoftwarepage"', sw)
        # The download prefix has no loadPage() and no submitClicked(). Splicing
        # the login prefix on instead invents `document.login is undefined`, an
        # error the live download page never produces.
        self.assertNotIn("function loadPage()", sw)
        self.assertNotIn("function submitClicked()", sw)
        self.assertNotIn('<form name="login"', sw)

    def test_the_two_prefixes_really_are_different_captures(self):
        """8,394 B against 1,797 B. If a re-capture ever made them the same
        file, the pairing above would still pass while meaning nothing."""
        sizes = {name: len((FIXTURES / prefix).read_bytes()) for name, (prefix, _form) in SURFACES.items()}
        self.assertGreater(sizes["login"], 2 * sizes["getsoftware"])

    def test_the_download_surface_has_no_states_to_ask_for(self):
        with self.assertRaises(BuildError) as caught:
            splice_login(login_import(), "getsoftware", "changepw")
        self.assertIn("loadPage", str(caught.exception))

    def test_unknown_surfaces_and_states_are_rejected(self):
        for call in (
            lambda: splice_login(login_import(), "portal-home"),
            lambda: splice_login(login_import(), "login", "locked-out"),
        ):
            with self.assertRaises(BuildError):
                call()

    def test_a_fragment_with_no_form_token_is_rejected(self):
        with self.assertRaises(BuildError):
            splice_login("<body>nothing here</body>")


class TestStates(unittest.TestCase):
    """loadPage() branches on values PAN-OS writes into the prefix per request.

    Rewriting those and letting the captured function run is the only honest
    way to see a state; anything that reached into the DOM afterwards would be
    previewing markup the page does not produce.
    """

    def test_default_leaves_the_capture_alone(self):
        self.assertEqual(STATES["default"], {})
        self.assertIn('var respStatus = "Success";', splice_login(login_import()))

    def test_each_state_sets_what_loadpage_branches_on(self):
        cases = {
            "error": ['var respStatus = "Error";'],
            "challenge": ['var respStatus = "Challenge";'],
            "changepw": ['var respStatus = "Error";', "var isChangePasswdForm = 1;", "var in_change_passwd = 1;"],
        }
        for state, expected in cases.items():
            out = splice_login(login_import(), "login", state)
            for literal in expected:
                with self.subTest(state=state, literal=literal):
                    self.assertIn(literal, out)

    def test_change_password_reaches_the_branch_that_shows_the_extra_fields(self):
        """isChangePasswdForm is only tested inside loadPage()'s Error branch,
        so a change-password preview with any other status shows a plain login
        form and looks entirely plausible."""
        self.assertEqual(STATES["changepw"]["respStatus"], '"Error"')
        self.assertNotIn('var respStatus = "Success";', splice_login(login_import(), "login", "changepw"))

    def test_a_state_that_matched_nothing_is_an_error_rather_than_a_no_op(self):
        """A re-captured prefix that renamed one of these would otherwise show
        the default state under four different labels, all of them plausible."""
        doctored = pathlib.Path(tempfile.mkdtemp())
        for name in ("panos-prefix-login.html", "pan_form-login.html"):
            text = (FIXTURES / name).read_text(encoding="utf-8").replace("var respStatus =", "var respState =")
            (doctored / name).write_text(text, encoding="utf-8")
        with self.assertRaises(BuildError) as caught:
            splice_login(login_import(), "login", "error", fixtures=doctored)
        self.assertIn("expected exactly 1", str(caught.exception))

    def test_every_state_has_a_preview_file_name(self):
        self.assertEqual(LOGIN_PREVIEWS, tuple(f"login-{s}" for s in STATES))


class TestAssets(unittest.TestCase):
    """jQuery is what fills the login logo, and it is loaded by relative path."""

    def test_asset_references_follow_the_prefix_they_are_given(self):
        out = splice_login(login_import(), "login", assets="../../portal/")
        self.assertIn('src="../../portal/js/jquery.min.js"', out)
        self.assertNotIn('src="portal/js/jquery.min.js"', out)

    def test_the_default_prefix_is_the_captured_one(self):
        self.assertIn('src="portal/js/jquery.min.js"', splice_login(login_import()))

    def test_the_asset_tree_ships_with_the_package(self):
        self.assertTrue((FIXTURES / "portal" / "js" / "jquery.min.js").is_file())

    def test_the_logout_page_gets_its_assets_repointed_too(self):
        out = splice_home(home_import(), assets="../../portal/")
        self.assertNotIn('href="portal/css/login.css"', out)
        self.assertIn('href="../../portal/css/login.css"', out)


class TestLogout(unittest.TestCase):
    def test_the_import_lands_between_the_captured_head_and_body(self):
        out = splice_home(home_import())
        self.assertLess(out.index("<head>"), out.index("var logout_text_array"))
        self.assertLess(out.index("var logout_text_array"), out.index("<body>"))

    def test_the_preview_stands_in_for_the_request_url(self):
        """The import gates its restyle on location.pathname, correctly -- the
        same file is also embedded in the portal home page, whose body has never
        been captured. A preview has no such pathname, so what the shim restores
        is the request URL's effect, not the page's logic."""
        out = splice_home(home_import())
        self.assertIn("location.pathname.indexOf('logout.esp')===-1", out)
        self.assertIn("setAttribute('data-gp','logout')", out)


class TestNeverImportable(unittest.TestCase):
    """The hard rule. Spliced bytes are for looking at, never for uploading."""

    def test_every_spliced_surface_is_rejected_by_the_import_guards(self):
        spliced = {name: splice_login(login_import(), "login", name.removeprefix("login-")) for name in LOGIN_PREVIEWS}
        spliced["getsoftware"] = splice_login(login_import(), "getsoftware")
        spliced["logout"] = splice_home(home_import())
        for name, text in spliced.items():
            with self.subTest(surface=name):
                _size, errors, _warnings = validate_portal(text)
                self.assertNotEqual(errors, [], f"{name} passed the import guards -- it must not")

    def test_the_import_itself_still_passes(self):
        """The pair of assertions is the point: the guards reject the splice
        because of what splicing adds, not because the import is broken."""
        _size, errors, _warnings = validate_portal(login_import())
        self.assertEqual(errors, [])

    def test_the_captured_form_carries_no_reusable_token(self):
        """PAN-OS mints a csrf-token per page load, so the captured one was
        valid for one request against one appliance. It is still replaced: a
        token-shaped string in a repository invites the opposite belief."""
        form = (FIXTURES / "pan_form-login.html").read_text(encoding="utf-8")
        self.assertIn('name="csrf-token" value="SAMPLE-PREVIEW-TOKEN-NOT-VALID"', form)
        self.assertIn("per page load", form, "the replacement needs to say why it is there")

    def test_the_csrf_input_is_why_spliced_output_can_never_be_validated(self):
        _size, errors, _warnings = validate_portal(splice_login(login_import()))
        self.assertTrue(any("csrf-token" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
