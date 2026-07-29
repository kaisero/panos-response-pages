"""Per-shell rules. Each is measured behaviour, and each fails silently."""

import pathlib
import re
import unittest

import pytest

from _build import portal_pages
from _paths import DATA

pytestmark = pytest.mark.integration

SHELLS = sorted((DATA / "templates/portal/shells").glob("*.html"))


def css(p: pathlib.Path) -> str:
    return re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)


class TestShellRules(unittest.TestCase):
    def test_shells_exist_for_every_theme(self):
        themes = {p.stem for p in (DATA / "templates/shells").glob("*.html")}
        self.assertEqual({p.stem for p in SHELLS}, themes)

    def test_only_the_horizontal_axis_is_clamped(self):
        """The change-password state is taller than the viewport, and only an
        expired password reveals it. Scoped to html/body: .field's own
        overflow:hidden is what makes clamping only overflow-x safe, so a
        whole-file assertion would forbid the very rule that makes this work."""
        pat = re.compile(r"(?:^|\n|\})\s*(?:html|body)[^{]*\{[^}]*overflow(?:-y)?\s*:\s*hidden")
        for p in SHELLS:
            with self.subTest(shell=p.stem):
                self.assertNotRegex(css(p), pat)

    def test_logout_logo_is_painted_from_css(self):
        """PAN-OS hard-codes its own <img src=...> into the logout body and
        only rewrites it at ready. A stylesheet applies at first paint; this is
        the only fix for the flash."""
        for p in SHELLS:
            with self.subTest(shell=p.stem):
                body = css(p)
                self.assertRegex(body, r"#logo\s*\{[^}]*background\s*:\s*url\(\s*[\"']?data:image/svg")
                self.assertRegex(body, r"#logo\s+img\s*\{[^}]*display\s*:\s*none")

    def test_logout_message_slot_reserves_height(self):
        """#logout is empty at parse time and filled at ready; without a
        min-height the card visibly resizes when text lands."""
        for p in SHELLS:
            with self.subTest(shell=p.stem):
                self.assertRegex(css(p), r"#logout\s*\{[^}]*min-height")

    def test_the_change_password_reset_does_not_out_specify_the_message_box(self):
        """PAN-OS puts class="msg" on the message div as well as on its border
        wrapper, so `#dChangePasswordMsgArea .msg` matches the message box too
        -- and at one id plus one class it beats `#dChangePasswordMsg`,
        stripping the padding and background off the box that shows the text.
        Only the change-password state renders any of it, so on a firewall
        nothing reveals it until somebody's password expires."""
        for p in SHELLS:
            with self.subTest(shell=p.stem):
                self.assertNotIn("#dChangePasswordMsgArea .msg", css(p))
                self.assertRegex(css(p), r"#dChangePasswordMsg\s*\{[^}]*padding")

    def test_no_shell_claims_an_id_panos_also_emits(self):
        """The injected form brings its own #activearea and #formdiv, so those
        ids are not unique. getElementById would silently return ours."""
        pat = re.compile(r"getElementById\(\s*['\"](?:formdiv|activearea|logo|heading)['\"]")
        for p in SHELLS:
            with self.subTest(shell=p.stem):
                self.assertNotRegex(p.read_text(encoding="utf-8"), pat)


class TestLoginLogo(unittest.TestCase):
    def test_login_logo_img_ships_without_a_src(self):
        """Shipping a src paints something before the logo variable lands --
        either a broken image or the wrong mark."""
        for (theme, page), html in portal_pages().items():
            if page == "login":
                with self.subTest(theme=theme):
                    m = re.search(r'<div id="logo">\s*<img([^>]*)>', html)
                    self.assertIsNotNone(m, "no #logo img")
                    self.assertNotIn("src=", m.group(1))
