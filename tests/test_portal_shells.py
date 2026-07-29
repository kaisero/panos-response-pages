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
                self.assertRegex(body, r"#logo(?:\s+\.mk|::before)\s*\{[^}]*background:var\(--lg\)")
                self.assertRegex(body, r"#logo\s+img\s*\{[^}]*display\s*:\s*none")

    def test_every_shell_offers_both_scheme_copies_of_the_logo(self):
        """The artwork is an isolated document, so the scheme cannot reach into
        it -- the shell has to choose between two whole assets. A shell that
        defines --lgl but never --lgd shows the light mark on a dark page."""
        for p in SHELLS:
            with self.subTest(shell=p.stem):
                body = css(p)
                for var in ("--lgl:url(", "--lgd:url("):
                    self.assertIn(var, body)
                self.assertIn("html[data-force-scheme=dark]{--lg:var(--lgd)}", body)
                self.assertIn("@media(prefers-color-scheme:dark){:root{--lg:var(--lgd)}}", body)

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
    def test_login_carries_no_img_and_no_logo_variable(self):
        """The mark is a CSS background on both imports now. An <img> would put
        it back on PAN-OS' ready handler -- one asset, no scheme -- and would
        paint nothing at all until jQuery had loaded."""
        for (theme, page), html in portal_pages().items():
            if page == "login":
                with self.subTest(theme=theme):
                    self.assertNotRegex(html, r'id="logo"[^>]*>\s*<img')
                    self.assertIn("var logo='';", html)

    def test_the_wordmark_is_text_not_artwork(self):
        """A name drawn into the SVG cannot follow a rename in config, and an
        SVG cannot measure text -- so a fixed viewBox either clips a long name
        or shrinks a short one. The mark is a symbol; the name is text."""
        for (theme, page), html in portal_pages().items():
            with self.subTest(theme=theme, page=page):
                if page == "login":
                    # A <span> beside the mark, in a body we own.
                    self.assertRegex(html, r'<div id="logo"><span class="mk"[^>]*></span><span>[^<]+</span></div>')
                else:
                    # PAN-OS owns the logout body, so the only way in is CSS.
                    self.assertRegex(html, r'#logo::after\{content:"[^"]+"\}')

    def test_the_mark_carries_no_lettering(self):
        """The check that keeps the two from drifting back together."""
        for (theme, page), html in portal_pages().items():
            with self.subTest(theme=theme, page=page):
                for uri in re.findall(r"--lg[ld]:url\(\"([^\"]+)\"\)", html):
                    self.assertNotIn("%3Ctext", uri, "the mark has lettering drawn into it")

    def test_the_two_scheme_copies_are_different_artwork(self):
        """Both copies are the same source file rendered twice. If the S_*
        binding ever stopped switching, they would be byte-identical and the
        dark page would show light-scheme ink -- with nothing else to notice."""
        for (theme, page), html in portal_pages().items():
            if page == "login":
                with self.subTest(theme=theme):
                    light = re.search(r"--lgl:url\(\"([^\"]+)\"\)", html)
                    dark = re.search(r"--lgd:url\(\"([^\"]+)\"\)", html)
                    self.assertIsNotNone(light)
                    self.assertIsNotNone(dark)
                    self.assertNotEqual(light.group(1), dark.group(1))
