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

    def test_no_color_mix_dependency(self):
        """color-mix() is newer than the CSS this project is willing to assume,
        and an unsupported value here would drop the border silently."""
        self.assertNotIn("color-mix", SHELL)

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

    def test_pan_form_controls_are_styled(self):
        """PAN-OS injects its own markup for <pan_form/>; unstyled it renders as
        a raw browser button beside a designed primary action."""
        self.assertRegex(SHELL, r"\.acts input\[type=submit\]")
        self.assertRegex(SHELL, r"\.acts (input\[type=submit\],|.*)button\{")


if __name__ == "__main__":
    unittest.main()


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
                yield page.stem, body[body.rindex("<a ", 0, start) : body.index(">", body.index('href="', start))]

    def test_every_report_link_carries_the_rebuild_attributes(self):
        found = 0
        for name, tag in self._report_links():
            found += 1
            for attr in ("data-to", "data-subject", "data-intro", "data-prompt"):
                self.assertIn(attr, tag, f"{name} missing {attr}")
        expected = len(list(PAGES.glob("*.html")))
        self.assertEqual(found, expected, "every page should offer a way to reach IT")

    def test_static_fallback_puts_the_url_token_last(self):
        for name, tag in self._report_links():
            if "<url/>" not in tag:
                continue  # safe-search has no <url/> token
            after = tag[tag.index("<url/>") + len("<url/>") :]
            self.assertNotIn(
                "%0A",
                after,
                f"{name}: no field may follow <url/> in the static href, or an '&' in the URL truncates it away",
            )

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
            self.assertNotIn("data-theme=", self.html)
        else:
            self.assertIn("data-theme=", self.html, "no style selector was emitted")
            for theme in themes:
                self.assertIn(
                    f'data-theme="{theme["name"]}"', self.html, f"{theme['name']} is built but not selectable"
                )

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
