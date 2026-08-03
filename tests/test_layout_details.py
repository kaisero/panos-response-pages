"""Layout details that broke once and must not break again."""

import re
import unittest

from _build import preview_dir
from _paths import DATA

SHELL = (DATA / "templates/shells/assist.html").read_text(encoding="utf-8")
PAGES = DATA / "templates/pages"

SECTION_RE = re.compile(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", re.S)


def slots(name):
    text = (PAGES / f"{name}.html").read_text(encoding="utf-8")
    return {k: v.strip() for k, v in SECTION_RE.findall(text)}


class TestWarnline(unittest.TestCase):
    """.warnline is display:flex, which makes every inline child its own flex
    item. Bare text either side of a <strong> therefore laid out as separate
    columns, splitting one sentence into three. All text must sit in a single
    wrapping element."""

    WARNLINE_RE = re.compile(r'<p class="warnline">(.*?)</p>', re.S)

    def test_shell_reserves_one_flex_item_for_text(self):
        self.assertRegex(SHELL, r"\.warnline>span\s*\{[^}]*flex:1")
        self.assertRegex(SHELL, r"\.warnline>svg\s*\{[^}]*flex:none")

    def test_every_warnline_wraps_its_text_in_a_single_span(self):
        found = 0
        for page in PAGES.glob("*.html"):
            for body in self.WARNLINE_RE.findall(page.read_text(encoding="utf-8")):
                found += 1
                inner = body.replace("{{WARN_MARK}}", "").strip()
                self.assertTrue(
                    inner.startswith("<span>") and inner.endswith("</span>"),
                    f"{page.stem}: warnline text must be wrapped in one <span>, "
                    f"or flex will split the sentence -- got {inner[:70]!r}",
                )
                # exactly one span, no stray text outside it
                self.assertEqual(inner.count("<span>"), 1, page.stem)
        self.assertGreaterEqual(found, 1, "expected at least one warnline")

    def test_every_warnline_leads_with_the_warning_icon(self):
        for page in PAGES.glob("*.html"):
            for body in self.WARNLINE_RE.findall(page.read_text(encoding="utf-8")):
                self.assertTrue(
                    body.lstrip().startswith("{{WARN_MARK}}"), f"{page.stem}: warnline should open with the icon"
                )


class TestInfobox(unittest.TestCase):
    """The info callout shares the warnline's structure -- flex, so all text must
    live in one span or the sentence splits into columns."""

    INFOBOX_RE = re.compile(r'<p class="infobox">(.*?)</p>', re.S)

    BASE_RE = re.compile(r"\.infobox,\.warnline\{[^}]*\}")

    def test_both_callouts_share_one_treatment(self):
        """Info and warning are the same component with different meaning. The
        declarations are shared so the two cannot drift apart again."""
        base = self.BASE_RE.search(SHELL)
        self.assertIsNotNone(base, "callouts should share a single rule")
        self.assertIn("display:flex", base.group(0))
        self.assertRegex(SHELL, r"\.infobox>span,\.warnline>span\{[^}]*flex:1")
        self.assertRegex(SHELL, r"\.infobox>svg,\.warnline>svg\{[^}]*flex:none")

    def test_only_the_edge_and_icon_carry_severity(self):
        """The warning differs from the info box by colour of edge and icon, not
        by a different box. Body text stays on normal ink so it stays readable."""
        base = self.BASE_RE.search(SHELL).group(0)
        self.assertIn("color:var(--ik)", base, "callout text should use normal ink")
        self.assertNotIn("var(--tw)", base, "the shared base must be tone-independent")
        warn = re.search(r"(?m)^\.warnline\{[^}]*\}", SHELL).group(0)
        self.assertIn("border-left-color:var(--tt)", warn)
        self.assertRegex(SHELL, r"\.warnline>svg\{color:var\(--tt\)\}")

    def test_callout_prominence_does_not_vary_by_palette(self):
        """The accent wash is the ramp's 0 stop, which is a saturated peach in
        one brand and a pale cream in another. The derived surface tint plus a
        solid edge keeps the callout equally prominent everywhere."""
        base = self.BASE_RE.search(SHELL).group(0)
        self.assertIn("background:var(--sa)", base)
        self.assertRegex(base, r"border-left:\d+px solid var\(--at\)")
        self.assertNotIn("var(--aw)", base, "ramp-0 washes differ too much in lightness between brands")

    def test_every_infobox_wraps_its_text_in_a_single_span(self):
        """Same flex constraint as the warnline: bare text either side of a
        <strong> would lay out as separate columns."""
        found = 0
        for page in PAGES.glob("*.html"):
            for body in self.INFOBOX_RE.findall(page.read_text(encoding="utf-8")):
                found += 1
                inner = body.replace("{{INFO_MARK}}", "").strip()
                self.assertTrue(
                    inner.startswith("<span>") and inner.endswith("</span>"),
                    f"{page.stem}: info text must sit in one span -- got {inner[:70]!r}",
                )
                self.assertEqual(inner.count("<span>"), 1, page.stem)
        self.assertGreaterEqual(found, 1, "expected at least one info box")

    def test_credential_block_keeps_the_never_asks_guidance(self):
        body = (PAGES / "credential-block-page.html").read_text(encoding="utf-8")
        boxes = self.INFOBOX_RE.findall(body)
        self.assertEqual(len(boxes), 1)
        self.assertIn("never ask", boxes[0])

    def test_no_page_mixes_a_warnline_and_an_infobox(self):
        """Two stacked callouts read as competing alerts; each page should make
        one supplementary statement."""
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            self.assertFalse(
                self.INFOBOX_RE.search(body) and TestWarnline.WARNLINE_RE.search(body),
                f"{page.stem} carries both a warnline and an info box",
            )

    def test_every_infobox_leads_with_the_info_icon(self):
        for page in PAGES.glob("*.html"):
            for body in self.INFOBOX_RE.findall(page.read_text(encoding="utf-8")):
                self.assertTrue(body.lstrip().startswith("{{INFO_MARK}}"), page.stem)


class TestActionOrder(unittest.TestCase):
    def test_continue_sits_left_of_report_on_both_coach_pages(self):
        for name in ("url-coach-text", "credential-coach-text"):
            actions = slots(name)["ACTIONS"]
            self.assertIn("<pan_form/>", actions, f"{name} should offer Continue")
            self.assertLess(
                actions.index("<pan_form/>"),
                actions.index("Report to IT"),
                f"{name}: Continue must precede Report to IT",
            )


class TestActionStyling(unittest.TestCase):
    def test_report_to_it_is_a_button_on_every_page_that_offers_it(self):
        """It rendered as an underlined text link on url-coach-text, which read
        as prose rather than a control."""
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            if "Report to IT" not in body:
                continue
            # The mailto body carries <url/> and <category/>, so the anchor's
            # attributes contain ">" -- match backwards from the label instead.
            idx = body.index(">Report to IT</a>")
            opening = body.rindex("<a ", 0, idx)
            self.assertIn('class="btn"', body[opening:idx], f"{page.stem}: Report to IT must be a full button")

    def test_no_underlined_action_style_remains(self):
        self.assertNotIn("btn-secondary", SHELL, "the underlined secondary style was retired")
        for page in PAGES.glob("*.html"):
            self.assertNotIn("btn-secondary", page.read_text(encoding="utf-8"), page.stem)


class TestIndicatorAndInjectedForm(unittest.TestCase):
    def test_indicator_is_in_the_production_shell(self):
        self.assertIn('<div class="ind">{{MARK}}</div>', SHELL)
        self.assertRegex(SHELL, r"\.hd\s+\.ind\s*\{[^}]*border-radius:50%")

    def test_indicator_stacks_on_mobile(self):
        mobile = SHELL[SHELL.index("@media(max-width:600px)") :]
        self.assertRegex(mobile, r"\.hd\{grid-template-columns:1fr")

    def test_mobile_actions_share_a_row(self):
        """`.btn{width:100%}` in the mobile block forced Continue and Report to IT
        onto separate rows even at 430px, where both fit comfortably."""
        mobile = SHELL[SHELL.index("@media(max-width:600px)") :]
        self.assertNotRegex(mobile, r"\.btn\{width:100%\}", "full-width buttons stack instead of sharing a row")
        self.assertRegex(mobile, r"\.acts>\.btn,\.acts>form\{flex:1")
        self.assertRegex(
            mobile, r"\.acts>form input\{width:100%\}", "the injected control must fill its flexed form wrapper"
        )


class TestMailto(unittest.TestCase):
    """A raw "&" in <url/> terminates the mailto body parameter, silently
    dropping every field after it. PAN-OS substitutes raw bytes, so the page
    cannot encode at serve time -- the script rebuilds the href from the rendered
    fact table with encodeURIComponent, and the static href is ordered so that a
    no-JS truncation loses only trailing text."""

    def _report_links(self):
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            if 'id="rep"' in body:
                start = body.index('id="rep"')
                # Bound on '">', not '>': the email-mode href embeds raw PAN-OS
                # tokens like <user/>, and cutting at the first bare '>' would
                # close the slice on that token's own bracket instead of the
                # attribute's closing quote, truncating the anchor mid-href.
                yield page.stem, body[body.rindex("<a ", 0, start) : body.index('">', body.index('href="', start)) + 2]

    def _mailto_sections(self):
        """The pre-filled mailto each page declares.

        It lives in its own section rather than in the anchor, because the anchor's
        href is now chosen at build time between this and a configured ticket URL.
        The <url/> ordering rule follows the mailto, not the anchor.
        """
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            m = re.search(r"<!--@CONTACT_MAILTO-->(.*?)<!--/@CONTACT_MAILTO-->", body, re.S)
            if m:
                yield page.stem, m.group(1)

    def test_every_report_link_carries_the_rebuild_attributes(self):
        # data-to is email-mode only -- it is an address, and a ticket URL has
        # none -- so the template carries {{CONTACT_TO}} and the build decides.
        # The other three ship in both modes: they are the page's incident
        # metadata, and what a ticket adapter will read.
        found = 0
        for name, tag in self._report_links():
            found += 1
            for attr in ("{{CONTACT_TO}}", "data-subject", "data-intro", "data-prompt"):
                self.assertIn(attr, tag, f"{name} missing {attr}")
        expected = len(list(PAGES.glob("*.html")))
        self.assertEqual(found, expected, "every page should offer a way to reach IT")

    def test_every_page_declares_a_mailto_section(self):
        """Email mode is the default, so a page without one has no href at all.
        page.py falls back to an empty string rather than raising."""
        declared = {name for name, _ in self._mailto_sections()}
        expected = {p.stem for p in PAGES.glob("*.html")}
        self.assertEqual(declared, expected, "every page needs a pre-filled mailto for email mode")

    def test_mailto_sections_are_single_line(self):
        """parse_sections strips the outer whitespace but not the interior, so a
        newline introduced by reformatting would land inside the href."""
        for name, mailto in self._mailto_sections():
            self.assertNotIn("\n", mailto.strip(), f"{name}: the mailto section must stay on one line")

    def test_static_fallback_puts_the_url_token_last(self):
        checked = 0
        for name, mailto in self._mailto_sections():
            if "<url/>" not in mailto:
                continue  # safe-search, application and file pages have no <url/> token
            checked += 1
            after = mailto[mailto.index("<url/>") + len("<url/>") :]
            self.assertNotIn(
                "%0A",
                after,
                f"{name}: no field may follow <url/> in the static href, or an '&' in the URL truncates it away",
            )
        self.assertGreaterEqual(checked, 4, "no page's mailto carried a <url/> token -- this test asserted nothing")

    def test_subjects_are_distinct_per_page(self):
        subjects = {}
        for name, tag in self._report_links():
            m = re.search(r'data-subject="([^"]+)"', tag)
            self.assertIsNotNone(m, name)
            subjects.setdefault(m.group(1), []).append(name)
        dupes = {s: n for s, n in subjects.items() if len(n) > 1}
        self.assertEqual(dupes, {}, f"pages share a mail subject, so tickets are indistinguishable: {dupes}")


class TestPreviewGallery(unittest.TestCase):
    """preview/index.html is generated by build.py and is the thing a reviewer
    actually looks at, so it gets the same scrutiny as the pages."""

    @classmethod
    def setUpClass(cls):
        cls.html = (preview_dir() / "index.html").read_text(encoding="utf-8")

    def _visible(self):
        """Markup with <style> and <script> stripped -- 'flex-direction' is not
        user-facing copy."""
        out = re.sub(r"<style>.*?</style>", "", self.html, flags=re.S)
        return re.sub(r"<script>.*?</script>", "", out, flags=re.S)

    def test_uses_preview_language_not_prototype(self):
        visible = self._visible().lower()
        for word in ("prototype", "direction"):
            self.assertNotIn(word, visible, f"the preview is not a design exploration: {word!r}")

    def test_style_selector_appears_exactly_when_there_is_a_choice(self):
        """The style is fixed at build time, so a one-option radiogroup is noise --
        but once a build produces several, every one of them has to be reachable
        or the gallery quietly hides a style from review."""
        import json

        themes = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "themes").glob("*.json"))]
        if len(themes) == 1:
            self.assertNotIn('id="themegrp"', self.html)
        else:
            self.assertIn('id="themebtn"', self.html, "no style control was emitted")
            for theme in themes:
                self.assertIn(
                    f'data-value="{theme["name"]}"', self.html, f"{theme['name']} is built but not selectable"
                )

    def test_the_long_lists_do_not_grow_the_control_bar(self):
        """The chrome used to cost about 500 px of a 900 px viewport, most of it
        the page list wrapping onto three rows. The closed control is one line
        whatever a build produces -- its rows live in a popup that is hidden
        until opened -- so this is the rule that keeps the bar from creeping
        back: no page name may appear as a visible button in the bar itself."""
        self.assertIn('id="pagebtn"', self.html)
        self.assertNotRegex(self.html, r'<button role="radio" data-page="')

    def test_the_portal_frames_are_not_shrink_wrapped(self):
        """A portal page is a small card centred in min-height:100vh. Collapsing
        the frame to the card collapses the viewport it is centred in, so it
        loses the background it was designed to sit on and reads as a broken
        thumbnail. Block pages fill their frame and still shrink-wrap."""
        self.assertRegex(self.html, r"var FLOOR=\{desktop:\d{3},mobile:\d{3}\}")
        self.assertIn('i.setAttribute("data-min",FLOOR[kind])', self.html)

    def test_the_spliced_frames_still_carry_their_warning(self):
        """The one thing on this page that is not decoration: a spliced preview
        carries PAN-OS' own prefix and an inert CSRF token, and importing one
        breaks the portal."""
        self.assertIn("never importable", self.html)

    def test_every_control_is_labelled(self):
        """Two of the segmented controls dropped their visible caption to fit
        the bar on one line, so the label has to survive somewhere."""
        for group in ("Viewport", "Colour scheme"):
            self.assertIn(f'aria-label="{group}"', self.html)
        for ctl in ("Style", "Page"):
            self.assertIn(f"<span>{ctl}</span>", self.html)

    def test_takes_its_colours_from_the_palette(self):
        import json

        palette = json.loads((DATA / "palettes/cyber-orange.json").read_text(encoding="utf-8"))
        self.assertIn(palette["colors"]["accent"], self.html, "preview chrome should use the built palette's accent")
        self.assertIn(palette["colors"]["d_accent"], self.html)

    def test_frames_are_sized_to_their_content(self):
        """Fixed iframe heights made every page scroll inside its frame."""
        self.assertIn("function fit(", self.html)
        self.assertNotRegex(self.html, r"\.dev\.desktop iframe\{[^}]*height:\d+px")
        self.assertNotRegex(self.html, r"\.dev\.mobile iframe\{[^}]*height:\d+px")

    def test_embedded_pages_cannot_break_out_of_the_payload(self):
        self.assertNotIn("</script>", self.html[: self.html.rindex("</script>")])


if __name__ == "__main__":
    unittest.main()
